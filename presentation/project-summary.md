# TidalTwin — Project Summary

Interactive 4D Ocean Model Validation & Decision Intelligence Platform · Smart India Hackathon

---

## 1. What It Is

TidalTwin is **not another ocean viewer**. It is a validation platform:
for every monitored coast it puts the decisions **MODEL | OBSERVED | DEVIATION**
side by side, scores how confident we are in both the observation stream and the
model, flags **model–observation disagreement**, explains *why* in plain
language, and pushes a decision (safety advisory, alert, briefing) to a coastal
command center. The 3D ocean globe is the interface — the product is
data → comparison → anomaly → interpretation → decision.

## 2. Features (what it does)

| Module | What it does |
|---|---|
| **Mission Control Dashboard** | Live status of the whole ocean: health ring, energy gauges, region telemetry, Ocean Situation strip |
| **Model Validation Workspace** | MODEL \| OBSERVED \| DEVIATION per field + plain-language "why" panel + forecast-vs-reality verification charts |
| **Explainable Confidence Engine** | Observation confidence (0–100) with a **why-82%?** weighted component breakdown (age, coverage, sampling, agreement) + model trust + HIGH DISAGREEMENT flags |
| **Model Skill Score** | Honest per-variable forecast verification — MAE / RMSE / bias / skill-vs-climatology per region |
| **Ocean Event Detection** | Anomalies upgraded to **named phenomena** — marine heatwave, cold-water anomaly, rapid temp change, strong-current, coastal flooding risk, model mismatch — each with intensity + start→peak→now evolution + confidence |
| **What-If Simulator** | Wind slider → clearly-labelled illustrative projection of wave height, SST & hazard band (*"what could happen"*) |
| **Data Provenance** | Every value traceable: source, dataset, observation time, model-run id, QC + interpolation processing |
| **3D Digital Twin Globe** | Interactive 3D ocean with labels, heat, waves, currents + live storm track |
| **4D Event Replay** | Scrub 48h observation → 24h projection, re-coloured as Observed \| Model \| Difference with event flags |
| **AI Surveillance** | Anomaly detection (Isolation Forest + z-score) with severity + confidence scores |
| **AI Forecasting** | 12-hour predictions for temperature & waves, with in-system verification metrics (MAE; not independently validated) |
| **Safety Center** | Per-coast SAFE/CAUTION/DANGER advisories, safe sailing window, SMS/WhatsApp + 6-language voice bulletins, live WebSocket feed |
| **National Risk Map & Report** | One-screen command view + composite risk index ranking + executive summary + CSV export |
| **Ocean AI Assistant** | Natural-language Q&A: safety checks, trends, comparisons, superlatives |
| **Story Mode** | Guided narratives that explain ocean science with live data |
| **PWA + Live Push** | Installable offline shell + 12-second live broadcast channel |
| **Docker Deployment** | One command (`docker compose up --build`) runs the whole platform |

## 3. Architecture

```
┌───────────────┐      ┌───────────────┐      ┌──────────────┐
│   React UI    │─────▶│   FastAPI     │─────▶│  PostgreSQL  │
│  (TypeScript) │  HTTP│  AI Engines   │  SQL │  + PostGIS   │
│    + Cesium   │◀─WS──│ Validation ·  │      │  (spatial)   │
└───────────────┘      │ Safety ·      │      └──────────────┘
                       │ Anomaly ·     │
                       │ Forecast · NLP│
                       └──────┬────────┘
                              │
                     ┌────────▼────────┐
                     │ Open-Meteo API  │  live marine data
                     └─────────────────┘
```

**Decision pipeline:** live data → QC → spatial/temporal matching →
**MODEL–OBSERVATION DIFFERENCE ENGINE** → Uncertainty (confidence breakdown) +
Event classification → 4D replay → 3D globe + Safety/Risk surfaces → operational
decision (advisory, alert, report, scenario).

## 4. Tech Stack

**Frontend:** React 19 · TypeScript · Vite · Cesium (3D globe) · Framer Motion ·
Recharts · lucide-react · PWA (manifest + service worker)

**Backend:** Python 3.12 · FastAPI · SQLAlchemy 2 · Pydantic · Uvicorn ·
WebSocket live broadcast

**Database:** PostgreSQL 16 · PostGIS 3 (geospatial)

