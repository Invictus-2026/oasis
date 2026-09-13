/** Ambient shipping-lane backdrop.
 *
 *  These are sample lanes, not AIS data — they exist so the ocean reads as
 *  trafficked water rather than empty blue. Two properties matter:
 *
 *  - **Deterministic.** A lane is derived from the integer cell it starts in,
 *    so panning away and back redraws exactly the same network. Nothing is
 *    stored; nothing animates.
 *  - **Unbounded.** Lanes are generated for whatever viewport is asked for,
 *    the same way the graticule is, so there is no edge of the world where
 *    traffic stops.
 */

export type Lane = GeoJSON.Feature<GeoJSON.LineString>;

/** Prevailing corridor bearings, in compass degrees. Real traffic bundles
 *  into a handful of corridors between port pairs, so picking from a small
 *  set makes lanes run parallel and cross at angles — a random bearing per
 *  lane just looks like scribble. */
const CORRIDORS = [18, 72, 121, 164];

/** Integer hash → [0, 1). `salt` gives each cell several independent draws. */
function rand(ix: number, iy: number, salt: number): number {
  let h = (ix | 0) * 374761393 + (iy | 0) * 668265263 + salt * 2246822519;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** Lane length as a multiple of the cell size. Lanes overrun their own cell
 *  by design — that overlap is what turns per-cell lanes into a network. */
const LEN_CELLS_MIN = 2.5;
const LEN_CELLS_MAX = 6;
const SEGMENTS = 5;

/** Cell size for a given viewport span, quantised to halving steps so that
 *  zooming changes density in discrete jumps instead of continuously
 *  reshuffling every lane. Keeps the lane count roughly constant. */
function cellSizeFor(span: number): number {
  const target = span / 10;
  const pow = Math.round(Math.log2(Math.max(target, 1e-6) / 0.05));
  return 0.05 * Math.pow(2, Math.max(0, pow));
}

/** Build the lane network covering a bounding box. `west`/`east` are passed
 *  through unwrapped, so a viewport spanning the antimeridian still works. */
export function buildLaneNetwork(
  west: number,
  south: number,
  east: number,
  north: number,
): Lane[] {
  const cell = cellSizeFor(Math.max(east - west, north - south));

  // Lanes anchored outside the viewport can still cross it, so widen the cell
  // sweep by the longest lane a cell can produce.
  const reach = cell * LEN_CELLS_MAX;
  const i0 = Math.floor((west - reach) / cell);
  const i1 = Math.ceil((east + reach) / cell);
  const j0 = Math.floor((south - reach) / cell);
  const j1 = Math.ceil((north + reach) / cell);

  const lanes: Lane[] = [];

  for (let i = i0; i <= i1; i++) {
    for (let j = j0; j <= j1; j++) {
      // Not every cell carries traffic — gaps keep the network from reading
      // as a grid.
      if (rand(i, j, 7) < 0.22) continue;

      const lon = (i + rand(i, j, 1)) * cell;
      const lat = (j + rand(i, j, 2)) * cell;

      const corridor = CORRIDORS[Math.floor(rand(i, j, 3) * CORRIDORS.length)];
      const jitter = (rand(i, j, 4) - 0.5) * 16;
      const len = cell * (LEN_CELLS_MIN + rand(i, j, 5) * (LEN_CELLS_MAX - LEN_CELLS_MIN));

      // Walk the lane out segment by segment, letting the course drift a
      // little — ships hold a heading but not to the degree.
      const coords: [number, number][] = [[lon, lat]];
      let bearing = corridor + jitter;
      let x = lon;
      let y = lat;

      for (let s = 0; s < SEGMENTS; s++) {
        bearing += (rand(i * 31 + s, j, 6) - 0.5) * 7;
        const rad = (90 - bearing) * (Math.PI / 180);
        const step = len / SEGMENTS;
        // Longitude degrees shrink with latitude; without this correction
        // lanes visibly flatten toward the poles.
        const cosLat = Math.max(Math.cos(y * (Math.PI / 180)), 0.2);
        x += (Math.cos(rad) * step) / cosLat;
        y += Math.sin(rad) * step;
        coords.push([x, y]);
      }

      lanes.push({
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: coords },
      });
    }
  }

  return lanes;
}
