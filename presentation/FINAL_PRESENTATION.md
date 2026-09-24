# TidalTwin — 4D Ocean Digital Twin
## Final Presentation Deck (15 slides)

> **How to use this deck.** Each slide gives the on-screen content, a suggested
> visual, and short speaker notes. Every number is traceable to the repository
> (see [`../docs/RESULTS_AND_LIMITATIONS.md`](../docs/RESULTS_AND_LIMITATIONS.md)).
> No unsupported claims: TIDE is a **decision-support heuristic**, tested and
> demonstrated, and **not empirically/scientifically validated**.

---

## SLIDE 1 — TITLE

**On screen**
```
4D OCEAN DIGITAL TWIN

TIDE-Loop: Trust-aware Information for Decision and Exploration

Stack: React 19 · TypeScript · Vite · CesiumJS  ·  FastAPI · SQLAlchemy
       Python 3.12  ·  PostgreSQL 16 + PostGIS 3.4  ·  Docker
```

**Placeholders**
- Team / presenters: `<names>`
- Institution: `<institution>`
- Event / date: `<event, date>`
- Repository: `<repo link>`

**Speaker notes**
> "This is a 4D ocean digital twin. It goes beyond showing what is happening in
> the ocean: its TIDE-Loop helps decide **which observation should be considered
> next, and why** — using uncertainty, data gaps, event persistence, decision
> impact and normalised observation cost."

Do **not** say: world's first, world's best, scientifically proven.

---

## SLIDE 2 — THE PROBLEM

**On screen**
```
Ocean data is:
  multidimensional · dynamic · spatial · depth-dependent
  time-dependent · heterogeneous

Questions current workflows already help answer:
  What is happening?  Where?  When?  Why might it have happened?

The question this project adds:
  WHERE SHOULD WE OBSERVE NEXT, AND WHY?
```

**Visual:** split image — a rich 3D ocean scene on the left, a single decision
question highlighted on the right.

**Speaker notes**
> "Ocean data is multidimensional and changes across space, depth and time, and
> it comes from many different sources. Existing workflows answer what/where/when
> and help with why. The decision gap we address is: given a limited budget,
> where should the next observation go, and what evidence supports that choice?"

---

## SLIDE 3 — EXISTING GAP

**On screen**
```
Observation → Visualization → Detection → Investigation
                                              │
                                   Decision-support gap
                                              ↓
   What should we observe next?  Why there?
   What evidence supports it?  What could change if we measure there?
```

**Speaker notes**
> "We are not claiming existing ocean systems cannot observe, visualise, detect
> or investigate. They can. What this project does is **integrate** those stages
> with an explicit next-observation decision layer, so the investigation ends in
> a ranked, evidence-backed recommendation rather than stopping at a map."

---

## SLIDE 4 — PROPOSED SYSTEM

**On screen**
```
4D OCEAN DIGITAL TWIN
        ↓
ANOMALY RADAR
        ↓
FORENSICS
        ↓
EVENT DNA
        ↓
TIDE-LOOP
        ↓
OBSERVATION PRIORITIZATION
        ↓
WHAT-IF SIMULATION
        ↓
DECISION REPLAY
        ↓
VALIDATION

Side interface: OCEAN COPILOT (natural-language access to the same engines)
```

**Speaker notes**
> "This is the full pipeline, implemented end to end. The Copilot is not a
> separate brain — it is a natural-language interface onto the same grounded
> data and engines."

---

## SLIDE 5 — 4D OCEAN DIGITAL TWIN

**On screen**
```
Dimensions: Latitude · Longitude · Depth · Time

TIDE variable set (10):
  temperature · salinity · oxygen · chlorophyll · wave height
  current speed · pressure · nutrients · pH · density

Depth views: temperature–depth transects · Argo-style trajectories
```

**Honesty note on slide**
```
Availability differs by variable and source. The side-by-side
MODEL | OBSERVED comparison is available for a core set; other variables
may be model-derived or unavailable for a given location.
```

**Speaker notes**
> "The twin is four-dimensional: horizontal position, depth and time. The TIDE
> layer recognises ten ocean variables, but availability is honest — some are
> observed, some model-derived, some unavailable. We never present a
> model-derived value as an observation."

