# Research Dossier — SIH26143

**Title:** Leveraging satellite imagery to determine Oil spills at sea along with AIS data correlations to identify vessel responsible for the spill.
**Organization:** National Technical Research Organisation (NTRO)
**Category:** Software · **Theme:** Space Technology · **Deadline:** 20 September 2026

## Official Problem Statement (verbatim)

**Background:** Marine oil spills inflict great damage on marine ecosystems and several times remain un-attributable to the vessel causing such spills. Leveraging satellite imagery along with AIS data will enable detection of oil spills and the vessel responsible for the same.

**Description:** The core challenge attempts to facilitate detection of oil spills and also identifying the polluting vessel using remote sensing satellite data (SAR and EO imagery) and AIS data. Participants are to design an intelligent automated pipeline to do the following:
- **(a)** Detect and characterise the oil spill and calculate geometric properties and age, if feasible.
- **(b)** Using oceanographic and meteorological data, trace the slick backward toward its origin point and time (hindcast), and predict the future flow of the slick (forecast).
- **(c)** Analyse and attribute the spill to a vessel using historic AIS data to reconstruct vessel traffic around the origin window in space and time. Irrelevant traffic is to be filtered out, and potential suspect vessels are to be scored considering aspects such as proximity, trajectory, and behavioural anomalies.

**Expected Solution:** An automated detection and hindcasting machine-learning model that identifies oil slicks from satellite imagery, maps their drift paths both backward and forward, and ranks potential culprit vessels based on spatio-temporal correlation with AIS data. A suitable visual interface is also to be developed.

