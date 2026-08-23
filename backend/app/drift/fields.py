"""Ocean forcing: surface currents and 10 m wind, interpolated in space.

The case bundle ships a coarse field (32x32 over the bbox). Real ERA5/CMEMS
NetCDF drop in here unchanged once credentials exist; the interpolation and
everything downstream of it does not care which it is.
"""

from __future__ import annotations

import numpy as np


class ForcingField:
    """Bilinear interpolation of a steady (time-invariant) forcing field.

    Steady is a real simplification and is stated as such in the provenance.
    Over a 24 h hindcast in the northern Gulf in summer the mesoscale field is
    slowly varying, so the dominant error is the diffusivity, not the time
    dependence.
    """

    def __init__(self, lons, lats, u_current, v_current, u_wind, v_wind):
        self.lons = np.asarray(lons)
        self.lats = np.asarray(lats)
        self.u_current = np.asarray(u_current)
        self.v_current = np.asarray(v_current)
        self.u_wind = np.asarray(u_wind)
        self.v_wind = np.asarray(v_wind)

    @classmethod
    def from_bundle(cls, bundle) -> "ForcingField | None":
        f = bundle.forcing()
        if f is None:
            return None
        return cls(f["lons"], f["lats"], f["u_current"], f["v_current"],
                   f["u_wind"], f["v_wind"])

    def _interp(self, grid: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Vectorised bilinear sample of `grid` (ny, nx) at scattered points."""
        nx, ny = len(self.lons), len(self.lats)
        fx = np.interp(lon, self.lons, np.arange(nx))
        fy = np.interp(lat, self.lats, np.arange(ny))

        x0 = np.clip(np.floor(fx).astype(int), 0, nx - 2)
        y0 = np.clip(np.floor(fy).astype(int), 0, ny - 2)
        tx, ty = fx - x0, fy - y0

        return (
            grid[y0, x0] * (1 - tx) * (1 - ty)
            + grid[y0, x0 + 1] * tx * (1 - ty)
            + grid[y0 + 1, x0] * (1 - tx) * ty
            + grid[y0 + 1, x0 + 1] * tx * ty
        )

    def surface_velocity(self, lon, lat, wind_factor: float) -> tuple[np.ndarray, np.ndarray]:
        """Total surface drift velocity in m/s.

        Oil on the surface moves with the current plus a fraction of the wind.
        The 2-4% wind factor is the standard operational range; it stands in for
        the combined effect of Stokes drift and the wind-driven surface layer.
        """
        u = self._interp(self.u_current, lon, lat) + wind_factor * self._interp(self.u_wind, lon, lat)
        v = self._interp(self.v_current, lon, lat) + wind_factor * self._interp(self.v_wind, lon, lat)
        return u, v
