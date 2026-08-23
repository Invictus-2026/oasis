import time

from fastapi import APIRouter

from app.core import fixtures
from app.core.schemas import PipelineResponse

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.get("/run", response_model=PipelineResponse)
def run() -> PipelineResponse:
    """Convenience endpoint: run every stage and return the composed result.

    Used to warm-start the dashboard so nothing spins during a live demo.
    """
    t0 = time.perf_counter()
    result = PipelineResponse(
        case=fixtures.case_meta(),
        detection=fixtures.detect_response(),
        hindcast=fixtures.hindcast_response(),
        forecast=fixtures.forecast_response(),
        attribution=fixtures.attribute_response(),
        total_duration_ms=0.0,
    )
    result.total_duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    return result
