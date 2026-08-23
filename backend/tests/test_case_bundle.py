"""Phase 1 acceptance tests for the frozen case bundle.

These assert the properties every downstream phase depends on. If the bundle is
rebuilt and one of these fails, Phases 2-4 are being developed against a case
that cannot actually demonstrate the pipeline.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

CASE = Path(__file__).resolve().parents[2] / "data" / "case"

pytestmark = pytest.mark.skipif(
    not (CASE / "case.json").exists(),
    reason="case bundle not built — run scripts/build_case.py",
)


@pytest.fixture(scope="module")
def meta():
    return json.loads((CASE / "case.json").read_text())


@pytest.fixture(scope="module")
def ais():
    import pandas as pd
    return pd.read_parquet(CASE / "ais.parquet")


def test_bundle_is_complete(meta):
    for key, name in meta["files"].items():
        if name:
            assert (CASE / name).exists(), f"{key} missing: {name}"


def test_every_source_declares_whether_it_is_real(meta):
    assert meta["sources"]
    for s in meta["sources"]:
        assert "is_synthetic" in s
        if s["is_synthetic"]:
            assert s["note"], f"synthetic source {s['name']} must explain itself"


def test_official_sources_are_actually_real(meta):
    """The two sources the problem statement names must not be substituted."""
    real = {s["name"] for s in meta["sources"] if not s["is_synthetic"]}
    assert any("Zenodo" in n for n in real), "official SAR dataset must be real"
    assert any("AccessAIS" in n for n in real), "official AIS source must be real"


def test_origin_lies_inside_the_case_bbox(meta):
    """If the origin falls outside the region there is no AIS coverage there and
    Stage 3 has nothing to search."""
    b, (lon, lat) = meta["bbox"], meta["ground_truth"]["origin"]
    assert b["west"] < lon < b["east"], f"origin lon {lon} outside [{b['west']}, {b['east']}]"
    assert b["south"] < lat < b["north"], f"origin lat {lat} outside [{b['south']}, {b['north']}]"


def test_origin_is_well_inside_not_on_the_edge(meta):
    """It must be far enough in that a 25 km attribution radius is not clipped."""
    b, (lon, lat) = meta["bbox"], meta["ground_truth"]["origin"]
    margin_km = min(
        (lon - b["west"]) * 97.8, (b["east"] - lon) * 97.8,
        (lat - b["south"]) * 110.6, (b["north"] - lat) * 110.6,
    )
    assert margin_km > 20, f"origin only {margin_km:.1f} km from the bbox edge"


def test_slick_area_is_credible_for_one_vessel(meta):
    """A 188 km2 slick implies a Deepwater-Horizon-scale blowout, not a
    discharge, and would undermine the whole attribution premise."""
    assert 2.0 < meta["slick"]["area_km2"] < 60.0


def test_slick_is_elongated_like_an_underway_discharge(meta):
    s = meta["slick"]
    span = math.dist(s["end_a"], s["end_b"])
    assert span > 0.15, "trail should span a meaningful distance in degrees"


def test_ais_contains_real_traffic_not_only_the_injected_vessel(ais, meta):
    gt = meta["ground_truth"]["polluter_mmsi"]
    others = ais[ais.MMSI != gt]
    assert others.MMSI.nunique() > 50, "need a realistic traffic background to filter down from"


def test_polluter_is_present_and_has_its_gap(ais, meta):
    import pandas as pd
    gt = meta["ground_truth"]["polluter_mmsi"]
    trk = ais[ais.MMSI == gt].sort_values("BaseDateTime")
    assert len(trk) > 100, "polluter track too sparse"
    dt = trk.BaseDateTime.diff().dt.total_seconds().div(60)
    assert dt.max() >= meta["ground_truth"]["polluter_gap_minutes"] - 1, "AIS gap not present"


def test_polluter_reported_positions_never_reach_the_origin(ais, meta):
    """The dark-vessel signature. The vessel goes silent across the release
    window, so at ~11.5 kn its nearest REPORTED fix is still well away from the
    origin. Naive "AIS track intersects the slick" matching therefore misses it
    entirely — which is exactly the gap Stage 3 exists to close."""
    gt = meta["ground_truth"]
    trk = ais[ais.MMSI == gt["polluter_mmsi"]]
    lon0, lat0 = gt["origin"]
    d = np.hypot((trk.LON - lon0) * 97.8, (trk.LAT - lat0) * 110.6)
    assert d.min() > 8.0, "the gap should leave a real hole in the reported track"


def test_polluter_interpolated_path_passes_through_the_origin(ais, meta):
    """Interpolating across the gap — what Stage 3 actually does — must put the
    vessel at the origin, or the ground truth is not recoverable at all."""
    gt = meta["ground_truth"]
    trk = ais[ais.MMSI == gt["polluter_mmsi"]].sort_values("BaseDateTime")
    lon0, lat0 = gt["origin"]

    dt = trk.BaseDateTime.diff().dt.total_seconds().div(60)
    i = int(dt.values.argmax())            # the gap sits between i-1 and i
    a, b = trk.iloc[i - 1], trk.iloc[i]

    f = np.linspace(0, 1, 200)
    lon = a.LON + f * (b.LON - a.LON)
    lat = a.LAT + f * (b.LAT - a.LAT)
    d = np.hypot((lon - lon0) * 97.8, (lat - lat0) * 110.6)
    assert d.min() < 3.0, (
        f"interpolated path misses the origin by {d.min():.1f} km — ground truth unrecoverable"
    )


def test_real_traffic_exists_near_the_origin(ais, meta):
    """Otherwise the ranked list is the injected vessel alone, which proves
    nothing about filtering."""
    gt = meta["ground_truth"]
    others = ais[ais.MMSI != gt["polluter_mmsi"]]
    lon0, lat0 = gt["origin"]
    d = np.hypot((others.LON - lon0) * 97.8, (others.LAT - lat0) * 110.6)
    near = others[d < 25.0]
    assert near.MMSI.nunique() >= 3, (
        f"only {near.MMSI.nunique()} real vessels within 25 km of the origin"
    )


def test_rasters_are_consistent(meta):
    sar = np.load(CASE / "sar_db.npy")
    oil = np.load(CASE / "mask_oil.npy")
    assert sar.shape == oil.shape == (meta["grid"], meta["grid"])
    assert oil.any(), "oil mask is empty"


def test_oil_is_darker_and_smoother_than_open_sea(meta):
    """The physical signature detection depends on. If this fails the rendered
    scene is not testing anything."""
    sar = np.load(CASE / "sar_db.npy")
    oil = np.load(CASE / "mask_oil.npy")
    sea = ~oil
    assert sar[oil].mean() < sar[sea].mean() - 3.0, "oil not appreciably darker"
    assert sar[oil].std() < sar[sea].std(), "oil should damp speckle variance"
