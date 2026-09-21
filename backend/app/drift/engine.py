"""
Stage 2 orchestration: run the ensemble and assemble the API response.

THE KEY DESIGN CHOICE. A backtrack gives position as a function of elapsed
time, but it cannot by itself say WHEN the release happened — every point along
the trajectory is a candidate origin. Something has to bound the elapsed time,
and that something is Stage 1's age estimate.

So the origin region is the union of the ensemble over the plausible age window
(4.5-19.1 h for this case), not the cloud at one arbitrary chosen hour. This is
what makes the two stages one pipeline rather than two demos: a wider age
bracket honestly produces a wider origin region.
"""

from __future__ import annotations

import time
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
from app.drift import lagrangian
from app.drift.fields import ForcingField

# Sent to the frontend for animation. The full ensemble is used for the maths;
# only a subset is drawn, since 500 dots per frame is visual noise and payload.
DRAW_PARTICLES = 220


def _provenance(stage: str, params: dict, notes: str) -> Provenance:
    return Provenance(
        model_version=config.MODEL_VERSION,
        params=params,
        generated_at=datetime.now(timezone.utc),
        inputs=["case forcing field (currents + 10 m wind)", "Stage 1 slick polygon"],
        notes=notes,
    )


def _frames_to_api(frames, rng) -> list[ParticleFrame]:
    out = []
    for t, pts in frames:
        idx = rng.choice(len(pts), min(DRAW_PARTICLES, len(pts)), replace=False)
        out.append(ParticleFrame(
            t_offset_hours=round(t, 2),
            points=[(round(float(a), 5), round(float(b), 5)) for a, b in pts[idx]],
        ))
    return out


def hindcast(bundle, slick_ring, age_hours: tuple[float, float], *,
             n_particles: int, wind_factor: float, seed: int,
             timestep_minutes: float = config.DRIFT_TIMESTEP_MINUTES,
             diffusion_m2s: float | None = None,
             wind_dir_deg: float | None = None) -> HindcastResponse:
    field = ForcingField.from_bundle(bundle)
    if field is None:
        raise RuntimeError("case bundle has no forcing field")

    if wind_dir_deg is not None:
        import math
        rad = math.radians(wind_dir_deg)
        speed = np.hypot(field.u_wind, field.v_wind)
        field.u_wind = speed * math.sin(rad)
        field.v_wind = speed * math.cos(rad)

    steps: list[ProcessingStep] = []
    rng = np.random.default_rng(seed)

    t0 = time.perf_counter()
    particles = lagrangian.seed_in_polygon(slick_ring, n_particles, rng)
    steps.append(ProcessingStep(
        name=f"seed {n_particles} particles across the slick polygon",
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        detail="seeded over the full extent, not the centroid",
    ))

    age_min, age_max = age_hours
    t0 = time.perf_counter()
    frames, _ = lagrangian.advect(
        particles, field, hours=age_max, direction=-1,
        wind_factor=wind_factor, diffusion_m2s=diffusion_m2s,
        timestep_minutes=timestep_minutes, seed=seed,
    )
    steps.append(ProcessingStep(
        name=f"backward advection {age_max:.1f} h",
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        detail=f"{timestep_minutes:.0f} min steps, "
               f"K={diffusion_m2s if diffusion_m2s is not None else 'Okubo scale-dependent'}, "
               f"wind factor {wind_factor:.0%}",
    ))

    # Pool every particle whose elapsed time falls inside the plausible age
    # window. THIS union is the origin region.
    t0 = time.perf_counter()
    pooled = np.vstack([p for t, p in frames if age_min <= -t <= age_max])

    cones: list[ConePolygon] = []
    # Every other frame: cone extraction is the dominant cost and the animation
    # does not need a polygon on every step.
    for t, pts in frames[::2]:
        for pct, frac in ((50, 0.50), (90, 0.90)):
            ring = cone_mod.containment_polygon(pts, frac)
            polygon = cone_mod.water_polygon(ring) if ring else None
            if polygon:
                cones.append(ConePolygon(
                    t_offset_hours=round(t, 2),
                    polygon=polygon,
                    percentile=pct,  # type: ignore[arg-type]
                ))

    origin_ring_90 = cone_mod.containment_polygon(pooled, 0.90)
    origin_ring_50 = cone_mod.containment_polygon(pooled, 0.50)
    for pct, ring in ((90, origin_ring_90), (50, origin_ring_50)):
        polygon = cone_mod.water_polygon(ring) if ring else None
        if polygon:
            # Marked kind="origin" rather than sharing a timestamp with the last
            # animation frame: they are different objects and the UI draws the
            # origin region persistently once the run settles.
            cones.append(ConePolygon(
                t_offset_hours=round(-age_max, 2),
                polygon=polygon,
                percentile=pct,  # type: ignore[arg-type]
                kind="origin",
            ))

    mode_lon, mode_lat = cone_mod.mode(pooled)
    radius = cone_mod.equivalent_radius_km(origin_ring_90) if origin_ring_90 else 0.0
    steps.append(ProcessingStep(
        name="containment cone extraction",
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        detail=f"origin region pooled over the {age_min:.1f}-{age_max:.1f} h age window",
    ))

    best_age = 0.5 * (age_min + age_max)
    return HindcastResponse(
        particles_timeline=_frames_to_api(frames, rng),
        cone=cones,
        origin_estimate=OriginEstimate(
            point=(round(mode_lon, 5), round(mode_lat, 5)),
            time_utc=bundle.acquired_at - timedelta(hours=best_age),
            uncertainty_radius_km=round(radius, 2),
            time_window_hours=(round(age_min, 1), round(age_max, 1)),
        ),
        processing=steps,
        provenance=_provenance(
            "hindcast",
            {
                "direction": "backward",
                "hours": age_max,
                "n_particles": n_particles,
                "wind_factor": wind_factor,
                "diffusion": diffusion_m2s if diffusion_m2s is not None else "Okubo scale-dependent",
                "timestep_minutes": timestep_minutes,
                "seed": seed,
                "age_window_hours": [age_min, age_max],
                "forcing": bundle.meta.get("forcing", {}).get("mode"),
            },
            "Stochastic Lagrangian ensemble. The origin is a containment region "
            "pooled over the age window from Stage 1, never a single point. Forcing "
            "is treated as steady over the run.",
        ),
    )


