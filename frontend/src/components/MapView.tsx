import maplibregl from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type {
  AttributeResponse,
  CaseMeta,
  CustomImageOverlay,
  DetectResponse,
  ForecastResponse,
  HindcastResponse,
  ReRouteOption,
} from "../api/types";
import { buildLaneNetwork } from "../lib/laneNetwork";
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
  activeSlickId?: string | null;
  mockWindDir?: number;
  customOverlays?: CustomImageOverlay[];
  offlineMap?: boolean;
  reRouteOption?: ReRouteOption | null;
  rerouteResult?: import("../api/types").RerouteResponse | null;
  onMapClick?: (lngLat: [number, number]) => void;
  simWaypoints?: Array<[number, number]>;
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

const easeOutCubic = (p: number) => 1 - Math.pow(1 - p, 3);

/** Scale a polygon's rings toward their own centroid by `factor` (0 = a
 *  point, 1 = full size). Used both for the fixed hindcast/forecast shrink
 *  and for the origin-region grow-in animation, which just ramps the same
 *  factor up over time instead of holding it constant. */
function scalePoly(geom: GeoJSON.Geometry, factor: number): GeoJSON.Geometry {
  if (geom.type !== "Polygon") return geom;
  const coords = geom.coordinates.map(ring => {
    const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
    const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    return ring.map(p => [cx + (p[0] - cx) * factor, cy + (p[1] - cy) * factor]);
  });
  return { ...geom, coordinates: coords };
}

/** Trim a line to the leading `progress` fraction of its length, interpolating
 *  the cut segment so the tip moves smoothly rather than jumping vertex to
 *  vertex — this is what makes a track look like it's drawing itself in. */
function sliceCoords(coords: [number, number][], progress: number): [number, number][] {
  if (progress >= 1 || coords.length < 2) return coords;
  if (progress <= 0) return [coords[0]];
  const dists: number[] = [0];
  for (let i = 1; i < coords.length; i++) {
    const dx = coords[i][0] - coords[i - 1][0];
    const dy = coords[i][1] - coords[i - 1][1];
    dists.push(dists[i - 1] + Math.sqrt(dx * dx + dy * dy));
  }
  const total = dists[dists.length - 1];
  if (total === 0) return coords;
  const target = total * progress;
  const out: [number, number][] = [coords[0]];
  for (let i = 1; i < coords.length; i++) {
    if (dists[i] <= target) {
      out.push(coords[i]);
    } else {
      const segStart = dists[i - 1], segEnd = dists[i];
      const t = segEnd > segStart ? (target - segStart) / (segEnd - segStart) : 0;
      const p0 = coords[i - 1], p1 = coords[i];
      out.push([p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t]);
      break;
    }
  }
  return out;
}

function sliceLine(geom: GeoJSON.Geometry, progress: number): GeoJSON.Geometry {
  if (progress >= 1) return geom;
  if (geom.type === "LineString") {
    return { ...geom, coordinates: sliceCoords(geom.coordinates as [number, number][], progress) };
  }
  if (geom.type === "MultiLineString") {
    return { ...geom, coordinates: geom.coordinates.map(line => sliceCoords(line as [number, number][], progress)) };
  }
  return geom;
}

function getLineEnd(geom: GeoJSON.Geometry, progress: number): [number, number] | null {
  const sliced = sliceLine(geom, progress);
  if (sliced.type === "LineString") {
    const coords = sliced.coordinates as [number, number][];
    return coords.length > 0 ? coords[coords.length - 1] : null;
  }
  if (sliced.type === "MultiLineString") {
    const lines = sliced.coordinates as [number, number][][];
    for (let i = lines.length - 1; i >= 0; i--) {
      if (lines[i].length > 0) return lines[i][lines[i].length - 1];
    }
  }
  return null;
}

/** A no-network raster style. Demo rule: nothing on screen may depend on the
 *  venue's wifi, so the basemap is a flat colour plus our own data. */
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#e2e8f0" } }], // Light theme ocean color
};

import { useTheme } from "../context/ThemeContext";

