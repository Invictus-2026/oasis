"""Contract tests.

These guard the Phase-0 API shape. When Phases 2-4 swap fixtures for real
implementations, these tests must keep passing unchanged — that is the whole
point of freezing the contract.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ORIGIN_BODY = {
    "origin_region": {"type": "Polygon", "coordinates": [[
        [-90.20, 28.35], [-89.95, 28.35], [-89.95, 28.65], [-90.20, 28.65], [-90.20, 28.35],
    ]]},
    "release_window_start_utc": datetime(2023, 6, 15, 2, 10, tzinfo=timezone.utc).isoformat(),
    "release_window_end_utc": datetime(2023, 6, 15, 6, 10, tzinfo=timezone.utc).isoformat(),
    "drift_bearing_deg": 64.9,
}


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_case_carries_disclaimer_and_provenance():
    c = client.get("/api/case").json()
    assert c["disclaimer"], "the constructed-scenario disclaimer must never be empty"
    assert c["provenance"]["model_version"]
    assert any(s["is_synthetic"] for s in c["sources"]), "synthetic inputs must be declared"


def test_detect_returns_geometry_and_rejected_lookalikes():
    d = client.post("/api/detect", json={}).json()
    assert len(d["slicks"]) >= 1
    g = d["slicks"][0]["geometry"]
    assert g["area_km2"] > 0 and g["perimeter_km"] > 0
    assert 0 < g["compactness"] <= 1
    # Showing what we ruled out pre-answers the look-alike judge question.
    assert len(d["rejected_lookalikes"]) >= 1
    assert all(r["reason"] for r in d["rejected_lookalikes"])


def test_detect_age_is_a_caveated_range():
    age = client.post("/api/detect", json={}).json()["slicks"][0]["age"]
    assert age["min_hours"] < age["max_hours"], "age must be a bracket, never a point estimate"
    assert age["confidence"] == "low"
    assert age["method_note"]


def test_hindcast_produces_a_cone_not_a_pin():
    h = client.post("/api/drift/hindcast", json={"slick_id": "slick-001"}).json()
    assert h["particles_timeline"], "need frames to animate"
    pct = {c["percentile"] for c in h["cone"]}
    assert pct == {50, 90}, "both containment levels are required"
    o = h["origin_estimate"]
    assert o["uncertainty_radius_km"] > 0, "a point estimate with no uncertainty is false precision"
    lo, hi = o["time_window_hours"]
    assert lo < hi


def test_hindcast_frames_run_backward():
    h = client.post("/api/drift/hindcast", json={"slick_id": "slick-001"}).json()
    offsets = [f["t_offset_hours"] for f in h["particles_timeline"]]
    assert min(offsets) < 0 and max(offsets) == 0


def test_forecast_runs_forward_with_a_centroid_path():
    f = client.post("/api/drift/forecast", json={"slick_id": "slick-001", "hours": 12}).json()
    assert max(fr["t_offset_hours"] for fr in f["particles_timeline"]) > 0
    assert f["centroid_path"]["type"] == "LineString"
    assert len(f["centroid_path"]["coordinates"]) >= 2


def test_hindcast_is_deterministic():
    """A cone that jitters between rehearsals will get questioned on stage."""
    body = {"slick_id": "slick-001", "seed": 42}
    a = client.post("/api/drift/hindcast", json=body).json()
    b = client.post("/api/drift/hindcast", json=body).json()
    assert a["origin_estimate"]["point"] == b["origin_estimate"]["point"]


def test_attribution_is_ranked_and_explainable():
    a = client.post("/api/attribute", json=ORIGIN_BODY).json()
    cands = a["candidates"]
    assert cands, "at least one candidate expected"
    assert [c["rank"] for c in cands] == list(range(1, len(cands) + 1))
    assert all(cands[i]["score"] >= cands[i + 1]["score"] for i in range(len(cands) - 1))
    for c in cands:
        assert set(c["breakdown"]) == {
            "origin_proximity", "temporal_compatibility", "trajectory_consistency",
            "behaviour_anomaly", "ais_gap", "counterfactual_similarity",
        }
        for key, v in c["breakdown"].items():
            if v is not None:  # counterfactual_similarity is null outside the top-N
                assert 0 <= v <= 1, f"{key} out of range: {v}"
        assert c["narrative"], "every score needs a human-readable reason"
        assert c["label"] in ("candidate", "investigation lead")


def test_attribution_shows_the_traffic_being_filtered_down():
    a = client.post("/api/attribute", json=ORIGIN_BODY).json()
    assert a["total_vessels_in_region"] >= a["after_filter"] > 0


def test_attribution_flags_a_dark_vessel():
    """The frozen case's injected polluter has a real AIS gap overlapping the
    release window (Phase 6/7); this must surface as DARK_VESSEL."""
    a = client.post("/api/attribute", json=ORIGIN_BODY).json()
    assert any("DARK_VESSEL" in c["flags"] for c in a["candidates"])


def test_attribution_returns_the_weights_it_used():
    """Scoring must be auditable, not magic — no hard-coded percentage."""
    a = client.post("/api/attribute", json=ORIGIN_BODY).json()
    assert abs(sum(a["weights"].values()) - 1.0) < 1e-6


def test_ground_truth_polluter_ranks_first():
    """The acceptance criterion, now genuinely met: real AIS ingestion
    (Phase 6) feeding real spatial/temporal/trajectory/behaviour evidence and
    six-component scoring (Phase 7) — not a fixture ordering — ranks the
    injected ground-truth polluter first. See app/attribution/engine.py."""
    gt = client.get("/api/case").json()["ground_truth"]["polluter_mmsi"]
    a = client.post("/api/attribute", json=ORIGIN_BODY).json()
    assert a["candidates"][0]["mmsi"] == gt


def test_report_states_limitations():
    r = client.post("/api/report", json={"case_id": "gom-2023-06-15", "slick_id": "slick-001"}).json()
    assert len(r["limitations"]) >= 4, "the limitations section is a scoring point, not boilerplate"
    assert r["processing_chain"]


def test_pipeline_run_composes_every_stage():
    p = client.get("/api/pipeline/run").json()
    assert set(p) >= {"case", "detection", "hindcast", "forecast", "attribution"}
