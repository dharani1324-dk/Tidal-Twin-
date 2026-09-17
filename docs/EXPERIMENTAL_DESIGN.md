# Experimental Design

> The comparison experiment used to characterise TIDE against fair baselines.
> Full methodology and exclusion rules: [`TIDE_BENCHMARK_PROTOCOL.md`](TIDE_BENCHMARK_PROTOCOL.md).
> Machine-readable output: [`benchmark-results/`](benchmark-results/).

## 1. Objective

Measure, fairly and reproducibly, how the TIDE prioritisation layer behaves
relative to simple, clearly defined baselines, and report **only** the metrics
the available data supports. The goal is honesty about capability, not a
favourable comparison.

## 2. Strategies compared

| Strategy | Selection rule |
|----------|----------------|
| `RANDOM` | Uniform random sample of the pool, seeded |
| `UNIFORM` | Evenly spaced along longitude (geographic-spread proxy) |
| `UNCERTAINTY_ONLY` | Highest `uncertainty` |
| `ANOMALY_ONLY` | Highest `anomaly_persistence` |
| `DATA_GAP_ONLY` | Highest `data_gap` |
| `TIDE` | Highest `observation_value` (the documented formula) |

Ties are resolved deterministically by `candidate_id`.

## 3. Fairness requirements

A fair comparison requires, and the framework asserts:

- **same candidate pool** for every strategy in a case,
- **same event / case** for every strategy,
- **same observation budget**,
- **same variables and depth**,
- **same constraints**,
- **same cost assumptions**.

TIDE is never given a field the baselines cannot also see. All outcome
simulations reuse the single shared pure primitive `simulate_candidate`, so the
benchmark and the in-app what-if cannot diverge.

## 4. Reference experiment

```text
Budget        = 1
Seed          = 42
Variables     = temperature, wave_height, salinity, current_speed
Depth         = 0 m
Locations     = 8
Observations  = 768  (760 real + 8 simulated)
Events        = 3
Pool degenerate = false
Dataset       = tidaltwin-live-store / live
Algorithm     = TIDE_ALGORITHM_VERSION 1.0
```

Randomness is confined to the baseline draws, via a fresh
`random.Random(f"{seed}:{case_id}:{strategy}")` per (case, strategy). TIDE's
selection is fully deterministic, so re-running with the same dataset and seed
reproduces the same rows.

## 5. Metrics

| Metric | Definition |
|--------|------------|
| `decision_change_rate` | fraction of selections where the documented decision rule's output changed |
| `uncertainty_reduction` | heuristic before→after uncertainty change (mean shown) |
| `validation_error` | absolute model-minus-observed, where a pair exists |
| `detection_time` | only for event cases; else `NOT AVAILABLE` |
| `evidence_count` | number of traceable evidence items |
| `observation_cost` | normalised demonstration cost per method |

No composite "winner" score is invented. False-alarm and missed-event rates are
`GROUND TRUTH UNAVAILABLE`.

## 6. Reference results (actual)

From `docs/benchmark-results/tide-benchmark_20260917T153433Z_budget1_seed42.json`:

| Strategy | Decision Change | Mean Uncertainty Reduction |
|----------|-----------------|----------------------------|
| RANDOM | 1.00 | 0.1905 |
| UNIFORM | 1.00 | 0.1883 |
| UNCERTAINTY_ONLY | 1.00 | 0.1898 |
| ANOMALY_ONLY | 0.75 | 0.2527 |
| DATA_GAP_ONLY | 1.00 | 0.1898 |
| TIDE | 0.75 | 0.2527 |

`pool_is_degenerate = false` (at least one candidate per case has non-zero
`observation_value`, after a detected event exists).

## 7. Interpretation

> **In this reference run, TIDE ties ANOMALY_ONLY on the reported metrics.**

Stated explicitly, the experiment does **not** show that:

- TIDE is superior, optimal, or best;
- TIDE beats all baselines;
- TIDE is scientifically proven.

Why the tie is expected: TIDE's `observation_value` is zero whenever
`anomaly_persistence` is zero, and on a single-event reference dataset the
highest-persistence candidate is also the highest-value candidate, so
`ANOMALY_ONLY` and `TIDE` select the same candidate. A non-zero
`decision_change_rate` reflects a **documented threshold crossing**, not a
measured operational improvement.

## 8. Reproducing the experiment

```bash
cd backend
python -m scripts.export_benchmark --budget 1 --seed 42
```

Writes a new timestamped file under `docs/benchmark-results/` (never
overwrites). See [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) for the environment,
dataset and the boundary of what is *not* reproducible (exact live observation
values without the captured dataset).

## 9. Scope not covered by this design

`FUTURE RESEARCH` (not implemented): independent ground truth; multiple
datasets/regions; larger budgets with honest compounding; uncertainty
calibration; probabilistic information gain; validated cost models; expert
evaluation; controlled field experiments; stronger baselines; statistical
significance analysis with repeated seeds.
