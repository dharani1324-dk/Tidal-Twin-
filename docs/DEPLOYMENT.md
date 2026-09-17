# TidalTwin — Deployment Guide

> Concise, executable instructions for running TidalTwin locally, in Docker, or
> on a cloud host. For architecture see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## 1. Local development

Prerequisites: **Python 3.12+**, **Node.js 20+**, **PostgreSQL 16 with PostGIS**.

```bash
# One command (starts backend + frontend together)
./run.sh            # macOS / Linux
.\run.ps1           # Windows PowerShell
```

Then open <http://127.0.0.1:5173>. Or run the two halves manually:

```bash
# Terminal 1 - backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 - frontend
cd frontend
npm install
npm run dev
```

## 2. Environment setup

| File | Purpose |
|------|---------|
| `backend/.env` | Copy from `backend/.env.example`. Set `DATABASE_URL`. |
| `frontend/.env.local` | Copy from `frontend/.env.example`. Set `VITE_API_BASE_URL` (empty when same-origin). |
| Root | No root env file; `docker compose` reads shell environment. |

Never commit `.env` / `.env.local`. Both are gitignored. If you set
`ENVIRONMENT=production` while `DATABASE_URL` still points at `localhost`, the
backend logs a warning at startup (it does not crash).

## 3. Database setup

```bash
cd backend
python -m scripts.init_db          # create tables / extensions
python -m scripts.seed_data        # seed 8 coastal locations
python -m scripts.refresh_ocean_data   # best-effort live observations
```

## 4. Demo mode

```bash
curl -X POST http://127.0.0.1:8000/api/v1/demo/seed     # labelled SIMULATED rows
curl      http://127.0.0.1:8000/api/v1/demo/status      # demo data + demo event
curl -X POST http://127.0.0.1:8000/api/v1/demo/reset    # remove only simulated rows
```

Or use **START TIDE DEMO** in the running frontend. Reset affects only
simulation-labelled rows and saved UI state; real observations are never
modified.

## 5. Production build

```bash
cd frontend
npm run build        # copy:cesium + tsc typecheck + vite build -> dist/
```

The backend is served by Uvicorn; there is no separate compile step.

## 6. Deployment (Docker — recommended)

```bash
docker compose up --build          # db + backend + frontend
# open http://localhost:8080
```

| Service | URL |
|---------|-----|
| Frontend (nginx) | <http://localhost:8080> |
| Backend | <http://localhost:8000> (docs at `/docs`) |
| Database | `localhost:5433` |

Everything is overridable without editing the file:

```bash
ENVIRONMENT=production CORS_ORIGINS=https://app.example.com \
POSTGRES_PASSWORD='<strong-secret>' \
CESIUM_ION_TOKEN='<your-token>' \
docker compose up --build -d
```

Startup sequence: PostGIS becomes healthy → backend waits, initialises schema,
seeds locations, refreshes live data (best effort) → backend healthcheck passes →
frontend starts. The backend image runs as the `production` environment by
default in Compose.

### Cloud

No provider-specific config is required. Any host with Docker can run the
Compose file. For a managed database, set `DATABASE_URL` directly and point
`CORS_ORIGINS` at the frontend origin. Do **not** use the default
`POSTGRES_PASSWORD` in any public deployment.

## 7. Health check

```bash
curl http://localhost:8000/api/health          # or /api/v1/health
```

Reports per-subsystem `AVAILABLE` / `LIMITED` / `UNAVAILABLE` /
`OPTIONAL / UNAVAILABLE`, plus `version`, `release`, `environment`,
`simulation_mode`. Compose uses this endpoint for the backend healthcheck.

## 8. Shutdown / reset

```bash
docker compose down            # stop containers, keep database
docker compose down -v         # stop AND wipe the database volume (fresh start)
```

## 9. Troubleshooting / common errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Database unreachable` in health | wrong `DATABASE_URL` / DB not up | start PostGIS, fix credentials, URL-encode special chars |
| Frontend calls fail in the browser | CORS blocked / wrong API base | set `CORS_ORIGINS`; set `VITE_API_BASE_URL` for cross-origin |
| `POSTGIS` errors on table creation | DB is plain PostgreSQL | use `postgis/postgis` image or install PostGIS |
| Globe has no detailed terrain | no Cesium Ion token | optional — set `CESIUM_ION_TOKEN` / `VITE_CESIUM_ION_TOKEN` |
| First TIDE request is slow (~5 s) | cold shared-input cache | expected once; startup warms it, subsequent calls ~0.2 s |
| Live refresh failed at startup | no internet in container | non-fatal; app runs on seeded data |
| Port already in use | 8000/8080/5173/5433 taken | stop the other process or remap the port |
