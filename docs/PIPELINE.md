# SpillTrace — Model & Pipeline Reference

Every algorithm behind the dashboard: what it is, exactly how it's computed, what data
trained or calibrated it, what's been measured, what's still fixture data, and what to
build next. This is the doc to hand a technical judge, or to read before answering "how
does your model actually work?"

Nothing here is aspirational unless the section says so explicitly. Numbers were
re-measured against the frozen `gom-2023-06-15` case study while writing this file
(2026-08-24), not copied from an old run.

---

## 1. The five pipelines, at a glance

SpillTrace answers three questions (what, where/when, who) through five distinct
computational pipelines. Only two of them are learned models in the ML sense — the
other three are classical CV, a physical simulation, and a heuristic formula. All five
are documented here because "the ML pipeline" for this system is really "the analytical
pipeline," and conflating the two undersells the physics-based work and oversells the
one neural net.

| # | Pipeline | Kind | Status | File(s) |
|---|---|---|---|---|
| 1a | Classical dark-spot detector | Deterministic classical CV, no learned weights | **Real, primary path** | `backend/app/detection/classical.py` |
| 1b | U-Net segmentation detector | Learned model (CNN) | **Real, trained, gated by 1a's logic** | `backend/app/detection/unet.py`, `ml/train_unet_run.py` |
| 1c | Age estimation | Closed-form physical heuristic (Okubo 1971) | **Real** | `backend/app/detection/age.py` |
| 2 | Drift hindcast/forecast | Stochastic Lagrangian particle ensemble | **Real** | `backend/app/drift/lagrangian.py`, `cone.py`, `fields.py` |
| 3 | AIS attribution scoring | Weighted multi-factor score | **Not implemented — fixture data only** | `backend/app/core/fixtures.py` (real code would live in `backend/app/attribution/`, currently empty) |

Not covered below: `backend/app/api/scene.py` (SAR quicklook rendering) is display
processing — percentile stretch, gamma, colour ramp — not an analytical model, so it's
out of scope for this doc.

---

## 2. Stage 1a — Classical dark-spot detector (the guaranteed path)

**Why it exists first:** no learned weights, no training data, no GPU, deterministic —
it cannot fail on demo day the way a model checkpoint or a flaky inference server can.
Every later stage is layered on top of this interface, never a replacement for it. This
is the literal implementation of the project's design rule "fallback before headline."

### 2.1 Algorithm

A standard operational SAR oil-spill chain, six steps:

```
Lee speckle filter → land/bright-target mask → adaptive local threshold
  → morphology (open, close) → connected components + contours
  → per-region physical discrimination (oil vs look-alike)
```

1. **Lee adaptive speckle filter** (7×7 window). Blends each pixel toward the local mean
   in proportion to how consistent the local variance is with pure speckle — homogeneous
   sea gets smoothed hard, edges survive. A plain box blur would smear the boundary the
   geometry readout depends on.
2. **Land/bright-target mask.** Anything above the 99.5th percentile + 1.5 dB is excluded
   and dilated 5×5 to swallow sidelobes — vessels are bright point targets and must not
   anchor a dark-region boundary.
3. **Adaptive local threshold.** A pixel is a candidate if it's more than
   `k=0.55` local standard deviations below a 129×129-window local mean. Adaptive, not
   global, because Sentinel-1 GRD carries a brightness ramp across the swath from the
   incidence-angle dependence of backscatter — one global cut either misses the dark side
   or floods the bright side with false positives.
4. **Morphology.** Open (3px) drops isolated speckle; close (15px, deliberately large)
   bridges gaps in a weakly-damped region before its ragged perimeter gets misread as
   "elongated."
5. **Connected components + contours.** `cv2.findContours` per labelled blob, simplified
   to 2px tolerance, with a 220px minimum area floor.
6. **Per-region discrimination** (`classify()`) — the actual oil-vs-lookalike decision.

### 2.1b Morphology extraction (per candidate region)

Every retained *and* rejected region carries a full measurement record
(`detection/geometry.py: describe()` / `backscatter()`), returned through the API on
both `Slick.geometry`/`Slick.backscatter` and `RejectedLookalike`:

| Measurement | How it is computed |
|---|---|
| `area_km2` | pixel count × pixel ground area (not the simplified polygon, which would bias low) |
| `perimeter_km` | contour ring length under a local flat-earth approximation |
| `length_km` / `width_km` | extents along the region's **own principal axes**, not an axis-aligned bounding box — a diagonal trail would otherwise report a width equal to its diagonal |
| `aspect_ratio` | `length_km / width_km` |
| `elongation` | second-moment eigenvalue ratio of the fitted ellipse (distinct from aspect ratio: mass distribution vs. bounding extent) |
| `orientation_deg` | major-axis compass bearing, 0=N clockwise |
| `compactness` | `4πA/P²` recomputed in real units |
| `solidity` | area / convex-hull area; separates a solid trail from a ragged patch |
| backscatter stats | `mean_db`, `std_db`, `background_db`, `contrast_db`, `variance_ratio`, `edge_gradient` — the radiometry behind the confidence score |

Width is the quantity age estimation inverts through the Okubo diffusivity law (§4.1),
so it is a physical input, not a display field. Measured on the frozen case study: a
26.24 km × 0.94 km trail, aspect ratio 28.0, bearing 064.9°.

