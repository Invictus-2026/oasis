/**
 * API client with a mock fallback.
 *
 * Demo rule: the UI must never show a blank screen. If the backend is down or
 * slow, we fall back to the bundled fixtures and surface a visible banner
 * rather than failing.
 *
 * The bundled fixtures are hand-georeferenced to the SAR scene shipped in
 * public/sar/, so for the presentation build they are the source of truth and
 * the network is not consulted at all. Set VITE_USE_BACKEND=1 to talk to the
 * live pipeline instead (or VITE_FORCE_MOCK=1 to pin fixtures explicitly).
 */

import caseMock from "../mock/case.json";
import detectionMock from "../mock/detection.json";
import hindcastMock from "../mock/hindcast.json";
import forecastMock from "../mock/forecast.json";
import attributionMock from "../mock/attribution.json";

import type {
  AttributeResponse,
  CaseMeta,
  DetectResponse,
  DetectionMethod,
  ForecastResponse,
  HindcastResponse,
  LonLat,
  ReportContent,
} from "./types";

const FORCE_MOCK =
  import.meta.env.VITE_FORCE_MOCK === "1" || import.meta.env.VITE_USE_BACKEND !== "1";
const TIMEOUT_MS = 8000;

export type DataMode = "live" | "mock";

let dataMode: DataMode = FORCE_MOCK ? "mock" : "live";
export const getDataMode = (): DataMode => dataMode;

const listeners = new Set<(m: DataMode) => void>();
export function onDataModeChange(fn: (m: DataMode) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function setMode(m: DataMode) {
  if (m !== dataMode) {
    dataMode = m;
    listeners.forEach((fn) => fn(m));
  }
}

async function call<T>(path: string, body: unknown, fallback: unknown): Promise<T> {
  if (FORCE_MOCK) return fallback as T;

  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctl.signal,
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    setMode("live");
    return (await res.json()) as T;
  } catch (err) {
    console.warn(`[OASIS] ${path} failed, using bundled fixture:`, err);
    setMode("mock");
    return fallback as T;
  } finally {
    clearTimeout(timer);
  }
}

export const getCase = () =>
  call<CaseMeta>("/api/case", undefined, caseMock);

export const detect = (method: DetectionMethod = "classical") =>
  call<DetectResponse>("/api/detect", { method }, detectionMock);

export const hindcast = (slickId: string, hours = 24, nParticles = 500, customPolygon?: GeoJSON.Polygon, mockWindDir?: number) =>
  call<HindcastResponse>(
    "/api/drift/hindcast",
    {
      slick_id: slickId,
      hours,
      n_particles: nParticles,
      custom_polygon: customPolygon,
      mock_wind_dir_deg: mockWindDir,
    },
    hindcastMock,
  );

export const forecast = (slickId: string, hours = 12, nParticles = 500, customPolygon?: GeoJSON.Polygon, mockWindDir?: number) =>
  call<ForecastResponse>(
    "/api/drift/forecast",
    {
      slick_id: slickId,
      hours,
      n_particles: nParticles,
      custom_polygon: customPolygon,
      mock_wind_dir_deg: mockWindDir,
    },
    forecastMock,
  );

/** Builds a rough circular polygon (Phase 7's AttributeRequest wants a
 *  region, not a point) around the hindcast origin estimate at the given
 *  radius in km. A coarse approximation is fine here: this is the ORIGIN
 *  REGION input to step 1's spatial filter, not a geometry the UI renders. */
function circleRegion([lon, lat]: LonLat, radiusKm: number, steps = 24): GeoJSON.Polygon {
  const kmPerDegLat = 110.574;
  const kmPerDegLon = 111.32 * Math.cos((lat * Math.PI) / 180);
  const ring: LonLat[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = (2 * Math.PI * i) / steps;
    ring.push([lon + (radiusKm * Math.cos(t)) / kmPerDegLon, lat + (radiusKm * Math.sin(t)) / kmPerDegLat]);
  }
  return { type: "Polygon", coordinates: [ring] };
}

export const attribute = (
  origin: LonLat,
  originTimeUtc: string,
  opts?: {
    uncertaintyRadiusKm?: number;
    timeWindowHours?: [number, number];
    driftBearingDeg?: number;
    counterfactualTopN?: number;
  },
) => {
  const radiusKm = opts?.uncertaintyRadiusKm ?? 25;
  const [winLo, winHi] = opts?.timeWindowHours ?? [0, 6];
  const centre = new Date(originTimeUtc).getTime();
  const start = new Date(centre - winHi * 3600_000).toISOString();
  const end = new Date(centre + winLo * 3600_000).toISOString();

  return call<AttributeResponse>(
    "/api/attribute",
    {
      origin_region: circleRegion(origin, Math.max(radiusKm, 5)),
      release_window_start_utc: start,
      release_window_end_utc: end,
      drift_bearing_deg: opts?.driftBearingDeg ?? 48.0,
      search_radius_km: radiusKm,
      counterfactual_top_n: opts?.counterfactualTopN ?? 5,
    },
    attributionMock,
  );
};

export const report = (caseId: string, slickId: string) =>
  call<ReportContent>("/api/report", { case_id: caseId, slick_id: slickId }, null);

export const reroute = (req: import("./types").RerouteRequest) =>
  call<import("./types").RerouteResponse>("/api/vessel/reroute", req, {
    original_path: [req.start_point, req.end_point],
    rerouted_path: [req.start_point, req.end_point],
    distance_original_km: 100,
    distance_rerouted_km: 100,
    original_time_hours: 5.4,
    rerouted_time_hours: 5.4,
    extra_time_hours: 0,
    extra_fuel_tons: 0,
    is_rerouted: false,
    processing_time_ms: 10
  });
