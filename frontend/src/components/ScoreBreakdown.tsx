import type { AttributeResponse, VesselCandidate } from "../api/types";
import { SCORE_FACTORS } from "../api/types";
import { km, utc } from "../lib/format";
import { Empty, Meter, Panel, Stat, Tag } from "./ui";

interface Props {
  candidate: VesselCandidate | null;
  weights: AttributeResponse["weights"] | null;
}

export default function ScoreBreakdown({ candidate, weights }: Props) {
  return (
    <Panel title="Why this score" subtitle={candidate ? candidate.name : undefined}>
      {!candidate || !weights ? (
        <Empty>Select a candidate to see its score decomposition.</Empty>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-x-3 gap-y-2">
            <Stat label="MMSI" value={candidate.mmsi} />
            <Stat label="Type" value={candidate.vessel_type} />
            <Stat label="Closest approach" value={km(candidate.closest_approach_km)} />
            <Stat label="At"
                  value={candidate.closest_approach_utc ? utc(candidate.closest_approach_utc) : "—"} />
          </div>

          <div className="space-y-2">
            {SCORE_FACTORS.map((f) => (
              <Meter
                key={f.key}
                label={f.label}
                hint={f.hint}
                value={candidate.breakdown[f.key]}
                weight={weights[f.key]}
                tone={f.key === "ais_gap" && candidate.breakdown.ais_gap > 0.5 ? "alert" : "cone"}
              />
            ))}
          </div>

          <div className="mt-3 flex items-baseline justify-between border-t border-ink-700 pt-2">
            <span className="text-[10px] uppercase tracking-wider text-mute-400">Composite</span>
            <span className="tnum text-base font-semibold text-mute-100">
              {candidate.score.toFixed(3)}
            </span>
          </div>

          {candidate.gaps.length > 0 && (
            <div className="mt-2.5 rounded border border-alert-500/25 bg-alert-500/5 p-2">
              <div className="mb-1 flex items-center gap-1.5">
                <Tag tone="alert">AIS GAP</Tag>
                <span className="tnum text-[11px] text-mute-300">
                  {candidate.gaps[0].duration_minutes.toFixed(0)} min
                </span>
              </div>
              <div className="tnum text-[10px] text-mute-400">
                {utc(candidate.gaps[0].start_utc)} → {utc(candidate.gaps[0].end_utc)}
              </div>
              {/* Honesty about the base rate is what makes the flag credible. */}
              <p className="mt-1.5 text-[10px] leading-relaxed text-mute-400">
                Gaps are frequently benign — coverage holes and equipment faults are common. This is
                one weighted signal among five, never a conclusion on its own.
              </p>
            </div>
          )}

          <p className="mt-2.5 text-[11px] leading-relaxed text-mute-300">{candidate.narrative}</p>
        </>
      )}
    </Panel>
  );
}
