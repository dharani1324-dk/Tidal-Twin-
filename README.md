# OceanVerse

OceanVerse is an ocean monitoring and digital-twin application for exploring
observations, detected events, data coverage, coastal scenarios, and source
quality. It combines live provider integrations with clearly labelled model,
historical, and demonstration data.

## Run locally

1. Start PostgreSQL with PostGIS and set the backend environment variables from
   `backend/.env.example`.
2. In `backend`, install `requirements.txt` and run `uvicorn app.main:app --reload`.
3. In `frontend`, run `npm install`, set `VITE_API_URL` to the backend URL, then
   run `npm run dev`.

API docs are available at `http://127.0.0.1:8000/docs`. Deployment instructions
are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Main areas

- Dashboard and ocean event monitoring
- Digital Twin and coastal scenario exploration
- Data layers, source coverage, and quality details
- Event forensics and Ocean Copilot
- Demo data tools with explicit simulation labels

## Project docs

- [API reference](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Known data limitations](docs/SCIENTIFIC_LIMITATIONS.md)
- [Deployment](docs/DEPLOYMENT.md)
