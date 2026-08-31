"""Phase 2 — morphology measurement and GeoJSON output tests.

The classical detection chain (Lee filter -> normalisation -> adaptive
threshold -> morphology -> connected components -> contours) already exists and
is covered by test_detection.py. What this file covers is the *characterisation*
half of Phase 2: that every candidate region carries a full morphology record
(area, perimeter, length, width, aspect ratio, orientation, shape, backscatter
statistics) and that regions leave the backend as renderable GeoJSON.

Nothing here asserts a learned-model accuracy figure. The only accuracy claims
in this codebase are the classical detector's IoU/recall/precision measured
against the case bundle's ground-truth mask in test_detection.py.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from app.core.case_store import load_case
from app.detection import classical, geometry, pipeline

CASE = Path(__file__).resolve().parents[2] / "data" / "case"

pytestmark = pytest.mark.skipif(
    not (CASE / "case.json").exists(),
    reason="case bundle not built — run scripts/build_case.py",
)


@pytest.fixture(scope="module")
def bundle():
    return load_case()


@pytest.fixture(scope="module")
def result(bundle):
    return pipeline.run(bundle)


@pytest.fixture(scope="module")
def truth():
    return json.loads((CASE / "case.json").read_text())


# -- morphology completeness ----------------------------------------------

MORPHOLOGY_FIELDS = (
    "area_km2",
    "perimeter_km",
    "length_km",
    "width_km",
    "aspect_ratio",
    "orientation_deg",
    "compactness",
    "solidity",
)


def test_every_candidate_carries_the_full_morphology_record(result):
    """Phase 2 acceptance: each candidate has morphology metadata."""
    assert result.slicks, "no candidate regions produced"
    for slick in result.slicks:
        dumped = slick.geometry.model_dump()
        for field in MORPHOLOGY_FIELDS:
            assert field in dumped, f"{field} missing from SlickGeometry"
            assert dumped[field] is not None, f"{field} is None"


def test_every_candidate_carries_backscatter_statistics(result):
    """Backscatter stats are measured per region and must reach the API."""
    for slick in result.slicks:
        b = slick.backscatter
        assert b is not None, "backscatter block missing"
        for field in ("mean_db", "std_db", "background_db", "contrast_db", "variance_ratio"):
            assert getattr(b, field) is not None, f"{field} missing"


def test_rejected_lookalikes_also_carry_morphology_and_backscatter(result):
    """A rejection is only auditable if its measurements are visible too."""
    assert result.rejected_lookalikes
    for r in result.rejected_lookalikes:
        assert r.geometry is not None
        assert r.backscatter is not None


# -- morphology correctness -------------------------------------------------

def test_length_exceeds_width_for_a_trail(result):
    g = result.slicks[0].geometry
    assert g.length_km > g.width_km, "an underway discharge must be longer than it is wide"


def test_aspect_ratio_is_length_over_width(result):
    g = result.slicks[0].geometry
    assert g.aspect_ratio == pytest.approx(g.length_km / g.width_km, rel=0.02)


def test_aspect_ratio_is_high_for_the_case_study_trail(result):
    """The frozen case is a 26 km underway discharge, not a blob."""
    assert result.slicks[0].geometry.aspect_ratio > 3


def test_length_is_consistent_with_ground_truth(result, truth):
    """Trail length drives the age estimate, so a wrong length is not cosmetic."""
    got = result.slicks[0].geometry.length_km
    exp = truth["slick"].get("length_km")
    if exp is None:
        pytest.skip("case bundle has no length_km ground truth")
    assert abs(got - exp) / exp < 0.30, f"length {got} km vs truth {exp} km"


def test_solidity_is_between_zero_and_one(result):
    for slick in result.slicks:
        assert 0.0 < slick.geometry.solidity <= 1.0


def test_area_and_perimeter_stay_physically_consistent(result):
    """4*pi*A/P^2 <= 1 for any real shape; a violation means mismatched units."""
    for slick in result.slicks:
        g = slick.geometry
        iso = 4 * math.pi * g.area_km2 / (g.perimeter_km ** 2)
        assert iso <= 1.0 + 1e-6, "compactness above 1 implies an area/perimeter unit error"


def test_orientation_is_a_compass_bearing(result):
    for slick in result.slicks:
        assert 0.0 <= slick.geometry.orientation_deg < 180.0


# -- GeoJSON output ---------------------------------------------------------

def test_slick_polygon_is_valid_renderable_geojson(result):
    """MapLibre needs a closed ring of [lon, lat] pairs."""
    for slick in result.slicks:
        poly = slick.polygon
        assert poly["type"] == "Polygon"
        ring = poly["coordinates"][0]
        assert len(ring) >= 4, "a polygon ring needs at least 4 positions when closed"
        assert ring[0] == ring[-1], "ring must be explicitly closed"
        for lon, lat in ring:
            assert -180.0 <= lon <= 180.0
            assert -90.0 <= lat <= 90.0


def test_polygon_falls_inside_the_case_bounding_box(result, bundle):
    b = bundle.bbox
    for slick in result.slicks:
        for lon, lat in slick.polygon["coordinates"][0]:
            assert b["west"] <= lon <= b["east"]
            assert b["south"] <= lat <= b["north"]


def test_feature_collection_is_standards_compliant(result):
    """The whole detection result must serialise to a GeoJSON FeatureCollection
    carrying morphology in feature properties."""
    fc = pipeline.to_feature_collection(result)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == len(result.slicks) + len(result.rejected_lookalikes)

    for feature in fc["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Polygon"
        props = feature["properties"]
        assert props["class"] in ("oil", "lookalike")
        for field in MORPHOLOGY_FIELDS:
            assert field in props, f"{field} missing from feature properties"
        assert "mean_db" in props and "contrast_db" in props

    # Must survive a real JSON round-trip: numpy scalars would break this.
    assert json.loads(json.dumps(fc))["type"] == "FeatureCollection"


# -- ingestion / normalisation ---------------------------------------------

def test_normalise_maps_arbitrary_intensities_to_a_db_like_range():
    """Uploaded imagery has no calibrated Sigma0, so normalisation must put it
    on a comparable relative scale before the detector's thresholds apply."""
    gray = np.linspace(0, 255, 256, dtype=np.float32).reshape(16, 16)
    out = classical.normalise(gray)
    assert out.shape == gray.shape
    assert out.min() >= -60.0 and out.max() <= 10.0
    # Monotonic: darker pixels must stay darker after normalisation.
    assert out.flat[0] < out.flat[-1]


