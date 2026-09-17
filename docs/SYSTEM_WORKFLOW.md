# System Workflow

> The end-to-end research workflow and how each stage maps to an implemented
> subsystem, followed by the data provenance model.

## 1. Research workflow

```text
OBSERVE
   ↓
DETECT
   ↓
INVESTIGATE
   ↓
UNDERSTAND
   ↓
PRIORITIZE
   ↓
OBSERVE NEXT
   ↓
SIMULATE
   ↓
DECIDE
   ↓
VALIDATE
```

| Stage | Question answered | Implemented subsystem | Representative surface |
|-------|-------------------|-----------------------|------------------------|
| **OBSERVE** | What is the ocean doing now? | 4D Digital Twin, ocean ingestion | `/globe`, `GET /api/v1/twin/*`, `services/ocean_data.py` |
| **DETECT** | Is anything unusual? | Anomaly Radar, event detection | `/anomalies`, `detect_events()` |
| **INVESTIGATE** | Why, and how coherent is it? | Ocean Forensics | `/forensics`, `forensics/forensics.py` |
| **UNDERSTAND** | What kind of event is this? | Event Timeline + Event DNA | `/forensics` fingerprint panel, `fingerprint()` |
| **PRIORITIZE** | Where should we look next? | TIDE-Loop ranking + evidence | `/tide`, `GET /api/v1/tide/candidates` |
| **OBSERVE NEXT** | What is the recommended next observation? | TIDE candidate + APEX | `GET /api/v1/tide/events/{id}`, APEX recommendations |
| **SIMULATE** | What if we measure there? | Virtual observation (what-if) | `POST /api/v1/tide/virtual-observation` |
| **DECIDE** | What is the decision state? | Decision rule + verdict + replay | `/tide`, `/tide/replay` |
| **VALIDATE** | How well did it behave, honestly? | Validation + benchmark framework | `/tide/validation`, `GET /api/v1/tide/benchmarks` |

The loop repeats: validation outcomes and new observations re-enter at OBSERVE.

## 2. Stage detail

### OBSERVE
Public observations are ingested and stored as `OceanObservation` rows against
`OceanLocation` records. The twin compares model (history-conditioned baseline)
against the latest observed value per variable.

### DETECT
`detect_events(db)` classifies events from observation history. Event types:
`marine_heatwave`, `cold_water_anomaly`, `rapid_temp_change`,
`strong_current_event`, `coastal_flooding_risk`, `model_mismatch_event`.

### INVESTIGATE
Forensics provides region context, uncertainty and the autopsy view; the
uncertainty output is a TIDE input (÷ 100).

### UNDERSTAND
The Event DNA fingerprint summarises the event's multi-variable signature and
categorical tags. TIDE references it as contextual evidence; it does not
re-derive it.

### PRIORITIZE
`TideEngine.rankings()` builds one candidate per location from uncertainty,
disagreement, persistence, gaps, decision impact and cost, then scores and sorts
them by `observation_value` (ties broken by `candidate_id`).

### OBSERVE NEXT
The top candidate names the location, variable, depth and method (platform) for
the next observation, with evidence, confidence and decision context attached.

### SIMULATE
The what-if deploys a virtual sensor, derives a reading, and reports before/after
uncertainty, risk, rank and decision. Always `SIMULATED`; never persisted.

### DECIDE
The documented decision rule maps the state to `INVESTIGATE_ANOMALY` /
`INCREASE_MONITORING` / `CONTINUE_MONITORING`; the verdict gives a cautious
hypothesis; replay shows the model-only vs TIDE-assisted path.

### VALIDATE
The validation surface reports maturity, dataset, ground-truth availability,
consistency and edge cases; the benchmark reports per-strategy metrics with
sample sizes and explicit unavailable labels.

## 3. Data provenance

Current verified live state:

```text
768 observations
760 real
8 simulated
```

| Provenance / status | Meaning | Current source |
|---------------------|---------|----------------|
| `REAL` | Real observation stream | Open-Meteo Marine |
| `HISTORICAL` | Older cached observation | Open-Meteo Marine (cached) |
| `SIMULATED` | Labelled demonstration row | `SIMULATED_HEATWAVE` |
| `SYNTHETIC` | Synthetic/demo row | demo/synthetic markers |
| `MODEL_DERIVED` | Model estimate, never an observation | Twin baseline / TIDE candidate |

Observation status is derived from `data_type` + `source`
(`adapters.observation_status`): `SIMULATED` → `SYNTHETIC`/`DEMO` →
`MODEL`/`FORECAST` → `HISTORICAL` → else `REAL`. TIDE candidates are always
`MODEL_DERIVED`; virtual observations and benchmark outcomes are always
`SIMULATED`.

**Why provenance matters:** a recommendation that mixes simulated rows with real
rows without labelling them is untrustworthy. TidalTwin makes the status explicit
everywhere, prevents `SIMULATED` from ever being shown as `REAL`, and provides
`POST /api/v1/demo/reset` which deletes **only** simulation-labelled rows (real
rows untouched). Simulated observations are **not** real measurements; the
8-row demonstration block exists to make an event detectable and is clearly
labelled `SIMULATED OBSERVATION — DEMONSTRATION ONLY`.
