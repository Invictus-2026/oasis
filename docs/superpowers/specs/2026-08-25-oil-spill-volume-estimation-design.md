# Oil spill volume estimation — design

Status: approved, not yet implemented
Date: 2026-08-25

## Problem

SpillTrace (`docs/PIPELINE.md`) currently has no volume estimate anywhere in
the pipeline. All five existing stages report area (km²), age (hours), drift
(containment cones) or attribution (vessel ranking) — never volume. There is
no thickness or volume ground truth anywhere in the project's data (not in
the Kaggle U-Net training set, not in the frozen `gom-2023-06-15` case
study), so a literal supervised "trained volume model" cannot be built with
what exists today.

## Decision

Ship a physical, literature-grounded volume **estimator** (no new training
data, no new model checkpoint) rather than waiting on a labeled thickness
dataset that may not be obtainable before the deadline. This mirrors the
project's existing convention for `age.py` (§4 of `PIPELINE.md`): a bounded
range, a stated method, and `confidence: "low"` unconditionally, not a false-
precision point number.

Scope, per explicit user decisions during brainstorming:
- **Classical detector only.** The classical path is the primary, demo-safe
  path (0.878 IoU) and already computes per-region `contrast_db` — the exact
  signal thickness banding needs. U-Net stays untouched; its `Region`
  objects don't carry the per-pixel data this needs, and it already carries
  a documented 2x area over-estimate (§3.6) that a volume number would
  inherit.
- **Backend/schema only, no frontend/UI this pass.** The number lands in the
  API response schema; wiring it into the dashboard is separate follow-up
  work.

## The physical link

SAR carries no color information, only backscatter damping (dB). The
literature's standard operational scale for damping-to-thickness in the
optical/visual domain is the **Bonn Agreement Oil Appearance Code (BAOAC)**,
confirmed against the primary source during this session:

| Code | Appearance | Thickness | Litres/km² |
|---|---|---|---|
| 1 | Sheen | 0.04–0.30 µm | 40–300 |
| 2 | Rainbow | 0.30–5.0 µm | 300–5,000 |
| 3 | Metallic | 5.0–50 µm | 5,000–50,000 |
| 4 | Discontinuous true colour | 50–200 µm | 50,000–200,000 |
| 5 | Continuous true colour | >200 µm | >200,000 |

