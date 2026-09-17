# 🌊 TidalTwin

**An Interactive 4D Ocean Model Validation & Decision Intelligence Platform**

`Release 1.0.0 · TIDE-Loop` (a packaging identifier; **not** a scientific
validity claim — see [`docs/SCIENTIFIC_LIMITATIONS.md`](docs/SCIENTIFIC_LIMITATIONS.md))

Built for the Smart India Hackathon. This project is **not another ocean
viewer** — it streams live ocean data, compares the AI model against reality
field by field (MODEL | OBSERVED | DEVIATION), scores observation confidence,
flags model–observation disagreement, explains *why* — then pushes a decision
(safety advisory, alert, risk briefing) to a coastal command center. The 3D
globe is the interface; validation is the product.

---

## 📌 Project

**TidalTwin** is a 4D Ocean Digital Twin for the Indian Ocean: a live Cesium
globe fed by public ocean observations, layered with anomaly detection,
forensics, event fingerprinting, and a decision-support recommendation engine.

## 💡 Innovation

The core innovation is **TIDE-Loop** (**T**rust-aware **I**nformation for
**D**ecision and **E**xploration): given an active ocean event, land the *next
observation* where it most reduces decision uncertainty relative to its cost.

```
Observation Value =
  Decision Impact × Uncertainty × Data Gap × Anomaly Persistence
  ÷ Observation Cost
```

TIDE is transparent and deterministic. It is a **decision-support heuristic**,
not a validated value-of-information model.

## 🔬 Research / Innovation Overview

- **Problem** — existing workflows observe, visualise, detect and compare; the
  added decision question is *where to prioritise the next observation* given
  uncertainty, disagreement, data gaps, persistence, decision impact and cost.
- **TIDE-Loop** —
  `MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION → BETTER DECISION → VALIDATION ↺`.
- **Architecture** — 4D Twin → Anomaly Radar → Forensics → Event DNA → TIDE-Loop
  (uncertainty / gaps / disagreement) → prioritisation → evidence → what-if →
  replay → validation.
- **Benchmark status** — reference run (8 locations, 768 observations, 3 events,
  budget 1, seed 42): pool non-degenerate; **TIDE ties ANOMALY_ONLY**; **no
  superiority claimed**.
- **Scientific limitations** — TIDE is implemented, tested and demonstrated;
  `EMPIRICALLY_VALIDATED` is **not available** (no independent ground truth).
- **Reproducibility** — environment, seed, dataset and frozen artifacts are
  documented in [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

Full research package: [`docs/RESEARCH_INDEX.md`](docs/RESEARCH_INDEX.md).

## 🏗️ Architecture (brief)

- **Backend** — FastAPI + SQLAlchemy + PostGIS (`backend/app`). Routers under
  `app/api`, AI modules under `app/modules/ai`.
- **Frontend** — React 19 + TypeScript + Vite + CesiumJS (`frontend/src`).
- **Database** — PostgreSQL 16 + PostGIS.
- **Data flow** — 4D Twin → Anomaly Radar / Forensics / Observations → Event →
  Event DNA → Uncertainty/Gap → TIDE → Next Observation → What-If Simulation →
  Decision Replay → Validation → Copilot explanation.

Full component diagram: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## ✨ Features

- 4D Digital Twin (Cesium globe, live layers, Argo, event markers)
- Ocean Anomaly Radar + Ocean Forensics + Event Timeline + Event DNA
- APEX observation recommendations and TIDE Command Center
- TIDE candidate ranking, evidence, confidence, verdict, uncertainty & gaps
- "What If We Measure Here?" virtual observation (never persisted)
- Decision Replay (model-only vs TIDE-assisted, read-only)
- Validation & benchmarking framework (honest, baselines, reproducible)
- Ocean Copilot (context-aware, evidence-grounded)
- Phase 9: system health indicator, error boundaries, demonstration mode

## ▶️ Running the project

### One command (Docker)

```bash
docker compose up --build
```

| Service  | URL                     |
|----------|-------------------------|
| Frontend | http://localhost:8080   |
| Backend  | http://localhost:8000   |
| API docs | http://localhost:8000/docs |
| Database | localhost:5433          |

### One command (local, no Docker)

Starts the backend and frontend together (needs Python 3.12+, Node 20+ and a
reachable PostGIS database):

```bash
./run.sh            # macOS / Linux
.\run.ps1           # Windows PowerShell
```

Open <http://127.0.0.1:5173>. Or run the two halves manually:

### Local development (without Docker)

Backend (from `backend/`):

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (from `frontend/`), in a second terminal:

```bash
npm install
npm run dev
```

The frontend reads `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`).

