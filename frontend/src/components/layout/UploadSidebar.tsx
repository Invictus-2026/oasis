import { useNavigate } from "react-router-dom";
import { useRef, useState } from "react";
import { UploadCloud, FileImage, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { useSpillState } from "../../context/SpillContext";
import { generateMockUploadDetection } from "../../lib/mockDetector";
import { buildAdHocDetection } from "../../lib/uploadProjection";
import type { DetectionMethod, UploadResponse } from "../../api/types";

const SAMPLE_IMAGES = [
  { name: "Sentinel-1 (500m)", path: "/sar-samples/sentinel_500.png", gsd: 10.0 },
  { name: "ALOS PALSAR (250m)", path: "/sar-samples/palsar_250.png", gsd: 12.5 },
];

function loadImageElement(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

/** Persistent, always-visible upload panel — a quick path to run a satellite
 *  image through the detection pipeline from any page, without navigating to
 *  Satellite Intelligence first. Mirrors the nav Sidebar's docking style. */
export default function UploadSidebar() {
  const { caseMeta, injectAdHocDetection, setActiveSlickId } = useSpillState();
  const navigate = useNavigate();

  const [file, setFile] = useState<File | null>(null);
  const [gsd, setGsd] = useState(10.0);
  const [method, setMethod] = useState<DetectionMethod>("classical");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadSample = async (sample: typeof SAMPLE_IMAGES[0]) => {
    setError(null);
    setDone(false);
    try {
      const res = await fetch(sample.path);
      const blob = await res.blob();
      const loadedFile = new File([blob], sample.name.replace(/[^a-zA-Z0-9]/g, "_") + ".png", { type: "image/png" });
      setGsd(sample.gsd);
      setFile(loadedFile);
    } catch (e: any) {
      setError("Failed to load sample: " + e.message);
    }
  };

  const runDetection = async () => {
    if (!file) return;
    setRunning(true);
    setError(null);
    setDone(false);

    try {
      const imgUrl = URL.createObjectURL(file);
      let data: UploadResponse | null = null;
      try {
        const form = new FormData();
        form.append("file", file);
        form.append("method", method);
        form.append("gsd_m", String(gsd));
        if (caseMeta) {
          form.append("lon", String(caseMeta.center[0]));
          form.append("lat", String(caseMeta.center[1]));
        }
        const res = await fetch("/api/detect/upload", { method: "POST", body: form });
        if (res.ok) data = await res.json();
      } catch { }

      if (!data) {
        const img = await loadImageElement(imgUrl);
        data = await generateMockUploadDetection(
          img,
          gsd,
          caseMeta ? [caseMeta.center[0], caseMeta.center[1]] : [-89.85125, 28.47625],
          method
        );
      }

      const built = buildAdHocDetection(data, { gsd, fileName: file.name, caseMeta, overlayImageUrl: imgUrl });
      if (!built) {
        setError("No georeferenced regions detected in this image.");
        return;
      }

      injectAdHocDetection(built.detection, built.overlay);
      setActiveSlickId(built.detection.slicks[0].id);
      setDone(true);
      navigate("/satellite");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <aside className="w-72 bg-white border-l border-ink-200 flex flex-col h-full shrink-0">
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        <h2 className="text-sm font-bold text-ink-900 flex items-center gap-2">
          <UploadCloud className="w-4 h-4 text-blue-600" /> Upload Satellite Image
        </h2>

        <label className="relative flex flex-col items-center justify-center w-full h-28 border-2 border-dashed border-ink-300 rounded-xl bg-ink-50 hover:bg-ink-100 hover:border-blue-400 transition-colors cursor-pointer group">
          <UploadCloud className="w-7 h-7 text-ink-400 group-hover:text-blue-500 mb-1.5 transition-colors" />
          <p className="text-xs text-ink-700 font-semibold text-center px-2">
            <span className="text-blue-600 group-hover:underline">Click to upload</span> or drag and drop
          </p>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept="image/*"
            onChange={(e) => {
              if (e.target.files?.[0]) {
                setFile(e.target.files[0]);
                setDone(false);
                setError(null);
              }
            }}
          />
        </label>

        {file && (
          <div className="text-xs font-semibold text-blue-700 bg-blue-50 p-2.5 rounded-lg border border-blue-200 flex items-center gap-2">
            <FileImage className="w-3.5 h-3.5 shrink-0" /> <span className="truncate">{file.name}</span>
          </div>
        )}

        <div>
          <span className="text-[10px] font-bold text-ink-400 uppercase tracking-widest">Or try a sample</span>
          <div className="flex flex-col gap-1.5 mt-2">
            {SAMPLE_IMAGES.map((s, i) => (
              <button
                key={i}
                onClick={() => loadSample(s)}
                className="text-xs font-semibold bg-ink-100 hover:bg-blue-100 hover:text-blue-700 text-ink-700 px-3 py-1.5 rounded-md transition-colors border border-ink-200 hover:border-blue-200 text-left"
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-[10px] font-bold text-ink-500 uppercase tracking-wider mb-1">Ground Sample Distance (m/px)</label>
          <input
            type="number"
            step="0.1"
            value={gsd}
            onChange={(e) => setGsd(parseFloat(e.target.value))}
            className="w-full bg-ink-50 border border-ink-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-[10px] font-bold text-ink-500 uppercase tracking-wider mb-1">Detector</label>
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value as DetectionMethod)}
            className="w-full bg-ink-50 border border-ink-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="classical">Classical Adaptive</option>
            <option value="unet">U-Net AI</option>
          </select>
        </div>

        {error && (
          <div className="bg-red-50 text-red-700 p-2.5 rounded-lg text-xs border border-red-200 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {error}
          </div>
        )}

        {done && !error && (
          <div className="bg-emerald-50 text-emerald-700 p-2.5 rounded-lg text-xs border border-emerald-200 flex items-center gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> Projected to map.
          </div>
        )}

        <button
          onClick={runDetection}
          disabled={!file || running}
          className="mt-auto bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2.5 rounded-lg text-sm font-bold flex items-center justify-center gap-2 shadow-sm transition-all active:scale-[0.98]"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />}
          {running ? "Analyzing..." : "Run Detection"}
        </button>
      </div>
    </aside>
  );
}
