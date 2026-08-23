from fastapi import APIRouter

from app.core import fixtures
from app.core.schemas import CaseMeta

router = APIRouter(prefix="/api", tags=["case"])


@router.get("/case", response_model=CaseMeta)
def get_case() -> CaseMeta:
    """Case metadata, data provenance and the constructed-scenario disclaimer.

    Phase 1 replaces the fixture with a read of data/case/case.json.
    """
    return fixtures.case_meta()
