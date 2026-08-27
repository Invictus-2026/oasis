"""Real environmental data, read from the frozen case bundle.

This is the production path today: `data/case/forcing.npz` carries a 32x32
current + 10 m wind field over the case bbox, and `ForcingField` already knows
how to interpolate it. This provider is a thin adapter over that same object,
deliberately — the drift engine's measured behaviour depends on that
interpolation, so Phase 3 reuses it rather than reimplementing it.

Two honest limitations, both reported in the data rather than hidden:

  * **Steady field.** The bundle has no time axis, so `at()` returns the same
    values for any timestamp and flags `is_steady=True`. The interface still
    takes a time so that a genuinely time-varying source (CMEMS, ERA5, INCOIS)
    drops in later without touching a single caller.
  * **No wave data.** The bundle ships none, so wave fields stay `None` rather
    than being invented.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.environment.base import EnvironmentalData, EnvironmentalDataProvider


class CaseBundleProvider(EnvironmentalDataProvider):
    """Environmental data from a loaded CaseBundle's forcing field."""

    name = "case-bundle"

    def __init__(self, bundle):
        self._bundle = bundle
        self._field = None
        if bundle is not None:
            # Imported lazily so this module stays importable when the drift
            # package's dependencies are not needed.
            from app.drift.fields import ForcingField

            self._field = ForcingField.from_bundle(bundle)

        mode = (bundle.meta.get("forcing", {}).get("mode") if bundle else None) or "unknown"
        self._mode = mode
        self._synthetic = mode == "synthetic"

    def available(self) -> bool:
        return self._field is not None

    @property
    def _source_label(self) -> str:
        case_id = self._bundle.id if self._bundle else "no-case"
        return (
            f"case bundle '{case_id}' forcing field ({self._mode}, "
            f"steady/time-invariant)"
        )

    def at(self, lon: float, lat: float, time: datetime) -> EnvironmentalData:
        if self._field is None:
            raise RuntimeError("no forcing field available; check available() first")

        f = self._field
        lon_a, lat_a = np.asarray([lon], dtype=float), np.asarray([lat], dtype=float)

        return EnvironmentalData(
            lon=lon,
            lat=lat,
            time_utc=time,
            u_current_ms=float(f._interp(f.u_current, lon_a, lat_a)[0]),
            v_current_ms=float(f._interp(f.v_current, lon_a, lat_a)[0]),
            u_wind_ms=float(f._interp(f.u_wind, lon_a, lat_a)[0]),
            v_wind_ms=float(f._interp(f.v_wind, lon_a, lat_a)[0]),
            # The bundle carries no wave field. Left as None on purpose.
            wave_height_m=None,
            wave_dir_deg=None,
            wave_period_s=None,
            source=self._source_label,
            is_synthetic=self._synthetic,
            is_steady=True,
        )

    def surface_velocity(self, lon, lat, wind_factor: float, time: datetime):
        """Vectorised override.

        Delegates straight to the ForcingField the drift engine already uses,
        so particle advection through this provider is bit-identical to
        advection through the field directly — and accepts whole arrays of
        particles in one call rather than one sample at a time.
        """
        if self._field is None:
            raise RuntimeError("no forcing field available; check available() first")
        return self._field.surface_velocity(np.asarray(lon), np.asarray(lat), wind_factor)
