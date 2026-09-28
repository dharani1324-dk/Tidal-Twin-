# API endpoint groups

The live OpenAPI schema at `/openapi.json` is the authoritative route list.
Interactive docs are available at `/docs`.

- `/api/v1/health` — backend, database, and ocean-data health
- `/api/v1/ocean/*` — locations and observations
- `/api/v1/currents/*`, `/api/v1/edr/*` — derived currents and environmental
  data retrieval
- `/api/v1/apex/*`, `/api/v1/coastal/*` — domain analysis and recommendations
- `/api/v1/anomalies/*`, `/api/v1/twin/*` — event detection and digital-twin
  comparisons
- `/api/v1/forensics/*`, `/api/v1/intelligence/*` — event evidence and analysis
- `/api/v1/data-layers/*`, `/api/v1/validation/*` — source coverage and quality
- `/api/v1/microplastics/*` — archived sample and surface analysis
- `/api/v1/monitoring/*`, `/api/v1/safety/*` — alerts and coastal safety
- `/api/v1/demo/*` — labelled demo data status, seed, and reset
- `/api/v1/assistant/*` — Ocean Copilot
