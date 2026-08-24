import type {
  AttributeResponse, CaseMeta, DetectResponse, ForecastResponse, HindcastResponse,
} from "../api/types";
import { isFixture } from "./ui";

type Status = "done" | "running" | "pending";

interface Stage {
  n: string;
  label: string;
  status: Status;
  result?: string;
  fixture?: boolean;
}

interface Props {
  caseMeta: CaseMeta | null;
  detection: DetectResponse | null;
  detecting: boolean;
  hindcast: HindcastResponse | null;
  forecast: ForecastResponse | null;
  drifting: "hindcast" | "forecast" | null;
  attribution: AttributeResponse | null;
  attributing: boolean;
}

const GLYPH: Record<Status, string> = { done: "✓", running: "●", pending: "○" };
const COLOR: Record<Status, string> = {
  done: "text-vessel-500", running: "text-cone-500", pending: "text-mute-400/50",
};

/** The pipeline as an operational status board, not a decorative stepper.
 *  Every status and result line comes straight out of app state — nothing
 *  here is a separate fabricated stage; "classification" is the same
 *  detection response as "dark object detection", just a different read of it. */
export default function Pipeline({
  caseMeta, detection, detecting, hindcast, forecast, drifting, attribution, attributing,
}: Props) {
  const candidateCount = detection ? detection.slicks.length + detection.rejected_lookalikes.length : undefined;

  const stages: Stage[] = [
    {
      n: "01", label: "SAR ingestion",
      status: caseMeta ? "done" : "pending",
      result: caseMeta?.scene_id,
    },
    {
      n: "02", label: "Dark object detection",
      status: detecting ? "running" : detection ? "done" : "pending",
      result: candidateCount !== undefined ? `${candidateCount} candidate region${candidateCount === 1 ? "" : "s"}` : undefined,
    },
    {
      n: "03", label: "Slick classification",
      status: detecting ? "running" : detection ? "done" : "pending",
      result: detection ? `${detection.slicks.length} oil, ${detection.rejected_lookalikes.length} rejected` : undefined,
    },
    {
      n: "04", label: "AIS matching",
      status: attributing ? "running" : attribution ? "done" : "pending",
      result: attribution ? `${attribution.after_filter} of ${attribution.total_vessels_in_region} vessels` : undefined,
      fixture: isFixture(attribution?.provenance),
    },
    {
      n: "05", label: "Backtrack",
      status: drifting === "hindcast" ? "running" : hindcast ? "done" : "pending",
      result: hindcast ? `origin ±${hindcast.origin_estimate.uncertainty_radius_km.toFixed(1)} km` : undefined,
    },
    {
      n: "06", label: "Forecast",
      status: drifting === "forecast" ? "running" : forecast ? "done" : "pending",
      result: forecast
        ? forecast.impact_flags.length > 0
          ? `${forecast.impact_flags.length} impact flag${forecast.impact_flags.length === 1 ? "" : "s"}`
          : "no coastline impact"
        : undefined,
    },
  ];

  return (
    <div className="rounded border border-ink-700 bg-ink-850/60 px-3 py-2">
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-mute-300">Pipeline</div>
      <ul>
        {stages.map((s) => (
          <li key={s.n} className="flex items-center gap-2 py-0.5 text-[11px]">
            <span className="tnum w-4 shrink-0 text-mute-400/60">{s.n}</span>
            <span className={`w-3.5 shrink-0 text-center ${COLOR[s.status]} ${s.status === "running" ? "animate-pulse" : ""}`}>
              {GLYPH[s.status]}
            </span>
            <span className={`flex-1 truncate ${s.status === "pending" ? "text-mute-400/60" : "text-mute-200"}`}>
              {s.label}
            </span>
            {s.result && (
              <span className="tnum shrink-0 text-mute-400">
                {s.result}
                {s.fixture && <span className="text-mute-400/50"> · fixture</span>}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
