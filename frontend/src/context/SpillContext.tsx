import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from "react";
import * as api from "../api/client";
import { getDataMode, onDataModeChange } from "../api/client";
import { shiftHindcast, shiftForecast, shiftAttribution } from "../lib/shiftMock";
import type {
  AttributeResponse,
  CaseMeta,
  DetectResponse,
  DetectionMethod,
  ForecastResponse,
  HindcastResponse,
  ProcessingStep,
  ReportContent,
} from "../api/types";
import { type LayerVisibility } from "../components/MapView";
import { type ViewMode } from "../lib/viewMode";

const FRAME_MS = 150; // Slower playback for smoother analysis

interface SpillContextType {
  caseMeta: CaseMeta | null;
  detection: DetectResponse | null;
  hindcast: HindcastResponse | null;
  forecast: ForecastResponse | null;
  attribution: AttributeResponse | null;
  report: ReportContent | null;
  
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
  dataMode: "live" | "offline";
  focusRequest: { id: string; nonce: number } | null;
  viewMode: ViewMode;
  layers: LayerVisibility;
  steps: ProcessingStep[];
  mockWindDir: number;

  runDetect: (m: DetectionMethod) => Promise<void>;
  runHindcast: (windDir?: number) => Promise<void>;
  runForecast: (windDir?: number) => Promise<void>;
  runAttribute: (windDir?: number) => Promise<void>;
  runReport: () => Promise<void>;
  
  setHindcastIndex: React.Dispatch<React.SetStateAction<number>>;
  setForecastIndex: React.Dispatch<React.SetStateAction<number>>;
  setHindcastPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  setForecastPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  
  setSelectedMmsi: React.Dispatch<React.SetStateAction<string | null>>;
  setViewMode: React.Dispatch<React.SetStateAction<ViewMode>>;
  toggleLayer: (k: keyof LayerVisibility) => void;
  onFocusLookalike: (id: string) => void;
  randomizeWind: () => number;  // returns the new direction
  
  injectAdHocDetection: (det: DetectResponse) => void;
  
  // Legacy compatibility, though components will migrate off this
  frameIndex: number;
  frames: number;
  playing: boolean;
  setFrameIndex: React.Dispatch<React.SetStateAction<number>>;
  setPlaying: React.Dispatch<React.SetStateAction<boolean>>;
}

const SpillContext = createContext<SpillContextType | null>(null);

export function useSpillState() {
  const context = useContext(SpillContext);
  if (!context) {
    throw new Error("useSpillState must be used within a SpillProvider");
  }
  return context;
}

