import MapView from "../components/MapView";
import LayerToggles from "../components/LayerToggles";
import Timeline from "../components/Timeline";
import AnalysisPanel from "../components/AnalysisPanel";
import ErrorBoundary from "../components/ErrorBoundary";
import { ViewModeProvider } from "../lib/viewMode";
import { useSpillState } from "../context/SpillContext";

export default function MaritimeMap() {
  const {
    caseMeta,
    detection,
    hindcast,
    forecast,
    attribution,
    selectedMmsi,
    setSelectedMmsi,
    hindcastIndex,
    forecastIndex,
    viewMode,
    setViewMode,
    layers,
    toggleLayer,
    focusRequest,
  } = useSpillState();

  return (
    <ViewModeProvider value={viewMode}>
      <div className="relative w-full h-full flex flex-col bg-ink-50">
        <header className="px-6 py-4 border-b border-ink-200 flex justify-between items-center bg-white dark:bg-ink-100 z-10 shrink-0 shadow-sm">
          <div>
            <h2 className="text-lg font-bold text-ink-900 tracking-tight">Maritime Map</h2>
            <p className="text-xs text-ink-500 mt-0.5">Central operational command map</p>
          </div>
          <div className="flex items-center gap-2 bg-ink-50 p-1 rounded-md border border-ink-200">
             {(["analyst", "executive"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setViewMode(m)}
                className={`px-3 py-1.5 text-xs font-semibold rounded uppercase tracking-wider transition-all ${
                  viewMode === m 
                    ? "bg-white dark:bg-ink-200 shadow-sm text-blue-600 dark:text-blue-400 border border-ink-200"
                    : "text-ink-500 hover:text-ink-800"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </header>
        
        <div className="flex-1 relative min-h-0 bg-[#e5e9f0] dark:bg-[#0b111b]"> {/* Slightly blueish map bg placeholder */}
          <ErrorBoundary label="Map">
            <MapView
              caseMeta={caseMeta}
              detection={detection}
              hindcast={hindcast}
              forecast={forecast}
              attribution={attribution}
              layers={layers}
              hindcastIndex={hindcastIndex}
              forecastIndex={forecastIndex}
              selectedMmsi={selectedMmsi}
              onSelectVessel={setSelectedMmsi}
              focusRequest={focusRequest}
            />
          </ErrorBoundary>
          
          {/* Subtle inset shadow for depth */}
          <div className="pointer-events-none absolute inset-0 z-[5] shadow-[inset_0_0_80px_20px_rgba(0,0,0,0.03)]" />
          
          <div className="pointer-events-none absolute left-4 top-4 z-10 flex flex-col gap-4">
            <LayerToggles layers={layers} onToggle={toggleLayer} />
          </div>
          
          <div className="pointer-events-none absolute right-4 top-4 z-10">
            <AnalysisPanel />
          </div>

          <div className="pointer-events-none absolute inset-x-4 bottom-6 z-10">
            <Timeline />
          </div>
        </div>
      </div>
    </ViewModeProvider>
  );
}
