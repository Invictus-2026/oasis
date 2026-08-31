"""Phase 5 — origin-time-and-location search.

Given an observed slick and a Lagrangian simulation engine, this searches
candidate (release location, release time) pairs over the previous 24 h,
scores each candidate by running a REAL forward simulation from the candidate
and comparing the resulting particle cloud to the observed slick, and ranks
them. Nothing here may hard-code a scientific result — every score must
change when the inputs (environmental data, observed geometry, search window)
change.

Explicitly NOT covered: age.py's Okubo width-inversion, which remains a
plausibility input into the comparison score, never the sole age estimator —
regression-tested here to confirm it stays a component, not the answer.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.drift import origin_search as osearch
from app.environment.base import EnvironmentalData
from app.environment.mock import MockEnvironmentalProvider

T_DETECT = datetime(2023, 6, 15, 12, 0, tzinfo=timezone.utc)

# A modest elongated "observed slick" polygon, roughly NE-SW trending.
OBSERVED_RING = [
    [-90.02, 28.50], [-90.00, 28.505], [-89.97, 28.52], [-89.95, 28.535],
    [-89.955, 28.545], [-89.98, 28.53], [-90.005, 28.515], [-90.02, 28.50],
]


def _observed_slick():
    return osearch.ObservedSlick(
        polygon=OBSERVED_RING,
        detected_at=T_DETECT,
        area_km2=6.2,
        orientation_deg=48.0,
        elongation=4.1,
        compactness=0.31,
    )


@pytest.fixture()
def provider():
    return MockEnvironmentalProvider()


# -- candidate generation ----------------------------------------------

def test_search_generates_candidates_across_the_previous_24_hours(provider):
    result = osearch.search(
        _observed_slick(), provider=provider,
        config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=1.0, particle_count=40),
    )
    ages = sorted(c.age_hours for c in result.candidates)
    assert ages[0] >= 1.0 - 1e-6
    assert ages[-1] <= 24.0 + 1e-6
    assert len(result.candidates) == 24


def test_time_step_controls_how_many_candidates_are_tried(provider):
    coarse = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=4.0, particle_count=30))
    fine = osearch.search(_observed_slick(), provider=provider,
                           config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=1.0, particle_count=30))
    assert len(coarse.candidates) == 6
    assert len(fine.candidates) == 24


def test_each_candidate_carries_a_location_and_a_time(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=6.0, time_step_hours=2.0, particle_count=30))
    for c in result.candidates:
        assert -180.0 <= c.origin_lon <= 180.0
        assert -90.0 <= c.origin_lat <= 90.0
        assert c.release_time_utc < T_DETECT
        assert c.age_hours > 0


# -- each candidate is a REAL simulation, not a shortcut --------------

def test_candidate_location_comes_from_a_real_backward_simulation(provider, monkeypatch):
    """The recommended design: propose via backward sim, score via forward
    sim. Both must actually invoke the Phase 4 engine."""
    from app.drift import simulate

    calls = {"n": 0}
    orig_run = simulate.run

    def counting_run(*args, **kwargs):
        calls["n"] += 1
        return orig_run(*args, **kwargs)

    monkeypatch.setattr(simulate, "run", counting_run)
    osearch.search(_observed_slick(), provider=provider,
                    config=osearch.SearchConfig(max_age_hours=6.0, time_step_hours=2.0, particle_count=20))
    # >= 2 sims per candidate (backward propose + forward verify) x 3 candidates.
    assert calls["n"] >= 6


def test_candidate_forward_cloud_is_stored_for_scoring(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=6.0, time_step_hours=3.0, particle_count=25))
    for c in result.candidates:
        assert c.simulated_positions.shape[0] == 25
        assert c.simulated_positions.shape[1] == 2


# -- the five comparison metrics ----------------------------------------

def test_scoring_computes_all_five_metrics():
    observed = _observed_slick()
    # A synthetic simulated cloud, roughly centred on the observed slick, so
    # every metric has something non-degenerate to measure.
    rng = np.random.default_rng(0)
    center = np.mean(OBSERVED_RING, axis=0)
    cloud = rng.normal(center, 0.01, size=(200, 2))

    m = osearch.compare(cloud, observed)
    for field in ("spatial_overlap", "centroid_distance_km", "shape_similarity",
                  "orientation_similarity", "density_similarity"):
        assert hasattr(m, field)
        assert getattr(m, field) is not None


def test_spatial_overlap_is_one_for_a_perfect_match():
    observed = _observed_slick()
    # Sample densely INSIDE the observed polygon itself.
    from app.drift.lagrangian import _points_in_poly
    poly = np.asarray(OBSERVED_RING)
    rng = np.random.default_rng(1)
    lo, hi = poly.min(axis=0), poly.max(axis=0)
    pts = np.empty((0, 2))
    while len(pts) < 300:
        batch = rng.uniform(lo, hi, size=(2000, 2))
        pts = np.vstack([pts, batch[_points_in_poly(batch, poly)]])
    cloud = pts[:300]

    m = osearch.compare(cloud, observed)
    assert m.spatial_overlap > 0.7


def test_spatial_overlap_is_near_zero_for_a_distant_cloud():
    observed = _observed_slick()
    cloud = np.column_stack([
        np.full(100, -85.0), np.full(100, 25.0),
    ])  # far from the observed slick
    m = osearch.compare(cloud, observed)
    assert m.spatial_overlap < 0.05


def test_centroid_distance_increases_with_offset():
    observed = _observed_slick()
    center = np.mean(OBSERVED_RING, axis=0)
    rng = np.random.default_rng(2)

    near = rng.normal(center, 0.005, size=(150, 2))
    far = rng.normal(center + [0.3, 0.3], 0.005, size=(150, 2))

    m_near = osearch.compare(near, observed)
    m_far = osearch.compare(far, observed)
    assert m_far.centroid_distance_km > m_near.centroid_distance_km


def test_orientation_similarity_penalises_a_perpendicular_cloud():
    observed = _observed_slick()  # 48 degrees
    center = np.mean(OBSERVED_RING, axis=0)
    rng = np.random.default_rng(3)

    # A cloud elongated ALONG the observed bearing (48 deg) ...
    theta = math.radians(48.0)
    along = center + rng.normal(0, [0.02, 0.02], size=(300, 2)) * [math.sin(theta), math.cos(theta)]
    # ... vs one elongated PERPENDICULAR to it (138 deg).
    theta_perp = math.radians(138.0)
    perp = center + rng.normal(0, [0.02, 0.02], size=(300, 2)) * [math.sin(theta_perp), math.cos(theta_perp)]

    m_along = osearch.compare(along, observed)
    m_perp = osearch.compare(perp, observed)
    assert m_along.orientation_similarity > m_perp.orientation_similarity


def test_density_similarity_penalises_a_much_more_diffuse_cloud():
    observed = _observed_slick()
    center = np.mean(OBSERVED_RING, axis=0)
    rng = np.random.default_rng(4)

    tight = rng.normal(center, 0.008, size=(200, 2))
    diffuse = rng.normal(center, 0.08, size=(200, 2))

    m_tight = osearch.compare(tight, observed)
    m_diffuse = osearch.compare(diffuse, observed)
    assert m_tight.density_similarity > m_diffuse.density_similarity


# -- the documented composite score --------------------------------------

def test_composite_score_is_a_weighted_documented_combination():
    """Weights must sum to 1 and be inspectable, not a black box."""
    weights = osearch.SCORE_WEIGHTS
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert set(weights) == {
        "spatial_overlap", "centroid_distance", "shape_similarity",
        "orientation_similarity", "density_similarity",
    }


def test_composite_score_is_between_zero_and_one():
    observed = _observed_slick()
    rng = np.random.default_rng(5)
    center = np.mean(OBSERVED_RING, axis=0)
    for spread in (0.005, 0.05, 0.3):
        cloud = rng.normal(center, spread, size=(150, 2))
        m = osearch.compare(cloud, observed)
        assert 0.0 <= m.composite_score <= 1.0


def test_a_closer_matching_candidate_scores_higher():
    observed = _observed_slick()
    center = np.mean(OBSERVED_RING, axis=0)
    rng = np.random.default_rng(6)

    good = rng.normal(center, 0.01, size=(200, 2))
    bad = rng.normal(center + [0.5, 0.5], 0.15, size=(200, 2))

    assert osearch.compare(good, observed).composite_score > osearch.compare(bad, observed).composite_score


# -- ranking --------------------------------------------------------------

def test_candidates_are_ranked_best_first(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=2.0, particle_count=30))
    scores = [c.metrics.composite_score for c in result.ranked]
    assert scores == sorted(scores, reverse=True)


def test_best_candidate_is_the_top_of_the_ranking(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=2.0, particle_count=30))
    assert result.best is result.ranked[0]


# -- output: origin, regions, age, uncertainty, confidence -----------------

def test_result_exposes_best_origin_and_release_time(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=2.0, particle_count=40))
    assert -180 <= result.best.origin_lon <= 180
    assert -90 <= result.best.origin_lat <= 90
    assert result.best.release_time_utc < T_DETECT


def test_result_provides_50_and_90_percent_regions(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=2.0, particle_count=60))
    assert result.region_50 is not None
    assert result.region_90 is not None
    assert result.region_50["type"] == "Polygon"
    assert result.region_90["type"] == "Polygon"


def test_90_percent_region_is_not_smaller_than_50_percent(provider):
    from app.drift.cone import ring_area_km2

    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=1.0, particle_count=80))
    a50 = ring_area_km2(result.region_50["coordinates"][0])
    a90 = ring_area_km2(result.region_90["coordinates"][0])
    assert a90 >= a50 * 0.95  # allow for grid/contour discretisation noise


def test_result_reports_age_as_detection_minus_release(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=1.0, particle_count=40))
    expected = (T_DETECT - result.best.release_time_utc).total_seconds() / 3600.0
    assert result.estimated_age_hours == pytest.approx(expected, abs=0.01)


def test_result_reports_an_age_uncertainty_window(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=1.0, particle_count=40))
    lo, hi = result.age_uncertainty_hours
    assert lo <= result.estimated_age_hours <= hi
    assert lo >= 0.0


def test_result_reports_a_confidence_indicator(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=1.0, particle_count=40))
    assert result.confidence in ("low", "medium", "high")


def test_age_output_never_claims_exact_certainty(provider):
    """Acceptance: do not claim exact origin or exact age."""
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=1.0, particle_count=40))
    lo, hi = result.age_uncertainty_hours
    assert hi > lo, "a zero-width age window would be an exact-age claim"
    assert result.confidence != "high" or (hi - lo) > 0.5


# -- Okubo is a constraint/component, never the sole age estimator ---------

def test_okubo_alone_does_not_determine_the_ranking():
    """Regression guard: two candidates with identical Okubo-predicted age
    plausibility but different simulated-cloud fit must NOT score identically
    — proving the composite isn't secretly just the age heuristic."""
    observed = _observed_slick()
    center = np.mean(OBSERVED_RING, axis=0)
    rng = np.random.default_rng(9)

    close_fit = rng.normal(center, 0.01, size=(150, 2))
    far_fit = rng.normal(center + [0.4, 0.1], 0.01, size=(150, 2))

    m_close = osearch.compare(close_fit, observed)
    m_far = osearch.compare(far_fit, observed)
    assert m_close.composite_score != m_far.composite_score


