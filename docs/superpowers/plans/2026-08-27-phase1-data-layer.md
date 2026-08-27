# Phase 1 Persistent Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SpillTrace a real, persistent database layer (SQLite + SQLAlchemy) with ORM models, Pydantic schemas, repository/service layers, Alembic migrations, and REST CRUD/read APIs for ten entities (incidents, slicks, satellite images, detections, environmental observations, simulations, vessels, AIS positions, attribution results, reports) — without touching the existing fixture-backed detection/drift/attribution/report pipeline or the frontend UI.

**Architecture:** FastAPI routers → service layer (mock/db switch via `DATA_MODE`) → repository layer (generic `BaseRepository[Model]`) → SQLAlchemy 2.0 ORM models → SQLite (`data/spilltrace.db`). Pydantic `Create`/`Read`/`Update` schemas are the API contract, kept separate from the existing frozen `app/core/schemas.py`. Frontend gets new `api/client.ts` functions that follow the existing live-fetch-with-mock-fallback pattern.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (declarative, `Mapped`/`mapped_column`), Alembic, SQLite, Pydantic v2, pytest + httpx `TestClient` (backend); TypeScript, Vite (frontend, types + client functions only, no new UI).

**Spec:** `docs/superpowers/specs/2026-08-27-phase1-data-layer-design.md`

## Global Constraints

- Do not implement SAR detection, Lagrangian simulation, AIS analysis, attribution scoring, or forecasting logic — this phase is storage + CRUD only.
- Do not modify existing endpoints (`/api/case`, `/api/detect`, `/api/drift/*`, `/api/attribute`, `/api/report`, `/api/scene`, `/api/upload`, `/api/pipeline/run`) or existing tests (`test_case_bundle.py`, `test_contract.py`, `test_detection.py`, `test_drift.py`).
- Do not modify existing frontend UI components, MapView, sliding panels, SpillSelector, active slick filtering.
- Do not remove or weaken the existing frontend mock fallback in `api/client.ts` (`VITE_FORCE_MOCK`, catch-and-fallback in `call()`).
- Database engine: SQLite via SQLAlchemy, file at `data/spilltrace.db` (repo-root `data/` dir, matching `config.DATA_DIR`), `DATABASE_URL` env-overridable.
- ORM/schema separation: SQLAlchemy models in `app/db/models.py`, Pydantic schemas in `app/schemas/entities.py` — never merged (no SQLModel).
- Geometry and other structured fields are stored as JSON columns (GeoJSON dicts in, GeoJSON dicts out) — no PostGIS.
- Mock/real switch: backend `DATA_MODE` env var (`db` default / `mock`); frontend reuses existing `call()` fallback pattern + `VITE_FORCE_MOCK`.
- New REST routes use plural nouns and must not collide with existing singular routes (`/api/incidents` new vs `/api/case` existing; `/api/reports` new vs `/api/report` existing).

---

## Task 1: DB engine, session, and config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/session.py`
- Test: `backend/tests/test_db_session.py`

**Interfaces:**
- Produces: `app.db.base.Base` (SQLAlchemy `DeclarativeBase`), `app.db.session.engine`, `app.db.session.SessionLocal`, `app.db.session.get_db() -> Generator[Session, None, None]`, `app.db.session.init_db() -> None`. `app.core.config.DATABASE_URL: str`, `app.core.config.DATA_MODE: str`.

- [ ] **Step 1: Add SQLAlchemy and Alembic to dependencies**

Edit `backend/requirements.txt`, add a new section after the `Phase 0` block:

```
# Phase 1 — persistent data layer
sqlalchemy>=2.0
alembic>=1.13
```

Edit `backend/pyproject.toml`, add to the `dependencies` list (after `"pydantic>=2.9",`):

```toml
    "sqlalchemy>=2.0",
    "alembic>=1.13",
```

- [ ] **Step 2: Install and verify**

Run: `cd backend && .venv/bin/pip install -r requirements.txt`
Expected: `sqlalchemy` and `alembic` install successfully.

- [ ] **Step 3: Add DATABASE_URL and DATA_MODE to config.py**

Edit `backend/app/core/config.py`. Add near the top, after the existing imports (`from pathlib import Path`):

```python
import os
```

Add after the existing `DATA_DIR = REPO_ROOT / "data"` line:

```python
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'spilltrace.db'}")
DATA_MODE = os.environ.get("DATA_MODE", "db")  # "db" | "mock"
```

- [ ] **Step 4: Write the failing test**

Create `backend/tests/test_db_session.py`:

```python
"""DB engine/session smoke tests for the Phase 1 data layer."""

from app.db.session import init_db, SessionLocal


def test_init_db_creates_sqlite_file(tmp_path, monkeypatch):
    db_path = tmp_path / "smoke.db"
    monkeypatch.setattr("app.db.session.engine", None, raising=False)
    from sqlalchemy import create_engine
    import app.db.session as session_module

    session_module.engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    session_module.SessionLocal.configure(bind=session_module.engine)

    init_db()

    assert db_path.exists()


def test_get_db_yields_a_working_session():
    gen = None
    from app.db.session import get_db

    gen = get_db()
    db = next(gen)
    try:
        result = db.execute(__import__("sqlalchemy").text("SELECT 1")).scalar()
        assert result == 1
    finally:
        gen.close()
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_db_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 6: Create app/db/__init__.py**

Create `backend/app/db/__init__.py` (empty file).

- [ ] **Step 7: Create app/db/base.py**

Create `backend/app/db/base.py`:

```python
"""SQLAlchemy declarative base shared by every ORM model in app/db/models.py."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 8: Create app/db/session.py**

Create `backend/app/db/session.py`:

```python
"""Engine, session factory and FastAPI dependency for the Phase 1 database.

SQLite by default (app.core.config.DATABASE_URL), swappable to any
SQLAlchemy-supported database via the DATABASE_URL env var with no code
change. init_db() creates any missing tables on startup so a fresh checkout
works without a manual migration step; Alembic (backend/alembic/) remains
the source of truth for versioned schema changes.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import config
from app.db.base import Base

config.DATA_DIR.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    from app.db import models  # noqa: F401 — registers all models on Base.metadata

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_db_session.py -v`
Expected: `test_init_db_creates_sqlite_file` and `test_get_db_yields_a_working_session` PASS. (`init_db()` importing `app.db.models`, which does not exist yet, is fine — Step 4's test monkeypatches the engine before calling `init_db()`, and `app.db.models` is created in Task 2; if this task is executed standalone, temporarily create an empty `backend/app/db/models.py` so the import succeeds, then let Task 2 replace it.)

- [ ] **Step 10: Commit**

```bash
git add backend/requirements.txt backend/pyproject.toml backend/app/core/config.py backend/app/db/__init__.py backend/app/db/base.py backend/app/db/session.py backend/tests/test_db_session.py
git commit -m "feat(db): add SQLAlchemy engine, session and DB config"
```

---

## Task 2: ORM models for all ten entities + startup hook

**Files:**
- Create: `backend/app/db/models.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_db_models.py`

**Interfaces:**
- Consumes: `app.db.base.Base` (Task 1), `app.db.session.init_db` (Task 1).
- Produces: ORM classes in `app.db.models` — `Incident`, `Slick`, `SatelliteImage`, `Detection`, `EnvironmentalObservation`, `Simulation`, `Vessel`, `AISPosition`, `AttributionResult`, `Report`. Each has an integer `id` primary key. Foreign keys: `Slick.incident_id`, `SatelliteImage.incident_id`, `Detection.satellite_image_id`, `Detection.slick_id` (nullable), `EnvironmentalObservation.incident_id`, `Simulation.slick_id`, `AISPosition.vessel_id`, `AttributionResult.incident_id`, `AttributionResult.simulation_id` (nullable), `AttributionResult.vessel_id`, `Report.incident_id`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_db_models.py`:

```python
"""ORM model + relationship configuration tests."""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, configure_mappers

from app.db.base import Base
from app.db import models


def _temp_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)()


def test_all_ten_tables_are_created(tmp_path):
    engine, _ = _temp_session(tmp_path)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "incidents", "slicks", "satellite_images", "detections",
        "environmental_observations", "simulations", "vessels",
        "ais_positions", "attribution_results", "reports",
    }
    assert expected <= tables


def test_mappers_configure_without_error():
    configure_mappers()  # raises if any relationship() target is unresolved


def test_slick_belongs_to_incident_relationship(tmp_path):
    _, session = _temp_session(tmp_path)
    incident = models.Incident(
        name="t", origin_lon=0.0, origin_lat=0.0,
        origin_time_utc="2024-01-01T00:00:00+00:00",
    )
    session.add(incident)
    session.commit()

    slick = models.Slick(
        incident_id=incident.id, polygon={"type": "Point", "coordinates": [0, 0]},
        area_km2=1.0, confidence=0.5, method="classical",
        detected_at="2024-01-01T01:00:00+00:00",
    )
    session.add(slick)
    session.commit()
    session.refresh(incident)

    assert slick.incident_id == incident.id
    assert incident.slicks[0].id == slick.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_db_models.py -v`
