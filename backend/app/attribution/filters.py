"""
Phase 7, steps 1-4 — spatial filtering, temporal filtering, trajectory
compatibility, and behaviour analysis.

Operates on `ais_ingest.VesselTrack` objects (Phase 6's real reconstruction
output), not a hardcoded vessel list. Every function here returns a plain
dataclass of transparent, individually-inspectable numbers — no step computes
a final verdict, and nothing here decides which vessel is responsible. A
vessel that passes every filter and every behaviour check is a CANDIDATE with
EVIDENCE, never a "suspect" or "culprit" (see docstrings and the language
checked by tests/test_attribution_filters.py).

Isolation Forest (behaviour_analysis(..., use_isolation_forest=True)) is
strictly optional and off by default: a rule-based `deviation_score` is always
computed and always explainable; the model score, when requested, is an
ADDITIONAL, separately-reported number — never a replacement for the
transparent rules, and never silently blended into them.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.attribution.ais_ingest import AISGap, VesselTrack, detect_gaps

KM_PER_DEG_LAT = 110.574


def _km_per_deg_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dx = (lon2 - lon1) * _km_per_deg_lon((lat1 + lat2) / 2.0)
    dy = (lat2 - lat1) * KM_PER_DEG_LAT
    return math.hypot(dx, dy)


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing lat1,lon1 -> lat2,lon2, degrees clockwise from north."""
    dx = (lon2 - lon1) * _km_per_deg_lon((lat1 + lat2) / 2.0)
    dy = (lat2 - lat1) * KM_PER_DEG_LAT
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two DIRECTIONS, 0-180.

    Use for genuine direction comparisons (a course change, a heading vs a
    direction of travel) where travelling the reverse way is a real
    difference. Do NOT use this for comparing a bearing against an AXIS
    (a slick's elongation orientation, a trail's own line) — see
    _axis_diff below.
    """
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _axis_diff(a: float, b: float) -> float:
    """Smallest difference between two AXES (undirected lines), 0-90.

    A line has no inherent direction: a bearing of 64.9 degrees and one of
    244.9 degrees (its exact reverse) describe the SAME axis — a vessel
    could have travelled it either way. Matches origin_search.py's
    _orientation_similarity, which makes the identical distinction when
    comparing a simulated cloud's elongation axis to an observed slick's
    measured orientation_deg.
    """
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _points_in_poly(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Vectorised even-odd ray casting — same construction used throughout
    this project's drift/detection code (drift/lagrangian.py)."""
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), dtype=bool)
    x1, y1 = poly[:-1, 0], poly[:-1, 1]
    x2, y2 = poly[1:, 0], poly[1:, 1]
    for a, b, c, d in zip(x1, y1, x2, y2):
        cond = (b > y) != (d > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (c - a) * (y - b) / (d - b + 1e-15) + a
        inside ^= cond & (x < xint)
    return inside


# ---------------------------------------------------------------------------
# Step 1: spatial filtering
# ---------------------------------------------------------------------------


@dataclass
class SpatialResult:
    intersects: bool
    min_distance_km: float
    closest_point: tuple[float, float] | None
    closest_time_utc: datetime | None


def spatial_filter(track: VesselTrack, origin_region: dict) -> SpatialResult:
    """Does this vessel's track enter or intersect the origin probability
    region? `origin_region` is a GeoJSON Polygon (e.g. Phase 5's
    origin_search region_50/region_90).

    Reports the minimum distance from any fix to the region's boundary/
    interior even when the track never enters it, since "how close did it
    come" is itself evidence worth keeping, not just a pass/fail gate.
    """
    ring = np.asarray(origin_region["coordinates"][0])
    pts = np.array([[p.lon, p.lat] for p in track.positions])
    inside = _points_in_poly(pts, ring)

    if inside.any():
        idx = int(np.argmax(inside))
        p = track.positions[idx]
        return SpatialResult(
            intersects=True, min_distance_km=0.0,
            closest_point=(p.lon, p.lat), closest_time_utc=p.timestamp,
        )

    # Distance to the nearest ring vertex/edge-ish approximation: nearest
    # vertex distance is a reasonable, cheap bound for a compact polygon
    # (Phase 5's origin regions are small, near-convex containment shapes).
    best_km, best_p = math.inf, None
    for p in track.positions:
        d = min(_haversine_km(p.lat, p.lon, ring[j, 1], ring[j, 0]) for j in range(len(ring)))
        if d < best_km:
            best_km, best_p = d, p

    return SpatialResult(
        intersects=False, min_distance_km=round(best_km, 3),
        closest_point=(best_p.lon, best_p.lat) if best_p else None,
        closest_time_utc=best_p.timestamp if best_p else None,
    )


# ---------------------------------------------------------------------------
# Step 2: temporal filtering
# ---------------------------------------------------------------------------


@dataclass
class TemporalResult:
    present_during_window: bool
    overlap_minutes: float
    time_to_window_minutes: float | None  # None when present; else distance to the window


def temporal_filter(track: VesselTrack, release_window: tuple[datetime, datetime]) -> TemporalResult:
    """Was this vessel actively reporting during the estimated release
    window? `release_window` is typically Phase 5's
    (release_time_utc - age_uncertainty, release_time_utc + age_uncertainty).
    """
    w_start, w_end = release_window
    t_start, t_end = track.positions[0].timestamp, track.positions[-1].timestamp

    overlap_start = max(t_start, w_start)
    overlap_end = min(t_end, w_end)
    overlap_minutes = max(0.0, (overlap_end - overlap_start).total_seconds() / 60.0)

    if overlap_minutes > 0:
        return TemporalResult(present_during_window=True, overlap_minutes=round(overlap_minutes, 1),
                               time_to_window_minutes=None)

    if t_end < w_start:
        gap = (w_start - t_end).total_seconds() / 60.0
    else:
        gap = (t_start - w_end).total_seconds() / 60.0
    return TemporalResult(present_during_window=False, overlap_minutes=0.0,
                           time_to_window_minutes=round(gap, 1))


# ---------------------------------------------------------------------------
# Step 3: trajectory compatibility
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryResult:
    track_bearing_deg: float
    consistency_score: float  # 0-1; 1.0 = the track's own axis runs along the slick's own axis
    nearest_leg_distance_km: float  # closest a track segment comes to the slick's own axis line


def trajectory_compatibility(
    track: VesselTrack,
    drift_bearing_deg: float,
    reference_point: tuple[float, float] | None = None,
) -> TrajectoryResult:
    """Is this vessel's own movement compatible with the inferred spill
    scenario?

    Compares the vessel's track to the OBSERVED SLICK'S OWN axis
    (`drift_bearing_deg` — pass the slick's measured `orientation_deg`, not a
    current/wind drift direction), not to how the oil later drifted under
    wind/current. This distinction matters physically: an underway discharge
    lays down a trail along the VESSEL'S OWN heading at the time, and that
    trail is then carried and reshaped by the current afterward — so the
    slick's drift direction can be, and often is, entirely different from
    both the vessel's heading during discharge AND its heading before/after.
    What is actually diagnostic is whether some segment of the vessel's track
    ran close to and roughly parallel with the slick's own long axis, which
    is what a discharge trail geometrically IS at the moment of release.

    Uses the closest single LEG of the track (not just start->end
    displacement), since a vessel's overall journey may bend well before or
    after passing near the slick's axis — the discharge only has to align
    with one local leg, not the vessel's whole voyage.
    """
    pts = track.positions
    if reference_point is not None:
        ref_lat, ref_lon = reference_point[1], reference_point[0]
    else:
        # No reference point given: fall back to the track's own midpoint, so
        # this still degrades gracefully rather than requiring the caller to
        # always supply the slick's centroid.
        mid = pts[len(pts) // 2]
        ref_lat, ref_lon = mid.lat, mid.lon

    # best_score starts at None (not 0.0): a genuine best leg scoring exactly
    # 0 must still be recorded, or every leg tying at 0 silently reports
    # "-1 km, never evaluated" instead of the real nearest distance — caught
    # by testing against the live case bundle.
    best_score, best_bearing, best_dist = None, 0.0, math.inf
    for a, b in zip(pts, pts[1:]):
        leg_bearing = _bearing_deg(a.lat, a.lon, b.lat, b.lon)
        leg_dist_km = min(
            _haversine_km(a.lat, a.lon, ref_lat, ref_lon),
            _haversine_km(b.lat, b.lon, ref_lat, ref_lon),
        )
        # AXIS comparison, not direction: a vessel travelling either way along
        # the trail's own line is equally compatible with having laid it down.
        angle_score = max(0.0, 1.0 - _axis_diff(leg_bearing, drift_bearing_deg) / 90.0)
        # A leg far from the slick counts for little regardless of how well
        # its bearing matches — proximity gates relevance.
        proximity_score = max(0.0, 1.0 - leg_dist_km / 50.0)
        leg_score = angle_score * proximity_score
        if best_score is None or leg_score > best_score:
            best_score, best_bearing, best_dist = leg_score, leg_bearing, leg_dist_km

    return TrajectoryResult(
        track_bearing_deg=round(best_bearing, 1),
        consistency_score=round(best_score or 0.0, 4),
        nearest_leg_distance_km=round(best_dist, 3) if best_dist != math.inf else -1.0,
    )


# ---------------------------------------------------------------------------
# Step 4: behaviour analysis
# ---------------------------------------------------------------------------


@dataclass
class BehaviourResult:
    ais_gaps: list[AISGap] = field(default_factory=list)
    speed_anomalies: list[dict] = field(default_factory=list)
    course_changes: list[dict] = field(default_factory=list)
    stops: list[dict] = field(default_factory=list)
    deviation_score: float = 0.0  # 0-1; how erratic the track is relative to its own net bearing
    # Strictly optional secondary detector (see module docstring). None means
    # "not requested", never "no anomaly" — the two must not be conflated.
    anomaly_model_score: float | None = None


# Thresholds are stated, not hidden, and surfaced in provenance by the caller
# so every flag traces back to a documented rule.
SPEED_JUMP_KNOTS = 12.0          # a change this large between consecutive fixes is notable
SPEED_JUMP_MIN_KNOTS = 3.0       # below this the "jump" is noise, not a signal
COURSE_CHANGE_DEG = 90.0         # a turn sharper than this between fixes is notable
STOP_SPEED_KNOTS = 0.5           # sustained speed below this counts as stopped
STOP_MIN_MINUTES = 15.0          # must persist this long to count as an "unexpected" stop


def _speed_anomalies(track: VesselTrack) -> list[dict]:
    out = []
    for a, b in zip(track.positions, track.positions[1:]):
        if a.speed_knots is None or b.speed_knots is None:
            continue
        jump = abs(b.speed_knots - a.speed_knots)
        if jump >= SPEED_JUMP_KNOTS and min(a.speed_knots, b.speed_knots) > SPEED_JUMP_MIN_KNOTS:
            out.append({
                "at_utc": b.timestamp.isoformat(), "from_knots": a.speed_knots,
                "to_knots": b.speed_knots, "change_knots": round(jump, 2),
            })
    return out


def _course_changes(track: VesselTrack) -> list[dict]:
    out = []
    for a, b in zip(track.positions, track.positions[1:]):
        if a.course_deg is None or b.course_deg is None:
            continue
        diff = _angle_diff(a.course_deg, b.course_deg)
        if diff >= COURSE_CHANGE_DEG:
            out.append({
                "at_utc": b.timestamp.isoformat(), "from_deg": a.course_deg,
                "to_deg": b.course_deg, "change_deg": round(diff, 1),
            })
    return out


def _stops(track: VesselTrack) -> list[dict]:
    out = []
    run_start = None
    for i, p in enumerate(track.positions):
        stopped = p.speed_knots is not None and p.speed_knots <= STOP_SPEED_KNOTS
        if stopped and run_start is None:
            run_start = i
        elif not stopped and run_start is not None:
            _maybe_record_stop(track.positions, run_start, i - 1, out)
            run_start = None
    if run_start is not None:
        _maybe_record_stop(track.positions, run_start, len(track.positions) - 1, out)
    return out


def _maybe_record_stop(positions, start_idx: int, end_idx: int, out: list[dict]) -> None:
    duration = (positions[end_idx].timestamp - positions[start_idx].timestamp).total_seconds() / 60.0
    if duration >= STOP_MIN_MINUTES:
        out.append({
            "start_utc": positions[start_idx].timestamp.isoformat(),
            "end_utc": positions[end_idx].timestamp.isoformat(),
            "duration_minutes": round(duration, 1),
        })


def _deviation_score(track: VesselTrack) -> float:
    """How erratic the track is, combining two signals so a there-and-back
    track (near-zero net displacement) and a genuine zig-zag (nonzero net
    displacement but legs that swing wide of it) are both caught:

    - INEFFICIENCY: total distance travelled vs. net (start->end)
      displacement. A straight track has a ratio near 1; a track that
      doubles back on itself has a ratio well above 1, up to unboundedly
      large for a perfect there-and-back.
    - LEG DIVERGENCE: the fraction of distance travelled on legs pointing
      more than 60 degrees away from the net bearing — distance-weighted so
      one short erratic hop does not dominate an otherwise straight, long
      track. Requires a nonzero net bearing to be meaningful, so it
      contributes 0 when net displacement is negligible (inefficiency alone
      already captures that case).
    """
    pts = track.positions
    if len(pts) < 3:
        return 0.0

    p0, p1 = pts[0], pts[-1]
    net_dist = _haversine_km(p0.lat, p0.lon, p1.lat, p1.lon)

    total_leg_km, erratic_km = 0.0, 0.0
    net_bearing = _bearing_deg(p0.lat, p0.lon, p1.lat, p1.lon) if net_dist >= 1e-6 else None
    for a, b in zip(pts, pts[1:]):
        leg_km = _haversine_km(a.lat, a.lon, b.lat, b.lon)
        if leg_km < 1e-6:
            continue
        total_leg_km += leg_km
        if net_bearing is not None:
            leg_bearing = _bearing_deg(a.lat, a.lon, b.lat, b.lon)
            if _angle_diff(leg_bearing, net_bearing) > 60.0:
                erratic_km += leg_km

    if total_leg_km < 1e-6:
        return 0.0

    # Ratio-based inefficiency: 0 at path==net_dist, saturating toward 1 as
    # the path grows to roughly 3x the net displacement (a generous bound —
    # even a moderately winding transit rarely triples its direct distance).
    inefficiency = min(1.0, max(0.0, (total_leg_km - net_dist) / (2.0 * total_leg_km))) if total_leg_km > 0 else 0.0
    divergence = erratic_km / total_leg_km

    return round(min(1.0, max(inefficiency, divergence)), 4)


def _isolation_forest_score(track: VesselTrack) -> float:
    """Optional secondary detector (see module docstring). Fits a fresh,
    single-track Isolation Forest over each fix's (speed, course-change,
    inter-fix distance) and reports the fraction of fixes flagged anomalous —
    not a black box left uninterpreted: which fixes were flagged remains
    available on the model, this is just the summary number.

    Raises ImportError with a clear message if scikit-learn is not installed,
    so a caller who explicitly asked for this gets an honest failure rather
    than a silently wrong score.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError as exc:
        raise ImportError(
            "Isolation Forest requested but scikit-learn is not installed; "
            "install it or omit use_isolation_forest=True"
        ) from exc

    pts = track.positions
    if len(pts) < 4:
        return 0.0

    rows = []
    for i, p in enumerate(pts):
        speed = p.speed_knots or 0.0
        course_change = 0.0
        if i > 0 and p.course_deg is not None and pts[i - 1].course_deg is not None:
            course_change = _angle_diff(p.course_deg, pts[i - 1].course_deg)
        dist_km = _haversine_km(pts[i - 1].lat, pts[i - 1].lon, p.lat, p.lon) if i > 0 else 0.0
        rows.append([speed, course_change, dist_km])

    X = np.asarray(rows)
    model = IsolationForest(n_estimators=100, contamination="auto", random_state=42)
    labels = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    return round(float(np.mean(labels == -1)), 4)


def behaviour_analysis(
    track: VesselTrack,
    gap_threshold_minutes: float = 30.0,
    use_isolation_forest: bool = False,
    release_window: tuple[datetime, datetime] | None = None,
) -> BehaviourResult:
    """Step 4 — transparent rule-based behaviour indicators, with an OPTIONAL
    Isolation Forest as a secondary, separately-reported signal.

    Every indicator here is a plain fact about the track (a gap existed, a
    speed jump happened, a course reversed, a stop lasted N minutes) — none
    of it is a suspicion label. Whether these facts move a candidate's rank
    is entirely the caller's (scoring.py's) decision, made transparently.

    `release_window`, if given, is forwarded to detect_gaps() so each gap's
    overlaps_origin_window reflects the ACTUAL estimated release window
    rather than always reading False — omitting it here was a real bug
    caught by testing against the live case bundle (a 96-minute gap that
    genuinely overlaps the true release time was reporting overlap=False).
    """
    return BehaviourResult(
        ais_gaps=detect_gaps(track.positions, threshold_minutes=gap_threshold_minutes,
                              origin_window=release_window),
        speed_anomalies=_speed_anomalies(track),
        course_changes=_course_changes(track),
        stops=_stops(track),
        deviation_score=_deviation_score(track),
        anomaly_model_score=_isolation_forest_score(track) if use_isolation_forest else None,
    )
