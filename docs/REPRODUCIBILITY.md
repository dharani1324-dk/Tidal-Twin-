# TidalTwin — Reproducibility

> How to reproduce the documented behaviour and benchmark artifacts, and where
> exact numeric reproduction is impossible.

## 1. Environment

| Component | Version used | Notes |
|-----------|--------------|-------|
| Python | 3.12 | `backend/requirements.txt` pins all backend packages |
| Node.js | 20+ (22 used in Docker) | `frontend/package.json` |
| PostgreSQL | 16 + PostGIS 3.4 | `postgis/postgis:16-3.4` in Docker |
| OS | Windows 11 (dev) / Linux (Docker) | scripts provided for both |
| Backend framework | FastAPI 0.115.6, Uvicorn 0.34.0, SQLAlchemy 2.0.36 | |
| Frontend | React 19, TypeScript 6, Vite 8, CesiumJS 1.145 | |
| TIDE algorithm version | `TIDE_ALGORITHM_VERSION = "1.0"` | bump on any scoring/ranking change |

## 2. Installation and configuration

```bash
# 1. Configure the backend
cd backend
cp .env.example .env          # Windows: copy .env.example .env
# edit DATABASE_URL to point at a PostGIS database

# 2. Install
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS/Linux

# 3. Install the frontend
cd ../frontend
cp .env.example .env.local
npm install
```

## 3. Database setup

```bash
# From backend/ (schema + 8 coastal locations + best-effort live data)
python -m scripts.init_db
python -m scripts.seed_data
python -m scripts.refresh_ocean_data     # best effort; offline is fine
```

Optionally seed the labelled demonstration dataset:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/demo/seed
```

## 4. Dataset source and version

| Item | Value |
|------|-------|
| Observation source | **Open-Meteo Marine** public API (real observations) |
| Benchmark dataset id | `tidaltwin-live-store` |
| Benchmark dataset version | `live` |
| Dataset size (reference run) | 8 locations, 768 observations, 3 detected events |
| Reference run timestamp | see the artifact filename (`docs/benchmark-results/`) |
| Demonstration rows | 8 rows, `source = SIMULATED_HEATWAVE`, location Goa Coast (Panaji) |

> **REPRODUCTION REQUIRES DATASET.** Open-Meteo Marine is a live, time-varying
> feed. The *structure* of a run is reproducible; the exact observation values,
> and therefore the exact benchmark numbers, are **not reproducible without the
> original captured data**. The committed artifacts under
> `docs/benchmark-results/` are the frozen records of the runs that were
> actually executed.

## 5. Configuration that affects results

| Setting | Default | Effect |
|---------|---------|--------|
| Observation budget | `1` (1–10) | candidates selected per case |
| Seed | `42` | reproducible RANDOM/UNIFORM baseline draws |
| Depth | `0.0 m` | depth used for case construction |
| Strategies | all six | `RANDOM, UNIFORM, UNCERTAINTY_ONLY, ANOMALY_ONLY, DATA_GAP_ONLY, TIDE` |
| Cost assumption | `NORMALIZED OBSERVATION COST — DEMONSTRATION ASSUMPTION` | divisor floor `0.05` |

Randomness: only the baseline strategies consume randomness, via a fresh
`random.Random(f"{seed}:{case_id}:{strategy}")` per (case, strategy). TIDE's
selection is fully deterministic. Re-running with the same seed and the same
dataset therefore reproduces the same baseline draws.

## 6. Candidate generation and selection

- Pools come from the existing TIDE pipeline (`TideEngine.rankings`) over the
  TIDE adapters (Twin comparison, Forensics, events, APEX, gaps). No second
  scorer exists.
- Every strategy receives the **identical pool** and **identical budget**.
- Outcome simulation reuses the shared pure `simulate_candidate` primitive, so
  the benchmark and the in-app what-if cannot diverge.

## 7. Metrics

| Metric | Definition |
|--------|------------|
| `decision_change_rate` | fraction of selections where the documented decision rule's output changed |
| `uncertainty_reduction` | heuristic before→after uncertainty change (`_safe_reduction`) |
| `validation_error` | model minus observed for available model/observed pairs |
| `detection_time` | only when events exist; else `NOT AVAILABLE` |
| `observation_cost` | normalised demonstration cost per method |

Metrics are grouped per strategy. No composite "winner" score is invented.

## 8. Exclusions

- No independent ground truth ⇒ false-alarm / missed-event metrics excluded as
  `GROUND TRUTH UNAVAILABLE`.
- Cases with no candidates are reported with `N = 0` and
  `status = NOT AVAILABLE` rather than a zero value.
- When `pool_is_degenerate = true`, selection-differentiation metrics are not
  interpretable and are flagged as such.

## 9. Expected outputs

```bash
cd backend
python -m scripts.export_benchmark --budget 1 --seed 42
```

Writes `docs/benchmark-results/tide-benchmark_<timestamp>_budget1_seed42.json`.
The file is self-contained: dataset, configuration, fairness, selection,
rows, aggregates, ground-truth block, timing, scientific boundary, limitations,
and the consistency/edge-case report. See
[`benchmark-results/README.md`](benchmark-results/README.md).

## 10. Reference results (actual)

From `docs/benchmark-results/tide-benchmark_20260917T153433Z_budget1_seed42.json`
(dataset: 8 locations, 768 observations, 3 events):

| Strategy | decision_change_rate | mean uncertainty reduction |
|----------|----------------------|----------------------------|
| RANDOM | 1.0 | 0.1905 |
| UNIFORM | 1.0 | 0.1883 |
| UNCERTAINTY_ONLY | 1.0 | 0.1898 |
| ANOMALY_ONLY | 0.75 | 0.2527 |
| DATA_GAP_ONLY | 1.0 | 0.1898 |
| TIDE | 0.75 | 0.2527 |

- `pool_is_degenerate = false` (one candidate per case has non-zero
  `observation_value`, after a detected event exists).
- TIDE and ANOMALY_ONLY tie on this dataset. **No superiority is claimed.**
- `GROUND TRUTH UNAVAILABLE` for false-alarm / missed-event rates.

## 11. What is NOT reproducible

- Exact live observation values and exact numeric metrics, without the original
  captured dataset (**REPRODUCTION REQUIRES DATASET**).
- Any accuracy/validation claim — none exists.
- Event labels against independent ground truth — not available.
