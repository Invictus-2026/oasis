from fastapi import APIRouter

from app.core import fixtures
from app.core.case_store import load_case
from app.core.schemas import CaseMeta

router = APIRouter(prefix="/api", tags=["case"])


@router.get("/case", response_model=CaseMeta)
def get_case() -> CaseMeta:
    """Case metadata, per-source provenance and the constructed-scenario
    disclaimer.

    Served from the frozen bundle in data/case/. Falls back to fixtures when
    the bundle has not been built, so the frontend still works on a fresh
    checkout.
    """
    bundle = load_case()
    return bundle.as_case_meta() if bundle else fixtures.case_meta()
