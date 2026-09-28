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
  non-simulated source records are untouched.
- A `MODEL_DERIVED` candidate can never be reported as `REAL`.

## Verdict safety

Verdicts use cautious vocabulary (`LIKELY_SENSOR_ISSUE`,
`LIKELY_MODEL_ISSUE`, `LIKELY_MISSING_PHENOMENON`, `INSUFFICIENT_EVIDENCE`).
The system never asserts "the sensor is broken" or "the model is wrong".
Sparse or contradictory evidence returns `INSUFFICIENT_EVIDENCE`.

The TIDE hypotheses endpoint lists possible surface heat accumulation, reduced
vertical mixing, and horizontal advection explanations. It reports only
available measurement comparisons as support or contradiction; required but
absent heat flux, wind, profile, or spatial-gradient evidence is listed as
missing. Confidence is `100 × evidence-direction support × required-signal
coverage`, with both factors returned alongside the result. It is a traceable
heuristic score, not a probability or causal conclusion.

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

## Microplastics module

Full detail in `docs/MICROPLASTICS.md`. The load-bearing limitations:

- **The NOAA NCEI collection is an archive, not a live feed.** Records in the
  Indian Ocean window span 2013-05-27 to 2021-12-08 only. Nothing the module
  reports describes present-day conditions. Recency is therefore measured
  against the newest sample *in the collection*, not against today, and the
  payload states `is_live_feed: false`.
- **Concentrations are never combined across unit families.** `pieces/m3`
  (water column), `pieces/kg dw` (sediment) and `pieces/10 min` (nurdle patrol)
  measure different things under different sampling effort and are not
  convertible. There is deliberately no blended "microplastic risk number".
- **The severity ladder is the source's own and is unit-specific.** A value of
  54 is `Medium` in sediment and far above the top of the water-column ladder.
  We carry NOAA's published class verbatim and never overrule it; our derived
  ladder only fills gaps.
- **Interpolation is inverse distance weighting, not kriging.** No variogram is
  fitted, because the data cannot support one. Grid cells with no sample in
  range are reported as gaps and never filled with zero — an unsampled cell and
  a sampled-clean cell must never look the same.
- **Drift is a single-layer surface corridor, not a forecast.** It is refused
  outright when no real current forcing exists, rather than advected with a
  default velocity. When forcing exists it passes credibility gates (minimum
  vessels and position reports, a 1.5 m/s plausibility ceiling, distance to the
  origin, and a positive uncertainty requirement); failures are attached to the
  output and downgrade confidence to `VERY_LOW` rather than being suppressed.
- **Microplastics are not a passive tracer.** Buoyant particles wind-slip and
  dense ones sink. Neither sinking, beaching, resuspension nor vertical shear
  is modelled.
- **Only 2 of 8 monitored regions have any published microplastic sample.** The
  other six are named as data gaps and given no estimated value.
- The NASA satellite-derived plastic-signal connector is credential-gated and
  **unimplemented**. It returns `UNAVAILABLE` with a reason; no satellite layer
  is fabricated in its place.

## Release identity

Version `1.0.0` / release name `TIDE-Loop` are **packaging identifiers**. They
do **not** claim scientific maturity or accuracy.
