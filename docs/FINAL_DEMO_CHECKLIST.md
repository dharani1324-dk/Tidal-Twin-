# TidalTwin — Final Demo Checklist

> Live values below were read from the running API on the reference dataset
> (8 locations · 768 observations · 3 detected events). Re-verify them before
> presenting; if the numbers differ, read the new values from the app — never
> present stale numbers as live.

## Before the demo

| # | Check | How to verify |
|---|-------|---------------|
| 1 | Environment configured | `backend/.env` exists (copy of `.env.example`); `DOCS` note: no secrets committed |
| 2 | Database available | health `checks.database.status == "AVAILABLE"` |
| 3 | Ocean data available | health `checks.ocean_data.status == "AVAILABLE"` (reference: 768 observations) |
| 4 | Backend running | `GET /api/health` returns 200 |
| 5 | Frontend running | open <http://localhost:8080> (Docker) or <http://127.0.0.1:5173> (`run.ps1`) |
| 6 | Cesium working | globe renders; without an Ion token it still renders from bundled assets |
| 7 | TIDE working | `GET /api/v1/tide/candidates?variable=temperature` returns 200 |
| 8 | Copilot working | `POST /api/v1/assistant/ask {"question":"..."}` returns 200 |
| 9 | Demo data available | `GET /api/v1/demo/status` → `demo_data_present: true`, `detected_events: 3` |
| 10 | Benchmark data available | `GET /api/v1/tide/benchmarks?budget=1` returns 200; artifact in `docs/benchmark-results/` |

One-shot warm-up before the audience arrives (see `docs/DEPLOYMENT.md`):

```bash
curl -X POST http://localhost:8000/api/v1/demo/seed
curl http://localhost:8000/api/v1/demo/status
curl "http://localhost:8000/api/v1/tide/candidates?variable=temperature"
```

## During the demo

Click **START TIDE DEMO** and follow the 8-step guide; the underlying journey is:

| Step | Screen | What to point out |
|------|--------|-------------------|
| 1 | 4D Ocean Twin | live Cesium globe, observation status labels |
| 2 | Anomaly Radar | the detected event(s) — reference: 3 events at Goa |
| 3 | Ocean Forensics | why the anomaly occurred, region context |
| 4 | Event DNA | fingerprint built from available signals |
| 5 | TIDE | uncertainty, data gaps, disagreement (unavailable values shown as such) |
| 6 | TIDE candidate + evidence | why this location, evidence chain |
| 7 | Confidence vs uncertainty | explicitly different concepts |
| 8 | Verdict | cautious `LIKELY_*` / `INSUFFICIENT_EVIDENCE` vocabulary |
| 9 | What If We Measure Here? | `SIMULATED OBSERVATION — DEMONSTRATION ONLY`, before/after, DECISION CHANGED/UNCHANGED |
| 10 | Decision Replay | model-only vs TIDE-assisted, read-only |
| 11 | Validation / benchmarking | tested, **not** empirically validated; ground truth unavailable |
| 12 | Ocean Copilot | ask an evidence-grounded question |

Then show **RESET DEMO** (deletes only simulated rows) and confirm real
observations are untouched.

## Backup (if the live stack fails)

- **Screenshots may only be shown as screenshots.** Never claim a screenshot is
  live data. State plainly: *"This is a captured screenshot of the running
  system, not a live connection."*
- **Known demonstration event:** `event-0` — Goa Coast (Panaji), **Marine
  heatwave**, confidence **0.91**, 4/4 practical criteria (Event DNA, TIDE
  candidates, evidence, timeline).
- **Known candidate:** `tide-5-temperature-0-buoy` — Goa Coast (Panaji),
  `observation_value ≈ 0.7457`, method **BUOY**, status **MODEL_DERIVED**.
- **Known Copilot questions:** "Is TIDE scientifically validated?", "Where
  should we sample next?", "Why is Goa flagged?".
- **Known events:** `event-0` Marine heatwave (0.91), `event-1`
  Model–observation mismatch (0.76), `event-2` Rapid temperature change (0.72).

## Honesty reminders (do not skip)

- Say **implemented / tested / demonstrated** — never "validated" or
  "accurate".
- Say **MODEL_DERIVED** for TIDE candidates, **SIMULATED** for what-if readings.
- Say **GROUND TRUTH UNAVAILABLE** for false alarms / missed events.
- "Observation Value" is a **decision-support heuristic**, not a probability.