### 2.2 The discrimination formula

Four physically-motivated 0–1 terms, weight-averaged into a confidence score:

```python
s_contrast = clip((contrast_db - 2.0) / 6.0, 0, 1)     # weight 0.34
s_variance = clip((1.0 - variance_ratio) / 0.5, 0, 1)  # weight 0.31
s_shape    = clip((0.55 - compactness) / 0.45, 0, 1)   # weight 0.23
s_edge     = clip((edge_gradient - 0.15) / 0.5, 0, 1)  # weight 0.12

score  = 0.34*s_contrast + 0.31*s_variance + 0.23*s_shape + 0.12*s_edge
is_oil = score >= 0.45
```

| Term | Physical basis | Weight |
|---|---|---|
| **Contrast** | Mineral oil damps Bragg backscatter hard — typically 5–10 dB below the surrounding sea. Biogenic films and low-wind patches are darker too, but much less so. | 0.34 |
| **Variance ratio** | Oil suppresses small-scale roughness (speckle), so the patch isn't just darker, it's *smoother* — inside/ambient speckle std ratio, inverted. The single most useful separator: a low-wind zone is dark while staying as speckled as the sea. | 0.31 |
| **Shape (compactness)** | `4πA/P²`. An underway discharge is a long thin trail; low-wind zones and biogenic slicks are blobby. Compactness near 1 argues strongly against a vessel discharge. | 0.23 |
| **Edge gradient** | An oil boundary is a sharp discontinuity; a wind-driven roughness gradient fades. | 0.12 |

These four numbers are exactly what the dashboard's "Evidence" bars show (Analyst mode,
Detection panel) — not a separate presentation-layer computation, the literal terms
`classify()` scores and averages. `weight_contrast`/`weight_variance`/`weight_shape`/
`weight_edge` ship in the API response (`DetectionEvidence`) so the composite is
auditable rather than a black-box number.

Both the retained region and every rejected region get a natural-language `reason`
string assembled from whichever terms were decisive — that's the text behind the
"Ruled out" chips in the UI.

### 2.3 Measured performance (frozen `gom-2023-06-15` case, re-measured 2026-08-24)

| Metric | Value |
|---|---|
| Detection IoU | **0.878** |
| Recall / Precision | 0.931 / 0.939 |
| Look-alikes rejected | 2 of 2, each with a stated physical reason |
| Runtime | well under 1s |

`backend/tests/test_detection.py` asserts `detection_iou >= 0.80` as the regression
floor. Re-measure with `cd backend && .venv/bin/python -m pytest tests/test_detection.py -q`.

### 2.4 Ad-hoc upload path (`POST /api/detect/upload`)

The same detector, run on a user-supplied image rather than the frozen bundle. Two
things differ and are stated in the response's `notes` rather than hidden:

- **No calibrated Sigma0.** An uploaded PNG/JPEG carries brightness, not backscatter, so
  `classical.normalise()` applies a 1st/99th-percentile stretch onto a dB-like span. The
  detector only ever reasons about *relative* local contrast, which is what makes this
  sound; absolute dB values for uploaded imagery are not physically meaningful.
- **No geotransform.** Ground sampling distance is a user-supplied assumption (default
  10 m/px, Sentinel-1 IW GRD class), and lon/lat exist only if the caller anchors the
  scene centre via `lon`/`lat` form fields. With an anchor the response includes a
  GeoJSON `FeatureCollection` the MapLibre map renders directly; **without one, `geojson`
  is `null`** rather than a polygon placed at an invented location.

**No accuracy metric is reported on this path** — there is no ground-truth mask for an
arbitrary upload, so IoU/recall/precision are absent by design, not omitted by oversight.
`backend/tests/test_upload_geojson.py` asserts that absence.

---

## 3. Stage 1b — U-Net learned detector (real, trained, honestly gated)

This is a genuine trained model, not a stub — `plan.md` originally listed this as
Phase 7, "optional, cuttable, never blocks the demo," and it has since actually been
built. Selectable via `method=unet` on `POST /api/detect`; the classical path stays
selectable as "fast mode" so the guaranteed fallback is a feature, not a patch removed.

### 3.1 Architecture

- **Model:** U-Net (`segmentation_models_pytorch.Unet`)
- **Encoder:** ResNet34, ImageNet-pretrained
- **Input:** 3-channel, 256×256 patches (the calibrated dB raster is percentile-stretched
  to 8-bit grayscale and replicated across 3 channels — see §3.4)
- **Output:** single-channel logit → sigmoid → probability map
- **Params:** ~24M (ResNet34 encoder + U-Net decoder)
- **Inference:** tiled, 256px patches at 128px stride (50% overlap), probabilities
  averaged across overlapping tiles to soften seam artefacts, stitched to the full
  1024×1024 scene

### 3.2 Training dataset

- **Source:** Kaggle `bakhtiyar2222/deep-sar-oil-spill-segmentation-refined`
- **Split:** 6,455 train / 1,615 val image-mask pairs (256×256 PNG pairs, binary mask)
- **Classes in the data:** oil vs. not-oil only — **no separate look-alike/negative
  class**. This single fact is the root cause of the biggest limitation documented
  below (§3.6) and the top item in the future-work list (§7).

