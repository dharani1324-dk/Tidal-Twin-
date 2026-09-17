# TIDE-Loop Implementation Plan

## Inspection summary

TidalTwin is a React 19 + TypeScript/Vite frontend and a FastAPI + SQLAlchemy
backend. PostgreSQL/PostGIS is the configured persistent store. CesiumJS powers
the primary 3D globe; Three.js is also available. Deployment is Docker Compose
with PostGIS, FastAPI, and nginx/Vite frontend containers. No authentication or
automated test framework is currently present.

Existing assets to reuse:

- `OceanObservation` and `OceanLocation` provide the observation/location base;
  observations already include depth, source, and a coarse `data_type`.
- `/api/v1/twin` and `modules/ai/twin` already provide comparison,
  disagreement, confidence, anomaly, event, evidence explanation, and
  situation capabilities.
- `/api/v1/intelligence` and `modules/ai/forensics` already expose coverage,
  uncertainty, priority, coverage simulation, timelines, forensic analysis,
  fingerprints, and what-if primitives.
- `/api/v1/apex/recommendations` already offers a coverage/event-oriented
  observation recommender; it will become an input to TIDE, not a competing
  planner.
- `DigitalTwin.tsx` and `CesiumGlobe.tsx` already display uncertainty rings,
  sampling-priority rings, Argo paths, disagreement patches, and anomalies.
- The rule-based Ocean Copilot already routes "where should we sample next?"
  to the APEX recommender.

## Target design

`modules/ai/tide/` will be a pure, modular domain layer. It will consume
existing persisted observations and Twin/Forensics outputs through small
adapters, so scientific models or data feeds can later be replaced without
changing API or UI contracts.

```text
Ocean observations + model/twin outputs + forensics
                    |
              TIDE adapters
                    |
  disagreement -> uncertainty -> data gap -> decision impact/cost
                    |
       next-best observation -> evidence/verdict/confidence
                    |
       virtual observation -> replay -> decision regret
```

All synthetic or model-produced records will carry one of `REAL`,
`HISTORICAL`, `SYNTHETIC`, `SIMULATED`, or `MODEL_DERIVED`; UI/API responses
will surface that status rather than presenting a simulation as a measurement.

## Phased implementation

### Phase 3 — domain engine

1. Add typed Pydantic domain contracts in `app/schemas/tide.py` for candidate
   observations, scores, gaps, disagreements, evidence, and decisions.
2. Add `app/modules/ai/tide/` services: observation manager, uncertainty,
   data-gap, disagreement adapter, decision-impact, cost, and planner.
3. Implement the transparent configurable score:
   `impact * uncertainty * gap * persistence / max(cost, epsilon)`.
   Component inputs remain normalized to 0–1; the response returns both the
   components and expected uncertainty reduction.
4. Add a deterministic seed-backed demonstration adapter only where current
   data is absent, with `SYNTHETIC` status and reproducible seed.
5. Add `/api/v1/tide/candidates`, `/rankings`, `/uncertainty`, `/data-gaps`,
   and `/disagreements`. Existing Twin/Intelligence/APEX endpoints remain.

### Phase 4 — explanation and verdicts

1. Add evidence and confidence builders plus sensor/model/missing-phenomenon/
   insufficient-evidence verdict rules.
2. Return the required verdict, confidence, evidence, alternative explanation,
   and next observation from `/api/v1/tide/verdict` and `/evidence`.
3. Add an Event DNA adapter that appends TIDE evidence and recommendation to
   the existing Forensics fingerprint output.

### Phase 5 — virtual observation

1. Add a clearly labelled `POST /api/v1/tide/virtual-observation` operation.
2. Generate deterministic, plausible local simulated readings from model and
   nearby observation context; never persist it as a real observation.
3. Return before/after uncertainty, anomaly rank, decision, confidence, and a
   `decision_unchanged` flag.

### Phase 6 — decision replay and regret

