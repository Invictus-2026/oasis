"""
SpillTrace API contract.

These pydantic models ARE the contract between backend and frontend. They are
frozen in Phase 0 so both halves of the team can work in parallel. Change them
deliberately and update `frontend/src/api/types.ts` + `frontend/src/mock/` in
the same commit.

Geometry is expressed as GeoJSON dicts (RFC 7946), coordinates always [lon, lat].
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------

GeoJSON = dict[str, Any]
LonLat = tuple[float, float]


class Provenance(BaseModel):
    """Attached to every response. This is what makes the audit story real
    rather than merely claimed: every number on screen can name the code
    version, the parameters and the inputs that produced it."""

    model_version: str
    params: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
    inputs: list[str] = Field(default_factory=list)
    notes: str | None = None


class ProcessingStep(BaseModel):
    name: str
    duration_ms: float
    detail: str | None = None


class BBox(BaseModel):
    """[west, south, east, north] in degrees."""

    west: float
    south: float
    east: float
    north: float

    def as_list(self) -> list[float]:
        return [self.west, self.south, self.east, self.north]


# --------------------------------------------------------------------------
# GET /api/case
# --------------------------------------------------------------------------


class DataSource(BaseModel):
    name: str
    kind: Literal["sar", "ais", "wind", "current", "coastline", "synthetic"]
    source_url: str | None = None
    licence: str | None = None
    is_synthetic: bool = False
    note: str | None = None


class GroundTruth(BaseModel):
    """Only present because this is a constructed validation scenario. It is
    what lets us prove the pipeline actually works rather than merely runs."""

    origin: LonLat
    origin_time_utc: datetime
    polluter_mmsi: str
    polluter_name: str


class CaseMeta(BaseModel):
    id: str
    name: str
    bbox: BBox
    center: LonLat
    scene_id: str
    acquired_at: datetime
    sar_overlay_url: str | None = None
    sources: list[DataSource]
    ground_truth: GroundTruth | None = None
    disclaimer: str
    provenance: Provenance


# --------------------------------------------------------------------------
# POST /api/detect
# --------------------------------------------------------------------------


class SlickGeometry(BaseModel):
    """Morphology of one detected region, in real-world units.

    Fields carry defaults so a fixture or an older cached payload that predates
    the extent measurements still validates — mock mode must never break on a
    schema addition.
    """

    area_km2: float
    perimeter_km: float
    length_km: float = Field(default=0.0, description="extent along the region's major axis")
    width_km: float = Field(default=0.0, description="extent along the region's minor axis")
    aspect_ratio: float = Field(default=1.0, description="length/width of the principal-axis extents")
    elongation: float = Field(description="major/minor axis ratio of the fitted ellipse")
    orientation_deg: float = Field(description="major-axis bearing, 0=N, clockwise")
    compactness: float = Field(description="4*pi*A/P^2; 1.0 = perfect circle")
    solidity: float = Field(default=1.0, description="area/convex-hull area; 1.0 = convex, lower = ragged")


class BackscatterStats(BaseModel):
    """Radiometric statistics measured on the speckle-filtered raster.

    These are the numbers behind the contrast and variance sub-scores, exposed
    so a confidence value can be traced back to physical measurements. For
    uploaded imagery with no calibrated Sigma0 these are relative, not absolute
    — see the upload endpoint's notes field."""

    mean_db: float = Field(description="mean backscatter inside the region")
    std_db: float = Field(description="backscatter standard deviation inside the region")
    background_db: float = Field(description="mean backscatter of the surrounding annulus")
    contrast_db: float = Field(description="background - inside; positive means darker than the sea")
    variance_ratio: float = Field(description="inside std / background std; oil damps speckle below 1")
    edge_gradient: float = Field(default=0.0, description="mean |gradient| on the region boundary")


class AgeEstimate(BaseModel):
    """Deliberately a range, not a point. The PS itself hedges this as
    'if feasible'; we attempt it and label the uncertainty honestly."""

    min_hours: float
    max_hours: float
    confidence: Literal["low", "medium", "high"] = "low"
    method_note: str
    # Structured pull-outs of the same numbers method_note narrates in prose,
    # so the UI can show them as compact fields instead of forcing a read.
    diffusivity_m2s: float | None = Field(default=None, description="Okubo scale-dependent horizontal eddy diffusivity")
    damping_db: float | None = Field(default=None, description="backscatter contrast used to shade freshness")
    weathering: str | None = None


class DetectionMethod(str, Enum):
    classical = "classical"
    unet = "unet"


