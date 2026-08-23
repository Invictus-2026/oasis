# SpillTrace — Internal Round Prototype Plan

**Problem statement:** SIH26143 (NTRO) — Detect oil spills from satellite imagery, hindcast/forecast slick drift, and attribute the spill to a vessel using AIS.
**Full research context:** see `research.md` in this directory. Read it before executing any phase.

**Constraints this plan is built around:**
- 3-4 days to an internal round, 2-3 builders.
- Format: live demo + PPT to judges.
- Team strength: React/frontend and backend/APIs. ML is the weak axis, so ML must never block the demo.
- Effort weighting: UI 30% / attribution 30% / drift 25% / detection 15%.

**North star:** a single-page dashboard that walks a judge through detect -> characterise -> hindcast cone -> forecast -> ranked suspect vessels -> evidence report, on one frozen case study, fully offline.

---

## Non-negotiable design rules

1. **Everything runs offline at demo time.** No live API calls, no internet dependency. All source data cached in `data/`.
2. **Never accuse, always rank.** Output is a confidence-scored candidate list with a per-factor explainability breakdown.
3. **Fallback before headline.** Every ML/physics component ships a simple deterministic version first; the fancy version is an upgrade that can be cut.
4. **Honest labelling in the UI.** Age estimation, the constructed validation scenario, and the drift engine's simplifications are all visibly caveated on screen. The honesty is a scoring point, not a weakness.
5. **Frontend never waits on backend.** Mock JSON fixtures matching the exact API contract exist from Phase 0.

---

## SCOPE DECISION (2026-08-23)

Target is a prototype that conveys the idea end to end, not a production
system. **Phases 3 and 4 are built for real, then we stop.**

Reason: Stage 1 is real, and fixture Stages 2-4 disagree with it badly — the
fixture hindcast origin sits 58 km from the actually-detected slick and four of
five candidate vessels do not exist in the real AIS. A judge clicking through
would see the demo fall apart on the second click. Faking it convincingly costs
nearly as much as computing it, and attribution on 202 real vessels is the
differentiator the research identifies.

**Cut from scope:** Phase 6 (evidence PDF — the on-screen panel stays), Phase 7
(U-Net — the classical detector is the deliverable), the timeline scrubber, and
forecast animation polish.

**Still in scope:** Phase 3 (drift), Phase 4 (attribution), Phase 8 (hardening
and deck).

---

## Cut list (execute in this order if behind schedule)

1. Timeline scrubber
2. Forecast animation (fall back to a static forecast path)
3. U-Net detection (fall back to the classical detector)
4. Age estimation
5. PDF evidence report (fall back to an on-screen evidence panel)

**Never cut:** the map, the hindcast probability cone, the ranked vessel table with score breakdown.

---

## Target repo structure

```
sih/
  research.md
  plan.md
  README.md
  data/
    raw/            # downloaded Zenodo SAR patches, AccessAIS CSVs, ERA5/CMEMS NetCDF
    case/           # the frozen case study bundle (see Phase 1)
  backend/
    app/
      main.py             # FastAPI app + CORS
      api/
        detection.py
        drift.py
        attribution.py
        report.py
        case.py
      core/
        config.py
        schemas.py        # pydantic models = the API contract
      detection/
        classical.py      # baseline detector (never fails)
        unet.py           # optional learned detector
        geometry.py       # area, perimeter, elongation, orientation
        age.py            # heuristic age proxy
      drift/
        engine.py         # DriftEngine interface
        lagrangian.py     # NumPy ensemble advector (our implementation)
        fields.py         # loads cached current + wind NetCDF
        cone.py           # particle cloud -> probability cone polygons
      attribution/
        ais_ingest.py     # parse + reconstruct tracks
        gaps.py           # AIS gap detection
        filters.py        # spatiotemporal pruning against the origin cone
        scoring.py        # weighted explainable score
      report/
        pdf.py
    tests/
    requirements.txt
  frontend/
    src/
      App.tsx
      components/
        MapView.tsx
        DetectionPanel.tsx
        DriftControls.tsx
        VesselTable.tsx
        ScoreBreakdown.tsx
        EvidencePanel.tsx
        TimelineScrubber.tsx
      api/client.ts
      mock/            # fixtures mirroring the API contract
    package.json
  ml/
    train_unet.ipynb    # Colab notebook
    weights/
  deck/
```

