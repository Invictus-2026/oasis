import React, { useRef } from "react";
import { useSpillState } from "../context/SpillContext";
import { Play, Pause } from "lucide-react";

interface TrackProps {
  label: string;
  color: "blue" | "purple";
  frames: number;
  index: number;
  playing: boolean;
  disabled: boolean;
  onPlay: () => void;
  onScrub: (i: number) => void;
  /** direction: hindcast fills right-to-left, forecast left-to-right */
  reverse?: boolean;
}

function Track({ label, color, frames, index, playing, disabled, onPlay, onScrub, reverse }: TrackProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const pct = frames > 1 ? (index / (frames - 1)) * 100 : 0;
  const fillPct = reverse ? 100 - pct : pct;

  const colorMap = {
    blue: {
      label: "text-blue-600",
      thumb: "bg-blue-600 border-blue-700",
      fill: "bg-blue-500",
      track: "bg-blue-100",
      shadow: "shadow-blue-200",
      ring: "focus:ring-blue-300",
    },
    purple: {
      label: "text-purple-600",
      thumb: "bg-purple-600 border-purple-700",
      fill: "bg-purple-500",
      track: "bg-purple-100",
      shadow: "shadow-purple-200",
      ring: "focus:ring-purple-300",
    },
  }[color];

  function getPosFromEvent(e: React.MouseEvent | MouseEvent | React.TouchEvent | TouchEvent): number {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    const clientX = "touches" in e ? e.touches[0].clientX : (e as MouseEvent).clientX;
    const raw = (clientX - rect.left) / rect.width;
    const clamped = Math.max(0, Math.min(1, raw));
    return reverse ? 1 - clamped : clamped;
  }

  function scrubTo(ratio: number) {
    const newIndex = Math.round(ratio * Math.max(0, frames - 1));
    onScrub(newIndex);
  }

  function handleMouseDown(e: React.MouseEvent) {
    if (disabled) return;
    e.preventDefault();
    isDragging.current = true;
    scrubTo(getPosFromEvent(e));

    const onMove = (me: MouseEvent) => {
      if (!isDragging.current) return;
      scrubTo(getPosFromEvent(me));
    };
    const onUp = () => {
      isDragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function handleTouchStart(e: React.TouchEvent) {
    if (disabled) return;
    scrubTo(getPosFromEvent(e));
  }

  function handleTouchMove(e: React.TouchEvent) {
    if (disabled) return;
    scrubTo(getPosFromEvent(e));
  }

  return (
    <div className={`flex min-w-0 flex-col gap-1 flex-1 ${disabled ? "opacity-40" : ""}`}>
      <div className={`text-[10px] font-bold uppercase tracking-widest ${colorMap.label}`}>{label}</div>
      <div className="flex items-center gap-2">
        {/* Play button */}
        <button
          onClick={onPlay}
          disabled={disabled || frames === 0}
          className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-all border
            ${disabled || frames === 0
              ? "bg-ink-100 border-ink-200 text-ink-400 cursor-not-allowed"
              : `bg-white border-ink-200 text-ink-700 hover:bg-ink-50 hover:border-ink-300 shadow-sm`
            }`}
        >
          {playing
            ? <Pause className="w-3.5 h-3.5 fill-current" />
            : <Play className="w-3.5 h-3.5 fill-current ml-0.5" />
          }
        </button>

        {/* Scrubber track */}
        <div
          ref={trackRef}
          className={`relative flex-1 h-5 cursor-pointer select-none ${disabled || frames === 0 ? "cursor-not-allowed" : ""}`}
          onMouseDown={handleMouseDown}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
        >
          {/* Background */}
          <div className={`absolute inset-y-0 my-auto h-2 w-full rounded-full ${colorMap.track} border border-ink-200`} />

          {/* Fill */}
          <div
            className={`absolute inset-y-0 my-auto h-2 rounded-full ${colorMap.fill} transition-none`}
            style={reverse
              ? { left: `${100 - fillPct}%`, right: 0 }
              : { left: 0, width: `${fillPct}%` }
            }
          />

          {/* Tick marks */}
          {[25, 50, 75].map(t => (
            <div key={t} className="absolute top-1/2 -translate-y-1/2 h-2.5 w-px bg-ink-300/60" style={{ left: `${t}%` }} />
          ))}

          {/* Draggable Thumb */}
          <div
            className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 rounded-full border-2 shadow-md transition-none ${colorMap.thumb} ${colorMap.shadow}`}
            style={{ left: `${pct}%` }}
          />
        </div>

        {/* Frame label */}
        <span className="w-10 text-right text-[10px] font-mono text-ink-500 tabular-nums shrink-0">
          {frames > 0 ? `${index + 1}/${frames}` : "—"}
        </span>
      </div>
    </div>
  );
}

export default function Timeline() {
  const {
    hindcast, forecast,
    hindcastIndex, forecastIndex,
    hindcastPlaying, forecastPlaying,
    setHindcastPlaying, setForecastPlaying,
    setHindcastIndex, setForecastIndex,
    drifting,
  } = useSpillState();

  if (!hindcast && !forecast) return null;

  const hindcastFrames = hindcast?.particles_timeline.length ?? 0;
  const forecastFrames = forecast?.particles_timeline.length ?? 0;

  // Span labels come from the run itself — the fixtures backtrack 30 h and
  // forecast 9 h, and a live run may use a different window again.
  const span = (ts: number[] | undefined) =>
    ts && ts.length ? Math.round(Math.max(...ts.map(Math.abs))) : 0;
  const hindcastSpan = -span(hindcast?.particles_timeline.map(f => f.t_offset_hours));
  const forecastSpan = span(forecast?.particles_timeline.map(f => f.t_offset_hours));

  const toggleHindcast = () => {
    if (!hindcastPlaying && hindcastIndex >= hindcastFrames - 1) setHindcastIndex(0);
    setHindcastPlaying(p => !p);
  };
  const toggleForecast = () => {
    if (!forecastPlaying && forecastIndex >= forecastFrames - 1) setForecastIndex(0);
    setForecastPlaying(p => !p);
  };

  const scrubHindcast = (i: number) => { setHindcastPlaying(false); setHindcastIndex(i); };
  const scrubForecast = (i: number) => { setForecastPlaying(false); setForecastIndex(i); };

  return (
    <div className="pointer-events-auto w-full max-w-4xl mx-auto rounded-xl border border-ink-200 bg-white/95 shadow-xl backdrop-blur-md px-5 py-4 flex flex-col gap-3">
      {/* Header labels */}
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-black uppercase tracking-widest text-blue-600">Hindcast ({hindcastSpan}h)</span>
        <div className="flex items-center gap-1.5">
          <div className="h-px w-12 bg-ink-200" />
          <span className="text-[11px] font-black uppercase tracking-widest text-ink-800">Det. 0h</span>
          <div className="h-px w-12 bg-ink-200" />
        </div>
        <span className="text-[11px] font-black uppercase tracking-widest text-purple-600">Forecast (+{forecastSpan}h)</span>
      </div>

      {/* Two tracks */}
      <div className="flex flex-wrap items-start gap-4">
        <Track
          label="Backtrack"
          color="blue"
          frames={hindcastFrames}
          index={hindcastIndex}
          playing={hindcastPlaying}
          disabled={!hindcast || !!drifting}
          onPlay={toggleHindcast}
          onScrub={scrubHindcast}
        />

        {/* Center divider */}
        <div className="flex flex-col items-center gap-0.5 pt-5 shrink-0">
          <div className="w-0.5 h-3 bg-ink-300 rounded-full" />
          <div className="w-1.5 h-1.5 rounded-full bg-ink-400" />
          <div className="w-0.5 h-3 bg-ink-300 rounded-full" />
        </div>

        <Track
          label="Forecast"
          color="purple"
          frames={forecastFrames}
          index={forecastIndex}
          playing={forecastPlaying}
          disabled={!forecast || !!drifting}
          onPlay={toggleForecast}
          onScrub={scrubForecast}
        />
      </div>
    </div>
  );
}
