# TIDE Validation Report

Phase 8 — Scientific Validation, Benchmarking & Reliability.

Generated: TIDE algorithm version `1.0`. All results below were produced by the
framework on the project's current live store via
`app.modules.ai.tide.validation`. They are **demonstration results on real
inputs**, not field measurements, and TIDE is **not scientifically validated**.

## 1. Repository assessment

- TIDE already had a scoring formula, ranking, evidence, confidence, verdict,
  what-if simulation, and Decision Replay (Phases 3–7). Phase 8 adds a validation
  and benchmarking layer **around** those engines without modifying their
  behaviour.
- Existing validation surfaces (`app/api/validation.py`) already expose model
  skill, deviation and observation confidence; Phase 8 does not duplicate them.
- The only reusable outcome primitive available for simulation is
  `simulate_candidate` (used by what-if). The benchmark reuses it directly.
- The current dataset has **zero detected events**, which materially constrains
  which metrics are honestly computable.

## 2. Validation framework

New reusable pipeline in `backend/app/modules/ai/tide/validation.py`:

`INPUT (candidate pools) → SCORING (existing formula) → RANKING (existing engine)
→ SELECTION (per strategy, fair) → SIMULATED RESULT (existing primitive) →
DECISION (existing rule table) → METRICS (aggregated with N)`

Key properties:

- Strategies share one candidate pool and one budget (fairness asserted in the
  report and tested).
- All metrics are zero/None-safe; unsupported metrics return `NOT AVAILABLE` /
  `GROUND TRUTH UNAVAILABLE` / `INSUFFICIENT DATA (N=x)`.
- `pool_fn` and `sim_fn` are injectable, so the framework is unit-testable
  without a database.
- Read-only: an automated test confirms the observation count is unchanged
  before/after a full validation + benchmark run.

## 3. Benchmark strategies

`RANDOM`, `UNIFORM`, `UNCERTAINTY_ONLY`, `ANOMALY_ONLY`, `DATA_GAP_ONLY`, `TIDE`
(definition and fairness rules in `docs/TIDE_BENCHMARK_PROTOCOL.md`).

## 4. Metrics

Uncertainty reduction (absolute + relative, zero-safe), decision change,
validation error (model-vs-observed absolute error), detection time, evidence
count, and normalized observation cost. False alarm / missed event are
`GROUND TRUTH UNAVAILABLE`. Aggregates require `N >= 3`.

## 5. Tests

- `backend/tests/test_tide_validation.py` adds 30 tests: strategy selection and
  fairness, seeded reproducibility, benchmark determinism, sample-size gating,
  finite-output guarantees, ground-truth honesty, sensitivity/edge cases,
  contradictory-evidence verdicts, evidence-id stability, confidence
  distinctness, simulation isolation, the validation/benchmark APIs, and the
  Copilot validation intent.
- Full backend suite: **67 tests OK** (previously 37).
- Frontend has no unit-test runner; verified with `tsc -b`, `oxlint` and
  `npm run build` (all clean apart from the pre-existing tolerated warnings).

## 6. Benchmark results (actual, current dataset)

Dataset: `tidaltwin-live-store` / `live` — **8 locations, 768 observations,
0 detected events**. Candidate pool per variable case: **8** candidates, of which
**0** have a non-zero `observation_value`.

Because there are no detected events, `anomaly_persistence = 0` for every
candidate, so `observation_value = 0` for all candidates. All score-based
strategies therefore **tie** and fall back to `candidate_id` ordering. Selection
differentiation is **not measurable on this dataset**; the outcome metrics below
remain valid but largely identical across strategies.

`N` is the number of evaluated selections. Values shown as percentages are the
mean reduction in uncertainty; each result is a demonstration simulation.

### Budget = 1

| Strategy | N | Mean reduction | Median | Min | Max | Decision changes | Validation error | Detection time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RANDOM | 4 | 19.05% | 18.98% | 18.84% | 19.42% | 4 / 4 | INSUFFICIENT DATA (N=2) | NOT AVAILABLE |
| UNIFORM | 4 | 18.83% | 18.84% | 18.21% | 19.42% | 4 / 4 | INSUFFICIENT DATA (N=2) | NOT AVAILABLE |
| UNCERTAINTY_ONLY | 4 | 18.98% | 18.98% | 18.84% | 19.11% | 4 / 4 | INSUFFICIENT DATA (N=2) | NOT AVAILABLE |
| ANOMALY_ONLY | 4 | 18.98% | 18.98% | 18.84% | 19.11% | 4 / 4 | INSUFFICIENT DATA (N=2) | NOT AVAILABLE |
| DATA_GAP_ONLY | 4 | 18.98% | 18.98% | 18.84% | 19.11% | 4 / 4 | INSUFFICIENT DATA (N=2) | NOT AVAILABLE |
| TIDE | 4 | 18.98% | 18.98% | 18.84% | 19.11% | 4 / 4 | INSUFFICIENT DATA (N=2) | NOT AVAILABLE |