**Stack:** FastAPI + Python 3.11 (numpy, rasterio, shapely, scipy, opencv-python, xarray, netCDF4, reportlab) / React + TypeScript + Vite + MapLibre GL + Tailwind. No PostGIS for the prototype; the case bundle is JSON/GeoJSON on disk. Mention PostGIS as the production path in the deck.

---

## Phase 0 — Scaffold and API contract

**Goal:** both builders can start work in parallel within the hour, with zero coupling.

Tasks:
1. Create the repo structure above. `git init`.
2. Write `backend/app/core/schemas.py` with the full API contract as pydantic models (see "API contract" below).
3. Stand up FastAPI with all endpoints returning hardcoded fixture data that satisfies the schemas.
4. Scaffold the Vite + React + TS + Tailwind + MapLibre frontend; blank map centred on the case region.
5. Copy the backend fixtures into `frontend/src/mock/` so the UI can run with the backend down.
6. `README.md` with run instructions for both halves.

**Acceptance:** `uvicorn` serves all endpoints with plausible fake data; `npm run dev` shows a map; the frontend renders the fake slick polygon from a live backend call.

### API contract (freeze this in Phase 0, change it only deliberately)

- `GET /api/case` -> case metadata: id, name, region bbox, scene id, acquisition timestamp, data provenance strings, a `disclaimer` string for the constructed-scenario banner.
- `POST /api/detect` -> `{ slicks: [{ id, polygon: GeoJSON, confidence, method: "classical"|"unet", geometry: { area_km2, perimeter_km, elongation, orientation_deg, compactness }, age: { min_hours, max_hours, confidence: "low", method_note } }], rejected_lookalikes: [{ polygon, reason, confidence }], processing: { steps: [...], duration_ms } }`
- `POST /api/drift/hindcast` body `{ slick_id, hours_back, n_particles }` -> `{ particles_timeline: [{ t_offset_hours, points: [[lon,lat],...] }], cone: [{ t_offset_hours, polygon: GeoJSON, percentile: 50|90 }], origin_estimate: { point: [lon,lat], time_utc, uncertainty_radius_km, time_window_hours: [lo,hi] } }`
- `POST /api/drift/forecast` body `{ slick_id, hours_forward }` -> same shape, plus `impact_flags` (coastline proximity) if cheap.
- `POST /api/attribute` body `{ origin_estimate, search_radius_km, time_window_hours }` -> `{ total_vessels_in_region, after_filter, candidates: [{ mmsi, name, vessel_type, track: GeoJSON LineString, score, rank, flags: ["DARK_VESSEL", ...], breakdown: { proximity, temporal_overlap, heading_consistency, ais_gap, speed_anomaly }, weights: {...}, narrative: "..." }] }`
- `POST /api/report` -> PDF bytes + a JSON echo of the same content for the on-screen evidence panel.
- `GET /api/pipeline/run` (optional convenience) -> runs all stages and returns the composed result.

Every response carries `provenance: { model_version, params, generated_at, inputs: [...] }`. This is what makes the audit story real rather than claimed.

---

## Phase 1 — Freeze the case study

**Goal:** one immutable data bundle everything else is built against. Nothing downstream can start safely until this exists.

