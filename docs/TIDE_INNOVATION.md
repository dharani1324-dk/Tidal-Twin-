# TIDE-Loop — Innovation

> **TIDE = Trust-aware Information for Decision and Exploration.**
> This document explains what TIDE-Loop contributes, how it is defined, and how
> it is implemented. It describes an **implemented integration and
> prioritisation architecture**; it does not claim that the conceptual loop is
> globally unprecedented. Deep algorithm detail: [`TIDE_ALGORITHM.md`](TIDE_ALGORITHM.md).

## 1. The core loop

```text
MODEL
  ↓
OBSERVATION
  ↓
DISAGREEMENT
  ↓
NEXT OBSERVATION
  ↓
BETTER DECISION
  ↓
VALIDATION
  ↺
```

TIDE closes the gap between *detecting* an ocean condition and *deciding what to
measure next*. It is the layer that turns anomaly/forensics/event outputs into a
prioritised, inspectable next observation.

## 2. Traditional monitoring vs the implemented TIDE workflow

**Traditional monitoring**

```text
Observe → Detect → Analyze
```

**Implemented TIDE workflow**

```text
Model
→ Observe
→ Detect disagreement/uncertainty
→ Prioritize next observation
→ Simulate possible observation
→ Support decision
→ Validate
→ Repeat
```

The project's contribution is the **implemented integration** of these stages
into one loop, with evidence and trust carried through each stage and made
inspectable. *"Better decision"* describes the intended purpose of the loop; the
benchmark does **not** establish that decisions are objectively improved (see
[`RESULTS_AND_LIMITATIONS.md`](RESULTS_AND_LIMITATIONS.md)).

## 3. Where TIDE sits in the system

TIDE consumes existing systems through adapters and adds no parallel science:

| Input | Source system |
|-------|----------------|
| Uncertainty | Ocean Forensics (uncertainty output ÷ 100) |
| Disagreement (model vs observed, severity) | Twin comparison |
| Anomaly persistence | Event timeline (active events) |
| Decision impact | APEX recommendation (normalised) |
| Candidates (location/variable/platform) | APEX |
| Data gaps | Observation-window count and recency |
| Event DNA | Ocean Forensics fingerprint |

`adapters.py → engine.py (ranking) → scoring.py (formula) → verdicts.py →
explanations.py (evidence/confidence)`, with `virtual_observation()`,
`replay.build_replay()` and `validation.py` around it.

## 4. TIDE mathematical model

The implemented formula (`app/modules/ai/tide/scoring.py`,
`calculate_observation_value`):

```text
Observation Value
=
Decision Impact
×
Uncertainty
×
Data Gap
×
Anomaly Persistence
÷
Observation Cost
```

Implemented precisely as:

```text
observation_value = impact × uncertainty × gap × persistence ÷ max(cost, 0.05)
```

Properties, as implemented:

- **Normalisation / clamping.** `unit(value)` converts each factor to a finite
  value clamped to the closed interval `[0, 1]`.
- **Finite-value handling.** Non-numeric values return a default (`0.0`; cost
  defaults to `1.0` when absent). `NaN` and `±Infinity` return the default. No
  `NaN`/`Infinity` can propagate into a score.
- **Minimum denominator (cost floor).** `max(cost, 0.05)` prevents
  divide-by-zero and prevents a zero-cost demonstration method from producing an
  infinite score. The floor is **not** a monetary value.
- **Rounding.** `observation_value` and `expected_uncertainty_reduction` are
  rounded to 4 decimals in the API payload.

### Expected uncertainty reduction (heuristic)

```text
expected_uncertainty_reduction =
  unit(uncertainty × (0.30 + 0.40·gap + 0.20·persistence − 0.15·cost))
```

This is a documented heuristic, explicitly **not** Bayesian information gain.

### Observation method costs

```text
DRONE                0.28
BUOY                 0.35
ARGO_FLOAT           0.42
MANUAL_SAMPLE        0.48
AUTONOMOUS_VEHICLE   0.62
RESEARCH_VESSEL      0.92
VIRTUAL_SENSOR       0.08
```

