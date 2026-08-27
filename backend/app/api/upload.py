"""
Ad-hoc image upload endpoint, for the temp-frontend demo tool.

Unlike /api/detect (which runs against the frozen, georeferenced case-study
bundle in data/case/), this accepts an arbitrary user-supplied image with no
known ground-sampling distance or calibrated radiometry. Two assumptions this
implies, stated up front rather than hidden in the numbers:

  1. Ground sampling distance (GSD) is user-supplied (default 10 m/pixel,
     matching Sentinel-1 IW GRD -- the resolution class both detectors were
     built/trained around). Area and volume scale directly with this number.
  2. There is no calibrated Sigma0 backscatter for a plain photo, so pixel
     intensity is linearly mapped onto a synthetic "dB-like" array (darker =
     more damped) purely so the existing threshold/shape logic -- which only
     needs RELATIVE contrast, not absolute calibration -- has something to
     work with. Absolute dB numbers for uploaded images are not physically
     meaningful; only the relative comparisons the detectors act on are.

Volume numbers additionally carry volume.py's own heuristic-thickness caveat.
"""

from __future__ import annotations

import io
import math

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from app.core.schemas import BackscatterStats, GeoJSON, SlickGeometry
from app.detection import classical, unet
from app.detection import volume as volume_mod

router = APIRouter(prefix="/api/detect", tags=["detect-upload"])

DEFAULT_GSD_M = 10.0  # Sentinel-1 IW GRD ground range resolution class
MAX_SIDE_PX = 2048    # downscale anything bigger; keeps CPU inference time sane

KM_PER_DEG_LAT = 110.574

# PIL decodes far more than this, but these are the formats a SAR quicklook or
# an exported scene actually arrives as. Anything else is rejected with a
# message naming what is supported rather than failing obscurely downstream.
SUPPORTED_FORMATS = {"PNG", "JPEG", "TIFF", "BMP", "WEBP"}


class UploadRegion(BaseModel):
    contour: list[list[float]]  # pixel [x, y] ring, for drawing on a canvas
    circle: dict                # {cx, cy, radius} minimum enclosing circle
    confidence: float
    reason: str
    area_px: int
    area_km2: float
    contrast_db: float
    thickness_um: float
    volume_m3: float
    volume_liters: float
    volume_barrels: float
    # Phase 2 additions: the full morphology record and the radiometric stats
    # behind the confidence score, plus the georeferenced ring when an anchor
    # was supplied.
    morphology: SlickGeometry
    backscatter: BackscatterStats
    polygon: GeoJSON | None = None


class UploadResponse(BaseModel):
    width: int
    height: int
    method: str
    gsd_m: float
    oil_regions: list[UploadRegion]
    rejected_lookalikes: list[UploadRegion]
    total_area_km2: float
    total_volume_liters: float
    total_volume_barrels: float
    processing: list[dict]
    notes: str
    geojson: GeoJSON | None = None


def _load_image(raw: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="could not read image file")

    if img.format and img.format.upper() not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported image format {img.format}; supported: {', '.join(sorted(SUPPORTED_FORMATS))}",
        )

    if max(img.size) > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / max(img.size)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    return img


def _image_to_pseudo_db(img: Image.Image) -> np.ndarray:
    """Normalise an uncalibrated image onto a relative dB-like scale.

    Delegates to classical.normalise() so the upload path and the frozen-case
    path share one definition of "normalisation" — and so a robust percentile
    stretch is used rather than a raw /255, which a handful of saturated pixels
    would otherwise flatten.
    """
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    return classical.normalise(gray)


def _min_enclosing_circle(contour: np.ndarray) -> dict:
    (cx, cy), r = cv2.minEnclosingCircle(contour.astype(np.float32))
    return {"cx": round(float(cx), 1), "cy": round(float(cy), 1), "radius": round(float(r), 1)}


