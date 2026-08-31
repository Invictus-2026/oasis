"""
GET /api/environment — normalised environmental fields.

Answers three shapes of question through one endpoint:

  * a point in space and time          ?lon=&lat=&time=
  * a point across a time range        ?lon=&lat=&start=&end=&step_hours=
  * a selected incident                ?incident_id=            (location resolved from the case)

Everything comes back as the shared EnvironmentalData type regardless of which
provider served it, and the response names that provider so real and synthetic
data are never confused on screen.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core import config
from app.core.case_store import load_case
from app.core.schemas import Provenance
from app.environment import get_provider, list_providers
from app.environment.base import EnvironmentalData

router = APIRouter(prefix="/api/environment", tags=["environment"])


class EnvironmentResponse(BaseModel):
    incident_id: str | None = None
    lon: float
    lat: float
    provider: str
    is_synthetic: bool
    is_steady: bool
    samples: list[dict]
    provenance: Provenance


class ProviderInfo(BaseModel):
    name: str
    available: bool
    kind: str


class ProvidersResponse(BaseModel):
    active: str
    providers: list[ProviderInfo]


def _as_utc(value: datetime) -> datetime:
    """Naive timestamps are treated as UTC rather than rejected, since the rest
    of this API speaks UTC throughout."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@router.get("", response_model=EnvironmentResponse)
def environment(
    incident_id: str | None = Query(default=None, description="case id; resolves the location"),
    lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    time: datetime | None = Query(default=None, description="single instant (UTC)"),
    start: datetime | None = Query(default=None, description="range start (UTC)"),
    end: datetime | None = Query(default=None, description="range end (UTC)"),
    step_hours: float = Query(default=config.ENV_DEFAULT_STEP_HOURS, gt=0.0),
) -> EnvironmentResponse:
    """Environmental fields for an incident, a location, and/or a time range."""
    bundle = load_case()

    # -- resolve WHERE ----------------------------------------------------
    if incident_id is not None:
        if bundle is None or bundle.id != incident_id:
            raise HTTPException(status_code=404, detail=f"unknown incident '{incident_id}'")
        if lon is None or lat is None:
            lon, lat = bundle.meta["center"]

    if lon is None or lat is None:
        raise HTTPException(
            status_code=400,
            detail="supply either incident_id, or both lon and lat",
        )

    # -- resolve WHEN -----------------------------------------------------
    # No time at all still answers, anchored to the case acquisition, so a bare
    # location query is useful rather than a validation error.
    default_time = bundle.acquired_at if bundle is not None else datetime.now(timezone.utc)

    provider = get_provider(bundle)

    try:
        if start is not None or end is not None:
            if start is None or end is None:
                raise HTTPException(status_code=400, detail="start and end must be supplied together")
            samples = provider.series(lon, lat, _as_utc(start), _as_utc(end), step_hours)
        else:
            samples = [provider.at(lon, lat, _as_utc(time) if time else default_time)]
    except ValueError as exc:
        # Inverted ranges, non-positive steps and over-large series land here.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    first: EnvironmentalData = samples[0]

    return EnvironmentResponse(
        incident_id=incident_id,
        lon=lon,
        lat=lat,
        provider=provider.name,
        is_synthetic=first.is_synthetic,
        is_steady=first.is_steady,
        samples=[s.model_dump(mode="json") for s in samples],
        provenance=Provenance(
            model_version=config.MODEL_VERSION,
            params={
                "provider": provider.name,
                "mode": config.ENV_DATA_MODE,
                "step_hours": step_hours if (start and end) else None,
                "n_samples": len(samples),
            },
            generated_at=datetime.now(timezone.utc),
            inputs=[first.source],
            # Two independent facts, deliberately not conflated: WHICH provider
            # served the data, and whether those values are modelled rather
            # than measured. The case bundle is a real provider whose forcing
            # happens to be synthesised, so it is both "real provider" and
            # "synthetic values" at once.
            notes=" ".join(filter(None, [
                f"Served by the '{provider.name}' provider through the Phase 3 "
                f"environmental abstraction.",
                "Values are modelled, not measured." if first.is_synthetic else "",
                "This provider has no time axis, so every sample in the range "
                "repeats the same steady field." if first.is_steady else "",
                "This is the synthetic fallback, used because no real provider "
                "was available." if provider.name == "mock-synthetic" else "",
            ])),
        ),
    )


@router.get("/providers", response_model=ProvidersResponse)
def providers() -> ProvidersResponse:
    """Which environmental sources exist and which one is currently serving."""
    bundle = load_case()
    return ProvidersResponse(
        active=get_provider(bundle).name,
        providers=[ProviderInfo(**p) for p in list_providers(bundle)],
    )
