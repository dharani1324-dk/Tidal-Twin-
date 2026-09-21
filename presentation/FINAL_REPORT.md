# TidalTwin — Final Hackathon Report

**An Interactive 4D Ocean Model Validation & Decision Intelligence Platform**
Release 1.0.0 · "TIDE-Loop" · Built for the Smart India Hackathon (SIH)

> How the whole project works, every feature's workflow, and how to present it.
> Every number and claim in this report is traceable to the repository —
> nothing is invented, and limits are stated explicitly.

---

## 1. One-minute overview (tell the judges this)

TidalTwin is **not another ocean viewer**. It is a **4D ocean digital twin** — a
live 3D globe of the Indian Ocean, fed by **real public ocean data** (satellite,
Argo floats, underwater gliders, ship CTD casts, ocean-model grids) — that goes
one step further than "see what's happening": it **compares an ocean model
against reality field by field, detects and investigates anomalies, and decides
_in which coastal region the next observation gives the most decision value_.**

Three pillars:

1. **Real data, honestly labelled.** Live NOAA/ERDDAP sources (ERSST v5
   sea-surface temperature, VIIRS·Himawari satellite chlorophyll, HYCOM
   ocean-model 3D grid, Argo floats, gliders, CTD casts, NetCDF in-situ files).
   The UI never fabricates a value — a missing measurement is shown as
   "Data unavailable" with the exact command that ingests it.
2. **Observation → Detection → Investigation → Decision loop (TIDE-Loop).**
   MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION → BETTER DECISION →
   VALIDATION ↺, closed around a transparent, deterministic scoring formula.
3. **A decision-support product, not a chart.** From a scientist's confidence
   score to a fisherman's safety bulletin — everything ends in a ranked,
   evidence-backed recommendation and a replayable decision history.

---

## 2. The problem and the gap

Ocean data is **multidimensional** (space × depth × time), **dynamic** and
**heterogeneous** (buoys, satellites, floats, ships, models). Existing ocean
platforms already answer: *What is happening? Where? When? Why?*

**The gap this project addresses:** given a limited budget of sensors and
ships, **WHERE should we observe NEXT, and WHY there?** An investigation that
stops at a map is not a decision. TidalTwin turns an ocean investigation into
**prioritisation, evidence, a virtual what-if test, a replayable decision, and
an honest validation.**

---

## 3. The innovation — TIDE-Loop

**T**rust-aware **I**nformation for **D**ecision and **E**xploration.

```
Observation Value =
  Decision Impact × Uncertainty × Data Gap × Anomaly Persistence
  ÷ Observation Cost
```

| Factor | One-line meaning |
|--------|------------------|
| Decision Impact | how much a decision depends on this variable |
| Uncertainty | how uncertain that variable currently is |
| Data Gap | how sparse/stale the coverage is |
| Anomaly Persistence | how long the anomaly has persisted |
| Observation Cost | normalised cost of the observation method |

Guards: inputs are clamped to finite 0–1; cost is floored (ε = 0.05) so a
zero-cost method can't inflate the score; cost values are **demonstration
assumptions**, never a monetary claim. TIDE is deterministic, transparent and
**honestly labelled a decision-support heuristic** — not an empirically
validated model (that list is intentionally empty).

The loop it drives:

```
MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION → BETTER DECISION → VALIDATION ↺
```

---

## 4. How the whole project works (end to end)

### 4.1 The layered flow

