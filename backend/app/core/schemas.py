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
    area_km2: float
    perimeter_km: float
    elongation: float = Field(description="major/minor axis ratio of the fitted ellipse")
    orientation_deg: float = Field(description="major-axis bearing, 0=N, clockwise")
    compactness: float = Field(description="4*pi*A/P^2; 1.0 = perfect circle")


class AgeEstimate(BaseModel):
    """Deliberately a range, not a point. The PS itself hedges this as
    'if feasible'; we attempt it and label the uncertainty honestly."""

    min_hours: float
    max_hours: float
    confidence: Literal["low", "medium", "high"] = "low"
    method_note: str


class DetectionMethod(str, Enum):
    classical = "classical"
    unet = "unet"


class Slick(BaseModel):
    id: str
    polygon: GeoJSON
    confidence: float = Field(ge=0.0, le=1.0)
    method: DetectionMethod
    geometry: SlickGeometry
    age: AgeEstimate | None = None


class RejectedLookalike(BaseModel):
    """Surfacing what we ruled out, and why, pre-answers the most common
    judge question about biogenic slicks and low-wind patches."""

    id: str
    polygon: GeoJSON
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


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


class HindcastResponse(BaseModel):
    particles_timeline: list[ParticleFrame]
    cone: list[ConePolygon]
    origin_estimate: OriginEstimate
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
# POST /api/attribute
# --------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Every factor normalised 0-1 and returned individually, so the UI can
    show WHY a vessel ranks where it does. No black-box score."""

    proximity: float = Field(ge=0.0, le=1.0)
    temporal_overlap: float = Field(ge=0.0, le=1.0)
    heading_consistency: float = Field(ge=0.0, le=1.0)
    ais_gap: float = Field(ge=0.0, le=1.0)
    speed_anomaly: float = Field(ge=0.0, le=1.0)


class ScoreWeights(BaseModel):
    proximity: float = 0.30
    temporal_overlap: float = 0.25
    ais_gap: float = 0.20
    heading_consistency: float = 0.15
    speed_anomaly: float = 0.10


class AISGap(BaseModel):
    start_utc: datetime
    end_utc: datetime
    duration_minutes: float
    interpolated_path: GeoJSON | None = None
    overlaps_origin_window: bool = False


class CandidateFlag(str, Enum):
    dark_vessel = "DARK_VESSEL"
    course_deviation = "COURSE_DEVIATION"
    slow_steaming = "SLOW_STEAMING"
    closest_approach = "CLOSEST_APPROACH"


class VesselCandidate(BaseModel):
    mmsi: str
    name: str
    vessel_type: str
    track: GeoJSON
    score: float = Field(ge=0.0, le=1.0)
    rank: int
    flags: list[CandidateFlag] = Field(default_factory=list)
    breakdown: ScoreBreakdown
    gaps: list[AISGap] = Field(default_factory=list)
    closest_approach_km: float
    closest_approach_utc: datetime | None = None
    narrative: str = Field(
        description="One human sentence explaining the score, generated from the breakdown"
    )


class AttributeRequest(BaseModel):
    origin: LonLat
    origin_time_utc: datetime
    search_radius_km: float = 25.0
    time_window_hours: float = 6.0
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
