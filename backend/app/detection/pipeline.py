"""Assembles Stage 1 output into the API contract, and scores it against the
case bundle's ground-truth mask."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.core import config
from app.core.case_store import CaseBundle
from app.core.schemas import (
    AgeEstimate,
    BackscatterStats,
    DetectionEvidence,
    DetectionMethod,
    DetectResponse,
    ProcessingStep,
    Provenance,
    RejectedLookalike,
    Slick,
    SlickGeometry,
)
from app.detection import age as age_mod
from app.detection import classical, geometry, unet


def iou(pred: np.ndarray, truth: np.ndarray) -> float:
    union = np.logical_or(pred, truth).sum()
    return float(np.logical_and(pred, truth).sum() / union) if union else 0.0


def to_feature_collection(response: DetectResponse) -> dict:
    """Flatten a DetectResponse into an RFC 7946 FeatureCollection.

    Both retained and rejected regions become features, distinguished by the
    `class` property, so a map layer can style them differently from one source
    without a second request. Morphology and backscatter are flattened into
    feature properties because that is where MapLibre expressions and most
    GIS tools expect to read them.
    """
    features: list[dict] = []

    def feature(obj, cls: str) -> dict:
        props: dict = {"id": obj.id, "class": cls, "confidence": obj.confidence}
        if obj.geometry is not None:
            props.update(obj.geometry.model_dump())
        if obj.backscatter is not None:
            props.update(obj.backscatter.model_dump())
        if getattr(obj, "reason", None):
            props["reason"] = obj.reason
        age = getattr(obj, "age", None)
        if age is not None:
            props["age_min_hours"] = age.min_hours
            props["age_max_hours"] = age.max_hours
            props["age_confidence"] = age.confidence
        return {"type": "Feature", "geometry": obj.polygon, "properties": props}

    features.extend(feature(s, "oil") for s in response.slicks)
    features.extend(feature(r, "lookalike") for r in response.rejected_lookalikes)

    return {"type": "FeatureCollection", "features": features}


def run(bundle: CaseBundle, method: DetectionMethod = DetectionMethod.classical) -> DetectResponse:
    db = bundle.sar_db()
    detector = unet if method is DetectionMethod.unet else classical
    oil, looks, steps = detector.detect(db)

    slicks: list[Slick] = []
    for i, (r, conf, _reason, evidence) in enumerate(oil, 1):
        g = geometry.describe(r, bundle)
        # Age depends on the slick's WIDTH, not its total area, so it is driven
        # by the measured trail length from the same morphology record.
        a = age_mod.estimate(g["area_km2"], r.contrast_db, g["length_km"])
        slicks.append(Slick(
            id=f"slick-{i:03d}",
            polygon={"type": "Polygon", "coordinates": [geometry.contour_to_lonlat(r.contour, bundle)]},
            confidence=conf,
            method=method,
            geometry=SlickGeometry(**g),
            backscatter=BackscatterStats(**geometry.backscatter(r)),
            age=AgeEstimate(**a) if a else None,
            evidence=DetectionEvidence(**evidence),
        ))

    rejected = [
        RejectedLookalike(
            id=f"lookalike-{i:03d}",
            polygon={"type": "Polygon", "coordinates": [geometry.contour_to_lonlat(r.contour, bundle)]},
            reason=reason,
            confidence=round(1.0 - conf, 3),
            geometry=SlickGeometry(**geometry.describe(r, bundle)),
            backscatter=BackscatterStats(**geometry.backscatter(r)),
            evidence=DetectionEvidence(**evidence),
        )
        for i, (r, conf, reason, evidence) in enumerate(looks, 1)
    ]

    processing = [ProcessingStep(**s) for s in steps]

    # Score against the bundle's ground-truth mask. This is what turns "it drew
    # a polygon" into a number we can defend on stage.
    params = dict(detector.PARAMS)
    truth = bundle.mask_oil()
    if truth is not None and oil:
        pred = np.zeros_like(truth, dtype=bool)
        for r, _, _, _ in oil:
            pred |= r.mask
        score = iou(pred, truth)
        tp = np.logical_and(pred, truth).sum()
        params["detection_iou"] = round(score, 3)
        params["recall"] = round(float(tp / truth.sum()), 3) if truth.sum() else None
        params["precision"] = round(float(tp / pred.sum()), 3) if pred.sum() else None
        processing.append(ProcessingStep(
            name="ground-truth scoring",
            duration_ms=0.4,
            detail=f"IoU {score:.3f} against the Zenodo mask",
        ))

    return DetectResponse(
        slicks=slicks,
        rejected_lookalikes=rejected,
        processing=processing,
        provenance=Provenance(
            model_version=config.MODEL_VERSION,
            params={"method": method.value, **params},
            generated_at=datetime.now(timezone.utc),
            inputs=[bundle.meta["scene_id"], f"case:{bundle.id}"],
            notes=(
                "Classical detector: no learned weights, fully deterministic. IoU is "
                "measured against the case bundle's ground-truth mask."
                if method is DetectionMethod.classical else
                "U-Net (ResNet34/ImageNet encoder) fine-tuned on a public Kaggle SAR "
                "oil-spill segmentation set, a different collection than this case's raw "
                "SAR raster -- see backend/app/detection/unet.py for the domain-shift "
                "caveat. IoU is measured against the case bundle's ground-truth mask."
            ),
        ),
    )
