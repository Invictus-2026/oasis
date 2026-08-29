import { useState } from "react";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider, AnalystOnly } from "../lib/viewMode";
import SpillSelector from "../components/SpillSelector";
import { hours, km, lonLat, utc } from "../lib/format";
import {
  Map, History, ArrowRight, Crosshair, HelpCircle,
  Navigation, AlertTriangle, ShieldCheck, Play, Pause, ChevronDown, ChevronRight, Wind, Activity
} from "lucide-react";

// ── helpers ────────────────────────────────────────────────────
function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
  const map: Record<string, string> = {
    gray: "bg-ink-100 text-ink-600 border-ink-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    red: "bg-red-50 text-red-700 border-red-200",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${map[color] ?? map.gray}`}>
      {children}
    </span>
  );
}

function SectionCard({ title, icon, children, defaultOpen = true }: {
  title: string; icon: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-ink-200 bg-white shadow-sm overflow-hidden mt-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3.5 bg-ink-50 border-b border-ink-200 hover:bg-ink-100 transition-colors text-left"
      >
        <span className="text-blue-600">{icon}</span>
        <span className="flex-1 text-sm font-bold text-ink-800 tracking-tight">{title}</span>
        {open ? <ChevronDown className="w-4 h-4 text-ink-400" /> : <ChevronRight className="w-4 h-4 text-ink-400" />}
      </button>
      {open && <div className="px-5 py-4">{children}</div>}
    </div>
  );
}

function StatBox({ label, value, hint }: { label: string; value: string | React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50 p-3 flex flex-col justify-between">
      <div className="text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">{label}</div>
      <div className="text-sm md:text-lg font-black text-ink-900 font-mono">{value}</div>
      {hint && <div className="mt-1.5 text-[9px] text-ink-400 leading-tight">{hint}</div>}
    </div>
  );
}

