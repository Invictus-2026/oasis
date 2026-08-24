from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.core import fixtures
from app.core.case_store import load_case
from app.core.schemas import DetectRequest, DetectResponse, DetectionMethod
from app.detection import pipeline, unet

router = APIRouter(prefix="/api", tags=["detection"])


@lru_cache(maxsize=4)
def _run(method: DetectionMethod) -> DetectResponse:
    """The case is frozen and the detector is deterministic, so the same method
    always yields the same answer. Caching keeps a re-run instant during a live
    demo instead of re-filtering a 1024x1024 scene."""
    return pipeline.run(load_case(), method)


@router.post("/detect", response_model=DetectResponse)
def detect(req: DetectRequest) -> DetectResponse:
    """Stage 1 — detect and characterise the slick.

    Runs the real classical detector against the frozen case bundle. Falls back
    to fixtures only when the bundle has not been built.
    """
    if load_case() is None:
        return fixtures.detect_response(req.method)

    if req.method is DetectionMethod.unet and not unet.available():
        # Refusing loudly beats silently serving classical output under a
        # U-Net label.
        raise HTTPException(status_code=503, detail="U-Net weights not available; use method=classical")

    return _run(req.method)