class DetectionEvidence(BaseModel):
    """The four real, physically-motivated 0-1 sub-scores classify() computes
    and weight-averages into a region's confidence — contrast, variance, shape
    and edge terms exactly as scored, not a separate presentation-layer
    computation. This is what makes 'why oil, why not' auditable rather than a
    single opaque number."""

    contrast: float = Field(ge=0.0, le=1.0, description="backscatter damping vs local background")
    variance: float = Field(ge=0.0, le=1.0, description="speckle suppression vs ambient sea")
    shape: float = Field(ge=0.0, le=1.0, description="elongated trail vs compact blob")
    edge: float = Field(ge=0.0, le=1.0, description="boundary sharpness")
    weight_contrast: float = 0.34
    weight_variance: float = 0.31
    weight_shape: float = 0.23
    weight_edge: float = 0.12


class Slick(BaseModel):
    id: str
    polygon: GeoJSON
    confidence: float = Field(ge=0.0, le=1.0)
    method: DetectionMethod
    geometry: SlickGeometry
    backscatter: BackscatterStats | None = None
    age: AgeEstimate | None = None
    evidence: DetectionEvidence | None = None


class RejectedLookalike(BaseModel):
    """Surfacing what we ruled out, and why, pre-answers the most common
    judge question about biogenic slicks and low-wind patches."""

    id: str
    polygon: GeoJSON
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    geometry: SlickGeometry | None = None
    backscatter: BackscatterStats | None = None
    evidence: DetectionEvidence | None = None


class DetectRequest(BaseModel):
    case_id: str | None = None
    method: DetectionMethod = DetectionMethod.classical


class DetectResponse(BaseModel):
    slicks: list[Slick]
    rejected_lookalikes: list[RejectedLookalike]
    processing: list[ProcessingStep]
    provenance: Provenance


# --------------------------------------------------------------------------
# POST /api/drift/hindcast  |  POST /api/drift/forecast
# --------------------------------------------------------------------------


class ParticleFrame(BaseModel):
    """One animation frame. t_offset_hours is negative for hindcast."""

    t_offset_hours: float
    points: list[LonLat]


class ConePolygon(BaseModel):
    t_offset_hours: float
    polygon: GeoJSON
    percentile: Literal[50, 90]
    kind: Literal["frame", "origin"] = Field(
        default="frame",
        description=(
            "'frame' is the ensemble at one instant, for animation. 'origin' is the "
            "region pooled over the whole plausible age window — the actual answer, "
            "and necessarily larger than any single frame."
        ),
    )


class OriginEstimate(BaseModel):
    point: LonLat
    time_utc: datetime
    uncertainty_radius_km: float
    time_window_hours: tuple[float, float] = Field(
        description="(lo, hi) hours before detection bounding the plausible release"
    )


class DriftRequest(BaseModel):
    slick_id: str
    hours: float = 24.0
    n_particles: int = 500
    wind_factor: float = Field(
        default=0.03,
        description="fraction of 10m wind added to surface current; 0.02-0.04 is the defensible range",
    )
    seed: int = 42
    # Phase 4 additions. Defaults match the values engine.py already used as
    # fixed constants, so an old client that omits these fields gets the
    # identical run it always got.
    timestep_minutes: float = Field(
        default=15.0, gt=0.0, le=1440.0,
        description="integration step; smaller values trade runtime for finer trajectories",
    )
    diffusion_m2s: float | None = Field(
        default=None, ge=0.0,
        description="fixed horizontal eddy diffusivity; omit to derive it from the ensemble's "
                    "own spread each step via the Okubo (1971) scale-dependent law",
    )
    custom_polygon: GeoJSON | None = Field(
        default=None,
        description="A polygon geometry representing a custom-uploaded slick, used instead of slick_id lookup.",
    )
    mock_wind_dir_deg: float | None = Field(
        default=None, ge=0.0, le=360.0,
        description="Optional override for the wind direction (bearing toward, degrees clockwise from north), used for simulation testing.",
    )


class HindcastResponse(BaseModel):
    particles_timeline: list[ParticleFrame]
    cone: list[ConePolygon]
    origin_estimate: OriginEstimate
    processing: list[ProcessingStep]
    provenance: Provenance


# --------------------------------------------------------------------------
# POST /api/drift/origin-search  (Phase 5)
# --------------------------------------------------------------------------


class OriginSearchRequest(BaseModel):
    slick_id: str
    max_age_hours: float = Field(default=24.0, gt=0.0, le=24 * 14)
    time_step_hours: float = Field(default=1.0, gt=0.0, le=24.0)
    n_particles: int = Field(default=150, gt=0, le=5000)
    wind_factor: float = Field(default=0.03, ge=0.0, le=0.2)
    timestep_minutes: float = Field(default=15.0, gt=0.0, le=1440.0)
    diffusion_m2s: float | None = Field(default=None, ge=0.0)
    seed: int = 42
    custom_polygon: GeoJSON | None = None
    mock_wind_dir_deg: float | None = Field(default=None, ge=0.0, le=360.0)


