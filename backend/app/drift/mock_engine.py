"""Mock-mode drift: the real simulation engine, fed synthetic environmental data.

This replaces the old fixtures._drift() fallback, which faked particle motion
with gaussian jitter around a fixed velocity and never touched wind or current
at all — the exact "pre-generated/translated particle" pattern Phase 4 rules
out. There is now exactly one simulation (drift/simulate.py); mock mode means
running it against MockEnvironmentalProvider instead of the case bundle's
forcing field. Same advection, same Okubo diffusion, same timestep loop — the
only thing that differs is where the u/v numbers come from.

The output is adapted into the existing HindcastResponse/ForecastResponse
contract using the same cone-extraction and origin-estimate logic engine.py
uses on the real path, so the frontend's MapLibre rendering and the mock/real
switch stay invisible to the UI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from app.core import config
from app.core.schemas import (
    ConePolygon,
    ForecastResponse,
    HindcastResponse,
    ImpactFlag,
    OriginEstimate,
    ParticleFrame,
    ProcessingStep,
    Provenance,
)
from app.drift import cone as cone_mod
from app.drift import simulate
from app.environment.mock import MockEnvironmentalProvider

DRAW_PARTICLES = 220
# Mock mode has no detected slick to seed from, so a representative footprint
# stands in — sized and placed like the frozen case's own slick, not an
# arbitrary point, so the ensemble's spread is still geometry-driven rather
# than a single dot growing in place.
MOCK_SLICK_RING = [
    [-90.14, 26.89], [-90.06, 26.90], [-89.99, 26.93],
    [-89.99, 26.95], [-90.10, 26.94], [-90.14, 26.89],
]
MOCK_AGE_WINDOW = (6.0, 14.0)
MOCK_ACQUIRED_AT = datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _provenance(stage: str, params: dict, notes: str) -> Provenance:
    return Provenance(
        model_version=f"{config.MODEL_VERSION}+mock-env",
        params=params,
        generated_at=datetime.now(timezone.utc),
        inputs=["mock-synthetic environmental provider", "representative slick footprint"],
        notes=notes,
    )


def _frames_to_api(result: simulate.SimulationResult, rng: np.random.Generator) -> list[ParticleFrame]:
    out = []
    for f in result.frames:
        idx = rng.choice(len(f.positions), min(DRAW_PARTICLES, len(f.positions)), replace=False)
        out.append(ParticleFrame(
            t_offset_hours=round(f.t_offset_hours, 2),
            points=[(round(float(a), 5), round(float(b), 5)) for a, b in f.positions[idx]],
        ))
    return out


def hindcast(*, ring: list[list[float]] = MOCK_SLICK_RING, hours: float, n_particles: int, wind_factor: float, seed: int,
             timestep_minutes: float = config.DRIFT_TIMESTEP_MINUTES,
             diffusion_m2s: float | None = None,
             wind_dir_deg: float | None = None) -> HindcastResponse:
    """Same shape as engine.hindcast(), driven by simulate.run() + the mock
    provider instead of a case bundle."""
    provider = MockEnvironmentalProvider()
    if wind_dir_deg is not None:
        from app.environment.base import OverrideWindProvider
        provider = OverrideWindProvider(provider, wind_dir_deg)
    
    draw_rng = np.random.default_rng(seed)

    age_min, age_max = MOCK_AGE_WINDOW
    cfg = simulate.SimulationConfig(
        particle_count=n_particles, timestep_minutes=timestep_minutes,
        duration_hours=age_max, windage_coefficient=wind_factor,
        diffusion_coefficient_m2s=diffusion_m2s,
    )
    result = simulate.run(
        ring, provider=provider, start_time=MOCK_ACQUIRED_AT,
        direction=-1, config=cfg, seed=seed,
    )

    pooled = np.vstack([f.positions for f in result.frames if age_min <= -f.t_offset_hours <= age_max])

    cones: list[ConePolygon] = []
    for f in result.frames[::2]:
        for pct, frac in ((50, 0.50), (90, 0.90)):
            ring = cone_mod.containment_polygon(f.positions, frac)
            if ring:
                cones.append(ConePolygon(
                    t_offset_hours=round(f.t_offset_hours, 2),
                    polygon={"type": "Polygon", "coordinates": [ring]},
                    percentile=pct,  # type: ignore[arg-type]
                ))

    origin_ring_90 = cone_mod.containment_polygon(pooled, 0.90)
    origin_ring_50 = cone_mod.containment_polygon(pooled, 0.50)
    for pct, ring in ((90, origin_ring_90), (50, origin_ring_50)):
        if ring:
            cones.append(ConePolygon(
                t_offset_hours=round(-age_max, 2),
                polygon={"type": "Polygon", "coordinates": [ring]},
                percentile=pct,  # type: ignore[arg-type]
                kind="origin",
            ))

    mode_lon, mode_lat = cone_mod.mode(pooled)
    radius = cone_mod.equivalent_radius_km(origin_ring_90) if origin_ring_90 else 0.0
    best_age = 0.5 * (age_min + age_max)

    return HindcastResponse(
        particles_timeline=_frames_to_api(result, draw_rng),
        cone=cones,
        origin_estimate=OriginEstimate(
            point=(round(mode_lon, 5), round(mode_lat, 5)),
            time_utc=MOCK_ACQUIRED_AT - timedelta(hours=best_age),
            uncertainty_radius_km=round(radius, 2),
            time_window_hours=(round(age_min, 1), round(age_max, 1)),
        ),
        processing=[
            ProcessingStep(name=f"seed {n_particles} particles across a representative footprint",
                            duration_ms=0.0, detail="no detected slick available in mock mode"),
            ProcessingStep(name=f"backward simulation {age_max:.1f} h", duration_ms=0.0,
                            detail=f"{timestep_minutes:.0f} min steps, wind factor {wind_factor:.0%}"),
            ProcessingStep(name="containment cone extraction", duration_ms=0.0),
        ],
        provenance=_provenance(
            "hindcast",
            {
                "direction": "backward", "hours": age_max, "n_particles": n_particles,
                "wind_factor": wind_factor,
                "diffusion": diffusion_m2s if diffusion_m2s is not None else "Okubo scale-dependent",
                "timestep_minutes": timestep_minutes, "seed": seed,
                "age_window_hours": [age_min, age_max], "forcing": "mock-synthetic",
            },
            "MOCK MODE — real Lagrangian simulation (advection + Okubo diffusion, same equations "
            "as the live path) run against synthetic environmental data, not the case bundle. "
            "The seed footprint is a representative shape, not a detected slick.",
        ),
    )


def forecast(*, ring: list[list[float]] = MOCK_SLICK_RING, hours: float, n_particles: int, wind_factor: float, seed: int,
             timestep_minutes: float = config.DRIFT_TIMESTEP_MINUTES,
             diffusion_m2s: float | None = None,
             wind_dir_deg: float | None = None) -> ForecastResponse:
    provider = MockEnvironmentalProvider()
    if wind_dir_deg is not None:
        from app.environment.base import OverrideWindProvider
        provider = OverrideWindProvider(provider, wind_dir_deg)

    draw_rng = np.random.default_rng(seed + 1)

    cfg = simulate.SimulationConfig(
        particle_count=n_particles, timestep_minutes=timestep_minutes,
        duration_hours=hours, windage_coefficient=wind_factor,
        diffusion_coefficient_m2s=diffusion_m2s,
    )
    result = simulate.run(
        ring, provider=provider, start_time=MOCK_ACQUIRED_AT,
        direction=+1, config=cfg, seed=seed + 1,
    )

    cones = []
    for f in result.frames:
        ring = cone_mod.containment_polygon(f.positions, 0.90)
        if ring:
            cones.append(ConePolygon(
                t_offset_hours=round(f.t_offset_hours, 2),
                polygon={"type": "Polygon", "coordinates": [ring]},
                percentile=90,
            ))
    path = [[round(float(f.positions[:, 0].mean()), 5), round(float(f.positions[:, 1].mean()), 5)]
            for f in result.frames]

    seed_ring = np.asarray(ring)
    final = result.frames[-1].positions
    north = 29.00  # matches the frozen case bbox's northern edge
    lat_end = final[:, 1].mean()
    v_north = (final[:, 1].mean() - seed_ring[:, 1].mean()) / max(hours, 1e-6)
    flags: list[ImpactFlag] = []
    if v_north > 0:
        dist_deg = north - lat_end
        eta = dist_deg / v_north
        if 0 < eta < 96:
            flags.append(ImpactFlag(
                kind="coastline", name="Northern boundary — Terrebonne Bay approaches",
                eta_hours=round(float(eta), 1), distance_km=round(float(dist_deg * 110.574), 1),
            ))

    return ForecastResponse(
        particles_timeline=_frames_to_api(result, draw_rng),
        cone=cones,
        centroid_path={"type": "LineString", "coordinates": path},
        impact_flags=flags,
        processing=[
            ProcessingStep(name=f"forward simulation {hours:.0f} h", duration_ms=0.0,
                            detail="mock provider, same engine as the live path"),
            ProcessingStep(name="forecast envelope + centroid track", duration_ms=0.0),
        ],
        provenance=_provenance(
            "forecast",
            {
                "direction": "forward", "hours": hours, "n_particles": n_particles,
                "wind_factor": wind_factor,
                "diffusion": diffusion_m2s if diffusion_m2s is not None else "Okubo scale-dependent",
                "timestep_minutes": timestep_minutes, "seed": seed + 1, "forcing": "mock-synthetic",
            },
            "MOCK MODE — same simulation engine as the live forecast, driven by synthetic "
            "environmental data because no case bundle is available.",
        ),
    )
