"""`GridRoutePlanner` — the public entry point for grid-based spill-avoidance
routing, built to be cheap to re-invoke as new drift hindcasts arrive.

Usage:

    planner = GridRoutePlanner.build(
        bbox=BoundingBox(west=-90.6, south=28.1, east=-89.4, north=29.0),
        resolution_deg=0.02,
        bathymetry=gebco_array, bathy_bbox=gebco_bbox,
        current_u=u_grid, current_v=v_grid, current_bbox=current_bbox,
    )
    result = planner.plan(start=(lon, lat), end=(lon, lat), spill_polygons=[geojson])
    ...
    # a new hindcast comes in; reuse the same grid/bathymetry
    result2 = planner.replan(current_position=(lon, lat), spill_polygons=[new_geojson])

`plan`/`replan` return a `RouteResult`, whose `.to_json()` is exactly the
dict shape described in the module's API surface: ordered lat/lon
waypoints, distance, and time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.routing.astar import CostParams, astar
from app.routing.grid import BoundingBox, NavGrid, build_grid, haversine_km


@dataclass
class RouteResult:
    waypoints: list[tuple[float, float]]  # (lon, lat), in travel order
    distance_km: float
    estimated_time_hours: float
    estimated_fuel_units: float
    found: bool
    reason: str = "ok"

    def to_json(self) -> dict:
        return {
            "found": self.found,
            "reason": self.reason,
            "waypoints": [{"lon": lon, "lat": lat} for lon, lat in self.waypoints],
            "distance_km": round(self.distance_km, 3),
            "estimated_time_hours": round(self.estimated_time_hours, 3),
            "estimated_fuel_units": round(self.estimated_fuel_units, 3),
        }


@dataclass
class GridRoutePlanner:
    grid: NavGrid
    cost_params: CostParams = field(default_factory=CostParams)

    @classmethod
    def build(
        cls,
        bbox: BoundingBox,
        resolution_deg: float = 0.02,
        bathymetry: np.ndarray | None = None,
        bathy_bbox: BoundingBox | None = None,
        depth_threshold_m: float = 0.0,
        current_u: np.ndarray | None = None,
        current_v: np.ndarray | None = None,
        current_bbox: BoundingBox | None = None,
        cost_params: CostParams | None = None,
    ) -> "GridRoutePlanner":
        """Rasterise the operating area once. This is the expensive step
        (bathymetry/current resampling); everything after this reuses the
        same `NavGrid` and only touches the small hazard-mask layer."""
        grid = build_grid(
            bbox=bbox,
            resolution_deg=resolution_deg,
            bathymetry=bathymetry,
            bathy_bbox=bathy_bbox,
            depth_threshold_m=depth_threshold_m,
            current_u=current_u,
            current_v=current_v,
            current_bbox=current_bbox,
        )
        return cls(grid=grid, cost_params=cost_params or CostParams())

    def plan(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        spill_polygons: list[dict] | None = None,
    ) -> RouteResult:
        """Full plan from `start` to `end` (each (lon, lat)). Sets the hazard
        layer from `spill_polygons` (GeoJSON Polygon/MultiPolygon geometries
        or Features — buffer already applied by the caller) and searches."""
        self.grid.set_hazard_polygons(spill_polygons or [])
        return self._route(start, end)

    def replan(
        self,
        current_position: tuple[float, float],
        end: tuple[float, float] | None = None,
        spill_polygons: list[dict] | None = None,
    ) -> RouteResult:
        """Recompute the route from the vessel's current position after new
        spill geometry arrives (e.g. an updated drift hindcast), without
        rebuilding the bathymetry/current grid. `end` defaults to the last
        destination used, if omitted, so a caller only tracking hazard
        updates need not re-pass it every time."""
        if end is None:
            end = getattr(self, "_last_end", None)
            if end is None:
                raise ValueError("no prior destination to reuse; pass end= explicitly")
        self.grid.set_hazard_polygons(spill_polygons or [])
        return self._route(current_position, end)

    def _route(self, start: tuple[float, float], end: tuple[float, float]) -> RouteResult:
        self._last_end = end
        start_lon, start_lat = start
        end_lon, end_lat = end

        if not self._in_bbox(start_lon, start_lat):
            return RouteResult([], 0.0, 0.0, 0.0, found=False, reason="start point outside operating area")
        if not self._in_bbox(end_lon, end_lat):
            return RouteResult([], 0.0, 0.0, 0.0, found=False, reason="end point outside operating area")

        start_idx = self.grid.index_of(start_lon, start_lat)
        end_idx = self.grid.index_of(end_lon, end_lat)

        try:
            start_idx = self.grid.nearest_navigable(*start_idx)
            end_idx = self.grid.nearest_navigable(*end_idx)
        except ValueError:
            return RouteResult([], 0.0, 0.0, 0.0, found=False,
                                reason="no navigable water found near start or end point")

        if start_idx == end_idx:
            return RouteResult(
                [(start_lon, start_lat), (end_lon, end_lat)], 0.0, 0.0, 0.0, found=True,
                reason="start and end resolve to the same grid cell",
            )

        cell_path = astar(self.grid, start_idx, end_idx, self.cost_params)
        if cell_path is None:
            return RouteResult([], 0.0, 0.0, 0.0, found=False,
                                reason="no route found: spill and/or land fully block the operating area")

        waypoints = [(start_lon, start_lat)]
        waypoints += [self.grid.lonlat_of(r, c) for r, c in cell_path[1:-1]]
        waypoints.append((end_lon, end_lat))
        waypoints = _simplify_line_of_sight(waypoints, self.grid)

        distance_km = sum(
            haversine_km(*waypoints[i], *waypoints[i + 1]) for i in range(len(waypoints) - 1)
        )
        speed_kmh = self.cost_params.vessel_speed_kmh
        time_hours = distance_km / speed_kmh if speed_kmh > 0 else float("inf")
        fuel = distance_km * self.cost_params.fuel_per_km

        return RouteResult(waypoints, distance_km, time_hours, fuel, found=True)

    def _in_bbox(self, lon: float, lat: float) -> bool:
        b = self.grid.bbox
        return b.west <= lon <= b.east and b.south <= lat <= b.north


def _segment_is_clear(grid: NavGrid, p0: tuple[float, float], p1: tuple[float, float]) -> bool:
    """True if every point sampled along the straight segment p0->p1 (at
    roughly half a cell's spacing) lands on a navigable grid cell.

    Used to decide whether a shortcut between two non-adjacent waypoints is
    actually safe to take, rather than trusting geometric collinearity —
    a route that hugs a curved hazard boundary can look "nearly straight"
    point-to-point while a longer chord across those same points cuts
    inside the hazard, which pure collinearity would miss entirely.
    """
    lon0, lat0 = p0
    lon1, lat1 = p1
    cell_lon, cell_lat = grid.cell_size_deg
    step = min(cell_lon, cell_lat) / 2 if cell_lon and cell_lat else 1.0
    length = math.hypot(lon1 - lon0, lat1 - lat0)
    n_steps = max(1, int(math.ceil(length / step))) if step > 0 else 1
    nav = grid.navigable
    for i in range(n_steps + 1):
        t = i / n_steps
        lon, lat = lon0 + t * (lon1 - lon0), lat0 + t * (lat1 - lat0)
        row, col = grid.index_of(lon, lat)
        if not nav[row, col]:
            return False
    return True


def _simplify_line_of_sight(points: list[tuple[float, float]], grid: NavGrid) -> list[tuple[float, float]]:
    """Greedy line-of-sight simplification: from each kept waypoint, skip
    ahead to the farthest later waypoint reachable by a straight,
    entirely-navigable segment. Produces a much shorter waypoint list than
    the raw one-per-cell A* path while guaranteeing every shortcut is still
    hazard/land-free, unlike a plain collinearity test.
    """
    if len(points) <= 2:
        return points
    simplified = [points[0]]
    i = 0
    n = len(points)
    while i < n - 1:
        j = n - 1
        while j > i + 1 and not _segment_is_clear(grid, points[i], points[j]):
            j -= 1
        simplified.append(points[j])
        i = j
    return simplified
