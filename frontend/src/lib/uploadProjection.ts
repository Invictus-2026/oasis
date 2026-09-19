import type { CaseMeta, CustomImageOverlay, DetectResponse, UploadResponse } from "../api/types";

/** Converts a raw upload-detection response into the georeferenced
 *  DetectResponse + CustomImageOverlay shape that SpillContext.injectAdHocDetection
 *  expects. Shared by every ad-hoc upload entry point (Satellite Intelligence page,
 *  the global upload sidebar) so the georeferencing math stays in one place. */
export function buildAdHocDetection(
  resData: UploadResponse,
  opts: { gsd: number; fileName?: string; caseMeta: CaseMeta | null; overlayImageUrl: string }
): { detection: DetectResponse; overlay: CustomImageOverlay } | null {
  const primaryRegion = resData.oil_regions[0];
  if (!primaryRegion) return null;
  const polygon = primaryRegion.polygon;
  if (!polygon) return null;

  const slickId = "adhoc-" + Date.now();
  const centerLon = opts.caseMeta?.center[0] ?? -89.85125;
  const centerLat = opts.caseMeta?.center[1] ?? 28.47625;
  const kmPerDegLon = 111.32 * Math.cos((centerLat * Math.PI) / 180);
  const degLonPerPx = (opts.gsd / 1000.0) / kmPerDegLon;
  const degLatPerPx = (opts.gsd / 1000.0) / 110.574;
  const halfW = (resData.width / 2.0) * degLonPerPx;
  const halfH = (resData.height / 2.0) * degLatPerPx;

  const overlay: CustomImageOverlay = {
    id: slickId,
    imageUrl: opts.overlayImageUrl,
    coordinates: [
      [centerLon - halfW, centerLat + halfH],
      [centerLon + halfW, centerLat + halfH],
      [centerLon + halfW, centerLat - halfH],
      [centerLon - halfW, centerLat - halfH],
    ],
    bbox: { west: centerLon - halfW, south: centerLat - halfH, east: centerLon + halfW, north: centerLat + halfH },
    name: opts.fileName || "Custom Upload Scene",
  };

  const detection: DetectResponse = {
    slicks: [{
      id: slickId,
      polygon,
      confidence: primaryRegion.confidence,
      method: resData.method,
      geometry: primaryRegion.morphology,
      backscatter: primaryRegion.backscatter,
      age: null,
      evidence: null,
      thickness_um: primaryRegion.thickness_um,
      contrast_db: primaryRegion.contrast_db,
    }],
    rejected_lookalikes: resData.rejected_lookalikes.map((rl, idx) => ({
      id: `lookalike-${slickId}-${idx}`,
      polygon: rl.polygon || { type: "Polygon", coordinates: [] },
      confidence: rl.confidence ?? 0.0,
      reason: rl.reason,
    })),
    processing: resData.processing,
    provenance: {
      model_version: "custom-upload",
      params: { gsd: opts.gsd },
      generated_at: new Date().toISOString(),
      inputs: [opts.fileName ?? "custom"],
      notes: "Injected from custom upload",
    },
  };

  return { detection, overlay };
}
