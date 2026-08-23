/**
 * API client with a mock fallback.
 *
 * Demo rule: the UI must never show a blank screen. If the backend is down or
 * slow, we fall back to the bundled fixtures and surface a visible banner
 * rather than failing. Set VITE_FORCE_MOCK=1 to work offline deliberately.
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

const FORCE_MOCK = import.meta.env.VITE_FORCE_MOCK === "1";
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
    console.warn(`[SpillTrace] ${path} failed, using bundled fixture:`, err);
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

export const hindcast = (slickId: string, hours = 24, nParticles = 500) =>
  call<HindcastResponse>(
    "/api/drift/hindcast",
    { slick_id: slickId, hours, n_particles: nParticles },
    hindcastMock,
  );

export const forecast = (slickId: string, hours = 12, nParticles = 500) =>
  call<ForecastResponse>(
    "/api/drift/forecast",
    { slick_id: slickId, hours, n_particles: nParticles },
    forecastMock,
  );

export const attribute = (origin: LonLat, originTimeUtc: string, radiusKm = 25) =>
  call<AttributeResponse>(
    "/api/attribute",
    { origin, origin_time_utc: originTimeUtc, search_radius_km: radiusKm },
    attributionMock,
  );

export const report = (caseId: string, slickId: string) =>
  call<ReportContent>("/api/report", { case_id: caseId, slick_id: slickId }, null);
