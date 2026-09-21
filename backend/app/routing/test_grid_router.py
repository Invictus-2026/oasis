"""Synthetic tests for the grid-based A* spill-avoidance router.

No real bathymetry/current data needed: an all-water grid plus a
hand-built circular "spill" polygon is enough to prove the geometry,
land-masking, current-weighting, and replanning behaviour independently of
any real dataset.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from app.routing.grid import BoundingBox, build_grid, haversine_km
from app.routing.astar import CostParams, astar, edge_cost
from app.routing.planner import GridRoutePlanner


def circle_polygon(center_lon: float, center_lat: float, radius_deg: float, n: int = 48) -> dict:
    """A GeoJSON Polygon approximating a circle — stands in for a spill
    extent (+ buffer) already expanded to its final shape."""
    coords = [
        [
            center_lon + radius_deg * math.cos(2 * math.pi * i / n),
            center_lat + radius_deg * math.sin(2 * math.pi * i / n),
        ]
        for i in range(n)
    ]
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


BBOX = BoundingBox(west=-91.0, south=28.0, east=-89.0, north=29.0)


class NavGridTests(unittest.TestCase):
    def test_all_water_grid_is_fully_navigable_without_bathymetry(self):
        grid = build_grid(BBOX, resolution_deg=0.05)
        self.assertTrue(grid.navigable.all())

    def test_land_masking_blocks_shallow_cells(self):
        # A tiny bathymetry grid: west half is land (+50 m), east half ocean (-500 m).
        bathy = np.full((10, 10), -500.0)
        bathy[:, :5] = 50.0
        grid = build_grid(BBOX, resolution_deg=0.1, bathymetry=bathy, bathy_bbox=BBOX, depth_threshold_m=0.0)
        west_col = grid.blocked[:, 0]
        east_col = grid.blocked[:, -1]
        self.assertTrue(west_col.all())
        self.assertFalse(east_col.any())

    def test_hazard_polygon_masks_expected_cells(self):
        grid = build_grid(BBOX, resolution_deg=0.02)
        spill = circle_polygon(-90.0, 28.5, radius_deg=0.15)
        grid.set_hazard_polygons([spill])
        center_row, center_col = grid.index_of(-90.0, 28.5)
        self.assertTrue(grid.hazard[center_row, center_col])
        corner_row, corner_col = grid.index_of(BBOX.west + 0.01, BBOX.south + 0.01)
        self.assertFalse(grid.hazard[corner_row, corner_col])

    def test_replacing_hazard_layer_does_not_touch_land_mask(self):
        bathy = np.full((10, 10), -500.0)
        bathy[:, :5] = 50.0
        grid = build_grid(BBOX, resolution_deg=0.1, bathymetry=bathy, bathy_bbox=BBOX, depth_threshold_m=0.0)
        before = grid.blocked.copy()
        grid.set_hazard_polygons([circle_polygon(-90.0, 28.5, 0.1)])
        np.testing.assert_array_equal(before, grid.blocked)


class AStarTests(unittest.TestCase):
    def test_straight_line_when_unobstructed(self):
        grid = build_grid(BBOX, resolution_deg=0.05)
        start = grid.index_of(-90.8, 28.2)
        goal = grid.index_of(-89.2, 28.8)
        path = astar(grid, start, goal)
        self.assertIsNotNone(path)
        # A clear grid should produce a reasonably direct path: total path
        # length shouldn't blow past the straight-line cell distance by much
        # (8-connected grid distance is within ~8% of Euclidean at worst).
        straight = math.dist(start, goal)
        rows = [p[0] for p in path]
        cols = [p[1] for p in path]
        path_len = sum(math.dist((rows[i], cols[i]), (rows[i + 1], cols[i + 1])) for i in range(len(path) - 1))
        self.assertLess(path_len, straight * 1.1)

    def test_unreachable_when_fully_enclosed(self):
        grid = build_grid(BBOX, resolution_deg=0.05)
        goal = grid.index_of(-90.0, 28.5)
        # Ring of hazard cells around the goal, thick enough that 8-connected
        # movement can't slip through a diagonal gap.
        grid.hazard[:, :] = False
        gr, gc = goal
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if max(abs(dr), abs(dc)) >= 2:
                    grid.hazard[gr + dr, gc + dc] = True
        start = grid.index_of(-90.8, 28.2)
        path = astar(grid, start, goal)
        self.assertIsNone(path)

    def test_current_penalty_increases_cost_against_flow(self):
        grid = build_grid(BBOX, resolution_deg=0.1)
        grid.u[:, :] = 5.0  # strong eastward current everywhere
        grid.v[:, :] = 0.0
        params = CostParams(current_penalty_weight=2.0)
        r, c = 5, 5
        eastward_cost = edge_cost(grid, r, c, r, c + 1, params)  # with current
        westward_cost = edge_cost(grid, r, c, r, c - 1, params)  # against current
        self.assertGreater(westward_cost, eastward_cost)


class GridRoutePlannerTests(unittest.TestCase):
    def test_route_bends_around_circular_spill(self):
        """The core scenario from the spec: start and end on either side of a
        circular spill placed directly between them. The direct line must
        cross the spill; the returned route must not.

        Per the spec, the polygon handed to the planner is "the spill
        extent, with a buffer" already applied — so this test buffers the
        true spill radius before passing it in, and then checks clearance
        against that same buffered radius (minus a hair of tolerance for
        grid discretisation), not against a zero-margin exact boundary.
        """
        start = (-90.8, 28.5)
        end = (-89.2, 28.5)
        center = (-90.0, 28.5)
        true_radius = 0.15
        buffer = 0.05
        buffered_radius = true_radius + buffer
        spill = circle_polygon(*center, radius_deg=buffered_radius)

        planner = GridRoutePlanner.build(BBOX, resolution_deg=0.02)
        result = planner.plan(start=start, end=end, spill_polygons=[spill])

        self.assertTrue(result.found)
        self.assertGreater(len(result.waypoints), 2, "a route around an obstacle needs interior waypoints")

        # Confirm the direct line actually would have crossed the spill,
        # so this is a meaningful test of the detour rather than a no-op.
        self.assertTrue(_segment_crosses_circle(start, end, center, buffered_radius))

        # A one-grid-cell allowance for discretisation: the hazard mask only
        # excludes cells whose CENTRE falls inside the buffered polygon, so a
        # route can legitimately graze within about one cell width of the
        # nominal boundary without ever entering a hazard cell.
        tolerance = 0.02 * 1.5
        clear_radius = buffered_radius - tolerance

        for lon, lat in result.waypoints:
            dist = math.hypot(lon - center[0], lat - center[1])
            self.assertGreaterEqual(dist, clear_radius, f"waypoint ({lon}, {lat}) is inside the spill")

        for i in range(len(result.waypoints) - 1):
            self.assertFalse(
                _segment_crosses_circle(result.waypoints[i], result.waypoints[i + 1], center, clear_radius),
                f"edge {result.waypoints[i]} -> {result.waypoints[i + 1]} crosses the spill",
            )

        # Detouring costs some extra distance versus the straight line, but
        # not an absurd amount for a circle this size relative to the transit.
        straight_km = haversine_km(*start, *end)
        self.assertGreater(result.distance_km, straight_km)
        self.assertLess(result.distance_km, straight_km * 1.6)
        self.assertGreater(result.estimated_time_hours, 0)
        self.assertGreater(result.estimated_fuel_units, 0)

    def test_replan_reuses_grid_and_moves_hazard(self):
        start = (-90.8, 28.5)
        end = (-89.2, 28.5)
        planner = GridRoutePlanner.build(BBOX, resolution_deg=0.03)

        first_spill = circle_polygon(-90.0, 28.5, radius_deg=0.15)
        first = planner.plan(start=start, end=end, spill_polygons=[first_spill])
        self.assertTrue(first.found)

        grid_identity = id(planner.grid)

        # Updated hindcast: spill has drifted north and shrunk.
        moved_spill = circle_polygon(-90.0, 28.75, radius_deg=0.1)
        vessel_now = first.waypoints[min(2, len(first.waypoints) - 1)]
        second = planner.replan(current_position=vessel_now, spill_polygons=[moved_spill])

        self.assertTrue(second.found)
        self.assertEqual(id(planner.grid), grid_identity, "replan must reuse the existing NavGrid object")
        for lon, lat in second.waypoints:
            dist = math.hypot(lon - (-90.0), lat - 28.75)
            self.assertGreaterEqual(dist, 0.1 * 0.98)

    def test_replan_without_end_reuses_last_destination(self):
        planner = GridRoutePlanner.build(BBOX, resolution_deg=0.05)
        planner.plan(start=(-90.8, 28.5), end=(-89.2, 28.5), spill_polygons=[])
        result = planner.replan(current_position=(-90.5, 28.5), spill_polygons=[])
        self.assertTrue(result.found)
        self.assertAlmostEqual(result.waypoints[-1][0], -89.2, places=6)
        self.assertAlmostEqual(result.waypoints[-1][1], 28.5, places=6)

    def test_route_around_land_and_spill_together(self):
        bathy = np.full((20, 20), -500.0)
        bathy[:16, 8:12] = 50.0  # a north-south land strip blocking the middle, with a gap at the top
        planner = GridRoutePlanner.build(
            BBOX, resolution_deg=0.05, bathymetry=bathy, bathy_bbox=BBOX, depth_threshold_m=0.0,
        )
        result = planner.plan(start=(-90.9, 28.1), end=(-89.1, 28.9), spill_polygons=[])
        self.assertTrue(result.found)
        for lon, lat in result.waypoints:
            row, col = planner.grid.index_of(lon, lat)
            self.assertFalse(planner.grid.blocked[row, col], f"waypoint ({lon},{lat}) is on land")

    def test_to_json_shape(self):
        planner = GridRoutePlanner.build(BBOX, resolution_deg=0.1)
        result = planner.plan(start=(-90.8, 28.5), end=(-89.2, 28.5), spill_polygons=[])
        payload = result.to_json()
        self.assertIn("waypoints", payload)
        self.assertIn("distance_km", payload)
        self.assertIn("estimated_time_hours", payload)
        self.assertTrue(all({"lon", "lat"} == set(wp) for wp in payload["waypoints"]))

    def test_point_outside_bbox_is_rejected_cleanly(self):
        planner = GridRoutePlanner.build(BBOX, resolution_deg=0.1)
        result = planner.plan(start=(-120.0, 28.5), end=(-89.2, 28.5), spill_polygons=[])
        self.assertFalse(result.found)
        self.assertIn("outside", result.reason)


def _segment_crosses_circle(
    p0: tuple[float, float], p1: tuple[float, float], center: tuple[float, float], radius: float
) -> bool:
    """True if the closest approach of segment p0->p1 to `center` is within
    `radius` — a plain point-to-segment distance check, used only by the
    tests to state the "route must avoid the spill" property precisely."""
    x0, y0 = p0
    x1, y1 = p1
    cx, cy = center
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return math.hypot(x0 - cx, y0 - cy) < radius
    t = max(0.0, min(1.0, ((cx - x0) * dx + (cy - y0) * dy) / (dx * dx + dy * dy)))
    closest = (x0 + t * dx, y0 + t * dy)
    return math.hypot(closest[0] - cx, closest[1] - cy) < radius


if __name__ == "__main__":
    unittest.main()
