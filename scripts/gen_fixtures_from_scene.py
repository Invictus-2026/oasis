#!/usr/bin/env python3
"""Regenerate the bundled demo fixtures so every layer lines up with the
bundled SAR scene (frontend/public/sar/scene-sar.png == assets/oil_spil.png).

The scene is georeferenced by the case bbox, corner to corner, which works out
to a flat 0.0005 deg per pixel on both axes. Everything below is authored in
scene pixel coordinates — traced off the imagery — and converted once, so the
slick, the backtrack, the origin and the forecast all sit exactly where the
radar signature is.

    python3 scripts/gen_fixtures_from_scene.py
"""

import json
import math
import os
import random

random.seed(20230615)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK = os.path.join(ROOT, "frontend", "src", "mock")

# ── scene georeferencing ───────────────────────────────────────────────────
LON_W, LAT_N = -90.36, 28.75
DEG_PER_PX = 0.0005            # 1440 px -> 0.72 deg lon, 810 px -> 0.405 deg lat
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.32 * math.cos(math.radians(28.55))


def px(x, y):
    """Scene pixel -> [lon, lat], rounded to the fixture's 6dp convention."""
    return [round(LON_W + x * DEG_PER_PX, 6), round(LAT_N - y * DEG_PER_PX, 6)]


def km_xy(p):
    """[lon, lat] -> local km plane (east, north) about the scene centre."""
    return ((p[0] - LON_W) * KM_PER_DEG_LON, (p[1] - LAT_N) * KM_PER_DEG_LAT)


def from_km(ex, nx):
    return [round(LON_W + ex / KM_PER_DEG_LON, 6), round(LAT_N + nx / KM_PER_DEG_LAT, 6)]


# ── the slick, traced off the SAR signature ────────────────────────────────
# Smooth, low-backscatter region hugging the coast, from the damaged carrier in
# the south-east up the bay to the north-west. Boundary extracted by
# brightness + local-variance segmentation of the scene, then simplified.
SLICK_PX = [
    (468, 83), (559, 110), (656, 172), (704, 190), (759, 157), (796, 171),
    (868, 264), (942, 362), (953, 395), (936, 422), (1003, 451), (1008, 483),
    (998, 513), (943, 538), (896, 513), (868, 554), (855, 557), (828, 486),
    (781, 423), (748, 356), (721, 295), (663, 296), (606, 257), (551, 248),
    (547, 187), (499, 172), (492, 128), (457, 97),
]

# The damaged bulk carrier, circled on the scene — the release point.
VESSEL_PX = (1111, 495)

# Look-alikes, placed on genuinely featureless open-water patches east of the
# slick so "ruled out" reads honestly against the imagery.
LOOKALIKE_PX = [(1268, 168), (1306, 646)]

SCENE_TIME = "2023-06-15T12:00:00Z"      # SAR acquisition == hindcast t=0
ORIGIN_TIME = "2023-06-14T06:00:00Z"     # 30 h of backward advection

HIND_HOURS = 30.0
HIND_STEP = 3.0
FCST_HOURS = 9.0
FCST_STEP = 1.0


PROV_AT = "2026-08-27T00:00:00Z"


def provenance(stage, params, inputs):
    return {
        "model_version": "spilltrace-0.1.0+fixture",
        "params": dict(params, stage=stage),
        "generated_at": PROV_AT,
        "inputs": inputs,
        "notes": "FIXTURE DATA — not produced by the real pipeline.",
    }


# ── slick geometry in km ───────────────────────────────────────────────────
slick_ll = [px(x, y) for x, y in SLICK_PX]
slick_ring = slick_ll + [slick_ll[0]]
slick_km = [km_xy(p) for p in slick_ll]

vessel = px(*VESSEL_PX)
vessel_km = km_xy(vessel)


