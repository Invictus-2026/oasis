from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.api.detection import _run as run_detection
from app.core import fixtures
from app.core.case_store import load_case
from app.core.schemas import (
    DetectionMethod,
    DriftRequest,
    ForecastResponse,
    HindcastResponse,
)
from app.drift import engine

router = APIRouter(prefix="/api/drift", tags=["drift"])

# Stage 1 output is where the ensemble is seeded and where the age window comes
# from, so Stage 2 always reads the real detection rather than taking a polygon
# from the client. That is what keeps the stages a pipeline.
DEFAULT_AGE_WINDOW = (4.0, 20.0)


def _slick_context(slick_id: str):
    det = run_detection(DetectionMethod.classical)
    slick = next((s for s in det.slicks if s.id == slick_id), None) or (
        det.slicks[0] if det.slicks else None
    )
    if slick is None:
        raise HTTPException(status_code=404, detail="no slick detected to drift")
    ring = slick.polygon["coordinates"][0]
    age = (slick.age.min_hours, slick.age.max_hours) if slick.age else DEFAULT_AGE_WINDOW
    return ring, age


@lru_cache(maxsize=8)
def _hindcast(slick_id: str, n: int, wf: float, seed: int) -> HindcastResponse:
    ring, age = _slick_context(slick_id)
    return engine.hindcast(load_case(), ring, age, n_particles=n, wind_factor=wf, seed=seed)


@lru_cache(maxsize=8)
def _forecast(slick_id: str, hours: float, n: int, wf: float, seed: int) -> ForecastResponse:
    ring, _ = _slick_context(slick_id)
    return engine.forecast(load_case(), ring, hours, n_particles=n, wind_factor=wf, seed=seed)


@router.post("/hindcast", response_model=HindcastResponse)
def hindcast(req: DriftRequest) -> HindcastResponse:
    """Stage 2a — run the ensemble backward to a containment region.

    The run length and the origin window come from Stage 1's age estimate, not
    from `hours`: a backtrack alone cannot say when the release happened, so
    something must bound the elapsed time.
    """
    if load_case() is None:
        return fixtures.hindcast_response(req.hours, req.n_particles, req.seed, req.wind_factor)
    return _hindcast(req.slick_id, req.n_particles, req.wind_factor, req.seed)


@router.post("/forecast", response_model=ForecastResponse)
def forecast(req: DriftRequest) -> ForecastResponse:
    """Stage 2b — the same engine forward, for response planning."""
    if load_case() is None:
        return fixtures.forecast_response(req.hours, req.n_particles, req.seed, req.wind_factor)
    return _forecast(req.slick_id, req.hours, req.n_particles, req.wind_factor, req.seed)