class CandidateMetrics(BaseModel):
    """The five required comparison metrics plus the documented composite,
    for one candidate release location/time — auditable rather than a single
    opaque rank."""

    spatial_overlap: float = Field(ge=0.0, le=1.0)
    centroid_distance_km: float
    shape_similarity: float = Field(ge=0.0, le=1.0)
    orientation_similarity: float = Field(ge=0.0, le=1.0)
    density_similarity: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)


class OriginCandidate(BaseModel):
    release_time_utc: datetime
    age_hours: float
    origin: LonLat
    metrics: CandidateMetrics
    age_plausibility: float = Field(
        ge=0.0, le=1.0,
        description="how well this age matches the Okubo width-inversion bracket — an empirical "
                    "constraint folded into ranking, never the sole age estimator",
    )


class OriginSearchResponse(BaseModel):
    """Best estimated origin/time plus the full ranked candidate set, so the
    result is auditable rather than a single number asserted without
    evidence."""

    best_origin: LonLat
    region_50: GeoJSON | None
    region_90: GeoJSON | None
    estimated_release_time_utc: datetime
    estimated_age_hours: float
    age_uncertainty_hours: tuple[float, float]
    confidence: Literal["low", "medium", "high"]
    candidates: list[OriginCandidate] = Field(
        description="every searched (release location, release time) pair, ranked best first"
    )
    geojson: GeoJSON = Field(description="origin regions + best-origin point, ready for MapLibre")
    processing: list[ProcessingStep]
    provenance: Provenance


class ImpactFlag(BaseModel):
    kind: Literal["coastline", "protected_area", "infrastructure"]
    name: str
    eta_hours: float
    distance_km: float


class ForecastResponse(BaseModel):
    particles_timeline: list[ParticleFrame]
    cone: list[ConePolygon]
    centroid_path: GeoJSON
    impact_flags: list[ImpactFlag] = Field(default_factory=list)
    processing: list[ProcessingStep]
    provenance: Provenance


# --------------------------------------------------------------------------
# GET /api/ais/tracks  (Phase 6 — ingestion + track reconstruction)
# --------------------------------------------------------------------------


class AISPositionOut(BaseModel):
    """One normalised AIS broadcast. `imo`/`heading_deg` are null whenever
    the source does not carry them — the real case-bundle AIS source (NOAA
    AccessAIS-derived) has neither; never fabricated to fill the field."""

    timestamp: datetime
    lat: float
    lon: float
    speed_knots: float | None = None
    course_deg: float | None = None
    heading_deg: float | None = None
    imo: str | None = None


class VesselOut(BaseModel):
    mmsi: str
    name: str | None = None
    vessel_type_code: int | None = None
    imo: str | None = None


class VesselTrackOut(BaseModel):
    vessel: VesselOut
    positions: list[AISPositionOut]
    linestring: GeoJSON | None = Field(
        default=None, description="null when fewer than two valid fixes exist for this vessel"
    )
    interpolated_segments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="short, plausibility-checked straight-line fills between two real fixes — "
                    "never fabricated across a long or physically implausible gap",
    )
    gaps: list[AISGap] = Field(
        default_factory=list,
        description="reporting gaps above the threshold. A plain geometric/temporal fact, "
                    "never a suspicion label — see AISGap.label",
    )


class AISTracksResponse(BaseModel):
    """Phase 6 output: real AIS ingestion and track reconstruction, not
    attribution scoring — no proximity/heading/suspicion score is computed
    or returned here. That remains /api/attribute's job."""

    vessels: list[VesselTrackOut]
    geojson: GeoJSON = Field(description="every vessel's track as one FeatureCollection of "
                                          "LineStrings, ready for the existing MapLibre map")
    total_positions_parsed: int
    total_vessels: int
    processing: list[ProcessingStep]
    provenance: Provenance