def shoelace(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


AREA_KM2 = shoelace(slick_km)
PERIM_KM = sum(
    math.dist(slick_km[i], slick_km[(i + 1) % len(slick_km)]) for i in range(len(slick_km))
)

cx = sum(p[0] for p in slick_km) / len(slick_km)
cy = sum(p[1] for p in slick_km) / len(slick_km)
sxx = sum((p[0] - cx) ** 2 for p in slick_km) / len(slick_km)
syy = sum((p[1] - cy) ** 2 for p in slick_km) / len(slick_km)
sxy = sum((p[0] - cx) * (p[1] - cy) for p in slick_km) / len(slick_km)
theta = 0.5 * math.atan2(2 * sxy, sxx - syy)          # major axis, math convention
ux, uy = math.cos(theta), math.sin(theta)
proj = [(p[0] - cx) * ux + (p[1] - cy) * uy for p in slick_km]
perp = [-(p[0] - cx) * uy + (p[1] - cy) * ux for p in slick_km]
LENGTH_KM = max(proj) - min(proj)
WIDTH_KM = max(perp) - min(perp)

# Drift axis: from the carrier towards the far (north-west) end of the slick.
head_km = max(slick_km, key=lambda p: math.dist(p, vessel_km))
DRIFT_BEARING = (math.degrees(math.atan2(head_km[0] - vessel_km[0],
                                         head_km[1] - vessel_km[1])) + 360) % 360
DRIFT_KM = math.dist(head_km, vessel_km)
DRIFT_KMH = DRIFT_KM / HIND_HOURS   # consistent with the backtrack window

print(f"slick  area={AREA_KM2:.1f} km2  perim={PERIM_KM:.1f} km  "
      f"L={LENGTH_KM:.1f}  W={WIDTH_KM:.1f}")
print(f"drift  bearing={DRIFT_BEARING:.1f} deg  axis={DRIFT_KM:.1f} km  "
      f"speed={DRIFT_KM / HIND_HOURS:.2f} km/h")
print(f"origin {vessel}")


# ── particle helpers ───────────────────────────────────────────────────────
def inside(pt, ring):
    x, y = pt
    hit = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < xi:
                hit = not hit
    return hit


def seed_particles(n):
    xs = [p[0] for p in slick_km]
    ys = [p[1] for p in slick_km]
    out = []
    while len(out) < n:
        c = (random.uniform(min(xs), max(xs)), random.uniform(min(ys), max(ys)))
        if inside(c, slick_km):
            out.append(c)
    return out


def ring_percentile(points, centre, pct, bins=40):
    """Radial percentile hull — an organic ensemble cone rather than an ellipse."""
    buckets = [[] for _ in range(bins)]
    for x, y in points:
        dx, dy = x - centre[0], y - centre[1]
        a = math.atan2(dy, dx)
        buckets[int((a + math.pi) / (2 * math.pi) * bins) % bins].append(math.hypot(dx, dy))
    radii = []
    for i in range(bins):
        pool = list(buckets[i])
        k = 1
        while len(pool) < 6 and k < bins // 2:
            pool += buckets[(i - k) % bins] + buckets[(i + k) % bins]
            k += 1
        pool.sort()
        radii.append(pool[min(len(pool) - 1, int(len(pool) * pct))] if pool else 0.0)
    # circular smoothing so the ring reads as a contour, not a starburst
    for _ in range(3):
        radii = [(radii[i - 1] + 2 * radii[i] + radii[(i + 1) % bins]) / 4 for i in range(bins)]
    ring = []
    for i in range(bins):
        a = -math.pi + (i + 0.5) * 2 * math.pi / bins
        r = max(radii[i], 0.25)
        ring.append(from_km(centre[0] + r * math.cos(a), centre[1] + r * math.sin(a)))
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


N_PARTICLES = 240
seed = seed_particles(N_PARTICLES)

# ── hindcast: backward advection collapsing onto the carrier ───────────────
hind_frames, hind_cone = [], []
steps = int(HIND_HOURS / HIND_STEP)
for i in range(steps + 1):
    t = -HIND_STEP * i
    f = 1.0 - (i / steps) * 0.972              # contract towards the release point
    sigma = 1.6 * (i / steps) ** 0.7           # growing positional uncertainty
    pts_km = []
    for j, (x, y) in enumerate(seed):
        rx, ry = random.gauss(0, sigma), random.gauss(0, sigma)
        pts_km.append((vessel_km[0] + (x - vessel_km[0]) * f + rx,
                       vessel_km[1] + (y - vessel_km[1]) * f + ry))
    mx = sum(p[0] for p in pts_km) / len(pts_km)
    my = sum(p[1] for p in pts_km) / len(pts_km)
    hind_frames.append({
        "t_offset_hours": t,
        "points": [from_km(x, y) for x, y in pts_km],
    })
    for pct, key in ((0.5, 50), (0.9, 90)):
        hind_cone.append({
            "t_offset_hours": t,
            "polygon": ring_percentile(pts_km, (mx, my), pct),
            "percentile": key,
        })

final = [km_xy(p) for p in hind_frames[-1]["points"]]
fx = sum(p[0] for p in final) / len(final)
fy = sum(p[1] for p in final) / len(final)
r = sorted(math.dist(p, (fx, fy)) for p in final)
UNCERTAINTY_KM = round(r[int(len(r) * 0.9)], 1)

hindcast = {
    "particles_timeline": hind_frames,
    "cone": hind_cone,
    "origin_estimate": {
        "point": vessel,
        "time_utc": ORIGIN_TIME,
        "uncertainty_radius_km": UNCERTAINTY_KM,
        "time_window_hours": [2.0, 4.0],
    },
    "processing": [
        {"name": "load current + wind fields", "duration_ms": 140.0,
         "detail": "ERA5 10 m wind + CMEMS surface currents"},
        {"name": f"seed {N_PARTICLES * 2} particles in slick polygon",
         "duration_ms": 9.0, "detail": f"{AREA_KM2:.1f} km² detected extent"},
        {"name": f"backward advection {HIND_HOURS:.0f} h", "duration_ms": 1180.0,
         "detail": "15 min timestep"},
        {"name": "percentile cone extraction", "duration_ms": 210.0,
         "detail": "50th / 90th ensemble percentiles"},
    ],
    "provenance": provenance("hindcast", {
        "hours": HIND_HOURS, "n_particles": 500, "wind_factor": 0.03,
        "diffusion_m2s": 5.0, "seed": 42, "direction": "backward",
    }, ["detection/slick-001", "ERA5 10 m wind", "CMEMS surface currents"]),
}

# ── forecast: forward advection down the same drift axis ───────────────────
brg = math.radians(DRIFT_BEARING)
fcst_frames, fcst_cone, centroid_path = [], [], []
fsteps = int(FCST_HOURS / FCST_STEP)
for i in range(fsteps + 1):
    t = FCST_STEP * i
    dist = DRIFT_KMH * t
    ex, ny = math.sin(brg) * dist, math.cos(brg) * dist
    spread = 1.0 + 0.22 * (i / fsteps)          # shear + spreading
    sigma = 1.55 * (i / fsteps) ** 0.6
    pts_km = []
    for x, y in seed:
        rx, ry = random.gauss(0, sigma), random.gauss(0, sigma)
        pts_km.append((cx + (x - cx) * spread + ex + rx,
                       cy + (y - cy) * spread + ny + ry))
    mx = sum(p[0] for p in pts_km) / len(pts_km)
    my = sum(p[1] for p in pts_km) / len(pts_km)
    fcst_frames.append({
        "t_offset_hours": t,
        "points": [from_km(x, y) for x, y in pts_km],
    })
    for pct, key in ((0.5, 50), (0.9, 90)):
        fcst_cone.append({
            "t_offset_hours": t,
            "polygon": ring_percentile(pts_km, (mx, my), pct),
            "percentile": key,
        })
    centroid_path.append(from_km(cx + ex, cy + ny))

forecast = {
    "particles_timeline": fcst_frames,
    "cone": fcst_cone,
    "centroid_path": {"type": "LineString", "coordinates": centroid_path},
    "impact_flags": [
        {"kind": "coastline", "name": "Northwest headland shoreline",
         "eta_hours": 7.0, "distance_km": 9.0},
        {"kind": "coastline", "name": "Inner bay shoreline",
         "eta_hours": 11.5, "distance_km": 14.8},
    ],
    "processing": [
        {"name": "load current + wind fields", "duration_ms": 140.0,
         "detail": f"drift {DRIFT_KMH:.2f} km/h towards {DRIFT_BEARING:.0f}°"},
        {"name": f"forward advection {FCST_HOURS:.0f} h", "duration_ms": 610.0,
         "detail": "15 min timestep"},
        {"name": "percentile cone extraction", "duration_ms": 130.0, "detail": None},
        {"name": "coastline impact screen", "duration_ms": 45.0,
         "detail": "2 shoreline intersects"},
    ],
    "provenance": provenance("forecast", {
        "hours": FCST_HOURS, "n_particles": 500, "wind_factor": 0.03,
        "seed": 42, "direction": "forward",
    }, ["detection/slick-001", "ERA5 10 m wind", "CMEMS surface currents"]),
}

# ── detection ──────────────────────────────────────────────────────────────
def blob(centre_px, rx_px, ry_px, rot_deg, wobble, n=40):
    cxp, cyp = centre_px
    rot = math.radians(rot_deg)
    ring = []
    for i in range(n):
        a = 2 * math.pi * i / n
        w = 1 + wobble * math.sin(3 * a + 0.7) + 0.5 * wobble * math.sin(5 * a + 2.1)
        ex, ey = rx_px * math.cos(a) * w, ry_px * math.sin(a) * w
        ring.append(px(cxp + ex * math.cos(rot) - ey * math.sin(rot),
                       cyp + ex * math.sin(rot) + ey * math.cos(rot)))
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


detection = {
    "slicks": [{
        "id": "slick-001",
        "polygon": {"type": "Polygon", "coordinates": [slick_ring]},
        "confidence": 0.94,
        "method": "classical",
        "geometry": {
            "area_km2": round(AREA_KM2, 1),
            "perimeter_km": round(PERIM_KM, 1),
            "length_km": round(LENGTH_KM, 1),
            "width_km": round(WIDTH_KM, 1),
            "aspect_ratio": round(LENGTH_KM / WIDTH_KM, 2),
            "elongation": round(LENGTH_KM / WIDTH_KM, 2),
            "orientation_deg": round(DRIFT_BEARING, 1),
            "compactness": round(4 * math.pi * AREA_KM2 / PERIM_KM ** 2, 2),
            "solidity": 0.88,
        },
        "backscatter": {
            "mean_db": -19.4, "std_db": 1.12, "background_db": -9.6,
            "contrast_db": 9.8, "variance_ratio": 0.54, "edge_gradient": 0.61,
        },
        "age": {
            "min_hours": 24.0, "max_hours": 34.0, "confidence": "medium",
            "method_note": (
                "Fay gravity-viscous spreading rate inferred from the detected area, "
                "cross-checked against backscatter damping decay along the slick axis. "
                "Order-of-magnitude bracket, not a calibrated measurement."
            ),
            "diffusivity_m2s": 0.3, "damping_db": 9.8, "weathering": "weathering",
        },
        "evidence": {
            "contrast": 0.91, "variance": 0.84, "shape": 0.79, "edge": 0.66,
            "weight_contrast": 0.34, "weight_variance": 0.31,
            "weight_shape": 0.23, "weight_edge": 0.12,
        },
    }],
    "rejected_lookalikes": [
        {
            "id": "lookalike-001",
            "polygon": blob(LOOKALIKE_PX[0], 46, 34, 25, 0.10),
            "reason": ("Low-wind zone: high compactness (0.83) and a soft edge gradient; "
                       "ERA5 wind 1.9 m/s here, below the 3 m/s detectability floor."),
        },
        {
            "id": "lookalike-002",
            "polygon": blob(LOOKALIKE_PX[1], 38, 30, -15, 0.12),
            "reason": ("Biogenic film signature: weak backscatter damping (-3.1 dB vs "
                       "-9.8 dB for the retained slick) and no drift-consistent elongation."),
        },
    ],
    "processing": [
        {"name": "load SAR scene", "duration_ms": 310.0,
         "detail": "S1A_IW_GRDH_1SDV_20230615T120000"},
        {"name": "speckle filter (Lee 7x7)", "duration_ms": 480.0, "detail": None},
        {"name": "land mask", "duration_ms": 95.0, "detail": "SRTM-derived coastline"},
        {"name": "adaptive threshold + morphology", "duration_ms": 260.0, "detail": None},
        {"name": "contour extraction", "duration_ms": 88.0, "detail": "3 regions found"},
        {"name": "look-alike discrimination", "duration_ms": 41.0, "detail": "2 rejected"},
        {"name": "geometry + age proxy", "duration_ms": 22.0, "detail": None},
    ],
    "provenance": provenance("detection", {
        "method": "classical", "speckle": "lee_7x7", "threshold": "otsu_adaptive",
    }, ["S1A_IW_GRDH_1SDV_20230615T120000"]),
}

# ── attribution ────────────────────────────────────────────────────────────
# Tracks drawn in open water east of the slick. The lead runs north-west past
# the release point and drops off AIS exactly across it.
TRACKS_PX = {
    "367301820": [(1424, 800), (1386, 748), (1348, 700), (1310, 654), (1272, 610),
                  (1236, 572), (1200, 552), (1168, 540),
                  (1072, 452), (1052, 410), (1040, 362), (1036, 306), (1042, 246),
                  (1058, 186), (1080, 126), (1104, 66), (1122, 20)],
    "538007612": [(1392, 30), (1374, 128), (1354, 226), (1334, 324), (1316, 422),
                  (1300, 520), (1288, 618), (1280, 716), (1276, 800)],
    "311000765": [(1438, 548), (1394, 580), (1350, 614), (1308, 650), (1268, 688),
                  (1238, 726), (1216, 764), (1198, 806)],
    "356420119": [(1138, 12), (1188, 38), (1240, 66), (1292, 96), (1344, 128),
                  (1396, 162), (1438, 190)],
    "366998210": [(1222, 300), (1250, 360), (1272, 422), (1288, 486), (1296, 550),
                  (1298, 614), (1292, 678), (1280, 742)],
}
GAP_PX = {
    "367301820": [(1168, 540), (1120, 496), (1072, 452)],
    "538007612": [(1334, 324), (1316, 422)],
}

CANDIDATES = [
    ("367301820", "MV KESTREL TRADER", "Bulk Carrier", 0.941, 1, "investigation lead",
     ["DARK_VESSEL", "CLOSEST_APPROACH", "SLOW_STEAMING"],
     {"origin_proximity": 0.972, "temporal_compatibility": 0.955,
      "trajectory_consistency": 0.981, "behaviour_anomaly": 0.86,
      "ais_gap": 1.0, "counterfactual_similarity": 0.953}),
    ("538007612", "MV NORTHERN PETREL", "Bulk Carrier", 0.612, 2, "investigation lead",
     ["SLOW_STEAMING"],
     {"origin_proximity": 0.541, "temporal_compatibility": 0.688,
      "trajectory_consistency": 0.604, "behaviour_anomaly": 0.71,
      "ais_gap": 0.42, "counterfactual_similarity": 0.617}),
    ("366998210", "SEACOR REVIVAL", "Offshore Supply Vessel", 0.418, 3, "candidate",
     [],
     {"origin_proximity": 0.585, "temporal_compatibility": 0.402,
      "trajectory_consistency": 0.311, "behaviour_anomaly": 0.36,
      "ais_gap": 0.0, "counterfactual_similarity": 0.44}),
    ("311000765", "MV GULF SENTINEL", "Crude Oil Tanker", 0.336, 4, "candidate",
     [],
     {"origin_proximity": 0.362, "temporal_compatibility": 0.455,
      "trajectory_consistency": 0.288, "behaviour_anomaly": 0.22,
      "ais_gap": 0.0, "counterfactual_similarity": 0.351}),
    ("356420119", "MV ATLANTIC PIONEER", "Container Ship", 0.214, 5, "candidate",
     [],
     {"origin_proximity": 0.188, "temporal_compatibility": 0.351,
      "trajectory_consistency": 0.142, "behaviour_anomaly": 0.15,
      "ais_gap": 0.0, "counterfactual_similarity": 0.243}),
]

NARRATIVE = {
    "367301820": ("Went AIS-dark for 94 minutes while transiting within {d:.1f} km of the "
                  "estimated release point, on a heading consistent with the slick axis "
                  "({b:.0f}°). Hull damage visible in the SAR scene at the same position."),
    "538007612": ("Passed {d:.1f} km east of the estimated release point at reduced speed. "
                  "A 38-minute reporting gap falls outside the origin time window."),
    "366998210": ("Field-support transit {d:.1f} km east of the estimated release point; "
                  "continuous AIS coverage throughout the origin window."),
    "311000765": ("Outbound transit passing {d:.1f} km south-east of the estimated release "
                  "point, after the origin window closed."),
    "356420119": ("Deep-water transit {d:.1f} km north-east of the estimated release point; "
                  "no track segment inside the origin cone."),
}


def closest_km(track_px):
    best = 1e9
    pts = [km_xy(px(*p)) for p in track_px]
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0, min(1, ((vessel_km[0] - ax) * vx +
                                               (vessel_km[1] - ay) * vy) / L2))
        best = min(best, math.dist((ax + t * vx, ay + t * vy), vessel_km))
    return best


