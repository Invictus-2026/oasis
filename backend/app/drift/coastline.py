"""Water-only clipping for spill/drift polygons.

Cone, slick, and look-alike geometry is meant to describe where oil sits or
plausibly might sit on the water surface — it should never be drawn as
covering land. `water_only()` clips a GeoJSON polygon against a real
coastline mask (see scripts/fetch_coastline.py for how that mask is built)
so this holds regardless of what the drift/cone math produces upstream.

This intentionally clips polygon *regions* only, not individual drift
particle points: a particle drifting onto land is meaningful information
(the spill reaching shore), and the app already surfaces that separately
via ImpactFlag(kind="coastline", ...). It's the drawn area — the shape a
viewer reads as "oil is here" — that must never appear to sit on land.
"""

from __future__ import annotations

import json
from functools import lru_cache

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from app.core.config import CASE_DIR

COASTLINE_PATH = CASE_DIR / "coastline.json"


@lru_cache(maxsize=1)
def _land_polygon() -> BaseGeometry | None:
    """The cached land mask, or None if no coastline data ships (or no land
    falls near the case bbox at all — e.g. a fully open-ocean case)."""
    if not COASTLINE_PATH.exists():
        return None
    data = json.loads(COASTLINE_PATH.read_text())
    features = data.get("features", [])
    if not features:
        return None
    geom = shape(features[0]["geometry"])
    return geom if not geom.is_empty else None


def water_only(polygon_geojson: dict) -> dict | None:
    """Clip a GeoJSON Polygon/MultiPolygon to the water side of the
    coastline mask. Returns None if the shape is entirely on land (nothing
    left to draw) or invalid; returns the polygon unchanged if it doesn't
    reach land or no coastline data is available.
    """
    land = _land_polygon()
    if land is None:
        return polygon_geojson

    geom = shape(polygon_geojson)
    if not geom.is_valid:
        geom = geom.buffer(0)  # standard shapely fix for minor self-intersections
    if geom.is_empty:
        return None

    if not geom.intersects(land):
        return polygon_geojson

    clipped = geom.difference(land)
    if clipped.is_empty:
        return None
    return mapping(clipped)