```
                PUBLIC OCEAN DATA SOURCES
        NOAA ERSST · CoastWatch VIIRS · HYCOM · Argo · Gliders · CTD · NetCDF files
                          │  (fetch_*.py / ingest_*.py on a networked host)
                          ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                     BACKEND — FastAPI (Python)                │
        │  app/api/*      HTTP doors (REST /api/v1/*)                   │
        │  app/modules/*  AI engines: twin · anomaly · forensics ·      │
        │                 tide · coastal · apex · nlp copilot · ...     │
        │  app/models/*   SQLAlchemy tables (observations, locations,   │
        │                 argo, glider, ctd, netcdf, alerts, provenance)│
        └───────────────────────────────┬───────────────────────────────┘
                          │  SQLAlchemy / SQL
                          ▼
              PostgreSQL 16 + PostGIS  (the "truth store")
                          ▲
        ┌─────────────────┴─────────────────────────────────────────────┐
        │  FRONTEND — React 19 · TypeScript · Vite · CesiumJS           │
        │  App shell (sidebar + status bar + alerts)                    │
        │  18 pages · 3D Digital Twin globe · Copilot FAB               │
        └───────────────────────────────────────────────────────────────┘
```

**A request end to end (example: the depth-slice layer).**
1. User toggles "Model Depth Slice" on `/globe`.
2. React calls `fetchModelGridSummary()` on the typed API client.
3. Axios `GET /api/v1/modelgrid/summary` hits FastAPI.
4. The router queries ingested NetCDF grid rows via SQLAlchemy.
5. The response returns the **real** available fields and their depth levels
   (`available: true/false` is honest — no fake grid).
6. React renders the depth picker and, when a real level is selected, requests
   `GET /api/v1/modelgrid/latest?variable=…&depth_m=…`.
7. CesiumJS paints those cells on the globe, colored by a live domain-scaled
   ramp. If no grid is ingested yet, the card says so honestly.

### 4.2 The research/decision workflow (product journey)

| Stage | Question answered | Where |
|-------|-------------------|-------|
| **OBSERVE** | What is the ocean doing now? | Digital Twin globe |
| **DETECT** | Is anything unusual? | Anomaly Radar |
| **INVESTIGATE** | Why, and how coherent is it? | Ocean Forensics |
| **UNDERSTAND** | What kind of event is this? | Event Timeline + Event DNA fingerprint |
| **PRIORITIZE** | Where should we look next? | TIDE ranking + evidence |
| **OBSERVE NEXT** | What is the recommended next observation? | TIDE candidate + APEX |
| **SIMULATE** | What if we measure there? | Virtual observation (never persisted) |
| **DECIDE** | What is the decision state? | Decision rule + verdict |
| **VALIDATE** | How well did it behave, honestly? | Validation + benchmark framework |

The loop then repeats — validation outcomes and new observations re-enter at
OBSERVE. This exact sequence is what the **START TIDE DEMO** guide walks a judge
through (8 steps, navigating the real app, no fake animation).

---

## 5. System architecture & stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19 · TypeScript ~6.0 · Vite 8 · CesiumJS 1.145 · recharts · three · framer-motion · lucide-react |
| Backend | Python 3.12 · FastAPI · SQLAlchemy · Pydantic v2 · uvicorn |
| Database | PostgreSQL 16 + PostGIS |
| Deployment | Docker Compose (frontend nginx :8080 · backend :8000 · DB :5433) or local `run.ps1` / `run.sh` |
| API docs | auto Swagger at `http://localhost:8000/docs` |