function calcDistance([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]) {
  const R = 6371; // km
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

// ── main component ─────────────────────────────────────────────
export default function DriftIntelligence() {
  const {
    hindcast, forecast, drifting,
    hindcastPlaying, hindcastIndex, hindcastFrames,
    forecastPlaying, forecastIndex, forecastFrames,
    runHindcast, runForecast, randomizeWind,
    setHindcastIndex, setHindcastPlaying,
    setForecastIndex, setForecastPlaying,
    viewMode, activeSlickId, setActiveSlickId
  } = useSpillState();

  const [activeTab, setActiveTab] = useState<"hindcast" | "forecast">("hindcast");

  if (!activeSlickId) {
    return (
      <SpillSelector
        title="Drift Intelligence"
        description="Select an oil spill region to reverse-simulate ocean currents or predict its future spread."
      />
    );
  }

  const isAdhoc = activeSlickId.startsWith("adhoc-");

  // Playback handlers
  const handleTogglePlayHindcast = () => {
    if (!hindcastPlaying && hindcastIndex >= hindcastFrames - 1) setHindcastIndex(0);
    setHindcastPlaying(p => !p);
  };

  const handleTogglePlayForecast = () => {
    if (!forecastPlaying && forecastIndex >= forecastFrames - 1) setForecastIndex(0);
    setForecastPlaying(p => !p);
  };

  // Forecast Milestones computation
  let milestones: any[] = [];
  if (forecast && forecast.particles_timeline.length > 0) {
    const horizons = [2, 4, 6, 8, 12, 24, 36, 48, 72];
    milestones = horizons.map(h => {
      let closestIdx = 0;
      let minDiff = Infinity;
      forecast.particles_timeline.forEach((frame, idx) => {
        const diff = Math.abs(frame.t_offset_hours - h);
        if (diff < minDiff) {
          minDiff = diff;
          closestIdx = idx;
        }
      });
      
      // If the forecast doesn't cover this horizon yet, skip it
      if (minDiff > 2) return null;
      
      const p0 = forecast.centroid_path.coordinates[0];
      const p1 = forecast.centroid_path.coordinates[closestIdx];
      const distance = p0 && p1 ? calcDistance(p0 as [number, number], p1 as [number, number]) : 0;
      
      const targetT = forecast.particles_timeline[closestIdx].t_offset_hours;
      const coneAtT = forecast.cone.find(c => c.t_offset_hours === targetT);
      
      let spreadRadius = 0;
      if (coneAtT && p1) {
        const pts = coneAtT.polygon.coordinates[0] || [];
        let maxD = 0;
        pts.forEach(pt => {
          const d = calcDistance(p1 as [number, number], pt as [number, number]);
          if (d > maxD) maxD = d;
        });
        spreadRadius = maxD;
      }
      
      return { horizon: h, index: closestIdx, distance, spreadRadius, targetT };
    }).filter(Boolean);
  }

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">

        {/* ── Page Header ── */}
        <header className="page-header flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <button onClick={() => setActiveSlickId(null)} className="text-ink-400 hover:text-blue-600 transition-colors mr-1 text-sm font-bold">
                ← Back
              </button>
              <Map className="w-5 h-5 text-blue-600" />
              <h2 className="!mb-0">Drift Intelligence</h2>
            </div>
            <p>Compute particle drift backwards to estimate origin, or forwards to predict spread.</p>
          </div>
        </header>

        {isAdhoc && (
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 mt-4 flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-sm font-bold text-purple-900">Custom Origin Sandbox</span>
              <span className="text-xs text-purple-700">Explore mock environmental drift vectors from your uploaded slick.</span>
            </div>
            <button
              onClick={() => {
                const newDir = randomizeWind();
                if (activeTab === "hindcast") runHindcast(newDir);
                else runForecast(newDir);
              }}
              className="flex items-center gap-2 px-3 py-1.5 bg-white border border-purple-200 text-purple-700 hover:bg-purple-100 rounded text-xs font-bold transition-colors"
            >
              <Wind className="w-3.5 h-3.5" />
              Randomize Wind & Current
            </button>
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-2 mt-6 border-b border-ink-200 pb-px">
          <button
            onClick={() => setActiveTab("hindcast")}
            className={`px-4 py-2 font-bold text-sm tracking-wide transition-colors border-b-2 ${
              activeTab === "hindcast"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-ink-500 hover:text-ink-800"
            }`}
          >
            Hindcast (Backtrack)
          </button>
          <button
            onClick={() => setActiveTab("forecast")}
            className={`px-4 py-2 font-bold text-sm tracking-wide transition-colors border-b-2 ${
              activeTab === "forecast"
                ? "border-purple-600 text-purple-600"
                : "border-transparent text-ink-500 hover:text-ink-800"
            }`}
          >
            Forecast (Predict)
          </button>
        </div>

        {/* ── Hindcast Tab ── */}
        {activeTab === "hindcast" && (
          <div className="mt-6 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-ink-600">Reverse-simulate ocean currents and winds to find the origin.</p>
              <button
                onClick={() => runHindcast()}
                disabled={drifting === "hindcast"}
                className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-bold bg-blue-600 text-white hover:bg-blue-700 transition-all shadow-sm"
              >
                <History className="w-4 h-4" />
                Run Hindcast
                {drifting === "hindcast" && <span className="w-3 h-3 rounded-full border-2 border-white/30 border-t-white animate-spin ml-1" />}
              </button>
            </div>

            {drifting === "hindcast" && !hindcast && (
              <div className="mt-4 space-y-4">
                <div className="h-20 skeleton rounded-xl" />
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="h-24 skeleton rounded-lg" />
                  <div className="h-24 skeleton rounded-lg" />
                </div>
              </div>
            )}

            {hindcast && (
              <>
                <div className="bg-white border border-ink-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row items-center gap-4">
                  <button
                    onClick={handleTogglePlayHindcast}
                    className="flex items-center justify-center w-12 h-12 rounded-full bg-blue-600 text-white shadow-md hover:bg-blue-700 hover:scale-105 active:scale-95 transition-all shrink-0"
                  >
                    {hindcastPlaying ? <Pause className="w-6 h-6 fill-current" /> : <Play className="w-6 h-6 fill-current ml-1" />}
                  </button>

                  <div className="flex-1 w-full flex flex-col">
                    <div className="flex justify-between items-end mb-2">
                      <span className="text-xs font-bold text-ink-600 uppercase tracking-wider">Hindcast Scrub</span>
                      <span className="text-lg font-black text-blue-600 tabular-nums">
                        {hindcast?.particles_timeline[Math.min(hindcastIndex, hindcastFrames - 1)]?.t_offset_hours.toFixed(0)} <span className="text-xs text-blue-400">HOURS</span>
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={Math.max(0, hindcastFrames - 1)}
                      value={hindcastIndex}
                      onChange={(e) => { setHindcastPlaying(false); setHindcastIndex(Number(e.target.value)); }}
                      className="w-full h-2 cursor-pointer appearance-none rounded-full bg-ink-100 accent-blue-500"
                    />
                  </div>
                </div>

                {hindcast.origin_estimate && (
                  <SectionCard title="Origin Estimate" icon={<Crosshair className="w-4 h-4" />}>
                    <div className="flex items-center gap-2 mb-4">
                      <Badge color="blue">90% CONTAINMENT CONE</Badge>
                      <span className="text-[11px] text-ink-500">
                        The cone represents the probabilistic answer region.
                      </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      <StatBox label="Most Likely Point" value={lonLat(hindcast.origin_estimate.point)} />
                      <StatBox label="Uncertainty Radius" value={km(hindcast.origin_estimate.uncertainty_radius_km)} />
                      <StatBox label="Release Time" value={utc(hindcast.origin_estimate.time_utc)} />
                      <StatBox
                        label="Release Window"
                        value={`${hours(hindcast.origin_estimate.time_window_hours[0])} – ${hours(hindcast.origin_estimate.time_window_hours[1])}`}
                        hint="Inherited from Stage 1 age estimate"
                      />
                    </div>
                    <AnalystOnly>
                      <div className="mt-4 bg-blue-50 border border-blue-100 rounded-lg p-3 flex gap-3 text-sm text-blue-800">
                        <HelpCircle className="w-5 h-5 shrink-0 text-blue-500 mt-0.5" />
                        <div>
                          <strong>Analyst Note:</strong> The shaded region is where the release plausibly occurred, pooled over the whole age window from Stage 1 — the marker is only its densest point.
                        </div>
                      </div>
                    </AnalystOnly>
                  </SectionCard>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Forecast Tab ── */}
        {activeTab === "forecast" && (
          <div className="mt-6 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-ink-600">Predict future spread and coastal impacts for up to 72 hours.</p>
              <button
                onClick={() => runForecast()}
                disabled={drifting === "forecast"}
                className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-bold bg-purple-600 text-white hover:bg-purple-700 transition-all shadow-sm"
              >
                <ArrowRight className="w-4 h-4" />
                Run Forecast 72h
                {drifting === "forecast" && <span className="w-3 h-3 rounded-full border-2 border-white/30 border-t-white animate-spin ml-1" />}
              </button>
            </div>

            {drifting === "forecast" && !forecast && (
              <div className="mt-4 space-y-4">
                <div className="h-20 skeleton rounded-xl" />
                <div className="grid grid-cols-2 gap-4">
                  <div className="h-32 skeleton rounded-lg" />
                  <div className="h-32 skeleton rounded-lg" />
                </div>
              </div>
            )}

            {forecast && (
              <>
                <div className="bg-white border border-ink-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row items-center gap-4">
                  <button
                    onClick={handleTogglePlayForecast}
                    className="flex items-center justify-center w-12 h-12 rounded-full bg-purple-600 text-white shadow-md hover:bg-purple-700 hover:scale-105 active:scale-95 transition-all shrink-0"
                  >
                    {forecastPlaying ? <Pause className="w-6 h-6 fill-current" /> : <Play className="w-6 h-6 fill-current ml-1" />}
                  </button>

                  <div className="flex-1 w-full flex flex-col">
                    <div className="flex justify-between items-end mb-2">
                      <span className="text-xs font-bold text-ink-600 uppercase tracking-wider">Forecast Scrub</span>
                      <span className="text-lg font-black text-purple-600 tabular-nums">
                        +{forecast?.particles_timeline[Math.min(forecastIndex, forecastFrames - 1)]?.t_offset_hours.toFixed(0)} <span className="text-xs text-purple-400">HOURS</span>
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={Math.max(0, forecastFrames - 1)}
                      value={forecastIndex}
                      onChange={(e) => { setForecastPlaying(false); setForecastIndex(Number(e.target.value)); }}
                      className="w-full h-2 cursor-pointer appearance-none rounded-full bg-ink-100 accent-purple-500"
                    />
                  </div>
                </div>

                <SectionCard title="Impact Warnings" icon={<AlertTriangle className="w-4 h-4 text-red-500" />}>
                  {forecast.impact_flags.length === 0 ? (
                    <div className="flex items-center gap-3 text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg p-4">
                      <ShieldCheck className="w-6 h-6 shrink-0" />
                      <div>
                        <div className="font-bold">Clear Horizon</div>
                        <div className="text-sm">No coastal or infrastructure impacts predicted.</div>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {forecast.impact_flags.map((f) => (
                        <div key={f.name} className="flex items-center gap-4 bg-red-50 border border-red-200 rounded-lg p-4">
                          <AlertTriangle className="w-6 h-6 text-red-600 shrink-0" />
                          <div className="flex-1">
                            <div className="font-bold text-red-900">{f.name}</div>
                            <div className="text-sm text-red-700 mt-0.5">{f.kind} Impact</div>
                          </div>
                          <div className="text-right">
                            <div className="text-lg font-black text-red-700 tabular-nums">{hours(f.eta_hours)}</div>
                            <div className="text-[10px] font-bold uppercase tracking-widest text-red-500">ETA</div>
                          </div>
                          <div className="w-px h-10 bg-red-200 mx-2" />
                          <div className="text-right">
                            <div className="text-lg font-black text-ink-900 tabular-nums">{km(f.distance_km)}</div>
                            <div className="text-[10px] font-bold uppercase tracking-widest text-ink-400">Distance</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </SectionCard>

                <SectionCard title="Time Horizon Analysis" icon={<Activity className="w-4 h-4 text-purple-600" />}>
                  <div className="text-sm text-ink-500 mb-4">
                    Click on a milestone to jump the map to that specific hour and visualize the predicted spread.
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                    {milestones.map((m) => {
                      const isActive = Math.abs(forecastIndex - m.index) < 3;
                      return (
                        <button
                          key={m.horizon}
                          onClick={() => { setForecastPlaying(false); setForecastIndex(m.index); }}
                          className={`flex flex-col text-left p-3 rounded-lg border transition-all ${
                            isActive
                              ? "bg-purple-50 border-purple-300 ring-2 ring-purple-200 shadow-sm"
                              : "bg-ink-50 border-ink-200 hover:border-purple-200 hover:bg-white"
                          }`}
                        >
                          <div className="flex justify-between items-center mb-2 w-full">
                            <span className="font-black text-lg text-purple-800">+{m.horizon}h</span>
                            {isActive && <Badge color="purple">ACTIVE</Badge>}
                          </div>
                          <div className="w-full flex justify-between items-center">
                            <span className="text-[11px] text-ink-500 font-bold uppercase">Distance</span>
                            <span className="text-sm font-mono text-ink-900 font-bold">{km(m.distance)}</span>
                          </div>
                          <div className="w-full flex justify-between items-center mt-1">
                            <span className="text-[11px] text-ink-500 font-bold uppercase">Spread Radius</span>
                            <span className="text-sm font-mono text-ink-900 font-bold">{km(m.spreadRadius)}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </SectionCard>
              </>
            )}
          </div>
        )}

      </div>
    </ViewModeProvider>
  );
}
