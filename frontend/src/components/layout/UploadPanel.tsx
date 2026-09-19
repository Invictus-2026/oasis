import { useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { UploadCloud, FileImage, AlertTriangle, Info, CheckCircle2, Loader2 } from "lucide-react";
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

/** Embedded upload section rendered inside the main nav Sidebar — a quick path
 *  to run a satellite image through the detection pipeline from any page,
 *  without navigating to Satellite Intelligence first. */
export default function UploadPanel() {
  const { caseMeta, injectAdHocDetection, setActiveSlickId } = useSpillState();
  const navigate = useNavigate();

  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [gsd, setGsd] = useState(10.0);
  const [method, setMethod] = useState<DetectionMethod>("classical");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) { setPreviewUrl(null); return; }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const loadSample = async (sample: typeof SAMPLE_IMAGES[0]) => {
    setError(null);
    setNotice(null);
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
    if (!file || !previewUrl) return;
    setRunning(true);
    setError(null);
    setNotice(null);
    setDone(false);

    try {
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
        const img = await loadImageElement(previewUrl);
        data = await generateMockUploadDetection(
          img,
          gsd,
          caseMeta ? [caseMeta.center[0], caseMeta.center[1]] : [-89.85125, 28.47625],
          method
        );
      }

      if (data.oil_regions.length === 0) {
        setNotice("No oil-like signature detected in this image. Try another image, or adjust GSD/detector and run again.");
        return;
      }

      const built = buildAdHocDetection(data, { gsd, fileName: file.name, caseMeta, overlayImageUrl: previewUrl });
      if (!built) {
        setError("Detection succeeded but returned no georeferenced geometry.");
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
    <div className="flex flex-col gap-3">
        <h2 className="text-xs font-bold text-ink-500 uppercase tracking-widest flex items-center gap-2">
          <UploadCloud className="w-3.5 h-3.5 text-blue-600" /> Upload Satellite Image
        </h2>

        <label className="relative flex flex-col items-center justify-center w-full h-20 border-2 border-dashed border-ink-300 rounded-lg bg-ink-50 hover:bg-ink-100 hover:border-blue-400 transition-colors cursor-pointer group">
          <UploadCloud className="w-5 h-5 text-ink-400 group-hover:text-blue-500 mb-1 transition-colors" />
          <p className="text-[11px] text-ink-700 font-semibold text-center px-2 leading-tight">
            <span className="text-blue-600 group-hover:underline">Click to upload</span> or drag & drop
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
                setNotice(null);
              }
            }}
          />
        </label>

        {file && previewUrl && (
          <div className="rounded-lg border border-ink-200 overflow-hidden bg-ink-900">
            <img src={previewUrl} alt={file.name} className="w-full h-24 object-cover" />
          </div>
        )}

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

        {notice && (
          <div className="bg-amber-50 text-amber-700 p-2.5 rounded-lg text-xs border border-amber-200 flex items-start gap-2">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {notice}
          </div>
        )}

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
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg text-xs font-bold flex items-center justify-center gap-2 shadow-sm transition-all active:scale-[0.98]"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />}
          {running ? "Analyzing..." : "Run Detection"}
        </button>
    </div>
  );
}