1. Build replay frames from existing observation timelines and the synthetic
   demo scenario when real history is insufficient.
2. Add `/api/v1/tide/decision-replay` and `POST /api/v1/tide/replay`.
3. Calculate an explicitly non-universal, configurable regret comparison for
   model-only versus TIDE-assisted decisions.

### Phase 7 — UI and globe

1. Add a `/tide` TIDE-Loop command-center route using the existing app shell,
   design tokens, Axios client, and Digital Twin visual language.
2. Add an optional `tideRecommendations` globe overlay to `CesiumGlobe` using
   distinctive but restrained rings/markers and current layer lifecycle rules.
3. Add selection, filters, expandable evidence, real/simulated badges, and the
   before/after virtual-observation panel.
4. Link selected recommendation/event to existing Digital Twin and Forensics
   deep links instead of cloning their displays.

### Phase 8 — Copilot

Extend the existing rule-based intent router to call TIDE services for next
sampling, evidence, uncertainty, model-sensor verdict, virtual observation,
and replay questions. Responses will retain location IDs and source/status
context for map links.

### Phase 9 — testing and verification

Introduce pytest for backend domain and API tests. Cover ranking monotonicity,
safe zero-cost handling, all verdict classes, virtual-observation uncertainty
reduction/unchanged decisions, replay ordering/hiding/regret, and data-status
separation. Run backend tests and `npm.cmd run build` after each UI phase.

### Phase 10 — demo and documentation

Create the persistent low-oxygen demonstration only after the engine is
complete. Add `TIDE_ARCHITECTURE.md`, `TIDE_API.md`, `TIDE_ALGORITHM.md`,
`TIDE_DEMO.md`, and a concise README section with the approved positioning.

## Integration constraints

- Do not alter current API response shapes or remove pages/routes.
- Do not make database migrations mandatory for Phase 3; use typed domain
  responses first. Persist recommendations/replays only in a later migration
  when product requirements demand audit history.
- Keep expensive ranking server-side and request-driven; do not recalculate it
  during Cesium render cycles.
- Treat unsupported variables in existing data as unavailable, not inferred as
  real observations.

## Implementation status — Phase 5 interactive frontend

Phase 3 (domain engine), Phase 4 (explanation/verdicts), Phase 5 (virtual
observation), Phase 7 (UI + globe), and Phase 8 (Copilot) are implemented:

- `POST /api/v1/tide/virtual-observation` exists and is deterministic and
  non-persisting. It derives the simulated reading from existing Twin compare
  inputs (observed, then model, then latest persisted temperature), marks the
  reading `SIMULATED`, and returns before/after uncertainty, anomaly risk,
  ranking, decision, and confidence plus `decision_result` and notes. It never
  writes to `OceanObservation`.
- `GET /api/v1/tide/events/event-{index}` composes the existing detected event
  with its existing Forensics fingerprint/Event DNA and the TIDE context.
- NEW `/tide` route → `pages/Tide.tsx` (TIDE Command Center) using the existing
  app shell and design tokens: candidate list with real scores, "Why This
  Location", confidence + verdict panel, Event DNA→TIDE panel, deterministic
  explanation panel, before/after What-If simulator, status badges, and
  loading/error/empty states. No new globe was created.
- `CesiumGlobe` gained a `tide` layer key, a `tideCandidates` prop, and
  ranked decision markers (turquoise diamond + `#rank.` label); `DigitalTwin`
  toggles it via the existing Data Layers panel (default off).
- The Copilot `tide` intent now answers evidence, verdict, Event DNA, and
  what-if questions directly from the engine using `ans_tide(db, loc, text)`
  and adds a TIDE capability card + sample chips.
- Backend tests (unittest, `backend/tests/test_tide_domain.py`) cover rankings,
  verdicts, traceability, and the new virtual-observation endpoint. Frontend
  verified with `npm run lint` (oxlint) and `npm run build` (copy:cesium &&
  tsc -b && vite build).

