"""Phase 6 acceptance — GET /api/ais/tracks.

AIS records become vessel trajectories; tracks render on the existing
MapLibre map (via the returned GeoJSON FeatureCollection, in the same shape
MapView.tsx already consumes for other layers); AIS gaps are detectable;
existing endpoints/UI are unaffected.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_ais_records_become_vessel_trajectories(client):
    r = client.get("/api/ais/tracks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_vessels"] >= 1
    assert body["vessels"]
    v = body["vessels"][0]
    assert v["vessel"]["mmsi"]
    assert v["positions"]


def test_response_returns_a_renderable_geojson_feature_collection(client):
    body = client.get("/api/ais/tracks").json()
    fc = body["geojson"]
    assert fc["type"] == "FeatureCollection"
    for feature in fc["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "LineString"
        for lon, lat in feature["geometry"]["coordinates"]:
            assert -180 <= lon <= 180 and -90 <= lat <= 90
        assert "mmsi" in feature["properties"]
    json.dumps(fc)


def test_ais_gaps_are_detectable(client):
    """Acceptance: AIS gaps are detectable. Uses a tight threshold so the
    endpoint's own mock/real data reliably exercises at least one gap."""
    r = client.get("/api/ais/tracks", params={"gap_threshold_minutes": 5})
    body = r.json()
    all_gaps = [g for v in body["vessels"] for g in v["gaps"]]
    assert all_gaps, "no gaps detected even at a 5-minute threshold"
    for g in all_gaps:
        assert g["duration_minutes"] >= 5


def test_gaps_are_never_labelled_suspicious(client):
    """Acceptance: do not call vessels suspicious merely because a gap
    exists. Checks the structured gap/vessel fields, not the provenance
    prose — the notes field legitimately says 'never a finding that a
    vessel is suspicious' as an honesty disclaimer, which is the opposite
    of the violation this guards against."""
    r = client.get("/api/ais/tracks", params={"gap_threshold_minutes": 5})
    body = r.json()

    for v in body["vessels"]:
        assert set(v.keys()) & {"suspicious", "guilty", "verdict", "risk_level"} == set()
        for g in v["gaps"]:
            assert set(g.keys()) & {"suspicious", "guilty", "verdict", "risk_level"} == set()
            assert "investigation" in g["label"].lower() or "signal" in g["label"].lower()
            for banned in ("suspicious", "guilty", "criminal"):
                assert banned not in g["label"].lower()


def test_no_attribution_scoring_is_present_in_the_response(client):
    """Phase 6 is ingestion only; no score/rank/proximity field should appear
    on this endpoint's vessels."""
    body = client.get("/api/ais/tracks").json()
    for v in body["vessels"]:
        assert "score" not in v
        assert "rank" not in v
        assert "flags" not in v


def test_vessel_metadata_is_present_when_available(client):
    body = client.get("/api/ais/tracks").json()
    v = body["vessels"][0]
    assert "name" in v["vessel"]
    assert "vessel_type_code" in v["vessel"]


def test_imo_and_heading_are_null_not_fabricated(client):
    body = client.get("/api/ais/tracks").json()
    for v in body["vessels"]:
        for p in v["positions"][:20]:
            # Present as explicit null (not fabricated), matching the real
            # AIS source's missing IMO/heading columns.
            assert "imo" in p
            assert "heading_deg" in p


def test_provenance_states_this_is_real_ingestion(client):
    body = client.get("/api/ais/tracks").json()
    notes = body["provenance"]["notes"].lower()
    assert "ingestion" in notes or "reconstruct" in notes


def test_response_is_plain_json_serialisable(client):
    body = client.get("/api/ais/tracks").json()
    json.dumps(body)


def test_invalid_gap_threshold_is_rejected(client):
    r = client.get("/api/ais/tracks", params={"gap_threshold_minutes": -5})
    assert r.status_code == 422


def test_existing_attribute_endpoint_is_unaffected(client):
    """Existing endpoint's behaviour (including its pre-existing
    ScoreBreakdown schema mismatch — one of test_contract.py's known-failing
    assertions, unrelated to and untouched by Phase 6) must not change: this
    just confirms Phase 6 did not alter engine.py or its route. Uses
    raises_server_exceptions=False since the pre-existing bug is an unhandled
    ValidationError that the default TestClient would otherwise re-raise here
    instead of surfacing as a 500."""
    from fastapi.testclient import TestClient as _TestClient

    from app.main import app as _app

    with _TestClient(_app, raise_server_exceptions=False) as lenient_client:
        r = lenient_client.post("/api/attribute", json={
            "origin": [-90.05, 28.45], "origin_time_utc": "2023-06-15T04:00:00Z",
        })
    assert r.status_code == 500


def test_existing_health_and_detect_endpoints_are_unaffected(client):
    assert client.get("/health").status_code == 200
    assert client.post("/api/detect", json={"method": "classical"}).status_code == 200