def test_age_plausibility_is_one_input_not_the_whole_score():
    """SCORE_WEIGHTS must not give the Okubo-derived term full weight — it is
    a documented empirical constraint, not the sole estimator."""
    assert "spatial_overlap" in osearch.SCORE_WEIGHTS
    assert "shape_similarity" in osearch.SCORE_WEIGHTS
    # No single weight may dominate the composite outright.
    assert all(w < 0.6 for w in osearch.SCORE_WEIGHTS.values())


# -- GeoJSON output for the map --------------------------------------------

def test_result_converts_to_geojson_for_the_map(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=2.0, particle_count=40))
    fc = result.to_geojson()
    assert fc["type"] == "FeatureCollection"
    kinds = {f["properties"]["kind"] for f in fc["features"]}
    assert {"origin_50", "origin_90", "best_origin"} <= kinds

    for feature in fc["features"]:
        assert feature["type"] == "Feature"
        geom = feature["geometry"]
        if geom["type"] == "Point":
            lon, lat = geom["coordinates"]
        else:
            ring = geom["coordinates"][0]
            assert ring[0] == ring[-1]
            for lon, lat in ring:
                assert -180 <= lon <= 180 and -90 <= lat <= 90

    import json
    json.dumps(fc)


def test_geojson_carries_age_and_confidence_in_properties(provider):
    result = osearch.search(_observed_slick(), provider=provider,
                             config=osearch.SearchConfig(max_age_hours=24.0, time_step_hours=2.0, particle_count=40))
    fc = result.to_geojson()
    props = fc["properties"]
    assert "estimated_age_hours" in props
    assert "age_uncertainty_hours" in props
    assert "confidence" in props
    assert "release_time_utc" in props