export function SpillProvider({ children }: { children: ReactNode }) {
  const [caseMeta, setCaseMeta] = useState<CaseMeta | null>(null);
  const [detection, setDetection] = useState<DetectResponse | null>(null);
  const [hindcast, setHindcast] = useState<HindcastResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [attribution, setAttribution] = useState<AttributeResponse | null>(null);
  const [report, setReport] = useState<ReportContent | null>(null);

  const [method, setMethod] = useState<DetectionMethod>("classical");
  const [detecting, setDetecting] = useState(false);
  const [drifting, setDrifting] = useState<"hindcast" | "forecast" | null>(null);
  const [attributing, setAttributing] = useState(false);
  const [reporting, setReporting] = useState(false);

  const [hindcastIndex, setHindcastIndex] = useState(0);
  const [forecastIndex, setForecastIndex] = useState(0);
  const [hindcastPlaying, setHindcastPlaying] = useState(false);
  const [forecastPlaying, setForecastPlaying] = useState(false);
  
  const [selectedMmsi, setSelectedMmsi] = useState<string | null>(null);
  const [dataMode, setDataMode] = useState<"live" | "offline">(getDataMode() as "live" | "offline");
  const [focusRequest, setFocusRequest] = useState<{ id: string; nonce: number } | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("analyst");

  const [layers, setLayers] = useState<LayerVisibility>({
    sar: true, slick: true, lookalikes: true, cone: true, particles: true, forecast: true, tracks: true,
  });
  
  const [mockWindDir, setMockWindDir] = useState(0);

  const autorun = new URLSearchParams(window.location.search).get("autorun") === "1";

  // Initialization
  useEffect(() => {
    const off = onDataModeChange(setDataMode as any);
    api.getCase().then(setCaseMeta);
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
        const a = await api.attribute(h.origin_estimate.point, h.origin_estimate.time_utc);
        setAttribution(a);
        setSelectedMmsi(a.candidates[0]?.mmsi ?? null);
      })
      .finally(() => setDetecting(false));
    return off;
  }, []);

  const hindcastFrames = hindcast?.particles_timeline.length ?? 0;
  const forecastFrames = forecast?.particles_timeline.length ?? 0;

  // Particle animation
  const timer = useRef<number | null>(null);
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

  const runHindcast = useCallback(async (windDir?: number) => {
    if (!detection?.slicks[0]) return;
    setDrifting("hindcast");
    try {
      const isAdhoc = detection.slicks[0].id.startsWith("adhoc-");
      const raw = isAdhoc
        ? (await import("../mock/hindcast.json")).default
        : await api.hindcast(detection.slicks[0].id, 24);
      let h = raw as HindcastResponse;
      if (isAdhoc) {
        const poly = detection.slicks[0].polygon as GeoJSON.Polygon;
        const pts = poly.coordinates[0];
        const cLon = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        const cLat = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        h = shiftHindcast(h, cLon - (-90.016633), cLat - 28.472599, windDir ?? mockWindDir);
      }
      setHindcast(h);
      setAttribution(null);
      setSelectedMmsi(null);
      setHindcastIndex(0);
      setHindcastPlaying(true);
    } finally {
      setDrifting(null);
    }
  }, [detection, mockWindDir]);

  const runForecast = useCallback(async (windDir?: number) => {
    if (!detection?.slicks[0]) return;
    setDrifting("forecast");
    try {
      const isAdhoc = detection.slicks[0].id.startsWith("adhoc-");
      const raw = isAdhoc
        ? (await import("../mock/forecast.json")).default
        : await api.forecast(detection.slicks[0].id, 72);
      let f = raw as ForecastResponse;
      if (isAdhoc) {
        const poly = detection.slicks[0].polygon as GeoJSON.Polygon;
        const pts = poly.coordinates[0];
        const cLon = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        const cLat = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        f = shiftForecast(f, cLon - (-90.016633), cLat - 28.472599, windDir ?? mockWindDir);
      }
      
      // Limit to max 15 segments as requested
      if (f.particles_timeline.length > 15) {
        f.particles_timeline = f.particles_timeline.slice(0, 15);
        const maxT = f.particles_timeline[f.particles_timeline.length - 1].t_offset_hours;
        f.cone = f.cone.filter(c => c.t_offset_hours <= maxT);
        
        // Also truncate the centroid path coordinates if possible (approximate by segment count)
        if (f.centroid_path.type === "LineString") {
           f.centroid_path.coordinates = f.centroid_path.coordinates.slice(0, 15);
        }
      }
      
      setForecast(f);
      setForecastIndex(0);
      setForecastPlaying(true);
    } finally {
      setDrifting(null);
    }
  }, [detection, mockWindDir]);

  const runAttribute = useCallback(async (windDir?: number) => {
    const o = hindcast?.origin_estimate;
    if (!o) return;
    setAttributing(true);
    try {
      const isAdhoc = detection?.slicks[0]?.id.startsWith("adhoc-");
      const raw = isAdhoc
        ? (await import("../mock/attribution.json")).default
        : await api.attribute(o.point, o.time_utc);
      let a = raw as AttributeResponse;
      if (isAdhoc && detection?.slicks[0]) {
        const poly = detection.slicks[0].polygon as GeoJSON.Polygon;
        const pts = poly.coordinates[0];
        const cLon = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        const cLat = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        a = shiftAttribution(a, cLon - (-90.016633), cLat - 28.472599, windDir ?? mockWindDir);
      }
      setAttribution(a);
      setSelectedMmsi(a.candidates[0]?.mmsi ?? null);
    } finally {
      setAttributing(false);
    }
  }, [hindcast, detection, mockWindDir]);

  const runReport = useCallback(async () => {
    if (!caseMeta || !detection?.slicks[0]) return;
    setReporting(true);
    try {
      setReport(await api.report(caseMeta.id, detection.slicks[0].id));
    } finally {
      setReporting(false);
    }
  }, [caseMeta, detection]);

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

  const injectAdHocDetection = useCallback((det: DetectResponse) => {
    setDetection(det);
    setHindcast(null);
    setForecast(null);
    setAttribution(null);
    setReport(null);
    setSelectedMmsi(null);
    setHindcastIndex(0);
    setForecastIndex(0);
  }, []);

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
        method,
        detecting,
        drifting,
        attributing,
        reporting,
        
        hindcastIndex,
        forecastIndex,
        hindcastPlaying,
        forecastPlaying,
        
        // Legacy compat (for DriftControls until updated)
        frameIndex: hindcastIndex,
        frames: Math.max(hindcastFrames, forecastFrames),
        playing: hindcastPlaying || forecastPlaying,
        setFrameIndex: setHindcastIndex,
        setPlaying: setHindcastPlaying,
        
        selectedMmsi,
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
        setViewMode,
        toggleLayer,
        onFocusLookalike,
        randomizeWind,
        injectAdHocDetection,
      }}
    >
      {children}
    </SpillContext.Provider>
  );
}
