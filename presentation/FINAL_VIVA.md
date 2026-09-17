# TidalTwin — Final Viva Preparation

> 50 technical questions with factual answers grounded in the implementation,
> plus a **TOUGH QUESTIONS** section. If a fact is not supported, the answer says
> so. Canonical numbers: 768 observations (760 real + 8 simulated), 3 events,
> backend 96/96 tests, reference benchmark **TIDE ties ANOMALY_ONLY**.

---

## Basic

**1. What is the project?**
A 4D ocean digital twin and decision-support platform. It compares model output
against observations across space, depth and time, detects and investigates ocean
events, and prioritises the next observation through the TIDE-Loop.

**2. What problem does it solve?**
The next-observation decision: given limited observation capacity, *where should
we observe next, and why?* — using uncertainty, data gaps, persistence, decision
impact and cost.

**3. Why is it called a 4D Digital Twin?**
Because it represents ocean state across four dimensions — latitude, longitude,
depth and time — and maintains a live comparison of model versus observation.

**4. What are the four dimensions?**
Latitude, longitude, depth (subsurface/transects) and time.

**5. What is TIDE?**
**Trust-aware Information for Decision and Exploration** — a decision-support
heuristic that scores candidate observations and attaches evidence, confidence
and a cautious verdict.

---

## Architecture

**6. Explain the system architecture.**
React/TypeScript/Cesium frontend → FastAPI backend → PostgreSQL + PostGIS.
The backend holds ingestion, the twin comparison, anomaly/forensics/DNA, TIDE,
what-if, replay, validation/benchmark, and the Copilot.

**7. How does the frontend communicate with the backend?**
Over REST/HTTP (JSON) with a WebSocket broadcast channel for live updates.

**8. What database is used?**
PostgreSQL 16 with the PostGIS 3.4 extension.

**9. Why PostGIS?**
Locations are geographic polygons/geometry; PostGIS allows spatial storage and
queries (geometries, centroids, spatial relationships) instead of ad-hoc
coordinate math.

**10. Why Cesium?**
CesiumJS provides a mature 3D globe with time-dynamic data and terrain-ready
rendering, which suits a geospatial digital twin. It is integrated by copying
Cesium assets and loading them via a dynamic `import('cesium')` with
`CESIUM_BASE_URL='/cesium/'` (not via a bundler plugin).

---

## Ocean Intelligence

**11. What is anomaly detection?**
Flagging conditions that deviate from expected behaviour. Here it combines
z-score statistics with an Isolation Forest model, producing severity and
confidence.

**12. What is ocean forensics?**
An investigation step: for an event it reports what changed, when, at what
depth, the uncertainty, possible contributing factors, and the evidence.

**13. What is Event DNA?**
A structured event fingerprint (dimensions such as temperature anomaly,
salinity, oxygen, chlorophyll, nutrients, wave height, current speed, duration,
peak intensity, plus tags and a label). It provides context to downstream
decision support; it does not re-derive the event or prove a cause.

**14. What is an observation gap?**
The absence or sparsity/staleness of coverage for a variable at a location/depth
— expressed as gap evidence such as depth gap, temporal gap, sparse or missing
observation.

**15. What is uncertainty?**
A normalised 0..1 measure of how unsure the estimate for a variable currently is.
It is distinct from confidence and from observation value.

---

## TIDE

**16. Explain the TIDE formula.**
`observation_value = decision_impact × uncertainty × data_gap ×
anomaly_persistence ÷ observation_cost`, with a floor on the denominator
(`max(cost, 0.05)`). All inputs are clamped to 0..1; non-finite values fall back
safely.

**17. Why is observation cost included?**
Two candidates may be equally informative but differ in cost; dividing by cost
keeps prioritisation cost-aware. Cost is a **normalised demonstration
assumption**, not a monetary figure.

**18. How is uncertainty normalised?**
Inputs pass through a `unit()` clamp that returns a finite value in `[0,1]`, or
the default for non-numeric/NaN/±Inf inputs.