candidates = []
for mmsi, name, vtype, score, rank, label, flags, breakdown in CANDIDATES:
    tr = TRACKS_PX[mmsi]
    d = closest_km(tr)
    gaps = []
    if mmsi in GAP_PX:
        is_lead = mmsi == "367301820"
        gaps.append({
            "start_utc": "2023-06-14T05:13:00Z" if is_lead else "2023-06-14T12:04:00Z",
            "end_utc": "2023-06-14T06:47:00Z" if is_lead else "2023-06-14T12:42:00Z",
            "duration_minutes": 94.0 if is_lead else 38.0,
            "interpolated_path": {
                "type": "LineString",
                "coordinates": [px(*p) for p in GAP_PX[mmsi]],
            },
            "overlaps_origin_window": is_lead,
            "label": "AIS reporting gap — investigation signal, not a finding of wrongdoing",
        })
    candidates.append({
        "mmsi": mmsi, "name": name, "vessel_type": vtype,
        "track": {"type": "LineString", "coordinates": [px(*p) for p in tr]},
        "score": score, "rank": rank, "label": label, "flags": flags,
        "breakdown": breakdown, "gaps": gaps,
        "closest_approach_km": round(d, 1),
        "closest_approach_utc": ORIGIN_TIME,
        "narrative": NARRATIVE[mmsi].format(d=d, b=DRIFT_BEARING),
    })
    print(f"  {name:<22} closest {d:5.1f} km")

