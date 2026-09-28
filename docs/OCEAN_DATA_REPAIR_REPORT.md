# Ocean Data Stability and Live Source Audit

**Audit date:** 2026-09-28  
**Project:** TidalTwin (existing OceanVerse AI workspace)  
**Scope:** Production API checks, current MoES/data adapters, frontend data consumers, validation/build checks.

## Data flow

```text
Provider (INCOIS ERDDAP / RSMC, CMLRE-IndOBIS, NIOT, …)
  -> backend provider adapter and parser (`backend/app/api/moes.py`)
  -> source-specific response (availability, status, checked time, records)
  -> optional normalized adapter (`backend/app/services/moes_normalizer.py`)
  -> `UnifiedOceanRecord/v1` validation (`backend/app/schemas/moes.py`)
  -> versioned `/api/v1/moes/...` route and in-process source cache
  -> typed API client (`frontend/src/api/client.ts`)
  -> page-level fetch/state -> chart, map, dashboard, or Cesium layer
```

The APIs do not all use one response envelope: some return a source payload, some a list, and some an `available/status/error` envelope. Existing consumers depend on these route-specific contracts. ERSST and chlorophyll correctly report unavailable data in a 200 response envelope when no grid has been ingested; the Twin and Data Layers crashes occurred because their consumers treated that envelope as a successful grid and dereferenced missing arrays. Those two consumers now normalize missing arrays to empty arrays and show the unavailable state without inventing values.

## Production source observations

These are point-in-time checks; provider availability and data age can change. A successful catalog/API request means the endpoint responded, not that its observations are current.

| Source / product | Observed state | Meaning |
|---|---|---|
| INCOIS ERDDAP catalog | LIVE; 16 datasets listed | Catalog request succeeded. Some catalog products have old source dates; e.g. AMSRE monthly latest source time was 2011-09-14. |
| INCOIS RSMC HYCOM | LIVE at check; forecast run about 17 hours old | Forecast/model-derived points, not in-situ observations. |
| INCOIS RSMC WW3 waves | STALE; run about 41 hours old | A valid but stale forecast. |
| INCOIS Argo 10-day VAM | STALE; latest valid time about 61 days old | Gridded analysis, not raw float readings. |
| NIOT buoy directory | LIVE; 22 station metadata entries | Station metadata and stated coverage only; no live sensor time series was observed. |
| CMLRE / IndOBIS | LIVE; historical occurrence records returned | Occurrences span historical dates; this is not live abundance or animal tracking. |
| NCCR | No verified public machine endpoint | An official assessment document was found, not a stable data API. |
| NCPOR | No verified public machine endpoint | Portal/dashboard only in this audit. |
| IMD | ACCESS_RESTRICTED | The provider requires network/IP access not available to the deployed service. |
| NCMRWF | No verified public machine endpoint | No stable machine-readable source was verified. |
| IITM | TEMPORARILY_UNAVAILABLE | TLS certificate chain was not trusted. TLS verification remains enabled. |
| NCESS | PORTAL_IN_TRIAL | Portal exists; no stable public API verified. |
| ERSST / chlorophyll grids | UNAVAILABLE | No latest grid readings ingested; API response truthfully reports unavailable. |

Production `/api/v1/health` was reachable and reported database/PostGIS, TIDE, and Copilot available; Cesium was optional/unavailable and ocean data was limited. It reported 384 model-derived records and zero direct measurements, historical records, or satellite-derived records in the shared health snapshot. This is a limitation of populated shared stores, separate from the live provider adapter checks above.

## Repairs and contract checks

- Normalized ocean records now reject out-of-range coordinates, negative depth, non-finite numeric values, and timestamps without an explicit timezone. Accepted timestamps are emitted as UTC ISO-8601 with `Z`.
- IndOBIS `eventDate` is preserved verbatim in `attributes.event_date`. It becomes `observed_at` only when the provider supplies a timezone-qualified timestamp. Year-only, date-only, and date-range values remain imprecise source metadata; no time of day is fabricated.
- ERSST unavailable envelopes are handled safely in Digital Twin and Data Layers. Missing samples/cells and other optional array payloads are guarded, with empty/unavailable states rather than render-time `.filter`/`.map` failures.
- INCOIS ERDDAP TLS uses a trusted CA chain with normal certificate and hostname verification; verification is not disabled.

## Validation evidence

- Backend full suite: 396 passed, 1 skipped in the prior baseline. The current full suite is being rerun with 12 new normalized-record contract cases.
- Frontend tests: 37 passed.
- Frontend production build: passed.
- Frontend lint: exit 0 with existing warnings (state updates from effects, effect dependencies, one type-erasure warning, and fast-refresh export warning).
- Docker Compose could not be started in this environment because Docker Desktop's daemon was unavailable. Production Railway services were reachable during the audit.
- Interactive browser console/visual checks were unavailable; route HTTP and built bundles were checked directly.

## Remaining operational limits

- “Live” currently describes a successful provider request/catalog check. Freshness is product-specific, and provider responses include stale forecast/analysis data. Shared health inventory still has no direct measured observations in the production snapshot.
- Not every MoES institution has a verifiable public machine API. Restricted/private sources must stay unavailable until official access is configured.
- Refresh behavior is distributed across page effects and route-local caches; there is no single shared polling/refresh manager for every ocean product.
- Write routes, including demo seed/reset, do not have application authentication. Demo reset is constrained to labeled demo rows, but public write-route access remains a deployment hardening issue.
- The application has route-specific response contracts. A global response-envelope migration would need a staged API/client compatibility change and is not part of this stability repair.
