import { useState, useRef, useEffect } from "react";
import { useSpillState } from "../context/SpillContext";
import { ViewModeProvider, AnalystOnly } from "../lib/viewMode";
import { bearingLabel, deg, hours, km, km2, pct, ratio } from "../lib/format";
import {
  Satellite, Search, Layers, Zap, BrainCircuit, Maximize, 
  Clock, EyeOff, AlertTriangle, Eye, ChevronDown, ChevronRight,
  UploadCloud, FileImage, Image as ImageIcon
} from "lucide-react";
import type { DetectionMethod, UploadResponse, UploadRegion } from "../api/types";

// ── helpers ────────────────────────────────────────────────────
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
      {open && <div className="px-5 py-4">{children}</div>}
    </div>
  );
}

function StatBox({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50 p-3 flex flex-col justify-between">
      <div className="text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">{label}</div>
      <div className="text-lg font-black text-ink-900 font-mono">{value}</div>
      {hint && <div className="mt-1.5 text-[9px] text-ink-400 leading-tight">{hint}</div>}
    </div>
  );
}

// ── AdHocUpload Component ──────────────────────────────────────
function AdHocUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [gsd, setGsd] = useState<number>(10.0);
  const [method, setMethod] = useState<DetectionMethod>("classical");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    if (file) {
      const url = URL.createObjectURL(file);
      setImgUrl(url);
      setResult(null);
      setError(null);
      return () => URL.revokeObjectURL(url);
    }
  }, [file]);

  const runDetection = async () => {
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("method", method);
      form.append("gsd_m", String(gsd));
      
      const res = await fetch("/api/detect/upload", {
        method: "POST",
        body: form
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (imgUrl && canvasRef.current) {
      const img = new Image();
      img.onload = () => {
        imgRef.current = img;
        drawCanvas();
      };
      img.src = imgUrl;
    }
  }, [imgUrl]);

  useEffect(() => {
    if (result && imgRef.current) {
      drawCanvas();
    }
  }, [result]);

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    // Use a maximum width that matches the side panel while maintaining aspect ratio
    const MAX_WIDTH = Math.min(600, img.naturalWidth);
    const scale = MAX_WIDTH / img.naturalWidth;
    
    canvas.width = img.naturalWidth * scale;
    canvas.height = img.naturalHeight * scale;
    
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    if (result) {
      const drawRegion = (r: UploadRegion, color: string, dashed: boolean) => {
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        if (dashed) ctx.setLineDash([6, 4]);

        if (r.contour.length >= 2) {
          ctx.beginPath();
          ctx.moveTo(r.contour[0][0] * scale, r.contour[0][1] * scale);
          for (let i = 1; i < r.contour.length; i++) {
            ctx.lineTo(r.contour[i][0] * scale, r.contour[i][1] * scale);
          }
          ctx.closePath();
          ctx.stroke();
        }

        ctx.globalAlpha = 0.55;
        ctx.beginPath();
        ctx.arc(r.circle.cx * scale, r.circle.cy * scale, r.circle.radius * scale, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      };

      result.oil_regions.forEach(r => drawRegion(r, "#f59e0b", false)); // amber-500
      result.rejected_lookalikes.forEach(r => drawRegion(r, "#94a3b8", true)); // ink-400
    }
  };

  return (
    <div className="mt-6 flex flex-col gap-6">
      
      {/* Upload Controls */}
      <div className="bg-white rounded-xl border border-ink-200 shadow-sm p-5">
         <div className="flex flex-col gap-4">
            
            <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-ink-200 rounded-lg cursor-pointer bg-ink-50 hover:bg-ink-100 transition-colors">
               <div className="flex flex-col items-center justify-center pt-5 pb-6 text-center">
                  <UploadCloud className="w-8 h-8 mb-2 text-ink-500" />
                  <p className="mb-1 text-sm font-semibold text-ink-700">Click to upload SAR Image</p>
                  <p className="text-xs text-ink-500">PNG, JPG up to 10MB</p>
               </div>
               <input 
                  type="file" 
                  className="hidden" 
                  accept="image/*"
                  onChange={e => e.target.files && setFile(e.target.files[0])}
               />
            </label>

            {file && (
               <div className="flex items-center gap-3 bg-blue-50 border border-blue-100 p-3 rounded-lg text-blue-800 text-sm">
                  <FileImage className="w-5 h-5 text-blue-500 shrink-0" />
                  <span className="font-mono truncate">{file.name}</span>
               </div>
            )}

            <div className="grid grid-cols-2 gap-4 mt-2">
               <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">Detector Algorithm</label>
                  <select 
                     value={method} 
                     onChange={e => setMethod(e.target.value as DetectionMethod)}
                     className="w-full bg-ink-50 border border-ink-200 rounded-lg p-2.5 text-sm font-bold text-ink-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                     <option value="classical">Classical</option>
                     <option value="unet">U-Net</option>
                  </select>
               </div>
               <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-ink-500 mb-1">GSD (m/px)</label>
                  <input 
                     type="number"
                     step="0.1"
                     min="0.1"
                     value={gsd}
                     onChange={e => setGsd(parseFloat(e.target.value))}
                     className="w-full bg-ink-50 border border-ink-200 rounded-lg p-2.5 text-sm font-bold text-ink-800 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                  />
               </div>
            </div>

            <button
               onClick={runDetection}
               disabled={!file || running}
               className={`w-full mt-2 py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition-all ${
                  !file || running
                     ? "bg-ink-100 text-ink-400 cursor-not-allowed"
                     : "bg-blue-600 text-white hover:bg-blue-700 shadow-sm active:scale-[0.98]"
               }`}
            >
               {running ? (
                 <><span className="w-5 h-5 rounded-full border-2 border-white border-t-transparent animate-spin" /> Analyzing Image…</>
               ) : (
                 <><Search className="w-5 h-5" /> Run Detection</>
               )}
            </button>
            
            {error && (
               <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-3 mt-1">
                  <strong>Error:</strong> {error}
               </div>
            )}
         </div>
      </div>

      {/* Canvas View */}
      {imgUrl && (
         <div className="bg-ink-950 rounded-xl overflow-hidden shadow-inner border border-ink-800 flex justify-center p-4">
            <canvas ref={canvasRef} className="max-w-full h-auto bg-ink-900 rounded" />
         </div>
      )}

      {/* Results */}
      {result && (
         <div className="flex flex-col gap-4">
            
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 flex flex-col md:flex-row items-center justify-between gap-6">
               <div>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="w-5 h-5 text-amber-600" />
                    <h3 className="text-lg font-black text-amber-900 tracking-tight">
                       {result.oil_regions.length} Slick(s) Detected
                    </h3>
                  </div>
                  <p className="text-sm text-amber-700 leading-relaxed">
                     Ad-hoc upload analysis using {result.method === "unet" ? "U-Net" : "classical thresholding"} at {result.gsd_m} m/px.
                  </p>
               </div>
               <div className="flex items-center gap-6 text-center bg-white p-4 rounded-lg border border-amber-100 shadow-sm min-w-[200px] justify-center">
                  <div>
                     <div className="text-3xl font-black text-amber-600 tabular-nums">{result.total_area_km2.toFixed(2)}</div>
                     <div className="text-[10px] font-bold uppercase tracking-widest text-amber-500">Total Area (km²)</div>
                  </div>
               </div>
            </div>

            <SectionCard title="Detection Metrics" icon={<Layers className="w-4 h-4" />}>
               <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                  <StatBox label="Image Dimensions" value={`${result.width}×${result.height}`} />
                  <StatBox label="Volume (Liters)" value={result.total_volume_liters.toLocaleString()} />
                  <StatBox label="Volume (Barrels)" value={result.total_volume_barrels.toFixed(1)} />
               </div>
               <div className="bg-ink-50 p-4 rounded-lg border border-ink-200">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-ink-500 mb-2">Methodology Disclaimer</div>
                  <p className="text-xs text-ink-600 leading-relaxed">{result.notes}</p>
               </div>
            </SectionCard>

            {result.oil_regions.length > 0 && (
               <SectionCard title={`Confirmed Regions (${result.oil_regions.length})`} icon={<ImageIcon className="w-4 h-4" />}>
                  <div className="space-y-3">
                    {result.oil_regions.map((r, i) => (
                       <div key={i} className="flex gap-4 p-4 rounded-lg border border-ink-200 bg-ink-50">
                          <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center font-bold text-xs shrink-0">#{i + 1}</div>
                          <div className="flex-1 grid grid-cols-2 gap-2">
                             <div className="col-span-2 text-sm font-semibold text-ink-800 mb-1">{r.reason}</div>
                             <div className="text-xs"><span className="text-ink-500">Area:</span> <span className="font-mono font-bold">{r.area_km2.toFixed(3)} km²</span></div>
                             <div className="text-xs"><span className="text-ink-500">Conf:</span> <span className="font-mono font-bold">{(r.confidence * 100).toFixed(0)}%</span></div>
                             <div className="text-xs"><span className="text-ink-500">Thickness:</span> <span className="font-mono font-bold">{r.thickness_um.toFixed(1)} µm</span></div>
                             <div className="text-xs"><span className="text-ink-500">Contrast:</span> <span className="font-mono font-bold">{r.contrast_db.toFixed(1)} dB</span></div>
                          </div>
                       </div>
                    ))}
                  </div>
               </SectionCard>
            )}

            {result.rejected_lookalikes.length > 0 && (
               <SectionCard title={`Ruled Out Look-alikes (${result.rejected_lookalikes.length})`} icon={<EyeOff className="w-4 h-4" />} defaultOpen={false}>
                  <div className="space-y-3">
                    {result.rejected_lookalikes.map((r, i) => (
                       <div key={i} className="flex gap-4 p-4 rounded-lg border border-ink-200 bg-ink-50">
                          <div className="w-8 h-8 rounded-full bg-ink-200 text-ink-600 flex items-center justify-center font-bold text-xs shrink-0">#{i + 1}</div>
                          <div className="flex-1">
                             <div className="flex items-center gap-2 mb-1">
                                <Badge color="gray">NOT OIL</Badge>
                                <span className="text-xs font-mono text-ink-500">Conf: {(r.confidence * 100).toFixed(0)}%</span>
                             </div>
                             <p className="text-sm text-ink-700 leading-relaxed">{r.reason}</p>
                          </div>
                       </div>
                    ))}
                  </div>
               </SectionCard>
            )}

         </div>
      )}

    </div>
  );
}

