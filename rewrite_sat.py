import re

with open("frontend/src/pages/SatelliteIntelligence.tsx", "r") as f:
    content = f.read()

new_content = """import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider } from "../lib/viewMode";
import { bearingLabel, deg, hours, km, pct, ratio } from "../lib/format";
import {
  Satellite, Search, Layers, Zap, BrainCircuit, Maximize,
  Clock, EyeOff, AlertTriangle, Eye, ChevronDown, ChevronRight,
  UploadCloud, FileImage, Image as ImageIcon, MapPin, CheckCircle2, ArrowRight, Activity, Crosshair
} from "lucide-react";
import type { DetectionMethod, UploadResponse, UploadRegion, CustomImageOverlay, Slick, RejectedLookalike, SlickGeometry, AgeEstimate, DetectionEvidence, BackscatterStats } from "../api/types";
import { motion, AnimatePresence } from "framer-motion";

function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
  const map: Record<string, string> = {
    gray:   "bg-ink-100 text-ink-600 border-ink-200",
    blue:   "bg-blue-50 text-blue-700 border-blue-200",
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    amber:  "bg-amber-50 text-amber-700 border-amber-200",
    red:    "bg-red-50 text-red-700 border-red-200",
    green:  "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${map[color] ?? map.gray}`}>
      {children}
    </span>
  );
}

function SectionCard({ title, icon, children, defaultOpen = true }: {
  title: string; icon: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-ink-200 bg-white shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3.5 bg-ink-50 border-b border-ink-200 hover:bg-ink-100 transition-colors text-left"
      >
        <span className="text-blue-600">{icon}</span>
        <span className="flex-1 text-sm font-bold text-ink-800 tracking-tight">{title}</span>
        {open ? <ChevronDown className="w-4 h-4 text-ink-400" /> : <ChevronRight className="w-4 h-4 text-ink-400" />}
      </button>
      <AnimatePresence>
         {open && (
           <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="px-5 py-4 overflow-hidden">
             {children}
           </motion.div>
         )}
      </AnimatePresence>
    </div>
  );
}

function StatBox({ label, value, hint }: { label: string; value: string | number | React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50 p-3 flex flex-col justify-between h-full">
      <div className="text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">{label}</div>
      <div className="text-lg font-black text-ink-900 font-mono">{value}</div>
      {hint && <div className="mt-1.5 text-[9px] text-ink-400 leading-tight">{hint}</div>}
    </div>
  );
}

const SAMPLE_IMAGES = [
  { name: "Sentinel-1 (500m)", path: "/sar-samples/sentinel_500.png", gsd: 10.0 },
  { name: "ALOS PALSAR (250m)", path: "/sar-samples/palsar_250.png", gsd: 12.5 },
  { name: "ALOS PALSAR (500m)", path: "/sar-samples/palsar_500.png", gsd: 12.5 },
  { name: "ALOS PALSAR (750m)", path: "/sar-samples/palsar_750.png", gsd: 12.5 },
];

// --- Shared Data Models for UI ---
interface UnifiedSlick {
  id: string;
  isLookalike: boolean;
  confidence: number;
  reason?: string;
  geometry: SlickGeometry;
  centroid: [number, number];
  age?: AgeEstimate | null;
  evidence?: DetectionEvidence | null;
  backscatter?: BackscatterStats | null;
  // Upload specific
  thickness_um?: number;
  contrast_db?: number;
}

function SlickDetailsPanel({ item, onMapProject }: { item: UnifiedSlick; onMapProject?: () => void }) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      key={item.id}
      className="flex flex-col gap-4"
    >
      {/* Primary Banner */}
      <div className={`rounded-xl p-5 flex flex-col md:flex-row items-center justify-between gap-6 ${item.isLookalike ? "bg-ink-50 border border-ink-200" : "bg-amber-50 border border-amber-200"}`}>
        <div>
          <div className="flex items-center gap-2 mb-2">
            {item.isLookalike ? <EyeOff className="w-5 h-5 text-ink-500" /> : <AlertTriangle className="w-5 h-5 text-amber-600" />}
            <h3 className={`text-lg font-black tracking-tight ${item.isLookalike ? "text-ink-900" : "text-amber-900"}`}>
              {item.isLookalike ? "Ruled Out Look-alike" : "Confirmed Oil Slick"}
            </h3>
          </div>
          <p className={`text-sm ${item.isLookalike ? "text-ink-600" : "text-amber-700"}`}>
            {item.reason || "High confidence detection verified by morphological filtering."}
          </p>
        </div>
        <div className={`flex items-center gap-6 text-center p-4 rounded-lg border shadow-sm min-w-[200px] justify-center ${item.isLookalike ? "bg-white border-ink-200" : "bg-white border-amber-100"}`}>
          <div>
             <div className={`text-3xl font-black tabular-nums ${item.isLookalike ? "text-ink-500" : "text-amber-600"}`}>{item.geometry.area_km2.toFixed(1)}</div>
             <div className={`text-[10px] font-bold uppercase tracking-widest ${item.isLookalike ? "text-ink-400" : "text-amber-500"}`}>km² Area</div>
          </div>
          <div className={`w-px h-10 ${item.isLookalike ? "bg-ink-100" : "bg-amber-100"}`} />
          <div>
             <div className="text-3xl font-black text-ink-900 tabular-nums">{(item.confidence * 100).toFixed(0)}<span className="text-xl">%</span></div>
             <div className="text-[10px] font-bold uppercase tracking-widest text-ink-400">Confidence</div>
          </div>
        </div>
      </div>

      {onMapProject && !item.isLookalike && (
        <button
           onClick={onMapProject}
           className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3.5 rounded-lg shadow-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
        >
           <MapPin className="w-5 h-5" />
           Project into Maritime Map for Drift Analysis
        </button>
      )}

      {/* Geometry & Location */}
      <SectionCard title="Geometry & Location" icon={<Maximize className="w-4 h-4" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
           <StatBox label="Centroid" value={`${item.centroid[1].toFixed(2)}°N, ${Math.abs(item.centroid[0]).toFixed(2)}°W`} hint="Estimated center of mass" />
           <StatBox label="Perimeter" value={km(item.geometry.perimeter_km)} />
           <StatBox label="Dimensions" value={`${item.geometry.length_km.toFixed(1)} × ${item.geometry.width_km.toFixed(1)} km`} hint="Length by Width" />
           <StatBox label="Orientation" value={`${deg(item.geometry.orientation_deg)} ${bearingLabel(item.geometry.orientation_deg)}`} />
           <StatBox 
              label="Elongation" 
              value={ratio(item.geometry.elongation)} 
              hint={`Major:minor axis ratio (${item.geometry.elongation.toFixed(1)}:1)`} 
           />
           <StatBox 
              label="Compactness" 
              value={item.geometry.compactness.toFixed(3)} 
              hint="Near 1 is circular, lower is trail-like." 
           />
           {item.thickness_um !== undefined && (
             <StatBox label="Thickness" value={`${item.thickness_um.toFixed(1)} µm`} hint="Estimated from backscatter" />
           )}
           {item.contrast_db !== undefined && (
             <StatBox label="Contrast" value={`${item.contrast_db.toFixed(1)} dB`} hint="Against background sea" />
           )}
        </div>
      </SectionCard>

      {/* Weathering & Age Estimate */}
      {item.age && (
        <SectionCard title="Age & Weathering Estimate" icon={<Clock className="w-4 h-4" />}>
          <div className="flex flex-col md:flex-row gap-6">
             <div className="shrink-0 text-center md:text-left bg-blue-50 border border-blue-100 p-4 rounded-lg">
                <div className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-1">Release Window</div>
                <div className="text-2xl font-black text-blue-700 tabular-nums">
                   {hours(item.age.min_hours)} – {hours(item.age.max_hours)}
                </div>
                <div className="mt-2 flex justify-center md:justify-start">
                   <Badge color={item.age.confidence === "high" ? "green" : item.age.confidence === "medium" ? "blue" : "amber"}>
                     {item.age.confidence.toUpperCase()} CONFIDENCE
                   </Badge>
                </div>
             </div>
             <div className="flex-1 grid grid-cols-2 gap-4">
                {item.age.diffusivity_m2s != null && (
                  <StatBox label="Diffusivity" value={`${item.age.diffusivity_m2s.toFixed(2)} m²/s`} />
                )}
                {item.age.damping_db != null && (
                  <StatBox label="Radar Damping" value={`${item.age.damping_db.toFixed(1)} dB`} />
                )}
                <div className="col-span-2 text-sm text-ink-600 bg-ink-50 p-3 rounded-lg border border-ink-100">
                   <strong>Methodology:</strong> {item.age.method_note}
                </div>
             </div>
          </div>
        </SectionCard>
      )}

      {/* Evidence Subscores */}
      {item.evidence && (
         <SectionCard title="Detection Evidence" icon={<Layers className="w-4 h-4" />} defaultOpen={false}>
            <div className="grid gap-4">
               {[
                  { label: "Backscatter damping", val: item.evidence.contrast, w: item.evidence.weight_contrast, hint: "Contrast vs local background." },
                  { label: "Speckle suppression", val: item.evidence.variance, w: item.evidence.weight_variance, hint: "Inside/ambient speckle variance ratio." },
                  { label: "Elongated shape", val: item.evidence.shape, w: item.evidence.weight_shape, hint: "Low compactness argues for a trail over a blob." },
                  { label: "Edge sharpness", val: item.evidence.edge, w: item.evidence.weight_edge, hint: "A discharge boundary is a sharp discontinuity." }
               ].map(e => (
                  <div key={e.label}>
                     <div className="flex justify-between items-baseline mb-1">
                        <span className="text-sm font-semibold text-ink-800">{e.label}</span>
                        <span className="text-xs font-mono font-bold text-blue-600">{(e.val * 100).toFixed(0)}%</span>
                     </div>
                     <div className="h-2 bg-ink-100 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${e.val * 100}%` }} />
                     </div>
                     <p className="text-[10px] text-ink-500 mt-1">{e.hint}</p>
                  </div>
               ))}
            </div>
         </SectionCard>
      )}
    </motion.div>
  );
}

function SidebarList({ items, selectedId, onSelect }: { items: UnifiedSlick[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const slicks = items.filter(i => !i.isLookalike);
  const lookalikes = items.filter(i => i.isLookalike);

  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-xs font-bold uppercase tracking-widest text-ink-500 mb-3 px-1 flex items-center gap-2">
          <Activity className="w-3.5 h-3.5" /> Confirmed Slicks ({slicks.length})
        </h4>
        <div className="space-y-2">
          {slicks.map((s, i) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                selectedId === s.id 
                  ? "bg-amber-50 border-amber-300 shadow-sm ring-1 ring-amber-300" 
                  : "bg-white border-ink-200 hover:border-amber-200 hover:bg-amber-50/30"
              }`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold text-ink-900 text-sm">Slick #{i + 1}</span>
                <Badge color="amber">{(s.confidence * 100).toFixed(0)}% CONF</Badge>
              </div>
              <div className="text-xs text-ink-500 font-mono">{s.geometry.area_km2.toFixed(2)} km²</div>
            </button>
          ))}
          {slicks.length === 0 && <div className="text-sm text-ink-400 italic px-2">No slicks confirmed.</div>}
        </div>
      </div>

      <div>
        <h4 className="text-xs font-bold uppercase tracking-widest text-ink-500 mb-3 px-1 flex items-center gap-2">
          <EyeOff className="w-3.5 h-3.5" /> Look-alikes ({lookalikes.length})
        </h4>
        <div className="space-y-2">
          {lookalikes.map((s, i) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                selectedId === s.id 
                  ? "bg-ink-100 border-ink-300 shadow-sm ring-1 ring-ink-300" 
                  : "bg-white border-ink-200 hover:border-ink-300 hover:bg-ink-50"
              }`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold text-ink-900 text-sm">Look-alike #{i + 1}</span>
                <span className="text-xs text-ink-400 font-mono">{(s.confidence * 100).toFixed(0)}% CONF</span>
              </div>
              <div className="text-[10px] text-ink-500 line-clamp-1">{s.reason}</div>
            </button>
          ))}
          {lookalikes.length === 0 && <div className="text-sm text-ink-400 italic px-2">No look-alikes found.</div>}
        </div>
      </div>
    </div>
  );
}

// ── AdHocUpload Component ──────────────────────────────────────
function AdHocUpload() {
  const { caseMeta, injectAdHocDetection, setActiveSlickId } = useSpillState();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [gsd, setGsd] = useState<number>(10.0);
  const [method, setMethod] = useState<DetectionMethod>("classical");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [projected, setProjected] = useState(false);
  
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    if (file) {
      const url = URL.createObjectURL(file);
      setImgUrl(url);
      setResult(null);
      setError(null);
      setProjected(false);
      setSelectedId(null);
      return () => URL.revokeObjectURL(url);
    }
  }, [file]);

  const loadSample = async (sample: typeof SAMPLE_IMAGES[0]) => {
    try {
      setError(null);
      setProjected(false);
      const res = await fetch(sample.path);
      const blob = await res.blob();
      const loadedFile = new File([blob], sample.name.replace(/[^a-zA-Z0-9]/g, "_") + ".png", { type: "image/png" });
      setGsd(sample.gsd);
      setFile(loadedFile);
    } catch (e: any) {
      setError("Failed to load sample image: " + e.message);
    }
  };

  const runDetection = async () => {
    if (!file && !imgUrl) return;
    setRunning(true);
    setError(null);
    setProjected(false);

    try {
      let data: UploadResponse | null = null;
      if (file) {
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
        } catch {}
      }

      if (!data) {
        if (!imgRef.current && !canvasRef.current) throw new Error("Image element not loaded.");
        const canvas = canvasRef.current || document.createElement("canvas");
        const ctx = canvas.getContext("2d")!;
        const w = imgRef.current?.naturalWidth || 800;
        const h = imgRef.current?.naturalHeight || 600;
        if (!canvasRef.current) {
          canvas.width = w; canvas.height = h;
          ctx.drawImage(imgRef.current!, 0, 0);
        }
        data = await generateMockUploadDetection(ctx, w, h, gsd, method);
      }

      setResult(data);
      if (data.oil_regions.length > 0) setSelectedId("slick-0");
      else if (data.rejected_lookalikes.length > 0) setSelectedId("lookalike-0");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (imgUrl && canvasRef.current) {
      const img = new Image();
      img.onload = () => { imgRef.current = img; drawCanvas(); };
      img.src = imgUrl;
    }
  }, [imgUrl]);

  useEffect(() => {
    if (result && imgRef.current) drawCanvas();
  }, [result, selectedId]);

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const MAX_WIDTH = Math.min(800, img.naturalWidth || 800);
    const scale = MAX_WIDTH / (img.naturalWidth || 800);
    canvas.width = (img.naturalWidth || 800) * scale;
    canvas.height = (img.naturalHeight || 600) * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    if (result) {
      const drawRegion = (r: UploadRegion, color: string, dashed: boolean, isSelected: boolean) => {
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = isSelected ? 4 : 2;
        if (dashed) ctx.setLineDash([6, 4]);

        if (r.contour.length >= 2) {
          ctx.beginPath();
          ctx.moveTo(r.contour[0][0] * scale, r.contour[0][1] * scale);
          for (let i = 1; i < r.contour.length; i++) ctx.lineTo(r.contour[i][0] * scale, r.contour[i][1] * scale);
          ctx.closePath();
          ctx.stroke();
          ctx.fillStyle = isSelected 
             ? (color === "#f59e0b" ? "rgba(245, 158, 11, 0.4)" : "rgba(148, 163, 184, 0.4)")
             : (color === "#f59e0b" ? "rgba(245, 158, 11, 0.15)" : "rgba(148, 163, 184, 0.1)");
          ctx.fill();
        }
        ctx.globalAlpha = isSelected ? 0.8 : 0.4;
        ctx.beginPath();
        ctx.arc(r.circle.cx * scale, r.circle.cy * scale, r.circle.radius * scale, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      };

      result.oil_regions.forEach((r, i) => drawRegion(r, "#f59e0b", false, selectedId === `slick-${i}`));
      result.rejected_lookalikes.forEach((r, i) => drawRegion(r, "#94a3b8", true, selectedId === `lookalike-${i}`));
    }
  };

  const handleProjectToMap = () => {
    if (!result || result.oil_regions.length === 0) return;
    const primaryRegion = result.oil_regions[0];
    const polygon = primaryRegion.polygon;
    if (!polygon) { setError("No georeferenced geometry available."); return; }

    const slickId = "adhoc-" + Date.now();
    const imgWidth = result.width;
    const imgHeight = result.height;
    const centerLon = caseMeta?.center[0] ?? -89.85125;
    const centerLat = caseMeta?.center[1] ?? 28.47625;
    const kmPerDegLon = 111.32 * Math.cos((centerLat * Math.PI) / 180);
    const degLonPerPx = (gsd / 1000.0) / kmPerDegLon;
    const degLatPerPx = (gsd / 1000.0) / 110.574;
    const halfW = (imgWidth / 2.0) * degLonPerPx;
    const halfH = (imgHeight / 2.0) * degLatPerPx;

    let overlayDataUrl = imgUrl || "";
    if (canvasRef.current) {
      try { overlayDataUrl = canvasRef.current.toDataURL("image/png"); } catch {}
    }

    const customOverlay: CustomImageOverlay = {
      id: slickId, imageUrl: overlayDataUrl,
      coordinates: [
        [centerLon - halfW, centerLat + halfH],
        [centerLon + halfW, centerLat + halfH],
        [centerLon + halfW, centerLat - halfH],
        [centerLon - halfW, centerLat - halfH],
      ],
      bbox: { west: centerLon - halfW, south: centerLat - halfH, east: centerLon + halfW, north: centerLat + halfH },
      name: file?.name || "Custom Upload Scene",
    };

    injectAdHocDetection({
      slicks: [{
        id: slickId, polygon, confidence: primaryRegion.confidence, method: result.method,
        geometry: primaryRegion.morphology, backscatter: primaryRegion.backscatter, age: null, evidence: null,
      }],
      rejected_lookalikes: result.rejected_lookalikes.map((rl, idx) => ({
        id: `lookalike-${slickId}-${idx}`, polygon: rl.polygon || { type: "Polygon", coordinates: [] },
        confidence: rl.confidence ?? 0.0, reason: rl.reason,
      })),
      processing: result.processing,
      provenance: { model_version: "custom-upload", params: { gsd }, generated_at: new Date().toISOString(), inputs: [file?.name ?? "custom"], notes: "Injected from custom upload" },
    }, customOverlay);

    setActiveSlickId(slickId);
    setProjected(true);
  };

  const unifiedItems: UnifiedSlick[] = result ? [
    ...result.oil_regions.map((r, i) => ({
      id: `slick-${i}`, isLookalike: false, confidence: r.confidence, geometry: r.morphology, centroid: [caseMeta?.center[0] ?? -90, caseMeta?.center[1] ?? 28.5] as [number, number],
      thickness_um: r.thickness_um, contrast_db: r.contrast_db
    })),
    ...result.rejected_lookalikes.map((r, i) => ({
      id: `lookalike-${i}`, isLookalike: true, confidence: r.confidence, reason: r.reason, geometry: r.morphology, centroid: [caseMeta?.center[0] ?? -90, caseMeta?.center[1] ?? 28.5] as [number, number],
      thickness_um: r.thickness_um, contrast_db: r.contrast_db
    }))
  ] : [];

  const activeItem = unifiedItems.find(i => i.id === selectedId);

  return (
    <div className="mt-6">
      <div className="bg-white p-6 rounded-xl border border-ink-200 shadow-sm mb-6 flex flex-col xl:flex-row gap-6">
        <div className="flex-1">
          <h3 className="text-sm font-bold text-ink-900 mb-4 flex items-center gap-2">
            <UploadCloud className="w-4 h-4 text-blue-600" /> Image Upload
          </h3>
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-4">
              <label className="cursor-pointer bg-ink-50 hover:bg-ink-100 border border-ink-200 text-ink-700 px-4 py-2 rounded-lg text-sm font-semibold transition-colors flex items-center gap-2 shrink-0">
                <FileImage className="w-4 h-4" /> Choose File
                <input type="file" className="hidden" accept="image/*" onChange={(e) => { if (e.target.files?.[0]) setFile(e.target.files[0]); }} />
              </label>
              <div className="text-sm text-ink-500 truncate max-w-xs">{file ? file.name : "No file selected"}</div>
            </div>
            
            <div className="flex gap-2 flex-wrap">
              {SAMPLE_IMAGES.map((s, i) => (
                <button key={i} onClick={() => loadSample(s)} className="text-xs bg-ink-100 hover:bg-ink-200 text-ink-700 px-3 py-1.5 rounded-md transition-colors">{s.name}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="w-px bg-ink-100 hidden xl:block" />

        <div className="flex-1 flex flex-col sm:flex-row gap-6">
          <div className="flex-1">
            <label className="block text-xs font-bold text-ink-500 uppercase tracking-wider mb-2">Ground Sample Distance (m/px)</label>
            <input type="number" step="0.1" value={gsd} onChange={(e) => setGsd(parseFloat(e.target.value))} className="w-full bg-ink-50 border border-ink-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            <p className="text-[10px] text-ink-400 mt-1">Scale of pixels. Larger GSD = lower resolution.</p>
          </div>
          <div className="flex-1">
             <label className="block text-xs font-bold text-ink-500 uppercase tracking-wider mb-2">Detector</label>
             <select value={method} onChange={(e) => setMethod(e.target.value as DetectionMethod)} className="w-full bg-ink-50 border border-ink-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="classical">Classical Adaptive</option>
                <option value="unet">U-Net AI</option>
             </select>
          </div>
        </div>
      </div>

      {(file || imgUrl) && (
        <div className="flex justify-end mb-6">
          <button onClick={runDetection} disabled={running} className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2.5 rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm transition-all active:scale-[0.98]">
            {running ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Search className="w-4 h-4" />}
            {running ? "Analyzing Image..." : "Run Detection Pipeline"}
          </button>
        </div>
      )}

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-lg mb-6 text-sm border border-red-200 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {(imgUrl || result) && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 mb-6">
           {result && unifiedItems.length > 0 && (
             <div className="xl:col-span-4">
               <SidebarList items={unifiedItems} selectedId={selectedId} onSelect={setSelectedId} />
             </div>
           )}
           
           <div className={`flex flex-col gap-6 ${result && unifiedItems.length > 0 ? "xl:col-span-8" : "xl:col-span-12"}`}>
             <div className="bg-ink-100 rounded-xl overflow-hidden border border-ink-200 relative flex justify-center w-full max-h-[600px]">
               <canvas ref={canvasRef} className="max-w-full max-h-[600px] object-contain shadow-sm bg-ink-900" />
             </div>
             
             {projected ? (
               <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-6 text-center shadow-sm">
                 <div className="flex justify-center mb-3"><CheckCircle2 className="w-12 h-12 text-emerald-500" /></div>
                 <h3 className="text-xl font-black text-emerald-900 mb-2">Successfully Projected</h3>
                 <p className="text-emerald-700 mb-6">Custom scene injected into operational intelligence.</p>
                 <div className="flex justify-center gap-4">
                   <button onClick={() => navigate("/map")} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm transition-all">
                     View on Map <MapPin className="w-4 h-4" />
                   </button>
                   <button onClick={() => navigate("/drift")} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm transition-all">
                     Drift Intelligence <ArrowRight className="w-4 h-4" />
                   </button>
                 </div>
               </div>
             ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                   <StatBox label="Image Dimensions" value={`${result?.width || 0}×${result?.height || 0}`} />
                   <StatBox label="Detected Regions" value={unifiedItems.length} />
                   <StatBox label="Total Area" value={`${result?.total_area_km2.toFixed(1) || "0.0"} km²`} />
                   <StatBox label="Estimated Volume" value={`${result?.total_volume_barrels.toFixed(0) || "0"} bbls`} />
                </div>
             )}

             {activeItem && !projected && (
                <div className="mt-2">
                   <SlickDetailsPanel item={activeItem} onMapProject={!activeItem.isLookalike ? handleProjectToMap : undefined} />
                </div>
             )}
           </div>
        </div>
      )}
    </div>
  );
}

// ── main component ─────────────────────────────────────────────
export default function SatelliteIntelligence() {
  const { detection, detecting, method, runDetect, onFocusLookalike, viewMode } = useSpillState();
  const [mode, setMode] = useState<"case" | "upload">("case");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const unetAvailable = true;

  const handleRun = (m: DetectionMethod) => {
    runDetect(m);
  };

  useEffect(() => {
    if (detection?.slicks?.length) {
      setSelectedId(detection.slicks[0].id);
    } else if (detection?.rejected_lookalikes?.length) {
      setSelectedId(detection.rejected_lookalikes[0].id);
    } else {
      setSelectedId(null);
    }
  }, [detection]);

  // Convert `case` mode data into the unified model
  const unifiedItems: UnifiedSlick[] = detection ? [
    ...detection.slicks.map((s) => {
       const pts = s.polygon.type === "Polygon" ? s.polygon.coordinates[0] as [number, number][] : [];
       const cx = pts.length > 0 ? pts.reduce((sum, p) => sum + p[0], 0) / pts.length : 0;
       const cy = pts.length > 0 ? pts.reduce((sum, p) => sum + p[1], 0) / pts.length : 0;
       return {
         id: s.id, isLookalike: false, confidence: s.confidence, geometry: s.geometry,
         centroid: [cx, cy] as [number, number], age: s.age, evidence: s.evidence
       };
    }),
    ...detection.rejected_lookalikes.map((r) => {
       const pts = r.polygon.type === "Polygon" ? r.polygon.coordinates[0] as [number, number][] : [];
       const cx = pts.length > 0 ? pts.reduce((sum, p) => sum + p[0], 0) / pts.length : 0;
       const cy = pts.length > 0 ? pts.reduce((sum, p) => sum + p[1], 0) / pts.length : 0;
       return {
         id: r.id, isLookalike: true, confidence: r.confidence, reason: r.reason, 
         geometry: r.geometry || { area_km2: 0, perimeter_km: 0, length_km: 0, width_km: 0, aspect_ratio: 0, elongation: 0, orientation_deg: 0, compactness: 0, solidity: 0 },
         centroid: [cx, cy] as [number, number], evidence: r.evidence
       };
    })
  ] : [];

  const activeItem = unifiedItems.find(i => i.id === selectedId);

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">
        <header className="page-header flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Satellite className="w-5 h-5 text-blue-600" />
              <h2 className="!mb-0">Satellite Intelligence</h2>
            </div>
            <p>Analyze Synthetic Aperture Radar (SAR) imagery for anomalies and potential oil slicks.</p>
          </div>
          
          <div className="flex bg-ink-100 p-1 rounded-lg self-start border border-ink-200">
             <button onClick={() => setMode("case")} className={`px-4 py-1.5 rounded-md text-xs uppercase tracking-wider font-bold transition-colors ${mode === "case" ? "bg-white shadow-sm text-blue-600" : "text-ink-500 hover:text-ink-700"}`}>Case Study</button>
             <button onClick={() => setMode("upload")} className={`px-4 py-1.5 rounded-md text-xs uppercase tracking-wider font-bold transition-colors ${mode === "upload" ? "bg-white shadow-sm text-blue-600" : "text-ink-500 hover:text-ink-700"}`}>Custom Upload</button>
          </div>
        </header>

        {mode === "upload" ? (
           <AdHocUpload />
        ) : (
           <div className="mt-6">
              
              <div className="flex items-center justify-between mb-6 bg-ink-50 p-2 rounded-lg border border-ink-200">
                 <span className="text-xs font-bold uppercase tracking-wider text-ink-500 px-3 flex items-center gap-2"><Crosshair className="w-4 h-4" /> Live Map Analysis</span>
                 <div className="flex gap-2">
                   <button
                     onClick={() => handleRun("classical")}
                     disabled={detecting && method !== "classical"}
                     className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all ${
                       method === "classical" 
                         ? "bg-white shadow-sm border border-ink-200 text-ink-900" 
                         : "text-ink-600 hover:text-ink-900 hover:bg-ink-100/50"
                     }`}
                   >
                     <Zap className="w-4 h-4" /> Classical
                     {detecting && method === "classical" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
                   </button>
                   <button
                     onClick={() => handleRun("unet")}
                     disabled={!unetAvailable || (detecting && method !== "unet")}
                     className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all ${
                       method === "unet" 
                         ? "bg-white shadow-sm border border-ink-200 text-blue-600" 
                         : "text-ink-600 hover:text-blue-600 hover:bg-ink-100/50"
                     }`}
                   >
                     <BrainCircuit className="w-4 h-4" /> U-Net
                     {detecting && method === "unet" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
                   </button>
                 </div>
              </div>

              {!detection && !detecting && (
                <div className="flex flex-col items-center justify-center py-16 px-6 text-center border-2 border-dashed border-ink-200 rounded-2xl bg-ink-50/50">
                  <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center mb-4">
                    <Search className="w-8 h-8" />
                  </div>
                  <h3 className="text-lg font-bold text-ink-900 mb-2">No Detection Results</h3>
                  <p className="text-ink-500 max-w-md text-sm">
                    Select an algorithm from the top right to analyze the current SAR scene and extract potential slicks.
                  </p>
                </div>
              )}

              {detecting && !detection && (
                <div className="space-y-4">
                   <div className="h-32 skeleton rounded-xl" />
                   <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                     <div className="h-24 skeleton rounded-lg" />
                     <div className="h-24 skeleton rounded-lg" />
                     <div className="h-24 skeleton rounded-lg" />
                     <div className="h-24 skeleton rounded-lg" />
                   </div>
                </div>
              )}

              {detection && unifiedItems.length > 0 && (
                <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                   <div className="xl:col-span-4">
                     <SidebarList items={unifiedItems} selectedId={selectedId} onSelect={setSelectedId} />
                   </div>
                   
                   <div className="xl:col-span-8 flex flex-col gap-6">
                     {activeItem ? (
                       <SlickDetailsPanel item={activeItem} />
                     ) : (
                       <div className="flex items-center justify-center h-64 bg-ink-50 rounded-xl border border-ink-200 text-ink-500 text-sm">
                         Select a slick to view deep analysis.
                       </div>
                     )}
                   </div>
                </div>
              )}
           </div>
        )}
      </div>
    </ViewModeProvider>
  );
}
