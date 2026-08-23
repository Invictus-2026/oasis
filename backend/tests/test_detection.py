"""Phase 2 acceptance tests — the real classical detector against the frozen case.

These assert measured accuracy, not just that a polygon comes back. If the
detector regresses, the IoU floor here fails before anyone sees it on stage.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from app.core.case_store import load_case
from app.detection import age as age_mod
from app.detection import classical, pipeline

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


# -- accuracy --------------------------------------------------------------

def test_detects_exactly_one_slick(result):
    assert len(result.slicks) == 1


def test_iou_against_ground_truth(result):
    """The headline number. Measured against the official Zenodo mask."""
    assert result.provenance.params["detection_iou"] >= 0.80


def test_recall_and_precision(result):
    p = result.provenance.params
    assert p["recall"] >= 0.85, "missing too much of the slick"
    assert p["precision"] >= 0.85, "too much false positive area"


def test_area_matches_ground_truth(result, truth):
    got = result.slicks[0].geometry.area_km2
    exp = truth["slick"]["area_km2"]
    assert abs(got - exp) / exp < 0.20, f"area {got} vs truth {exp}"


def test_orientation_matches_ground_truth(result, truth):
    got = result.slicks[0].geometry.orientation_deg
    exp = truth["slick"]["orientation_deg"]
    diff = min(abs(got - exp), 180 - abs(got - exp))
    assert diff < 10, f"bearing {got} vs truth {exp}"


# -- discrimination --------------------------------------------------------

def test_rejects_both_lookalikes(result):
    """The demo beat that pre-answers the most common judge question."""
    assert len(result.rejected_lookalikes) == 2


def test_every_rejection_states_a_physical_reason(result):
    for r in result.rejected_lookalikes:
        assert len(r.reason) > 40
        assert any(k in r.reason.lower() for k in
                   ("variance", "compact", "damping", "gradient", "wind"))


def test_lookalikes_do_not_overlap_the_true_slick(result, bundle):
    """A rejection that actually covers the oil would be a miss dressed up as
    a discrimination."""
    oil = bundle.mask_oil()
    ys, xs = np.nonzero(oil)
    lon, lat = bundle.pixel_to_lonlat(xs, ys)
    pts = set(zip(np.round(lon, 3), np.round(lat, 3)))
    for r in result.rejected_lookalikes:
        ring = r.polygon["coordinates"][0]
        assert not any((round(a, 3), round(b, 3)) in pts for a, b in ring)


def test_oil_is_smoother_and_darker_than_the_rejected_regions(bundle):
    """The physical basis of the discriminator."""
    oil, looks, _ = classical.detect(bundle.sar_db())
    assert oil and looks
    o = oil[0][0]
    for la, _, _ in looks:
        assert o.variance_ratio < la.variance_ratio + 0.05 or o.contrast_db > la.contrast_db


# -- characterisation ------------------------------------------------------

def test_slick_is_elongated(result):
    assert result.slicks[0].geometry.elongation > 5


def test_compactness_is_low_for_a_trail(result):
    assert result.slicks[0].geometry.compactness < 0.25


def test_age_bracket_contains_the_truth(result, truth):
    """The estimate is heuristic, so we require the BRACKET to contain the
    real elapsed time, not the midpoint to match it."""
    a = result.slicks[0].age
    real = truth["ground_truth"]["drift_hours"]
    assert a.min_hours <= real <= a.max_hours, f"{a.min_hours}-{a.max_hours} h excludes {real} h"


def test_age_is_always_caveated(result):
    a = result.slicks[0].age
    assert a.confidence == "low"
    assert "not a calibrated measurement" in a.method_note


def test_age_uses_width_not_total_area():
    """Regression guard. Treating an underway discharge as a radial release
    underestimates the age by roughly an order of magnitude."""
    trail = age_mod.estimate(area_km2=16.0, contrast_db=6.6, length_km=26.0)
    blob = age_mod.estimate(area_km2=16.0, contrast_db=6.6, length_km=None)
    assert trail and blob
    assert trail["max_hours"] < blob["min_hours"], "length must change the answer"


# -- determinism and speed -------------------------------------------------

def test_detection_is_deterministic(bundle):
    a, b = pipeline.run(bundle), pipeline.run(bundle)
    assert a.slicks[0].geometry.model_dump() == b.slicks[0].geometry.model_dump()
    assert a.provenance.params["detection_iou"] == b.provenance.params["detection_iou"]


def test_provenance_records_the_tunables(result):
    p = result.provenance.params
    for k in ("speckle", "threshold_k", "morph_close_px", "background_window"):
        assert k in p, f"{k} missing from provenance — scoring must be auditable"
