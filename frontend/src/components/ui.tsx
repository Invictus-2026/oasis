import type { ReactNode } from "react";

import type { Provenance } from "../api/types";

/** True when a response came from the bundled fixtures rather than a live
 *  computation — fixtures.py suffixes model_version with "+fixture". Reading
 *  this instead of hand-tracking a flag means the tag can never drift out of
 *  sync with what actually produced the data on screen. */
export function isFixture(p?: Provenance | null): boolean {
  return !!p?.model_version?.endsWith("+fixture");
}

/** A console section, not a card. Flat, hairline-bordered, dense — the panel
 *  is a label for the rows inside it, not a decorative surface. */
export function Panel({ title, subtitle, children, right, provenance }: {
  title: string; subtitle?: string; children: ReactNode; right?: ReactNode; provenance?: Provenance | null;
}) {
  return (
    <section className="rounded border border-ink-200 bg-white dark:bg-ink-100 shadow-sm">
      <header className="flex items-baseline justify-between gap-3 border-b border-ink-100 px-3 py-1.5 bg-ink-50 rounded-t">
        <div className="flex items-baseline gap-2">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.14em] text-ink-700">{title}</h2>
          {isFixture(provenance) && (
            <span className="text-[9px] font-medium uppercase tracking-wider text-ink-400" title="Served from bundled fixtures, not a live computation">
              · fixture
            </span>
          )}
          {subtitle && <span className="text-[11px] text-ink-500">{subtitle}</span>}
        </div>
        {right}
      </header>
      <div className="px-3 py-2.5">{children}</div>
    </section>
  );
}

/** Collapsed by default: the number and its confidence lead, the method
 *  goes behind one click. `<details>` gives this for free — no state, no JS,
 *  keyboard- and screen-reader-accessible out of the box. */
export function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-ink-500 hover:text-ink-700">
        <svg viewBox="0 0 8 8" className="h-2 w-2 shrink-0 fill-current transition-transform duration-150 group-open:rotate-90">
          <path d="M1 0 L7 4 L1 8 Z" />
        </svg>
        {label}
      </summary>
      <div className="mt-1.5 border-l-2 border-ink-200 pl-2.5 text-[11px] leading-relaxed text-ink-600">
        {children}
      </div>
    </details>
  );
}

export function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div title={hint}>
      <div className="text-[10px] uppercase font-bold tracking-wider text-ink-400">{label}</div>
      <div className="tnum mt-0.5 text-[15px] leading-tight font-semibold text-ink-900">{value}</div>
    </div>
  );
}

export function Tag({ children, tone = "neutral" }: {
  children: ReactNode; tone?: "neutral" | "alert" | "warn" | "good" | "mute";
}) {
  const tones = {
    neutral: "border-ink-200 bg-ink-50 text-ink-700",
    alert: "border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400",
    warn: "border-orange-200 dark:border-orange-500/30 bg-orange-50 dark:bg-orange-500/10 text-orange-700 dark:text-orange-400",
    good: "border-green-200 dark:border-green-500/30 bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400",
    mute: "border-ink-200 bg-transparent text-ink-500",
  }[tone];
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wide transition-colors ${tones}`}>
      {children}
    </span>
  );
}

export function Button({ children, onClick, disabled, busy, tone = "default" }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; busy?: boolean;
  tone?: "default" | "primary";
}) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded border px-2.5 py-1.5 text-xs font-bold " +
    "transition-[background-color,border-color,box-shadow,transform] duration-150 ease-out-soft " +
    "active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100";
  const tones = {
    default: "border-ink-200 bg-white dark:bg-ink-100 text-ink-700 hover:border-ink-300 hover:bg-ink-50",
    primary: "border-blue-500 bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-500/25 shadow-sm",
  }[tone];
  return (
    <button className={`${base} ${tones}`} onClick={onClick} disabled={disabled || busy}>
      {busy && <span className="size-2.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

/** A labelled 0-1 bar. Used for score factors, where showing the weight
 *  alongside the value is what makes the composite auditable. */
export function Meter({ label, value, weight, hint, tone = "cone" }: {
  label: string; value: number; weight?: number; hint?: string; tone?: "cone" | "alert";
}) {
  const color = tone === "alert" ? "bg-red-500" : "bg-blue-500";
  return (
    <div title={hint}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold text-ink-700">{label}</span>
        <span className="tnum text-[11px] font-bold text-ink-900">
          {value.toFixed(2)}
          {weight !== undefined && <span className="text-ink-400"> × {weight.toFixed(2)}</span>}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-100 border border-ink-200">
        <div
          className={`h-full rounded-full ${color} transition-[width] duration-500 ease-out-soft`}
          style={{ width: `${value * 100}%` }}
        />
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-center gap-1.5 py-1 text-[11px] italic font-medium text-ink-500">
      <span className="h-1 w-1 shrink-0 rounded-full bg-ink-300" />
      {children}
    </p>
  );
}

/** Shimmering placeholder rows for a panel waiting on its first response.
 *  Shape hints at what is about to render (a label + value pair) so the
 *  layout does not jump when real content arrives. */
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2.5" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center justify-between gap-3">
          <span className="h-3 w-24 rounded bg-ink-100 animate-pulse" />
          <span className="h-3 flex-1 rounded bg-ink-100 animate-pulse" />
        </div>
      ))}
    </div>
  );
}