## 🔐 Environment

Backend settings come from `backend/.env` (see `backend/.env.example`):

| Variable         | Required | Default                | Purpose |
|------------------|----------|------------------------|---------|
| `DATABASE_URL`   | yes      | local Postgres         | PostGIS connection string |
| `API_HOST`       | no       | `127.0.0.1`            | Bind host |
| `API_PORT`       | no       | `8000`                 | Bind port |
| `ENVIRONMENT`    | no       | `development`          | Startup warnings/logging |
| `CORS_ORIGINS`   | no       | `*`                    | Allowed frontend origins |
| `CESIUM_ION_TOKEN` | optional | empty                | Ion terrain/imagery (base globe works without it) |
| `VITE_API_BASE_URL` | no    | `http://127.0.0.1:8000`| Frontend → backend base URL |

Startup logs a clear warning for any missing/unsafe configuration. No secrets
are ever returned by the API or written to logs.

## 🧪 Demo

1. Start the stack, open the frontend.
2. Click **START TIDE DEMO** in the top bar. A dismissible 8-step guide appears.
3. The guide navigates the real application (no fake animation):
   Anomaly Radar → Forensics → Event DNA → TIDE → What-If → Decision Replay →
   Validation → Copilot.
4. **Seed demonstration data** creates clearly-labelled
   `SIMULATED OBSERVATION — DEMONSTRATION ONLY` rows (via
   `POST /api/v1/demo/seed`). **Reset demo** deletes only simulation rows
   (`POST /api/v1/demo/reset`) and never touches real observations.
5. `GET /api/v1/demo/status` reports what demonstration data exists and which
   event is selected as the **DEMONSTRATION EVENT** (practical availability,
   not a scientific ranking).

See [`docs/DEMO_READINESS.md`](docs/DEMO_READINESS.md) for the verified checklist.

## 🔌 API (important endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health`, `/api/v1/health` | Per-subsystem health |
| GET | `/api/v1/tide/candidates` | Ranked TIDE candidates |
| GET | `/api/v1/tide/evidence` / `/explanation` | Evidence + explanation |
| GET | `/api/v1/tide/verdict` | Evidence-based verdict |
| POST | `/api/v1/tide/virtual-observation` | Simulated what-if (not persisted) |
| GET | `/api/v1/tide/events` / `/{id}/replay` | Event index / decision replay |
| GET | `/api/v1/tide/validation` / `/benchmarks` | Validation + benchmarks |
| GET/POST | `/api/v1/demo/status` `/seed` `/reset` | Demonstration mode |

## ✅ Testing

Backend (from `backend/`):

```bash
.venv\Scripts\python -m unittest discover -s tests
```

Frontend (from `frontend/`):

```bash
npx tsc -b          # typecheck
npx oxlint          # lint
npm run build       # production build
```

There is no frontend unit-test runner; verification is typecheck + lint + build.

Export a machine-readable benchmark artifact (writes a new file, never
overwrites):

```bash
cd backend
.venv\Scripts\python -m scripts.export_benchmark --budget 1 --seed 42
```

See [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) and
[`docs/benchmark-results/`](docs/benchmark-results/) for the reference results.

## 📚 Documentation

