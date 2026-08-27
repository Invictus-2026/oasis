/**
 * Mirror of backend/app/core/schemas.py — the frozen API contract.
 * Change both files in the same commit, then re-run scripts/export_mocks.py.
 */

export type LonLat = [number, number];
/** Real geojson types, via @types/geojson (bundled with maplibre-gl). */
export type Geom = GeoJSON.Geometry;
export type FeatureColl = GeoJSON.FeatureCollection;

export interface Provenance {
  model_version: string;
  params: Record<string, unknown>;
  generated_at: string;
  inputs: string[];
  notes: string | null;
}

export interface ProcessingStep {
  name: string;
  duration_ms: number;
  detail: string | null;
}

export interface BBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface DataSource {
  name: string;
  kind: "sar" | "ais" | "wind" | "current" | "coastline" | "synthetic";
  source_url: string | null;
  licence: string | null;
  is_synthetic: boolean;
  note: string | null;
}

export interface GroundTruth {
  origin: LonLat;
  origin_time_utc: string;
  polluter_mmsi: string;
  polluter_name: string;
}

export interface CaseMeta {
  id: string;
  name: string;
  bbox: BBox;
  center: LonLat;
  scene_id: string;
  acquired_at: string;
  sar_overlay_url: string | null;
  sources: DataSource[];
  ground_truth: GroundTruth | null;
  disclaimer: string;
  provenance: Provenance;
}

export type DetectionMethod = "classical" | "unet";

export interface SlickGeometry {
  area_km2: number;
  perimeter_km: number;
  /** Extent along the region's own major axis (not a bounding box). */
  length_km: number;
  /** Extent along the region's minor axis; the quantity age estimation inverts. */
  width_km: number;
  /** length_km / width_km. Distinct from `elongation`, which is the
   *  second-moment eigenvalue ratio of the fitted ellipse. */
  aspect_ratio: number;
  elongation: number;
  orientation_deg: number;
  compactness: number;
  /** area / convex-hull area; 1.0 = convex, lower = ragged. */
  solidity: number;
}

/** Radiometric statistics measured per region on the speckle-filtered raster.
 *  Absolute for calibrated case-study SAR; relative only for uploaded imagery
 *  that carries no Sigma0 calibration. */
export interface BackscatterStats {
  mean_db: number;
  std_db: number;
  background_db: number;
  contrast_db: number;
  variance_ratio: number;
  edge_gradient: number;
}

export interface AgeEstimate {
  min_hours: number;
  max_hours: number;
  confidence: "low" | "medium" | "high";
  method_note: string;
  diffusivity_m2s?: number | null;
  damping_db?: number | null;
  weathering?: string | null;
}

/** The four real, weighted 0-1 sub-scores classify() computes on the backend
 *  and averages into confidence — not a separate frontend computation. */
export interface DetectionEvidence {
  contrast: number;
  variance: number;
  shape: number;
  edge: number;
  weight_contrast: number;
  weight_variance: number;
  weight_shape: number;
  weight_edge: number;
}

export interface Slick {
  id: string;
  polygon: Geom;
  confidence: number;
  method: DetectionMethod;
  geometry: SlickGeometry;
  backscatter?: BackscatterStats | null;
  age: AgeEstimate | null;
  evidence?: DetectionEvidence | null;
}

export interface RejectedLookalike {
  id: string;
  polygon: Geom;
  reason: string;
  confidence: number;
  geometry?: SlickGeometry | null;
  backscatter?: BackscatterStats | null;
  evidence?: DetectionEvidence | null;
}

export interface DetectResponse {
  slicks: Slick[];
  rejected_lookalikes: RejectedLookalike[];
  processing: ProcessingStep[];
  provenance: Provenance;
}

export interface ParticleFrame {
  t_offset_hours: number;
  points: LonLat[];
}

export interface ConePolygon {
  t_offset_hours: number;
  polygon: Geom;
  percentile: 50 | 90;
  /** "frame" is one animation step; "origin" is the pooled answer region. */
  kind: "frame" | "origin";
}

export interface OriginEstimate {
  point: LonLat;
  time_utc: string;
  uncertainty_radius_km: number;
  time_window_hours: [number, number];
}

export interface HindcastResponse {
  particles_timeline: ParticleFrame[];
  cone: ConePolygon[];
  origin_estimate: OriginEstimate;
  processing: ProcessingStep[];
  provenance: Provenance;
}

