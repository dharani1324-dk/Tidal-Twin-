# TidalTwin — Research Overview

> A 4D Ocean Digital Twin with an integrated, evidence-carrying, decision-aware
> observation-prioritisation loop (TIDE-Loop). This document is the entry point
> to the research package; every figure and claim is grounded in the actual
> implementation and is cross-linked to the source-level documents.

## Title

**TidalTwin: an integrated 4D ocean digital twin with evidence-carrying,
decision-aware observation prioritisation (TIDE-Loop).**

## Abstract

TidalTwin is a working 4D ocean digital twin for Indian coastal waters. It
ingests public ocean observations, compares them against a history-conditioned
model baseline, detects and names ocean events, builds a structured event
signature ("Event DNA"), and exposes a transparent prioritisation layer called
**TIDE-Loop** (Trust-aware Information for Decision and Exploration). Given an
active event, TIDE ranks *candidate next observations* by
`Decision Impact × Uncertainty × Data Gap × Anomaly Persistence ÷ max(Observation Cost, 0.05)`,
attaches inspectable evidence and a cautious interpretation ("verdict"), supports
a clearly-labelled what-if simulation, and replays the model-only versus
TIDE-assisted decision path. A reproducible benchmark framework compares TIDE
against five fair baselines (RANDOM, UNIFORM, UNCERTAINTY_ONLY, ANOMALY_ONLY,
DATA_GAP_ONLY) on an identical candidate pool and budget.

The current status is deliberately scoped. TIDE is **implemented, tested and
demonstrated**; its `EMPIRICALLY_VALIDATED` list is **intentionally empty**. On
the reference run (8 locations, 768 observations, 3 detected events, budget 1,
seed 42) the candidate pool is non-degenerate and **TIDE ties ANOMALY_ONLY** on
the two reported metrics; **no superiority is claimed**. There is no independent
ground truth, so false-alarm and missed-event rates are reported as
`GROUND TRUTH UNAVAILABLE`. The contribution documented here is an **implemented,
inspectable integration and prioritisation architecture**, not a validated
value-of-information model and not a claim of novelty over the wider scientific
literature.

## Problem

Coastal decision-makers already have access to ocean observation systems,
visualisation tools, anomaly detectors and model–observation comparison products.
What is often missing is a single, inspectable step that answers: *given current
uncertainty, model–observation disagreement, data gaps, event persistence,
decision impact and observation cost, where should the **next** observation be
prioritised?* TidalTwin is built around that decision-support question. See
[`PROBLEM_AND_GAP.md`](PROBLEM_AND_GAP.md).

## Research Motivation

- Make the prioritisation logic **transparent** rather than opaque: every
  recommendation carries the factors that produced it and inspectable evidence.
- Keep **trust and provenance explicit**: real, historical, simulated, synthetic
  and model-derived data are distinguishable everywhere and can never be
  conflated.
- Make the system **honest by construction**: the framework can and does return
  `NOT AVAILABLE`, `INSUFFICIENT DATA` and `GROUND TRUTH UNAVAILABLE`.
- Make the whole thing **reproducible**: deterministic scoring, a seeded
  benchmark, frozen artifacts and documented configuration.

## Proposed System

A FastAPI + SQLAlchemy/PostGIS backend and a React + CesiumJS frontend. The
backend exposes a 4D digital twin, anomaly detection, forensics and Event DNA,
model–observation comparison with explainable confidence, an APEX observation
recommender, the TIDE-Loop layer, a what-if virtual observation, decision replay,
a validation/benchmark framework, and a local rule-based Ocean Copilot.

## Core Innovation

The implemented contribution is the **integration and decision-aware
prioritisation architecture** around the existing twin/forensics/event systems:
a single loop that carries evidence and trust from detection through to a
prioritised next observation, a replayable decision, and an honest validation
surface. It is not claimed to be globally unprecedented; it is claimed to be
implemented, inspectable and reproducible. See
[`TIDE_INNOVATION.md`](TIDE_INNOVATION.md).

## System Architecture

```
                    4D OCEAN DIGITAL TWIN
                             │
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                    ↓
   Observations          Model Data          Ocean Context
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ↓
                     ANOMALY RADAR
                             ↓
                       FORENSICS
                             ↓
                       EVENT DNA
                             ↓
                         TIDE-LOOP
                             │
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
        Uncertainty      Data Gaps      Disagreement
              │              │              │
              └──────────────┼──────────────┘
                             ↓
                  Observation Prioritization
                             ↓
                       Evidence Layer
                             ↓
                    What-If Simulation
                             ↓
                     Decision Replay
                             ↓
                       Validation
                             ↺
```

