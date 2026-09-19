"""Conservative simulation routing with an explicit, user-supplied clearance scenario."""
import heapq
import math
import time
from fastapi import APIRouter, HTTPException
from shapely.geometry import Point, LineString, Polygon, shape, mapping
from shapely.ops import unary_union, transform
from app.core.schemas import RerouteRequest, RerouteResponse

router = APIRouter()

@router.post("/api/vessel/reroute", response_model=RerouteResponse)
def reroute_vessel(req: RerouteRequest):
    started = time.time()
    points = [req.start_point, req.end_point]
    has_points = all(p is not None for p in points)
    for p in points:
        if p is not None and (not all(math.isfinite(v) for v in p) or not -180 <= p[0] <= 180 or not -85 <= p[1] <= 85):
            raise HTTPException(422, "Coordinates must be finite, within ±180° longitude and ±85° latitude.")
    lat = sum(p[1] for p in points if p is not None) / max(1, sum(p is not None for p in points))
    scale_x = 111.32 * math.cos(math.radians(lat))
    project = lambda x, y, z=None: (x * scale_x, y * 111.32)
    unproject = lambda x, y, z=None: (x / scale_x, y / 111.32)
    speed = req.vessel_speed_knots * 1.852
    line = LineString([project(*p) for p in points]) if has_points else None
    distance = line.length if line is not None else 0.0
    zone = None
    arrival = None

    def result(decision, reason, path=None, error=None):
        coords = path if path is not None else (points if has_points else [])
        length = LineString([project(*p) for p in coords]).length if len(coords) > 1 else distance
        return RerouteResponse(
            decision=decision, reason=reason, hazard_arrival_hours=arrival,
            clearance_hours=req.clearance_hours, clearance_buffer_hours=req.clearance_buffer_hours,
            original_path=points if has_points else [], rerouted_path=coords,
            distance_original_km=distance, distance_rerouted_km=length,
            original_time_hours=distance / speed, rerouted_time_hours=length / speed,
            extra_time_hours=max(0, length-distance) / speed,
            extra_fuel_tons=max(0, length-distance) / speed,
            is_rerouted=decision == "reroute", exclusion_zone=zone,
            processing_time_ms=(time.time()-started)*1000, error=error)

    polygons = []
    raw_polygons = []
    for obstacle in req.obstacles:
        try:
            geom = shape(obstacle.get("geometry", obstacle))
            if geom.geom_type not in ("Polygon", "MultiPolygon") or geom.is_empty:
                raise ValueError("Expected a nonempty polygon")
            geom = transform(project, geom).buffer(0)
            if geom.is_empty:
                raise ValueError("Empty geometry")
            raw_polygons.append(geom)
            polygons.append(geom.buffer(req.safety_margin_km))
        except Exception:
            return result("unavailable", "Invalid hazard geometry: no route can be assessed.", path=[], error="Invalid hazard geometry")
    area = unary_union(polygons) if polygons else Polygon()
    # The safety margin is precautionary padding around a hazard, not the
    # hazard itself. A waypoint that merely falls within that padding (but
    # is genuinely outside the actual spill/forecast polygon) should still be
    # routable -- only a waypoint inside the real hazard is unrecoverable.
    raw_area = unary_union(raw_polygons) if raw_polygons else Polygon()
    if not area.is_empty:
        zone = mapping(transform(unproject, area))
    if not has_points:
        return result("pending", "Select a start and destination to compare arrival with spill clearance.")
    if distance == 0:
        return result("unavailable", "Start and destination must be different.", path=[], error="Identical waypoints")
    if not polygons:
        return result("unavailable", "No spill geometry is available. Detect spills before assessing a route.", path=[], error="No hazard data")
    intersection = line.intersection(area)
    if intersection.is_empty:
        return result("direct_clear", "The direct route does not cross any supplied spill or forecast region, including the safety margin.")
    # First entry, not destination ETA, determines whether the ship encounters oil.
    from shapely.ops import nearest_points
    entry = nearest_points(Point(line.coords[0]), intersection)[1]
    arrival = line.project(entry) / speed
    if req.clearance_hours is not None and arrival > req.clearance_hours + req.clearance_buffer_hours:
        return result("direct_after_clearance", f"The ship reaches the first hazard in {arrival:.2f} h, after the assumed clearance at {req.clearance_hours:.2f} h plus a {req.clearance_buffer_hours:.2f} h uncertainty buffer. No detour is needed under this scenario; confirm clearance before transit.")
    if raw_area.covers(Point(line.coords[0])) or raw_area.covers(Point(line.coords[-1])):
        return result("unavailable", "A waypoint is inside the hazard boundary and clearance before entry is not established. Move it outside the boundary.", path=[], error="Waypoint inside hazard")
    # A waypoint can legitimately sit inside the safety-margin padding while
    # still being outside the real hazard (checked above) -- carve a small
    # clearance disc around each endpoint out of the routing obstacle so the
    # visibility graph can still depart from/arrive at it, without weakening
    # avoidance anywhere else along the route.
    endpoint_clearance = unary_union([
        Point(line.coords[0]).buffer(req.safety_margin_km + 0.05),
        Point(line.coords[-1]).buffer(req.safety_margin_km + 0.05),
    ])
    routing_area = area.difference(endpoint_clearance)
    # Visibility graph directly on the real (possibly non-convex) obstacle
    # boundary -- NOT its convex hull. A convex hull silently re-fills any
    # notch (like the endpoint-clearance bite above, or a genuine gap between
    # two separate hazard clusters), which defeats both.
    parts = [p for p in (list(routing_area.geoms) if routing_area.geom_type == "MultiPolygon" else [routing_area]) if not p.is_empty]
    nodes = [line.coords[0], line.coords[-1]]
    for p in parts:
        nodes += list(p.exterior.coords[:-1])
        for interior in p.interiors:
            nodes += list(interior.coords[:-1])
    if len(nodes) > 1200:
        return result("unavailable", "Hazard geometry is too complex for this simulation.", path=[], error="Geometry limit")
    graph = [[] for _ in nodes]
    for i, a in enumerate(nodes):
        for j in range(i):
            segment = LineString([a, nodes[j]])
            if segment.relate_pattern(routing_area, "F********"):
                graph[i].append((j, segment.length))
                graph[j].append((i, segment.length))
    queue, costs, previous = [(0.0, 0)], {0: 0.0}, {}
    while queue:
        cost, node = heapq.heappop(queue)
        if node == 1:
            break
        if cost > costs[node]:
            continue
        for nxt, weight in graph[node]:
            value = cost + weight
            if value < costs.get(nxt, float("inf")):
                costs[nxt], previous[nxt] = value, node
                heapq.heappush(queue, (value, nxt))
    if 1 not in costs:
        return result("unavailable", "No spill-avoiding path could be calculated. Adjust the waypoints.", path=[], error="No route found")
    indices = [1]
    while indices[-1] != 0:
        indices.append(previous[indices[-1]])
    path = [list(unproject(*nodes[i])) for i in reversed(indices)]
    explanation = "Clearance time is unknown, so the spill remains an obstacle." if req.clearance_hours is None else f"Assumed clearance plus buffer is {req.clearance_hours + req.clearance_buffer_hours:.2f} h, which is not before entry."
    return result("reroute", f"The direct route enters a hazard in {arrival:.2f} h. {explanation} The detour avoids all supplied hazard regions and their safety margins.", path=path)