> **NORMALIZED OBSERVATION COST — DEMONSTRATION ASSUMPTION.**
> These are configured demonstration constants, not universally established
> ocean-observation costs and not operational quotations. Exact keys come from
> `scoring.py` (`METHOD_COSTS`); the names differ slightly from the informal
> list above (e.g. `ARGO_FLOAT`, `MANUAL_SAMPLE`, `AUTONOMOUS_VEHICLE`).

### Interpretation

A higher `observation_value` means a candidate next observation scores higher on
the combination of potential decision relevance, current uncertainty, data gap,
event persistence and inverse cost. It is a **priority score**, not a
probability, benefit, or guarantee.

## 5. Decision rule table

`decision_for(decision_impact, data_gap)`:

| Condition (checked in order) | Decision |
|------------------------------|----------|
| `decision_impact >= 0.65` | `INVESTIGATE_ANOMALY` |
| else `data_gap >= 0.50` | `INCREASE_MONITORING` |
| else | `CONTINUE_MONITORING` |

Mirrored in `replay.DECISION_RULES` and reported verbatim in the API.

## 6. The five core concepts (never interchangeable)

| Concept | Meaning | What it is NOT |
|---------|---------|----------------|
| **Uncertainty** | How uncertain the current estimate is | confidence |
| **Confidence** | How strongly the available evidence supports an interpretation | a calibrated probability; not uncertainty |
| **Observation Value** | Priority/value assigned to a possible next observation | a probability or measured benefit |
| **Decision Impact** | Potential relevance of the observation to the decision state | observation value |
| **Evidence Strength** | Strength of the supporting evidence items | proof of a cause |