**19. What is decision impact?**
A normalised 0..1 estimate of how much the decision depends on the variable —
higher impact means a wrong value matters more.

**20. What is anomaly persistence?**
A normalised measure of how long the anomaly has persisted; longer persistence
raises priority (and drives much of the score, which is why TIDE can coincide
with ANOMALY_ONLY).

**21. Why separate confidence from uncertainty?**
They answer different questions. Uncertainty is how unsure the value is;
confidence is how well-supported the *candidate* is (including evidence
coverage). Observation value is the cost-aware prioritisation score. Collapsing
them would hide the reasoning.

**22. What is evidence-carrying intelligence?**
Every candidate carries evidence items (type, strength, description) so a
recommendation can be traced to its grounds instead of asserted.

**23. How are candidates ranked?**
By `observation_value` descending, with deterministic tie-breaking by
`candidate_id`.

**24. What happens when values are missing?**
Missing/non-finite inputs default to 0 (cost defaults to 1) via the `unit()`
clamp, so scoring stays finite and never crashes.

**25. What happens when cost is zero?**
The denominator floors at `epsilon = 0.05`, so a zero/tiny cost cannot inflate
the score into an unbounded value.

---

## Verdicts

**26. What does LIKELY_MODEL_ISSUE mean?**
Available evidence is more consistent with the model being the weaker side of the
disagreement — a **cautious category**, not proof.

**27. Does the system prove a model is wrong?**
No. Verdicts are evidence-relative categories and are never presented as proof.

**28. Does it prove a sensor is faulty?**
No. `LIKELY_SENSOR_ISSUE` is a cautious category; the system does not certify
sensor failure.

**29. What does INSUFFICIENT_EVIDENCE mean?**
There is not enough consistent evidence (e.g. too few observations, low severity,
or contradictory evidence) to support a stronger category. It is the safe
default.

---

## Simulation

**30. What is a virtual observation?**
A simulated reading derived from existing inputs at a location, used to show the
before/after effect of measuring there.

**31. Is simulated data stored as real data?**
No. Simulated outcomes are never written to the observation store.

**32. How is simulation isolation enforced?**
The what-if uses the shared pure `simulate_candidate` primitive, results are
labelled SIMULATED, and the reset endpoint deletes only simulation rows; tests
assert real rows are untouched.

**33. Why is the simulation labelled demonstration only?**
Because it is a transparent heuristic estimate of the effect of a confirmed
reading, not a field measurement. The label prevents misinterpretation.

---

## Replay

**34. What is Decision Replay?**
A read-only, step-by-step reconstruction of the decision process contrasting
MODEL-ONLY and TIDE-ASSISTED paths.

**35. What is MODEL-ONLY?**
The path where the decision is formed without the TIDE-prioritised observation.

**36. What is TIDE-ASSISTED?**
The path where the TIDE-prioritised observation is applied before the decision.

**37. What is regret?**
An optional demonstration metric comparing the two paths' outcomes. It is a
demonstration figure, not a validated measure.

**38. Is regret a scientifically validated metric here?**
No. It is explicitly a demonstration metric.

---

## Validation

**39. What is the benchmark?**
A reproducible framework that runs multiple observation-selection strategies on
the same candidate pools/cases and reports metrics with sample sizes.

**40. What baselines were used?**
RANDOM, UNIFORM, UNCERTAINTY_ONLY, ANOMALY_ONLY, DATA_GAP_ONLY, and TIDE.
`MIN_SAMPLE = 3`.

**41. What did the reference benchmark show?**
Budget 1, seed 42, 8 locations, 768 observations, 3 events, non-degenerate pool:
TIDE and ANOMALY_ONLY both 0.75 decision-change and 0.2527 mean uncertainty
reduction — **TIDE ties ANOMALY_ONLY**.

**42. Did TIDE outperform all baselines?**
No. In the reference run it ties the strongest baseline. No superiority is
claimed.

