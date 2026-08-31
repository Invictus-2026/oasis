from fastapi import APIRouter

from app.attribution import engine
from app.core import fixtures
from app.core.case_store import data_files_ready
from app.core.schemas import AttributeRequest, AttributeResponse

router = APIRouter(prefix="/api", tags=["attribution"])


@router.post("/attribute", response_model=AttributeResponse)
def attribute(req: AttributeRequest) -> AttributeResponse:
    """Stage 3 — filter AIS traffic against the estimated origin and return a
    ranked, explainable candidate list. Never an identification.

    Real ingestion + six-component scoring (Phase 6/7) when the case bundle's
    binary data files are on disk; falls back to the fixture response
    otherwise, mirroring every other endpoint's mock-mode convention.
    """
    if not data_files_ready():
        if req.origin_region and "coordinates" in req.origin_region:
            pts = req.origin_region["coordinates"][0]
            origin_pos = [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]
        else:
            origin_pos = None
        return fixtures.attribute_response(req.weights, origin=origin_pos, origin_time_utc=req.release_window_start_utc)
    return engine.reconstruct_and_score(req)
