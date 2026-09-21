"""water_only() must keep spill/drift polygon geometry off land, and the
fixture-backed API responses that draw cones/slicks must honour that —
regression coverage for the Mississippi Delta cone tip that was previously
confirmed (via reverse-geocoding) to render on real land.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Point, shape

from app.core import fixtures
from app.drift.coastline import COASTLINE_PATH, water_only

pytestmark = pytest.mark.skipif(
    not COASTLINE_PATH.exists(),
    reason="coastline mask not built — run scripts/fetch_coastline.py",
)


def test_polygon_straddling_the_coast_keeps_only_its_water_half():
    from app.drift.coastline import _land_polygon
    from shapely.geometry import mapping

    land = _land_polygon()
    assert land is not None, "coastline mask should have land in this case bbox"

    # A point confirmed (via reverse-geocoding, during development of this
    # feature) to sit on real land near Terrebonne Bay, at the edge of the
    # buffered land mask — a circle around it straddles the coastline.
    land_pt = Point(-89.570992, 28.861178)
    circle = land_pt.buffer(0.3)

    clipped = water_only(mapping(circle))
    assert clipped is not None, "a polygon straddling the coast should keep its water half"

    clipped_geom = shape(clipped)
    assert clipped_geom.intersection(land).area < 1e-9
    assert clipped_geom.area < circle.area, "clipping should have removed the land portion"


def test_polygon_fully_on_land_returns_none():
    from app.drift.coastline import _land_polygon

    land = _land_polygon()
    assert land is not None
    # centroid of the land polygon is, by construction, inside it (or very close)
    inside_point = land.representative_point()
    tiny_land_polygon = inside_point.buffer(0.001)

    from shapely.geometry import mapping

    result = water_only(mapping(tiny_land_polygon))
    assert result is None


def test_open_water_polygon_is_unchanged():
    from shapely.geometry import Point, mapping

    open_water = Point(-90.00, 28.55).buffer(0.05)  # case center, confirmed open water
    result = water_only(mapping(open_water))
    assert result is not None
    assert shape(result).equals(open_water)


def test_fixture_detection_slick_stays_off_land():
    from app.drift.coastline import _land_polygon

    land = _land_polygon()
    if land is None:
        pytest.skip("no land near this case bbox")

    detection = fixtures.detect_response()
    for slick in detection.slicks:
        geom = shape(slick.polygon)
        overlap = geom.intersection(land).area
        assert overlap < 1e-9, f"slick {slick.id} overlaps land"


def test_fixture_forecast_cone_stays_off_land():
    from app.drift.coastline import _land_polygon

    land = _land_polygon()
    if land is None:
        pytest.skip("no land near this case bbox")

    # 24h (not the UI default of 12h) so this actually exercises the clip:
    # the fixture's mean drift carries the 90th-percentile cone onto the
    # buffered land mask by ~t=18h, confirmed by direct measurement before
    # water_only() was wired into forecast_response().
    forecast = fixtures.forecast_response(hours=24.0)
    for cone in forecast.cone:
        geom = shape(cone.polygon)
        overlap = geom.intersection(land).area
        assert overlap < 1e-9, (
            f"forecast cone at t={cone.t_offset_hours}h (p{cone.percentile}) overlaps land"
        )
