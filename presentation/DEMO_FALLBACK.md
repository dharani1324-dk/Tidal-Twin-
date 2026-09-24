# TidalTwin — Demo Fallback Plan

> What to do when something fails during the live demo. **Never fabricate a live
> demonstration.** If you switch to a screenshot or a recorded output, say so
> explicitly and state the data status.

---

## Universal rules

1. Stay calm and narrate the fallback: "The live service is unavailable; I'll
   show the captured output instead."
2. Label every static image as a **screenshot**, with its **data status**.
3. Prefer the **documented, frozen artifacts** (benchmark JSON, health JSON)
   over memory.
4. Keep the **three-layer explanation** consistent (simple / technical /
   research). Never upgrade a tested claim into a validated one under pressure.

---

## Failure modes and fallbacks

### Internet fails
- **Symptom:** live ingestion can't reach Open-Meteo.
- **Fallback:** use the **already-stored reference dataset** (768 observations:
  760 real + 8 simulated, 3 events). All twin/TIDE/replay/validation features
  still work from stored data.
- **Say:** "Live ingestion is offline; the stored reference dataset is what the
  twin is running on."

### Cesium fails
- **Symptom:** globe blank or slow.
- **Fallback:** switch to the **2D map / non-globe views** (Risk Map, Validation
  Workspace tables) which don't require the globe renderer.
- **Backup:** show screenshot #2/#3 (globe + variables) labelled as a screenshot.
- **Say:** "The 3D renderer failed to initialise; here is the captured globe,
  and the underlying data is available in the table views."

### Backend fails
- **Symptom:** API 5xx or timeouts.
- **Fallback:** restart the service (`uvicorn app.main:app`, wait ~4 s for
  warm-up). If it won't recover, use the **screenshot set** and the frozen
  benchmark/health artifacts.
- **Say:** "I'm restarting the API; meanwhile here is the verified output."

### Copilot fails
- **Symptom:** no answer / error.
- **Fallback:** show the **known grounded questions** and their expected intent:
  - "Why is this observation candidate prioritized?" → `tide`
  - "What evidence supports the current TIDE recommendation?" → `tide`
  - "Where should we sample next?" → `recommend`
  - "Where did this value come from?" → `provenance`
- **Backup:** screenshot #19 (Copilot) with the answer visible.
- **Say:** "The assistant is rule-based and answers from the same engines; here
  is the captured exchange."

### Database fails
- **Symptom:** connection refused, empty responses.
- **Fallback:** restart the DB container (`docker compose up -d db`), wait for
  HEALTHY. If it stays down, use screenshots + artifacts.
- **Say:** "The database container is restarting; the captured figures are from
  the same reference dataset."

### Browser rendering fails
- **Symptom:** layout broken / WebGL issues.
- **Fallback:** try another browser; reduce quality; otherwise use the
  **screenshot set**.
- **Say:** "Rendering is environment-specific; here are the captured views."

---

## Frozen artifacts to keep open

| Artifact | Use |
|----------|-----|
| `docs/benchmark-results/tide-benchmark_20260917T153433Z_budget1_seed42.json` | Exact benchmark numbers (TIDE ties ANOMALY_ONLY) |
| `/api/v1/health`, `/api/v1/demo/status` JSON (saved) | Engineering proof (768 obs, 3 events) |
| `docs/REPRODUCIBILITY.md` | Environment, seed, dataset, expected outputs |
| `docs/RESULTS_AND_LIMITATIONS.md` | Maturity vocabulary and claim boundaries |
| `presentation/SCREENSHOT_CHECKLIST.md` | Which image proves which point |

## Known demo anchors (if all else fails, narrate these)

- **Known event:** `event-0` Marine heatwave at Goa Coast (Panaji), confidence
  **0.91**; also `event-1` model–observation mismatch (0.76) and `event-2` rapid
  temperature change (0.72).
- **Known candidate:** `tide-5-temperature-0-buoy` (Goa).
- **Known benchmark:** budget 1, seed 42 → TIDE = ANOMALY_ONLY = 0.75 / 0.2527.

## What NOT to do

- Don't claim a screenshot is live.
- Don't invent a decision change that wasn't observed.
- Don't say "validated", "proven" or "better" to recover the moment.
- Don't re-run destructive commands (`demo/reset`) mid-demo.
