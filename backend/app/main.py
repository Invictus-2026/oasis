"""SpillTrace API.

Oil-spill detection, drift hindcast/forecast and AIS-based vessel attribution
for SIH26143 (NTRO).

Phase 0: every endpoint is fixture-backed so the frontend can be built in
parallel. Phases 2-4 swap the fixtures for real implementations one router at
a time, without the API contract changing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import attribution, case, detection, drift, pipeline, report
from app.core import config

app = FastAPI(
    title="SpillTrace API",
    version=config.MODEL_VERSION,
    description=__doc__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (case.router, detection.router, drift.router, attribution.router, report.router, pipeline.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": config.MODEL_VERSION, "case": config.CASE_ID}
