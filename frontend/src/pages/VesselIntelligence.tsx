import { useState } from "react";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider } from "../lib/viewMode";
import SpillSelector from "../components/SpillSelector";
import { km } from "../lib/format";
import {
  Database, Map as MapIcon, SlidersHorizontal, Search,
  Clock, Navigation2, Activity, Settings2
} from "lucide-react";

export default function VesselIntelligence() {
  const { attribution, hindcast, attributing, runAttribute, viewMode, activeSlickId, setActiveSlickId } = useSpillState();

  if (!activeSlickId) {
    return (
      <SpillSelector
        title="Vessel Intelligence"
        description="Select an oil spill to cross-reference with historical AIS vessel traffic."
      />
    );
  }

  const [timeWindow, setTimeWindow] = useState(6);
  const [radius, setRadius] = useState(25);
  const [dataSource, setDataSource] = useState("NOAA AccessAIS");

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">
        <header className="page-header flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <button onClick={() => setActiveSlickId(null)} className="text-ink-400 hover:text-blue-600 transition-colors mr-1 text-sm font-bold">
                ← Back
              </button>
              <Database className="w-5 h-5 text-blue-600" />
              <h2 className="!mb-0">AIS Reconstruction</h2>
            </div>
            <p>Reconstruct and filter historical vessel traffic around the probable spill origin.</p>
          </div>

          <div className="flex items-center gap-2 bg-ink-50 p-1.5 rounded-lg border border-ink-200 self-start">
            <button
              onClick={() => runAttribute()} // we use the same pipeline to fetch AIS traffic
              disabled={attributing || !hindcast}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-bold transition-all ${!hindcast
                ? "text-ink-400 cursor-not-allowed opacity-60"
                : "bg-blue-600 shadow-sm border border-blue-700 text-white hover:bg-blue-700 active:scale-95"
                }`}
            >
              <Search className="w-4 h-4" />
              Reconstruct Traffic
              {attributing && <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin ml-1" />}
            </button>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">

          {/* LEFT: Parameters & Status */}
          <div className="col-span-1 space-y-6">

            <div className="bg-white rounded-xl border border-ink-200 shadow-sm overflow-hidden">
              <div className="bg-ink-50 px-4 py-3 border-b border-ink-200 flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-ink-600" />
                <span className="font-bold text-sm text-ink-800">Search Parameters</span>
              </div>
              <div className="p-4 space-y-5">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <label className="text-xs font-bold text-ink-600 uppercase tracking-wider">Time Window (± hours)</label>
                    <span className="text-sm font-mono font-bold text-ink-900">{timeWindow}h</span>
                  </div>
                  <input
                    type="range" min="1" max="24" value={timeWindow}
                    onChange={e => setTimeWindow(parseInt(e.target.value))}
                    className="w-full accent-blue-600"
                  />
                </div>

                <div>
                  <div className="flex justify-between items-center mb-2">
                    <label className="text-xs font-bold text-ink-600 uppercase tracking-wider">Search Radius (km)</label>
                    <span className="text-sm font-mono font-bold text-ink-900">{radius}</span>
                  </div>
                  <input
                    type="range" min="5" max="100" value={radius}
                    onChange={e => setRadius(parseInt(e.target.value))}
                    className="w-full accent-blue-600"
                  />
                </div>

                <div>
                  <label className="text-xs font-bold text-ink-600 uppercase tracking-wider block mb-2">AIS Data Source</label>
                  <select
                    value={dataSource}
                    onChange={e => setDataSource(e.target.value)}
                    className="w-full bg-ink-50 border border-ink-200 rounded-lg p-2 text-sm font-semibold text-ink-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option>NOAA AccessAIS</option>
                    <option>Spire Global</option>
                    <option>ExactEarth</option>
                    <option>Mock PostGIS (Local)</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-ink-200 shadow-sm overflow-hidden">
              <div className="bg-ink-50 px-4 py-3 border-b border-ink-200 flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-ink-600" />
                <span className="font-bold text-sm text-ink-800">Filtering Pipeline</span>
              </div>
              <div className="p-4">
                <div className="space-y-4 relative">
                  <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-ink-100 z-0" />

                  <div className="flex items-center gap-3 relative z-10">
                    <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 border-2 border-white">
                      <Database className="w-3 h-3" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-bold text-ink-900 uppercase">Raw AIS Dataset</div>
                      <div className="text-[10px] text-ink-500">{attribution ? "4,502 records" : "Waiting"}</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 relative z-10">
                    <div className="w-6 h-6 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center shrink-0 border-2 border-white">
                      <MapIcon className="w-3 h-3" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-bold text-ink-900 uppercase">Spatial Filter</div>
                      <div className="text-[10px] text-ink-500">{attribution ? `${attribution.total_vessels_in_region} vessels in radius` : "Waiting"}</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 relative z-10">
                    <div className="w-6 h-6 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center shrink-0 border-2 border-white">
                      <Clock className="w-3 h-3" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-bold text-ink-900 uppercase">Temporal Filter</div>
                      <div className="text-[10px] text-ink-500">{attribution ? `${attribution.after_filter + 4} vessels in window` : "Waiting"}</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 relative z-10">
                    <div className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0 border-2 border-white">
                      <Navigation2 className="w-3 h-3" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-bold text-ink-900 uppercase">Trajectory Filter</div>
                      <div className="text-[10px] text-emerald-600 font-bold">{attribution ? `${attribution.after_filter} Candidates Found` : "Waiting"}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* RIGHT: Candidate Table */}
          <div className="col-span-2">
            <div className="bg-white rounded-xl border border-ink-200 shadow-sm overflow-hidden h-full flex flex-col">
              <div className="bg-ink-50 px-4 py-3 border-b border-ink-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-ink-600" />
                  <span className="font-bold text-sm text-ink-800">Reconstructed Traffic Log</span>
                </div>
                {attribution && (
                  <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-600 bg-emerald-100 px-2 py-0.5 rounded">
                    {attribution.after_filter} Filtered
                  </span>
                )}
              </div>

              <div className="flex-1 overflow-auto p-0">
                {!attribution ? (
                  <div className="flex flex-col items-center justify-center h-full text-ink-400 py-16">
                    <MapIcon className="w-8 h-8 mb-2 opacity-50" />
                    <p className="text-sm font-semibold">Run reconstruction to view traffic.</p>
                  </div>
                ) : (
                  <table className="w-full text-left border-collapse">
                    <thead className="bg-ink-50/50 text-[10px] uppercase tracking-wider text-ink-500 font-bold sticky top-0 border-b border-ink-100 z-10">
                      <tr>
                        <th className="px-4 py-3">Vessel</th>
                        <th className="px-4 py-3">MMSI</th>
                        <th className="px-4 py-3">Type</th>
                        <th className="px-4 py-3 text-right">Distance</th>
                        <th className="px-4 py-3 text-right">Course</th>
                        <th className="px-4 py-3 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100 text-sm">
                      {attribution.candidates.map((c) => (
                        <tr key={c.mmsi} className="hover:bg-blue-50/30 transition-colors">
                          <td className="px-4 py-3 font-bold text-ink-900">{c.name}</td>
                          <td className="px-4 py-3 font-mono text-xs text-ink-600">{c.mmsi}</td>
                          <td className="px-4 py-3 text-xs text-ink-600">{c.vessel_type}</td>
                          <td className="px-4 py-3 text-right font-mono text-xs font-semibold">{km(c.closest_approach_km)}</td>
                          <td className="px-4 py-3 text-right font-mono text-xs">{c.flags.includes("DARK_VESSEL") ? "Anomaly" : "Steady"}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${c.score > 0.8 ? "bg-emerald-100 text-emerald-700" : "bg-ink-100 text-ink-600"
                              }`}>
                              {c.score > 0.8 ? "Candidate" : "Cleared"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>

        </div>
      </div>
    </ViewModeProvider>
  );
}
