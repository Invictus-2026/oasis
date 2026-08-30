import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider } from "../lib/viewMode";
import { km2, pct, hours, km } from "../lib/format";
import {
   Activity, AlertTriangle, Anchor,
   Satellite, Search, Waves, Wind, Navigation, ShieldCheck, Target, Crosshair
} from "lucide-react";

export default function Overview() {
   const {
      caseMeta, detection, hindcast, forecast, attribution, viewMode,
      runHindcast, runAttribute, drifting, attributing,
   } = useSpillState();

   const runAisCorrelation = async () => {
      const h = hindcast ?? (await runHindcast());
      if (h) await runAttribute(undefined, h);
   };

   const slick = detection?.slicks[0];
   const origin = hindcast?.origin_estimate;
   const impact = forecast?.impact_flags;

   return (
      <ViewModeProvider value={viewMode}>
         <div className="flex flex-col min-h-full bg-ink-50">
            
            {/* HERO SECTION: MarineTraffic Map */}
            <div className="relative w-full h-[400px] shrink-0 bg-ink-900 overflow-hidden">
               <iframe 
                  src="https://www.marinetraffic.com/en/ais/embed/zoom:9/centery:27.05/centerx:-90.0"
                  className="absolute inset-0 w-full h-full border-0 z-0 mix-blend-luminosity opacity-80"
                  title="Marine Traffic Live Map"
               />
               
               
               
               {/* Bottom fade out */}
               <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-ink-50 to-transparent z-10 pointer-events-none" />
            </div>

            {/* MAIN DASHBOARD CONTENT */}
            <div className="flex-1 px-6 pb-12 -mt-6 relative z-20 space-y-6">
               
               {/* VITAL SIGNS (2x2 Grid) */}
               <div className="grid grid-cols-2 gap-4">
                  <div className="bg-white p-5 rounded-2xl shadow-sm border border-ink-200/60 hover:shadow-md transition-shadow group">
                     <div className="flex items-start justify-between mb-2">
                        <div className="text-[10px] font-bold text-ink-400 uppercase tracking-widest">Active Incident</div>
                        <Activity className="w-4 h-4 text-blue-500 group-hover:scale-110 transition-transform" />
                     </div>
                     <div className="text-3xl font-black text-ink-900">1</div>
                     <div className="text-[10px] text-blue-600 font-bold mt-1 uppercase tracking-widest">Gulf of Mexico</div>
                  </div>
                  
                  <div className="bg-white p-5 rounded-2xl shadow-sm border border-ink-200/60 hover:shadow-md transition-shadow group">
                     <div className="flex items-start justify-between mb-2">
                        <div className="text-[10px] font-bold text-ink-400 uppercase tracking-widest">Slick Area</div>
                        <AlertTriangle className="w-4 h-4 text-amber-500 group-hover:scale-110 transition-transform" />
                     </div>
                     <div className="text-3xl font-black text-ink-900">{slick ? km2(slick.geometry.area_km2) : "--"}</div>
                     <div className="text-[10px] text-amber-600 font-bold mt-1 uppercase tracking-widest">Confirmed Size</div>
                  </div>

                  <div className="bg-white p-5 rounded-2xl shadow-sm border border-ink-200/60 hover:shadow-md transition-shadow group">
                     <div className="flex items-start justify-between mb-2">
                        <div className="text-[10px] font-bold text-ink-400 uppercase tracking-widest">Suspect Vessels</div>
                        <Search className="w-4 h-4 text-purple-500 group-hover:scale-110 transition-transform" />
                     </div>
                     <div className="text-3xl font-black text-ink-900">{attribution ? attribution.after_filter : "--"}</div>
                     <div className="text-[10px] text-purple-600 font-bold mt-1 uppercase tracking-widest">Correlated Targets</div>
                  </div>

                  <div className="bg-white p-5 rounded-2xl shadow-sm border border-ink-200/60 hover:shadow-md transition-shadow group relative overflow-hidden">
                     <div className={`absolute right-0 top-0 w-24 h-24 blur-2xl rounded-full opacity-20 ${impact && impact.length > 0 ? 'bg-red-500' : 'bg-emerald-500'}`} />
                     <div className="flex items-start justify-between mb-2 relative z-10">
                        <div className="text-[10px] font-bold text-ink-400 uppercase tracking-widest">Coast Threat</div>
                        <Waves className={`w-4 h-4 ${impact && impact.length > 0 ? 'text-red-500' : 'text-emerald-500'} group-hover:scale-110 transition-transform`} />
                     </div>
                     <div className="text-3xl font-black text-ink-900 relative z-10">{impact && impact.length > 0 ? "YES" : "NO"}</div>
                     <div className={`text-[10px] font-bold mt-1 uppercase tracking-widest relative z-10 ${impact && impact.length > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                        {impact && impact.length > 0 ? 'Impact Imminent' : 'Clear Region'}
                     </div>
                  </div>
               </div>

               {/* INTELLIGENCE BRIEF */}
               <div className="bg-white rounded-2xl shadow-sm border border-ink-200/60 overflow-hidden">
                  <div className="bg-gradient-to-r from-ink-100/50 to-transparent px-5 py-4 border-b border-ink-100 flex items-center justify-between">
                     <div className="flex items-center gap-2">
                        <Satellite className="w-4 h-4 text-ink-600" />
                        <span className="font-bold text-sm text-ink-900 tracking-tight">Intelligence Brief</span>
                     </div>
                     <ShieldCheck className="w-4 h-4 text-emerald-500" />
                  </div>
                  <div className="p-5 flex flex-col gap-5">
                     {caseMeta ? (
                        <div className="grid grid-cols-2 gap-4">
                           <div className="bg-ink-50 rounded-xl p-4 border border-ink-100/50">
                              <div className="text-[10px] font-bold uppercase tracking-widest text-ink-400 mb-3">Observation Context</div>
                              <div className="space-y-3">
                                 <div>
                                    <div className="text-[9px] font-bold text-ink-400 uppercase">Region</div>
                                    <div className="text-xs font-bold text-ink-900">{caseMeta.name}</div>
                                 </div>
                                 <div>
                                    <div className="text-[9px] font-bold text-ink-400 uppercase">Scene ID</div>
                                    <div className="text-xs font-mono font-semibold text-blue-600 truncate">{caseMeta.scene_id}</div>
                                 </div>
                                 <div>
                                    <div className="text-[9px] font-bold text-ink-400 uppercase">Acquired At</div>
                                    <div className="text-xs font-mono font-semibold text-ink-700">{new Date(caseMeta.acquired_at).toLocaleString()}</div>
                                 </div>
                              </div>
                           </div>
                           
                           {slick ? (
                              <div className="bg-amber-50/50 rounded-xl p-4 border border-amber-100/50 flex flex-col justify-center">
                                 <div className="text-center mb-4">
                                    <div className="text-3xl font-black text-amber-600 tabular-nums">{km2(slick.geometry.area_km2)}</div>
                                    <div className="text-[9px] font-bold text-amber-500 uppercase tracking-widest mt-1">Confirmed Area</div>
                                 </div>
                                 <div className="space-y-2">
                                    <div className="flex justify-between items-center text-xs">
                                       <span className="font-bold uppercase text-ink-500">Confidence</span>
                                       <span className="font-mono font-bold text-ink-900">{pct(slick.confidence)}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-xs">
                                       <span className="font-bold uppercase text-ink-500">Method</span>
                                       <span className="font-bold text-ink-900 capitalize">{slick.method}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-xs">
                                       <span className="font-bold uppercase text-ink-500">Lookalikes</span>
                                       <span className="font-mono font-bold text-ink-900">{detection.rejected_lookalikes.length} Rejected</span>
                                    </div>
                                 </div>
                              </div>
                           ) : (
                              <div className="bg-ink-50 rounded-xl p-4 border border-ink-100/50 flex items-center justify-center text-center">
                                 <div className="text-ink-400 text-xs font-bold">Detection not run yet</div>
                              </div>
                           )}
                        </div>
                     ) : (
                        <div className="text-center text-ink-400 text-sm italic py-4">Case metadata loading...</div>
                     )}
                  </div>
               </div>

               {/* ENVIRONMENTAL THREAT MATRIX */}
               <div className="bg-white rounded-2xl shadow-sm border border-ink-200/60 overflow-hidden">
                  <div className="bg-gradient-to-r from-ink-100/50 to-transparent px-5 py-4 border-b border-ink-100 flex items-center justify-between">
                     <div className="flex items-center gap-2">
                        <Wind className="w-4 h-4 text-blue-600" />
                        <span className="font-bold text-sm text-ink-900 tracking-tight">Environmental Threat Matrix</span>
                     </div>
                     <Target className="w-4 h-4 text-blue-400" />
                  </div>
                  <div className="p-5">
                     {origin || forecast ? (
                        <div className="grid grid-cols-1 gap-4">
                           {origin && (
                              <div className="bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl p-4 border border-blue-200/60 relative overflow-hidden">
                                 <div className="absolute right-0 bottom-0 opacity-10 pointer-events-none">
                                    <Crosshair className="w-24 h-24 -mb-6 -mr-6" />
                                 </div>
                                 <div className="text-[10px] font-bold uppercase tracking-widest text-blue-600 mb-3 relative z-10">Hindcast Origin Estimate</div>
                                 <div className="flex justify-between items-center mb-2 relative z-10">
                                    <span className="text-xs font-bold text-ink-600 uppercase">Estimated Release</span>
                                    <span className="font-mono font-black text-ink-900 text-sm bg-white/50 px-2 py-0.5 rounded shadow-sm border border-blue-100/50">{new Date(origin.time_utc).toLocaleTimeString()}</span>
                                 </div>
                                 <div className="flex justify-between items-center relative z-10">
                                    <span className="text-xs font-bold text-ink-600 uppercase">Uncertainty Radius</span>
                                    <span className="font-mono font-bold text-ink-900 text-sm">{km(origin.uncertainty_radius_km)}</span>
                                 </div>
                              </div>
                           )}
                           {forecast && (
                              <div className={`rounded-xl p-4 border relative overflow-hidden ${impact && impact.length > 0 ? 'bg-gradient-to-br from-red-50 to-red-100/50 border-red-200/60' : 'bg-gradient-to-br from-emerald-50 to-emerald-100/50 border-emerald-200/60'}`}>
                                 <div className={`text-[10px] font-bold uppercase tracking-widest mb-3 relative z-10 ${impact && impact.length > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                                    72h Forecast Impact Threat
                                 </div>
                                 {impact && impact.length > 0 ? (
                                    <div className="text-sm font-black text-red-700 flex items-center gap-3 relative z-10 bg-white/50 px-3 py-2 rounded-lg border border-red-200/50">
                                       <AlertTriangle className="w-5 h-5 shrink-0 animate-pulse text-red-600" />
                                       Coastline impact expected in {hours(impact[0].eta_hours)}
                                    </div>
                                 ) : (
                                    <div className="text-sm font-bold text-emerald-700 flex items-center gap-3 relative z-10 bg-white/50 px-3 py-2 rounded-lg border border-emerald-200/50">
                                       <Waves className="w-5 h-5 shrink-0 text-emerald-500" />
                                       No coastline impact predicted
                                    </div>
                                 )}
                              </div>
                           )}
                        </div>
                     ) : (
                        <div className="text-center text-ink-400 text-sm font-bold italic py-2">Environmental models not run.</div>
                     )}
                  </div>
               </div>

               {/* ATTRIBUTION ROSTER */}
               <div className="bg-white rounded-2xl shadow-sm border border-ink-200/60 overflow-hidden mb-8">
                  <div className="bg-gradient-to-r from-ink-100/50 to-transparent px-5 py-4 border-b border-ink-100 flex items-center justify-between">
                     <div className="flex items-center gap-2">
                        <Anchor className="w-4 h-4 text-purple-600" />
                        <span className="font-bold text-sm text-ink-900 tracking-tight">Attribution Roster</span>
                     </div>
                     <span className="text-[10px] font-bold uppercase tracking-widest text-ink-400">
                        {attribution ? `${attribution.total_vessels_in_region} Scanned` : "Pending"}
                     </span>
                  </div>
                  <div className="p-5">
                     {attribution ? (
                        <div className="space-y-3">
                           {attribution.candidates.slice(0, 4).map((c, i) => (
                              <div key={c.mmsi} className="group flex justify-between items-center p-3 border border-ink-100/60 bg-ink-50/30 rounded-xl hover:bg-white hover:border-ink-200 hover:shadow-sm transition-all duration-200">
                                 <div className="flex items-center gap-4">
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-black shrink-0 border ${c.flags.includes("DARK_VESSEL") ? "bg-red-50 text-red-600 border-red-200 shadow-[0_0_10px_rgba(239,68,68,0.2)]" : "bg-white text-ink-600 border-ink-200"}`}>
                                       {i + 1}
                                    </div>
                                    <div>
                                       <div className="text-sm font-bold text-ink-900 leading-tight group-hover:text-blue-600 transition-colors">{c.name}</div>
                                       <div className="flex items-center gap-2 mt-0.5">
                                          <Navigation className="w-3 h-3 text-ink-400" />
                                          <div className="text-[10px] text-ink-500 font-mono font-semibold">{c.mmsi}</div>
                                       </div>
                                    </div>
                                 </div>
                                 <div className="text-right">
                                    <div className="font-mono font-black text-ink-900 text-base">{c.score.toFixed(3)}</div>
                                    <div className="text-[9px] uppercase tracking-widest text-ink-400 font-bold mt-0.5">Match</div>
                                 </div>
                              </div>
                           ))}
                           {attribution.candidates.length > 4 && (
                              <div className="text-center mt-4">
                                 <button className="text-[10px] font-bold text-blue-600 uppercase tracking-widest hover:text-blue-800 transition-colors px-4 py-2 bg-blue-50 hover:bg-blue-100 rounded-lg">
                                    View All {attribution.candidates.length} Candidates
                                 </button>
                              </div>
                           )}
                        </div>
                     ) : (
                        <div className="flex flex-col items-center gap-3 py-4">
                           <div className="text-ink-400 text-sm font-bold italic">AIS correlation not run.</div>
                           <button
                              onClick={runAisCorrelation}
                              disabled={!!drifting || attributing}
                              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold uppercase tracking-widest transition-colors disabled:opacity-50"
                           >
                              <Anchor className="w-3.5 h-3.5" />
                              {attributing || drifting ? "Correlating..." : "Run AIS Correlation"}
                           </button>
                        </div>
                     )}
                  </div>
               </div>

            </div>
         </div>
      </ViewModeProvider>
   );
}
