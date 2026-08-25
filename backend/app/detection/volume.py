"""
Heuristic oil-volume estimation from a detected slick's area.

Real oil volume cannot be recovered from SAR backscatter or plain image
intensity alone -- thickness is the dominant unknown, and there is no
accepted method to invert it from a single grayscale image (this mirrors the
age-estimation caveat in age.py: attempted and bounded, not claimed as a
measurement). Rather than silently picking one thickness, this uses the same
visual-appearance thickness bands actual oil-spill responders use in the
field: the Bonn Agreement / ITOPF Oil Appearance Code, which relates how
dark/continuous an oil film looks to its typical thickness range.

    Code  Appearance                    Thickness      Litres/km^2
    1     Sheen (silvery/grey)          0.04-0.30 um   40-300
    2     Rainbow                       0.30-5.0 um    300-5,000
    3     Metallic                      5.0-50 um      5,000-50,000
    4     Discontinuous true colour     50-200 um      50,000-200,000
    5     Continuous true colour        >200 um        >200,000

(Reference: Bonn Agreement Oil Appearance Code, used operationally by ITOPF
and national spill responders for aerial volume estimation from visual
observation of oil on water.)

A detector has no human visual judgement of "how dark/continuous does this
look", so contrast_db -- how many dB a region is damped below its local
background, already computed by classical.classify() for every detected
region regardless of which detector produced it -- stands in as the proxy:
stronger damping is treated as thicker, more weathered oil; weak damping as a
thin sheen. This is a coarse, order-of-magnitude proxy, not a validated
inversion, and is reported as such in every response that uses it.
"""

from __future__ import annotations

import math

CONTRAST_DB_THIN = 2.0     # dB -> thin end of the bracket (sheen/rainbow)
CONTRAST_DB_THICK = 10.0   # dB -> thick end of the bracket (continuous true colour)
THICKNESS_UM_THIN = 0.3
THICKNESS_UM_THICK = 200.0

LITRES_PER_BARREL = 158.987


def estimate_thickness_um(contrast_db: float) -> float:
    """Interpolate log-thickness across the Bonn Agreement bracket by damping
    strength. Clipped at both ends -- this is a bracket read off a table, not
    a formula that extrapolates sensibly outside it."""
    t = (contrast_db - CONTRAST_DB_THIN) / (CONTRAST_DB_THICK - CONTRAST_DB_THIN)
    t = min(max(t, 0.0), 1.0)
    log_thin, log_thick = math.log10(THICKNESS_UM_THIN), math.log10(THICKNESS_UM_THICK)
    return float(10 ** (log_thin + t * (log_thick - log_thin)))


def estimate(area_km2: float, contrast_db: float) -> dict:
    """Volume estimate for one region, plus the assumption that produced it.

    Unit algebra: area_km2 * 1e6 = area_m2; thickness_um * 1e-6 = thickness_m;
    volume_m3 = area_m2 * thickness_m = area_km2 * thickness_um (the 1e6 and
    1e-6 cancel). Sanity check against the Bonn table itself: at 100 um over
    1 km2, this gives 100 m3 = 100,000 L/km2, inside the table's 50,000-
    200,000 L/km2 band for that thickness -- consistent by construction.
    """
    thickness_um = estimate_thickness_um(contrast_db)
    volume_m3 = area_km2 * thickness_um
    volume_liters = volume_m3 * 1000.0
    volume_barrels = volume_liters / LITRES_PER_BARREL

    return {
        "thickness_um": round(thickness_um, 2),
        "volume_m3": round(volume_m3, 1),
        "volume_liters": round(volume_liters, 0),
        "volume_barrels": round(volume_barrels, 1),
        "method_note": (
            f"Heuristic, not a calibrated measurement: thickness ({thickness_um:.1f} um) inferred "
            f"from backscatter damping ({contrast_db:.1f} dB below local background) via the Bonn "
            f"Agreement / ITOPF Oil Appearance Code bracket (0.3-200 um, sheen to continuous true "
            f"colour). Volume = area x thickness. Treat as order-of-magnitude, not precise -- real "
            f"thickness estimation needs multispectral/hyperspectral imagery or field verification."
        ),
    }
