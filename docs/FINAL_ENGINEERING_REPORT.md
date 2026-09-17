# TidalTwin — Final Engineering Report (Phase 10)

> Actual results only. Every important item is classified using the project's
> maturity vocabulary. Where something was not executed, it says so.

**Release:** `1.0.0` · `TIDE-Loop` (packaging identifier, not a validity claim)
**Report date:** 2026-09-17
**Repository state:** working tree, not committed

## Project

| Item | Status |
|------|--------|
| 4D Ocean Digital Twin + decision-intelligence platform | IMPLEMENTED |
| Reproducible local + container startup | IMPLEMENTED / DEMONSTRATED |
| Submission documentation package | IMPLEMENTED |

## Architecture

Backend FastAPI + SQLAlchemy + PostGIS; frontend React 19 + TypeScript + Vite +
CesiumJS; single PostGIS database. Documented in
[`ARCHITECTURE.md`](ARCHITECTURE.md). Status: **IMPLEMENTED**.

## Implemented Systems

| System | Status |
|--------|--------|
| 4D Ocean Digital Twin | IMPLEMENTED / TESTED |
| Ocean Copilot (rule-based, local) | IMPLEMENTED / TESTED |
| Ocean Anomaly Radar | IMPLEMENTED / TESTED |
| Ocean Forensics | IMPLEMENTED / TESTED |
| Ocean Event Timeline | IMPLEMENTED |
| Ocean Fingerprint / Event DNA | IMPLEMENTED / TESTED |
| APEX observation recommendations | IMPLEMENTED |
| TIDE evidence & trust layer | IMPLEMENTED / TESTED |
| TIDE observation ranking | IMPLEMENTED / TESTED |
| TIDE uncertainty & data-gap analysis | IMPLEMENTED / TESTED |
| Model-vs-Sensor verdicts | IMPLEMENTED / TESTED |
| What If We Measure Here? (virtual sensor) | IMPLEMENTED / TESTED |
| TIDE Decision Replay | IMPLEMENTED / TESTED |
| Validation / benchmarking framework | IMPLEMENTED / TESTED |
| Unified Ocean Intelligence workflow | IMPLEMENTED / DEMONSTRATED |
| Cesium visualization | IMPLEMENTED (browser render NOT TESTED — headless) |
| Demo mode | IMPLEMENTED / TESTED / DEMONSTRATED |
| Engineering hardening (health, boundaries, logging, caching) | IMPLEMENTED / TESTED |

## TIDE-Loop

The closed loop **MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION →
BETTER DECISION → VALIDATION ↺** is implemented and demonstrated.

```text
Observation Value =
  Decision Impact × Uncertainty × Data Gap × Anomaly Persistence
  ÷ max(Observation Cost, 0.05)
```

| Aspect | Classification |
|--------|----------------|
| Scoring / ranking | IMPLEMENTED / TESTED |
| Evidence, confidence, verdict | IMPLEMENTED / TESTED |
| Simulation isolation | IMPLEMENTED / TESTED |
| Empirical validation | **NOT AVAILABLE** (`EMPIRICALLY_VALIDATED` empty) |
| Ground truth | **GROUND TRUTH UNAVAILABLE** |

Distinct concepts (Observation Value, Uncertainty, Confidence, Decision Impact,
Evidence Strength) are kept separate in code, API and UI. The formula is
documented as a **decision-support heuristic, not a validated value-of-
information metric**.

## Data Sources

| Source | Status |
|--------|--------|
| Open-Meteo Marine observations | REAL (live, time-varying) |
| Derived currents / AIS | SIMULATED / DERIVED, provenance-linked |
| Demonstration anomaly (`SIMULATED_HEATWAVE`) | DEMONSTRATION ONLY |
| Independent event ground truth | **NOT AVAILABLE** |

Reference dataset: 8 locations, **768 observations (760 real + 8 simulated)**,
3 detected (demo-labelled) events.

## APIs

