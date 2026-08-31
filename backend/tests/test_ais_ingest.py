"""Phase 6 — AIS ingestion and vessel-track reconstruction.

Covers parsing raw AIS records into normalised positions, grouping by MMSI,
chronological sorting, track reconstruction, gap detection, and GeoJSON
LineString output — against both a small synthetic fixture (so every edge
case is exercised precisely) and the real case-bundle AIS parquet.

Explicitly NOT covered here: attribution scoring (proximity/heading/context
suspicion) — that is attribution/engine.py's job and stays untouched. Nothing
in this module may label a vessel "suspicious"; only interpolation and gap
detection are performed, and a gap is surfaced as an investigation signal,
never a verdict.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.attribution import ais_ingest

CASE = Path(__file__).resolve().parents[2] / "data" / "case"
needs_bundle = pytest.mark.skipif(
    not (CASE / "case.json").exists(),
    reason="case bundle not built — run scripts/build_case.py",
)

T0 = datetime(2023, 6, 15, 0, 0, tzinfo=timezone.utc)


def _raw(rows: list[dict]) -> pd.DataFrame:
    """Build a raw-AIS-shaped DataFrame matching data/case/ais.parquet's
    actual columns (MMSI, BaseDateTime, LAT, LON, SOG, COG, VesselName,
    VesselType) — no IMO, no heading, exactly like the real file."""
    return pd.DataFrame(rows)


def _row(mmsi, t, lat, lon, sog=8.0, cog=90.0, name="TEST VESSEL", vtype=70):
    return {
        "MMSI": mmsi, "BaseDateTime": t, "LAT": lat, "LON": lon,
        "SOG": sog, "COG": cog, "VesselName": name, "VesselType": vtype,
    }


# -- 1. parsing --------------------------------------------------------

def test_parse_normalises_raw_columns_to_ais_positions():
    raw = _raw([_row("366123456", T0, 28.40, -90.10)])
    positions = ais_ingest.parse(raw)
    assert len(positions) == 1
    p = positions[0]
    assert p.mmsi == "366123456"
    assert p.timestamp == T0
    assert p.lat == pytest.approx(28.40)
    assert p.lon == pytest.approx(-90.10)
    assert p.speed_knots == pytest.approx(8.0)
    assert p.course_deg == pytest.approx(90.0)


def test_parse_leaves_imo_and_heading_as_none_when_absent():
    """The real AIS source has no IMO or true-heading columns. Never fabricate
    them — None is the honest value, matching this project's own pattern for
    absent measurements (e.g. Phase 3's wave_height_m=None)."""
    raw = _raw([_row("366123456", T0, 28.40, -90.10)])
    p = ais_ingest.parse(raw)[0]
    assert p.imo is None
    assert p.heading_deg is None


def test_parse_uses_imo_and_heading_when_the_source_provides_them():
    raw = _raw([_row("366123456", T0, 28.40, -90.10)])
    raw["IMO"] = ["IMO9412345"]
    raw["Heading"] = [95.0]
    p = ais_ingest.parse(raw)[0]
    assert p.imo == "IMO9412345"
    assert p.heading_deg == pytest.approx(95.0)


def test_parse_drops_positions_with_invalid_coordinates():
    raw = _raw([
        _row("366123456", T0, 28.40, -90.10),
        _row("366123456", T0 + timedelta(minutes=5), 999.0, -90.10),   # invalid lat
        _row("366123456", T0 + timedelta(minutes=10), 28.41, -999.0),  # invalid lon
    ])
    positions = ais_ingest.parse(raw)
    assert len(positions) == 1


def test_parse_drops_rows_with_a_missing_mmsi_or_timestamp():
    raw = _raw([
        _row("366123456", T0, 28.40, -90.10),
        _row(None, T0, 28.41, -90.10),
        _row("366123457", None, 28.42, -90.10),
    ])
    positions = ais_ingest.parse(raw)
    assert len(positions) == 1


def test_parse_is_empty_safe():
    assert ais_ingest.parse(_raw([])) == []


# -- 2. MMSI grouping + 3. chronological sorting -------------------------

def test_positions_group_by_mmsi():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("B", T0, 29.00, -89.50),
        _row("A", T0 + timedelta(minutes=10), 28.41, -90.09),
    ])
    grouped = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))
    assert set(grouped) == {"A", "B"}
    assert len(grouped["A"]) == 2
    assert len(grouped["B"]) == 1


