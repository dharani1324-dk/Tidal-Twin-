# OceanVerse AI — Final Verification Checklist

Run this BEFORE the demo, the final submission, or any judge preview.
Everything below has been verified working during development.

---

## ✅ Core Services

- [ ] PostgreSQL service is running (`postgresql-x64-18` in Services).
- [ ] Database `oceanverse` exists with PostGIS enabled:
  ```
  psql -U postgres -h localhost -d oceanverse -c "SELECT PostGIS_Version();"
  ```
- [ ] Backend starts cleanly: `uvicorn app.main:app --reload` (port 8000).
- [ ] Frontend starts cleanly: `npm run dev` (port 5173).
- [ ] Docker (optional): `docker compose config` parses without errors.
  (Requires Docker Desktop/engine — not currently installed on this machine.)

## ✅ Backend Endpoints (Open http://127.0.0.1:8000/docs)

- [ ] `GET /api/v1/health` → `{"status":"healthy"}`
- [ ] `GET /api/v1/db-status` → connection OK + counts
- [ ] `GET /api/v1/ocean/locations` → 8 locations
- [ ] `GET /api/v1/ocean/locations/1/observations` → rows returned
- [ ] `POST /api/v1/monitoring/scan` → `{"scan":{"scanned":8,...}}`
- [ ] `GET /api/v1/monitoring/alerts` → list (1 active if heatwave simulated)
- [ ] `GET /api/v1/monitoring/forecast` → 8 regions, 12 points each
- [ ] `GET /api/v1/stories` → 4 stories with hooks
- [ ] `GET /api/v1/comparison` → 8 comparisons with MAE metrics
- [ ] `GET /api/v1/reports/index` → 8 regions ranked
- [ ] `GET /api/v1/reports/summary` → executive summary text
- [ ] `GET /api/v1/reports/csv` → downloads valid CSV (header + data rows)
- [ ] `POST /api/v1/assistant/ask` → answers: safety, trend, compare, hottest/coldest

## ✅ Frontend Pages (http://localhost:5173)

- [ ] **Dashboard** — health ring, gauges, region chips, telemetry load
- [ ] **Digital Twin** — 3D globe renders, markers appear, layers toggle
- [ ] **Monitoring** — "Run AI Radar Scan" works, alerts render with severity
- [ ] **Ocean AI** — all 4 demo questions answered correctly
- [ ] **Story Mode** — 4 stories, chapter flips, live data facts show
- [ ] **Reports** — national gauge, risk table, summary, CSV download
- [ ] Every nav item highlights correctly; page transitions smooth

## ✅ The AI Heatwave Demo (5-minute judge moment)

1. [ ] Simulate the heatwave:
   ```
   cd backend
   .venv\Scripts\python -m scripts.simulate_anomaly --kind heatwave --location goa
   ```
2. [ ] Open **Monitoring**, watch an alert appear on "Goa" (medium, ~85%).
3. [ ] Open **Reports** — Goa ranked #1 ELEVATED, national gauge reflects it.
4. [ ] Assistant answers `is it safe to go fishing in goa today?`.

## ✅ Data Integrity

- [ ] Exactly 8 locations, no duplicates (seed script is idempotent).
- [ ] Observations have timestamps in ascending order (anomaly window correct).
- [ ] Alert timestamps and statuses correct after a scan.

## ✅ Code Quality

- [ ] Frontend builds with zero TypeScript errors: `npm run build`.
- [ ] No `.env` committed (contains `Dharani%407` password — it's gitignored).
- [ ] No `node_modules`, `.venv`, or `dist` in git.
- [ ] `git log` tells the full story (Step 1 → Step 14).

## 🚨 Smoke Test (run right before judging)
```
cd frontend && npm run dev        # terminal 1
cd backend  && uvicorn app.main:app --reload   # terminal 2
# keep both windows visible, open the browser at localhost:5173
```

## Backup Powers (if something breaks)
- Backend restart fixes most issues (in-memory engines warm up instantly).
- If the frontend can't reach the backend, restart uvicorn and refresh.
- If alert detection gives 0 alerts: ensure the heatwave data was inserted
  (rows with source `SIMULATED_HEATWAVE`), then re-scan.