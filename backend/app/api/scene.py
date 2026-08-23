"""Serves the SAR scene as a browser-renderable image overlay.

The detected polygon means little floating in empty space. Drawing it on the
actual backscatter — where a viewer can see the dark trail the detector keyed
on, and the look-alikes it rejected — is what makes the result legible.
"""

from __future__ import annotations

import io
from functools import lru_cache

import numpy as np
from fastapi import APIRouter, HTTPException, Response

from app.core.case_store import load_case

router = APIRouter(prefix="/api/scene", tags=["scene"])

# Display processing. These affect ONLY the browser overlay — the detector
# always runs on the full-resolution unmodified backscatter.
MULTILOOK = 2        # box-average factor; real SAR quicklooks are multi-looked
STRETCH = (1.0, 99.0)
GAMMA = 1.9          # >1 darkens midtones so the sea recedes and the slick reads

# Blue-steel ramp. Dark enough to sit inside the dark UI without glare, and to
# leave the amber detection outline as the brightest thing on the map.
SEA_RGB = (18, 30, 48)
BRIGHT_RGB = (122, 146, 178)


@lru_cache(maxsize=2)
def _render(colorise: bool) -> bytes:
    from PIL import Image

    bundle = load_case()
    db = bundle.sar_db()

    # Multi-look: average NxN blocks. Speckle is multiplicative noise, so
    # averaging suppresses it while preserving the damped patches. Without this
    # the overlay reads as television static rather than as an ocean scene.
    if MULTILOOK > 1:
        h, w = db.shape
        h, w = h - h % MULTILOOK, w - w % MULTILOOK
        db = db[:h, :w].reshape(h // MULTILOOK, MULTILOOK, w // MULTILOOK, MULTILOOK).mean(axis=(1, 3))

    lo, hi = np.percentile(db, STRETCH)
    norm = np.clip((db - lo) / (hi - lo), 0, 1) ** GAMMA

    if colorise:
        rgb = np.stack([
            (SEA_RGB[c] + norm * (BRIGHT_RGB[c] - SEA_RGB[c])).astype(np.uint8)
            for c in range(3)
        ], axis=-1)
        img = Image.fromarray(rgb, mode="RGB")
    else:
        img = Image.fromarray((norm * 255).astype(np.uint8), mode="L")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@router.get("/sar.png")
def sar_png(grey: bool = False) -> Response:
    """The case's SAR backscatter, percentile-stretched, as a PNG.

    Georeferencing is the case bbox: the frontend places it as an image source
    with the bbox corners, so it lines up with the detection polygons exactly.
    """
    if load_case() is None:
        raise HTTPException(status_code=404, detail="case bundle not built")
    return Response(
        content=_render(colorise=not grey),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
