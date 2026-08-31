import time
from fastapi import APIRouter
from app.core.schemas import RerouteRequest, RerouteResponse
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
from shapely.ops import unary_union
import numpy as np

router = APIRouter()

KM_PER_DEG = 111.32

def create_polygon(geojson: dict):
    # Extracts the coordinates from a GeoJSON dict and creates a shapely Polygon or MultiPolygon
    geom = geojson
    if geojson.get("type") == "Feature":
        geom = geojson.get("geometry", {})
        
    if geom.get("type") == "Polygon":
        return Polygon(geom["coordinates"][0])
    elif geom.get("type") == "MultiPolygon":
        polys = [Polygon(p[0]) for p in geom["coordinates"]]
        return MultiPolygon(polys)
    return Polygon()

@router.post("/api/vessel/reroute", response_model=RerouteResponse)
def reroute_vessel(req: RerouteRequest):
    t0 = time.time()
    
    has_points = req.start_point is not None and req.end_point is not None
    if has_points:
        start_pt = Point(req.start_point[0], req.start_point[1])
        end_pt = Point(req.end_point[0], req.end_point[1])
        original_line = LineString([start_pt, end_pt])
        # Calculate original distance in km
        dist_deg = start_pt.distance(end_pt)
        distance_orig_km = dist_deg * KM_PER_DEG
    else:
        start_pt, end_pt, original_line = None, None, None
        distance_orig_km = 0.0
    
    # Process obstacles
    polys = []
    for obs in req.obstacles:
        try:
            poly = create_polygon(obs)
            if not poly.is_empty:
                # Buffer(0) is a well-known trick to clean up invalid self-intersecting geometries
                cleaned_poly = poly.buffer(0)
                polys.append(cleaned_poly)
        except Exception:
            pass
            
    SPEED_KMH = 27.78  # 15 knots
    original_time = distance_orig_km / SPEED_KMH

    if not polys:
        # No valid obstacles
        return RerouteResponse(
            original_path=[req.start_point, req.end_point] if has_points else [],
            rerouted_path=[req.start_point, req.end_point] if has_points else [],
            distance_original_km=distance_orig_km,
            distance_rerouted_km=distance_orig_km,
            original_time_hours=original_time,
            rerouted_time_hours=original_time,
            extra_time_hours=0.0,
            extra_fuel_tons=0.0,
            is_rerouted=False,
            processing_time_ms=(time.time() - t0) * 1000
        )
        
    combined_obstacle = unary_union(polys)
    
    # Convert safety margin to degrees (approximate)
    margin_deg = req.safety_margin_km / KM_PER_DEG
    
    # Group into connected clusters and convex_hull them individually!
    # This prevents creating a giant 100km barrier across unrelated distant spills.
    base_area = combined_obstacle.buffer(margin_deg).simplify(0.005, preserve_topology=True)
    if base_area.geom_type == 'MultiPolygon':
        safe_area = MultiPolygon([geom.convex_hull for geom in base_area.geoms])
    else:
        safe_area = base_area.convex_hull
    
    from shapely.geometry import mapping
    exclusion_geojson = mapping(safe_area)
    
    if not has_points:
        return RerouteResponse(
            original_path=[],
            rerouted_path=[],
            distance_original_km=0.0,
            distance_rerouted_km=0.0,
            original_time_hours=0.0,
            rerouted_time_hours=0.0,
            extra_time_hours=0.0,
            extra_fuel_tons=0.0,
            is_rerouted=False,
            exclusion_zone=exclusion_geojson,
            processing_time_ms=(time.time() - t0) * 1000
        )

    if safe_area.contains(start_pt) or safe_area.contains(end_pt):
        return RerouteResponse(
            original_path=[req.start_point, req.end_point],
            rerouted_path=[req.start_point, req.end_point],
            distance_original_km=distance_orig_km,
            distance_rerouted_km=distance_orig_km,
            original_time_hours=original_time,
            rerouted_time_hours=original_time,
            extra_time_hours=0.0,
            extra_fuel_tons=0.0,
            is_rerouted=False,
            exclusion_zone=exclusion_geojson,
            processing_time_ms=(time.time() - t0) * 1000,
            error="Selected point is inside the hazard barrier."
        )

    # Check if original path intersects the safe area
    if not original_line.intersects(safe_area):
        return RerouteResponse(
            original_path=[req.start_point, req.end_point],
            rerouted_path=[req.start_point, req.end_point],
            distance_original_km=distance_orig_km,
            distance_rerouted_km=distance_orig_km,
            original_time_hours=original_time,
            rerouted_time_hours=original_time,
            extra_time_hours=0.0,
            extra_fuel_tons=0.0,
            is_rerouted=False,
            exclusion_zone=exclusion_geojson,
            processing_time_ms=(time.time() - t0) * 1000
        )
        
    # Extract the actual polygon(s) we intersect to avoid MultiPolygon exterior errors
    if safe_area.geom_type == 'MultiPolygon':
        intersected_polys = [p for p in safe_area.geoms if original_line.intersects(p)]
        if len(intersected_polys) > 1:
            routing_poly = unary_union(intersected_polys).convex_hull
        elif len(intersected_polys) == 1:
            routing_poly = intersected_polys[0]
        else:
            routing_poly = safe_area.convex_hull
    else:
        routing_poly = safe_area
        
    # Simple routing algorithm: route along the boundary of the safe area
    # We find the intersection of the line with the boundary
    try:
        boundary = routing_poly.exterior
        intersection = boundary.intersection(original_line)
        
        # If intersection is MultiPoint, get first and last
        if intersection.geom_type == 'MultiPoint':
            pts = list(intersection.geoms)
        elif intersection.geom_type == 'Point':
            pts = [intersection, intersection]
        elif intersection.geom_type == 'LineString':
            pts = [Point(intersection.coords[0]), Point(intersection.coords[-1])]
        elif intersection.geom_type == 'GeometryCollection':
            # Extract all points from the collection
            pts = []
            for geom in intersection.geoms:
                if geom.geom_type == 'Point':
                    pts.append(geom)
                elif geom.geom_type == 'LineString':
                    pts.append(Point(geom.coords[0]))
                    pts.append(Point(geom.coords[-1]))
        else:
            # Fallback
            pts = []
            
        if len(pts) >= 2:
            # Sort by distance from start
            pts = sorted(pts, key=lambda p: start_pt.distance(p))
            pt1 = pts[0]
            pt2 = pts[-1]
            
            # Find the path along the boundary from pt1 to pt2
            # Project points onto the boundary to get their distances along it
            from shapely.ops import substring
            
            d1 = boundary.project(pt1)
            d2 = boundary.project(pt2)
            
            # Substring needs a LineString, boundary is a LinearRing
            boundary_line = LineString(boundary.coords)
            
            # Ensure d1 is the smaller distance to simplify wrapping math
            is_swapped = False
            if d1 > d2:
                d1, d2 = d2, d1
                is_swapped = True

            # Path 1: Forward from d1 to d2
            path1 = substring(boundary_line, d1, d2)
            
            # Path 2: Backward from d1 to 0, then length to d2 (wrapping around the origin)
            part1 = substring(boundary_line, d1, 0)
            part2 = substring(boundary_line, boundary_line.length, d2)
            path2_coords = list(part1.coords) + list(part2.coords)[1:]
            path2 = LineString(path2_coords)
            
            # Calculate lengths to find shortest route
            if path1.length < path2.length:
                best_detour = list(path1.coords)
            else:
                best_detour = list(path2.coords)
                
            # If we swapped d1 and d2 earlier, the shortest path is currently running from pt2 to pt1,
            # so we must reverse it to run from pt1 to pt2.
            if is_swapped:
                best_detour.reverse()
                
            rerouted_coords = [(req.start_point[0], req.start_point[1])] + best_detour + [(req.end_point[0], req.end_point[1])]
            
            # Smooth the detour using Chaikin's corner cutting algorithm (2 iterations)
            for _ in range(2):
                if len(rerouted_coords) < 3:
                    break
                smoothed = [rerouted_coords[0]]
                for i in range(len(rerouted_coords) - 1):
                    p1 = rerouted_coords[i]
                    p2 = rerouted_coords[i+1]
                    q = (0.75 * p1[0] + 0.25 * p2[0], 0.75 * p1[1] + 0.25 * p2[1])
                    r = (0.25 * p1[0] + 0.75 * p2[0], 0.25 * p1[1] + 0.75 * p2[1])
                    smoothed.extend([q, r])
                smoothed.append(rerouted_coords[-1])
                rerouted_coords = smoothed
                
        else:
            # Fallback if intersection logic fails: just route to centroid and offset
            centroid = safe_area.centroid
            offset_pt = Point(centroid.x + margin_deg*2, centroid.y + margin_deg*2)
            rerouted_coords = [
                (req.start_point[0], req.start_point[1]),
                (offset_pt.x, offset_pt.y),
                (req.end_point[0], req.end_point[1])
            ]
            
    except Exception as e:
        print(f"Routing error: {e}")
        rerouted_coords = [
            (req.start_point[0], req.start_point[1]),
            (req.end_point[0], req.end_point[1])
        ]
        
    rerouted_line = LineString(rerouted_coords)
    distance_rerouted_km = rerouted_line.length * KM_PER_DEG
    
    SPEED_KMH = 27.78  # 15 knots
    FUEL_TONS_PER_HOUR = 1.0
    
    original_time = distance_orig_km / SPEED_KMH
    rerouted_time = distance_rerouted_km / SPEED_KMH
    
    return RerouteResponse(
        original_path=[req.start_point, req.end_point],
        rerouted_path=[list(c) for c in rerouted_coords],
        distance_original_km=distance_orig_km,
        distance_rerouted_km=distance_rerouted_km,
        original_time_hours=original_time,
        rerouted_time_hours=rerouted_time,
        extra_time_hours=rerouted_time - original_time,
        extra_fuel_tons=(rerouted_time - original_time) * FUEL_TONS_PER_HOUR,
        is_rerouted=True,
        exclusion_zone=exclusion_geojson,
        processing_time_ms=(time.time() - t0) * 1000
    )