| Item | Status |
|------|--------|
| Per-subsystem health (`/api/health`, `/api/v1/health`) | IMPLEMENTED / TESTED |
| TIDE endpoints (`/api/v1/tide/*`) | IMPLEMENTED / TESTED |
| Validation / benchmarks | IMPLEMENTED / TESTED |
| Demonstration (`/api/v1/demo/*`) | IMPLEMENTED / TESTED |
| Status-code & error semantics | TESTED (17 failure-recovery tests) |
| Contract reference | [`API.md`](API.md) |

## Frontend

| Item | Status |
|------|--------|
| Typecheck (`tsc -b`) | PASS (exit 0) |
| Lint (`oxlint`) | PASS (pre-existing warnings only) |
| Production build (`npm run build`) | PASS (~5.9s; pre-existing chunk-size warning) |
| Error boundaries (every route + Copilot FAB) | IMPLEMENTED |
| System-status indicator (honest states) | IMPLEMENTED |
| Demo guide + reset | IMPLEMENTED / TESTED (API) |
| In-browser visual verification | **NOT TESTED** (headless environment) |

## Cesium

| Item | Status |
|------|--------|
| Integration + asset copy at build | IMPLEMENTED / TESTED |
| Viewer lifecycle cleanup | IMPLEMENTED |
| Ion token handling (optional) | IMPLEMENTED |
| Rendered-frame performance in a browser | **NOT TESTED** |

## Simulation

| Item | Status |
|------|--------|
| Virtual observation never persisted | TESTED (unit test) |
| Benchmark never writes observations | TESTED |
| `SIMULATED` can never become `REAL` | TESTED |
| Demo reset removes only simulated rows | TESTED (real rows untouched) |

## Replay

IMPLEMENTED / TESTED. Read-only; model-only vs TIDE-assisted paths; `event-0`
replay returns 200.

## Validation

| Item | Status |
|------|--------|
| Framework | IMPLEMENTED / TESTED |
| Empirical validation | **NOT AVAILABLE** |
| False-alarm / missed-event metrics | **GROUND TRUTH UNAVAILABLE** |
| Sensitivity / edge checks | ALGORITHM CONSISTENCY TESTING (all consistent; all finite) |

## Benchmarking

IMPLEMENTED / TESTED / DEMONSTRATED. Machine-readable artifact exported to
`docs/benchmark-results/` (never overwritten).

Reference run (`budget=1`, `seed=42`, dataset 8 locations / 768 observations /
3 events):

| Strategy | decision_change_rate | mean uncertainty reduction |
|----------|----------------------|----------------------------|
| RANDOM | 1.0 | 0.1905 |
| UNIFORM | 1.0 | 0.1883 |
| UNCERTAINTY_ONLY | 1.0 | 0.1898 |
| ANOMALY_ONLY | 0.75 | 0.2527 |
| DATA_GAP_ONLY | 1.0 | 0.1898 |
| TIDE | 0.75 | 0.2527 |

`pool_is_degenerate = false` (differentiation measurable). **No strategy is
declared superior**; TIDE and ANOMALY_ONLY tie on this dataset.

## Testing

| Suite | Result |
|-------|--------|
| Backend (`unittest discover -s tests`) | **96 tests OK** |
| Phase 10 failure-recovery/edge tests | 17 added, all OK |
| Frontend typecheck | PASS |
| Frontend lint | PASS (pre-existing warnings) |
| Frontend build | PASS |
| Dependency audit (`npm audit --omit=dev`) | 0 vulnerabilities |

Edge conditions covered: invalid/unknown event and case ids (404), invalid
variable/method/depth/budget/strategy (422), unknown location (empty 200 / 404),
missing body (422), empty Copilot question (graceful 200), zero/NaN/Infinity/
null scoring inputs (finite, non-negative).

## Deployment

| Item | Status |
|------|--------|
| `docker-compose.yml` (db + backend + frontend, healthchecks, configurable env) | IMPLEMENTED |
| `Dockerfile` (backend, frontend) + `.dockerignore` | IMPLEMENTED |
| Production-mode distinction (`ENVIRONMENT`) | IMPLEMENTED |
| `docs/DEPLOYMENT.md` | IMPLEMENTED |
| `docker compose build frontend` | PASS (image `project20-frontend` built) |
| `docker compose up` (db + backend + frontend) | PASS (all three healthy) |
| PostgreSQL container | HEALTHY (`postgis/postgis:16-3.4`) |
| Backend container | HEALTHY (`project20-backend`) |
| Frontend container | HEALTHY (`project20-frontend`) |
| Cesium assets over HTTP (`/cesium/Workers/...`, `/cesium/Widgets/lighter.css`) | PASS (200) |
| Frontend→backend proxy (`/api/health`) | PASS (200) |
| Local launcher (`run.ps1`, `run.sh`) | IMPLEMENTED |