⚠️ **This is not the dataset the problem statement points to.** The officially-referenced
Zenodo Sentinel-1 SAR oil-spill dataset ([zenodo.org/records/8253899](https://zenodo.org/records/8253899),
"Part II — No Oil and Lookalike categories") already ships a lookalike negative class
purpose-built for this exact problem, per `research.md` §17/§29/§35. The model currently
deployed was trained on a different, Kaggle-mirrored collection instead. Retraining on
the official set is the single highest-leverage improvement available — see §7.1.

### 3.3 Training procedure

| Hyperparameter | Value |
|---|---|
| Loss | `BCEWithLogitsLoss + DiceLoss` (binary, from logits), summed |
| Optimizer | Adam, LR 1e-4 |
| LR schedule | `ReduceLROnPlateau` (mode=max on val IoU, factor 0.5, patience 3) |
| Batch size | 8 |
| Epochs | 20 (budget), early-stop patience 5 |
| Mixed precision | `torch.amp.autocast` + `GradScaler` (CUDA only) |
| Seed | 42 (`torch.manual_seed` + `np.random.seed`) |
| Augmentation | horizontal flip (p=0.5), vertical flip (p=0.5), random 90° rotation (p=0.5), brightness/contrast jitter (p=0.3), Gaussian noise (p=0.2) — via `albumentations` |
| Normalization | ImageNet mean/std |
| Checkpointing | best val-IoU epoch only, saved to `ml/weights/unet_best.pth` |

Scripts: `ml/train_unet.ipynb` (interactive/Colab) and `ml/train_unet_run.py` (headless
mirror, same logic, prints per-epoch progress for background execution).

### 3.4 Domain-shift bridge (the biggest scientific caveat)

The checkpoint was trained on pre-normalized 8-bit chips from a *different* SAR
collection than this system's actual input — the frozen case's raw, calibrated dB
raster (`data/case/sar_db.npy`). There's no verified colorimetric mapping between the
two datasets' preprocessing pipelines. The bridge used today is a 1st/99th-percentile
stretch to 8-bit grayscale (`_to_rgb_uint8` in `unet.py`) — a documented heuristic, not
a validated equivalence. Any IoU number for this model should be read with that caveat
attached.

### 3.5 The hybrid gate (why U-Net alone isn't enough)

On its own, trained without a look-alike class, the network confidently flags round
dark blobs — low-wind zones, biogenic slicks — as oil right alongside real trails.
Measured on the frozen case study *before* any gate: **100% recall, 5.9% precision.**

The fix implemented: a region is only reported as oil if, in addition to the network's
learned probability, its shape is trail-like — `compactness < 0.55`, the exact
zero-crossing the classical detector's own shape term (`s_shape`) uses. This is shape
**only**, not the full four-term `classify()` score, and that's a deliberate, measured
choice: `classify()`'s variance term is calibrated against the classical detector's own
region boundaries. Measured against a U-Net-produced boundary on this case study, the
true slick scored `variance_ratio=2.6` — "rougher than background," the physical
*opposite* of oil damping. That's a boundary-measurement artefact of how the U-Net's
mask edges differ from the classical threshold's edges, not a real signal, so the
variance term is excluded from the gate. Shape is unaffected by that mismatch and is the
cleanest discriminator available to this detector.

Regions the network liked but the shape gate rejects are surfaced as
`rejected_lookalikes`, exactly like the classical path, with the reason stated as an
explicit override ("U-Net flagged this region... but overridden as a look-alike...").

⚠️ This gate was tuned and validated against **one frozen case-study scene** (one real
slick, three false positives it correctly overrides), not a labeled test set. Treat it
as a documented, reasoned engineering choice, not a statistically validated one.

### 3.6 Measured performance

**Training-time (Kaggle held-out val set, `ml/data/`, in-distribution):**

| Metric | Value |
|---|---|
| Best val IoU (per-image, matches training metric) | **0.739** (epoch 20/20 — training completed the full budget without early-stopping firing; see §7.2) |

Re-measure the full confusion-matrix breakdown (pixel accuracy, precision, recall, F1,
dataset-pooled IoU) with `ml/evaluate_unet.py` — see §8.

**On the frozen `gom-2023-06-15` case study (out-of-distribution — the real deployment
condition), measured live via `POST /api/detect {"method":"unet"}` on 2026-08-24:**

| Metric | Classical | U-Net |
|---|---|---|
| Detection IoU | **0.878** | **0.501** |
| Recall | 0.931 | **1.000** |
| Precision | 0.939 | **0.501** |
| Detected area | 15.9 km² (truth 16.0) | 32.0 km² |
| Inference time | <1 s | **~9.5 s** (CPU, tiled 256px/128-stride over a 1024² scene) |

This is the honest, quantified version of §3.4/§3.5's caveats: the U-Net **never misses**
the slick (perfect recall — the domain shift hasn't broken its ability to find dark,
elongated regions) but **roughly doubles its extent** relative to ground truth
(precision 0.501, area 32 km² vs. true 16 km²) and runs an order of magnitude slower
than the classical path on CPU. Classical remains the higher-precision, faster,
demo-safe default; U-Net is a real, working, honestly-worse-on-this-scene alternative,
which is a much more credible story for judges than either hiding the comparison or
pretending U-Net won.

There is currently **no automated test coverage** for the U-Net path (`grep -r unet
backend/tests/` finds nothing) — see §7.4.

---

## 4. Stage 1c — Age estimation (physical heuristic, not ML)

The problem statement itself hedges age estimation as "if feasible" and the literature
has no accepted method for recovering elapsed time from imagery alone (`research.md`
§20/§37). This is attempted anyway, bounded, and stated on screen rather than emitting a
false-precision number — differentiating from teams that skip it entirely.

### 4.1 The model

**Key insight the method depends on:** an underway discharge is a *line source*, not a
point source. The trail's *length* is set by how far the vessel steamed while
discharging and carries no age information. Only its *width* does. (Fay's classical
spreading law — the obvious first guess — assumes an instantaneous point release and
underestimates age by an order of magnitude if applied to the full slick area; it's
explicitly not used here.)

Width is inverted through **Okubo (1971) scale-dependent horizontal turbulent
diffusivity**, the same empirical law from dye-release experiments that also drives the
drift ensemble's diffusion term (§5) — one physics model shared across both stages, so
the age estimate and the drift uncertainty are internally consistent rather than two
unrelated numbers that happen to appear near each other in the UI.

```
K = 0.0103 · L^1.15                    (Okubo 1971; K in cm²/s, L in cm — the trail width)
σ = width / 4                          (visible trail taken as ±2σ across)
t = σ² / (2K)
```

A second, independent signal — backscatter damping decay (dB below local background) —
shades the estimate within the resulting bracket (fresher film → younger end, more
weathered → older end) but never sets the bracket itself.

### 4.2 Uncertainty

- Diffusivity is treated as uncertain by a **factor of 2 either way** (`K_UNCERTAINTY =
  2.0`) — real ocean diffusivity genuinely varies this much at a fixed scale, and it
  dominates the error budget over everything else in the formula.
- `confidence` is reported as `"low"` **unconditionally** — never upgraded, regardless of
  how narrow the resulting bracket happens to look, because the diffusivity uncertainty
  is structural, not something a good fit can shrink away.
- Output is always a `[min_hours, max_hours]` range plus a `method_note` prose string
  (now collapsed behind "View reasoning" in the UI — see the frontend change history)
  and, as of this session, three structured pull-outs of the same numbers:
  `diffusivity_m2s`, `damping_db`, `weathering` (`"relatively fresh" |
  "weathering" | "well-weathered"`).

### 4.3 Measured result (frozen case)

| | Value |
|---|---|
| Age bracket | 4.5–19.1 h |
| Ground truth | 8.0 h |
| Confidence | low (by design, always) |

---

## 4b. Environmental data abstraction (Phase 3)

The drift ensemble needs currents and wind. Rather than let it import a specific
data source, everything environmental goes through one seam in
`backend/app/environment/`:

| Piece | File | Role |
|---|---|---|
| `EnvironmentalData` | `base.py` | The normalised type: lon, lat, timestamp, u/v current, u/v wind, optional waves, plus provenance (`source`, `is_synthetic`, `is_steady`) |
| `EnvironmentalDataProvider` | `base.py` | ABC. One required method, `at()`; `series()` and `surface_velocity()` derive from it |
| `CaseBundleProvider` | `bundle.py` | Real path — adapts the existing `ForcingField` over `data/case/forcing.npz` |
| `MockEnvironmentalProvider` | `mock.py` | Always-available synthetic fallback |
| `get_provider()` | `resolver.py` | Picks the best available provider; falls back to mock. `ENV_DATA_MODE=mock` forces it |

Served at `GET /api/environment` for a point, a time range, or an incident id, and
`GET /api/environment/providers` to inspect what is available.

**Direction convention**, stated because the alternative is equally common and differs
by 180°: directions are the way a vector points **toward**, degrees clockwise from
north. Due-east flow reads 90°.

Three honesty properties worth noting:

- **Steady ≠ time-varying.** The case bundle's forcing has no time axis, so
  `CaseBundleProvider` returns the same field for any timestamp and sets
  `is_steady=True`. The interface still takes a `time` so a real time-varying source
  (CMEMS, ERA5, INCOIS) drops in with no caller changes.
- **Synthetic ≠ fallback.** The frozen case's forcing is itself synthesised, so the
  *real* provider legitimately reports `is_synthetic=True`. The response distinguishes
  which provider served the request from whether its values are modelled.
- **Absent ≠ zero.** The bundle ships no wave data, so wave fields are `None` rather
  than 0.0.

**Not yet wired into simulation.** `drift/lagrangian.py` still calls `ForcingField`
directly, and the measured drift numbers in §5.5 are unchanged (origin error 7.7 km,
re-verified). `CaseBundleProvider.surface_velocity()` is a vectorised passthrough to
that same object and returns bit-identical velocities for a full 500-particle array —
asserted by `test_provider_accepts_a_whole_particle_array_like_the_drift_engine_does`
— so wiring the engine through the provider is a one-line swap, not a physics change.

---

## 5. Stage 2 — Drift hindcast/forecast (Lagrangian ensemble)

A stochastic particle simulation, not a neural model — included here because it's
exactly as central to "the model" as detection is, and the problem statement's
"Expected Solution" groups detection and drift together as one ML/modelling deliverable.

### 5.1 Why a custom engine instead of OpenDrift

Deliberate build-vs-buy call, documented in `lagrangian.py`'s own module docstring:
OpenDrift needs a conda-scale install and CMEMS credentials; this implementation is
~100 lines and runs in under a second. `drift/engine.py` defines the `DriftEngine` seam
an OpenDrift adapter would slot into unchanged later — the swap is a config change, not
a redesign, which is the honest claim made in the pitch.

### 5.2 The physics

Per particle, per timestep:

```
dx = (u_current + wind_factor · u_wind) · dt  +  √(2·K·dt) · N(0,1)
```

- **Advection:** bilinearly-interpolated surface current plus a wind-factor fraction
  (default 3%, defensible range 2–4%) of 10 m wind — standard operational treatment
  standing in for the combined effect of Stokes drift and the wind-driven surface layer.
- **Diffusion:** the same Okubo (1971) scale-dependent law as age estimation (§4.1), but
  now recomputed *every timestep from the ensemble cloud's own current spread* — a patch
  diffuses faster the larger it already is, because progressively bigger eddies act on
  it. A fixed K under-spreads a growing cloud and quietly overstates confidence in the
  origin.
- **Direction:** `direction=-1` for hindcast, `+1` for forecast, same engine.
  Advection reverses with direction; diffusion does **not** — turbulent spreading is
  irreversible, so running time backward still *widens* the cloud. This is precisely
  why the origin comes out as a region, not a point.
- **Seeding:** particles are scattered across the *entire slick polygon* by rejection
  sampling, not just its centroid — seeding a 26 km trail from its centroid alone would
  collapse the origin uncertainty the slick's own extent implies.
- Defaults: 500 particles, 15-minute timestep.

### 5.1b Configurable simulation + the mock path (Phase 4)

`/api/drift/hindcast` and `/api/drift/forecast` now accept `timestep_minutes` and
`diffusion_m2s` alongside the existing `hours` (duration), `n_particles` and
`wind_factor` (windage) — every knob Phase 4 requires is a per-request parameter, not a
fixed constant, with defaults matching the values that were previously hardcoded so an
old client sees no change.

**`drift/simulate.py`** is a second, parallel implementation of the same physics,
written to depend on `EnvironmentalDataProvider` (§4b) instead of `ForcingField`
directly. It exists so a mock run can execute the *real* simulation equations —
advection + Okubo diffusion + the same timestep loop — against synthetic environmental
data, rather than faking particle motion. It does not replace `drift/lagrangian.py`,
which still backs the real case-bundle path unchanged (§5.5's numbers are the
regression floor); `CaseBundleProvider.surface_velocity()` was already proven
bit-identical to `ForcingField` in Phase 3, so both implementations agree on the real
path's physics.

**What mock mode used to do:** `core/fixtures.py`'s `_drift()` faked particle motion
with `random.gauss()` jitter around a fixed straight-line velocity (1.20, 0.88 km/h)
and never read wind or current at all — the pre-generated/translated pattern Phase 4
rules out. **What it does now:** `drift/mock_engine.py` runs `drift/simulate.py`
against `MockEnvironmentalProvider` (§4b), with the same cone-extraction and
origin-estimate logic `engine.py` uses on the real path. `fixtures.hindcast_response()`/
`forecast_response()` still exist and still back `/api/pipeline/run`, an unconditional
all-fixture demo warm-start endpoint outside this phase's scope — they are simply no
longer reachable from `/api/drift/*`.

### 5.3 From particle cloud to an answer

A scatter of 500 dots isn't something a judge can read. `drift/cone.py` kernel-densities
the cloud onto a 160×160 grid, finds the density threshold enclosing 50%/90% of the
total mass, and traces its contour — following the cloud's actual (often curved,
sheared) shape rather than misrepresenting it as a convex hull or an ellipse.