---

## SLIDE 6 — OCEAN EVENT INTELLIGENCE

**On screen**
```
ANOMALY → FORENSICS → EVENT TIMELINE → EVENT DNA

Anomaly Radar : detects unusual conditions vs a model baseline
Forensics     : what changed · when · at what depth · contributing factors
                · uncertainty · evidence
Event DNA     : a structured event fingerprint (context for downstream decisions)
```

**Event types actually emitted**
```
marine_heatwave · cold_water_anomaly · rapid_temp_change
strong_current_event · coastal_flooding_risk · model_mismatch_event
```

**Speaker notes**
> "The Radar flags unusual conditions, Forensics investigates them, and Event DNA
> packages the event into a structured signature. Event DNA is a grounded
> fingerprint, not a validated classification model."

---

## SLIDE 7 — THE CORE INNOVATION: TIDE-LOOP

**On screen**
```
TIDE-Loop
Trust-aware Information for Decision and Exploration

MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION
      → BETTER DECISION → VALIDATION ↺

The loop connects:
  model information · observations · disagreement · uncertainty
  data gaps · event persistence · decision impact · observation cost
  evidence
```

**Speaker notes**
> "TIDE-Loop closes the cycle. A model and observations are compared; the
> disagreement and the remaining gaps feed a prioritisation of the next
> observation; the outcome is simulated and replayed; and the result is
> validated against the framework. We are not claiming the loop is universally
> unprecedented — the contribution is the integration."

---

## SLIDE 8 — TIDE OBSERVATION VALUE

**On screen**
```
Observation Value =
  Decision Impact × Uncertainty × Data Gap × Anomaly Persistence
  ÷ Observation Cost
```

| Factor | Meaning (one line) |
|--------|--------------------|
| Decision Impact | how much the decision depends on this variable |
| Uncertainty | how uncertain that variable currently is |
| Data Gap | how sparse/stale coverage is for it |
| Anomaly Persistence | how long the anomaly has persisted |
| Observation Cost | normalised cost of the observation method |

**Honesty note**
```
Observation cost = NORMALIZED OBSERVATION COST — DEMONSTRATION ASSUMPTION
Not a universal real-world cost.

Implementation guards: inputs clamped to 0..1 (finite only); a minimum
denominator (epsilon = 0.05) prevents zero-cost inflation.
```

**Speaker notes**
> "This is the actual implemented formula. Every factor is a normalised 0..1
> input. Cost is a demonstration assumption, not a monetary claim. Zero or tiny
> cost cannot inflate the score because the denominator is floored at 0.05."

---

## SLIDE 9 — TRUST & EVIDENCE

**On screen**
```
Candidate → Observation Value → Evidence → Confidence → Verdict

Three different things:
  Uncertainty      — how unsure the estimate is
  Confidence       — how well-supported the candidate is
  Observation Value— the prioritisation score (cost-aware)

Evidence types used:
  model-observation mismatch · persistent anomaly · data gap
  temporal gap · depth gap · stale observation · sparse/no observation
  APEX recommendation · Event DNA feature
```

**Speaker notes**
> "Uncertainty, confidence and observation value are not the same quantity. Each
> candidate carries evidence with a type, strength and description, so a
> recommendation can be traced rather than asserted. Verdicts are deliberately
> cautious: LIKELY_* categories, never proven causes."

---

## SLIDE 10 — WHAT IF WE MEASURE HERE?

**On screen**
```
SELECT LOCATION → VIRTUAL SENSOR → SIMULATED OBSERVATION
      → BEFORE → AFTER → DECISION

Before: uncertainty, anomaly risk, decision state
After : uncertainty, anomaly risk, decision state
        (decision changed OR unchanged)
```

**Mandatory label (large)**
```
SIMULATED OBSERVATION — DEMONSTRATION ONLY
Not collected by a sensor. Not written to the observation store.
```

**Speaker notes**
> "The what-if creates a virtual observation from existing inputs and shows the
> before/after. It is explicitly labelled demonstration-only and is never
> persisted. If the decision does not change, we say so — that is a valid
> outcome."

---

## SLIDE 11 — DECISION REPLAY

