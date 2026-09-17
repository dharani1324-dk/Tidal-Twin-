# TidalTwin — Project Explanation (Four Versions)

> Pick the version that matches your time slot. All versions are consistent and
> grounded in the implementation. Canonical facts: 768 observations (760 real +
> 8 simulated), 3 detected events, reference benchmark **TIDE ties ANOMALY_ONLY**,
> backend **96/96 tests**, Docker **PASS / all HEALTHY**.

---

## 30-SECOND VERSION

> "This is a 4D Ocean Digital Twin that helps determine what observation should
> be considered next, and why. It compares a model against observations across
> space, depth and time, detects and investigates ocean events, and then a
> TIDE-Loop prioritises the next observation using uncertainty, data gaps, event
> persistence, decision impact and a normalised cost. Every recommendation is
> backed by traceable evidence. The science is honest: TIDE is a tested
> decision-support heuristic, and broader empirical validation is future work."

---

## 1-MINUTE VERSION

> "**Problem.** Ocean data is multidimensional, dynamic and heterogeneous. Many
> workflows can tell you what is happening, where and when. The harder question
> is: given limited observations, **where should we observe next, and why?**
>
> **System.** TidalTwin is a 4D ocean digital twin — latitude, longitude, depth
> and time. It compares model output against observations, runs anomaly
> detection, investigates events through a Forensics engine, and packages them
> into a structured Event DNA fingerprint.
>
> **TIDE.** The core is TIDE-Loop: Trust-aware Information for Decision and
> Exploration. It scores candidate observations by decision impact, uncertainty,
> data gap, anomaly persistence and normalised observation cost, then attaches
> evidence, a confidence value and a cautious verdict. You can simulate the
> effect of measuring at a location, replay the decision, and validate it.
>
> **Innovation.** The contribution is the integration — a closed, evidence-aware
> loop from model and observation through to a reproducible decision. TIDE is a
> decision-support heuristic, not a validated value-of-information model."

---

## 3-MINUTE VERSION

> "TidalTwin is a 4D Ocean Digital Twin and decision-support platform.
>
> **4D Twin.** The globe places data over latitude and longitude, with a depth
> dimension and a time scrubber. It supports a TIDE variable set of ten
> variables — temperature, salinity, oxygen, chlorophyll, wave height, current
> speed, pressure, nutrients, pH and density — with honest status labels:
> observed, historical, simulated, synthetic or model-derived.
>
> **Anomaly Radar.** Conditions are compared against a model baseline and
> unusual ones are flagged for the six emitted event types, such as marine
> heatwave and model-observation mismatch.
>
> **Forensics.** For an event, the engine reports what changed, when, at what
> depth, the uncertainty, and the evidence, including possible contributing
> factors.
>
> **Event DNA.** The event is converted into a structured fingerprint — a
> signature with tags — that provides context downstream.
>
> **TIDE.** The core innovation is TIDE-Loop. For each candidate observation it
> computes:
> `observation value = decision impact × uncertainty × data gap × anomaly
> persistence ÷ observation cost`. Cost is a normalised demonstration
> assumption and the denominator is floored, so a tiny cost cannot inflate the
> score. Each candidate carries evidence, a confidence value and a cautious
> verdict such as LIKELY_MODEL_ISSUE or INSUFFICIENT_EVIDENCE — never a proven
> cause.
>
> **What-If.** You can ask 'what if we measure here?' to create a virtual
> observation, explicitly labelled SIMULATED OBSERVATION — DEMONSTRATION ONLY,
> showing before/after uncertainty, risk and decision state. It is never stored.
>
> **Replay.** Decision Replay compares MODEL-ONLY and TIDE-ASSISTED paths; they
> are identical before the observation step, which makes the value of the
> observation inspectable.
>
> **Validation.** A benchmark compares RANDOM, UNIFORM, UNCERTAINTY_ONLY,
> ANOMALY_ONLY, DATA_GAP_ONLY and TIDE. In the reference run, **TIDE ties
> ANOMALY_ONLY**. We do not claim superiority. The engineering is verified:
> 96/96 backend tests and a healthy Docker stack. Independent scientific
> validation is future work because there is no independent ground truth."

---

## 10-MINUTE TECHNICAL VERSION

### 1. Architecture and data flow
- **Frontend:** React 19 + TypeScript + Vite, CesiumJS globe, served by nginx.
- **Backend:** FastAPI (Python 3.12) with SQLAlchemy 2.
- **Database:** PostgreSQL 16 + PostGIS 3.4 (geospatial).
- **Ingestion:** Open-Meteo Marine API (`sea_surface_temperature`,
  `wave_height`, `wave_direction`), stored per location.
- **Flow:** ingest → store → compare model vs observation → detect → forensics →
  Event DNA → TIDE → what-if → replay → validation.
- The twin exposes a core MODEL | OBSERVED comparison (temperature, wave height,
  wave direction, and salinity/current where available) plus depth transects,
  while TIDE recognises ten variables.

### 2. APIs
- Health and demo: `/api/v1/health`, `/api/v1/demo/status`, `/api/v1/demo/reset`.
- Twin/validation: compare, disagreement, profile, confidence, explain.
- TIDE: candidate generation, recommendation, evidence, what-if, replay.
- Benchmark/validation framework endpoints.
- Assistant (Copilot), monitoring, safety, reports, intelligence, APEX,
  coastal, currents, lens/EDR.
