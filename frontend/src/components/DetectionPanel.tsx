import type { DetectResponse, DetectionMethod } from "../api/types";
import { bearingLabel, deg, hours, km, km2, pct } from "../lib/format";
import { Button, Empty, Panel, Stat, Tag } from "./ui";

interface Props {
  detection: DetectResponse | null;
  busy: boolean;
  method: DetectionMethod;
  unetAvailable: boolean;
  onRun: (method: DetectionMethod) => void;
}

export default function DetectionPanel({ detection, busy, method, unetAvailable, onRun }: Props) {
  const slick = detection?.slicks[0];

  return (
    <Panel
      title="Stage 1 — Detection"
      subtitle="Slick extraction and characterisation"
      right={
        <div className="flex gap-1.5">
          <Button onClick={() => onRun("classical")} busy={busy && method === "classical"}>
            Classical
          </Button>
          <Button
            tone="primary"
            disabled={!unetAvailable}
            busy={busy && method === "unet"}
            onClick={() => onRun("unet")}
          >
            U-Net
          </Button>
        </div>
      }
    >
      {!slick ? (
        <Empty>Run detection to extract the slick.</Empty>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-1.5">
            <Tag tone="warn">OIL SLICK</Tag>
            <Tag>{slick.method === "unet" ? "U-Net segmentation" : "Classical threshold"}</Tag>
            <Tag tone="mute">confidence {pct(slick.confidence)}</Tag>
          </div>

          <div className="grid grid-cols-3 gap-x-3 gap-y-3">
            <Stat label="Area" value={km2(slick.geometry.area_km2)} />
            <Stat label="Perimeter" value={km(slick.geometry.perimeter_km)} />
            <Stat label="Elongation" value={`${slick.geometry.elongation.toFixed(2)}:1`}
                  hint="Major:minor axis ratio of the fitted ellipse. High elongation is consistent with a moving discharge." />
            <Stat label="Orientation"
                  value={`${deg(slick.geometry.orientation_deg)} ${bearingLabel(slick.geometry.orientation_deg)}`} />
            <Stat label="Compactness" value={slick.geometry.compactness.toFixed(3)}
                  hint="4πA/P². Near 1 is circular, which is more typical of a low-wind patch than a vessel discharge." />
          </div>

          {slick.age && (
            <div className="mt-3 rounded border border-slick-500/25 bg-slick-500/5 p-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-mute-400">Estimated age</span>
                <Tag tone="mute">{slick.age.confidence} confidence</Tag>
              </div>
              <div className="tnum mt-0.5 text-sm text-slick-400">
                {hours(slick.age.min_hours)} – {hours(slick.age.max_hours)}
              </div>
              {/* The caveat is deliberately on screen, not buried in a tooltip. */}
              <p className="mt-1.5 text-[10px] leading-relaxed text-mute-400">{slick.age.method_note}</p>
            </div>
          )}

          {detection && detection.rejected_lookalikes.length > 0 && (
            <div className="mt-3 border-t border-ink-700 pt-2.5">
              <div className="mb-1.5 text-[10px] uppercase tracking-wider text-mute-400">
                Ruled out ({detection.rejected_lookalikes.length})
              </div>
              <ul className="space-y-1.5">
                {detection.rejected_lookalikes.map((r) => (
                  <li key={r.id} className="flex gap-2">
                    <Tag tone="mute">NOT OIL</Tag>
                    <p className="flex-1 text-[10px] leading-relaxed text-mute-400">{r.reason}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
