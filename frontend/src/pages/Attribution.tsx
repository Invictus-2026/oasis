import { useState } from "react";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider } from "../lib/viewMode";
import { km } from "../lib/format";
import { SCORE_FACTORS } from "../api/types";
import {
  Anchor, CheckCircle2, AlertTriangle, HelpCircle,
  Search, Eye, ShieldAlert, SlidersHorizontal, ChevronDown, ChevronRight
} from "lucide-react";
import SpillSelector from "../components/SpillSelector";

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

// ── main component ─────────────────────────────────────────────
export default function Attribution() {
  const { attribution, attributing, hindcast, selectedMmsi, runAttribute, setSelectedMmsi, viewMode, activeSlickId, setActiveSlickId } = useSpillState();

  if (!activeSlickId) {
    return (
      <SpillSelector
        title="Attribution Engine"
        description="Select an oil spill to correlate its origin with historical vessel tracks and identify candidates."
      />
    );
  }

  const selectedCandidate = attribution?.candidates.find((c) => c.mmsi === selectedMmsi) ?? null;

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
              <Anchor className="w-5 h-5 text-blue-600" />
              <h2 className="!mb-0">Vessel Attribution</h2>
            </div>
            <p>Correlate the estimated spill origin with historical AIS data to identify candidate vessels.</p>
          </div>

          <div className="flex items-center gap-2 bg-ink-50 p-1.5 rounded-lg border border-ink-200 self-start">
            <button
              onClick={() => runAttribute()}
              disabled={attributing || !hindcast}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-bold transition-all ${!hindcast
                ? "text-ink-400 cursor-not-allowed opacity-60"
                : "bg-blue-600 shadow-sm border border-blue-700 text-white hover:bg-blue-700 active:scale-95"
                }`}
            >
              <Search className="w-4 h-4" />
              Correlate AIS
              {attributing && <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin ml-1" />}
            </button>
          </div>
        </header>

        {(!attribution && !attributing) && (
          <div className="mt-8 flex flex-col items-center justify-center py-16 px-6 text-center border-2 border-dashed border-ink-200 rounded-2xl bg-ink-50/50">
            <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center mb-4">
              <Anchor className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold text-ink-900 mb-2">AIS Traffic Correlation</h3>
            <p className="text-ink-500 max-w-md text-sm">
              {!hindcast
                ? "Run the drift backtrack first. Candidates are screened against the estimated origin, not the observed slick."
                : "Click Correlate AIS to screen historical maritime traffic against the estimated origin."
              }
            </p>
          </div>
        )}

        {attributing && !attribution && (
          <div className="mt-8 space-y-4">
            <div className="h-24 skeleton rounded-xl" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="col-span-2 h-96 skeleton rounded-lg" />
              <div className="col-span-1 h-96 skeleton rounded-lg" />
            </div>
          </div>
        )}

        {attribution && (
          <div className="flex flex-col gap-4 mt-6">
            {/* Results Banner */}
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 flex flex-col md:flex-row items-center justify-between gap-6">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                  <h3 className="text-lg font-black text-emerald-900 tracking-tight">Correlation Complete</h3>
                </div>
                <p className="text-sm text-emerald-700">
                  Filtered {attribution.total_vessels_in_region} vessels down to a highly probable shortlist of {attribution.after_filter} candidates based on spatial overlap, trajectory, and behavioral anomalies.
                </p>
              </div>
              <div className="flex items-center gap-6 text-center bg-white p-4 rounded-lg border border-emerald-100 shadow-sm min-w-[200px] justify-center shrink-0">
                <div>
                  <div className="text-3xl font-black text-ink-900 tabular-nums">{attribution.total_vessels_in_region}</div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-ink-400">Total</div>
                </div>
                <div className="w-px h-10 bg-emerald-100" />
                <div>
                  <div className="text-3xl font-black text-emerald-600 tabular-nums">{attribution.after_filter}</div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-500">Candidates</div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-5 items-start">

              {/* Vessel List */}
              <div className="w-full">
                <SectionCard title={`Candidate Shortlist (${attribution.candidates.length})`} icon={<Anchor className="w-4 h-4" />}>
                  <div className="flex flex-col gap-3">
                    {attribution.candidates.map((c) => {
                      const selected = c.mmsi === selectedMmsi;
                      const isDark = c.flags.includes("DARK_VESSEL");

                      return (
                        <div
                          key={c.mmsi}
                          onClick={() => setSelectedMmsi(selected ? null : c.mmsi)}
                          className={`cursor-pointer rounded-xl border p-4 transition-all duration-200 ${selected
                            ? "border-blue-400 bg-blue-50/50 shadow-md ring-2 ring-blue-100"
                            : "border-ink-200 bg-white hover:border-ink-300 hover:shadow-sm"
                            }`}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex gap-3">
                              <div className={`w-8 h-8 rounded-full flex items-center justify-center font-black text-sm shrink-0 ${isDark ? "bg-red-100 text-red-700" : "bg-ink-100 text-ink-700"
                                }`}>
                                {c.rank}
                              </div>
                              <div>
                                <div className="text-sm font-bold text-ink-900 mb-0.5">{c.name}</div>
                                <div className="text-[11px] font-mono text-ink-500">MMSI {c.mmsi} · {c.vessel_type}</div>
                              </div>
                            </div>
                            <div className="text-right shrink-0">
                              <div className="text-lg font-black text-ink-900 tabular-nums">{c.score.toFixed(3)}</div>
                              <div className="text-[9px] font-bold uppercase tracking-wider text-ink-400">Match Score</div>
                            </div>
                          </div>

                          <div className="mt-3 flex items-center gap-3">
                            <div className="flex-1 h-2 rounded-full bg-ink-100 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${isDark ? "bg-red-500" : "bg-emerald-500"}`}
                                style={{ width: `${c.score * 100}%` }}
                              />
                            </div>
                            <div className="text-xs font-mono text-ink-500 shrink-0">
                              {km(c.closest_approach_km)} closest
                            </div>
                          </div>

                          {c.flags.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-1.5">
                              {c.flags.map(f => (
                                <Badge key={f} color={f === "DARK_VESSEL" ? "red" : "amber"}>
                                  {f.replace(/_/g, " ")}
                                </Badge>
                              ))}
                            </div>
                          )}

                          {selected && (
                            <div className="mt-4 pt-3 border-t border-blue-100">
                              <p className="text-xs text-blue-900 leading-relaxed bg-blue-100/50 p-3 rounded-lg border border-blue-100">
                                <strong>Analyst Summary:</strong> {c.narrative}
                              </p>
                              <div className="mt-3 flex justify-end">
                                <button className="flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:text-blue-800">
                                  <Eye className="w-3.5 h-3.5" /> Track on Map
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </SectionCard>

                <div className="mt-4 flex items-start gap-3 bg-ink-50 p-4 rounded-xl border border-ink-200">
                  <ShieldAlert className="w-5 h-5 text-ink-500 shrink-0" />
                  <p className="text-[11px] leading-relaxed text-ink-600">
                    Ranked by weighted spatio-temporal and behavioural correlation. This is a confidence-scored candidate list, <strong>not a definitive identification</strong>, and it is not on its own sufficient legal evidence of responsibility.
                  </p>
                </div>
              </div>

              {/* Score Breakdown (Sidebar) */}
              <div className="w-full">
                <SectionCard title="Score Breakdown" icon={<SlidersHorizontal className="w-4 h-4" />}>
                  {selectedCandidate ? (
                    <div>
                      <div className="mb-4">
                        <div className="text-xl font-black text-ink-900 mb-1">{selectedCandidate.name}</div>
                        <div className="text-xs font-mono text-ink-500">Total Score: {selectedCandidate.score.toFixed(3)}</div>
                      </div>

                      <div className="space-y-4">
                        {SCORE_FACTORS.map(({ key, label, hint }) => {
                          const val = selectedCandidate.breakdown[key];
                          const w = attribution.weights[key];
                          if (w === 0) return null;
                          const isAlert = key === "ais_gap" && val > 0;

                          return (
                            <div key={key}>
                              <div className="flex justify-between items-baseline mb-1">
                                <div className="flex items-center gap-1">
                                  <span className="text-[11px] font-bold uppercase tracking-wider text-ink-700">{label}</span>
                                  {isAlert && <AlertTriangle className="w-3 h-3 text-red-500" />}
                                </div>
                                <span className="text-[11px] font-mono font-bold text-blue-600">{(val * 100).toFixed(0)}%</span>
                              </div>
                              <div className="h-1.5 bg-ink-100 rounded-full overflow-hidden mb-1">
                                <div
                                  className={`h-full rounded-full ${isAlert ? "bg-red-500" : "bg-blue-500"}`}
                                  style={{ width: `${val * 100}%` }}
                                />
                              </div>
                              <div className="flex justify-between items-start">
                                <p className="text-[9px] text-ink-400 leading-tight w-2/3">{hint}</p>
                                <span className="text-[9px] font-mono text-ink-300">wt: {w.toFixed(2)}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <HelpCircle className="w-8 h-8 text-ink-300 mx-auto mb-2" />
                      <p className="text-sm text-ink-500">Select a candidate vessel from the list to view its scoring breakdown.</p>
                    </div>
                  )}
                </SectionCard>
              </div>

            </div>
          </div>
        )}
      </div>
    </ViewModeProvider>
  );
}