def test_positions_within_a_group_are_sorted_chronologically():
    raw = _raw([
        _row("A", T0 + timedelta(minutes=20), 28.42, -90.08),
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=10), 28.41, -90.09),
    ])
    grouped = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))
    times = [p.timestamp for p in grouped["A"]]
    assert times == sorted(times)


# -- 4. track reconstruction ---------------------------------------------

def test_reconstruct_track_builds_a_linestring_in_chronological_order():
    raw = _raw([
        _row("A", T0 + timedelta(minutes=10), 28.41, -90.09),
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=20), 28.42, -90.08),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    track = ais_ingest.reconstruct_track(positions)
    assert track.linestring["type"] == "LineString"
    coords = track.linestring["coordinates"]
    assert coords == [[-90.10, 28.40], [-90.09, 28.41], [-90.08, 28.42]]


def test_reconstruct_track_requires_at_least_two_positions():
    raw = _raw([_row("A", T0, 28.40, -90.10)])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    with pytest.raises(ValueError):
        ais_ingest.reconstruct_track(positions)


# -- 5. interpolation, only where scientifically appropriate -------------

def test_short_gaps_are_interpolated():
    """A short, physically plausible gap (implied speed within a sane bound)
    gets a linear interpolated path — this is a real geometric fill-in, not
    a claim about what the vessel actually did."""
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=20), 28.42, -90.08),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    track = ais_ingest.reconstruct_track(positions)
    assert track.interpolated_segments, "a short, plausible gap should be interpolated"
    seg = track.interpolated_segments[0]
    assert seg["start_utc"] == T0
    assert seg["end_utc"] == T0 + timedelta(minutes=20)
    assert len(seg["path"]["coordinates"]) >= 2


def test_long_or_implausible_gaps_are_not_interpolated():
    """A gap long enough, or requiring an implausible implied speed, must NOT
    be silently bridged with a straight line — that would fabricate a
    position no one observed. It becomes an AISGap instead (tested below),
    not an interpolated segment."""
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        # 6 hours later, 400 km away -> implied speed is absurd for any vessel.
        _row("A", T0 + timedelta(hours=6), 30.50, -87.00),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    track = ais_ingest.reconstruct_track(positions)
    assert not track.interpolated_segments


def test_interpolation_never_extends_past_the_last_real_fix():
    """Only BETWEEN two observed fixes, never extrapolated beyond them."""
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=15), 28.41, -90.09),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    track = ais_ingest.reconstruct_track(positions)
    for seg in track.interpolated_segments:
        assert seg["start_utc"] >= positions[0].timestamp
        assert seg["end_utc"] <= positions[-1].timestamp


# -- 6. AIS gap detection --------------------------------------------------

def test_gap_detected_above_the_threshold():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=90), 28.50, -90.00),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    gaps = ais_ingest.detect_gaps(positions, threshold_minutes=30.0)
    assert len(gaps) == 1
    assert gaps[0].duration_minutes == pytest.approx(90.0)
    assert gaps[0].start_utc == T0
    assert gaps[0].end_utc == T0 + timedelta(minutes=90)


def test_no_gap_below_the_threshold():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=10), 28.41, -90.09),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    gaps = ais_ingest.detect_gaps(positions, threshold_minutes=30.0)
    assert gaps == []


