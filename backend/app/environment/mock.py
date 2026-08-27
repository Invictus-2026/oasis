"""Synthetic environmental data — the always-available fallback.

Mirrors `case_store`'s existing "never fail, fall back" philosophy: when no
real forcing is on disk and no external feed is reachable, the system still
answers, and every sample it returns is stamped `is_synthetic=True` so the
distinction can never be lost downstream.

The field is analytic and deterministic, not random: the same query always
returns the same answer, so a drift run over mock data is still reproducible.
It varies smoothly in space and time because a constant field would make the
fallback useless for exercising anything that consumes it.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.environment.base import EnvironmentalData, EnvironmentalDataProvider

# A slow, broadly eastward drift with a gentle mesoscale meander, and a wind
# with a diurnal component. Magnitudes chosen to sit in the middle of what the
# northern Gulf actually does in summer, which is also the regime the frozen
# case study represents.
BASE_CURRENT_MS = (0.11, 0.08)
BASE_WIND_MS = (3.6, 2.4)

_EPOCH = datetime(2023, 1, 1, tzinfo=timezone.utc)


class MockEnvironmentalProvider(EnvironmentalDataProvider):
    """Analytic synthetic field. Always available, always labelled synthetic."""

    name = "mock-synthetic"

    def available(self) -> bool:
        # The entire point of this provider: it is the thing that cannot fail.
        return True

    def at(self, lon: float, lat: float, time: datetime) -> EnvironmentalData:
        if time.tzinfo is None:
            time = time.replace(tzinfo=timezone.utc)
        t_hours = (time - _EPOCH).total_seconds() / 3600.0

        # Spatial meander: a smooth eddy-like rotation, wavelength ~1 degree.
        sx, sy = math.sin(lon * 6.0), math.cos(lat * 6.0)
        # Temporal: a semi-diurnal tidal-ish signal on the current and a
        # diurnal cycle on the wind.
        tide = math.sin(2 * math.pi * t_hours / 12.42)   # M2 period
        diurnal = math.sin(2 * math.pi * t_hours / 24.0)

        u_current = BASE_CURRENT_MS[0] + 0.06 * sy + 0.04 * tide
        v_current = BASE_CURRENT_MS[1] + 0.06 * sx - 0.03 * tide

        u_wind = BASE_WIND_MS[0] + 1.2 * diurnal + 0.5 * sx
        v_wind = BASE_WIND_MS[1] + 0.9 * diurnal + 0.5 * sy

        # Waves are modelled from the wind rather than left None, since this
        # provider is explicitly synthetic end to end. A rough fully-developed
        # sea relation is enough for a fallback; it is not a wave model.
        wind_speed = math.hypot(u_wind, v_wind)
        wave_height = round(0.025 * wind_speed ** 2, 3)

        return EnvironmentalData(
            lon=lon,
            lat=lat,
            time_utc=time,
            u_current_ms=round(u_current, 4),
            v_current_ms=round(v_current, 4),
            u_wind_ms=round(u_wind, 4),
            v_wind_ms=round(v_wind, 4),
            wave_height_m=wave_height,
            wave_dir_deg=round(math.degrees(math.atan2(u_wind, v_wind)) % 360.0, 2),
            wave_period_s=round(2.5 + 0.35 * wind_speed, 2),
            source="synthetic analytic field (mock provider — not measured data)",
            is_synthetic=True,
            # It does vary with time, so this is genuinely not a steady field.
            is_steady=False,
        )
