"""The environmental data seam: one normalised type, one provider interface.

Design rule this file exists to enforce: **nothing downstream imports a
provider directly.** The drift engine, the API and any future forecasting code
depend on `EnvironmentalDataProvider`, so swapping a synthetic field for CMEMS,
ERA5 or INCOIS is a resolver change rather than a rewrite.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

# A range this wide is almost always a mistake (a unit slip, a stray year), and
# materialising it would be a memory hazard rather than a useful answer.
MAX_SERIES_SAMPLES = 5000


def _bearing(u: float, v: float) -> float:
    """Direction a vector points TOWARD, degrees clockwise from north.

    Stated explicitly because the alternative meteorological convention (the
    direction wind blows FROM) is equally common and differs by 180 degrees —
    a silent sign error in any drift calculation that gets it wrong.
    """
    if u == 0.0 and v == 0.0:
        return 0.0
    return math.degrees(math.atan2(u, v)) % 360.0


class EnvironmentalData(BaseModel):
    """One environmental observation at a point in space and time.

    This is the shared normalised type every provider returns and every
    consumer reads. Units are SI throughout: velocities m/s, heights m,
    directions degrees clockwise from north.
    """

    model_config = ConfigDict(frozen=True)

    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)
    time_utc: datetime

    # -- primary fields (Phase 3 priority) --------------------------------
    u_current_ms: float = Field(description="eastward surface current component")
    v_current_ms: float = Field(description="northward surface current component")
    u_wind_ms: float = Field(description="eastward 10 m wind component")
    v_wind_ms: float = Field(description="northward 10 m wind component")

    # -- optional fields (where available) --------------------------------
    # None means "this provider has no wave data", never "the sea was flat".
    wave_height_m: float | None = Field(default=None, description="significant wave height")
    wave_dir_deg: float | None = Field(default=None, description="mean wave direction, toward")
    wave_period_s: float | None = Field(default=None, description="peak wave period")

    # -- provenance -------------------------------------------------------
    source: str = Field(default="unknown", description="which provider produced this sample")
    is_synthetic: bool = Field(default=False, description="true when values are modelled, not measured")
    is_steady: bool = Field(
        default=False,
        description="true when the provider has no time axis and returns the same field for any time",
    )

    # -- derived conveniences ---------------------------------------------
    # Computed rather than stored so they can never disagree with u/v.
    @property
    def current_speed_ms(self) -> float:
        return math.hypot(self.u_current_ms, self.v_current_ms)

    @property
    def current_dir_deg(self) -> float:
        return _bearing(self.u_current_ms, self.v_current_ms)

    @property
    def wind_speed_ms(self) -> float:
        return math.hypot(self.u_wind_ms, self.v_wind_ms)

    @property
    def wind_dir_deg(self) -> float:
        return _bearing(self.u_wind_ms, self.v_wind_ms)

    def model_dump(self, **kwargs):  # type: ignore[override]
        """Include the derived fields, so an API consumer reading JSON sees the
        same surface a Python caller sees."""
        data = super().model_dump(**kwargs)
        data.update(
            current_speed_ms=round(self.current_speed_ms, 4),
            current_dir_deg=round(self.current_dir_deg, 2),
            wind_speed_ms=round(self.wind_speed_ms, 4),
            wind_dir_deg=round(self.wind_dir_deg, 2),
        )
        return data


class EnvironmentalDataProvider(ABC):
    """Interface every environmental data source implements.

    `at()` is the only required method. `series()` and `surface_velocity()` are
    supplied here in terms of it, so a new provider needs one method to be
    fully usable by the API and by the simulation engine.
    """

    #: Human-readable identifier, surfaced in API provenance.
    name: str = "unnamed"

    @abstractmethod
    def at(self, lon: float, lat: float, time: datetime) -> EnvironmentalData:
        """Environmental conditions at one point in space and time."""

    def available(self) -> bool:
        """Whether this provider can currently serve data.

        The resolver uses this to fall back. A provider that needs credentials,
        a network call or a data file should return False rather than raise
        when those are missing.
        """
        return True

    def series(
        self,
        lon: float,
        lat: float,
        start: datetime,
        end: datetime,
        step_hours: float = 1.0,
    ) -> list[EnvironmentalData]:
        """Samples at one location across a time range, inclusive of both ends."""
        if step_hours <= 0:
            raise ValueError("step_hours must be positive")
        if end < start:
            raise ValueError("end must not precede start")

        span_hours = (end - start).total_seconds() / 3600.0
        n = int(span_hours / step_hours) + 1
        if n > MAX_SERIES_SAMPLES:
            raise ValueError(
                f"requested range would produce {n} samples, above the "
                f"{MAX_SERIES_SAMPLES} limit; widen step_hours or narrow the range"
            )

        return [self.at(lon, lat, start + timedelta(hours=i * step_hours)) for i in range(n)]

    def surface_velocity(
        self,
        lon,
        lat,
        wind_factor: float,
        time: datetime,
    ):
        """Total surface drift velocity (u, v) in m/s: current + wind_factor x wind.

        This is the method the Lagrangian engine needs, expressed once here so
        every provider inherits identical physics. Accepts either a scalar or
        an array of positions — the simulation engine calls this once per
        timestep with the ENTIRE particle ensemble, not once per particle, so
        a provider that only handled scalars would force a Python loop over
        every particle at every step.

        Providers backed by a gridded field (CaseBundleProvider) override this
        to interpolate all four components in one vectorised numpy pass rather
        than looping `.at()` per particle, which is what this default does.
        """
        import numpy as np

        lon_arr = np.atleast_1d(np.asarray(lon, dtype=float))
        lat_arr = np.atleast_1d(np.asarray(lat, dtype=float))
        u = np.empty_like(lon_arr)
        v = np.empty_like(lat_arr)
        for i, (lo, la) in enumerate(zip(lon_arr, lat_arr)):
            s = self.at(float(lo), float(la), time)
            u[i] = s.u_current_ms + wind_factor * s.u_wind_ms
            v[i] = s.v_current_ms + wind_factor * s.v_wind_ms

        if np.isscalar(lon) or (hasattr(lon, "ndim") and lon.ndim == 0):
            return float(u[0]), float(v[0])
        return u, v


class OverrideWindProvider(EnvironmentalDataProvider):
    """Wraps an existing provider, replacing the wind direction while preserving speed."""

    def __init__(self, base_provider: EnvironmentalDataProvider, wind_dir_deg: float):
        self._base = base_provider
        self._wind_dir_rad = math.radians(wind_dir_deg)
        self.name = f"{self._base.name} (wind overridden to {wind_dir_deg}°)"

    def available(self) -> bool:
        return self._base.available()

    def at(self, lon: float, lat: float, time: datetime) -> EnvironmentalData:
        d = self._base.at(lon, lat, time)
        speed = math.hypot(d.u_wind_ms, d.v_wind_ms)
        u_new = speed * math.sin(self._wind_dir_rad)
        v_new = speed * math.cos(self._wind_dir_rad)
        
        # We must use model_copy since EnvironmentalData is frozen
        return d.model_copy(update={
            "u_wind_ms": round(u_new, 4),
            "v_wind_ms": round(v_new, 4),
            "source": self.name
        })

    def surface_velocity(self, lon, lat, wind_factor: float, time: datetime):
        """Cannot simply delegate to base because we must intercept the wind."""
        # For simplicity we fall back to the per-particle loop. Vectorized
        # overriding is possible but this decorator is only for small manual tests.
        return EnvironmentalDataProvider.surface_velocity(self, lon, lat, wind_factor, time)

