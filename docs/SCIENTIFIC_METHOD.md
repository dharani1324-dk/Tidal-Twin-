# Scientific Method

> How claims about this project are structured, what has actually been
> established, and where the evidence stops. Written so that a reviewer can see
> exactly which statements are engineering verification and which would be
> scientific validation.

## 1. Claim hierarchy

The project distinguishes four levels and never upgrades one into another:

| Level | Definition | How it is established | Status |
|-------|------------|-----------------------|--------|
| IMPLEMENTED | Code exists and runs | Source inspection | Yes |
| TESTED | Covered by automated tests | `backend/tests/` (96 tests) | Yes |
| DEMONSTRATED | Observable via the running app/API | Verified endpoints, Docker stack | Yes, where executed |
| EMPIRICALLY VALIDATED | Checked against independent ground truth | Field/external labels + review | **NOT AVAILABLE** |

Software tests do **not** constitute scientific validation. The test suite
verifies that the implementation matches its documented behaviour and that
simulation cannot leak into the store; it says nothing about whether the scoring
formula is correct for the ocean.

## 2. What is being evaluated

The TIDE layer implements a decision-support priority score:

```text
observation_value = decision_impact × uncertainty × data_gap × anomaly_persistence
                    ÷ max(observation_cost, 0.05)
```

The scientific question *would* be: does prioritising by this score lead to
better observation outcomes against an independent standard? Answering that
requires independent ground truth and a defined outcome criterion, **neither of
which exists in this project.** Consequently, the project evaluates its
*behaviour and consistency*, not its *correctness*.

## 3. Experimental objects

- **Case** — one scenario: a variable case (`temperature@0`) or an event case
  (`event-0`, `event-1`, …).
- **Strategy** — one selection rule (`RANDOM`, `UNIFORM`, `UNCERTAINTY_ONLY`,
  `ANOMALY_ONLY`, `DATA_GAP_ONLY`, `TIDE`).
- **Candidate** — a possible next observation (location, variable, depth,
  method, factors, score, evidence, confidence).
- **Budget** — the number of candidates a strategy may select per case (1–10;
  each selected candidate evaluated independently, not compounded).

## 4. Measurement framework

For each selected candidate the framework records: selection identity, initial
and final uncertainty, uncertainty reduction (absolute and relative),
decision-change flag (under the documented rule table), validation error
(model-minus-observed where a pair exists), detection time (event cases only),
evidence count, and normalised observation cost. Aggregates are reported with
sample size `N`; statistics (mean/median/min/max) are only reported when
`N >= 3` (`MIN_SAMPLE`), otherwise `INSUFFICIENT DATA (N=x)`.

## 5. Evidence and confidence

- **Evidence** is emitted only for inputs that actually exist (comparison
  mismatch, active-event persistence, detected gaps) and is traced with an id,
  source system and data status. It is inspectable context, not proof.
- **Confidence** is a heuristic evidence-support score, intentionally separate
  from uncertainty and observation value. It is not a calibrated probability.
- **Verdicts** (`LIKELY_SENSOR_ISSUE`, `LIKELY_MODEL_ISSUE`,
  `LIKELY_MISSING_PHENOMENON`, `INSUFFICIENT_EVIDENCE`) state which hypothesis is
  *more consistent* with available evidence; they never assert a proven cause.
  A contradictory-evidence gate returns `INSUFFICIENT_EVIDENCE` when the
  disagreeing share of observations reaches 0.5.

## 6. Validation framework (metrics and availability)

| Metric | Availability in this project |
|--------|------------------------------|
| Uncertainty reduction | Computable (heuristic before→after) |
| Relative uncertainty reduction | When initial uncertainty > 0 |
| Decision change | Computable (documented threshold crossing) |
| Validation error (model − observed) | Only where a model/observed pair exists |
| Detection time | Only for event cases |
| Evidence count | Always |
| Observation cost | Normalised demonstration cost |
| **False alarm** | **GROUND TRUTH UNAVAILABLE** |
| **Missed event** | **GROUND TRUTH UNAVAILABLE** |

Missing metrics are never imputed. Event labels are produced by the system's own
`classify_events` logic, so they cannot serve as independent labels.

## 7. Algorithm consistency testing

The validation surface includes, and the benchmark artifact embeds, a
consistency report:

- **Sensitivity** — each benefit factor increases the score; cost decreases it
  (`all_consistent = true`).
- **Ranking sensitivity** — a candidate's rank responds when one factor changes.
- **Edge cases** — zero, one, tiny/huge cost, null, `NaN`, `Infinity` and
  out-of-range inputs all produce finite, non-negative scores
  (`all_finite = true`).

This is **ALGORITHM CONSISTENCY TESTING**. It verifies the implementation matches
its documented formula; it is not scientific validation and does not establish
that the formula is correct for the ocean.

## 8. Threats to validity

- **No independent ground truth** — the dominant limitation; blocks accuracy,
  false-alarm, missed-event and detection-skill claims.
- **Heuristic, not information-theoretic** scoring — `expected_uncertainty_
  reduction` is a documented heuristic, not an information gain.
- **Demonstration costs** — method costs are normalised assumptions.
- **No compounding** — multi-observation budgets produce independent rows, not a
  campaign simulation.
- **Reference-dataset dependence** — the live source is time-varying; exact
  numbers require the captured dataset.
- **Non-browser verification** — Cesium rendering, responsive layout and
  accessibility were not independently verified in a browser.

## 9. Boundary statement

The system **implements** a decision-aware prioritisation framework and the
framework **evaluates** its own behaviour reproducibly. The current dataset and
design **do not establish** superiority, optimality, prediction accuracy, or
generalisation. Maturity vocabulary is applied consistently across the API, the
UI and every document. See [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).