**On screen**
```
MODEL-ONLY   VS   TIDE-ASSISTED

Compare where supported:
  event detection · uncertainty · evidence
  observation · decision state · validation

Two modes are identical before the OBSERVATION step.
Any "regret" shown is a DEMONSTRATION METRIC.
```

**Speaker notes**
> "Replay lets the audience inspect the decision process instead of only seeing
> the final recommendation. Both modes share the same setup; they diverge only
> after the observation step. We do not claim TIDE universally improves
> decisions."

---

## SLIDE 12 — VALIDATION & BENCHMARKING

**On screen**
```
Strategies: RANDOM · UNIFORM · UNCERTAINTY_ONLY · ANOMALY_ONLY
            DATA_GAP_ONLY · TIDE

Reference run:
  Budget = 1 · Seed = 42 · Locations = 8
  Observations = 768 · Events = 3 · pool_is_degenerate = false
```

| Strategy | Decision Change | Mean Uncertainty Reduction |
|----------|:---------------:|:--------------------------:|
| RANDOM | 1.00 | 0.1905 |
| UNIFORM | 1.00 | 0.1883 |
| UNCERTAINTY_ONLY | 1.00 | 0.1898 |
| ANOMALY_ONLY | 0.75 | 0.2527 |
| DATA_GAP_ONLY | 1.00 | 0.1898 |
| **TIDE** | **0.75** | **0.2527** |

**Statement on slide (verbatim)**
> In this reference run, **TIDE ties ANOMALY_ONLY** on the reported metrics.

**Speaker notes**
> "Be explicit: TIDE ties the strongest baseline here. The value of the
> framework is that the comparison is reproducible and testable. We do not claim
> superiority, optimality, or scientific validation. False alarms and
> missed-event rates are unavailable — there is no independent ground truth."

---

## SLIDE 13 — ENGINEERING & DEMONSTRATION STATUS

**On screen**
```
Backend tests            96 / 96 PASS
Frontend TypeScript      PASS
Frontend lint            PASS
Frontend production build PASS
Docker frontend build    PASS
Docker Compose           PASS
Database                 HEALTHY
Backend                  HEALTHY
Frontend                 HEALTHY
Cesium assets            verified (HTTP 200)
npm audit --omit=dev     0 vulnerabilities
```

**Honesty note**
```
Automated + headless verification only. Browser rendering, responsiveness and
accessibility were NOT independently verified in a live browser session.
```

**Speaker notes**
> "Everything on this slide is verified. The one thing we do not overstate is
> the browser session — those checks are outstanding."

---

## SLIDE 14 — LIMITATIONS

**On screen**
```
• No independent ground truth
• TIDE is currently a decision-support heuristic
• Empirical scientific validation NOT established
• False-alarm / missed-event ground truth UNAVAILABLE
• Observation costs are demonstration assumptions
• Browser visual / accessibility verification incomplete
• No frontend unit-test runner (typecheck + lint + build only)
• TIDE cache is per worker
• Exact live-data reproduction requires the captured dataset
```

**Speaker notes**
> "This slide is here on purpose. Stating limitations precisely is what makes
> the rest of the claims defensible."

---

## SLIDE 15 — CONCLUSION & FUTURE RESEARCH

**On screen**
```
Conclusion — an integrated loop:
Observe → Detect → Investigate → Understand → Prioritize
        → Observe Next → Simulate → Decide → Validate
```

**Future research (label clearly: FUTURE WORK)**
```
independent ground truth · larger datasets · longer historical periods
domain-expert evaluation · calibrated uncertainty · validated observation costs
probabilistic information gain · multi-region evaluation
larger observation budgets · field validation
```

**Speaker notes**
> "Closing line: the project integrates ocean intelligence into a decision-aware
> loop — with evidence, honest simulation boundaries, and a reproducible
> validation framework. Broader scientific validation is future work."

---

## Design notes

- One idea per slide; keep the TIDE-Loop diagram (Slide 7) the visual anchor.
- Use a neutral palette; highlight evidence in one accent colour.
- Place the mandatory simulation label and the "TIDE ties ANOMALY_ONLY"
  statement as large, unmissable text.
- Keep exact numbers as shown; they are audited in Phase 12.
