# Results and Limitations

> What the project has and has not established. The five sections below are kept
> strictly separate; software testing is never converted into scientific
> validation.

## Implemented

- 4D ocean digital twin, live ingestion, model–observation comparison with
  explainable confidence.
- Anomaly detection; event detection and naming; Event Timeline; Event DNA
  (Forensics fingerprint); Ocean Forensics.
- APEX observation recommendations.
- TIDE-Loop: candidate generation, scoring, ranking, evidence tracing,
  confidence, cautious verdicts, decision rule.
- What-if virtual observation (never persisted); Decision Replay (two modes);
  validation and benchmark framework; Ocean Copilot.
- Cesium visualisation; Docker deployment; demo mode.

## Tested

- Backend: **96 tests OK / 0 failures** (`python -m unittest discover -s tests`).
- Includes 17 Phase 10 failure-recovery/edge tests (unknown/absent resources →
  404, invalid params → 422, empty results → 200, no 500 leaks) and simulation
  isolation tests.
- Frontend: `npx tsc -b` PASS; `npx oxlint` PASS (pre-existing
  `react(set-state-in-effect)` warnings only); `npm run build` PASS (pre-existing
  chunk-size warning).
- Docker: frontend image build PASS; `docker compose up` PASS with PostgreSQL,
  backend and frontend all HEALTHY; Cesium assets served 200.
- Algorithm consistency: sensitivity `all_consistent = true`; edge cases
  `all_finite = true`.
- Dependency audit: `npm audit --omit=dev` → 0 vulnerabilities.

## Demonstrated

- Live reference dataset: 8 locations, **768 observations (760 real + 8
  simulated)**, **3 detected events** (Goa Coast: marine heatwave, confidence
  0.91; model–observation mismatch, 0.76; rapid temperature change, 0.72).
- TIDE candidate ranking, evidence, confidence and verdict observable via the
  API/UI; `event-0` replay returns 200; what-if returns a `SIMULATED` result.
- Demo seed/reset: seed creates 8 labelled `SIMULATED` rows and 0 alerts; reset
  deletes only simulated rows (real rows untouched).
- Reference benchmark (budget 1, seed 42): non-degenerate pool; **TIDE ties
  ANOMALY_ONLY**.
- **Not browser-verified:** Cesium rendering, visual behaviour, responsive layout
  and accessibility were not independently verified in a real browser session.

## Empirically Evaluated

- The **reference benchmark** is an empirical evaluation *on the reference
  dataset*: strategy behaviour, decision-change rate and mean uncertainty
  reduction are measured, with sample sizes and explicit unavailable labels.
- The consistency/sensitivity and edge-case reports empirically confirm the
  implementation matches its documented formula.
- This is evaluation of the **software's behaviour**, on one dataset, not
  validation of the **scientific hypothesis** that prioritising by TIDE improves
  real ocean outcomes.

## Not Yet Empirically Validated

- **TIDE superiority / optimality** — NOT ESTABLISHED (TIDE ties the strongest
  baseline on the reference run).
- **Optimal observation selection** — NOT ESTABLISHED.
- **Prediction accuracy** — NOT ESTABLISHED.
- **False-alarm rate** — GROUND TRUTH UNAVAILABLE.
- **Missed-event rate** — GROUND TRUTH UNAVAILABLE.
- **Generalisation** to other regions/periods — NOT ESTABLISHED.
- **Uncertainty calibration**, **information gain**, **validated cost models** —
  not implemented as validated quantities.

## Scientific claim boundary

| Claim Type | Current Status |
|------------|----------------|
| Software implementation | IMPLEMENTED |
| Algorithm consistency | TESTED |
| Simulation isolation | TESTED |
| Docker deployment | TESTED |
| Benchmark framework | IMPLEMENTED |
| Reference benchmark | DEMONSTRATED / EMPIRICALLY EVALUATED where supported |
| TIDE superiority | NOT ESTABLISHED |
| Optimal observation selection | NOT ESTABLISHED |
| Prediction accuracy | NOT ESTABLISHED |
| False alarm rate | GROUND TRUTH UNAVAILABLE |
| Missed-event rate | GROUND TRUTH UNAVAILABLE |
| Generalization | NOT ESTABLISHED |

## Limitations

1. No independent ground truth.
2. Scoring is a heuristic, not information gain.
3. Method costs are normalised demonstration assumptions.
4. Multi-observation budgets are not compounded.
5. Reference-dataset dependence (live source; exact numbers need the captured
   dataset).
6. Browser rendering/accessibility/responsive behaviour not independently
   verified.
7. In-process TIDE cache is per worker; multi-worker deployments warm separately.
8. No frontend unit-test runner (verification = typecheck + lint + build).

## Future research

`FUTURE RESEARCH` — explicitly **not implemented**:

- curvature/coverage of larger observational datasets;
- independent ground-truth acquisition (field campaign / external labels);
- longer historical periods and multi-region evaluation;
- uncertainty calibration and probabilistic information gain;
- validated observation-cost models;
- domain-expert and stakeholder evaluation;
- controlled field experiments;
- stronger baselines and statistical significance analysis;
- larger observation budgets with honest compounding.
