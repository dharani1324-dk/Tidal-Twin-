# TIDE Benchmark Artifacts

Machine-readable output of the Phase 8 TIDE benchmark framework
(`backend/app/modules/ai/tide/validation.py`), produced by:

```bash
cd backend
python -m scripts.export_benchmark --budget 1 --seed 42
```

## Naming

```
tide-benchmark_<UTC timestamp>_budget<N>_seed<S>[-<n>].json
```

Artifacts are **never overwritten**. A new file is written on every run; the
`-<n>` suffix is only added if a file with the same second already exists.

## Contents

Each artifact is self-contained and audit-ready:

| Field | Meaning |
|-------|---------|
| `algorithm_version` | `TIDE_ALGORITHM_VERSION` at run time |
| `dataset` | dataset id/version, location/observation/event counts |
| `configuration` | budget, strategies, cases, seed, cost assumption, ground-truth flag |
| `fairness` | shared-pool / equal-budget guarantees |
| `selection` | per-case pool size, non-zero `observation_value` counts, degeneracy note |
| `rows` | one row per (case × strategy × selected candidate) |
| `aggregates` | per-strategy metrics (decision-change rate, uncertainty reduction, validation error, detection time, cost) |
| `ground_truth` | always reports that independent ground truth is unavailable |
| `timing_ms` | candidate generation / evaluation / total |
| `scientific_boundary` | maturity vocabulary and explicit non-claims |
| `limitations` | known honesty caveats |
| `consistency` | algorithm-consistency sensitivity + edge-case report (NOT scientific validation) |

## Interpreting this honestly

- Strategy metrics are **demonstration heuristics derived from existing inputs**,
  not field measurements.
- With no independent ground truth, false-alarm and missed-event rates are
  reported as `GROUND TRUTH UNAVAILABLE`.
- `pool_is_degenerate = true` means every candidate in every case had
  `observation_value = 0` (no detected events), so score-based strategies tie.
  After documenting an event in the dataset, this flips to `false` and
  differentiation becomes measurable — but still not validated.
- A non-zero `decision_change_rate` reflects a documented threshold crossing,
  **not** a measured operational improvement.

See [`../TIDE_BENCHMARK_PROTOCOL.md`](../TIDE_BENCHMARK_PROTOCOL.md) and
[`../TIDE_VALIDATION_REPORT.md`](../TIDE_VALIDATION_REPORT.md).
