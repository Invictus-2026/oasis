# Phase 1 — persistent data layer & database foundation — design

Status: approved, ready for implementation plan
Date: 2026-08-27

## Problem

SpillTrace's backend (`backend/app/`) has no database. It is entirely
fixture/file-backed: a single frozen case study is loaded once from
`data/case/case.json` (+ `.npy`/`.parquet` siblings) via `case_store.py`, and
every endpoint (`/api/case`, `/api/detect`, `/api/drift/*`, `/api/attribute`,
`/api/report`) either reads that frozen bundle or falls back to static
fixtures in `app/core/fixtures.py`. There is no way to persist a new,
real-world incident, or to store more than one case at a time.

## Scope

Phase 1 is the **data layer only**: persistent storage, schema, migrations,
and CRUD/read REST APIs for the ten core entities. It explicitly does **not**
implement SAR detection, Lagrangian drift simulation, AIS analysis,
attribution scoring, or forecasting — those remain exactly as they are today
(fixture-backed, single frozen case study, untouched). The existing endpoints
under `/api/case`, `/api/detect`, `/api/drift/*`, `/api/attribute`,
`/api/report`, `/api/scene`, `/api/upload`, `/api/pipeline/run` are not
modified. This is a new, parallel subsystem.

The existing frontend UI (MapLibre map, sliding panels, SpillSelector, active
slick filtering, mock mode) is preserved unchanged; this phase only adds the
ability to fetch persisted incidents/slicks from a real API, with the same
mock-fallback guarantee the rest of the app already has.

## Decisions

- **SQLite via SQLAlchemy 2.0**, not Postgres. Zero external services to run;
  a single file at `backend/data/spilltrace.db`. `DATABASE_URL` stays
  configurable in `app/core/config.py` so it can point at Postgres later
  without code changes.
- **SQLAlchemy ORM models + separate Pydantic schemas**, not SQLModel. Keeps
  DB schema and API contract decoupled, matching this repo's existing
  convention (`core/schemas.py` is already a hand-maintained contract file
  independent of any ORM).
- **Alembic** owns migrations (`alembic upgrade head`). A startup hook also
  calls `Base.metadata.create_all()` if tables don't exist, so a fresh
  checkout works with zero manual steps — mirrors this repo's existing
  "never fail, fall back" philosophy (`case_store.load_case()` already
  degrades gracefully when the bundle is missing).
- **Geometry as GeoJSON JSON columns**, not PostGIS. No new geospatial DB
  dependency; matches the requirement that spatial entities return
  GeoJSON-compatible structures directly.
- **Generic `BaseRepository[Model]` / `BaseService`** to avoid repeating
  near-identical CRUD boilerplate across ten entities. Per-entity subclasses
  only where relationship-specific queries are needed (e.g. slicks filtered
  by `incident_id`, vessel lookup by `mmsi`).
- **Mock/real switch reuses two patterns already in this codebase** rather
  than inventing a third:
  - Backend: `DATA_MODE` env var (`db` default / `mock`) — when `mock`, the
    service layer returns seeded in-memory fixtures instead of querying
    SQLite, mirroring `case_store.py`'s existing fixture-fallback.
  - Frontend: extend `api/client.ts`'s existing `call()` helper (try live
    fetch → catch → bundled JSON fallback) with new functions
    (`getIncidents`, `getIncident`, `getSlicksForIncident`, ...) backed by
    new `mock/incidents.json` / `mock/slicks.json` fixtures. `VITE_FORCE_MOCK`
    continues to force mock mode globally. Nothing existing is removed.

## Entities & relationships

```
Incident
  → Slick (incident_id)
      → SatelliteImage (incident_id) / Detection (satellite_image_id, slick_id?)
      → Simulation (slick_id)
          → AISPosition (vessel_id) / Vessel
              → AttributionResult (incident_id, simulation_id?, vessel_id)
                  → Report (incident_id)
  → EnvironmentalObservation (incident_id)
```

- **Incident** — id, name, status, origin_lon, origin_lat, origin_time_utc,
  description, created_at, updated_at
- **Slick** `→ incident_id` — polygon (GeoJSON JSON), area_km2, confidence,
  method, detected_at
- **SatelliteImage** `→ incident_id` — scene_id, source, acquired_at, bbox
  (JSON), url/path
- **Detection** `→ satellite_image_id`, optional `→ slick_id` — method,
  confidence, evidence (JSON)
- **EnvironmentalObservation** `→ incident_id` — observed_at, wind
  speed/dir, current speed/dir, source
- **Simulation** `→ slick_id` — kind (hindcast/forecast), params (JSON),
  origin_estimate (JSON)
- **Vessel** — mmsi (unique), name, vessel_type
- **AISPosition** `→ vessel_id` — lon, lat, speed, heading, timestamp
- **AttributionResult** `→ incident_id`, `→ simulation_id` (nullable),
  `→ vessel_id` — score, breakdown (JSON), rank
- **Report** `→ incident_id` — generated_at, content (JSON), pdf_path
  (nullable)

## REST API surface

New routes, distinct from the existing fixture endpoints:
- Full CRUD: `/api/incidents`, `/api/vessels`
- Create + List + Get (+ Delete): `/api/slicks`, `/api/satellite-images`,
  `/api/detections`, `/api/environmental-observations`, `/api/simulations`,
  `/api/ais-positions`, `/api/attribution-results`, `/api/reports`
- Nested convenience reads: `/api/incidents/{id}/slicks`,
  `/api/vessels/{id}/positions`

## Module layout

```
backend/app/db/            engine, session, Base, ORM models (one file/entity)
backend/app/schemas/       Pydantic Create/Read/Update schemas (new; core/schemas.py
                            stays frozen as the existing fixture-API contract)
backend/app/repositories/  BaseRepository[Model] + per-entity subclasses
backend/app/services/      business logic + DATA_MODE mock/db switch
backend/app/api/           new routers, registered in main.py alongside existing ones
backend/alembic/           migration environment + versioned migrations
```

## Testing

`tests/test_incidents_api.py` using a temp-file/in-memory SQLite DB
(dependency-overridden per test): create an incident via the API, read it
back, create a slick under that incident, verify the `incident_id`
relationship and that it's returned under `/api/incidents/{id}/slicks`.
Existing tests (`test_case_bundle.py`, `test_contract.py`, `test_detection.py`,
`test_drift.py`) are untouched.

## Acceptance criteria

- Backend starts successfully with no manual DB setup step.
- Database initializes/migrates (tables created on first run; Alembic
  available for future schema changes).
- A test incident can be created and read back via the API.
- A slick created under an incident correctly reports that `incident_id`.
- The frontend can retrieve a persisted incident through the new API.
- Existing UI and existing endpoints continue working unmodified.
- With the backend unavailable (or `DATA_MODE=mock` / `VITE_FORCE_MOCK=1`),
  mock mode remains fully functional on both sides.
