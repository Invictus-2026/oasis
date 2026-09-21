/** Formatting helpers. Kept in one place so readouts stay consistent. */

export const km = (v: number, d = 1) => `${v.toFixed(d)} km`;

/** Below this, a km² reading at 1 decimal place rounds to "0.0" and reads as
 *  missing data rather than a genuinely small area (e.g. a cropped/thumbnail
 *  upload) — switch to m² so a real, tiny spill still shows a real number. */
const KM2_TO_M2_THRESHOLD = 0.05;

export const km2 = (v: number, d = 1) => {
  if (v > 0 && v < KM2_TO_M2_THRESHOLD) {
    return `${Math.round(v * 1e6).toLocaleString()} m²`;
  }
  return `${v.toFixed(d)} km²`;
};
export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const deg = (v: number) => `${v.toFixed(0)}°`;

export const utc = (iso: string) =>
  new Date(iso).toISOString().replace("T", " ").slice(0, 16) + "Z";

export const lonLat = ([lon, lat]: [number, number]) =>
  `${Math.abs(lat).toFixed(3)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(3)}°${lon >= 0 ? "E" : "W"}`;

export const hours = (v: number) => `${v % 1 === 0 ? v.toFixed(0) : v.toFixed(1)} h`;

/** Ratios read as measurements, not identifiers — round them. 37.96:1 is
 *  false precision the geometry doesn't actually support at a glance. */
export const ratio = (v: number) => `${Math.round(v)}:1`;

/** Compass bearing to a cardinal label, for readouts that a judge reads aloud. */
export function bearingLabel(d: number): string {
  const names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return names[Math.round((((d % 360) + 360) % 360) / 22.5) % 16];
}