**Docker healthcheck fix (found during verification).** The frontend probe used
`wget http://localhost/`, but busybox `wget` in `nginx:alpine` resolved
`localhost` to IPv6 `::1` while nginx listens on IPv4 `0.0.0.0:80`, so the probe
always failed (`health log: exit=1`) and the container never became healthy. The
probe was changed to `http://127.0.0.1/`; the container now reports `healthy`.
This is a Docker-configuration-only change; no application code was touched.

`vite-plugin-cesium` is **not** part of this project: it is absent from
`package.json`, `package-lock.json`, `node_modules` and all commits. Cesium is
integrated via `scripts/copy-cesium.mjs` + dynamic `import('cesium')` with
`CESIUM_BASE_URL = '/cesium/'`. A previously reported `vite-plugin-cesium`
`TS2349` error is **not reproducible** in this checkout and no import change was
made.

## Performance

Measured on the reference dataset (headless, after warm-up):

| Operation | Result |
|-----------|--------|
| Startup incl. awaited TIDE warm-up | ~4.3 s |
| `GET /api/v1/health` | ~14–20 ms |
| `GET /api/v1/demo/status` (first request, was ~13.5 s) | **~371 ms** |
| `GET /api/v1/tide/candidates` (warm) | ~140–226 ms |
| `GET /api/v1/tide/validation` (warm) | ~367 ms |
| `GET /api/v1/tide/benchmarks?budget=1` | ~1.0–1.1 s |
| Frontend production build | ~5.6–5.9 s |

Fixes applied: awaited (timeout-bounded) TIDE warm-up so the first request
cannot race it; TIDE read-cache TTL raised to a configurable 120 s.

Existing tolerated warnings (unchanged, not hidden): oxlint
`react(set-state-in-effect)` across several pages, and the Vite chunk-size
warning (Cesium bundle). Neither is an error.

## Security

| Item | Status |
|------|--------|
| Tracked secrets | NONE (`.env`, `.env.*` gitignored; only `.env.example` tracked) |
| Health payload secrets | NONE (tested) |
| Dependency vulnerabilities | 0 (`npm audit --omit=dev`) |
| API input validation | 422 on invalid params; 404 on missing resources; generic 500 |
| CORS | configurable via `CORS_ORIGINS` (default `*` for local demo) |
| Debug/stack traces exposed | NONE (handler returns generic 500) |
| Frontend token | dev-only `.env.local` (untracked); **rotate if ever shared** |

## Known Limitations

- No independent ground truth ⇒ no accuracy/validation claims.
- TIDE heuristic, not a validated value-of-information model.
- Cesium rendering, responsive layout and accessibility **not browser-verified**
  in this environment (no real browser session was run).
- Docker stack verified on this host only; not validated on other
  architectures/registries.
- Live Open-Meteo data means exact numeric reproduction requires the captured
  dataset.
- In-process TIDE cache is per worker; multi-worker deployments warm separately.
- No frontend unit-test runner (verification = typecheck + lint + build).

## Scientific Claim Boundary

TIDE is **implemented, tested and demonstrated — not scientifically validated**.
Unsupported claims were removed from the presentation documents. Maturity
vocabulary and full boundaries: [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).

## Demo Readiness

**PASS** for everything verifiable headlessly: startup, health, events, TIDE
ranking/evidence/confidence/verdict, what-if simulation isolation, replay,
validation, benchmarking, demo seed/reset, production build, 96 tests.
**NOT TESTED / browser-only:** Cesium rendering, dev-server visual behaviour,
Copilot visual grounding, responsive/accessibility in a live browser.

See [`FINAL_DEMO_CHECKLIST.md`](FINAL_DEMO_CHECKLIST.md) and
[`DEMO_READINESS.md`](DEMO_READINESS.md).
