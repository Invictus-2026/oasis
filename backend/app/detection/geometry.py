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
    """Full morphology record for one region, in real-world units.

    Area comes from the pixel count rather than the simplified polygon: contour
    simplification is for rendering, and using it here would quietly bias the
    area low.

    Length and width are the extents along the region's own principal axes
    (measured in classical._shape_stats), converted to km. Aspect ratio is
    length/width — related to, but not the same as, `elongation`, which is the
    second-moment eigenvalue ratio of the fitted ellipse. Both are reported
    because they answer different questions: elongation describes the mass
    distribution, aspect ratio the bounding extent.
    """
    px_km = math.sqrt(bundle.pixel_area_km2())  # square pixels in this projection

    area_km2 = region.area_px * bundle.pixel_area_km2()
    ring = contour_to_lonlat(region.contour, bundle)
    perim_km = ring_perimeter_km(ring)

    length_km = region.length_px * px_km
    width_km = region.width_px * px_km
    aspect_ratio = (length_km / width_km) if width_km > 0 else 1.0

    # Recompute compactness in real units. The pixel-space value is distorted
    # because a degree of longitude is shorter than a degree of latitude here.
    compactness = (4 * math.pi * area_km2 / (perim_km ** 2)) if perim_km > 0 else 0.0

    return {
        "area_km2": round(area_km2, 2),
        "perimeter_km": round(perim_km, 2),
        "length_km": round(length_km, 2),
        "width_km": round(width_km, 3),
        "aspect_ratio": round(aspect_ratio, 2),
        "elongation": round(region.elongation, 2),
        "orientation_deg": round(region.orientation_deg, 1),
        "compactness": round(min(compactness, 1.0), 3),
        "solidity": round(region.solidity, 3),
    }


def backscatter(region) -> dict:
    """Per-region backscatter statistics, as measured on the filtered raster.

    These are the raw radiometric numbers behind the contrast and variance
    terms in classical.classify(); surfacing them keeps the confidence score
    auditable instead of opaque.
    """
    return {
        "mean_db": round(float(region.mean_db), 2),
        "std_db": round(float(region.std_db), 3),
        "background_db": round(float(region.background_db), 2),
        "contrast_db": round(float(region.contrast_db), 2),
        "variance_ratio": round(float(region.variance_ratio), 3),
        "edge_gradient": round(float(region.edge_gradient), 4),
    }