WEIGHTS = {
    "origin_proximity": 0.22, "temporal_compatibility": 0.18,
    "trajectory_consistency": 0.18, "behaviour_anomaly": 0.14,
    "ais_gap": 0.14, "counterfactual_similarity": 0.14,
}

attribution = {
    "total_vessels_in_region": 213,
    "after_filter": len(candidates),
    "candidates": candidates,
    "weights": WEIGHTS,
    "all_tracks": None,
    "processing": [
        {"name": "load AIS extract", "duration_ms": 420.0,
         "detail": "213 vessels, 48 h window"},
        {"name": "track reconstruction + interpolation", "duration_ms": 380.0, "detail": None},
        {"name": "AIS gap detection", "duration_ms": 95.0, "detail": ">30 min threshold"},
        {"name": "spatiotemporal filter against origin cone", "duration_ms": 140.0,
         "detail": f"213 -> {len(candidates)} candidates"},
        {"name": "weighted scoring", "duration_ms": 18.0, "detail": None},
    ],
    "provenance": provenance("attribution", {
        "radius_km": UNCERTAINTY_KM, "window_hours": 6.0,
        "weights": WEIGHTS, "gap_threshold_min": 30,
    }, ["NOAA AccessAIS extract", "hindcast origin estimate"]),
}

# ── case ───────────────────────────────────────────────────────────────────
case = json.load(open(os.path.join(MOCK, "case.json")))
case["center"] = [round((cx / KM_PER_DEG_LON) + LON_W, 6),
                  round((cy / KM_PER_DEG_LAT) + LAT_N, 6)]
case["ground_truth"] = {
    "origin": vessel,
    "origin_time_utc": "2023-06-14T06:10:00Z",
    "polluter_mmsi": "367301820",
    "polluter_name": "MV KESTREL TRADER",
}
case["provenance"]["generated_at"] = PROV_AT

for name, payload in (("case", case), ("detection", detection), ("hindcast", hindcast),
                      ("forecast", forecast), ("attribution", attribution)):
    path = os.path.join(MOCK, f"{name}.json")
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=1)
        fh.write("\n")
    print(f"wrote {path} ({os.path.getsize(path) // 1024} KB)")
