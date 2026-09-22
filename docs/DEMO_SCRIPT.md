# OASIS — 7-Minute Demo Video Script

**Problem statement:** SIH26143 (NTRO) — use Sentinel-1 SAR imagery to detect oil
spills at sea and correlate with AIS data to identify the responsible vessel.

**Goal of this video:** show a judge, in 7 minutes, that OASIS takes a raw SAR
scene all the way to a ranked, evidence-backed list of suspect vessels — the
full **what → where/when → who** pipeline — with nothing hand-waved, plus the
operational and reporting layers built on top of it.

Total runtime target: **7:00**. Timings below are per-section budgets, not
strict cues — go a few seconds over/under a section but lands the video at ~7:00.

---

## Before you hit record

1. Start both servers so the app is live, not fixture-only, if the backend demo
   pipeline is ready:
   ```bash
   ./scripts/check.sh --serve
   ```
   If the backend isn't ready for a clean run, it's fine — the frontend falls
   back to bundled fixtures automatically and shows an `OFFLINE FIXTURES`
   badge. Either mode is demoable; just don't call fixture data "live" in the
   voiceover.
2. Open the app at `http://localhost:5173` in a clean, full-screen browser
   window (hide bookmarks bar, close devtools).
3. Pre-expand nothing — start from a fresh page load on **Overview** so the
   hero section and vitals animate in on camera.
4. Have a script/teleprompter ready so pacing stays tight — there is no time
   to ad-lib.
5. Decide narration mode: voiceover recorded after screen capture (recommended
   — lets you re-take narration without re-doing clicks) or live narration
   while recording. Script below is written for either.
6. Do one full rehearsal pass with a stopwatch. At 7 minutes the margin for
   error is smaller than it feels — a 10-second overrun per section compounds
   to nearly a minute by the end.

---

## 0:00–0:30 — Cold open: the problem (no UI yet, or Overview hero only)

**Say:**
> "When an oil spill is detected at sea, investigators can see *that* it
> happened — but proving *who* caused it, days later, from a moving vessel
> and a drifting slick, is the hard part. The slick itself doesn't carry a
> signature. By the time a response team is on scene, the vessel responsible
> could be hundreds of kilometers away, transponder back on, looking exactly
> like every other ship in the shipping lane. OASIS is a system built for
> exactly that gap: it takes a satellite radar image, detects the spill,
> hindcasts where and when it started, and cross-references AIS ship-tracking
> data to produce a ranked, confidence-scored list of suspect vessels — never
> a blind accusation, always an explainable one."

**Do:** Sit on the Overview page hero (MarineTraffic live map band + vitals
grid: Active Incident / Slick Area / etc.) while you say this.

---

## 0:30–1:15 — Overview dashboard (orientation)

**Say:**
> "This is the command dashboard. One active incident in the Gulf of Mexico —
> slick area, drift confidence, and impact flags are computed live from the
> pipeline, not hardcoded. Down the left is the investigation flow: Maritime
> Map, Satellite Intelligence, Drift Intelligence, Attribution, Reroute
> Simulation, Reports, Alerts, and Data Sources — that's the order a real
> analyst would work in, and it's the order I'll walk through. Each stage
> hands validated output to the next: detection feeds drift, drift feeds
> attribution, attribution feeds the report. Nothing here is a standalone
> demo screen — it's one continuous pipeline."

**Do:**
- Let the vitals cards (Active Incident, Slick Area, etc.) be visible.
- Hover down the sidebar nav slowly enough that each label is readable,
  without clicking yet.
- Briefly hover over the live map band to show it's an interactive
  MarineTraffic layer, not a static image.

---

## 1:15–2:15 — Satellite Intelligence (Stage 1: detection — "what")

**Say:**
> "This is where it starts: a Sentinel-1 SAR scene. Radar imaging works day
> or night, through cloud cover, which is exactly why it's the right sensor
> for spill detection — optical satellites are useless over a cloudy ocean.
> Dark patches on radar can mean an oil slick — or they can mean a
> look-alike: low wind, algae, a current shear line. OASIS runs classical
> detection plus geometry and texture analysis to tell the difference, then
> estimates the slick's age from how it's spread and thinned."

**Do:**
- Navigate to **Satellite Intelligence**.
- Show the SAR image with the detected slick overlay.
- Expand one section card (e.g. detection evidence / backscatter stats) to
  show real numbers, not just a shape on a map.
- Use the upload panel to drop a sample scene (`Sentinel-1 (500m)` or
  `ALOS PALSAR (250m)` from the built-in samples) and let it run detection
  live, then land on this page automatically. This is the strongest "it
  actually runs" beat in the whole video — don't cut it if you have 7
  minutes to work with.

**Say (while upload/detection is running):**
> "This isn't replaying a cached result — it's running the actual detection
> model against a fresh scene right now."

**Say (once overlay/evidence is on screen):**
> "IoU against ground truth on our frozen case study is 0.878 — this isn't a
> demo-only shape, it's a validated detector. And critically, the detector
> also outputs a confidence and a look-alike likelihood, so downstream stages
> know how much to trust this input rather than treating every detection as
> certain."

---