Sources: [Bonn Agreement BAOAC status report](https://www.bonnagreement.org/site/assets/files/3952/current-status-report-final-19jan07.pdf),
[MUMM — BA oil appearance code](https://odnature.naturalsciences.be/mumm/en/national/ba-oil-appearance-code).

BAOAC is defined for visual/optical appearance, not SAR backscatter — using
it here is a deliberate proxy, stated as such in the docs, not a validated
equivalence (same epistemic honesty as the U-Net's dB→8-bit domain-shift
bridge in §3.4 of `PIPELINE.md`).

`classical.py`'s existing `classify()` already treats `contrast_db` on an
operative 2–8 dB scale: `s_contrast = clip((contrast_db - 2.0) / 6.0, 0, 1)`
saturates at 8 dB. That saturation point is the honest admission that SAR
damping can't keep resolving "thicker" past some point — so the 5 BAOAC
codes collapse into **3 SAR-resolvable bins** over that same scale, reusing
the existing thresholds rather than inventing new ones:

| Bin | contrast_db (background − pixel) | BAOAC codes spanned | Thickness range |
|---|---|---|---|
| thin | 2.0 – 4.0 dB | 1–2 (sheen/rainbow) | 0.04–5.0 µm |
| moderate | 4.0 – 6.0 dB | 3 (metallic) | 5.0–50 µm |
| thick | ≥ 6.0 dB | 4–5 (true colour) | 50–200 µm |

The `thick` bin's 200 µm upper bound is a stated **floor, not a ceiling**:
SAR damping saturates, so a region in this bin could physically be far
thicker (and voluminous) than 200 µm implies. The max volume figure is
therefore a documented underestimate for any spill with a `thick`-banded
core, not a true upper bound. This must be stated on screen wherever the
number is shown (future UI work) and in `PIPELINE.md`.

## Per-pixel, not per-region

A real slick isn't one uniform thickness — a discharge trail typically has a
thicker core and a thin sheen halo. `extract_regions()` in `classical.py`
already has the filtered dB raster and each region's mask in scope when it
computes the existing aggregate stats (`mean_db`, `background_db`,
`contrast_db`, etc.). Per-pixel banding is a few added lines in the same
loop — no new raster pass, no new file read.

## The volume identity

```
m³ = area_km² × thickness_µm
```

This is exact, not an approximation: 1 km² = 10⁶ m², 1 µm = 10⁻⁶ m, and the
two powers of ten cancel. No unit-conversion bug surface.

Barrels: `barrels = m³ / 0.158987` (1 barrel = 0.158987 m³, standard oil
barrel conversion).

## Component design

### 1. `backend/app/detection/classical.py`

- Add `THICKNESS_BANDS` module-level constant next to `PARAMS`, so it's
  surfaced the same way tunables already are — e.g.:
  ```python
  THICKNESS_BANDS = [
      # (name, db_min, db_max_or_None, thickness_min_um, thickness_max_um)
      ("thin",     2.0, 4.0, 0.04, 5.0),
      ("moderate", 4.0, 6.0, 5.0,  50.0),
      ("thick",    6.0, None, 50.0, 200.0),
  ]
  ```
- In `extract_regions()`, where `inside = db[rm]` is already computed:
  compute per-pixel damping `around.mean() - inside` (background scalar
  minus each pixel's dB value — reuses the same `around`/`ring` background
  already computed for `contrast_db`), bin each pixel into one of
  `THICKNESS_BANDS` (or "below-threshold": damping < 2.0 dB, which can occur
  for edge/boundary pixels inside a region whose *mean* clears 2.0 dB even
  if not every pixel does — those pixels contribute zero volume, not an
  error).
- Add `band_px: dict[str, int]` field to the `Region` dataclass, populated
  in `extract_regions()`, one entry per band name in `THICKNESS_BANDS` plus
  a pixel count.

### 2. `backend/app/detection/volume.py` (new)

Pure function, no I/O, mirrors `age.py`'s shape:

```python
def estimate(band_px: dict[str, int], pixel_area_km2: float) -> dict | None:
    """Bonn Agreement Oil Appearance Code thickness bands, driven by
    per-pixel SAR backscatter damping. Deliberately a range: SAR damping
    saturates for thick films, so the top band's max is a floor, not a
    ceiling. confidence is always "low" -- literature-typical band
    boundaries, not fit against this project's own labeled data, since no
    thickness ground truth exists anywhere in the pipeline."""
```

- Converts `band_px[name]` → `area_km2 = count * pixel_area_km2` per band.
- `min_m3 = Σ area_km2_i * thickness_min_um_i`, `max_m3` analogous with
  `thickness_max_um_i`, `mid_m3` with the per-band midpoint.
- `min_barrels`/`max_barrels` via the barrel conversion.
- `method_note`: prose narrating which bands dominated by area, e.g. "62%
  of the mapped extent falls in the 'thin' sheen/rainbow band (0.04-5 µm),
  31% 'moderate' metallic (5-50 µm), 7% 'thick' true-colour (≥50 µm, floor
  only — SAR damping saturates above this)." — same pattern as
  `age.py`'s `method_note`.
- Returns `None` if `band_px` is empty/all-zero (defensive, mirrors how
  `age.estimate` can return `None`).

### 3. `backend/app/core/schemas.py`

New model, structurally parallel to `AgeEstimate`:

```python
class VolumeEstimate(BaseModel):
    """Bonn Agreement Oil Appearance Code thickness bands, driven by
    per-pixel SAR backscatter damping. Deliberately a range, and the top
    band's max is a floor not a ceiling -- SAR damping saturates. Like
    AgeEstimate, confidence is always "low": band boundaries are
    literature-typical, not fit against this project's own labeled data."""

    min_m3: float
    mid_m3: float
    max_m3: float
    min_barrels: float
    max_barrels: float
    confidence: Literal["low", "medium", "high"] = "low"
    method_note: str
    band_areas_km2: dict[str, float]
```

Add `volume: VolumeEstimate | None = None` to `Slick` (same optionality
pattern as `age`).

### 4. `backend/app/detection/pipeline.py`

In the `oil` loop in `run()`, after `g = geometry.describe(r, bundle)`:

```python
v = (
    volume_mod.estimate(r.band_px, bundle.pixel_area_km2())
    if method is DetectionMethod.classical
    else None
)
```

pass `volume=VolumeEstimate(**v) if v else None` into the `Slick(...)`
constructor. Import `volume as volume_mod` alongside the existing
`from app.detection import age as age_mod`.

### 5. `backend/tests/test_detection.py`

Add assertions to the existing classical-detector test (or a new test
function following the same fixture pattern):
- `slick.volume is not None` for the classical path on the frozen case.
- `0 <= volume.min_m3 <= volume.mid_m3 <= volume.max_m3`.
- `sum(volume.band_areas_km2.values())` is between 0 and the slick's own
  `geometry.area_km2` inclusive — never exceeds it (would mean
  double-counting pixels across bands), and for the frozen case where region
  means clear the 2.0 dB floor by a wide margin, expect it close to the
  full area with only a thin edge-pixel margin excluded. Below-threshold
  edge pixels (mean region damping clears 2.0 dB but individual boundary
  pixels don't) are legitimately excluded from every band, so this is a
  bound, not an exact-equality check.
- U-Net path: `slick.volume is None` (explicit, not just absence of a
  positive assertion — pins the "classical only" scope decision so a future
  change can't silently regress it unnoticed, matching the project's stated
  rationale for why `detection_iou >= 0.80` is a pinned regression floor).

### 6. `docs/PIPELINE.md`

New §2.4 "Thickness/volume estimation (BAOAC proxy)" under the classical
detector section (§2), same rigor as the rest of the document:
- The algorithm as described above.
- The BAOAC citation and table.
- Explicit statement: "SAR carries no color information; BAOAC is an
  optical/visual standard used here as a physically-motivated proxy via
  backscatter damping, not a validated equivalence."
- Explicit statement: "The top band's 200 µm ceiling is a floor on true
  thickness, not a cap — SAR damping saturates above roughly 6-8 dB of
  contrast, so `max_m3` for any spill with a `thick`-banded core is itself
  an underestimate."
- `confidence: "low"`, unconditionally, stated the same way §4.2 states it
  for age, with the same reasoning: literature-typical band boundaries, not
  fit against this project's own labeled data (none exists).
- Add a row to the reproduction commands in §8 once the test lands.

## Explicitly out of scope for this pass

- U-Net path (no `band_px` plumbing added there).
- Frontend/dashboard surfacing (schema + API only).
- Any new training data, model checkpoint, or ground-truth calibration.
- Per-pixel thickness *beyond* the 3-bin proxy (e.g. a continuous
  regression) — not supportable without validated backscatter-to-thickness
  calibration data, which doesn't exist for this project.

## Testing strategy

Unit-level: `volume.estimate()` is a pure function over `band_px` +
`pixel_area_km2` — straightforward to test in isolation with synthetic
`band_px` dicts before wiring into the full pipeline (TDD-appropriate).
Integration-level: the `test_detection.py` additions above, run against the
frozen `gom-2023-06-15` case bundle exactly like the existing IoU/precision/
recall assertions.