Remaining roadmap: pytest migration, later phase-10 demo data and reference
docs.

## Implementation status — Phase 6 decision replay

Reading replay is implemented end to end (read-only, demo-scoped):

- `backend/app/modules/ai/tide/replay.py` adds `ReplayEngine.build(event_id, …)`
  (request-derived, deterministic, never persists) and the pure composer
  `build_replay(ctx, candidate, sim, *, event_id, variable, depth_m)`. It
  composes existing Phase 3/4/5 engines — `event_context`, `rankings`,
  `virtual_observation` — into a 10-step two-mode story:
  `EVENT_START → NORMAL → EARLY_SIGNAL → ANOMALY_DETECTED →
  MODEL_SENSOR_DISAGREEMENT → HIGH_UNCERTAINTY → TIDE_RECOMMENDATION →
  OBSERVATION → DECISION → VALIDATION`.
- Both modes are identical until `OBSERVATION`; `MODEL-ONLY REPLAY` keeps the
  model state, `TIDE-ASSISTED REPLAY` incorporates the simulated reading
  (always `observation_status = SIMULATED`). The observation is never written
  to the store and every simulated value carries the
  `SIMULATED OBSERVATION - DEMONSTRATION ONLY` caveat.
- Payload includes step snapshots, mode summaries, a side-by-side comparison
  (uncertainty / anomaly risk / confidence / decision / detection-time with
  deltas and `calculated` flags), a decision-change summary grounded in the
  documented `DECISION_RULES` table, the demonstration-only regret metric
  (`0.5·(unc_before − unc_after) + 0.5·(conf_after − conf_before)`, clamped,
  labelled `DEMONSTRATION METRIC - NOT A SCIENTIFIC VALIDATION METRIC`),
  a validation block (model-only real vs TIDE-assisted simulated, or
  `VALIDATION DATA UNAVAILABLE` when no value exists), uncertainty/evidence
  journeys, the seven-step TIDE loop status, trust labels, and notes.
- API (see `app/api/tide.py`):
  - `GET /api/v1/tide/events` — index of playable events in `event-N` order
    (replaces the planned `POST /replay` with a safer, read-only GET).
  - `GET /api/v1/tide/events/{event_id}/replay` — full replay; query params
    `location_id`, `variable`, `depth_m`, `observation_type`, `value`;
    `TIDE_INVALID_REQUEST` (422) for bad variable/depth, `TIDE_EVENT_NOT_FOUND`
    (404) when it cannot be built; validated by the `DecisionReplay` schema.
- Schemas added in `app/schemas/tide.py` (`ReplayState`, `ReplayStep`,
  `ReplayModeSummary`, `ReplayMetric`, `ReplayComparison`, `ReplayDecision`,
  `ReplayRegret`, `ReplayValidation{,Block}`, `ReplayJourneyPoint`,
  `ReplayEvidence`, `ReplayLoopStatus`, `DecisionReplay`).
- Frontend: `/tide/replay` route → `pages/DecisionReplay.tsx` + CSS. Event
  picker (from `fetchTideEventIndex`), playback controls + step dots, mode
  summaries side-by-side, comparison table and documented rules, uncertainty
  journey chart (recharts), evidence journey, TIDE loop badges, decision banner,
  validation card, regret ring, Event DNA, trust/limitations, and `CesiumGlobe`
  replay markers (event beacon + candidate + simulated-observation sprites,
  camera focus at the observation step). Entry points: `Tide.tsx` (header
  button + "Open Decision Replay" from the what-if result) and `Forensics.tsx`
  (per-event "Replay decision" link, variable mapped onto TIDE keys).
- Backend tests added in `backend/tests/test_tide_replay.py` (regret clamping,
  full timeline, mode divergence + SIMULATED isolation, decision change,
  comparison numerics, validation availability, trust mapping, evidence
  ordering, and API contract: index order, replay envelope, 404 and 422).
  Full suite: 33 tests OK. Frontend verified with `tsc -b`, `oxlint`, and
  `npm run build`.