- **Origin estimate** = the union of the ensemble over the *entire plausible age window*
  from Stage 1c (e.g. 4.5–19.1 h), not the cloud at one arbitrarily chosen hour. This is
  what makes detection and drift one pipeline rather than two demos glued together: a
  wider age bracket honestly produces a wider origin region.
- **Origin marker** = the mode (densest point) of that pooled cloud — reported only
  alongside the containment region, never alone.
- Forecast: same engine, `direction=+1`, 90% containment cone plus a centroid path,
  screened against a small set of coastline/protected-area/infrastructure targets for
  impact flags.

### 5.4 Known simplification

The forcing field is treated as **steady** (time-invariant) over the run — stated
explicitly in `ForcingField`'s docstring and in the response provenance. Over a 24 h
hindcast in the northern Gulf in summer the mesoscale field is slowly varying, so the
dominant error source is the diffusivity uncertainty (§5.2), not the time-independence
assumption — but it's a real simplification, not free.

### 5.5 Measured performance (frozen case)

| Metric | Value |
|---|---|
| Hindcast origin error (mode vs. true origin) | **7.7 km** |
| 90% containment region | contains the true origin |
| Drift runtime (500 particles, full ensemble) | **38 ms** |

Sensitivity check suggested (and demonstrated in the deck, per `plan.md`): re-run at
2%/3%/4% wind-drift factor and show the cone widens — a cheap, concrete demonstration of
genuine uncertainty awareness rather than a single unexamined run.

