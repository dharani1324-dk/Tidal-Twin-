# TidalTwin — API Contract Reference

Base URL (local): `http://127.0.0.1:8000`. Interactive docs: `/docs`, `/redoc`.
OpenAPI schema: `/openapi.json`.

This document describes the important, stable contracts. For the full list of
registered routes see [`ENDPOINTS.md`](ENDPOINTS.md).

## Response envelopes

- **TIDE endpoints** (`/api/v1/tide/*`) return a consistent envelope:

  ```json
  { "success": true, "data": { }, "error": null }
  ```

- **Health and demo endpoints** return their payload directly (no envelope).
- Other feature routers return their own feature-shaped payloads; they are
  documented by the OpenAPI schema at `/docs`.

## HTTP status conventions

| Status | Meaning in this API |
|--------|---------------------|
| 200 | Success (including legitimate empty results, e.g. `[]`) |
| 404 | The addressed resource does not exist (unknown event / no candidate) |
| 405 | Wrong method for a known path |
| 422 | Invalid or missing parameters (validation error) |
| 500 | Unexpected server error — generic payload, no internal detail leaked |

Error bodies use FastAPI's `detail` field. TIDE/benchmark validation errors put a
machine code inside `detail.code`, e.g.:

```json
{ "detail": { "code": "TIDE_INVALID_REQUEST", "message": "variable must be one of [...]" } }
```

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Alias, for external monitors / smoke tests |
| GET | `/api/v1/health` | Per-subsystem health (used by the frontend status indicator) |

Payload highlights: `status` (`healthy` | `degraded` | `unavailable`),
`service`, `version`, `release`, `environment`, `simulation_mode`, `checked_at`,
and `checks` for `backend`, `database`, `ocean_data`, `tide`, `copilot`,
`cesium`. Each check carries `status`
(`AVAILABLE` | `LIMITED` | `UNAVAILABLE` | `OPTIONAL / UNAVAILABLE`) and a
human `detail`. **No secrets are ever included.** The TIDE check is a
lightweight probe (30 s TTL); it does not build the full ranking.

## TIDE

All accept optional `location_id`; `variable` defaults to `temperature`;
`depth_m` defaults to `0.0`.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/tide/candidates` | Ranked candidates |
| GET | `/api/v1/tide/rankings` | Candidates + explicit formula string |
| GET | `/api/v1/tide/uncertainty` | Uncertainty inputs |
| GET | `/api/v1/tide/data-gaps` | Data-gap factors |
| GET | `/api/v1/tide/disagreements` | Model-vs-observed disagreement |
| GET | `/api/v1/tide/evidence` | Evidence chain; 404 if no candidate |
| GET | `/api/v1/tide/explanation` | Evidence + confidence + decision context |
| GET | `/api/v1/tide/verdict` | Requires `location_id`; 404 if no candidate |
| GET | `/api/v1/tide/events` | Event index (`event-0`, `event-1`, …) |
| GET | `/api/v1/tide/events/{event_id}` | Event context (DNA, evidence, verdict) |
| GET | `/api/v1/tide/events/{event_id}/replay` | Read-only decision replay |
| POST | `/api/v1/tide/virtual-observation` | What-if simulation (never persisted) |

`variable` must be one of: `temperature, salinity, oxygen, chlorophyll,
current_speed, wave_height, pressure, nutrients, ph, density`. `depth_m` must be
`>= 0`. Unknown variable or negative depth → **422**.

### Simulation isolation

`POST /api/v1/tide/virtual-observation` derives a reading from existing inputs
(or an explicit `value`), returns a result whose
`simulated_observation.status == "SIMULATED"`, and **never writes** to
`ocean_observations`. This is enforced by tests.

## Validation & benchmarking

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/tide/validation` | Maturity, dataset, ground truth, boundary, consistency |
| GET | `/api/v1/tide/benchmarks` | Machine-readable benchmark report |
| GET | `/api/v1/tide/benchmarks/{case_id}` | Case-level drill-down |

Benchmark query params: `budget` (1–10, default 1), `variables`
(comma-separated), `strategies` (comma-separated), `depth_m` (>= 0), `seed`
(default 42). Invalid values → **422**.

`/benchmarks/{case_id}` accepts either `event-N` or a non-event identifier that
encodes a known variable (`<variable>` or `<variable>@<depth>`, e.g.
`temperature@0`). An unknown event id, or a non-event id that does not encode a
known variable, returns **404**.

## Demonstration mode

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/demo/status` | Demonstration data + selected DEMONSTRATION EVENT |
| POST | `/api/v1/demo/seed` | `location` (default `goa`), `kind` (`heatwave`\|`surge`), `force` |
| POST | `/api/v1/demo/reset` | Deletes **only** simulation-labelled rows |

Seed writes labelled `SIMULATED` observations and **zero alerts** (`scan=False`).
Reset never touches real observations. `kind` is pattern-validated → **422** on
anything else.

## Copilot

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/assistant/capabilities` | Supported intents |
| POST | `/api/v1/assistant/ask` | Context-aware, evidence-grounded answer |
| POST | `/api/v1/assistant/multimodal` | Multimodal query |

Copilot is a local, rule-based NLP service with **no external dependency**; a
Copilot failure cannot affect the rest of the API.

## Conventions summary

- Empty result sets are **200 with `[]`**, not 404.
- Missing resources addressed by id are **404**.
- Parameter problems are **422** with a machine-readable code where applicable.
- No endpoint returns stack traces; unexpected errors are a generic `500`.
- Simulation (`SIMULATED` / `SYNTHETIC`) and `MODEL_DERIVED` status are always
  explicit in payloads and can never be reported as `REAL`.