Note: event replay requires at least one threshold-crossing detected event in
the store; `GET /api/v1/tide/events` reflects whatever `detect_events` finds.

## Implementation status � Phase 7 integrated ocean intelligence experience

Phase 7 adds **no new engines and no duplicate systems**. It composes the
existing Digital Twin, Anomaly Radar, Forensics, Intelligence, TIDE, What-If,
Decision Replay, Validation and Copilot surfaces into one explainable workflow:
`OBSERVE ? DETECT ? INVESTIGATE ? UNDERSTAND ? PRIORITIZE ? OBSERVE NEXT ?
SIMULATE ? DECIDE ? VALIDATE` (+ `EXPLAIN`).

- New frontend workspace under `frontend/src/components/workspace/`:
  - `workflow.css` / `workspace.css` � shared styling for the workflow header,
    trust chips, quality indicator, meters, brief tiles, health chips, graph
    chain and the evidence drawer.
  - `WorkflowHeader.tsx` � the nine-stage rail plus an `EXPLAIN � COPILOT`
    chip. Every stage links to an existing route (`/globe`, `/anomalies`,
    `/forensics`, `/intelligence`, `/tide`, `/tide/replay`, `/validate`,
    `/scenarios`); no routes or engines were duplicated.
  - `IntelligenceBrief.tsx` � presentational brief tiles (WHAT / WHERE / WHEN /
    WHAT CHANGED / CONFIDENCE / DISAGREES / WHY IT MATTERS / OBSERVE NEXT /
    EVIDENCE / WHAT IF / HOW VALIDATED) plus direct actions.
  - `IntelligenceWorkspace.tsx` � the container. Reads the real endpoints
    (`fetchCoverage`, `fetchValidationSituation`, `fetchHealthScore`,
    `fetchTideCandidates`, `fetchTideExplanation`, `fetchTideVerdict`,
    `fetchTideEventContext`, `fetchTideEventIndex`) and persists context via the
    existing URL parameter `?location_id=` � no new global state store.
  - `EvidenceDrawer.tsx` � a single global drawer that renders the **same**
    `TideEvidence` contract used by TIDE / What-If / Replay (deduped and grouped
    by `source_system`), so there is one evidence vocabulary everywhere.
  - `IntelligenceGraph.tsx` � the Event DNA ? TIDE ? Decision chain; empty
    stages read `DATA UNAVAILABLE`.
  - `SystemHealth.tsx` � subsystem chips resolved from the actual responses:
    `AVAILABLE` (reachable + data), `LIMITED` (reachable + empty),
    `UNAVAILABLE` (unreachable).
  - `UncertaintyGauge.tsx`, `DataQualityIndicator.tsx`, `TrustBadge.tsx` �
    shared trust/quality visuals. Uncertainty, confidence, observation value and
    decision impact are shown as four **distinct** meters; `TrustBadge` exposes
    the REAL / HISTORICAL / MODEL_DERIVED / SIMULATED / SYNTHETIC /
    INSUFFICIENT_EVIDENCE vocabulary and marks simulated data with the
    `SIMULATED OBSERVATION � DEMONSTRATION ONLY` caveat.
