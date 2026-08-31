"""
Phase 4 — configurable Lagrangian particle simulation.

The seven required stages, explicit rather than implied:

    1. initialise particles       seed_positions()
    2. obtain environmental data  provider.at() / provider.surface_velocity()
    3. calculate movement         advection: current + windage * wind
    4. apply diffusion            stochastic term, Okubo scale-dependent by default
    5. advance time                the step loop in run()
    6. store trajectories         SimulationResult.frames
    7. return GeoJSON             SimulationResult.to_geojson()

This module depends on `EnvironmentalDataProvider` (app/environment/base.py)
and nothing more concrete — not `ForcingField`, not the case bundle, not a
file on disk. Any provider that answers `.at(lon, lat, time)` can drive a run,
which is what lets a mock run use the exact same equations as a real one; the
only thing that differs is which numbers the provider hands back.

Physics is unchanged from drift/lagrangian.py (that module still backs the
existing /api/drift/hindcast and /api/drift/forecast endpoints and is left
alone so their measured numbers do not move):

    dx = (u_current + windage * u_wind) * dt  +  sqrt(2 K dt) * N(0, 1)

K defaults to the same Okubo (1971) scale-dependent diffusivity used
throughout this project, recomputed each step from the ensemble's own spread,
unless a fixed diffusion_coefficient_m2s is configured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from pydantic import BaseModel, Field, field_validator

from app.drift.lagrangian import _points_in_poly, okubo_diffusivity
from app.environment.base import EnvironmentalDataProvider

KM_PER_DEG_LAT = 110.574


def km_per_deg_lon(lat) -> float:
    return 111.320 * np.cos(np.radians(lat))


class SimulationConfig(BaseModel):
    """Every knob Phase 4 requires to be configurable, validated at construction
    so an engine call can never silently run with a nonsensical setting."""

    particle_count: int = Field(default=500, gt=0, le=20_000)
    timestep_minutes: float = Field(default=15.0, gt=0.0, le=1440.0)
    duration_hours: float = Field(default=24.0, gt=0.0, le=24 * 30)
    windage_coefficient: float = Field(
        default=0.03, ge=0.0, le=0.2,
        description="fraction of 10m wind added to surface current; 0.02-0.04 is the defensible range",
    )
    # None means "derive from the Okubo scale-dependent law each step",
    # matching drift/lagrangian.py's existing default behaviour. A number
    # pins a fixed diffusivity instead.
    diffusion_coefficient_m2s: float | None = Field(default=None, ge=0.0)

    @field_validator("diffusion_coefficient_m2s")
    @classmethod
    def _finite(cls, v):
        if v is not None and not math.isfinite(v):
            raise ValueError("diffusion_coefficient_m2s must be finite")
        return v


@dataclass
class SimulationFrame:
    """All particle positions at one instant."""

    t_offset_hours: float
    positions: np.ndarray  # (n_particles, 2) -> [lon, lat]


@dataclass
class SimulationResult:
    frames: list[SimulationFrame]
    config: SimulationConfig
    direction: int
    provider_name: str
    is_synthetic: bool
    start_time: datetime
    particle_ids: list[int] = field(default_factory=list)

    def __post_init__(self):
        if not self.particle_ids:
            n = self.frames[0].positions.shape[0] if self.frames else 0
            self.particle_ids = list(range(n))

    def trajectories(self) -> np.ndarray:
        """(n_particles, n_frames, 2) array — the full stored path per particle."""
        return np.stack([f.positions for f in self.frames], axis=1)

    def final_positions(self) -> np.ndarray:
        return self.frames[-1].positions

    def to_geojson(self) -> dict:
        """One LineString feature per particle trajectory, plus a run-metadata
        block in `properties` so a consumer can see exactly which knobs
        produced this output without re-deriving it from the frames."""
        traj = self.trajectories()
        features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(float(lon), 6), round(float(lat), 6)] for lon, lat in path],
                },
                "properties": {
                    "particle_id": pid,
                    "start_time_utc": self.start_time.isoformat(),
                    "final_time_utc": (
                        self.start_time + timedelta(hours=self.direction * self.frames[-1].t_offset_hours)
                    ).isoformat(),
                },
            }
            for pid, path in zip(self.particle_ids, traj)
        ]
        return {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "particle_count": self.config.particle_count,
                "timestep_minutes": self.config.timestep_minutes,
                "duration_hours": self.config.duration_hours,
                "windage_coefficient": self.config.windage_coefficient,
                "diffusion_coefficient_m2s": self.config.diffusion_coefficient_m2s,
                "direction": "forward" if self.direction > 0 else "backward",
                "provider": self.provider_name,
                "is_synthetic": self.is_synthetic,
                "start_time_utc": self.start_time.isoformat(),
                "n_frames": len(self.frames),
            },
        }


def seed_positions(
    ring: list[list[float]],
    n: int,
    rng: np.random.Generator,
    mode: str = "polygon",
) -> np.ndarray:
    """Stage 1 — initialise particles.

    `mode="polygon"` scatters uniformly inside the ring by rejection sampling
    (matches lagrangian.seed_in_polygon: seeding the whole footprint, not just
    the centroid, is what lets the ensemble's spread reflect the seed
    geometry's own extent). `mode="point"` treats `ring` as a single [lon, lat]
    pair repeated n times, for point-source tests and single-origin releases.
    """
    if mode == "point":
        pt = np.asarray(ring[0], dtype=float)
        return np.tile(pt, (n, 1))

    poly = np.asarray(ring, dtype=float)
    lon_min, lat_min = poly.min(axis=0)
    lon_max, lat_max = poly.max(axis=0)

    out = np.empty((0, 2))
    for _ in range(60):
        if len(out) >= n:
            break
        batch = np.column_stack([
            rng.uniform(lon_min, lon_max, n * 8),
            rng.uniform(lat_min, lat_max, n * 8),
        ])
        out = np.vstack([out, batch[_points_in_poly(batch, poly)]])

    if len(out) < n:
        c = poly.mean(axis=0)
        pad = np.column_stack([
            rng.normal(c[0], 0.01, n - len(out)),
            rng.normal(c[1], 0.01, n - len(out)),
        ])
        out = np.vstack([out, pad]) if len(out) else pad

    return out[:n]


def _sample_velocity(
    provider: EnvironmentalDataProvider,
    lon: np.ndarray,
    lat: np.ndarray,
    time: datetime,
    windage: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Stage 2 + start of stage 3 — obtain conditions at each particle's
    CURRENT position and combine into a surface velocity.

    Providers that can vectorise (CaseBundleProvider, wrapping a gridded
    interpolator) override `surface_velocity()` for a single fast call.
    Providers that cannot fall back to `EnvironmentalDataProvider`'s default
    implementation, which loops `.at()` per particle — correct for any
    provider, just not the fast path.
    """
    u, v = provider.surface_velocity(lon, lat, windage, time)
    return np.asarray(u, dtype=float), np.asarray(v, dtype=float)


def run(
    ring: list[list[float]],
    *,
    provider: EnvironmentalDataProvider,
    start_time: datetime,
    direction: int,
    config: SimulationConfig | None = None,
    seed: int = 42,
    seed_mode: str = "polygon",
    frame_every: int = 1,
) -> SimulationResult:
    """Run the full seven-stage simulation and return the stored trajectories.

    `direction` is +1 for forward (forecast-style) and -1 for backward
    (hindcast-style) simulation — mathematically appropriate for both because
    advection simply flips sign while diffusion does not: turbulent spreading
    is irreversible, so a backward run still widens the ensemble rather than
    collapsing it, exactly as the existing hindcast engine relies on.
    """
    if direction not in (1, -1):
        raise ValueError("direction must be +1 (forward) or -1 (backward)")

    cfg = config or SimulationConfig()
    rng = np.random.default_rng(seed)

    # -- stage 1: initialise particles -------------------------------------
    p = seed_positions(ring, cfg.particle_count, rng, mode=seed_mode)

    dt_s = cfg.timestep_minutes * 60.0
    n_steps = max(1, int(round(cfg.duration_hours * 3600.0 / dt_s)))

    frames = [SimulationFrame(t_offset_hours=0.0, positions=p.copy())]
    provider_name = getattr(provider, "name", provider.__class__.__name__)
    first_sample = provider.at(float(p[0, 0]), float(p[0, 1]), start_time)
    is_synthetic = bool(first_sample.is_synthetic)

    for step in range(1, n_steps + 1):
        t_elapsed_s = step * dt_s
        current_time = start_time + timedelta(seconds=direction * t_elapsed_s)

        # -- stage 2 + 3: obtain conditions at each particle's position and
        # calculate advective movement (current + windage * wind) -----------
        u, v = _sample_velocity(provider, p[:, 0], p[:, 1], current_time, cfg.windage_coefficient)

        # -- stage 4: apply diffusion -----------------------------------
        if cfg.diffusion_coefficient_m2s is None:
            lat0 = float(p[:, 1].mean())
            sx = float(p[:, 0].std()) * km_per_deg_lon(lat0) * 1000.0
            sy = float(p[:, 1].std()) * KM_PER_DEG_LAT * 1000.0
            k = okubo_diffusivity(4.0 * math.hypot(sx, sy))
        else:
            k = cfg.diffusion_coefficient_m2s
        sigma_m = math.sqrt(2.0 * k * dt_s)

        dx_m = direction * u * dt_s + rng.normal(0.0, sigma_m, len(p))
        dy_m = direction * v * dt_s + rng.normal(0.0, sigma_m, len(p))

        # -- stage 5: advance time (position update for this step) -------
        p = p.copy()
        p[:, 0] += dx_m / 1000.0 / km_per_deg_lon(p[:, 1])
        p[:, 1] += dy_m / 1000.0 / KM_PER_DEG_LAT

        # -- stage 6: store trajectory ------------------------------------
        if step % frame_every == 0 or step == n_steps:
            frames.append(SimulationFrame(
                t_offset_hours=direction * t_elapsed_s / 3600.0,
                positions=p.copy(),
            ))

    return SimulationResult(
        frames=frames,
        config=cfg,
        direction=direction,
        provider_name=provider_name,
        is_synthetic=is_synthetic,
        start_time=start_time,
    )
    # -- stage 7: return GeoJSON-compatible output -> SimulationResult.to_geojson()
