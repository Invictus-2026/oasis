"""
Phase 7 — real vessel attribution: real AIS ingestion (Phase 6) feeding real
spatial/temporal/trajectory/behaviour filtering and transparent six-component
scoring (app/attribution/scoring.py), instead of the hardcoded MOCK_VESSELS
list this module used to return unconditionally.

Falls back to the fixture response when the case bundle's binary data files
are not on disk (mirrors this codebase's existing convention, e.g.
case_store.data_files_ready(), drift/mock_engine.py) — mock mode never fails,
it runs the same downstream scoring shape with fixture-derived candidates
instead of real AIS.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.attribution import ais_ingest, scoring
from app.core import config, fixtures
from app.core.case_store import CaseBundle, data_files_ready, load_case
from app.core.schemas import (
    AISGap,
    AttributeRequest,
    AttributeResponse,
    CandidateFlag,
    CandidateLabel,
    ProcessingStep,
    Provenance,
    ScoreBreakdown,
    ScoreWeights,
    VesselCandidate,
)


def _weighted_score(breakdown_dict: dict[str, float | None], weights: ScoreWeights) -> float:
    """Recompute the composite under the CALLER's weights (which may differ
    from scoring.SCORE_WEIGHTS's defaults), redistributing the
    counterfactual weight when that component is None — same rule as
    scoring.composite_score(), applied to a caller-supplied weight set."""
    w = weights.model_dump()
    components = {k: v for k, v in breakdown_dict.items() if k != "counterfactual_similarity" or v is not None}
    if breakdown_dict["counterfactual_similarity"] is None:
        redistribute = w.pop("counterfactual_similarity")
        remaining_total = sum(w.values())
        w = {k: v + redistribute * (v / remaining_total) for k, v in w.items()}
    score = sum(components[k] * w[k] for k in components if k in w)
    return round(min(1.0, max(0.0, score)), 4)


def _candidate_flags(candidate: scoring.Candidate) -> list[CandidateFlag]:
    flags: list[CandidateFlag] = []
    ev = candidate.evidence
    if any(g.overlaps_origin_window for g in ev.behaviour.ais_gaps):
        flags.append(CandidateFlag.dark_vessel)
    if ev.behaviour.course_changes:
        flags.append(CandidateFlag.course_deviation)
    if ev.behaviour.stops:
        flags.append(CandidateFlag.slow_steaming)
    if ev.spatial.intersects or ev.spatial.min_distance_km < 3.0:
        flags.append(CandidateFlag.closest_approach)
    return flags


def _to_api_candidate(
    candidate: scoring.Candidate,
    vessel: ais_ingest.Vessel,
    track_geojson: dict,
    weights: ScoreWeights,
) -> VesselCandidate:
    ev = candidate.evidence
    breakdown_dict = {
        "origin_proximity": ev.origin_proximity,
        "temporal_compatibility": ev.temporal_compatibility,
        "trajectory_consistency": ev.trajectory_consistency,
        "behaviour_anomaly": ev.behaviour_anomaly,
        "ais_gap": ev.ais_gap,
        "counterfactual_similarity": ev.counterfactual_similarity,
    }
    score = _weighted_score(breakdown_dict, weights)

    return VesselCandidate(
        mmsi=candidate.mmsi,
        name=vessel.name,
        vessel_type=str(vessel.vessel_type_code) if vessel.vessel_type_code is not None else None,
        track=track_geojson,
        score=score,
        rank=0,
        label=(
            CandidateLabel.investigation_lead
            if score >= scoring.INVESTIGATION_LEAD_THRESHOLD
            else CandidateLabel.candidate
        ),
        flags=_candidate_flags(candidate),
        breakdown=ScoreBreakdown(**breakdown_dict),
        gaps=[
            AISGap(
                start_utc=g.start_utc, end_utc=g.end_utc, duration_minutes=g.duration_minutes,
                interpolated_path=g.interpolated_path, overlaps_origin_window=g.overlaps_origin_window,
                label=g.label,
            )
            for g in ev.behaviour.ais_gaps
        ],
        closest_approach_km=round(ev.spatial.min_distance_km, 3),
        closest_approach_utc=ev.spatial.closest_time_utc,
        narrative=candidate.narrative,
    )


def _observed_slick_and_provider(bundle: CaseBundle):
    """The real Stage 1 detection and Phase 3 environmental provider, for the
    counterfactual simulation step (Step 5) — mirrors drift.py's own pattern
    of always reading the real detected slick rather than trusting client
    input for Stage 1 output (see app/api/drift.py's _slick_context).

    Returns (None, None) when either is unavailable, in which case
    scoring.rank_candidates() simply skips the counterfactual step for every
    candidate (counterfactual_similarity stays None) rather than failing.
    """
    if not data_files_ready():
        return None, None

    from app.api.detection import _run as run_detection
    from app.core.schemas import DetectionMethod
    from app.drift.origin_search import ObservedSlick
    from app.environment import get_provider

    detection = run_detection(DetectionMethod.classical)
    if not detection.slicks:
        return None, None
    slick = detection.slicks[0]

    observed_slick = ObservedSlick(
        polygon=slick.polygon["coordinates"][0],
        detected_at=bundle.acquired_at,
        area_km2=slick.geometry.area_km2,
        orientation_deg=slick.geometry.orientation_deg,
        elongation=slick.geometry.elongation,
        compactness=slick.geometry.compactness,
        length_km=slick.geometry.length_km,
    )
    return observed_slick, get_provider(bundle)


def reconstruct_and_score(req: AttributeRequest) -> AttributeResponse:
    """Steps 1-6 end to end against the real case bundle's AIS traffic.

    Falls back to fixtures.attribute_response() when the case bundle's
    binary files are not on disk — this function is not called at all in
    that case; see the router (app/api/attribution.py).
    """
    t0 = time.perf_counter()

    bundle = load_case()
    raw = bundle.ais()
    results = ais_ingest.ingest(raw)
    tracks = {mmsi: r.track for mmsi, r in results.items() if r.track is not None}
    vessels = {mmsi: r.vessel for mmsi, r in results.items()}
    total_in_region = len(results)

    observed_slick, provider = _observed_slick_and_provider(bundle)

    ranked = scoring.rank_candidates(
        tracks,
        origin_region=req.origin_region,
        release_window=(req.release_window_start_utc, req.release_window_end_utc),
        drift_bearing_deg=req.drift_bearing_deg,
        observed_slick=observed_slick,
        provider=provider,
        search_radius_km=req.search_radius_km,
        counterfactual_top_n=req.counterfactual_top_n,
    )

    candidates = [
        _to_api_candidate(c, vessels[c.mmsi], tracks[c.mmsi].linestring, req.weights)
        for c in ranked
    ]
    candidates.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(candidates):
        c.rank = i + 1

    all_tracks = ais_ingest.to_feature_collection(results)

    return AttributeResponse(
        total_vessels_in_region=total_in_region,
        after_filter=len(candidates),
        candidates=candidates,
        weights=req.weights,
        all_tracks=all_tracks,
        processing=[
            ProcessingStep(
                name="ingest + reconstruct + filter + score",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                detail=f"{total_in_region} vessel(s) in the AIS bundle, "
                       f"{req.counterfactual_top_n} received counterfactual simulation",
            ),
        ],
        provenance=Provenance(
            model_version=config.MODEL_VERSION,
            params={
                "search_radius_km": req.search_radius_km,
                "counterfactual_top_n": req.counterfactual_top_n,
                "weights": req.weights.model_dump(),
            },
            generated_at=datetime.now(timezone.utc),
            inputs=[f"case bundle '{bundle.id}' AIS traffic"],
            notes=(
                "Real ingestion (Phase 6) and real six-component scoring (Phase 7): spatial + "
                "temporal filtering, trajectory compatibility, transparent rule-based behaviour "
                "analysis, AIS gap detection, and counterfactual simulation for the top-ranked "
                "candidates. Every candidate is a plausibility signal, never an identification — "
                "see each candidate's individually-stored evidence components."
            ),
        ),
    )