- The workspace is embedded in `pages/Dashboard.tsx` immediately after the
  situation strip. When the engines have no signals it degrades honestly
  (`DATA UNAVAILABLE`, "no threshold-crossing events � honest reading of a calm
  ocean") rather than fabricating values.
- `pages/Tide.tsx` gains an **Observation Value formula** card showing
  `Decision Impact � Uncertainty � Data Gap � Anomaly Persistence � Observation
  Cost` with per-factor bars, the resulting value, the expected uncertainty
  reduction, and the caveat that observation value is a decision-support
  heuristic, not a scientifically validated information-gain metric.
- Copilot gains an `intelligence brief` intent end to end:
  - `app/modules/ai/nlp/copilot.py` adds `ans_brief(db, loc)` returning
    structured `ANSWER / EVIDENCE / CONFIDENCE / LIMITATIONS / NEXT ACTION`
    text built from the real TIDE rankings, validation `situation_panel`,
    `classify_events`, the forensics `health_score`, and the latest observation,
    with honest degradation when data is missing.
  - `app/api/assistant.py` advertises the `brief` capability card and the
    sample prompt "Give me the ocean intelligence brief."; the same prompt is a
    default chip in `pages/Assistant.tsx`.
- Backend tests added in `backend/tests/test_copilot_brief.py` (intent
  detection, structured sections from real data, honest degradation, and the
  `/api/v1/assistant/ask` envelope). Full suite: 37 tests OK. Frontend verified
  with `tsc -b`, `oxlint` and `npm run build`.

Note: Phase 7 is integration only. It reuses the existing Cesium globe, the
existing TIDE evidence contract, the existing URL-parameter context pattern and
the existing Copilot � nothing is rebuilt, and no scientific value is ever
hardcoded.

## Phase 8 � Scientific Validation, Benchmarking & Reliability

Phase 8 adds measurement and honesty around the existing TIDE engines. Nothing in
Phases 3�7 is rebuilt or changed in behaviour.

- `app/modules/ai/tide/scoring.py` now exposes `TIDE_ALGORITHM_VERSION = "1.0"`
  (bump on any behaviour change).
- `app/modules/ai/tide/validation.py` (new) is the reusable, read-only pipeline:
  `INPUT -> SCORING -> RANKING -> SELECTION -> SIMULATED RESULT -> DECISION ->
  METRICS`. It defines the baselines `RANDOM`, `UNIFORM`, `UNCERTAINTY_ONLY`,
  `ANOMALY_ONLY`, `DATA_GAP_ONLY`, `TIDE`; enforces a shared candidate pool and
  budget (fairness); supports budgets 1/3/5/10; aggregates with an always-visible
  `N` and a `MIN_SAMPLE = 3` gate; and returns `NOT AVAILABLE` /
  `GROUND TRUTH UNAVAILABLE` / `INSUFFICIENT DATA` whenever a metric is not
  supported. It also provides sensitivity, ranking-sensitivity and edge-case
  reports labelled **ALGORITHM CONSISTENCY TESTING**, a degeneracy diagnostic,
  timing, and injectable `pool_fn` / `sim_fn` for database-free tests.
- `app/modules/ai/tide/verdicts.py` � `classify_verdict` gains optional
  `agreeing_observations` / `disagreeing_observations`; contradictory evidence
  (>= 50% disagreeing) returns `INSUFFICIENT_EVIDENCE`. Defaults preserve the
  original behaviour.
- `app/api/tide.py` adds `GET /api/v1/tide/validation`,
  `GET /api/v1/tide/benchmarks` and `GET /api/v1/tide/benchmarks/{case_id}` with
  input validation and the existing `{success, data, error}` envelope.
- Copilot gains a `tide_validation` intent (`ans_tide_validation`) answering
  "Is TIDE scientifically validated?" and related benchmark/reproducibility
  questions with a careful *tested, not validated* answer, plus a capability
  card and a default Assistant chip.
- Frontend adds the `/tide/validation` **TIDE Validation Center**
  (`pages/TideValidation.tsx` + `.css`): maturity, dataset, ground-truth honesty,
  scientific claim boundary, consistency/edge-case results, reproducibility,
  limitations, a neutral "observed uncertainty reduction by strategy" chart, a
  decision-outcome table with no winner, a budget control, and per-selection
  drill-down. It is linked from the TIDE Command Center header and the sidebar.
- Tests: `backend/tests/test_tide_validation.py` (30 tests) covers selection
  fairness, seeded/deterministic benchmarks, finite outputs, ground-truth
  honesty, contradictory verdicts, stable evidence ids, confidence distinctness,
  simulation isolation (observation count unchanged) and the new APIs.
- Docs: `docs/TIDE_BENCHMARK_PROTOCOL.md` and `docs/TIDE_VALIDATION_REPORT.md`
  (new), plus this plan and `docs/TIDE_ALGORITHM.md`.

Verification: backend **67 tests OK**; frontend `tsc -b`, `oxlint` and
`npm run build` clean apart from the pre-existing tolerated warnings. Actual
benchmark numbers, including the dataset's degenerate zero-observation-value
ranking, are recorded honestly in `docs/TIDE_VALIDATION_REPORT.md`. No scientific
result is fabricated, and TIDE remains explicitly not scientifically validated.

---

## Phase 9 — Final Engineering Hardening + Demonstration Mode

Phase 9 hardens reliability, performance, startup, demo readiness and honesty.
No existing engine is rebuilt and no new scientific feature is added.

- **Health**: `app/api/health.py` (new) serves `GET /api/health` and
  `GET /api/v1/health` with per-subsystem checks (backend, database + PostGIS,
  ocean data, TIDE modules, Copilot, Cesium) using the honest vocabulary
  `AVAILABLE` / `LIMITED` / `UNAVAILABLE` / `OPTIONAL / UNAVAILABLE`. No secrets
  are returned.
- **Environment validation**: `app/core/config.py` gains `ENVIRONMENT`,
  `CORS_ORIGINS`, `CESIUM_ION_TOKEN`, `cors_origins()` and
  `validate_environment()`; issues are logged clearly at startup. CORS now reads
  from config instead of a hard-coded `*`.
- **Logging**: `app/core/logging_config.py` + request middleware and an unhandled
  exception handler log method/path/status/duration and failures — never bodies,
  headers or secrets.
- **Performance**: profiling showed `uncertainty_inputs` (~2.3s) and
  `apex_candidates` (~3.5s) dominate TIDE latency. A short-TTL read cache in
  `adapters.py` (`invalidate_caches()`) plus a startup warm-up reduces warm TIDE
  ranking calls from ~5.9s to ~0.16s and validation status from ~5s to ~0.3s.
  A lightweight TIDE module probe replaces the heavy ranking inside health.
- **Demonstration mode**: `app/api/demo.py` (new) provides
  `GET /api/v1/demo/status`, `POST /api/v1/demo/seed`,
  `POST /api/v1/demo/reset`. Seeding reuses `scripts.simulate_anomaly.simulate`
  with `scan=False`, so it writes **labelled simulated observations only and no
  alerts**. Reset deletes only simulation-labelled rows. The status endpoint
  reports the **DEMONSTRATION EVENT** chosen by practical availability (Event
  DNA + candidates + evidence + timeline), explicitly not a scientific ranking.
- **Frontend**: `ErrorBoundary` wrapping every route and the Copilot FAB;
  `SystemStatusPill` (real health poll + accessible text states); `DemoGuide`
  (one-click START TIDE DEMO, 8-step real navigation, seed/reset, labels).
- **Docs**: updated `README.md`; new `docs/ARCHITECTURE.md` and
  `docs/DEMO_READINESS.md`.
- **Tests**: `backend/tests/test_health_demo.py` (11 tests: health shape, secret
  safety, overall-status logic, demo status honesty, simulation classification,
  reset filter safety, virtual-observation non-persistence, candidate status) and
  `backend/tests/test_smoke_journey.py` (full API journey smoke test).

Verification: backend **79 tests OK**; frontend `tsc -b`, `oxlint` and
`npm run build` clean apart from the pre-existing tolerated warnings. The
demonstration dataset is `8 SIMULATED / 760 REAL` observations producing 3
detected (demo-labelled) events; reset leaves the 760 real observations intact.
