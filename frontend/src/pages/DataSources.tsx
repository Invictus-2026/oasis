import { Satellite, MapPin, Calendar, Radio, Ruler } from "lucide-react";

interface SampleScene {
  file: string;
  sensor: string;
  mode: string;
  acquired: string;
  region: string;
  resolution: string;
  polarization: string;
  note: string;
}

// Illustrative SAR quicklooks bundled from the training corpus (ml/data/images).
// These are sample tiles used to validate detection — not live case imagery.
const SAMPLES: SampleScene[] = [
  {
    file: "palsar_0.png",
    sensor: "ALOS PALSAR",
    mode: "L-band Stripmap",
    acquired: "2011-03-14",
    region: "Gulf of Mexico, offshore Louisiana",
    resolution: "10 m / px",
    polarization: "HH",
    note: "Dark elongated patch consistent with a surface slick; used as a positive training exemplar.",
  },
  {
    file: "palsar_105.png",
    sensor: "ALOS PALSAR",
    mode: "L-band Stripmap",
    acquired: "2010-11-02",
    region: "South Atlantic shipping lane",
    resolution: "10 m / px",
    polarization: "HH",
    note: "Low-backscatter streak with wind-sheltered edge, flagged during model validation.",
  },
  {
    file: "palsar_250.png",
    sensor: "ALOS PALSAR",
    mode: "L-band Stripmap",
    acquired: "2011-06-27",
    region: "Arabian Sea approach",
    resolution: "10 m / px",
    polarization: "HH",
    note: "Reference tile with a biogenic look-alike, retained for false-positive testing.",
  },
  {
    file: "palsar_500.png",
    sensor: "ALOS PALSAR",
    mode: "L-band Stripmap",
    acquired: "2011-09-19",
    region: "Bay of Bengal, coastal shelf",
    resolution: "10 m / px",
    polarization: "HH",
    note: "Vessel-adjacent dark slick used in attribution model calibration.",
  },
  {
    file: "palsar_750.png",
    sensor: "ALOS PALSAR",
    mode: "L-band Stripmap",
    acquired: "2012-01-08",
    region: "North Sea platform cluster",
    resolution: "10 m / px",
    polarization: "HH",
    note: "Multi-source slick pattern near fixed infrastructure, annotated for shape variety.",
  },
  {
    file: "sentinel_500.png",
    sensor: "Sentinel-1",
    mode: "C-band IW GRD",
    acquired: "2019-04-22",
    region: "Mediterranean Sea, shipping corridor",
    resolution: "10 m / px",
    polarization: "VV+VH",
    note: "Cross-sensor sample verifying detector generalisation beyond L-band imagery.",
  },
];

export default function DataSources() {
  return (
    <div className="page-shell">
      <header className="page-header">
        <h2>Data Sources</h2>
        <p>Sample SAR imagery used to train and validate the detection pipeline</p>
      </header>


      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {SAMPLES.map((s) => (
          <div key={s.file} className="content-card !p-0 overflow-hidden flex flex-col">
            <div className="relative bg-ink-900">
              <img
                src={`/sar-samples/${s.file}`}
                alt={`SAR quicklook — ${s.region}`}
                className="w-full aspect-square object-cover"
              />
              <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded border border-blue-200 bg-white/95 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-blue-700">
                <Satellite className="w-3 h-3" /> {s.sensor}
              </span>
              <span className="absolute top-2 right-2 rounded border border-amber-200 bg-amber-50/95 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-amber-700">
                SAMPLE
              </span>
            </div>

            <div className="p-3.5 flex-1 flex flex-col gap-2.5">
              <div className="text-sm font-bold text-ink-900">{s.region}</div>
              <p className="text-[11px] leading-relaxed text-ink-600">{s.note}</p>

              <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-ink-100 pt-2.5">
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-ink-400 shrink-0" />
                  <span className="text-[11px] font-mono text-ink-700">{s.acquired}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-ink-400 shrink-0" />
                  <span className="text-[11px] font-mono text-ink-700">{s.polarization}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Ruler className="w-3.5 h-3.5 text-ink-400 shrink-0" />
                  <span className="text-[11px] font-mono text-ink-700">{s.resolution}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-ink-400 shrink-0" />
                  <span className="text-[11px] font-mono text-ink-700 truncate">{s.mode}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