The implementation keeps these separate: confidence is computed from its own
factors and evidence coverage; observation value is computed from the formula;
decision impact is an independent normalised input. See
[`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).

## 7. Evidence-carrying intelligence

TIDE recommendations are intended to be **inspectable**. Evidence items are
traced with a stable, recommendation-scoped id and provenance
(`explanations.trace_evidence`).

**Evidence types actually emitted by the current implementation:**

| Evidence type | Emitted by | Meaning |
|---------------|-----------|---------|
| `MODEL_OBSERVATION_MISMATCH` | engine | Twin comparison reports model–observation disagreement |
| `PERSISTENT_ANOMALY` | engine | Active event/persistence at the location |
| `APEX_RECOMMENDATION` | engine | APEX generated this location as a candidate |
| `EVENT_DNA_FEATURE` | event context | Event DNA categorical tags |
| `NO_OBSERVATION` | adapters (gap) | No observations exist |
| `SPARSE_OBSERVATION` | adapters (gap) | Few observations |
| `STALE_OBSERVATION` | adapters (gap) | Recent coverage is stale |
| `DEPTH_GAP` | adapters (gap) | Depth coverage missing |
| `TEMPORAL_GAP` | adapters (gap) | Temporal coverage gap |
| `NO_MATERIAL_GAP` | adapters (gap) | No material gap (floor) |

**Fields on a traced evidence item:** `evidence_id` (format
`"{candidate_id}:e{index}"`), `type`, `strength`, `description`, `variable`
(where applicable), `source_system`, `location_id`, `depth_m`, `data_status`
(and the schema also allows `timestamp`, currently not populated).

**Not currently emitted.** The names `SPATIAL_CONSISTENCY` and
`HIGH_UNCERTAINTY` appear only in the source-system mapping table (reserved);
`MULTI_OBSERVATION_AGREEMENT`, `QUALITY_FLAG` and `FORENSICS_EVIDENCE` are not
present as emitted evidence types. They are **not** documented as implemented
evidence.

**Evidence count** feeds confidence (`min(1, len(evidence)/3)`) and is reported
per benchmark row. **Limitations:** evidence depends on the availability of
comparison/event/gap inputs; it is supporting context, not proof of cause.

## 8. Event DNA integration

```text
Ocean Event
    ↓
Event Fingerprint / DNA
    ↓
Event Characteristics
    ↓
TIDE Context
    ↓
Observation Prioritization
```

Event DNA is the existing Forensics fingerprint
(`app/modules/ai/forensics/fingerprint.py`, `fingerprint(event)`). Its dimensions
are: `temp_anomaly`, `salinity`, `oxygen`, `chlorophyll`, `nutrients`,
`wave_height`, `current_speed`, `duration_h`, `peak_intensity`, plus derived
categorical `tags` (e.g. `warm`/`hot`, `salty`/`fresh`, `high_productivity`,
`oxygenated`/`hypoxic`, `rough`/`calm`, `fast_current`/`slow_current`) and a
`label`. TIDE references it as **contextual evidence** (`EVENT_DNA_FEATURE`) and
never re-derives it. Event DNA is a structured event signature, not a validated
classifier. No new Event DNA features were invented for this documentation.

## 9. Model vs sensor verdicts

The cautious, evidence-based verdict vocabulary
(`app/modules/ai/tide/verdicts.py`, `classify_verdict`):

```text
LIKELY_SENSOR_ISSUE
LIKELY_MODEL_ISSUE
LIKELY_MISSING_PHENOMENON
INSUFFICIENT_EVIDENCE
```

These are **decision-support interpretations**. They do **not** prove sensor
failure, model failure, or the existence of a missing phenomenon. Conditions, as
implemented:

| Condition (in order) | Verdict |
|----------------------|---------|
| `observation_count < 2` or `severity < 0.20` | `INSUFFICIENT_EVIDENCE` |
| contradictory share of observations `>= 0.5` | `INSUFFICIENT_EVIDENCE` |
| `severity >= 0.65` and persistence `< 0.35` and spatial `< 0.35` | `LIKELY_SENSOR_ISSUE` |
| `severity >= 0.55` and persistence `>= 0.60` and spatial `>= 0.55` | `LIKELY_MODEL_ISSUE` |
| `severity >= 0.55` and persistence `>= 0.45` and spatial `>= 0.45` | `LIKELY_MISSING_PHENOMENON` |
| otherwise | `INSUFFICIENT_EVIDENCE` |

Each verdict also carries an `alternative_explanation` (the competing
hypothesis) and a `recommended_observation`. Limits: sparse or contradictory
evidence returns `INSUFFICIENT_EVIDENCE`.

## 10. What If We Measure Here?

```text
Select Candidate
      ↓
Deploy Virtual Sensor
      ↓
SIMULATED OBSERVATION
      ↓
Before Uncertainty
      ↓
After Uncertainty
      ↓
Risk / Anomaly Change
      ↓
Decision Change
      ↓
Validation
```

`POST /api/v1/tide/virtual-observation` is deterministic and request-derived. It
ranks candidates for a location, derives a reading from existing inputs (Twin
`observed`, then Twin `model`, then the latest persisted temperature; or an
explicit `value`), computes before/after state, and reports the changed rank and
a `DECISION_CHANGED` / `DECISION_UNCHANGED` result.

> **SIMULATED OBSERVATION — DEMONSTRATION ONLY.**

Virtual observations are **never persisted** to `ocean_observations` (enforced
by tests) and are never presented as real measurements. Before/after values are
transparent heuristics on real inputs, not field measurements.

## 11. Decision Replay

```text
MODEL-ONLY            TIDE-ASSISTED
```

A read-only, 10-step replay (`EVENT_START → NORMAL → EARLY_SIGNAL →
ANOMALY_DETECTED → MODEL_SENSOR_DISAGREEMENT → HIGH_UNCERTAINTY →
TIDE_RECOMMENDATION → OBSERVATION → DECISION → VALIDATION`). It examines event
progression, uncertainty, evidence, the observation, the decision state and
validation. In `MODEL-ONLY` the model state is replayed as-is; in
`TIDE-ASSISTED` a simulated observation (always `SIMULATED`) is incorporated
from the `OBSERVATION` step onward; the two modes are identical before that
point. Any regret-type quantity is a **demonstration metric**, not a universal
scientific measure. Replay does not claim that TIDE improves decisions — the
benchmark does not establish that.

## 12. Scientific boundary

TIDE is a **decision-support heuristic**. `EMPIRICALLY_VALIDATED` is **NOT
AVAILABLE**. See [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md) and
[`RESULTS_AND_LIMITATIONS.md`](RESULTS_AND_LIMITATIONS.md).