export interface ImpactFlag {
  kind: "coastline" | "protected_area" | "infrastructure";
  name: string;
  eta_hours: number;
  distance_km: number;
}

export interface ForecastResponse {
  particles_timeline: ParticleFrame[];
  cone: ConePolygon[];
  centroid_path: Geom;
  impact_flags: ImpactFlag[];
  processing: ProcessingStep[];
  provenance: Provenance;
}

export interface ScoreBreakdown {
  proximity: number;
  temporal_overlap: number;
  heading_consistency: number;
  ais_gap: number;
  speed_anomaly: number;
}

export interface ScoreWeights {
  proximity: number;
  temporal_overlap: number;
  ais_gap: number;
  heading_consistency: number;
  speed_anomaly: number;
}

export interface AISGap {
  start_utc: string;
  end_utc: string;
  duration_minutes: number;
  interpolated_path: Geom | null;
  overlaps_origin_window: boolean;
}

export type CandidateFlag =
  | "DARK_VESSEL"
  | "COURSE_DEVIATION"
  | "SLOW_STEAMING"
  | "CLOSEST_APPROACH";

export interface VesselCandidate {
  mmsi: string;
  name: string;
  vessel_type: string;
  track: Geom;
  score: number;
  rank: number;
  flags: CandidateFlag[];
  breakdown: ScoreBreakdown;
  gaps: AISGap[];
  closest_approach_km: number;
  closest_approach_utc: string | null;
  narrative: string;
}

export interface AttributeResponse {
  total_vessels_in_region: number;
  after_filter: number;
  candidates: VesselCandidate[];
  weights: ScoreWeights;
  all_tracks: FeatureColl | null;
  processing: ProcessingStep[];
  provenance: Provenance;
}

export interface ReportContent {
  case_id: string;
  generated_at: string;
  scene_id: string;
  acquired_at: string;
  processing_chain: ProcessingStep[];
  detection_summary: Record<string, unknown>;
  origin_summary: Record<string, unknown>;
  candidates: VesselCandidate[];
  limitations: string[];
  provenance: Provenance;
}

/** The order of the five scoring factors as shown in the UI. */
export const SCORE_FACTORS: {
  key: keyof ScoreBreakdown;
  label: string;
  hint: string;
}[] = [
  { key: "proximity", label: "Proximity to origin", hint: "Distance to the estimated release point, weighted by the cone's probability density" },
  { key: "temporal_overlap", label: "Temporal overlap", hint: "Vessel presence within the estimated release time window" },
  { key: "ais_gap", label: "AIS gap", hint: "Reporting gap overlapping the release window — the dark-vessel signal" },
  { key: "heading_consistency", label: "Heading consistency", hint: "Course alignment with the observed slick axis" },
  { key: "speed_anomaly", label: "Speed anomaly", hint: "Slow steaming or unusual manoeuvre near the origin" },
];

export interface UploadRegion {
  contour: [number, number][];
  circle: { cx: number; cy: number; radius: number };
  confidence: number;
  reason: string;
  area_px: number;
  area_km2: number;
  contrast_db: number;
  thickness_um: number;
  volume_m3: number;
  volume_liters: number;
  volume_barrels: number;
  morphology: SlickGeometry;
  backscatter: BackscatterStats;
  /** Georeferenced ring; null unless lon/lat were supplied with the upload. */
  polygon?: Geom | null;
}

export interface UploadResponse {
  width: number;
  height: number;
  method: DetectionMethod;
  gsd_m: number;
  oil_regions: UploadRegion[];
  rejected_lookalikes: UploadRegion[];
  total_area_km2: number;
  total_volume_liters: number;
  total_volume_barrels: number;
  processing: ProcessingStep[];
  notes: string;
  /** FeatureCollection ready for MapLibre; null when the upload carried no
   *  lon/lat anchor, since there is then no honest georeferencing. */
  geojson?: GeoJSONFeatureCollection | null;
}

/** RFC 7946 FeatureCollection as returned by the detection endpoints.
 *  Morphology and backscatter fields are flattened into feature properties so
 *  MapLibre expressions can style directly off them. */
export interface GeoJSONFeatureCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: Geom;
    properties: Record<string, unknown> & {
      class: "oil" | "lookalike";
      confidence: number;
    };
  }[];
}
