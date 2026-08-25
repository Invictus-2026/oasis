"""
Stage 1 — optional learned detector (Phase 7 upgrade).

Loads ml/weights/unet_best.pth: a segmentation_models_pytorch U-Net with a
ResNet34/ImageNet-pretrained encoder, fine-tuned on the Kaggle "Deep-SAR
oil-spill segmentation (refined)" dataset (ALOS PALSAR / Sentinel-1, binary
oil vs. not-oil masks). See ml/train_unet_run.py for the training run that
produced it and ml/evaluate_unet.py for its held-out metrics.

This is an upgrade layered on top of the classical detector's interface
(classical.py), never a replacement for it — detect() returns the same
(oil, lookalikes, steps) shape pipeline.py already expects from
classical.detect(), so nothing downstream (geometry, age, drift) needs to
know which detector produced the mask.

Two honesty notes worth keeping in mind if this is questioned:

1. Domain shift. This checkpoint was trained on pre-normalized 8-bit chips
   from a *different* SAR collection than the frozen case study's raw
   calibrated dB raster (data/case/sar_db.npy). There is no verified
   colorimetric mapping between the two datasets' preprocessing, so a
   percentile stretch is used to bridge the value ranges below. That is a
   documented heuristic, not a validated equivalence.
2. Hybrid, not purely learned. The training data has no separate look-alike
   class, so on its own the network confidently flags round dark blobs
   (low-wind zones, biogenic slicks) as oil alongside real trails -- measured
   on the frozen case study, 100% recall but only 5.9% precision before this
   gate existed. A region is only reported as oil if, in addition to the
   network's probability, its shape is trail-like rather than round
   (compactness below SHAPE_COMPACTNESS_CUTOFF -- the same crossover
   classical.classify()'s own shape term uses). Shape only, not the full
   four-term classify() score: classify()'s variance term is calibrated
   against the classical detector's OWN region boundaries, and measured
   against a U-Net-shaped boundary it misfires (on this case study the real
   slick scored variance_ratio=2.6, i.e. "rougher than background" -- the
   physical opposite of oil damping -- a boundary-measurement artefact, not
   a real signal). Shape is unaffected by that mismatch and is the cleanest
   discriminator available here. Regions the network liked but the shape
   gate rejects are surfaced as rejected_lookalikes, same as the classical
   path, with the reason stated as an override.

   Caveat: this gate was validated against a single frozen case-study scene
   (one real slick, three false positives), not a labeled test set. Treat
   it as a documented, reasoned design choice, not a statistically
   validated one.
"""

from __future__ import annotations

import time
from functools import lru_cache

import numpy as np

from app.core import config
from app.detection.classical import PARAMS as CLASSICAL_PARAMS
from app.detection.classical import Region, bright_mask, classify, clean, extract_regions, lee_filter

WEIGHTS_PATH = config.WEIGHTS_DIR / "unet_best.pth"

PATCH_PX = 256
STRIDE_PX = 128  # 50% overlap, averaged on stitch to soften tile-seam artefacts
CONF_THRESHOLD = 0.5
SHAPE_COMPACTNESS_CUTOFF = 0.55  # same zero-crossing classify()'s own shape term uses
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

PARAMS = {
    "encoder": "resnet34",
    "encoder_weights_source": "imagenet",
    "trained_on": "kaggle:bakhtiyar2222/deep-sar-oil-spill-segmentation-refined",
    "patch_px": PATCH_PX,
    "stride_px": STRIDE_PX,
    "threshold": CONF_THRESHOLD,
    "speckle": CLASSICAL_PARAMS["speckle"],
    "min_area_px": CLASSICAL_PARAMS["min_area_px"],
}


def available() -> bool:
    return WEIGHTS_PATH.exists()


@lru_cache(maxsize=1)
def _load_model():
    import torch
    import segmentation_models_pytorch as smp

    ckpt = torch.load(WEIGHTS_PATH, map_location="cpu")
    model = smp.Unet(
        encoder_name=ckpt["encoder"],
        encoder_weights=None,  # loading trained weights next, no need to re-fetch ImageNet
        in_channels=3,
        classes=1,
    )
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    return model, ckpt


def _to_rgb_uint8(db: np.ndarray) -> np.ndarray:
    """Percentile-stretch the calibrated dB raster into an 8-bit grayscale
    image replicated across 3 channels, matching the visual-range input the
    checkpoint was trained on. See the domain-shift note in the module
    docstring."""
    lo, hi = np.percentile(db, [1.0, 99.0])
    stretched = np.clip((db - lo) / (hi - lo + 1e-9), 0.0, 1.0)
    gray = (stretched * 255).astype(np.uint8)
    return np.stack([gray, gray, gray], axis=-1)


def _tile_starts(length: int, patch: int, stride: int) -> list[int]:
    starts = list(range(0, max(length - patch, 0) + 1, stride))
    if not starts:
        return [0]
    if starts[-1] != length - patch:
        starts.append(length - patch)
    return starts


