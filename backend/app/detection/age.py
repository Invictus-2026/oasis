"""
Heuristic spill-age estimation.

The problem statement hedges this as "age, if feasible", and the literature has
no accepted method for recovering elapsed time from imagery alone. Most
submissions will skip it. We attempt it, bound it, and state the method on
screen rather than emitting a false-precision number.

THE GEOMETRY MATTERS. An underway discharge is a line source, not a point
source: the trail's LENGTH is set by how far the vessel steamed while
discharging, and carries no age information at all. Only its WIDTH does. Fay's
classical spreading law describes an instantaneous release spreading radially
and is simply the wrong model here — applying it to the full slick area
underestimates the age by an order of magnitude.

So the width is modelled with horizontal turbulent diffusion, using Okubo's
(1971) empirical scale-dependent diffusivity from dye-release experiments:

    K = 0.0103 * L^1.15          (cm²/s, L in cm)
    sigma = sqrt(2 K t)   =>     t = sigma² / (2K)

taking the visible trail width as roughly ±2 sigma.

A second, independent proxy — backscatter damping decay — is used only to
shade the estimate within that bracket, never to set it. Confidence is
reported as "low" regardless, because the diffusivity spans a factor of a few
in any real ocean.
"""

from __future__ import annotations

import math

# Okubo scale-dependent horizontal diffusivity.
OKUBO_COEFF = 0.0103
OKUBO_EXPONENT = 1.15

# The visible trail is taken as ±2 sigma across, so sigma = width / 4.
WIDTH_TO_SIGMA = 4.0

# Ocean diffusivity is uncertain by roughly a factor of two either way even at a
# fixed scale, and that dominates the error budget.
K_UNCERTAINTY = 2.0

# Contrast bounds for the damping proxy, in dB below local background.
FRESH_CONTRAST_DB = 9.0
WEATHERED_CONTRAST_DB = 3.0


def okubo_diffusivity(length_scale_m: float) -> float:
    """Horizontal eddy diffusivity in m²/s at the given scale."""
    l_cm = max(length_scale_m, 1.0) * 100.0
    k_cm2_s = OKUBO_COEFF * l_cm ** OKUBO_EXPONENT
    return k_cm2_s * 1e-4


def estimate(area_km2: float, contrast_db: float, length_km: float | None = None) -> dict | None:
    """Bracketed age from trail width, or None if the inputs are unusable.

    `length_km` is the trail's major-axis extent. Without it the slick is
    treated as roughly circular, which is the right fallback for a blob but
    will overestimate the width — and therefore the age — for a trail.
    """
    if area_km2 <= 0:
        return None

    area_m2 = area_km2 * 1e6
    if length_km and length_km > 0:
        width_m = area_m2 / (length_km * 1000.0)
        geometry = f"trail {length_km:.1f} km long by {width_m:.0f} m wide"
    else:
        width_m = 2.0 * math.sqrt(area_m2 / math.pi)
        geometry = f"equivalent disc {width_m:.0f} m across"

    sigma = width_m / WIDTH_TO_SIGMA
    k = okubo_diffusivity(width_m)
    if k <= 0:
        return None

    t_hours = sigma ** 2 / (2.0 * k) / 3600.0
    lo = t_hours / K_UNCERTAINTY
    hi = t_hours * K_UNCERTAINTY

    # Damping decay shades within the bracket: a fresh-looking film pulls
    # toward the young end, a weathered one toward the old end.
    freshness = (contrast_db - WEATHERED_CONTRAST_DB) / (FRESH_CONTRAST_DB - WEATHERED_CONTRAST_DB)
    freshness = min(max(freshness, 0.0), 1.0)
    shift = (0.5 - freshness) * 0.30 * (hi - lo)
    lo, hi = max(0.25, lo + shift), hi + shift

    weathering = (
        "relatively fresh" if freshness > 0.6
        else "weathering" if freshness > 0.3
        else "well-weathered"
    )

    return {
        "min_hours": round(lo, 1),
        "max_hours": round(hi, 1),
        "confidence": "low",
        "method_note": (
            f"Heuristic proxy, not a calibrated measurement. Treated as a line source: the "
            f"{geometry} was laid down by a moving vessel, so its length reflects the vessel's "
            f"track and only its width carries age. Width inverted through Okubo scale-dependent "
            f"turbulent diffusion (K = {k:.2f} m²/s at this scale), bracketed by the factor-of-"
            f"{K_UNCERTAINTY:.0f} uncertainty in ocean diffusivity, then shaded by backscatter "
            f"damping of {contrast_db:.1f} dB indicating a {weathering} film."
        ),
    }