### Budget = 3

| Strategy | N | Mean reduction | Median | Min | Max | Decision changes | Validation error | Detection time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RANDOM | 12 | 18.98% | 18.84% | 18.21% | 19.42% | 12 / 12 | 0.1427 | NOT AVAILABLE |
| UNIFORM | 12 | 18.93% | 18.84% | 18.21% | 19.42% | 12 / 12 | 0.1015 | NOT AVAILABLE |
| UNCERTAINTY_ONLY | 12 | 18.88% | 18.84% | 18.21% | 19.42% | 12 / 12 | 0.1620 | NOT AVAILABLE |
| ANOMALY_ONLY | 12 | 18.88% | 18.84% | 18.21% | 19.42% | 12 / 12 | 0.1620 | NOT AVAILABLE |
| DATA_GAP_ONLY | 12 | 18.88% | 18.84% | 18.21% | 19.42% | 12 / 12 | 0.1620 | NOT AVAILABLE |
| TIDE | 12 | 18.88% | 18.84% | 18.21% | 19.42% | 12 / 12 | 0.1620 | NOT AVAILABLE |

Budgets 5 and 10 behave the same way (120 and 192 evaluated selections
respectively; mean reduction converges to 18.88%).

**No strategy is declared superior.** The small differences are within the
range produced by candidate selection under a degenerate score, and the
"validation error" column mixes different selected locations/variables; it is
reported per aggregate only when `N >= 3` and is not a skill score.

## 7. Algorithm consistency results

- **Sensitivity:** all four benefit factors increase the score and cost
  decreases it — `all_consistent = true`.
- **Ranking sensitivity:** available; target candidate rank responds to factor
  changes across the 8-candidate pool.
- **Edge cases:** zero, one, tiny/huge cost, null, `NaN`, `Infinity` and
  out-of-range inputs all produce finite, non-negative scores —
  `all_finite = true`.

These are **ALGORITHM CONSISTENCY TESTING**, not scientific validation.

## 8. APIs

- `GET /api/v1/tide/validation` — maturity, dataset, ground truth, boundary,
  sensitivity, edge cases, reproducibility.
- `GET /api/v1/tide/benchmarks` — machine-readable report
  (`budget`, `variables`, `strategies`, `depth_m`, `seed`).
- `GET /api/v1/tide/benchmarks/{case_id}` — case/event-level drill-down.

All return the `{success, data, error}` envelope; invalid input returns 422 and
an unknown case returns 404.

## 9. Frontend

`/tide/validation` **TIDE Validation Center**: validation status and maturity,
dataset and ground-truth honesty, scientific claim boundary, consistency and
edge-case results, reproducibility, limitations, the neutral "Observed
uncertainty reduction by strategy" chart, the decision-outcome table (no winner),
a budget control (1/3/5/10), and per-row drill-down (event, location, depth,
variable, observation, evidence, before/after uncertainty, validation error,
detection time). Linked from the TIDE Command Center header and the sidebar. The
Copilot gains a `tide_validation` intent (capability card + Assistant chip)
answering "Is TIDE scientifically validated?" with a careful *tested, not
validated* answer.

## 10. Files changed

Backend: `app/modules/ai/tide/scoring.py` (algorithm version),
`app/modules/ai/tide/verdicts.py` (contradictory-evidence gate),
`app/modules/ai/tide/validation.py` (new), `app/api/tide.py` (endpoints),
`app/modules/ai/nlp/copilot.py` (intent + answer),
`app/api/assistant.py` (capability card), `tests/test_tide_validation.py` (new).
Frontend: `api/client.ts`, `types/tide.ts`, `pages/TideValidation.tsx` +
`.css` (new), `pages/Tide.tsx`, `pages/Assistant.tsx`, `App.tsx`.
Docs: this report, `docs/TIDE_BENCHMARK_PROTOCOL.md`, updates to
`docs/TIDE_ALGORITHM.md` and `docs/TIDE_IMPLEMENTATION_PLAN.md`.

## 11. Scientific limitations

- No independent ground truth, so no accuracy, false-alarm or detection-skill
  claim is possible.
- Outcomes are demonstration heuristics derived from existing inputs.
- Observation cost is a normalized demonstration assumption.
- The current dataset yields a degenerate `observation_value` ranking.
- Consistency testing validates the implementation, not the ocean model.

## 12. Remaining work

- Introduce an independent ground-truth dataset (field campaign / external event
  labels) to enable false-alarm, missed-event and true detection-time metrics.
- Support multi-observation campaigns with honest compounding if required.
- Re-run the protocol after each algorithm-version bump and publish updated
  numbers with their `N`.
