"""
GET /api/ais/tracks — Phase 6 AIS ingestion and vessel-track reconstruction.

Real AIS parsing, MMSI grouping, chronological ordering, track
reconstruction, gap detection and GeoJSON output over data/case/ais.parquet.
Purely additive: this is a new endpoint, not a replacement for
/api/attribute, which still serves its existing (fixture) scoring response
unchanged so the existing UI and attribution flow are undisturbed.

No attribution scoring happens here — see app/attribution/ais_ingest.py's
module docstring. A detected gap is returned as a geometric/temporal fact,
never a suspicion verdict.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.attribution import ais_ingest
from app.core import config
from app.core.case_store import data_files_ready, load_case
from app.core.schemas import (
    AISGap,
    AISPositionOut,
    AISTracksResponse,
    Provenance,
    ProcessingStep,
    VesselOut,
    VesselTrackOut,
)

router = APIRouter(prefix="/api/ais", tags=["ais"])


def _to_out(result: ais_ingest.VesselIngestResult) -> VesselTrackOut:
    return VesselTrackOut(
        vessel=VesselOut(
            mmsi=result.vessel.mmsi, name=result.vessel.name,
            vessel_type_code=result.vessel.vessel_type_code, imo=result.vessel.imo,
        ),
        positions=[
            AISPositionOut(
                timestamp=p.timestamp, lat=p.lat, lon=p.lon,
                speed_knots=p.speed_knots, course_deg=p.course_deg,
                heading_deg=p.heading_deg, imo=p.imo,
            )
            for p in result.positions
        ],
        linestring=result.track.linestring if result.track else None,
        interpolated_segments=result.track.interpolated_segments if result.track else [],
        gaps=[
            AISGap(
                start_utc=g.start_utc, end_utc=g.end_utc, duration_minutes=g.duration_minutes,
                interpolated_path=g.interpolated_path, overlaps_origin_window=g.overlaps_origin_window,
                label=g.label,
            )
            for g in result.gaps
        ],
    )


@router.get("/tracks", response_model=AISTracksResponse)
def tracks(
    gap_threshold_minutes: float = Query(
        default=ais_ingest.DEFAULT_GAP_THRESHOLD_MINUTES, gt=0.0,
        description="minimum silence, in minutes, to report as an AIS gap",
    ),
) -> AISTracksResponse:
    """Ingest the case bundle's real AIS traffic into vessel tracks.

    Falls back to a small synthetic AIS table when the case bundle's binary
    data files are not on disk (mirrors this codebase's existing
    fixture-fallback convention, e.g. case_store.data_files_ready()), so the
    endpoint always answers.
    """
    t0 = time.perf_counter()
    bundle = load_case()

    if bundle is not None and data_files_ready():
        raw = bundle.ais()
        origin_window = None
        gt = bundle.meta.get("ground_truth")
        if gt and gt.get("origin_time_utc"):
            center = datetime.fromisoformat(gt["origin_time_utc"])
            origin_window = (center - timedelta(hours=6), center + timedelta(hours=6))
        source_label = f"case bundle '{bundle.id}' AIS traffic (data/case/ais.parquet)"
        is_synthetic = False
    else:
        raw = _mock_ais_table()
        origin_window = None
        source_label = "mock AIS fixture — case bundle unavailable"
        is_synthetic = True

    results = ais_ingest.ingest(raw, gap_threshold_minutes=gap_threshold_minutes, origin_window=origin_window)
    vessels_out = [_to_out(r) for r in results.values()]
    fc = ais_ingest.to_feature_collection(results)

    return AISTracksResponse(
        vessels=vessels_out,
        geojson=fc,
        total_positions_parsed=sum(len(r.positions) for r in results.values()),
        total_vessels=len(results),
        processing=[
            ProcessingStep(
                name="parse + group + reconstruct + detect gaps",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                detail=f"{len(results)} vessel(s), gap threshold {gap_threshold_minutes:.0f} min",
            ),
        ],
        provenance=Provenance(
            model_version=config.MODEL_VERSION,
            params={
                "gap_threshold_minutes": gap_threshold_minutes,
                "max_interpolation_gap_minutes": ais_ingest.MAX_INTERPOLATION_GAP_MINUTES,
                "max_plausible_speed_knots": ais_ingest.MAX_PLAUSIBLE_SPEED_KNOTS,
            },
            generated_at=datetime.now(timezone.utc),
            inputs=[source_label],
            notes=(
                ("MOCK MODE — " if is_synthetic else "")
                + "Real ingestion pipeline (parse, group by MMSI, sort, reconstruct, gap-detect); "
                "no attribution/suspicion scoring is computed here. AIS gaps are reported as "
                "geometric/temporal facts — an investigation signal, never a finding that a "
                "vessel is suspicious. See app/attribution/ais_ingest.py."
            ),
        ),
    )


def _mock_ais_table():
    """A small synthetic AIS table, same column shape as the real parquet, so
    the ingestion pipeline itself (not a separate fixture generator) produces
    the mock-mode response — matching this project's drift/mock_engine.py
    pattern: the mock path runs the real code against synthetic input rather
    than faking the output shape by hand."""
    import pandas as pd

    base = datetime(2023, 6, 15, 0, 0, tzinfo=timezone.utc)
    rows = []
    # Two vessels, one with a deliberate gap, so the mock path exercises both
    # a clean track and gap detection without a real case bundle.
    for i in range(12):
        rows.append({
            "MMSI": "366000001", "BaseDateTime": base + timedelta(minutes=10 * i),
            "LAT": 28.40 + 0.01 * i, "LON": -90.10 + 0.01 * i,
            "SOG": 8.0, "COG": 45.0, "VesselName": "MOCK VESSEL ONE", "VesselType": 80,
        })
    for i, minutes in enumerate([0, 10, 20, 30, 130, 140, 150]):
        rows.append({
            "MMSI": "366000002", "BaseDateTime": base + timedelta(minutes=minutes),
            "LAT": 28.60 - 0.01 * i, "LON": -89.90 - 0.01 * i,
            "SOG": 6.0, "COG": 210.0, "VesselName": "MOCK VESSEL TWO", "VesselType": 70,
        })
    return pd.DataFrame(rows)