Full component detail: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## TIDE-Loop

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

The loop is implemented as: existing Twin comparison, Forensics uncertainty,
event persistence, APEX candidates and data gaps are combined; the scoring
formula ranks candidates; evidence and confidence are attached; a verdict
hypothesis is produced; a virtual observation can simulate the effect of the
next reading; replay shows the decision path; validation reports the outcome
with explicit limits. See [`TIDE_ALGORITHM.md`](TIDE_ALGORITHM.md) and
[`SYSTEM_WORKFLOW.md`](SYSTEM_WORKFLOW.md).

## Evidence and Trust

Every recommendation is intended to be **inspectable**. Evidence items carry a
stable id, type, source system, location, depth, variable, strength and data
status. Trust status is one of `REAL`, `HISTORICAL`, `SIMULATED`, `SYNTHETIC`,
`MODEL_DERIVED`. Confidence is a heuristic evidence-support score, explicitly
distinct from uncertainty, observation value and decision impact. See
[`SCIENTIFIC_METHOD.md`](SCIENTIFIC_METHOD.md).

## Observation Prioritization

Candidates are ranked by the documented formula with all factors normalised to
`[0, 1]`; method costs are a `NORMALIZED OBSERVATION COST — DEMONSTRATION
ASSUMPTION`. The prioritisation is deterministic and fully reported. See
[`TIDE_INNOVATION.md`](TIDE_INNOVATION.md) §TIDE mathematical model.

## Decision Replay

A read-only, two-mode replay (`MODEL-ONLY` vs `TIDE-ASSISTED`) over a fixed
10-step timeline from event start to validation. The modes are identical before
the observation step. See [`SYSTEM_WORKFLOW.md`](SYSTEM_WORKFLOW.md).

## Validation

Software verification is **TESTED** (96 backend tests, typecheck/lint/build on
the frontend). Algorithm behaviour is checked with **ALGORITHM CONSISTENCY
TESTING** (sensitivity and edge cases). Empirical scientific validation is **NOT
AVAILABLE** — there is no independent ground truth. See
[`SCIENTIFIC_METHOD.md`](SCIENTIFIC_METHOD.md) and
[`RESULTS_AND_LIMITATIONS.md`](RESULTS_AND_LIMITATIONS.md).

## Benchmarking

A fair, reproducible benchmark compares six strategies on an identical candidate
pool and budget. Reference run (`budget=1`, `seed=42`, 8 locations, 768
observations, 3 events): `pool_is_degenerate = false`; **TIDE ties ANOMALY_ONLY**
(decision-change rate 0.75, mean uncertainty reduction 0.2527 for both). **No
superiority is claimed.** See [`EXPERIMENTAL_DESIGN.md`](EXPERIMENTAL_DESIGN.md)
and [`benchmark-results/`](benchmark-results/).

## Results

| Item | Status |
|------|--------|
| TIDE implementation | IMPLEMENTED |
| Software verification | TESTED |
| End-to-end demonstration | DEMONSTRATED (where verified; browser-only items not browser-verified) |
| Reference benchmark | DEMONSTRATED / EMPIRICALLY EVALUATED on the reference dataset only |
| Empirical scientific validation | **NOT AVAILABLE** |
| TIDE superiority / optimality | **NOT ESTABLISHED** |

## Limitations

No independent ground truth; heuristic (not information-theoretic) scoring;
normalised demonstration costs; non-compounded multi-observation budget;
browser rendering/accessibility not independently verified; TIDE ties the
strongest baseline on the reference run. Full list:
[`RESULTS_AND_LIMITATIONS.md`](RESULTS_AND_LIMITATIONS.md) and
[`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md).

## Reproducibility

Environment, dataset, seed, configuration, expected outputs and the boundary of
what is *not* reproducible are documented in
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md). Benchmark artifacts are frozen,
timestamped and never overwritten.

## Future Research

`FUTURE RESEARCH`: independent ground truth; uncertainty calibration;
probabilistic information gain; validated cost models; expert evaluation;
controlled field experiments; stronger baselines; larger budgets; statistical
significance analysis. These are **not implemented** — see
[`RESULTS_AND_LIMITATIONS.md`](RESULTS_AND_LIMITATIONS.md) §Future research.