**43. Why can't you claim TIDE is scientifically validated?**
Scientific validation requires independent ground truth and broader evaluation.
Neither is available; TIDE is a heuristic tested against its own documented
formula.

**44. What is missing ground truth?**
An independent, externally labelled record of what actually happened. Without
it, false-alarm and missed-event rates cannot be computed.

**45. What would you do for real scientific validation?**
Acquire independent labels (field campaign or external datasets), run
multi-region/longer-period evaluation, calibrate uncertainty, validate cost
models, and add expert review and statistical significance testing.

---

## Engineering

**46. How many backend tests pass?**
96 tests, 96 passing, 0 failing (`python -m unittest discover -s tests`).

**47. How was Docker verified?**
The frontend image builds; `docker compose up` runs PostgreSQL/PostGIS, backend
and frontend, all HEALTHY; Cesium assets and the `/api/health` proxy return 200.

**48. How is system health monitored?**
A health endpoint plus container healthchecks; the frontend healthcheck probes
`http://127.0.0.1/` (not "localhost") to avoid IPv6 resolution issues.

**49. How are secrets handled?**
`.env`/`.env.*` are gitignored, `.env.example` files are tracked as templates,
and no real tokens are committed. A developer-local Cesium Ion token is
untracked and should be rotated.

**50. What are the current limitations?**
No independent ground truth; TIDE is a heuristic (not validated); costs are
assumptions; browser visual/accessibility verification incomplete; no frontend
unit-test runner; per-worker cache; exact live-data reproduction requires the
captured dataset.

---

# TOUGH QUESTIONS

### "What exactly is your innovation?"
> "The implemented contribution is the TIDE-Loop: a closed workflow that fuses
> model-vs-observation disagreement, uncertainty, data gaps, event persistence,
> decision impact and normalised observation cost into an evidence-carrying
> observation priority, then supports what-if simulation, decision replay and
> benchmark validation. I am not claiming universal novelty — I am claiming a
> coherent, reproducible integration."

### "Isn't this just a weighted formula?"
> "The formula is one component. The contribution is the integration: evidence
> per candidate, a confidence value distinct from uncertainty, cautious verdicts,
> strict simulation isolation, a two-mode replay, and a reproducible benchmark.
> The formula is deliberately transparent, but the workflow around it is the
> deliverable."

### "Your benchmark doesn't show TIDE winning. Why?"
> "Correct — the reference run shows TIDE tying ANOMALY_ONLY on the reported
> metrics. The current result does not establish superiority. The purpose of the
> framework is to make the comparison reproducible and testable, so a stronger
> claim would require new data, not new wording."

### "Is this scientifically validated?"
> "The software and algorithm have been tested, but independent scientific
> empirical validation is not yet established, because independent ground truth
> and broader evaluation are unavailable."

### "Can your system predict the future?"
> "The project includes a forecasting component, but I do not claim predictive
> accuracy: there is no independent ground truth to score predictions against.
> The core contribution is observation prioritisation, not forecasting."

### "Can the system tell whether a sensor is faulty?"
> "It provides cautious verdict categories based on available evidence. It does
> not prove sensor failure."

### "Are your observations real?"
> "The store distinguishes REAL, HISTORICAL, SIMULATED, SYNTHETIC and
> MODEL_DERIVED. The reference dataset is 760 real plus 8 labelled simulated.
> TIDE candidates are MODEL_DERIVED; virtual observations and benchmark outcomes
> are SIMULATED and never presented as real."

### "Two of your baselines have identical numbers — is that suspicious?"
> "No. On a single-event reference dataset the highest-persistence candidate is
> also the highest-value candidate, so ANOMALY_ONLY and TIDE select the same
> candidate. The identical metric values are an expected consequence, and the
> benchmark reports them as-is."

### "If TIDE ties a simple baseline, why keep it?"
> "Because the tie is dataset-specific and the framework is the point. TIDE
> exposes its evidence, cost sensitivity and decision rule, which simple
> baselines do not. The benchmark is designed to expose exactly this, honestly."
