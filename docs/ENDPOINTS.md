# Live API Endpoints (smoke-tested)

| Method | Path | Router | Notes |
|---|---|---|---|
| GET | `/api/v1/health` | status | boot/liveness |
| GET | `/api/v1/currents/derived` | currents | derived surface currents (honest corpus) |
| GET | `/api/v1/currents/summary` | currents | coverage + provenance summary |
| GET | `/api/v1/currents/lens` | lens | Phase 2 trust/fog lens over derived corpus |
| GET | `/api/v1/edr/collections` | edr | Phase 3 OGC EDR catalogue |
| GET | `/api/v1/edr/position` | edr | OGC EDR position query |

All routers registered in `app/main.py`; live boot + TestClient smoke PASS for
the list above. GFW live fetch: **blocked by network egress** (see JUDGE_BRIEF).