class _Anchor:
    """Georeferencing for an image that carries none.

    A plain PNG/JPEG has no geotransform, so lon/lat can only exist if the
    caller says where the scene sits. Given a centre point and the assumed
    ground sampling distance, pixels map to degrees through a local flat-earth
    approximation — accurate well under a percent across a scene of this size,
    and honest about being an assumption rather than a measurement.
    """

    def __init__(self, lon: float, lat: float, gsd_m: float, width: int, height: int):
        self.lon, self.lat = lon, lat
        self.width, self.height = width, height
        km_per_px = gsd_m / 1000.0
        self.deg_lon_per_px = km_per_px / (111.320 * max(math.cos(math.radians(lat)), 1e-6))
        self.deg_lat_per_px = km_per_px / KM_PER_DEG_LAT

    def ring(self, contour: np.ndarray) -> list[list[float]]:
        cx, cy = self.width / 2.0, self.height / 2.0
        ring = [
            [
                round(self.lon + (float(x) - cx) * self.deg_lon_per_px, 6),
                # Pixel rows increase southward.
                round(self.lat - (float(y) - cy) * self.deg_lat_per_px, 6),
            ]
            for x, y in contour
        ]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring


def _morphology(region, gsd_m: float, perimeter_km: float) -> SlickGeometry:
    """Morphology in real units, derived from the assumed GSD.

    Mirrors geometry.describe(), but scaled by a user-supplied GSD instead of a
    bundle geotransform, since an uploaded image has no georeferencing of its
    own.
    """
    px_km = gsd_m / 1000.0
    area_km2 = region.area_px * px_km * px_km
    length_km = region.length_px * px_km
    width_km = region.width_px * px_km
    compactness = (4 * math.pi * area_km2 / (perimeter_km ** 2)) if perimeter_km > 0 else 0.0

    return SlickGeometry(
        area_km2=round(area_km2, 4),
        perimeter_km=round(perimeter_km, 3),
        length_km=round(length_km, 3),
        width_km=round(width_km, 4),
        aspect_ratio=round(length_km / width_km, 2) if width_km > 0 else 1.0,
        elongation=round(region.elongation, 2),
        orientation_deg=round(region.orientation_deg, 1),
        compactness=round(min(compactness, 1.0), 3),
        solidity=round(region.solidity, 3),
    )


def _region_to_upload(region_tuple, gsd_m: float, anchor: _Anchor | None) -> UploadRegion:
    from app.detection import geometry as geometry_mod

    r, conf, reason, _evidence = region_tuple
    area_km2 = r.area_px * (gsd_m ** 2) / 1e6
    vol = volume_mod.estimate(area_km2, r.contrast_db)

    perimeter_km = r.perimeter_px * (gsd_m / 1000.0)
    polygon = None
    if anchor is not None:
        ring = anchor.ring(r.contour)
        polygon = {"type": "Polygon", "coordinates": [ring]}
        # With a real anchor, measure the perimeter on the ground the same way
        # the frozen-case path does.
        perimeter_km = geometry_mod.ring_perimeter_km(ring)

    return UploadRegion(
        contour=[[float(x), float(y)] for x, y in r.contour],
        circle=_min_enclosing_circle(r.contour),
        confidence=conf,
        reason=reason,
        area_px=r.area_px,
        area_km2=round(area_km2, 4),
        contrast_db=round(r.contrast_db, 2),
        thickness_um=vol["thickness_um"],
        volume_m3=vol["volume_m3"],
        volume_liters=vol["volume_liters"],
        volume_barrels=vol["volume_barrels"],
        morphology=_morphology(r, gsd_m, perimeter_km),
        backscatter=BackscatterStats(**geometry_mod.backscatter(r)),
        polygon=polygon,
    )


