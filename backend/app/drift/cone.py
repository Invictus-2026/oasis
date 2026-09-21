"""
Turn a particle cloud into containment polygons.

A scatter of 500 dots is not an answer a judge can read. The honest summary is
"the release occurred somewhere in here, with this much confidence", which is a
region at a stated containment level.

Method: kernel-density the cloud onto a grid, then find the density threshold
enclosing p% of the total mass and trace its contour. This follows the shape of
the cloud, including the curved, sheared shapes a real current field produces,
which a convex hull or an ellipse would both misrepresent.
"""

from __future__ import annotations

import math

import cv2
import numpy as np
from scipy import ndimage

from app.drift.coastline import water_only

GRID = 160
SMOOTH_PX = 3.5

KM_PER_DEG_LAT = 110.574


def _density(points: np.ndarray, pad: float = 0.22):
    lon, lat = points[:, 0], points[:, 1]
    lo_x, hi_x = lon.min(), lon.max()
    lo_y, hi_y = lat.min(), lat.max()
    dx, dy = (hi_x - lo_x) or 0.01, (hi_y - lo_y) or 0.01
    lo_x, hi_x = lo_x - pad * dx, hi_x + pad * dx
    lo_y, hi_y = lo_y - pad * dy, hi_y + pad * dy

    ix = np.clip(((lon - lo_x) / (hi_x - lo_x) * (GRID - 1)).astype(int), 0, GRID - 1)
    iy = np.clip(((lat - lo_y) / (hi_y - lo_y) * (GRID - 1)).astype(int), 0, GRID - 1)

    h = np.zeros((GRID, GRID), dtype=np.float32)
    np.add.at(h, (iy, ix), 1.0)
    h = ndimage.gaussian_filter(h, SMOOTH_PX)
    return h, (lo_x, hi_x, lo_y, hi_y)


def _threshold_for_mass(h: np.ndarray, fraction: float) -> float:
    """Density level enclosing `fraction` of the total mass."""
    flat = np.sort(h.ravel())[::-1]
    cum = np.cumsum(flat)
    total = cum[-1]
    if total <= 0:
        return 0.0
    idx = int(np.searchsorted(cum, fraction * total))
    return float(flat[min(idx, len(flat) - 1)])


def containment_polygon(points: np.ndarray, fraction: float) -> list[list[float]] | None:
    """Smallest region containing `fraction` of the ensemble, as a GeoJSON ring."""
    if len(points) < 8:
        return None

    h, (lo_x, hi_x, lo_y, hi_y) = _density(points)
    thr = _threshold_for_mass(h, fraction)
    mask = (h >= thr).astype(np.uint8)
    if mask.sum() < 4:
        return None

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    cnt = max(cnts, key=cv2.contourArea)
    cnt = cv2.approxPolyDP(cnt, 1.2, True).reshape(-1, 2)
    if len(cnt) < 3:
        return None

    ring = [
        [float(lo_x + cx / (GRID - 1) * (hi_x - lo_x)),
         float(lo_y + cy / (GRID - 1) * (hi_y - lo_y))]
        for cx, cy in cnt
    ]
    ring.append(ring[0])
    return ring


def water_polygon(ring: list[list[float]]) -> dict | None:
    """A containment ring as a GeoJSON polygon dict, clipped to water.

    Cone/origin regions are drawn as the answer to "where might the oil
    be" — they must never be drawn as covering land, however the density
    contour above happened to come out. Returns None if the ring is
    entirely on land (nothing left to draw); may return a MultiPolygon if
    clipping splits the region into separate water pockets.
    """
    return water_only({"type": "Polygon", "coordinates": [ring]})


def mode(points: np.ndarray) -> tuple[float, float]:
    """Densest point of the cloud — the single most likely position.

    Reported only alongside the containment region, never on its own.
    """
    h, (lo_x, hi_x, lo_y, hi_y) = _density(points)
    iy, ix = np.unravel_index(int(np.argmax(h)), h.shape)
    return (
        float(lo_x + ix / (GRID - 1) * (hi_x - lo_x)),
        float(lo_y + iy / (GRID - 1) * (hi_y - lo_y)),
    )


def ring_area_km2(ring: list[list[float]]) -> float:
    """Shoelace area of a lon/lat ring in km²."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = 111.320 * math.cos(math.radians(lat0))
    pts = [((lon) * kx, lat * KM_PER_DEG_LAT) for lon, lat in ring]
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def equivalent_radius_km(ring: list[list[float]]) -> float:
    return math.sqrt(ring_area_km2(ring) / math.pi)
