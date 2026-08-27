"""
Phase 6 — AIS ingestion and vessel-track reconstruction.

Turns raw AIS records (data/case/ais.parquet: MMSI, BaseDateTime, LAT, LON,
SOG, COG, VesselName, VesselType — the actual columns the real NOAA
AccessAIS-derived source ships) into normalised positions, grouped by vessel,
chronologically ordered, reconstructed into a track with a GeoJSON LineString,
and screened for reporting gaps.

This module does ingestion and reconstruction ONLY. It computes no proximity,
heading-consistency, or suspicion score — that is attribution/engine.py's job
(Stage 3 scoring) and is untouched here. A gap detected by this module is a
plain geometric/temporal fact (how long, whether it overlaps a stated time
window); it is never labelled suspicious, and nothing here decides whether a
vessel is a candidate polluter.

Pipeline, in order:

    1. parse()              raw DataFrame -> list[AISPosition], honestly None
                             for fields the source does not carry (IMO,
                             true heading — see module docstring below)
    2. group_by_mmsi()      positions grouped per vessel
    3. (sorting is part of group_by_mmsi/reconstruct_track — see there)
    4. reconstruct_track()  ordered positions -> VesselTrack (LineString +
                             interpolated segments where geometrically sound)
    5. (interpolation is part of reconstruct_track — see _interpolate_gap)
    6. detect_gaps()        reporting gaps above a threshold, as AISGap facts
    7. build_vessel()       static metadata (name, type) from the positions
    8. VesselTrack.to_geojson_feature() / to_feature_collection()

    ingest()                 runs 1-7 for every vessel in one raw DataFrame
    to_feature_collection()  every vessel's track as one GeoJSON FeatureCollection
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

KM_PER_DEG_LAT = 110.574

# A gap is only reported to the caller when a vessel goes silent for at least
# this long. Matches app.core.config.AIS_GAP_THRESHOLD_MINUTES's existing
# value so this module's default agrees with the rest of the codebase without
# importing config (keeps this module usable standalone/in tests).
DEFAULT_GAP_THRESHOLD_MINUTES = 30.0

# Interpolation plausibility bounds. A straight-line fill between two real
# fixes is only drawn when it implies a physically ordinary transit — not a
# claim about what the vessel actually did, just a geometrically reasonable
# guess for a rendering gap. Outside these bounds the segment is left
# unfilled and, if long enough, surfaced instead as an AISGap.
MAX_INTERPOLATION_GAP_MINUTES = 60.0
MAX_PLAUSIBLE_SPEED_KNOTS = 40.0  # generous ceiling; fast ferries run ~35kn


def _km_per_deg_lon(lat: float) -> float:
    return 111.320 * math.cos(math.radians(lat))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dx = (lon2 - lon1) * _km_per_deg_lon((lat1 + lat2) / 2.0)
    dy = (lat2 - lat1) * KM_PER_DEG_LAT
    return math.hypot(dx, dy)


@dataclass(frozen=True)
class AISPosition:
    """One normalised AIS broadcast. Matches the fields listed in the Phase 6
    spec; `imo` and `heading_deg` are None whenever the source does not carry
    them, never fabricated — the real case bundle's AIS source has neither.

    `name`/`vessel_type_code` ride along on the position (real AIS position
    reports repeat a vessel's static data on most broadcasts) so vessel
    metadata association (stage 7) needs no separate join back to the raw
    rows.
    """

    mmsi: str
    timestamp: datetime
    lat: float
    lon: float
    speed_knots: float | None
    course_deg: float | None
    heading_deg: float | None = None
    imo: str | None = None
    name: str | None = None
    vessel_type_code: int | None = None


@dataclass
class AISGap:
    """A reporting gap: two consecutive real fixes further apart in time than
    the threshold. A plain fact about transmission, not a judgement — see
    module docstring. `label` is deliberately phrased as an investigation
    signal, never an accusation."""

    start_utc: datetime
    end_utc: datetime
    duration_minutes: float
    interpolated_path: dict | None
    overlaps_origin_window: bool = False
    label: str = "AIS reporting gap — investigation signal, not a finding of wrongdoing"


@dataclass
class Vessel:
    """Static metadata associated with an MMSI, read off its own broadcasts —
    AIS carries this in every position report (or the voyage/static message,
    where the source has it), not a separate registry lookup."""

    mmsi: str
    name: str | None
    vessel_type_code: int | None
    imo: str | None = None


@dataclass
class VesselTrack:
    """The reconstructed path for one vessel: real fixes in order, plus any
    short gaps bridged with a plausibility-checked straight line."""

    mmsi: str
    positions: list[AISPosition]
    interpolated_segments: list[dict] = field(default_factory=list)

    @property
    def linestring(self) -> dict:
        return {
            "type": "LineString",
            "coordinates": [[p.lon, p.lat] for p in self.positions],
        }

    def to_geojson_feature(self, mmsi: str, name: str | None) -> dict:
        return {
            "type": "Feature",
            "geometry": self.linestring,
            "properties": {
                "mmsi": mmsi,
                "name": name,
                "n_positions": len(self.positions),
                "first_fix_utc": self.positions[0].timestamp.isoformat(),
                "last_fix_utc": self.positions[-1].timestamp.isoformat(),
                "n_interpolated_segments": len(self.interpolated_segments),
            },
        }


@dataclass
class VesselIngestResult:
    vessel: Vessel
    positions: list[AISPosition]
    track: VesselTrack | None
    gaps: list[AISGap]


# ---------------------------------------------------------------------------
# 1. Parsing
# ---------------------------------------------------------------------------

# Raw-column -> normalised-field map. Matches data/case/ais.parquet exactly;
# a future real-time feed with different column names is a map change here,
# not a rewrite of the pipeline.
_COLUMN_MAP = {
    "mmsi": "MMSI",
    "timestamp": "BaseDateTime",
    "lat": "LAT",
    "lon": "LON",
    "speed_knots": "SOG",
    "course_deg": "COG",
    "name": "VesselName",
    "vessel_type_code": "VesselType",
    # Not present in the real source; read only if a future feed supplies them.
    "imo": "IMO",
    "heading_deg": "Heading",
}


def parse(raw: pd.DataFrame) -> list[AISPosition]:
    """Stage 1 — raw AIS rows to normalised AISPosition records.

    Rows with no MMSI, no timestamp, or coordinates outside valid lon/lat
    range are dropped rather than kept with garbage values: a broken fix is
    worse than a missing one for everything downstream (track geometry, gap
    timing). `imo`/`heading_deg` are read from the source when present and
    left None otherwise — never fabricated.
    """
    if raw is None or len(raw) == 0:
        return []

    has_imo = "IMO" in raw.columns
    has_heading = "Heading" in raw.columns

    positions: list[AISPosition] = []
    for row in raw.itertuples(index=False):
        r = row._asdict()
        mmsi = r.get(_COLUMN_MAP["mmsi"])
        ts = r.get(_COLUMN_MAP["timestamp"])
        lat = r.get(_COLUMN_MAP["lat"])
        lon = r.get(_COLUMN_MAP["lon"])

        if mmsi is None or (isinstance(mmsi, float) and math.isnan(mmsi)):
            continue
        if ts is None or pd.isna(ts):
            continue
        if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
            continue
        lat, lon = float(lat), float(lon)
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue

        ts = pd.Timestamp(ts).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        speed = r.get(_COLUMN_MAP["speed_knots"])
        course = r.get(_COLUMN_MAP["course_deg"])
        name = r.get(_COLUMN_MAP["name"])
        vtype = r.get(_COLUMN_MAP["vessel_type_code"])

        positions.append(AISPosition(
            mmsi=str(mmsi),
            timestamp=ts,
            lat=lat,
            lon=lon,
            speed_knots=float(speed) if speed is not None and not pd.isna(speed) else None,
            course_deg=float(course) if course is not None and not pd.isna(course) else None,
            heading_deg=(
                float(r["Heading"]) if has_heading and pd.notna(r.get("Heading")) else None
            ),
            imo=(str(r["IMO"]) if has_imo and pd.notna(r.get("IMO")) else None),
            name=str(name) if name is not None and pd.notna(name) else None,
            vessel_type_code=int(vtype) if vtype is not None and pd.notna(vtype) else None,
        ))

    return positions


# ---------------------------------------------------------------------------
# 2 + 3. Grouping and chronological sorting
# ---------------------------------------------------------------------------

def group_by_mmsi(positions: list[AISPosition]) -> dict[str, list[AISPosition]]:
    """Stage 2 + 3 — one chronologically sorted list per vessel."""
    grouped: dict[str, list[AISPosition]] = defaultdict(list)
    for p in positions:
        grouped[p.mmsi].append(p)
    return {mmsi: sorted(pts, key=lambda p: p.timestamp) for mmsi, pts in grouped.items()}


# ---------------------------------------------------------------------------
# 4 + 5. Track reconstruction, with plausibility-gated interpolation
# ---------------------------------------------------------------------------

def _interpolate_gap(a: AISPosition, b: AISPosition) -> dict | None:
    """A straight-line fill between two consecutive fixes, IF AND ONLY IF the
    implied transit is scientifically plausible: short enough in time, and
    not requiring a speed no real vessel sustains.

    This is explicitly a rendering/geometric convenience, not a claim about
    the vessel's actual path — real AIS tracks are rarely perfectly straight.
    Long or implausible gaps are left un-bridged; detect_gaps() surfaces them
    as an honest gap instead of a fabricated line.
    """
    dt_minutes = (b.timestamp - a.timestamp).total_seconds() / 60.0
    if dt_minutes <= 0 or dt_minutes > MAX_INTERPOLATION_GAP_MINUTES:
        return None

    dist_km = _haversine_km(a.lat, a.lon, b.lat, b.lon)
    implied_speed_knots = dist_km / 1.852 / (dt_minutes / 60.0) if dt_minutes > 0 else 0.0
    if implied_speed_knots > MAX_PLAUSIBLE_SPEED_KNOTS:
        return None

    return {
        "start_utc": a.timestamp,
        "end_utc": b.timestamp,
        "path": {"type": "LineString", "coordinates": [[a.lon, a.lat], [b.lon, b.lat]]},
        "implied_speed_knots": round(implied_speed_knots, 2),
    }


def reconstruct_track(positions: list[AISPosition]) -> VesselTrack:
    """Stage 4 + 5 — chronological fixes into a LineString track, with short,
    plausible gaps bridged by a straight-line interpolated segment.

    Requires at least two positions: a single fix has no track to draw.
    """
    if len(positions) < 2:
        raise ValueError("reconstruct_track needs at least two positions")

    ordered = sorted(positions, key=lambda p: p.timestamp)
    segments = [
        seg for a, b in zip(ordered, ordered[1:])
        if (seg := _interpolate_gap(a, b)) is not None
    ]
    return VesselTrack(mmsi=ordered[0].mmsi, positions=ordered, interpolated_segments=segments)


# ---------------------------------------------------------------------------
# 6. Gap detection
# ---------------------------------------------------------------------------

def detect_gaps(
    positions: list[AISPosition],
    threshold_minutes: float = DEFAULT_GAP_THRESHOLD_MINUTES,
    origin_window: tuple[datetime, datetime] | None = None,
) -> list[AISGap]:
    """Stage 6 — every consecutive pair of fixes further apart than
    `threshold_minutes`, reported as a plain fact.

    `origin_window`, if given, only sets `overlaps_origin_window` — a
    geometric/temporal overlap check the caller (attribution scoring, in a
    later phase) can read. It does not change whether a gap is reported, and
    it never becomes a suspicion label; see module docstring.
    """
    ordered = sorted(positions, key=lambda p: p.timestamp)
    gaps: list[AISGap] = []

    for a, b in zip(ordered, ordered[1:]):
        dt_minutes = (b.timestamp - a.timestamp).total_seconds() / 60.0
        if dt_minutes < threshold_minutes:
            continue

        overlaps = False
        if origin_window is not None:
            w_start, w_end = origin_window
            overlaps = a.timestamp <= w_end and b.timestamp >= w_start

        seg = _interpolate_gap(a, b)  # may legitimately be None for a long gap
        gaps.append(AISGap(
            start_utc=a.timestamp,
            end_utc=b.timestamp,
            duration_minutes=round(dt_minutes, 1),
            interpolated_path=seg["path"] if seg else None,
            overlaps_origin_window=overlaps,
        ))

    return gaps


# ---------------------------------------------------------------------------
# 7. Vessel metadata association
# ---------------------------------------------------------------------------

def build_vessel(mmsi: str, positions: list[AISPosition]) -> Vessel:
    """Stage 7 — static metadata read off the vessel's own broadcasts.

    Takes the most recent non-null name/type/IMO seen across the vessel's
    positions (chronological order assumed, matching group_by_mmsi's output),
    since identity fields are broadcast repeatedly and the latest report is
    the most likely to be accurate/updated.
    """
    name = vtype = imo = None
    for p in positions:  # later positions override earlier ones
        if p.name is not None:
            name = p.name
        if p.vessel_type_code is not None:
            vtype = p.vessel_type_code
        if p.imo is not None:
            imo = p.imo
    return Vessel(mmsi=mmsi, name=name, vessel_type_code=vtype, imo=imo)


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def ingest(
    raw: pd.DataFrame,
    gap_threshold_minutes: float = DEFAULT_GAP_THRESHOLD_MINUTES,
    origin_window: tuple[datetime, datetime] | None = None,
) -> dict[str, VesselIngestResult]:
    """Run every stage for every vessel in one raw AIS DataFrame.

    Vessels with fewer than two valid fixes get `track=None` rather than
    being dropped or crashing the batch — they still appear in the result
    with their positions and metadata.
    """
    positions = parse(raw)
    grouped = group_by_mmsi(positions)

    results: dict[str, VesselIngestResult] = {}
    for mmsi, pts in grouped.items():
        vessel = build_vessel(mmsi, pts)
        track = reconstruct_track(pts) if len(pts) >= 2 else None
        gaps = detect_gaps(pts, gap_threshold_minutes, origin_window)
        results[mmsi] = VesselIngestResult(vessel=vessel, positions=pts, track=track, gaps=gaps)

    return results


def to_feature_collection(results: dict[str, VesselIngestResult]) -> dict:
    """Stage 8 — every vessel WITH a reconstructed track as one GeoJSON
    FeatureCollection, ready for the existing MapLibre track layer."""
    features = [
        r.track.to_geojson_feature(mmsi=mmsi, name=r.vessel.name)
        for mmsi, r in results.items()
        if r.track is not None
    ]
    return {"type": "FeatureCollection", "features": features}
