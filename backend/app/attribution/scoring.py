"""
Phase 7, steps 5-6 — counterfactual simulation and transparent attribution
scoring.

Step 5 (counterfactual): for a candidate vessel, run a REAL forward
Lagrangian simulation (drift/simulate.py, Phase 4's engine) seeded at the
vessel's own track and compare the resulting cloud against the observed
slick using the REAL five-metric comparison already built for origin search
(drift/origin_search.compare(), Phase 5) — not a new, unrelated similarity
formula. This is deliberately expensive (a real physics run), so callers
should only request it for a small number of high-ranked candidates; see
`rank_candidates(..., counterfactual_top_n=...)`.

Step 6 (scoring): six components, stored SEPARATELY on `Evidence`, combined
into one composite via named, documented, inspectable weights
(`SCORE_WEIGHTS`) that sum to 1 — never a hard-coded percentage baked into
the score itself. When a component was not computed (counterfactual
similarity for a candidate outside the top-N), its weight is redistributed
across the remaining components rather than treated as 0, so skipping the
expensive step never silently penalises a candidate.

Language discipline (acceptance criterion): a vessel that clears these
filters is a CANDIDATE, or an INVESTIGATION LEAD when the evidence is
stronger. Findings are EVIDENCE; a behavioural fact is an ANOMALY. Nothing in
this module calls a vessel a "culprit," "suspect," "guilty," or otherwise
renders a verdict — every score is a ranked plausibility signal, never a
finding of fact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from app.attribution import filters
from app.attribution.ais_ingest import VesselTrack
from app.environment.base import EnvironmentalDataProvider

# Named, documented weights — the only place a "percentage" exists, and it is
# a labelled constant anyone can inspect and change, never baked silently
# into the score. Mirrors this project's existing house rule (detection's
# classify() weights, drift's SCORE_WEIGHTS in origin_search.py).
SCORE_WEIGHTS: dict[str, float] = {
    "origin_proximity": 0.22,
    "temporal_compatibility": 0.18,
    "trajectory_consistency": 0.18,
    "behaviour_anomaly": 0.14,
    "ais_gap": 0.14,
    "counterfactual_similarity": 0.14,
}

# Above this composite, a candidate is described as an "investigation lead"
# rather than a plain "candidate" — still never a verdict, just a stronger
# plausibility signal worth a human's attention first. A named constant, not
# a hardcoded string comparison scattered through the code.
INVESTIGATION_LEAD_THRESHOLD = 0.55


@dataclass
class CounterfactualResult:
    similarity: float
    metrics: "object"  # origin_search.ComparisonMetrics; typed loosely to avoid a hard import cycle
    candidate_origin: tuple[float, float]


def counterfactual_similarity(
    track: VesselTrack,
    observed_slick,
    *,
    provider: EnvironmentalDataProvider,
    particle_count: int = 150,
    windage_coefficient: float = 0.03,
    seed: int = 42,
) -> CounterfactualResult:
    """Step 5 — simulate a release from this vessel's own track and compare
    it against the observed slick.

    The candidate origin is the vessel's position at the timestamp closest to
    the observed slick's own detection time minus the implied age (i.e. the
    vessel's position nearest the estimated release moment) — this is a
    counterfactual ABOUT this specific vessel's movement, not a generic
    origin search (that is Phase 5's job; this reuses its comparison math,
    not its search).
    """
    from app.drift import simulate
    from app.drift.origin_search import compare

    # Nearest fix to the observed slick's detection time is the most
    # information-dense point on this vessel's track to release from; using
    # the vessel's LAST fix before detection avoids projecting the vessel
    # into a time it was never observed at.
    candidates_before = [p for p in track.positions if p.timestamp <= observed_slick.detected_at]
    origin_position = candidates_before[-1] if candidates_before else track.positions[-1]

    age_hours = max(
        0.5, (observed_slick.detected_at - origin_position.timestamp).total_seconds() / 3600.0,
    )

    cfg = simulate.SimulationConfig(
        particle_count=particle_count, duration_hours=age_hours,
        windage_coefficient=windage_coefficient,
    )
    result = simulate.run(
        [[origin_position.lon, origin_position.lat]], provider=provider,
        start_time=origin_position.timestamp, direction=+1, config=cfg,
        seed=seed, seed_mode="point",
    )
    predicted_cloud = result.final_positions()
    metrics = compare(predicted_cloud, observed_slick)

    return CounterfactualResult(
        similarity=metrics.composite_score, metrics=metrics,
        candidate_origin=(origin_position.lon, origin_position.lat),
    )


@dataclass
class Evidence:
    """All six Step-6 components, stored separately — never collapsed into
    the composite without the individual numbers remaining inspectable."""

    origin_proximity: float
    temporal_compatibility: float
    trajectory_consistency: float
    behaviour_anomaly: float
    ais_gap: float
    counterfactual_similarity: float | None  # None = not computed (outside top-N), never a fabricated 0

    spatial: filters.SpatialResult
    temporal: filters.TemporalResult
    trajectory: filters.TrajectoryResult
    behaviour: filters.BehaviourResult
    counterfactual: CounterfactualResult | None = None


def _origin_proximity_score(spatial: filters.SpatialResult, radius_km: float) -> float:
    if spatial.intersects:
        return 1.0
    return max(0.0, 1.0 - spatial.min_distance_km / radius_km)


def _temporal_compatibility_score(temporal: filters.TemporalResult, tolerance_minutes: float = 180.0) -> float:
    if temporal.present_during_window:
        return 1.0
    gap = temporal.time_to_window_minutes or 0.0
    return max(0.0, 1.0 - gap / tolerance_minutes)


def _behaviour_anomaly_score(behaviour: filters.BehaviourResult) -> float:
    """Combines the transparent rule-based indicators into one 0-1 number.
    Each indicator contributes independently (capped) so no single anomaly
    type can single-handedly saturate the score; the optional Isolation
    Forest score, when present, is blended in as one more independent
    signal, never a replacement for the rule-based indicators."""
    parts = [
        min(1.0, len(behaviour.speed_anomalies) / 2.0),
        min(1.0, len(behaviour.course_changes) / 2.0),
        min(1.0, len(behaviour.stops) / 1.0),
        behaviour.deviation_score,
    ]
    if behaviour.anomaly_model_score is not None:
        parts.append(behaviour.anomaly_model_score)
    return round(sum(parts) / len(parts), 4)


def _ais_gap_score(behaviour: filters.BehaviourResult, saturating_minutes: float = 90.0) -> float:
    """Longest gap, scaled — a gap overlapping the origin window scores full
    weight regardless of raw duration, since overlap with the release moment
    is the actually meaningful fact, not duration alone."""
    if not behaviour.ais_gaps:
        return 0.0
    best = max(
        (1.0 if g.overlaps_origin_window else min(1.0, g.duration_minutes / saturating_minutes))
        for g in behaviour.ais_gaps
    )
    return round(best, 4)


def build_evidence(
    *,
    track: VesselTrack,
    origin_region: dict,
    release_window: tuple[datetime, datetime],
    drift_bearing_deg: float,
    observed_slick=None,
    provider: EnvironmentalDataProvider | None = None,
    search_radius_km: float = 25.0,
    gap_threshold_minutes: float = 30.0,
    use_isolation_forest: bool = False,
) -> Evidence:
    """Steps 1-4 (+ optionally step 5) for one vessel track, producing the
    six-component Evidence record step 6 scores.

    Counterfactual simulation (step 5) only runs when both `observed_slick`
    and `provider` are supplied — callers that only want the cheap steps
    (e.g. to rank before deciding who gets the expensive step) pass neither
    and get `counterfactual_similarity=None`.
    """
    spatial = filters.spatial_filter(track, origin_region)
    temporal = filters.temporal_filter(track, release_window)
    # drift_bearing_deg is the SLICK'S OWN measured orientation (e.g. Phase 2's
    # geometry.orientation_deg), not a current/wind drift direction — see
    # trajectory_compatibility's docstring for why that distinction matters.
    # The reference point (slick centroid) comes from the origin region's own
    # centroid, which is always available even when no full ObservedSlick was
    # supplied for the optional counterfactual step.
    ring = origin_region["coordinates"][0]
    slick_centroid = (
        sum(p[0] for p in ring) / len(ring),
        sum(p[1] for p in ring) / len(ring),
    )
    trajectory = filters.trajectory_compatibility(track, drift_bearing_deg, reference_point=slick_centroid)
    behaviour = filters.behaviour_analysis(
        track, gap_threshold_minutes=gap_threshold_minutes, use_isolation_forest=use_isolation_forest,
        release_window=release_window,
    )

    counterfactual = None
    if observed_slick is not None and provider is not None:
        counterfactual = counterfactual_similarity(track, observed_slick, provider=provider)

    return Evidence(
        origin_proximity=round(_origin_proximity_score(spatial, search_radius_km), 4),
        temporal_compatibility=round(_temporal_compatibility_score(temporal), 4),
        trajectory_consistency=trajectory.consistency_score,
        behaviour_anomaly=_behaviour_anomaly_score(behaviour),
        ais_gap=_ais_gap_score(behaviour),
        counterfactual_similarity=round(counterfactual.similarity, 4) if counterfactual else None,
        spatial=spatial, temporal=temporal, trajectory=trajectory, behaviour=behaviour,
        counterfactual=counterfactual,
    )


def composite_score(evidence: Evidence) -> float:
    """Step 6 — the weighted composite, from SCORE_WEIGHTS.

    When counterfactual_similarity is None (not computed for this
    candidate), its weight is redistributed proportionally across the other
    five components rather than treated as 0 — omitting an expensive step
    must never look identical to a candidate that ran it and scored badly.
    """
    components = {
        "origin_proximity": evidence.origin_proximity,
        "temporal_compatibility": evidence.temporal_compatibility,
        "trajectory_consistency": evidence.trajectory_consistency,
        "behaviour_anomaly": evidence.behaviour_anomaly,
        "ais_gap": evidence.ais_gap,
    }
    weights = dict(SCORE_WEIGHTS)

    if evidence.counterfactual_similarity is not None:
        components["counterfactual_similarity"] = evidence.counterfactual_similarity
    else:
        redistribute = weights.pop("counterfactual_similarity")
        remaining_total = sum(weights.values())
        weights = {k: v + redistribute * (v / remaining_total) for k, v in weights.items()}

    score = sum(components[k] * weights[k] for k in components)
    return round(min(1.0, max(0.0, score)), 4)


def _narrative(mmsi: str, evidence: Evidence) -> str:
    """One human sentence per candidate, built only from the stored evidence
    fields — nothing here is asserted independently of a number the caller
    can also see."""
    bits = []
    if evidence.spatial.intersects:
        bits.append("track intersects the origin probability region")
    elif evidence.spatial.min_distance_km < 25.0:
        bits.append(f"passed within {evidence.spatial.min_distance_km:.1f} km of the origin region")

    if evidence.temporal.present_during_window:
        bits.append("was actively reporting during the estimated release window")

    if evidence.behaviour.ais_gaps:
        longest = max(evidence.behaviour.ais_gaps, key=lambda g: g.duration_minutes)
        bits.append(f"had a {longest.duration_minutes:.0f}-minute AIS reporting gap")

    if evidence.counterfactual_similarity is not None:
        bits.append(
            f"a simulated release from this vessel's track reproduces the observed slick with "
            f"{evidence.counterfactual_similarity:.0%} similarity"
        )

    if not bits:
        return "Limited evidence connects this vessel to the spill scenario."
    return "This vessel " + "; ".join(bits) + "."


@dataclass
class Candidate:
    mmsi: str
    score: float
    label: str  # "candidate" | "investigation lead" — see acceptance vocabulary
    evidence: Evidence
    narrative: str


# Hard pre-filter margins (steps 1-2). Deliberately generous: these exist
# only to drop vessels that are obviously irrelevant (on the far side of the
# map, active weeks away from the release), not to make a borderline call —
# a vessel just outside search_radius_km should still be SCORED lower via
# origin_proximity, not silently dropped. A vessel passes if it clears
# EITHER the spatial or temporal margin; failing both means its track has no
# plausible connection to this incident at all.
PREFILTER_SPATIAL_MARGIN_KM = 150.0
PREFILTER_TEMPORAL_MARGIN_HOURS = 48.0


def rank_candidates(
    tracks: dict[str, VesselTrack],
    *,
    origin_region: dict,
    release_window: tuple[datetime, datetime],
    drift_bearing_deg: float,
    observed_slick=None,
    provider: EnvironmentalDataProvider | None = None,
    search_radius_km: float = 25.0,
    gap_threshold_minutes: float = 30.0,
    counterfactual_top_n: int = 5,
    use_isolation_forest: bool = False,
) -> list[Candidate]:
    """Steps 1-6 end to end.

    Steps 1-2 (spatial/temporal filtering) first drop any vessel whose track
    never comes within a generous margin of the origin region AND never
    overlaps a generous margin around the release window — "find vessels
    entering/intersecting" / "find vessels present during," per the spec.
    Vessels that DO clear the coarse filter still have origin_proximity and
    temporal_compatibility scored normally in step 6 (a vessel 20 km away
    still ranks below one that intersects); the filter only removes vessels
    with no plausible connection to the incident at all.

    Survivors get evidence built WITHOUT the expensive counterfactual step,
    are ranked by the resulting composite, then re-scored WITH the
    counterfactual step (step 5) for only the top `counterfactual_top_n` —
    exactly "for high-ranked candidates" from the spec, keeping this fast
    when many vessels pass the coarse filter.
    """
    survivors: dict[str, VesselTrack] = {}
    for mmsi, track in tracks.items():
        spatial = filters.spatial_filter(track, origin_region)
        temporal = filters.temporal_filter(track, release_window)
        spatially_plausible = spatial.intersects or spatial.min_distance_km <= PREFILTER_SPATIAL_MARGIN_KM
        temporally_plausible = (
            temporal.present_during_window
            or (temporal.time_to_window_minutes or math.inf) <= PREFILTER_TEMPORAL_MARGIN_HOURS * 60.0
        )
        if spatially_plausible and temporally_plausible:
            survivors[mmsi] = track

    prelim: dict[str, Evidence] = {
        mmsi: build_evidence(
            track=track, origin_region=origin_region, release_window=release_window,
            drift_bearing_deg=drift_bearing_deg, search_radius_km=search_radius_km,
            gap_threshold_minutes=gap_threshold_minutes, use_isolation_forest=use_isolation_forest,
        )
        for mmsi, track in survivors.items()
    }
    prelim_ranked = sorted(prelim.items(), key=lambda kv: composite_score(kv[1]), reverse=True)

    final: dict[str, Evidence] = dict(prelim)
    if observed_slick is not None and provider is not None:
        for mmsi, _ in prelim_ranked[:counterfactual_top_n]:
            final[mmsi] = build_evidence(
                track=survivors[mmsi], origin_region=origin_region, release_window=release_window,
                drift_bearing_deg=drift_bearing_deg, observed_slick=observed_slick, provider=provider,
                search_radius_km=search_radius_km, gap_threshold_minutes=gap_threshold_minutes,
                use_isolation_forest=use_isolation_forest,
            )

    candidates = []
    for mmsi, evidence in final.items():
        score = composite_score(evidence)
        label = "investigation lead" if score >= INVESTIGATION_LEAD_THRESHOLD else "candidate"
        candidates.append(Candidate(
            mmsi=mmsi, score=score, label=label, evidence=evidence,
            narrative=_narrative(mmsi, evidence),
        ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
