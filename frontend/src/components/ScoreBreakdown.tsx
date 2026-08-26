import type { AttributeResponse, Provenance, VesselCandidate } from "../api/types";
import { SCORE_FACTORS } from "../api/types";
import { km, utc } from "../lib/format";
import { AnalystOnly } from "../lib/viewMode";
import { Empty, Meter, Panel, Stat, Tag } from "./ui";

interface Props {
  candidate: VesselCandidate | null;
  weights: AttributeResponse["weights"] | null;
  provenance?: Provenance | null;
}

export default function ScoreBreakdown({ candidate, weights, provenance }: Props) {
  return (
    <Panel title="Why this score" subtitle={candidate ? candidate.name : undefined} provenance={provenance}>
      {!candidate || !weights ? (
        <Empty>Select a candidate to see its score decomposition.</Empty>
      ) : (
        <>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-ink-500">Composite score</span>
            <span className="tnum text-base font-semibold text-ink-900">
              {candidate.score.toFixed(3)}
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-600">{candidate.narrative}</p>

          <AnalystOnly>
            <div className="mb-3 mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-ink-200 pt-2.5">
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
          </AnalystOnly>

          {candidate.gaps.length > 0 && (
            <div className="mt-2.5 border-t border-red-200 dark:border-red-500/30 pt-2">
              <div className="mb-1 flex items-center gap-1.5">
                <Tag tone="alert">AIS GAP</Tag>
                <span className="tnum text-[11px] text-ink-600">
                  {candidate.gaps[0].duration_minutes.toFixed(0)} min
                </span>
              </div>
              <div className="tnum text-[10px] text-ink-500">
                {utc(candidate.gaps[0].start_utc)} → {utc(candidate.gaps[0].end_utc)}
              </div>
              {/* Honesty about the base rate is what makes the flag credible. */}
              <p className="mt-1.5 text-[10px] leading-relaxed text-ink-500">
                Gaps are frequently benign — coverage holes and equipment faults are common. This is
                one weighted signal among five, never a conclusion on its own.
              </p>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
