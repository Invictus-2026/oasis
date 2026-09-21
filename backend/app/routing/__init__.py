"""Grid-based A* spill-avoidance routing.

Separate from `app.api.reroute`'s visibility-graph engine (which routes
around exact hazard polygon vertices and is what the live frontend demo
calls today). This module instead rasterises the operating area into a
navigable grid — masking land via bathymetry and no-go cells via the spill
polygon — and searches it with A*, so a route can be biased continuously by
current strength/direction rather than only blocked by hard obstacles.

Entry point: `GridRoutePlanner`. Build one per operating bounding box (does
the expensive rasterisation once), then call `.plan()` / `.replan()` as many
times as new spill geometry arrives.
"""

from app.routing.planner import GridRoutePlanner, RouteResult
from app.routing.grid import NavGrid

__all__ = ["GridRoutePlanner", "RouteResult", "NavGrid"]
