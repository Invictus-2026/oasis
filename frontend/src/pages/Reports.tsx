import { useState } from "react";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider } from "../lib/viewMode";
import { utc } from "../lib/format";
import {
  FileText, Download, ShieldAlert, Clock, Anchor, Layers,
  ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, Circle,
  BookOpen, Database, Cpu, Map, Users,
} from "lucide-react";
import type { ProcessingStep, VesselCandidate } from "../api/types";

// ── helpers ────────────────────────────────────────────────────
function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
  const map: Record<string, string> = {
    gray:   "bg-ink-100 text-ink-600 border-ink-200",
    blue:   "bg-blue-50 text-blue-700 border-blue-200",
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    amber:  "bg-amber-50 text-amber-700 border-amber-200",
    red:    "bg-red-50 text-red-700 border-red-200",
    green:  "bg-emerald-50 text-emerald-700 border-emerald-200",
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
    <div className="rounded-xl border border-ink-200 bg-white shadow-sm overflow-hidden">
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

function StepRow({ step, index }: { step: ProcessingStep; index: number }) {
  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-ink-100 last:border-0 text-xs">
      <span className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-[10px] shrink-0">
        {index + 1}
      </span>
      <span className="flex-1 text-ink-700 font-medium">{step.name}</span>
      {step.detail && <span className="text-ink-400 truncate max-w-[200px]">{step.detail}</span>}
      <span className="font-mono text-[11px] text-blue-600 tabular-nums shrink-0">{step.duration_ms.toFixed(0)} ms</span>
    </div>
  );
}