def _predict_prob_map(db: np.ndarray) -> np.ndarray:
    """Tiled inference with overlap-averaged stitching, so probabilities
    near tile boundaries don't show a seam."""
    import torch

    model, _ = _load_model()

    # The case-study scene is always >= PATCH_PX on both sides, but ad-hoc
    # user uploads (see api/upload.py) may not be. Reflect-pad up to at
    # least one full patch, run inference, then crop back to the original
    # size so callers never see the padding.
    orig_h, orig_w = db.shape
    pad_h = max(PATCH_PX - orig_h, 0)
    pad_w = max(PATCH_PX - orig_w, 0)
    if pad_h or pad_w:
        db = np.pad(db, ((0, pad_h), (0, pad_w)), mode="reflect")

    rgb = _to_rgb_uint8(db)
    h, w = db.shape

    ys = _tile_starts(h, PATCH_PX, STRIDE_PX)
    xs = _tile_starts(w, PATCH_PX, STRIDE_PX)

    patches, coords = [], []
    for y in ys:
        for x in xs:
            patch = rgb[y:y + PATCH_PX, x:x + PATCH_PX].astype(np.float32) / 255.0
            patch = (patch - IMAGENET_MEAN) / IMAGENET_STD
            patches.append(patch.transpose(2, 0, 1))
            coords.append((y, x))

    batch = torch.from_numpy(np.stack(patches).astype(np.float32))
    with torch.no_grad():
        logits = model(batch)
        probs = torch.sigmoid(logits).squeeze(1).numpy()

    prob_sum = np.zeros((h, w), dtype=np.float32)
    weight = np.zeros((h, w), dtype=np.float32)
    for (y, x), p in zip(coords, probs):
        prob_sum[y:y + PATCH_PX, x:x + PATCH_PX] += p
        weight[y:y + PATCH_PX, x:x + PATCH_PX] += 1.0

    prob = prob_sum / np.maximum(weight, 1e-9)
    return prob[:orig_h, :orig_w] if (pad_h or pad_w) else prob


def detect(db: np.ndarray) -> tuple[
    list[tuple[Region, float, str, dict[str, float]]],
    list[tuple[Region, float, str, dict[str, float]]],
    list[dict],
]:
    """Run the learned detector. Same (oil, lookalikes, steps) contract as
    classical.detect(), so pipeline.py can call either interchangeably."""
    steps: list[dict] = []

    def step(name, fn, detail: str | None = None):
        t = time.perf_counter()
        out = fn()
        steps.append({"name": name, "duration_ms": round((time.perf_counter() - t) * 1000, 1), "detail": detail})
        return out

    filtered = step(
        f"speckle filter (Lee {CLASSICAL_PARAMS['speckle_window']}x{CLASSICAL_PARAMS['speckle_window']})",
        lambda: lee_filter(db, CLASSICAL_PARAMS["speckle_window"]),
    )
    excluded = step("land / hard-target mask", lambda: bright_mask(filtered),
                     "bright returns and their sidelobes")
    prob = step(
        f"U-Net inference (tiled {PATCH_PX}px, {STRIDE_PX}px stride)",
        lambda: _predict_prob_map(filtered),
        f"checkpoint {WEIGHTS_PATH.name}",
    )
    binary = step(f"threshold (p > {CONF_THRESHOLD})", lambda: (prob > CONF_THRESHOLD) & ~excluded)
    cleaned = step("morphology (open then close)", lambda: clean(binary))
    regions = step("connected components + contours", lambda: extract_regions(filtered, cleaned, excluded))
    steps[-1]["detail"] = f"{len(regions)} candidate regions"

    t_gate = time.perf_counter()
    oil: list[tuple[Region, float, str, dict[str, float]]] = []
    looks: list[tuple[Region, float, str, dict[str, float]]] = []
    for r in regions:
        net_conf = float(np.clip(prob[r.mask].mean(), 0, 1))
        # classify()'s full weighted score is calibrated against the
        # classical detector's OWN region boundaries; against a U-Net mask
        # its variance term measures noise, not oil damping (verified: on
        # this case study the true slick scored variance_ratio=2.6, i.e.
        # "rougher than background", the physical opposite of damping -- a
        # boundary-measurement artefact, not a real signal). Shape is not
        # affected by that mismatch and is the cleanest discriminator this
        # detector has: round low-wind/biogenic blobs vs. elongated trails.
        # So the gate here is shape alone, using classify()'s own established
        # compactness crossover, not the full four-term formula.
        _, phys_score, phys_reason, evidence = classify(r)
        is_trail_shaped = r.compactness < SHAPE_COMPACTNESS_CUTOFF

        if is_trail_shaped:
            reason = (
                f"U-Net probability {net_conf:.2f} over a {r.area_px}px region; shape is trail-like "
                f"(compactness {r.compactness:.2f}, elongation {r.elongation:.0f}:1), not a round blob."
            )
            oil.append((r, round(net_conf, 3), reason, evidence))
        else:
            reason = (
                f"U-Net flagged this region with probability {net_conf:.2f}, but overridden as a "
                f"look-alike: compactness {r.compactness:.2f} is too round for a discharge trail "
                f"(cutoff {SHAPE_COMPACTNESS_CUTOFF}). {phys_reason.rstrip('.')}."
            )
            looks.append((r, round(1.0 - phys_score, 3), reason, evidence))

    oil.sort(key=lambda x: -x[0].area_px)
    looks.sort(key=lambda x: -x[0].area_px)
    steps.append({
        "name": "shape plausibility gate (compactness cutoff, reused from classical detector)",
        "duration_ms": round((time.perf_counter() - t_gate) * 1000, 1),
        "detail": f"{len(oil)} oil, {len(looks)} overridden as look-alike",
    })

    return oil, looks, steps
