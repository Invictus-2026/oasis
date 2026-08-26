import { useSpillState } from "../context/SpillContext";
import { Play, Pause, FastForward, Rewind } from "lucide-react";

export default function AnalysisPanel() {
  const {
    caseMeta,
    hindcast,
    forecast,
    runHindcast,
    runForecast,
    drifting,
    playing,
    setPlaying,
    frameIndex,
    frames,
  } = useSpillState();

  if (!caseMeta) return null;

  return (
    <div className="pointer-events-auto rounded-md border border-ink-200 bg-white shadow-sm w-64 overflow-hidden">
      <div className="bg-ink-50 px-3 py-2 border-b border-ink-200 flex justify-between items-center">
        <h3 className="text-xs font-bold text-ink-700 tracking-wider">ANALYSIS</h3>
      </div>

      <div className="p-3 space-y-4">
        {/* Incident Info */}
        <div>
          <div className="text-[10px] text-ink-400 uppercase font-semibold mb-1">Incident</div>
          <div className="text-sm font-medium text-ink-900">{caseMeta.name}</div>
        </div>

        <div className="border-t border-ink-100 pt-3">
          <div className="text-[10px] text-ink-400 uppercase font-semibold mb-2">Drift Simulation</div>
          
          <div className="flex flex-col gap-2">
            <button
              onClick={runHindcast}
              disabled={!!drifting}
              className="flex items-center justify-between px-2 py-1.5 rounded bg-ink-50 hover:bg-blue-50 border border-ink-200 hover:border-blue-200 transition-colors text-sm text-ink-700 disabled:opacity-50"
            >
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${hindcast ? "bg-blue-500" : "bg-ink-300"}`} />
                Hindcast
              </div>
              {drifting === "hindcast" && <span className="text-[10px] animate-pulse">Running...</span>}
            </button>
            
            <button
              onClick={runForecast}
              disabled={!!drifting}
              className="flex items-center justify-between px-2 py-1.5 rounded bg-ink-50 hover:bg-blue-50 border border-ink-200 hover:border-blue-200 transition-colors text-sm text-ink-700 disabled:opacity-50"
            >
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${forecast ? "bg-purple-500" : "bg-ink-300"}`} />
                Forecast
              </div>
               {drifting === "forecast" && <span className="text-[10px] animate-pulse">Running...</span>}
            </button>
          </div>
        </div>

        {hindcast && (
          <div className="border-t border-ink-100 pt-3">
            <div className="flex justify-between items-center mb-1">
              <span className="text-[10px] text-ink-400 uppercase font-semibold">Particles</span>
              <span className="text-xs font-mono font-medium">50,000</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-[10px] text-ink-400 uppercase font-semibold">Windage</span>
              <span className="text-xs font-mono font-medium">3%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