# --------------------------------------------------------------------------
# POST /api/attribute
# --------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Every factor normalised 0-1 and returned individually, so the UI can
    show WHY a vessel ranks where it does. No black-box score.

    Six components (Phase 7): origin proximity, temporal compatibility,
    trajectory consistency, behaviour anomaly, AIS gap, and counterfactual
    simulation similarity. `counterfactual_similarity` is null for a
    candidate that did not receive the expensive simulate-and-compare step
    (see app/attribution/scoring.py — only the top-ranked candidates get it),
    never a fabricated 0.
    """

    origin_proximity: float = Field(ge=0.0, le=1.0)
    temporal_compatibility: float = Field(ge=0.0, le=1.0)
    trajectory_consistency: float = Field(ge=0.0, le=1.0)
    behaviour_anomaly: float = Field(ge=0.0, le=1.0)
    ais_gap: float = Field(ge=0.0, le=1.0)
    counterfactual_similarity: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="null when this candidate did not receive a counterfactual simulation run",
    )


class ScoreWeights(BaseModel):
    """Named, documented weights — the only place a percentage exists in the
    whole scoring path, and it is an inspectable constant, never baked
    silently into the composite. See app/attribution/scoring.SCORE_WEIGHTS,
    the source of these defaults."""

    origin_proximity: float = 0.22
    temporal_compatibility: float = 0.18
    trajectory_consistency: float = 0.18
    behaviour_anomaly: float = 0.14
    ais_gap: float = 0.14
    counterfactual_similarity: float = 0.14


class AISGap(BaseModel):
    """A plain geometric/temporal fact about a silence in AIS reporting.
    Never a verdict — `label` is deliberately phrased as an investigation
    signal, not an accusation. See app/attribution/ais_ingest.py (Phase 6)."""

    start_utc: datetime
    end_utc: datetime
    duration_minutes: float
    interpolated_path: GeoJSON | None = None
    overlaps_origin_window: bool = False
    label: str = "AIS reporting gap — investigation signal, not a finding of wrongdoing"


class CandidateFlag(str, Enum):
    dark_vessel = "DARK_VESSEL"
    course_deviation = "COURSE_DEVIATION"
    slow_steaming = "SLOW_STEAMING"
    closest_approach = "CLOSEST_APPROACH"


class CandidateLabel(str, Enum):
    """Acceptance vocabulary (Phase 7): a vessel is a CANDIDATE, or an
    INVESTIGATION LEAD when the evidence is stronger — never a "suspect" or
    "culprit". Crossing the lead threshold is a stronger plausibility
    signal, not a verdict; see app/attribution/scoring.INVESTIGATION_LEAD_THRESHOLD."""

    candidate = "candidate"
    investigation_lead = "investigation lead"


class VesselCandidate(BaseModel):
    mmsi: str
    name: str | None = None
    vessel_type: str | None = None
    track: GeoJSON
    score: float = Field(ge=0.0, le=1.0)
    rank: int
    label: CandidateLabel = CandidateLabel.candidate
    flags: list[CandidateFlag] = Field(default_factory=list)
    breakdown: ScoreBreakdown
    gaps: list[AISGap] = Field(default_factory=list)
    closest_approach_km: float
    closest_approach_utc: datetime | None = None
    narrative: str = Field(
        description="One human sentence explaining the score, generated from the breakdown"
    )


class AttributeRequest(BaseModel):
    origin_region: GeoJSON = Field(
        description="origin probability region (Polygon), e.g. Phase 5's origin-search region_50/region_90"
    )
    release_window_start_utc: datetime
    release_window_end_utc: datetime
    drift_bearing_deg: float = Field(
        description="the observed slick's OWN measured orientation (e.g. Phase 2's "
                    "geometry.orientation_deg) — the trail's own axis, not a current/wind drift "
                    "direction. An underway discharge's trail runs along the vessel's heading at "
                    "the moment of release, then the current reshapes it afterward, so a "
                    "vessel's later drift-like motion is not the diagnostic signal here; whether "
                    "the vessel's own track once ran along the trail's axis is."
    )
    search_radius_km: float = 25.0
    counterfactual_top_n: int = Field(
        default=5, ge=0, le=50,
        description="how many top-ranked candidates receive the expensive counterfactual simulation step",
    )
    weights: ScoreWeights = Field(default_factory=ScoreWeights)


class AttributeResponse(BaseModel):
    total_vessels_in_region: int
    after_filter: int
    candidates: list[VesselCandidate]
    weights: ScoreWeights
    all_tracks: GeoJSON | None = Field(
        default=None, description="FeatureCollection of every track pre-filter, for the fade-out animation"
    )
    processing: list[ProcessingStep]
    provenance: Provenance


# --------------------------------------------------------------------------
# POST /api/report
# --------------------------------------------------------------------------


class ReportRequest(BaseModel):
    case_id: str
    slick_id: str
    include_map_snapshot: bool = False


class ReportContent(BaseModel):
    """JSON echo of the PDF, so the on-screen evidence panel and the document
    can never disagree with each other."""

    case_id: str
    generated_at: datetime
    scene_id: str
    acquired_at: datetime
    processing_chain: list[ProcessingStep]
    detection_summary: dict[str, Any]
    origin_summary: dict[str, Any]
    candidates: list[VesselCandidate]
    limitations: list[str]
    provenance: Provenance


# --------------------------------------------------------------------------
# GET /api/pipeline/run
# --------------------------------------------------------------------------


class PipelineResponse(BaseModel):
    case: CaseMeta
    detection: DetectResponse
    hindcast: HindcastResponse
    forecast: ForecastResponse
    attribution: AttributeResponse
    total_duration_ms: float
