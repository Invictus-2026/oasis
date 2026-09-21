"""Navigable grid construction.

A `NavGrid` rasterises a lat/lon bounding box into a regular cell grid and
tracks, per cell:

  * `blocked`   — permanently unnavigable (land, from bathymetry)
  * `hazard`    — currently unnavigable (spill polygon + buffer); this layer
                  is cheap to rebuild on its own so replanning after a new
                  drift hindcast never re-touches the bathymetry mask.
  * `u`, `v`    — current vector components (m/s) sampled onto the grid, used
                  for cost weighting rather than blocking.

No GIS stack: a polygon is a plain list of (lon, lat) rings (as GeoJSON
gives you), rasterised with an even-odd point-in-polygon test done in numpy
per row. Bathymetry is treated as a GEBCO-style dense grid of elevation
values in metres (negative = underwater), passed straight in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

EARTH_RADIUS_KM = 6371.0088


@dataclass
class BoundingBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not (self.west < self.east and self.south < self.north):
            raise ValueError("bounding box must have west < east and south < north")


def _point_in_rings(xs: np.ndarray, ys: np.ndarray, rings: list[list[tuple[float, float]]]) -> np.ndarray:
    """Even-odd rule membership test for arrays of points against a polygon's
    rings (first ring = exterior, rest = holes), GeoJSON-style.

    Vectorised over `xs`/`ys` (same shape); returns a bool array. Ray casting
    with a horizontal ray, accumulated ring by ring with XOR — a point inside
    an odd number of rings (exterior minus holes) is inside the polygon.
    """
    inside = np.zeros(xs.shape, dtype=bool)
    for ring in rings:
        ring_inside = np.zeros(xs.shape, dtype=bool)
        n = len(ring)
        if n < 3:
            continue
        x1, y1 = ring[-1]
        for x2, y2 in ring:
            crosses = ((y1 > ys) != (y2 > ys))
            if np.any(crosses):
                # x-coordinate where the edge crosses the ray's latitude.
                with np.errstate(divide="ignore", invalid="ignore"):
                    x_intersect = (x2 - x1) * (ys - y1) / (y2 - y1 + 1e-300) + x1
                ring_inside ^= crosses & (xs < x_intersect)
            x1, y1 = x2, y2
        inside ^= ring_inside
    return inside


def _dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    """Grow a boolean mask outward by `iterations` cells (8-connected),
    pure numpy (no scipy) so this module stays dependency-light. Cheap for
    the small iteration counts (1-3) this module actually uses."""
    out = mask
    for _ in range(iterations):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        grown[1:, 1:] |= out[:-1, :-1]
        grown[:-1, :-1] |= out[1:, 1:]
        grown[1:, :-1] |= out[:-1, 1:]
        grown[:-1, 1:] |= out[1:, :-1]
        out = grown
    return out


def rasterize_polygon(
    lons: np.ndarray,
    lats: np.ndarray,
    geojson_polygon: dict,
) -> np.ndarray:
    """Boolean mask, shape (n_lat, n_lon), True where a grid cell centre
    falls inside `geojson_polygon` (a GeoJSON Polygon or MultiPolygon dict —
    a bare geometry, or a Feature wrapping one).

    Note: any buffer distance around the spill must already be baked into
    the polygon's coordinates before this call (e.g. via shapely `.buffer()`
    upstream, or by widening the polygon yourself) — this function only
    rasterises whatever ring geometry it is given.
    """
    geom = geojson_polygon.get("geometry", geojson_polygon)
    gtype = geom.get("type")
    if gtype == "Polygon":
        polygons = [geom["coordinates"]]
    elif gtype == "MultiPolygon":
        polygons = geom["coordinates"]
    else:
        raise ValueError(f"expected Polygon or MultiPolygon, got {gtype!r}")

    xs, ys = np.meshgrid(lons, lats)  # both (n_lat, n_lon)
    mask = np.zeros(xs.shape, dtype=bool)
    for rings in polygons:
        mask |= _point_in_rings(xs, ys, [[(pt[0], pt[1]) for pt in ring] for ring in rings])
    return mask


@dataclass
class NavGrid:
    bbox: BoundingBox
    n_lon: int
    n_lat: int
    lons: np.ndarray = field(repr=False)   # (n_lon,) cell-centre longitudes
    lats: np.ndarray = field(repr=False)   # (n_lat,) cell-centre latitudes
    blocked: np.ndarray = field(repr=False)  # (n_lat, n_lon) bool — land, permanent
    hazard: np.ndarray = field(repr=False)   # (n_lat, n_lon) bool — spill+buffer, replaceable
    u: np.ndarray = field(repr=False)        # (n_lat, n_lon) float — eastward current m/s
    v: np.ndarray = field(repr=False)        # (n_lat, n_lon) float — northward current m/s

    @property
    def cell_size_deg(self) -> tuple[float, float]:
        return (self.lons[1] - self.lons[0]) if self.n_lon > 1 else 0.0, \
               (self.lats[1] - self.lats[0]) if self.n_lat > 1 else 0.0

    @property
    def navigable(self) -> np.ndarray:
        """Cells currently safe to route through: not land, not hazard."""
        return ~self.blocked & ~self.hazard

    def index_of(self, lon: float, lat: float) -> tuple[int, int]:
        """Nearest (row, col) grid index for a lon/lat point, clamped to the
        grid bounds so a point right on (or just past, from float error) the
        bbox edge still resolves to the boundary cell instead of raising."""
        col = int(round((lon - self.lons[0]) / (self.lons[1] - self.lons[0]))) if self.n_lon > 1 else 0
        row = int(round((lat - self.lats[0]) / (self.lats[1] - self.lats[0]))) if self.n_lat > 1 else 0
        col = min(max(col, 0), self.n_lon - 1)
        row = min(max(row, 0), self.n_lat - 1)
        return row, col

    def lonlat_of(self, row: int, col: int) -> tuple[float, float]:
        return float(self.lons[col]), float(self.lats[row])

    def set_hazard_polygons(self, polygons: list[dict], dilate_cells: int = 1) -> None:
        """Recompute the hazard layer from scratch (cheap: same-size boolean
        raster, no bathymetry re-sampling) — this is what a re-plan call uses
        instead of rebuilding the whole grid.

        `dilate_cells` grows the rasterised mask outward by that many cells
        (default 1) before it becomes the hazard layer. Cell-centre rasterisation
        alone only guarantees a route never enters a hazard cell — a straight
        segment between two cells that each graze the hazard boundary can
        still pass fractionally inside it between them. Dilating by one cell
        gives routes a real stand-off margin at negligible cost; set to 0 to
        rasterise exactly as given (e.g. if the caller's polygon already
        carries a generous buffer and exact-cell fidelity matters more).
        """
        mask = np.zeros((self.n_lat, self.n_lon), dtype=bool)
        for poly in polygons:
            mask |= rasterize_polygon(self.lons, self.lats, poly)
        if dilate_cells > 0 and mask.any():
            mask = _dilate(mask, dilate_cells)
        self.hazard = mask

    def nearest_navigable(self, row: int, col: int, max_radius: int = 25) -> tuple[int, int]:
        """BFS ring search outward for the nearest navigable cell — used when
        a start/end point (or a vessel's live position) lands inside a
        hazard or land cell, so routing can still depart from/arrive at the
        vessel's real position instead of failing outright."""
        nav = self.navigable
        if nav[row, col]:
            return row, col
        for r in range(1, max_radius + 1):
            r0, r1 = max(0, row - r), min(self.n_lat - 1, row + r)
            c0, c1 = max(0, col - r), min(self.n_lon - 1, col + r)
            ring_rows, ring_cols = [], []
            for rr in range(r0, r1 + 1):
                for cc in range(c0, c1 + 1):
                    if max(abs(rr - row), abs(cc - col)) != r:
                        continue
                    ring_rows.append(rr)
                    ring_cols.append(cc)
            if not ring_rows:
                continue
            ring_rows_a, ring_cols_a = np.array(ring_rows), np.array(ring_cols)
            ok = nav[ring_rows_a, ring_cols_a]
            if ok.any():
                idx = np.argmin(
                    (ring_rows_a[ok] - row) ** 2 + (ring_cols_a[ok] - col) ** 2
                )
                return int(ring_rows_a[ok][idx]), int(ring_cols_a[ok][idx])
        raise ValueError("no navigable cell found within search radius")


def build_grid(
    bbox: BoundingBox,
    resolution_deg: float,
    bathymetry: np.ndarray | None = None,
    bathy_bbox: BoundingBox | None = None,
    depth_threshold_m: float = 0.0,
    current_u: np.ndarray | None = None,
    current_v: np.ndarray | None = None,
    current_bbox: BoundingBox | None = None,
) -> NavGrid:
    """Build a `NavGrid` over `bbox` at `resolution_deg` cell size.

    `bathymetry`: a GEBCO-style dense 2-D elevation grid in metres (row 0 =
    north, per GEBCO convention; negative = underwater), spanning
    `bathy_bbox` (defaults to `bbox` if the caller's array already matches
    it exactly). Cells shallower than `depth_threshold_m` (default: sea
    level, 0 m) are masked as land. Pass `bathymetry=None` to skip land
    masking entirely (e.g. an all-water test grid).

    `current_u`/`current_v`: optional dense grids (m/s) over `current_bbox`,
    resampled onto the routing grid by nearest-neighbour (current fields are
    smooth relative to routing-grid resolution, so nearest-neighbour is
    sufficient and keeps this dependency-free).
    """
    n_lon = max(2, int(round((bbox.east - bbox.west) / resolution_deg)) + 1)
    n_lat = max(2, int(round((bbox.north - bbox.south) / resolution_deg)) + 1)
    lons = np.linspace(bbox.west, bbox.east, n_lon)
    lats = np.linspace(bbox.south, bbox.north, n_lat)

    blocked = np.zeros((n_lat, n_lon), dtype=bool)
    if bathymetry is not None:
        src_bbox = bathy_bbox or bbox
        depth = _resample_nearest(bathymetry, src_bbox, lons, lats)
        # depth_threshold_m is a non-negative "must be at least this deep"
        # figure (e.g. 5 m keel clearance): navigable requires elevation
        # below -depth_threshold_m (GEBCO convention: negative = underwater).
        blocked = depth > -abs(depth_threshold_m)

    u = np.zeros((n_lat, n_lon))
    v = np.zeros((n_lat, n_lon))
    if current_u is not None and current_v is not None:
        src_bbox = current_bbox or bbox
        u = _resample_nearest(current_u, src_bbox, lons, lats)
        v = _resample_nearest(current_v, src_bbox, lons, lats)

    hazard = np.zeros((n_lat, n_lon), dtype=bool)
    return NavGrid(bbox=bbox, n_lon=n_lon, n_lat=n_lat, lons=lons, lats=lats,
                    blocked=blocked, hazard=hazard, u=u, v=v)


def _resample_nearest(
    source: np.ndarray,
    source_bbox: BoundingBox,
    dst_lons: np.ndarray,
    dst_lats: np.ndarray,
) -> np.ndarray:
    """Nearest-neighbour resample `source` (row 0 = north, GEBCO/raster
    convention) onto the `dst_lons` x `dst_lats` grid. Pure numpy indexing —
    no rasterio/scipy — which is what keeps this module dependency-light."""
    src_h, src_w = source.shape
    src_lons = np.linspace(source_bbox.west, source_bbox.east, src_w)
    src_lats_north_to_south = np.linspace(source_bbox.north, source_bbox.south, src_h)

    col_idx = np.clip(np.searchsorted(src_lons, dst_lons), 0, src_w - 1)
    # searchsorted needs ascending order; latitudes here run north->south
    # (descending), so search on the reversed, ascending view and flip back.
    row_idx_asc = np.clip(np.searchsorted(src_lats_north_to_south[::-1], dst_lats), 0, src_h - 1)
    row_idx = src_h - 1 - row_idx_asc

    rows, cols = np.meshgrid(row_idx, col_idx, indexing="ij")
    return source[rows, cols]


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))
