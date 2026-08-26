import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider } from "../lib/viewMode";
import { km2, pct, hours, km } from "../lib/format";
import { 
  Activity, AlertTriangle, Anchor, Map, 
  Satellite, Search, Waves, Wind 
} from "lucide-react";

export default function Overview() {
  const { caseMeta, detection, hindcast, forecast, attribution, viewMode } = useSpillState();

  const slick = detection?.slicks[0];
  const origin = hindcast?.origin_estimate;
  const impact = forecast?.impact_flags;

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell pb-12">
        {/* Global Status Banner */}
        <div className="mb-6 bg-gradient-to-r from-blue-900 to-ink-900 rounded-2xl p-8 text-white shadow-lg relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 opacity-10">
             <Map className="w-48 h-48" />
          </div>
          <div className="relative z-10">
            <div className="flex items-center gap-3 mb-4">
               <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
               </span>
               <span className="text-emerald-400 font-bold tracking-widest text-xs uppercase">System Operational</span>
            </div>
            <h1 className="text-3xl font-black tracking-tight mb-2">Ocean Sentinel Command</h1>
            <p className="text-blue-200 max-w-xl text-sm leading-relaxed">
              Global monitoring of maritime anomalies, dark vessel activity, and environmental hazards. 
              Currently tracking an active incident in the Gulf of Mexico.
            </p>
          </div>
        </div>

        {/* Top-Level Metrics */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="bg-white p-5 rounded-xl border border-ink-200 shadow-sm flex items-center gap-4">
             <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
               <Activity className="w-6 h-6" />
             </div>
             <div>
                <div className="text-2xl font-black text-ink-900">1</div>
                <div className="text-xs font-bold text-ink-500 uppercase tracking-widest mt-0.5">Active Incident</div>
             </div>
          </div>
          <div className="bg-white p-5 rounded-xl border border-ink-200 shadow-sm flex items-center gap-4">
             <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
               <AlertTriangle className="w-6 h-6" />
             </div>
             <div>
                <div className="text-2xl font-black text-ink-900">{slick ? km2(slick.geometry.area_km2) : "--"}</div>
                <div className="text-xs font-bold text-ink-500 uppercase tracking-widest mt-0.5">Slick Area</div>
             </div>
          </div>
          <div className="bg-white p-5 rounded-xl border border-ink-200 shadow-sm flex items-center gap-4">
             <div className="w-12 h-12 rounded-full bg-red-50 text-red-600 flex items-center justify-center shrink-0">
               <Search className="w-6 h-6" />
             </div>
             <div>
                <div className="text-2xl font-black text-ink-900">{attribution ? attribution.after_filter : "--"}</div>
                <div className="text-xs font-bold text-ink-500 uppercase tracking-widest mt-0.5">Suspect Vessels</div>
             </div>
          </div>
          <div className="bg-white p-5 rounded-xl border border-ink-200 shadow-sm flex items-center gap-4">
             <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
               <Waves className="w-6 h-6" />
             </div>
             <div>
                <div className="text-2xl font-black text-ink-900">{impact && impact.length > 0 ? "YES" : "NO"}</div>
                <div className="text-xs font-bold text-ink-500 uppercase tracking-widest mt-0.5">Coast Threat</div>
             </div>
          </div>
        </div>

        {/* Active Incident Details */}
        <h2 className="text-lg font-bold text-ink-900 mb-4 px-1">Active Incident Overview</h2>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
           
           {/* Scene Context */}
           <div className="bg-white rounded-xl border border-ink-200 shadow-sm overflow-hidden flex flex-col">
              <div className="bg-ink-50 px-5 py-3 border-b border-ink-200 flex items-center gap-2">
                 <Satellite className="w-4 h-4 text-ink-500" />
                 <span className="font-bold text-sm text-ink-800">Observation Data</span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-center">
                 {caseMeta ? (
                   <div className="space-y-4">
                      <div>
                        <div className="text-xs text-ink-500 font-bold uppercase tracking-widest mb-1">Region</div>
                        <div className="text-lg font-bold text-ink-900">{caseMeta.name}</div>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                         <div>
                           <div className="text-[10px] text-ink-400 font-bold uppercase tracking-widest mb-0.5">Scene ID</div>
                           <div className="text-xs font-mono font-semibold text-blue-600 truncate">{caseMeta.scene_id}</div>
                         </div>
                         <div>
                           <div className="text-[10px] text-ink-400 font-bold uppercase tracking-widest mb-0.5">Acquired At</div>
                           <div className="text-xs font-mono font-semibold text-ink-700">{new Date(caseMeta.acquired_at).toLocaleString()}</div>
                         </div>
                      </div>
                   </div>
                 ) : (
                   <div className="text-center text-ink-400 text-sm italic">Case metadata loading...</div>
                 )}
              </div>
           </div>

           {/* Detection Status */}
           <div className="bg-white rounded-xl border border-ink-200 shadow-sm overflow-hidden flex flex-col">
              <div className="bg-ink-50 px-5 py-3 border-b border-ink-200 flex items-center gap-2">
                 <AlertTriangle className="w-4 h-4 text-amber-600" />
                 <span className="font-bold text-sm text-ink-800">Detection Status</span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-center">
                 {slick ? (
                   <div className="flex gap-6 items-center">
                     <div className="text-center px-6 py-4 bg-amber-50 rounded-lg border border-amber-200">
                        <div className="text-3xl font-black text-amber-600 tabular-nums">{km2(slick.geometry.area_km2)}</div>
                        <div className="text-[10px] font-bold text-amber-500 uppercase tracking-widest mt-1">Confirmed Area</div>
                     </div>
                     <div className="flex-1 space-y-3">
                        <div className="flex justify-between items-end border-b border-ink-100 pb-2">
                           <span className="text-xs font-bold uppercase text-ink-500">Confidence</span>
                           <span className="font-mono text-sm font-bold text-ink-900">{pct(slick.confidence)}</span>
                        </div>
                        <div className="flex justify-between items-end border-b border-ink-100 pb-2">
                           <span className="text-xs font-bold uppercase text-ink-500">Method</span>
                           <span className="text-sm font-bold text-ink-900 capitalize">{slick.method}</span>
                        </div>
                        <div className="flex justify-between items-end pb-1">
                           <span className="text-xs font-bold uppercase text-ink-500">Lookalikes Rejected</span>
                           <span className="font-mono text-sm font-bold text-ink-900">{detection.rejected_lookalikes.length}</span>
                        </div>
                     </div>
                   </div>
                 ) : (
                   <div className="text-center text-ink-400 text-sm">
                     <div className="mb-2">No detection run yet.</div>
                     <button className="text-blue-600 font-bold hover:underline">Run Detection in Maritime Map</button>
                   </div>
                 )}
              </div>
           </div>

        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
           
           {/* Drift Summary */}
           <div className="bg-white rounded-xl border border-ink-200 shadow-sm overflow-hidden flex flex-col">
              <div className="bg-ink-50 px-5 py-3 border-b border-ink-200 flex items-center gap-2">
                 <Wind className="w-4 h-4 text-blue-600" />
                 <span className="font-bold text-sm text-ink-800">Environmental Analysis</span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-center">
                 {origin || forecast ? (
                   <div className="space-y-4">
                     {origin && (
                        <div className="bg-blue-50 border border-blue-100 p-4 rounded-lg">
                           <div className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-2">Hindcast Origin</div>
                           <div className="flex justify-between items-center mb-1">
                              <span className="text-sm text-ink-700">Estimated Release</span>
                              <span className="font-mono font-bold text-ink-900">{new Date(origin.time_utc).toLocaleTimeString()}</span>
                           </div>
                           <div className="flex justify-between items-center">
                              <span className="text-sm text-ink-700">Uncertainty Radius</span>
                              <span className="font-mono font-bold text-ink-900">{km(origin.uncertainty_radius_km)}</span>
                           </div>
                        </div>
                     )}
                     {forecast && (
                        <div className={`p-4 rounded-lg border ${impact && impact.length > 0 ? 'bg-red-50 border-red-200' : 'bg-emerald-50 border-emerald-200'}`}>
                           <div className={`text-[10px] font-bold uppercase tracking-widest mb-2 ${impact && impact.length > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                              12h Forecast Impact
                           </div>
                           {impact && impact.length > 0 ? (
                              <div className="text-sm font-bold text-red-800 flex items-center gap-2">
                                 <AlertTriangle className="w-4 h-4 shrink-0" />
                                 Coastline impact expected in {hours(impact[0].eta_hours)}
                              </div>
                           ) : (
                              <div className="text-sm font-bold text-emerald-700 flex items-center gap-2">
                                 <Waves className="w-4 h-4 shrink-0" />
                                 No coastline impact predicted
                              </div>
                           )}
                        </div>
                     )}
                   </div>
                 ) : (
                   <div className="text-center text-ink-400 text-sm">
                     <div className="mb-2">Environmental models not run.</div>
                   </div>
                 )}
              </div>
           </div>

           {/* Attribution Summary */}
           <div className="bg-white rounded-xl border border-ink-200 shadow-sm overflow-hidden flex flex-col">
              <div className="bg-ink-50 px-5 py-3 border-b border-ink-200 flex items-center gap-2">
                 <Anchor className="w-4 h-4 text-purple-600" />
                 <span className="font-bold text-sm text-ink-800">Vessel Attribution</span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-center">
                 {attribution ? (
                   <div className="space-y-3">
                     <div className="flex justify-between items-center mb-2 px-1">
                        <span className="text-xs font-bold uppercase tracking-widest text-ink-500">Top Candidates</span>
                        <span className="text-xs text-ink-400">Out of {attribution.total_vessels_in_region} vessels</span>
                     </div>
                     {attribution.candidates.slice(0, 3).map((c, i) => (
                        <div key={c.mmsi} className="flex justify-between items-center p-3 border border-ink-100 rounded-lg hover:bg-ink-50 transition-colors">
                           <div className="flex items-center gap-3">
                              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black shrink-0 ${c.flags.includes("DARK_VESSEL") ? "bg-red-100 text-red-700" : "bg-ink-100 text-ink-600"}`}>
                                 {i + 1}
                              </span>
                              <div>
                                <div className="text-sm font-bold text-ink-900 leading-tight">{c.name}</div>
                                <div className="text-[10px] text-ink-500 font-mono mt-0.5">{c.mmsi}</div>
                              </div>
                           </div>
                           <div className="text-right">
                              <div className="font-mono font-black text-ink-900">{c.score.toFixed(3)}</div>
                              <div className="text-[9px] uppercase tracking-widest text-ink-400 mt-0.5">Match</div>
                           </div>
                        </div>
                     ))}
                     {attribution.candidates.length > 3 && (
                        <div className="text-center mt-2">
                           <span className="text-[10px] font-bold text-blue-600 uppercase tracking-widest">+ {attribution.candidates.length - 3} MORE CANDIDATES</span>
                        </div>
                     )}
                   </div>
                 ) : (
                   <div className="text-center text-ink-400 text-sm">
                     <div className="mb-2">AIS correlation not run.</div>
                   </div>
                 )}
              </div>
           </div>

        </div>

      </div>
    </ViewModeProvider>
  );
}