### 5.6 Origin-time-and-location search (Phase 5)

`POST /api/drift/origin-search` turns the fixed-age-window hindcast above into a real
search. Rather than trusting a single Okubo-derived age bracket and pooling one backward
run over it, it searches candidate release times across the previous 24 h (hourly by
default) and, for each, runs a genuine simulate-and-compare cycle
(`backend/app/drift/origin_search.py`):

1. **Propose.** A real backward Lagrangian simulation (Phase 4's `drift/simulate.py`)
   from the observed slick to candidate age `t` — its centroid is the candidate origin.
2. **Verify.** A real *forward* simulation from that candidate origin at that candidate
   time, back up to the detection time — this is what the candidate PREDICTS the slick
   should look like.
3. **Score.** The predicted cloud against the observed slick polygon on five documented
   metrics (spatial overlap, centroid distance, shape similarity, orientation similarity,
   particle-density similarity), combined into one weighted composite
   (`SCORE_WEIGHTS`, sums to 1, no term above 0.6).
4. **Rank.** All candidates sorted by composite score.

**Line-source seeding.** An elongated observed slick (elongation > 3, this project's own
threshold for "underway discharge, not a point release" — see `detection/age.py`) is
verified against a short line-source release oriented along its own measured bearing,
not a single point. A point release physically cannot reproduce a 26 km trail no matter
how correct the origin and time are; this was caught by testing against the frozen case,
where shape/density similarity were collapsing to ~0 for every candidate before the fix.

**Okubo as constraint, not estimator.** `detection/age.py`'s width-inversion bracket
(now correctly passed the trail's `length_km` — omitting it was a second bug caught the
same way, and reproduces the documented order-of-magnitude overestimate) is folded in as
`age_plausibility`, capped at a 15% adjustment to the composite score. It cannot override
a genuinely poor geometry match, by design — the requirement is that Okubo constrain, not
determine, the ranking.

**Known limitation, disclosed rather than tuned away.** `spatial_overlap` and
`density_similarity` are mechanically biased toward *shorter* candidate ages: less
elapsed time means less diffusion spread, which produces a tighter, easier-to-match
cloud independent of whether the release location is actually correct. Measured against
the frozen case (true age 8.0 h), the search currently favours ages 1-2 h short of
truth; `centroid_distance_km` stays roughly flat across candidate ages, confirming the
bias sits in the spread-sensitive terms specifically. Re-weighting until this one case
matched ground truth would be exactly the curve-fitting the "no hard-coded scientific
result" requirement rules out, so it is stated in both the module docstring and the
API's `provenance.notes` instead. A structural fix (normalising overlap/density by the
candidate's own predicted spread) is a candidate for future work.

**Output.** Best origin, 50%/90% containment regions (from the best candidate's own
predicted cloud, via the same `cone.py` machinery §5.3 uses), estimated release time,
age (`detection_time - release_time`) with an explicit `[min, max]` uncertainty window
spanning every candidate scoring within 15% of the best, and a `low`/`medium`/`high`
confidence that requires both a decisive score margin *and* a tight age window to earn
`high`. Every candidate's full metric breakdown is returned, not just the winner, so the
ranking is auditable rather than a single asserted answer.

---

## 6. Stage 3 — AIS attribution scoring: **ingestion is real, scoring is not**

Be precise about this with judges: **`POST /api/attribute` (the scoring endpoint) still
calls `engine.reconstruct_and_score()` against a hardcoded `MOCK_VESSELS` Python list**,
regardless of input — it does not read `data/case/ais.parquet` at all. This is the one
stage where the UI's explainability (the 5-factor score breakdown, the narrative
sentences, the DARK_VESSEL flag) is real *presentation* of a *designed but unimplemented*
computation. The dashboard's "· fixture" honesty tag on this panel is accurate.

