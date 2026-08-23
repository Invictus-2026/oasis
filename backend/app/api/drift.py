from fastapi import APIRouter

from app.core import fixtures
from app.core.schemas import DriftRequest, ForecastResponse, HindcastResponse

router = APIRouter(prefix="/api/drift", tags=["drift"])


@router.post("/hindcast", response_model=HindcastResponse)
def hindcast(req: DriftRequest) -> HindcastResponse:
    """Stage 2a — run the ensemble backward to a probability cone and an
    origin estimate. Phase 3 replaces the fixture with app.drift.lagrangian.
    """
    return fixtures.hindcast_response(
        hours=req.hours, n_particles=req.n_particles, seed=req.seed, wind_factor=req.wind_factor
    )


@router.post("/forecast", response_model=ForecastResponse)
def forecast(req: DriftRequest) -> ForecastResponse:
    """Stage 2b — same engine forward, for response planning."""
    return fixtures.forecast_response(
        hours=req.hours, n_particles=req.n_particles, seed=req.seed, wind_factor=req.wind_factor
    )
