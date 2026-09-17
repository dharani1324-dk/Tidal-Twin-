# TidalTwin — Architecture

> 4D Ocean Model Validation & Decision Intelligence Platform.
> This document describes the components and how they relate. It reflects the
> repository as of **Phase 10 (Deployment, Packaging & Final Submission
> Readiness)**, release **1.0.0 / TIDE-Loop**.

## 1. High-level system

```
                         ┌─────────────────────────────┐
                         │        FRONTEND (React)      │
                         │  Cesium globe · TIDE pages   │
                         │  Copilot · status indicator  │
                         └───────────────┬─────────────┘
                                         │ REST (axios) /api/v1/*
                         ┌───────────────▼─────────────┐
                         │        BACKEND (FastAPI)     │
                         │  app/api/*  →  app/modules/*  │
                         └───────────────┬─────────────┘
                                         │ SQLAlchemy
                         ┌───────────────▼─────────────┐
                         │   PostgreSQL 16 + PostGIS    │
                         │ locations · observations ·   │
                         │ alerts · provenance          │
                         └──────────────────────────────┘
```

## 2. Conceptual intelligence flow (TIDE-Loop architecture)

```
                    4D OCEAN DIGITAL TWIN
                             │
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                    ↓
   Observations          Model Data          Ocean Context
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ↓
                     ANOMALY RADAR
                             ↓
                       FORENSICS
                             ↓
                       EVENT DNA
                             ↓
                         TIDE-LOOP
                             │
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
        Uncertainty      Data Gaps      Disagreement
              │              │              │
              └──────────────┼──────────────┘
                             ↓
                  Observation Prioritization
                             ↓
                       Evidence Layer
                             ↓
                    What-If Simulation
                             ↓
                     Decision Replay
                             ↓
                       Validation
                             ↺
```

The loop in one line (see [`TIDE_INNOVATION.md`](TIDE_INNOVATION.md)):

```text
MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION → BETTER DECISION → VALIDATION ↺
```

The Copilot sits alongside the loop, explaining the same grounded context in
natural language rather than forming part of the decision chain.

## 3. Backend components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| API routers | `backend/app/api/` | HTTP surface: ocean, monitoring, validation, twin, tide, demo, health, … |
| Config | `backend/app/core/config.py` | Settings from `.env`, CORS, startup validation |
| Logging | `backend/app/core/logging_config.py` | Concise, secret-free logging |
| Database | `backend/app/core/database.py` | Engine, session, `get_db` |
| Models | `backend/app/models/` | `OceanLocation`, `OceanObservation`, `OceanAlert`, `Provenance` |
| Ocean ingestion | `backend/app/services/ocean_data.py` | Fetch/normalize public observations |
| Anomaly | `backend/app/modules/ai/anomaly/` | Threshold/scan detection, live broadcast |
| Twin compare | `backend/app/modules/ai/twin/` | MODEL vs OBSERVED, events, situation, anomalies |
| Forensics | `backend/app/modules/ai/forensics/` | Uncertainty map, fingerprint / Event DNA |
| Validation engine | `backend/app/modules/ai/validation/` | Confidence, skill, difference, classify_events |
| APEX | `backend/app/modules/ai/apex/` | Observation recommendations |
| TIDE | `backend/app/modules/ai/tide/` | Scoring, engine, verdicts, replay, validation framework, adapters |
| Copilot | `backend/app/modules/ai/nlp/copilot.py` | Intent detection + grounded answers |

## 4. TIDE internal pipeline

```
adapters.py ─ uncertainty / event / APEX / gaps / disagreement inputs
      │
      ▼
engine.py  ─ TideEngine.rankings()  ──►  scoring.calculate_observation_value()
      │                                         │
      │                                         ▼
      │                                    verdicts.classify_verdict()
      ▼
explanations.py ─ evidence / confidence / decision context
      │
      ├── virtual_observation()  ──► pure simulate_candidate()  (never persisted)
      ├── replay.build_replay()  ──► read-only 10-step timeline
      └── validation.py          ──► benchmark / sensitivity / edge cases
```

- `scoring.TIDE_ALGORITHM_VERSION` is bumped whenever behaviour changes.
- `simulate_candidate` / `decision_for` are the single shared primitives used by
  both the what-if simulation and the Phase 8 benchmark, so they cannot diverge.
- `adapters.invalidate_caches()` clears the short-TTL shared-input cache after
  demo seed/reset or any data refresh.

## 5. Frontend components

| Area | Location | Notes |
|------|----------|-------|
| App shell | `frontend/src/App.tsx` | Navigation, status bar, error-boundary-guarded routes |
| Globe | `frontend/src/components/3d/globe/CesiumGlobe.tsx` | Single viewer instance, cleanup on unmount |
| Workspace | `frontend/src/components/workspace/` | TrustBadge, SystemHealth, UncertaintyGauge, EvidenceDrawer, … |
| System | `frontend/src/components/system/` | `SystemStatusPill`, `DemoGuide` (Phase 9) |
| Pages | `frontend/src/pages/` | Dashboard, DigitalTwin, Tide, DecisionReplay, TideValidation, … |
| API client | `frontend/src/api/client.ts` | Typed axios wrappers |
| Types | `frontend/src/types/` | `tide.ts`, `system.ts` contracts |

## 6. Trust & simulation boundaries

- `TRUST_META` / `TrustBadge` render a single vocabulary everywhere:
  `REAL`, `HISTORICAL`, `MODEL_DERIVED`, `SIMULATED`, `SYNTHETIC`.
- An observation is classified `SIMULATED`/`SYNTHETIC` from its `source`/
  `data_type` (`adapters.observation_status`) — it can never be shown as `REAL`.
- Simulation flows (`virtual_observation`, benchmark) never write to
  `ocean_observations`; enforced by tests.
- Demonstration rows are labelled and removable via `POST /api/v1/demo/reset`,
  which only deletes simulation-labelled rows.

## 7. Reliability (Phase 9)

- `/api/health` and `/api/v1/health` report per-subsystem status
  (`AVAILABLE` / `LIMITED` / `UNAVAILABLE` / `OPTIONAL / UNAVAILABLE`).
- Every frontend route is wrapped in an `ErrorBoundary`; the Copilot FAB has its
  own boundary. One surface failing cannot blank the application.
- Optional services (e.g. Cesium Ion) degrade without failing the app.
