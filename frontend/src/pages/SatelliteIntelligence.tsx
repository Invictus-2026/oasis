import { useState } from "react";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider, AnalystOnly } from "../lib/viewMode";
import { bearingLabel, deg, hours, km, km2, pct, ratio } from "../lib/format";
import {
  Satellite, Search, Layers, Zap, BrainCircuit, Maximize, 
  MapPin, Clock, FileWarning, EyeOff, AlertTriangle, Eye, ChevronDown, ChevronRight
} from "lucide-react";
import type { DetectionMethod } from "../api/types";

// ── helpers ────────────────────────────────────────────────────
function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
  const map: Record<string, string> = {
    gray:   "bg-ink-100 text-ink-600 border-ink-200",
    blue:   "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/30",
    purple: "bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-200 dark:border-purple-500/30",
    amber:  "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/30",
    red:    "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/30",
    green:  "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30",
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
    <div className="rounded-xl border border-ink-200 bg-white dark:bg-ink-100 shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3.5 bg-ink-50 border-b border-ink-200 hover:bg-ink-100 transition-colors text-left"
      >
        <span className="text-blue-600 dark:text-blue-400">{icon}</span>
        <span className="flex-1 text-sm font-bold text-ink-800 tracking-tight">{title}</span>
        {open ? <ChevronDown className="w-4 h-4 text-ink-400" /> : <ChevronRight className="w-4 h-4 text-ink-400" />}
      </button>
      {open && <div className="px-5 py-4">{children}</div>}
    </div>
  );
}

function StatBox({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50 p-3 flex flex-col justify-between">
      <div className="text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">{label}</div>
      <div className="text-lg font-black text-ink-900 font-mono">{value}</div>
      {hint && <div className="mt-1.5 text-[9px] text-ink-400 leading-tight">{hint}</div>}
    </div>
  );
}