function CandidateRow({ c }: { c: VesselCandidate }) {
  const isDark = c.flags.includes("DARK_VESSEL");
  return (
    <div className={`rounded-lg border px-4 py-3 ${isDark ? "border-red-200 bg-red-50/40" : "border-ink-200 bg-white"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-black shrink-0 ${isDark ? "bg-red-100 text-red-700" : "bg-ink-100 text-ink-600"}`}>
            {c.rank}
          </span>
          <div>
            <div className="text-sm font-bold text-ink-900">{c.name}</div>
            <div className="text-[11px] text-ink-500 font-mono">{c.mmsi} · {c.vessel_type}</div>
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-lg font-black text-ink-900 tabular-nums">{c.score.toFixed(3)}</div>
          <div className="text-[10px] text-ink-400 uppercase tracking-wider">score</div>
        </div>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-1">
        {isDark && <Badge color="red">DARK VESSEL</Badge>}
        {c.flags.filter(f => f !== "DARK_VESSEL").map(f => (
          <Badge key={f} color="amber">{f.replace(/_/g, " ")}</Badge>
        ))}
        <Badge color="gray">{c.closest_approach_km.toFixed(1)} km closest approach</Badge>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-600">{c.narrative}</p>
      {/* Score bars */}
      <div className="mt-2.5 grid grid-cols-5 gap-1.5">
        {(["proximity", "temporal_overlap", "ais_gap", "heading_consistency", "speed_anomaly"] as const).map(k => (
          <div key={k}>
            <div className="h-1.5 rounded-full bg-ink-100 overflow-hidden">
              <div
                className={`h-full rounded-full ${k === "ais_gap" && c.breakdown[k] > 0.5 ? "bg-red-500" : "bg-blue-500"}`}
                style={{ width: `${c.breakdown[k] * 100}%` }}
              />
            </div>
            <div className="text-[9px] text-ink-400 mt-0.5 text-center truncate">{k.replace(/_/g, " ")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── main component ─────────────────────────────────────────────
export default function Reports() {
  const { caseMeta, steps, report, reporting, detection, hindcast, forecast, attribution, runReport, viewMode } = useSpillState();

  const totalMs = steps.reduce((s, x) => s + x.duration_ms, 0);
  const hasAll = !!detection && !!hindcast && !!forecast;

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">

        {/* ── Page Header ── */}
        <header className="page-header">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2>Investigation Report</h2>
              <p>
                {caseMeta ? `${caseMeta.name} · ${caseMeta.scene_id}` : "Loading case metadata…"}
              </p>
            </div>
            <button
              onClick={runReport}
              disabled={reporting || !detection}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-bold transition-all
                ${reporting || !detection
                  ? "border-ink-200 bg-ink-50 text-ink-400 cursor-not-allowed"
                  : "border-blue-500 bg-blue-600 text-white hover:bg-blue-700 shadow-sm hover:shadow-md active:scale-[0.98]"
                }`}
            >
              {reporting ? (
                <><span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Generating…</>
              ) : (
                <><FileText className="w-4 h-4" /> Generate Report</>
              )}
            </button>
          </div>
        </header>

        {/* ── Status bar ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: "Detection", done: !!detection, icon: <Layers className="w-4 h-4" /> },
            { label: "Drift / Origin", done: !!hindcast, icon: <Map className="w-4 h-4" /> },
            { label: "Forecast", done: !!forecast, icon: <Clock className="w-4 h-4" /> },
            { label: "Attribution", done: !!attribution, icon: <Anchor className="w-4 h-4" /> },
          ].map(s => (
            <div key={s.label} className={`flex items-center gap-2.5 rounded-lg border p-3 ${s.done ? "border-emerald-200 bg-emerald-50" : "border-ink-200 bg-white"}`}>
              <span className={s.done ? "text-emerald-600" : "text-ink-400"}>{s.icon}</span>
              <div>
                <div className="text-[11px] font-bold text-ink-700">{s.label}</div>
                <div className={`text-[10px] ${s.done ? "text-emerald-600" : "text-ink-400"}`}>
                  {s.done ? "Complete" : "Pending"}
                </div>
              </div>
              {s.done
                ? <CheckCircle2 className="w-4 h-4 text-emerald-500 ml-auto" />
                : <Circle className="w-4 h-4 text-ink-300 ml-auto" />
              }
            </div>
          ))}
        </div>

        {!hasAll && (
          <div className="mb-6 flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
            <p className="text-sm text-amber-800">
              Run <strong>Detection</strong>, <strong>Hindcast</strong> and <strong>Forecast</strong> from the Maritime Map before generating a report.
            </p>
          </div>
        )}

        <div className="flex flex-col gap-4">

          {/* Case Overview */}
          <SectionCard title="Case Overview" icon={<BookOpen className="w-4 h-4" />}>
            {caseMeta ? (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3">
                {[
                  ["Case ID", caseMeta.id],
                  ["Scene ID", caseMeta.scene_id],
                  ["Acquired", utc(caseMeta.acquired_at)],
                  ["Area (W)", `${caseMeta.bbox.west.toFixed(3)}°`],
                  ["Area (E)", `${caseMeta.bbox.east.toFixed(3)}°`],
                  ["Center", `${caseMeta.center[0].toFixed(3)}°, ${caseMeta.center[1].toFixed(3)}°`],
                ].map(([label, val]) => (
                  <div key={label}>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-ink-400">{label}</div>
                    <div className="text-sm font-semibold text-ink-900 font-mono mt-0.5">{val}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-400 italic">Case metadata not loaded.</p>
            )}
          </SectionCard>

          {/* Detection summary */}
          <SectionCard title="Stage 1 — Detection" icon={<ShieldAlert className="w-4 h-4" />} defaultOpen={!!detection}>
            {detection ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {detection.slicks.map(s => (
                  <div key={s.id} className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-amber-600 mb-1">Oil Slick</div>
                    <div className="text-2xl font-black text-ink-900">{s.geometry.area_km2.toFixed(1)}</div>
                    <div className="text-[10px] text-ink-500">km² area</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      <Badge color="amber">{(s.confidence * 100).toFixed(0)}% conf.</Badge>
                      <Badge color="gray">{s.method}</Badge>
                    </div>
                  </div>
                ))}
                <div className="rounded-lg border border-ink-200 bg-ink-50 p-3">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">Ruled Out</div>
                  <div className="text-2xl font-black text-ink-900">{detection.rejected_lookalikes.length}</div>
                  <div className="text-[10px] text-ink-500">look-alikes</div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-ink-400 italic">Run detection to see results.</p>
            )}
          </SectionCard>

          {/* Origin / Hindcast summary */}
          <SectionCard title="Stage 2 — Drift Origin" icon={<Map className="w-4 h-4" />} defaultOpen={!!hindcast}>
            {hindcast ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  ["Estimated origin", `${hindcast.origin_estimate.point[0].toFixed(4)}°, ${hindcast.origin_estimate.point[1].toFixed(4)}°`],
                  ["Uncertainty radius", `${hindcast.origin_estimate.uncertainty_radius_km.toFixed(1)} km`],
                  ["Release time", utc(hindcast.origin_estimate.time_utc)],
                  ["Time window", `${hindcast.origin_estimate.time_window_hours[0].toFixed(0)} – ${hindcast.origin_estimate.time_window_hours[1].toFixed(0)} h`],
                ].map(([label, val]) => (
                  <div key={label} className="rounded-lg border border-blue-100 bg-blue-50 p-3">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-blue-500 mb-1">{label}</div>
                    <div className="text-sm font-black text-ink-900 font-mono">{val}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-400 italic">Run backtrack to see origin estimate.</p>
            )}
          </SectionCard>

          {/* Forecast impact flags */}
          <SectionCard title="Stage 2b — Forecast Impact" icon={<Clock className="w-4 h-4" />} defaultOpen={!!forecast}>
            {forecast ? (
              forecast.impact_flags.length === 0 ? (
                <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3">
                  <CheckCircle2 className="w-5 h-5 shrink-0" />
                  <span className="text-sm font-semibold">No coastline impact forecast within horizon.</span>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {forecast.impact_flags.map(f => (
                    <div key={f.name} className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                      <AlertTriangle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                      <div>
                        <div className="text-sm font-bold text-red-800">{f.name}</div>
                        <div className="text-[11px] text-red-600 font-mono mt-0.5">
                          ETA {f.eta_hours.toFixed(1)} h · {f.distance_km.toFixed(1)} km
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )
            ) : (
              <p className="text-sm text-ink-400 italic">Run forecast to see impact flags.</p>
            )}
          </SectionCard>

          {/* Candidate vessels */}
          <SectionCard title="Stage 3 — Vessel Attribution" icon={<Users className="w-4 h-4" />} defaultOpen={!!attribution}>
            {attribution ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2 text-[11px] text-ink-500">
                  <span>{attribution.total_vessels_in_region} vessels in region</span>
                  <span className="text-ink-300">→</span>
                  <span className="font-bold text-ink-700">{attribution.after_filter} candidates</span>
                </div>
                {attribution.candidates.map(c => <CandidateRow key={c.mmsi} c={c} />)}
              </div>
            ) : (
              <p className="text-sm text-ink-400 italic">Run attribution to see candidates.</p>
            )}
          </SectionCard>

          {/* Data sources */}
          {caseMeta && (
            <SectionCard title="Data Sources & Provenance" icon={<Database className="w-4 h-4" />} defaultOpen={false}>
              <ul className="divide-y divide-ink-100">
                {caseMeta.sources.map(s => (
                  <li key={s.name} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                    <Badge color={s.is_synthetic ? "amber" : "blue"}>{s.is_synthetic ? "SYNTHETIC" : s.kind.toUpperCase()}</Badge>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold text-ink-800 truncate">{s.name}</div>
                      {s.note && <p className="text-[11px] text-ink-500 mt-0.5 leading-relaxed">{s.note}</p>}
                    </div>
                    {s.licence && <span className="text-[10px] text-ink-400 shrink-0">{s.licence}</span>}
                  </li>
                ))}
              </ul>
            </SectionCard>
          )}

          {/* Processing chain */}
          {steps.length > 0 && (
            <SectionCard title="Processing Chain" icon={<Cpu className="w-4 h-4" />} defaultOpen={false}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] text-ink-500 uppercase font-bold tracking-wider">{steps.length} steps</span>
                <span className="text-[11px] font-mono font-bold text-blue-600">{totalMs.toFixed(0)} ms total</span>
              </div>
              <div className="divide-y divide-ink-100">
                {steps.map((s, i) => <StepRow key={`${s.name}-${i}`} step={s} index={i} />)}
              </div>
            </SectionCard>
          )}

          {/* Limitations */}
          {report && (
            <SectionCard title="Known Limitations" icon={<AlertTriangle className="w-4 h-4" />}>
              <ul className="space-y-2">
                {report.limitations.map((l, i) => (
                  <li key={i} className="flex gap-2.5 text-sm text-ink-600 leading-relaxed">
                    <span className="mt-1 w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                    {l}
                  </li>
                ))}
              </ul>
            </SectionCard>
          )}

          {/* Disclaimer */}
          {caseMeta?.disclaimer && (
            <div className="rounded-xl border border-ink-200 bg-ink-50 px-5 py-4">
              <div className="text-[10px] font-bold uppercase tracking-widest text-ink-500 mb-1.5">Disclaimer</div>
              <p className="text-[11px] leading-relaxed text-ink-600">{caseMeta.disclaimer}</p>
            </div>
          )}

        </div>
      </div>
    </ViewModeProvider>
  );
}
