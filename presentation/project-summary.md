# OceanVerse AI — Project Summary

AI-Powered Ocean Digital Twin & Decision Intelligence Platform · Smart India Hackathon

---

## 1. What It Is

OceanVerse AI builds a **real-time digital copy of the ocean** from public
sensor data, then applies **AI** to detect danger, forecast the future, answer
questions, and generate executive-grade reports. It is a complete
"data-in → decisions-out" ocean intelligence platform.

## 2. Features (what it does)

| Module | What it does |
|---|---|
| **Mission Control Dashboard** | Live status of the whole ocean: health ring, energy gauges, region telemetry, live feed |
| **3D Digital Twin Globe** | Interactive 3D ocean with atmosphere, clickable region markers, data layers |
| **AI Surveillance** | Anomaly detection (Isolation Forest + z-score) with severity + confidence scores |
| **AI Forecasting** | 12-hour predictions for temperature & waves, verified against reality (MAE) |
| **Ocean AI Assistant** | Natural-language Q&A: safety checks, trends, comparisons, superlatives |
| **Story Mode** | Guided narratives that explain ocean science with live data |
| **Time Explorer** | Scrub through recent history; watch forecasts track reality |
| **National Risk Report** | Composite risk index ranking for all regions + executive summary + CSV export |
| **Docker Deployment** | One command (`docker compose up --build`) runs the whole platform |

## 3. Architecture

```
┌───────────────┐      ┌───────────────┐      ┌──────────────┐
│   React UI    │─────▶│   FastAPI     │─────▶│  PostgreSQL  │
│  (TypeScript) │  HTTP│   (Python)    │  SQL │  + PostGIS   │
│  + Three.js   │      │  AI Engines   │      │  (spatial)   │
└───────────────┘      └──────┬────────┘      └──────────────┘
                              │
                     ┌────────▼────────┐
                     │ Open-Meteo API  │  live marine data
                     └─────────────────┘
```

## 4. Tech Stack

**Frontend:** React 19 · TypeScript · Vite · Three.js (@react-three/fiber) ·
Framer Motion · Recharts · lucide-react

**Backend:** Python 3.12 · FastAPI · SQLAlchemy 2 · Pydantic · Uvicorn

**Database:** PostgreSQL 16 · PostGIS 3 (geospatial)

**AI/ML:** scikit-learn (Isolation Forest) · NumPy (z-score stats) ·
Rule-based NLP · Trend forecasting

**Data Source:** Open-Meteo Marine API (free, no API key needed)

**Deployment:** Docker + docker-compose (nginx frontend, FastAPI backend,
PostGIS database)

## 5. Demo Highlights (proof the AI works)

- 8 Indian coastal regions monitored in real time.
- 384+ real observations ingested from Open-Meteo.
- Live-detected **marine heatwave at Goa** at **85% confidence** (reproducible
  via `python -m scripts.simulate_anomaly`).
- Forecast verification: mean absolute error ~0.1–0.6°C across regions.
- National Risk Index ranks Goa #1 (ELEVATED) with full transparency.

## 6. How to Extend (future roadmap)

- **More regions:** point the twin at any coastline by adding locations.
- **More sensors:** incorporate buoy networks, satellite SST, tide gauges.
- **Harder AI:** LSTMs / transformers for multi-day ensemble forecasting.
- **Real alerting:** SMS/WhatsApp advisories to fishing communities.
- **Coral & biodiversity layer:** tracking reef stress from SST anomalies.
- **Multi-language assistant:** Hindi + regional languages via NLP.

## 7. Bigger Role (why it matters)

Ocean climate risk is a national challenge: food security (fisheries), coastal
safety (storms), and biodiversity (reefs). OceanVerse AI shows that with
**public data, open-source AI, and good design**, ordinary citizens and small
governments can have world-class ocean intelligence today.