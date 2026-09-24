# TidalTwin — Complete Project Report
### Smart India Hackathon 2026 · SIH26067 · Ocean Digital Twin / Decision Intelligence

**Location:** `C:\Project 2.0` (monorepo: `backend/`, `frontend/`, `ai-models/`, `docs/`)
**State at writing:** all code committed, working tree clean, all quality gates green.
**One honest caveat, stated up front:** live GFW data ingest is externally blocked by the
network egress filter (TLS handshake EOF on both GFW hosts, verified 3 ways). Every value
in the live corpus is therefore *simulated or derived* — clearly and permanently tagged as
such, provenance-linked, and **never** presented as observed. Nothing is faked or hidden.

---

## 1. What the product is — in one paragraph

TidalTwin is an **ocean digital twin and decision-intelligence platform** for Indian
coastal waters. It ingests AIS vessel telemetry, converts it into **derived surface
currents**, and surfaces the result through a photo-real 3D globe plus a full
intelligence layer (threat chains, anomaly forensics, ecology, safety advisories,
report generation). Its founding contract — visible everywhere in the UI — is
**honesty**: the system owns that its corpus is simulated, labels every derived value
with its method and provenance, and shows "coverage gaps / not observed" instead of
painting a confident guess. A judge can trust what they read because the system is
explicit about what it does not know.

## 2. Architecture

```
┌──────────────────────────  FRONTEND  ──────────────────────────┐
│ React 18 + TypeScript · Vite · CesiumJS globe · self-contained │
│ design system (deep-ocean tokens: abyss/glass/cyan-telemetry)  │
│ Pages: Dashboard, OceanVision globe, RiskMap, DigitalTwin,     │
│   Intelligence, Forensics, CoastalIntel, Safety, Monitoring,   │
│   Stories, Reports, AnomalyIntel, ScenarioLab, Validate,       │
│   Assistant (fab)                                              │
│ 3D globe: real Cesium (CesiumGlobe.tsx), TransectHUD overlay,  │
│   AssistantFab contextual copilot                             │
├──────────────────────────  BACKEND  ───────────────────────────┤
│ FastAPI (+Uvicorn) · SQLAlchemy+Postgres/PostGIS · WebSockets  │
│   live monitoring broadcasts · pydantic schemas (strict)       │
│ Routers on disk (verbatim names):                              │
│   apex, assistant, coastal, currents, edr, intelligence, lens, │
│   monitoring, ocean, reports, safety, status, stories, twin,   │
│   validation                                                   │
│ Live endpoints (TestClient smoke verified):                    │
│   /api/v1/health · /api/v1/currents/derived (+summary, lens) · │
│   /api/v1/edr/collections (+position, catalog) ·               │
│   /api/v1/intelligence/* (autopsy, causal, whatif, timeline,   │
│   threat-chain, coverage, uncertainty, events, health, ...) ·  │
│   /api/v1/twin/* (situation, confidence, explain, events,      │
│   sources, profile, compare, transect, disagreement) ·         │
│   /api/v1/ocean/locations · /api/v1/coastal/* (slr, spill,     │
│   coral, fisheries, impact, beach) · /api/v1/safety/* (storm,  │
│   advisory, trust, timeseries, ws/live) · /api/v1/validation/* │
│   · /api/v1/reports/* (summary, csv, index) · /api/v1/stories  │
│   · /api/v1/assistant/capabilities, ask, multimodal            │
├──────────────────────────  DATA  ──────────────────────────────┤
│ PostgreSQL 16 + PostGIS (lattice + geometry), host `127.0.0.1` │
│ Honest ledger (live SQL, verbatim):                            │
│   ais_tracks:           SIMULATED, provenance 2 · n=40        │
│   derived_currents:     DERIVED, provenance 5 · n=40          │
│   (zero OBSERVED rows — nothing masquerades as real)          │
├──────────────────────────  AI  ────────────────────────────────┤
│ Deterministic physics + provenance-driven modules: current     │
│ derivation (median binning, uncertainty), depth/thermocline,   │
│ coastal SLR/spill/coral modelling, twin compare/confidence,    │
│ threat-chain & causal intelligence, what-if and counterfactual,│
│ forensics autopsy, chart/Cesium visual reasoning. Real GFW     │
│ ingestion coded and token-validated but egress-blocked (see 4).│
└────────────────────────────────────────────────────────────────┘
```

