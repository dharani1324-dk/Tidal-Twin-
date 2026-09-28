# OceanVerse architecture

OceanVerse presents ocean observations and analysis through a React/TypeScript
frontend and a FastAPI backend. PostgreSQL with PostGIS stores observations and
geographic entities. External provider adapters fetch ocean and weather data;
the backend keeps source and quality metadata alongside results.

```text
Browser (React, Vite, Cesium)
          │ REST / JSON
          ▼
FastAPI routers ── domain services ── provider adapters
          │                              │
          ▼                              ▼
PostgreSQL + PostGIS              Ocean/weather providers
```

## Main areas

| Area | Location | Responsibility |
|---|---|---|
| Frontend routes | `frontend/src/App.tsx` | Dashboard, Digital Twin, data layers, forensics, scenarios, assistant |
| API routers | `backend/app/api/` | HTTP endpoints and request validation |
| AI/domain modules | `backend/app/modules/ai/` | Event detection, twin comparison, forensics, source quality, domain analysis |
| Data models | `backend/app/models/` | SQLAlchemy entities and database access |
| Provider adapters | `backend/app/modules/ai/` | External data acquisition and provenance |

## Data handling

Observation payloads retain source and data-type labels. Simulated demo records
are explicitly marked and can be reset without deleting other observations.
Unavailable provider values remain unavailable; they are not replaced with
fabricated live readings. For known data limitations, see
[`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).

## Runtime

The frontend and backend can run locally or as separate Railway services. The
backend exposes health at `/api/v1/health` and OpenAPI at `/openapi.json`.
Configuration is supplied through environment variables; see
[`DEPLOYMENT.md`](DEPLOYMENT.md).
