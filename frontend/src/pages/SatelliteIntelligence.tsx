import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider } from "../lib/viewMode";
import { bearingLabel, deg, hours, km, ratio } from "../lib/format";
import {
  Satellite, Search, Layers, Zap, BrainCircuit, Maximize,
  Clock, EyeOff, AlertTriangle, ChevronDown, ChevronRight,
  MapPin, Activity, Crosshair,
  Wind, Ship, FlameKindling, Droplets, Compass, Route, ExternalLink, ShieldCheck
} from "lucide-react";
import type { DetectionMethod, SlickGeometry, AgeEstimate, DetectionEvidence, BackscatterStats, OilClassifyResponse, ReRouteOption } from "../api/types";

function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
  const map: Record<string, string> = {
    gray: "bg-ink-100 text-ink-600 border-ink-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    red: "bg-red-50 text-red-700 border-red-200",
    green: "bg-emerald-50 text-emerald-700 border-emerald-200",
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
      {open && (
        <div className="overflow-hidden transition-all duration-300">
          <div className="px-5 py-4">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value, hint }: { label: string; value: string | number | React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50 p-3 flex flex-col justify-between h-full">
      <div className="text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">{label}</div>
      <div className="text-lg font-black text-ink-900 font-mono">{value}</div>
      {hint && <div className="mt-1.5 text-[9px] text-ink-400 leading-tight">{hint}</div>}
    </div>
  );
}

// --- Shared Data Models for UI ---
interface UnifiedSlick {
  id: string;
  isLookalike: boolean;
  confidence: number;
  reason?: string;
  geometry: SlickGeometry;
  centroid: [number, number];
  age?: AgeEstimate | null;
  evidence?: DetectionEvidence | null;
  backscatter?: BackscatterStats | null;
  // Upload specific
  thickness_um?: number;
  contrast_db?: number;
}

function SlickDetailsPanel({ item, onMapProject }: { item: UnifiedSlick; onMapProject?: () => void }) {
  return (
    <div key={item.id} className="flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
      {/* Primary Banner */}
      <div className={`rounded-xl p-5 flex flex-col md:flex-row items-center justify-between gap-6 ${item.isLookalike ? "bg-ink-50 border border-ink-200" : "bg-amber-50 border border-amber-200"}`}>
        <div>
          <div className="flex items-center gap-2 mb-2">
            {item.isLookalike ? <EyeOff className="w-5 h-5 text-ink-500" /> : <AlertTriangle className="w-5 h-5 text-amber-600" />}
            <h3 className={`text-lg font-black tracking-tight ${item.isLookalike ? "text-ink-900" : "text-amber-900"}`}>
              {item.isLookalike ? "Ruled Out Look-alike" : "Confirmed Oil Slick"}
            </h3>
          </div>
          <p className={`text-sm ${item.isLookalike ? "text-ink-600" : "text-amber-700"}`}>
            {item.reason || "High confidence detection verified by morphological filtering."}
          </p>
        </div>
        <div className={`flex items-center gap-6 text-center p-4 rounded-lg border shadow-sm min-w-[200px] justify-center ${item.isLookalike ? "bg-white border-ink-200" : "bg-white border-amber-100"}`}>
          <div>
            <div className={`text-3xl font-black tabular-nums ${item.isLookalike ? "text-ink-500" : "text-amber-600"}`}>{item.geometry.area_km2.toFixed(1)}</div>
            <div className={`text-[10px] font-bold uppercase tracking-widest ${item.isLookalike ? "text-ink-400" : "text-amber-500"}`}>km² Area</div>
          </div>
          <div className={`w-px h-10 ${item.isLookalike ? "bg-ink-100" : "bg-amber-100"}`} />
          <div>
            <div className="text-3xl font-black text-ink-900 tabular-nums">{(item.confidence * 100).toFixed(0)}<span className="text-xl">%</span></div>
            <div className="text-[10px] font-bold uppercase tracking-widest text-ink-400">Confidence</div>
          </div>
        </div>
      </div>

      {onMapProject && !item.isLookalike && (
        <button
          onClick={onMapProject}
          className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3.5 rounded-lg shadow-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
        >
          <MapPin className="w-5 h-5" />
          Project into Maritime Map for Drift Analysis
        </button>
      )}

      {/* Geometry & Location */}
      <SectionCard title="Geometry & Location" icon={<Maximize className="w-4 h-4" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatBox label="Centroid" value={`${item.centroid[1].toFixed(2)}°N, ${Math.abs(item.centroid[0]).toFixed(2)}°W`} hint="Estimated center of mass" />
          <StatBox label="Perimeter" value={km(item.geometry.perimeter_km)} />
          <StatBox label="Dimensions" value={`${item.geometry.length_km.toFixed(1)} × ${item.geometry.width_km.toFixed(1)} km`} hint="Length by Width" />
          <StatBox label="Orientation" value={`${deg(item.geometry.orientation_deg)} ${bearingLabel(item.geometry.orientation_deg)}`} />
          <StatBox
            label="Elongation"
            value={ratio(item.geometry.elongation)}
            hint={`Major:minor axis ratio (${item.geometry.elongation.toFixed(1)}:1)`}
          />
          <StatBox
            label="Compactness"
            value={item.geometry.compactness.toFixed(3)}
            hint="Near 1 is circular, lower is trail-like."
          />
          {item.thickness_um !== undefined && (
            <StatBox label="Thickness" value={`${item.thickness_um.toFixed(1)} µm`} hint="Estimated from backscatter" />
          )}
          {item.contrast_db !== undefined && (
            <StatBox label="Contrast" value={`${item.contrast_db.toFixed(1)} dB`} hint="Against background sea" />
          )}
        </div>
      </SectionCard>

      {/* Weathering & Age Estimate */}
      {item.age && (
        <SectionCard title="Age & Weathering Estimate" icon={<Clock className="w-4 h-4" />}>
          <div className="flex flex-col md:flex-row gap-6">
            <div className="shrink-0 text-center md:text-left bg-blue-50 border border-blue-100 p-4 rounded-lg">
              <div className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-1">Release Window</div>
              <div className="text-2xl font-black text-blue-700 tabular-nums">
                {hours(item.age.min_hours)} – {hours(item.age.max_hours)}
              </div>
              <div className="mt-2 flex justify-center md:justify-start">
                <Badge color={item.age.confidence === "high" ? "green" : item.age.confidence === "medium" ? "blue" : "amber"}>
                  {item.age.confidence.toUpperCase()} CONFIDENCE
                </Badge>
              </div>
            </div>
            <div className="flex-1 grid grid-cols-2 gap-4">
              {item.age.diffusivity_m2s != null && (
                <StatBox label="Diffusivity" value={`${item.age.diffusivity_m2s.toFixed(2)} m²/s`} />
              )}
              {item.age.damping_db != null && (
                <StatBox label="Radar Damping" value={`${item.age.damping_db.toFixed(1)} dB`} />
              )}
              <div className="col-span-2 text-sm text-ink-600 bg-ink-50 p-3 rounded-lg border border-ink-100">
                <strong>Methodology:</strong> {item.age.method_note}
              </div>
            </div>
          </div>
        </SectionCard>
      )}

      {/* Evidence Subscores */}
      {item.evidence && (
        <SectionCard title="Detection Evidence" icon={<Layers className="w-4 h-4" />} defaultOpen={false}>
          <div className="grid gap-4">
            {[
              { label: "Backscatter damping", val: item.evidence.contrast, w: item.evidence.weight_contrast, hint: "Contrast vs local background." },
              { label: "Speckle suppression", val: item.evidence.variance, w: item.evidence.weight_variance, hint: "Inside/ambient speckle variance ratio." },
              { label: "Elongated shape", val: item.evidence.shape, w: item.evidence.weight_shape, hint: "Low compactness argues for a trail over a blob." },
              { label: "Edge sharpness", val: item.evidence.edge, w: item.evidence.weight_edge, hint: "A discharge boundary is a sharp discontinuity." }
            ].map(e => (
              <div key={e.label}>
                <div className="flex justify-between items-baseline mb-1">
                  <span className="text-sm font-semibold text-ink-800">{e.label}</span>
                  <span className="text-xs font-mono font-bold text-blue-600">{(e.val * 100).toFixed(0)}%</span>
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
    </div>
  );
}

// ── OilImpactPanel Component ────────────────────────────────────
function OilImpactPanel({ data, loading }: { data: OilClassifyResponse | null; loading: boolean }) {
  const { setActiveReRouteOption } = useSpillState();
  const navigate = useNavigate();
  const [selectedOptId, setSelectedOptId] = useState<string>("port_fastest");

  useEffect(() => {
    if (data?.reroute_plan?.options?.length) {
      const rec = data.reroute_plan.recommended_option_id;
      setSelectedOptId(rec);
      const chosen = data.reroute_plan.options.find(o => o.id === rec) || data.reroute_plan.options[0];
      setActiveReRouteOption(chosen);
    }
  }, [data]);

  if (loading) {
    return (
      <div className="rounded-xl border border-ink-200 bg-ink-50 p-5 flex items-center gap-4">
        <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
        <div className="text-sm font-semibold text-ink-600">Analysing oil film thickness & computing optimal navigation route…</div>
      </div>
    );
  }

  if (!data) return null;

  const { impact, thickness_um, reroute_plan } = data;
  const isReroute = impact.re_route_needed;
  const thicknessDisplay = thickness_um != null ? `${thickness_um.toFixed(1)} µm` : "N/A";

  type EvapKey = "fast" | "partial" | "partial-heavy" | "minimal";
  const bandKey: EvapKey =
    thickness_um == null         ? "minimal"
    : thickness_um <= 10         ? "fast"
    : thickness_um <= 35         ? "partial"
    : thickness_um <= 65         ? "partial-heavy"
    :                              "minimal";

  const bandStyle: Record<EvapKey, { bg: string; border: string; icon: string; label: string }> = {
    "fast":          { bg: "bg-emerald-50", border: "border-emerald-200", icon: "text-emerald-600", label: "✅ Evaporates Rapidly" },
    "partial":       { bg: "bg-amber-50",   border: "border-amber-200",   icon: "text-amber-500",  label: "🟡 Partially Evaporates" },
    "partial-heavy": { bg: "bg-orange-50",  border: "border-orange-200",  icon: "text-orange-500", label: "🟠 Partial — Residue Remains" },
    "minimal":       { bg: "bg-red-50",     border: "border-red-200",     icon: "text-red-500",    label: "❌ Does Not Evaporate" },
  };
  const band = bandStyle[bandKey];

  const activeOption = reroute_plan?.options.find(o => o.id === selectedOptId) || reroute_plan?.options[0];

  const handleSelectOption = (opt: ReRouteOption) => {
    setSelectedOptId(opt.id);
    setActiveReRouteOption(opt);
  };

  return (
    <div className="flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-3 duration-500">
      {/* Physical Assessment card */}
      <div className="rounded-xl border border-ink-200 bg-white shadow-sm overflow-hidden">
        {/* Card header */}
        <div className="flex items-center gap-3 px-5 py-3.5 bg-ink-50 border-b border-ink-200">
          <Droplets className="w-4 h-4 text-blue-600 shrink-0" />
          <span className="flex-1 text-sm font-bold text-ink-800 tracking-tight">Oil Film Physical Assessment</span>
          <span className="font-mono text-xs font-bold bg-blue-100 text-blue-700 px-2.5 py-1 rounded-md">
            {thicknessDisplay} film
          </span>
        </div>

        {/* Three stat boxes */}
        <div className="px-5 py-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
          {/* Thickness */}
          <div className="rounded-lg border border-ink-200 bg-ink-50 p-3 flex flex-col gap-1">
            <div className="flex items-center gap-1.5">
              <Droplets className="w-3.5 h-3.5 text-blue-500" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-blue-600">Thickness</span>
            </div>
            <div className="text-xl font-black text-ink-900 font-mono">{thicknessDisplay}</div>
            <p className="text-[10px] leading-snug text-ink-500">
              SAR-derived oil film depth measured in micrometres (µm).
            </p>
          </div>

          {/* Evaporation */}
          <div className={`rounded-lg border p-3 flex flex-col gap-1 ${band.bg} ${band.border}`}>
            <div className="flex items-center gap-1.5">
              <Wind className={`w-3.5 h-3.5 ${band.icon}`} />
              <span className={`text-[10px] font-bold uppercase tracking-wider ${band.icon}`}>Evaporation</span>
            </div>
            <div className={`text-sm font-black ${band.icon}`}>{band.label}</div>
            <p className={`text-[10px] leading-snug ${band.icon} opacity-80`}>
              {impact.evaporation_potential}
            </p>
          </div>

          {/* Navigational hazard */}
          <div className={`rounded-lg border p-3 flex flex-col gap-1 ${
            isReroute ? "bg-red-50 border-red-200" : "bg-emerald-50 border-emerald-200"
          }`}>
            <div className="flex items-center gap-1.5">
              <FlameKindling className={`w-3.5 h-3.5 ${isReroute ? "text-red-500" : "text-emerald-600"}`} />
              <span className={`text-[10px] font-bold uppercase tracking-wider ${
                isReroute ? "text-red-600" : "text-emerald-600"
              }`}>Nav. Hazard</span>
            </div>
            <div className={`text-sm font-black ${isReroute ? "text-red-800" : "text-emerald-800"}`}>
              {isReroute ? "Fouling Risk" : "Minimal Risk"}
            </div>
            <p className={`text-[10px] leading-snug ${
              isReroute ? "text-red-700" : "text-emerald-700"
            }`}>{impact.navigational_hazard}</p>
          </div>
        </div>
      </div>

      {/* Routing verdict strip */}
      <div className={`rounded-xl border flex items-center gap-4 px-5 py-4 ${
        isReroute ? "bg-red-50 border-red-200" : "bg-emerald-50 border-emerald-200"
      }`}>
        <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${
          isReroute ? "bg-red-100" : "bg-emerald-100"
        }`}>
          <Ship className={`w-5 h-5 ${isReroute ? "text-red-600" : "text-emerald-600"}`} />
        </div>
        <div className="flex-1">
          <div className={`text-sm font-black ${
            isReroute ? "text-red-900" : "text-emerald-900"
          }`}>
            {isReroute ? "⚠ Re-routing Recommended" : "✓ No Re-routing Required"}
          </div>
          <div className={`text-xs mt-0.5 ${
            isReroute ? "text-red-700" : "text-emerald-700"
          }`}>
            {isReroute
              ? "Vessel should deviate from current heading — persistent oil at this thickness poses a sea-chest intake fouling hazard."
              : "Oil film will dissipate naturally at this thickness — vessel may proceed on current course."}
          </div>
        </div>
      </div>

      {/* ── Enhanced Optimal Alternate Re-Routing Module ────────── */}
      {isReroute && reroute_plan && (
        <div className="rounded-xl border border-emerald-300 bg-white shadow-sm overflow-hidden">
          {/* Header */}
          <div className="px-5 py-3.5 bg-emerald-50/80 border-b border-emerald-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Route className="w-4 h-4 text-emerald-700" />
              <span className="text-sm font-bold text-emerald-950 tracking-tight">
                Optimal Alternate Navigation Re-Route
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded">
                Speed: {reroute_plan.vessel_speed_kts.toFixed(0)} kts
              </span>
              <button
                onClick={() => navigate("/map")}
                className="text-xs font-bold text-emerald-700 hover:text-emerald-900 flex items-center gap-1 bg-white hover:bg-emerald-100/50 px-2.5 py-1 rounded border border-emerald-300 transition-colors shadow-2xs"
              >
                Open Maritime Map <ExternalLink className="w-3 h-3" />
              </button>
            </div>
          </div>

          <div className="p-5 flex flex-col gap-4">
            {/* Strategy selector tabs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {reroute_plan.options.map((opt) => {
                const isSel = opt.id === selectedOptId;
                return (
                  <button
                    key={opt.id}
                    onClick={() => handleSelectOption(opt)}
                    className={`p-3.5 rounded-lg border text-left transition-all relative ${
                      isSel
                        ? "bg-emerald-50/90 border-emerald-500 ring-2 ring-emerald-500/20 shadow-xs"
                        : "bg-white border-ink-200 hover:border-emerald-300 hover:bg-ink-50/50"
                    }`}
                  >
                    <div className="flex justify-between items-start mb-1.5 gap-2">
                      <span className="font-bold text-xs text-ink-900 flex items-center gap-1.5">
                        {opt.is_recommended && <Zap className="w-3.5 h-3.5 text-emerald-600 fill-emerald-600 shrink-0" />}
                        {opt.name}
                      </span>
                      {opt.is_recommended ? (
                        <span className="text-[9px] font-black uppercase tracking-wider bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded shrink-0">
                          Recommended · Safe
                        </span>
                      ) : (
                        <span className="text-[9px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded shrink-0">
                          Down-Drift Wide
                        </span>
                      )}
                    </div>
                    <div className="flex items-baseline gap-3 text-xs font-mono mb-1.5">
                      <span className="font-bold text-emerald-700">+{opt.time_delay_min.toFixed(0)} min delay</span>
                      <span className="text-ink-400">+{opt.extra_distance_nm.toFixed(1)} NM ({opt.extra_distance_pct.toFixed(1)}%)</span>
                    </div>
                    {opt.plume_clearance_desc && (
                      <p className="text-[10px] text-ink-500 leading-tight border-t border-ink-100/70 pt-1.5 mt-1">
                        {opt.plume_clearance_desc}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Guidance summary highlight */}
            <div className="bg-emerald-50/60 border border-emerald-200 rounded-lg p-3 flex items-start gap-2.5">
              <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div className="text-xs text-emerald-900 leading-relaxed font-medium">
                {reroute_plan.guidance_summary}
              </div>
            </div>

            {/* Selected Route Telemetry Grid */}
            {activeOption && (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <StatBox
                    label="Time Delay"
                    value={`+${activeOption.time_delay_min.toFixed(1)} min`}
                    hint={`Total transit: ${activeOption.transit_time_min.toFixed(0)} min`}
                  />
                  <StatBox
                    label="Detour Distance"
                    value={`${activeOption.distance_nm.toFixed(1)} NM`}
                    hint={`+${activeOption.extra_distance_nm.toFixed(1)} NM (+${activeOption.extra_distance_pct.toFixed(1)}%)`}
                  />
                  <StatBox
                    label="Safety Buffer"
                    value={`${activeOption.min_clearance_nm.toFixed(1)} NM`}
                    hint="Clear of slick fouling boundary"
                  />
                  <StatBox
                    label="Fuel Penalty"
                    value={`+${activeOption.fuel_extra_mt.toFixed(2)} MT`}
                    hint="Estimated HFO consumption"
                  />
                </div>

                {/* Waypoint Corridor Table */}
                <div className="rounded-lg border border-ink-200 overflow-hidden bg-ink-50/50">
                  <div className="px-4 py-2.5 bg-ink-100/70 border-b border-ink-200 flex justify-between items-center">
                    <span className="text-xs font-bold text-ink-800 uppercase tracking-wider flex items-center gap-1.5">
                      <Compass className="w-3.5 h-3.5 text-blue-600" />
                      Tactical Waypoint Plan & Steering Orders
                    </span>
                    <span className="text-[10px] text-ink-500 font-mono">
                      {activeOption.waypoints.length} WAYPOINTS
                    </span>
                  </div>
                  <div className="divide-y divide-ink-100">
                    {activeOption.waypoints.map((wpt, idx) => (
                      <div key={wpt.name} className="p-3.5 bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                        <div className="flex items-start gap-3">
                          <div className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-800 font-black flex items-center justify-center text-[10px] shrink-0">
                            {idx + 1}
                          </div>
                          <div>
                            <div className="font-bold text-ink-900">{wpt.name}</div>
                            <div className="text-[11px] text-ink-500 font-mono mt-0.5">
                              {wpt.lat.toFixed(4)}°N, {Math.abs(wpt.lon).toFixed(4)}°W
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-4 sm:text-right">
                          <div>
                            <div className="text-[10px] uppercase font-bold text-ink-400 tracking-wider">Course to Steer</div>
                            <div className="font-mono font-black text-ink-900 text-sm flex items-center gap-1">
                              <Compass className="w-3 h-3 text-emerald-600" />
                              {wpt.course_to_steer_deg.toFixed(0)}°
                            </div>
                          </div>
                          {wpt.leg_distance_nm > 0 && (
                            <div>
                              <div className="text-[10px] uppercase font-bold text-ink-400 tracking-wider">Leg Distance</div>
                              <div className="font-mono font-bold text-ink-700">{wpt.leg_distance_nm.toFixed(1)} NM</div>
                            </div>
                          )}
                        </div>

                        <div className="sm:max-w-[280px] text-[11px] text-ink-600 bg-ink-50 p-2 rounded border border-ink-100">
                          {wpt.instructions}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SidebarList({ items, selectedId, onSelect }: { items: UnifiedSlick[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const slicks = items.filter(i => !i.isLookalike);
  const lookalikes = items.filter(i => i.isLookalike);

  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-xs font-bold uppercase tracking-widest text-ink-500 mb-3 px-1 flex items-center gap-2">
          <Activity className="w-3.5 h-3.5" /> Confirmed Slicks ({slicks.length})
        </h4>
        <div className="space-y-2">
          {slicks.map((s, i) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${selectedId === s.id
                  ? "bg-amber-50 border-amber-300 shadow-sm ring-1 ring-amber-300"
                  : "bg-white border-ink-200 hover:border-amber-200 hover:bg-amber-50/30"
                }`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold text-ink-900 text-sm">Slick #{i + 1}</span>
                <Badge color="amber">{(s.confidence * 100).toFixed(0)}% CONF</Badge>
              </div>
              <div className="text-xs text-ink-500 font-mono">{s.geometry.area_km2.toFixed(2)} km²</div>
            </button>
          ))}
          {slicks.length === 0 && <div className="text-sm text-ink-400 italic px-2">No slicks confirmed.</div>}
        </div>
      </div>

      <div>
        <h4 className="text-xs font-bold uppercase tracking-widest text-ink-500 mb-3 px-1 flex items-center gap-2">
          <EyeOff className="w-3.5 h-3.5" /> Look-alikes ({lookalikes.length})
        </h4>
        <div className="space-y-2">
          {lookalikes.map((s, i) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${selectedId === s.id
                  ? "bg-ink-100 border-ink-300 shadow-sm ring-1 ring-ink-300"
                  : "bg-white border-ink-200 hover:border-ink-300 hover:bg-ink-50"
                }`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold text-ink-900 text-sm">Look-alike #{i + 1}</span>
                <span className="text-xs text-ink-400 font-mono">{(s.confidence * 100).toFixed(0)}% CONF</span>
              </div>
              <div className="text-[10px] text-ink-500 line-clamp-1 mt-1">{s.reason}</div>
            </button>
          ))}
          {lookalikes.length === 0 && <div className="text-sm text-ink-400 italic px-2">No look-alikes found.</div>}
        </div>
      </div>
    </div>
  );
}

// ── main component ─────────────────────────────────────────────
export default function SatelliteIntelligence() {
  const { caseMeta, detection, detecting, method, runDetect, viewMode, onFocusLookalike, setActiveSlickId, mockWindDir } = useSpillState();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [caseOilClassify, setCaseOilClassify] = useState<OilClassifyResponse | null>(null);
  const [caseOilClassifying, setCaseOilClassifying] = useState(false);

  const unetAvailable = true;

  const handleRun = (m: DetectionMethod) => {
    runDetect(m);
  };

  const classifyCaseSlick = (slickId: string) => {
    if (!detection?.slicks) return;
    const slick = detection.slicks.find(s => s.id === slickId);
    if (!slick) return;

    const rawContrast = slick.contrast_db ?? slick.backscatter?.contrast_db ?? 6.0;
    const contrast_dB = -Math.abs(rawContrast);
    const elongation = slick.geometry?.elongation ?? 2.0;
    const thickness_proxy = Math.max(0.01, Math.min(1.0, 1.0 / (elongation * 0.5 + 0.5)));
    const compactness = slick.geometry?.compactness ?? 0.5;
    const area_growth_rate = Math.max(0.01, Math.min(1.0, 1.0 - compactness));
    const variance_ratio = slick.backscatter?.variance_ratio ?? 0.7;
    const weathering_indicator = Math.max(0.01, Math.min(1.0, 1.0 - variance_ratio));
    const VV_VH_ratio = Math.max(1.0, Math.abs(contrast_dB) * 1.1);

    // Exact thickness from the slick (e.g. from upload or fixture)
    const thickness_um = slick.thickness_um != null
      ? slick.thickness_um
      : Math.max(2, Math.min(120, Math.abs(rawContrast) * 5.0));

    const pts = slick.polygon?.type === "Polygon" ? (slick.polygon.coordinates[0] as [number, number][]) : [];
    const center_lon = pts.length > 0 ? pts.reduce((sum, p) => sum + p[0], 0) / pts.length : (caseMeta?.center[0] ?? -90.02);
    const center_lat = pts.length > 0 ? pts.reduce((sum, p) => sum + p[1], 0) / pts.length : (caseMeta?.center[1] ?? 28.47);
    const length_km = slick.geometry?.length_km ?? 36.0;
    const width_km = slick.geometry?.width_km ?? 8.4;
    const orientation_deg = slick.geometry?.orientation_deg ?? 48.0;

    setCaseOilClassify(null);
    setCaseOilClassifying(true);
    fetch("/api/classify-oil", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contrast_dB, thickness_proxy, area_growth_rate,
        weathering_indicator, VV_VH_ratio,
        thickness_um,
        center_lon, center_lat, length_km, width_km, orientation_deg,
        mock_wind_dir_deg: mockWindDir,
        drift_heading_deg: 340.0,
      }),
    })
      .then(res => res.ok ? res.json() : null)
      .then(json => { if (json) setCaseOilClassify(json as OilClassifyResponse); })
      .catch(() => null)
      .finally(() => setCaseOilClassifying(false));
  };

  useEffect(() => {
    // Keep the current selection if it still exists in the updated detection
    const selectionStillValid = selectedId && (
      detection?.slicks?.some(s => s.id === selectedId) ||
      detection?.rejected_lookalikes?.some(r => r.id === selectedId)
    );

    if (!selectionStillValid) {
      if (detection?.slicks?.length) {
        const id = detection.slicks[0].id;
        setSelectedId(id);
        onFocusLookalike(id);
        setActiveSlickId(id);
        classifyCaseSlick(id);
      } else if (detection?.rejected_lookalikes?.length) {
        const id = detection.rejected_lookalikes[0].id;
        setSelectedId(id);
        onFocusLookalike(id);
        setCaseOilClassify(null);
      } else {
        setSelectedId(null);
        setCaseOilClassify(null);
      }
    }
  }, [detection]);

  const handleSelect = (id: string) => {
    setSelectedId(id);
    onFocusLookalike(id);
    if (detection?.slicks?.some(s => s.id === id)) {
      setActiveSlickId(id);
      classifyCaseSlick(id);
    } else {
      setCaseOilClassify(null);
    }
  };

  // Convert `case` mode data into the unified model
  const unifiedItems: UnifiedSlick[] = detection ? [
    ...detection.slicks.map((s) => {
      const pts = s.polygon.type === "Polygon" ? s.polygon.coordinates[0] as [number, number][] : [];
      const cx = pts.length > 0 ? pts.reduce((sum, p) => sum + p[0], 0) / pts.length : 0;
      const cy = pts.length > 0 ? pts.reduce((sum, p) => sum + p[1], 0) / pts.length : 0;
      return {
        id: s.id, isLookalike: false, confidence: s.confidence, geometry: s.geometry,
        centroid: [cx, cy] as [number, number], age: s.age, evidence: s.evidence,
        backscatter: s.backscatter,
        thickness_um: s.thickness_um ?? undefined,
        contrast_db: s.contrast_db ?? s.backscatter?.contrast_db,
      };
    }),
    ...detection.rejected_lookalikes.map((r) => {
      const pts = r.polygon.type === "Polygon" ? r.polygon.coordinates[0] as [number, number][] : [];
      const cx = pts.length > 0 ? pts.reduce((sum, p) => sum + p[0], 0) / pts.length : 0;
      const cy = pts.length > 0 ? pts.reduce((sum, p) => sum + p[1], 0) / pts.length : 0;
      return {
        id: r.id, isLookalike: true, confidence: r.confidence, reason: r.reason,
        geometry: r.geometry || { area_km2: 0, perimeter_km: 0, length_km: 0, width_km: 0, aspect_ratio: 0, elongation: 0, orientation_deg: 0, compactness: 0, solidity: 0 },
        centroid: [cx, cy] as [number, number], evidence: r.evidence
      };
    })
  ] : [];

  const activeItem = unifiedItems.find(i => i.id === selectedId);

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">
        <header className="page-header flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Satellite className="w-5 h-5 text-blue-600" />
              <h2 className="!mb-0">Satellite Intelligence</h2>
            </div>
            <p>Analyze Synthetic Aperture Radar (SAR) imagery for anomalies and potential oil slicks.</p>
          </div>
        </header>

        <div className="mt-6">

            <div className="flex items-center justify-between mb-6 bg-ink-50 p-2 rounded-lg border border-ink-200">
              <span className="text-xs font-bold uppercase tracking-wider text-ink-500 px-3 flex items-center gap-2"><Crosshair className="w-4 h-4" /> Live Map Analysis</span>
              <div className="flex gap-2">
                <button
                  onClick={() => handleRun("classical")}
                  disabled={detecting && method !== "classical"}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all ${method === "classical"
                      ? "bg-white shadow-sm border border-ink-200 text-ink-900"
                      : "text-ink-600 hover:text-ink-900 hover:bg-ink-100/50"
                    }`}
                >
                  <Zap className="w-4 h-4" /> Classical
                  {detecting && method === "classical" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
                </button>
                <button
                  onClick={() => handleRun("unet")}
                  disabled={!unetAvailable || (detecting && method !== "unet")}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all ${method === "unet"
                      ? "bg-white shadow-sm border border-ink-200 text-blue-600"
                      : "text-ink-600 hover:text-blue-600 hover:bg-ink-100/50"
                    }`}
                >
                  <BrainCircuit className="w-4 h-4" /> U-Net
                  {detecting && method === "unet" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
                </button>
              </div>
            </div>

            {!detection && !detecting && (
              <div className="flex flex-col items-center justify-center py-16 px-6 text-center border-2 border-dashed border-ink-200 rounded-2xl bg-ink-50/50">
                <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center mb-4">
                  <Search className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-bold text-ink-900 mb-2">No Detection Results</h3>
                <p className="text-ink-500 max-w-md text-sm">
                  Select an algorithm from the top right to analyze the current SAR scene and extract potential slicks.
                </p>
              </div>
            )}

            {detecting && !detection && (
              <div className="space-y-4">
                <div className="h-32 skeleton rounded-xl" />
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="h-24 skeleton rounded-lg" />
                  <div className="h-24 skeleton rounded-lg" />
                  <div className="h-24 skeleton rounded-lg" />
                  <div className="h-24 skeleton rounded-lg" />
                </div>
              </div>
            )}

            {detection && unifiedItems.length > 0 && (
              <div className="flex flex-col gap-6">
                {!activeItem ? (
                  <div className="animate-in fade-in slide-in-from-left-4 duration-500">
                    <SidebarList items={unifiedItems} selectedId={selectedId} onSelect={handleSelect} />
                  </div>
                ) : (
                  <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-right-4 duration-500">
                    <button onClick={() => { setSelectedId(null); setCaseOilClassify(null); }} className="self-start flex items-center gap-2 text-sm font-bold text-ink-500 hover:text-ink-800 transition-colors bg-ink-50 hover:bg-ink-100 px-4 py-2 rounded-lg border border-ink-200">
                      <ChevronRight className="w-4 h-4 rotate-180" /> Back to Analysis List
                    </button>
                    {/* Oil Impact Panel — shown for confirmed slicks */}
                    {!activeItem.isLookalike && (caseOilClassify || caseOilClassifying) && (
                      <div>
                        <h4 className="text-xs font-bold uppercase tracking-widest text-ink-500 mb-3 flex items-center gap-2">
                          <Droplets className="w-3.5 h-3.5" /> Oil Physical Assessment & Routing
                        </h4>
                        <OilImpactPanel data={caseOilClassify} loading={caseOilClassifying} />
                      </div>
                    )}
                    <SlickDetailsPanel item={activeItem} />
                  </div>
                )}
              </div>
            )}
          </div>
      </div>
    </ViewModeProvider>
  );
}