export default function MapView({
  caseMeta, detection, hindcast, forecast, attribution,
  layers, hindcastIndex, forecastIndex, selectedMmsi, onSelectVessel, focusRequest, activeSlickId, mockWindDir,
  customOverlays = [],
  reRouteOption,
  rerouteResult,
  onMapClick,
  simWaypoints = [],
}: Props) {
  const container = useRef < HTMLDivElement > (null);
  const map = useRef < maplibregl.Map | null > (null);
  const resizeObs = useRef < ResizeObserver | null > (null);

  const targetSlicks = detection?.slicks || [];

  // State, not a ref: when the style finishes loading the data effects below
  // must re-run. A ref flips silently and they would never fire again.
  const [ready, setReady] = useState(false);
  const { theme } = useTheme();

  useEffect(() => {
    if (!ready || !map.current) return;
    // Rich oceanic colors for offline map
    const mapBgColor = theme === "dark" ? "#181e1b" : "#e5eee5";
    map.current.setPaintProperty("bg", "background-color", mapBgColor);
    map.current.setPaintProperty("graticule-line", "line-color", theme === "dark" ? "#45554a" : "#b6cbb9");
    map.current.setPaintProperty("graticule-line", "line-opacity", theme === "dark" ? 0.6 : 0.5);
    map.current.setPaintProperty("shippingLanes-line", "line-color", theme === "dark" ? C.laneDark : C.lane);
    map.current.setPaintProperty("shippingLanes-line", "line-opacity", theme === "dark" ? 0.8 : 0.7);
  }, [theme, ready]);


  const onSelect = useRef(onSelectVessel);
  onSelect.current = onSelectVessel;
  
  const onMapClickRef = useRef(onMapClick);
  onMapClickRef.current = onMapClick;

  const tracksAnim = useRef<{ key: string; start: number | null; raf: number | null }>({ key: "", start: null, raf: null });
  const originGrowAnim = useRef<{ key: string; start: number | null; raf: number | null }>({ key: "", start: null, raf: null });
  const originMarkers = useRef<maplibregl.Marker[]>([]);

  // ---- init -------------------------------------------------------------
  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [-90.0, 27.05],
      zoom: 8.2,
      attributionControl: false,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: true }), "bottom-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

    const ro = new ResizeObserver(() => m.resize());
    ro.observe(container.current!);
    resizeObs.current = ro;

    m.on("error", (e) => console.error("[SpillTrace] map error:", e?.error ?? e));

    m.on("load", () => {
      for (const id of ["graticule", "shippingLanes", "frame", "cone90", "cone50", "originRegion90",
        "originRegion50", "lookalikes", "slick",
        "particles", "forecastCone", "forecastPath", "tracks", "origin",
        "gap", "connector", "windField", "currentField",
        "rerouteExclusion", "rerouteDirect", "reroutePath", "rerouteWaypoints",
        "simOriginalPath", "simReroutedPath", "simBoatIcon", "simClickWaypoints",
        "exclusionZone"]
      ) {
        m.addSource(id, { type: "geojson", data: EMPTY });
      }

      const shipSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" xmlns="http://www.w3.org/2000/svg"><path d="M2 12l2-6 8-2 8 2 2 6-4 10H6L2 12z" fill="#10b981"/></svg>`;
      const img = new Image(24, 24);
      img.onload = () => {
        if (!m.hasImage("green-boat-icon")) m.addImage("green-boat-icon", img);
      };
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(shipSvg);

      const redShipSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" xmlns="http://www.w3.org/2000/svg"><path d="M2 12l2-6 8-2 8 2 2 6-4 10H6L2 12z" fill="#f87171"/></svg>`;
      const imgRed = new Image(24, 24);
      imgRed.onload = () => {
        if (!m.hasImage("boat-icon")) m.addImage("boat-icon", imgRed);
      };
      imgRed.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(redShipSvg);

      const pinSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" xmlns="http://www.w3.org/2000/svg"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" fill="#3b82f6"/><circle cx="12" cy="10" r="3" fill="white"/></svg>`;
      const imgPin = new Image(24, 24);
      imgPin.onload = () => {
        if (!m.hasImage("blue-pin-icon")) m.addImage("blue-pin-icon", imgPin);
      };
      imgPin.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(pinSvg);

      // Graticules
      m.addLayer({
        id: "graticule-line", source: "graticule", type: "line",
        paint: { "line-color": "#93c5fd", "line-width": 1, "line-opacity": 0.5 }
      });

      // Ambient shipping traffic. Deliberately hairline and low-contrast:
      // this is texture that says "trafficked water", and it sits directly
      // above the graticule so every spill layer added below draws over it.
      m.addLayer({
        id: "shippingLanes-line", source: "shippingLanes", type: "line",
        paint: {
          "line-color": C.lane,
          "line-width": 0.5,
          "line-opacity": 0.7,
        }
      });

      m.addLayer({
        id: "windField-line", source: "windField", type: "line",
        paint: { "line-color": "#10b981", "line-width": 1.5, "line-opacity": 0.4 } // Emerald wind
      });

      m.addLayer({
        id: "currentField-line", source: "currentField", type: "line",
        paint: { "line-color": "#3b82f6", "line-width": 1.5, "line-opacity": 0.4 } // Blue currents
      });

      // Draw order matters: cones sit under everything, the slick sits above
      // the look-alikes so the retained detection reads as primary.
      m.addLayer({
        id: "cone90-fill", source: "cone90", type: "fill",
        paint: { "fill-color": C.cone90 }
      });
      m.addLayer({
        id: "cone50-fill", source: "cone50", type: "fill",
        paint: { "fill-color": C.cone50 }
      });
      m.addLayer({
        id: "cone90-line", source: "cone90", type: "line",
        paint: { "line-color": C.coneLine, "line-width": 1, "line-opacity": 0.5, "line-dasharray": [3, 2] }
      });

      // The answer: where the release plausibly happened, pooled over the whole
      // age window. Drawn solid and persistently, unlike the animating frames.
      m.addLayer({
        id: "originRegion90-fill", source: "originRegion90", type: "fill",
        paint: { "fill-color": "rgba(53, 200, 216, 0.13)" }
      });
      m.addLayer({
        id: "originRegion50-fill", source: "originRegion50", type: "fill",
        paint: { "fill-color": "rgba(53, 200, 216, 0.26)" }
      });
      m.addLayer({
        id: "originRegion90-line", source: "originRegion90", type: "line",
        paint: { "line-color": C.coneLine, "line-width": 1.8 }
      });
      m.addLayer({
        id: "originRegion50-line", source: "originRegion50", type: "line",
        paint: { "line-color": C.coneLine, "line-width": 1, "line-opacity": 0.7 }
      });

      m.addLayer({
        id: "forecastCone-fill", source: "forecastCone", type: "fill",
        paint: { "fill-color": "rgba(147, 51, 234, 0.13)" }
      });
      m.addLayer({
        id: "forecastPath-glow", source: "forecastPath", type: "line",
        paint: { "line-color": "#34d399", "line-width": 8, "line-blur": 5, "line-opacity": 0.3 }
      });
      m.addLayer({
        id: "forecastPath-line", source: "forecastPath", type: "line",
        paint: { "line-color": C.forecast, "line-width": 2.5, "line-dasharray": [2, 1.5] }
      });

      m.addLayer({
        id: "lookalikes-fill", source: "lookalikes", type: "fill",
        paint: { "fill-color": C.rejectFill }
      });
      m.addLayer({
        id: "lookalikes-line", source: "lookalikes", type: "line",
        paint: { "line-color": C.reject, "line-width": 1.5, "line-dasharray": [2, 2] }
      });

      m.addLayer({
        id: "slick-fill", source: "slick", type: "fill",
        paint: { "fill-color": C.slickFill }
      });
      m.addLayer({
        id: "slick-line", source: "slick", type: "line",
        paint: { "line-color": C.slick, "line-width": 2 }
      });

      m.addLayer({
        id: "particles-circle", source: "particles", type: "circle",
        paint: { "circle-radius": 2, "circle-color": C.particle, "circle-opacity": 0.55 }
      });

      m.addSource("forecastParticles", { type: "geojson", data: EMPTY });
      m.addLayer({
        id: "forecastParticles-circle", source: "forecastParticles", type: "circle",
        paint: { "circle-radius": 2, "circle-color": C.forecast, "circle-opacity": 0.55 }
      });

      // Neon glow halo, drawn beneath the real track/path lines: a wider,
      // blurred duplicate in radar cyan/green. line-blur is MapLibre's native
      // glow primitive — the canvas equivalent of a CSS drop-shadow, which
      // can't be applied to a canvas-painted layer directly.
      m.addLayer({
        id: "tracks-glow", source: "tracks", type: "line",
        paint: {
          "line-color": "#22d3ee",
          "line-width": ["case", ["get", "selected"], 10, 6],
          "line-blur": ["case", ["get", "selected"], 6, 4],
          "line-opacity": ["case", ["get", "dimmed"], 0.06, ["case", ["get", "selected"], 0.55, 0.22]],
        }
      });

      // Selected vessel is drawn bright; everything else dims. Colour is
      // driven by feature properties so selection is a paint update, not a
      // source rebuild.
      m.addLayer({
        id: "tracks-line", source: "tracks", type: "line",
        paint: {
          "line-color": ["case", ["get", "selected"], C.suspect,
            ["get", "suspect"], C.suspect, C.vessel],
          "line-width": ["case", ["get", "selected"], 3.5, 1.6],
          "line-opacity": ["case", ["get", "dimmed"], 0.15, 0.85],
        }
      });

      m.addLayer({
        id: "tracks-head", source: "tracks", type: "symbol",
        filter: ["==", ["geometry-type"], "Point"],
        layout: {
          "icon-image": "boat-icon",
          "icon-size": ["case", ["get", "selected"], 1.2, 0.8],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-opacity": ["case", ["get", "dimmed"], 0.25, 1],
        }
      });

      // The evidence connective tissue: what links a selected vessel to the
      // spill. The gap is where its AIS went dark; the connector is a plain
      // "this is how close it came" line to the origin — not a claim, a ruler.
      // Plain white rather than a semantic colour: a DARK_VESSEL's track is
      // already drawn in the suspect red, and a same-colour overlay would be
      // invisible exactly where the gap matters most.
      m.addLayer({
        id: "gap-line", source: "gap", type: "line",
        paint: {
          "line-color": "#ffffff", "line-width": 4, "line-dasharray": [1.4, 1.2],
          "line-opacity": 0.9
        }
      });
      m.addLayer({
        id: "connector-line", source: "connector", type: "line",
        paint: {
          "line-color": C.coneLine, "line-width": 1.2, "line-dasharray": [1.5, 1.5],
          "line-opacity": 0.6
        }
      });

      m.addLayer({
        id: "origin-dot", source: "origin", type: "circle",
        paint: {
          "circle-radius": 6, "circle-color": C.origin,
          "circle-stroke-color": "#ffffff", "circle-stroke-width": 2
        }
      });

      // ── Re-Routing Alternate Navigation Layers ─────────────────────
      m.addLayer({
        id: "rerouteExclusion-fill", source: "rerouteExclusion", type: "fill",
        paint: { "fill-color": "rgba(239, 68, 68, 0.08)" }
      });
      m.addLayer({
        id: "rerouteExclusion-line", source: "rerouteExclusion", type: "line",
        paint: { "line-color": "#ef4444", "line-width": 1.5, "line-dasharray": [3, 2], "line-opacity": 0.8 }
      });
      m.addLayer({
        id: "rerouteDirect-line", source: "rerouteDirect", type: "line",
        paint: { "line-color": "#ef4444", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.75 }
      });
      m.addLayer({
        id: "reroutePath-glow", source: "reroutePath", type: "line",
        paint: { "line-color": "#10b981", "line-width": 10, "line-blur": 6, "line-opacity": 0.5 }
      });
      m.addLayer({
        id: "exclusionZone-fill", source: "exclusionZone", type: "fill",
        paint: { "fill-color": "#ef4444", "fill-opacity": 0.15 }
      });
      m.addLayer({
        id: "exclusionZone-line", source: "exclusionZone", type: "line",
        paint: { "line-color": "#dc2626", "line-width": 1.5, "line-dasharray": [4, 4] }
      });
      m.addLayer({
        id: "simOriginalPath-line", source: "simOriginalPath", type: "line",
        paint: { "line-color": "#ef4444", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.8 }
      });
      m.addLayer({
        id: "simReroutedPath-line", source: "simReroutedPath", type: "line",
        paint: { "line-color": "#10b981", "line-width": 3, "line-opacity": 0.9 }
      });
      m.addLayer({
        id: "simBoatIcon-symbol", source: "simBoatIcon", type: "symbol",
        layout: {
          "icon-image": "green-boat-icon",
          "icon-size": 0.6,
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
      });
      m.addLayer({
        id: "simClickWaypoints-symbol", source: "simClickWaypoints", type: "symbol",
        layout: {
          "icon-image": "blue-pin-icon",
          "icon-size": 0.8,
          "icon-offset": [0, -12], // offset up so the pin tip points at the coord
          "icon-allow-overlap": true,
        },
      });
      m.addLayer({
        id: "reroutePath-line", source: "reroutePath", type: "line",
        paint: { "line-color": "#059669", "line-width": 3.5 }
      });
      m.addLayer({
        id: "rerouteWaypoints-circle", source: "rerouteWaypoints", type: "circle",
        paint: {
          "circle-radius": 6,
          "circle-color": "#10b981",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2.5
        }
      });

      m.on("click", "tracks-line", (e) => {
        const mmsi = e.features?.[0]?.properties?.mmsi;
        if (mmsi) onSelect.current(String(mmsi));
      });
      m.on("mouseenter", "tracks-line", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "tracks-line", () => { m.getCanvas().style.cursor = ""; });

      m.on("click", (e) => {
        // Only trigger if we didn't click on a track
        const features = m.queryRenderedFeatures(e.point, { layers: ["tracks-line"] });
        if (!features.length) {
          onMapClickRef.current?.([e.lngLat.lng, e.lngLat.lat]);
        }
      });

      setReady(true);
      m.triggerRepaint();
    });

    map.current = m;
    return () => {
      resizeObs.current?.disconnect();
      resizeObs.current = null;
      originMarkers.current.forEach((mk) => mk.remove());
      originMarkers.current = [];
      m.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  const setData = (id: string, data: GeoJSON.FeatureCollection) => {
    const src = map.current?.getSource(id) as maplibregl.GeoJSONSource | undefined;
    src?.setData(data);
  };

  // ---- fit to the case bbox and draw the AOI frame ----------
  useEffect(() => {
    if (!map.current || !caseMeta) return;
    const b = caseMeta.bbox;
    map.current.fitBounds([[b.west, b.south], [b.east, b.north]], { padding: 60, duration: 700 });

    if (!ready) return;
    setData("frame", {
      type: "FeatureCollection",
      features: [{
        type: "Feature", properties: {}, geometry: {
          type: "LineString",
          coordinates: [[b.west, b.south], [b.east, b.south], [b.east, b.north],
          [b.west, b.north], [b.west, b.south]]
        }
      }],
    });
  }, [caseMeta, ready]);



  // ---- SAR overlay ------------------------------------------------------
  // Added in its own effect rather than in the style-load handler: the case is
  // fetched asynchronously and usually arrives AFTER the style has loaded, so
  // adding it during load would silently skip the imagery.
  //
  // The bundled scene ships as two tonal variants — a moody, dark-water render
  // for the SAR/dark theme and a brighter inverted render for the light
  // theme — swapped in place via updateImage() rather than removing and
  // re-adding the source, so toggling theme doesn't flash the map blank.
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !caseMeta?.sar_overlay_url) return;

    const url = caseMeta.sar_overlay_url;

    const existing = m.getSource("sar") as maplibregl.ImageSource | undefined;
    if (existing) {
      existing.updateImage({ url });
      return;
    }

    const b = caseMeta.bbox;
    m.addSource("sar", {
      type: "image",
      url,
      // Image sources take corners clockwise from the top-left.
      coordinates: [
        [b.west, b.north], [b.east, b.north],
        [b.east, b.south], [b.west, b.south],
      ],
    });
    // Beneath every vector layer, so the imagery is context and never
    // obscures the detection it is supporting.
    m.addLayer(
      {
        id: "sar-raster", source: "sar", type: "raster",
        paint: { "raster-opacity": 0.95, "raster-fade-duration": 300 }
      },
      "graticule-line",
    );
  }, [ready, caseMeta, theme]);

  // ---- Custom Uploaded SAR Overlays -------------------------------------
  const registeredOverlayIds = useRef<Set<string>>(new Set());
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;

    const currentIds = new Set(customOverlays.map(o => o.id));

    // Remove layers/sources no longer present
    registeredOverlayIds.current.forEach(id => {
      if (!currentIds.has(id)) {
        const layerId = `sar-raster-custom-${id}`;
        const sourceId = `sar-custom-${id}`;
        if (m.getLayer(layerId)) m.removeLayer(layerId);
        if (m.getSource(sourceId)) m.removeSource(sourceId);
        registeredOverlayIds.current.delete(id);
      }
    });

    // Add or update custom overlays
    customOverlays.forEach(overlay => {
      const sourceId = `sar-custom-${overlay.id}`;
      const layerId = `sar-raster-custom-${overlay.id}`;

      const existing = m.getSource(sourceId) as maplibregl.ImageSource | undefined;
      if (existing) {
        existing.updateImage({
          url: overlay.imageUrl,
          coordinates: overlay.coordinates,
        });
      } else {
        m.addSource(sourceId, {
          type: "image",
          url: overlay.imageUrl,
          coordinates: overlay.coordinates,
        });

        const beforeLayer = m.getLayer("graticule-line") ? "graticule-line" : undefined;
        m.addLayer(
          {
            id: layerId,
            source: sourceId,
            type: "raster",
            paint: {
              "raster-opacity": 0.95,
              "raster-fade-duration": 300,
            },
          },
          beforeLayer
        );
        registeredOverlayIds.current.add(overlay.id);
      }
    });
  }, [ready, customOverlays]);

  // Update visibility for all SAR raster layers (built-in + custom uploads)
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    if (m.getLayer("sar-raster")) {
      m.setLayoutProperty("sar-raster", "visibility", layers.sar ? "visible" : "none");
    }
    customOverlays.forEach(overlay => {
      const layerId = `sar-raster-custom-${overlay.id}`;
      if (m.getLayer(layerId)) {
        m.setLayoutProperty(layerId, "visibility", layers.sar ? "visible" : "none");
      }
    });
  }, [ready, layers.sar, caseMeta, customOverlays]);

  // ---- detection --------------------------------------------------------
  useEffect(() => {
    if (!ready) return;
    setData("slick", {
      type: "FeatureCollection",
      features: layers.slick
        ? detection?.slicks?.map(s => ({
          type: "Feature",
          geometry: s.polygon,
          properties: {
            id: s.id,
            confidence: s.confidence,
            selected: s.id === activeSlickId,
            class: "oil",
          }
        })) || []
        : [],
    });
    setData("lookalikes", {
      type: "FeatureCollection",
      features: layers.lookalikes && detection && (!activeSlickId || activeSlickId === "all")
        ? detection.rejected_lookalikes.map((r) => ({
          type: "Feature", geometry: r.polygon,
          properties: { id: r.id, reason: r.reason },
        }))
        : [],
    });
  }, [ready, targetSlicks, layers.slick, layers.lookalikes, detection, activeSlickId]);

  // ---- fly to isolated slick / custom upload ---------------------------
  useEffect(() => {
    if (!ready || !map.current || !activeSlickId || activeSlickId === "all" || !detection) return;
    const active = detection.slicks.find(s => s.id === activeSlickId);
    if (active && active.polygon.type === "Polygon") {
      const pts = active.polygon.coordinates[0] as [number, number][];
      const lons = pts.map(p => p[0]);
      const lats = pts.map(p => p[1]);
      const minLon = Math.min(...lons);
      const maxLon = Math.max(...lons);
      const minLat = Math.min(...lats);
      const maxLat = Math.max(...lats);
      map.current.fitBounds(
        [[minLon, minLat], [maxLon, maxLat]],
        { padding: 100, maxZoom: 11, duration: 1200 }
      );
    }
  }, [ready, activeSlickId, detection]);

  // ---- hindcast cone, particles, origin ---------------------------------
  useEffect(() => {
    if (!ready) return;
    const frames = hindcast?.particles_timeline ?? [];
    const frame = frames[Math.min(hindcastIndex, frames.length - 1)];
    const t = frame?.t_offset_hours;

    // Animating frames: the ensemble cone at this instant. The fixtures are
    // authored directly against the bundled SAR scene, so geometry is drawn at
    // its true extent — no display-only rescaling.
    for (const p of [50, 90] as const) {
      const rings = hindcast?.cone.filter(
        (c) => c.percentile === p && c.t_offset_hours === t,
      ) ?? [];
      setData(`cone${p}`, {
        type: "FeatureCollection",
        features: layers.cone
          ? rings.map(ring => ({ type: "Feature", geometry: ring.polygon, properties: { percentile: p } }))
          : [],
      });
    }

    const particleFeatures: GeoJSON.Feature[] =
      layers.particles && frame
        ? frame.points.map((pt) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: pt },
          properties: {},
        }))
        : [];
    setData("particles", { type: "FeatureCollection", features: particleFeatures });

    // The origin region and marker appear only once the run has settled.
    const atEnd = frames.length > 0 && hindcastIndex >= frames.length - 1;
    const minT = hindcast ? Math.min(...hindcast.cone.map(c => c.t_offset_hours)) : 0;

    const originRings: Record<50 | 90, GeoJSON.Feature[]> = { 50: [], 90: [] };
    for (const p of [50, 90] as const) {
      originRings[p] = (hindcast?.cone.filter(
        (c) => c.percentile === p && c.t_offset_hours === minT,
      ) ?? []).map(ring => ({ type: "Feature", geometry: ring.polygon, properties: { percentile: p } }));
    }

    // Grow the origin-region cones outward from a point rather than popping
    // in fully formed, the first time a given hindcast run settles. Scrubbing
    // back off the final frame and forward again does not replay it.
    const TARGET_SHRINK = 1;
    const growKey = atEnd ? `${hindcast?.origin_estimate?.point?.join(",")}-${minT}` : "";
    if (originGrowAnim.current.raf) cancelAnimationFrame(originGrowAnim.current.raf);
    const renderOriginRegions = (factor: number) => {
      for (const p of [50, 90] as const) {
        setData(`originRegion${p}`, {
          type: "FeatureCollection",
          features: layers.cone && atEnd
            ? originRings[p].map(f => ({ ...f, geometry: scalePoly(f.geometry, factor) }))
            : [],
        });
      }
    };
    if (growKey && growKey !== originGrowAnim.current.key) {
      originGrowAnim.current.key = growKey;
      originGrowAnim.current.start = null;
      const DURATION = 1100;
      const step = (ts: number) => {
        if (originGrowAnim.current.start === null) originGrowAnim.current.start = ts;
        const p = Math.min(1, (ts - originGrowAnim.current.start) / DURATION);
        renderOriginRegions(TARGET_SHRINK * easeOutCubic(p));
        originGrowAnim.current.raf = p < 1 ? requestAnimationFrame(step) : null;
      };
      originGrowAnim.current.raf = requestAnimationFrame(step);
    } else {
      if (!growKey) originGrowAnim.current.key = "";
      renderOriginRegions(TARGET_SHRINK);
    }

    const originFeatures: GeoJSON.Feature[] = [];
    if (atEnd && hindcast?.origin_estimate) {
      originFeatures.push({ type: "Feature", geometry: { type: "Point", coordinates: hindcast.origin_estimate.point }, properties: {} });
    }
    if (atEnd && (hindcast as any)?.extra_origins) {
      for (const ext of (hindcast as any).extra_origins) {
        originFeatures.push({ type: "Feature", geometry: { type: "Point", coordinates: ext.point }, properties: {} });
      }
    }
    setData("origin", { type: "FeatureCollection", features: originFeatures });

    // Sonar-ping rings are plain animated DOM markers (CSS keyframes handle
    // the scale+fade), positioned on top of the canvas-rendered origin dots.
    originMarkers.current.forEach((mk) => mk.remove());
    originMarkers.current = [];
    if (map.current) {
      for (const f of originFeatures) {
        if (f.geometry.type !== "Point") continue;
        // A brighter cyan than the origin dot itself: the dot's own blue
        // blends into the (also blue) origin-region fill it sits on top of,
        // so the ping needs its own contrast to read against the map.
        const el = document.createElement("div");
        el.innerHTML =
          `<span class="sonar-ping-ring" style="--sonar-color:#5eead4"></span>` +
          `<span class="sonar-ping-ring delay-1" style="--sonar-color:#5eead4"></span>` +
          `<span class="sonar-ping-ring delay-2" style="--sonar-color:#5eead4"></span>`;
        originMarkers.current.push(
          new maplibregl.Marker({ element: el, anchor: "center" })
            .setLngLat(f.geometry.coordinates as [number, number])
            .addTo(map.current),
        );
      }
    }

    return () => { if (originGrowAnim.current.raf) cancelAnimationFrame(originGrowAnim.current.raf); };
  }, [ready, hindcast, hindcastIndex, layers.cone, layers.particles]);

  // ---- forecast ---------------------------------------------------------
  useEffect(() => {
    if (!ready) return;
    const forecastFrames = forecast?.particles_timeline ?? [];
    const forecastFrame = forecastFrames[Math.min(forecastIndex, forecastFrames.length - 1)];
    const forecastT = forecastFrame?.t_offset_hours ?? 0;

    // Progressively expand the cone by filtering up to the current timestamp.
    // Same rule as the hindcast: the fixture geometry is already georeferenced
    // to the SAR scene, so it is drawn at its true extent.
    const outer = forecast?.cone.filter((c) => c.percentile === 90 && c.t_offset_hours <= forecastT) ?? [];
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
      features: layers.forecast && forecast?.centroid_path
        ? [{ type: "Feature", geometry: forecast.centroid_path, properties: {} }]
        : [],
    });

    const particleFeatures: GeoJSON.Feature[] =
      layers.particles && forecastFrame
        ? forecastFrame.points.map((pt) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: pt },
          properties: {},
        }))
        : [];
    setData("forecastParticles", { type: "FeatureCollection", features: particleFeatures });
  }, [ready, forecast, layers.forecast, layers.particles, forecastIndex]);

  // ---- vessel tracks ------------------------------------------------------
  // Tracks draw themselves in (leading-edge reveal, like a radar trail sweep)
  // the first time a given set of candidates appears. Re-runs of this effect
  // for a selection change alone reuse the finished (progress=1) geometry —
  // clicking a different vessel recolours it, it doesn't replay the draw-in.
  useEffect(() => {
    if (!ready) return;
    const candidates = layers.tracks && attribution ? attribution.candidates : [];
    const sig = candidates.map((c) => {
      const geom = c.track as any;
      const len = geom?.type === "LineString" ? geom.coordinates.length : geom?.type === "MultiLineString"
        ? geom.coordinates.reduce((n: number, l: any[]) => n + l.length, 0) : 0;
      return `${c.mmsi}:${len}`;
    }).join(",");
    const isNew = sig !== tracksAnim.current.key;
    if (tracksAnim.current.raf) cancelAnimationFrame(tracksAnim.current.raf);
    tracksAnim.current.key = sig;
    if (isNew) tracksAnim.current.start = null;

    const render = (progress: number) => setData("tracks", {
      type: "FeatureCollection",
      features: candidates.flatMap((c) => {
        const props = {
          mmsi: c.mmsi,
          name: c.name,
          suspect: c.flags.includes("DARK_VESSEL"),
          selected: c.mmsi === selectedMmsi,
          dimmed: selectedMmsi !== null && c.mmsi !== selectedMmsi,
        };
        const res: any[] = [{
          type: "Feature",
          geometry: sliceLine(c.track, progress),
          properties: props,
        }];
        const endPt = getLineEnd(c.track, progress);
        if (endPt) {
          res.push({
            type: "Feature",
            geometry: { type: "Point", coordinates: endPt },
            properties: props,
          });
        }
        return res;
      }),
    });

    if (isNew && candidates.length > 0) {
      const DURATION = 900;
      const step = (ts: number) => {
        if (tracksAnim.current.start === null) tracksAnim.current.start = ts;
        const p = Math.min(1, (ts - tracksAnim.current.start) / DURATION);
        render(easeOutCubic(p));
        tracksAnim.current.raf = p < 1 ? requestAnimationFrame(step) : null;
      };
      tracksAnim.current.raf = requestAnimationFrame(step);
    } else {
      render(1);
    }
    return () => { if (tracksAnim.current.raf) cancelAnimationFrame(tracksAnim.current.raf); };
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

  // ── Re-Routing Alternate Detour Path Synchronization ─────────────
  useEffect(() => {
    if (!ready) return;
    if (!reRouteOption) {
      setData("rerouteExclusion", EMPTY);
      setData("rerouteDirect", EMPTY);
      setData("reroutePath", EMPTY);
      setData("rerouteWaypoints", EMPTY);
      return;
    }

    setData("rerouteExclusion", {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: reRouteOption.geojson_exclusion_zone }]
    });

    setData("rerouteDirect", {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: { label: "Direct Hazard Line" }, geometry: reRouteOption.geojson_direct }]
    });

    setData("reroutePath", {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: { label: reRouteOption.name }, geometry: reRouteOption.geojson_path }]
    });

    setData("rerouteWaypoints", {
      type: "FeatureCollection",
      features: reRouteOption.waypoints.map(w => ({
        type: "Feature",
        properties: { name: w.name, course: `${w.course_to_steer_deg}°`, instructions: w.instructions },
        geometry: { type: "Point", coordinates: [w.lon, w.lat] }
      }))
    });
  }, [ready, reRouteOption]);

  useEffect(() => {
    if (!ready) return;
    if (!rerouteResult) {
      setData("simOriginalPath", EMPTY);
      setData("simReroutedPath", EMPTY);
      setData("simBoatIcon", EMPTY);
      setData("exclusionZone", EMPTY);
      return;
    }
    setData("simOriginalPath", rerouteResult.original_path.length < 2 ? EMPTY : {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: rerouteResult.original_path } }]
    });
    setData("simReroutedPath", rerouteResult.rerouted_path.length < 2 ? EMPTY : {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: rerouteResult.rerouted_path } }]
    });
    if (rerouteResult.exclusion_zone) {
      setData("exclusionZone", {
        type: "FeatureCollection",
        features: [{
          type: "Feature",
          properties: {},
          geometry: rerouteResult.exclusion_zone
        }]
      });
    } else {
      setData("exclusionZone", EMPTY);
    }

    setData("simBoatIcon", EMPTY);
    if (rerouteResult.rerouted_path.length < 2) return;

    // Animate the boat
    let raf: number;
    let startTs: number | null = null;
    const DURATION = 3000; // 3 seconds

    const renderAnim = (progress: number) => {
      const pt = getLineEnd({ type: "LineString", coordinates: rerouteResult.rerouted_path }, progress);
      if (pt) {
        setData("simBoatIcon", {
          type: "FeatureCollection",
          features: [{
            type: "Feature",
            properties: {},
            geometry: { type: "Point", coordinates: pt }
          }]
        });
      }
    };

    const step = (ts: number) => {
      if (!startTs) startTs = ts;
      const progress = Math.min(1, (ts - startTs) / DURATION);
      renderAnim(progress);
      if (progress < 1) {
        raf = requestAnimationFrame(step);
      }
    };

    raf = requestAnimationFrame(step);

    return () => {
      if (raf) cancelAnimationFrame(raf);
    };
  }, [ready, rerouteResult]);

  useEffect(() => {
    if (!ready) return;
    setData("simClickWaypoints", {
      type: "FeatureCollection",
      features: simWaypoints.map(pt => ({
        type: "Feature",
        properties: {},
        geometry: { type: "Point", coordinates: pt }
      }))
    });
  }, [ready, simWaypoints]);

  const handledFocusNonce = useRef<number | null>(null);

  // ---- "View on SAR": fly to a ruled-out candidate ------------------------
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !focusRequest || !detection) return;
    
    if (handledFocusNonce.current === focusRequest.nonce) return;
    handledFocusNonce.current = focusRequest.nonce;

    const target = detection.rejected_lookalikes.find((r) => r.id === focusRequest.id) ||
                   detection.slicks.find((s) => s.id === focusRequest.id);
    if (!target || target.polygon.type !== "Polygon") return;
    const ring = target.polygon.coordinates[0] as [number, number][];
    const lons = ring.map((p) => p[0]);
    const lats = ring.map((p) => p[1]);
    m.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 140, maxZoom: 12, duration: 700 },
    );
  }, [ready, focusRequest, detection]);

  // ---- Dynamic endless graticule and wind field --------------------------
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || mockWindDir === undefined) return;

    const updateGridAndArrows = () => {
      const bounds = m.getBounds();
      // Pad bounds slightly so lines don't pop in at the exact edge
      const west = bounds.getWest() - 1;
      const east = bounds.getEast() + 1;
      const south = bounds.getSouth() - 1;
      const north = bounds.getNorth() + 1;

      const step = 0.25;
      const from = (v: number) => Math.floor(v / step) * step;

      // 1. Graticule
      const lines: GeoJSON.Feature[] = [];
      for (let lon = from(west); lon < east; lon += step) {
        lines.push({
          type: "Feature", properties: {},
          geometry: { type: "LineString", coordinates: [[lon, south], [lon, north]] }
        });
      }
      for (let lat = from(south); lat < north; lat += step) {
        lines.push({
          type: "Feature", properties: {},
          geometry: { type: "LineString", coordinates: [[west, lat], [east, lat]] }
        });
      }
      setData("graticule", { type: "FeatureCollection", features: lines });

      // 2. Wind Arrows
      const arrows: GeoJSON.Feature[] = [];
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

      for (let lon = from(west) + step / 2; lon < east; lon += step) {
        for (let lat = from(south) + step / 2; lat < north; lat += step) {
          const endLon = lon + dx;
          const endLat = lat + dy;
          arrows.push({
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
      setData("windField", { type: "FeatureCollection", features: arrows });

      // Currents (blue arrows), let's offset the angle slightly (e.g. Ekman transport 45deg right of wind)
      const currentArrows: GeoJSON.Feature[] = [];
      const currentRad = (90 - mockWindDir + 45) * (Math.PI / 180);
      const cdx = Math.cos(currentRad) * arrowLen * 0.8;
      const cdy = Math.sin(currentRad) * arrowLen * 0.8;
      const chx1 = Math.cos(currentRad + Math.PI - headAngle) * headLen;
      const chy1 = Math.sin(currentRad + Math.PI - headAngle) * headLen;
      const chx2 = Math.cos(currentRad + Math.PI + headAngle) * headLen;
      const chy2 = Math.sin(currentRad + Math.PI + headAngle) * headLen;

      // Shift the grid slightly for currents so they don't overlap wind perfectly
      for (let lon = from(west) + step * 0.25; lon < east; lon += step) {
        for (let lat = from(south) + step * 0.25; lat < north; lat += step) {
          const endLon = lon + cdx;
          const endLat = lat + cdy;
          currentArrows.push({
            type: "Feature", properties: {},
            geometry: {
              type: "MultiLineString",
              coordinates: [
                [[lon, lat], [endLon, endLat]],
                [[endLon, endLat], [endLon + chx1, endLat + chy1]],
                [[endLon, endLat], [endLon + chx2, endLat + chy2]]
              ]
            }
          });
        }
      }
      setData("currentField", { type: "FeatureCollection", features: currentArrows });
    };

    updateGridAndArrows();
    m.on("move", updateGridAndArrows);
    return () => { m.off("move", updateGridAndArrows); };
  }, [ready, mockWindDir]);

  // ---- ambient shipping lanes --------------------------------------------
  // Regenerated per viewport like the graticule, but on its own listener:
  // lanes are pure backdrop and shouldn't depend on whether a page happens
  // to supply wind. The network is deterministic, so redrawing on every move
  // is idempotent — pan away and back and the same lanes are there.
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;

    const updateLanes = () => {
      const b = m.getBounds();
      setData("shippingLanes", {
        type: "FeatureCollection",
        features: buildLaneNetwork(b.getWest(), b.getSouth(), b.getEast(), b.getNorth()),
      });
    };

    updateLanes();
    m.on("move", updateLanes);
    return () => { m.off("move", updateLanes); };
  }, [ready]);

  return (
    <>
      <div ref={container} className="absolute inset-0 h-full w-full" />
      {/* SAR/satellite-radar skin: grain + scanlines + a slow diagonal sweep,
       *  layered over the dark-theme map so it reads as radar imagery rather
       *  than just a dimmed basemap. Cross-faded via opacity, not mounted
       *  conditionally, so the transition itself animates. */}
      <div className={`sar-noise-overlay active ${theme}`}>
        <div className="sar-vignette" />
        <div className="sar-scanlines" />
        <div className="sar-sweep" />
        {theme === "dark" && <div className="sar-grain" />}
      </div>
    </>
  );
}
