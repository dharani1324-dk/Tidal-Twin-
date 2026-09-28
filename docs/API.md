# OceanVerse API reference

Local API base URL: `http://127.0.0.1:8000`. Interactive documentation is at
`/docs`, `/redoc`, and `/openapi.json`. See [ENDPOINTS.md](ENDPOINTS.md) for the
route inventory.

## Response conventions

Health and demonstration endpoints return their payload directly. Other feature
routers return feature-specific JSON documented in OpenAPI.

| Status | Meaning |
|---|---|
| 200 | Request succeeded, including a valid empty result |
| 404 | Requested resource does not exist |
| 405 | Method is not supported for the route |
| 422 | Request parameters failed validation |
| 500 | Unexpected server error |

## Main route groups

- `/api/v1/health` — service and data-source health
- `/api/v1/ocean/*` — ocean observations and environmental data
- `/api/v1/anomalies/*` — detected ocean events
- `/api/v1/twin/*` — digital-twin comparisons and scenarios
- `/api/v1/forensics/*` — event evidence and fingerprints
- `/api/v1/data-layers/*` — source coverage and data quality
- `/api/v1/demo/*` — demo status, seed, and reset
- `/api/v1/assistant/*` — Ocean Copilot

Exact paths and methods are defined by the running OpenAPI schema.
