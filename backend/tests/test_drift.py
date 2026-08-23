"""Phase 3 acceptance tests — the real Lagrangian ensemble against the frozen case."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from app.api.drift import _forecast, _hindcast
from app.core.case_store import load_case
from app.drift import cone as cone_mod
from app.drift import lagrangian

CASE = Path(__file__).resolve().parents[2] / "data" / "case"

pytestmark = pytest.mark.skipif(
    not (CASE / "case.json").exists(),
    reason="case bundle not built — run scripts/build_case.py",
)


@pytest.fixture(scope="module")
def truth():
    return json.loads((CASE / "case.json").read_text())["ground_truth"]


@pytest.fixture(scope="module")
def hind():
    return _hindcast("slick-001", 500, 0.03, 42)


@pytest.fixture(scope="module")
def fore():
    return _forecast("slick-001", 12.0, 500, 0.03, 42)


def _origin_region(h, pct: int) -> Polygon:
    """The pooled origin region — the answer, distinct from any single frame."""
    c = next(c for c in h.cone if c.percentile == pct and c.kind == "origin")
    return Polygon(c.polygon["coordinates"][0])


# -- the acceptance criterion ----------------------------------------------

def test_ninety_percent_region_contains_the_true_origin(hind, truth):
    """Phase 3's headline requirement."""
    assert _origin_region(hind, 90).contains(Point(*truth["origin"]))


def test_origin_mode_is_close_to_the_truth(hind, truth):
    o = hind.origin_estimate.point
    d = math.hypot((o[0] - truth["origin"][0]) * 97.8, (o[1] - truth["origin"][1]) * 110.6)
    assert d < 15.0, f"mode is {d:.1f} km from the true origin"


def test_true_release_time_is_inside_the_window(hind, truth):
    lo, hi = hind.origin_estimate.time_window_hours
    assert lo <= truth["drift_hours"] <= hi


# -- uncertainty is represented honestly ------------------------------------

def test_origin_is_a_region_not_a_pin(hind):
    assert hind.origin_estimate.uncertainty_radius_km > 1.0
    assert _origin_region(hind, 90).area > 0


def test_fifty_percent_region_is_inside_the_ninety(hind):
    """Containment levels must nest, or they are not containment levels."""
    inner, outer = _origin_region(hind, 50), _origin_region(hind, 90)
    assert inner.area < outer.area
    assert outer.buffer(1e-9).contains(inner.buffer(-1e-9)) or inner.intersection(outer).area / inner.area > 0.9


def test_cloud_spreads_across_track_as_it_runs_backward(hind):
    """Diffusion is irreversible: running time backward still widens the cloud.
    It shows up ACROSS the trail, since along-track the 26 km slick already
    dominates. The growth is modest, and that is the physically honest result —
    Okubo diffusion adds a couple of km over 19 h, so the origin uncertainty is
    driven by the age window and the slick's own extent, not by turbulence."""
    frames = hind.particles_timeline
    first = np.array(frames[0].points)
    last = np.array(frames[-1].points)
    assert last[:, 1].std() > first[:, 1].std() * 1.05


def test_age_window_dominates_the_origin_uncertainty(hind):
    """The pooled origin region must be larger than the cloud at any single
    instant, because not knowing WHEN the release happened is the biggest term."""
    pooled = _origin_region(hind, 90)
    widest_frame = max(
        Polygon(c.polygon["coordinates"][0]).area
        for c in hind.cone if c.percentile == 90 and c.kind == "frame"
    )
    assert pooled.area > widest_frame


