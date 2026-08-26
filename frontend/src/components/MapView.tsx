import maplibregl from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type {
  AttributeResponse,
  CaseMeta,
  DetectResponse,
  ForecastResponse,
  HindcastResponse,
} from "../api/types";
import { C } from "../lib/theme";

export interface LayerVisibility {
  sar: boolean;
  slick: boolean;
  lookalikes: boolean;
  cone: boolean;
  particles: boolean;
  forecast: boolean;
  tracks: boolean;
}

interface Props {
  caseMeta: CaseMeta | null;
  detection: DetectResponse | null;
  hindcast: HindcastResponse | null;
  forecast: ForecastResponse | null;
  attribution: AttributeResponse | null;
  layers: LayerVisibility;
  hindcastIndex: number;
  forecastIndex: number;
  selectedMmsi: string | null;
  onSelectVessel: (mmsi: string | null) => void;
  /** A new object (even with the same id) re-triggers the fly-to, so clicking
   *  "View on SAR" twice in a row still refocuses. */
  focusRequest: { id: string; nonce: number } | null;
  mockWindDir?: number;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** Nearest vertex on a track to a target point. Planar distance is fine at
 *  this scale/zoom — this is a visual "here's roughly where they meet"
 *  connector, not a geodesic claim. */
function nearestVertex(coords: [number, number][], target: [number, number]): [number, number] {
  let best = coords[0];
  let bestD = Infinity;
  for (const c of coords) {
    const d = (c[0] - target[0]) ** 2 + (c[1] - target[1]) ** 2;
    if (d < bestD) { bestD = d; best = c; }
  }
  return best;
}

/** A no-network raster style. Demo rule: nothing on screen may depend on the
 *  venue's wifi, so the basemap is a flat colour plus our own data. */
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#e2e8f0" } }], // Light theme ocean color
};