**Officially provided data sources:**
- **AIS data**: sample AIS data / format available at [marinecadastre.gov/accessais](https://marinecadastre.gov/accessais/) (AccessAIS — NOAA/BOEM's U.S. AIS vessel-traffic download tool). Real AIS data may be used where available; **otherwise synthetic AIS data may be generated for the region of the chosen oil spill** to demonstrate the algorithm — this is explicitly sanctioned by the problem statement, not a fallback the team has to justify apologetically.
- **Satellite imagery**: Zenodo — *"Sentinel-1 SAR Oil Spill image dataset for train, validate, and test deep learning models"* (a 3-part released dataset — see §17 for direct links and structure).

> **Note on this document:** This dossier was originally drafted from a bare-title version of the PS (no description was published in the source tracking sheet at the time). It has since been fully revised against the **official Background/Description/Expected-Solution text and dataset links above**, which are now the authoritative scope for the project. All findings from the original broader research pass (competitor landscape, Indian ecosystem, legal context, technical literature) remain valid background — they are retained and re-organized around the now-explicit four-part deliverable: **(1) detect + characterise + age-estimate**, **(2) hindcast + forecast drift**, **(3) AIS-based suspect-vessel scoring**, **(4) visual interface**.

---

## 1. Problem Statement Understanding

The official description decomposes into **four explicit deliverables**, in order of pipeline flow:

**(1) Detection + characterisation + age estimation.** Given SAR/EO satellite imagery, detect an oil slick, segment its extent, and derive geometric properties (area, perimeter, shape/elongation, orientation) — and, "if feasible," estimate its **age** (how long since the discharge). Age estimation is the most technically demanding and least standardized sub-requirement here: it typically relies on how a slick's backscatter signature, thickness, and shape evolve as it weathers (spreads, thins, emulsifies, evaporates) over time — there is no single universally agreed algorithm for this in the literature, so "if feasible" is a meaningful hedge the PS authors are giving teams (see §19, §29).

**(2) Hindcast + forecast drift modelling.** Using oceanographic (currents) and meteorological (wind) data, run a **drift/trajectory model** in two directions from the detected slick's position and time: *backward* (hindcast) to estimate the likely origin point and time of discharge, and *forward* (forecast) to predict where the slick will go next (relevant for both attribution and spill-response planning). This is explicitly bidirectional — most academic "backtracking" papers found in research only run the model backward for attribution; the PS additionally wants the forward/operational-response half.

**(3) AIS-based vessel attribution and scoring.** Reconstruct vessel traffic in the space-time window around the *hindcast-estimated origin* (not just around the observed slick location, which may be far from the origin by the time it's detected) using historic AIS data. Filter out irrelevant traffic (vessels far away, wrong heading, wrong type), then **score** remaining candidate vessels on multiple weighted signals: **proximity** (spatial distance to estimated origin at estimated origin time), **trajectory** (heading/speed consistency with having been at that point), and **behavioural anomalies** (e.g., AIS gaps, sudden course/speed changes, loitering, deviation from expected shipping lanes — signals associated with deliberate evasion, not just a scoring afterthought).

**(4) Visual interface.** A dashboard/UI to present the detected slick, its geometric/age characterisation, the hindcast/forecast drift paths, and the ranked suspect-vessel list with scores — i.e., the analyst-facing output, not just a backend model.

**Why this is harder than "detect oil + match AIS":** the attribution step is explicitly *not* "find the AIS track that intersects the visible slick" — by the time a satellite captures the slick, it may have drifted far from the discharge point (see §29 on revisit-time-vs-drift-speed). The PS's own structure (hindcast origin *first*, then search AIS around *that* window) reflects this correctly and is the right approach the literature also converges on. It also explicitly treats attribution as **adversarial and probabilistic** (behavioural-anomaly scoring implies some suspects will have tried to hide), not a deterministic lookup — see §11, §30, §31.

The team retains real latitude on: which region/historical spill event to build the demo around (the Zenodo dataset and AIS sources are not India-specific — see §17), what specific weighting scheme to use for the suspect-vessel score, and what age-estimation method (if any) to attempt.

---

## 2. Why This Problem Exists

Oil pollution enforcement at sea has a structural detection gap that has existed since the earliest days of shipping regulation, worsened by three factors:

- **The ocean is enormous and largely unsurveilled.** No terrestrial sensor network can watch open water continuously; only satellites offer full-EEZ coverage, and even they are constrained by orbital revisit schedules (§13, §29).
- **Illegal discharge is a *deliberate*, self-concealing act**, not an accident that leaves obvious forensic traces. Operators who bypass oily-water separators ("magic pipes") or conduct illegal tank-washing at sea do so specifically because the ocean offers no witnesses — historically, **76% of successful U.S. MARPOL prosecutions (1993–2017) originated from whistleblowers**, not from independent detection, showing how weak passive/enforcement-driven detection has been ([M-Info](https://www.m-info.org/post/prosecution-in-us-for-marpol-violations)).
- **AIS, the main vessel-identity system, is voluntary and disableable by design.** It was built for collision-avoidance safety, not law enforcement — there is no cryptographic or tamper-proof binding between a vessel and its AIS broadcast, so the exact population you want to catch (deliberate polluters) is the population most able and motivated to go dark, spoof position, or reuse another vessel's identity.

In short: the problem exists because **detection technology (satellites) and identification technology (AIS) were built independently, for different purposes, by different actors, and nobody has closed the loop between "we saw oil" and "we know who put it there"** in a systematic, automated, evidentiary-grade way — especially not in the Indian context.

---

## 3. Why It Matters / Real-World Impact

**Documented incidents near India:**

- **Chennai/Ennore, Jan 2017**: Tankers *BW Maple* and *Dawn Kanchipuram* collided ~2nm off Kamarajar Port; ~20–75 tonnes spilled; oil fouled 35+ km of coastline within a week and reached Mahabalipuram (75 km south) within two weeks; port officials initially denied damage, delaying cleanup ([Wikipedia](https://en.wikipedia.org/wiki/2017_Ennore_oil_spill)).
- **Mumbai, Aug 2010**: *MSC Chitra* collided with *MV Khalijia II*; 400–1,000 tonnes of heavy fuel oil spilled — the largest slick in Indian history at the time (~25 km²); 110 km of coastline affected, 70% of it mangroves/mudflats; ~400 containers (31 hazardous) fell overboard ([Wikipedia](https://en.wikipedia.org/wiki/2010_Mumbai_oil_spill)).
- **Kerala, May 2025**: The Liberia-flagged *MSC ELSA 3* sank ~38nm off Kochi carrying 84 tonnes diesel + 367 tonnes furnace oil plus hazardous cargo. Coast Guard aircraft spotted the slick within 2–3 hours; **ISRO's EOS-4 SAR satellite was used to detect the spill on 27 May 2025**, two days after the sinking ([ISRO/IIRS](https://science.iirs.gov.in/eos-4-detects-oil-spill-near-kerala-coast-on-27-may-2025/)). Kerala declared a state disaster.
- **X-Press Pearl, Sri Lanka, May 2021**: Regional Indian Ocean precedent — described by UNEP as the worst maritime pollution ever in the Indian Ocean, releasing plastic nurdles, oil, and heavy metals with severe transboundary fisheries impact ([UNEP](https://www.unep.org/resources/report/x-press-pearl-maritime-disaster-sri-lanka-report-un-environmental-advisory-mission)).

**Scale of the problem globally:** ITOPF recorded only 6 tanker spills in 2025 (~4,000 tonnes total) — a >90% reduction since the 1970s ([ITOPF](https://www.itopf.org/news/news/itopf-publishes-2025-oil-tanker-spill-statistics/)). But this tracks only *accidental large tanker spills*. The much bigger, chronic, and largely invisible problem is **illegal operational discharge** — deliberate bilge dumping and tank washing at sea — estimated by one source at roughly 5x the volume of the Exxon Valdez spill *every year* (treat as an approximate, not precisely sourced figure). This is exactly the class of pollution AIS-based attribution targets, because it's caused by identifiable vessels making a deliberate choice, not by catastrophic accidents.

**Legal significance:** Under UNCLOS Article 220, a coastal state's right to detain and prosecute a foreign vessel in its EEZ scales with the strength of evidence — it requires "clear and objective evidence" of a substantial discharge causing major pollution. Satellite + AIS correlation is precisely the kind of evidence UNCLOS anticipates. This has already worked once: in the **Maersk Kiera case (Feb 2012)**, EMSA satellite detection cross-referenced with AIS tracks was accepted as **primary evidence in a UK court**, resulting in a conviction ([EMSA](https://www.emsa.europa.eu/csn-menu/csn-service/oil-spill-detection-examples/286-oil-spill-detection-examples/1873-oil-spill-detection-examples-maersk-kiera-february-2012.html)) — proof that this exact technical approach has real prosecutorial value, not just environmental-monitoring value.

**India's legal gap makes this doubly important:** India's Merchant Shipping Act, 1958 currently provides only **civil liability** for oil pollution, with no dedicated criminal penalty regime; prosecutors fall back on IPC §278 (public nuisance), capped at a token ₹500 fine ([IJPIEL](https://ijpiel.com/index.php/2021/09/02/oil-spill-liability-responses-under-indian-law-time-for-an-integrated-regulatory-framework/)). Better detection/attribution technology only pays off if paired with legal reform — worth noting as context, not something the team can fix, but something that frames realistic impact claims.

---

## 4. Current Situation and Existing Workflow (India)

Today, India's response to a spill is largely **reactive and manual, not automated or continuous**:

1. A spill is usually first noticed via **aerial reconnaissance** (Indian Coast Guard Dornier-228 aircraft with pollution-surveillance gear), a vessel's own report, or a member of the public — as in the Kerala 2025 case where ICG aircraft spotted the slick within 2–3 hours of the sinking, before any satellite tasking occurred.
2. **INCOIS** (Indian National Centre for Ocean Information Services, under MoES) then provides an **Online Oil Spill Advisory Service** — but this is a *drift-prediction/advisory tool* (models where the oil will go next for cleanup planning), not a detection or attribution system ([INCOIS](https://incois.gov.in/)).
3. **ISRO's SAR satellites (RISAT-1, EOS-4)** have been used **reactively, on-demand, for specific known incidents** — e.g., EOS-4 imaged the Kerala spill two days after the sinking was already known via other means — rather than running continuous automated surveillance of the EEZ ([ISRO/IIRS](https://science.iirs.gov.in/eos-4-detects-oil-spill-near-kerala-coast-on-27-may-2025/)).
4. Response coordination follows the **National Oil Spill Disaster Contingency Plan (NOS-DCP)**, with the Indian Coast Guard as the designated national authority, using booms, skimmers, and dispersants once a spill is confirmed.
5. Separately, the Navy's **IMAC (Information Management and Analysis Centre)** — being upgraded into a National Maritime Domain Awareness (NMDA) Centre — fuses coastal radar, AIS, and shipping-database data to track >120,000 vessels/year transiting the Indian Ocean, but there is **no public evidence it ingests satellite-derived oil-slick detections or performs automated slick-to-vessel correlation** ([Swarajya](https://swarajyamag.com/news-brief/upgrading-indias-maritime-vigilance-indian-navys-imac-to-transform-into-national-maritime-domain-awareness-centre); [Maritime Gateway](https://www.maritimegateway.com/national-maritime-domain-awareness-nmda-project/)).
6. Vessel identification/attribution, when it happens at all, appears to rely on **circumstantial evidence and manual investigation** after the fact, not a systematic satellite+AIS matching pipeline.

**The clearest finding of this research**: *India already has every individual piece* — ISRO SAR satellites, INCOIS drift models, IMAC/NMDA AIS fusion, Coast Guard response assets — **but no evidence they are wired together into one automated detection→attribution→evidence pipeline**, the way EMSA's CleanSeaNet does for Europe. That gap is effectively the whole problem statement.

---

## 5. Who Faces This Problem / Stakeholders

- **Indian Coast Guard** — designated first responder and NOS-DCP authority; needs faster, corroborated detection to scramble aircraft/vessels and, separately, evidence to support enforcement action.
- **NTRO** — the sponsoring agency; per its IMINT/SIGINT/maritime-surveillance mandate, plausibly interested in this as much for the **general SAR+AIS fusion / dark-vessel-detection capability** (dual-use for maritime security, smuggling, sanctions evasion) as for the stated environmental use case (inference — no public NTRO statement confirms this explicitly, see §32).
- **Ministry of Earth Sciences / INCOIS** — currently owns drift-prediction; would be a natural consumer or co-owner of a detection+attribution capability.
- **Indian Navy (IMAC/NMDA)** — already ingests AIS at scale; a natural integration point rather than a competitor.
- **Coastal fishing communities and fisheries sector** — bear the direct economic brunt of spills (documented in the Chennai, Mumbai, and X-Press Pearl cases).
- **Port authorities and shipping companies** — legitimate vessels benefit from a system that can exonerate them (proving they were *not* the source) as much as one that accuses others.
- **Environmental regulators / courts** — end consumers of any "evidence" this system produces; their evidentiary standards (chain of custody, reproducibility) directly constrain system design (§23).
- **Foreign-flagged vessel operators transiting India's EEZ** — the actual targets of attribution; note India's jurisdiction over them is governed by UNCLOS Article 220 tiers, not unconditional (§3).
- **International bodies (IMO, flag states)** — if India cannot successfully prosecute domestically, evidence may need to be handed to a vessel's flag state under UNCLOS Article 228.

---

## 6. Existing Solutions and Competitors

| System | Operator | What it does | Relevance |
|---|---|---|---|
| **CleanSeaNet** | EMSA (EU) | Operational since 2007; SAR-based spill detection fused with AIS (via SafeSeaNet) for polluter identification; human analysts confirm candidates; <30 min alert to national authorities; 34 coastal states covered | **The single closest working analog to this PS.** Directly proves the concept is operationally viable and has been used successfully in court (Maersk Kiera case, §3). ([EMSA](https://www.emsa.europa.eu/csn-menu.html)) |
| **ERMA** (Environmental Response Management Application) | NOAA | GIS fusion tool built for Deepwater Horizon (2010); combines SAR slick outputs, AIS vessel positions (via USCG National AIS network), weather, shoreline status | Response-coordination tool, not an automated detection/attribution pipeline — useful as an architecture reference for the dashboard/fusion layer ([NOAA](https://response.restoration.noaa.gov/about/media/noaas-online-mapping-tool-erma-opens-environmental-disaster-data-public.html)) |
| **NOAA Marine Pollution Surveillance Reports** | NOAA/NESDIS | Near-real-time analyst-driven satellite anomaly detection, cross-referenced against known oil platforms/pipelines/wellheads/natural seeps to rule out non-vessel sources | Model for the "distinguish source type" sub-problem (§29) ([NOAA OSPO](https://www.ospo.noaa.gov/products/ocean/marinepollution/)) |
| **SkyTruth** (nonprofit) | SkyTruth + partners | Free-imagery-based independent pollution monitoring; famously proved BP's Deepwater Horizon flow-rate estimate was 5–25x too low; tracked a 14-year chronic leak that forced USCG intervention | Shows civil-society/independent-actor value of the same core technology ([Fast Company](https://www.fastcompany.com/40406093/how-satellite-data-caught-gulf-oil-companies-hiding-enormous-oil-spills)) |
| **Global Fishing Watch (GFW)** | Nonprofit (Oceana/Google/SkyTruth-founded) | Uses the full Sentinel-1 archive + ML to detect vessels **independent of AIS**, explicitly to catch "dark vessels" whose AIS is off; found **AIS misses ~90% of SAR-detected vessels** | **Most directly transferable prior art for the "identify the vessel" half of the PS**, especially for vessels trying to evade identification — the same logic (SAR sees a vessel; AIS doesn't corroborate) generalizes directly to spill attribution ([GFW](https://globalfishingwatch.org/research-project-dark-vessels/)) |
| **KSAT (Kongsberg Satellite Services)** | Commercial (Norway) | Operational oil-spill detection service, ground-station partner for many national coast guards | Commercial benchmark ([KSAT](https://www.ksat.no/earth-observation/environmental-monitoring/oil-spill-detection-service/)) |
| **Orbital EOS** | Commercial | AI + multi-sensor (radar+optical) spill monitoring, claims ~95% near-real-time detection accuracy, oil-thickness/volume estimation | Commercial benchmark ([Orbital EOS](https://www.orbitaleos.com/oil-spill-tracking/)) |
| **Windward** | Commercial (AIS-centric maritime risk analytics) | Frames AIS gaps as "dark activity" risk signal; fuses AIS with SAR/EO/RF detections and vessel-ownership/behavioral history | Directly relevant methodology for the attribution/ranking layer ([Windward](https://windward.ai/glossary/dark-activity/)) |

**Two named products from informal briefs ("OceanEye", "Bureau Veritas Terra Analytics") could not be verified as real existing products** in this research pass — flagged so the team doesn't cite them without independent verification.

**India-specific:** No operational Indian equivalent of CleanSeaNet was found. This is the clearest competitive white space (§9).

---

## 7. Existing Technologies Being Used

- **SAR satellites**: Sentinel-1 (C-band, ESA/Copernicus, free) is the global workhorse; RADARSAT-2, TerraSAR-X/TanDEM-X, COSMO-SkyMed (commercial/allied); India's RISAT-1 and EOS-4 (RISAT-1A) are the indigenous C-band SAR assets used reactively for domestic incidents.
- **Optical/multispectral**: Sentinel-2, Landsat-8, MODIS, VIIRS — useful for validation and daytime/clear-sky corroboration, but cannot see through cloud/darkness the way SAR can.
- **Classical CV pipelines**: adaptive/local thresholding or K-means for dark-spot segmentation, then GLCM texture features + SVM/Random Forest classification of oil-vs-lookalike.
- **Deep learning**: U-Net, DeepLabv3+, Mask R-CNN, and more recent hybrid CNN-transformer and domain-adapted Segment-Anything-Model approaches for joint segmentation + oil/lookalike discrimination (see §20 for specific papers/metrics).
- **AIS**: VHF transponder broadcasts (position, speed, course, MMSI, vessel type), aggregated terrestrially (coastal receiver networks — India's NAIS) and via satellite-AIS (S-AIS) for open-ocean coverage; commercial aggregators (Spire, MarineTraffic/Kpler, ORBCOMM/S&P Global) have consolidated heavily 2023–2025.
- **Drift/trajectory modeling**: NOAA's GNOME/PyGNOME, OpenDrift (open-source, Python, has a purpose-built "openoil" module), MEDSLIK-II, OSCAR, SIMAP, OILMAP — used to backtrack a detected slick to its likely origin point and time given ocean currents and wind.
- **Geospatial infrastructure in India**: Bhuvan (ISRO's public geoportal — a 2014 paper proposed an "Oil Spill Map for Indian Sea Region" on Bhuvan-GIS, unclear current operational status), MOSDAC (near-real-time dissemination center for ISRO meteorological/oceanographic missions, tiered/gated access), IMAC/NMDA's AIS+radar fusion infrastructure.

---

## 8. Limitations of Current Solutions

- **CleanSeaNet-style systems are restricted/regional** — EMSA's archive and alerts are not public and limited to EU/EFTA states; there's no equivalent open or Indian system.
- **Detection is fundamentally probabilistic and noisy** — look-alikes (biogenic slicks, low-wind zones, rain cells, current shear, grease ice) create persistent false positives that even modern CNNs haven't fully solved (best reported mIoU in the seminal benchmark paper is ~65%, not near-100%).
- **AIS-only correlation has a massive blind spot** — GFW's own research found AIS misses ~90% of SAR-detected vessels; any system relying solely on "whose AIS track passes through the slick" will systematically miss the most deliberate/malicious polluters, who are precisely the ones going dark.
- **Satellite revisit latency vs. spill drift speed** — a slick can drift, disperse, and become undetectable within hours to a few days, while a single-satellite SAR revisit can be as slow as 12 days (Sentinel-1 ran degraded, single-satellite, 2021–2024/25 after Sentinel-1B failed). Even the best-case 6-day revisit (achieved only once the full Sentinel-1C/1D constellation is operational, expected mid-2026) is not "real-time."
- **India-specific**: the pieces exist (ISRO SAR, INCOIS drift models, IMAC/NMDA AIS fusion) but aren't integrated; satellite tasking has so far been reactive (after a spill is already known via aerial spotting), not a continuous automated screen; no public system does automated slick-to-vessel matching.
- **Legal/evidentiary immaturity in India** — even a technically perfect system faces a legal system with only civil liability for oil pollution and no standardized framework for admitting satellite-derived evidence (contrast with EMSA's court-tested Maersk Kiera precedent).

---

## 9. Gaps in the Current Ecosystem

1. **No integrated Indian detection→attribution pipeline** — the single clearest, most defensible gap for a hackathon pitch: all the components exist in India, none are wired together.
2. **No public/open system addresses the "dark vessel" case for spill attribution specifically** — GFW does this for illegal fishing; nobody visibly does it for oil-spill attribution.
3. **No automated drift-backtracking-to-AIS matching pipeline** appears to be operational anywhere publicly documented outside of ad-hoc academic case studies (e.g., Syrian spill 2021, Mediterranean tracing studies) — this is a research-stage technique, not yet a hardened product.
4. **Evidentiary/chain-of-custody standardization gap**, both globally (courts scrutinize satellite-analysis pipelines case by case) and specifically in India (no codified framework for admitting this kind of evidence).
5. **Legal follow-through gap in India** (civil-only liability, negligible penalty caps) — a technology-only solution can't fully close this, but the team should be aware it exists so as not to overclaim real-world deterrence impact.

---

## 10. What Can Actually Be Improved

Given the above, realistic, achievable improvements a student team can meaningfully demonstrate:

- **Automate the fusion step**: build the pipeline that CleanSeaNet does manually (analyst cross-references slick + AIS) into a repeatable, auditable, semi-automated workflow.
- **Make attribution probabilistic and multi-signal**, not a brittle single-rule match — combining spatial proximity, drift-backtracked origin estimation, AIS-gap timing, vessel-type weighting, and (if available) historical behavior into a ranked confidence score, rather than a binary accusation.
- **Explicitly handle the dark-vessel case** as a first-class scenario (not an edge case) by flagging SAR-detected vessel signatures with no corroborating AIS track near the estimated spill origin/time — directly borrowing GFW's proven methodology.
- **Build in auditability/chain-of-custody from day one** (raw scene ID, model version, processing steps, timestamped AIS snapshot) — cheap to add, directly answers a documented real gap, and signals maturity to judges.
- **Be honest about latency/coverage limits** and frame the system as a triage/evidence tool that works whenever a satellite pass is available, with a clear upgrade path (more SAR sources, faster tasking) rather than falsely implying blanket real-time coverage.

---

## 11. Possible Solution Approaches

The official Expected Solution fixes the overall shape of the pipeline (detect+characterise → hindcast+forecast → AIS scoring → UI), so the team's real design decisions are about **depth and method** within each stage, not whether to build each stage at all:

- **Stage 1 depth (detection/characterisation/age)**: minimum viable = segmentation + basic geometry (area, perimeter, elongation); stretch goal = age estimation via a weathering/spreading proxy model (see §19). Given the PS itself says "age, if feasible," a defensible strategy is to implement a **simple, clearly-labeled heuristic age proxy** (e.g., relating slick area/perimeter growth and backscatter texture decay to elapsed time, calibrated against known spill timelines in the dataset) rather than skipping it — attempting it, even imperfectly, differentiates from teams that skip the hardest sub-requirement.
- **Stage 2 depth (hindcast/forecast)**: minimum viable = wrap an existing open-source drift engine (OpenDrift/PyGNOME) and run it bidirectionally from the detected slick's centroid/polygon using historical current+wind reanalysis data (e.g., HYCOM/OSCAR currents, ERA5 wind) for the chosen spill's date/region; stretch goal = ensemble/uncertainty-bounded hindcast (multiple perturbed runs producing a probability cone for origin, not a single point) — this is what real operational systems (MEDSLIK, Janeiro et al.'s Syrian-spill study) do and is a strong "we understood the uncertainty" signal for judges.
- **Stage 3 depth (AIS scoring)**: minimum viable = spatial+temporal proximity filter + a weighted score combining proximity, heading/course consistency, and an AIS-gap flag; stretch goal = a learned/ML scoring model (e.g., Isolation Forest for behavioural anomalies, as seen in the literature) instead of hand-tuned weights, plus explicit "dark vessel" candidates (SAR-detected vessel signatures — if using EO/SAR imagery that also resolves ships — with no AIS corroboration nearby).
- **Stage 4 depth (UI)**: minimum viable = a map (Leaflet/Mapbox) showing the slick polygon, hindcast/forecast paths, and a ranked vessel table; stretch goal = a timeline scrubber, confidence visualization (e.g., a "probability cone" rendering for the hindcast), and an exportable evidence/audit report per case.

**Recommended framing for a hackathon build**: implement all four stages at "minimum viable" depth first to have a working end-to-end demo early, then invest remaining time in the stretch goals most likely to stand out — per the research below (§35–37), the **AIS-scoring stage (3)** and **bidirectional drift modelling (2)** are where the least off-the-shelf tooling exists and where a genuinely useful contribution is most visible to judges, so they're the best places to spend extra depth if time is limited.

---

## 12. Potential Novelty / Innovation Opportunities

- **Fusing drift-backtracking with AIS-gap analysis in one scored pipeline** — individual pieces exist in the literature (drift models, AIS correlation, dark-vessel SAR detection) but a single system that chains all three (detect → backtrack origin/time → screen AIS for both "present nearby" and "suspiciously absent nearby" vessels → produce one ranked list) does not appear to have a widely publicized open-source or Indian-government reference implementation.
- **Explainable, audit-ready output** designed for downstream legal/enforcement use (confidence scores + full processing provenance) rather than just a research-paper-style accuracy metric — most academic work stops at IoU/F1, not at "would this hold up as evidence."
- **India-specific**: being the first (as far as this research found) to propose wiring together ISRO SAR + INCOIS drift models + AIS into one civilian-facing tool, explicitly designed to plug into IMAC/NMDA's existing AIS infrastructure rather than duplicating it.
- **Natural seep / infrastructure disambiguation**: incorporating a known-seep and known-infrastructure (rigs, pipelines, wellheads) overlay to automatically rule out non-vessel sources before running vessel attribution — NOAA does this operationally; building it in from the start would be a differentiator most hackathon teams likely skip.
- **Dual framing for NTRO**: presenting the "dark vessel" detection module as generalizable beyond oil spills to broader maritime domain awareness (smuggling, sanctions evasion) may resonate strongly with NTRO's actual mandate, if pitched carefully as a bonus capability rather than mission creep away from the stated environmental problem.
- **Attempting spill-age estimation at all**: the PS explicitly hedges this as "if feasible," meaning it's likely the least-attempted sub-requirement across submissions. Even a simple, honestly-caveated heuristic (e.g., regressing elapsed time against slick area growth + backscatter texture decay, calibrated on known-timeline spills in the Zenodo dataset) would differentiate a submission, since most academic literature reviewed doesn't treat age estimation as a solved or commonly implemented step.
- **True bidirectional (hindcast *and* forecast) drift modelling**: most academic prior art (Janeiro et al., Zodiatis et al., MEDSLIK-coupled studies) only runs backtracking for attribution. Explicitly also generating the forward forecast (useful for spill-response planning, not just blame) directly matches the PS wording and is an easy, high-signal addition once a bidirectional-capable engine like OpenDrift is already integrated.
- **Uncertainty-aware output** (a hindcast "probability cone" instead of a single point-estimate origin) rather than a false-precision single answer — mirrors how real oceanographic forecasting communicates uncertainty and would read as more scientifically credible to a judge panel evaluating a science-heavy PS.

---

## 13. Technical Requirements

### 13a. Hardware Requirements
- **No custom hardware needed** for a software-category PS. Standard requirements: a GPU (even a free-tier Colab/Kaggle GPU) for training/running the segmentation CNN; no specialized sensors, drones, or edge devices are implied by the problem statement.
- Real satellites (Sentinel-1, RISAT/EOS-4) are the "hardware" in the broader system, but the team consumes their data via APIs/downloads — no team-owned hardware involved.

### 13b. Software Requirements
- Python data/geospatial stack: `rasterio`, `GDAL`, `xarray`, `numpy`
- Deep learning framework: PyTorch or TensorFlow (for U-Net/DeepLabV3+ segmentation)
- SAR preprocessing: ESA's **SNAP** toolbox (S1TBX) for calibration/speckle filtering/orthorectification, or Google Earth Engine's pre-calibrated Sentinel-1 GRD collection
- Geospatial database: PostGIS (spatial indexing, `ST_DWithin`/`ST_Intersects` for the spatiotemporal join)
- Drift modeling: OpenDrift (Python, pip-installable, has a built-in `openoil` module) or NOAA's PyGNOME
- AIS decoding: `pyais` (Python AIVDM/AIVDO decoder)
- Backend: FastAPI (pairs naturally with the Python ML stack) or Django
- Frontend/dashboard: Leaflet, Mapbox GL, or deck.gl for map visualization; a timeline scrubber for temporal review

### 13c. AI/ML Requirements
- A semantic segmentation model (U-Net or DeepLabv3+ recommended, per literature benchmarks — DeepLabv3+ reported best mIoU ~65% on the standard MKLab benchmark) with a pretrained backbone (ImageNet-pretrained ResNet/MobileNet) fine-tuned on a small public oil-spill SAR dataset, since available labeled data is limited (hundreds to ~15,000 patches across known datasets).
- Optionally, a lightweight anomaly/classification model (Isolation Forest or similar) on AIS behavioral features for the "suspicious dark period" flagging — mirrors a documented hybrid framework combining Isolation Forest (AIS anomalies) + SVM (imagery classification).
- **Not required**: LLMs/NLP — this is a computer vision + geospatial/tabular data fusion problem, not a language problem (an LLM could optionally be used for a natural-language summary/report generator layer, but it is not core to the technical challenge).

### 13d. Data Requirements and Available Datasets
See the consolidated table in §17.

### 13e. APIs / External Services Required
See §18.

---

## 14–16. (See 13b/13c above — Software & AI/ML Requirements merged into §13 for coherence)

---

## 17. Data Requirements and Available Datasets

### 17a. Officially specified datasets (verified against the PS)

**Satellite imagery — Zenodo "Sentinel-1 SAR Oil spill image dataset for train, validate, and test deep learning models"** (this is the exact dataset named in the PS):

| Part | Content | Link |
|---|---|---|
| Part I | 1,200 Sentinel-1 SAR Sigma0 images (oil-spill class) + ground-truth masks, 2048×2048 TIFF, in dB | [zenodo.org/records/8346860](https://zenodo.org/records/8346860) |
| Part II | "No Oil" and "Lookalike" category training/validation images (same format) | [zenodo.org/records/8253899](https://zenodo.org/records/8253899) |
| Part III | Held-out test images | [zenodo.org/records/13761290](https://zenodo.org/records/13761290) |

This is a directly usable, no-registration-hassle, purpose-built dataset — it already includes the "lookalike" negative class needed to address the false-positive problem (§29), and ground-truth masks suitable for training a U-Net/DeepLabv3+ segmentation model out of the box. **This should be the team's primary training/validation dataset**, rather than the gated MKLab benchmark or community Kaggle mirrors considered earlier in this research (still listed below as supplementary options).

**AIS data — AccessAIS (marinecadastre.gov/accessais)**, NOAA/BOEM's public U.S. vessel-traffic tool:
- Provides an interactive web tool to download **real historical U.S. AIS data** for a user-defined region and time window, delivered as zipped CSV (older data was File Geodatabase format pre-2015; 2024+ bulk data is also available in GeoParquet) ([AccessAIS](https://marinecadastre.gov/accessais/), [NOAA Digital Coast](https://coast.noaa.gov/digitalcoast/tools/ais.html), [AIS FAQ PDF](https://coast.noaa.gov/data/marinecadastre/ais/faq.pdf)).
- Coverage is **U.S. waters only** — this is real, high-quality, free AIS data, but it constrains the team to demonstrating on a **U.S.-region historical spill** if using real AIS from this source. A companion bulk-download GitHub mirror also exists ([ocm-marinecadastre/ais-vessel-traffic](https://github.com/ocm-marinecadastre/ais-vessel-traffic)).
- **The PS explicitly permits synthetic AIS data** ("real AIS if available may be used else synthetic data can be prepared for the region of oil spill") — meaning the team is not required to force-fit a U.S. spill; a defensible approach is to pick whichever oil-spill scene from the Zenodo dataset has the best characteristics for the demo (clear slick, known ground truth), then generate a synthetic vessel-traffic scenario for that scene's actual region/time using AccessAIS's real data purely as a **format/behavioral-realism reference** (realistic speed/course distributions, gap patterns, vessel-type mixes).

### 17b. Supplementary/background sources (from broader research)

**Satellite (SAR) access, if pulling additional/fresh scenes beyond the Zenodo dataset:**

| Source | Cost | Access | Notes |
|---|---|---|---|
| Copernicus Data Space Ecosystem (Sentinel-1) | Free | openEO/Sentinel Hub APIs, OData/STAC | Copernicus publishes a worked "Oil spill mapping using Sentinel-1" openEO example notebook |
| Google Earth Engine | Free (research/education) | Python/JS API, `COPERNICUS/S1_GRD` | Pre-calibrated GRD — saves preprocessing time |
| ASF Vertex (Alaska Satellite Facility) | Free + limited free on-demand processing credits | `asf_search` SDK, HyP3 REST API | Good backup |
| ISRO Bhuvan / MOSDAC | Free but **gated**; NRT access is discretionary/case-by-case | Web portal, limited API maturity | Position as the real production data source in the pitch, not the demo data source |

**Other oil-spill/ship-detection datasets** (useful for pretraining, augmentation, or the ship-detection half if pursuing dark-vessel detection): MKLab/Krestenitis benchmark (gated, [m4d.iti.gr](https://m4d.iti.gr/oil-spill-detection-dataset/)), OpenSARShip (11,346 ship slices with AIS ground truth — useful for the SAR+AIS fusion half), xView3-SAR (GFW/DIU dark-vessel dataset), SSDD/HRSID (ship-detection benchmarks).

**Other open AIS sources** (if a non-U.S. region is preferred and synthetic data isn't desired): Global Fishing Watch (free research API, global coverage, data since 2012), Danish Maritime Authority (free, no registration, 2006–present), BarentsWatch/Norway (free live + historical).

### 17c. Oceanographic and meteorological data (needed for Stage 2 — hindcast/forecast, not explicitly named in the PS's dataset links but required by the Description)

| Source | Data | Access |
|---|---|---|
| **Copernicus Marine Service (CMEMS)** | Ocean current fields (surface currents, reanalysis + forecast) | Free, registration required, API access via `copernicusmarine` Python toolbox |
| **HYCOM** (HYbrid Coordinate Ocean Model) | Global ocean current reanalysis/forecast | Free, direct download/OPeNDAP |
| **ECMWF ERA5** | Wind reanalysis (surface wind speed/direction, hourly, global, back to 1940) | Free via Copernicus Climate Data Store, `cdsapi` Python client |
| **NOAA OSCAR** | Satellite-derived surface currents | Free |

These currents/wind fields are the direct inputs OpenDrift/PyGNOME need to run the hindcast/forecast — without them, Stage 2 of the PS cannot be built at all, so securing this data early is as important as the imagery/AIS sources.

---

## 18. APIs / External Services Required

- **Zenodo dataset downloads** (Sentinel-1 SAR oil-spill Parts I–III) — static files, no API key needed
- **AccessAIS** (marinecadastre.gov) — web tool / bulk CSV download, no API key for basic use
- **Copernicus Marine Service (CMEMS)** — ocean current data, free registration + API
- **Copernicus Climate Data Store (ERA5)** — wind data, free registration + `cdsapi`
- **Copernicus Data Space Ecosystem / Google Earth Engine** — only needed if supplementing the Zenodo dataset with fresh Sentinel-1 scenes
- **OpenDrift / PyGNOME** — not external services but open-source libraries invoked locally for drift modeling
- Optionally, a mapping tile provider (Mapbox, OpenStreetMap tiles) for the dashboard frontend
- Optionally, Global Fishing Watch API — only if the team chooses a non-U.S. region and wants real (rather than synthetic) AIS as a substitute for AccessAIS's U.S.-only coverage

---

## 19. Domains and Concepts Our Team Needs to Study

- **SAR physics fundamentals**: Bragg scattering, backscatter, incidence angle, why oil dampens capillary waves, wind-speed detection windows (~1.5–14 m/s), speckle noise
- **SAR image preprocessing**: radiometric calibration, terrain correction, speckle filtering (Lee/Refined Lee), land masking
- **Semantic/instance segmentation**: U-Net, DeepLabv3+, Mask R-CNN architectures; transfer learning with small datasets; IoU/F1 evaluation
- **AIS protocol basics**: NMEA/AIVDM message types, MMSI, dynamic vs. static data, satellite-AIS vs. terrestrial-AIS coverage differences
- **AIS evasion techniques**: spoofing, GPS/GNSS jamming, identity laundering, "going dark" — and how GFW/Windward detect these
- **Ocean drift/trajectory modeling**: how currents + wind determine oil movement, and how backtracking (running a drift model in reverse) estimates origin point/time; and forward-running the same model for spill-response forecasting
- **Oil weathering and age estimation**: how a slick's physical/optical/radar signature evolves over time as it spreads, thins, emulsifies, and evaporates — spreading-rate models (e.g., Fay's classical spreading theory) relate slick area growth to elapsed time; SAR backscatter/texture and (if EO imagery is available) color/thickness signatures also change with weathering stage. This is genuinely under-standardized in the literature (see §20's "thickness estimation" survey) — the team should expect to build a simplified, explicitly-caveated proxy rather than expect an off-the-shelf "age detector"
- **Maritime law basics**: UNCLOS Article 220/228 (coastal-state enforcement jurisdiction tiers), MARPOL Annex I, India's Merchant Shipping Act — enough to correctly frame what the system's output is *for*
- **Evidentiary/forensic standards for remote-sensing data** — chain of custody, reproducibility, what makes satellite-derived findings admissible
- **Basic geospatial engineering**: PostGIS, spatial joins, coordinate reference systems, polygon/vector operations

---

## 20. Relevant Research Papers and Academic Work

**Detection (segmentation/classification):**
1. Krestenitis et al. (2019), *"Oil Spill Identification from Satellite Images Using Deep Neural Networks,"* Remote Sensing 11(15):1762 — the field's benchmark dataset+paper; DeepLabv3+ best, mIoU ≈65%. ([MDPI](https://www.mdpi.com/2072-4292/11/15/1762))
2. Yekeen, Balogun, Wan Yusof (2020), *"A novel deep learning instance segmentation model for automated marine oil spill detection,"* ISPRS J. Photogrammetry and Remote Sensing 167:190-200 — Mask R-CNN, F1=0.968. ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0924271620301982))
3. "Large-scale detection and categorization of oil spills from SAR images with deep learning" (2020), Remote Sensing 12(14):2260 / [arXiv:2006.13575](https://arxiv.org/pdf/2006.13575)
4. "SAR Oil Spill Detection System through Random Forest Classifiers" (2021), Remote Sensing 13(11):2044
5. "Oils spills detection from SAR Earth observations based on hybrid CNN transformer networks" (2023), Marine Pollution Bulletin
6. "Marine oil spill detection and segmentation in SAR data with two steps Deep Learning framework" (2024) — MARINEXT vs U-Net/SegNeXt comparison, F1-macro 92.7%
7. "Detection of Oil Spill in SAR Image Using an Improved DeepLabV3+" (2024), Sensors 24(17):5460
8. "A Review of Artificial Intelligence and Remote Sensing for Marine Oil Spill Detection, Classification, and Thickness Estimation" (2025), Remote Sensing 17(22):3681 — comprehensive recent survey, good starting point for the team

**Attribution (SAR+AIS fusion):**
9. "A new ship tracing technology from oil spills based on multi-source data" (2024), Marine Pollution Bulletin — spatiotemporal proximity + backtracking methodology
10. "Performance of a simple backtracking method for marine oil source searching in a 3D ocean" (2019), Marine Pollution Bulletin
11. "Oil Spilling Detection at Marine Environment using AIS and Satellite Datasets" (2025) — Isolation Forest (AIS) + SVM (imagery) hybrid framework
12. "Operational System for Ship Detection and Identification Using SAR and AIS for Ships of Illegal Oil Discharge" — directly on-topic prior art
13. "Satellite imagery in evaluating oil spill modelling scenarios for the Syrian oil spill crisis, summer 2021," Frontiers in Marine Science — real case study using drift backtracking + AIS
14. xView3-SAR paper (arXiv:2206.00897) — GFW/DIU dark-vessel detection dataset and methodology, most transferable prior art for the attribution half

**Drift modeling tools (cite as established, credible tools rather than reinventing):**
- NOAA GNOME/PyGNOME (open source)
- OpenDrift + its `openoil` module (open source, Python)

---

## 21. Relevant Government Initiatives, Platforms, Standards and Policies

- **ISRO/NRSC**: RISAT-1, EOS-4 (RISAT-1A) SAR satellites; Bhuvan geoportal; MOSDAC data dissemination
- **INCOIS** (MoES): Online Oil Spill Advisory Service (drift prediction)
- **Indian Coast Guard**: National Oil Spill Disaster Contingency Plan (NOS-DCP, since 1996, last major update 2015); NATPOLREX exercises
- **Indian Navy**: IMAC → National Maritime Domain Awareness (NMDA) Centre upgrade (BEL contract, integrating 7 ministries/15 agencies/13 coastal states)
- **MoES**: COMAPS (Coastal Ocean Monitoring and Prediction System), SWQM (Sea Water Quality Monitoring), real-time coastal buoy network (Digha, Goa, Mumbai, Kochi, Vizag, Chennai)
- **India's Merchant Shipping Act, 1958 (Part XB)** — current civil-liability-only legal framework; Merchant Shipping Bill 2024 reform in progress ([PRS India](https://prsindia.org/billtrack/the-merchant-shipping-bill-2024))
- **International**: MARPOL Annex I, UNCLOS Articles 220/228, IMO frameworks
- **EU**: EMSA CleanSeaNet, SafeSeaNet (AIS aggregation) — the clearest working reference model
- **US**: NOAA ERMA, OSPO Marine Pollution Surveillance Reports, APPS (Act to Prevent Pollution from Ships)

---

## 22. Open-Source Projects and Tools We Can Leverage

- **SNAP / S1TBX** (ESA) — SAR calibration, speckle filtering, orthorectification
- **Google Earth Engine** — cloud-scale Sentinel-1 access + compute, with published oil-spill-detection tutorials
- **`pyais`** (GitHub: `M0r13n/pyais`) — actively maintained AIS message decoder
- **OpenDrift** (with `openoil` module) — open-source oil drift trajectory modeling
- **NOAA PyGNOME** (GitHub: `NOAA-ORR-ERD/PyGnome`) — the standard, credible drift-modeling engine to cite
- **`chashmishcoder/Oil-Spill-Detection`** (GitHub) — explicitly combines AIS + Sentinel-1 SAR, directly relevant prior art
- **`CUG-URS/CBDNet-main`** (GitHub) — official implementation of a published oil-spill contextual/boundary-supervised detection network
- **`oceanhackweek/ohw23_proj_oil`** (GitHub) — includes a labeled 15,774-sample oil-spill dataset
- **xView3-SAR reference code** — dark-vessel detection methodology and baseline models
- **PostGIS** — spatial database for the fusion/attribution layer

---

## 23. Security and Privacy Considerations

- **Chain-of-custody / evidentiary integrity**: if outputs are meant to support enforcement, the pipeline needs immutable audit logging — raw scene ID, processing/model version, timestamps, AIS data snapshot — from day one. Legal scholarship confirms courts scrutinize methodological validity end-to-end, and India currently has no standardized framework for admitting this kind of evidence (one cited Indian case admitted satellite data informally, without a codified standard).
- **Dual-use nature**: given NTRO's IMINT/maritime-surveillance mandate, the underlying SAR+AIS fusion / dark-vessel-detection capability plausibly has security value beyond pollution enforcement (smuggling, sanctions evasion, general maritime domain awareness). The team should pitch the stated environmental/enforcement use case primarily, while being prepared to discuss this natural extension if judges ask (this is inference, not a confirmed NTRO position).
- **Data sovereignty**: a production system handling vessel-tracking/attribution data for a security-adjacent agency would likely need to run on sovereign/government-controlled infrastructure (on-prem or empanelled cloud like NIC/MeghRaj) rather than public cloud — worth a one-line acknowledgment in the pitch even though the hackathon prototype itself can run on free-tier cloud.
- **Privacy**: AIS data is already broadcast openly by design (not personal data in the traditional sense), but vessel-tracking/behavioral profiling does raise proportionality questions if extended beyond the stated pollution-enforcement purpose — worth a brief mention of scope limitation.

---

## 24. Scalability Considerations

- **Compute is cheap, data access is the bottleneck.** Training/running the segmentation CNN is feasible on a single GPU or free Colab/Kaggle tier; the harder scaling problem is satellite tasking/download bandwidth and AIS feed volume (Danish AIS alone runs ~2GB/day).
- **Continuous EEZ-wide monitoring** (vs. a single-scene demo) would require automated scene-ingestion scheduling keyed to satellite pass times over the Indian EEZ, plus a queueing/inference pipeline that can keep up with incoming scene volume — architecturally straightforward (standard batch/queue pattern) but non-trivial in a hackathon timeframe.
- **AIS ingestion at national scale** (India's NAIS feed) would be a much higher-volume, higher-frequency stream than the demo datasets — the PostGIS spatial-join approach should scale reasonably with proper indexing, but this is untested at that scale by the team.

---

## 25. Cost Considerations

- **Free tier is sufficient for the prototype**: Sentinel-1 (free), Google Earth Engine (free for research), Global Fishing Watch / Danish AIS (free), Colab/Kaggle GPU (free) — a working demo requires effectively $0 in data/compute cost.
- **Commercial tasked SAR** (ICEYE, Capella, Umbra) is quote-based/contract-priced, not publicly listed — signals meaningfully higher cost than Sentinel-1's free 10m-resolution imagery; relevant only if the team wants to discuss a "production upgrade path" for higher resolution/faster revisit.
- **Commercial AIS** (Spire, MarineTraffic paid tiers) reportedly runs into tens of thousands of USD/year for global real-time coverage with history — not needed for the prototype, but worth citing as a real production cost driver.
- **The actually expensive part of a production system is not compute or the free data — it's the drift-modeling/fusion engineering and the legal/evidentiary integration work**, which are labor costs, not infrastructure costs.

---

## 26. Prototype vs. Production Requirements

| Aspect | Hackathon Prototype | Production (NTRO-scale) |
|---|---|---|
| Satellite imagery | Official Zenodo Sentinel-1 SAR oil-spill dataset (Parts I–III), supplemented by fresh Copernicus/GEE scenes if needed | RISAT/EOS-4 + possibly commercial tasked SAR for faster revisit/higher resolution |
| AIS data | AccessAIS real historical U.S. AIS, or synthetic AIS generated for the chosen spill's region (both explicitly sanctioned by the PS) | India's NAIS feed (Coast Guard/IMAC), integrated via NMDA |
| Ocean/weather data | Free CMEMS currents + ERA5 wind reanalysis for the historical spill's date/region | Same sources, operationalized as a live feed |
| Deployment | Local machine / free-tier cloud (Colab, laptop) | Sovereign/on-prem or empanelled government cloud (data sovereignty) |
| Scope | Single historical case study proving the pipeline end-to-end | Continuous EEZ-wide automated monitoring |
| Attribution output | Ranked candidate list with confidence scores, clearly framed as proof-of-concept | Same, but integrated with formal chain-of-custody/evidence packaging for legal use |
| Latency | Not real-time; batch processing of a chosen historical scene is acceptable | Near-real-time triage (following CleanSeaNet's <30-minute alert benchmark) |

**Framing to use with judges**: *"This prototype proves the detect→characterise→hindcast/forecast→attribute pipeline works end-to-end on the officially provided Zenodo imagery dataset and real/synthetic AIS built per the PS's own guidance; it's architected so that swapping in India's NAIS feed and ISRO's SAR tasking is a data-source substitution, not a redesign."*

---

## 27. Possible Architecture Approaches

```
[Stage 1 — Satellite ingestion, detection, characterisation]
  Sentinel-1 SAR imagery (Zenodo dataset Parts I-III; Copernicus/GEE for extra scenes)
    → calibration + speckle filtering + land masking
    → CNN segmentation (U-Net / DeepLabv3+, pretrained backbone) — trained to distinguish
      oil / lookalike / no-oil using the Zenodo dataset's built-in negative classes
    → polygon extraction: geometric properties (area, perimeter, elongation, orientation)
    → age-estimation proxy (heuristic, explicitly caveated — see §19)
    → store geometry + metadata + timestamp in PostGIS

[Stage 2 — Hindcast + forecast drift modelling]
  Ocean current data (CMEMS/HYCOM) + wind data (ERA5) for the scene's region/date
    → OpenDrift / PyGNOME run BACKWARD from slick polygon/centroid+timestamp
      → estimated origin point + time window (ideally as a probability cone, not a point)
    → same engine run FORWARD from the detection → forecast future slick trajectory
      (for response planning, matches the PS's explicit forward-prediction ask)

[Stage 3 — AIS ingestion + attribution scoring — parallel to Stage 1]
  AIS feed (AccessAIS real US data, or synthetic data generated for the chosen region)
    → trajectory reconstruction, AIS-gap detection
    → filter to vessels plausibly near the ESTIMATED ORIGIN (from Stage 2), not just
      near the observed slick — this is the PS's explicit design intent
    → score remaining candidates: proximity to origin at origin time, heading/speed
      trajectory consistency, behavioural anomalies (AIS gaps, erratic course changes,
      deviation from expected shipping lanes), optionally vessel-type weighting
    → output a ranked, confidence-scored candidate list — NOT a single deterministic accusation

[Stage 4 — Presentation layer]
  Map dashboard (Leaflet/Mapbox/deck.gl): slick polygon + geometry/age readout,
  hindcast probability cone + forecast path, candidate vessel tracks, ranked score
  table, timeline scrubber
  Backend: FastAPI + PostGIS
```

This mirrors the architecture pattern used (informally, manually) by EMSA CleanSeaNet and (for the dark-vessel half) Global Fishing Watch — the innovation is automating and scoring the fusion step rather than leaving it to a human analyst, plus adding the forward-forecast and age-estimation pieces the PS explicitly asks for but which most existing prior art skips.

---

## 28. Possible Technology Stacks

- **Core**: Python (rasterio, GDAL, xarray, numpy), PyTorch or TensorFlow
- **Geospatial**: PostGIS, GDAL, Shapely
- **Drift modeling**: OpenDrift (recommended for hackathon — pure Python, `pip install`) or PyGNOME
- **Backend**: FastAPI
- **Frontend**: React + Leaflet/Mapbox GL, or deck.gl for large-scale trajectory visualization
- **AIS decoding**: `pyais`
- **Oceanographic/meteorological data access**: `copernicusmarine` (CMEMS currents), `cdsapi` (ERA5 wind)
- **Data access**: Copernicus openEO / Sentinel Hub SDK, Google Earth Engine Python API, Global Fishing Watch REST API (only if supplementing beyond the official Zenodo/AccessAIS sources)

---

## 29. Major Technical Challenges

1. **Limited labeled training data** (hundreds to ~15,000 patches across known public datasets) — mitigate with transfer learning (pretrained ImageNet backbone) and augmentation rather than training from scratch.
2. **The dark-vessel/attribution problem is fundamentally probabilistic** — AIS gaps are often benign (dead zones, equipment faults), and deliberate polluters are precisely the ones most likely to spoof/disable AIS. A ranked/confidence-scored output is the only honest framing.
3. **Satellite revisit-time vs. slick-drift-time mismatch** — likely the single biggest feasibility gap. Sentinel-1 revisit degraded to ~12 days for several years (2021–2025, single-satellite operation after Sentinel-1B's failure) and is only returning to a 6-day nominal revisit with the Sentinel-1C/1D constellation (full transition expected mid-2026). Oil slicks can disperse within hours to days — meaning many real spills will have no coincident satellite pass during the detectable/traceable window.
4. **False positives from look-alikes** (biogenic slicks, low-wind zones, rain cells, current shear, grease ice) remain unsolved even by modern CNNs.
5. **Overclaiming risk**: framing the system as guaranteeing real-time, nationwide detection would be factually indefensible given #3, and likely to be caught by a technically literate NTRO-affiliated judge panel.
6. **Age estimation has no standard method** — unlike segmentation (where benchmarked architectures/metrics exist), the literature does not converge on a single accepted technique for estimating elapsed time since discharge from imagery alone. The PS's own "if feasible" hedge acknowledges this; the team's challenge is choosing a defensible, clearly-scoped proxy (e.g., spreading-rate-based) rather than either skipping it or overstating its accuracy.
7. **Hindcast uncertainty compounds over time** — ocean current/wind reanalysis data has its own error bars, and drift models amplify positional uncertainty the further back (or forward) in time they run. A single-point origin estimate will typically be wrong; representing this as a probability region (not a pin on a map) is more defensible but adds real implementation complexity (ensemble runs, uncertainty propagation).
8. **Ground truth for validating the fused pipeline is scarce** — the Zenodo dataset provides labeled imagery, but does not include matched AIS/vessel-attribution ground truth (i.e., no dataset says "this exact vessel caused this exact spill"). The team will likely need to construct its own semi-synthetic validation scenario (known spill + real or synthetic AIS with an injected "ground truth" polluter) to demonstrate and evaluate Stage 3 at all.

---

## 30. Edge Cases and Failure Scenarios

- A detected slick has **no vessel of any kind (AIS or SAR-visible) nearby** — likely indicates a natural seep or a pipeline/rig source; system should cross-reference known seep/infrastructure locations to correctly *not* accuse a vessel.
- A detected slick coincides with **multiple vessels' tracks simultaneously** — requires the ranking/confidence approach rather than a single-match rule.
- **AIS spoofing**: a vessel's broadcast position doesn't match its true position — the system may need to flag "AIS position inconsistent with expected drift/behavior" as its own signal, though sophisticated detection of spoofing itself is a hard sub-problem.
- **Weather conditions outside the detectable wind window** (<1.5 m/s or >14 m/s) — the system should recognize and report "no reliable detection possible under current wind conditions" rather than silently failing or false-flagging.
- **Look-alike misclassified as oil** — a biogenic bloom or low-wind patch triggers a false attribution investigation against an innocent nearby vessel; false-positive cost here is not just technical but reputational/legal.
- **A genuinely innocent vessel is nearby a spill from an unrelated source** (e.g., natural seep) — ranking/confidence scoring must avoid implying certainty it doesn't have.

---

## 31. Risks and Limitations

- **The most important risk: mistaking correlation for proof.** A vessel being near a slick, or going dark near a slick, is *evidence*, not proof of causation. The team must consistently frame outputs as investigative leads / ranked candidates for further verification, not verdicts — both for technical honesty and to avoid an embarrassing judge question about false-accusation liability.
- **Data availability risk**: real Indian AIS/satellite data is not accessible to a student team within a hackathon timeframe; the team must be transparent about using proxy/historical data and articulate why the substitution is architecturally valid.
- **Legal follow-through risk**: even a perfect technical system doesn't change India's weak civil-liability framework for oil pollution — worth acknowledging rather than overselling real-world deterrence impact.
- **Revisit-latency risk** (see §29.3) — core physical limitation, not solvable by better software alone.

---

## 32. Questions That Need Clarification from the Problem-Statement Organization

The official Description/Expected-Solution text and dataset links (added above) already answer several questions this dossier originally flagged as open (region flexibility is explicit — real-or-synthetic AIS "for the region of oil spill" — and the exact imagery dataset is named). The remaining genuinely open items worth asking NTRO (via SIH's clarification channel, if available) or explicitly flagging as assumptions in the pitch:

1. Is age estimation expected to be demonstrated with any **quantitative accuracy claim**, or is a qualitative/heuristic proxy acceptable given the PS's own "if feasible" hedge?
2. Is there a **specific accuracy/false-positive-rate bar**, or a preferred evaluation metric, for the detection and attribution stages (e.g., IoU threshold for segmentation, precision@k for the ranked suspect list)?
3. For the **behavioural-anomaly scoring** in Stage 3 — are there specific anomaly types NTRO wants prioritized (AIS gaps, course/speed deviation, shipping-lane deviation), or is the team free to define its own scoring scheme?
4. Is the deliverable meant to demonstrate a **path toward legally admissible evidence** (implying chain-of-custody/audit features matter for judging), or purely a technical/analytical capability with no evidentiary framing expected?
5. Should the demo target the **Indian EEZ specifically** (even with synthetic/proxy data standing in for a real Indian spill), or is a globally-applicable demo using the officially linked Zenodo/AccessAIS data (which are not India-specific) equally acceptable?
6. Has this exact problem statement appeared in a prior SIH cycle under a different framing (no public record was found, but NTRO has sponsored similar satellite-analytics problems before, e.g., illegal mining detection)?

---

## 33. Potential SIH Judging Points

Based on general SIH evaluation guidance (innovation, feasibility/practicability, direct relevance to the stated problem, technical implementation quality, usability, clarity):

- **Feasibility awareness** will likely matter more than raw ambition — judges (especially on an NTRO/space-tech PS) are likely to be technically literate about satellite revisit limits and AIS's known weaknesses; overclaiming will be penalized.
- **A working demo on real data** (even substituted/historical) will outperform a polished slide deck describing a hypothetical real-time system.
- **Directly addressing both halves of the PS** (detection *and* attribution) rather than only building an oil-spill detector (the more common, "easier" half) is likely to differentiate strongly, since attribution is the harder, more novel ask.
- **Explicit handling of the "identify the vessel" problem's adversarial nature** (dark vessels, spoofing) shows deeper problem understanding than naive AIS-track matching.

---

## 34. Possible Judge Questions

- *"What happens when the responsible vessel has its AIS turned off?"* — Have a clear answer: dark-vessel flagging via SAR-detected-vessel-without-AIS-corroboration (GFW methodology), presented as a ranked suspicion signal, not a solved identification.
- *"How do you distinguish a real oil spill from a biogenic slick or low-wind patch?"* — Have a clear answer on your false-positive mitigation approach (wind-field cross-referencing, multi-temporal comparison, model confidence thresholds).
- *"Would this evidence hold up in court?"* — Be honest: reference the Maersk Kiera precedent as proof the *general approach* has worked, while acknowledging India lacks a codified evidentiary framework today, and that your system is designed to produce auditable, reproducible output as a first step toward that standard.
- *"How often would this actually catch a spill, given satellite revisit times?"* — Be honest about the coverage gap; frame the system as best-effort triage, improving with additional SAR sources.
- *"Is this really an environmental tool, or is it maritime surveillance?"* — Be prepared to acknowledge the dual-use angle thoughtfully rather than being caught off guard, especially given NTRO's actual mandate.
- *"What data are you actually using right now vs. what would be used in production?"* — Be transparent about proxy data use; this transparency itself is a credibility point, not a weakness, if framed well.

---

## 35. What Would Make Our Solution Stand Out

- Being one of the only teams to seriously tackle the **attribution half** (not just detection) with a defensible, GFW-inspired dark-vessel-aware approach.
- **Demonstrable end-to-end pipeline on real (if substituted) data**, not just slides — including a real drift-backtracking step, not a hand-waved "we'd correlate with AIS."
- **Built-in auditability/evidence-provenance** from day one, directly answering a real, researched gap (India's lack of a codified satellite-evidence standard).
- **Honest, technically literate framing of limitations** (revisit time, look-alikes, probabilistic attribution) — counterintuitively, this builds more credibility with a sophisticated judge panel than an overconfident pitch.
- Explicitly connecting the solution to **existing Indian infrastructure** (ISRO SAR, INCOIS drift models, IMAC/NMDA) as an integration story rather than a from-scratch replacement — shows systems thinking, not just a standalone model.

---

## 36. Potential Novelty Ideas (Consolidated)

1. Automated fusion pipeline replacing CleanSeaNet's manual analyst step, with confidence scoring.
2. Dark-vessel detection module (SAR-detected vessel + no AIS corroboration) as a first-class output, not an afterthought.
3. Drift-backtracking-to-AIS-gap-timing correlation as the core attribution signal, rather than naive "AIS track intersects slick" — searching AIS around the **hindcast-estimated origin**, exactly as the PS specifies.
4. **True bidirectional drift modelling** (hindcast + forecast) — most academic prior art only backtracks; running both directions matches the PS's explicit ask and is an easy differentiator once a bidirectional engine (OpenDrift) is wired up.
5. **Attempting spill-age estimation** at all, since the PS itself flags it as the hardest/optional sub-requirement most teams will likely skip.
6. **Uncertainty-aware hindcast output** (a probability cone for origin, not a single pin) rather than false precision.
7. Natural-seep/infrastructure disambiguation layer to avoid false vessel accusations.
8. Chain-of-custody/audit-log design built for eventual legal/evidentiary use.
9. Explicit "confidence, not verdict" output design and UX — arguably as much a product-design novelty as a technical one.
10. Positioning as an integration layer atop existing Indian assets (ISRO/INCOIS/IMAC) rather than a competing standalone system.

---

## 37. Final Recommendations on Direction to Explore

1. **Build directly on the officially provided data**: the Zenodo Sentinel-1 SAR oil-spill dataset (Parts I–III) for detection/segmentation training, and AccessAIS (real U.S. data) or PS-sanctioned synthetic AIS for the attribution half. This removes most of the data-sourcing risk this dossier originally flagged, since the organizers have already pointed to workable, no-registration-hassle sources.
2. **Do not attempt a from-scratch, first-principles CV model.** Use a pretrained-backbone U-Net or DeepLabv3+ fine-tuned on the Zenodo dataset (which conveniently already includes "no oil" and "lookalike" negative classes) — this is standard practice in the literature and saves enormous time.
3. **Treat Stage 2 (hindcast/forecast) and Stage 3 (AIS scoring) as the differentiators**, since they have the least off-the-shelf tooling and the most room for genuine technical contribution. Use OpenDrift (pip-installable, purpose-built `openoil` module, supports running both backward and forward) rather than a custom physics engine; source currents/wind from CMEMS/ERA5 for the chosen spill's date and region.
4. **Attempt spill-age estimation with an explicitly-labeled heuristic** (e.g., a spreading-rate/backscatter-decay proxy calibrated against the dataset's known cases) rather than skipping it outright — the PS's "if feasible" wording suggests most teams will skip this, making even an honest, imperfect attempt a differentiator.
5. **Build the dark-vessel-flagging capability into Stage 3's behavioural-anomaly scoring** — even a simple version (an AIS gap coinciding with the estimated origin window, or a SAR/EO-visible vessel signature with no matching AIS track) directly demonstrates understanding of the problem's hardest, most novel half and mirrors proven prior art (GFW's dark-vessel methodology).
6. **Design Stage 3's output as a ranked, confidence-scored candidate list with audit metadata**, not a single accusation — this is both more technically honest and more likely to impress judges who understand the domain's real uncertainty, and it matches the PS's own wording ("scored" candidates, not "identified" candidates).
7. **In the pitch, proactively address feasibility limits** (satellite revisit time, look-alike false positives, AIS evasion, hindcast uncertainty) rather than waiting to be asked — this reads as maturity, not weakness, especially for a security-agency-sponsored, technically sophisticated problem statement.
8. **Treat the legal/evidentiary and NTRO-dual-use angles as narrative context to demonstrate depth of understanding**, not as scope to build — the hackathon deliverable should stay a working technical prototype covering all four officially specified stages, with these considerations shown through thoughtful design choices (audit logs, confidence scoring) rather than separate legal-analysis deliverables.

---

*This document is a research synthesis produced via multi-source web research (see inline citations throughout) plus the official Background/Description/Expected-Solution text and dataset links supplied directly by the user. Facts are sourced; anything presented as inference, assumption, or team recommendation is explicitly labeled as such. Before committing to a final direction, verify time-sensitive facts (dataset access terms, API quotas, Sentinel-1 constellation status) close to the actual hackathon date, as several (Sentinel-1C/1D transition, dataset access policies) are actively evolving as of this research (August 2026).*
