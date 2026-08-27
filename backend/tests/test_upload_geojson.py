"""Phase 2 acceptance — upload a SAR image, get renderable GeoJSON back.

The frozen-case path (/api/detect) has always returned georeferenced polygons.
This covers the *upload* path: an arbitrary supported SAR image goes in, and
candidate regions come back with morphology metadata and real lon/lat GeoJSON,
so the existing MapLibre map can render them without a second code path.

Mock mode is covered too: with no case bundle and no georeferencing, the
endpoint must still answer rather than fail.
"""

import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _synthetic_sar_png() -> bytes:
    """A bright speckled sea with one dark elongated trail through it.

    Deterministic, so a failure is a real regression rather than a reroll.
    """
    rng = np.random.default_rng(42)
    img = rng.normal(180, 12, (512, 512))

    # A long, thin, low-backscatter streak: the shape the detector looks for.
    ys, xs = np.mgrid[0:512, 0:512]
    trail = (np.abs((ys - 256) - 0.35 * (xs - 256)) < 11) & (xs > 90) & (xs < 430)
    img[trail] = rng.normal(70, 6, trail.sum())

    buf = io.BytesIO()
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), mode="L").save(buf, format="PNG")
    return buf.getvalue()


def _post(client, **data):
    return client.post(
        "/api/detect/upload",
        files={"file": ("scene.png", _synthetic_sar_png(), "image/png")},
        data=data,
    )


# -- acceptance -------------------------------------------------------------

def test_upload_produces_candidate_regions(client):
    r = _post(client, method="classical")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["oil_regions"], "no candidate oil regions detected in a synthetic trail scene"


def test_each_candidate_has_morphology_metadata(client):
    body = _post(client, method="classical").json()
    for region in body["oil_regions"] + body["rejected_lookalikes"]:
        m = region["morphology"]
        for field in ("area_km2", "perimeter_km", "length_km", "width_km",
                      "aspect_ratio", "orientation_deg", "compactness", "solidity"):
            assert field in m and m[field] is not None, f"{field} missing"
        for field in ("mean_db", "std_db", "background_db", "contrast_db", "variance_ratio"):
            assert field in region["backscatter"], f"{field} missing"


def test_upload_returns_a_renderable_feature_collection(client):
    """The acceptance criterion: MapLibre can render the detected polygon."""
    body = _post(client, method="classical", lon="-90.0", lat="28.5").json()
    fc = body["geojson"]
    assert fc["type"] == "FeatureCollection"
    assert fc["features"], "no features to render"

    for feature in fc["features"]:
        assert feature["geometry"]["type"] == "Polygon"
        ring = feature["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1], "ring must be closed for MapLibre"
        for lon, lat in ring:
            assert -180.0 <= lon <= 180.0
            assert -90.0 <= lat <= 90.0
        assert feature["properties"]["class"] in ("oil", "lookalike")

    json.dumps(fc)  # must be plain-JSON serialisable


def test_anchoring_moves_the_polygon_to_the_supplied_centre(client):
    """Without georeferencing the caller supplies an anchor; the polygon must
    actually honour it rather than landing at a hardcoded location."""
    a = _post(client, method="classical", lon="-90.0", lat="28.5").json()
    b = _post(client, method="classical", lon="72.8", lat="18.9").json()

    lon_a = a["geojson"]["features"][0]["geometry"]["coordinates"][0][0][0]
    lon_b = b["geojson"]["features"][0]["geometry"]["coordinates"][0][0][0]
    assert abs(lon_a - (-90.0)) < 2.0
    assert abs(lon_b - 72.8) < 2.0


def test_pixel_contours_are_still_returned_for_the_canvas_tool(client):
    """temp-frontend/app.js draws pixel-space contours; don't break it."""
    body = _post(client, method="classical").json()
    region = body["oil_regions"][0]
    assert region["contour"] and len(region["contour"][0]) == 2
    assert "circle" in region


# -- robustness / mock mode -------------------------------------------------

def test_geojson_is_omitted_gracefully_when_no_anchor_is_given(client):
    """No anchor and no georeferencing means no honest lon/lat. The endpoint
    must still return regions rather than inventing coordinates."""
    body = _post(client, method="classical").json()
    assert "geojson" in body
    assert body["geojson"] is None or body["geojson"]["type"] == "FeatureCollection"


def test_rejects_an_unreadable_file(client):
    r = client.post(
        "/api/detect/upload",
        files={"file": ("bad.png", b"not an image", "image/png")},
        data={"method": "classical"},
    )
    assert r.status_code == 400


def test_rejects_a_nonpositive_gsd(client):
    r = _post(client, method="classical", gsd_m="0")
    assert r.status_code == 400


def test_notes_state_the_uncalibrated_assumption(client):
    """Honesty guard: uploaded imagery has no calibrated Sigma0 and the GSD is
    assumed. If that caveat ever disappears, this test fails."""
    body = _post(client, method="classical").json()
    notes = body["notes"].lower()
    assert "assumption" in notes or "assumed" in notes
    assert "sigma0" in notes or "calibrated" in notes


def test_no_fabricated_accuracy_metrics_on_the_upload_path(client):
    """There is no ground truth for an uploaded image, so the response must not
    carry an IoU/recall/precision *value* for it.

    Checks structured fields rather than the raw text, since the notes string
    legitimately mentions accuracy in order to disclaim it.
    """
    body = _post(client, method="classical", lon="-90.0", lat="28.5").json()

    def keys(d):
        for k, v in d.items():
            yield k.lower()
            if isinstance(v, dict):
                yield from keys(v)

    banned = {"detection_iou", "iou", "recall", "precision", "f1", "f1_score", "accuracy"}
    scopes = [body]
    scopes += body["oil_regions"] + body["rejected_lookalikes"]
    scopes += [f["properties"] for f in body["geojson"]["features"]]

    for scope in scopes:
        found = banned & set(keys(scope))
        assert not found, f"{found} reported without ground truth"
