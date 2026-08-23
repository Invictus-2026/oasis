import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import * as api from "./api/client";
import { getDataMode, onDataModeChange } from "./api/client";
import type {
  AttributeResponse,
  CaseMeta,
  DetectResponse,
  DetectionMethod,
  ForecastResponse,
  HindcastResponse,
  ProcessingStep,
  ReportContent,
} from "./api/types";
import DetectionPanel from "./components/DetectionPanel";
import DriftControls from "./components/DriftControls";
import ErrorBoundary from "./components/ErrorBoundary";
import EvidencePanel from "./components/EvidencePanel";
import LayerToggles from "./components/LayerToggles";
import MapView, { type LayerVisibility } from "./components/MapView";
import ScoreBreakdown from "./components/ScoreBreakdown";
import VesselTable from "./components/VesselTable";
import { Tag } from "./components/ui";

const FRAME_MS = 90;

export default function App() {
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

  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selectedMmsi, setSelectedMmsi] = useState<string | null>(null);
  const [dataMode, setDataMode] = useState(getDataMode());

  const [layers, setLayers] = useState<LayerVisibility>({
    slick: true, lookalikes: true, cone: true, particles: true, forecast: true, tracks: true,
  });

  // ---- warm start ------------------------------------------------------
  // Load the case AND run detection immediately. Two reasons: nothing spins
  // during a live demo, and with no network basemap an empty map is
  // indistinguishable from a broken one — there must be something on it the
  // moment the page opens.
  useEffect(() => {
    const off = onDataModeChange(setDataMode);
    api.getCase().then(setCaseMeta);
    setDetecting(true);
    api.detect("classical")
      .then(setDetection)
      .finally(() => setDetecting(false));
    return off;
  }, []);

  const frames = hindcast?.particles_timeline.length ?? 0;

  // ---- particle animation ------------------------------------------------
  const timer = useRef<number | null>(null);
  useEffect(() => {
    if (!playing || frames === 0) return;
    timer.current = window.setInterval(() => {
      setFrameIndex((i) => {
        if (i >= frames - 1) {
          setPlaying(false);
          return frames - 1;
        }
        return i + 1;
      });
    }, FRAME_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [playing, frames]);

  // ---- actions -----------------------------------------------------------
  const runDetect = useCallback(async (m: DetectionMethod) => {
    setMethod(m);
    setDetecting(true);
    try {
      setDetection(await api.detect(m));
      // A new detection invalidates everything downstream of it.
      setHindcast(null);
      setForecast(null);
      setAttribution(null);
      setReport(null);
      setSelectedMmsi(null);
      setFrameIndex(0);
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
      setFrameIndex(0);
      setPlaying(true);
    } finally {
      setDrifting(null);
    }
  }, [detection]);

  const runForecast = useCallback(async () => {
    if (!detection?.slicks[0]) return;
    setDrifting("forecast");
    try {
      setForecast(await api.forecast(detection.slicks[0].id, 12));
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

  const steps: ProcessingStep[] = useMemo(
    () => [
      ...(detection?.processing ?? []),
      ...(hindcast?.processing ?? []),
      ...(forecast?.processing ?? []),
      ...(attribution?.processing ?? []),
    ],
    [detection, hindcast, forecast, attribution],
  );

  const selected = attribution?.candidates.find((c) => c.mmsi === selectedMmsi) ?? null;

  return (
    <div className="flex h-full flex-col bg-ink-950">
      {/* ---- header ---- */}
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-ink-700 bg-ink-900 px-4 py-2">
        <div className="flex items-baseline gap-3">
          <h1 className="text-sm font-semibold tracking-tight text-mute-100">
            Spill<span className="text-slick-500">Trace</span>
          </h1>
          <span className="hidden text-[11px] text-mute-400 sm:inline">
            Oil spill detection, drift hindcast and vessel attribution
          </span>
        </div>
        <div className="flex items-center gap-2">
          {caseMeta && <Tag tone="mute">{caseMeta.name}</Tag>}
          <Tag tone={dataMode === "live" ? "good" : "warn"}>
            {dataMode === "live" ? "LIVE API" : "OFFLINE FIXTURES"}
          </Tag>
        </div>
      </header>

      {/* ---- constructed-scenario disclaimer: always visible, never dismissible ---- */}
      {caseMeta && (
        <div className="shrink-0 border-b border-slick-500/20 bg-slick-500/[0.07] px-4 py-1.5">
          <p className="text-[10px] leading-relaxed text-slick-400/90">
            <span className="font-semibold">Constructed validation scenario.</span>{" "}
            {caseMeta.disclaimer.replace("Constructed validation scenario. ", "")}
          </p>
        </div>
      )}

      {/* ---- body ---- */}
      <div className="flex min-h-0 flex-1">
        <main className="relative min-w-0 flex-1">
          <ErrorBoundary label="Map">
            <MapView
              caseMeta={caseMeta}
              detection={detection}
              hindcast={hindcast}
              forecast={forecast}
              attribution={attribution}
              layers={layers}
              frameIndex={frameIndex}
              selectedMmsi={selectedMmsi}
              onSelectVessel={setSelectedMmsi}
            />
          </ErrorBoundary>
          <div className="pointer-events-none absolute left-3 top-3 z-10">
            <LayerToggles layers={layers} onToggle={toggleLayer} />
          </div>
        </main>

        <aside className="w-[380px] shrink-0 space-y-2 overflow-y-auto border-l border-ink-700 bg-ink-900 p-2">
          <ErrorBoundary label="Detection">
            <DetectionPanel
              detection={detection}
              busy={detecting}
              method={method}
              unetAvailable={false}
              onRun={runDetect}
            />
          </ErrorBoundary>

          <ErrorBoundary label="Drift">
            <DriftControls
              hindcast={hindcast}
              forecast={forecast}
              busy={drifting}
              playing={playing}
              frameIndex={frameIndex}
              frameCount={frames}
              onHindcast={runHindcast}
              onForecast={runForecast}
              onScrub={(i) => { setPlaying(false); setFrameIndex(i); }}
              onTogglePlay={() => {
                if (!playing && frameIndex >= frames - 1) setFrameIndex(0);
                setPlaying((p) => !p);
              }}
            />
          </ErrorBoundary>

          <ErrorBoundary label="Attribution">
            <VesselTable
              attribution={attribution}
              busy={attributing}
              disabled={!hindcast}
              selectedMmsi={selectedMmsi}
              onRun={runAttribute}
              onSelect={setSelectedMmsi}
            />
          </ErrorBoundary>

          <ErrorBoundary label="Score breakdown">
            <ScoreBreakdown candidate={selected} weights={attribution?.weights ?? null} />
          </ErrorBoundary>

          <ErrorBoundary label="Evidence">
            <EvidencePanel
              caseMeta={caseMeta}
              steps={steps}
              report={report}
              busy={reporting}
              disabled={!detection}
              onGenerate={runReport}
            />
          </ErrorBoundary>
        </aside>
      </div>
    </div>
  );
}
