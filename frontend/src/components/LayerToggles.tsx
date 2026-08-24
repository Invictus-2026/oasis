import type { LayerVisibility } from "./MapView";
import { C } from "../lib/theme";

const LAYERS: { key: keyof LayerVisibility; label: string; swatch: string; dashed?: boolean }[] = [
  { key: "sar", label: "SAR scene", swatch: "#9fb0c8" },
  { key: "slick", label: "Oil slick", swatch: C.slick },
  { key: "lookalikes", label: "Ruled out", swatch: C.reject, dashed: true },
  { key: "cone", label: "Origin cone", swatch: C.coneLine, dashed: true },
  { key: "particles", label: "Particles", swatch: C.particle },
  { key: "forecast", label: "Forecast", swatch: C.forecast, dashed: true },
  { key: "tracks", label: "AIS tracks", swatch: C.vessel },
];

/** Doubles as the map legend, so colours are explained without a second
 *  element competing for space. */
export default function LayerToggles({ layers, onToggle }: {
  layers: LayerVisibility;
  onToggle: (k: keyof LayerVisibility) => void;
}) {
  return (
    <div className="pointer-events-auto rounded-sm border border-ink-700 bg-ink-900/85 p-2 backdrop-blur-sm">
      <div className="mb-1.5 text-[9px] uppercase tracking-[0.14em] text-mute-400">Layers</div>
      <ul className="space-y-0.5">
        {LAYERS.map((l) => (
          <li key={l.key}>
            <button
              onClick={() => onToggle(l.key)}
              className={`flex w-full items-center gap-2 rounded-sm px-1 py-0.5 text-[11px] transition-colors duration-150 hover:bg-ink-800 ${
                layers[l.key] ? "text-mute-100" : "text-mute-400/50"
              }`}
            >
              <span
                className="h-0.5 w-4 shrink-0 rounded-full transition-[background-color] duration-150"
                style={{
                  background: layers[l.key] ? l.swatch : "transparent",
                  border: layers[l.key] ? undefined : `1px ${l.dashed ? "dashed" : "solid"} ${l.swatch}55`,
                }}
              />
              {l.label}
            </button>
          </li>
        ))}
      </ul>

      {/* Not independently toggled — these follow the AIS tracks layer and
          only appear once a vessel is selected. Explained here so the map's
          own vocabulary is legible rather than guessed at. */}
      <div className="mt-1.5 space-y-0.5 border-t border-ink-700 pt-1.5">
        <div className="flex items-center gap-2 px-1 py-0.5 text-[11px] text-mute-400/70">
          <span className="h-0.5 w-4 shrink-0 rounded-full" style={{ background: "#ffffff" }} />
          AIS gap (selected)
        </div>
        <div className="flex items-center gap-2 px-1 py-0.5 text-[11px] text-mute-400/70">
          <span className="h-0.5 w-4 shrink-0 rounded-full" style={{ background: C.coneLine }} />
          Link to origin
        </div>
      </div>
    </div>
  );
}
