"""Phase 7 steps 1-4 — spatial filtering, temporal filtering, trajectory
compatibility, and behaviour analysis.

Everything here is transparent, rule-based scoring against real
ais_ingest.VesselTrack objects (Phase 6's output) — no black-box model, and
no vessel is ever labelled a culprit. Language is checked as an acceptance
criterion: candidate / investigation lead / evidence / anomaly, never
"suspect", "guilty", or "culprit".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.attribution import ais_ingest, filters

T0 = datetime(2023, 6, 15, 4, 0, tzinfo=timezone.utc)  # release window centre
ORIGIN = (-90.10, 28.42)


def _positions(mmsi, pts_with_minutes, sog=8.0, cog=90.0):
    """pts_with_minutes: list of (minute_offset, lat, lon)."""
    return [
        ais_ingest.AISPosition(
            mmsi=mmsi, timestamp=T0 + timedelta(minutes=m), lat=lat, lon=lon,
            speed_knots=sog, course_deg=cog,
        )
        for m, lat, lon in pts_with_minutes
    ]


def _track(mmsi, pts_with_minutes, **kw):
    return ais_ingest.reconstruct_track(_positions(mmsi, pts_with_minutes, **kw))


# -- Step 1: spatial filtering ----------------------------------------------

def test_vessel_track_intersecting_origin_region_passes_spatial_filter():
    region = {"type": "Polygon", "coordinates": [[
        [-90.15, 28.38], [-90.05, 28.38], [-90.05, 28.46], [-90.15, 28.46], [-90.15, 28.38],
    ]]}
    track = _track("A", [(0, 28.40, -90.12), (10, 28.42, -90.10), (20, 28.44, -90.08)])
    result = filters.spatial_filter(track, region)
    assert result.intersects is True
    assert result.min_distance_km == pytest.approx(0.0, abs=0.5)


def test_vessel_track_far_from_origin_region_fails_spatial_filter():
    region = {"type": "Polygon", "coordinates": [[
        [-90.15, 28.38], [-90.05, 28.38], [-90.05, 28.46], [-90.15, 28.46], [-90.15, 28.38],
    ]]}
    track = _track("A", [(0, 25.00, -85.00), (10, 25.10, -84.90)])
    result = filters.spatial_filter(track, region)
    assert result.intersects is False
    assert result.min_distance_km > 100.0


def test_spatial_filter_reports_a_finite_distance_when_outside():
    region = {"type": "Polygon", "coordinates": [[
        [-90.02, 28.40], [-90.00, 28.40], [-90.00, 28.42], [-90.02, 28.42], [-90.02, 28.40],
    ]]}
    track = _track("A", [(0, 28.50, -90.20), (10, 28.51, -90.19)])
    result = filters.spatial_filter(track, region)
    assert result.intersects is False
    assert 0 < result.min_distance_km < 50.0


# -- Step 2: temporal filtering ----------------------------------------------

def test_vessel_present_during_release_window_passes_temporal_filter():
    window = (T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    track = _track("A", [(-30, 28.40, -90.12), (30, 28.42, -90.10)])
    result = filters.temporal_filter(track, window)
    assert result.present_during_window is True
    assert result.overlap_minutes > 0


def test_vessel_absent_during_release_window_fails_temporal_filter():
    window = (T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    track = _track("A", [(600, 28.40, -90.12), (610, 28.42, -90.10)])  # 10h later
    result = filters.temporal_filter(track, window)
    assert result.present_during_window is False
    assert result.overlap_minutes == 0


def test_temporal_filter_computes_time_to_window():
    window = (T0, T0 + timedelta(hours=1))
    # Track ends 90 minutes before the window opens.
    track = _track("A", [(-120, 28.40, -90.12), (-90, 28.41, -90.11)])
    result = filters.temporal_filter(track, window)
    assert result.present_during_window is False
    assert result.time_to_window_minutes == pytest.approx(90.0, abs=1.0)


# -- Step 3: trajectory compatibility ----------------------------------------

def test_trajectory_compatible_with_a_matching_drift_bearing():
    """A vessel steaming along the same bearing the observed slick drifted on
    is compatible; a perpendicular vessel is not."""
    track = _track("A", [(0, 28.40, -90.12), (30, 28.44, -90.08)], cog=45.0)
    result = filters.trajectory_compatibility(track, drift_bearing_deg=45.0)
    assert result.consistency_score > 0.8


def test_trajectory_incompatible_with_a_perpendicular_bearing():
    # Track physically runs due south (bearing ~180), perpendicular to a
    # drift bearing of 90 (due east) — the track's own geometry must drive
    # the score, not merely differ in COG from the earlier test.
    track = _track("A", [(0, 28.44, -90.10), (30, 28.40, -90.10)])
    result = filters.trajectory_compatibility(track, drift_bearing_deg=90.0)
    assert result.consistency_score < 0.5


def test_trajectory_compatibility_uses_the_tracks_own_bearing_not_just_cog():
    """Track geometry (start->end bearing) is the ground truth; a reported COG
    that disagrees with the track's own shape should not fool the score."""
    # Track physically moves along ~45 deg regardless of what COG claims.
    track = _track("A", [(0, 28.40, -90.12), (30, 28.44, -90.08)], cog=200.0)
    result = filters.trajectory_compatibility(track, drift_bearing_deg=45.0)
    assert result.track_bearing_deg == pytest.approx(45.0, abs=15.0)


