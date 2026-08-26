import { useState } from "react";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider, AnalystOnly } from "../lib/viewMode";
import { hours, km, lonLat, utc } from "../lib/format";
import {
  Map, History, ArrowRight, Crosshair, HelpCircle, 
  Clock, Navigation, Search, AlertTriangle, ShieldCheck, Play, Pause, ChevronDown, ChevronRight, Wind
} from "lucide-react";

// ── helpers ────────────────────────────────────────────────────
function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
  const map: Record<string, string> = {
    gray:   "bg-ink-100 text-ink-600 border-ink-200",
    blue:   "bg-blue-50 text-blue-700 border-blue-200",
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    amber:  "bg-amber-50 text-amber-700 border-amber-200",
    red:    "bg-red-50 text-red-700 border-red-200",
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

// ── main component ─────────────────────────────────────────────
export default function DriftIntelligence() {
  const {
    detection,
    hindcast, forecast, drifting,
    hindcastPlaying, hindcastIndex, frames,
    runHindcast, runForecast, randomizeWind,
    setHindcastIndex, setHindcastPlaying,
    viewMode
  } = useSpillState();

  const isAdhoc = detection?.slicks[0]?.id.startsWith("adhoc-");

  const o = hindcast?.origin_estimate;
  const t = hindcast?.particles_timeline[Math.min(hindcastIndex, frames - 1)]?.t_offset_hours ?? 0;

  const handleTogglePlay = () => {
    if (!hindcastPlaying && hindcastIndex >= frames - 1) setHindcastIndex(0);
    setHindcastPlaying(p => !p);
  };

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">
        
        {/* ── Page Header ── */}
        <header className="page-header flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Map className="w-5 h-5 text-blue-600" />
              <h2 className="!mb-0">Drift Intelligence</h2>
            </div>
            <p>Compute particle drift backwards to estimate origin, or forwards to predict spread.</p>
          </div>
          
          <div className="flex items-center gap-2 bg-ink-50 p-1.5 rounded-lg border border-ink-200 self-start">
            <button
              onClick={() => runHindcast()}
              disabled={drifting === "hindcast"}
              className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold bg-white shadow-sm border border-ink-200 text-blue-600 hover:text-blue-700 transition-all"
            >
              <History className="w-4 h-4" />
              Backtrack Origin
              {drifting === "hindcast" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
            </button>
            <button
              onClick={() => runForecast()}
              disabled={drifting === "forecast" || !hindcast}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all ${
                !hindcast 
                  ? "text-ink-400 cursor-not-allowed opacity-60" 
                  : "bg-white shadow-sm border border-ink-200 text-purple-600 hover:text-purple-700"
              }`}
            >
              <ArrowRight className="w-4 h-4" />
              Forecast 12h
              {drifting === "forecast" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
            </button>
          </div>
        </header>

        {isAdhoc && (
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 mt-4 mb-2 flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-sm font-bold text-purple-900">Custom Origin Sandbox</span>
              <span className="text-xs text-purple-700">Explore mock environmental drift vectors from your uploaded slick.</span>
            </div>
            <button
              onClick={() => {
                const newDir = randomizeWind();
                runHindcast(newDir);
                runForecast(newDir);
              }}
              className="flex items-center gap-2 px-3 py-1.5 bg-white border border-purple-200 text-purple-700 hover:bg-purple-100 rounded text-xs font-bold transition-colors"
            >
              <Wind className="w-3.5 h-3.5" />
              Randomize Wind & Current
            </button>
          </div>
        )}

        {(!hindcast && !drifting) && (
          <div className="mt-8 flex flex-col items-center justify-center py-16 px-6 text-center border-2 border-dashed border-ink-200 rounded-2xl bg-ink-50/50">
            <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center mb-4">
              <Navigation className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold text-ink-900 mb-2">Lagrangian Particle Engine</h3>
            <p className="text-ink-500 max-w-md text-sm">
              Click <strong>Backtrack Origin</strong> to reverse-simulate ocean currents and winds to estimate where the slick was originally released.
            </p>
          </div>
        )}

        {drifting === "hindcast" && !hindcast && (
          <div className="mt-8 space-y-4">
             <div className="h-40 skeleton rounded-xl" />
             <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
               <div className="h-24 skeleton rounded-lg" />
               <div className="h-24 skeleton rounded-lg" />
             </div>
          </div>
        )}

        {hindcast && (
          <div className="flex flex-col gap-4 mt-6">
            
            {/* Playback Controls (Banner) */}
            <div className="bg-white border border-ink-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row items-center gap-4">
               <button 
                  onClick={handleTogglePlay}
                  className="flex items-center justify-center w-12 h-12 rounded-full bg-blue-600 text-white shadow-md hover:bg-blue-700 hover:scale-105 active:scale-95 transition-all shrink-0"
               >
                  {hindcastPlaying ? <Pause className="w-6 h-6 fill-current" /> : <Play className="w-6 h-6 fill-current ml-1" />}
               </button>
               
               <div className="flex-1 w-full flex flex-col">
                  <div className="flex justify-between items-end mb-2">
                     <span className="text-xs font-bold text-ink-600 uppercase tracking-wider">Timeline Scrub</span>
                     <span className="text-lg font-black text-blue-600 tabular-nums">
                        {t > 0 ? "+" : ""}{t.toFixed(0)} <span className="text-xs text-blue-400">HOURS</span>
                     </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, frames - 1)}
                    value={hindcastIndex}
                    onChange={(e) => { setHindcastPlaying(false); setHindcastIndex(Number(e.target.value)); }}
                    className="w-full h-2 cursor-pointer appearance-none rounded-full bg-ink-100 accent-blue-500"
                  />
               </div>
            </div>

            {/* Origin Estimate */}
            {o && (
              <SectionCard title="Origin Estimate" icon={<Crosshair className="w-4 h-4" />}>
                 <div className="flex items-center gap-2 mb-4">
                    <Badge color="blue">90% CONTAINMENT CONE</Badge>
                    <span className="text-[11px] text-ink-500">
                      The cone, not just the pin, represents the probabilistic answer region.
                    </span>
                 </div>
                 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatBox label="Most Likely Point" value={lonLat(o.point)} />
                    <StatBox label="Uncertainty Radius" value={km(o.uncertainty_radius_km)} />
                    <StatBox label="Release Time" value={utc(o.time_utc)} />
                    <StatBox 
                       label="Release Window" 
                       value={`${hours(o.time_window_hours[0])} – ${hours(o.time_window_hours[1])}`} 
                       hint="Inherited from Stage 1 age estimate"
                    />
                 </div>
                 <AnalystOnly>
                   <div className="mt-4 bg-blue-50 border border-blue-100 rounded-lg p-3 flex gap-3 text-sm text-blue-800">
                      <HelpCircle className="w-5 h-5 shrink-0 text-blue-500 mt-0.5" />
                      <div>
                        <strong>Analyst Note:</strong> The shaded region is where the release plausibly occurred, pooled over the whole age window from Stage 1 — the marker is only its densest point. The backtrack runs as far as that age window allows, so a less certain age gives a larger region.
                      </div>
                   </div>
                 </AnalystOnly>
              </SectionCard>
            )}

            {/* Forecast Impact */}
            {forecast && (
              <SectionCard title="Forward Forecast" icon={<ArrowRight className="w-4 h-4" />}>
                 {forecast.impact_flags.length === 0 ? (
                    <div className="flex items-center gap-3 text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg p-4">
                       <ShieldCheck className="w-6 h-6 shrink-0" />
                       <div>
                          <div className="font-bold">Clear Horizon</div>
                          <div className="text-sm">No coastline or protected area impact predicted within the 12h forecast window.</div>
                       </div>
                    </div>
                 ) : (
                    <div className="space-y-3">
                       {forecast.impact_flags.map((f) => (
                          <div key={f.name} className="flex items-center gap-4 bg-red-50 border border-red-200 rounded-lg p-4">
                             <AlertTriangle className="w-6 h-6 text-red-600 shrink-0" />
                             <div className="flex-1">
                                <div className="font-bold text-red-900">{f.name}</div>
                                <div className="text-sm text-red-700 mt-0.5">Predicted Impact</div>
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
            )}

          </div>
        )}
      </div>
    </ViewModeProvider>
  );
}
