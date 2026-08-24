import type { DetectResponse, DetectionMethod } from "../api/types";
import { bearingLabel, deg, hours, km, km2, pct, ratio } from "../lib/format";
import { AnalystOnly } from "../lib/viewMode";
import { Button, Disclosure, Empty, Meter, Panel, Skeleton, Stat, Tag } from "./ui";

interface Props {
  detection: DetectResponse | null;
  busy: boolean;
  method: DetectionMethod;
  unetAvailable: boolean;
  onRun: (method: DetectionMethod) => void;
  onFocusLookalike: (id: string) => void;
}

export default function DetectionPanel({
  detection, busy, method, unetAvailable, onRun, onFocusLookalike,
}: Props) {
  const slick = detection?.slicks[0];

  return (
    <Panel
      title="Stage 1 — Detection"
      subtitle="Slick extraction and characterisation"
      provenance={detection?.provenance}
      right={
        <div className="flex gap-1.5">
          <Button onClick={() => onRun("classical")} busy={busy && method === "classical"}>
            Classical
          </Button>
          <Button
            tone="primary"
            disabled={!unetAvailable}
            busy={busy && method === "unet"}
            onClick={() => onRun("unet")}
          >
            U-Net
          </Button>
        </div>
      }
    >
      {!slick ? (
        busy ? <Skeleton rows={5} /> : <Empty>Run detection to extract the slick.</Empty>
      ) : (
        <>
          <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
            <Tag tone="warn">OIL SLICK</Tag>
            <Tag>{slick.method === "unet" ? "U-Net segmentation" : "Classical threshold"}</Tag>
            <Tag tone="mute">confidence {pct(slick.confidence)}</Tag>
          </div>

          {slick.evidence && (
            <AnalystOnly>
              <div className="mb-2.5 space-y-1.5 border-t border-ink-700 pt-2">
                <div className="text-[10px] uppercase tracking-wider text-mute-400">Evidence</div>
                <Meter label="Backscatter damping" value={slick.evidence.contrast} weight={slick.evidence.weight_contrast}
                       hint="Contrast vs local background. Mineral oil damps Bragg backscatter hard." />
                <Meter label="Speckle suppression" value={slick.evidence.variance} weight={slick.evidence.weight_variance}
                       hint="Inside/ambient speckle variance ratio, inverted. Oil is smoother, not just darker." />
                <Meter label="Elongated shape" value={slick.evidence.shape} weight={slick.evidence.weight_shape}
                       hint="Low compactness argues for a trail over a blob." />
                <Meter label="Edge sharpness" value={slick.evidence.edge} weight={slick.evidence.weight_edge}
                       hint="A discharge boundary is a sharp discontinuity; wind roughness fades." />
              </div>
            </AnalystOnly>
          )}

          <div className="grid grid-cols-3 gap-x-3 gap-y-2.5">
            <Stat label="Area" value={km2(slick.geometry.area_km2)} />
            <AnalystOnly>
              <Stat label="Perimeter" value={km(slick.geometry.perimeter_km)} />
              <Stat label="Elongation" value={ratio(slick.geometry.elongation)}
                    hint={`Major:minor axis ratio of the fitted ellipse (${slick.geometry.elongation.toFixed(2)}:1 exact). High elongation is consistent with a moving discharge.`} />
              <Stat label="Orientation"
                    value={`${deg(slick.geometry.orientation_deg)} ${bearingLabel(slick.geometry.orientation_deg)}`} />
              <Stat label="Compactness" value={slick.geometry.compactness.toFixed(3)}
                    hint="4πA/P². Near 1 is circular, which is more typical of a low-wind patch than a vessel discharge." />
            </AnalystOnly>
          </div>

          {slick.age && (
            <div className="mt-2.5 border-t border-ink-700 pt-2">
              <div className="flex items-baseline justify-between">
                <span className="text-[10px] uppercase tracking-wider text-mute-400">Estimated age</span>
                <Tag tone="mute">{slick.age.confidence} confidence</Tag>
              </div>
              <div className="tnum mt-0.5 text-sm text-slick-400">
                {hours(slick.age.min_hours)} – {hours(slick.age.max_hours)}
              </div>
              <AnalystOnly>
                <div className="mt-1.5 grid grid-cols-3 gap-x-3 gap-y-1.5">
                  <Stat label="Method" value="Okubo diffusion" />
                  {slick.age.diffusivity_m2s != null && (
                    <Stat label="Diffusivity" value={`${slick.age.diffusivity_m2s.toFixed(2)} m²/s`} />
                  )}
                  {slick.age.damping_db != null && (
                    <Stat label="Damping" value={`${slick.age.damping_db.toFixed(1)} dB`} />
                  )}
                </div>
                <div className="mt-1.5">
                  <Disclosure label="View reasoning">
                    {slick.age.method_note}
                  </Disclosure>
                </div>
              </AnalystOnly>
            </div>
          )}

          {detection && detection.rejected_lookalikes.length > 0 && (
            <div className="mt-2.5 border-t border-ink-700 pt-2">
              <div className="mb-1.5 text-[10px] uppercase tracking-wider text-mute-400">
                Ruled out ({detection.rejected_lookalikes.length})
              </div>
              <ul className="space-y-1.5">
                {detection.rejected_lookalikes.map((r) => (
                  <li key={r.id} className="flex items-start justify-between gap-2">
                    <div className="flex gap-2">
                      <Tag tone="mute">NOT OIL · {pct(r.confidence)}</Tag>
                      <AnalystOnly>
                        <p className="flex-1 text-[10px] leading-relaxed text-mute-400">{r.reason}</p>
                      </AnalystOnly>
                    </div>
                    <button
                      onClick={() => onFocusLookalike(r.id)}
                      className="shrink-0 text-[10px] text-mute-400 underline decoration-dotted underline-offset-2 hover:text-mute-200"
                    >
                      View on SAR
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
