from fastapi import APIRouter

from app.attribution import engine
from app.core.schemas import AttributeRequest, AttributeResponse

router = APIRouter(prefix="/api", tags=["attribution"])


@router.post("/attribute", response_model=AttributeResponse)
def attribute(req: AttributeRequest) -> AttributeResponse:
    """Stage 3 — filter AIS traffic against the estimated origin and return a
    ranked, explainable candidate list. Never an identification.
    """
    return engine.reconstruct_and_score(req.weights)
