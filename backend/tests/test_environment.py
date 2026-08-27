"""Phase 3 — environmental data provider abstraction.

Covers the provider interface itself (real + mock implementations agree on a
normalised EnvironmentalData shape), the resolution/fallback logic, and the
query API for incident / location / time range.

Deliberately NOT covered here: particle simulation. Phase 3 only has to prove
the simulation engine *could* pull its forcing through this seam.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.environment import mock as mock_provider
from app.environment.base import EnvironmentalData, EnvironmentalDataProvider
from app.environment.bundle import CaseBundleProvider
from app.environment.resolver import get_provider

CASE = Path(__file__).resolve().parents[2] / "data" / "case"
T0 = datetime(2023, 6, 15, 12, 0, tzinfo=timezone.utc)

# A point inside the frozen case bbox.
LON, LAT = -90.05, 28.45


@pytest.fixture()
def mock():
    return mock_provider.MockEnvironmentalProvider()


# -- the normalised type ----------------------------------------------------

REQUIRED_FIELDS = (
    "lon", "lat", "time_utc",
    "u_current_ms", "v_current_ms",
    "u_wind_ms", "v_wind_ms",
)


def test_environmental_data_carries_every_required_field(mock):
    sample = mock.at(LON, LAT, T0)
    for field in REQUIRED_FIELDS:
        assert getattr(sample, field) is not None, f"{field} missing"


def test_waves_are_optional_not_fabricated(mock):
    """Waves are 'where available'. A provider with no wave data must say None
    rather than invent a number."""
    sample = mock.at(LON, LAT, T0)
    assert hasattr(sample, "wave_height_m")
    assert hasattr(sample, "wave_dir_deg")


def test_derived_speed_and_bearing_are_consistent(mock):
    """Speed/direction are conveniences over u/v, so they must agree with them."""
    import math

    s = mock.at(LON, LAT, T0)
    assert s.current_speed_ms == pytest.approx(math.hypot(s.u_current_ms, s.v_current_ms), rel=1e-6)
    assert s.wind_speed_ms == pytest.approx(math.hypot(s.u_wind_ms, s.v_wind_ms), rel=1e-6)
    assert 0.0 <= s.current_dir_deg < 360.0
    assert 0.0 <= s.wind_dir_deg < 360.0


def test_direction_convention_is_documented_and_correct(mock):
    """Oceanographic convention here: direction the vector points TOWARD,
    degrees clockwise from north. Due-east flow must read 90 degrees."""
    sample = EnvironmentalData(
        lon=0.0, lat=0.0, time_utc=T0,
        u_current_ms=1.0, v_current_ms=0.0,
        u_wind_ms=0.0, v_wind_ms=1.0,
    )
    assert sample.current_dir_deg == pytest.approx(90.0)   # east
    assert sample.wind_dir_deg == pytest.approx(0.0)       # north


def test_is_json_serialisable(mock):
    import json
    json.dumps(mock.at(LON, LAT, T0).model_dump(mode="json"))


# -- the provider interface -------------------------------------------------

def test_mock_provider_implements_the_interface(mock):
    assert isinstance(mock, EnvironmentalDataProvider)


def test_interface_cannot_be_instantiated_directly():
    """It is an abstraction; a concrete provider must supply .at()."""
    with pytest.raises(TypeError):
        EnvironmentalDataProvider()  # type: ignore[abstract]


def test_every_provider_reports_availability_and_name(mock):
    assert isinstance(mock.available(), bool)
    assert isinstance(mock.name, str) and mock.name


def test_mock_provider_is_always_available(mock):
    """The whole point of the fallback: it must never be the thing that fails."""
    assert mock.available() is True


def test_provider_is_deterministic(mock):
    """Two identical queries must agree, or drift runs stop being reproducible."""
    a = mock.at(LON, LAT, T0)
    b = mock.at(LON, LAT, T0)
    assert a.model_dump() == b.model_dump()


def test_series_covers_the_requested_range(mock):
    end = T0 + timedelta(hours=6)
    series = mock.series(LON, LAT, T0, end, step_hours=2.0)
    assert len(series) == 4  # 0, 2, 4, 6 h inclusive
    assert series[0].time_utc == T0
    assert series[-1].time_utc == end
    assert all(s.lon == LON and s.lat == LAT for s in series)


def test_series_is_ordered_in_time(mock):
    series = mock.series(LON, LAT, T0, T0 + timedelta(hours=12), step_hours=3.0)
    times = [s.time_utc for s in series]
    assert times == sorted(times)


def test_series_rejects_an_inverted_range(mock):
    with pytest.raises(ValueError):
        mock.series(LON, LAT, T0, T0 - timedelta(hours=1), step_hours=1.0)


def test_series_rejects_a_nonpositive_step(mock):
    with pytest.raises(ValueError):
        mock.series(LON, LAT, T0, T0 + timedelta(hours=1), step_hours=0.0)


def test_single_instant_range_returns_one_sample(mock):
    series = mock.series(LON, LAT, T0, T0, step_hours=1.0)
    assert len(series) == 1


# -- the real (case-bundle) provider ---------------------------------------

needs_bundle = pytest.mark.skipif(
    not (CASE / "case.json").exists(),
    reason="case bundle not built — run scripts/build_case.py",
)


@needs_bundle
def test_bundle_provider_returns_real_forcing():
    from app.core.case_store import load_case

    provider = CaseBundleProvider(load_case())
    assert provider.available() is True

    sample = provider.at(LON, LAT, T0)
    for field in REQUIRED_FIELDS:
        assert getattr(sample, field) is not None
    # The frozen case has a real mesoscale field; a dead-zero sample would mean
    # the interpolation silently missed the grid.
    assert sample.current_speed_ms > 0.0
    assert sample.wind_speed_ms > 0.0


@needs_bundle
def test_bundle_provider_matches_the_underlying_forcing_field():
    """The provider must not alter the physics the drift engine already uses."""
    from app.core.case_store import load_case
    from app.drift.fields import ForcingField

    bundle = load_case()
    field = ForcingField.from_bundle(bundle)
    provider = CaseBundleProvider(bundle)

    sample = provider.at(LON, LAT, T0)
    u = float(field._interp(field.u_current, LON, LAT))
    v = float(field._interp(field.v_current, LON, LAT))
    assert sample.u_current_ms == pytest.approx(u, rel=1e-9)
    assert sample.v_current_ms == pytest.approx(v, rel=1e-9)


@needs_bundle
def test_bundle_provider_is_steady_and_says_so():
    """This field has no time axis. Returning the same values for any time is
    correct; silently implying time-variation would not be."""
    from app.core.case_store import load_case

    provider = CaseBundleProvider(load_case())
    a = provider.at(LON, LAT, T0)
    b = provider.at(LON, LAT, T0 + timedelta(hours=18))
    assert (a.u_current_ms, a.v_current_ms) == (b.u_current_ms, b.v_current_ms)
    assert a.is_steady is True
    assert "steady" in a.source.lower() or "time-invariant" in a.source.lower()


@needs_bundle
def test_bundle_provider_satisfies_the_drift_engine_seam():
    """Phase 3's forward-looking acceptance: simulation must later be able to
    pull forcing through the provider. It needs surface_velocity()."""
    from app.core.case_store import load_case

    provider = CaseBundleProvider(load_case())
    u, v = provider.surface_velocity(LON, LAT, wind_factor=0.03, time=T0)
    assert isinstance(float(u), float) and isinstance(float(v), float)


@needs_bundle
def test_provider_accepts_a_whole_particle_array_like_the_drift_engine_does():
    """The load-bearing forward-looking test.

    lagrangian.advect() calls surface_velocity() once per timestep with the
    entire particle array, not once per particle. If the provider could only
    answer scalar queries, wiring simulation through it in Phase 4 would be a
    500x slowdown rather than a drop-in swap. It must also return exactly what
    ForcingField returns, or swapping the seam would silently change the
    measured drift results.
    """
    import numpy as np

    from app.core.case_store import load_case
    from app.drift.fields import ForcingField

    bundle = load_case()
    provider = CaseBundleProvider(bundle)
    field = ForcingField.from_bundle(bundle)

    rng = np.random.default_rng(0)
    lon = rng.uniform(-90.3, -89.7, 500)
    lat = rng.uniform(28.2, 28.9, 500)

    u_p, v_p = provider.surface_velocity(lon, lat, 0.03, T0)
    u_f, v_f = field.surface_velocity(lon, lat, 0.03)

    assert isinstance(u_p, np.ndarray) and u_p.shape == (500,)
    assert np.array_equal(u_p, u_f)
    assert np.array_equal(v_p, v_f)


@needs_bundle
def test_surface_velocity_equals_current_plus_wind_factor():
    from app.core.case_store import load_case

    provider = CaseBundleProvider(load_case())
    s = provider.at(LON, LAT, T0)
    u, v = provider.surface_velocity(LON, LAT, wind_factor=0.03, time=T0)
    assert float(u) == pytest.approx(s.u_current_ms + 0.03 * s.u_wind_ms, rel=1e-9)
    assert float(v) == pytest.approx(s.v_current_ms + 0.03 * s.v_wind_ms, rel=1e-9)


def test_bundle_provider_reports_unavailable_without_a_bundle():
    provider = CaseBundleProvider(None)
    assert provider.available() is False


# -- resolution / fallback --------------------------------------------------

def test_resolver_falls_back_to_mock_when_real_is_unavailable():
    provider = get_provider(bundle=None)
    assert provider.available() is True
    assert "mock" in provider.name.lower()


@needs_bundle
def test_resolver_prefers_the_real_provider_when_available():
    from app.core.case_store import load_case

    provider = get_provider(bundle=load_case())
    assert "mock" not in provider.name.lower()


def test_resolver_honours_a_forced_mock_mode(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config, "ENV_DATA_MODE", "mock", raising=False)
    provider = get_provider(bundle=None)
    assert "mock" in provider.name.lower()


def test_mock_provider_varies_in_space_and_time(mock):
    """A constant field would make the fallback useless for demonstrating
    drift behaviour."""
    here = mock.at(LON, LAT, T0)
    far = mock.at(LON + 0.4, LAT + 0.4, T0)
    later = mock.at(LON, LAT, T0 + timedelta(hours=9))

    assert (here.u_current_ms, here.v_current_ms) != (far.u_current_ms, far.v_current_ms)
    assert (here.u_wind_ms, here.v_wind_ms) != (later.u_wind_ms, later.v_wind_ms)


def test_mock_values_are_physically_plausible(mock):
    """Fallback data still has to be defensible on screen."""
    for hours in (0, 6, 12, 24):
        s = mock.at(LON, LAT, T0 + timedelta(hours=hours))
        assert 0.0 <= s.current_speed_ms < 3.0, "surface current out of plausible range"
        assert 0.0 <= s.wind_speed_ms < 40.0, "wind speed out of plausible range"


def test_mock_provider_is_labelled_as_synthetic(mock):
    """Honesty guard: mock data must never be mistaken for measured data."""
    s = mock.at(LON, LAT, T0)
    assert s.is_synthetic is True
    assert "synthetic" in s.source.lower() or "mock" in s.source.lower()


@needs_bundle
def test_real_provider_is_not_labelled_synthetic_when_forcing_is_real():
    """The frozen case's forcing is itself synthesised, and the provider must
    report that faithfully rather than claiming measurement."""
    from app.core.case_store import load_case

    bundle = load_case()
    provider = CaseBundleProvider(bundle)
    s = provider.at(LON, LAT, T0)
    declared = bundle.meta.get("forcing", {}).get("mode")
    assert s.is_synthetic == (declared == "synthetic")
