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

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from app.detection import classical, unet
from app.detection import volume as volume_mod

router = APIRouter(prefix="/api/detect", tags=["detect-upload"])

DEFAULT_GSD_M = 10.0  # Sentinel-1 IW GRD ground range resolution class
MAX_SIDE_PX = 2048    # downscale anything bigger; keeps CPU inference time sane


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


def _load_image(raw: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="could not read image file")

    if max(img.size) > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / max(img.size)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    return img


def _image_to_pseudo_db(img: Image.Image) -> np.ndarray:
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    # Darker pixel -> more damped -> lower "dB"; linear map onto a plausible
    # Sigma0 range so the existing adaptive-threshold/shape logic behaves the
    # way it does on real calibrated backscatter, which is all it needs since
    # every downstream decision is relative (local contrast), not absolute.
    return (gray / 255.0) * 30.0 - 30.0


def _min_enclosing_circle(contour: np.ndarray) -> dict:
    (cx, cy), r = cv2.minEnclosingCircle(contour.astype(np.float32))
    return {"cx": round(float(cx), 1), "cy": round(float(cy), 1), "radius": round(float(r), 1)}


def _region_to_upload(region_tuple, gsd_m: float) -> UploadRegion:
    r, conf, reason, _evidence = region_tuple
    area_km2 = r.area_px * (gsd_m ** 2) / 1e6
    vol = volume_mod.estimate(area_km2, r.contrast_db)
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
    )


@router.post("/upload", response_model=UploadResponse)
async def detect_upload(
    file: UploadFile = File(...),
    method: str = Form("classical"),
    gsd_m: float = Form(DEFAULT_GSD_M),
) -> UploadResponse:
    """Run detection on a user-uploaded image and return drawable regions
    plus an area/volume estimate. See module docstring for the assumptions
    this makes that /api/detect (frozen case study) does not have to."""
    if method not in ("classical", "unet"):
        raise HTTPException(status_code=400, detail="method must be 'classical' or 'unet'")
    if method == "unet" and not unet.available():
        raise HTTPException(status_code=503, detail="U-Net weights not available; use method=classical")
    if gsd_m <= 0:
        raise HTTPException(status_code=400, detail="gsd_m must be positive")

    raw = await file.read()
    img = _load_image(raw)
    db = _image_to_pseudo_db(img)

    detector = unet if method == "unet" else classical
    oil, looks, steps = detector.detect(db)

    oil_regions = [_region_to_upload(t, gsd_m) for t in oil]
    look_regions = [_region_to_upload(t, gsd_m) for t in looks]

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
        notes=(
            f"Ad-hoc upload, not the frozen case study: ground sampling distance is a stated "
            f"assumption ({gsd_m:g} m/px, Sentinel-1 IW GRD class), not measured from this image's "
            f"metadata, and pixel intensity is linearly mapped to a synthetic backscatter-like "
            f"value since this image has no calibrated Sigma0. Area and volume scale directly with "
            f"that assumption -- treat them as illustrative, not measured. Volume additionally "
            f"carries the Bonn Agreement thickness-bracket heuristic in volume.py."
        ),
    )
