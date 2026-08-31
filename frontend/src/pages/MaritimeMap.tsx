import MapView from "../components/MapView";
import LayerToggles from "../components/LayerToggles";
import Timeline from "../components/Timeline";
import ErrorBoundary from "../components/ErrorBoundary";
import { ViewModeProvider } from "../lib/viewMode";
import { useSpillState } from "../context/SpillContext";
import { Navigation } from "lucide-react";
import { useLocation } from "react-router-dom";

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
    mockWindDir,
    activeSlickId,
    customOverlays,
    runHindcast,
    runForecast,
    drifting,
    activeReRouteOption,
  } = useSpillState();

  const location = useLocation();
  // On the standalone Maritime Map page (/map), always show ALL spills.
  // On intelligence pages (drift/vessel/attribution), use the isolated activeSlickId.
  const isMapPage = location.pathname === "/map";
  const effectiveSlickId = isMapPage ? null : activeSlickId;

  return (
    <ViewModeProvider value={viewMode}>
      <div className="relative w-full h-full flex flex-col bg-ink-50">
        <header className="px-6 py-4 border-b border-ink-200 flex justify-between items-center bg-white z-10 shrink-0 shadow-sm">
          <div>
            <h2 className="text-lg font-bold text-ink-900 tracking-tight">Maritime Map</h2>
            <p className="text-xs text-ink-500 mt-0.5">Central operational command map</p>
          </div>
          <div className="flex items-center gap-2 bg-ink-50 p-1 rounded-md border border-ink-200">
            {(["analyst", "executive"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setViewMode(m)}
                className={`px-3 py-1.5 text-xs font-semibold rounded uppercase tracking-wider transition-all ${viewMode === m
                  ? "bg-white shadow-sm text-blue-600 border border-ink-200"
                  : "text-ink-500 hover:text-ink-800"
                  }`}
              >
                {m}
              </button>
            ))}
          </div>
        </header>

        <div className="flex-1 relative min-h-0 bg-[#e5e9f0]"> {/* Slightly blueish map bg placeholder */}
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
              activeSlickId={effectiveSlickId}
              mockWindDir={mockWindDir}
              customOverlays={customOverlays}
              reRouteOption={activeReRouteOption}
            />
          </ErrorBoundary>

          {/* Subtle inset shadow for depth */}
          <div className="pointer-events-none absolute inset-0 z-[5] shadow-[inset_0_0_80px_20px_rgba(0,0,0,0.03)]" />

          <div className="pointer-events-none absolute left-4 top-4 z-10 flex flex-col gap-4">
            <LayerToggles layers={layers} onToggle={toggleLayer} />
          </div>

          <div className="pointer-events-none absolute right-4 top-4 z-10">
            <div className="pointer-events-auto flex gap-2 rounded-md border border-ink-200 bg-white shadow-sm p-2">
              <button
                onClick={() => runHindcast()}
                disabled={!!drifting}
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-ink-50 hover:bg-blue-50 border border-ink-200 hover:border-blue-200 transition-colors text-sm text-ink-700 disabled:opacity-50"
              >
                <div className={`w-2 h-2 rounded-full ${hindcast ? "bg-blue-500" : "bg-ink-300"}`} />
                {drifting === "hindcast" ? "Running..." : "Hindcast"}
              </button>

              <button
                onClick={() => runForecast()}
                disabled={!!drifting}
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-ink-50 hover:bg-blue-50 border border-ink-200 hover:border-blue-200 transition-colors text-sm text-ink-700 disabled:opacity-50"
              >
                <div className={`w-2 h-2 rounded-full ${forecast ? "bg-purple-500" : "bg-ink-300"}`} />
                {drifting === "forecast" ? "Running..." : "Forecast"}
              </button>
            </div>
          </div>

          {/* Compass Widget */}
          <div className="pointer-events-none absolute left-4 bottom-24 z-10 flex flex-col items-center justify-center bg-white/95 backdrop-blur-sm p-3 rounded-xl shadow-lg border border-ink-200 w-24 h-24">
            <span className="text-[10px] font-bold tracking-widest text-ink-400 mb-1">WIND</span>
            <div className="relative flex items-center justify-center w-12 h-12 rounded-full border border-ink-100 bg-ink-50">
              <span className="absolute top-0 text-[8px] font-bold text-ink-300 -mt-0.5">N</span>
              <span className="absolute bottom-0 text-[8px] font-bold text-ink-300 -mb-0.5">S</span>
              <span className="absolute left-0 text-[8px] font-bold text-ink-300 ml-1">W</span>
              <span className="absolute right-0 text-[8px] font-bold text-ink-300 mr-1">E</span>
              <Navigation
                className="w-6 h-6 text-blue-600 transition-transform duration-700 ease-out"
                style={{ transform: `rotate(${mockWindDir}deg)` }}
              />
            </div>
            <span className="text-xs font-bold text-ink-700 mt-1">{mockWindDir}°</span>
          </div>

          <div className="pointer-events-none absolute inset-x-4 bottom-6 z-10">
            <Timeline />
          </div>
        </div>
      </div>
    </ViewModeProvider>
  );
}
