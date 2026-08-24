"""
Stage 1 — classical dark-spot detection on SAR backscatter.

This is the guaranteed path. It has no learned weights, no training data and no
GPU, so it cannot fail on demo day. The U-Net in Phase 7 is an upgrade layered
on top of the same interface, never a replacement for it.

The chain follows standard operational SAR oil-spill practice:

    speckle filter -> land/bright mask -> ADAPTIVE threshold -> morphology
    -> connected components -> contours -> per-region discrimination

The threshold is deliberately adaptive rather than global. Sentinel-1 scenes
carry a brightness ramp across the swath from the incidence-angle dependence of
backscatter, so a single global cut either misses dark regions on the bright
side of the swath or floods the dark side with false positives.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage

# Detector tunables. Surfaced in the API provenance block so every number on
# screen can be traced back to the parameters that produced it.
PARAMS = {
    "speckle": "lee_7x7",
    "speckle_window": 7,
    "background_window": 129,
    "threshold_k": 0.55,
    "min_area_px": 220,
    "morph_open_px": 3,
    "morph_close_px": 15,
    "contour_simplify_px": 2.0,
}


@dataclass
class Region:
    """One candidate dark region, before it is classified oil or look-alike."""

    id: int
    mask: np.ndarray
    contour: np.ndarray          # (N, 2) pixel coords, already simplified
    area_px: int
    perimeter_px: float
    # radiometry
    mean_db: float
    std_db: float
    background_db: float
    contrast_db: float           # background - inside; positive means darker
    variance_ratio: float        # inside std / background std; oil damps speckle
    edge_gradient: float         # mean |grad| on the boundary; oil edges are sharper
    # shape
    compactness: float
    elongation: float
    orientation_deg: float


def lee_filter(img: np.ndarray, size: int = 7) -> np.ndarray:
    """Lee adaptive speckle filter.

    A plain box blur would smear the slick boundary, which is precisely the
    feature the geometry readout depends on. Lee blends toward the local mean
    only where local variance is consistent with pure speckle, so homogeneous
    sea is smoothed hard while edges survive.
    """
    img = img.astype(np.float32)
    mean = ndimage.uniform_filter(img, size)
    sq_mean = ndimage.uniform_filter(img ** 2, size)
    var = np.maximum(sq_mean - mean ** 2, 0.0)

    overall = np.mean(var)
    weight = var / (var + overall + 1e-9)
    return mean + weight * (img - mean)


def bright_mask(db: np.ndarray) -> np.ndarray:
    """Mask land and hard targets (ships, rigs).

    The case study is open ocean so no coastline falls in frame, but vessels
    appear as bright point targets and must not anchor a dark-region boundary.
    Anything far above the scene's bright tail is excluded and dilated slightly
    to swallow its sidelobes.
    """
    thr = np.percentile(db, 99.5) + 1.5
    m = db > thr
    return ndimage.binary_dilation(m, np.ones((5, 5), bool))


def adaptive_dark_mask(db: np.ndarray, excluded: np.ndarray) -> np.ndarray:
    """Flag pixels significantly darker than their local background.

    A large-window local mean and standard deviation model the slowly varying
    sea state and the incidence ramp; anything more than k local standard
    deviations below that is a candidate.
    """
    w = PARAMS["background_window"]
    work = db.copy()
    # Excluded pixels must not drag the local statistics.
    work[excluded] = np.median(db)

    bg_mean = ndimage.uniform_filter(work, w)
    bg_sq = ndimage.uniform_filter(work ** 2, w)
    bg_std = np.sqrt(np.maximum(bg_sq - bg_mean ** 2, 1e-6))

    dark = work < (bg_mean - PARAMS["threshold_k"] * bg_std)
    return dark & ~excluded


def clean(mask: np.ndarray) -> np.ndarray:
    """Open to drop isolated speckle, close to bridge gaps, then fill holes.

    The closing kernel is deliberately large. A weakly damped region — exactly
    what a low-wind zone or biogenic slick is — thresholds into a patchy,
    ragged blob, and a ragged blob has a long convoluted perimeter that scores
    as ELONGATED. Left uncleaned, such a patch is misread as a discharge trail.
    Consolidating it first is what lets the shape term do its job.
    """
    o, c = PARAMS["morph_open_px"], PARAMS["morph_close_px"]
    m = mask.astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((o, o), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((c, c), np.uint8))
    return ndimage.binary_fill_holes(m.astype(bool))


def _shape_stats(ys: np.ndarray, xs: np.ndarray) -> tuple[float, float]:
    """Elongation and orientation from the second moments of the region."""
    if len(xs) < 3:
        return 1.0, 0.0
    c = np.cov(np.vstack([xs.astype(float), ys.astype(float)]))
    evals, evecs = np.linalg.eigh(c)
    lo, hi = float(max(evals[0], 1e-9)), float(max(evals[1], 1e-9))
    major = evecs[:, int(np.argmax(evals))]
    # Pixel rows increase southward, so negate dy to get a compass bearing.
    bearing = np.degrees(np.arctan2(major[0], -major[1])) % 180.0
    return float(np.sqrt(hi / lo)), float(bearing)


def extract_regions(db: np.ndarray, mask: np.ndarray, excluded: np.ndarray) -> list[Region]:
    """Turn the binary mask into measured candidate regions."""
    lab, n = ndimage.label(mask)
    if n == 0:
        return []

    grad = np.hypot(*np.gradient(db))
    regions: list[Region] = []

    for i in range(1, n + 1):
        rm = lab == i
        area = int(rm.sum())
        if area < PARAMS["min_area_px"]:
            continue

        cnts, _ = cv2.findContours(rm.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = max(cnts, key=cv2.contourArea)
        peri = float(cv2.arcLength(cnt, True))
        if peri <= 0:
            continue
        approx = cv2.approxPolyDP(cnt, PARAMS["contour_simplify_px"], True).reshape(-1, 2)
        if len(approx) < 3:
            continue

        # Local background: an annulus around the region, excluding other
        # candidates so one dark patch cannot bias its neighbour's contrast.
        grown = ndimage.binary_dilation(rm, np.ones((41, 41), bool))
        ring = grown & ~ndimage.binary_dilation(rm, np.ones((11, 11), bool))
        ring &= ~mask & ~excluded
        if ring.sum() < 50:
            ring = ~mask & ~excluded

        inside, around = db[rm], db[ring]
        boundary = rm ^ ndimage.binary_erosion(rm)

        ys, xs = np.nonzero(rm)
        elong, orient = _shape_stats(ys, xs)

        regions.append(Region(
            id=i,
            mask=rm,
            contour=approx,
            area_px=area,
            perimeter_px=peri,
            mean_db=float(inside.mean()),
            std_db=float(inside.std()),
            background_db=float(around.mean()),
            contrast_db=float(around.mean() - inside.mean()),
            variance_ratio=float(inside.std() / (around.std() + 1e-9)),
            edge_gradient=float(grad[boundary].mean()) if boundary.any() else 0.0,
            compactness=float(4 * np.pi * area / (peri ** 2)),
            elongation=elong,
            orientation_deg=orient,
        ))

    return regions


# ---------------------------------------------------------------------------
# Discrimination
# ---------------------------------------------------------------------------

def classify(r: Region) -> tuple[bool, float, str, dict[str, float]]:
    """Decide oil vs look-alike, with a confidence and a stated reason.

    No learned weights: these are the physical discriminators the SAR
    oil-spill literature actually uses, each scored 0-1 and averaged.

      contrast       mineral oil damps Bragg backscatter hard, typically 5-10 dB
                     below the surrounding sea. Biogenic films and low-wind
                     patches are darker too, but much less so.
      variance ratio oil suppresses the small-scale roughness that produces
                     speckle, so the damped patch is not just darker but
                     SMOOTHER. This is the single most useful separator, since a
                     low-wind zone is dark while remaining as speckled as the sea.
      shape          an underway discharge is a long thin trail. Low-wind zones
                     and biogenic slicks are blobby. Compactness near 1 argues
                     strongly against a vessel discharge.
      edge sharpness an oil boundary is a sharp discontinuity; a wind-driven
                     roughness gradient fades.
    """
    # Each term saturates at a physically motivated value.
    s_contrast = float(np.clip((r.contrast_db - 2.0) / 6.0, 0, 1))
    s_variance = float(np.clip((1.0 - r.variance_ratio) / 0.5, 0, 1))
    s_shape = float(np.clip((0.55 - r.compactness) / 0.45, 0, 1))
    s_edge = float(np.clip((r.edge_gradient - 0.15) / 0.5, 0, 1))

    score = 0.34 * s_contrast + 0.31 * s_variance + 0.23 * s_shape + 0.12 * s_edge
    is_oil = score >= 0.45
    evidence = {"contrast": s_contrast, "variance": s_variance, "shape": s_shape, "edge": s_edge}

    if is_oil:
        reason = (
            f"Damping {r.contrast_db:.1f} dB below local background with speckle variance "
            f"at {r.variance_ratio:.2f} of ambient, and an elongated "
            f"{r.elongation:.0f}:1 form consistent with an underway discharge."
        )
    else:
        bits = []
        if r.compactness > 0.45:
            bits.append(f"compact form (compactness {r.compactness:.2f}) rather than a trail")
        if r.variance_ratio > 0.75:
            bits.append(
                f"speckle variance {r.variance_ratio:.2f} of ambient, so the surface is dark "
                f"but still rough — characteristic of a low-wind zone, not a damped oil film"
            )
        if r.contrast_db < 4.0:
            bits.append(f"weak damping at only {r.contrast_db:.1f} dB below background")
        if r.edge_gradient < 0.25:
            bits.append("soft boundary gradient rather than a sharp oil edge")
        reason = (bits[0][0].upper() + bits[0][1:] + (
            "; " + "; ".join(bits[1:]) if len(bits) > 1 else "")) if bits else \
            "Failed the combined oil-likelihood threshold."

    return is_oil, round(float(np.clip(score, 0, 1)), 3), reason, evidence


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def detect(db: np.ndarray) -> tuple[
    list[tuple[Region, float, str, dict[str, float]]],
    list[tuple[Region, float, str, dict[str, float]]],
    list[dict],
]:
    """Run the full chain.

    Returns (oil, lookalikes, timings), each candidate paired with its
    confidence and the reason it was kept or rejected.
    """
    steps: list[dict] = []

    def step(name: str, fn, detail: str | None = None):
        t = time.perf_counter()
        out = fn()
        steps.append({
            "name": name,
            "duration_ms": round((time.perf_counter() - t) * 1000, 1),
            "detail": detail,
        })
        return out

    filtered = step(f"speckle filter (Lee {PARAMS['speckle_window']}x{PARAMS['speckle_window']})",
                    lambda: lee_filter(db, PARAMS["speckle_window"]))
    excluded = step("land / hard-target mask", lambda: bright_mask(filtered),
                    "bright returns and their sidelobes")
    dark = step(f"adaptive threshold (local mean - {PARAMS['threshold_k']}σ)",
                lambda: adaptive_dark_mask(filtered, excluded),
                f"{PARAMS['background_window']} px background window")
    cleaned = step("morphology (open then close)", lambda: clean(dark))
    regions = step("connected components + contours",
                   lambda: extract_regions(filtered, cleaned, excluded))
    steps[-1]["detail"] = f"{len(regions)} candidate regions"

    t = time.perf_counter()
    oil, looks = [], []
    for r in regions:
        is_oil, conf, reason, evidence = classify(r)
        (oil if is_oil else looks).append((r, conf, reason, evidence))
    oil.sort(key=lambda x: -x[0].area_px)
    looks.sort(key=lambda x: -x[0].area_px)
    steps.append({
        "name": "look-alike discrimination",
        "duration_ms": round((time.perf_counter() - t) * 1000, 1),
        "detail": f"{len(oil)} oil, {len(looks)} rejected",
    })

    return oil, looks, steps
