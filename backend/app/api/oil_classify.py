"""POST /api/classify-oil — Physics-based oil spill impact assessment.

Computes evaporation rate and navigational routing recommendation from the
physical thickness (µm) of the detected oil film, based on real-world
oceanographic evaporation bands for marine spills.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.schemas import OilClassifyRequest, OilClassifyResponse, OilImpactAssessment

router = APIRouter(prefix="/api", tags=["oil-classification"])


def _evaporation_band(thickness_um: float) -> tuple[str, str, str, bool]:
    """
    Return (evaporation_label, evaporation_detail, hazard_detail, re_route_needed)
    based on oil film thickness in micrometres.

    Bands follow published SAR + oceanography literature on film thickness vs
    weathering behaviour for spills in marine environments:
      ≤ 10 µm  → very thin iridescent film → fast evaporation, no residue
      10–35 µm → thin / continuous sheen  → partial evaporation, light residue
      35–65 µm → continuous thick sheen   → partial evaporation, significant residue
      > 65 µm  → emulsified / mousse       → minimal evaporation, persistent fouling
    """
    if thickness_um <= 10:
        return (
            "Evaporates Rapidly",
            f"At {thickness_um:.1f} µm the film is extremely thin. Light fractions "
            "volatilise within hours leaving no significant residue on the ocean surface.",
            "Thin iridescent film — negligible physical obstruction. No fouling risk to vessel cooling intakes or hull.",
            False,
        )
    elif thickness_um <= 35:
        return (
            "Partially Evaporates",
            f"At {thickness_um:.1f} µm lighter fractions evaporate over 12–48 h, but "
            "heavier waxy residues remain as a surface sheen.",
            "Low fouling risk — lighter fractions dissipate, but waxy residue may accumulate on hull below waterline.",
            False,
        )
    elif thickness_um <= 65:
        return (
            "Partially Evaporates — Residue Remains",
            f"At {thickness_um:.1f} µm only ~30–50 % of the volume evaporates. "
            "The remaining heavy fractions form a persistent oily layer for several days.",
            "Moderate fouling hazard — persistent oily layer can partially obstruct engine cooling-water intakes.",
            True,
        )
    else:
        return (
            "Does Not Evaporate Significantly",
            f"At {thickness_um:.1f} µm the oil is thick enough to emulsify with seawater "
            "and form a mousse that persists for weeks, gradually weathering into tar balls.",
            "Severe fouling hazard — thick emulsified layer will clog engine cooling intakes and coat hull surfaces.",
            True,
        )


@router.post("/classify-oil", response_model=OilClassifyResponse)
def classify_oil(req: OilClassifyRequest) -> OilClassifyResponse:
    """
    Physics-based assessment of oil spill impact from film thickness.
    Returns evaporation behaviour and navigational routing recommendation.
    """
    features = {
        "contrast_dB": req.contrast_dB,
        "thickness_proxy": req.thickness_proxy,
        "area_growth_rate": req.area_growth_rate,
        "weathering_indicator": req.weathering_indicator,
        "VV_VH_ratio": req.VV_VH_ratio,
    }

    # Prefer actual physical thickness; fall back to the 0-1 proxy × 100
    thickness_um = req.thickness_um if req.thickness_um is not None else req.thickness_proxy * 100.0

    evap_label, evap_detail, hazard_detail, re_route = _evaporation_band(thickness_um)

    impact = OilImpactAssessment(
        evaporation_potential=evap_detail,
        navigational_hazard=hazard_detail,
        re_route_needed=re_route,
    )

    return OilClassifyResponse(
        predicted_type=evap_label,   # repurposed: now carries the evaporation label
        impact=impact,
        features_used=features,
        thickness_um=thickness_um,
    )
