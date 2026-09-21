"""Acceptance tests for the grid A* spill-avoidance routing endpoints
(POST /api/routing/plan, POST /api/routing/replan).

Separate surface from POST /api/vessel/reroute (app/api/reroute.py's
visibility-graph engine) — see app/api/grid_reroute.py and app/routing/ for
the module-level tests covering the search algorithm itself.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _circle(cx: float, cy: float, r: float, n: int = 32) -> dict:
    coords = [
        [cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)]
        for i in range(n)
    ]
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


# Two points inside the frozen case bbox, with a spill sitting between them.
BBOX = config.CASE_BBOX
START = [BBOX["west"] + 0.05, (BBOX["south"] + BBOX["north"]) / 2]
END = [BBOX["east"] - 0.05, (BBOX["south"] + BBOX["north"]) / 2]
SPILL_CENTER = [(BBOX["west"] + BBOX["east"]) / 2, (BBOX["south"] + BBOX["north"]) / 2]


def test_plan_returns_a_route_around_the_spill(client):
    spill = _circle(*SPILL_CENTER, r=0.08)
    resp = client.post("/api/routing/plan", json={
        "start": START, "end": END, "spill_polygons": [spill], "resolution_deg": 0.02,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert len(body["waypoints"]) > 2
    assert body["distance_km"] > 0
    assert body["estimated_time_hours"] > 0
    assert isinstance(body["session_id"], str) and body["session_id"]


def test_plan_with_no_spill_is_direct(client):
    resp = client.post("/api/routing/plan", json={"start": START, "end": END, "spill_polygons": []})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert len(body["waypoints"]) == 2


def test_plan_rejects_point_outside_operating_area(client):
    resp = client.post("/api/routing/plan", json={
        "start": [0.0, 0.0], "end": END, "spill_polygons": [],
    })
    assert resp.status_code == 422


def test_replan_reuses_session_and_reflects_new_spill(client):
    spill = _circle(*SPILL_CENTER, r=0.08)
    plan_resp = client.post("/api/routing/plan", json={
        "start": START, "end": END, "spill_polygons": [spill], "resolution_deg": 0.03,
    })
    session_id = plan_resp.json()["session_id"]

    moved_center = [SPILL_CENTER[0], min(BBOX["north"] - 0.05, SPILL_CENTER[1] + 0.15)]
    moved_spill = _circle(*moved_center, r=0.05)
    vessel_now = plan_resp.json()["waypoints"][min(1, len(plan_resp.json()["waypoints"]) - 1)]

    replan_resp = client.post("/api/routing/replan", json={
        "session_id": session_id,
        "current_position": [vessel_now["lon"], vessel_now["lat"]],
        "spill_polygons": [moved_spill],
    })
    assert replan_resp.status_code == 200
    body = replan_resp.json()
    assert body["found"] is True
    assert body["session_id"] == session_id


def test_replan_unknown_session_is_rejected(client):
    resp = client.post("/api/routing/replan", json={
        "session_id": "does-not-exist", "current_position": START, "spill_polygons": [],
    })
    assert resp.status_code == 404
