# Research Document Index

> Map of the research and engineering documentation. Read this first to find
> what you need. Maturity language (IMPLEMENTED / TESTED / DEMONSTRATED /
> EMPIRICALLY VALIDATED) is used consistently throughout.

## Research Overview

- [`RESEARCH_OVERVIEW.md`](RESEARCH_OVERVIEW.md) — title, abstract, problem,
  motivation, proposed system, core innovation, architecture, TIDE-Loop,
  evidence/trust, prioritisation, replay, validation, benchmarking, results,
  limitations, reproducibility, future research.

## Problem and Gap

- [`PROBLEM_AND_GAP.md`](PROBLEM_AND_GAP.md) — the system-level decision question
  (where to prioritise the next observation) and the integration gap addressed.
  Does not claim existing systems are incapable.

## TIDE Innovation

- [`TIDE_INNOVATION.md`](TIDE_INNOVATION.md) — the TIDE-Loop, traditional vs
  TIDE workflow, mathematical model, method costs, the five distinct concepts,
  evidence types, Event DNA, verdict vocabulary, what-if, replay.

## System Workflow

- [`SYSTEM_WORKFLOW.md`](SYSTEM_WORKFLOW.md) — OBSERVE → DETECT → INVESTIGATE →
  UNDERSTAND → PRIORITIZE → OBSERVE NEXT → SIMULATE → DECIDE → VALIDATE mapped to
  implemented subsystems, plus data provenance.

## Scientific Method

- [`SCIENTIFIC_METHOD.md`](SCIENTIFIC_METHOD.md) — claim hierarchy, what is
  evaluated, experimental objects, measurement framework, evidence/confidence,
  validation metrics and availability, algorithm consistency testing, threats to
  validity, boundary statement.

## Experimental Design

- [`EXPERIMENTAL_DESIGN.md`](EXPERIMENTAL_DESIGN.md) — strategies, fairness
  requirements, reference experiment configuration, metrics, reference results
  and their (non-superior) interpretation, reproduction, scope not covered.

## Results and Limitations

- [`RESULTS_AND_LIMITATIONS.md`](RESULTS_AND_LIMITATIONS.md) — separate
  Implemented / Tested / Demonstrated / Empirically Evaluated / Not Yet
  Empirically Validated sections, claim-boundary table, future research.

## Architecture

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — high-level components, TIDE-Loop
  architecture diagram, backend/frontend components, trust and simulation
  boundaries, reliability.

## Algorithm

- [`TIDE_ALGORITHM.md`](TIDE_ALGORITHM.md) — scoring, adapters, evidence,
  confidence, verdicts, Event DNA, virtual observation, algorithm version.

## Benchmark Protocol

- [`TIDE_BENCHMARK_PROTOCOL.md`](TIDE_BENCHMARK_PROTOCOL.md) — cases, strategies,
  inputs, budget, metrics, exclusions, ground-truth statement, reproducibility,
  scientific claim boundary, limitations.

## Validation

- [`TIDE_VALIDATION_REPORT.md`](TIDE_VALIDATION_REPORT.md) — validation framework
  and historical Phase 8 results (see note below).
- [`benchmark-results/`](benchmark-results/) — frozen, timestamped
  machine-readable benchmark artifacts + interpretation guide.

> **Note on result freshness.** `TIDE_VALIDATION_REPORT.md` is the Phase 8
> report captured when the store had **0 detected events**. The reference used by
> the current research package (3 events, non-degenerate pool) is the Phase 10
> artifact `benchmark-results/tide-benchmark_20260917T153433Z_budget1_seed42.json`
> as reported in [`EXPERIMENTAL_DESIGN.md`](EXPERIMENTAL_DESIGN.md) §6 and
> [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) §10.

## Reproducibility

- [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) — environment, install, database
  setup, dataset/version, result-affecting configuration, metrics, exclusions,
  expected outputs, reference results, what is not reproducible.

## Scientific Limitations

- [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md) — maturity vocabulary,
  what TIDE is and is not, distinct concepts, ground truth, simulation
  boundaries, verdict safety, benchmark honesty, release identity.

## Engineering and Delivery

- [`FINAL_ENGINEERING_REPORT.md`](FINAL_ENGINEERING_REPORT.md) — final verified
  engineering status and evidence.
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — local/Docker/cloud deployment.
- [`API.md`](API.md) — API contracts and status codes.
- [`DEMO_READINESS.md`](DEMO_READINESS.md) — verified demo checklist.
- [`FINAL_DEMO_CHECKLIST.md`](FINAL_DEMO_CHECKLIST.md) — before/during/backup
  demo checklist.
- [`TIDE_IMPLEMENTATION_PLAN.md`](TIDE_IMPLEMENTATION_PLAN.md) — phase-by-phase
  implementation plan and history.
