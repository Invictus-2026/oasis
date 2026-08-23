/** Formatting helpers. Kept in one place so readouts stay consistent. */

export const km = (v: number, d = 1) => `${v.toFixed(d)} km`;
export const km2 = (v: number, d = 1) => `${v.toFixed(d)} km²`;
export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const deg = (v: number) => `${v.toFixed(0)}°`;

export const utc = (iso: string) =>
  new Date(iso).toISOString().replace("T", " ").slice(0, 16) + "Z";

export const lonLat = ([lon, lat]: [number, number]) =>
  `${Math.abs(lat).toFixed(3)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(3)}°${lon >= 0 ? "E" : "W"}`;

export const hours = (v: number) => `${v % 1 === 0 ? v.toFixed(0) : v.toFixed(1)} h`;

/** Compass bearing to a cardinal label, for readouts that a judge reads aloud. */
export function bearingLabel(d: number): string {
  const names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return names[Math.round((((d % 360) + 360) % 360) / 22.5) % 16];
}
