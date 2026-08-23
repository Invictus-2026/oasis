from datetime import datetime, timezone

from fastapi import APIRouter

from app.core import config, fixtures
from app.core.schemas import ReportContent, ReportRequest

router = APIRouter(prefix="/api", tags=["report"])


@router.post("/report", response_model=ReportContent)
def report(req: ReportRequest) -> ReportContent:
    """Evidence report content. Phase 6 adds a PDF rendering of exactly this
    payload, so the document and the on-screen panel can never disagree.
    """
    case = fixtures.case_meta()
    detection = fixtures.detect_response()
    hindcast = fixtures.hindcast_response()
    attribution = fixtures.attribute_response()

    slick = detection.slicks[0]
    return ReportContent(
        case_id=req.case_id,
        generated_at=datetime.now(timezone.utc),
        scene_id=case.scene_id,
        acquired_at=case.acquired_at,
        processing_chain=detection.processing + hindcast.processing + attribution.processing,
        detection_summary={
            "slick_id": slick.id,
            "method": slick.method.value,
            "confidence": slick.confidence,
            **slick.geometry.model_dump(),
            "age_hours": [slick.age.min_hours, slick.age.max_hours] if slick.age else None,
            "lookalikes_rejected": len(detection.rejected_lookalikes),
        },
        origin_summary={
            "point": hindcast.origin_estimate.point,
            "time_utc": hindcast.origin_estimate.time_utc.isoformat(),
            "uncertainty_radius_km": hindcast.origin_estimate.uncertainty_radius_km,
            "time_window_hours": list(hindcast.origin_estimate.time_window_hours),
        },
        candidates=attribution.candidates,
        limitations=config.LIMITATIONS,
        provenance=case.provenance,
    )