// ── main component ─────────────────────────────────────────────
export default function SatelliteIntelligence() {
  const { detection, detecting, method, runDetect, onFocusLookalike, viewMode } = useSpillState();

  const slick = detection?.slicks[0];
  const unetAvailable = true;

  const handleRun = (m: DetectionMethod) => {
    runDetect(m);
  };

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">
        
        {/* ── Page Header ── */}
        <header className="page-header flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Satellite className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              <h2 className="!mb-0">Satellite Intelligence</h2>
            </div>
            <p>Analyze Synthetic Aperture Radar (SAR) imagery for anomalies and potential oil slicks.</p>
          </div>
          
          <div className="flex items-center gap-2 bg-ink-50 p-1.5 rounded-lg border border-ink-200 self-start">
            <button
              onClick={() => handleRun("classical")}
              disabled={detecting && method !== "classical"}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all ${
                method === "classical"
                  ? "bg-white dark:bg-ink-200 shadow-sm border border-ink-200 text-ink-900"
                  : "text-ink-600 hover:text-ink-900 hover:bg-ink-100/50"
              }`}
            >
              <Zap className="w-4 h-4" />
              Classical
              {detecting && method === "classical" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
            </button>
            <button
              onClick={() => handleRun("unet")}
              disabled={!unetAvailable || (detecting && method !== "unet")}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all ${
                method === "unet"
                  ? "bg-white dark:bg-ink-200 shadow-sm border border-ink-200 text-blue-600 dark:text-blue-400"
                  : "text-ink-600 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-ink-100/50"
              }`}
            >
              <BrainCircuit className="w-4 h-4" />
              U-Net
              {detecting && method === "unet" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
            </button>
          </div>
        </header>

        {!slick && !detecting && (
          <div className="mt-8 flex flex-col items-center justify-center py-16 px-6 text-center border-2 border-dashed border-ink-200 rounded-2xl bg-ink-50/50">
            <div className="w-16 h-16 bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 rounded-full flex items-center justify-center mb-4">
              <Search className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold text-ink-900 mb-2">No Detection Results</h3>
            <p className="text-ink-500 max-w-md text-sm">
              Select an algorithm from the top right to analyze the current SAR scene and extract potential slicks.
            </p>
          </div>
        )}

        {detecting && !slick && (
          <div className="mt-8 space-y-4">
             <div className="h-32 skeleton rounded-xl" />
             <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
               <div className="h-24 skeleton rounded-lg" />
               <div className="h-24 skeleton rounded-lg" />
               <div className="h-24 skeleton rounded-lg" />
               <div className="h-24 skeleton rounded-lg" />
             </div>
          </div>
        )}

        {slick && (
          <div className="flex flex-col gap-4 mt-6">
            
            {/* Primary Result Banner */}
            <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-xl p-5 flex flex-col md:flex-row items-center justify-between gap-6">
               <div>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                    <h3 className="text-lg font-black text-amber-900 dark:text-amber-300 tracking-tight">Confirmed Oil Slick</h3>
                  </div>
                  <p className="text-sm text-amber-700 dark:text-amber-400">
                    High confidence detection using {slick.method === "unet" ? "U-Net semantic segmentation" : "classical thresholding"}.
                  </p>
               </div>
               <div className="flex items-center gap-6 text-center bg-white dark:bg-ink-100 p-4 rounded-lg border border-amber-100 dark:border-amber-500/20 shadow-sm min-w-[200px] justify-center">
                  <div>
                     <div className="text-3xl font-black text-amber-600 dark:text-amber-400 tabular-nums">{slick.geometry.area_km2.toFixed(1)}</div>
                     <div className="text-[10px] font-bold uppercase tracking-widest text-amber-500 dark:text-amber-400">km² Area</div>
                  </div>
                  <div className="w-px h-10 bg-amber-100 dark:bg-amber-500/20" />
                  <div>
                     <div className="text-3xl font-black text-ink-900 tabular-nums">{(slick.confidence * 100).toFixed(0)}<span className="text-xl">%</span></div>
                     <div className="text-[10px] font-bold uppercase tracking-widest text-ink-400">Confidence</div>
                  </div>
               </div>
            </div>

            {/* Geometry & Morphology */}
            <SectionCard title="Geometry & Morphology" icon={<Maximize className="w-4 h-4" />}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                 <StatBox label="Perimeter" value={km(slick.geometry.perimeter_km)} />
                 <StatBox label="Orientation" value={`${deg(slick.geometry.orientation_deg)} ${bearingLabel(slick.geometry.orientation_deg)}`} />
                 <StatBox 
                    label="Elongation" 
                    value={ratio(slick.geometry.elongation)} 
                    hint={`Major:minor axis ratio (${slick.geometry.elongation.toFixed(1)}:1)`} 
                 />
                 <StatBox 
                    label="Compactness" 
                    value={slick.geometry.compactness.toFixed(3)} 
                    hint="Near 1 is circular, lower is trail-like." 
                 />
              </div>
            </SectionCard>

            {/* Weathering & Age Estimate */}
            {slick.age && (
              <SectionCard title="Age & Weathering Estimate" icon={<Clock className="w-4 h-4" />}>
                <div className="flex flex-col md:flex-row gap-6">
                   <div className="shrink-0 text-center md:text-left bg-blue-50 dark:bg-blue-500/10 border border-blue-100 dark:border-blue-500/30 p-4 rounded-lg">
                      <div className="text-[10px] font-bold uppercase tracking-widest text-blue-500 dark:text-blue-400 mb-1">Release Window</div>
                      <div className="text-2xl font-black text-blue-700 dark:text-blue-400 tabular-nums">
                         {hours(slick.age.min_hours)} – {hours(slick.age.max_hours)}
                      </div>
                      <div className="mt-2 flex justify-center md:justify-start">
                         <Badge color={slick.age.confidence === "high" ? "green" : slick.age.confidence === "medium" ? "blue" : "amber"}>
                           {slick.age.confidence.toUpperCase()} CONFIDENCE
                         </Badge>
                      </div>
                   </div>
                   <div className="flex-1 grid grid-cols-2 gap-4">
                      {slick.age.diffusivity_m2s != null && (
                        <StatBox label="Diffusivity" value={`${slick.age.diffusivity_m2s.toFixed(2)} m²/s`} />
                      )}
                      {slick.age.damping_db != null && (
                        <StatBox label="Radar Damping" value={`${slick.age.damping_db.toFixed(1)} dB`} />
                      )}
                      <div className="col-span-2 text-sm text-ink-600 bg-ink-50 p-3 rounded-lg border border-ink-100">
                         <strong>Methodology:</strong> {slick.age.method_note}
                      </div>
                   </div>
                </div>
              </SectionCard>
            )}

            {/* Evidence Subscores */}
            {slick.evidence && (
               <SectionCard title="Detection Evidence" icon={<Layers className="w-4 h-4" />} defaultOpen={false}>
                  <div className="grid gap-4">
                     {[
                        { label: "Backscatter damping", val: slick.evidence.contrast, w: slick.evidence.weight_contrast, hint: "Contrast vs local background. Mineral oil damps Bragg backscatter hard." },
                        { label: "Speckle suppression", val: slick.evidence.variance, w: slick.evidence.weight_variance, hint: "Inside/ambient speckle variance ratio, inverted. Oil is smoother, not just darker." },
                        { label: "Elongated shape", val: slick.evidence.shape, w: slick.evidence.weight_shape, hint: "Low compactness argues for a trail over a blob." },
                        { label: "Edge sharpness", val: slick.evidence.edge, w: slick.evidence.weight_edge, hint: "A discharge boundary is a sharp discontinuity; wind roughness fades." }
                     ].map(e => (
                        <div key={e.label}>
                           <div className="flex justify-between items-baseline mb-1">
                              <span className="text-sm font-semibold text-ink-800">{e.label}</span>
                              <span className="text-xs font-mono font-bold text-blue-600 dark:text-blue-400">{(e.val * 100).toFixed(0)}%</span>
                           </div>
                           <div className="h-2 bg-ink-100 rounded-full overflow-hidden">
                              <div className="h-full bg-blue-500 rounded-full" style={{ width: `${e.val * 100}%` }} />
                           </div>
                           <p className="text-[10px] text-ink-500 mt-1">{e.hint}</p>
                        </div>
                     ))}
                  </div>
               </SectionCard>
            )}

            {/* Ruled Out Look-alikes */}
            {detection && detection.rejected_lookalikes.length > 0 && (
              <SectionCard title={`Ruled Out Look-alikes (${detection.rejected_lookalikes.length})`} icon={<EyeOff className="w-4 h-4" />} defaultOpen={false}>
                 <div className="space-y-3">
                   {detection.rejected_lookalikes.map((r, idx) => (
                     <div key={r.id} className="flex flex-col sm:flex-row sm:items-start gap-4 p-4 rounded-lg border border-ink-200 bg-ink-50">
                        <div className="w-8 h-8 rounded-full bg-ink-200 text-ink-600 flex items-center justify-center font-bold text-xs shrink-0">
                           #{idx + 1}
                        </div>
                        <div className="flex-1">
                           <div className="flex items-center gap-2 mb-1">
                              <Badge color="gray">NOT OIL</Badge>
                              <span className="text-xs font-mono text-ink-500">Conf: {pct(r.confidence)}</span>
                           </div>
                           <p className="text-sm text-ink-700 leading-relaxed mb-2">{r.reason}</p>
                           <button 
                              onClick={() => onFocusLookalike(r.id)}
                              className="text-xs flex items-center gap-1 font-semibold text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                           >
                              <Eye className="w-3.5 h-3.5" /> View on Map
                           </button>
                        </div>
                     </div>
                   ))}
                 </div>
              </SectionCard>
            )}

          </div>
        )}
      </div>
    </ViewModeProvider>
  );
}
