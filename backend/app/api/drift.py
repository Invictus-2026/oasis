from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.api.detection import _run as run_detection
from app.core import config, fixtures
from app.core.case_store import load_case, data_files_ready
from app.core.schemas import (
    DetectionMethod,
    DriftRequest,
    ForecastResponse,
    HindcastResponse,
)
from app.drift import engine, mock_engine

router = APIRouter(prefix="/api/drift", tags=["drift"])

# Stage 1 output is where the ensemble is seeded and where the age window comes
# from, so Stage 2 always reads the real detection rather than taking a polygon
# from the client. That is what keeps the stages a pipeline.
DEFAULT_AGE_WINDOW = (4.0, 20.0)


def _slick_context(slick_id: str):
    # If binary data files are missing, use the fixture detection response
    # so drift can still be demonstrated without the full case bundle.
    if data_files_ready():
        det = run_detection(DetectionMethod.classical)
    else:
        det = fixtures.detect_response(DetectionMethod.classical)
    slick = next((s for s in det.slicks if s.id == slick_id), None) or (
        det.slicks[0] if det.slicks else None
    )
    if slick is None:
        raise HTTPException(status_code=404, detail="no slick detected to drift")
    ring = slick.polygon["coordinates"][0]
    age = (slick.age.min_hours, slick.age.max_hours) if slick.age else DEFAULT_AGE_WINDOW
    return ring, age


@lru_cache(maxsize=8)
def _hindcast(slick_id: str, n: int, wf: float, seed: int,
              ts: float = config.DRIFT_TIMESTEP_MINUTES, k: float | None = None) -> HindcastResponse:
    ring, age = _slick_context(slick_id)
    return engine.hindcast(load_case(), ring, age, n_particles=n, wind_factor=wf, seed=seed,
                            timestep_minutes=ts, diffusion_m2s=k)


@lru_cache(maxsize=8)
def _forecast(slick_id: str, hours: float, n: int, wf: float, seed: int,
              ts: float = config.DRIFT_TIMESTEP_MINUTES, k: float | None = None) -> ForecastResponse:
    ring, _ = _slick_context(slick_id)
    return engine.forecast(load_case(), ring, hours, n_particles=n, wind_factor=wf, seed=seed,
                            timestep_minutes=ts, diffusion_m2s=k)


@router.post("/hindcast", response_model=HindcastResponse)
def hindcast(req: DriftRequest) -> HindcastResponse:
    """Stage 2a — run the ensemble backward to a containment region.

    Mock mode (no case bundle on disk) runs the SAME simulation engine
    (drift/simulate.py: advection + Okubo diffusion + configurable timestep)
    against synthetic environmental data, never a translated/pre-generated
    trajectory — see drift/mock_engine.py.
    """
    if not data_files_ready():
        return mock_engine.hindcast(
            hours=req.hours, n_particles=req.n_particles, wind_factor=req.wind_factor,
            seed=req.seed, timestep_minutes=req.timestep_minutes, diffusion_m2s=req.diffusion_m2s,
        )
    return _hindcast(req.slick_id, req.n_particles, req.wind_factor, req.seed,
                      req.timestep_minutes, req.diffusion_m2s)


@router.post("/forecast", response_model=ForecastResponse)
def forecast(req: DriftRequest) -> ForecastResponse:
    """Stage 2b — the same engine forward, for response planning."""
    if not data_files_ready():
        return mock_engine.forecast(
            hours=req.hours, n_particles=req.n_particles, wind_factor=req.wind_factor,
            seed=req.seed, timestep_minutes=req.timestep_minutes, diffusion_m2s=req.diffusion_m2s,
        )
    return _forecast(req.slick_id, req.hours, req.n_particles, req.wind_factor, req.seed,
                      req.timestep_minutes, req.diffusion_m2s)