# -- Step 4: behaviour analysis ----------------------------------------------

def test_ais_gaps_are_detected_as_a_behaviour_indicator():
    track = _track("A", [(0, 28.40, -90.12), (90, 28.50, -90.00)])  # 90 min gap
    b = filters.behaviour_analysis(track, gap_threshold_minutes=30.0)
    assert b.ais_gaps
    assert b.ais_gaps[0].duration_minutes == pytest.approx(90.0)


def test_speed_anomaly_detected_for_a_sudden_speed_change():
    pts = [(0, 28.40, -90.12, 8.0), (10, 28.412, -90.118, 8.0), (20, 28.60, -90.00, 35.0)]
    track = ais_ingest.reconstruct_track([
        ais_ingest.AISPosition(mmsi="A", timestamp=T0 + timedelta(minutes=m), lat=lat, lon=lon,
                                speed_knots=sog, course_deg=90.0)
        for m, lat, lon, sog in pts
    ])
    b = filters.behaviour_analysis(track)
    assert b.speed_anomalies


def test_sudden_course_change_is_detected():
    track = _track("A", [(0, 28.40, -90.12), (10, 28.41, -90.11)], cog=45.0)
    # Manually build a track with a real course reversal between fixes.
    positions = [
        ais_ingest.AISPosition(mmsi="A", timestamp=T0, lat=28.40, lon=-90.12, speed_knots=8.0, course_deg=45.0),
        ais_ingest.AISPosition(mmsi="A", timestamp=T0 + timedelta(minutes=10), lat=28.41, lon=-90.11,
                                speed_knots=8.0, course_deg=220.0),
    ]
    track2 = ais_ingest.reconstruct_track(positions)
    b = filters.behaviour_analysis(track2)
    assert b.course_changes
    assert b.course_changes[0]["change_deg"] > 90