Tasks:
1. Download 1-3 Sentinel-1 SAR patches from the official Zenodo oil-spill dataset (Parts I-III), choosing patches that contain both a clear oil slick and a lookalike/no-oil patch.
2. Choose a plausible ocean location and date for the demo scenario. Default choice: **Gulf of Mexico, offshore Louisiana**, a date in 2023, because AccessAIS covers US waters. Georeference the SAR patch onto that bbox.
3. Download AccessAIS data for that bbox and a 48-hour window around the date. Trim to the bbox to keep it small.
4. Download a small ERA5 (10m wind) and CMEMS (surface current) subset for the same bbox/window; cache as NetCDF in `data/raw/`. If credentials are a problem, generate a physically plausible synthetic field and label it as such everywhere.
5. Inject one synthetic ground-truth polluter into the AIS: a vessel that transits through the true origin point at the true origin time and goes AIS-dark for a 90-minute window covering it.
6. Write `data/case/case.json` recording every input, its source URL, licence, and the exact ground truth (origin point, origin time, polluter MMSI) so evaluation is possible.
7. Write `scripts/build_case.py` so the bundle is reproducible.

**Honesty requirement:** the SAR patch and the AIS traffic are not from the same real event. This is a *constructed validation scenario*, and the UI must say so in a small persistent banner. Judges respect this; being caught hiding it is fatal.

**Acceptance:** `data/case/` contains the SAR raster, AIS CSV/parquet, wind+current NetCDF, and `case.json` with ground truth. Loading it needs no network.

---

## Phase 2 — Detection and characterisation (Stage 1)

**Goal:** a slick polygon with real geometry on the map, produced by code that runs in under 5 seconds.

Tasks:
1. `detection/classical.py`: load SAR patch -> Lee or median speckle filter -> land mask -> adaptive/Otsu threshold on dark regions -> morphological open/close -> contour extraction -> polygon simplification -> pixel-to-lonlat transform. **This is the guaranteed path. Build it first and completely.**
2. `detection/geometry.py`: area (km²), perimeter (km), elongation (major/minor axis of fitted ellipse), orientation (deg), compactness (4*pi*A/P²).
3. Lookalike rejection: a simple discriminator on the extracted regions (compactness, edge gradient sharpness, backscatter contrast, size) that labels at least one region as a rejected lookalike with a stated reason. This directly pre-answers a guaranteed judge question.
4. `detection/age.py`: heuristic age proxy combining a Fay-regime spreading-rate estimate from slick area and a backscatter-contrast decay term. Output a *range* in hours with `confidence: "low"` and a `method_note` string that appears in the UI.
5. Wire `POST /api/detect` to real output. Delete the fixture path.

**Acceptance:** real polygon and real geometry numbers render on the map from the frozen case, plus at least one rejected lookalike badge.

---

## Phase 3 — Drift engine, hindcast cone and forecast (Stage 2)

**Goal:** the demo's visual centrepiece. A particle cloud animating backward in time and collapsing into a shaded probability cone.

**Decision already made: do not use OpenDrift for this round.** Conda install pain, credentials, multi-GB downloads. Build our own and expose it behind an interface so the swap is a config change, which is a true and defensible claim.

Tasks:
1. `drift/fields.py`: load cached current+wind NetCDF via xarray, bilinear interpolation in space and time, with a graceful synthetic-field fallback.
2. `drift/engine.py`: define `DriftEngine` with `run(particles, t0, hours, direction)`. This is the seam an OpenDrift adapter would plug into later.
3. `drift/lagrangian.py`: NumPy ensemble advector. Per timestep per particle: `dx = (u_current + 0.03 * u_wind) * dt + random_walk(K_diffusion)`. Seed particles by sampling inside the slick polygon. Run with `direction = -1` for hindcast, `+1` for forecast. 500 particles, 15-minute timestep, vectorised. Target under 2 seconds for 24 hours of simulation.
4. `drift/cone.py`: at each output timestep, convert the particle cloud into 50th and 90th percentile containment polygons (KDE or alpha-shape/convex-hull over the densest fraction). Produce the origin estimate as the mode of the final cloud plus an uncertainty radius and a time window.
5. Wire `/api/drift/hindcast` and `/api/drift/forecast`.

**Sensitivity note for the deck:** run the ensemble at 2%, 3% and 4% wind-drift factors and show that the cone widens. That single slide demonstrates genuine uncertainty awareness.

