# TidalTwin — Demo Readiness (Phase 9)

> Only items that were actually executed and observed are checked. Browser-only
> checks (Cesium rendering, visual polish in a live browser) are left unchecked
> and marked "not browser-verified" because this phase ran headless.

## Startup

- [x] Backend starts (FastAPI app + lifespan execute via the test client)
- [ ] Frontend dev server starts (`npm run dev`) — not run headless
- [x] Frontend production build succeeds (`npm run build`)
- [x] Database available (`/api/v1/health` → Database `AVAILABLE`)

## Core Visualization

- [ ] Cesium renders in a browser — not browser-verified
- [x] Ocean data loads (760 real observations verified via health + counts)
- [x] Events load (3 detected events after seeding the demonstration anomaly)
- [x] Cesium bundle/asset copy succeeds during the production build

## Intelligence

- [x] Anomaly Radar (event detection returns events)
- [x] Forensics / Event DNA (`fingerprint(event)` returns tags; used by the demo selector)
- [x] TIDE candidate ranking (`/api/v1/tide/candidates` returns candidates)
- [x] Evidence (`/api/v1/tide/explanation` responds)
- [x] Confidence (returned inside explanation / verdict payloads)
- [x] Verdict (`/api/v1/tide/verdict` responds; cautious LIKELY_* vocabulary)

## Simulation

- [x] What If (`POST /api/v1/tide/virtual-observation` returns a result)
- [x] Explicit simulation label (`simulated_observation.status == "SIMULATED"`)
- [x] No real-data mutation (observation count unchanged; unit test)
- [x] Benchmark simulation never writes to the observation store (unit test)

## Decision

- [x] Decision Replay (`GET /api/v1/tide/events/event-0/replay` → 200)
- [x] Model-only vs TIDE-assisted modes present in the replay payload
- [x] Decision comparison (before/after decision shown in replay + what-if)

## Validation

- [x] Validation data (`/api/v1/tide/validation` → 200)
- [x] `EMPIRICALLY_VALIDATED` is honestly empty
- [x] Benchmarks (`/api/v1/tide/benchmarks?budget=1` → 200)
- [x] Missing-data handling (validation error → `INSUFFICIENT DATA`; demo event
      unavailable when no events)

## Copilot

- [x] Context-aware question answered (`POST /api/v1/assistant/ask`)
- [ ] Evidence-grounded responses visually verified in the browser — not verified

## Reliability

- [x] Error boundaries wrap every route and the Copilot FAB
- [x] Loading states (existing pages + demo guide "Loading…" state)
- [x] Empty states (demo event reports "Not available" with a reason)
- [x] Partial service failure (health reports per-subsystem; optional Cesium Ion
      is `OPTIONAL / UNAVAILABLE` without failing the app)

## Demonstration mode

- [x] `GET /api/v1/demo/status` reports demonstration data + event honestly
- [x] `POST /api/v1/demo/seed` creates labelled `SIMULATED` rows (created 8,
      detected 3 events, **0 alerts written**)
- [x] `POST /api/v1/demo/reset` deleted 8 simulation rows, real rows untouched (760)
- [x] One-click guide navigates the real routes (START TIDE DEMO)
- [x] `DEMONSTRATION DATA` / `SIMULATED OBSERVATION — DEMONSTRATION ONLY` labels

## Build

- [x] Backend tests: `96 tests OK` (`python -m unittest discover -s tests`)
- [x] Phase 9 tests: 11 health/demo/simulation-safety + 1 journey smoke
- [x] Phase 10 tests: 17 failure-recovery / edge-case API tests
- [x] Benchmark artifact exported (`docs/benchmark-results/`, budget 1, seed 42)
- [x] Frontend typecheck: `npx tsc -b` clean
- [x] Frontend lint: `npx oxlint` (pre-existing warnings only)
- [x] Frontend production build: success (pre-existing chunk-size warning only)

## Presentation views (no screenshots fabricated)

| # | View | Route |
|---|------|-------|
| 1 | 4D Ocean Digital Twin | `/globe` |
| 2 | Anomaly Radar | `/anomalies` |
| 3 | Ocean Forensics | `/forensics` |
| 4 | Event DNA | `/forensics` (fingerprint panel) |
| 5 | TIDE Command Center | `/tide` |
| 6 | TIDE Candidate + Evidence | `/tide` (evidence drawer) |
| 7 | What If We Measure Here? | `/tide` (virtual observation) |
| 8 | Decision Replay | `/tide/replay` |
| 9 | Validation | `/tide/validation` |
| 10 | Copilot | `/assistant` |

## Demonstration flow (one click)

`START TIDE DEMO` → 8-step guide navigates the real application:
Anomaly Radar → Forensics → Event DNA → TIDE → Uncertainty/Disagreement →
Candidate/Evidence → What-If → Decision Replay → Validation → Copilot.
