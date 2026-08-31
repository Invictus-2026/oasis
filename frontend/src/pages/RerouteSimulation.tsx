import React, { useState, useEffect } from "react";
import { useSpillState } from "../context/SpillContext";
import MapView from "../components/MapView";
import { ViewModeProvider } from "../lib/viewMode";
import LayerToggles from "../components/LayerToggles";
import Timeline from "../components/Timeline";
import { reroute } from "../api/client";
import type { RerouteResponse } from "../api/types";

export default function RerouteSimulation() {
  const {
    caseMeta,
    detection,
    hindcast,
    forecast,
    attribution,
    layers,
    toggleLayer,
    hindcastIndex,
    forecastIndex,
    selectedMmsi,
    setSelectedMmsi,
    focusRequest,
    activeSlickId,
    setActiveSlickId,
    mockWindDir,
    customOverlays,
    runHindcast,
    runForecast,
    drifting,
  } = useSpillState();

  const [startPoint, setStartPoint] = useState<[number, number] | null>(null);
  const [endPoint, setEndPoint] = useState<[number, number] | null>(null);
  const [rerouteResult, setRerouteResult] = useState<RerouteResponse | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);

  const handleMapClick = (lngLat: [number, number]) => {
    if (!startPoint) {
      setStartPoint(lngLat);
    } else if (!endPoint) {
      setEndPoint(lngLat);
    } else {
      // Reset
      setStartPoint(lngLat);
      setEndPoint(null);
      setRerouteResult(null);
    }
  };

  const calculateReroute = async () => {
    setIsSimulating(true);

    try {
      const obstacles: import("geojson").Geometry[] = [];
      if (detection?.slicks) {
        obstacles.push(...detection.slicks.map((s) => s.polygon));
      }
      if (forecast?.cone) {
        obstacles.push(...forecast.cone.map(c => c.polygon));
      }
      if (hindcast?.cone) {
        obstacles.push(...hindcast.cone.map(c => c.polygon));
      }

      // Check physics classification: thin oil sheen (<= 35um) rapidly evaporates and does NOT require rerouting
      const activeSlick = activeSlickId
        ? detection?.slicks.find(s => s.id === activeSlickId)
        : detection?.slicks?.[0];

      const isEvaporativeSafe = activeSlick
        ? (activeSlick.thickness_um ?? 25) <= 35
        : false;

      const res = await reroute({
        start_point: startPoint,
        end_point: endPoint,
        obstacles,
        safety_margin_km: 2.0,
        re_route_needed: !isEvaporativeSafe,
      });
      setRerouteResult(res);
      if (res.error) {
        alert(res.error);
      }
    } catch (e) {
      console.error("Routing failed:", e);
    } finally {
      setIsSimulating(false);
    }
  };

  useEffect(() => {
    calculateReroute();
  }, [startPoint, endPoint, detection, forecast, hindcast]);

  return (
    <ViewModeProvider value="analyst">
      <div className="flex h-full w-full bg-ink-50">
        <div className="flex-1 relative min-h-0 bg-[#e5e9f0]">
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
            activeSlickId={activeSlickId}
            mockWindDir={mockWindDir}
            customOverlays={customOverlays}
            rerouteResult={rerouteResult}
            onMapClick={handleMapClick}
            simWaypoints={[...(startPoint ? [startPoint] : []), ...(endPoint ? [endPoint] : [])]}
          />
          <div className="pointer-events-none absolute inset-0 z-[5] shadow-[inset_0_0_80px_20px_rgba(0,0,0,0.03)]" />
          <div className="pointer-events-none absolute left-4 top-4 z-10 flex flex-col gap-4">
            <LayerToggles layers={layers} onToggle={toggleLayer} />
          </div>

          <div className="pointer-events-none absolute right-4 top-4 z-10">
            <div className="pointer-events-auto flex items-center bg-white/95 backdrop-blur-sm p-1 rounded shadow-md border border-ink-200">
              <button
                onClick={() => runHindcast(undefined, true)}
                disabled={!!drifting}
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-ink-50 hover:bg-blue-50 border border-ink-200 hover:border-blue-200 transition-colors text-sm text-ink-700 disabled:opacity-50 mr-1"
              >
                <div className={`w-2 h-2 rounded-full ${hindcast ? "bg-blue-500" : "bg-ink-300"}`} />
                {drifting === "hindcast" ? "Running..." : "Hindcast"}
              </button>

              <button
                onClick={() => runForecast(undefined, true)}
                disabled={!!drifting}
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-ink-50 hover:bg-purple-50 border border-ink-200 hover:border-purple-200 transition-colors text-sm text-ink-700 disabled:opacity-50"
              >
                <div className={`w-2 h-2 rounded-full ${forecast ? "bg-purple-500" : "bg-ink-300"}`} />
                {drifting === "forecast" ? "Running..." : "Forecast"}
              </button>
            </div>
          </div>

          {/* Timeline Widget at the bottom */}
          <div className="pointer-events-none absolute inset-x-4 bottom-6 z-10">
            <Timeline />
          </div>
        </div>

        {/* Sidebar */}
        <div className="w-[400px] border-l border-ink-200 bg-white shadow-[-4px_0_15px_-3px_rgba(0,0,0,0.05)] z-20 flex flex-col">
          <div className="p-6 border-b border-ink-100">
            <h2 className="text-xl font-semibold text-ink-900 mb-1">Reroute Simulation</h2>
            <p className="text-sm text-ink-500">Plan safe trajectories around active spill regions.</p>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-ink-900 uppercase tracking-wider">Instructions</h3>
              <p className="text-sm text-ink-700 bg-blue-50 border border-blue-100 rounded p-4">
                Click on the map to place a <strong>Start Point</strong>, then click again to place a <strong>Destination Point</strong>. 
                The system will automatically calculate the safest route avoiding active spills.
              </p>
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-ink-900 uppercase tracking-wider">Waypoints</h3>
              <div className="flex items-center justify-between p-3 bg-ink-50 rounded border border-ink-200">
                <span className="text-sm font-medium text-ink-700">Start Point</span>
                <span className="text-xs font-mono text-ink-500">
                  {startPoint ? `${startPoint[1].toFixed(4)}°, ${startPoint[0].toFixed(4)}°` : "Not set"}
                </span>
              </div>
              <div className="flex items-center justify-between p-3 bg-ink-50 rounded border border-ink-200">
                <span className="text-sm font-medium text-ink-700">End Point</span>
                <span className="text-xs font-mono text-ink-500">
                  {endPoint ? `${endPoint[1].toFixed(4)}°, ${endPoint[0].toFixed(4)}°` : "Not set"}
                </span>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-ink-900 uppercase tracking-wider">Active Spills</h3>
              <div className="space-y-2">
                <button
                  onClick={() => setActiveSlickId(null)}
                  className="w-full text-left px-3 py-2 text-sm rounded bg-ink-50 hover:bg-ink-100 border border-ink-200 transition-colors text-ink-900 font-medium"
                >
                  All Spills
                </button>
                {detection?.slicks.map((s, i) => (
                  <button
                    key={s.id}
                    onClick={() => setActiveSlickId(s.id)}
                    className={`w-full flex justify-between items-center px-3 py-2 text-sm rounded border transition-colors ${
                      activeSlickId === s.id
                        ? "bg-blue-50 border-blue-200"
                        : "bg-white border-ink-200 hover:bg-ink-50"
                    }`}
                  >
                    <span className="font-medium text-ink-900">Spill #{i + 1}</span>
                    <span className="text-xs text-ink-500">{s.geometry.area_km2.toFixed(1)} km²</span>
                  </button>
                ))}
              </div>
            </div>

            {rerouteResult && (
              <div className="space-y-4 pt-4 border-t border-ink-200">
                <h3 className="text-sm font-semibold text-ink-900 uppercase tracking-wider">Routing Analysis</h3>
                {rerouteResult.is_rerouted ? (
                  <div className="space-y-3">
                    <div className="bg-red-50 border border-red-100 rounded p-3 flex justify-between items-center">
                      <span className="text-sm font-medium text-red-800">Original Distance</span>
                      <span className="text-sm font-bold text-red-900">{rerouteResult.distance_original_km.toFixed(1)} km</span>
                    </div>
                    <div className="bg-green-50 border border-green-100 rounded p-3 flex justify-between items-center">
                      <span className="text-sm font-medium text-green-800">Rerouted Distance</span>
                      <span className="text-sm font-bold text-green-900">{rerouteResult.distance_rerouted_km.toFixed(1)} km</span>
                    </div>

                    <div className="mt-4 space-y-2">
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-ink-600">Extra Distance:</span>
                        <span className="font-semibold text-ink-900">
                          {(rerouteResult.distance_rerouted_km - rerouteResult.distance_original_km).toFixed(1)} km
                        </span>
                      </div>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-ink-600">Extra Time (+15 kts):</span>
                        <span className="font-semibold text-ink-900">
                          {rerouteResult.extra_time_hours.toFixed(2)} hrs
                        </span>
                      </div>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-ink-600">Est. Extra Fuel:</span>
                        <span className="font-semibold text-ink-900">
                          {rerouteResult.extra_fuel_tons.toFixed(2)} tons
                        </span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-center">
                    <p className="text-sm font-bold text-emerald-900">Safe Direct Transit!</p>
                    <p className="text-xs text-emerald-700 mt-1 leading-relaxed">
                      Oil sheen is thin (&le; 35 µm) and rapidly evaporates. Physics classification model confirms <strong>No Reroute Required</strong>. Proceed on planned direct voyage.
                    </p>
                  </div>
                )}
              </div>
            )}
            
            {isSimulating && (
              <div className="pt-4 flex justify-center">
                <span className="text-sm font-medium text-blue-600 animate-pulse">Calculating optimal route...</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </ViewModeProvider>
  );
}
