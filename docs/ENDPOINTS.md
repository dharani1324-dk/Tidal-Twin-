# TidalTwin — Served endpoints (verbatim from live smoke, no invented paths)

`GET` on the headline Phase routes, all HTTP 200 with real payloads:

| Phase | Path (verbatim from `TestClient` smoke) | Returns |
|---|---|---|
| 0 | `/api/v1/health` | service/status dict |
| 1 | `/api/v1/currents/derived` | 40 DERIVED vectors, provenance-linked |
| 1 | `/api/v1/currents/derived/summary` | coverage + cell counts (7-key dict) |
| 2 | `/api/v1/currents/lens` | trust/fog lens (grid, uncertainty, method + provenance breakdowns) |
| 3 | `/api/v1/edr/collections` | OGC EDR collections (2) + honesty note |

Broader `/api` surface (all registered on `app`; smoke: HTTP 200 unless noted —
`405` = POST-only route GET'd, `422` = required params omitted, `404` = templated
path needing a real `{location_id}` — all *correct* HTTP semantics, not defects):

- `/api/v1/apex/*` — adaptive, argo, carbon, light-pollution, recommendations,
  remote-sensing (200)
- `/api/v1/assistant/*` — capabilities; ask / multimodal are POST
- `/api/v1/coastal/*` — beach, coral, fisheries, impact, slr (200); spill POST
- `/api/v1/comparison[/{location_id}]` — comparison report
- `/api/v1/db-status` — DB health
- `/api/v1/intelligence/*` — coverage, events, health, impact, priority,
  relationships, threat-chain, uncertainty (200); autopsy/causal/future/
  investigate/thermocline/timeline need params; counterfactual/whatif POST
- `/api/v1/monitoring/*` — alerts, forecast (200); scan POST
- `/api/v1/ocean/*` — locations (8) (200); observations need `{location_id}`
- `/api/v1/reports/*` — index, summary (200)
- `/api/v1/safety/*` — advisory, storm, timeseries, trust (200); ws/live WS
- `/api/v1/stories` — 200
- `/api/v1/twin/*` — anomalies, disagreement, events, situation, sources (200);
  compare/confidence/explain/profile/transect need params
- `/api/v1/tide/*` — candidates, rankings, uncertainty, data-gaps,
  disagreements, evidence, verdict, events, explanation, decision (200);
  virtual-observation POST
- `/api/v1/validation/*` — confidence, difference, events, provenance,
  situation, skill (200); scenario POST

Live smoke + ledger probe:
`backend/scripts/probe_authoritative.py`
