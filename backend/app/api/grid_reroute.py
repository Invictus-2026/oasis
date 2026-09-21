"""Grid-based A* spill-avoidance routing endpoint.

POST /api/routing/plan    — build a route (and cache the rasterised grid)
POST /api/routing/replan  — recompute from the vessel's current position
                             against new spill geometry, reusing the cached
                             grid from a prior /plan call

This is a separate engine from POST /api/vessel/reroute (app/api/reroute.py),
which routes around exact hazard polygon vertices with a visibility graph.
This one rasterises the operating bounding box into a navigable grid — land
masked out via bathymetry, the spill (+ buffer) masked out as a replaceable
hazard layer — and searches it with A*, so a current vector field can bias
the route continuously rather than only blocking cells. See app/routing/.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException

from app.core import config
from app.core.schemas import (
    GridRoutePlanRequest,
    GridRouteReplanRequest,
    GridRouteResponse,
    GridRouteWaypoint,
)
from app.routing import GridRoutePlanner
from app.routing.astar import CostParams
from app.routing.grid import BoundingBox

router = APIRouter(prefix="/api/routing", tags=["routing"])

# Session cache: keeps a built NavGrid (the expensive rasterisation step)
# alive between a /plan call and later /replan calls for the same vessel,
# so a new drift hindcast never pays to re-mask bathymetry. In-process only
# and unbounded by design for a live-demo scope — see the size note below.
_SESSIONS: dict[str, GridRoutePlanner] = {}
_MAX_SESSIONS = 200  # demo-scale cap; evicts oldest on overflow rather than growing unbounded


def _operating_bbox() -> BoundingBox:
    b = config.CASE_BBOX
    return BoundingBox(west=b["west"], south=b["south"], east=b["east"], north=b["north"])


def _new_session_id() -> str:
    if len(_SESSIONS) >= _MAX_SESSIONS:
        _SESSIONS.pop(next(iter(_SESSIONS)))
    return uuid.uuid4().hex


def _to_response(session_id: str, result, started: float) -> GridRouteResponse:
    return GridRouteResponse(
        session_id=session_id,
        found=result.found,
        reason=result.reason,
        waypoints=[GridRouteWaypoint(lon=lon, lat=lat) for lon, lat in result.waypoints],
        distance_km=round(result.distance_km, 3),
        estimated_time_hours=round(result.estimated_time_hours, 3),
        estimated_fuel_units=round(result.estimated_fuel_units, 3),
        processing_time_ms=round((time.time() - started) * 1000, 3),
    )


@router.post("/plan", response_model=GridRouteResponse)
def plan_route(req: GridRoutePlanRequest) -> GridRouteResponse:
    started = time.time()
    bbox = _operating_bbox()

    def in_bbox(lon: float, lat: float) -> bool:
        return bbox.west <= lon <= bbox.east and bbox.south <= lat <= bbox.north

    if not in_bbox(*req.start) or not in_bbox(*req.end):
        raise HTTPException(422, "start and end must both fall within the operating area "
                                  f"({bbox.west},{bbox.south},{bbox.east},{bbox.north})")

    planner = GridRoutePlanner.build(
        bbox=bbox,
        resolution_deg=req.resolution_deg,
        depth_threshold_m=req.depth_threshold_m,
        cost_params=CostParams(
            current_penalty_weight=req.current_penalty_weight,
            vessel_speed_kmh=req.vessel_speed_knots * 1.852,
        ),
    )
    result = planner.plan(start=tuple(req.start), end=tuple(req.end), spill_polygons=req.spill_polygons)

    session_id = _new_session_id()
    _SESSIONS[session_id] = planner
    return _to_response(session_id, result, started)


@router.post("/replan", response_model=GridRouteResponse)
def replan_route(req: GridRouteReplanRequest) -> GridRouteResponse:
    started = time.time()
    planner = _SESSIONS.get(req.session_id)
    if planner is None:
        raise HTTPException(404, "unknown or expired session_id; call /plan first")

    end = tuple(req.end) if req.end is not None else None
    try:
        result = planner.replan(
            current_position=tuple(req.current_position),
            end=end,
            spill_polygons=req.spill_polygons,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    return _to_response(req.session_id, result, started)