**Acceptance:** hindcast returns a per-timestep cone and an origin estimate whose 90% polygon contains the ground-truth origin from `case.json`. Forecast returns a forward path. Both under 3 seconds.

---

## Phase 4 — AIS attribution and scoring (Stage 3)

**Goal:** the differentiator. Most teams will not build this.

Tasks:
1. `attribution/ais_ingest.py`: parse the AccessAIS extract, group by MMSI, sort by time, reconstruct tracks, interpolate to a common time grid, drop implausible jumps.
2. `attribution/gaps.py`: detect reporting gaps above a threshold (default 30 minutes), record gap start/end/duration and the interpolated position across the gap.
3. `attribution/filters.py`: prune to vessels whose track comes within `search_radius_km` of the origin estimate during the origin time window. Report `total_vessels_in_region` and `after_filter` so the UI can show traffic being filtered down. That before/after number is a great demo beat.
4. `attribution/scoring.py`: weighted composite with each factor normalised to 0-1 and returned individually:
   - `proximity` — minimum distance from track to origin estimate, weighted by the cone's probability density at the closest approach, not just raw distance.
   - `temporal_overlap` — overlap between the vessel's presence and the estimated origin time window.
   - `heading_consistency` — whether the vessel's course is consistent with a discharge that would produce the observed slick orientation.
   - `ais_gap` — a gap overlapping the origin window scores high. This is the dark-vessel signal.
   - `speed_anomaly` — slow steaming or an unusual manoeuvre near the origin.
   Default weights: proximity 0.30, temporal 0.25, ais_gap 0.20, heading 0.15, speed 0.10. Make weights configurable and return them in the response so scoring is auditable rather than magic.
5. Set `DARK_VESSEL` flag when an AIS gap materially overlaps the origin window.
6. Generate a one-sentence `narrative` per candidate from the breakdown, for example: "Went AIS-dark for 94 minutes while transiting within 3.1 km of the estimated origin."
7. **Validate against ground truth:** the injected polluter must rank #1. Record the score margin over #2. That margin is a number to put in the deck.

**Acceptance:** `/api/attribute` returns 3-5 ranked candidates with full breakdowns; the ground-truth polluter is rank 1; at least one candidate carries `DARK_VESSEL`.

---

## Phase 5 — Dashboard (Stage 4)

**Goal:** the thing judges actually look at. This runs in parallel with Phases 2-4 against mocks from day one.

Tasks:
1. `MapView`: MapLibre with a dark basemap, the SAR patch as a raster overlay, layer toggles for slick / lookalikes / hindcast cone / forecast path / AIS tracks / candidate tracks.
2. `DetectionPanel`: geometry readout, confidence, method badge (classical vs U-Net), age range with its visible low-confidence caveat, rejected-lookalike chips with reasons.
3. `DriftControls`: "Backtrack 24h" and "Forecast 12h" buttons, particle animation over the timeline, cone rendered as two nested translucent polygons (90% outer, 50% inner) with an origin marker and its uncertainty circle.
4. `VesselTable`: ranked candidates, score bar, flags, click to select. Selecting highlights that vessel's track on the map and dims the rest.
5. `ScoreBreakdown`: horizontal bars per factor with the weight shown, plus the narrative sentence. This panel is what makes the system explainable rather than a black box.
6. `EvidencePanel`: provenance list, processing steps with durations, and the "Generate Evidence Report" button.
7. Persistent banner: "Constructed validation scenario — real Sentinel-1 imagery and real AIS traffic, synthetically co-located. See methodology."
8. Visual identity: pick one accent colour, one type pairing, dark theme (maps read better dark and it looks like an operations console). Add a `SpillTrace` wordmark in the header.

**Acceptance:** the entire demo narrative is clickable end to end with no dead controls and no console errors.

---

## Phase 6 — Evidence report

Tasks:
1. `report/pdf.py` with reportlab: case ID, scene ID and acquisition time, processing chain with model versions and parameters, detection geometry, hindcast origin with uncertainty, ranked candidates with full score breakdowns, and an explicit limitations section written in the language of confidence rather than verdict.
2. Embed a static map snapshot if cheap; skip it if not.
3. `POST /api/report` returns the PDF; the frontend downloads it.