// ── main component ─────────────────────────────────────────────
export default function SatelliteIntelligence() {
  const { detection, detecting, method, runDetect, onFocusLookalike, viewMode } = useSpillState();
  const [mode, setMode] = useState<"case" | "upload">("case");

  const slick = detection?.slicks[0];
  const unetAvailable = true;

  const handleRun = (m: DetectionMethod) => {
    runDetect(m);
  };

  return (
    <ViewModeProvider value={viewMode}>
      <div className="page-shell">
        
        {/* ── Page Header ── */}
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
                 <span className="text-xs font-bold uppercase tracking-wider text-ink-500 px-3">Live Map Analysis</span>
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
                     <Zap className="w-4 h-4" />
                     Classical
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
                     <BrainCircuit className="w-4 h-4" />
                     U-Net
                     {detecting && method === "unet" && <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin ml-1" />}
                   </button>
                 </div>
              </div>

              {!slick && !detecting && (
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

              {detecting && !slick && (
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

              {slick && (
                <div className="flex flex-col gap-4">
                  
                  {/* Primary Result Banner */}
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 flex flex-col md:flex-row items-center justify-between gap-6">
                     <div>
                        <div className="flex items-center gap-2 mb-2">
                          <AlertTriangle className="w-5 h-5 text-amber-600" />
                          <h3 className="text-lg font-black text-amber-900 tracking-tight">Confirmed Oil Slick</h3>
                        </div>
                        <p className="text-sm text-amber-700">
                          High confidence detection using {slick.method === "unet" ? "U-Net semantic segmentation" : "classical thresholding"}.
                        </p>
                     </div>
                     <div className="flex items-center gap-6 text-center bg-white p-4 rounded-lg border border-amber-100 shadow-sm min-w-[200px] justify-center">
                        <div>
                           <div className="text-3xl font-black text-amber-600 tabular-nums">{slick.geometry.area_km2.toFixed(1)}</div>
                           <div className="text-[10px] font-bold uppercase tracking-widest text-amber-500">km² Area</div>
                        </div>
                        <div className="w-px h-10 bg-amber-100" />
                        <div>
                           <div className="text-3xl font-black text-ink-900 tabular-nums">{(slick.confidence * 100).toFixed(0)}<span className="text-xl">%</span></div>
                           <div className="text-[10px] font-bold uppercase tracking-widest text-ink-400">Confidence</div>
                        </div>
                     </div>
                  </div>

                  {/* Geometry & Morphology */}
                  <SectionCard title="Geometry & Morphology" icon={<Maximize className="w-4 h-4" />}>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                       <StatBox label="Perimeter" value={km(slick.geometry.perimeter_km)} />
                       <StatBox label="Orientation" value={`${deg(slick.geometry.orientation_deg)} ${bearingLabel(slick.geometry.orientation_deg)}`} />
                       <StatBox 
                          label="Elongation" 
                          value={ratio(slick.geometry.elongation)} 
                          hint={`Major:minor axis ratio (${slick.geometry.elongation.toFixed(1)}:1)`} 
                       />
                       <StatBox 
                          label="Compactness" 
                          value={slick.geometry.compactness.toFixed(3)} 
                          hint="Near 1 is circular, lower is trail-like." 
                       />
                    </div>
                  </SectionCard>

                  {/* Weathering & Age Estimate */}
                  {slick.age && (
                    <SectionCard title="Age & Weathering Estimate" icon={<Clock className="w-4 h-4" />}>
                      <div className="flex flex-col md:flex-row gap-6">
                         <div className="shrink-0 text-center md:text-left bg-blue-50 border border-blue-100 p-4 rounded-lg">
                            <div className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-1">Release Window</div>
                            <div className="text-2xl font-black text-blue-700 tabular-nums">
                               {hours(slick.age.min_hours)} – {hours(slick.age.max_hours)}
                            </div>
                            <div className="mt-2 flex justify-center md:justify-start">
                               <Badge color={slick.age.confidence === "high" ? "green" : slick.age.confidence === "medium" ? "blue" : "amber"}>
                                 {slick.age.confidence.toUpperCase()} CONFIDENCE
                               </Badge>
                            </div>
                         </div>
                         <div className="flex-1 grid grid-cols-2 gap-4">
                            {slick.age.diffusivity_m2s != null && (
                              <StatBox label="Diffusivity" value={`${slick.age.diffusivity_m2s.toFixed(2)} m²/s`} />
                            )}
                            {slick.age.damping_db != null && (
                              <StatBox label="Radar Damping" value={`${slick.age.damping_db.toFixed(1)} dB`} />
                            )}
                            <div className="col-span-2 text-sm text-ink-600 bg-ink-50 p-3 rounded-lg border border-ink-100">
                               <strong>Methodology:</strong> {slick.age.method_note}
                            </div>
                         </div>
                      </div>
                    </SectionCard>
                  )}

                  {/* Evidence Subscores */}
                  {slick.evidence && (
                     <SectionCard title="Detection Evidence" icon={<Layers className="w-4 h-4" />} defaultOpen={false}>
                        <div className="grid gap-4">
                           {[
                              { label: "Backscatter damping", val: slick.evidence.contrast, w: slick.evidence.weight_contrast, hint: "Contrast vs local background. Mineral oil damps Bragg backscatter hard." },
                              { label: "Speckle suppression", val: slick.evidence.variance, w: slick.evidence.weight_variance, hint: "Inside/ambient speckle variance ratio, inverted. Oil is smoother, not just darker." },
                              { label: "Elongated shape", val: slick.evidence.shape, w: slick.evidence.weight_shape, hint: "Low compactness argues for a trail over a blob." },
                              { label: "Edge sharpness", val: slick.evidence.edge, w: slick.evidence.weight_edge, hint: "A discharge boundary is a sharp discontinuity; wind roughness fades." }
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

                  {/* Ruled Out Look-alikes */}
                  {detection && detection.rejected_lookalikes.length > 0 && (
                    <SectionCard title={`Ruled Out Look-alikes (${detection.rejected_lookalikes.length})`} icon={<EyeOff className="w-4 h-4" />} defaultOpen={false}>
                       <div className="space-y-3">
                         {detection.rejected_lookalikes.map((r, idx) => (
                           <div key={r.id} className="flex flex-col sm:flex-row sm:items-start gap-4 p-4 rounded-lg border border-ink-200 bg-ink-50">
                              <div className="w-8 h-8 rounded-full bg-ink-200 text-ink-600 flex items-center justify-center font-bold text-xs shrink-0">
                                 #{idx + 1}
                              </div>
                              <div className="flex-1">
                                 <div className="flex items-center gap-2 mb-1">
                                    <Badge color="gray">NOT OIL</Badge>
                                    <span className="text-xs font-mono text-ink-500">Conf: {pct(r.confidence)}</span>
                                 </div>
                                 <p className="text-sm text-ink-700 leading-relaxed mb-2">{r.reason}</p>
                                 <button 
                                    onClick={() => onFocusLookalike(r.id)}
                                    className="text-xs flex items-center gap-1 font-semibold text-blue-600 hover:text-blue-800"
                                 >
                                    <Eye className="w-3.5 h-3.5" /> View on Map
                                 </button>
                              </div>
                           </div>
                         ))}
                       </div>
                    </SectionCard>
                  )}

                </div>
              )}
           </div>
        )}
      </div>
    </ViewModeProvider>
  );
}
