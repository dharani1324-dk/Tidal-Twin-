# TIDE Benchmark Protocol

Phase 8 — Scientific Validation, Benchmarking & Reliability.

This protocol defines exactly how TIDE is benchmarked, what the numbers mean,
and what they cannot show. It is written so another engineer can reproduce every
number from the same dataset, configuration and seed.

> **TIDE is implemented, demonstrated and computationally tested. It is NOT
> scientifically or empirically validated.** No independent ground-truth dataset,
> field campaign or expert review supports its scores.

## Objective

Measure, fairly and reproducibly, how the existing TIDE decision layer behaves
relative to simple, clearly-defined baselines, and report only the metrics the
available data actually supports.

The goal is honesty about capability, not a favourable comparison. The framework
must be able to return `NOT AVAILABLE`, `GROUND TRUTH UNAVAILABLE` or
`INSUFFICIENT DATA` and does so whenever the data does not support a metric.

## Maturity vocabulary

| Term | Meaning |
| --- | --- |
| IMPLEMENTED | Code exists and runs. |
| DEMONSTRATED | Observable on the current dataset. |
| TESTED | Verified by automated tests. |
| EMPIRICALLY VALIDATED | Supported by independent ground truth and review. **TIDE is not here.** |

## Benchmark unit and cases

A **case** is one scenario to be observed. Two kinds of case exist:

- **Variable case** — `"{variable}@{depth}"`, e.g. `temperature@0`. Used when no
  detected events exist. The candidate pool is the full location set for that
  variable (or a single location for an event case).
- **Event case** — one per detected event (`event-0`, `event-1`, …), inheriting
  the event's location, variable and `began_hours_ago`. Used only when events
  exist; when there are zero events, event cases simply do not appear.

The default run uses the variables `temperature`, `wave_height`, `salinity`,
`current_speed` at depth `0`.

## Strategies

All strategies select from the **identical candidate pool** for a case and are
subject to the **identical budget**. TIDE is never given a field that the
baselines cannot also see.

| Strategy | Selection rule |
| --- | --- |
| `RANDOM` | Uniform random sample of the pool, seeded (`random.Random`). |
| `UNIFORM` | Evenly spaced along longitude (a proxy for geographic spread). |
| `UNCERTAINTY_ONLY` | Highest `uncertainty`. |
| `ANOMALY_ONLY` | Highest `anomaly_persistence`. |
| `DATA_GAP_ONLY` | Highest `data_gap`. |
| `TIDE` | Highest `observation_value` (the documented formula). |

Ties are resolved deterministically by `candidate_id`.

## Inputs

- Candidate pools and all factor fields come from the existing
  `TideEngine.rankings` output (via `app.modules.ai.tide.validation`).
- Outcome estimation reuses the existing pure primitive
  `app.modules.ai.tide.engine.simulate_candidate` — the same function behind the
  what-if (`virtual-observation`) feature. No second scoring engine is added.
- Dataset metadata is read from the live store
  (`OceanLocation`, `OceanObservation`) and the existing event detector
  (`adapters.detect_events`).

## Observation budget

`budget` is the maximum number of candidates a strategy may select per case.
Supported values: **1, 3, 5, 10**. The API accepts `1..10`.

Each selected candidate is evaluated **independently**. The framework does **not**
invent compounding effects from selecting multiple observations; a budget of `B`
produces `B` independent rows, not a simulated `B`-observation campaign. This is
a deliberate, documented simplification.

## Metrics

For every selected candidate the framework records:

| Field | Definition | Availability |
| --- | --- | --- |
| Selected candidate | id, location, variable, depth, method, cost, status | always |
| Initial / final uncertainty | before and after the simulated observation | always |
| Uncertainty reduction | `initial − final` (absolute) | always |
| Relative reduction | `reduction ÷ initial` (zero-safe) | when `initial > 0` |
| Decision change | `decision_before != decision_after` under the documented rule table | always |
| Validation error | absolute model-vs-observed difference from the existing Twin comparison | only when a model/observed pair exists |
| Detection time | hours since event start | only for event cases; otherwise `NOT AVAILABLE` |
| Evidence count | number of traceable evidence items | always |
| Observation cost | normalized demonstration cost | always |

Aggregates are computed per strategy with the sample size `N` always shown.
Mean / median / min / max are reported **only** when `N >= 3`
(`MIN_SAMPLE`). Below that the value is reported as
`INSUFFICIENT DATA (N=x)`, never averaged.

## Exclusions and unavailable metrics

- **False alarm / missed event** — `GROUND TRUTH UNAVAILABLE`. The project has no
  independent event labels; detected events are produced by the system's own
  thresholds and model baselines, so they cannot serve as ground truth.
- **Detection time** — `NOT AVAILABLE` in the current dataset because there are
  zero detected events.
- **Validation error** — `NOT AVAILABLE` for variable/depth combinations with no
  model/observed pair.
- Cases or strategies that produce no selection are reported with `N = 0` rather
  than a fabricated statistic.

## Ground truth statement

There is **no** independent ground truth in this project. Every apparent
"event" is system-derived. Consequently:

- False-alarm and missed-event rates cannot be computed.
- "Accuracy", "detection skill" and "superiority" claims are out of scope.
- Model-vs-observed differences describe agreement with the existing Twin
  comparison, not forecast skill against independent measurements.

## Simulation and isolation

- All outcome values are **simulated / demonstration heuristics**, never field
  measurements. Every row carries `SIMULATED` observation status and the
  `SIMULATED OBSERVATION — DEMONSTRATION ONLY` label.
- The framework is **read-only**. Running validation or a benchmark must not
  change the number of persisted `OceanObservation` rows. This is enforced by an
  automated isolation test.
- Observation cost is a **`NORMALIZED OBSERVATION COST — DEMONSTRATION
  ASSUMPTION`**, not a monetary figure.

## Algorithm consistency testing

`GET /api/v1/tide/validation` includes:

- **Sensitivity** — confirms the formula responds monotonically and in the
  documented direction when each factor changes.
- **Ranking sensitivity** — confirms a candidate's rank responds when one factor
  changes.
- **Edge cases** — confirms zero, one, null, `NaN`, `Infinity` and out-of-range
  inputs never produce `NaN` / `Infinity` / undefined scores.

These are labelled **ALGORITHM CONSISTENCY TESTING**. They verify the
implementation matches its documented formula; they are **not** scientific
validation and do not establish that the formula is correct for the ocean.

## Reproducibility

Every report records: algorithm version, dataset id/version, event/case ids,
configuration (budget, strategies, variables, depth), seed, cost assumption and a
timestamp. Rerunning with the same inputs and seed reproduces identical rows.
`RANDOM` uses a per-(case, strategy) seeded generator so its output does not
depend on evaluation order.

## Scientific claim boundary

**What this validation can show:** implementation consistency, reproducibility,
ranking/sensitivity behaviour, deterministic behaviour, observed benchmark
outcomes with sample size, and simulation isolation.

**What it cannot show:** universal superiority over baselines, operational
forecasting performance, causal sensor/model/phenomenon attribution, real-world
deployment success, universal decision improvement, calibrated uncertainty, or
guaranteed observation value.

## Limitations

1. No independent ground truth.
2. Outcomes are demonstration heuristics, not measurements.
3. Observation cost is a normalized assumption.
4. Multi-observation campaigns are not compounded.
5. On the current dataset `anomaly_persistence = 0` for all candidates (no
   detected events), so `observation_value = 0` everywhere and score-based
   strategies tie (resolved by `candidate_id`). Selection differentiation is
   therefore **not measurable** on this dataset, even though outcome metrics
   remain valid.