export default function MapView({
  caseMeta, detection, hindcast, forecast, attribution,
  layers, hindcastIndex, forecastIndex, selectedMmsi, onSelectVessel, focusRequest, mockWindDir,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const resizeObs = useRef<ResizeObserver | null>(null);
  // State, not a ref: when the style finishes loading the data effects below
  // must re-run. A ref flips silently and they would never fire again.
  const [ready, setReady] = useState(false);
  const onSelect = useRef(onSelectVessel);
  onSelect.current = onSelectVessel;

  // ---- init -------------------------------------------------------------
  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [-90.0, 28.55],
      zoom: 8.2,
      attributionControl: false,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: true }), "bottom-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

    // MapLibre measures the container once at construction. Inside a flex
    // layout that measurement can land before the browser has resolved the
    // final height, and the canvas silently falls back to 400x300 — a map that
    // renders correctly into a corner too small to see. Observing the container
    // and resizing keeps the canvas correct on first paint and on every window
    // resize during a demo.
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(container.current!);
    resizeObs.current = ro;

    // Surface style/render failures instead of leaving a silently blank canvas.
    m.on("error", (e) => console.error("[SpillTrace] map error:", e?.error ?? e));

    m.on("load", () => {
      for (const id of ["graticule", "frame", "cone90", "cone50", "originRegion90",
                        "originRegion50", "lookalikes", "slick",
                        "particles", "forecastCone", "forecastPath", "tracks", "origin",
                        "gap", "connector", "windField"]) {
        m.addSource(id, { type: "geojson", data: EMPTY });
      }

      // With no network basemap the ocean is a flat colour.
      // Light theme graticules
      m.addLayer({ id: "graticule-line", source: "graticule", type: "line",
        paint: { "line-color": "#94a3b8", "line-width": 1, "line-opacity": 0.4 } });
      m.addLayer({ id: "frame-line", source: "frame", type: "line",
        paint: { "line-color": "#64748b", "line-width": 1.5, "line-dasharray": [4, 3] } });
        
      m.addLayer({ id: "windField-line", source: "windField", type: "line",
        paint: { "line-color": "#9ca3af", "line-width": 1.5, "line-opacity": 0.3 } });

      // Draw order matters: cones sit under everything, the slick sits above
      // the look-alikes so the retained detection reads as primary.
      m.addLayer({ id: "cone90-fill", source: "cone90", type: "fill",
        paint: { "fill-color": C.cone90 } });
      m.addLayer({ id: "cone50-fill", source: "cone50", type: "fill",
        paint: { "fill-color": C.cone50 } });
      m.addLayer({ id: "cone90-line", source: "cone90", type: "line",
        paint: { "line-color": C.coneLine, "line-width": 1, "line-opacity": 0.5, "line-dasharray": [3, 2] } });

      // The answer: where the release plausibly happened, pooled over the whole
      // age window. Drawn solid and persistently, unlike the animating frames.
      m.addLayer({ id: "originRegion90-fill", source: "originRegion90", type: "fill",
        paint: { "fill-color": "rgba(53, 200, 216, 0.13)" } });
      m.addLayer({ id: "originRegion50-fill", source: "originRegion50", type: "fill",
        paint: { "fill-color": "rgba(53, 200, 216, 0.26)" } });
      m.addLayer({ id: "originRegion90-line", source: "originRegion90", type: "line",
        paint: { "line-color": C.coneLine, "line-width": 1.8 } });
      m.addLayer({ id: "originRegion50-line", source: "originRegion50", type: "line",
        paint: { "line-color": C.coneLine, "line-width": 1, "line-opacity": 0.7 } });

      m.addLayer({ id: "forecastCone-fill", source: "forecastCone", type: "fill",
        paint: { "fill-color": "rgba(147, 51, 234, 0.13)" } });
      m.addLayer({ id: "forecastPath-line", source: "forecastPath", type: "line",
        paint: { "line-color": C.forecast, "line-width": 2.5, "line-dasharray": [2, 1.5] } });

      m.addLayer({ id: "lookalikes-fill", source: "lookalikes", type: "fill",
        paint: { "fill-color": C.rejectFill } });
      m.addLayer({ id: "lookalikes-line", source: "lookalikes", type: "line",
        paint: { "line-color": C.reject, "line-width": 1.5, "line-dasharray": [2, 2] } });

      m.addLayer({ id: "slick-fill", source: "slick", type: "fill",
        paint: { "fill-color": C.slickFill } });
      m.addLayer({ id: "slick-line", source: "slick", type: "line",
        paint: { "line-color": C.slick, "line-width": 2 } });

      m.addLayer({ id: "particles-circle", source: "particles", type: "circle",
        paint: { "circle-radius": 2, "circle-color": C.particle, "circle-opacity": 0.55 } });
        
      m.addSource("forecastParticles", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "forecastParticles-circle", source: "forecastParticles", type: "circle",
        paint: { "circle-radius": 2, "circle-color": C.forecast, "circle-opacity": 0.55 } });

      // Selected vessel is drawn bright; everything else dims. Colour is
      // driven by feature properties so selection is a paint update, not a
      // source rebuild.
      m.addLayer({ id: "tracks-line", source: "tracks", type: "line",
        paint: {
          "line-color": ["case", ["get", "selected"], C.suspect,
                         ["get", "suspect"], C.suspect, C.vessel],
          "line-width": ["case", ["get", "selected"], 3.5, 1.6],
          "line-opacity": ["case", ["get", "dimmed"], 0.15, 0.85],
        } });

      // The evidence connective tissue: what links a selected vessel to the
      // spill. The gap is where its AIS went dark; the connector is a plain
      // "this is how close it came" line to the origin — not a claim, a ruler.
      // Plain white rather than a semantic colour: a DARK_VESSEL's track is
      // already drawn in the suspect red, and a same-colour overlay would be
      // invisible exactly where the gap matters most.
      m.addLayer({ id: "gap-line", source: "gap", type: "line",
        paint: { "line-color": "#ffffff", "line-width": 4, "line-dasharray": [1.4, 1.2],
                 "line-opacity": 0.9 } });
      m.addLayer({ id: "connector-line", source: "connector", type: "line",
        paint: { "line-color": C.coneLine, "line-width": 1.2, "line-dasharray": [1.5, 1.5],
                 "line-opacity": 0.6 } });

      m.addLayer({ id: "origin-dot", source: "origin", type: "circle",
        paint: { "circle-radius": 6, "circle-color": C.origin,
                 "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });

      m.on("click", "tracks-line", (e) => {
        const mmsi = e.features?.[0]?.properties?.mmsi;
        if (mmsi) onSelect.current(String(mmsi));
      });
      m.on("mouseenter", "tracks-line", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "tracks-line", () => { m.getCanvas().style.cursor = ""; });

      setReady(true);
      m.triggerRepaint();
    });

    map.current = m;
    return () => {
      resizeObs.current?.disconnect();
      resizeObs.current = null;
      m.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  const setData = (id: string, data: GeoJSON.FeatureCollection) => {
    const src = map.current?.getSource(id) as maplibregl.GeoJSONSource | undefined;
    src?.setData(data);
  };

  // ---- fit to the case bbox, draw the graticule and AOI frame ----------
  useEffect(() => {
    if (!map.current || !caseMeta) return;
    const b = caseMeta.bbox;
    map.current.fitBounds([[b.west, b.south], [b.east, b.north]], { padding: 60, duration: 700 });

    if (!ready) return;
    const step = 0.25;
    const lines: GeoJSON.Feature[] = [];
    const from = (v: number) => Math.ceil(v / step) * step;
    for (let lon = from(b.west); lon < b.east; lon += step) {
      lines.push({ type: "Feature", properties: {},
        geometry: { type: "LineString", coordinates: [[lon, b.south], [lon, b.north]] } });
    }
    for (let lat = from(b.south); lat < b.north; lat += step) {
      lines.push({ type: "Feature", properties: {},
        geometry: { type: "LineString", coordinates: [[b.west, lat], [b.east, lat]] } });
    }
    setData("graticule", { type: "FeatureCollection", features: lines });
    setData("frame", {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: { type: "LineString",
        coordinates: [[b.west, b.south], [b.east, b.south], [b.east, b.north],
                      [b.west, b.north], [b.west, b.south]] } }],
    });
  }, [caseMeta, ready]);

  // ---- SAR overlay ------------------------------------------------------
  // Added in its own effect rather than in the style-load handler: the case is
  // fetched asynchronously and usually arrives AFTER the style has loaded, so
  // adding it during load would silently skip the imagery.
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !caseMeta?.sar_overlay_url || m.getSource("sar")) return;

    const b = caseMeta.bbox;
    m.addSource("sar", {
      type: "image",
      url: caseMeta.sar_overlay_url,
      // Image sources take corners clockwise from the top-left.
      coordinates: [
        [b.west, b.north], [b.east, b.north],
        [b.east, b.south], [b.west, b.south],
      ],
    });
    // Beneath every vector layer, so the imagery is context and never
    // obscures the detection it is supporting.
    m.addLayer(
      { id: "sar-raster", source: "sar", type: "raster",
        paint: { "raster-opacity": 0.95, "raster-fade-duration": 300 } },
      "graticule-line",
    );
  }, [ready, caseMeta]);

  useEffect(() => {
    if (!ready || !map.current?.getLayer("sar-raster")) return;
    map.current.setLayoutProperty("sar-raster", "visibility", layers.sar ? "visible" : "none");
  }, [ready, layers.sar, caseMeta]);

  // ---- detection --------------------------------------------------------
  useEffect(() => {
    if (!ready) return;
    setData("slick", {
      type: "FeatureCollection",
      features: layers.slick && detection
        ? detection.slicks.map((s) => ({
            type: "Feature", geometry: s.polygon,
            properties: { id: s.id, confidence: s.confidence },
          }))
        : [],
    });
    setData("lookalikes", {
      type: "FeatureCollection",
      features: layers.lookalikes && detection
        ? detection.rejected_lookalikes.map((r) => ({
            type: "Feature", geometry: r.polygon,
            properties: { id: r.id, reason: r.reason },
          }))
        : [],
    });
  }, [ready, detection, layers.slick, layers.lookalikes]);

  // ---- hindcast cone, particles, origin ---------------------------------
  useEffect(() => {
    if (!ready) return;
    const frames = hindcast?.particles_timeline ?? [];
    const frame = frames[Math.min(hindcastIndex, frames.length - 1)];
    const t = frame?.t_offset_hours;

    // Origin estimation should be tighter than the forecast spread.
    // Shrink hindcast geometry toward its centroid by this factor.
    const SHRINK = 0.45;
    function shrinkPoly(geom: GeoJSON.Geometry): GeoJSON.Geometry {
      if (geom.type !== "Polygon") return geom;
      const coords = geom.coordinates.map(ring => {
        const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
        const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
        return ring.map(p => [cx + (p[0] - cx) * SHRINK, cy + (p[1] - cy) * SHRINK]);
      });
      return { ...geom, coordinates: coords };
    }

    // Animating frames: the ensemble cone at this instant.
    for (const p of [50, 90] as const) {
      const ring = hindcast?.cone.find(
        (c) => c.percentile === p && c.t_offset_hours === t,
      );
      setData(`cone${p}`, {
        type: "FeatureCollection",
        features: layers.cone && ring
          ? [{ type: "Feature", geometry: shrinkPoly(ring.polygon), properties: { percentile: p } }]
          : [],
      });
    }

    // Shrink particles toward their frame centroid
    let particleFeatures: GeoJSON.Feature[] = [];
    if (layers.particles && frame) {
      const cx = frame.points.reduce((s, p) => s + p[0], 0) / frame.points.length;
      const cy = frame.points.reduce((s, p) => s + p[1], 0) / frame.points.length;
      particleFeatures = frame.points.map((pt) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [
          cx + (pt[0] - cx) * SHRINK,
          cy + (pt[1] - cy) * SHRINK,
        ] },
        properties: {},
      }));
    }
    setData("particles", { type: "FeatureCollection", features: particleFeatures });

    // The origin region and marker appear only once the run has settled.
    const atEnd = frames.length > 0 && hindcastIndex >= frames.length - 1;
    const minT = hindcast ? Math.min(...hindcast.cone.map(c => c.t_offset_hours)) : 0;
    for (const p of [50, 90] as const) {
      const ring = hindcast?.cone.find(
        (c) => c.percentile === p && c.t_offset_hours === minT,
      );
      setData(`originRegion${p}`, {
        type: "FeatureCollection",
        features: layers.cone && atEnd && ring
          ? [{ type: "Feature", geometry: shrinkPoly(ring.polygon), properties: { percentile: p } }]
          : [],
      });
    }

    const o = hindcast?.origin_estimate;
    setData("origin", {
      type: "FeatureCollection",
      features: atEnd && o
        ? [{ type: "Feature", geometry: { type: "Point", coordinates: o.point }, properties: {} }]
        : [],
    });
  }, [ready, hindcast, hindcastIndex, layers.cone, layers.particles]);

  // ---- forecast ---------------------------------------------------------
  useEffect(() => {
    if (!ready) return;
    const forecastFrames = forecast?.particles_timeline ?? [];
    const forecastFrame = forecastFrames[Math.min(forecastIndex, forecastFrames.length - 1)];
    const forecastT = forecastFrame?.t_offset_hours ?? 0;

    // Shrink forecast by 0.55. It should still be larger than origin (0.45)
    // but not overwhelmingly massive when simulated out to 72 hours.
    const SHRINK = 0.55;
    function shrinkPoly(geom: GeoJSON.Geometry): GeoJSON.Geometry {
      if (geom.type !== "Polygon") return geom;
      const coords = geom.coordinates.map(ring => {
        const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
        const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
        return ring.map(p => [cx + (p[0] - cx) * SHRINK, cy + (p[1] - cy) * SHRINK]);
      });
      return { ...geom, coordinates: coords };
    }

    // Progressively expand the cone by filtering up to the current timestamp
    const outer = forecast?.cone.filter((c) => c.percentile === 90 && c.t_offset_hours <= forecastT) ?? [];
    setData("forecastCone", {
      type: "FeatureCollection",
      features: layers.forecast
        ? outer.map((c) => ({
            type: "Feature", geometry: shrinkPoly(c.polygon),
            properties: { t: c.t_offset_hours },
          }))
        : [],
    });
    
    // Also shrink the path relative to its own centroid so it matches the scaled cone
    let shrunkPath = forecast?.centroid_path;
    if (shrunkPath && shrunkPath.type === "LineString") {
      const cx = shrunkPath.coordinates.reduce((s, p) => s + p[0], 0) / shrunkPath.coordinates.length;
      const cy = shrunkPath.coordinates.reduce((s, p) => s + p[1], 0) / shrunkPath.coordinates.length;
      shrunkPath = {
        ...shrunkPath,
        coordinates: shrunkPath.coordinates.map(p => [cx + (p[0] - cx) * SHRINK, cy + (p[1] - cy) * SHRINK])
      };
    }
    
    setData("forecastPath", {
      type: "FeatureCollection",
      features: layers.forecast && shrunkPath
        ? [{ type: "Feature", geometry: shrunkPath, properties: {} }]
        : [],
    });
    
    // Also render forecast particles if they exist
    let particleFeatures: GeoJSON.Feature[] = [];
    if (layers.particles && forecastFrame) {
      const cx = forecastFrame.points.reduce((s, p) => s + p[0], 0) / forecastFrame.points.length;
      const cy = forecastFrame.points.reduce((s, p) => s + p[1], 0) / forecastFrame.points.length;
      particleFeatures = forecastFrame.points.map((pt) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [
          cx + (pt[0] - cx) * SHRINK,
          cy + (pt[1] - cy) * SHRINK,
        ] },
        properties: {},
      }));
    }
    setData("forecastParticles", { type: "FeatureCollection", features: particleFeatures });
  }, [ready, forecast, layers.forecast, layers.particles, forecastIndex]);

  // ---- vessel tracks ----------------------------------------------------
  useEffect(() => {
    if (!ready) return;
    setData("tracks", {
      type: "FeatureCollection",
      features: layers.tracks && attribution
        ? attribution.candidates.map((c) => ({
            type: "Feature",
            geometry: c.track,
            properties: {
              mmsi: c.mmsi,
              name: c.name,
              suspect: c.flags.includes("DARK_VESSEL"),
              selected: c.mmsi === selectedMmsi,
              dimmed: selectedMmsi !== null && c.mmsi !== selectedMmsi,
            },
          }))
        : [],
    });
  }, [ready, attribution, selectedMmsi, layers.tracks]);

  // ---- selected vessel: its AIS gap and its link to the origin ----------
  // The two marks that answer "why does this vessel relate to the spill":
  // where it went dark, and how close its track actually came.
  useEffect(() => {
    if (!ready) return;
    const candidate = layers.tracks
      ? attribution?.candidates.find((c) => c.mmsi === selectedMmsi) ?? null
      : null;

    const gap = candidate?.gaps.find((g) => g.overlaps_origin_window) ?? candidate?.gaps[0];
    setData("gap", {
      type: "FeatureCollection",
      features: gap?.interpolated_path
        ? [{ type: "Feature", geometry: gap.interpolated_path, properties: {} }]
        : [],
    });

    const origin = hindcast?.origin_estimate.point;
    const track = candidate?.track;
    setData("connector", {
      type: "FeatureCollection",
      features: candidate && origin && track?.type === "LineString"
        ? [{
            type: "Feature",
            properties: {},
            geometry: {
              type: "LineString",
              coordinates: [nearestVertex(track.coordinates as [number, number][], origin), origin],
            },
          }]
        : [],
    });
  }, [ready, attribution, selectedMmsi, hindcast, layers.tracks]);

  // ---- "View on SAR": fly to a ruled-out candidate ------------------------
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !focusRequest || !detection) return;
    const target = detection.rejected_lookalikes.find((r) => r.id === focusRequest.id);
    if (!target || target.polygon.type !== "Polygon") return;
    const ring = target.polygon.coordinates[0] as [number, number][];
    const lons = ring.map((p) => p[0]);
    const lats = ring.map((p) => p[1]);
    m.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 140, maxZoom: 12, duration: 700 },
    );
  }, [ready, focusRequest, detection]);

  // ---- Wind field --------------------------------------------------------
  useEffect(() => {
    if (!ready || !caseMeta || mockWindDir === undefined) return;
    const step = 0.25;
    const b = caseMeta.bbox;
    const features: GeoJSON.Feature[] = [];
    const rad = (90 - mockWindDir) * (Math.PI / 180);
    const arrowLen = 0.08;
    const headLen = 0.03;
    const headAngle = 30 * (Math.PI / 180);

    const dx = Math.cos(rad) * arrowLen;
    const dy = Math.sin(rad) * arrowLen;

    const hx1 = Math.cos(rad + Math.PI - headAngle) * headLen;
    const hy1 = Math.sin(rad + Math.PI - headAngle) * headLen;
    const hx2 = Math.cos(rad + Math.PI + headAngle) * headLen;
    const hy2 = Math.sin(rad + Math.PI + headAngle) * headLen;

    for (let lon = b.west + step / 2; lon < b.east; lon += step) {
      for (let lat = b.south + step / 2; lat < b.north; lat += step) {
        const endLon = lon + dx;
        const endLat = lat + dy;
        features.push({
          type: "Feature", properties: {},
          geometry: {
            type: "MultiLineString",
            coordinates: [
              [[lon, lat], [endLon, endLat]],
              [[endLon, endLat], [endLon + hx1, endLat + hy1]],
              [[endLon, endLat], [endLon + hx2, endLat + hy2]]
            ]
          }
        });
      }
    }
    setData("windField", { type: "FeatureCollection", features });
  }, [caseMeta, mockWindDir, ready]);

  return <div ref={container} className="absolute inset-0 h-full w-full" />;
}
