#!/usr/bin/env python3
"""One-time fetch of a real coastline/land polygon clipped to the frozen case
bbox, so drift/forecast geometry (slick, lookalikes, cones) can be clipped to
water and never rendered on top of land.

Run once, from a machine with network access:

    uv run scripts/fetch_coastline.py

Source: Natural Earth's public-domain 10m land polygon dataset
(naturalearthdata.com), fetched once and clipped down to a small buffered
box around CASE_BBOX. The clipped result lands at data/case/coastline.json
and is committed to the repo — the running app never fetches it, or
contacts Natural Earth, again.

No GIS stack needed beyond shapely (already a project dependency): the
Natural Earth shapefile's polygon geometry is parsed directly from the
.shp binary (ESRI Shapefile format, polygon records only) rather than
pulling in fiona/GDAL for a single one-time read.
"""

from __future__ import annotations

import io
import json
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "case" / "coastline.json"

# Same bbox as backend/app/core/config.py's CASE_BBOX.
CASE_BBOX = {"west": -90.60, "south": 28.10, "east": -89.40, "north": 29.00}
# Generous buffer so cones/particles that wander outside the case bbox
# during longer forecasts still clip correctly against real land nearby.
BUFFER_DEG = 0.5

# Natural Earth's 10m land polygon is a continental-scale generalization —
# in the Mississippi Delta specifically (one of the most complex, low-lying
# coastlines on Earth) it can sit 15-20 km away from real marsh/barrier-
# island edges (measured against OSM's finer coastline data during
# development). Grow the polygon outward by this much so clipped geometry
# stays clear of land the raw dataset under-represents, rather than
# clipping tight to a boundary that's itself wrong in this region.
LAND_SAFETY_BUFFER_KM = 25.0
KM_PER_DEG = 111.32

LAND_URL = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip"


def _read_shapefile_polygons(shp_bytes: bytes) -> list[dict]:
    """Parse polygon records out of an ESRI Shapefile (.shp) binary.

    Format reference: an 100-byte file header, then a sequence of records,
    each an 8-byte record header (big-endian) followed by shape content
    (little-endian). Shape type 5 = Polygon: bbox, part index array, then
    a flat array of (x, y) points shared across all parts/rings.
    """
    polygons = []
    offset = 100  # past the file header
    n = len(shp_bytes)
    while offset < n:
        rec_number, content_len = struct.unpack(">ii", shp_bytes[offset:offset + 8])
        offset += 8
        content_start = offset
        shape_type = struct.unpack("<i", shp_bytes[offset:offset + 4])[0]
        offset += 4
        if shape_type == 5:  # Polygon
            offset += 32  # bounding box (4 doubles: xmin, ymin, xmax, ymax) — unused, just skipped
            num_parts, num_points = struct.unpack("<ii", shp_bytes[offset:offset + 8])
            offset += 8
            parts = struct.unpack(f"<{num_parts}i", shp_bytes[offset:offset + 4 * num_parts])
            offset += 4 * num_parts
            points = struct.unpack(f"<{2 * num_points}d", shp_bytes[offset:offset + 16 * num_points])
            offset += 16 * num_points
            rings = []
            part_bounds = list(parts) + [num_points]
            for i in range(num_parts):
                start, end = part_bounds[i], part_bounds[i + 1]
                ring = [(points[2 * j], points[2 * j + 1]) for j in range(start, end)]
                rings.append(ring)
            # Shapefile polygon rings can encode multiple disjoint outer
            # rings (this dataset's landmasses) plus holes; treat each ring
            # as its own polygon shell and let unary_union sort overlaps
            # out — simpler and just as correct for a coastline mask.
            for ring in rings:
                if len(ring) >= 4:
                    polygons.append({"type": "Polygon", "coordinates": [ring]})
        # content_len is in 16-bit words; skip to the next record regardless
        # of shape type so an unexpected record never desyncs the parser.
        offset = content_start + content_len * 2
    return polygons


def main() -> None:
    print(f"Fetching {LAND_URL} ...")
    with urllib.request.urlopen(LAND_URL, timeout=60) as resp:
        zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        shp_name = next(n for n in zf.namelist() if n.endswith(".shp"))
        shp_bytes = zf.read(shp_name)

    print("Parsing shapefile polygons ...")
    raw_polygons = _read_shapefile_polygons(shp_bytes)
    print(f"  {len(raw_polygons)} rings in the full world dataset")

    west = CASE_BBOX["west"] - BUFFER_DEG
    south = CASE_BBOX["south"] - BUFFER_DEG
    east = CASE_BBOX["east"] + BUFFER_DEG
    north = CASE_BBOX["north"] + BUFFER_DEG
    clip_box = shape({
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    })

    shapes = [shape(p) for p in raw_polygons]
    # Cheap bbox pre-filter before the expensive intersection.
    nearby = [s for s in shapes if s.is_valid and s.intersects(clip_box)]
    print(f"  {len(nearby)} rings intersect the buffered case bbox")

    if not nearby:
        print("No land found near the case bbox — writing an empty FeatureCollection.")
        merged = None
    else:
        merged = unary_union(nearby)
        buffer_deg = LAND_SAFETY_BUFFER_KM / KM_PER_DEG
        merged = merged.buffer(buffer_deg).intersection(clip_box)
        print(f"  buffered land by {LAND_SAFETY_BUFFER_KM} km ({buffer_deg:.4f}°)")

    geojson = {
        "type": "FeatureCollection",
        "features": (
            [{"type": "Feature", "properties": {}, "geometry": mapping(merged)}]
            if merged is not None and not merged.is_empty
            else []
        ),
        "properties": {
            "source": "Natural Earth 10m land (public domain)",
            "source_url": LAND_URL,
            "clipped_to": {"west": west, "south": south, "east": east, "north": north},
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(geojson))
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    sys.exit(main())
