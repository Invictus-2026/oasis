"""
Lagrangian ensemble drift.

A stochastic particle model, run backward for hindcast and forward for
forecast. Each particle steps:

    dx = (u_current + f * u_wind) * dt  +  sqrt(2 K dt) * N(0,1)

K is SCALE-DEPENDENT, from Okubo's (1971) diffusion diagram — the same law
Stage 1 uses to invert the trail width for age. A patch spreads faster the
larger it already is, because progressively bigger eddies act on it. A fixed K
under-spreads a growing cloud, which quietly overstates confidence in the
origin. Using one diffusion law across both stages also keeps them consistent:
the age estimate and the drift uncertainty rest on the same physics.

The random term is the key modelling choice. A deterministic backtrack returns
a single point and implies a precision the ocean does not support; the ensemble
spreads, and that spread IS the answer. What comes out is a probability region,
not a pin.

We implement this rather than wrapping OpenDrift deliberately: OpenDrift needs
a conda-scale install and CMEMS credentials, and this is ~100 lines that runs in
under a second. The DriftEngine seam in engine.py is where an OpenDrift adapter
would slot in unchanged.
"""

from __future__ import annotations

import math

import numpy as np

from app.drift.fields import ForcingField

KM_PER_DEG_LAT = 110.574


def km_per_deg_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def seed_in_polygon(ring: list[list[float]], n: int, rng: np.random.Generator) -> np.ndarray:
    """Scatter n particles uniformly inside a polygon by rejection sampling.

    Seeding the whole slick rather than just its centroid matters: a 26 km trail
    backtracked from its centroid alone would collapse the origin uncertainty
    that the slick's own extent implies.
    """
    poly = np.asarray(ring, dtype=float)
    lon_min, lat_min = poly.min(axis=0)
    lon_max, lat_max = poly.max(axis=0)

    out = np.empty((0, 2))
    # Rejection sampling. A thin trail has a low hit rate against its bounding
    # box, so we over-draw and cap the attempts.
    for _ in range(60):
        if len(out) >= n:
            break
        batch = np.column_stack([
            rng.uniform(lon_min, lon_max, n * 8),
            rng.uniform(lat_min, lat_max, n * 8),
        ])
        out = np.vstack([out, batch[_points_in_poly(batch, poly)]])

    if len(out) < n:
        # Degenerate polygon: fall back to jitter about the centroid so the
        # engine still produces a usable ensemble.
        c = poly.mean(axis=0)
        pad = np.column_stack([
            rng.normal(c[0], 0.01, n - len(out)),
            rng.normal(c[1], 0.01, n - len(out)),
        ])
        out = np.vstack([out, pad]) if len(out) else pad

    return out[:n]


def _points_in_poly(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Vectorised even-odd ray casting."""
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), dtype=bool)
    x1, y1 = poly[:-1, 0], poly[:-1, 1]
    x2, y2 = poly[1:, 0], poly[1:, 1]

    for a, b, c, d in zip(x1, y1, x2, y2):
        cond = ((b > y) != (d > y))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (c - a) * (y - b) / (d - b + 1e-15) + a
        inside ^= cond & (x < xint)
    return inside


def okubo_diffusivity(length_scale_m: float) -> float:
    """Horizontal eddy diffusivity in m²/s at the given scale (Okubo 1971)."""
    l_cm = max(length_scale_m, 1.0) * 100.0
    return 0.0103 * l_cm ** 1.15 * 1e-4


def advect(
    particles: np.ndarray,
    field: ForcingField,
    hours: float,
    direction: int,
    *,
    wind_factor: float = 0.03,
    diffusion_m2s: float | None = None,
    timestep_minutes: float = 15.0,
    seed: int = 42,
    frame_every: int = 4,
) -> tuple[list[tuple[float, np.ndarray]], np.ndarray]:
    """Advance the ensemble. `direction` is -1 for hindcast, +1 for forecast.

    Returns (frames, final_positions), where frames are (t_offset_hours, points)
    with t negative for a hindcast.
    """
    rng = np.random.default_rng(seed)
    dt = timestep_minutes * 60.0
    n_steps = max(1, int(round(hours * 60.0 / timestep_minutes)))

    p = particles.copy()
    frames: list[tuple[float, np.ndarray]] = [(0.0, p.copy())]

    for step in range(1, n_steps + 1):
        u, v = field.surface_velocity(p[:, 0], p[:, 1], wind_factor)

        # Diffusivity from the cloud's CURRENT size, unless one is pinned.
        if diffusion_m2s is None:
            lat0 = float(p[:, 1].mean())
            sx = float(p[:, 0].std()) * km_per_deg_lon(lat0) * 1000.0
            sy = float(p[:, 1].std()) * KM_PER_DEG_LAT * 1000.0
            k = okubo_diffusivity(4.0 * math.hypot(sx, sy))
        else:
            k = diffusion_m2s
        sigma = math.sqrt(2.0 * k * dt)     # metres per step

        # Advection is reversed for a hindcast; diffusion is not. Turbulent
        # spreading is irreversible, so running time backward still WIDENS the
        # cloud. That is why the origin comes out as a region.
        dx_m = direction * u * dt + rng.normal(0.0, sigma, len(p))
        dy_m = direction * v * dt + rng.normal(0.0, sigma, len(p))

        p[:, 0] += dx_m / 1000.0 / km_per_deg_lon_arr(p[:, 1])
        p[:, 1] += dy_m / 1000.0 / KM_PER_DEG_LAT

        if step % frame_every == 0 or step == n_steps:
            frames.append((direction * step * timestep_minutes / 60.0, p.copy()))

    return frames, p


def km_per_deg_lon_arr(lat: np.ndarray) -> np.ndarray:
    return 111.320 * np.cos(np.radians(lat))
