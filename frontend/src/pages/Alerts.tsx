import { useState } from "react";
import { useSpillState } from "../context/SpillContext";
import SpillSelector from "../components/SpillSelector";
import { lonLat, bearingLabel, km2 } from "../lib/format";
import {
  ShieldAlert, Anchor, Send, CheckCircle2, Loader2, Info,
  Radio, Ship, Megaphone,
} from "lucide-react";

interface Agency {
  id: string;
  name: string;
  type: string;
}

const AGENCIES: Agency[] = [
  { id: "uscg", name: "Coast Guard — Sector Command", type: "Coast Guard" },
  { id: "response", name: "Office of Spill Response & Restoration", type: "Environmental Response" },
  { id: "port", name: "Port Authority Vessel Traffic Service", type: "Port Authority" },
];

interface SentEntry {
  key: string;
  name: string;
  kind: "agency" | "vessel";
  sentAt: string;
}

function slickCenter(slick: { polygon: any }): [number, number] {
  if (slick.polygon?.type !== "Polygon") return [0, 0];
  const pts = slick.polygon.coordinates[0] as [number, number][];
  return [
    pts.reduce((s, p) => s + p[0], 0) / pts.length,
    pts.reduce((s, p) => s + p[1], 0) / pts.length,
  ];
}

export default function Alerts() {
  const { detection, activeSlickId, setActiveSlickId, attribution, mockWindDir, sendBroadcastAlert } = useSpillState();

  const [draftOverride, setDraftOverride] = useState<string | null>(null);
  const [sentLog, setSentLog] = useState<SentEntry[]>([]);
  const [sendingKey, setSendingKey] = useState<string | null>(null);

  if (!activeSlickId) {
    return (
      <SpillSelector
        title="Maritime Safety Alerts"
        description="Select an oil spill to notify Coast Guard stations and nearby vessels."
      />
    );
  }

  const slick = activeSlickId === "all"
    ? detection?.slicks[0]
    : detection?.slicks.find(s => s.id === activeSlickId);

  if (!slick) {
    return (
      <div className="page-shell flex flex-col items-center justify-center p-8 h-full text-center">
        <ShieldAlert className="w-12 h-12 mb-4 opacity-50 text-ink-500" />
        <p className="text-ink-500">That spill is no longer available.</p>
      </div>
    );
  }

  const center = slickCenter(slick);
  const areaKm2 = slick.geometry?.area_km2 ?? 0;
  const confidencePct = Math.round((slick.confidence ?? 0) * 100);

  const defaultMessage =
    `MARITIME SAFETY ALERT\n\n` +
    `An oil slick has been detected at approximately ${lonLat(center)}.\n` +
    `Estimated area: ${km2(areaKm2)}\n` +
    `Detection confidence: ${confidencePct}%\n` +
    `Prevailing wind: ${bearingLabel(mockWindDir)} (${mockWindDir}°)\n\n` +
    `Vessels transiting this area are advised to maintain a safe distance, avoid discharge or ballast operations nearby, and report any direct sightings to the nearest response agency.`;

  const message = draftOverride ?? defaultMessage;

  const sendAlert = (key: string, name: string, kind: "agency" | "vessel") => {
    if (sendingKey || sentLog.some(e => e.key === key)) return;
    setSendingKey(key);
    window.setTimeout(() => {
      setSendingKey(null);
      setSentLog(prev => [{ key, name, kind, sentAt: new Date().toISOString() }, ...prev]);
    }, 650);
  };

  const nearbyVessels = (attribution?.candidates ?? [])
    .slice()
    .sort((a, b) => a.closest_approach_km - b.closest_approach_km);

  const alertEveryone = () => {
    sendBroadcastAlert(message);
    const now = new Date().toISOString();
    const already = new Set(sentLog.map(e => e.key));
    const newEntries: SentEntry[] = [
      ...AGENCIES.filter(a => !already.has(a.id)).map(a => ({ key: a.id, name: a.name, kind: "agency" as const, sentAt: now })),
      ...nearbyVessels.filter(v => !already.has(v.mmsi)).map(v => ({ key: v.mmsi, name: v.name || v.mmsi, kind: "vessel" as const, sentAt: now })),
    ];
    if (newEntries.length) setSentLog(prev => [...newEntries, ...prev]);
  };

  return (
    <div className="page-shell flex flex-col h-full">
      <header className="page-header shrink-0 flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <button onClick={() => setActiveSlickId(null)} className="text-ink-400 hover:text-blue-600 transition-colors mr-1 text-sm font-bold">
              ← Back
            </button>
            <ShieldAlert className="w-5 h-5 text-blue-600" />
            <h2 className="!mb-0">Maritime Safety Alerts</h2>
          </div>
          <p className="text-sm">Notify response agencies and nearby vessels about this spill.</p>
        </div>
        <button
          onClick={alertEveryone}
          className="shrink-0 flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-white bg-red-600 hover:bg-red-700 active:scale-[0.98] shadow-sm transition-all"
        >
          <Megaphone className="w-4 h-4" /> Alert Everyone
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-5">

        <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
          <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <p className="text-[11px] leading-relaxed text-amber-800">
            <strong>Simulated dispatch.</strong> This demo has no live connection to any real Coast Guard, port authority,
            or vessel — sending an alert below only logs it locally for the purposes of this scenario.
          </p>
        </div>

        {/* Spill summary */}
        <div className="bg-white border border-ink-200 rounded-xl p-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-ink-400 mb-1">Location</div>
            <div className="text-sm font-mono font-bold text-ink-900">{lonLat(center)}</div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-ink-400 mb-1">Area</div>
            <div className="text-sm font-bold text-ink-900">{km2(areaKm2)}</div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-ink-400 mb-1">Confidence</div>
            <div className="text-sm font-bold text-ink-900">{confidencePct}%</div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-ink-400 mb-1">Wind</div>
            <div className="text-sm font-bold text-ink-900">{bearingLabel(mockWindDir)}</div>
          </div>
        </div>

        {/* Alert message */}
        <div>
          <label className="block text-xs font-bold text-ink-500 uppercase tracking-wider mb-2">Alert Message</label>
          <textarea
            value={message}
            onChange={(e) => setDraftOverride(e.target.value)}
            rows={6}
            className="w-full bg-ink-50 border border-ink-200 rounded-lg px-3 py-2.5 text-sm font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Response agencies */}
        <div>
          <h3 className="text-xs font-bold text-ink-500 uppercase tracking-wider mb-2 flex items-center gap-2">
            <Radio className="w-3.5 h-3.5" /> Coast Guard &amp; Response Agencies
          </h3>
          <div className="flex flex-col gap-2">
            {AGENCIES.map((a) => {
              const sent = sentLog.some(e => e.key === a.id);
              const sending = sendingKey === a.id;
              return (
                <div key={a.id} className="flex items-center justify-between gap-3 bg-white border border-ink-200 rounded-lg p-3">
                  <div>
                    <div className="text-sm font-bold text-ink-900">{a.name}</div>
                    <div className="text-[11px] text-ink-500">{a.type}</div>
                  </div>
                  <button
                    onClick={() => sendAlert(a.id, a.name, "agency")}
                    disabled={sending || sent}
                    className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold transition-colors ${
                      sent
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                    }`}
                  >
                    {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : sent ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Send className="w-3.5 h-3.5" />}
                    {sent ? "Alert Sent" : sending ? "Sending..." : "Send Alert"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Nearby vessels */}
        <div>
          <h3 className="text-xs font-bold text-ink-500 uppercase tracking-wider mb-2 flex items-center gap-2">
            <Ship className="w-3.5 h-3.5" /> Nearby Vessels
          </h3>
          {nearbyVessels.length === 0 ? (
            <div className="flex items-start gap-3 bg-ink-50 border border-ink-200 rounded-lg p-4">
              <Anchor className="w-4 h-4 text-ink-400 shrink-0 mt-0.5" />
              <p className="text-xs text-ink-500 leading-relaxed">
                Run Attribution for this spill first to identify vessels near the estimated origin — that list of
                candidates is what populates who can be notified here.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {nearbyVessels.map((v) => {
                const sent = sentLog.some(e => e.key === v.mmsi);
                const sending = sendingKey === v.mmsi;
                return (
                  <div key={v.mmsi} className="flex items-center justify-between gap-3 bg-white border border-ink-200 rounded-lg p-3">
                    <div>
                      <div className="text-sm font-bold text-ink-900">{v.name || "Unknown Vessel"}</div>
                      <div className="text-[11px] font-mono text-ink-500">MMSI {v.mmsi} · {v.closest_approach_km.toFixed(1)} km away</div>
                    </div>
                    <button
                      onClick={() => sendAlert(v.mmsi, v.name || v.mmsi, "vessel")}
                      disabled={sending || sent}
                      className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold transition-colors ${
                        sent
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                      }`}
                    >
                      {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : sent ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Send className="w-3.5 h-3.5" />}
                      {sent ? "Notified" : sending ? "Sending..." : "Notify Vessel"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Sent log */}
        {sentLog.length > 0 && (
          <div>
            <h3 className="text-xs font-bold text-ink-500 uppercase tracking-wider mb-2">Alert Log</h3>
            <div className="flex flex-col gap-1.5">
              {sentLog.map((e, i) => (
                <div key={i} className="flex items-center justify-between text-xs bg-ink-50 border border-ink-200 rounded-md px-3 py-2">
                  <span className="font-semibold text-ink-800">{e.name}</span>
                  <span className="font-mono text-ink-400">{new Date(e.sentAt).toLocaleTimeString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
