import { useState } from "react";
import type { LayerVisibility } from "./MapView";
import { ChevronDown, ChevronRight } from "lucide-react";
import { C } from "../lib/theme";

const LAYER_GROUPS = [
  {
    title: "SPILL",
    items: [
      { key: "slick", label: "Oil Slick", swatch: C.slick },
      { key: "sar", label: "Detection Mask", swatch: "#9fb0c8" },
    ],
  },
  {
    title: "DRIFT",
    items: [
      { key: "particles", label: "Hindcast", swatch: C.particle },
      { key: "cone", label: "Origin Region", swatch: C.coneLine, dashed: true },
      { key: "forecast", label: "Forecast", swatch: C.forecast, dashed: true },
    ],
  },
  {
    title: "VESSELS",
    items: [
      { key: "tracks", label: "AIS Tracks", swatch: C.vessel },
      { key: "lookalikes", label: "Candidates (Ruled out)", swatch: C.reject, dashed: true },
      // Gaps are implicit on selection in MapView, but we can list them here conceptually
    ],
  },
  {
    title: "ENVIRONMENT",
    items: [
      // These are currently placeholders until we add real environment data
      { key: "currents" as keyof LayerVisibility, label: "Currents", swatch: "#60a5fa" },
      { key: "wind" as keyof LayerVisibility, label: "Wind", swatch: "#9ca3af" },
    ],
  },
];

export default function LayerToggles({
  layers,
  onToggle,
}: {
  layers: LayerVisibility;
  onToggle: (k: keyof LayerVisibility) => void;
}) {
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    SPILL: true,
    DRIFT: true,
    VESSELS: true,
    ENVIRONMENT: true,
  });

  const toggleGroup = (title: string) => {
    setOpenGroups((prev) => ({ ...prev, [title]: !prev[title] }));
  };

  return (
    <div className="pointer-events-auto rounded-md border border-ink-200 bg-white shadow-sm w-56 overflow-hidden">
      <div className="bg-ink-50 px-3 py-2 border-b border-ink-200">
        <h3 className="text-xs font-bold text-ink-700 tracking-wider">LAYERS</h3>
      </div>
      
      <div className="max-h-96 overflow-y-auto">
        {LAYER_GROUPS.map((group) => (
          <div key={group.title} className="border-b border-ink-100 last:border-b-0">
            <button
              onClick={() => toggleGroup(group.title)}
              className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-ink-600 hover:bg-ink-50 transition-colors"
            >
              {group.title}
              {openGroups[group.title] ? (
                <ChevronDown className="w-3.5 h-3.5 text-ink-400" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-ink-400" />
              )}
            </button>
            
            {openGroups[group.title] && (
              <ul className="px-3 pb-2 space-y-1">
                {group.items.map((l) => {
                  const isActive = layers[l.key as keyof LayerVisibility];
                  return (
                    <li key={l.key}>
                      <button
                        onClick={() => {
                          if (l.key !== "currents" && l.key !== "wind") {
                             onToggle(l.key as keyof LayerVisibility);
                          }
                        }}
                        className={`flex w-full items-center gap-2 rounded-sm px-2 py-1 text-[11px] transition-colors duration-150 hover:bg-ink-50 ${
                          isActive ? "text-ink-900 font-medium" : "text-ink-400"
                        }`}
                      >
                        <div 
                          className="relative flex items-center justify-center w-3 h-3 rounded-sm border mr-1"
                          style={{ borderColor: isActive ? l.swatch : "var(--color-ink-300)" }}
                        >
                           {isActive && (
                              <div className="w-1.5 h-1.5 rounded-sm" style={{ backgroundColor: l.swatch }} />
                           )}
                        </div>
                        {l.label}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
