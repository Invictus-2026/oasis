"""Phase 3 acceptance — the environmental data query API.

For a selected incident and time range the backend must return environmental
fields, normalised into the shared EnvironmentalData type, with mock data
served when real data is unavailable.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Inside the frozen case bbox.
LON, LAT = -90.05, 28.45
T0 = "2023-06-15T12:00:00Z"
T1 = "2023-06-15T18:00:00Z"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# -- point query ------------------------------------------------------------

def test_point_query_returns_a_normalised_sample(client):
    r = client.get("/api/environment", params={"lon": LON, "lat": LAT, "time": T0})
    assert r.status_code == 200, r.text
    body = r.json()

    sample = body["samples"][0]
    for field in ("lon", "lat", "time_utc", "u_current_ms", "v_current_ms",
                  "u_wind_ms", "v_wind_ms", "current_speed_ms", "wind_speed_ms"):
        assert field in sample, f"{field} missing from the normalised sample"


def test_point_query_echoes_the_requested_location(client):
    r = client.get("/api/environment", params={"lon": LON, "lat": LAT, "time": T0})
    s = r.json()["samples"][0]
    assert s["lon"] == pytest.approx(LON)
    assert s["lat"] == pytest.approx(LAT)


def test_response_names_its_provider_and_says_if_synthetic(client):
    """Provenance is the house rule: every number says where it came from."""
    body = client.get("/api/environment", params={"lon": LON, "lat": LAT, "time": T0}).json()
    assert body["provider"]
    assert isinstance(body["is_synthetic"], bool)
    assert body["provenance"]["model_version"]


# -- time range -------------------------------------------------------------

def test_time_range_returns_a_series(client):
    r = client.get("/api/environment", params={
        "lon": LON, "lat": LAT, "start": T0, "end": T1, "step_hours": 2.0,
    })
    assert r.status_code == 200, r.text
    samples = r.json()["samples"]
    assert len(samples) == 4  # 12:00, 14:00, 16:00, 18:00
    assert samples[0]["time_utc"].startswith("2023-06-15T12:00")


def test_time_range_is_ordered(client):
    samples = client.get("/api/environment", params={
        "lon": LON, "lat": LAT, "start": T0, "end": T1, "step_hours": 1.0,
    }).json()["samples"]
    times = [s["time_utc"] for s in samples]
    assert times == sorted(times)


def test_inverted_range_is_rejected(client):
    r = client.get("/api/environment", params={
        "lon": LON, "lat": LAT, "start": T1, "end": T0, "step_hours": 1.0,
    })
    assert r.status_code == 400


def test_absurd_step_count_is_rejected(client):
    """Guard against a request that would materialise millions of samples."""
    r = client.get("/api/environment", params={
        "lon": LON, "lat": LAT,
        "start": "2023-01-01T00:00:00Z", "end": "2030-01-01T00:00:00Z",
        "step_hours": 0.01,
    })
    assert r.status_code == 400


def test_missing_time_defaults_to_the_case_acquisition(client):
    """A query with no time at all must still answer rather than 422."""
    r = client.get("/api/environment", params={"lon": LON, "lat": LAT})
    assert r.status_code == 200


# -- incident query ---------------------------------------------------------

def test_incident_query_resolves_location_from_the_case(client):
    """Acceptance: 'for a selected incident ... return environmental fields'."""
    r = client.get("/api/environment", params={"incident_id": "gom-2023-06-15"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["samples"]
    assert body["incident_id"] == "gom-2023-06-15"


def test_unknown_incident_is_rejected(client):
    r = client.get("/api/environment", params={"incident_id": "no-such-case"})
    assert r.status_code == 404


def test_query_without_location_or_incident_is_rejected(client):
    r = client.get("/api/environment")
    assert r.status_code == 400


def test_out_of_range_coordinates_are_rejected(client):
    r = client.get("/api/environment", params={"lon": 999.0, "lat": 28.0, "time": T0})
    assert r.status_code == 422


# -- mock fallback ----------------------------------------------------------

def test_mock_mode_still_answers(client, monkeypatch):
    """Acceptance: mock data works when real data is unavailable."""
    from app.core import config

    monkeypatch.setattr(config, "ENV_DATA_MODE", "mock", raising=False)
    r = client.get("/api/environment", params={"lon": LON, "lat": LAT, "time": T0})
    assert r.status_code == 200
    body = r.json()
    assert body["samples"]
    assert body["is_synthetic"] is True
    assert "mock" in body["provider"].lower()


def test_real_provider_is_not_described_as_a_fallback(client):
    """'synthetic values' and 'the mock fallback' are different facts.

    The frozen case's forcing field is itself synthesised, so the real
    case-bundle provider legitimately reports is_synthetic=True — but calling
    that the fallback would misrepresent which provider actually served the
    request.
    """
    body = client.get("/api/environment", params={"lon": LON, "lat": LAT, "time": T0}).json()
    notes = body["provenance"]["notes"].lower()
    if body["provider"] != "mock-synthetic":
        assert "fallback" not in notes, "a real provider must not be labelled a fallback"
        assert body["provider"] in notes


def test_providers_endpoint_reports_what_is_available(client):
    r = client.get("/api/environment/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["active"]
    names = [p["name"] for p in body["providers"]]
    assert any("mock" in n.lower() for n in names), "mock fallback must always be listed"
    for p in body["providers"]:
        assert isinstance(p["available"], bool)


def test_response_is_plain_json_serialisable(client):
    """numpy floats from the interpolator must not leak into the payload."""
    body = client.get("/api/environment", params={
        "lon": LON, "lat": LAT, "start": T0, "end": T1, "step_hours": 3.0,
    }).json()
    json.dumps(body)


def test_existing_endpoints_are_unaffected(client):
    """Phase 3 adds a parallel subsystem; it must not disturb the pipeline."""
    assert client.get("/health").status_code == 200
    assert client.post("/api/detect", json={"method": "classical"}).status_code == 200
