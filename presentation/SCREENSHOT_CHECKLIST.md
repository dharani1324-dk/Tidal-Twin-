# TidalTwin — Screenshot Checklist

> Capture these before the presentation as a fallback and for the report.
> **Never present a screenshot as a live result.** Label static images as
> screenshots and state the data status shown.

**Data-status vocabulary:** `REAL` · `HISTORICAL` · `SIMULATED` · `SYNTHETIC` ·
`MODEL_DERIVED` · `DEMO`.

Legend for "Mode": **LIVE** (backend running), **DEMO** (seeded reference
dataset), **SIMULATED** (virtual/what-if), **STATIC** (screenshot of any of the
above).

---

| # | Screenshot | Route / Module | Purpose | What must be visible | Data status | Mode |
|---|------------|----------------|---------|----------------------|-------------|------|
| 1 | Main dashboard | `/` Mission Control | First impression | Health ring, Ocean Situation strip, region telemetry | mixed REAL/MODEL_DERIVED | LIVE |
| 2 | 4D Cesium globe | `/globe` Digital Twin | Show 4D twin | Globe, location markers, variable selector, time control | REAL + MODEL_DERIVED | LIVE |
| 3 | Ocean variables | `/globe` variable panel | Variable breadth | The ten TIDE variables listed with availability | mixed | LIVE |
| 4 | Anomaly Radar | `/anomalies` | Detection | Radar scan result, anomaly severity/confidence, region | MODEL_DERIVED / DEMO | LIVE |
| 5 | Event Timeline | event view (Forensics/Anomaly) | Event evolution | start → peak → now, timestamps, intensity | DEMO | LIVE |
| 6 | Forensics | `/forensics` | Investigation | What changed, when, depth, contributing factors, uncertainty | DEMO | LIVE |
| 7 | Event DNA | Forensics → Event DNA | Structured fingerprint | Fingerprint dimensions + tags for the selected event | DEMO | LIVE |
| 8 | TIDE Command Center | `/tide` | Core innovation entry | Candidate list, ranking, summary | MODEL_DERIVED (candidates) | LIVE |
| 9 | TIDE candidate ranking | `/tide` | Prioritisation | Ranked candidates with observation value | MODEL_DERIVED | LIVE |
| 10 | Why This Location? | `/tide` candidate → **WHY THIS LOCATION?** | Explainability | Text grounded in the candidate's evidence | MODEL_DERIVED | LIVE |
| 11 | Evidence panel | `/tide` candidate | Trust/evidence | Evidence items with type, strength, description | MODEL_DERIVED | LIVE |
| 12 | Confidence panel | `/tide` candidate | Confidence ≠ uncertainty | Confidence value + component breakdown | MODEL_DERIVED | LIVE |
| 13 | Verdict | `/tide` candidate | Cautious classification | Verdict label, alternative explanation, recommended observation | MODEL_DERIVED | LIVE |
| 14 | What If We Measure Here? | `/tide` candidate → **WHAT IF WE MEASURE HERE?** | Simulation entry | The label **SIMULATED OBSERVATION — DEMONSTRATION ONLY** | SIMULATED | SIMULATED |
| 15 | Before/After uncertainty | What-If result | Effect of measurement | Before vs after uncertainty/risk and decision state | SIMULATED | SIMULATED |
| 16 | Decision Replay | `/tide/replay` | Process inspection | MODEL-ONLY vs TIDE-ASSISTED, step stages, OBSERVATION divergence | SIMULATED (outcomes) | LIVE |
| 17 | Validation | `/tide/validation` | Framework | Sensitivity + edge-case consistency, labels visible | ALGORITHM CONSISTENCY TESTING | LIVE |
| 18 | Benchmark results | `/tide/validation` / artifact | Reference results | Six strategies + the "TIDE ties ANOMALY_ONLY" note | DEMO | LIVE |
| 19 | Ocean Copilot | `/assistant` | NL interface | A grounded Q&A (e.g. "Why is this candidate prioritized?") with citations | mixed | LIVE |
| 20 | System health / demo status | `/api/v1/health`, `/api/v1/demo/status`, Docker | Engineering proof | Healthy services, 768 obs (760 real + 8 simulated), 3 events | REAL | LIVE |

---

## Capture notes

- Use a consistent window size and browser zoom; hide personal bookmarks.
- Include the data-status tag in any figure caption.
- For #14 and #15, ensure the SIMULATED label is readable in the image.
- For #18, use the frozen artifact
  `docs/benchmark-results/tide-benchmark_20260917T153433Z_budget1_seed42.json`
  so the numbers match exactly.
- For #20, capture both the health JSON and the Compose "Healthy" states.

## Caption template

```
<Figure title> — <route>. Data status: <REAL|HISTORICAL|SIMULATED|SYNTHETIC|MODEL_DERIVED>.
Captured from the running system on <date>. Source: TidalTwin.
```
