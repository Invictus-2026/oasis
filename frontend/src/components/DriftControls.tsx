import type { ForecastResponse, HindcastResponse } from "../api/types";
import { hours, km, lonLat, utc } from "../lib/format";
import { Button, Empty, Panel, Stat, Tag } from "./ui";

interface Props {
  hindcast: HindcastResponse | null;
  forecast: ForecastResponse | null;
  busy: "hindcast" | "forecast" | null;
  playing: boolean;
  frameIndex: number;
  frameCount: number;
  onHindcast: () => void;
  onForecast: () => void;
  onScrub: (i: number) => void;
  onTogglePlay: () => void;
}

export default function DriftControls({
  hindcast, forecast, busy, playing, frameIndex, frameCount,
  onHindcast, onForecast, onScrub, onTogglePlay,
}: Props) {
  const o = hindcast?.origin_estimate;
  const t = hindcast?.particles_timeline[Math.min(frameIndex, frameCount - 1)]?.t_offset_hours ?? 0;

  return (
    <Panel
      title="Stage 2 — Drift"
      subtitle="Bidirectional Lagrangian ensemble"
      right={
        <div className="flex gap-1.5">
          <Button tone="primary" onClick={onHindcast} busy={busy === "hindcast"}>
            Backtrack
          </Button>
          <Button onClick={onForecast} busy={busy === "forecast"} disabled={!hindcast}>
            Forecast 12h
          </Button>
        </div>
      }
    >
      {!hindcast ? (
        <Empty>Backtrack the slick to estimate where and when it was released.</Empty>
      ) : (
        <>
          <div className="mb-2 flex items-center gap-2">
            <Button onClick={onTogglePlay}>{playing ? "Pause" : "Replay"}</Button>
            <input
              type="range"
              min={0}
              max={Math.max(0, frameCount - 1)}
              value={frameIndex}
              onChange={(e) => onScrub(Number(e.target.value))}
              className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-ink-700 accent-cone-500"
            />
            <span className="tnum w-14 text-right text-[11px] text-mute-300">
              {t > 0 ? "+" : ""}{t.toFixed(0)} h
            </span>
          </div>

          {o && (
            <div className="rounded border border-cone-500/25 bg-cone-500/5 p-2">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-mute-400">
                  Estimated origin
                </span>
                {/* The cone, not the pin, is the actual answer. Say so. */}
                <Tag tone="mute">90% containment</Tag>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Stat label="Most likely point" value={lonLat(o.point)} />
                <Stat label="Uncertainty radius" value={km(o.uncertainty_radius_km)} />
                <Stat label="Release time" value={utc(o.time_utc)} />
                <Stat label="Release window"
                      value={`${hours(o.time_window_hours[0])} – ${hours(o.time_window_hours[1])} before imaging`}
                      hint="Inherited from the Stage 1 age estimate; it bounds how far back the ensemble is run." />
              </div>
              <p className="mt-2 text-[10px] leading-relaxed text-mute-400">
                The shaded region is where the release plausibly occurred, pooled over the whole
                age window from Stage 1 — the marker is only its densest point. The backtrack runs
                as far as that age window allows, so a less certain age gives a larger region.
              </p>
            </div>
          )}

          {forecast && (
            <div className="mt-2.5 border-t border-ink-700 pt-2.5">
              <div className="mb-1.5 text-[10px] uppercase tracking-wider text-mute-400">
                Forward forecast
              </div>
              {forecast.impact_flags.length === 0 ? (
                <Empty>No coastline impact within the forecast horizon.</Empty>
              ) : (
                <ul className="space-y-1">
                  {forecast.impact_flags.map((f) => (
                    <li key={f.name} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="text-mute-300">{f.name}</span>
                      <span className="tnum text-mute-400">
                        {km(f.distance_km)} · ETA {hours(f.eta_hours)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
