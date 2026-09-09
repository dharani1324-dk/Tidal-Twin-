# OceanVerse AI — Live Demo Script (5 Minutes)

A timed, judge-facing walkthrough. Practice this flow so it becomes muscle
memory. **Total: 5 minutes** with room for questions.

---

## Pre-Demo Checklist (do BEFORE judges arrive)
- [ ] Backend running: `uvicorn app.main:app --reload` (port 8000)
- [ ] Frontend running: `npm run dev` (port 5173)
- [ ] Browser open on **Dashboard** (`http://localhost:5173`)
- [ ] Heatwave data ALREADY simulated for Goa (so the globe shows the hotspot):
  ```
  cd backend
  .venv\Scripts\python -m scripts.simulate_anomaly --location goa --kind heatwave
  ```
- [ ] One alert active = Goa temperature anomaly (check Monitoring page).
- [ ] Screen brightness up, no clutter on desktop, fonts at readable size.

---

## The Script

### 0:00–0:30 — OPENING (on the Dashboard)
> "This is OceanVerse AI — an AI-powered digital twin of India's ocean.
> Everything you're seeing runs on **live data** and **machine learning**."

Do this: slowly move across the dashboard — health ring, energy gauge bars,
region chips, live telemetry feed. Let the animation breathe.

### 0:30–1:00 — THE 3D GLOBE (navigate to "Digital Twin")
> "Here's the ocean itself. Eight regions across India's coastline are being
> monitored in real time — temperature, wave height, wave direction.
> Watch the markers breathe as data flows in."

Do this: spin the globe gently. Toggle a layer or two on/off to show
interactivity. Point at the **Goa marker** — it's hot from the simulation.

### 1:00–1:45 — AI WATCHES FOR DANGER (navigate to "Monitoring")
> "This is where the AI does its job. Our anomaly engine — using the same
> machine-learning technique banks use for fraud detection — watches every
> region and flags anything unusual."

Do this: **click "Run AI Radar Scan"** live. Then show the active alert card:
> "There it is: a temperature anomaly off Goa, 85% confidence. The AI detected
> this heatwave before it became dangerous."

### 1:45–2:15 — THE ASSISTANT (navigate to "Ocean AI")
> "Our platform speaks plain language. Ask the ocean a question."

Do this: type these EXACT demo questions and read the answers aloud:
1. `is it safe to go fishing in goa today?`
2. `compare wave heights between chennai and goa`
3. `which region has the warmest water right now?`

Read the first answer dramatically — it's the "wow".

### 2:15–2:45 — STORY MODE (navigate to "Story Mode")
> "We turned the data into understanding. Story Mode guides you through ocean
> science — and every number on screen is real, live sensor data."

Do this: click **Marine Heatwaves**, flip a chapter, point at the bar chart
showing **Goa elevated** and the "Hottest right now: Goa Coast" fact.

### 2:45–3:30 — THE RISK REPORT (navigate to "Reports")
> "And this is what government stakeholders see: a National Risk Index.
> Every region scored, ranked, and explained — no black boxes."

Do this: point at the **national gauge** (risk score) and the **Goa row**
ranked #1 ELEVATED with its red status pill.
> "See the weightings at the bottom? You can verify every number and download
> the raw data as CSV."

### 3:30–4:30 — THE "PROOF" MOMENT (Story Mode → time explorer OR ask a judge to)
> "And because this is science, not magic — here's the forecast verification.
> The blue line is what the AI predicted. The green line is what the ocean
> actually did. They nearly overlap. That's a trustworthy model."

Do this: on Story Mode, use the **Time Explorer slider** while the two lines
track each other, or on Reports point to the accuracy metrics.

### 4:30–5:00 — CLOSING + IMPACT
> "In five minutes you've seen: live data ingestion, 3D visualization,
> AI anomaly detection, natural-language intelligence, guided storytelling,
> and executive decision reports — in one platform. The same twin can be
> pointed at any coastline on earth. This is data in, decisions out."

---

## Backup Plan (if an API fails)
- If the live backend is down, the frontend still renders — keep the
  conversation calm: "let me restart the service", restart uvicorn.
- If the simulate step wasn't run, the "Run AI Radar Scan" still works on
  normal data — say "the ocean is calm today, which is why our AI is quiet —
  that's exactly what it's supposed to do."

## What NOT to do
- ❌ Don't read code aloud.
- ❌ Don't say "it's just statistical" — say "statistics + machine learning".
- ❌ Don't apologize for anything. It's a hackathon demo, not a launch.