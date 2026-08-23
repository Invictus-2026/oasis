#!/usr/bin/env python3
"""Dump the fixture responses to frontend/src/mock/ as JSON.

Lets the frontend run with the backend down, and keeps the two in sync by
construction. Re-run after any schema change:

    backend/.venv/bin/python scripts/export_mocks.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import fixtures  # noqa: E402

OUT = ROOT / "frontend" / "src" / "mock"
ORIGIN_TIME = datetime(2023, 6, 15, 4, 10, tzinfo=timezone.utc)


def _thin(payload: dict, every: int = 4, max_points: int = 120) -> dict:
    """Particle timelines are large. The mock only needs enough frames to
    prove the animation renders."""
    tl = payload.get("particles_timeline")
    if tl:
        payload["particles_timeline"] = [
            {**f, "points": f["points"][:max_points]} for f in tl[::every]
        ]
    return payload


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bundle = {
        "case": fixtures.case_meta().model_dump(mode="json"),
        "detection": fixtures.detect_response().model_dump(mode="json"),
        "hindcast": _thin(fixtures.hindcast_response().model_dump(mode="json")),
        "forecast": _thin(fixtures.forecast_response().model_dump(mode="json")),
        "attribution": fixtures.attribute_response().model_dump(mode="json"),
    }
    for name, payload in bundle.items():
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2))
        print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
