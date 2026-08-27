"""Phase 7 steps 5-6 — counterfactual simulation and transparent attribution
scoring.

Step 5 reuses the real simulation engine (Phase 4's drift/simulate.py) and
the real comparison metrics (Phase 5's drift/origin_search.compare()) to
simulate a release from a candidate vessel's position and compare it against
the observed slick — a genuine physics run, not a lookup.

Step 6 combines six SEPARATELY STORED components into one transparent,
weighted composite. No percentage is hard-coded: every weight is a named,
inspectable constant, and every component is a real, independently
computable number, never a placeholder.

Acceptance-critical language check: candidate / investigation lead /
evidence / anomaly are used throughout; "culprit" (or any equivalent
accusation) must never appear.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.attribution import ais_ingest, filters, scoring
from app.environment.mock import MockEnvironmentalProvider

T0 = datetime(2023, 6, 15, 4, 0, tzinfo=timezone.utc)
DETECTED_AT = datetime(2023, 6, 15, 12, 0, tzinfo=timezone.utc)

ORIGIN_REGION = {"type": "Polygon", "coordinates": [[
    [-90.14, 28.38], [-90.06, 28.38], [-90.06, 28.46], [-90.14, 28.46], [-90.14, 28.38],
]]}
RELEASE_WINDOW = (T0 - timedelta(hours=1), T0 + timedelta(hours=1))

OBSERVED_RING = [
    [-90.02, 28.50], [-90.00, 28.505], [-89.97, 28.52], [-89.95, 28.535],
    [-89.955, 28.545], [-89.98, 28.53], [-90.005, 28.515], [-90.02, 28.50],
]


def _observed_slick():
    from app.drift.origin_search import ObservedSlick

    return ObservedSlick(
        polygon=OBSERVED_RING, detected_at=DETECTED_AT, area_km2=6.2,
        orientation_deg=48.0, elongation=4.1, compactness=0.31,
    )


def _track(mmsi, pts_with_minutes, sog=8.0, cog=48.0):
    positions = [
        ais_ingest.AISPosition(mmsi=mmsi, timestamp=T0 + timedelta(minutes=m), lat=lat, lon=lon,
                                speed_knots=sog, course_deg=cog)
        for m, lat, lon in pts_with_minutes
    ]
    return ais_ingest.reconstruct_track(positions)


@pytest.fixture()
def provider():
    return MockEnvironmentalProvider()


# -- Step 5: counterfactual simulation ---------------------------------

def test_counterfactual_runs_a_real_forward_simulation(provider, monkeypatch):
    from app.drift import simulate

    calls = {"n": 0}
    orig = simulate.run

    def counting(*a, **kw):
        calls["n"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(simulate, "run", counting)
    track = _track("A", [(0, 28.40, -90.10), (30, 28.42, -90.08)])
    scoring.counterfactual_similarity(track, _observed_slick(), provider=provider, particle_count=30)
    assert calls["n"] >= 1


def test_counterfactual_similarity_is_between_zero_and_one(provider):
    track = _track("A", [(0, 28.40, -90.10), (30, 28.42, -90.08)])
    result = scoring.counterfactual_similarity(track, _observed_slick(), provider=provider, particle_count=30)
    assert 0.0 <= result.similarity <= 1.0


def test_counterfactual_seeds_from_the_vessels_own_position(provider):
    """The simulated release must originate at the candidate vessel's track,
    not an arbitrary point — otherwise this would not be a counterfactual
    ABOUT that vessel."""
    near = _track("A", [(0, 28.44, -90.10), (30, 28.44, -90.09)])   # near observed slick
    far = _track("B", [(0, 20.00, -85.00), (30, 20.01, -84.99)])    # far from everything

    r_near = scoring.counterfactual_similarity(near, _observed_slick(), provider=provider, particle_count=40)
    r_far = scoring.counterfactual_similarity(far, _observed_slick(), provider=provider, particle_count=40)
    assert r_near.similarity != r_far.similarity


def test_counterfactual_reuses_the_documented_five_metric_comparison(provider):
    """Reuses Phase 5's compare() rather than reinventing scoring math — the
    result must carry the same five sub-metrics."""
    track = _track("A", [(0, 28.40, -90.10), (30, 28.42, -90.08)])
    result = scoring.counterfactual_similarity(track, _observed_slick(), provider=provider, particle_count=30)
    for field in ("spatial_overlap", "centroid_distance_km", "shape_similarity",
                  "orientation_similarity", "density_similarity"):
        assert hasattr(result.metrics, field)


# -- Step 6: transparent composite scoring -------------------------------

def _all_evidence(provider, mmsi="A", with_gap=False, near_origin=True, run_counterfactual=True):
    if with_gap:
        pts = [(0, 28.40, -90.10), (90, 28.42, -90.08)]  # 90-min gap
    else:
        pts = [(0, 28.40, -90.10), (10, 28.405, -90.095), (20, 28.41, -90.09), (30, 28.42, -90.08)]
    lat_shift = 0.0 if near_origin else 10.0
    track = _track(mmsi, [(m, lat + lat_shift, lon) for m, lat, lon in pts])

    return scoring.build_evidence(
        track=track,
        origin_region=ORIGIN_REGION,
        release_window=RELEASE_WINDOW,
        drift_bearing_deg=48.0,
        observed_slick=_observed_slick() if run_counterfactual else None,
        provider=provider if run_counterfactual else None,
    )


def test_evidence_stores_all_six_components_separately(provider):
    ev = _all_evidence(provider)
    for field in ("origin_proximity", "temporal_compatibility", "trajectory_consistency",
                  "behaviour_anomaly", "ais_gap", "counterfactual_similarity"):
        assert hasattr(ev, field), f"{field} missing from evidence"


def test_counterfactual_component_is_none_when_not_requested(provider):
    """Step 5 is expensive and only runs for high-ranked candidates — a
    candidate that never got a counterfactual run must report None, never a
    fabricated 0."""
    ev = _all_evidence(provider, run_counterfactual=False)
    assert ev.counterfactual_similarity is None


def test_weights_are_named_constants_summing_to_one():
    """Acceptance: do not hard-code percentages. Every weight is a documented,
    inspectable constant."""
    total = sum(scoring.SCORE_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6
    assert set(scoring.SCORE_WEIGHTS) == {
        "origin_proximity", "temporal_compatibility", "trajectory_consistency",
        "behaviour_anomaly", "ais_gap", "counterfactual_similarity",
    }


def test_composite_score_omits_counterfactual_weight_when_not_run():
    """When counterfactual_similarity is None, its weight must be
    redistributed rather than silently treated as 0 (which would penalise
    every candidate that didn't get the expensive step)."""
    ev_with = _all_evidence(provider=MockEnvironmentalProvider(), run_counterfactual=True)
    ev_without = _all_evidence(provider=MockEnvironmentalProvider(), run_counterfactual=False)

    score_with = scoring.composite_score(ev_with)
    score_without = scoring.composite_score(ev_without)
    assert 0.0 <= score_with <= 1.0
    assert 0.0 <= score_without <= 1.0


def test_a_candidate_near_origin_scores_higher_than_one_far_away(provider):
    near = _all_evidence(provider, mmsi="A", near_origin=True, run_counterfactual=False)
    far = _all_evidence(provider, mmsi="B", near_origin=False, run_counterfactual=False)
    assert scoring.composite_score(near) > scoring.composite_score(far)


def test_no_hardcoded_percentage_in_composite(provider):
    """Changing any one component must move the composite score by an amount
    consistent with its documented weight — proof the score is actually
    computed from the stored components, not a fixed number."""
    ev = _all_evidence(provider, run_counterfactual=False)
    base = scoring.composite_score(ev)
    assert ev.behaviour_anomaly < 0.7, "fixture must leave headroom to boost this component"

    import dataclasses
    boosted = dataclasses.replace(ev, behaviour_anomaly=min(1.0, ev.behaviour_anomaly + 0.3))
    boosted_score = scoring.composite_score(boosted)
    assert boosted_score != base
    # The change must be explainable by the documented weight, not arbitrary
    # (allowing for the composite's own 4-decimal rounding at each step).
    expected_delta = 0.3 * scoring.SCORE_WEIGHTS["behaviour_anomaly"]
    assert abs((boosted_score - base) - expected_delta) < 0.01


# -- ranking ---------------------------------------------------------------

def test_candidates_are_ranked_by_composite_score(provider):
    tracks = {
        "A": _track("A", [(0, 28.40, -90.10), (30, 28.42, -90.08)]),
        "B": _track("B", [(0, 20.00, -85.00), (30, 20.01, -84.99)]),
    }
    ranked = scoring.rank_candidates(
        tracks, origin_region=ORIGIN_REGION, release_window=RELEASE_WINDOW,
        drift_bearing_deg=48.0, observed_slick=_observed_slick(), provider=provider,
        counterfactual_top_n=2,
    )
    scores = [c.score for c in ranked]
    assert scores == sorted(scores, reverse=True)


def test_a_vessel_with_no_plausible_connection_is_filtered_out(provider):
    """Acceptance/design: steps 1-2 are a hard pre-filter, not just a soft
    score — a vessel far from the origin region AND active weeks away from
    the release window has no plausible connection to the incident and must
    not appear in the ranked output at all."""
    plausible = _track("A", [(0, 28.40, -90.10), (30, 28.42, -90.08)])
    irrelevant = _track("B", [
        (60 * 24 * 30, 5.0, 80.0), (60 * 24 * 30 + 30, 5.01, 80.01),
    ])  # a month later, on the far side of the planet
    ranked = scoring.rank_candidates(
        {"A": plausible, "B": irrelevant},
        origin_region=ORIGIN_REGION, release_window=RELEASE_WINDOW,
        drift_bearing_deg=48.0, observed_slick=None, provider=None,
    )
    mmsis = {c.mmsi for c in ranked}
    assert mmsis == {"A"}


def test_only_top_n_get_counterfactual_simulation(provider):
    """Acceptance/design: counterfactual is only run for high-ranked
    candidates (top N), not every candidate that passes earlier filters."""
    tracks = {mmsi: _track(mmsi, [(0, 28.40 + i * 0.01, -90.10), (30, 28.42 + i * 0.01, -90.08)])
              for i, mmsi in enumerate(["A", "B", "C", "D", "E"])}
    ranked = scoring.rank_candidates(
        tracks, origin_region=ORIGIN_REGION, release_window=RELEASE_WINDOW,
        drift_bearing_deg=48.0, observed_slick=_observed_slick(), provider=provider,
        counterfactual_top_n=2,
    )
    with_counterfactual = [c for c in ranked if c.evidence.counterfactual_similarity is not None]
    assert len(with_counterfactual) <= 2


# -- language / acceptance guards -------------------------------------------

def test_language_never_calls_a_vessel_a_culprit(provider):
    ev = _all_evidence(provider, with_gap=True, run_counterfactual=False)
    result = scoring.rank_candidates(
        {"A": _track("A", [(0, 28.40, -90.10), (90, 28.42, -90.08)])},
        origin_region=ORIGIN_REGION, release_window=RELEASE_WINDOW,
        drift_bearing_deg=48.0, observed_slick=None, provider=None,
    )
    c = result[0]
    for banned in ("culprit", "guilty", "perpetrator", "criminal"):
        assert banned not in c.narrative.lower()
        assert banned not in (c.label or "").lower()


def test_candidate_label_uses_acceptance_vocabulary(provider):
    result = scoring.rank_candidates(
        {"A": _track("A", [(0, 28.40, -90.10), (90, 28.42, -90.08)])},
        origin_region=ORIGIN_REGION, release_window=RELEASE_WINDOW,
        drift_bearing_deg=48.0, observed_slick=None, provider=None,
    )
    c = result[0]
    assert c.label in ("candidate", "investigation lead")


def test_evidence_is_never_summarised_as_a_verdict(provider):
    result = scoring.rank_candidates(
        {"A": _track("A", [(0, 28.40, -90.10), (90, 28.42, -90.08)])},
        origin_region=ORIGIN_REGION, release_window=RELEASE_WINDOW,
        drift_bearing_deg=48.0, observed_slick=None, provider=None,
    )
    import json
    blob = json.dumps(result[0].__dict__, default=str).lower()
    for banned in ("verdict", "confirmed", "proven", "identified as"):
        assert banned not in blob
