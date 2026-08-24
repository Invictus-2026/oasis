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
import Pipeline from "./components/Pipeline";
import ScoreBreakdown from "./components/ScoreBreakdown";
import Timeline, { type TimelineStage } from "./components/Timeline";
import VesselTable from "./components/VesselTable";
import { Tag } from "./components/ui";
import { km, utc } from "./lib/format";
import { ViewModeProvider, type ViewMode } from "./lib/viewMode";

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
  const [focusRequest, setFocusRequest] = useState<{ id: string; nonce: number } | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("analyst");

  const detectionRef = useRef<HTMLDivElement>(null);
  const driftRef = useRef<HTMLDivElement>(null);
  const attributionRef = useRef<HTMLDivElement>(null);
  const evidenceRef = useRef<HTMLDivElement>(null);
  const stageRefs: Record<TimelineStage, React.RefObject<HTMLDivElement | null>> = {
    detection: detectionRef, drift: driftRef, attribution: attributionRef, evidence: evidenceRef,
  };
  const onSelectStage = useCallback((stage: TimelineStage) => {
    stageRefs[stage].current?.scrollIntoView({ behavior: "smooth", block: "start" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [layers, setLayers] = useState<LayerVisibility>({
    sar: true, slick: true, lookalikes: true, cone: true, particles: true, forecast: true, tracks: true,
  });

  // ?autorun=1 runs the whole pipeline on load. Used for headless screenshots
  // and rehearsal, and as a live fallback if clicking through goes wrong.
  const autorun = new URLSearchParams(window.location.search).get("autorun") === "1";

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
      .then(async (det) => {
        setDetection(det);
        if (!autorun || !det.slicks[0]) return;
        const id = det.slicks[0].id;
        const h = await api.hindcast(id);
        setHindcast(h);
        setFrameIndex(h.particles_timeline.length - 1);
        setForecast(await api.forecast(id, 12));
        const a = await api.attribute(h.origin_estimate.point, h.origin_estimate.time_utc);
        setAttribution(a);
        setSelectedMmsi(a.candidates[0]?.mmsi ?? null);
      })
      .finally(() => setDetecting(false));
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const onFocusLookalike = useCallback((id: string) => {
    setFocusRequest({ id, nonce: Date.now() });
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
          <h1 className="text-[13px] font-semibold tracking-tight text-mute-100">
            Spill<span className="text-slick-500">Trace</span>
          </h1>
          <span className="hidden text-[11px] text-mute-400 sm:inline">
            Oil spill detection, drift hindcast and vessel attribution
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Analyst sees evidence, thresholds and reasoning; Executive sees the
              conclusion. Same data underneath either way — this only changes
              what's shown, never what's computed. */}
          <div className="flex items-center rounded-sm border border-ink-700 p-0.5 text-[10px] font-medium uppercase tracking-wider">
            {(["analyst", "executive"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setViewMode(m)}
                className={`rounded-sm px-2 py-0.5 transition-colors duration-150 ${
                  viewMode === m ? "bg-cone-500/20 text-cone-500" : "text-mute-400 hover:text-mute-200"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
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
              focusRequest={focusRequest}
            />
          </ErrorBoundary>
          {/* Vignette: a flat map reads as inert. A faint inset shadow gives the
              scene depth and pulls the eye toward the centre without costing
              any contrast on the data layers themselves. */}
          <div className="pointer-events-none absolute inset-0 z-[5] shadow-[inset_0_0_140px_40px_rgba(3,6,12,0.55)]" />
          <div className="pointer-events-none absolute left-3 top-3 z-10">
            <LayerToggles layers={layers} onToggle={toggleLayer} />
          </div>
          {/* HUD: the two real timestamps that anchor the whole case, always
              visible on the analytical surface itself rather than buried in a
              panel. No MapLibre text layer here — the offline style ships no
              glyphs, so this is a plain HTML overlay. */}
          {caseMeta && (
            <div className="pointer-events-none absolute right-3 top-3 z-10 rounded-sm bg-ink-950/70 px-2 py-1.5 text-right font-mono text-[10px] leading-relaxed text-mute-300 backdrop-blur-sm">
              <div>SCENE {utc(caseMeta.acquired_at)}</div>
              {hindcast && (
                <div className="text-cone-500">
                  ORIGIN {utc(hindcast.origin_estimate.time_utc)} · ±{km(hindcast.origin_estimate.uncertainty_radius_km, 1)}
                </div>
              )}
            </div>
          )}
          <div className="pointer-events-none absolute inset-x-3 bottom-3 z-10">
            <Timeline caseMeta={caseMeta} hindcast={hindcast} attribution={attribution} onSelectStage={onSelectStage} />
          </div>
        </main>

        <aside className="w-[380px] shrink-0 space-y-3 overflow-y-auto border-l border-ink-700 bg-ink-900 p-3">
          <ViewModeProvider value={viewMode}>
            <Pipeline
              caseMeta={caseMeta}
              detection={detection}
              detecting={detecting}
              hindcast={hindcast}
              forecast={forecast}
              drifting={drifting}
              attribution={attribution}
              attributing={attributing}
            />

            <div ref={detectionRef}>
              <ErrorBoundary label="Detection">
                <DetectionPanel
                  detection={detection}
                  busy={detecting}
                  method={method}
                  unetAvailable={true}
                  onRun={runDetect}
                  onFocusLookalike={onFocusLookalike}
                />
              </ErrorBoundary>
            </div>

            <div ref={driftRef}>
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
            </div>

            <div ref={attributionRef} className="space-y-3">
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
                <ScoreBreakdown candidate={selected} weights={attribution?.weights ?? null} provenance={attribution?.provenance} />
              </ErrorBoundary>
            </div>

            <div ref={evidenceRef}>
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
            </div>
          </ViewModeProvider>
        </aside>
      </div>
    </div>
  );
}