def test_multiple_gaps_are_all_detected():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=60), 28.45, -90.05),
        _row("A", T0 + timedelta(minutes=70), 28.46, -90.04),
        _row("A", T0 + timedelta(minutes=150), 28.50, -90.00),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    gaps = ais_ingest.detect_gaps(positions, threshold_minutes=30.0)
    assert len(gaps) == 2


def test_gap_flags_overlap_with_a_supplied_time_window():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=90), 28.50, -90.00),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    window = (T0 + timedelta(minutes=30), T0 + timedelta(minutes=60))
    gaps = ais_ingest.detect_gaps(positions, threshold_minutes=30.0, origin_window=window)
    assert gaps[0].overlaps_origin_window is True


def test_gap_does_not_flag_overlap_when_window_is_outside_the_gap():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=90), 28.50, -90.00),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    window = (T0 + timedelta(hours=5), T0 + timedelta(hours=6))
    gaps = ais_ingest.detect_gaps(positions, threshold_minutes=30.0, origin_window=window)
    assert gaps[0].overlaps_origin_window is False


def test_gaps_carry_an_interpolated_path_when_geometrically_plausible():
    """A gap can still show a straight-line interpolated_path (Phase 6's own
    reconstruction), while remaining flagged as a genuine gap — the two are
    not mutually exclusive; interpolation fills the geometry, detection
    flags the silence."""
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=40), 28.42, -90.08),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    gaps = ais_ingest.detect_gaps(positions, threshold_minutes=30.0)
    assert gaps[0].interpolated_path is not None


# -- gaps are investigation signals, never a verdict ----------------------

def test_gap_objects_carry_no_suspicion_or_verdict_field():
    """Acceptance: do not call vessels suspicious merely because a gap
    exists. The AISGap type itself must have no suspicion/verdict field —
    only a geometric fact (duration, overlap)."""
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=90), 28.50, -90.00),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    gap = ais_ingest.detect_gaps(positions, threshold_minutes=30.0)[0]
    fields = set(vars(gap))
    banned = {"suspicious", "suspect", "flag", "verdict", "guilty", "risk"}
    assert not (fields & banned)


def test_gap_label_is_investigation_signal_not_an_accusation():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=90), 28.50, -90.00),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["A"]
    gap = ais_ingest.detect_gaps(positions, threshold_minutes=30.0)[0]
    assert "investigation" in gap.label.lower() or "signal" in gap.label.lower()
    for banned_word in ("suspicious", "guilty", "criminal", "polluter"):
        assert banned_word not in gap.label.lower()


# -- 7. vessel metadata association ----------------------------------------

def test_vessel_metadata_is_associated_from_the_positions():
    raw = _raw([
        _row("366123456", T0, 28.40, -90.10, name="MV EXAMPLE", vtype=80),
        _row("366123456", T0 + timedelta(minutes=10), 28.41, -90.09, name="MV EXAMPLE", vtype=80),
    ])
    vessel = ais_ingest.build_vessel("366123456", ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["366123456"])
    assert vessel.mmsi == "366123456"
    assert vessel.name == "MV EXAMPLE"
    assert vessel.vessel_type_code == 80


def test_vessel_metadata_handles_a_missing_name():
    raw = _raw([_row("366123456", T0, 28.40, -90.10, name=None)])
    raw2 = _raw([_row("366123457", T0 + timedelta(minutes=1), 28.41, -90.09, name=None)])
    import pandas as pd
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(pd.concat([raw, raw2])))
    vessel = ais_ingest.build_vessel("366123456", positions["366123456"])
    assert vessel.name is None


# -- 8. GeoJSON LineString generation --------------------------------------

