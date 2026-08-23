"""Loader for the frozen case bundle in data/case/.

Phase 1 output. Everything is read from disk once and cached, so the demo has
no network dependency and no per-request I/O. If the bundle is absent the API
falls back to fixtures rather than failing, which keeps the frontend working
for anyone who has not run scripts/build_case.py yet.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from app.core import config
from app.core.schemas import BBox, CaseMeta, DataSource, GroundTruth, Provenance


class CaseBundle:
    """The frozen case study: rasters, AIS and metadata."""

    def __init__(self, meta: dict[str, Any], root: Path):
        self.meta = meta
        self.root = root

    # -- metadata ---------------------------------------------------------
    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def grid(self) -> int:
        return self.meta["grid"]

    @property
    def bbox(self) -> dict[str, float]:
        return self.meta["bbox"]

    @property
    def ground_truth(self) -> dict[str, Any]:
        return self.meta["ground_truth"]

    @property
    def acquired_at(self) -> datetime:
        return datetime.fromisoformat(self.meta["acquired_at"])

    # -- arrays (lazy, cached) --------------------------------------------
    @lru_cache(maxsize=1)  # noqa: B019 — one instance per process
    def sar_db(self) -> np.ndarray:
        return np.load(self.root / self.meta["files"]["sar_db"])

    @lru_cache(maxsize=1)  # noqa: B019
    def mask_oil(self) -> np.ndarray:
        return np.load(self.root / self.meta["files"]["mask_oil"])

    @lru_cache(maxsize=1)  # noqa: B019
    def mask_lookalike(self) -> np.ndarray | None:
        name = self.meta["files"].get("mask_lookalike")
        return np.load(self.root / name) if name else None

    @lru_cache(maxsize=1)  # noqa: B019
    def ais(self):
        import pandas as pd
        return pd.read_parquet(self.root / self.meta["files"]["ais"])

    @lru_cache(maxsize=1)  # noqa: B019
    def forcing(self) -> dict[str, np.ndarray] | None:
        name = self.meta.get("forcing", {}).get("file")
        if not name:
            return None
        z = np.load(self.root / name)
        return {k: z[k] for k in z.files}

    # -- geo ---------------------------------------------------------------
    def pixel_to_lonlat(self, col, row):
        b = self.bbox
        g = self.grid
        lon = b["west"] + (np.asarray(col) / (g - 1)) * (b["east"] - b["west"])
        lat = b["north"] - (np.asarray(row) / (g - 1)) * (b["north"] - b["south"])
        return lon, lat

    def pixel_area_km2(self) -> float:
        import math
        b = self.bbox
        lat = self.meta["center"][1]
        w = (b["east"] - b["west"]) * 111.320 * math.cos(math.radians(lat))
        h = (b["north"] - b["south"]) * 110.574
        return (w / self.grid) * (h / self.grid)

    # -- API projection ----------------------------------------------------
    def as_case_meta(self) -> CaseMeta:
        m = self.meta
        gt = m.get("ground_truth")
        return CaseMeta(
            id=m["id"],
            name=m["name"],
            bbox=BBox(**m["bbox"]),
            center=tuple(m["center"]),
            scene_id=m["scene_id"],
            acquired_at=self.acquired_at,
            sar_overlay_url=None,
            sources=[DataSource(**s) for s in m["sources"]],
            ground_truth=GroundTruth(
                origin=tuple(gt["origin"]),
                origin_time_utc=datetime.fromisoformat(gt["origin_time_utc"]),
                polluter_mmsi=gt["polluter_mmsi"],
                polluter_name=gt["polluter_name"],
            ) if gt else None,
            disclaimer=m["disclaimer"],
            provenance=Provenance(
                model_version=config.MODEL_VERSION,
                params={"case_id": m["id"], "grid": m["grid"], "seed": m.get("seed")},
                generated_at=datetime.fromisoformat(m["built_at"]),
                inputs=[s["name"] for s in m["sources"]],
                notes=(
                    f"{sum(not s['is_synthetic'] for s in m['sources'])} real and "
                    f"{sum(s['is_synthetic'] for s in m['sources'])} synthesised inputs. "
                    "Rebuild with scripts/build_case.py."
                ),
            ),
        )


@lru_cache(maxsize=1)
def load_case() -> CaseBundle | None:
    """The frozen bundle, or None if it has not been built."""
    p = config.CASE_DIR / "case.json"
    if not p.exists():
        return None
    return CaseBundle(json.loads(p.read_text()), config.CASE_DIR)
