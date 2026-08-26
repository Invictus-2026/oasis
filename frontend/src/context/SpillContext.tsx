import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from "react";
import * as api from "../api/client";
import { getDataMode, onDataModeChange } from "../api/client";
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

  runDetect: (m: DetectionMethod) => Promise<void>;
  runHindcast: () => Promise<void>;
  runForecast: () => Promise<void>;
  runAttribute: () => Promise<void>;
  runReport: () => Promise<void>;
  
  setHindcastIndex: React.Dispatch<React.SetStateAction<number>>;
  setForecastIndex: React.Dispatch<React.SetStateAction<number>>;
  setHindcastPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  setForecastPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  
  setSelectedMmsi: React.Dispatch<React.SetStateAction<string | null>>;
  setViewMode: React.Dispatch<React.SetStateAction<ViewMode>>;
  toggleLayer: (k: keyof LayerVisibility) => void;
  onFocusLookalike: (id: string) => void;
  
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

  const runHindcast = useCallback(async () => {
    if (!detection?.slicks[0]) return;
    setDrifting("hindcast");
    try {
      const h = await api.hindcast(detection.slicks[0].id, 24);
      setHindcast(h);
      setAttribution(null);
      setSelectedMmsi(null);
      setHindcastIndex(0);
      setHindcastPlaying(true);
    } finally {
      setDrifting(null);
    }
  }, [detection]);

  const runForecast = useCallback(async () => {
    if (!detection?.slicks[0]) return;
    setDrifting("forecast");
    try {
      setForecast(await api.forecast(detection.slicks[0].id, 12));
      setForecastIndex(0);
      setForecastPlaying(true);
    } finally {
      setDrifting(null);
    }
  }, [detection]);

  const runAttribute = useCallback(async () => {
    const o = hindcast?.origin_estimate;
    if (!o) return;
    setAttributing(true);
    try {
      const a = await api.attribute(o.point, o.time_utc);
      setAttribution(a);
      setSelectedMmsi(a.candidates[0]?.mmsi ?? null);
    } finally {
      setAttributing(false);
    }
  }, [hindcast]);

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
      }}
    >
      {children}
    </SpillContext.Provider>
  );
}