**What changed (Phase 6):** real AIS ingestion now exists and runs against the real
data, at `GET /api/ais/tracks` — a separate, additive endpoint, not a change to
`/api/attribute`. `backend/app/attribution/ais_ingest.py` parses the actual parquet
(MMSI, BaseDateTime, LAT, LON, SOG, COG, VesselName, VesselType — the columns the real
NOAA AccessAIS-derived source ships, no IMO or true-heading column, so those two output
fields are honestly `null` rather than fabricated), groups by vessel, sorts
chronologically, reconstructs a GeoJSON LineString track per vessel, plausibility-gates
straight-line interpolation across short gaps, and detects genuine reporting gaps. Live
against the frozen case: **the injected polluter (MV KESTREL TRADER, MMSI 367301820)
shows a real 96-minute AIS gap that overlaps the origin time window** — the actual
dark-vessel signal, surfaced by real ingestion instead of the `has_gap: True` flag
hand-set in `MOCK_VESSELS`. `ais_ingest.py` computes no score and labels a gap only as
"AIS reporting gap — investigation signal, not a finding of wrongdoing," never a
suspicion verdict — attribution scoring (§6.2 below) is a separate, later step that
would consume this module's output.

One current limitation, not a Phase 6 bug: the case bundle's `ais.parquet` today
contains only the single injected vessel (314 real positions, one real vessel) — the
broader background traffic `test_case_bundle.py`'s (already-failing, pre-existing)
`test_ais_contains_real_traffic_not_only_the_injected_vessel` expects has not actually
been built into the bundle yet. The ingestion pipeline itself handles an arbitrary
number of vessels (`tests/test_ais_ingest.py` exercises multi-vessel grouping directly);
it is the data file that is currently sparse.

### 6.1 What's already designed (schema, not code)

The scoring formula is frozen in `ScoreWeights`/`ScoreBreakdown` (`schemas.py`) and the
fixture generator mirrors it closely enough to be a faithful preview of what real code
should compute:

```
score = 0.30·proximity + 0.25·temporal_overlap + 0.20·ais_gap
      + 0.15·heading_consistency + 0.10·speed_anomaly
```

| Factor | Intended real computation | Weight |
|---|---|---|
| `proximity` | Minimum distance from track to origin estimate, weighted by the origin cone's probability density at closest approach — not raw distance alone | 0.30 |
| `temporal_overlap` | Overlap between the vessel's AIS presence and the estimated origin time window | 0.25 |
| `ais_gap` | A reporting gap (default >30 min) overlapping the origin window scores high — the dark-vessel signal | 0.20 |
| `heading_consistency` | Whether the vessel's course is consistent with a discharge producing the observed slick orientation | 0.15 |
| `speed_anomaly` | Slow steaming or an unusual manoeuvre near the origin | 0.10 |

Weights are request-configurable and returned in the response (`AttributeResponse.weights`)
specifically so the composite is auditable rather than magic — that part of the design
is sound and doesn't need to change when real code lands.

### 6.2 What real implementation still needs

Per `plan.md`'s Phase 4 spec:

1. ~~`ais_ingest.py` — parse the AccessAIS extract, group by MMSI, sort by time,
   reconstruct tracks, interpolate to a common time grid, drop implausible jumps.~~
   **Done (Phase 6)** — `backend/app/attribution/ais_ingest.py`, exposed at
   `GET /api/ais/tracks`. Interpolation is plausibility-gated (max 60 min gap, implied
   speed under 40 kn) rather than forced onto a fixed time grid — a long or physically
   implausible gap is left un-bridged and reported as an `AISGap` instead.
2. ~~`gaps.py` — detect reporting gaps above threshold...~~ **Done (Phase 6)**, folded
   into `ais_ingest.detect_gaps()` rather than a separate module; already has the schema
   slot `AISGap.interpolated_path` plus a new `AISGap.label` field stating the gap is an
   investigation signal, not a verdict.
3. `filters.py` — prune to vessels whose track comes within `search_radius_km` of the
   origin estimate during the origin time window; report `total_vessels_in_region` vs.
   `after_filter` (already real numbers in the schema, currently fixture-sourced). **Not
   yet built** — `/api/attribute` still uses `MOCK_VESSELS`, not
   `ais_ingest.ingest()`'s output.
4. `scoring.py` — the weighted composite above, computed from real track geometry
   instead of a `rng.gauss`-jittered straight line. **Not yet built.**
5. Validate against `data/case/case.json`'s ground truth: the injected polluter (MV
   KESTREL TRADER, MMSI in the case bundle) must rank #1, with a recorded score margin
   over #2 — a concrete number worth putting in the deck. **Not yet possible** until 3-4
   land; ingestion alone has no ranking to validate.

The real AIS data needed for this already exists in the case bundle
(`data/case/ais.parquet`, built from synthesized/NOAA AccessAIS traffic per
`scripts/build_case.py`) — this is implementation work, not a data-access blocker.

---

## 7. Future work, prioritized for SIH

Ordered by (impact on judge-facing credibility) ÷ (hours to implement) — same triage
lens `plan.md`'s own cut-list uses.

### 7.1 Retrain U-Net on the officially-referenced dataset — highest leverage