**Acceptance:** one click produces a PDF a judge could plausibly read as a case file.

---

## Phase 7 — U-Net detection upgrade (optional, cuttable)

Run this on Colab in the background from Phase 2 onward. It must never block anything.

Tasks:
1. `ml/train_unet.ipynb`: U-Net or DeepLabv3+ with an ImageNet-pretrained ResNet34 backbone (`segmentation_models_pytorch`), fine-tuned on the Zenodo dataset's 5 classes (sea, oil, lookalike, ship, land). Heavy augmentation. Report mIoU on a held-out split.
2. Export weights to `ml/weights/`, load in `detection/unet.py`, and expose it as `method: "unet"` behind a config flag.
3. Keep the classical detector selectable in the UI as "fast mode" so the fallback is a feature, not a patch.

**Acceptance:** if mIoU beats the classical baseline on the held-out split, ship it as default. Otherwise leave it off and say nothing more about it.

---

## Phase 8 — Demo hardening and deck

Tasks:
1. **Full offline test.** Disconnect from the network and run the entire demo. Anything that breaks gets cached or stubbed.
2. Seed all randomness. The hindcast cone must look identical every run. A cone that jitters between rehearsals will get questioned.
3. Warm-start: preload the case on app start so nothing spins during the demo.
4. Error boundaries on every panel so one failure cannot white-screen the app.
5. **Record a screen capture of the full working demo** and put it in the deck as insurance.
6. Write the 6-minute demo script with explicit click order and the two framing lines:
   - "We don't accuse a vessel. We produce a ranked, evidence-backed suspect list with a confidence score, because the physics genuinely doesn't support certainty, and a system that pretends otherwise is useless in court."
   - "This runs on the officially provided Zenodo and AccessAIS data. Swapping in ISRO's SAR and India's NAIS feed is a data-source change, not a redesign."
7. Deck outline: problem and cost -> why attribution is unsolved -> architecture diagram -> live demo -> what's real vs simulated (own this slide) -> limitations we already know (revisit time, lookalikes, AIS spoofing, hindcast uncertainty) -> production path with ISRO/INCOIS/IMAC -> team.
8. Prepare answers to the judge questions in `research.md` §34. Rehearse the AIS-off and lookalike answers until they are reflexive.
9. Three full rehearsals, at least one with someone outside the team interrupting with questions.

**Acceptance:** two consecutive clean run-throughs, offline, under 7 minutes.

---

## Suggested schedule (3-4 days, 2-3 builders)

| When | Frontend builder | Backend builder | Claude |
|---|---|---|---|
| Day 0 evening | Phase 0 frontend scaffold | Phase 1 case study freeze | Phase 0 contract + fixtures |
| Day 1 | Phase 5 map + panels on mocks | Phase 4 AIS ingest, gaps, scoring | Phase 2 detection + Phase 3 drift; kick off Phase 7 |
| Day 2 | Wire real endpoints; cone rendering; animation | Finish scoring; ground-truth validation | Integrate; fix the seams; age estimation |
| Day 3 | Polish, visual identity, error boundaries | Phase 6 report | Phase 7 evaluation; Phase 8 hardening |
| Day 4 AM | Freeze. Rehearse. Record the backup video. | | |

---

## Definition of done for the internal round

- [ ] Full click-through works offline in under 7 minutes.
- [ ] Hindcast 90% cone contains the ground-truth origin.
- [ ] Injected polluter ranks #1 with a stated score margin over #2.
- [ ] At least one candidate flagged DARK_VESSEL.
- [ ] At least one lookalike visibly rejected with a reason.
- [ ] Evidence PDF generates in one click.
- [ ] Constructed-scenario disclaimer visible in the UI.
- [ ] Backup demo video recorded.
- [ ] Every judge question in `research.md` §34 has a rehearsed answer.