def test_track_to_geojson_feature_is_a_linestring_with_metadata():
    raw = _raw([
        _row("366123456", T0, 28.40, -90.10, name="MV EXAMPLE"),
        _row("366123456", T0 + timedelta(minutes=10), 28.41, -90.09, name="MV EXAMPLE"),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["366123456"]
    track = ais_ingest.reconstruct_track(positions)
    feature = track.to_geojson_feature(mmsi="366123456", name="MV EXAMPLE")
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "LineString"
    assert feature["properties"]["mmsi"] == "366123456"
    assert feature["properties"]["name"] == "MV EXAMPLE"
    assert feature["properties"]["n_positions"] == 2


def test_geojson_is_plain_json_serialisable():
    import json

    raw = _raw([
        _row("366123456", T0, 28.40, -90.10),
        _row("366123456", T0 + timedelta(minutes=10), 28.41, -90.09),
    ])
    positions = ais_ingest.group_by_mmsi(ais_ingest.parse(raw))["366123456"]
    track = ais_ingest.reconstruct_track(positions)
    feature = track.to_geojson_feature(mmsi="366123456", name=None)
    json.dumps(feature)


# -- end to end: ingest() ties every stage together -----------------------

def test_ingest_produces_one_result_per_vessel():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=10), 28.41, -90.09),
        _row("B", T0, 29.00, -89.50),
        _row("B", T0 + timedelta(minutes=15), 29.02, -89.48),
    ])
    results = ais_ingest.ingest(raw)
    assert set(results) == {"A", "B"}
    for mmsi, r in results.items():
        assert r.vessel.mmsi == mmsi
        assert r.track is not None
        assert isinstance(r.gaps, list)


def test_ingest_skips_vessels_with_too_few_positions_for_a_track():
    """A single-fix vessel has no track to reconstruct, but should not crash
    the whole ingestion — it is reported with track=None."""
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=10), 28.41, -90.09),
        _row("LONELY", T0, 30.0, -88.0),
    ])
    results = ais_ingest.ingest(raw)
    assert results["LONELY"].track is None
    assert results["A"].track is not None


def test_ingest_feature_collection_contains_every_vessel_with_a_track():
    raw = _raw([
        _row("A", T0, 28.40, -90.10),
        _row("A", T0 + timedelta(minutes=10), 28.41, -90.09),
        _row("LONELY", T0, 30.0, -88.0),
    ])
    results = ais_ingest.ingest(raw)
    fc = ais_ingest.to_feature_collection(results)
    assert fc["type"] == "FeatureCollection"
    mmsis = {f["properties"]["mmsi"] for f in fc["features"]}
    assert mmsis == {"A"}  # LONELY has no track, so no LineString feature


# -- real case bundle -------------------------------------------------------

@needs_bundle
def test_ingest_runs_against_the_real_ais_parquet():
    """The frozen case bundle's ais.parquet currently ships only the single
    injected ground-truth vessel (367301820) — a known, pre-existing gap in
    the case bundle itself (test_case_bundle.py's real-traffic assertions are
    among this repo's already-failing tests, unrelated to Phase 6). This only
    asserts the pipeline runs end to end and produces a usable track for
    whatever vessels the data actually contains."""
    from app.core.case_store import load_case

    bundle = load_case()
    raw = bundle.ais()
    results = ais_ingest.ingest(raw)
    assert len(results) >= 1
    with_tracks = [r for r in results.values() if r.track is not None]
    assert with_tracks


@needs_bundle
def test_real_data_produces_at_least_one_detectable_gap_or_none_gracefully():
    """Not every real vessel will have a gap; this only asserts the pipeline
    runs cleanly end to end and gaps (if any) are well-formed."""
    from app.core.case_store import load_case

    bundle = load_case()
    results = ais_ingest.ingest(bundle.ais())
    for r in results.values():
        for g in r.gaps:
            assert g.duration_minutes > 0
            assert g.end_utc > g.start_utc


@needs_bundle
def test_real_positions_have_no_imo_or_heading():
    """Regression guard against silently fabricating these two fields for the
    real NOAA AccessAIS-derived source, which does not carry them."""
    from app.core.case_store import load_case

    bundle = load_case()
    positions = ais_ingest.parse(bundle.ais())
    assert all(p.imo is None for p in positions[:50])
    assert all(p.heading_deg is None for p in positions[:50])
