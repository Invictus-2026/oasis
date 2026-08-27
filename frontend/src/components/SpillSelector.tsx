import React from "react";
import { useSpillState } from "../context/SpillContext";
import { Droplet, ArrowRight, Wind } from "lucide-react";
import { lonLat, km } from "../lib/format";

export default function SpillSelector({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  const { detection, setActiveSlickId, randomizeWind, mockWindDir } = useSpillState();

  if (!detection?.slicks?.length) {
    return (
      <div className="page-shell flex flex-col items-center justify-center p-8 h-full">
        <Droplet className="w-12 h-12 mb-4 opacity-50 text-ink-500" />
        <p className="text-ink-500 text-center">No oil spills detected or uploaded.</p>
      </div>
    );
  }

  return (
    <div className="page-shell flex flex-col h-full">
      <header className="page-header shrink-0">
        <h2 className="!mb-2">{title}</h2>
        <p className="text-sm">{description}</p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-3">
        {/* Wind direction control */}
        <button
          onClick={(e) => { e.stopPropagation(); randomizeWind(); }}
          className="w-full flex items-center justify-between gap-2 px-4 py-3 bg-ink-50 border border-ink-200 rounded-lg text-sm font-bold text-ink-700 hover:bg-blue-50 hover:border-blue-200 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Wind className="w-4 h-4 text-blue-500" />
            Randomize Wind &amp; Current
          </div>
          <span className="text-xs font-mono text-ink-400">{mockWindDir}°</span>
        </button>
        {/* "All Spills" Card */}
        <div
          className="bg-blue-600 text-white rounded-lg p-4 hover:bg-blue-700 transition-colors cursor-pointer flex items-center justify-between group"
          onClick={() => setActiveSlickId("all")}
        >
          <div>
            <h3 className="text-base font-bold">All Spills</h3>
            <span className="text-[10px] font-bold uppercase tracking-wider mt-1 inline-block text-blue-200">
              {detection.slicks.length} regions · {km(detection.slicks.reduce((s, slick) => s + (slick.area_km2 || 0), 0))}²
            </span>
          </div>
          <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white group-hover:bg-white group-hover:text-blue-600 transition-colors">
            <ArrowRight className="w-4 h-4" />
          </div>
        </div>

        {/* Individual spill cards */}
        {detection.slicks.map((slick, i) => {
          const isCustom = slick.id.startsWith("adhoc-");

          let center: [number, number] = [0, 0];
          if (slick.polygon.type === "Polygon") {
            const pts = slick.polygon.coordinates[0] as [number, number][];
            center = [
              pts.reduce((s, p) => s + p[0], 0) / pts.length,
              pts.reduce((s, p) => s + p[1], 0) / pts.length,
            ];
          }

          return (
            <div
              key={slick.id}
              className="bg-white border-2 border-ink-200 rounded-lg p-4 hover:border-blue-500 transition-all cursor-pointer flex items-center justify-between group"
              onClick={() => setActiveSlickId(slick.id)}
            >
              <div>
                <h3 className="font-bold text-ink-900 text-sm">
                  {isCustom ? `Custom Upload ${i}` : `Location ${i + 1}`}
                </h3>
                <div className="text-[11px] text-ink-500 font-mono mt-1">
                  {lonLat(center)}
                </div>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider mt-1.5 inline-block ${isCustom ? "bg-purple-100 text-purple-700" : "bg-blue-50 text-blue-600"}`}>
                  {isCustom ? "Sandbox" : "Verified"} · {km(slick.area_km2 || 0)}²
                </span>
              </div>
              <div className="w-8 h-8 rounded-full bg-ink-50 flex items-center justify-center text-ink-400 group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
                <ArrowRight className="w-4 h-4" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