def _feature_collection(oil: list[UploadRegion], looks: list[UploadRegion]) -> GeoJSON | None:
    """FeatureCollection of everything that has a georeferenced ring.

    Returns None when no anchor was supplied: an uploaded image with no stated
    location has no honest lon/lat, and inventing one would put a polygon on
    the map at a place it was never observed.
    """
    features = [
        {
            "type": "Feature",
            "geometry": region.polygon,
            "properties": {
                "class": cls,
                "confidence": region.confidence,
                "reason": region.reason,
                **region.morphology.model_dump(),
                **region.backscatter.model_dump(),
                "volume_liters": region.volume_liters,
                "thickness_um": region.thickness_um,
            },
        }
        for cls, regions in (("oil", oil), ("lookalike", looks))
        for region in regions
        if region.polygon is not None
    ]
    return {"type": "FeatureCollection", "features": features} if features else None


@router.post("/upload", response_model=UploadResponse)
async def detect_upload(
    file: UploadFile = File(...),
    method: str = Form("classical"),
    gsd_m: float = Form(DEFAULT_GSD_M),
    lon: float | None = Form(None),
    lat: float | None = Form(None),
) -> UploadResponse:
    """Run detection on a user-uploaded SAR image.

    Returns drawable pixel contours (for the canvas tool), a full morphology
    record and backscatter statistics per candidate region, an area/volume
    estimate, and — when `lon`/`lat` place the scene centre — a GeoJSON
    FeatureCollection the existing MapLibre map can render directly.

    See the module docstring for the assumptions this makes that /api/detect
    (frozen case study) does not have to.
    """
    if method not in ("classical", "unet"):
        raise HTTPException(status_code=400, detail="method must be 'classical' or 'unet'")
    if method == "unet" and not unet.available():
        raise HTTPException(status_code=503, detail="U-Net weights not available; use method=classical")
    if gsd_m <= 0:
        raise HTTPException(status_code=400, detail="gsd_m must be positive")
    if (lon is None) != (lat is None):
        raise HTTPException(status_code=400, detail="lon and lat must be supplied together")
    if lon is not None and not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise HTTPException(status_code=400, detail="lon must be in [-180, 180] and lat in [-90, 90]")

    raw = await file.read()
    img = _load_image(raw)
    db = _image_to_pseudo_db(img)

    detector = unet if method == "unet" else classical
    oil, looks, steps = detector.detect(db)

    anchor = _Anchor(lon, lat, gsd_m, img.width, img.height) if lon is not None else None
    oil_regions = [_region_to_upload(t, gsd_m, anchor) for t in oil]
    look_regions = [_region_to_upload(t, gsd_m, anchor) for t in looks]

    georef = (
        f"Scene centre supplied as ({lon:.4f}, {lat:.4f}); pixel-to-degree mapping is a local "
        f"flat-earth approximation from the assumed GSD, not a geotransform read from the file. "
        if anchor is not None else
        "No scene centre supplied, so no GeoJSON is returned -- pixel contours only. Pass lon and "
        "lat to place the detection on the map. "
    )

    return UploadResponse(
        width=img.width,
        height=img.height,
        method=method,
        gsd_m=gsd_m,
        oil_regions=oil_regions,
        rejected_lookalikes=look_regions,
        total_area_km2=round(sum(o.area_km2 for o in oil_regions), 4),
        total_volume_liters=round(sum(o.volume_liters for o in oil_regions), 0),
        total_volume_barrels=round(sum(o.volume_barrels for o in oil_regions), 1),
        processing=steps,
        geojson=_feature_collection(oil_regions, look_regions),
        notes=(
            f"Ad-hoc upload, not the frozen case study: ground sampling distance is a stated "
            f"assumption ({gsd_m:g} m/px, Sentinel-1 IW GRD class), not measured from this image's "
            f"metadata, and pixel intensity is percentile-normalised onto a synthetic "
            f"backscatter-like value since this image has no calibrated Sigma0 -- so the dB figures "
            f"are relative, not absolute. {georef}"
            f"Area, length, width and volume all scale directly with the GSD assumption -- treat "
            f"them as illustrative, not measured. No accuracy metric is reported for uploaded "
            f"imagery because there is no ground-truth mask to score against. Volume additionally "
            f"carries the Bonn Agreement thickness-bracket heuristic in volume.py."
        ),
    )
