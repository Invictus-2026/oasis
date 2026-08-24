import type { AttributeResponse, CaseMeta, HindcastResponse } from "../api/types";
import { utc } from "../lib/format";
import { C } from "../lib/theme";

export type TimelineStage = "detection" | "drift" | "attribution" | "evidence";

interface Event {
  t: number; // epoch ms
  label: string;
  color: string;
  stage: TimelineStage;
}

interface Props {
  caseMeta: CaseMeta | null;
  hindcast: HindcastResponse | null;
  attribution: AttributeResponse | null;
  onSelectStage: (stage: TimelineStage) => void;
}

/** The real chronology INSIDE the case: release (backtracked), the vessel's
 *  closest approach, then the satellite pass that captured the scene. All
 *  three sit within the same ~day. Deliberately excludes "when this analysis
 *  was run" — that timestamp is whenever the demo happens to execute, weeks
 *  or months removed from the case, and would collapse this whole chronology
 *  onto one pixel if it shared the axis. Each dot only appears once its stage
 *  has actually produced a timestamp — the strip fills in as the pipeline
 *  runs, it isn't pre-drawn. */
export default function Timeline({ caseMeta, hindcast, attribution, onSelectStage }: Props) {
  const events: Event[] = [];

  if (hindcast) {
    events.push({
      t: new Date(hindcast.origin_estimate.time_utc).getTime(),
      label: "ORIGIN (EST.)", color: C.origin, stage: "drift",
    });
  }
  const topApproach = attribution?.candidates.find((c) => c.closest_approach_utc)?.closest_approach_utc;
  if (topApproach) {
    events.push({ t: new Date(topApproach).getTime(), label: "AIS CLOSEST APPROACH", color: C.vessel, stage: "attribution" });
  }
  if (caseMeta) {
    events.push({ t: new Date(caseMeta.acquired_at).getTime(), label: "SAR CAPTURE", color: "#9fb0c8", stage: "detection" });
  }

  if (events.length < 2) return null;

  events.sort((a, b) => a.t - b.t);
  const tMin = events[0].t;
  const tMax = events[events.length - 1].t;
  const span = Math.max(tMax - tMin, 1);
  const pos = (t: number) => 6 + ((t - tMin) / span) * 88; // 6%–94%, room for labels at the ends

  return (
    <div className="pointer-events-auto rounded-sm border border-ink-700 bg-ink-950/70 px-3 pb-2.5 pt-3 backdrop-blur-sm">
      <div className="relative h-4">
        <div className="absolute left-[6%] right-[6%] top-1/2 h-px -translate-y-1/2 bg-ink-700" />
        {events.map((e) => (
          <button
            key={e.label}
            onClick={() => onSelectStage(e.stage)}
            className="group absolute top-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center"
            style={{ left: `${pos(e.t)}%` }}
          >
            <span
              className="h-2.5 w-2.5 rounded-full ring-2 ring-ink-950 transition-transform duration-150 group-hover:scale-125"
              style={{ background: e.color }}
            />
          </button>
        ))}
      </div>
      {/* Labels alternate rows so two close-together events never collide —
          real timestamps can land arbitrarily close, unlike an illustrative
          evenly-spaced mockup. */}
      <div className="relative mt-1 h-11">
        {events.map((e, i) => (
          <div
            key={e.label}
            className="absolute w-24 -translate-x-1/2 text-center"
            style={{ left: `${pos(e.t)}%`, top: i % 2 === 0 ? 0 : "1.1rem" }}
          >
            <div className="text-[9px] font-medium uppercase tracking-wider text-mute-400">{e.label}</div>
            <div className="tnum text-[9px] text-mute-400/70">{utc(new Date(e.t).toISOString()).slice(5, 16)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
