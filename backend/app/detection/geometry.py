"""Geometric characterisation of a detected slick, in real-world units."""

from __future__ import annotations

import math

import numpy as np

KM_PER_DEG_LAT = 110.574


def km_per_deg_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def contour_to_lonlat(contour: np.ndarray, bundle) -> list[list[float]]:
    """Pixel contour -> a closed GeoJSON ring."""
    lon, lat = bundle.pixel_to_lonlat(contour[:, 0], contour[:, 1])
    ring = [[float(a), float(b)] for a, b in zip(lon, lat)]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def ring_perimeter_km(ring: list[list[float]]) -> float:
    """Great-circle-ish perimeter using a local flat-earth approximation, which
    is accurate to well under a percent over a scene this size."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
        mlat = 0.5 * (lat1 + lat2)
        dx = (lon2 - lon1) * km_per_deg_lon(mlat)
        dy = (lat2 - lat1) * KM_PER_DEG_LAT
        total += math.hypot(dx, dy)
    return total


def describe(region, bundle) -> dict:
    """Area, perimeter, elongation, orientation and compactness.

    Area comes from the pixel count rather than the simplified polygon: contour
    simplification is for rendering, and using it here would quietly bias the
    area low.
    """
    area_km2 = region.area_px * bundle.pixel_area_km2()
    ring = contour_to_lonlat(region.contour, bundle)
    perim_km = ring_perimeter_km(ring)

    # Recompute compactness in real units. The pixel-space value is distorted
    # because a degree of longitude is shorter than a degree of latitude here.
    compactness = (4 * math.pi * area_km2 / (perim_km ** 2)) if perim_km > 0 else 0.0

    return {
        "area_km2": round(area_km2, 2),
        "perimeter_km": round(perim_km, 2),
        "elongation": round(region.elongation, 2),
        "orientation_deg": round(region.orientation_deg, 1),
        "compactness": round(min(compactness, 1.0), 3),
    }
