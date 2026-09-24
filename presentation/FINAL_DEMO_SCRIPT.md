# TidalTwin — Final Live Demo Script (5 Minutes)

> Timed, judge-facing walkthrough of **4D Ocean Digital Twin + TIDE-Loop**.
> Practice until it is muscle memory. Every statement is grounded in the
> implementation. See [`FINAL_VIVA.md`](FINAL_VIVA.md) for Q&A and
> [`DEMO_FALLBACK.md`](DEMO_FALLBACK.md) for contingencies.

---

## Pre-flight (do BEFORE judges arrive)

- [ ] Backend running (`uvicorn app.main:app`, port 8000) — wait for warm-up
      (~4 s) so the first TIDE request is fast.
- [ ] Frontend running (`npm run dev`, port 5173) **or** Docker stack up
      (`docker compose up`) on port 8080.
- [ ] Verify `GET /api/v1/health` and `GET /api/v1/demo/status` return 200.
- [ ] Browser **fullscreen**, brightness up, notifications off.
- [ ] Confirm the reference dataset state: **768 observations (760 real + 8
      simulated)**, **3 detected events** at Goa Coast (Panaji).
- [ ] Know your known event: **`event-0` Marine heatwave, confidence 0.91**.
- [ ] Know your known candidate: `tide-5-temperature-0-buoy` (Goa).
- [ ] Rehearse the one Copilot question you will ask (see 4:30).

**Routes used:** `/globe`, `/anomalies`, `/forensics`, `/tide`,
`/tide/replay`, `/tide/validation`, `/assistant`.

---

## 0:00–0:30 — Introduce the project

**On screen:** Mission Control (`/`)

> "This is a 4D Ocean Digital Twin. It does not only show what is happening in
> the ocean. Its TIDE-Loop helps prioritize **what observation should be
> considered next**, based on uncertainty, data gaps, event persistence,
> decision impact and observation cost."

Do not use superiority claims. Then sweep the Ocean Situation strip.

---

## 0:30–1:00 — Show the 4D Twin

**On screen:** Digital Twin (`/globe`)

> "The twin is four-dimensional: latitude and longitude across the surface,
> **depth** below it, and **time**. Here we show ocean variables — temperature,
> waves, and the model-versus-observation comparison."

Do this: orbit the globe, toggle a variable, then open a depth/transect view if
available. Point out the depth axis and the time scrubber.

---

## 1:00–1:30 — Open Anomaly Radar

**On screen:** Anomaly Intel (`/anomalies`)

Do this: run the scan, then select the actual available Goa event.

> "The Radar compares conditions against a model baseline and flags unusual
> ones. Here is an active marine heatwave off Goa — this is a system-detected
> event on the reference dataset."

Show: anomaly, region, event state. If no live event appears, use the documented
reference event and say so (see fallback).

---

## 1:30–2:00 — Forensics → Event DNA

**On screen:** Ocean Forensics (`/forensics`)

> "Forensics investigates the event: what changed, when, at what depth, the
> uncertainty, and the evidence behind it."

Do this: open the event, read one evidence line, then open **Event DNA**.

> "The event is converted into a structured fingerprint that provides context
> for the downstream decision support. It is a grounded signature, not a claim
> about the cause."

---

## 2:00–3:00 — TIDE

**On screen:** TIDE Command Center (`/tide`)

> "Now TIDE. Each candidate observation is scored on uncertainty, data gap,
> disagreement, persistence and decision impact, against a normalised cost."

Do this: show the candidate ranking and open one candidate. Read out:
- observation value
- confidence
- evidence list
- the decision recommendation

Then click **WHY THIS LOCATION?**

> "This explains, from the actual evidence, why this candidate is prioritized —
> for example, a model-observation mismatch plus a persisting anomaly and a
> coverage gap."

---

## 3:00–3:45 — What If We Measure Here?

**On screen:** TIDE Command Center → What-If

Do this: click **WHAT IF WE MEASURE HERE?** on the leading candidate.

> "This creates a **SIMULATED OBSERVATION — DEMONSTRATION ONLY**. It is not
> collected by a sensor and is not written to the observation store."

Show before → virtual observation → after → decision.

If the decision does not change, say verbatim:

> "The decision remains unchanged under this simulated observation."

Do not force a decision change.

---

## 3:45–4:30 — Decision Replay

**On screen:** Decision Replay (`/tide/replay`)

> "Replay lets us inspect the decision process, not just the final answer. The
> MODEL-ONLY path and the TIDE-ASSISTED path are identical until the observation
> step, then they diverge."

Do this: step through a few stages; point at the divergence after OBSERVATION.

> "Any regret shown here is a demonstration metric, not a validated measure."

---

## 4:30–5:00 — Copilot + close

**On screen:** Ocean AI Copilot (`/assistant`)

Ask one grounded question:

> "Why is this observation candidate prioritized?"

or

> "What evidence supports the current TIDE recommendation?"

> "The answer is generated from the same project data and engines — not canned
> text."

Close:

> "The key idea is the closed TIDE-Loop: model, observation, disagreement, next
> observation, decision, and validation."

---

## Do / Don't

- Do lead with the **decision question**, not the 3D globe.
- Do say **implemented / tested / demonstrated**, never "validated" or "proven".
- Do label simulations and screenshots honestly.
- Don't claim TIDE is better than the baselines.
- Don't apologize for limitations — state them as engineering maturity.
- Don't open two heavy map views at once.