- Errors are mapped: 404 for absent resources, 422 for invalid parameters,
  200 with empty results where appropriate; no 500 leaks.

### 3. TIDE formula (implemented)
```
observation_value = impact × uncertainty × gap × persistence ÷ max(cost, 0.05)
expected_uncertainty_reduction =
    clamp01(uncertainty × (0.30 + 0.40·gap + 0.20·persistence − 0.15·cost))
```
- Inputs are normalised to 0..1; non-finite inputs fall back safely.
- `TIDE_ALGORITHM_VERSION = "1.0"`; ties broken deterministically by
  `candidate_id`.
- Decision rule: impact ≥ 0.65 → INVESTIGATE_ANOMALY; else gap ≥ 0.50 →
  INCREASE_MONITORING; else CONTINUE_MONITORING.

### 4. Evidence, confidence, verdicts
- Evidence items carry type, strength and a description, e.g.
  MODEL_OBSERVATION_MISMATCH, PERSISTENT_ANOMALY, data-gap types, APEX
  recommendation, Event DNA feature.
- Confidence is a separate heuristic (`min(1, evidence/3)` contributes), not the
  same as uncertainty or observation value.
- Verdicts: LIKELY_SENSOR_ISSUE, LIKELY_MODEL_ISSUE, LIKELY_MISSING_PHENOMENON,
  INSUFFICIENT_EVIDENCE — each with an alternative explanation and a recommended
  observation. No verdict proves a cause.

### 5. Simulation isolation
- The what-if uses a single shared pure primitive (`simulate_candidate`).
- Results are labelled SIMULATED and are never written to the observation store.
- `POST /api/v1/demo/reset` deletes only simulation rows; real rows are intact.

### 6. Replay
- A read-only 10-step sequence:
  EVENT_START → NORMAL → EARLY_SIGNAL → ANOMALY_DETECTED →
  MODEL_SENSOR_DISAGREEMENT → HIGH_UNCERTAINTY → TIDE_RECOMMENDATION →
  OBSERVATION → DECISION → VALIDATION.
- MODEL-ONLY and TIDE-ASSISTED share the setup and diverge at OBSERVATION.
- Any regret is a demonstration metric.

### 7. Benchmark
- Strategies: RANDOM, UNIFORM, UNCERTAINTY_ONLY, ANOMALY_ONLY, DATA_GAP_ONLY,
  TIDE; `MIN_SAMPLE = 3`.
- Reference run: budget 1, seed 42, 8 locations, 768 observations, 3 events,
  `pool_is_degenerate = false`.
- Result: TIDE and ANOMALY_ONLY both 0.75 decision-change and 0.2527 mean
  uncertainty reduction — **TIDE ties ANOMALY_ONLY; no superiority claimed**.
- False alarms / missed events: GROUND TRUTH UNAVAILABLE.

### 8. Engineering verification
- Backend 96/96 tests; frontend typecheck, lint and build PASS; Docker frontend
  build PASS; `docker compose up` PASS with database, backend and frontend
  HEALTHY; Cesium assets 200; `npm audit --omit=dev` 0 vulnerabilities.

### 9. Limitations
- No independent ground truth; TIDE is a heuristic, not a calibrated
  value-of-information model; costs are demonstration assumptions; browser
  visual/accessibility verification incomplete; no frontend unit-test runner;
  cache is per worker; exact live-data numerical reproduction needs the captured
  dataset.

---

## FINAL OBJECTIVES

1. Build a multidimensional **4D ocean digital twin** (latitude, longitude,
   depth, time) with honest data-status labelling.
2. **Detect and investigate** ocean anomalies using an Anomaly Radar and a
   Forensics engine.
3. Represent events with **structured Event DNA fingerprints**.
4. **Prioritise the next observation** using the TIDE-Loop score with evidence,
   confidence and cautious verdicts.
5. Provide **evidence-aware what-if** decision support with strict simulation
   isolation.
6. Provide **reproducible replay and validation/benchmark** mechanisms.

---

## FINAL METHODOLOGY

```
DATA
 ↓
4D DIGITAL TWIN
 ↓
ANOMALY DETECTION
 ↓
FORENSICS
 ↓
EVENT DNA
 ↓
TIDE ANALYSIS
 ↓
OBSERVATION PRIORITIZATION
 ↓
WHAT-IF
 ↓
DECISION REPLAY
 ↓
VALIDATION
```

Each stage is an implemented module; each stage's output is either grounded in
stored data or explicitly labelled as simulated/model-derived.

---

## FINAL CONCLUSION

TidalTwin integrates ocean intelligence into a single, decision-aware workflow:
it compares models with observations, detects and investigates events, turns
them into structured fingerprints, and then prioritises the next observation
through the TIDE-Loop with traceable evidence and trust-aware verdicts. What-if
simulation is strictly isolated and labelled; decisions can be replayed; and the
benchmark framework makes comparison reproducible. TIDE is **implemented, tested
and demonstrated** as a decision-support heuristic — it is **not scientifically
proven, not optimal, and does not always improve decisions**. Broader empirical
validation remains future work because independent ground truth is not yet
available.