The problem statement points to a Zenodo dataset
([zenodo.org/records/8253899](https://zenodo.org/records/8253899)) that already ships a
"Lookalike" negative class. The model in production was trained on a different Kaggle
mirror that has no such class — which is the documented, root-cause reason the shape-gate
override exists at all (§3.5). Retraining (or fine-tuning) on the official set, with
oil/lookalike/no-oil as three real classes instead of a post-hoc geometric patch, would:

- Let `classify()`'s full four-term score work on U-Net-produced boundaries instead of
  degrading to shape-only (directly fixes the `variance_ratio=2.6` boundary-artefact
  problem noted in §3.5).
- Close the "not the dataset the PS pointed to" gap before a judge notices it.
- Very likely lift IoU on the frozen case study above the current 0.501 — the model
  currently has *never seen* a lookalike-vs-oil distinction during training at all.

### 7.2 Cheap accuracy wins, no retraining required

- **Test-time augmentation** (average predictions over flips) — typically +1–3% IoU for
  free.
- **Threshold tuning.** `CONF_THRESHOLD=0.5` is asserted, not fit. `evaluate_unet.py`
  already computes precision/recall — sweep thresholds against the val set and report
  the best-F1 operating point instead.
- **Train longer / adjust the schedule.** Training completed all 20 budgeted epochs
  without `PATIENCE=5` early-stopping ever firing — the loss curve had not plateaued.
  Cheap to just raise `EPOCHS` or swap `ReduceLROnPlateau` for a cosine schedule and
  re-run.

### 7.3 Verify the val split isn't leaking

6,455/1,615 train/val is a healthy volume, but if the Kaggle source tiled a small
number of parent scenes into many overlapping/adjacent 256px patches, and the split was
done patch-wise rather than scene-wise, the reported 0.739 val IoU is optimistically
biased (train and val share spatially-correlated content). This is a five-minute check
(inspect filename patterns for a shared scene ID) that materially affects whether the
headline training number can be defended under a judge's follow-up question.

### 7.4 Test coverage for the U-Net path

`backend/tests/test_detection.py` has zero assertions exercising `method=unet` — every
number in §3.6 was measured by hand for this document, not by CI. At minimum: a
regression test pinning the case-study IoU/recall/precision within a tolerance band
(mirroring the existing classical-detector test), so a future change can't silently
regress it unnoticed.

### 7.5 Implement real attribution (Stage 3)

The largest actual scope gap in the whole system (§6). `research.md` explicitly calls
this stage — AIS-gap analysis fused with drift backtracking into one scored pipeline —
the least-precedented, most judge-visible contribution available ("individual pieces
exist in the literature... a single system that chains all three does not appear to
have a widely publicized open-source or Indian-government reference implementation").
It's also the most labor-intensive item on this list (`ais_ingest.py` → `gaps.py` →
`filters.py` → `scoring.py`, §6.2), so scope it as its own work block rather than
squeezing it in alongside the detection-model work above.

### 7.6 Report the domain-shift-bridge more rigorously (if time allows)

Right now the dB → 8-bit bridge (§3.4) is a percentile stretch chosen by inspection. If
a real Sentinel-1 scene in the checkpoint's native preprocessing format becomes
available, a small calibration/fine-tuning pass against it — rather than only a
value-range bridge at inference time — would be the statistically correct fix, not a
heuristic one.

### 7.7 Post-SIH / production path (not worth building now)

Documented in `README.md`'s "production path" framing and worth restating here for
completeness: ISRO SAR imagery in place of Sentinel-1, India's NAIS feed in place of
AccessAIS, INCOIS forcing fields in place of the synthesized/ERA5-CMEMS wind+current.
None of this changes the algorithms in this document — it's a data-source substitution,
which is precisely the claim the demo makes and should keep making.

---

## 8. Reproducing the numbers in this document

```bash
# Classical detector — IoU/recall/precision regression test
cd backend && .venv/bin/python -m pytest tests/test_detection.py -q

# U-Net vs classical, side by side, on the live case
.venv/bin/uvicorn app.main:app --port 8000 &
curl -s -X POST localhost:8000/api/detect -H 'Content-Type: application/json' \
  -d '{"method":"classical"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['provenance']['params'])"
curl -s -X POST localhost:8000/api/detect -H 'Content-Type: application/json' \
  -d '{"method":"unet"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['provenance']['params'])"

# U-Net held-out val set metrics (needs ml/.venv with torch/segmentation_models_pytorch)
cd ml && .venv/bin/python evaluate_unet.py

# Re-run training from scratch (headless)
cd ml && .venv/bin/python train_unet_run.py

# Drift engine determinism + timing
cd backend && .venv/bin/python -m pytest tests/test_drift.py -q
```

---

## 9. Environment / dependency reference

| Component | Library | Pinned version |
|---|---|---|
| Classical CV | `opencv-python-headless` | ≥4.10 |
| Classical CV | `scipy` | ≥1.13 |
| Learned detector | `torch` | 2.6.0 (CPU wheel in the backend venv; CUDA build in `ml/.venv` for training) |
| Learned detector | `torchvision` | 0.21.0 |
| Learned detector | `segmentation-models-pytorch` | ≥0.5 (0.5.0 in `ml/.venv`) |
| Training augmentation | `albumentations` | 2.0.8 |
| Drift ensemble | `numpy` | ≥1.26 |
| Attribution (future) | `pandas` / `pyarrow` | ≥2.2 / ≥17.0 (already in `backend/requirements.txt`, unused until §6.2 lands) |

`torch`/`torchvision` are pinned as a matched pair deliberately — letting them resolve
independently is the classic source of a `torchvision::nms does not exist` runtime
error. CPU-only install for the backend:

```bash
uv pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
```

---

## 10. References

Cited in `research.md`, reproduced here for the pipelines they're directly relevant to:

- Okubo, A. (1971). *Oceanic diffusion diagrams.* Deep-Sea Research — the scale-dependent
  diffusivity law behind both age estimation (§4) and drift diffusion (§5.2).
- Krestenitis et al. (2019). *Oil Spill Identification from Satellite Images Using Deep
  Neural Networks.* Remote Sensing 11(15):1762 — the field's benchmark dataset+paper;
  best reported DeepLabv3+ mIoU ≈65%, useful context for reading this project's 0.878
  (classical, in-domain) and 0.501 (U-Net, out-of-domain) numbers against the literature.
- Yekeen, Balogun, Wan Yusof (2020). *A novel deep learning instance segmentation model
  for automated marine oil spill detection.* ISPRS J. Photogrammetry and Remote Sensing
  167:190-200 — Mask R-CNN, F1=0.968.
- "Marine oil spill detection and segmentation in SAR data with two steps Deep Learning
  framework" (2024) — MARINEXT vs. U-Net/SegNeXt comparison, F1-macro 92.7%.
- Zenodo Sentinel-1 SAR oil-spill dataset, Parts I–III — the problem statement's named
  data source. Part I (masks, [zenodo.org/records/8346860](https://zenodo.org/records/8346860))
  is what this project's frozen case study is built from. Part II
  ([zenodo.org/records/8253899](https://zenodo.org/records/8253899), "No Oil" and
  "Lookalike" categories) is what §7.1 recommends training on next.

See `research.md` for the full literature survey and `plan.md` for the phase-by-phase
build plan this document's "Status" column is measured against.
