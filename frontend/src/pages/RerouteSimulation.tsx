import { useState, useEffect, useRef } from "react";
import { useSpillState } from "../context/SpillContext";
import MapView from "../components/MapView";
import { ViewModeProvider } from "../lib/viewMode";
import LayerToggles from "../components/LayerToggles";
import Timeline from "../components/Timeline";
import { reroute } from "../api/client";
import type { RerouteResponse } from "../api/types";

/** Great-circle distance in km, for estimating a plausible transit horizon. */
function haversineKm([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

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

  const [speed, setSpeed] = useState("15");
  const [clearance, setClearance] = useState("");
  const [buffer, setBuffer] = useState("2");
  const [routingError, setRoutingError] = useState<string | null>(null);
  const requestId = useRef(0);
  const inputsValid = Number(speed) > 0 && Number(speed) <= 60 && Number(buffer) >= 0 && Number(buffer) <= 168 && buffer !== "" && (clearance === "" || (Number(clearance) >= 0 && Number(clearance) <= 8760));

  useEffect(() => {
    const id = ++requestId.current;
    setRerouteResult(null);
    setRoutingError(null);
    setIsSimulating(false);
    if (!inputsValid) return;
    const timer = setTimeout(async () => {
      setIsSimulating(true);
      try {
        // Historical hindcast regions are not future obstacles. All current spills
        // remain included regardless of which spill is selected on the map.
        //
        // The forecast can span a much longer horizon (up to 72h) than any
        // plausible transit — a spill's position 3 days out is not a real
        // collision risk for a voyage that takes a few hours, but treating
        // the whole multi-day drift smear as one permanent obstacle forces
        // absurdly large detours around it. Cap obstacle cones to roughly
        // double the direct transit time (plus a margin for the detour
        // itself running longer), so only positions the ship could actually
        // reach in time are avoided.
        const speedKmh = Number(speed) * 1.852;
        const horizonHours = startPoint && endPoint && speedKmh > 0
          ? (haversineKm(startPoint, endPoint) / speedKmh) * 2 + 6
          : Infinity;
        const obstacles = [
          ...(detection?.slicks.map(s => s.polygon) ?? []),
          ...(forecast?.cone.filter(c => c.t_offset_hours <= horizonHours).map(c => c.polygon) ?? []),
        ];
        const res = await reroute({
          start_point: startPoint, end_point: endPoint, obstacles,
          // The forecast cone is a 90%-containment envelope, not the full
          // particle spread shown on the map — a tight 2km margin let routes
          // pass close enough to look like they were cutting through the
          // visible plume. Widened so a computed route stays clear of what's
          // actually rendered, not just the strict statistical boundary.
          safety_margin_km: 6, vessel_speed_knots: Number(speed),
          clearance_hours: clearance === "" ? null : Number(clearance),
          clearance_buffer_hours: Number(buffer),
        });
        if (requestId.current === id) setRerouteResult(res);
      } catch (error) {
        if (requestId.current === id) setRoutingError(error instanceof Error ? error.message : "Unable to calculate route. Try again.");
      } finally {
        if (requestId.current === id) setIsSimulating(false);
      }
    }, 250);
    return () => { clearTimeout(timer); requestId.current++; };
  }, [startPoint, endPoint, detection, forecast, speed, clearance, buffer, inputsValid]);

  return (
    <ViewModeProvider value="analyst">
      <div className="reroute-layout">
        <div className="reroute-map relative bg-ink-100">
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

          <div className="pointer-events-none absolute right-4 bottom-28 z-10">
            <div className="pointer-events-auto flex items-center bg-white/95 backdrop-blur-sm p-1 rounded shadow-md border border-ink-200">
              <button
                onClick={() => runHindcast()}
                disabled={!!drifting}
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-ink-50 hover:bg-blue-50 border border-ink-200 hover:border-blue-200 transition-colors text-sm text-ink-700 disabled:opacity-50 mr-1"
              >
                <div className={`w-2 h-2 rounded-full ${hindcast ? "bg-blue-500" : "bg-ink-300"}`} />
                {drifting === "hindcast" ? "Running..." : "Hindcast"}
              </button>

              <button
                onClick={() => runForecast()}
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
        <div className="reroute-panel bg-white z-20 flex flex-col">
          <div className="p-6 border-b border-ink-100">
            <h2 className="text-xl font-semibold text-ink-900 mb-1">Reroute Simulation</h2>
            <p className="text-sm text-ink-500">Compare arrival time with spill persistence before choosing a detour.</p>
          </div>

          <div className="reroute-panel-body p-5 space-y-6">
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-ink-900 uppercase tracking-wider">Instructions</h3>
              <p className="text-sm text-ink-700 bg-blue-50 border border-blue-100 rounded p-4">
                Click on the map to place a <strong>Start Point</strong>, then click again to place a <strong>Destination Point</strong>. 
                The route updates automatically. A third click starts a new voyage.
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
              <h3 className="text-sm font-semibold text-ink-900 uppercase tracking-wider">Spill map focus</h3>
              <div className="space-y-2">
                <p className="text-xs text-ink-600">Map focus only. Routing checks all detected spills.</p>
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

            <section className="space-y-4 border-t border-ink-200 pt-5">
              <h3 className="text-sm font-semibold text-ink-900">Arrival & clearance assumptions</h3>
              <label className="route-field">Vessel speed (knots)
                <input type="number" min="1" max="60" value={speed} onChange={e => setSpeed(e.target.value)} />
              </label>
              <label className="route-field">All regions clear in (hours from departure)
                <input type="number" min="0" max="8760" placeholder="Unknown — keep avoiding oil" value={clearance} onChange={e => setClearance(e.target.value)} />
              </label>
              <label className="route-field">Clearance uncertainty buffer (hours)
                <input type="number" min="0" max="168" value={buffer} onChange={e => setBuffer(e.target.value)} />
              </label>
              <p className="text-sm text-ink-600 leading-relaxed">Clearance is a simulation assumption for every supplied spill and forecast region, not a measured evaporation forecast. Leave it unknown unless you have a supported estimate. Thin oil alone does not establish clearance.</p>
              {!inputsValid && <p role="alert" className="text-sm text-red-600">Enter speed above 0 and up to 60 knots, clearance from 0–8760 hours, and a buffer from 0–168 hours.</p>}
              <button className="route-reset" onClick={() => { setStartPoint(null); setEndPoint(null); setRerouteResult(null); }}>Reset waypoints</button>
            </section>
            {routingError && <p role="alert" className="rounded-lg border border-red-200 p-4 text-sm text-red-600">{routingError}</p>}
            {rerouteResult && (
              <section aria-live="polite" className="space-y-4 border-t border-ink-200 pt-5">
                <div className="route-decision" data-decision={rerouteResult.decision}>
                  <h3 className="font-semibold text-ink-900">{({ reroute: "Reroute recommended", direct_clear: "No reroute: route avoids oil", direct_after_clearance: "No reroute under clearance assumption", pending: "Choose your waypoints", unavailable: "Route cannot be assessed" } as Record<string, string>)[rerouteResult.decision] ?? "Routing analysis"}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-700">{rerouteResult.reason}</p>
                </div>
                {startPoint && endPoint && !rerouteResult.error && <dl className="route-metrics">
                  <div><dt>Direct distance</dt><dd>{rerouteResult.distance_original_km.toFixed(1)} km</dd></div>
                  <div><dt>Selected distance</dt><dd>{rerouteResult.distance_rerouted_km.toFixed(1)} km</dd></div>
                  <div><dt>First hazard arrival</dt><dd>{rerouteResult.hazard_arrival_hours == null ? "No crossing" : `${rerouteResult.hazard_arrival_hours.toFixed(2)} h`}</dd></div>
                  <div><dt>Extra travel time</dt><dd>{rerouteResult.extra_time_hours.toFixed(2)} h</dd></div>
                  <div><dt>Extra distance</dt><dd>{(rerouteResult.distance_rerouted_km - rerouteResult.distance_original_km).toFixed(1)} km</dd></div>
                  <div><dt>Extra fuel estimate</dt><dd>{rerouteResult.extra_fuel_tons.toFixed(2)} t</dd></div>
                </dl>}
                <p className="text-xs leading-relaxed text-ink-600">Simulation only: constant speed, 2 km spill margin and fuel use of 1 t/h. Forecast regions are treated conservatively as a combined area. This planner does not check land, depth or shipping restrictions. Recheck spill observations before transit.</p>
              </section>
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