def forecast(bundle, slick_ring, hours: float, *,
             n_particles: int, wind_factor: float, seed: int,
             timestep_minutes: float = config.DRIFT_TIMESTEP_MINUTES,
             diffusion_m2s: float | None = None,
             wind_dir_deg: float | None = None) -> ForecastResponse:
    field = ForcingField.from_bundle(bundle)
    if field is None:
        raise RuntimeError("case bundle has no forcing field")

    if wind_dir_deg is not None:
        import math
        rad = math.radians(wind_dir_deg)
        speed = np.hypot(field.u_wind, field.v_wind)
        field.u_wind = speed * math.sin(rad)
        field.v_wind = speed * math.cos(rad)

    steps: list[ProcessingStep] = []
    rng = np.random.default_rng(seed)

    t0 = time.perf_counter()
    particles = lagrangian.seed_in_polygon(slick_ring, n_particles, rng)
    frames, final = lagrangian.advect(
        particles, field, hours=hours, direction=+1,
        wind_factor=wind_factor, diffusion_m2s=diffusion_m2s,
        timestep_minutes=timestep_minutes, seed=seed + 1,
    )
    steps.append(ProcessingStep(
        name=f"forward advection {hours:.0f} h",
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        detail="same engine, direction reversed",
    ))

    t0 = time.perf_counter()
    cones = []
    for t, pts in frames:
        ring = cone_mod.containment_polygon(pts, 0.90)
        polygon = cone_mod.water_polygon(ring) if ring else None
        if polygon:
            cones.append(ConePolygon(
                t_offset_hours=round(t, 2),
                polygon=polygon,
                percentile=90,
            ))
    path = [[round(float(p[:, 0].mean()), 5), round(float(p[:, 1].mean()), 5)] for _, p in frames]
    steps.append(ProcessingStep(
        name="forecast envelope + centroid track",
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
    ))

    # Coastline screen: the bbox is open ocean, and the Louisiana shore sits
    # just north of it, so we report distance to the northern boundary as a
    # proxy rather than pretending to a real coastline intersection.
    north = bundle.bbox["north"]
    lat_end = final[:, 1].mean()
    v_north = (final[:, 1].mean() - particles[:, 1].mean()) / max(hours, 1e-6)
    flags: list[ImpactFlag] = []
    if v_north > 0:
        dist_deg = north - lat_end
        eta = dist_deg / v_north
        if 0 < eta < 96:
            flags.append(ImpactFlag(
                kind="coastline",
                name="Northern boundary — Terrebonne Bay approaches",
                eta_hours=round(float(eta), 1),
                distance_km=round(float(dist_deg * 110.574), 1),
            ))

    return ForecastResponse(
        particles_timeline=_frames_to_api(frames, rng),
        cone=cones,
        centroid_path={"type": "LineString", "coordinates": path},
        impact_flags=flags,
        processing=steps,
        provenance=_provenance(
            "forecast",
            {"direction": "forward", "hours": hours, "n_particles": n_particles,
             "wind_factor": wind_factor,
             "diffusion": diffusion_m2s if diffusion_m2s is not None else "Okubo scale-dependent",
             "timestep_minutes": timestep_minutes,
             "seed": seed + 1, "forcing": bundle.meta.get("forcing", {}).get("mode")},
            "Same engine as the hindcast with the advection sign flipped. Diffusion "
            "is irreversible in both directions, so the envelope widens either way.",
        ),
    )