**Backend layout (why it's clean to present):**
- `app/api/*` — HTTP routers (health, ocean, twin, tide, argo, ersst, chlor,
  modelgrid, glider, ctd, ogc, cf, monitoring, intelligence, forensics,
  coastal, apex, safety, reports, stories, edr, currents, lens, scenario, demo…).
- `app/modules/ai/*` — the engines: `twin/`, `anomaly/`, `forensics/`,
  `tide/`, `validation/`, `coastal/`, `apex/`, `nlp/` (copilot), `comparison/`,
  `forecast/`, `scenarios/`.
- `app/models/*` — `OceanLocation`, `OceanObservation`, `OceanAlert`,
  `AisTrack/DerivedCurrent`, `NetcdfReadings`, `ArgoProfile`, `GliderProfile`,
  `CtdProfile`, `ProvenanceRecord`.
- `scripts/*` — one-time/data scripts: `init_db`, `seed_data`, `fetch_ersst`,
  `fetch_chlor`, `fetch_argo`, `fetch_glider`, `fetch_model`, `ingest_netcdf`,
  `ingest_ascii`, `ingest_ctd`, `refresh_ocean_data`, `probe_authoritative`.

**Frontend layout:** `App.tsx` (shell: grouped nav, live system status bar,
alert bell, "Ask Ocean AI" ⌘K), `pages/*` (18 pages), `components/3d/globe`
(CesiumGlobe + layered maths), `components/workspace` (TrustBadge, SystemHealth,
UncertaintyGauge, EvidenceDrawer), `api/client.ts` (typed wrappers).

---

## 6. The real-data backbone (science features, SIH 22-item checklist)

The core principle repeated everywhere: **real data, honestly labelled.** Five
provenance tokens are rendered by a single `TrustBadge` component —
`REAL · HISTORICAL · MODEL_DERIVED · SIMULATED · SYNTHETIC` — and a simulated
row can never be shown as REAL.

### 6.1 Real data sources

| Source | What it provides | Pipeline |
|--------|------------------|----------|
| NOAA ERSST v5 | Sea-surface temperature, 2° global | `fetch_ersst.py` → `/api/v1/ersst/latest` |
| CoastWatch VIIRS·Himawari | Satellite chlorophyll, ~5 km | `fetch_chlor.py` → `/api/v1/chlor/latest` |
| HYCOM (ERDDAP) | 3D ocean-model grid: temperature, salinity, current u/v | `fetch_model.py` → `netcdf_readings` → `/api/v1/modelgrid/*` |
| Argo (GDAC) | Real float T/S depth profiles, Indian Ocean | `fetch_argo.py`+`ingest_argo.py` → `/api/v1/argo/*` |
| Underwater gliders | Deployment tracks + T/S + **BGC (O₂/chlorophyll/nitrate)** | `fetch_glider.py` → `/api/v1/glider/*` |
| Ship CTD casts | Station T/S profiles (+ optional BGC) | `ingest_ctd.py` → `/api/v1/ctd/*` |
| NetCDF / ASCII files | In-situ sets, CF-convention | `ingest_netcdf.py`, `ingest_ascii.py` → `/api/v1/cf/validate` |
| Open-Meteo Marine | Live/cached coastal observations for TIDE | `refresh_ocean_data.py` |

### 6.2 The 22 scientific vis features (this sprint verified them end-to-end)

| # | Feature | Workflow (what → how → where) |
|---|---------|-------------------------------|
| 1 | Real NetCDF ingestion | netCDF file → axis mapping → `netcdf_readings` |
| 2 | CF-NetCDF conformance | standard_name/units aliases resolved at ingest |
| 3 | HYCOM 3D fetch | model monthly 3D grid → rows.temperature/salinity/current |
| 4 | Argo pipeline | float IDs → profile fetch → T/S per depth |
| 5 | Salinity field | grid salinity + frontend T/S pills + colorscale |
| 6 | 3D fields (depth) | `depth_m` carried through grid, transects, profiles |
| 7 | **Horizontal depth slices** | pick a real depth → cells colored T/S at that level |
| 8 | Live-domain colorscales | `ColorScaleBar` rescales from actual min/max |
| 9 | Per-field statistics | stats computed from real rows + `domainFrom` |
| 10 | Linear/log scale modes | `ScaleMode` toggle re-maps color ramp |
| 11 | Isosurfaces | marching-squares isolines on real fields |
| 12 | Layer opacity | per-layer sliders; re-colors without rebuilding the scene |
| 13 | Vertical exaggeration | 3D vertical scale slider |
| 14 | Current vectors | real u/v → arrow field (strongest → filtered 600) |
| 15 | Real Argo overlay | real floats rendered; click → depth profile |
| 16 | **Real glider overlay** | tracks polylines; click → physical profile |
| 17 | **CTD cast + BGC** | CTD ingest/API; glider BGC sub-charts (O₂/Chl/Nitrate) |
| 18 | Profile + transect views | T/S vs depth charts, reversed-depth-axis |
| 19 | ASCII observation import | CSV/whitespace file → linked observations |
| 20 | Sensor/plugin registry | plug unify a new sensor family without core changes |
| 21 | OGC services | WMS/WCS (`/ogc`) + EDR collections |
| 22 | CF validation | `netcdf_validate.py` + `/api/v1/cf/validate` |

> Status this sprint: all 22 present. The three that previously had backend-only
> support (#7 depth slices, #16 gliders, #17 CTD/BGC) now have full frontend
> UIs. Real downloads (chlor, model grid, gliders, CTD) must run on a networked
> host — the local UI honestly shows the ingest commands.

### 6.3 The Digital Twin globe — 18 layers a user can toggle

`Labels · Sea Temperature · Wave Height · Ocean Currents · Storm Track · Data
Uncertainty · Sampling Priority · Simulated Argo · Real Argo · Real SST (ERSST)
· Satellite Chlorophyll · Model-vs-Reality · Anomaly Beacons · TIDE decisions ·
SST Isolines · Current Vectors · Model Depth Slice · Real Gliders`

---

## 7. Feature catalog — every feature family and its workflow

### A. 3D Digital Twin / visualization
**Digital Twin globe** — Cesium globe + per-layer geometry + click-to-detail.
*Workflow:* toggle layer → `fetch{Field}Latest` → real rows → Cesium primitives
(billboard/polyline/points) → click → profile drawer.

### B. Ocean event intelligence
- **Anomaly Radar** — thresholds vs model baseline → flags
  `marine_heatwave · cold_water_anomaly · rapid_temp_change ·
  strong_current_event · coastal_flooding_risk · model_mismatch_event`.
- **Ocean Forensics** — what changed, when, at what depth, contributing
  factors, uncertainty → feeds TIDE (÷100).
- **Event DNA** — structured multi-variable fingerprint of an event
  (contextual evidence for downstream decisions).

### C. The decision loop (TIDE)
- **Command Center** (`/tide`) — ranked candidates, evidence, confidence,
  verdict. *Workflow:* `adapters` (uncertainty/events/gaps/disagreement/APEX) →
  `TideEngine.rankings()` → candidate score → evidence + `verdicts.classify`.
- **What-If** — pick location → virtual sensor → simulated reading →
  before/after uncertainty, risk, rank, decision. **Never persisted, always
  labelled SIMULATED.**
- **Decision Replay** (`/tide/replay`) — model-only vs TIDE-assisted, read-only,
  10-step timeline.
- **Validation Center** (`/tide/validation`) — maturity, dataset, ground-truth
  availability, consistency, edge cases + reproducible benchmarks
  (RANDOM · UNIFORM · UNCERTAINTY_ONLY · ANOMALY_ONLY · DATA_GAP_ONLY · TIDE).
  Reference run: budget 1, seed 42, 768 obs, 3 events →

  | Strategy | Decision change | Mean uncertainty reduction |
  |----------|:---------------:|:--------------------------:|
  | RANDOM | 1.00 | 0.1905 |
  | UNIFORM | 1.00 | 0.1883 |
  | UNCERTAINTY_ONLY | 1.00 | 0.1898 |
  | ANOMALY_ONLY | 0.75 | 0.2527 |
  | DATA_GAP_ONLY | 1.00 | 0.1898 |
  | **TIDE** | **0.75** | **0.2527** |

  Honest slide: **TIDE ties ANOMALY_ONLY** in this run; no superiority claimed.

### D. Ocean Vision & decision intelligence
- **Ocean Vision** (`/oceanvision`) — Apex engines: remote sensing, adaptive
  recommendations, light pollution, carbon, sensing advisories.
- **Decision Intelligence** (`/intelligence`) — coverage, events, impact,
  priority, relationships, threat-chains.
- **Anomaly Intel** (`/anomalies`) — ranked anomaly explorer.
- **Forensics page** (`/forensics`) — timeline + DNA fingerprint.

### E. Coastal, safety, risk, reporting
- **Coastal Intel** (`/coastal`) — oil spill, sea-level rise, impact, fisheries,
  coral, beach models.
- **Safety Center** (`/safety`) — live advisory feed, storm, trust, websocket
  broadcast loop.
- **Risk Map** (`/risk`) — national risk geospatial.
- **Risk Report** (`/reports`) — generated national risk summary.
- **Story Mode** (`/stories`) — narrative analysis of fields.

### F. Copilot
- **Ocean AI Copilot** (`/assistant`) — natural-language interface onto the
  *same grounded engines* (intent detection + context-aware answers), plus a
  floating **Ask Ocean AI** button everywhere and ⌘K.

### G. Monitoring & ops
- **Ocean Surveillance** (`/monitoring`) — alerts, forecasts, scan.
- App shell — live system status bar (`SYS`, `SAT LINK`, regions, critical
  alert badge, `LIVE/UPDATED Ns AGO`), notification bell, per-route
  `ErrorBoundary` so one surface can't blank the app, `SystemStatusPill`,
  **DemoGuide** (the 8-step tour).

---

## 8. Three end-to-end walkthroughs you can narrate live

**Walkthrough 1 — Data lifecycle (how real data gets in).**
`fetch_ersst.py` (or `fetch_argo.py`, `fetch_model.py`, `ingest_ctd.py`) →
writes real rows to the DB with provenance → API endpoint serves them →
UI renders them honestly; if nothing is ingested the UI says "Data
unavailable" and shows the exact command to run on a networked host.

**Walkthrough 2 — An incident, decided (the demo's core arc).**
The anomaly radar flags an event → forensics explains it → Event DNA
fingerprints it → TIDE ranks where to observe next with evidence →
"what if we measure here" shows before/after → replay shows the decision path →
validation reports honestly how well the run behaved.

**Walkthrough 3 — A user session on the globe.**
Toggle Real SST → toggle isolines + depth slice + vectors + gliders → click an
Argo float → depth profile chart → click a glider → physical profile + BGC
sub-charts → ask the Copilot to summarize the region.

---

## 9. API surface (grouped, all verified live)

`/health`, `/status`, `/demo/*` · `/ocean/*` · `/monitoring/*` · `/twin/*` ·
`/anomaly/*`?→`/anomalies` routes, `/intelligence/*` · `/currents/*` (`derived`,
`lens`) · `/forensics` · `/tide/*` (candidates, rankings, uncertainty, data
gaps, disagreements, evidence, verdict, explanation, decision, events, replay,
validation, benchmarks, `virtual-observation` POST) · `/validation/*` ·
`/comparison` · `/apex/*` · `/coastal/*` · `/safety/*` (incl. websocket) ·
`/reports/*` · `/stories` · `/scenarios` · `/assistant/*` (ask / multimodal
POST) · `/edr/collections` · `/ogc/*` (WMS/WCS) · `/cf/validate` ·
`/argo/*` · `/ersst/latest` · `/chlor/latest` · `/modelgrid/*` (summary,
latest, vectors) · `/glider/*` (deployments, samples, bgc) · `/ctd/*`
(stations, profile) · full Swagger at `/docs`.

---

## 10. Verification & engineering status (as verified this sprint)

| Check | Result |
|-------|--------|
| Backend test suite | **202 tests — OK** (`unittest discover`) |
| Frontend tests | **26/26 pass** (`node --test`) |
| TypeScript build | **PASS** (`tsc -b`) |
| Production build | **PASS** (`copy:cesium` + `tsc -b` + `vite build`) |
| Lint | `oxlint` configured |
| Live API smoke | `/ersst/latest`, `/argo`, `/modelgrid/*`, `/glider/*`, `/ctd/*` respond honestly |
| DB schema | `init_db` idempotent; all tables incl. argo/glider/ctd/netcdf |

Repository evidence: `docs/FINAL_ENGINEERING_REPORT.md`, `docs/TIDE_VALIDATION_REPORT.md`,
`docs/ENDPOINTS.md`, `presentation/FINAL_VIVA.md`.

---

## 11. Suggested demo script (5–8 minutes)

1. **0:00–0:45 — One-liner.** "Real ocean data in a 4D twin that decides where
   to observe next, with evidence — and it tells the truth about what it
   doesn't know." Show `/globe` full-screen.
2. **0:45–1:45 — Real-data layer stack.** Toggle Real SST → Isolines → Current
   Vectors → Depth Slice → Gliders. Click an Argo/glider marker → profile.
3. **1:45–2:45 — Anomaly → Forensics.** Open Anomaly Intel, open Forensics,
   show the Event DNA fingerprint.
4. **2:45–4:00 — TIDE.** Open Command Center: explain the formula, show a
   ranked candidate's evidence + verdict, then "What If we measure here?"
   (before/after). Emphasise SIMULATED labelling.
5. **4:00–4:45 — Replay.** Model-only vs TIDE-assisted timeline.
6. **4:45–5:30 — Validation.** TIDE Validation Center + the benchmark table;
   read the "TIDE ties ANOMALY_ONLY" line aloud.
7. **5:30–6:30 — Copilot.** "Ask the copilot to summarize …" — the FAB/⌘K demo;
   it answers from the same grounded engines.
8. **6:30–8:00 — Honesty & limits (this wins trust).** "Data unavailable" path,
   the ingest commands, and the limitations slide: no ground truth, no
   superiority claim, costs are assumptions.

---

## 12. Honest limitations (state them deliberately — they make the demo credible)

- TIDE is a **decision-support heuristic** — implemented, tested, demonstrated;
  **not empirically validated** (no independent ground truth).
- **Observation costs are demonstration assumptions**, not monetary facts.
- **What-if observations are simulations**, derived from existing inputs and
  never written to the observation store.
- Missing data is **never fabricated** — shown as `NOT AVAILABLE` /
  `DATA_UNAVAILABLE`.
- Live real downloads (chlor, model grid, gliders, CTD) need a networked host;
  sandboxed/offline demos show the honest no-data + ingest-command paths.
- Browser rendering/accessibility not independently audited in a live session.

---

## 13. Running the project (for your demo machine)

```bash
# Docker (everything at once)
docker compose up --build
#   frontend http://localhost:8080 · backend http://localhost:8000 · docs /docs

# Local dev
cd backend && .venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev          # http://127.0.0.1:5173
```

Then: click **START TIDE DEMO** → 8-step guide → **seed demo data** (labelled
SIMULATED) → present the walkthrough in §11 → **Reset demo** removes only
simulation rows.

---

## 14. Glossary (for nervous-answer moments)

- **TIDE-Loop** — the observe→validate decision cycle and its scoring formula.
- **Event DNA** — structured fingerprint of an event used as evidence.
- **Provenance tokens** — REAL / HISTORICAL / MODEL_DERIVED / SIMULATED /
  SYNTHETIC; how trust is shown to the user.
- **ERDDAP** — the NOAA data server family this project pulls real grids from.
- **ERSST v5 / VIIRS / HYCOM / Argo** — the real SST, satellite chlorophyll,
  ocean-model and float sources behind the twin.
- **BGC** — biogeochemical sensors (dissolved oxygen, chlorophyll, nitrate)
  carried by some gliders and CTD payloads.
- **OGC WMS/WCS/EDR** — open geospatial standards this platform also serves.

> Final line for the judges:
> **"We built the ocean's dashboards — and the loop that turns them into
> decisions, honestly."**