| Document | Contents |
|----------|----------|
| [`docs/RESEARCH_INDEX.md`](docs/RESEARCH_INDEX.md) | Index of the research documentation package |
| [`docs/RESEARCH_OVERVIEW.md`](docs/RESEARCH_OVERVIEW.md) | Abstract-level overview + results/limitations |
| [`docs/PROBLEM_AND_GAP.md`](docs/PROBLEM_AND_GAP.md) | Problem statement and the gap addressed |
| [`docs/TIDE_INNOVATION.md`](docs/TIDE_INNOVATION.md) | TIDE-Loop, formula, evidence, verdicts |
| [`docs/SYSTEM_WORKFLOW.md`](docs/SYSTEM_WORKFLOW.md) | Stage-by-stage workflow + data provenance |
| [`docs/SCIENTIFIC_METHOD.md`](docs/SCIENTIFIC_METHOD.md) | Claim hierarchy, validation metrics, threats |
| [`docs/EXPERIMENTAL_DESIGN.md`](docs/EXPERIMENTAL_DESIGN.md) | Benchmark strategies, fairness, reference results |
| [`docs/RESULTS_AND_LIMITATIONS.md`](docs/RESULTS_AND_LIMITATIONS.md) | Implemented/tested/demonstrated/validated split |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System + TIDE-Loop architecture, components |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Local, Docker and cloud deployment, troubleshooting |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | Environment, dataset, seeds, expected outputs |
| [`docs/API.md`](docs/API.md) | API contracts, status codes, simulation isolation |
| [`docs/SCIENTIFIC_LIMITATIONS.md`](docs/SCIENTIFIC_LIMITATIONS.md) | Claim boundaries and maturity vocabulary |
| [`docs/TIDE_ALGORITHM.md`](docs/TIDE_ALGORITHM.md) | TIDE scoring + simulation algorithm |
| [`docs/TIDE_BENCHMARK_PROTOCOL.md`](docs/TIDE_BENCHMARK_PROTOCOL.md) | Fair benchmark methodology |
| [`docs/TIDE_VALIDATION_REPORT.md`](docs/TIDE_VALIDATION_REPORT.md) | Actual validation/benchmark results |
| [`docs/DEMO_READINESS.md`](docs/DEMO_READINESS.md) | Verified demo checklist |
| [`docs/FINAL_DEMO_CHECKLIST.md`](docs/FINAL_DEMO_CHECKLIST.md) | Before / during / backup demo checklist |
| [`docs/FINAL_ENGINEERING_REPORT.md`](docs/FINAL_ENGINEERING_REPORT.md) | Final status + evidence |
| [`docs/ENDPOINTS.md`](docs/ENDPOINTS.md) | Full served-endpoint inventory |

## ⚠️ Scientific limitations

- TIDE uses **deterministic / heuristic scoring**. It is *implemented*,
  *demonstrated*, and *tested* — **not empirically validated**. The
  empirically-validated list is intentionally empty.
- **Virtual observations are demonstrations**, derived from existing inputs and
  never written to the observation store.
- **Confidence is a heuristic score**, not a calibrated probability, and is
  distinct from uncertainty, observation value, and decision impact.
- **Decision Replay** is a read-only demonstration/analysis framework.
- Missing data is shown as `NOT AVAILABLE` / `INSUFFICIENT DATA` / `GROUND TRUTH
  UNAVAILABLE` — never fabricated.

---

## 🗂️ Folder Structure Explained (File by File)

Everything you see below has a specific job. Think of it like the organs of a body — each one does something different, but together they make the organism work.