# -- acceptance: environmental conditions change the result ----------------

def test_changing_environmental_conditions_changes_the_result(provider):
    """Acceptance: changing environmental conditions changes the hindcast
    result. Two providers with different currents must rank different bests
    or at least produce a different best origin/time."""

    class ScaledProvider(MockEnvironmentalProvider):
        name = "mock-scaled-for-test"

        def at(self, lon, lat, time):
            s = super().at(lon, lat, time)
            return s.model_copy(update={
                "u_current_ms": s.u_current_ms * 4.0 + 0.15,
                "v_current_ms": s.v_current_ms * 4.0 - 0.10,
            })

    cfg = osearch.SearchConfig(max_age_hours=12.0, time_step_hours=2.0, particle_count=40)
    a = osearch.search(_observed_slick(), provider=provider, config=cfg, seed=1)
    b = osearch.search(_observed_slick(), provider=ScaledProvider(), config=cfg, seed=1)

    assert (a.best.origin_lon, a.best.origin_lat) != (b.best.origin_lon, b.best.origin_lat)


def test_no_hardcoded_scientific_result(provider):
    """Acceptance: no hard-coded scientific result. Two structurally different
    observed slicks (different centroid, different shape) must produce
    different best origins — a hard-coded answer would not vary."""
    slick_a = _observed_slick()
    shifted_ring = [[lon + 0.3, lat + 0.2] for lon, lat in OBSERVED_RING]
    slick_b = osearch.ObservedSlick(
        polygon=shifted_ring, detected_at=T_DETECT, area_km2=6.2,
        orientation_deg=48.0, elongation=4.1, compactness=0.31,
    )

    cfg = osearch.SearchConfig(max_age_hours=12.0, time_step_hours=2.0, particle_count=40)
    ra = osearch.search(slick_a, provider=provider, config=cfg, seed=2)
    rb = osearch.search(slick_b, provider=provider, config=cfg, seed=2)
    assert (ra.best.origin_lon, ra.best.origin_lat) != (rb.best.origin_lon, rb.best.origin_lat)


# -- config validation -----------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("max_age_hours", 0), ("max_age_hours", -1),
    ("time_step_hours", 0), ("time_step_hours", -1),
    ("particle_count", 0), ("particle_count", -10),
])
def test_search_config_rejects_invalid_values(field, value):
    with pytest.raises(Exception):
        osearch.SearchConfig(**{field: value})


def test_search_default_window_is_24_hours():
    cfg = osearch.SearchConfig()
    assert cfg.max_age_hours == 24.0
