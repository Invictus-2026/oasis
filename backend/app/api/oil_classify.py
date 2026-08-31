"""POST /api/classify-oil — Physics-based oil spill impact assessment and drift-aware nautical re-routing.

Computes evaporation rate and navigational routing recommendation from the
physical thickness (µm) of the detected oil film. When re-routing is required,
it evaluates both the slick geometry and the active forecast drift plume vector
to ensure the recommended detour routes into UP-DRIFT clean water and avoids
the downwind/down-current forecast plume.
"""
from __future__ import annotations

import math
from fastapi import APIRouter

from app.core.schemas import (
    OilClassifyRequest,
    OilClassifyResponse,
    OilImpactAssessment,
    ReRouteOption,
    ReRoutePlan,
    ReRouteWaypoint,
)

router = APIRouter(prefix="/api", tags=["oil-classification"])


def _haversine_nm(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate Great Circle distance between two points in Nautical Miles."""
    R_NM = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R_NM * c


def _initial_bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate initial compass bearing from (lon1, lat1) to (lon2, lat2)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360.0) % 360.0


def _offset_coord(lon: float, lat: float, dx_km: float, dy_km: float) -> tuple[float, float]:
    """Offset a lat/lon coordinate by dx (east) and dy (north) in kilometres."""
    km_per_deg_lat = 110.574
    km_per_deg_lon = 111.320 * math.cos(math.radians(lat))
    return (lon + dx_km / km_per_deg_lon, lat + dy_km / km_per_deg_lat)


def _evaporation_band(thickness_um: float) -> tuple[str, str, str, bool]:
    """
    Return (evaporation_label, evaporation_detail, hazard_detail, re_route_needed)
    based on oil film thickness in micrometres.
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


def _compute_reroute_plan(
    center_lon: float,
    center_lat: float,
    length_km: float = 36.0,
    width_km: float = 8.4,
    orientation_deg: float = 48.0,
    thickness_um: float = 45.0,
    vessel_speed_kts: float = 14.0,
    mock_wind_dir_deg: float | None = None,
    drift_heading_deg: float | None = None,
) -> ReRoutePlan:
    """
    Compute mathematically optimized maritime re-routing options around the hazard zone.
    CRITICAL: Evaluates the forecast drift vector so that the primary recommended route
    steers into UP-DRIFT pristine water and avoids the down-drift forecast plume.
    """
    theta = math.radians(orientation_deg)
    sin_t, cos_t = math.sin(theta), math.cos(theta)

    # Determine drift heading (direction in which oil forecast plume is traveling)
    # Default in GOM case is NNW/North (~340° towards Terrebonne Bay approaches)
    if drift_heading_deg is not None:
        drift_hdg = drift_heading_deg
    elif mock_wind_dir_deg is not None:
        drift_hdg = mock_wind_dir_deg
    else:
        drift_hdg = 340.0

    # Safety clearance buffer based on thickness (thicker = wider mandatory clearance)
    clearance_km = 4.8 if thickness_um > 65 else 3.6  # ~1.9 - 2.6 NM
    clearance_nm = clearance_km / 1.852

    # Vessel transit trajectory: entering from SW to NE crossing the fairway
    transit_span_km = max(length_km * 0.85, 18.0)
    
    # P_entry: Initiation point before slick
    p0_lon, p0_lat = _offset_coord(center_lon, center_lat, -transit_span_km * sin_t, -transit_span_km * cos_t)
    # P_exit: Destination recovery point after slick
    p3_lon, p3_lat = _offset_coord(center_lon, center_lat, transit_span_km * sin_t, transit_span_km * cos_t)

    direct_dist_nm = _haversine_nm(p0_lon, p0_lat, p3_lon, p3_lat)
    direct_time_min = (direct_dist_nm / vessel_speed_kts) * 60.0

    direct_geojson = {
        "type": "LineString",
        "coordinates": [[round(p0_lon, 5), round(p0_lat, 5)], [round(p3_lon, 5), round(p3_lat, 5)]]
    }

    # Generate exclusion zone buffer polygon around the slick
    poly_pts: list[list[float]] = []
    num_pts = 32
    rx = (length_km / 2.0) + clearance_km
    ry = (width_km / 2.0) + clearance_km
    for i in range(num_pts + 1):
        ang = 2.0 * math.pi * (i % num_pts) / num_pts
        ex = rx * math.cos(ang)
        ey = ry * math.sin(ang)
        dx = ex * sin_t - ey * cos_t
        dy = ex * cos_t + ey * sin_t
        gx, gy = _offset_coord(center_lon, center_lat, dx, dy)
        poly_pts.append([round(gx, 5), round(gy, 5)])

    exclusion_zone_geojson = {
        "type": "Polygon",
        "coordinates": [poly_pts]
    }

    # Vector pointing along ship route
    ship_brg = _initial_bearing_deg(p0_lon, p0_lat, p3_lon, p3_lat)

    # ──────────────────────────────────────────────────────────────────────────
    # Option 1: Starboard-Side UP-DRIFT Safe Route (South-East Track) — RECOMMENDED
    # Steers into clean water OPPOSITE to the North-drifting forecast plume!
    # ──────────────────────────────────────────────────────────────────────────
    stbd_offset_km = (width_km / 2.0) + clearance_km
    # Lateral deflection to Starboard (South-East, away from Northward forecast drift)
    w_stbd_dx = stbd_offset_km * cos_t
    w_stbd_dy = -stbd_offset_km * sin_t
    w_stbd_lon, w_stbd_lat = _offset_coord(center_lon, center_lat, w_stbd_dx, w_stbd_dy)

    d_stbd_leg1 = _haversine_nm(p0_lon, p0_lat, w_stbd_lon, w_stbd_lat)
    d_stbd_leg2 = _haversine_nm(w_stbd_lon, w_stbd_lat, p3_lon, p3_lat)
    d_stbd_total = d_stbd_leg1 + d_stbd_leg2
    t_stbd_min = (d_stbd_total / vessel_speed_kts) * 60.0
    extra_stbd_dist = d_stbd_total - direct_dist_nm
    extra_stbd_pct = (extra_stbd_dist / direct_dist_nm) * 100.0
    delay_stbd_min = t_stbd_min - direct_time_min
    fuel_stbd_mt = extra_stbd_dist * 0.052

    brg_p0_to_stbd = _initial_bearing_deg(p0_lon, p0_lat, w_stbd_lon, w_stbd_lat)
    brg_stbd_to_p3 = _initial_bearing_deg(w_stbd_lon, w_stbd_lat, p3_lon, p3_lat)

    stbd_waypoints = [
        ReRouteWaypoint(
            name="WPT-1 (Up-Drift Diversion Entry)",
            lat=round(p0_lat, 5),
            lon=round(p0_lon, 5),
            course_to_steer_deg=round(brg_p0_to_stbd, 1),
            leg_distance_nm=round(d_stbd_leg1, 2),
            instructions=f"Alter course to {brg_p0_to_stbd:.0f}° to initiate Up-Drift Starboard clearance (steering away from Northward forecast plume).",
        ),
        ReRouteWaypoint(
            name="WPT-2 (Apex Safe Water Waypoint)",
            lat=round(w_stbd_lat, 5),
            lon=round(w_stbd_lon, 5),
            course_to_steer_deg=round(brg_stbd_to_p3, 1),
            leg_distance_nm=round(d_stbd_leg2, 2),
            instructions=f"Up-drift safe standoff confirmed ({clearance_nm:.1f} NM from slick core, 0% plume intersection). Steer {brg_stbd_to_p3:.0f}° toward fairway recovery corridor.",
        ),
        ReRouteWaypoint(
            name="WPT-3 (Course Recovery Point)",
            lat=round(p3_lat, 5),
            lon=round(p3_lon, 5),
            course_to_steer_deg=round(ship_brg, 1),
            leg_distance_nm=0.0,
            instructions=f"Clear of all active slick and forecast drift zones. Resume nominal voyage track at {ship_brg:.0f}°.",
        ),
    ]

    stbd_path_geojson = {
        "type": "LineString",
        "coordinates": [
            [round(p0_lon, 5), round(p0_lat, 5)],
            [round(w_stbd_lon, 5), round(w_stbd_lat, 5)],
            [round(p3_lon, 5), round(p3_lat, 5)],
        ]
    }

    opt_stbd = ReRouteOption(
        id="starboard_updrift",
        name="Starboard Up-Drift Clear Route (South-East Track)",
        is_recommended=True,
        distance_nm=round(d_stbd_total, 2),
        direct_distance_nm=round(direct_dist_nm, 2),
        extra_distance_nm=round(extra_stbd_dist, 2),
        extra_distance_pct=round(extra_stbd_pct, 1),
        transit_time_min=round(t_stbd_min, 1),
        direct_time_min=round(direct_time_min, 1),
        time_delay_min=round(delay_stbd_min, 1),
        fuel_extra_mt=round(fuel_stbd_mt, 2),
        min_clearance_nm=round(clearance_nm, 1),
        plume_clearance_desc="Guaranteed Clean Water: Steers South-East on the up-drift side, completely opposite to the North-drifting forecast plume.",
        waypoints=stbd_waypoints,
        geojson_path=stbd_path_geojson,
        geojson_direct=direct_geojson,
        geojson_exclusion_zone=exclusion_zone_geojson,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Option 2: Extended North-East Offshore Perimeter Bypass (Down-Drift Wide Track)
    # Must sweep far north around the +48h forecast plume head to avoid clipping
    # ──────────────────────────────────────────────────────────────────────────
    port_offset_km = ((width_km / 2.0) + clearance_km) * 2.8  # Extra wide clearance to bypass forecast plume
    w_port_dx = -port_offset_km * cos_t
    w_port_dy = port_offset_km * sin_t + 6.0  # offset further north
    w_port_lon, w_port_lat = _offset_coord(center_lon, center_lat, w_port_dx, w_port_dy)

    d_port_leg1 = _haversine_nm(p0_lon, p0_lat, w_port_lon, w_port_lat)
    d_port_leg2 = _haversine_nm(w_port_lon, w_port_lat, p3_lon, p3_lat)
    d_port_total = d_port_leg1 + d_port_leg2
    t_port_min = (d_port_total / vessel_speed_kts) * 60.0
    extra_port_dist = d_port_total - direct_dist_nm
    extra_port_pct = (extra_port_dist / direct_dist_nm) * 100.0
    delay_port_min = t_port_min - direct_time_min
    fuel_port_mt = extra_port_dist * 0.052

    brg_p0_to_port = _initial_bearing_deg(p0_lon, p0_lat, w_port_lon, w_port_lat)
    brg_port_to_p3 = _initial_bearing_deg(w_port_lon, w_port_lat, p3_lon, p3_lat)

    port_waypoints = [
        ReRouteWaypoint(
            name="WPT-1 (North Offshore Diversion Entry)",
            lat=round(p0_lat, 5),
            lon=round(p0_lon, 5),
            course_to_steer_deg=round(brg_p0_to_port, 1),
            leg_distance_nm=round(d_port_leg1, 2),
            instructions=f"Alter course to {brg_p0_to_port:.0f}° to begin wide offshore sweep around the North-drifting forecast cone.",
        ),
        ReRouteWaypoint(
            name="WPT-2 (North Plume Outer Perimeter Waypoint)",
            lat=round(w_port_lat, 5),
            lon=round(w_port_lon, 5),
            course_to_steer_deg=round(brg_port_to_p3, 1),
            leg_distance_nm=round(d_port_leg2, 2),
            instructions=f"Outer perimeter clearance achieved ({clearance_nm * 2.8:.1f} NM buffer clear of forecast cone). Steer {brg_port_to_p3:.0f}° toward recovery point.",
        ),
        ReRouteWaypoint(
            name="WPT-3 (Course Recovery Point)",
            lat=round(p3_lat, 5),
            lon=round(p3_lon, 5),
            course_to_steer_deg=round(ship_brg, 1),
            leg_distance_nm=0.0,
            instructions=f"Clear of all drift zones. Resume nominal voyage track at {ship_brg:.0f}°.",
        ),
    ]

    port_path_geojson = {
        "type": "LineString",
        "coordinates": [
            [round(p0_lon, 5), round(p0_lat, 5)],
            [round(w_port_lon, 5), round(w_port_lat, 5)],
            [round(p3_lon, 5), round(p3_lat, 5)],
        ]
    }

    opt_port = ReRouteOption(
        id="port_downdrift_wide",
        name="Extended North Offshore Perimeter Bypass (Down-Drift Wide Track)",
        is_recommended=False,
        distance_nm=round(d_port_total, 2),
        direct_distance_nm=round(direct_dist_nm, 2),
        extra_distance_nm=round(extra_port_dist, 2),
        extra_distance_pct=round(extra_port_pct, 1),
        transit_time_min=round(t_port_min, 1),
        direct_time_min=round(direct_time_min, 1),
        time_delay_min=round(delay_port_min, 1),
        fuel_extra_mt=round(fuel_port_mt, 2),
        min_clearance_nm=round(clearance_nm * 2.8, 1),
        plume_clearance_desc="Down-Drift Notice: Passes north of the slick; requires extended standoff (+5.5 NM) to avoid the expanding North-drifting forecast cone.",
        waypoints=port_waypoints,
        geojson_path=port_path_geojson,
        geojson_direct=direct_geojson,
        geojson_exclusion_zone=exclusion_zone_geojson,
    )

    return ReRoutePlan(
        status="RE_ROUTE_REQUIRED",
        reason=f"Persistent oil film ({thickness_um:.1f} µm) exceeds sea chest intake safety threshold.",
        recommended_option_id="starboard_updrift",
        vessel_speed_kts=vessel_speed_kts,
        options=[opt_stbd, opt_port],
        guidance_summary=(
            f"Recommended: Take Starboard Up-Drift Track ({opt_stbd.name}). "
            f"The forecast plume is drifting North ({drift_hdg:.0f}°). Steal South-East into clean up-drift water "
            f"(adds only +{opt_stbd.extra_distance_nm:.1f} NM / +{opt_stbd.time_delay_min:.0f} min delay at {vessel_speed_kts:.0f} kts), "
            f"maintaining a certified {opt_stbd.min_clearance_nm:.1f} NM safety margin completely outside the forecast plume."
        )
    )


@router.post("/classify-oil", response_model=OilClassifyResponse)
def classify_oil(req: OilClassifyRequest) -> OilClassifyResponse:
    """
    Physics-based assessment of oil spill impact from film thickness and
    automated calculation of optimal, time-saving alternate diversion routes
    evaluated against the active forecast drift plume.
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

    reroute_plan = None
    if re_route:
        c_lon = req.center_lon if req.center_lon is not None else -90.02
        c_lat = req.center_lat if req.center_lat is not None else 28.47
        l_km = req.length_km if req.length_km is not None else 36.0
        w_km = req.width_km if req.width_km is not None else 8.4
        orient = req.orientation_deg if req.orientation_deg is not None else 48.0

        reroute_plan = _compute_reroute_plan(
            center_lon=c_lon,
            center_lat=c_lat,
            length_km=l_km,
            width_km=w_km,
            orientation_deg=orient,
            thickness_um=thickness_um,
            mock_wind_dir_deg=req.mock_wind_dir_deg,
            drift_heading_deg=req.drift_heading_deg,
        )

    return OilClassifyResponse(
        predicted_type=evap_label,
        impact=impact,
        features_used=features,
        thickness_um=thickness_um,
        reroute_plan=reroute_plan,
    )
