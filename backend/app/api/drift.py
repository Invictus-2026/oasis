import time
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.api.detection import _run as run_detection
from app.core import config, fixtures
from app.core.case_store import load_case, data_files_ready
from app.core.schemas import (
    CandidateMetrics,
    DetectionMethod,
    DriftRequest,
    ForecastResponse,
    HindcastResponse,
    OriginCandidate,
    OriginSearchRequest,
    OriginSearchResponse,
    ProcessingStep,
    Provenance,
)
from app.drift import engine, mock_engine, origin_search
from app.environment import CaseBundleProvider, get_provider
from datetime import datetime, timezone

router = APIRouter(prefix="/api/drift", tags=["drift"])

# Stage 1 output is where the ensemble is seeded and where the age window comes
# from, so Stage 2 always reads the real detection rather than taking a polygon
# from the client. That is what keeps the stages a pipeline.
DEFAULT_AGE_WINDOW = (4.0, 20.0)


def _detected_slick(slick_id: str):
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
    return slick


def _slick_context(slick_id: str):
    slick = _detected_slick(slick_id)
    ring = slick.polygon["coordinates"][0]
    age = (slick.age.min_hours, slick.age.max_hours) if slick.age else DEFAULT_AGE_WINDOW
    return ring, age


def _detection_time() -> datetime:
    bundle = load_case()
    return bundle.acquired_at if bundle is not None else datetime.now(timezone.utc)


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


@router.post("/origin-search", response_model=OriginSearchResponse)
def origin_search_route(req: OriginSearchRequest) -> OriginSearchResponse:
    """Stage 2c (Phase 5) — search candidate (release location, release time)
    pairs over the previous `max_age_hours` and rank them by running a real
    forward simulation per candidate and comparing it to the observed slick.

    Unlike /hindcast (which takes the age window as a given, from Stage 1c's
    Okubo-based estimate, and pools one backward run), this endpoint searches
    OVER release time itself and scores each candidate on how well its own
    simulated cloud reproduces the observed geometry — an optimization, not a
    single deterministic backtrack.
    """
    t0 = time.perf_counter()
    slick = _detected_slick(req.slick_id)
    detected_at = _detection_time()

    observed = origin_search.ObservedSlick(
        polygon=slick.polygon["coordinates"][0],
        detected_at=detected_at,
        area_km2=slick.geometry.area_km2,
        orientation_deg=slick.geometry.orientation_deg,
        elongation=slick.geometry.elongation,
        compactness=slick.geometry.compactness,
        length_km=slick.geometry.length_km,
    )

    bundle = load_case()
    provider = get_provider(bundle) if data_files_ready() else get_provider(None)

    cfg = origin_search.SearchConfig(
        max_age_hours=req.max_age_hours, time_step_hours=req.time_step_hours,
        particle_count=req.n_particles, timestep_minutes=req.timestep_minutes,
        windage_coefficient=req.wind_factor, diffusion_coefficient_m2s=req.diffusion_m2s,
    )
    result = origin_search.search(observed, provider=provider, config=cfg, seed=req.seed)

    candidates = [
        OriginCandidate(
            release_time_utc=c.release_time_utc,
            age_hours=round(c.age_hours, 2),
            origin=(round(c.origin_lon, 5), round(c.origin_lat, 5)),
            metrics=CandidateMetrics(**vars(c.metrics)),
            age_plausibility=c.age_plausibility,
        )
        for c in result.ranked
    ]

    return OriginSearchResponse(
        best_origin=(round(result.best.origin_lon, 5), round(result.best.origin_lat, 5)),
        region_50=result.region_50,
        region_90=result.region_90,
        estimated_release_time_utc=result.best.release_time_utc,
        estimated_age_hours=round(result.estimated_age_hours, 2),
        age_uncertainty_hours=result.age_uncertainty_hours,
        confidence=result.confidence,
        candidates=candidates,
        geojson=result.to_geojson(),
        processing=[
            ProcessingStep(
                name=f"search {len(result.candidates)} candidate release times "
                     f"(0-{req.max_age_hours:.0f}h, {req.time_step_hours:.1f}h steps)",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                detail="each candidate: backward propose + forward verify simulation",
            ),
        ],
        provenance=Provenance(
            model_version=config.MODEL_VERSION,
            params={
                "provider": provider.name,
                "max_age_hours": req.max_age_hours,
                "time_step_hours": req.time_step_hours,
                "n_candidates": len(result.candidates),
                "n_particles": req.n_particles,
                "wind_factor": req.wind_factor,
                "timestep_minutes": req.timestep_minutes,
                "diffusion_m2s": req.diffusion_m2s,
                "score_weights": origin_search.SCORE_WEIGHTS,
                "seed": req.seed,
            },
            generated_at=datetime.now(timezone.utc),
            inputs=[f"slick:{req.slick_id}", f"provider:{provider.name}"],
            notes=(
                "Origin and release time are the best-scoring candidate out of "
                f"{len(result.candidates)} searched, not a closed-form calculation. Every "
                "candidate is a real forward Lagrangian simulation compared against the "
                "observed slick on five metrics; ranking is not solely age-formula-derived. "
                "The 50%/90% regions and the age-uncertainty window are the honest range of "
                "plausible answers, not a point estimate. KNOWN BIAS: the overlap/density "
                "metrics mechanically favour shorter candidate ages, since less elapsed time "
                "means less diffusion spread and an easier-to-match tighter cloud, independent "
                "of whether the location is actually correct — see drift/origin_search.py's "
                "module docstring. The estimated age should be read as the search's best-fit "
                "answer under that known limitation, not a validated measurement."
            ),
        ),
    )
