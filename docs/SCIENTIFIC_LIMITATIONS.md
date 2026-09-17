# TidalTwin — Scientific Limitations

> This document exists so that no reader, judge, or future maintainer mistakes a
> transparent engineering framework for a scientifically validated system.
> Nothing here is a marketing caveat; every limitation below is implemented in
> the code and reflected in the API payloads.

## Maturity vocabulary (used consistently everywhere)

| Term | Meaning for this project |
|------|--------------------------|
| **IMPLEMENTED** | Code exists and runs in the repository. |
| **TESTED** | Covered by automated tests (`backend/tests/`). |
| **DEMONSTRATED** | Observable through the running application / API. |
| **EMPIRICALLY EVALUATED / VALIDATED** | Checked against independent ground truth. **Not achieved.** |
| **NOT AVAILABLE / INSUFFICIENT DATA** | The data required to state a result does not exist. |
| **DEMONSTRATION ONLY / SIMULATED** | Generated for demonstration; never a real observation. |

TIDE is **IMPLEMENTED, TESTED and DEMONSTRATED**. Its
`EMPIRICALLY_VALIDATED` list is **intentionally empty**.

## What TIDE is — and is not

TIDE-Loop ("Trust-aware Information for Decision and Exploration") is a
**deterministic, decision-aware observation-prioritisation framework**. It is a
**decision-support heuristic**, not:

- a scientifically validated value-of-information / optimal-control model,
- a Bayesian information-gain calculation,
- a calibrated probabilistic forecast,
- an autonomous scientific discovery system.

### The scoring formula

```text
Observation Value =
  Decision Impact × Uncertainty × Data Gap × Anomaly Persistence
  ÷ max(Observation Cost, 0.05)
```

- All factors are normalised to `[0, 1]`; non-finite inputs are clamped.
- The `0.05` cost floor prevents divide-by-zero; it is not a monetary value.
- Method costs (`METHOD_COSTS`) are **`NORMALIZED OBSERVATION COST —
  DEMONSTRATION ASSUMPTION`**, not operational quotations.
- `expected_uncertainty_reduction` is a documented heuristic, explicitly **not**
  information gain.

### Distinct concepts (never to be conflated)

| Concept | What it means | What it is NOT |
|---------|---------------|----------------|
| **Observation Value** | Priority score from the formula above | a probability or a measured benefit |
| **Uncertainty** | How little is known at a location/variable | confidence |
| **Confidence** | Heuristic strength of available evidence support | a calibrated probability, and not the same as uncertainty |
| **Decision Impact** | How much the decision could change | observation value |
| **Evidence Strength** | Support from available comparison/event/gap signals | proof of a cause |

## Ground truth

There is **no independent ground-truth event label set** in this project. Event
labels are produced by the project's own `classify_events` logic. Therefore:

- False-alarm and missed-event rates are reported as **`GROUND TRUTH
  UNAVAILABLE`**.
- Detection-timing metrics are only computable when events exist, and their
  labels derive from the same system being evaluated.
- Model-vs-observed pairs **do** exist (`twin/compare.py`), so a validation
  *error* (model minus observation) is computable even without event ground
  truth. That is a comparison, not independent validation.

## Simulation boundaries

- **Virtual observations** (`POST /api/v1/tide/virtual-observation`) are
  request-derived, deterministic, and **never persisted** to
  `ocean_observations`. Enforced by tests.
- **Benchmark** simulations reuse the same pure `simulate_candidate` primitive
  and likewise never write to the store.
- **Demonstration rows** are labelled `SIMULATED` / `SYNTHETIC` by their
  `source`. `POST /api/v1/demo/reset` deletes **only** rows matching that filter;
  real observations are untouched.
- A `MODEL_DERIVED` candidate can never be reported as `REAL`.

## Verdict safety

Verdicts use cautious vocabulary (`LIKELY_SENSOR_ISSUE`,
`LIKELY_MODEL_ISSUE`, `LIKELY_MISSING_PHENOMENON`, `INSUFFICIENT_EVIDENCE`).
The system never asserts "the sensor is broken" or "the model is wrong".
Sparse or contradictory evidence returns `INSUFFICIENT_EVIDENCE`.

## Benchmark honesty

- Baselines (RANDOM, UNIFORM, UNCERTAINTY_ONLY, ANOMALY_ONLY, DATA_GAP_ONLY)
  receive the **same candidate pool and budget** as TIDE; TIDE has no advantage
  in information access.
- When every candidate's `observation_value` is zero (no detected events),
  score-based strategies tie and the benchmark reports
  `pool_is_degenerate = true`. Selection differentiation is then not measurable.
- A non-zero `decision_change_rate` is a **threshold crossing of the documented
  heuristic**, not a measured operational improvement.
- Consistency/sensitivity checks are labelled **ALGORITHM CONSISTENCY
  TESTING**, never "validation".

## Release identity

Version `1.0.0` / release name `TIDE-Loop` are **packaging identifiers**. They
do **not** claim scientific maturity or accuracy.
