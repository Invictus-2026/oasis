import type { HindcastResponse, ForecastResponse, AttributeResponse } from "../api/types";

// The mock forecast's natural compass heading (WNW ~306°).
// Computed from centroid_path start→end in mock/forecast.json.
const BASE_FORECAST_COMPASS = 305.9;

// Mock data is centered on this lon/lat — the centroid of the "Oil Spill
// Extent" traced off the bundled SAR scene (frontend/public/sar/scene-sar.png).
export const MOCK_CENTER: [number, number] = [-89.983125, 28.591429];

/** Rotate point p around pivot, then translate by [dx, dy]. */
function xfmPt(
  p: number[],
  pivot: [number, number],
  dx: number,
  dy: number,
  cosT: number,
  sinT: number,
  aspect: number
): [number, number] {
  const x = (p[0] - pivot[0]) * aspect;
  const y = (p[1] - pivot[1]);
  const rx = x * cosT - y * sinT;
  const ry = x * sinT + y * cosT;
  return [rx / aspect + pivot[0] + dx, ry + pivot[1] + dy];
}

// Convert compass bearing (0=N, 90=E) to standard math angle in radians (0=E, CCW)
function compassToRad(c: number): number {
  return (90 - c) * (Math.PI / 180);
}

function makeXfm(pivot: [number, number], dx: number, dy: number, compassTarget: number) {
  const theta = compassToRad(compassTarget) - compassToRad(BASE_FORECAST_COMPASS);
  const aspect = Math.cos(pivot[1] * Math.PI / 180);
  const cosT = Math.cos(theta);
  const sinT = Math.sin(theta);
  return (p: number[]): [number, number] => xfmPt(p, pivot, dx, dy, cosT, sinT, aspect);
}

export function shiftForecast(
  mock: unknown,
  dx: number,
  dy: number,
  forecastCompass: number    // Particles drift IN this direction (same as wind)
): ForecastResponse {
  const m = JSON.parse(JSON.stringify(mock)) as ForecastResponse;
  const xfm = makeXfm(MOCK_CENTER, dx, dy, forecastCompass);

  m.particles_timeline.forEach(f => { f.points = f.points.map(xfm); });
  m.cone.forEach(c => {
    if (c.polygon.type === "Polygon")
      c.polygon.coordinates = c.polygon.coordinates.map(r => r.map(xfm));
  });
  if (m.centroid_path.type === "LineString")
    m.centroid_path.coordinates = m.centroid_path.coordinates.map(xfm);

  return m;
}

export function shiftHindcast(
  mock: unknown,
  dx: number,
  dy: number,
  forecastCompass: number    // Same rotation as forecast — the mock data is already opposite
): HindcastResponse {
  const m = JSON.parse(JSON.stringify(mock)) as HindcastResponse;
  const xfm = makeXfm(MOCK_CENTER, dx, dy, forecastCompass);

  m.particles_timeline.forEach(f => { f.points = f.points.map(xfm); });
  m.cone.forEach(c => {
    if (c.polygon.type === "Polygon")
      c.polygon.coordinates = c.polygon.coordinates.map(r => r.map(xfm));
  });
  m.origin_estimate.point = xfm(m.origin_estimate.point);

  return m;
}

export function shiftAttribution(
  mock: unknown,
  dx: number,
  dy: number,
  forecastCompass: number
): AttributeResponse {
  const m = JSON.parse(JSON.stringify(mock)) as AttributeResponse;
  // Attribution tracks are in the hindcast frame — same rotation applies
  const xfm = makeXfm(MOCK_CENTER, dx, dy, forecastCompass);

  m.candidates.forEach(c => {
    if (c.track.type === "LineString")
      c.track.coordinates = c.track.coordinates.map(xfm);
    c.gaps.forEach(g => {
      if (g.interpolated_path?.type === "LineString")
        g.interpolated_path.coordinates = g.interpolated_path.coordinates.map(xfm);
    });
  });

  if (m.all_tracks) {
    m.all_tracks.features.forEach(f => {
      if (f.geometry.type === "LineString")
        f.geometry.coordinates = f.geometry.coordinates.map(xfm);
    });
  }

  return m;
}
