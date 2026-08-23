from fastapi import APIRouter

from app.core import fixtures
from app.core.schemas import DetectRequest, DetectResponse

router = APIRouter(prefix="/api", tags=["detection"])


@router.post("/detect", response_model=DetectResponse)
def detect(req: DetectRequest) -> DetectResponse:
    """Stage 1 — detect and characterise the slick.

    Phase 2 replaces the fixture with app.detection.classical (and optionally
    app.detection.unet when weights are present).
    """
    return fixtures.detect_response(req.method)