def test_unexpected_stop_is_detected():
    """A sustained low-speed run (>= STOP_MIN_MINUTES) is flagged; the
    duration must actually clear the module's own threshold."""
    positions = [
        ais_ingest.AISPosition(mmsi="A", timestamp=T0, lat=28.40, lon=-90.12, speed_knots=8.0, course_deg=45.0),
        ais_ingest.AISPosition(mmsi="A", timestamp=T0 + timedelta(minutes=10), lat=28.401, lon=-90.119,
                                speed_knots=0.2, course_deg=45.0),
        ais_ingest.AISPosition(mmsi="A", timestamp=T0 + timedelta(minutes=20), lat=28.402, lon=-90.118,
                                speed_knots=0.1, course_deg=45.0),
        ais_ingest.AISPosition(mmsi="A", timestamp=T0 + timedelta(minutes=30), lat=28.4021, lon=-90.1179,
                                speed_knots=0.1, course_deg=45.0),
    ]
    track = ais_ingest.reconstruct_track(positions)
    b = filters.behaviour_analysis(track)
    assert b.stops
    assert b.stops[0]["duration_minutes"] >= filters.STOP_MIN_MINUTES


def test_trajectory_deviation_is_detected_for_an_erratic_track():
    """A track that zig-zags relative to its own overall bearing should be
    flagged; a straight one should not."""
    straight = _track("A", [(0, 28.40, -90.12), (10, 28.41, -90.11), (20, 28.42, -90.10), (30, 28.43, -90.09)])
    zigzag_positions = [
        ais_ingest.AISPosition(mmsi="B", timestamp=T0 + timedelta(minutes=m), lat=lat, lon=lon,
                                speed_knots=8.0, course_deg=0.0)
        for m, lat, lon in [
            (0, 28.40, -90.14), (10, 28.41, -90.10), (20, 28.42, -90.14),
            (30, 28.43, -90.10), (40, 28.44, -90.12),
        ]
    ]
    zigzag = ais_ingest.reconstruct_track(zigzag_positions)

    b_straight = filters.behaviour_analysis(straight)
    b_zigzag = filters.behaviour_analysis(zigzag)
    assert b_zigzag.deviation_score > b_straight.deviation_score


def test_deviation_score_is_high_for_a_there_and_back_track():
    """Edge case: a track with near-zero NET displacement (it travelled a
    long way but ended up back where it started) is not 'no signal' — it is
    the most erratic possible track, and must score high via the
    path-inefficiency term even though there is no meaningful net bearing
    for the leg-divergence term to compare against."""
    positions = [
        ais_ingest.AISPosition(mmsi="B", timestamp=T0 + timedelta(minutes=m), lat=lat, lon=lon,
                                speed_knots=8.0, course_deg=0.0)
        for m, lat, lon in [
            (0, 28.40, -90.12), (10, 28.44, -90.12), (20, 28.40, -90.12),
            (30, 28.44, -90.12), (40, 28.40, -90.12),
        ]
    ]
    track = ais_ingest.reconstruct_track(positions)
    b = filters.behaviour_analysis(track)
    # A perfect there-and-back sits exactly at the inefficiency formula's
    # midpoint (net_dist=0 -> inefficiency=0.5); clearly above a straight
    # track's near-zero score either way.
    assert b.deviation_score >= 0.5


def test_behaviour_analysis_never_labels_a_vessel_suspicious():
    """Acceptance: use candidate / investigation lead / evidence / anomaly.
    Never 'suspect', 'guilty', 'culprit'."""
    track = _track("A", [(0, 28.40, -90.12), (90, 28.50, -90.00)])
    b = filters.behaviour_analysis(track)
    import json
    blob = json.dumps(b.__dict__, default=str).lower()
    for banned in ("suspicious", "suspect", "guilty", "culprit"):
        assert banned not in blob


def test_isolation_forest_is_optional_and_off_by_default():
    """Acceptance: Isolation Forest may be added only as an optional
    secondary detector — never required, never the primary signal."""
    track = _track("A", [(0, 28.40, -90.12), (10, 28.41, -90.11), (20, 28.42, -90.10)])
    b = filters.behaviour_analysis(track)
    assert b.anomaly_model_score is None  # not run unless explicitly requested

    b2 = filters.behaviour_analysis(track, use_isolation_forest=True)
    assert b2.anomaly_model_score is not None
    assert 0.0 <= b2.anomaly_model_score <= 1.0
