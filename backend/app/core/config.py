"""Central configuration. Paths, the frozen case-study definition, and the
tunables that appear in provenance blocks."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CASE_DIR = DATA_DIR / "case"
WEIGHTS_DIR = REPO_ROOT / "ml" / "weights"

MODEL_VERSION = "oasis-0.1.0"

# --------------------------------------------------------------------------
# The frozen case study (Phase 1 fills data/case/ to match this)
# --------------------------------------------------------------------------
# Gulf of Mexico, offshore Louisiana. Chosen because AccessAIS covers US waters,
# it is a real high-traffic oil region, and the bbox is small enough that the
# cached wind/current subset stays a few MB.

CASE_ID = "gom-2023-06-15"
CASE_NAME = "Gulf of Mexico — offshore Louisiana"
CASE_BBOX = {"west": -90.60, "south": 28.10, "east": -89.40, "north": 29.00}
CASE_CENTER = (-90.00, 28.55)
SCENE_ID = "S1A_IW_GRDH_1SDV_20230615T120000"
ACQUIRED_AT = datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

DISCLAIMER = (
    "Constructed validation scenario. Real Sentinel-1 SAR imagery (Zenodo oil-spill "
    "dataset) and real AIS traffic (NOAA AccessAIS) are synthetically co-located onto "
    "a common region and time so the end-to-end pipeline can be validated against a "
    "known ground truth. The imagery and the vessel traffic are not from the same "
    "real-world incident."
)

# --------------------------------------------------------------------------
# Physics / scoring defaults (surfaced in provenance so they are auditable)
# --------------------------------------------------------------------------

DRIFT_WIND_FACTOR = 0.03          # fraction of 10 m wind added to surface current
DRIFT_DIFFUSION_M2S = 5.0         # horizontal eddy diffusivity, m^2/s
DRIFT_TIMESTEP_MINUTES = 15
DRIFT_N_PARTICLES = 500
DRIFT_SEED = 42

# --------------------------------------------------------------------------
# Environmental data (Phase 3)
# --------------------------------------------------------------------------
# "auto" prefers the best available real provider and falls back to the
# synthetic one; "mock" forces the fallback. Mirrors the frontend's
# VITE_FORCE_MOCK escape hatch so both halves can be pinned to mock data
# independently for an offline demo.
ENV_DATA_MODE = os.environ.get("ENV_DATA_MODE", "auto")  # "auto" | "mock"
ENV_DEFAULT_STEP_HOURS = 1.0

AIS_GAP_THRESHOLD_MINUTES = 30
ATTRIBUTION_RADIUS_KM = 25.0
ATTRIBUTION_WINDOW_HOURS = 6.0

LIMITATIONS = [
    "Sentinel-1 revisit (6-12 days) means many real spills have no coincident "
    "satellite pass during the detectable window. This system is best-effort triage, "
    "not continuous surveillance.",
    "SAR dark-patch detection cannot fully separate mineral oil from biogenic slicks, "
    "low-wind zones and rain cells. Rejected look-alikes are shown with their reasons.",
    "Drift hindcast uncertainty compounds backward in time. The origin is reported as a "
    "probability cone, never a single point.",
    "AIS can be switched off or spoofed, and gaps are frequently benign. A gap is "
    "treated as one weighted suspicion signal, never as proof.",
    "Output is a ranked, confidence-scored candidate list. It is not an identification "
    "and is not, on its own, evidence of responsibility.",
]
