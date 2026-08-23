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
  /** Index into the hindcast/forecast particle timeline, for the animation. */
  frameIndex: number;
  selectedMmsi: string | null;
  onSelectVessel: (mmsi: string | null) => void;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** A no-network raster style. Demo rule: nothing on screen may depend on the
 *  venue's wifi, so the basemap is a flat colour plus our own data. */
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#0a1526" } }],
};

export default function MapView({
  caseMeta, detection, hindcast, forecast, attribution,
  layers, frameIndex, selectedMmsi, onSelectVessel,
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
                        "particles", "forecastCone", "forecastPath", "tracks", "origin"]) {
        m.addSource(id, { type: "geojson", data: EMPTY });
      }

      // With no network basemap the ocean is a flat colour, and a flat colour
      // is indistinguishable from a broken map. A graticule and an AOI frame
      // give the view scale and orientation before any data exists.
      m.addLayer({ id: "graticule-line", source: "graticule", type: "line",
        paint: { "line-color": "#1d3350", "line-width": 1 } });
      m.addLayer({ id: "frame-line", source: "frame", type: "line",
        paint: { "line-color": "#31527d", "line-width": 1.5, "line-dasharray": [4, 3] } });

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
        paint: { "fill-color": "rgba(201, 139, 240, 0.13)" } });
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
        paint: { "circle-radius": 1.9, "circle-color": C.particle, "circle-opacity": 0.55 } });

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

      m.addLayer({ id: "origin-dot", source: "origin", type: "circle",
        paint: { "circle-radius": 5, "circle-color": C.origin,
                 "circle-stroke-color": "#062028", "circle-stroke-width": 2 } });

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
    const frame = frames[Math.min(frameIndex, frames.length - 1)];
    const t = frame?.t_offset_hours;

    // Animating frames: the ensemble at this instant.
    for (const p of [50, 90] as const) {
      const ring = hindcast?.cone.find(
        (c) => c.kind === "frame" && c.percentile === p && c.t_offset_hours === t,
      );
      setData(`cone${p}`, {
        type: "FeatureCollection",
        features: layers.cone && ring
          ? [{ type: "Feature", geometry: ring.polygon, properties: { percentile: p } }]
          : [],
      });
    }

    setData("particles", {
      type: "FeatureCollection",
      features: layers.particles && frame
        ? frame.points.map((pt) => ({
            type: "Feature", geometry: { type: "Point", coordinates: pt }, properties: {},
          }))
        : [],
    });

    // The origin region and marker appear only once the run has settled.
    // Showing them mid-animation would imply more certainty than the ensemble
    // has yet produced.
    const atEnd = frames.length > 0 && frameIndex >= frames.length - 1;
    for (const p of [50, 90] as const) {
      const ring = hindcast?.cone.find((c) => c.kind === "origin" && c.percentile === p);
      setData(`originRegion${p}`, {
        type: "FeatureCollection",
        features: layers.cone && atEnd && ring
          ? [{ type: "Feature", geometry: ring.polygon, properties: { percentile: p } }]
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
  }, [ready, hindcast, frameIndex, layers.cone, layers.particles]);

  // ---- forecast ---------------------------------------------------------
  useEffect(() => {
    if (!ready) return;
    const outer = forecast?.cone.filter((c) => c.percentile === 90) ?? [];
    setData("forecastCone", {
      type: "FeatureCollection",
      features: layers.forecast
        ? outer.map((c) => ({
            type: "Feature", geometry: c.polygon,
            properties: { t: c.t_offset_hours },
          }))
        : [],
    });
    setData("forecastPath", {
      type: "FeatureCollection",
      features: layers.forecast && forecast
        ? [{ type: "Feature", geometry: forecast.centroid_path, properties: {} }]
        : [],
    });
  }, [ready, forecast, layers.forecast]);

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

  return <div ref={container} className="absolute inset-0 h-full w-full" />;
}
