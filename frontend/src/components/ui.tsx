import type { ReactNode } from "react";

export function Panel({ title, subtitle, children, right }: {
  title: string; subtitle?: string; children: ReactNode; right?: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-ink-700 bg-ink-850/80 backdrop-blur">
      <header className="flex items-baseline justify-between gap-3 border-b border-ink-700 px-3 py-2">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mute-300">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[11px] text-mute-400">{subtitle}</p>}
        </div>
        {right}
      </header>
      <div className="px-3 py-3">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div title={hint}>
      <div className="text-[10px] uppercase tracking-wider text-mute-400">{label}</div>
      <div className="tnum mt-0.5 text-sm text-mute-100">{value}</div>
    </div>
  );
}

export function Tag({ children, tone = "neutral" }: {
  children: ReactNode; tone?: "neutral" | "alert" | "warn" | "good" | "mute";
}) {
  const tones = {
    neutral: "border-ink-600 bg-ink-800 text-mute-300",
    alert: "border-alert-500/50 bg-alert-500/15 text-alert-500",
    warn: "border-slick-500/50 bg-slick-500/15 text-slick-400",
    good: "border-vessel-500/50 bg-vessel-500/15 text-vessel-500",
    mute: "border-ink-700 bg-transparent text-mute-400",
  }[tone];
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${tones}`}>
      {children}
    </span>
  );
}

export function Button({ children, onClick, disabled, busy, tone = "default" }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; busy?: boolean;
  tone?: "default" | "primary";
}) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded border px-2.5 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-40";
  const tones = {
    default: "border-ink-600 bg-ink-800 text-mute-100 hover:border-ink-600 hover:bg-ink-700",
    primary: "border-cone-500/60 bg-cone-500/15 text-[#8be9f0] hover:bg-cone-500/25",
  }[tone];
  return (
    <button className={`${base} ${tones}`} onClick={onClick} disabled={disabled || busy}>
      {busy && <span className="size-2.5 animate-spin rounded-full border border-current border-t-transparent" />}
      {children}
    </button>
  );
}

/** A labelled 0-1 bar. Used for score factors, where showing the weight
 *  alongside the value is what makes the composite auditable. */
export function Meter({ label, value, weight, hint, tone = "cone" }: {
  label: string; value: number; weight?: number; hint?: string; tone?: "cone" | "alert";
}) {
  const color = tone === "alert" ? "bg-alert-500" : "bg-cone-500";
  return (
    <div title={hint}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] text-mute-300">{label}</span>
        <span className="tnum text-[11px] text-mute-400">
          {value.toFixed(2)}
          {weight !== undefined && <span className="text-mute-400/60"> × {weight.toFixed(2)}</span>}
        </span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-ink-800">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value * 100}%` }} />
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-1 text-[11px] italic text-mute-400">{children}</p>;
}
