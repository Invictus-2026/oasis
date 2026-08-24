import type { AttributeResponse, CandidateFlag } from "../api/types";
import { km } from "../lib/format";
import { Button, Empty, Panel, Skeleton, Tag } from "./ui";

const FLAG_TONE: Record<CandidateFlag, "alert" | "warn" | "neutral"> = {
  DARK_VESSEL: "alert",
  COURSE_DEVIATION: "warn",
  SLOW_STEAMING: "warn",
  CLOSEST_APPROACH: "neutral",
};

interface Props {
  attribution: AttributeResponse | null;
  busy: boolean;
  disabled: boolean;
  selectedMmsi: string | null;
  onRun: () => void;
  onSelect: (mmsi: string | null) => void;
}

export default function VesselTable({
  attribution, busy, disabled, selectedMmsi, onRun, onSelect,
}: Props) {
  return (
    <Panel
      title="Stage 3 — Attribution"
      subtitle={
        attribution
          ? `${attribution.total_vessels_in_region} vessels in region → ${attribution.after_filter} candidates`
          : "AIS correlation against the estimated origin"
      }
      provenance={attribution?.provenance}
      right={
        <Button tone="primary" onClick={onRun} busy={busy} disabled={disabled}>
          Correlate AIS
        </Button>
      }
    >
      {!attribution ? (
        busy ? (
          <Skeleton rows={3} />
        ) : (
          <Empty>
            {disabled
              ? "Run the backtrack first — candidates are screened against the estimated origin, not the observed slick."
              : "Screen AIS traffic against the estimated origin."}
          </Empty>
        )
      ) : (
        <>
          <ol className="space-y-1">
            {attribution.candidates.map((c) => {
              const selected = c.mmsi === selectedMmsi;
              return (
                <li key={c.mmsi}>
                  <button
                    onClick={() => onSelect(selected ? null : c.mmsi)}
                    className={`w-full rounded border px-2 py-1.5 text-left transition-colors duration-150 ${
                      selected
                        ? "border-cone-500/60 bg-cone-500/10 shadow-[0_0_12px_-4px_rgba(53,200,216,0.4)]"
                        : "border-ink-700 bg-ink-800/50 hover:border-ink-600 hover:bg-ink-800"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="tnum w-4 shrink-0 text-[11px] text-mute-400">{c.rank}</span>
                      <span className="flex-1 truncate text-xs text-mute-100">{c.name}</span>
                      <span className="tnum shrink-0 text-xs font-semibold text-mute-100">
                        {c.score.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 pl-6">
                      <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-800">
                        <div
                          className={`h-full rounded-full ${
                            c.flags.includes("DARK_VESSEL") ? "bg-alert-500" : "bg-vessel-500"
                          }`}
                          style={{ width: `${c.score * 100}%` }}
                        />
                      </div>
                      <span className="tnum shrink-0 text-[10px] text-mute-400">
                        {km(c.closest_approach_km)}
                      </span>
                    </div>
                    {c.flags.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1 pl-6">
                        {c.flags.map((f) => (
                          <Tag key={f} tone={FLAG_TONE[f]}>{f.replace(/_/g, " ")}</Tag>
                        ))}
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>

          {/* The framing line. It is on screen, not just in the pitch. */}
          <p className="mt-2.5 border-t border-ink-700 pt-2 text-[10px] leading-relaxed text-mute-400">
            Ranked by weighted spatio-temporal and behavioural correlation. This is a
            confidence-scored candidate list, <span className="text-mute-300">not an identification</span>,
            and it is not on its own evidence of responsibility.
          </p>
        </>
      )}
    </Panel>
  );
}