**AI/ML:** scikit-learn (Isolation Forest) · NumPy (z-score stats, difference
engine) · Rule-based NLP · Trend forecasting · Model-validation confidence

**Data Source:** Open-Meteo Marine API (free, no API key needed)

**Deployment:** Docker + docker-compose (nginx frontend, FastAPI backend,
PostGIS database)

## 5. Demo Highlights (system outputs on the reference dataset)

- 8 Indian coastal regions monitored and compared against observations.
- **768 observations** in the reference dataset (760 real + 8 labelled simulated).
- Detected **marine heatwave at Goa** at **0.91 event confidence** (the
  demonstration anomaly is reproducible via `python -m scripts.simulate_anomaly`).
- Difference Engine: model–observation deviation reported per coast, explained
  with a possible cause and confidence.
- Observation confidence engine: **heuristic 0–100 score** with component
  breakdown; disagreement flags raised.
- 4D Event Replay: re-colour the globe `Observed → Model → Difference`.
- Forecast verification: **in-system** MAE/bias metrics (not independently
  validated); National Risk Index fully transparent.

## 6. How to Extend (future roadmap)

- **More regions:** point the twin at any coastline by adding locations.
- **More sensors:** incorporate buoy networks, satellite SST, tide gauges.
- **Harder AI:** LSTMs / transformers for multi-day ensemble forecasting.
- **Real alerting:** SMS/WhatsApp advisories to fishing communities.
- **Coral & biodiversity layer:** tracking reef stress from SST anomalies.
- **Multi-language assistant:** Hindi + regional languages via NLP.

## 7. Bigger Role (why it matters)

Ocean climate risk is a national challenge: food security (fisheries), coastal
safety (storms), and biodiversity (reefs). TidalTwin shows that with
**public data, open-source AI, and good design**, ordinary citizens and small
governments can have serious ocean intelligence today.

---

## 8. Final Abstract

Ocean data is multidimensional, dynamic and heterogeneous, and most workflows
answer *what, where, when* and help with *why*. The harder decision is **where to
observe next, and why**. TidalTwin is a 4D ocean digital twin — latitude,
longitude, depth and time — that compares model output against observations,
detects anomalies, investigates events through a Forensics engine, and encodes
them as structured Event DNA fingerprints. Its core is **TIDE-Loop** (Trust-aware
Information for Decision and Exploration), which prioritises candidate
observations using decision impact, uncertainty, data gaps, anomaly persistence
and a normalised observation cost, attaching traceable evidence, a confidence
value and cautious verdicts such as `LIKELY_MODEL_ISSUE` or
`INSUFFICIENT_EVIDENCE`. The workflow supports evidence-aware what-if simulation
with strict isolation (a virtual observation is never stored as real), a two-mode
Decision Replay, and a reproducible benchmark. In the reference run (768
observations, 3 events, budget 1, seed 42), **TIDE ties ANOMALY_ONLY** and no
superiority is claimed. The system is implemented, tested (96/96 backend tests)
and demonstrated, but **not scientifically validated**: independent ground truth
is unavailable, so false-alarm and missed-event rates remain future work.

## 9. Final Objectives

1. Build a multidimensional 4D ocean digital twin with honest data-status labels.
2. Detect and investigate ocean anomalies (Anomaly Radar + Forensics).
3. Represent events with structured Event DNA fingerprints.
4. Prioritise the next observation with the TIDE-Loop, evidence and cautious
   verdicts.
5. Provide evidence-aware what-if decision support with strict simulation
   isolation.
6. Provide reproducible replay and benchmark validation mechanisms.

## 10. Final Methodology

```
DATA → 4D DIGITAL TWIN → ANOMALY DETECTION → FORENSICS → EVENT DNA
     → TIDE ANALYSIS → OBSERVATION PRIORITIZATION → WHAT-IF
     → DECISION REPLAY → VALIDATION
```

## 11. Final Conclusion

TidalTwin integrates observation, detection, investigation, understanding,
prioritisation, simulation, decision and validation into one closed,
evidence-aware loop. Its contribution is decision-aware observation
prioritisation with explicit trust boundaries and reproducibility. TIDE is
**implemented, tested and demonstrated** as a decision-support heuristic — **not
scientifically proven, not optimal, and not a guarantee of better decisions**;
broader empirical validation is future work.