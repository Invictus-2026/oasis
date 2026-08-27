"""
Phase-0 fixture data.

Deterministic, schema-valid fake responses so the frontend can be built before
any real pipeline exists. Every generator here is replaced by real code in
Phases 2-4; the shapes it produces are the contract.

Stdlib only, on purpose: the scaffold must run before anyone installs a
geospatial stack.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from app.core import config
from app.core.schemas import (
    AISGap,
    AgeEstimate,
    AttributeResponse,
    BackscatterStats,
    CandidateFlag,
    CandidateLabel,
    CaseMeta,
    ConePolygon,
    DataSource,
    DetectResponse,
    DetectionEvidence,
    DetectionMethod,
    ForecastResponse,
    GroundTruth,
    HindcastResponse,
    ImpactFlag,
    OriginEstimate,
    ParticleFrame,
    ProcessingStep,
    Provenance,
    RejectedLookalike,
    ScoreBreakdown,
    ScoreWeights,
    Slick,
    SlickGeometry,
    VesselCandidate,
)

# Ground truth for the constructed scenario. Phase 1 writes the real values
# into data/case/case.json; these mirror them so fixtures and reality agree.
GT_ORIGIN = (-90.115, 28.408)
GT_ORIGIN_TIME = datetime(2023, 6, 15, 4, 10, 0, tzinfo=timezone.utc)
GT_MMSI = "367301820"
GT_NAME = "MV KESTREL TRADER"

SLICK_ID = "slick-001"

KM_PER_DEG_LAT = 110.574


def _km_per_deg_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def _offset(lon: float, lat: float, dx_km: float, dy_km: float) -> tuple[float, float]:
    return (lon + dx_km / _km_per_deg_lon(lat), lat + dy_km / KM_PER_DEG_LAT)


def _provenance(step: str, params: dict, inputs: list[str], note: str | None = None) -> Provenance:
    return Provenance(
        model_version=f"{config.MODEL_VERSION}+fixture",
        params={"stage": step, **params},
        generated_at=datetime.now(timezone.utc),
        inputs=inputs,
        notes=note or "FIXTURE DATA — not produced by the real pipeline.",
    )


def _ellipse_polygon(
    lon: float, lat: float, major_km: float, minor_km: float, bearing_deg: float, n: int = 48,
    jitter: float = 0.0, rng: random.Random | None = None,
) -> list[list[float]]:
    """An oriented ellipse in lon/lat, optionally roughened so it reads as a
    detected shape rather than a drawn one."""
    theta = math.radians(bearing_deg)
    ring: list[list[float]] = []
    for i in range(n):
        t = 2 * math.pi * i / n
        a, b = major_km / 2, minor_km / 2
        if jitter and rng:
            a *= 1 + rng.uniform(-jitter, jitter)
            b *= 1 + rng.uniform(-jitter, jitter)
        x, y = a * math.cos(t), b * math.sin(t)
        # rotate so that bearing is measured clockwise from north
        dx = x * math.sin(theta) + y * math.cos(theta)
        dy = x * math.cos(theta) - y * math.sin(theta)
        ring.append(list(_offset(lon, lat, dx, dy)))
    ring.append(ring[0])
    return ring


# --------------------------------------------------------------------------
# GET /api/case
# --------------------------------------------------------------------------


def case_meta() -> CaseMeta:
    return CaseMeta(
        id=config.CASE_ID,
        name=config.CASE_NAME,
        bbox=config.CASE_BBOX,
        center=config.CASE_CENTER,
        scene_id=config.SCENE_ID,
        acquired_at=config.ACQUIRED_AT,
        sar_overlay_url=None,
        sources=[
            DataSource(
                name="Sentinel-1 SAR oil-spill dataset (Parts I-III)",
                kind="sar",
                source_url="https://zenodo.org/records/8346860",
                licence="CC BY 4.0",
                note="Officially specified in the problem statement.",
            ),
            DataSource(
                name="NOAA AccessAIS historical AIS",
                kind="ais",
                source_url="https://marinecadastre.gov/accessais/",
                licence="Public domain (US Government)",
                note="Officially specified in the problem statement.",
            ),
            DataSource(
                name="ERA5 10 m wind reanalysis",
                kind="wind",
                source_url="https://cds.climate.copernicus.eu/",
                licence="Copernicus licence",
            ),
            DataSource(
                name="CMEMS surface currents",
                kind="current",
                source_url="https://marine.copernicus.eu/",
                licence="Copernicus licence",
            ),
            DataSource(
                name="Injected ground-truth polluter track",
                kind="synthetic",
                is_synthetic=True,
                note="One synthetic vessel added so attribution can be validated against a known answer.",
            ),
        ],
        ground_truth=GroundTruth(
            origin=GT_ORIGIN,
            origin_time_utc=GT_ORIGIN_TIME,
            polluter_mmsi=GT_MMSI,
            polluter_name=GT_NAME,
        ),
        disclaimer=config.DISCLAIMER,
        provenance=_provenance("case", {"case_id": config.CASE_ID}, ["data/case/case.json"]),
    )


# --------------------------------------------------------------------------
# POST /api/detect
# --------------------------------------------------------------------------


def detect_response(method: DetectionMethod = DetectionMethod.classical) -> DetectResponse:
    rng = random.Random(1)
    # Slick sits NE of the true origin, consistent with ~8 h of NE-ward drift.
    slick_lon, slick_lat = _offset(*GT_ORIGIN, 9.5, 7.0)
    ring = _ellipse_polygon(slick_lon, slick_lat, 18.0, 4.2, 48.0, jitter=0.12, rng=rng)

    slick = Slick(
        id=SLICK_ID,
        polygon={"type": "Polygon", "coordinates": [ring]},
        confidence=0.87 if method is DetectionMethod.unet else 0.79,
        method=method,
        geometry=SlickGeometry(
            area_km2=59.4,
            perimeter_km=41.8,
            # Extents match the ellipse this fixture's own polygon is drawn
            # from (18.0 x 4.2 km semi-axes), so mock morphology stays
            # internally consistent with the mock geometry on screen.
            length_km=36.0,
            width_km=8.4,
            aspect_ratio=4.29,
            elongation=4.29,
            orientation_deg=48.0,
            compactness=0.427,
            solidity=0.94,
        ),
        backscatter=BackscatterStats(
            mean_db=-18.2,
            std_db=1.31,
            background_db=-9.8,
            contrast_db=8.4,
            variance_ratio=0.61,
            edge_gradient=0.42,
        ),
        age=AgeEstimate(
            min_hours=6.0,
            max_hours=14.0,
            confidence="low",
            diffusivity_m2s=0.30,
            damping_db=6.2,
            weathering="weathering",
            method_note=(
                "Heuristic proxy: Fay gravity-viscous spreading rate inferred from slick "
                "area, cross-checked against backscatter contrast decay. Not a calibrated "
                "measurement; treat as an order-of-magnitude bracket."
            ),
        ),
        evidence=DetectionEvidence(contrast=0.81, variance=0.77, shape=0.68, edge=0.54),
    )

    lookalikes = [
        RejectedLookalike(
            id="lookalike-001",
            polygon={
                "type": "Polygon",
                "coordinates": [
                    _ellipse_polygon(*_offset(slick_lon, slick_lat, -21.0, 12.0), 11.0, 9.0, 10.0,
                                     jitter=0.18, rng=rng)
                ],
            },
            reason="Low-wind zone: high compactness (0.81) and soft edge gradient; ERA5 wind 1.9 m/s, below the 3 m/s detectability floor.",
            confidence=0.74,
            geometry=SlickGeometry(
                area_km2=31.1, perimeter_km=19.6, length_km=22.0, width_km=18.0,
                aspect_ratio=1.22, elongation=1.22, orientation_deg=10.0,
                compactness=0.81, solidity=0.97,
            ),
            backscatter=BackscatterStats(
                mean_db=-13.4, std_db=2.44, background_db=-10.3,
                contrast_db=3.1, variance_ratio=0.94, edge_gradient=0.14,
            ),
            evidence=DetectionEvidence(contrast=0.31, variance=0.22, shape=0.18, edge=0.29),
        ),
        RejectedLookalike(
            id="lookalike-002",
            polygon={
                "type": "Polygon",
                "coordinates": [
                    _ellipse_polygon(*_offset(slick_lon, slick_lat, 14.0, -19.0), 7.5, 6.2, 120.0,
                                     jitter=0.22, rng=rng)
                ],
            },
            reason="Biogenic slick signature: weak backscatter damping (-3.1 dB vs -8.4 dB for the retained slick) and no coherent drift-consistent elongation.",
            confidence=0.66,
            geometry=SlickGeometry(
                area_km2=14.6, perimeter_km=13.4, length_km=15.0, width_km=12.4,
                aspect_ratio=1.21, elongation=1.21, orientation_deg=120.0,
                compactness=1.0, solidity=0.96,
            ),
            backscatter=BackscatterStats(
                mean_db=-12.9, std_db=2.61, background_db=-10.1,
                contrast_db=2.8, variance_ratio=1.02, edge_gradient=0.11,
            ),
            evidence=DetectionEvidence(contrast=0.18, variance=0.35, shape=0.41, edge=0.20),
        ),
    ]

    return DetectResponse(
        slicks=[slick],
        rejected_lookalikes=lookalikes,
        processing=[
            ProcessingStep(name="load SAR scene", duration_ms=310.0, detail=config.SCENE_ID),
            ProcessingStep(name="speckle filter (Lee 7x7)", duration_ms=480.0),
            ProcessingStep(name="land mask", duration_ms=95.0),
            ProcessingStep(name="adaptive threshold + morphology", duration_ms=260.0),
            ProcessingStep(name="contour extraction", duration_ms=88.0, detail="3 regions found"),
            ProcessingStep(name="look-alike discrimination", duration_ms=41.0, detail="2 rejected"),
            ProcessingStep(name="geometry + age proxy", duration_ms=22.0),
        ],
        provenance=_provenance(
            "detection",
            {"method": method.value, "speckle": "lee_7x7", "threshold": "otsu_adaptive"},
            [config.SCENE_ID],
        ),
    )


# --------------------------------------------------------------------------
# Drift
# --------------------------------------------------------------------------


def _drift(direction: int, hours: float, n_particles: int, seed: int):
    """Fake advection: a mean drift plus growing spread. Produces the same
    shapes the real Lagrangian engine will in Phase 3."""
    rng = random.Random(seed)
    slick_lon, slick_lat = _offset(*GT_ORIGIN, 9.5, 7.0)

    # Mean NE-ward set of ~1.5 km/h; backward runs it in reverse.
    u_kmh, v_kmh = 1.20, 0.88
    step_h = 1.0
    n_steps = int(hours / step_h)

    frames: list[ParticleFrame] = []
    cone: list[ConePolygon] = []

    # Seed particles inside the slick footprint.
    parts = []
    for _ in range(n_particles):
        parts.append(_offset(slick_lon, slick_lat, rng.gauss(0, 3.4), rng.gauss(0, 1.1)))

    for step in range(n_steps + 1):
        t = direction * step * step_h
        if step > 0:
            spread = 0.22 * math.sqrt(step)
            parts = [
                _offset(lon, lat,
                        direction * u_kmh * step_h + rng.gauss(0, spread),
                        direction * v_kmh * step_h + rng.gauss(0, spread))
                for lon, lat in parts
            ]
        if step % 2 == 0 or step == n_steps:
            frames.append(ParticleFrame(t_offset_hours=t, points=[(round(a, 5), round(b, 5)) for a, b in parts]))
            clon = sum(p[0] for p in parts) / len(parts)
            clat = sum(p[1] for p in parts) / len(parts)
            grow = 1.0 + 0.16 * step
            for pct, mult in ((50, 0.55), (90, 1.0)):
                cone.append(
                    ConePolygon(
                        t_offset_hours=t,
                        polygon={
                            "type": "Polygon",
                            "coordinates": [
                                _ellipse_polygon(clon, clat, 15.0 * grow * mult, 7.0 * grow * mult, 48.0)
                            ],
                        },
                        percentile=pct,
                    )
                )
    return frames, cone, parts


def hindcast_response(hours: float = 24.0, n_particles: int = 500, seed: int = 42,
                      wind_factor: float = 0.03) -> HindcastResponse:
    frames, cone, final = _drift(-1, hours, n_particles, seed)
    clon = sum(p[0] for p in final) / len(final)
    clat = sum(p[1] for p in final) / len(final)
    return HindcastResponse(
        particles_timeline=frames,
        cone=cone,
        origin_estimate=OriginEstimate(
            point=(round(clon, 5), round(clat, 5)),
            time_utc=config.ACQUIRED_AT - timedelta(hours=8),
            uncertainty_radius_km=11.4,
            time_window_hours=(6.0, 12.0),
        ),
        processing=[
            ProcessingStep(name="load current + wind fields", duration_ms=140.0),
            ProcessingStep(name=f"seed {n_particles} particles in slick polygon", duration_ms=8.0),
            ProcessingStep(name=f"backward advection {hours:.0f} h", duration_ms=1180.0,
                           detail=f"{config.DRIFT_TIMESTEP_MINUTES} min timestep"),
            ProcessingStep(name="percentile cone extraction", duration_ms=210.0),
        ],
        provenance=_provenance(
            "hindcast",
            {"hours": hours, "n_particles": n_particles, "wind_factor": wind_factor,
             "diffusion_m2s": config.DRIFT_DIFFUSION_M2S, "seed": seed, "direction": "backward"},
            ["ERA5 10 m wind", "CMEMS surface currents", SLICK_ID],
        ),
    )


def forecast_response(hours: float = 12.0, n_particles: int = 500, seed: int = 42,
                      wind_factor: float = 0.03) -> ForecastResponse:
    frames, cone, _ = _drift(+1, hours, n_particles, seed)
    path = []
    for f in frames:
        clon = sum(p[0] for p in f.points) / len(f.points)
        clat = sum(p[1] for p in f.points) / len(f.points)
        path.append([round(clon, 5), round(clat, 5)])
    return ForecastResponse(
        particles_timeline=frames,
        cone=cone,
        centroid_path={"type": "LineString", "coordinates": path},
        impact_flags=[
            ImpactFlag(kind="coastline", name="Terrebonne Bay shoreline", eta_hours=31.5, distance_km=48.2),
        ],
        processing=[
            ProcessingStep(name="load current + wind fields", duration_ms=140.0),
            ProcessingStep(name=f"forward advection {hours:.0f} h", duration_ms=610.0),
            ProcessingStep(name="percentile cone extraction", duration_ms=130.0),
            ProcessingStep(name="coastline impact screen", duration_ms=45.0),
        ],
        provenance=_provenance(
            "forecast",
            {"hours": hours, "n_particles": n_particles, "wind_factor": wind_factor,
             "seed": seed, "direction": "forward"},
            ["ERA5 10 m wind", "CMEMS surface currents", SLICK_ID],
        ),
    )


# --------------------------------------------------------------------------
# POST /api/attribute
# --------------------------------------------------------------------------

_VESSELS = [
    # (mmsi, name, type, bearing_deg, closest_km, has_gap, gap_min)
    (GT_MMSI, GT_NAME, "Chemical/Oil Products Tanker", 52.0, 1.8, True, 94.0),
    ("538007612", "MV NORTHERN PETREL", "Bulk Carrier", 61.0, 6.4, True, 38.0),
    ("311000765", "MV GULF SENTINEL", "Crude Oil Tanker", 128.0, 9.1, False, 0.0),
    ("366998210", "SEACOR REVIVAL", "Offshore Supply Vessel", 205.0, 14.7, False, 0.0),
    ("356420119", "MV ATLANTIC PIONEER", "Container Ship", 88.0, 21.3, False, 0.0),
]


def attribute_response(weights: ScoreWeights | None = None) -> AttributeResponse:
    """Mock/fixture shape for Phase 7's six-component scoring.

    Kept structurally aligned with app/attribution/scoring.py's real pipeline
    (same six components, same weighting, same "candidate"/"investigation
    lead" vocabulary) so mock mode is a faithful preview, not a different
    contract. Real ingestion + scoring runs through engine.py; this only
    backs /api/report and /api/pipeline/run's fixture-only paths.
    """
    weights = weights or ScoreWeights()
    rng = random.Random(7)
    origin_time = config.ACQUIRED_AT - timedelta(hours=8)

    candidates: list[VesselCandidate] = []
    for mmsi, name, vtype, bearing, closest, has_gap, gap_min in _VESSELS:
        # Build a straight-ish track passing at `closest` km from the origin.
        theta = math.radians(bearing)
        pts = []
        for s in range(-9, 10):
            along = s * 5.0
            pts.append(list(_offset(*GT_ORIGIN,
                                    along * math.sin(theta) + closest * math.cos(theta) + rng.gauss(0, 0.25),
                                    along * math.cos(theta) - closest * math.sin(theta) + rng.gauss(0, 0.25))))

        origin_proximity = max(0.0, 1.0 - closest / 25.0)
        temporal_compatibility = max(0.0, 1.0 - abs(closest) / 40.0)
        trajectory_consistency = max(0.0, 1.0 - abs(bearing - 48.0) / 180.0)
        gap_score = min(1.0, gap_min / 90.0) if has_gap else 0.0
        behaviour_anomaly = 0.72 if has_gap else 0.18
        # Mock proxy for the real counterfactual-simulation step: a vessel
        # whose proximity+trajectory already look plausible gets a
        # correspondingly plausible simulated-slick match in this fixture,
        # since there is no real environmental field to actually simulate
        # against in mock mode.
        counterfactual_similarity = round(0.5 * origin_proximity + 0.5 * trajectory_consistency, 3)

        breakdown = ScoreBreakdown(
            origin_proximity=round(origin_proximity, 3),
            temporal_compatibility=round(temporal_compatibility, 3),
            trajectory_consistency=round(trajectory_consistency, 3),
            behaviour_anomaly=round(behaviour_anomaly, 3),
            ais_gap=round(gap_score, 3),
            counterfactual_similarity=counterfactual_similarity,
        )
        score = round(
            breakdown.origin_proximity * weights.origin_proximity
            + breakdown.temporal_compatibility * weights.temporal_compatibility
            + breakdown.trajectory_consistency * weights.trajectory_consistency
            + breakdown.behaviour_anomaly * weights.behaviour_anomaly
            + breakdown.ais_gap * weights.ais_gap
            + breakdown.counterfactual_similarity * weights.counterfactual_similarity,
            3,
        )
        label = CandidateLabel.investigation_lead if score >= 0.55 else CandidateLabel.candidate

        flags: list[CandidateFlag] = []
        gaps: list[AISGap] = []
        if has_gap:
            gap_start = origin_time - timedelta(minutes=gap_min / 2)
            gap_end = gap_start + timedelta(minutes=gap_min)
            overlaps = gap_min >= 60
            # The gap sits around closest approach (track index 9, s=0) — a
            # short reconstructed segment bridging it, same as a real
            # gap-filler would draw across a genuine reporting hole.
            gaps.append(AISGap(
                start_utc=gap_start, end_utc=gap_end, duration_minutes=gap_min,
                overlaps_origin_window=overlaps,
                interpolated_path={"type": "LineString", "coordinates": [pts[7], pts[11]]},
            ))
            if overlaps:
                flags.append(CandidateFlag.dark_vessel)
        if closest < 3.0:
            flags.append(CandidateFlag.closest_approach)
        if behaviour_anomaly > 0.6:
            flags.append(CandidateFlag.slow_steaming)

        if has_gap and gap_min >= 60:
            narrative = (
                f"Went AIS-dark for {gap_min:.0f} minutes while transiting within "
                f"{closest:.1f} km of the estimated origin, on a heading consistent with the slick axis."
            )
        elif closest < 10:
            narrative = (
                f"Passed within {closest:.1f} km of the estimated origin during the release window "
                f"with continuous AIS reporting and no behavioural anomaly."
            )
        else:
            narrative = (
                f"Present in the region but closest approach was {closest:.1f} km, outside the "
                f"high-probability origin area."
            )

        candidates.append(
            VesselCandidate(
                mmsi=mmsi, name=name, vessel_type=vtype,
                track={"type": "LineString", "coordinates": pts},
                score=score, rank=0, label=label, flags=flags, breakdown=breakdown, gaps=gaps,
                closest_approach_km=closest,
                closest_approach_utc=origin_time + timedelta(minutes=rng.randint(-40, 40)),
                narrative=narrative,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(candidates, 1):
        c.rank = i

    return AttributeResponse(
        total_vessels_in_region=213,
        after_filter=len(candidates),
        candidates=candidates,
        weights=weights,
        all_tracks=None,
        processing=[
            ProcessingStep(name="load AIS extract", duration_ms=420.0, detail="213 vessels, 48 h window"),
            ProcessingStep(name="track reconstruction + interpolation", duration_ms=380.0),
            ProcessingStep(name="AIS gap detection", duration_ms=95.0,
                           detail=f">{config.AIS_GAP_THRESHOLD_MINUTES} min threshold"),
            ProcessingStep(name="spatiotemporal filter against origin cone", duration_ms=140.0,
                           detail="213 -> 5 candidates"),
            ProcessingStep(name="weighted scoring", duration_ms=18.0),
        ],
        provenance=_provenance(
            "attribution",
            {"radius_km": config.ATTRIBUTION_RADIUS_KM, "window_hours": config.ATTRIBUTION_WINDOW_HOURS,
             "weights": weights.model_dump(), "gap_threshold_min": config.AIS_GAP_THRESHOLD_MINUTES},
            ["NOAA AccessAIS extract", "hindcast origin estimate"],
        ),
    )
