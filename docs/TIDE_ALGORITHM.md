# TIDE-Loop Phase 3 Algorithm

## Scope and data status

TIDE is a decision-support heuristic layer, not a scientifically validated
observation-optimisation system. It adapts the existing Twin comparison,
Forensics uncertainty/events, persisted `OceanObservation` rows, and APEX
candidate generation. It returns `REAL`, `HISTORICAL`, `SYNTHETIC`,
`SIMULATED`, or `MODEL_DERIVED` status; Phase 3 candidate recommendations are
`MODEL_DERIVED`, never observations.

## Ranking

All ranking inputs are finite values normalized to `[0, 1]`:

```text
observation value = decision impact × uncertainty × data gap × persistence
                    ÷ max(observation cost, 0.05)
```

The cost floor protects against divide-by-zero and prevents a zero-cost demo
method from producing an infinite recommendation. Method costs are configured
demonstration constants, not operational quotations.

## Input adapters

- **Uncertainty:** existing Forensics uncertainty output divided by 100.
- **Data gap:** existing observation-window count and recency identify no,
  sparse, stale, temporal, and depth coverage gaps.
- **Disagreement:** existing Twin comparison supplies model/observed values and
  severity; existing active events provide the initial persistence proxy.
- **Decision impact:** existing APEX decision impact is normalized and combined
  with disagreement/persistence only as a minimum floor.
- **Candidates:** APEX supplies location, variable, and platform guidance;
  TIDE maps platform guidance to a method and owns final ranking.

## Expected uncertainty reduction

The initial, replaceable estimate combines current uncertainty, data-gap score,
persistence, and method cost. It is explicitly a heuristic—not Bayesian
information gain—and is suitable only for demonstrating transparent decision
logic until validated data/models are introduced.

## Evidence, confidence, and verdicts

Evidence is emitted only for available comparison mismatch, active-event
persistence, and detected gaps. Confidence measures evidence support and
comparison support; it is intentionally separate from priority. The verdict
classifier is an evidence-based heuristic: isolated, low-coherence spikes may
suggest a sensor issue; persistent coherent disagreement may suggest a model
issue; moderate coherent persistence may suggest a missing phenomenon. Sparse
evidence returns `INSUFFICIENT_EVIDENCE`.

## Phase 4 traceability and Event DNA

Each TIDE evidence item is assigned a stable recommendation-scoped ID and
records its source system, location, depth, data status, variable (when
available), strength, and description. Sources are existing Twin Comparison,
Event Timeline, Ocean Forensics, APEX, and Ocean Event DNA; no evidence item
is generated solely to fill a response field.

Confidence is separate from observation value and uncertainty. It summarizes
available comparison support and evidence coverage, then lists limiting factors
such as unavailable variable/depth observations. Verdict explanations use
cautious language: they identify which hypothesis is more consistent with
available evidence, not a proven sensor, model, or phenomenon cause.

`GET /api/v1/tide/events/event-{index}` composes an existing detected event,
the existing Forensics fingerprint/Event DNA, its TIDE candidate context,
evidence chain, confidence, verdict, and decision context. Event DNA remains
the existing Forensics fingerprint; TIDE only references it as traceable
context.

## Limitations

Current source data may not support every variable/depth. Unsupported values
remain unavailable rather than being treated as observed. Spatial consistency
and persistence currently use available Twin confidence/event evidence rather
than a full spatial statistics or multi-sensor assimilation model.

## Phase 5 — virtual observation (what-if)

`POST /api/v1/tide/virtual-observation` accepts `location_id`, `variable`,
`depth_m`, `observation_type` (default `VIRTUAL_SENSOR`), and an optional
`value` override. It performs a deterministic, request-derived simulation and
never writes an `OceanObservation`:

1. Rank candidates for the location; the top candidate anchors the simulation.
2. Derive the simulated reading from existing inputs in order: the Twin
   comparison `observed` value, then its `model` value, then the latest
   persisted temperature for the location (live locations only). If a `value`
   is supplied it is honoured instead.
3. Compute the before state (uncertainty, anomaly risk, ranking, decision,
   confidence) from the normal ranking inputs.
4. Compute the after state with reduction heuristics:
   - `uncertainty_after = uncertainty - expected_uncertainty_reduction`
   - `data_gap_after = data_gap × 0.45`
   - `confidence_after = confidence + 0.04 + 0.03 × (1 − data_gap_after)`
   - anomaly risk falls to ~50% if the simulated reading supports the model
     hypothesis (within the comparison tolerance), otherwise stays near its
     current level.
5. Re-rank all candidates as-if the reading existed and report the new #rank,
   a `decision_result` (`DECISION_CHANGED`/`DECISION_UNCHANGED`), and notes
   that always carry `SIMULATED`/demonstration-only language.

All before/after values are transparent heuristics on real inputs, never
fabricated scientific claims and never persisted outcomes.

## Phase 8 — algorithm version, validation and benchmarking

The scoring algorithm has an explicit version, `TIDE_ALGORITHM_VERSION = "1.0"`
(`app/modules/ai/tide/scoring.py`). Any change to scoring, ranking or decision
behaviour must bump it and update `docs/TIDE_VALIDATION_REPORT.md`.

Phase 8 adds `app/modules/ai/tide/validation.py`, a read-only framework that
measures the existing behaviour against fair baselines. It does not contain a
second scorer: it reuses `calculate_observation_value`, the engine ranking output
and the pure `simulate_candidate` primitive. Full methodology is in
`docs/TIDE_BENCHMARK_PROTOCOL.md`.

The verdict classifier gained an optional contradictory-evidence gate:
`classify_verdict(..., agreeing_observations=0, disagreeing_observations=0)`.
When disagreeing observations reach half of the available observations the
verdict returns `INSUFFICIENT_EVIDENCE`. The defaults preserve prior behaviour.

Maturity language used everywhere: **IMPLEMENTED / DEMONSTRATED / TESTED /
EMPIRICALLY VALIDATED**. TIDE is implemented, demonstrated and tested; its
`EMPIRICALLY_VALIDATED` list is intentionally empty. The project has no
independent ground truth, so false-alarm and missed-event metrics are reported as
`GROUND TRUTH UNAVAILABLE`, and consistency/sensitivity checks are labelled
**ALGORITHM CONSISTENCY TESTING**, not scientific validation. Observation cost is
a `NORMALIZED OBSERVATION COST — DEMONSTRATION ASSUMPTION`.
