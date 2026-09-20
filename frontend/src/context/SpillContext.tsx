import React, { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import * as api from "../api/client";
import { getDataMode, onDataModeChange } from "../api/client";

import type {
  AttributeResponse,
  CaseMeta,
  CustomImageOverlay,
  DetectResponse,
  DetectionMethod,
  ForecastResponse,
  HindcastResponse,
  ProcessingStep,
  ReportContent,
  ReRouteOption,
} from "../api/types";
import { type LayerVisibility } from "../components/MapView";
import { type ViewMode } from "../lib/viewMode";

const FRAME_MS = 60; // Faster playback for smoother analysis

const DEFAULT_WIND_DIR = 306;

// Bump whenever the bundled fixtures move, so a browser holding a cached run
// from the previous geometry doesn't paint stale layers over the SAR scene.
const STATE_KEY = "spilltrace_state_v2";

interface SpillContextType {
  caseMeta: CaseMeta | null;
  detection: DetectResponse | null;
  hindcast: HindcastResponse | null;
  forecast: ForecastResponse | null;
  attribution: AttributeResponse | null;
  report: ReportContent | null;
  customOverlays: CustomImageOverlay[];

  method: DetectionMethod;
  detecting: boolean;
  drifting: "hindcast" | "forecast" | null;
  attributing: boolean;
  reporting: boolean;

  hindcastIndex: number;
  forecastIndex: number;
  hindcastPlaying: boolean;
  forecastPlaying: boolean;

  selectedMmsi: string | null;
  activeSlickId: string | null;
  dataMode: "live" | "offline";
  focusRequest: { id: string; nonce: number } | null;
  viewMode: ViewMode;
  layers: LayerVisibility;
  steps: ProcessingStep[];
  mockWindDir: number;

  runDetect: (m: DetectionMethod) => Promise<void>;
  runHindcast: (windDir?: number) => Promise<HindcastResponse | null>;
  runForecast: (windDir?: number) => Promise<void>;
  runAttribute: (windDir?: number, hindcastOverride?: HindcastResponse) => Promise<void>;
  runReport: () => Promise<void>;

  setHindcastIndex: React.Dispatch<React.SetStateAction<number>>;
  setForecastIndex: React.Dispatch<React.SetStateAction<number>>;
  setHindcastPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  setForecastPlaying: React.Dispatch<React.SetStateAction<boolean>>;

  setSelectedMmsi: React.Dispatch<React.SetStateAction<string | null>>;
  setActiveSlickId: React.Dispatch<React.SetStateAction<string | null>>;
  setViewMode: React.Dispatch<React.SetStateAction<ViewMode>>;
  toggleLayer: (k: keyof LayerVisibility) => void;
  onFocusLookalike: (id: string) => void;
  randomizeWind: () => number;  // returns the new direction

  injectAdHocDetection: (det: DetectResponse, overlay?: CustomImageOverlay) => void;
  removeCustomOverlay: (id: string) => void;

  broadcastAlert: { message: string; sentAt: string } | null;
  sendBroadcastAlert: (message: string) => void;
  dismissBroadcastAlert: () => void;

  activeReRouteOption: ReRouteOption | null;
  setActiveReRouteOption: (opt: ReRouteOption | null) => void;

  rerouteResult: import("../api/types").RerouteResponse | null;
  simulateReroute: () => Promise<void>;

  // Legacy compatibility, though components will migrate off this
  frameIndex: number;
  frames: number;
  hindcastFrames: number;
  forecastFrames: number;
  playing: boolean;
  setFrameIndex: React.Dispatch<React.SetStateAction<number>>;
  setPlaying: React.Dispatch<React.SetStateAction<boolean>>;
}

const SpillContext = createContext < SpillContextType | null > (null);

export function useSpillState() {
  const context = useContext(SpillContext);
  if (!context) {
    throw new Error("useSpillState must be used within a SpillProvider");
  }
  return context;
}

export function SpillProvider({ children }: { children: ReactNode }) {
  const [caseMeta, setCaseMeta] = useState < CaseMeta | null > (null);
  const [detection, setDetection] = useState < DetectResponse | null > (null);
  const [hindcast, setHindcast] = useState < HindcastResponse | null > (null);
  const [forecast, setForecast] = useState < ForecastResponse | null > (null);
  const [attribution, setAttribution] = useState < AttributeResponse | null > (null);
  const [report, setReport] = useState < ReportContent | null > (null);
  const [customOverlays, setCustomOverlays] = useState < CustomImageOverlay[] > ([]);
  const [rerouteResult, setRerouteResult] = useState < import("../api/types").RerouteResponse | null > (null);

  const [method, setMethod] = useState < DetectionMethod > ("classical");
  const [detecting, setDetecting] = useState(false);
  const [drifting, setDrifting] = useState < "hindcast" | "forecast" | null > (null);
  const [attributing, setAttributing] = useState(false);
  const [reporting, setReporting] = useState(false);

  const [hindcastIndex, setHindcastIndex] = useState(0);
  const [forecastIndex, setForecastIndex] = useState(0);
  const [hindcastPlaying, setHindcastPlaying] = useState(false);
  const [forecastPlaying, setForecastPlaying] = useState(false);

  const [selectedMmsi, setSelectedMmsi] = useState < string | null > (null);
  const [activeSlickId, setActiveSlickId] = useState < string | null > (null);
  const [dataMode, setDataMode] = useState < "live" | "offline" > (getDataMode() as "live" | "offline");
  const [focusRequest, setFocusRequest] = useState < { id: string; nonce: number } | null > (null);
  const [viewMode, setViewMode] = useState < ViewMode > ("analyst");

  const [layers, setLayers] = useState < LayerVisibility > ({
    sar: true, slick: true, lookalikes: true, cone: true, particles: true, forecast: true, tracks: true,
  });

  const [activeReRouteOption, setActiveReRouteOption] = useState<ReRouteOption | null>(null);
  const [broadcastAlert, setBroadcastAlert] = useState<{ message: string; sentAt: string } | null>(null);
  const sendBroadcastAlert = useCallback((message: string) => {
    setBroadcastAlert({ message, sentAt: new Date().toISOString() });
  }, []);
  const dismissBroadcastAlert = useCallback(() => setBroadcastAlert(null), []);

  // The drift bearing of the bundled case: WNW, matching the slick axis traced
  // off the SAR scene (carrier in the south-east -> slick head in the bay).
  const [mockWindDir, setMockWindDir] = useState(DEFAULT_WIND_DIR);

  // Clear simulation data when switching between spills
  const prevActiveSlick = useRef < string | null > (null);
  useEffect(() => {
    if (prevActiveSlick.current !== null && activeSlickId !== prevActiveSlick.current) {
      // User switched spills — wipe old hindcast/forecast/attribution so
      // old blue/purple regions don't linger on the map
      setHindcast(null);
      setForecast(null);
      setAttribution(null);
      setSelectedMmsi(null);
      setHindcastIndex(0);
      setForecastIndex(0);
      setHindcastPlaying(false);
      setForecastPlaying(false);
    }
    prevActiveSlick.current = activeSlickId;
  }, [activeSlickId]);

  const autorun = new URLSearchParams(window.location.search).get("autorun") === "1";

  // Initialization
  useEffect(() => {
    const off = onDataModeChange(setDataMode as any);
    api.getCase().then(setCaseMeta);

    // Try restoring from localStorage first
    const savedState = localStorage.getItem(STATE_KEY);
    if (savedState) {
      try {
        const { detection: d, hindcast: h, forecast: f, attribution: a, mockWindDir: mw, customOverlays: co, activeSlickId: actId } = JSON.parse(savedState);
        if (d) setDetection(d);
        if (actId) setActiveSlickId(actId);
        if (h) {
          setHindcast(h);
          setHindcastIndex(h.particles_timeline.length - 1);
        }
        if (f) setForecast(f);
        if (a) {
          setAttribution(a);
          setSelectedMmsi(a.candidates[0]?.mmsi ?? null);
        }
        if (mw !== undefined) setMockWindDir(mw);
        if (co) setCustomOverlays(co);
        return off; // Skip default API fetch if we have saved state
      } catch (e) {
        console.error("Failed to parse saved state", e);
      }
    }

    setDetecting(true);
    api.detect("classical")
      .then(async (det) => {
        setDetection(det);
        if (!autorun || !det.slicks[0]) return;
        const id = det.slicks[0].id;
        const h = await api.hindcast(id);
        setHindcast(h);
        setHindcastIndex(h.particles_timeline.length - 1);
        setForecast(await api.forecast(id, 12));
        const a = await api.attribute(h.origin_estimate.point, h.origin_estimate.time_utc, {
          uncertaintyRadiusKm: h.origin_estimate.uncertainty_radius_km,
          timeWindowHours: h.origin_estimate.time_window_hours,
          driftBearingDeg: det.slicks[0].geometry.orientation_deg,
        });
        setAttribution(a);
        setSelectedMmsi(a.candidates[0]?.mmsi ?? null);
      })
      .finally(() => setDetecting(false));
    return off;
  }, []);

  // Save state to localStorage whenever it changes so custom picture uploads stay permanently across refresh
  useEffect(() => {
    if (detection) {
      const state = { detection, hindcast, forecast, attribution, mockWindDir, customOverlays, activeSlickId };
      try {
        localStorage.setItem(STATE_KEY, JSON.stringify(state));
      } catch (err) {
        console.warn("Failed to save state to localStorage", err);
      }
    }
  }, [detection, hindcast, forecast, attribution, mockWindDir, customOverlays, activeSlickId]);

  const hindcastFrames = hindcast?.particles_timeline.length ?? 0;
  const forecastFrames = forecast?.particles_timeline.length ?? 0;

  // Particle animation
  const timer = useRef < number | null > (null);
  useEffect(() => {
    if (!hindcastPlaying && !forecastPlaying) {
      if (timer.current) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
      return;
    }

    if (!timer.current) {
      timer.current = window.setInterval(() => {
        if (hindcastPlaying && hindcastFrames > 0) {
          setHindcastIndex((i) => {
            if (i >= hindcastFrames - 1) {
              setHindcastPlaying(false);
              return hindcastFrames - 1;
            }
            return i + 1;
          });
        }

        if (forecastPlaying && forecastFrames > 0) {
          setForecastIndex((i) => {
            if (i >= forecastFrames - 1) {
              setForecastPlaying(false);
              return forecastFrames - 1;
            }
            return i + 1;
          });
        }
      }, FRAME_MS);
    }

    return () => {
      if (timer.current) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
    };
  }, [hindcastPlaying, forecastPlaying, hindcastFrames, forecastFrames]);

  // Actions
  const runDetect = useCallback(async (m: DetectionMethod) => {
    setMethod(m);
    setDetecting(true);
    try {
      setDetection(await api.detect(m));
      setHindcast(null);
      setForecast(null);
      setAttribution(null);
      setReport(null);
      setSelectedMmsi(null);
      setHindcastIndex(0);
      setForecastIndex(0);
    } finally {
      setDetecting(false);
    }
  }, []);

  const runHindcast = useCallback(async (windDir?: number): Promise<HindcastResponse | null> => {
    if (!detection?.slicks?.length) return null;
    setDrifting("hindcast");
    try {
      // Filter slicks based on active selection
      const targetSlicks = activeSlickId && activeSlickId !== "all"
        ? detection.slicks.filter(s => s.id === activeSlickId)
        : detection.slicks;
      if (!targetSlicks.length) return null;

      const firstSlick = targetSlicks[0];
      const isAdhoc = firstSlick.id.startsWith("adhoc-");
      const result = await api.hindcast(
        firstSlick.id,
        24,
        500,
        isAdhoc ? (firstSlick.polygon as GeoJSON.Polygon) : undefined,
        windDir ?? mockWindDir
      );
      setHindcast(result);

      setAttribution(null);
      setSelectedMmsi(null);
      setHindcastIndex(0);
      setHindcastPlaying(true);
      return result;
    } finally {
      setDrifting(null);
    }
  }, [detection, mockWindDir, activeSlickId]);

  const runForecast = useCallback(async (windDir?: number) => {
    if (!detection?.slicks?.length) return;
    setDrifting("forecast");
    try {
      // Filter slicks based on active selection
      const targetSlicks = activeSlickId && activeSlickId !== "all"
        ? detection.slicks.filter(s => s.id === activeSlickId)
        : detection.slicks;
      if (!targetSlicks.length) return;

      const firstSlick = targetSlicks[0];
      const isAdhoc = firstSlick.id.startsWith("adhoc-");
      let finalF = await api.forecast(
        firstSlick.id,
        72,
        500,
        isAdhoc ? (firstSlick.polygon as GeoJSON.Polygon) : undefined,
        windDir ?? mockWindDir
      );

      setForecast(finalF);
      setForecastIndex(0);
      setForecastPlaying(true);
    } finally {
      setDrifting(null);
    }
  }, [detection, mockWindDir, activeSlickId]);

  const runAttribute = useCallback(async (_windDir?: number, hindcastOverride?: HindcastResponse) => {
    const h = hindcastOverride ?? hindcast;
    const o = h?.origin_estimate;
    if (!o) return;
    setAttributing(true);
    try {
      // Filter slicks based on active selection
      const targetSlicks = activeSlickId && activeSlickId !== "all" && detection?.slicks
        ? detection.slicks.filter(s => s.id === activeSlickId)
        : detection?.slicks || [];
      const firstSlick = targetSlicks[0] || detection?.slicks[0];

      const raw = await api.attribute(o.point, o.time_utc, {
        uncertaintyRadiusKm: o.uncertainty_radius_km,
        timeWindowHours: o.time_window_hours,
        driftBearingDeg: firstSlick?.geometry.orientation_deg,
      });
      const a = raw as AttributeResponse;
      setAttribution(a);
      setSelectedMmsi(a.candidates[0]?.mmsi ?? null);
    } finally {
      setAttributing(false);
    }
  }, [hindcast, detection, mockWindDir, activeSlickId]);

  const runReport = useCallback(async () => {
    if (!caseMeta || !detection?.slicks?.length) return;
    setReporting(true);
    try {
      const activeSlick = (activeSlickId && activeSlickId !== "all"
        ? detection.slicks.find(s => s.id === activeSlickId)
        : null) || detection.slicks[0];

      const rep = await api.report(caseMeta.id, activeSlick.id);
      if (rep) {
        setReport(rep);
      } else {
        const isCustom = activeSlick.id.startsWith("adhoc-");
        setReport({
          case_id: caseMeta.id,
          generated_at: new Date().toISOString(),
          scene_id: caseMeta.scene_id || caseMeta.id,
          acquired_at: caseMeta.acquired_at || new Date().toISOString(),
          processing_chain: [],
          detection_summary: { slick_id: activeSlick.id, area_km2: activeSlick.geometry.area_km2 },
          origin_summary: {},
          candidates: [],
          limitations: [
            "Uncalibrated radiometric values on ad-hoc uploaded SAR scenes.",
            "Hydrodynamic trajectory derived from 2D particle current and windage ensemble.",
            "AIS vessel correlation subject to transponder reporting intervals.",
          ],
          provenance: {
            model_version: "1.0",
            params: {},
            generated_at: new Date().toISOString(),
            inputs: [],
            notes: isCustom ? "Ad-hoc SAR upload investigation report." : "Comprehensive maritime spill intelligence dossier.",
          }
        });
      }
    } catch {
      const activeSlick = (activeSlickId && activeSlickId !== "all"
        ? detection.slicks.find(s => s.id === activeSlickId)
        : null) || detection.slicks[0];
      const isCustom = activeSlick?.id.startsWith("adhoc-");
      setReport({
        case_id: caseMeta.id,
        generated_at: new Date().toISOString(),
        scene_id: caseMeta.scene_id || caseMeta.id,
        acquired_at: caseMeta.acquired_at || new Date().toISOString(),
        processing_chain: [],
        detection_summary: { slick_id: activeSlick?.id || "unknown", area_km2: activeSlick?.geometry.area_km2 ?? 0 },
        origin_summary: {},
        candidates: [],
        limitations: [
          "Uncalibrated radiometric values on ad-hoc uploaded SAR scenes.",
          "Hydrodynamic trajectory derived from 2D particle current and windage ensemble.",
          "AIS vessel correlation subject to transponder reporting intervals.",
        ],
        provenance: {
          model_version: "1.0",
          params: {},
          generated_at: new Date().toISOString(),
          inputs: [],
          notes: isCustom ? "Ad-hoc SAR upload investigation report." : "Comprehensive maritime spill intelligence dossier.",
        }
      });
    } finally {
      setReporting(false);
    }
  }, [caseMeta, detection, activeSlickId]);

  const toggleLayer = useCallback((k: keyof LayerVisibility) => {
    setLayers((l) => ({ ...l, [k]: !l[k] }));
  }, []);

  const onFocusLookalike = useCallback((id: string) => {
    setFocusRequest({ id, nonce: Date.now() });
  }, []);

  const randomizeWind = useCallback((): number => {
    const d = Math.floor(Math.random() * 360);
    setMockWindDir(d);
    return d;
  }, []);

  const removeCustomOverlay = useCallback((id: string) => {
    setCustomOverlays((prev) => prev.filter((o) => o.id !== id));
  }, []);

  const injectAdHocDetection = useCallback((det: DetectResponse, overlay?: CustomImageOverlay) => {
    let targetSlickId = det.slicks[0]?.id || null;

    setDetection((prev) => {
      if (!prev) {
        if (overlay) {
          setCustomOverlays((prevOverlays) => [...prevOverlays.filter(o => o.id !== overlay.id), overlay]);
        }
        return det;
      }

      // Shift each new upload into a distinct spot so it doesn't overlap
      // the previous one, but wrap around a small fixed grid rather than
      // growing without bound — an unbounded 1.5°/1.0° step per upload
      // compounds fast (by the 8th upload it's ~10.5°/7° away, thousands of
      // km outside the case bundle's actual current-field grid, where
      // forecast/hindcast drift is physically meaningless). Wrapping keeps
      // every ad-hoc slick within a few tenths of a degree of the real scene.
      const gridIdx = prev.slicks.length % 9;
      const offsetLon = 0.12 * ((gridIdx % 3) + 1);
      const offsetLat = 0.09 * (Math.floor(gridIdx / 3) + 1);

      const shiftedSlicks = det.slicks.map(s => {
        if (s.polygon.type === "Polygon") {
          return {
            ...s,
            polygon: {
              ...s.polygon,
              coordinates: s.polygon.coordinates.map(ring =>
                ring.map(coord => [coord[0] + offsetLon, coord[1] + offsetLat])
              )
            }
          };
        }
        return s;
      });

      const shiftedLookalikes = det.rejected_lookalikes.map(r => {
        if (r.polygon.type === "Polygon") {
          return {
            ...r,
            polygon: {
              ...r.polygon,
              coordinates: r.polygon.coordinates.map(ring =>
                ring.map(coord => [coord[0] + offsetLon, coord[1] + offsetLat])
              )
            }
          };
        }
        return r;
      });

      if (overlay) {
        const shiftedOverlay: CustomImageOverlay = {
          ...overlay,
          coordinates: overlay.coordinates.map(([lon, lat]) => [
            lon + offsetLon,
            lat + offsetLat,
          ]) as [[number, number], [number, number], [number, number], [number, number]],
          bbox: {
            west: overlay.bbox.west + offsetLon,
            east: overlay.bbox.east + offsetLon,
            south: overlay.bbox.south + offsetLat,
            north: overlay.bbox.north + offsetLat,
          },
        };
        setCustomOverlays((prevOverlays) => [
          ...prevOverlays.filter((o) => o.id !== overlay.id),
          shiftedOverlay,
        ]);
      }

      return {
        ...prev,
        slicks: [...prev.slicks, ...shiftedSlicks],
        rejected_lookalikes: [...prev.rejected_lookalikes, ...shiftedLookalikes],
        processing: [...prev.processing, ...det.processing]
      };
    });

    if (targetSlickId) {
      setActiveSlickId(targetSlickId);
    }
  }, []);

  const simulateReroute = useCallback(async () => {
    if (!forecast || !forecast.centroid_path || forecast.centroid_path.type !== "LineString") return;
    try {
      // Determine bounds of the entire spill incident (origin to forecast)
      let minLon = 180, maxLon = -180, minLat = 90, maxLat = -90;
      
      const updateBounds = (lon: number, lat: number) => {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      };

      if (hindcast?.origin_estimate) updateBounds(hindcast.origin_estimate.point[0], hindcast.origin_estimate.point[1]);
      if (forecast?.centroid_path?.type === "LineString") {
        const coords = forecast.centroid_path.coordinates as [number, number][];
        if (coords.length > 0) updateBounds(coords[coords.length - 1][0], coords[coords.length - 1][1]);
      }
      
      // If we couldn't establish a good range, fallback to detection center
      if (minLon === 180) {
         const center_point = (forecast.centroid_path as any).coordinates[0];
         minLon = center_point[0] - 0.2; maxLon = center_point[0] + 0.2;
         minLat = center_point[1] - 0.4; maxLat = center_point[1] + 0.4;
      }

      // Create a diagonal incoming ship path that perfectly intersects the incident
      const start_point: [number, number] = [minLon - 0.1, minLat - 0.2];
      const end_point: [number, number] = [maxLon + 0.1, maxLat + 0.2];

      const obstacles: import("geojson").Geometry[] = [];
      if (detection?.slicks) {
        obstacles.push(...detection.slicks.map((s) => s.polygon));
      }
      if (forecast?.cone) {
        obstacles.push(...forecast.cone.filter(c => c.percentile === 90).map(c => c.polygon));
      }
      if (hindcast?.cone) {
        obstacles.push(...hindcast.cone.filter(c => c.percentile === 90).map(c => c.polygon));
      }
      
      const res = await api.reroute({
        start_point,
        end_point,
        obstacles,
        safety_margin_km: 2.0
      });
      setRerouteResult(res);
    } catch (e) {
      console.error(e);
    }
  }, [forecast, hindcast, detection]);

  const steps: ProcessingStep[] = [
    ...(detection?.processing ?? []),
    ...(hindcast?.processing ?? []),
    ...(forecast?.processing ?? []),
    ...(attribution?.processing ?? []),
  ];

  return (
    <SpillContext.Provider
      value={{
        caseMeta,
        detection,
        hindcast,
        forecast,
        attribution,
        report,
        customOverlays,
        rerouteResult,
        simulateReroute,
        method,
        detecting,
        drifting,
        attributing,
        reporting,

        hindcastIndex,
        forecastIndex,
        hindcastFrames,
        forecastFrames,
        hindcastPlaying,
        forecastPlaying,

        // Legacy compat (for DriftControls until updated)
        frameIndex: hindcastIndex,
        frames: Math.max(hindcastFrames, forecastFrames),
        playing: hindcastPlaying || forecastPlaying,
        setFrameIndex: setHindcastIndex,
        setPlaying: setHindcastPlaying,

        selectedMmsi,
        activeSlickId,
        dataMode,
        focusRequest,
        viewMode,
        layers,
        steps,
        mockWindDir,
        runDetect,
        runHindcast,
        runForecast,
        runAttribute,
        runReport,

        setHindcastIndex,
        setForecastIndex,
        setHindcastPlaying,
        setForecastPlaying,

        setSelectedMmsi,
        setActiveSlickId,
        setViewMode,
        toggleLayer,
        onFocusLookalike,
        randomizeWind,
        injectAdHocDetection,
        removeCustomOverlay,
        activeReRouteOption,
        setActiveReRouteOption,
        broadcastAlert,
        sendBroadcastAlert,
        dismissBroadcastAlert,
      }}
    >
      {children}
    </SpillContext.Provider>
  );
}
