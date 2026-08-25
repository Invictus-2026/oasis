# Oil Spill Volume Estimation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Bonn Agreement Oil Appearance Code (BAOAC) proxy volume estimate to the classical detector's output, without any new training data or model.

**Architecture:** Backscatter damping (dB) is binned per-pixel into 3 SAR-resolvable thickness bands (reusing `classify()`'s existing 2.0/8.0 dB operative scale), each band mapped to a literature thickness range from BAOAC, and volume computed as `area_km2 * thickness_um` (exact unit identity) summed across bands, min-to-max. Classical detector only; U-Net stays untouched.

**Tech Stack:** Python 3.12, numpy, pydantic (existing backend stack — no new dependencies).

**Spec:** `docs/superpowers/specs/2026-08-25-oil-spill-volume-estimation-design.md`

## Global Constraints

- No new training data, model checkpoint, or ground-truth calibration — this is a physical estimator, not a trained model.
- Classical detector only. U-Net's `Slick.volume` must stay `None` — its area is a documented ~2x over-estimate (`docs/PIPELINE.md` §3.6) that a volume figure would silently inherit.
- `VolumeEstimate.confidence` is `"low"` unconditionally, same convention as `AgeEstimate.confidence` in `backend/app/detection/age.py` — literature-typical band boundaries, not fit against project data.
- BAOAC thickness table (verified against https://www.bonnagreement.org/site/assets/files/3952/current-status-report-final-19jan07.pdf): code 1 sheen 0.04–0.30 µm, code 2 rainbow 0.30–5.0 µm, code 3 metallic 5.0–50 µm, code 4 discontinuous true colour 50–200 µm, code 5 continuous true colour >200 µm.
- Volume identity: `m3 = area_km2 * thickness_um` (exact — the two powers of ten cancel). Barrel conversion: `barrels = m3 / 0.158987`.
- Tests run via `cd backend && .venv/bin/python -m pytest <path> -v` (existing project venv, already provisioned).

---

## File Structure

- **`backend/app/detection/volume.py`** (new) — pure function `estimate(band_px, pixel_area_km2) -> dict | None`. No I/O, no dependency on `classical.py` or the case bundle. Owns the BAOAC thickness lookup and the volume/barrel math.
- **`backend/app/detection/classical.py`** (modify) — add `DAMPING_BINS` constant and `band_pixel_counts()` function; add `band_px: dict[str, int]` field to the `Region` dataclass; wire the new function into `extract_regions()`. Owns the pixel-level physics (dB → band name), same responsibility split as the file already has for `contrast_db`/`variance_ratio`/etc.
- **`backend/app/core/schemas.py`** (modify) — add `VolumeEstimate` model (parallel to `AgeEstimate`) and `volume: VolumeEstimate | None = None` on `Slick`.
- **`backend/app/detection/pipeline.py`** (modify) — call `volume.estimate()` for the classical path only, attach to each `Slick`.
- **`backend/tests/test_volume.py`** (new) — unit tests for `volume.estimate()` against synthetic `band_px` dicts.
- **`backend/tests/test_classical_bands.py`** (new) — unit tests for `band_pixel_counts()` against synthetic numpy arrays. Kept out of `test_detection.py` deliberately: that file has a module-level `pytestmark = pytest.mark.skipif(...)` gating every test on the case bundle existing, but this is a pure function that needs no bundle.
- **`backend/tests/test_detection.py`** (modify) — add integration assertions against the frozen case bundle, following the file's existing fixture pattern.
- **`docs/PIPELINE.md`** (modify) — new §2.4 documenting the estimator with the same rigor as the rest of the doc, plus a reproduction command in §8.

---

## Task 1: `volume.py` — the pure BAOAC volume estimator

**Files:**
- Create: `backend/app/detection/volume.py`
- Test: `backend/tests/test_volume.py`

**Interfaces:**
- Produces: `volume.BAND_THICKNESS_UM: dict[str, tuple[float, float]]` with keys `"thin"`, `"moderate"`, `"thick"` — later tasks (`classical.py`'s `DAMPING_BINS`) must use these exact three names. `volume.M3_PER_BARREL: float = 0.158987`. `volume.estimate(band_px: dict[str, int], pixel_area_km2: float) -> dict | None`, returning `None` when `band_px` is empty or all-zero, otherwise a dict with keys `min_m3`, `mid_m3`, `max_m3`, `min_barrels`, `max_barrels`, `confidence`, `method_note`, `band_areas_km2` — this exact key set is what Task 3 passes into `VolumeEstimate(**v)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_volume.py`:

```python
"""Unit tests for the BAOAC-proxy volume estimator
(backend/app/detection/volume.py). Pure-function tests against synthetic
band_px dicts -- no case bundle needed.
"""

import pytest

from app.detection import volume


def test_returns_none_for_empty_bands():
    assert volume.estimate({}, pixel_area_km2=0.01) is None


def test_returns_none_when_all_bands_are_zero():
    assert volume.estimate({"thin": 0, "moderate": 0, "thick": 0}, pixel_area_km2=0.01) is None


def test_volume_identity_area_times_thickness():
    """m3 = area_km2 * thickness_um is exact; verify with a single band and
    hand-computed expected bounds."""
    # 100 px * 0.01 km2/px = 1.0 km2, all in the "thin" band (0.04-5.0 um).
    result = volume.estimate({"thin": 100}, pixel_area_km2=0.01)
    assert result is not None
    assert result["min_m3"] == pytest.approx(1.0 * 0.04, rel=1e-6)
    assert result["max_m3"] == pytest.approx(1.0 * 5.0, rel=1e-6)
    assert result["mid_m3"] == pytest.approx(1.0 * (0.04 + 5.0) / 2.0, rel=1e-6)


def test_min_mid_max_are_ordered():
    result = volume.estimate({"thin": 40, "moderate": 30, "thick": 10}, pixel_area_km2=0.02)
    assert result is not None
    assert result["min_m3"] <= result["mid_m3"] <= result["max_m3"]


def test_barrels_conversion():
    result = volume.estimate({"moderate": 50}, pixel_area_km2=0.01)
    assert result is not None
    assert result["min_barrels"] == pytest.approx(result["min_m3"] / 0.158987, rel=1e-6)
    assert result["max_barrels"] == pytest.approx(result["max_m3"] / 0.158987, rel=1e-6)


def test_band_areas_sum_to_total_area():
    result = volume.estimate({"thin": 10, "moderate": 20, "thick": 5}, pixel_area_km2=0.5)
    assert result is not None
    assert sum(result["band_areas_km2"].values()) == pytest.approx(35 * 0.5, rel=1e-6)


def test_confidence_is_always_low():
    result = volume.estimate({"thin": 5}, pixel_area_km2=1.0)
    assert result is not None
    assert result["confidence"] == "low"


def test_method_note_mentions_baoac_and_floor_caveat():
    result = volume.estimate({"thick": 5}, pixel_area_km2=1.0)
    assert result is not None
    assert "Bonn Agreement" in result["method_note"]
    assert "floor" in result["method_note"]


def test_unknown_band_name_is_ignored():
    """band_px could in principle carry a name outside BAND_THICKNESS_UM --
    must not crash, and must not silently invent a thickness for it."""
    result = volume.estimate({"thin": 10, "mystery": 999}, pixel_area_km2=0.01)
    assert result is not None
    assert "mystery" not in result["band_areas_km2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_volume.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.detection.volume'` (or `ImportError`).

- [ ] **Step 3: Write the implementation**

Create `backend/app/detection/volume.py`:

```python
"""
Thickness/volume estimation via the Bonn Agreement Oil Appearance Code (BAOAC).

SAR carries no colour information, only backscatter damping (dB). BAOAC is a
visual/optical standard (confirmed against the primary source,
https://www.bonnagreement.org/site/assets/files/3952/current-status-report-final-19jan07.pdf)
used here as a physically-motivated proxy, not a validated equivalence -- the
same epistemic status as the U-Net's dB-to-8-bit domain-shift bridge
(unet.py's _to_rgb_uint8).

classify() in classical.py already treats contrast_db on an operative 2-8 dB
scale (s_contrast saturates at 8 dB). BAOAC's five appearance codes collapse
into three SAR-resolvable bands over that same scale, matching the per-pixel
binning classical.py's band_pixel_counts() computes:

    thin      0.04-5.0   um  (BAOAC codes 1-2: sheen/rainbow)
    moderate  5.0-50.0   um  (BAOAC code 3: metallic)
    thick     50.0-200.0 um  (BAOAC codes 4-5: true colour -- FLOOR, not
                              ceiling: SAR damping saturates, so a region in
                              this band could physically be far thicker, and
                              more voluminous, than 200 um implies)

The volume identity is exact, not approximate: 1 km^2 = 1e6 m^2 and
1 um = 1e-6 m, so the two powers of ten cancel and

    volume_m3 = area_km2 * thickness_um
"""

from __future__ import annotations

# band name -> (thickness_min_um, thickness_max_um), collapsed from BAOAC
# codes 1-2 (thin), 3 (moderate), 4-5 (thick). Names must match the bands
# classical.DAMPING_BINS / band_pixel_counts() produce.
BAND_THICKNESS_UM: dict[str, tuple[float, float]] = {
    "thin": (0.04, 5.0),
    "moderate": (5.0, 50.0),
    "thick": (50.0, 200.0),
}

M3_PER_BARREL = 0.158987


def estimate(band_px: dict[str, int], pixel_area_km2: float) -> dict | None:
    """Volume range from per-band pixel counts, or None if nothing is banded.

    Deliberately a range, not a point: min uses each band's minimum
    literature thickness, max uses each band's maximum. The "thick" band's
    max is a floor on true thickness (see module docstring), so max_m3 is
    itself a documented underestimate for any spill with a thick-banded
    core. confidence is always "low", like age.py's AgeEstimate: band
    boundaries are literature-typical, not fit against this project's own
    labeled data, since no thickness ground truth exists anywhere in the
    pipeline.
    """
    if sum(band_px.values()) <= 0:
        return None

    band_areas_km2: dict[str, float] = {}
    min_m3 = mid_m3 = max_m3 = 0.0
    for name, count in band_px.items():
        if count <= 0 or name not in BAND_THICKNESS_UM:
            continue
        area_km2 = count * pixel_area_km2
        band_areas_km2[name] = area_km2
        t_min, t_max = BAND_THICKNESS_UM[name]
        min_m3 += area_km2 * t_min
        mid_m3 += area_km2 * (t_min + t_max) / 2.0
        max_m3 += area_km2 * t_max

    if not band_areas_km2:
        return None

    total_area_km2 = sum(band_areas_km2.values())
    note_bits = ", ".join(
        f"{100.0 * a / total_area_km2:.0f}% '{name}' "
        f"({BAND_THICKNESS_UM[name][0]:g}-{BAND_THICKNESS_UM[name][1]:g} um)"
        for name, a in sorted(band_areas_km2.items(), key=lambda kv: -kv[1])
    )

    return {
        "min_m3": round(min_m3, 1),
        "mid_m3": round(mid_m3, 1),
        "max_m3": round(max_m3, 1),
        "min_barrels": round(min_m3 / M3_PER_BARREL, 1),
        "max_barrels": round(max_m3 / M3_PER_BARREL, 1),
        "confidence": "low",
        "band_areas_km2": {k: round(v, 4) for k, v in band_areas_km2.items()},
        "method_note": (
            "Bonn Agreement Oil Appearance Code proxy, not a calibrated measurement -- "
            "BAOAC is a visual/optical standard; SAR backscatter damping is used here as "
            f"a physically-motivated stand-in, not a validated equivalence. Mapped extent: "
            f"{note_bits}. The 'thick' band's 200 um ceiling is a floor on true thickness, "
            "not a cap: SAR damping saturates above roughly 6-8 dB of contrast, so max_m3 "
            "for a spill with a thick-banded core is itself an underestimate."
        ),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_volume.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/detection/volume.py backend/tests/test_volume.py
git commit -m "Add BAOAC-proxy volume estimator (pure function, no wiring yet)"
```

---

## Task 2: `classical.py` — per-pixel thickness-band binning

**Files:**
- Modify: `backend/app/detection/classical.py`
- Test: `backend/tests/test_classical_bands.py`

**Interfaces:**
- Consumes: nothing new from Task 1 directly (band *names* must match Task 1's `BAND_THICKNESS_UM` keys: `"thin"`, `"moderate"`, `"thick"`, but this module has no import dependency on `volume.py`).
- Produces: `classical.DAMPING_BINS: list[tuple[str, float, float | None]]` — `(name, damping_min_db, damping_max_db_or_None)`. `classical.band_pixel_counts(inside: np.ndarray, background_db: float) -> dict[str, int]`. `Region.band_px: dict[str, int]` — new field, populated by `extract_regions()`. Task 3 reads `region.band_px` directly.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_classical_bands.py`:

```python
"""Unit tests for classical.py's per-pixel thickness-band binning (feeds
volume.py). Pure numpy, no case bundle needed -- deliberately not in
test_detection.py, which skips every test when the case bundle is absent.
"""

import numpy as np

from app.detection.classical import DAMPING_BINS, band_pixel_counts


def test_bins_are_named_thin_moderate_thick_in_order():
    assert [b[0] for b in DAMPING_BINS] == ["thin", "moderate", "thick"]


def test_bins_are_contiguous():
    assert DAMPING_BINS[0][2] == DAMPING_BINS[1][1]  # thin's max == moderate's min
    assert DAMPING_BINS[1][2] == DAMPING_BINS[2][1]  # moderate's max == thick's min
    assert DAMPING_BINS[2][2] is None  # thick is open-ended


def test_pixels_below_the_floor_are_excluded_from_every_band():
    # background 10 dB, pixel 9 dB -> damping 1.0 dB, below the 2.0 dB floor
    # classify()'s own s_contrast term uses.
    inside = np.array([9.0, 9.0])
    counts = band_pixel_counts(inside, background_db=10.0)
    assert sum(counts.values()) == 0


def test_each_bin_boundary_lands_in_the_expected_band():
    # background 10 dB; pixel damping = 10 - pixel.
    inside = np.array([
        8.0,   # damping 2.0 -> thin (lower edge, inclusive)
        6.5,   # damping 3.5 -> thin
        6.0,   # damping 4.0 -> moderate (lower edge, inclusive)
        4.5,   # damping 5.5 -> moderate
        4.0,   # damping 6.0 -> thick (lower edge, inclusive)
        1.0,   # damping 9.0 -> thick
    ])
    counts = band_pixel_counts(inside, background_db=10.0)
    assert counts == {"thin": 2, "moderate": 2, "thick": 2}


def test_counts_sum_to_input_size_when_all_pixels_clear_the_floor():
    inside = np.full(50, 2.0)  # damping 8.0 for all -> all "thick"
    counts = band_pixel_counts(inside, background_db=10.0)
    assert sum(counts.values()) == 50
    assert counts["thick"] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_classical_bands.py -v`
Expected: FAIL — `ImportError: cannot import name 'DAMPING_BINS' from 'app.detection.classical'`.

- [ ] **Step 3: Write the implementation**

In `backend/app/detection/classical.py`, add the constant near `PARAMS` (after line 39, the closing `}` of `PARAMS`):

```python
# Per-pixel damping bins feeding the volume estimator (see volume.py). Reuses
# classify()'s own 2.0 dB contrast floor and 8.0 dB saturation point instead
# of inventing new thresholds -- that scale is already the honest statement
# of what SAR damping can and can't resolve. Names must match
# volume.BAND_THICKNESS_UM's keys.
DAMPING_BINS: list[tuple[str, float, float | None]] = [
    ("thin", 2.0, 4.0),
    ("moderate", 4.0, 6.0),
    ("thick", 6.0, None),
]
```

Add the `band_px` field to the `Region` dataclass (after `orientation_deg: float`, the last field):

```python
    orientation_deg: float
    band_px: dict[str, int]      # per-pixel thickness-band counts, see volume.py
```

Add the binning function after `_shape_stats` (before `extract_regions`):

```python
def band_pixel_counts(inside: np.ndarray, background_db: float) -> dict[str, int]:
    """Per-pixel damping binned into SAR-resolvable thickness bands.

    Pixels below the 2.0 dB floor classify()'s own s_contrast term uses
    contribute to no band. Their thickness is indistinguishable from noise,
    not zero -- reporting nothing is more honest than fabricating a
    thin-film volume for a boundary pixel that barely damps at all.
    """
    damping = background_db - inside
    counts = {name: 0 for name, _, _ in DAMPING_BINS}
    for name, lo, hi in DAMPING_BINS:
        if hi is None:
            counts[name] = int(np.sum(damping >= lo))
        else:
            counts[name] = int(np.sum((damping >= lo) & (damping < hi)))
    return counts
```

In `extract_regions()`, wire it in. Find this block (existing lines 178-199):

```python
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
```

Replace with:

```python
        inside, around = db[rm], db[ring]
        boundary = rm ^ ndimage.binary_erosion(rm)

        ys, xs = np.nonzero(rm)
        elong, orient = _shape_stats(ys, xs)
        background_db = float(around.mean())

        regions.append(Region(
            id=i,
            mask=rm,
            contour=approx,
            area_px=area,
            perimeter_px=peri,
            mean_db=float(inside.mean()),
            std_db=float(inside.std()),
            background_db=background_db,
            contrast_db=float(background_db - inside.mean()),
            variance_ratio=float(inside.std() / (around.std() + 1e-9)),
            edge_gradient=float(grad[boundary].mean()) if boundary.any() else 0.0,
            compactness=float(4 * np.pi * area / (peri ** 2)),
            elongation=elong,
            orientation_deg=orient,
            band_px=band_pixel_counts(inside, background_db),
        ))
```

(`background_db` is now computed once and reused for both `contrast_db` and the new binning call — no behavior change to `contrast_db`'s value, purely a small dedup.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_classical_bands.py -v`
Expected: PASS (5 tests).

Also run the existing classical-detector suite to confirm nothing broke:

Run: `cd backend && .venv/bin/python -m pytest tests/test_detection.py -q`
Expected: PASS (same as before this task — `band_px` is additive, `contrast_db`'s value is unchanged since it's the same `around.mean() - inside.mean()` computation, just pre-extracted into a variable).

- [ ] **Step 5: Commit**

```bash
git add backend/app/detection/classical.py backend/tests/test_classical_bands.py
git commit -m "Bin per-pixel SAR damping into thickness bands in extract_regions()"
```

---

## Task 3: Schema, pipeline wiring, integration tests, and docs

**Files:**
- Modify: `backend/app/core/schemas.py`
- Modify: `backend/app/detection/pipeline.py`
- Modify: `backend/tests/test_detection.py`
- Modify: `docs/PIPELINE.md`

**Interfaces:**
- Consumes: `volume.estimate(band_px, pixel_area_km2) -> dict | None` (Task 1), `Region.band_px` (Task 2), `CaseBundle.pixel_area_km2() -> float` (existing, `backend/app/core/case_store.py:86`).
- Produces: `schemas.VolumeEstimate` (pydantic model), `Slick.volume: VolumeEstimate | None`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_detection.py`, add near the top of the file, after the existing imports (the `from app.detection import age as age_mod` / `from app.detection import classical, pipeline` block):

```python
from app.detection import unet
```

Add these test functions at the end of the "characterisation" section (after `test_age_uses_width_not_total_area`, before the "determinism and speed" section comment):

```python
def test_slick_has_a_volume_estimate(result):
    v = result.slicks[0].volume
    assert v is not None
    assert 0 <= v.min_m3 <= v.mid_m3 <= v.max_m3
    assert v.confidence == "low"


def test_volume_band_areas_do_not_exceed_the_slick_area(result):
    """Edge pixels below the 2.0 dB floor are legitimately excluded from
    every band (see classical.band_pixel_counts), so this is a <=, not an
    exact match against geometry.area_km2."""
    v = result.slicks[0].volume
    total_band_area = sum(v.band_areas_km2.values())
    assert 0 < total_band_area <= result.slicks[0].geometry.area_km2 + 1e-6


def test_volume_barrels_are_consistent_with_m3(result):
    v = result.slicks[0].volume
    assert v.min_barrels == pytest.approx(v.min_m3 / 0.158987, rel=1e-3)
    assert v.max_barrels == pytest.approx(v.max_m3 / 0.158987, rel=1e-3)


def test_unet_slicks_have_no_volume_estimate(bundle):
    """Scope guard: volume estimation is classical-only by design. U-Net's
    area is a documented ~2x over-estimate (PIPELINE.md 3.6); a volume
    figure built on top of it would silently inherit that error."""
    if not unet.available():
        pytest.skip("no U-Net checkpoint available")
    from app.core.schemas import DetectionMethod
    result = pipeline.run(bundle, method=DetectionMethod.unet)
    for s in result.slicks:
        assert s.volume is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_detection.py -k volume -v`
Expected: FAIL — `AttributeError: 'Slick' object has no attribute 'volume'`.

- [ ] **Step 3: Write the implementation**

In `backend/app/core/schemas.py`, add `VolumeEstimate` right after the `AgeEstimate` class (before `class DetectionMethod(str, Enum):`):

```python
class VolumeEstimate(BaseModel):
    """Bonn Agreement Oil Appearance Code thickness bands, driven by
    per-pixel SAR backscatter damping. Deliberately a range, and the top
    band's max is a floor not a ceiling -- SAR damping saturates. Like
    AgeEstimate, confidence is always "low": band boundaries are
    literature-typical, not fit against this project's own labeled data,
    since no thickness ground truth exists anywhere in the pipeline."""

    min_m3: float
    mid_m3: float
    max_m3: float
    min_barrels: float
    max_barrels: float
    confidence: Literal["low", "medium", "high"] = "low"
    method_note: str
    band_areas_km2: dict[str, float]
```

Add the field to `Slick` (after `evidence: DetectionEvidence | None = None`):

```python
class Slick(BaseModel):
    id: str
    polygon: GeoJSON
    confidence: float = Field(ge=0.0, le=1.0)
    method: DetectionMethod
    geometry: SlickGeometry
    age: AgeEstimate | None = None
    evidence: DetectionEvidence | None = None
    volume: VolumeEstimate | None = None
```

In `backend/app/detection/pipeline.py`, update the import block:

```python
from app.core.schemas import (
    AgeEstimate,
    DetectionEvidence,
    DetectionMethod,
    DetectResponse,
    ProcessingStep,
    Provenance,
    RejectedLookalike,
    Slick,
    SlickGeometry,
    VolumeEstimate,
)
from app.detection import age as age_mod
from app.detection import classical, geometry, unet
from app.detection import volume as volume_mod
```

Update the `oil` loop in `run()`:

```python
    slicks: list[Slick] = []
    for i, (r, conf, _reason, evidence) in enumerate(oil, 1):
        g = geometry.describe(r, bundle)
        # Trail length from the major-axis extent, needed because age depends
        # on the slick's WIDTH, not its total area.
        length_km = _major_axis_km(r, bundle)
        a = age_mod.estimate(g["area_km2"], r.contrast_db, length_km)
        # Volume is classical-only: U-Net's area is a documented ~2x
        # over-estimate (PIPELINE.md 3.6), and a volume figure built on top
        # of it would silently inherit that error.
        v = (
            volume_mod.estimate(r.band_px, bundle.pixel_area_km2())
            if method is DetectionMethod.classical
            else None
        )
        slicks.append(Slick(
            id=f"slick-{i:03d}",
            polygon={"type": "Polygon", "coordinates": [geometry.contour_to_lonlat(r.contour, bundle)]},
            confidence=conf,
            method=method,
            geometry=SlickGeometry(**g),
            age=AgeEstimate(**a) if a else None,
            evidence=DetectionEvidence(**evidence),
            volume=VolumeEstimate(**v) if v else None,
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_detection.py tests/test_volume.py tests/test_classical_bands.py -v`
Expected: PASS, all tests including the pre-existing IoU/recall/precision/age suite (must still pass unchanged) and the new volume tests.

- [ ] **Step 5: Update the docs**

In `docs/PIPELINE.md`, add a new subsection after §2.3 ("Measured performance") and before §3 ("Stage 1b — U-Net"). Insert after the existing line `\`cd backend && .venv/bin/python -m pytest tests/test_detection.py -q\`.` and its preceding table, right before the `---` that precedes `## 3. Stage 1b`:

```markdown
### 2.4 Thickness/volume estimation (BAOAC proxy, classical path only)

Area alone cannot give a volume — a 1 mm sheen and a 10 cm slick can share
an identical SAR footprint. This stage adds a bounded volume range, using
the same "state a range, flag low confidence" convention §4 uses for age,
not a point number dressed up as precision.

**The proxy.** SAR carries no colour information, only backscatter damping
(dB). The literature's standard operational scale for damping-to-thickness
is visual, not radar: the **Bonn Agreement Oil Appearance Code (BAOAC)**,
confirmed against the primary source while writing this section
([bonnagreement.org](https://www.bonnagreement.org/site/assets/files/3952/current-status-report-final-19jan07.pdf)):

| Code | Appearance | Thickness | Litres/km² |
|---|---|---|---|
| 1 | Sheen | 0.04–0.30 µm | 40–300 |
| 2 | Rainbow | 0.30–5.0 µm | 300–5,000 |
| 3 | Metallic | 5.0–50 µm | 5,000–50,000 |
| 4 | Discontinuous true colour | 50–200 µm | 50,000–200,000 |
| 5 | Continuous true colour | >200 µm | >200,000 |

⚠️ BAOAC is a visual/optical standard. Using SAR backscatter damping as a
proxy for it is a deliberate, stated engineering choice, not a validated
equivalence — the same epistemic status as the U-Net's dB-to-8-bit
domain-shift bridge (§3.4).

**Collapsing 5 codes into 3 SAR-resolvable bands.** `classify()`'s own
`s_contrast` term already treats `contrast_db` on an operative 2–8 dB scale
(saturating at 8 dB) — that saturation point is the honest admission that
SAR damping stops resolving "thicker" past some level. So the 5 BAOAC codes
collapse into 3 bins over that same scale, reusing the existing thresholds:

| Bin | contrast_db (background − pixel) | BAOAC codes | Thickness |
|---|---|---|---|
| thin | 2.0–4.0 dB | 1–2 | 0.04–5.0 µm |
| moderate | 4.0–6.0 dB | 3 | 5.0–50 µm |
| thick | ≥6.0 dB | 4–5 | 50–200 µm |

The `thick` bin's 200 µm ceiling is a **floor on true thickness, not a
cap**: SAR damping saturates above roughly 6–8 dB of contrast, so `max_m3`
for any spill with a `thick`-banded core is itself a documented
underestimate, not an upper bound.

**Per-pixel, not per-region.** `classical.band_pixel_counts()` bins every
pixel inside a region individually (a real slick has a thicker core and a
thinner halo, not one uniform thickness) — implemented as a few added lines
in `extract_regions()`, no new raster pass.

**The volume identity.** `m3 = area_km2 * thickness_um` is exact, not
approximate: 1 km² = 10⁶ m² and 1 µm = 10⁻⁶ m, so the two powers of ten
cancel. Barrels: `barrels = m3 / 0.158987`.

**Scope: classical only.** U-Net's `Slick.volume` is always `None`. Its
`Region` objects technically carry `band_px` too (binning happens in the
shared `extract_regions()`), but `pipeline.py` deliberately does not build
a `VolumeEstimate` from them — U-Net's area is a documented ~2x
over-estimate (§3.6), and a volume figure on top of it would silently
inherit that error.

**Confidence is always `"low"`**, unconditionally — same convention as
§4.2's age estimate, and the same reason: the band boundaries are
literature-typical, not fit against this project's own labeled data, since
no thickness ground truth exists anywhere in the pipeline.

Reproduce: `cd backend && .venv/bin/python -m pytest tests/test_volume.py tests/test_classical_bands.py -q`
```

In §8 ("Reproducing the numbers in this document"), add a line after the existing classical detector test command:

```markdown
# Volume estimator — unit tests (pure function + per-pixel binning)
cd backend && .venv/bin/python -m pytest tests/test_volume.py tests/test_classical_bands.py -q
```

- [ ] **Step 6: Run the full backend test suite to confirm no regressions**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS, all tests (existing + new).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/schemas.py backend/app/detection/pipeline.py backend/tests/test_detection.py docs/PIPELINE.md
git commit -m "Wire BAOAC volume estimate into the classical detection response"
```

---

## Post-implementation check

After Task 3, `POST /api/detect {"method":"classical"}` responses will include a `volume` object per slick. Manually verify once with the running backend:

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000 &
curl -s -X POST localhost:8000/api/detect -H 'Content-Type: application/json' \
  -d '{"method":"classical"}' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['slicks'][0]['volume'])"
```

Expected: a dict with `min_m3`, `mid_m3`, `max_m3`, `min_barrels`, `max_barrels`, `confidence: "low"`, `method_note`, `band_areas_km2` — not `null`.
