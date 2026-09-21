"""A* search over a `NavGrid`, with an edge cost blending great-circle
distance, a fuel proxy, and a current-opposition penalty.

8-connected grid (8 neighbour directions per cell). Kept as a standalone
function of `(grid, start, goal, params)` rather than a class, since it has
no state of its own — `GridRoutePlanner` (planner.py) is what carries state
across a replan.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from app.routing.grid import NavGrid, haversine_km

# 8-connectivity offsets (d_row, d_col).
_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


@dataclass
class CostParams:
    """Tunables for the A* edge cost.

    `fuel_per_km`: proxy fuel burn per km at cruise (arbitrary units — only
    relative weighting against the current penalty matters for routing
    behaviour; the same constant is reused at the end to report an estimated
    fuel figure).
    `current_penalty_weight`: how strongly a headwind-like opposing current
    inflates an edge's cost, as a fraction of the edge's base distance cost.
    Zero disables current weighting entirely (blocking-only behaviour).
    `vessel_speed_kmh`: nominal vessel speed through still water, used both
    for the fuel proxy and for translating opposing-current strength into an
    equivalent extra-distance penalty.
    """

    fuel_per_km: float = 1.0
    current_penalty_weight: float = 1.5
    vessel_speed_kmh: float = 15.0 * 1.852  # 15 kn


def _edge_current_penalty(
    grid: NavGrid, r0: int, c0: int, r1: int, c1: int, params: CostParams
) -> float:
    """Cost multiplier addition (>= 0) for moving from cell (r0,c0) to
    (r1,c1) against the local current.

    Projects the mean current vector along the segment's travel direction:
    a following current (positive projection) gives zero penalty (it is
    never rewarded with negative cost, which would break A*'s admissibility
    and could create negative-cost cycles); an opposing current scales the
    penalty up to `current_penalty_weight` at a current speed equal to the
    vessel's own cruise speed, and beyond, since a strong-enough opposing
    current is a real routing hazard, not just an efficiency loss.
    """
    lon0, lat0 = grid.lonlat_of(r0, c0)
    lon1, lat1 = grid.lonlat_of(r1, c1)
    dx, dy = lon1 - lon0, lat1 - lat0
    norm = math.hypot(dx, dy) or 1.0
    dir_x, dir_y = dx / norm, dy / norm

    u = (grid.u[r0, c0] + grid.u[r1, c1]) / 2.0
    v = (grid.v[r0, c0] + grid.v[r1, c1]) / 2.0
    # u is eastward (lon-like), v is northward (lat-like) — same axes as
    # (dir_x, dir_y), so a plain dot product is the along-track component.
    along_track_ms = u * dir_x + v * dir_y

    if along_track_ms >= 0:
        return 0.0
    vessel_speed_ms = params.vessel_speed_kmh / 3.6
    opposing_fraction = min(2.0, abs(along_track_ms) / max(vessel_speed_ms, 1e-6))
    return params.current_penalty_weight * opposing_fraction


def edge_cost(grid: NavGrid, r0: int, c0: int, r1: int, c1: int, params: CostParams) -> float:
    """Cost of the single hop (r0,c0) -> (r1,c1). Always positive and finite
    for two navigable, grid-adjacent cells — required for Dijkstra/A*
    correctness."""
    lon0, lat0 = grid.lonlat_of(r0, c0)
    lon1, lat1 = grid.lonlat_of(r1, c1)
    dist_km = haversine_km(lon0, lat0, lon1, lat1)
    fuel = params.fuel_per_km * dist_km
    penalty = _edge_current_penalty(grid, r0, c0, r1, c1, params) * dist_km
    return dist_km + fuel + penalty


def _heuristic_km(grid: NavGrid, r: int, c: int, goal_r: int, goal_c: int) -> float:
    """Admissible lower bound: great-circle distance to the goal, ignoring
    fuel/current terms (both are non-negative additions to the true cost, so
    dropping them keeps the heuristic from overestimating)."""
    lon0, lat0 = grid.lonlat_of(r, c)
    lon1, lat1 = grid.lonlat_of(goal_r, goal_c)
    return haversine_km(lon0, lat0, lon1, lat1)


def astar(
    grid: NavGrid,
    start: tuple[int, int],
    goal: tuple[int, int],
    params: CostParams | None = None,
) -> list[tuple[int, int]] | None:
    """A* over `grid.navigable` cells from `start` to `goal` (both (row, col)
    indices). Returns the path as a list of (row, col), including both
    endpoints, or None if unreachable.
    """
    params = params or CostParams()
    nav = grid.navigable
    if not nav[start] or not nav[goal]:
        raise ValueError("start and goal must both be on navigable cells")

    n_lat, n_lon = grid.n_lat, grid.n_lon
    goal_r, goal_c = goal

    g_score: dict[tuple[int, int], float] = {start: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    open_heap: list[tuple[float, tuple[int, int]]] = [
        (_heuristic_km(grid, start[0], start[1], goal_r, goal_c), start)
    ]
    closed: set[tuple[int, int]] = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            return _reconstruct(came_from, current)
        closed.add(current)

        r0, c0 = current
        for dr, dc in _NEIGHBOURS:
            r1, c1 = r0 + dr, c0 + dc
            if not (0 <= r1 < n_lat and 0 <= c1 < n_lon):
                continue
            if not nav[r1, c1]:
                continue
            # Prevent cutting a diagonal corner between two blocked cells
            # (a real vessel can't clip a corner of land/hazard either).
            if dr != 0 and dc != 0 and not (nav[r0, c1] and nav[r1, c0]):
                continue
            tentative = g_score[current] + edge_cost(grid, r0, c0, r1, c1, params)
            neighbour = (r1, c1)
            if tentative < g_score.get(neighbour, math.inf):
                g_score[neighbour] = tentative
                came_from[neighbour] = current
                f = tentative + _heuristic_km(grid, r1, c1, goal_r, goal_c)
                heapq.heappush(open_heap, (f, neighbour))

    return None


def _reconstruct(
    came_from: dict[tuple[int, int], tuple[int, int]], current: tuple[int, int]
) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path
