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
- [ ] `GET /api/v1/safety/advisory` → 8 regions with status + safe window
- [ ] `GET /api/v1/safety/storm` → 25-point cyclone track with wind + radius
- [ ] `GET /api/v1/safety/trust` → 8 regions with MAE sparkline + drift flag
- [ ] `GET /api/v1/safety/timeseries` → 8 regions, 72 points each (48 obs + 24 forecast)
- [ ] `WS /api/v1/safety/ws/live` → snapshot + repeated broadcasts (every 12s)
- [ ] `GET /api/v1/validation/confidence` → per-coast obs confidence + **component breakdown** (why 82%?)
- [ ] `GET /api/v1/validation/difference` → MODEL | OBSERVED | DEVIATION per field (optionally `?location_id=`)
- [ ] `GET /api/v1/validation/situation` → operational situation strip per coast
- [ ] `GET /api/v1/validation/skill` → per-variable MAE / RMSE / bias / skill-vs-climatology
- [ ] `GET /api/v1/validation/events` → classified phenomena (heatwave, flood risk, mismatch…)
- [ ] `GET /api/v1/validation/provenance` → source / dataset / model run / processing per coast
- [ ] `POST /api/v1/validation/scenario` `{location_id, wind_percent}` → labelled what-if projection

## ✅ Frontend Pages (http://localhost:5173)

- [ ] **Dashboard** — health ring, gauges, region chips, telemetry load, **Ocean Situation strip**
- [ ] **Digital Twin** — 3D globe renders, markers appear, layers toggle
- [ ] **Digital Twin** — Storm Track layer shows cyclone path, cone + moving eye
- [ ] **Digital Twin** — **Event Replay**: Observed / Model / Difference modes + deviation readout
- [ ] **Monitoring** — "Run AI Radar Scan" works, alerts render with severity
- [ ] **Model Validation** — MODEL|OBSERVED|DEVIATION rows, "why it matters" panel,
      confidence meters with **why-92% component breakdown**, **Model Skill Score**
      (MAE/RMSE/bias/skill), **Ocean Event Detection** cards, **What-If simulator**
      (wind slider → wave/SST/hazard band), **Data Provenance** table,
      forecast-vs-reality charts for any coast
- [ ] **Ocean AI** — all 4 demo questions answered correctly
- [ ] **Safety Center** — advisory cards, LIVE Command Feed (WebSocket), SMS phone mock,
      multilingual voice bulletins, trust sparklines
- [ ] **Risk Map** — India silhouette, risk-banded markers, storm track + eye, threat ranking
- [ ] **Story Mode** — 4 stories, chapter flips, live data facts show
- [ ] **Reports** — national gauge, risk table, summary, CSV download
- [ ] **PWA** — `/manifest.webmanifest` + `/sw.js` served; install prompt hinted in prod build
- [ ] Every nav item highlights correctly; page transitions smooth

## ✅ The AI Heatwave Demo (5-minute judge moment)

1. [ ] Simulate the heatwave:
   ```
   cd backend
   .venv\Scripts\python -m scripts.simulate_anomaly --kind heatwave --location goa
   ```
2. [ ] Open **Monitoring**, watch an alert appear on "Goa" (medium, ~85%).
3. [ ] Open **Model Validation**, select Goa — **+1.8°C deviation**, red row,
      "persistent surface heating" interpretation, HIGH DISAGREEMENT flag,
      **marine heatwave** event card with evolution, skill score visible.
4. [ ] Open **Safety Center** — Goa card shows **DANGER/CAUTION**; run **SMS Alert** mock.
5. [ ] Open **Reports** — Goa ranked #1 ELEVATED, national gauge reflects it.
6. [ ] Assistant answers `is it safe to go fishing in goa today?`.

## ✅ Data Integrity

- [ ] Exactly 8 locations, no duplicates (seed script is idempotent).
- [ ] Observations have timestamps in ascending order (anomaly window correct).
- [ ] Alert timestamps and statuses correct after a scan.

## ✅ Code Quality

- [ ] Frontend builds with zero TypeScript errors: `npm run build`.
- [ ] No `.env` committed (contains `Dharani%407` password — it's gitignored).
- [ ] No `node_modules`, `.venv`, or `dist` in git.
- [ ] `git log` tells the full story (Step 1 → Step 14 → features: Model Validation,
      Safety Center, Risk Map, storm + Event Replay, live WebSocket feed, PWA).

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