def test_normalise_is_robust_to_outliers():
    """A few saturated pixels must not collapse the rest of the dynamic range."""
    img = np.full((32, 32), 100.0, dtype=np.float32)
    img[0, 0] = 1e6
    out = classical.normalise(img)
    assert np.isfinite(out).all()
    assert out.std() < 30.0


def test_normalise_handles_a_constant_image():
    """A flat image has zero dynamic range; normalisation must not divide by 0."""
    out = classical.normalise(np.full((16, 16), 42.0, dtype=np.float32))
    assert np.isfinite(out).all()


# -- Lee filter -------------------------------------------------------------

def test_lee_filter_reduces_speckle_variance_in_homogeneous_areas():
    rng = np.random.default_rng(0)
    flat = np.full((128, 128), -20.0, dtype=np.float32)
    speckled = flat + rng.normal(0, 2.0, flat.shape).astype(np.float32)
    filtered = classical.lee_filter(speckled, 7)
    assert filtered.std() < speckled.std(), "Lee filter must smooth homogeneous sea"


def test_lee_filter_preserves_a_strong_edge():
    """The boundary is the feature every geometry number depends on."""
    img = np.full((128, 128), -10.0, dtype=np.float32)
    img[:, 64:] = -25.0
    filtered = classical.lee_filter(img, 7)
    step = filtered[64, 70] - filtered[64, 58]
    assert step < -10.0, "a 15 dB edge must survive speckle filtering"


# -- geometry helper --------------------------------------------------------

def test_describe_returns_every_morphology_field(bundle):
    oil, _, _ = classical.detect(bundle.sar_db())
    assert oil
    described = geometry.describe(oil[0][0], bundle)
    for field in MORPHOLOGY_FIELDS:
        assert field in described


def test_measurements_are_json_serialisable(bundle):
    """numpy floats serialise under pydantic but not under json.dumps."""
    oil, _, _ = classical.detect(bundle.sar_db())
    described = geometry.describe(oil[0][0], bundle)
    json.dumps(described)  # raises TypeError on a numpy scalar
