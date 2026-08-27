import type {
  DetectionMethod,
  UploadResponse,
  UploadRegion,
  SlickGeometry,
  BackscatterStats,
  GeoJSONFeatureCollection,
} from "../api/types";

const KM_PER_DEG_LAT = 110.574;

/**
 * Generates realistic mock detection results from any uploaded image.
 * Uses image dimensions, GSD, and geographic anchor to produce authentic
 * slick contours, georeferenced polygons, morphology, volume, and lookalikes.
 */
export function generateMockUploadDetection(
  img: HTMLImageElement | HTMLCanvasElement,
  gsd: number = 10.0,
  anchor: [number, number] = [-89.85125, 28.47625],
  method: DetectionMethod = "classical"
): UploadResponse {
  const width = "naturalWidth" in img ? (img.naturalWidth || img.width) : img.width;
  const height = "naturalHeight" in img ? (img.naturalHeight || img.height) : img.height;

  const [centerLon, centerLat] = anchor;
  const kmPerDegLon = 111.32 * Math.cos((centerLat * Math.PI) / 180);
  const degLonPerPx = (gsd / 1000.0) / kmPerDegLon;
  const degLatPerPx = (gsd / 1000.0) / KM_PER_DEG_LAT;

  // Generate an organic, elongated oil slick contour in pixel coordinates
  const cx = width * 0.48;
  const cy = height * 0.52;
  const rx = width * 0.16;
  const ry = height * 0.08;
  const angle = 48 * (Math.PI / 180); // 48 deg orientation
  const cosA = Math.cos(angle);
  const sinA = Math.sin(angle);

  const numVertices = 28;
  const contour: [number, number][] = [];

  for (let i = 0; i <= numVertices; i++) {
    const theta = (2 * Math.PI * (i % numVertices)) / numVertices;
    // Organic deformation
    const mod =
      1.0 +
      0.28 * Math.sin(2 * theta + 0.6) +
      0.14 * Math.cos(3 * theta) +
      0.08 * Math.sin(5 * theta);
    const ex = rx * mod * Math.cos(theta);
    const ey = ry * mod * Math.sin(theta);
    // Rotate and translate
    const px = Math.round(cx + ex * cosA - ey * sinA);
    const py = Math.round(cy + ex * sinA + ey * cosA);
    contour.push([px, py]);
  }

  // Georeference the contour to lon/lat
  const polyRing: [number, number][] = contour.map(([x, y]) => [
    Number((centerLon + (x - width / 2) * degLonPerPx).toFixed(6)),
    Number((centerLat - (y - height / 2) * degLatPerPx).toFixed(6)),
  ]);

  // Approximate pixel area and real km2
  const pxKm = gsd / 1000.0;
  const approxAreaPx = Math.round(Math.PI * rx * ry * 1.05);
  const areaKm2 = Number((approxAreaPx * pxKm * pxKm).toFixed(4));
  const lengthKm = Number((rx * 2.2 * pxKm).toFixed(3));
  const widthKm = Number((ry * 1.9 * pxKm).toFixed(3));
  const perimeterKm = Number((2 * Math.PI * Math.sqrt((rx * rx + ry * ry) / 2) * pxKm * 1.15).toFixed(3));

  const morphology: SlickGeometry = {
    area_km2: areaKm2,
    perimeter_km: perimeterKm,
    length_km: lengthKm,
    width_km: widthKm,
    aspect_ratio: Number((lengthKm / Math.max(widthKm, 0.01)).toFixed(2)),
    elongation: 2.35,
    orientation_deg: 48.0,
    compactness: Number(Math.min(1.0, (4 * Math.PI * areaKm2) / (perimeterKm * perimeterKm)).toFixed(3)),
    solidity: 0.89,
  };

  const backscatter: BackscatterStats = {
    mean_db: -18.4,
    std_db: 1.35,
    background_db: -13.2,
    contrast_db: -5.2,
    variance_ratio: 0.38,
    edge_gradient: 2.1,
  };

  const thicknessUm = 12.5;
  const volumeM3 = areaKm2 * 1e6 * (thicknessUm * 1e-6);
  const volumeLiters = Math.round(volumeM3 * 1000);
  const volumeBarrels = Number((volumeLiters / 158.987).toFixed(1));

  const primaryOilRegion: UploadRegion = {
    contour,
    circle: {
      cx: Math.round(cx),
      cy: Math.round(cy),
      radius: Math.round(Math.max(rx, ry) * 1.25),
    },
    confidence: method === "unet" ? 0.94 : 0.88,
    reason: "Dark patch with high radiometric contrast (-5.2 dB) and high elongation matching crude oil spill signature.",
    area_px: approxAreaPx,
    area_km2: areaKm2,
    contrast_db: -5.2,
    thickness_um: thicknessUm,
    volume_m3: volumeM3,
    volume_liters: volumeLiters,
    volume_barrels: volumeBarrels,
    morphology,
    backscatter,
    polygon: {
      type: "Polygon",
      coordinates: [polyRing],
    },
  };

  // Generate 1 rejected lookalike (e.g. low wind calm water patch)
  const lcx = width * 0.78;
  const lcy = height * 0.28;
  const lrx = width * 0.07;
  const lry = height * 0.06;
  const lookContour: [number, number][] = [];
  for (let i = 0; i <= 16; i++) {
    const theta = (2 * Math.PI * (i % 16)) / 16;
    const px = Math.round(lcx + lrx * (1 + 0.15 * Math.sin(3 * theta)) * Math.cos(theta));
    const py = Math.round(lcy + lry * (1 + 0.15 * Math.cos(2 * theta)) * Math.sin(theta));
    lookContour.push([px, py]);
  }

  const lookRing: [number, number][] = lookContour.map(([x, y]) => [
    Number((centerLon + (x - width / 2) * degLonPerPx).toFixed(6)),
    Number((centerLat - (y - height / 2) * degLatPerPx).toFixed(6)),
  ]);

  const lookAreaKm2 = Number((Math.PI * lrx * lry * pxKm * pxKm).toFixed(4));
  const rejectedLookalike: UploadRegion = {
    contour: lookContour,
    circle: {
      cx: Math.round(lcx),
      cy: Math.round(lcy),
      radius: Math.round(lrx * 1.2),
    },
    confidence: 0.18,
    reason: "Ruled out: diffuse low-gradient boundary consistent with low-wind calm sea surface rather than oil damping.",
    area_px: Math.round(Math.PI * lrx * lry),
    area_km2: lookAreaKm2,
    contrast_db: -1.8,
    thickness_um: 1.0,
    volume_m3: lookAreaKm2 * 1e3,
    volume_liters: Math.round(lookAreaKm2 * 1e6),
    volume_barrels: Math.round((lookAreaKm2 * 1e6) / 158.987),
    morphology: {
      area_km2: lookAreaKm2,
      perimeter_km: Number((2 * Math.PI * lrx * pxKm).toFixed(3)),
      length_km: Number((lrx * 2 * pxKm).toFixed(3)),
      width_km: Number((lry * 2 * pxKm).toFixed(3)),
      aspect_ratio: 1.15,
      elongation: 1.12,
      orientation_deg: 12.0,
      compactness: 0.85,
      solidity: 0.94,
    },
    backscatter: {
      mean_db: -14.8,
      std_db: 0.8,
      background_db: -13.0,
      contrast_db: -1.8,
      variance_ratio: 0.72,
      edge_gradient: 0.45,
    },
    polygon: {
      type: "Polygon",
      coordinates: [lookRing],
    },
  };

  const geojson: GeoJSONFeatureCollection = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: primaryOilRegion.polygon!,
        properties: {
          class: "oil",
          confidence: primaryOilRegion.confidence,
          reason: primaryOilRegion.reason,
          area_km2: primaryOilRegion.area_km2,
          volume_liters: primaryOilRegion.volume_liters,
          contrast_db: primaryOilRegion.contrast_db,
        },
      },
      {
        type: "Feature",
        geometry: rejectedLookalike.polygon!,
        properties: {
          class: "lookalike",
          confidence: rejectedLookalike.confidence,
          reason: rejectedLookalike.reason,
          area_km2: rejectedLookalike.area_km2,
          volume_liters: rejectedLookalike.volume_liters,
          contrast_db: rejectedLookalike.contrast_db,
        },
      },
    ],
  };

  return {
    width,
    height,
    method,
    gsd_m: gsd,
    oil_regions: [primaryOilRegion],
    rejected_lookalikes: [rejectedLookalike],
    total_area_km2: areaKm2,
    total_volume_liters: volumeLiters,
    total_volume_barrels: volumeBarrels,
    processing: [
      { name: "Adaptive thresholding", duration_ms: 38, detail: "Otsu + morphological filter" },
      { name: "Connected-component labeling", duration_ms: 45, detail: "Region extraction" },
      { name: "Feature geometry computation", duration_ms: 22, detail: "Moments, convex hull" },
      { name: "Radiometric verification", duration_ms: 31, detail: "Relative backscatter contrast" },
    ],
    notes: `Ad-hoc upload analysis (${method === "unet" ? "U-Net CNN" : "Classical Adaptive Thresholding"}) evaluated at GSD = ${gsd} m/px.`,
    geojson,
  };
}
