import type { CaseMeta, ProcessingStep, ReportContent } from "../api/types";
import { utc } from "../lib/format";
import { Button, Empty, Panel, Tag } from "./ui";

interface Props {
  caseMeta: CaseMeta | null;
  steps: ProcessingStep[];
  report: ReportContent | null;
  busy: boolean;
  disabled: boolean;
  onGenerate: () => void;
}

export default function EvidencePanel({
  caseMeta, steps, report, busy, disabled, onGenerate,
}: Props) {
  const total = steps.reduce((s, x) => s + x.duration_ms, 0);

  return (
    <Panel
      title="Evidence &amp; provenance"
      subtitle={caseMeta ? `${caseMeta.scene_id} · acquired ${utc(caseMeta.acquired_at)}` : undefined}
      right={
        <Button onClick={onGenerate} busy={busy} disabled={disabled}>
          Generate report
        </Button>
      }
    >
      {caseMeta && (
        <div className="mb-3">
          <div className="mb-1.5 text-[10px] uppercase tracking-wider text-mute-400">Data sources</div>
          <ul className="space-y-1">
            {caseMeta.sources.map((s) => (
              <li key={s.name} className="flex items-start gap-1.5">
                {s.is_synthetic ? <Tag tone="warn">SYNTHETIC</Tag> : <Tag tone="mute">{s.kind.toUpperCase()}</Tag>}
                <span className="flex-1 text-[10px] leading-relaxed text-mute-400">
                  {s.name}
                  {s.licence && <span className="text-mute-400/60"> · {s.licence}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {steps.length > 0 && (
        <div className="mb-3">
          <div className="mb-1.5 flex items-baseline justify-between">
            <span className="text-[10px] uppercase tracking-wider text-mute-400">Processing chain</span>
            <span className="tnum text-[10px] text-mute-400">{total.toFixed(0)} ms</span>
          </div>
          <ul className="max-h-40 space-y-0.5 overflow-y-auto">
            {steps.map((s, i) => (
              <li key={`${s.name}-${i}`} className="flex items-baseline gap-2 text-[10px]">
                <span className="tnum w-6 shrink-0 text-mute-400/60">{i + 1}</span>
                <span className="flex-1 truncate text-mute-300" title={s.detail ?? undefined}>
                  {s.name}
                </span>
                <span className="tnum shrink-0 text-mute-400">{s.duration_ms.toFixed(0)} ms</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report ? (
        <div className="rounded border border-ink-700 bg-ink-800/50 p-2">
          <div className="mb-1.5 text-[10px] uppercase tracking-wider text-mute-400">
            Known limitations
          </div>
          <ul className="space-y-1.5">
            {report.limitations.map((l, i) => (
              <li key={i} className="flex gap-1.5 text-[10px] leading-relaxed text-mute-400">
                <span className="text-mute-400/50">·</span>
                <span>{l}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <Empty>Generate the report to see the full case file and its stated limitations.</Empty>
      )}
    </Panel>
  );
}