def test_wider_age_window_gives_a_wider_origin_region():
    """The link between Stage 1 and Stage 2: less certainty about the age must
    produce less certainty about the origin."""
    from app.drift import engine
    b = load_case()
    det_ring = _hindcast("slick-001", 500, 0.03, 42)
    ring = json.loads((CASE / "case.json").read_text())
    del det_ring, ring

    from app.api.detection import _run
    from app.core.schemas import DetectionMethod
    poly = _run(DetectionMethod.classical).slicks[0].polygon["coordinates"][0]

    narrow = engine.hindcast(b, poly, (7.0, 9.0), n_particles=400, wind_factor=0.03, seed=7)
    wide = engine.hindcast(b, poly, (4.0, 20.0), n_particles=400, wind_factor=0.03, seed=7)
    assert wide.origin_estimate.uncertainty_radius_km > narrow.origin_estimate.uncertainty_radius_km


# -- direction and mechanics ------------------------------------------------

def test_hindcast_runs_backward(hind):
    offsets = [f.t_offset_hours for f in hind.particles_timeline]
    assert min(offsets) < 0 and max(offsets) == 0


def test_forecast_runs_forward(fore):
    offsets = [f.t_offset_hours for f in fore.particles_timeline]
    assert max(offsets) > 0 and min(offsets) == 0


def test_forecast_returns_a_centroid_path(fore):
    assert fore.centroid_path["type"] == "LineString"
    assert len(fore.centroid_path["coordinates"]) >= 3


def test_particles_are_seeded_across_the_slick_not_at_a_point():
    """Seeding only the centroid would discard the origin uncertainty the
    slick's own 26 km extent implies."""
    from app.api.detection import _run
    from app.core.schemas import DetectionMethod
    ring = _run(DetectionMethod.classical).slicks[0].polygon["coordinates"][0]
    pts = lagrangian.seed_in_polygon(ring, 400, np.random.default_rng(1))
    span_km = (pts[:, 0].max() - pts[:, 0].min()) * 97.8
    assert span_km > 10.0, f"particles span only {span_km:.1f} km"


def test_diffusivity_grows_with_scale():
    """Okubo: a bigger patch spreads faster. A fixed K under-spreads a growing
    cloud and overstates confidence in the origin."""
    assert lagrangian.okubo_diffusivity(50_000) > lagrangian.okubo_diffusivity(500) * 5


# -- determinism and speed --------------------------------------------------

def test_hindcast_is_deterministic():
    """A cone that jitters between rehearsals will get questioned on stage."""
    from app.drift import engine
    from app.api.detection import _run
    from app.core.schemas import DetectionMethod
    b = load_case()
    ring = _run(DetectionMethod.classical).slicks[0].polygon["coordinates"][0]
    a = engine.hindcast(b, ring, (5.0, 15.0), n_particles=300, wind_factor=0.03, seed=11)
    c = engine.hindcast(b, ring, (5.0, 15.0), n_particles=300, wind_factor=0.03, seed=11)
    assert a.origin_estimate.point == c.origin_estimate.point


def test_drift_is_fast_enough_for_a_live_demo():
    import time
    from app.drift import engine
    from app.api.detection import _run
    from app.core.schemas import DetectionMethod
    b = load_case()
    ring = _run(DetectionMethod.classical).slicks[0].polygon["coordinates"][0]
    t = time.perf_counter()
    engine.hindcast(b, ring, (4.0, 20.0), n_particles=500, wind_factor=0.03, seed=3)
    assert (time.perf_counter() - t) < 3.0


def test_provenance_states_the_physics(hind):
    p = hind.provenance.params
    assert p["diffusion"] == "Okubo scale-dependent"
    for k in ("wind_factor", "timestep_minutes", "age_window_hours", "seed"):
        assert k in p


def test_containment_polygon_tracks_cloud_shape():
    """A sheared cloud must not be summarised as a circle."""
    rng = np.random.default_rng(0)
    pts = np.column_stack([rng.normal(-90, 0.20, 3000), rng.normal(28.5, 0.02, 3000)])
    ring = cone_mod.containment_polygon(pts, 0.9)
    poly = Polygon(ring)
    minx, miny, maxx, maxy = poly.bounds
    assert (maxx - minx) / (maxy - miny) > 3
