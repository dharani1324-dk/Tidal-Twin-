# 🌊 OceanVerse AI

**An AI-Powered Ocean Digital Twin & Decision Intelligence Platform**

Built for the Smart India Hackathon. This project creates a virtual (digital) copy of the real ocean using public data, and adds AI to help people make smart decisions about the sea.

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
│       ├── utils/            Helper functions
│       └── assets/           Images, logos, icons
│
├── database/
│   │   The data store. PostgreSQL + PostGIS (geographic data).
│   └── init/                 SQL scripts that set up the database first time.
│
├── docker/
│   │   Instructions to package the app into "containers" so it runs
│   │   anywhere. Like putting the app in a box with everything it needs.
│
├── deployment/
│       How to put the finished app on the internet for the world to see.
│
├── docs/
│       Detailed documentation — explains every part of the project.
│
└── presentation/
        Slides, posters, demo videos for the SIH final presentation.
```

---

## 🧠 The Big Idea (One Sentence)

> OceanVerse AI turns publicly available ocean data into a beautiful, interactive 3D "digital twin" of the sea, and uses AI to help answer questions and make decisions that protect the ocean and the people who depend on it.

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