Expected: FAIL — `app.db.models` does not exist (or is empty from Task 1's Step 9 workaround).

- [ ] **Step 3: Write the ORM models**

Create `backend/app/db/models.py`:

```python
"""SQLAlchemy ORM models for the Phase 1 persistent data layer.

Ten entities: Incident -> Slick -> SatelliteImage/Detection -> Simulation ->
AISPosition/Vessel -> AttributionResult -> Report. Structured/spatial fields
(polygon, bbox, evidence, params, breakdown, content) are stored as JSON so
API responses can hand back GeoJSON-compatible dicts directly with no
PostGIS dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="open")
    origin_lon: Mapped[float] = mapped_column(Float)
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    slicks: Mapped[list["Slick"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    satellite_images: Mapped[list["SatelliteImage"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    environmental_observations: Mapped[list["EnvironmentalObservation"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    attribution_results: Mapped[list["AttributionResult"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class Slick(Base):
    __tablename__ = "slicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    polygon: Mapped[dict[str, Any]] = mapped_column(JSON)
    area_km2: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="slicks")
    detections: Mapped[list["Detection"]] = relationship(back_populates="slick")
    simulations: Mapped[list["Simulation"]] = relationship(back_populates="slick", cascade="all, delete-orphan")


class SatelliteImage(Base):
    __tablename__ = "satellite_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    scene_id: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bbox: Mapped[dict[str, Any]] = mapped_column(JSON)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="satellite_images")
    detections: Mapped[list["Detection"]] = relationship(back_populates="satellite_image", cascade="all, delete-orphan")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    satellite_image_id: Mapped[int] = mapped_column(ForeignKey("satellite_images.id"), nullable=False)
    slick_id: Mapped[int | None] = mapped_column(ForeignKey("slicks.id"), nullable=True)
    method: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    satellite_image: Mapped["SatelliteImage"] = relationship(back_populates="detections")
    slick: Mapped["Slick | None"] = relationship(back_populates="detections")


class EnvironmentalObservation(Base):
    __tablename__ = "environmental_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    wind_speed_ms: Mapped[float] = mapped_column(Float)
    wind_dir_deg: Mapped[float] = mapped_column(Float)
    current_speed_ms: Mapped[float] = mapped_column(Float)
    current_dir_deg: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="environmental_observations")


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slick_id: Mapped[int] = mapped_column(ForeignKey("slicks.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String)  # "hindcast" | "forecast"
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    origin_estimate: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    slick: Mapped["Slick"] = relationship(back_populates="simulations")
    attribution_results: Mapped[list["AttributionResult"]] = relationship(back_populates="simulation")


class Vessel(Base):
    __tablename__ = "vessels"

    id: Mapped[int] = mapped_column(primary_key=True)
    mmsi: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String)
    vessel_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    positions: Mapped[list["AISPosition"]] = relationship(back_populates="vessel", cascade="all, delete-orphan")
    attribution_results: Mapped[list["AttributionResult"]] = relationship(back_populates="vessel")


class AISPosition(Base):
    __tablename__ = "ais_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[int] = mapped_column(ForeignKey("vessels.id"), nullable=False)
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    speed_knots: Mapped[float] = mapped_column(Float)
    heading_deg: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    vessel: Mapped["Vessel"] = relationship(back_populates="positions")


class AttributionResult(Base):
    __tablename__ = "attribution_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    simulation_id: Mapped[int | None] = mapped_column(ForeignKey("simulations.id"), nullable=True)
    vessel_id: Mapped[int] = mapped_column(ForeignKey("vessels.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON)
    rank: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="attribution_results")
    simulation: Mapped["Simulation | None"] = relationship(back_populates="attribution_results")
    vessel: Mapped["Vessel"] = relationship(back_populates="attribution_results")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="reports")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_db_models.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Wire the startup hook in main.py**

Edit `backend/app/main.py`. Add to the imports:

```python
from app.db.session import init_db
```

Add after the `app = FastAPI(...)` block (before `app.add_middleware`):

```python
@app.on_event("startup")
def _init_db() -> None:
    init_db()
```

- [ ] **Step 6: Verify the app still starts and /health works**

Run: `cd backend && .venv/bin/python -c "
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    r = c.get('/health')
    assert r.status_code == 200, r.text
    print('OK', r.json())
"`
Expected: prints `OK {...}` and a `data/spilltrace.db` file now exists at the repo root.

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/models.py backend/app/main.py backend/tests/test_db_models.py
git commit -m "feat(db): add ORM models for all ten Phase 1 entities"
```

---

## Task 3: Pydantic Create/Read/Update schemas

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/entities.py`
- Test: `backend/tests/test_entity_schemas.py`

**Interfaces:**
- Produces: `IncidentCreate`, `IncidentUpdate`, `IncidentRead`, `SlickCreate`, `SlickRead`, `SatelliteImageCreate`, `SatelliteImageRead`, `DetectionCreate`, `DetectionRead`, `EnvironmentalObservationCreate`, `EnvironmentalObservationRead`, `SimulationCreate`, `SimulationRead`, `VesselCreate`, `VesselUpdate`, `VesselRead`, `AISPositionCreate`, `AISPositionRead`, `AttributionResultCreate`, `AttributionResultRead`, `ReportCreate`, `ReportRead` — all in `app.schemas.entities`. Every `*Read` schema has `model_config = ConfigDict(from_attributes=True)` and an `id: int` field, so it validates directly from an ORM instance or a plain dict (used by mock mode in Task 5).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_entity_schemas.py`:

```python
"""Pydantic schema validation tests for the Phase 1 entities."""

from app.schemas.entities import IncidentCreate, IncidentRead, SlickCreate, SlickRead


def test_incident_create_requires_core_fields():
    payload = IncidentCreate(
        name="Test spill", origin_lon=-90.0, origin_lat=28.5,
        origin_time_utc="2024-01-01T00:00:00+00:00",
    )
    assert payload.status == "open"
    assert payload.description is None


def test_incident_read_validates_from_a_plain_dict():
    read = IncidentRead.model_validate({
        "id": 1, "name": "x", "status": "open", "origin_lon": 0.0,
        "origin_lat": 0.0, "origin_time_utc": "2024-01-01T00:00:00+00:00",
        "description": None,
    })
    assert read.id == 1


def test_slick_create_accepts_a_geojson_polygon():
    payload = SlickCreate(
        incident_id=1,
        polygon={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        area_km2=1.5, confidence=0.8, method="classical",
        detected_at="2024-01-01T00:00:00+00:00",
    )
    assert payload.polygon["type"] == "Polygon"


def test_slick_read_validates_from_a_plain_dict():
    read = SlickRead.model_validate({
        "id": 1, "incident_id": 1, "polygon": {"type": "Point", "coordinates": [0, 0]},
        "area_km2": 1.0, "confidence": 0.5, "method": "classical",
        "detected_at": "2024-01-01T00:00:00+00:00",
    })
    assert read.id == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_entity_schemas.py -v`
Expected: FAIL — `app.schemas` does not exist.

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/__init__.py` (empty file).

Create `backend/app/schemas/entities.py`:

```python
"""Pydantic Create/Read/Update schemas for the Phase 1 persistent data layer.

Kept separate from app/core/schemas.py, which stays frozen as the existing
fixture-backed API contract. Geometry fields are plain GeoJSON dicts;
*Read schemas validate from either an ORM instance (real DB mode) or a
plain dict (mock mode, see app/services/base.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

GeoJSON = dict[str, Any]


class IncidentCreate(BaseModel):
    name: str
    status: str = "open"
    origin_lon: float
    origin_lat: float
    origin_time_utc: datetime
    description: str | None = None


class IncidentUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    origin_lon: float | None = None
    origin_lat: float | None = None
    origin_time_utc: datetime | None = None
    description: str | None = None


class IncidentRead(IncidentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SlickCreate(BaseModel):
    incident_id: int
    polygon: GeoJSON
    area_km2: float
    confidence: float
    method: str
    detected_at: datetime


class SlickRead(SlickCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class SatelliteImageCreate(BaseModel):
    incident_id: int
    scene_id: str
    source: str
    acquired_at: datetime
    bbox: GeoJSON
    url: str | None = None


class SatelliteImageRead(SatelliteImageCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class DetectionCreate(BaseModel):
    satellite_image_id: int
    slick_id: int | None = None
    method: str
    confidence: float
    evidence: dict[str, Any]


class DetectionRead(DetectionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class EnvironmentalObservationCreate(BaseModel):
    incident_id: int
    observed_at: datetime
    wind_speed_ms: float
    wind_dir_deg: float
    current_speed_ms: float
    current_dir_deg: float
    source: str


class EnvironmentalObservationRead(EnvironmentalObservationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class SimulationCreate(BaseModel):
    slick_id: int
    kind: str
    params: dict[str, Any]
    origin_estimate: dict[str, Any]


class SimulationRead(SimulationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class VesselCreate(BaseModel):
    mmsi: str
    name: str
    vessel_type: str


class VesselUpdate(BaseModel):
    name: str | None = None
    vessel_type: str | None = None


class VesselRead(VesselCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class AISPositionCreate(BaseModel):
    vessel_id: int
    lon: float
    lat: float
    speed_knots: float
    heading_deg: float
    timestamp: datetime


class AISPositionRead(AISPositionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class AttributionResultCreate(BaseModel):
    incident_id: int
    simulation_id: int | None = None
    vessel_id: int
    score: float
    breakdown: dict[str, Any]
    rank: int


class AttributionResultRead(AttributionResultCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None


class ReportCreate(BaseModel):
    incident_id: int
    content: dict[str, Any]
    pdf_path: str | None = None


class ReportRead(ReportCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    generated_at: datetime | None = None
    created_at: datetime | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_entity_schemas.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas backend/tests/test_entity_schemas.py
git commit -m "feat(schemas): add Pydantic Create/Read/Update schemas for Phase 1 entities"
```

---

## Task 4: Generic repository layer

**Files:**
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/base.py`
- Create: `backend/app/repositories/entities.py`
- Test: `backend/tests/test_repositories.py`

**Interfaces:**
- Consumes: `app.db.models.*` (Task 2).
- Produces: `BaseRepository[ModelType]` with `create(db, **kwargs)`, `get(db, id)`, `list(db, **filters)`, `update(db, id, **kwargs)`, `delete(db, id) -> bool`. Instantiated per entity in `app.repositories.entities`: `incident_repository`, `slick_repository`, `satellite_image_repository`, `detection_repository`, `environmental_observation_repository`, `simulation_repository`, `vessel_repository`, `ais_position_repository`, `attribution_result_repository`, `report_repository`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_repositories.py`:

```python
"""Repository layer CRUD tests against a temp SQLite DB."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db import models  # noqa: F401
from app.repositories.entities import incident_repository, slick_repository


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_create_get_list_update_delete_incident(db_session):
    created = incident_repository.create(
        db_session, name="t", origin_lon=0.0, origin_lat=0.0,
        origin_time_utc="2024-01-01T00:00:00+00:00",
    )
    assert created.id is not None

    fetched = incident_repository.get(db_session, created.id)
    assert fetched.name == "t"

    all_rows = incident_repository.list(db_session)
    assert len(all_rows) == 1

    updated = incident_repository.update(db_session, created.id, name="renamed")
    assert updated.name == "renamed"

    assert incident_repository.delete(db_session, created.id) is True
    assert incident_repository.get(db_session, created.id) is None
    assert incident_repository.delete(db_session, created.id) is False


def test_list_filters_slicks_by_incident_id(db_session):
    incident = incident_repository.create(
        db_session, name="t", origin_lon=0.0, origin_lat=0.0,
        origin_time_utc="2024-01-01T00:00:00+00:00",
    )
    slick_repository.create(
        db_session, incident_id=incident.id, polygon={"type": "Point", "coordinates": [0, 0]},
        area_km2=1.0, confidence=0.5, method="classical",
        detected_at="2024-01-01T00:00:00+00:00",
    )
    slicks = slick_repository.list(db_session, incident_id=incident.id)
    assert len(slicks) == 1
    assert slicks[0].incident_id == incident.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_repositories.py -v`
Expected: FAIL — `app.repositories` does not exist.

- [ ] **Step 3: Write the base repository**

Create `backend/app/repositories/__init__.py` (empty file).

Create `backend/app/repositories/base.py`:

```python
"""Generic CRUD repository shared by all ten Phase 1 entities."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType]):
        self.model = model

    def create(self, db: Session, **kwargs: Any) -> ModelType:
        obj = self.model(**kwargs)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def get(self, db: Session, id: int) -> ModelType | None:
        return db.get(self.model, id)

    def list(self, db: Session, **filters: Any) -> list[ModelType]:
        stmt = select(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return list(db.execute(stmt).scalars().all())

    def update(self, db: Session, id: int, **kwargs: Any) -> ModelType | None:
        obj = self.get(db, id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, id: int) -> bool:
        obj = self.get(db, id)
        if obj is None:
            return False
        db.delete(obj)
        db.commit()
        return True
```

- [ ] **Step 4: Instantiate one repository per entity**

Create `backend/app/repositories/entities.py`:

```python
"""One BaseRepository instance per Phase 1 entity."""

from app.db import models
from app.repositories.base import BaseRepository

incident_repository = BaseRepository(models.Incident)
slick_repository = BaseRepository(models.Slick)
satellite_image_repository = BaseRepository(models.SatelliteImage)
detection_repository = BaseRepository(models.Detection)
environmental_observation_repository = BaseRepository(models.EnvironmentalObservation)
simulation_repository = BaseRepository(models.Simulation)
vessel_repository = BaseRepository(models.Vessel)
ais_position_repository = BaseRepository(models.AISPosition)
attribution_result_repository = BaseRepository(models.AttributionResult)
report_repository = BaseRepository(models.Report)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_repositories.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories backend/tests/test_repositories.py
git commit -m "feat(repositories): add generic BaseRepository and per-entity instances"
```

---

## Task 5: Service layer with mock/real DATA_MODE switch

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/base.py`
- Create: `backend/app/services/entities.py`
- Test: `backend/tests/test_services.py`

**Interfaces:**
- Consumes: `app.repositories.entities.*` (Task 4), `app.core.config.DATA_MODE` (Task 1).
- Produces: `BaseService[ModelType]` with `create(db, **kwargs)`, `get(db, id)`, `list(db, **filters)`, `update(db, id, **kwargs)`, `delete(db, id)`. When `config.DATA_MODE == "mock"`, these operate on an in-memory seeded list instead of the DB session (the `db` argument is accepted but unused in mock mode, so callers don't need to branch). Instantiated per entity in `app.services.entities`: `incident_service`, `slick_service`, `satellite_image_service`, `detection_service`, `environmental_observation_service`, `simulation_service`, `vessel_service`, `ais_position_service`, `attribution_result_service`, `report_service`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_services.py`:

```python
"""Service layer tests: DB delegation and the DATA_MODE=mock switch."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import config
from app.db.base import Base
from app.db import models  # noqa: F401
from app.services.entities import incident_service, vessel_service


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'svc.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_db_mode_delegates_to_repository(db_session, monkeypatch):
    monkeypatch.setattr(config, "DATA_MODE", "db")
    created = incident_service.create(
        db_session, name="t", origin_lon=0.0, origin_lat=0.0,
        origin_time_utc="2024-01-01T00:00:00+00:00",
    )
    assert created.id is not None
    assert incident_service.get(db_session, created.id).name == "t"


def test_mock_mode_returns_seeded_data_without_touching_the_db(db_session, monkeypatch):
    monkeypatch.setattr(config, "DATA_MODE", "mock")
    seeded = vessel_service.list(db_session)
    assert len(seeded) >= 1
    assert "mmsi" in seeded[0]


def test_mock_mode_create_and_get_round_trip(db_session, monkeypatch):
    monkeypatch.setattr(config, "DATA_MODE", "mock")
    created = incident_service.create(
        db_session, name="mock incident", origin_lon=1.0, origin_lat=1.0,
        origin_time_utc="2024-01-01T00:00:00+00:00",
    )
    fetched = incident_service.get(db_session, created["id"])
    assert fetched["name"] == "mock incident"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_services.py -v`
Expected: FAIL — `app.services` does not exist.

- [ ] **Step 3: Write the base service**

Create `backend/app/services/__init__.py` (empty file).

Create `backend/app/services/base.py`:

```python
"""Generic service layer with a mock/real DATA_MODE switch.

In "db" mode (default), every method delegates to the injected
BaseRepository. In "mock" mode, methods operate on an in-memory list seeded
from mock_data, returning plain dicts — Pydantic *Read schemas validate
these directly via model_validate() since they don't require ORM objects.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy.orm import Session

from app.core import config
from app.repositories.base import BaseRepository

ModelType = TypeVar("ModelType")


class BaseService(Generic[ModelType]):
    def __init__(self, repository: BaseRepository, mock_data: list[dict[str, Any]]):
        self.repository = repository
        self._seed = mock_data
        self._mock_store: list[dict[str, Any]] | None = None

    def _mock(self) -> list[dict[str, Any]]:
        if self._mock_store is None:
            self._mock_store = [dict(d) for d in self._seed]
        return self._mock_store

    def create(self, db: Session, **kwargs: Any):
        if config.DATA_MODE == "mock":
            record = dict(kwargs)
            record["id"] = len(self._mock()) + 1
            self._mock().append(record)
            return record
        return self.repository.create(db, **kwargs)

    def get(self, db: Session, id: int):
        if config.DATA_MODE == "mock":
            return next((r for r in self._mock() if r["id"] == id), None)
        return self.repository.get(db, id)

    def list(self, db: Session, **filters: Any):
        if config.DATA_MODE == "mock":
            return [r for r in self._mock() if all(r.get(k) == v for k, v in filters.items())]
        return self.repository.list(db, **filters)

    def update(self, db: Session, id: int, **kwargs: Any):
        if config.DATA_MODE == "mock":
            record = next((r for r in self._mock() if r["id"] == id), None)
            if record is None:
                return None
            record.update({k: v for k, v in kwargs.items() if v is not None})
            return record
        return self.repository.update(db, id, **kwargs)

    def delete(self, db: Session, id: int) -> bool:
        if config.DATA_MODE == "mock":
            before = len(self._mock())
            self._mock_store = [r for r in self._mock() if r["id"] != id]
            return len(self._mock_store) < before
        return self.repository.delete(db, id)
```

- [ ] **Step 4: Instantiate one service per entity, with seed data**

Create `backend/app/services/entities.py`:

```python
"""One BaseService instance per Phase 1 entity, with small seed fixtures
for DATA_MODE=mock (offline/demo mode with no database required)."""

from app.repositories import entities as repos
from app.services.base import BaseService

incident_service = BaseService(repos.incident_repository, mock_data=[
    {
        "id": 1,
        "name": "Gulf of Mexico — offshore Louisiana (mock)",
        "status": "open",
        "origin_lon": -90.00,
        "origin_lat": 28.55,
        "origin_time_utc": "2023-06-15T04:10:00+00:00",
        "description": "Seeded mock incident for offline/demo mode.",
    },
])

slick_service = BaseService(repos.slick_repository, mock_data=[
    {
        "id": 1,
        "incident_id": 1,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[[-90.12, 28.40], [-90.10, 28.40], [-90.10, 28.42], [-90.12, 28.42], [-90.12, 28.40]]],
        },
        "area_km2": 3.2,
        "confidence": 0.83,
        "method": "classical",
        "detected_at": "2023-06-15T12:00:00+00:00",
    },
])

satellite_image_service = BaseService(repos.satellite_image_repository, mock_data=[])
detection_service = BaseService(repos.detection_repository, mock_data=[])
environmental_observation_service = BaseService(repos.environmental_observation_repository, mock_data=[])
simulation_service = BaseService(repos.simulation_repository, mock_data=[])

vessel_service = BaseService(repos.vessel_repository, mock_data=[
    {"id": 1, "mmsi": "366123456", "name": "M/V Example (mock)", "vessel_type": "tanker"},
])

ais_position_service = BaseService(repos.ais_position_repository, mock_data=[])
attribution_result_service = BaseService(repos.attribution_result_repository, mock_data=[])
report_service = BaseService(repos.report_repository, mock_data=[])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_services.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services backend/tests/test_services.py
git commit -m "feat(services): add BaseService with DATA_MODE mock/db switch"
```

---

## Task 6: Incident + Slick routers (core acceptance path)

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/app/api/incidents.py`
- Create: `backend/app/api/slicks.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_incidents_api.py`

**Interfaces:**
- Consumes: `app.services.entities.incident_service`, `app.services.entities.slick_service` (Task 5); `app.schemas.entities.IncidentCreate/Read/Update`, `SlickCreate/Read` (Task 3); `app.db.session.get_db` (Task 1).
- Produces: `router` (`APIRouter`, prefix `/api/incidents`) in `app.api.incidents`; `router` (prefix `/api/slicks`) in `app.api.slicks`. Routes: `POST/GET /api/incidents`, `GET/PATCH/DELETE /api/incidents/{id}`, `GET /api/incidents/{id}/slicks`, `POST/GET /api/slicks`, `GET/DELETE /api/slicks/{id}`. Test fixture `client` (module-scoped-per-test `TestClient` with `get_db` overridden to a temp SQLite DB) in `tests/conftest.py`, reused by every later API test task.

- [ ] **Step 1: Write the shared test fixture**

Create `backend/tests/conftest.py`:

```python
"""Shared pytest fixtures for the Phase 1 data-layer API tests.

`client` gives every test a FastAPI TestClient wired to a throwaway,
per-test SQLite database via a get_db dependency override — the real
backend/../data/spilltrace.db file is never touched by tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db import models  # noqa: F401 — registers all models on Base.metadata
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api_test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_incidents_api.py`:

```python
"""Acceptance tests: an incident can be created/read, and a slick belongs
to the incident it was created under."""

INCIDENT_BODY = {
    "name": "Test incident",
    "status": "open",
    "origin_lon": -90.05,
    "origin_lat": 28.5,
    "origin_time_utc": "2024-01-01T00:00:00+00:00",
    "description": "Created by test_incidents_api.py",
}


def test_incident_can_be_created_and_read_back(client):
    created = client.post("/api/incidents", json=INCIDENT_BODY)
    assert created.status_code == 200, created.text
    created_body = created.json()
    assert created_body["id"]
    assert created_body["name"] == INCIDENT_BODY["name"]

    fetched = client.get(f"/api/incidents/{created_body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created_body


def test_incident_not_found_returns_404(client):
    assert client.get("/api/incidents/9999").status_code == 404


def test_incident_list_and_update(client):
    created = client.post("/api/incidents", json=INCIDENT_BODY).json()
    assert len(client.get("/api/incidents").json()) == 1

    updated = client.patch(f"/api/incidents/{created['id']}", json={"status": "closed"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "closed"


def test_slick_belongs_to_its_incident(client):
    incident = client.post("/api/incidents", json=INCIDENT_BODY).json()
    slick_body = {
        "incident_id": incident["id"],
        "polygon": {
            "type": "Polygon",
            "coordinates": [[[-90.1, 28.4], [-90.0, 28.4], [-90.0, 28.5], [-90.1, 28.5], [-90.1, 28.4]]],
        },
        "area_km2": 2.5,
        "confidence": 0.9,
        "method": "classical",
        "detected_at": "2024-01-01T06:00:00+00:00",
    }
    slick = client.post("/api/slicks", json=slick_body)
    assert slick.status_code == 200, slick.text
    slick_body_resp = slick.json()
    assert slick_body_resp["incident_id"] == incident["id"]

    nested = client.get(f"/api/incidents/{incident['id']}/slicks")
    assert nested.status_code == 200
    assert len(nested.json()) == 1
    assert nested.json()[0]["id"] == slick_body_resp["id"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_incidents_api.py -v`
Expected: FAIL — `404 Not Found` (routers don't exist yet / aren't registered).

- [ ] **Step 4: Write the incidents router**

Create `backend/app/api/incidents.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import IncidentCreate, IncidentRead, IncidentUpdate, SlickRead
from app.services.entities import incident_service, slick_service

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.post("", response_model=IncidentRead)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db)) -> IncidentRead:
    obj = incident_service.create(db, **payload.model_dump())
    return IncidentRead.model_validate(obj)


@router.get("", response_model=list[IncidentRead])
def list_incidents(db: Session = Depends(get_db)) -> list[IncidentRead]:
    return [IncidentRead.model_validate(o) for o in incident_service.list(db)]


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: int, db: Session = Depends(get_db)) -> IncidentRead:
    obj = incident_service.get(db, incident_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentRead.model_validate(obj)


@router.patch("/{incident_id}", response_model=IncidentRead)
def update_incident(incident_id: int, payload: IncidentUpdate, db: Session = Depends(get_db)) -> IncidentRead:
    obj = incident_service.update(db, incident_id, **payload.model_dump(exclude_unset=True))
    if obj is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentRead.model_validate(obj)


@router.delete("/{incident_id}", status_code=204)
def delete_incident(incident_id: int, db: Session = Depends(get_db)) -> None:
    if not incident_service.delete(db, incident_id):
        raise HTTPException(status_code=404, detail="Incident not found")


@router.get("/{incident_id}/slicks", response_model=list[SlickRead])
def list_incident_slicks(incident_id: int, db: Session = Depends(get_db)) -> list[SlickRead]:
    return [SlickRead.model_validate(o) for o in slick_service.list(db, incident_id=incident_id)]
```

- [ ] **Step 5: Write the slicks router**

Create `backend/app/api/slicks.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import SlickCreate, SlickRead
from app.services.entities import slick_service

router = APIRouter(prefix="/api/slicks", tags=["slicks"])


@router.post("", response_model=SlickRead)
def create_slick(payload: SlickCreate, db: Session = Depends(get_db)) -> SlickRead:
    obj = slick_service.create(db, **payload.model_dump())
    return SlickRead.model_validate(obj)


@router.get("", response_model=list[SlickRead])
def list_slicks(db: Session = Depends(get_db)) -> list[SlickRead]:
    return [SlickRead.model_validate(o) for o in slick_service.list(db)]


@router.get("/{slick_id}", response_model=SlickRead)
def get_slick(slick_id: int, db: Session = Depends(get_db)) -> SlickRead:
    obj = slick_service.get(db, slick_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Slick not found")
    return SlickRead.model_validate(obj)


@router.delete("/{slick_id}", status_code=204)
def delete_slick(slick_id: int, db: Session = Depends(get_db)) -> None:
    if not slick_service.delete(db, slick_id):
        raise HTTPException(status_code=404, detail="Slick not found")
```

- [ ] **Step 6: Register both routers in main.py**

Edit `backend/app/main.py`. Add to imports:

```python
from app.api import incidents, slicks
```

Change the router-registration loop to include the new routers:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router):
    app.include_router(r)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_incidents_api.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 8: Run the full backend suite to confirm nothing else broke**

Run: `cd backend && .venv/bin/pytest -v`
Expected: all tests PASS, including the pre-existing `test_case_bundle.py`, `test_contract.py`, `test_detection.py`, `test_drift.py`.

- [ ] **Step 9: Commit**

```bash
git add backend/tests/conftest.py backend/app/api/incidents.py backend/app/api/slicks.py backend/app/main.py backend/tests/test_incidents_api.py
git commit -m "feat(api): add /api/incidents and /api/slicks CRUD routers"
```

---

## Task 7: Vessel + AIS position routers

**Files:**
- Create: `backend/app/api/vessels.py`
- Create: `backend/app/api/ais_positions.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_vessels_api.py`

**Interfaces:**
- Consumes: `app.services.entities.vessel_service`, `app.services.entities.ais_position_service` (Task 5).
- Produces: `router` (prefix `/api/vessels`, full CRUD + `GET /api/vessels/{id}/positions`) in `app.api.vessels`; `router` (prefix `/api/ais-positions`) in `app.api.ais_positions`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_vessels_api.py`:

```python
"""Vessel CRUD and AIS position nesting tests."""

VESSEL_BODY = {"mmsi": "366999123", "name": "Test Vessel", "vessel_type": "tanker"}


def test_vessel_can_be_created_read_updated_deleted(client):
    created = client.post("/api/vessels", json=VESSEL_BODY).json()
    assert created["mmsi"] == VESSEL_BODY["mmsi"]

    fetched = client.get(f"/api/vessels/{created['id']}").json()
    assert fetched == created

    updated = client.patch(f"/api/vessels/{created['id']}", json={"name": "Renamed"}).json()
    assert updated["name"] == "Renamed"

    assert client.delete(f"/api/vessels/{created['id']}").status_code == 204
    assert client.get(f"/api/vessels/{created['id']}").status_code == 404


def test_ais_position_belongs_to_vessel(client):
    vessel = client.post("/api/vessels", json=VESSEL_BODY).json()
    position_body = {
        "vessel_id": vessel["id"], "lon": -90.1, "lat": 28.4,
        "speed_knots": 12.5, "heading_deg": 180.0,
        "timestamp": "2024-01-01T00:00:00+00:00",
    }
    created = client.post("/api/ais-positions", json=position_body)
    assert created.status_code == 200, created.text
    assert created.json()["vessel_id"] == vessel["id"]

    nested = client.get(f"/api/vessels/{vessel['id']}/positions")
    assert nested.status_code == 200
    assert len(nested.json()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_vessels_api.py -v`
Expected: FAIL — `404 Not Found`.

- [ ] **Step 3: Write the vessels router**

Create `backend/app/api/vessels.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import AISPositionRead, VesselCreate, VesselRead, VesselUpdate
from app.services.entities import ais_position_service, vessel_service

router = APIRouter(prefix="/api/vessels", tags=["vessels"])


@router.post("", response_model=VesselRead)
def create_vessel(payload: VesselCreate, db: Session = Depends(get_db)) -> VesselRead:
    obj = vessel_service.create(db, **payload.model_dump())
    return VesselRead.model_validate(obj)


@router.get("", response_model=list[VesselRead])
def list_vessels(db: Session = Depends(get_db)) -> list[VesselRead]:
    return [VesselRead.model_validate(o) for o in vessel_service.list(db)]


@router.get("/{vessel_id}", response_model=VesselRead)
def get_vessel(vessel_id: int, db: Session = Depends(get_db)) -> VesselRead:
    obj = vessel_service.get(db, vessel_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vessel not found")
    return VesselRead.model_validate(obj)


@router.patch("/{vessel_id}", response_model=VesselRead)
def update_vessel(vessel_id: int, payload: VesselUpdate, db: Session = Depends(get_db)) -> VesselRead:
    obj = vessel_service.update(db, vessel_id, **payload.model_dump(exclude_unset=True))
    if obj is None:
        raise HTTPException(status_code=404, detail="Vessel not found")
    return VesselRead.model_validate(obj)


@router.delete("/{vessel_id}", status_code=204)
def delete_vessel(vessel_id: int, db: Session = Depends(get_db)) -> None:
    if not vessel_service.delete(db, vessel_id):
        raise HTTPException(status_code=404, detail="Vessel not found")


@router.get("/{vessel_id}/positions", response_model=list[AISPositionRead])
def list_vessel_positions(vessel_id: int, db: Session = Depends(get_db)) -> list[AISPositionRead]:
    return [AISPositionRead.model_validate(o) for o in ais_position_service.list(db, vessel_id=vessel_id)]
```

- [ ] **Step 4: Write the AIS positions router**

Create `backend/app/api/ais_positions.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import AISPositionCreate, AISPositionRead
from app.services.entities import ais_position_service

router = APIRouter(prefix="/api/ais-positions", tags=["ais-positions"])


@router.post("", response_model=AISPositionRead)
def create_ais_position(payload: AISPositionCreate, db: Session = Depends(get_db)) -> AISPositionRead:
    obj = ais_position_service.create(db, **payload.model_dump())
    return AISPositionRead.model_validate(obj)


@router.get("", response_model=list[AISPositionRead])
def list_ais_positions(db: Session = Depends(get_db)) -> list[AISPositionRead]:
    return [AISPositionRead.model_validate(o) for o in ais_position_service.list(db)]


@router.get("/{position_id}", response_model=AISPositionRead)
def get_ais_position(position_id: int, db: Session = Depends(get_db)) -> AISPositionRead:
    obj = ais_position_service.get(db, position_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="AIS position not found")
    return AISPositionRead.model_validate(obj)


@router.delete("/{position_id}", status_code=204)
def delete_ais_position(position_id: int, db: Session = Depends(get_db)) -> None:
    if not ais_position_service.delete(db, position_id):
        raise HTTPException(status_code=404, detail="AIS position not found")
```

- [ ] **Step 5: Register both routers in main.py**

Edit `backend/app/main.py`. Replace:

```python
from app.api import incidents, slicks
```

with:

```python
from app.api import ais_positions, incidents, slicks, vessels
```

Replace:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router):
    app.include_router(r)
```

with:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router, vessels.router, ais_positions.router):
    app.include_router(r)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_vessels_api.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/vessels.py backend/app/api/ais_positions.py backend/app/main.py backend/tests/test_vessels_api.py
git commit -m "feat(api): add /api/vessels and /api/ais-positions routers"
```

---

## Task 8: Satellite image + detection routers

**Files:**
- Create: `backend/app/api/satellite_images.py`
- Create: `backend/app/api/detections.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_satellite_and_detections_api.py`

**Interfaces:**
- Consumes: `app.services.entities.satellite_image_service`, `app.services.entities.detection_service` (Task 5).
- Produces: `router` (prefix `/api/satellite-images`) in `app.api.satellite_images`; `router` (prefix `/api/detections`) in `app.api.detections`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_satellite_and_detections_api.py`:

```python
"""Satellite image and detection CRUD/read tests."""


def _incident(client):
    body = {
        "name": "t", "status": "open", "origin_lon": 0.0, "origin_lat": 0.0,
        "origin_time_utc": "2024-01-01T00:00:00+00:00",
    }
    return client.post("/api/incidents", json=body).json()


def test_satellite_image_create_and_list(client):
    incident = _incident(client)
    body = {
        "incident_id": incident["id"], "scene_id": "S1A_TEST", "source": "sentinel-1",
        "acquired_at": "2024-01-01T00:00:00+00:00",
        "bbox": {"west": -1, "south": -1, "east": 1, "north": 1}, "url": None,
    }
    created = client.post("/api/satellite-images", json=body)
    assert created.status_code == 200, created.text
    assert len(client.get("/api/satellite-images").json()) == 1


def test_detection_optionally_links_to_a_slick(client):
    incident = _incident(client)
    image_body = {
        "incident_id": incident["id"], "scene_id": "S1A_TEST", "source": "sentinel-1",
        "acquired_at": "2024-01-01T00:00:00+00:00",
        "bbox": {"west": -1, "south": -1, "east": 1, "north": 1}, "url": None,
    }
    image = client.post("/api/satellite-images", json=image_body).json()

    detection_body = {
        "satellite_image_id": image["id"], "slick_id": None, "method": "classical",
        "confidence": 0.7, "evidence": {"contrast": 0.5},
    }
    created = client.post("/api/detections", json=detection_body)
    assert created.status_code == 200, created.text
    assert created.json()["satellite_image_id"] == image["id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_satellite_and_detections_api.py -v`
Expected: FAIL — `404 Not Found`.

- [ ] **Step 3: Write the satellite images router**

Create `backend/app/api/satellite_images.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import SatelliteImageCreate, SatelliteImageRead
from app.services.entities import satellite_image_service

router = APIRouter(prefix="/api/satellite-images", tags=["satellite-images"])


@router.post("", response_model=SatelliteImageRead)
def create_satellite_image(payload: SatelliteImageCreate, db: Session = Depends(get_db)) -> SatelliteImageRead:
    obj = satellite_image_service.create(db, **payload.model_dump())
    return SatelliteImageRead.model_validate(obj)


@router.get("", response_model=list[SatelliteImageRead])
def list_satellite_images(db: Session = Depends(get_db)) -> list[SatelliteImageRead]:
    return [SatelliteImageRead.model_validate(o) for o in satellite_image_service.list(db)]


@router.get("/{image_id}", response_model=SatelliteImageRead)
def get_satellite_image(image_id: int, db: Session = Depends(get_db)) -> SatelliteImageRead:
    obj = satellite_image_service.get(db, image_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Satellite image not found")
    return SatelliteImageRead.model_validate(obj)


@router.delete("/{image_id}", status_code=204)
def delete_satellite_image(image_id: int, db: Session = Depends(get_db)) -> None:
    if not satellite_image_service.delete(db, image_id):
        raise HTTPException(status_code=404, detail="Satellite image not found")
```

- [ ] **Step 4: Write the detections router**

Create `backend/app/api/detections.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import DetectionCreate, DetectionRead
from app.services.entities import detection_service

router = APIRouter(prefix="/api/detections", tags=["detections"])


@router.post("", response_model=DetectionRead)
def create_detection(payload: DetectionCreate, db: Session = Depends(get_db)) -> DetectionRead:
    obj = detection_service.create(db, **payload.model_dump())
    return DetectionRead.model_validate(obj)


@router.get("", response_model=list[DetectionRead])
def list_detections(db: Session = Depends(get_db)) -> list[DetectionRead]:
    return [DetectionRead.model_validate(o) for o in detection_service.list(db)]


@router.get("/{detection_id}", response_model=DetectionRead)
def get_detection(detection_id: int, db: Session = Depends(get_db)) -> DetectionRead:
    obj = detection_service.get(db, detection_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Detection not found")
    return DetectionRead.model_validate(obj)


@router.delete("/{detection_id}", status_code=204)
def delete_detection(detection_id: int, db: Session = Depends(get_db)) -> None:
    if not detection_service.delete(db, detection_id):
        raise HTTPException(status_code=404, detail="Detection not found")
```

- [ ] **Step 5: Register both routers in main.py**

Edit `backend/app/main.py`. Replace:

```python
from app.api import ais_positions, incidents, slicks, vessels
```

with:

```python
from app.api import ais_positions, detections, incidents, satellite_images, slicks, vessels
```

Replace:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router, vessels.router, ais_positions.router):
    app.include_router(r)
```

with:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router, vessels.router, ais_positions.router,
          satellite_images.router, detections.router):
    app.include_router(r)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_satellite_and_detections_api.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/satellite_images.py backend/app/api/detections.py backend/app/main.py backend/tests/test_satellite_and_detections_api.py
git commit -m "feat(api): add /api/satellite-images and /api/detections routers"
```

---

## Task 9: Environmental observation + simulation routers

**Files:**
- Create: `backend/app/api/environmental_observations.py`
- Create: `backend/app/api/simulations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_environmental_and_simulations_api.py`

**Interfaces:**
- Consumes: `app.services.entities.environmental_observation_service`, `app.services.entities.simulation_service` (Task 5).
- Produces: `router` (prefix `/api/environmental-observations`) in `app.api.environmental_observations`; `router` (prefix `/api/simulations`) in `app.api.simulations`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_environmental_and_simulations_api.py`:

```python
"""Environmental observation and simulation CRUD/read tests."""


def _incident(client):
    body = {
        "name": "t", "status": "open", "origin_lon": 0.0, "origin_lat": 0.0,
        "origin_time_utc": "2024-01-01T00:00:00+00:00",
    }
    return client.post("/api/incidents", json=body).json()


def _slick(client, incident_id):
    body = {
        "incident_id": incident_id, "polygon": {"type": "Point", "coordinates": [0, 0]},
        "area_km2": 1.0, "confidence": 0.5, "method": "classical",
        "detected_at": "2024-01-01T00:00:00+00:00",
    }
    return client.post("/api/slicks", json=body).json()


def test_environmental_observation_create_and_list(client):
    incident = _incident(client)
    body = {
        "incident_id": incident["id"], "observed_at": "2024-01-01T00:00:00+00:00",
        "wind_speed_ms": 5.0, "wind_dir_deg": 180.0,
        "current_speed_ms": 0.3, "current_dir_deg": 90.0, "source": "test",
    }
    created = client.post("/api/environmental-observations", json=body)
    assert created.status_code == 200, created.text
    assert len(client.get("/api/environmental-observations").json()) == 1


def test_simulation_belongs_to_a_slick(client):
    incident = _incident(client)
    slick = _slick(client, incident["id"])
    body = {
        "slick_id": slick["id"], "kind": "hindcast",
        "params": {"hours": 24, "n_particles": 500},
        "origin_estimate": {"point": [0, 0], "uncertainty_radius_km": 5.0},
    }
    created = client.post("/api/simulations", json=body)
    assert created.status_code == 200, created.text
    assert created.json()["slick_id"] == slick["id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_environmental_and_simulations_api.py -v`
Expected: FAIL — `404 Not Found`.

- [ ] **Step 3: Write the environmental observations router**

Create `backend/app/api/environmental_observations.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import EnvironmentalObservationCreate, EnvironmentalObservationRead
from app.services.entities import environmental_observation_service

router = APIRouter(prefix="/api/environmental-observations", tags=["environmental-observations"])


@router.post("", response_model=EnvironmentalObservationRead)
def create_environmental_observation(
    payload: EnvironmentalObservationCreate, db: Session = Depends(get_db)
) -> EnvironmentalObservationRead:
    obj = environmental_observation_service.create(db, **payload.model_dump())
    return EnvironmentalObservationRead.model_validate(obj)


@router.get("", response_model=list[EnvironmentalObservationRead])
def list_environmental_observations(db: Session = Depends(get_db)) -> list[EnvironmentalObservationRead]:
    return [EnvironmentalObservationRead.model_validate(o) for o in environmental_observation_service.list(db)]


@router.get("/{observation_id}", response_model=EnvironmentalObservationRead)
def get_environmental_observation(observation_id: int, db: Session = Depends(get_db)) -> EnvironmentalObservationRead:
    obj = environmental_observation_service.get(db, observation_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Environmental observation not found")
    return EnvironmentalObservationRead.model_validate(obj)


@router.delete("/{observation_id}", status_code=204)
def delete_environmental_observation(observation_id: int, db: Session = Depends(get_db)) -> None:
    if not environmental_observation_service.delete(db, observation_id):
        raise HTTPException(status_code=404, detail="Environmental observation not found")
```

- [ ] **Step 4: Write the simulations router**

Create `backend/app/api/simulations.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import SimulationCreate, SimulationRead
from app.services.entities import simulation_service

router = APIRouter(prefix="/api/simulations", tags=["simulations"])


@router.post("", response_model=SimulationRead)
def create_simulation(payload: SimulationCreate, db: Session = Depends(get_db)) -> SimulationRead:
    obj = simulation_service.create(db, **payload.model_dump())
    return SimulationRead.model_validate(obj)


@router.get("", response_model=list[SimulationRead])
def list_simulations(db: Session = Depends(get_db)) -> list[SimulationRead]:
    return [SimulationRead.model_validate(o) for o in simulation_service.list(db)]


@router.get("/{simulation_id}", response_model=SimulationRead)
def get_simulation(simulation_id: int, db: Session = Depends(get_db)) -> SimulationRead:
    obj = simulation_service.get(db, simulation_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return SimulationRead.model_validate(obj)


@router.delete("/{simulation_id}", status_code=204)
def delete_simulation(simulation_id: int, db: Session = Depends(get_db)) -> None:
    if not simulation_service.delete(db, simulation_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
```

- [ ] **Step 5: Register both routers in main.py**

Edit `backend/app/main.py`. Replace:

```python
from app.api import ais_positions, detections, incidents, satellite_images, slicks, vessels
```

with:

```python
from app.api import (
    ais_positions,
    detections,
    environmental_observations,
    incidents,
    satellite_images,
    simulations,
    slicks,
    vessels,
)
```

Replace:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router, vessels.router, ais_positions.router,
          satellite_images.router, detections.router):
    app.include_router(r)
```

with:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router, vessels.router, ais_positions.router,
          satellite_images.router, detections.router,
          environmental_observations.router, simulations.router):
    app.include_router(r)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_environmental_and_simulations_api.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/environmental_observations.py backend/app/api/simulations.py backend/app/main.py backend/tests/test_environmental_and_simulations_api.py
git commit -m "feat(api): add /api/environmental-observations and /api/simulations routers"
```

---

## Task 10: Attribution result + report routers

**Files:**
- Create: `backend/app/api/attribution_results.py`
- Create: `backend/app/api/reports.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_attribution_and_reports_api.py`

**Interfaces:**
- Consumes: `app.services.entities.attribution_result_service`, `app.services.entities.report_service` (Task 5).
- Produces: `router` (prefix `/api/attribution-results`) in `app.api.attribution_results`; `router` (prefix `/api/reports`) in `app.api.reports`. Note: `/api/reports` is a new plural route and does not collide with the existing `/api/report` (singular, fixture-backed PDF generation) endpoint.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_attribution_and_reports_api.py`:

```python
"""Attribution result and report CRUD/read tests."""


def _incident(client):
    body = {
        "name": "t", "status": "open", "origin_lon": 0.0, "origin_lat": 0.0,
        "origin_time_utc": "2024-01-01T00:00:00+00:00",
    }
    return client.post("/api/incidents", json=body).json()


def _vessel(client):
    return client.post(
        "/api/vessels", json={"mmsi": "366000111", "name": "t", "vessel_type": "tanker"}
    ).json()


def test_attribution_result_links_incident_and_vessel(client):
    incident = _incident(client)
    vessel = _vessel(client)
    body = {
        "incident_id": incident["id"], "simulation_id": None, "vessel_id": vessel["id"],
        "score": 0.72, "breakdown": {"proximity": 0.8}, "rank": 1,
    }
    created = client.post("/api/attribution-results", json=body)
    assert created.status_code == 200, created.text
    assert created.json()["incident_id"] == incident["id"]
    assert created.json()["vessel_id"] == vessel["id"]


def test_report_create_and_list(client):
    incident = _incident(client)
    body = {"incident_id": incident["id"], "content": {"summary": "test"}, "pdf_path": None}
    created = client.post("/api/reports", json=body)
    assert created.status_code == 200, created.text
    assert len(client.get("/api/reports").json()) == 1


def test_new_reports_route_does_not_collide_with_existing_report_endpoint(client):
    # Existing fixture-backed POST /api/report (singular) must still respond.
    resp = client.post("/api/report", json={"case_id": "gom-2023-06-15", "slick_id": "slick-001"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_attribution_and_reports_api.py -v`
Expected: FAIL — `404 Not Found` on the new routes (the existing `/api/report` test should already pass).

- [ ] **Step 3: Write the attribution results router**

Create `backend/app/api/attribution_results.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import AttributionResultCreate, AttributionResultRead
from app.services.entities import attribution_result_service

router = APIRouter(prefix="/api/attribution-results", tags=["attribution-results"])


@router.post("", response_model=AttributionResultRead)
def create_attribution_result(payload: AttributionResultCreate, db: Session = Depends(get_db)) -> AttributionResultRead:
    obj = attribution_result_service.create(db, **payload.model_dump())
    return AttributionResultRead.model_validate(obj)


@router.get("", response_model=list[AttributionResultRead])
def list_attribution_results(db: Session = Depends(get_db)) -> list[AttributionResultRead]:
    return [AttributionResultRead.model_validate(o) for o in attribution_result_service.list(db)]


@router.get("/{result_id}", response_model=AttributionResultRead)
def get_attribution_result(result_id: int, db: Session = Depends(get_db)) -> AttributionResultRead:
    obj = attribution_result_service.get(db, result_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Attribution result not found")
    return AttributionResultRead.model_validate(obj)


@router.delete("/{result_id}", status_code=204)
def delete_attribution_result(result_id: int, db: Session = Depends(get_db)) -> None:
    if not attribution_result_service.delete(db, result_id):
        raise HTTPException(status_code=404, detail="Attribution result not found")
```

- [ ] **Step 4: Write the reports router**

Create `backend/app/api/reports.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.entities import ReportCreate, ReportRead
from app.services.entities import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("", response_model=ReportRead)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)) -> ReportRead:
    obj = report_service.create(db, **payload.model_dump())
    return ReportRead.model_validate(obj)


@router.get("", response_model=list[ReportRead])
def list_reports(db: Session = Depends(get_db)) -> list[ReportRead]:
    return [ReportRead.model_validate(o) for o in report_service.list(db)]


@router.get("/{report_id}", response_model=ReportRead)
def get_report(report_id: int, db: Session = Depends(get_db)) -> ReportRead:
    obj = report_service.get(db, report_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportRead.model_validate(obj)


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)) -> None:
    if not report_service.delete(db, report_id):
        raise HTTPException(status_code=404, detail="Report not found")
```

- [ ] **Step 5: Register both routers in main.py**

Edit `backend/app/main.py`. Update the import to the full set:

```python
from app.api import (
    ais_positions,
    attribution_results,
    detections,
    environmental_observations,
    incidents,
    reports,
    satellite_images,
    simulations,
    slicks,
    vessels,
)
```

Update the router-registration tuple to include everything:

```python
for r in (case.router, detection.router, drift.router, attribution.router,
          report.router, pipeline.router, scene.router, upload.router,
          incidents.router, slicks.router, vessels.router, ais_positions.router,
          satellite_images.router, detections.router,
          environmental_observations.router, simulations.router,
          attribution_results.router, reports.router):
    app.include_router(r)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_attribution_and_reports_api.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/attribution_results.py backend/app/api/reports.py backend/app/main.py backend/tests/test_attribution_and_reports_api.py
git commit -m "feat(api): add /api/attribution-results and /api/reports routers"
```

---

## Task 11: Alembic migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako` (from `alembic init` scaffold)
- Create: `backend/alembic/versions/<generated>_initial_schema.py`
- Modify: `backend/.gitignore` (or root `.gitignore` — see Task 12)

**Interfaces:**
- Consumes: `app.db.base.Base`, `app.db.models` (Task 2), `app.core.config.DATABASE_URL` (Task 1).
- Produces: `alembic upgrade head` creates all ten tables from a clean database; `alembic downgrade base` drops them.

- [ ] **Step 1: Scaffold Alembic**

Run: `cd backend && .venv/bin/alembic init alembic`
Expected: creates `backend/alembic/` (with `env.py`, `script.py.mako`, `versions/`) and `backend/alembic.ini`.

- [ ] **Step 2: Point Alembic at the app's models and DATABASE_URL**

Replace the contents of `backend/alembic/env.py` with:

```python
"""Alembic environment — points at app.db.base.Base.metadata and
app.core.config.DATABASE_URL so migrations always target the same DB the
FastAPI app uses."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import config as app_config  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: E402,F401 — registers all models on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", app_config.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

In `backend/alembic.ini`, delete/blank the `sqlalchemy.url = ...` line under `[alembic]` (it's set dynamically by `env.py` from `app.core.config.DATABASE_URL` above) — leave it as `sqlalchemy.url = `.

- [ ] **Step 3: Generate the initial migration**

Run: `cd backend && .venv/bin/alembic revision --autogenerate -m "initial schema"`
Expected: creates a new file under `backend/alembic/versions/` with `upgrade()`/`downgrade()` functions that `create_table`/`drop_table` for all ten entities.

- [ ] **Step 4: Verify the migration against a clean database**

Run:
```bash
cd backend
rm -f /tmp/alembic_verify.db
DATABASE_URL="sqlite:////tmp/alembic_verify.db" .venv/bin/alembic upgrade head
.venv/bin/python -c "
from sqlalchemy import create_engine, inspect
engine = create_engine('sqlite:////tmp/alembic_verify.db')
tables = set(inspect(engine).get_table_names())
expected = {
    'incidents', 'slicks', 'satellite_images', 'detections',
    'environmental_observations', 'simulations', 'vessels',
    'ais_positions', 'attribution_results', 'reports', 'alembic_version',
}
assert expected <= tables, tables
print('OK', sorted(tables))
"
DATABASE_URL="sqlite:////tmp/alembic_verify.db" .venv/bin/alembic downgrade base
rm -f /tmp/alembic_verify.db
```
Expected: prints `OK [...]` listing all eleven tables (ten entities + `alembic_version`), and `downgrade base` completes without error.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat(db): add Alembic migration environment and initial schema migration"
```

---

## Task 12: Gitignore, dependency lockfile check, and existing-test regression pass

**Files:**
- Modify: `.gitignore` (repo root)
- Test: full backend suite

**Interfaces:**
- None (housekeeping + regression gate).

- [ ] **Step 1: Ignore the SQLite DB file and journal**

Edit `.gitignore` (repo root). Add to the existing `# Data` section, after `data/case/*.npz`:

```
data/spilltrace.db
data/spilltrace.db-journal
```

- [ ] **Step 2: Confirm the DB file is untracked**

Run: `cd /home/abishekraj/Desktop/smart-india-hackathon && git status --short | grep spilltrace`
Expected: no output (the file is ignored, not staged).

- [ ] **Step 3: Run the full backend test suite**

Run: `cd backend && .venv/bin/pytest -v`
Expected: every test PASses — the pre-existing `test_case_bundle.py`, `test_contract.py`, `test_detection.py`, `test_drift.py` (untouched, still fixture-backed) alongside all Phase 1 tests added in Tasks 1–11.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore the local SQLite database file"
```

---

## Task 13: Frontend — types, mock fixtures, and API client functions

**Files:**
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/mock/incidents.json`
- Create: `frontend/src/mock/slicks.json`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces: `Incident`, `Slick` TypeScript interfaces in `frontend/src/api/types.ts`. `getIncidents(): Promise<Incident[]>`, `getIncident(id: number): Promise<Incident | null>`, `getSlicksForIncident(incidentId: number): Promise<Slick[]>` in `frontend/src/api/client.ts`, following the existing `call()` fallback pattern (live fetch → on failure, bundled mock JSON, `dataMode` flips to `"mock"`).

- [ ] **Step 1: Add TypeScript types**

Edit `frontend/src/api/types.ts`. Append at the end of the file:

```typescript
// --------------------------------------------------------------------------
// Phase 1 persistent data layer — mirrors backend/app/schemas/entities.py
// --------------------------------------------------------------------------

export interface Incident {
  id: number;
  name: string;
  status: string;
  origin_lon: number;
  origin_lat: number;
  origin_time_utc: string;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Slick {
  id: number;
  incident_id: number;
  polygon: Geom;
  area_km2: number;
  confidence: number;
  method: string;
  detected_at: string;
  created_at: string | null;
}
```

- [ ] **Step 2: Add bundled mock fixtures**

Create `frontend/src/mock/incidents.json`:

```json
[
  {
    "id": 1,
    "name": "Gulf of Mexico — offshore Louisiana (mock)",
    "status": "open",
    "origin_lon": -90.0,
    "origin_lat": 28.55,
    "origin_time_utc": "2023-06-15T04:10:00+00:00",
    "description": "Seeded mock incident for offline/demo mode.",
    "created_at": null,
    "updated_at": null
  }
]
```

Create `frontend/src/mock/slicks.json`:

```json
[
  {
    "id": 1,
    "incident_id": 1,
    "polygon": {
      "type": "Polygon",
      "coordinates": [[[-90.12, 28.40], [-90.10, 28.40], [-90.10, 28.42], [-90.12, 28.42], [-90.12, 28.40]]]
    },
    "area_km2": 3.2,
    "confidence": 0.83,
    "method": "classical",
    "detected_at": "2023-06-15T12:00:00+00:00",
    "created_at": null
  }
]
```

- [ ] **Step 3: Add client functions**

Edit `frontend/src/api/client.ts`. Add to the imports at the top:

```typescript
import incidentsMock from "../mock/incidents.json";
import slicksMock from "../mock/slicks.json";
```

Add to the `type` import block:

```typescript
import type {
  AttributeResponse,
  CaseMeta,
  DetectResponse,
  DetectionMethod,
  ForecastResponse,
  HindcastResponse,
  Incident,
  LonLat,
  ReportContent,
  Slick,
} from "./types";
```

Append at the end of the file:

```typescript
export const getIncidents = () =>
  call<Incident[]>("/api/incidents", undefined, incidentsMock);

export const getIncident = async (id: number): Promise<Incident | null> => {
  const all = await getIncidents();
  return all.find((i) => i.id === id) ?? null;
};

export const getSlicksForIncident = (incidentId: number) =>
  call<Slick[]>(
    `/api/incidents/${incidentId}/slicks`,
    undefined,
    (slicksMock as Slick[]).filter((s) => s.incident_id === incidentId),
  );
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 5: Manual live-fetch verification**

Run in one terminal: `cd backend && .venv/bin/uvicorn app.main:app --reload`
Run in another terminal: `cd frontend && npm run dev`
Then: `curl -s http://localhost:5173/api/incidents` (routed through the Vite proxy configured in `vite.config.ts`)
Expected: `[]` (empty list — no incidents created against the dev DB yet) with HTTP 200, proving the frontend dev server successfully proxies to the live backend. Then: `curl -s -X POST http://localhost:5173/api/incidents -H 'Content-Type: application/json' -d '{"name":"Manual check","origin_lon":-90.0,"origin_lat":28.5,"origin_time_utc":"2024-01-01T00:00:00+00:00"}'` should return the created incident with an `id`. Stop both servers (Ctrl+C) when done.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/mock/incidents.json frontend/src/mock/slicks.json
git commit -m "feat(frontend): add incident/slick types, mock fixtures and API client functions"
```

---

## Task 14: End-to-end acceptance verification

**Files:**
- None created/modified — verification only.

**Interfaces:**
- None.

- [ ] **Step 1: Fresh-checkout backend start check**

Run:
```bash
cd /home/abishekraj/Desktop/smart-india-hackathon
rm -f data/spilltrace.db
cd backend && .venv/bin/uvicorn app.main:app --port 8001 &
sleep 2
curl -s http://127.0.0.1:8001/health
```
Expected: `{"status": "ok", ...}` — the backend starts successfully and `data/spilltrace.db` now exists with no manual migration step (Task 2's startup hook ran `init_db()`).

- [ ] **Step 2: Create/read an incident and a nested slick over HTTP**

Run:
```bash
INCIDENT_ID=$(curl -s -X POST http://127.0.0.1:8001/api/incidents \
  -H 'Content-Type: application/json' \
  -d '{"name":"E2E check","origin_lon":-90.0,"origin_lat":28.5,"origin_time_utc":"2024-01-01T00:00:00+00:00"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -s http://127.0.0.1:8001/api/incidents/$INCIDENT_ID
curl -s -X POST http://127.0.0.1:8001/api/slicks \
  -H 'Content-Type: application/json' \
  -d "{\"incident_id\":$INCIDENT_ID,\"polygon\":{\"type\":\"Point\",\"coordinates\":[0,0]},\"area_km2\":1.0,\"confidence\":0.5,\"method\":\"classical\",\"detected_at\":\"2024-01-01T00:00:00+00:00\"}"
curl -s http://127.0.0.1:8001/api/incidents/$INCIDENT_ID/slicks
```
Expected: the incident is returned by GET; the slick's `incident_id` matches `$INCIDENT_ID`; the nested list contains exactly that slick.

- [ ] **Step 3: Confirm existing fixture endpoints still work unmodified**

Run:
```bash
curl -s http://127.0.0.1:8001/api/case | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['disclaimer']; print('case OK')"
curl -s -X POST http://127.0.0.1:8001/api/detect -H 'Content-Type: application/json' -d '{}' | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d['slicks'])>=1; print('detect OK')"
```
Expected: `case OK` and `detect OK`.

- [ ] **Step 4: Confirm mock mode works with the backend unavailable**

Run:
```bash
kill %1  # stops the uvicorn process started in Step 1
DATA_MODE=mock cd backend && .venv/bin/python -c "
import os
os.environ['DATA_MODE'] = 'mock'
from app.services.entities import incident_service
print(incident_service.list(None))
"
```
Expected: prints the seeded mock incident list without raising — proves `DATA_MODE=mock` never touches the database (the `db` argument is `None` and unused in mock mode).

Then, with the backend stopped, in the frontend:
```bash
cd frontend && VITE_FORCE_MOCK=1 npm run dev &
sleep 3
curl -s http://localhost:5173/ -o /dev/null -w '%{http_code}\n'
kill %1
```
Expected: `200` — the frontend dev server still serves the app; any component calling `getIncidents()`/`getCase()`/etc. would resolve from bundled JSON since `VITE_FORCE_MOCK=1` short-circuits every `call()` before it attempts a fetch.

- [ ] **Step 5: Run the full backend test suite one final time**

Run: `cd backend && .venv/bin/pytest -v`
Expected: all tests PASS (pre-existing + all Phase 1 tests).

- [ ] **Step 6: Clean up the verification database**

Run: `rm -f /home/abishekraj/Desktop/smart-india-hackathon/data/spilltrace.db`

No commit for this task — it is verification-only, confirming every acceptance criterion from the spec is met.