## 3. The build story (4 phases)

- **Phase 0 — Approach & honesty contract.** Client-owner approved 4 decisions:
  no fabrication, provenance on every row, honest tags, gaps reported as gaps.
- **Phase 1 — AIS as sensors → derived surface currents.** Built the honest corpus
  (40 SIMULATED tracks + 40 DERIVED currents, all provenance-linked), the GFW ingester
  (live path coded, token validated), and the derivation engine (`ai-models/current_derivation.py`).
- **Phase 2 — Trust & fog lens.** `/api/v1/currents/lens` — how much of the window is
  real data, with what uncertainty; confidence/depth-surfaced honestly.
- **Phase 3 — OGC EDR tier.** `/api/v1/edr/*` — OGC Environmental Data Retrieval
  collection/position endpoints with an explicit honesty note in the catalogue.

## 4. The real data wire (the one thing we cannot do from this network)

- GFW hosts `auth.` + `api.globalfishingwatch.org` **connect at TCP but the TLS handshake
  is killed by the egress filter** (`UNEXPECTED_EOF` / curl(35), reproduced via Python
  ssl, .NET SslStream, and curl — three independent methods).
- The GFW token in `backend/.env` is **valid** (offline RS256 verification passed:
  signature, iss=aud=gfw, exp 2036). It is gitignored and never echoed.
- When egress reopens, the already-written live path is one flag (`--live`) from working;
  until then the honest `SIMULATED`/`DERIVED` corpus stands in with full provenance.

## 5. What makes it special (why it is not another AI dashboard)

1. **Honesty as the headline feature, not a footnote.** The system tells you what it does
   not know. Coverage gaps render as gaps; simulated data is permanently tagged
   `SIMULATED`/`DERIVED` with provenance links; nothing is labelled `OBSERVED`.
2. **A 3D globe that is genuinely an ocean, not a demo prop.** Cesium globe with a
   full visual identity (bathymetric depth zones, sounding numerals, telemetry accents)
   — the chart-paper look of the product is *not* the default AI glassmorphism.
3. **A whole decision-intelligence layer over the twin.** Not just "dashboard panels":
   threat chains, causal analysis, what-if scenarios, confidence attribution, forensics
   autopsies, ecological/coastal advisory, and a live assistant — surfaced through a
   clean API a real coastal district could integrate.
4. **Provenance engineering.** Every record is traceable end-to-end (method tag →
   provenance batch → source), which is what makes the honesty claim *testable* — a
   judge can run the SQL ledger and see there is no masquerade.

## 6. Quality evidence (all real, verified this session)

- `py_compile` over all routers/models/main: **PASS**.
- FastAPI live boot via TestClient: **200** on the full Phase-1/2/3 set and the wider
  surface (100+ checks; 405/422/404 are correct semantics — POST-only, param-required,
  or templated paths — not defects).
- Frontend gates on real stdin-free runner: **tsc PASS · oxlint PASS · vite build PASS**.
- Git: clean tree, all work committed.

## 7. Honest limitations & what it would take to go live

- **Live GFW feed:** blocked by network egress (not code). Fix = network admin reopens
  TLS egress to the two GFW hosts; the coded live ingest is one flag away.
- **Simulated corpus:** all 40+40 rows are honest SIMULATED/DERIVED with provenance;
  real-world validation requires the egress fix and a real watch window.
- **Production hardening:** auth, rate-limit, and observability exist in-monorepo as
  modules but deeper deployment hardening (HTTPS terms, multi-tenant authz) is future
  work — the product is a working, honest twin, not a "certified deployment".

---

*TidalTwin — built to be believed. Every number you read is either real or
explicitly, permanently tagged as simulated/derived. That is the point.*