```
C:\Project 2.0\
│
├── backend/
│   │   The "brain" of the app. Written in Python (FastAPI).
│   │   Receives requests from the website, talks to the database and AI.
│   │
│   ├── app/
│   │   │   The actual application code.
│   │   │
│   │   ├── api/
│   │   │   │   All the "doors" (endpoints) that the website knocks on.
│   │   │   │   E.g. GET /temperature, POST /ask-ai
│   │   │   │
│   │   ├── core/
│   │   │   │   Core settings: database connection, security, config.
│   │   │   │   The "wiring" that connects everything.
│   │   │   │
│   │   ├── models/
│   │   │   │   Database models (SQLAlchemy) — describes the tables.
│   │   │   │   Like a blueprint of the database.
│   │   │   │
│   │   ├── schemas/
│   │   │   │   Data "shapes" for sending/receiving (Pydantic).
│   │   │   │   Ensures data is valid before it enters the system.
│   │   │   │
│   │   ├── services/
│   │   │   │   Business logic — the actual work happens here.
│   │   │   │   Fetching real ocean data from public APIs.
│   │   │   │
│   │   └── modules/
│   │       │   AI features live here, each in its own folder.
│   │       │
│   │       └── ai/
│   │           ├── anomaly/
│   │           │   Detects strange/harmful ocean events (like oil spills,
│   │           │   harmful algal blooms, temperature spikes).
│   │           │
│   │           ├── forecast/
│   │           │   Predicts future ocean conditions using machine learning.
│   │           │
│   │           └── nlp/
│   │               Natural Language Processing — powers the "Ocean AI
│   │               Assistant" that understands plain-English questions.
│   │
│   ├── scripts/
│   │       Small helper scripts (run once to set things up, download data).
│   │
│   └── tests/
│           Automatic tests to make sure nothing breaks.
│
├── frontend/
│   │   The "face" of the app — what the user sees. React + TypeScript.
│   │
│   └── src/
│       ├── components/
│       │   │   Reusable building blocks (buttons, cards, the 3D globe).
│       │   │
│       │   ├── 3d/
│       │   │   ├── globe/    The 3D ocean globe (Cesium/Three.js)
│       │   │   └── layers/   Data layers (heat, waves, currents)
│       │   │
│       │   ├── ui/           Buttons, glass cards, inputs, modals
│       │   └── charts/       Line, bar, comparison charts
│       │
│       ├── pages/            Each webpage (Dashboard, Maps, Reports)
│       ├── api/              How the frontend talks to the backend
│       ├── store/            Global state (what the app remembers)
│       ├── hooks/            Reusable React logic
│       ├── types/            Shared TypeScript contracts
│       └── assets/           Images, logos, icons
│
├── run.ps1 / run.sh
│       One-command local launcher (backend + frontend together).
│
├── docker-compose.yml
│       Containerised deployment: database + backend + frontend.
│
├── docs/
│       Detailed documentation — explains every part of the project.
│
└── presentation/
        Slides, posters, demo videos for the SIH final presentation.
```

---

## 🧠 The Big Idea (One Sentence)

> TidalTwin turns public ocean data into a **model-validation decision
> engine**: every coast is scored on how much the model disagrees with reality,
> why it matters, and what to do — from a scientist's confidence score to a
> fisherman's safety bulletin.

---

## 🚀 Deployment with Docker (One Command)

The whole platform — database, AI backend, and web frontend — ships as containers.
With Docker installed, you can bring the entire app up on any machine:

```bash
docker compose up --build
```

| Service    | URL                 | Notes                                 |
|------------|---------------------|---------------------------------------|
| Frontend   | http://localhost:8080 | React app served by nginx            |
| Backend    | http://localhost:8000 | FastAPI + AI engine (docs at /docs)  |
| Database   | localhost:5433       | PostgreSQL 16 + PostGIS              |

What happens on startup (automatically):
1. PostGIS database starts and becomes healthy.
2. Backend container waits for the DB, then:
   - creates all tables (`init_db`)
   - seeds the 8 Indian coastal locations (`seed_data`)
   - pulls live ocean observations from Open-Meteo (`refresh_ocean_data` — best effort)
3. Frontend container serves the app and proxies every `/api/...` call to the backend.

Stop everything:

```bash
docker compose down          # stop
docker compose down -v       # stop AND wipe the database volume (fresh start)
```

### Running locally (without Docker)
Backend: `cd backend`, then `uvicorn app.main:app --reload` (needs Python + PostgreSQL).
Frontend: `cd frontend`, then `npm run dev`.

---

## 🏆 SIH Presentation Package

Everything you need to present and win lives in [`presentation/`](presentation/):

| File | What it's for |
|------|---------------|
| `pitch.md` | The judge-facing story: problem → innovation → impact → ask |
| `demo-script.md` | A timed 5-minute walkthrough of every page and moment |
| `project-summary.md` | Features, architecture, tech stack, roadmap |
| `checklist.md` | Final verification checklist to run before judging |