## 1:45–2:35 — Drift Intelligence (Stage 2: hindcast/forecast — "where and when")

**Say:**
> "Detecting the slick only tells you where it is *now*. To find the
> responsible vessel we need to know where it *started* — so OASIS runs a
> bidirectional Lagrangian drift model: backward to estimate the origin point
> and time, forward to forecast where the slick is heading next, using wind
> and current data as an ensemble, not a single deterministic guess."

**Do:**
- Navigate to **Drift Intelligence**.
- Trigger the hindcast (if not already run) — show the spinner/compute state
  briefly, this proves it's a real computation.
- Show the drift cone on the map and the timeline scrubber; drag the
  timeline once to show forward/backward animation.
- Point at the origin estimate (lat/lon + time) and the forecast impact
  flags.

**Say:**
> "Origin error on our validated case study is 7.7 kilometers — accurate
> enough to narrow the AIS search window to a specific place and time window,
> which is exactly what Attribution needs next."

---

## 2:35–3:35 — Attribution (Stage 3: AIS correlation — "who")

**Say:**
> "This is the core of the problem statement: given the estimated spill
> origin and time window, which vessels were plausibly there? OASIS pulls AIS
> tracks, detects transponder gaps — a vessel going dark is itself a signal —
> and scores every nearby vessel against multiple independent factors:
> proximity to the origin, timing, course consistency, vessel type, and
> AIS-gap behavior."

**Do:**
- Navigate to **Attribution**.
- Show the ranked vessel list / score breakdown component.
- Expand the score breakdown for the top-ranked vessel — show the individual
  factor scores (SCORE_FACTORS), not just a single number.
- Explicitly show a lower-confidence or "insufficient evidence" case if the
  fixture has one — this is what makes the system credible to judges: it
  doesn't over-claim.

**Say:**
> "Every score is explainable — you can see exactly which factors pushed a
> vessel up or down the list. This is deliberately never a final
> identification — it's a ranked, evidence-backed candidate list for
> investigators to act on."

---

## 3:35–4:10 — Reroute Simulation (operational value-add)

**Say:**
> "Beyond attribution, OASIS has operational use too: given the drift
> forecast, we can plan spill-avoidance routes for other vessels in the area.
> This uses a grid-based A* routing engine that treats the forecasted slick
> as a no-go zone."

**Do:**
- Navigate to **Reroute Simulation**.
- Click a start point and an end point on the map.
- Show the computed route bending around the slick/hazard zone.
- (Optional, if time allows) trigger a re-plan to show the `/replan`
  endpoint reacting to updated drift data.

---

## 4:10–4:40 — Reports & Alerts (closing the loop)

**Say:**
> "Every incident rolls up into an evidence report — detection imagery, drift
> path, and the scored vessel list, in one exportable package for
> investigators or regulators. And the Alerts view keeps the whole team
> aware of active and resolved incidents in real time."

**Do:**
- Navigate to **Reports** — show the generated report content for the
  current case.
- Quick cut to **Alerts** — show the incident list/badges.
- (Optional) **Data Sources** — a 5-second glance to show what feeds the
  system (Sentinel-1, AIS, wind/current models) if time allows; cut it first
  if you're running long.

---

## 4:40–5:00 — Close

**Say:**
> "That's OASIS: one pipeline from a raw SAR scene to a ranked, explainable
> list of suspect vessels — detection, drift, and attribution, backed by
> validated accuracy at every stage, built for SIH26143."

**Do:** End on the Overview dashboard or a wide shot of the Attribution
ranked list — whichever is more visually convincing as a closing frame.

---

## Timing cheat-sheet

| Segment | Time | Cumulative |
|---|---|---|
| Cold open (problem) | 0:25 | 0:25 |
| Overview dashboard | 0:35 | 1:00 |
| Satellite Intelligence (detection) | 0:45 | 1:45 |
| Drift Intelligence (hindcast/forecast) | 0:50 | 2:35 |
| Attribution (AIS scoring) | 1:00 | 3:35 |
| Reroute Simulation | 0:35 | 4:10 |
| Reports & Alerts | 0:30 | 4:40 |
| Close | 0:20 | 5:00 |

## Cut-first list (if you're running over 5:00)

1. Reroute Simulation replan demo (keep only the initial route).
2. Data Sources glance.
3. Live upload demo on Satellite Intelligence — use a pre-loaded case instead.
4. Alerts page — mention verbally over Reports instead of switching pages.

## Add-if-you-have-extra-time list

1. A second, lower-confidence Attribution case to show the system isn't
   overconfident.
2. The `OFFLINE FIXTURES` badge callout, if backend is down, explaining the
   frontend/backend split resilience.
3. A quick sidebar-collapse toggle to show UI polish.

---

## Recording checklist

- [ ] Backend + frontend both running, or fixtures confirmed working
- [ ] Browser full-screen, bookmarks/devtools hidden
- [ ] Case study data loaded (frozen Gulf of Mexico case)
- [ ] Script rehearsed once end-to-end for timing before final take
- [ ] Screen resolution ≥ 1920×1080 for crisp text in map overlays
- [ ] Audio recorded separately or with a decent mic — narration clarity
      matters as much as the visuals for judges skimming many submissions
