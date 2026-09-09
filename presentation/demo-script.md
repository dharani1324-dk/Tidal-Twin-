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
- [ ] **Fullscreen** — the side nav now has 7 pages: Digital Twin, Monitoring,
  Safety Center, Risk Map, Story Mode, Ocean AI, Reports.
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
> monitored in real time — temperature, wave height, wave direction. Watch the
> markers breathe as data flows in."

Do this: spin the globe. **Toggle on "Storm Track"** — the cyclone path, its
cone and the moving eye appear. Then press **Play** on the Global Timeline:
the heat patches animate through 48 hours of observations into 24 hours of AI
projection.

### 1:00–1:30 — AI WATCHES FOR DANGER (navigate to "Monitoring")
> "This is where the AI does its job. Our anomaly engine — using the same
> machine-learning technique banks use for fraud detection — watches every
> region and flags anything unusual."

Do this: **click "Run AI Radar Scan"** live, then point at the active alert:
> "A temperature anomaly off Goa, 85% confidence. The AI found this heatwave
> before it became dangerous."

### 1:30–2:00 — THE ASSISTANT (navigate to "Ocean AI")
> "Our platform speaks plain language. Ask the ocean a question."

Do this: type these EXACT demo questions and read the answers aloud:
1. `is it safe to go fishing in goa today?`
2. `compare wave heights between chennai and goa`
3. `which region has the warmest water right now?`

### 2:00–2:30 — SAFETY CENTER: THE "WOW" (navigate to "Safety Center")
> "And now the part that matters to a fisherman. One screen, every coast,
> colour-coded safe / caution / danger — with a safe sailing window for each."

Do this (pick the **Goa** card — avoid clicking the LIVE feed's blast until here):
1. Point at the LIVE Command Feed at the top — "this is our **WebSocket live
   push**, updating every twelve seconds: storm position, wind speed, alerts."
2. Click **SMS Alert** on the Goa card — the phone mock fills with a
   WhatsApp-style bulletin ("Alert dispatched to 2,400 vessels").
3. Switch the **language picker to हिन्दी** and click **Voice** — the bulletin
   is read aloud in Hindi.
> "Voice, SMS or WhatsApp — in six Indian languages, the warning reaches the
> beach before the storm does."

### 2:30–3:00 — NATIONAL RISK MAP (navigate to "Risk Map")
> "This is the state's view: one screen, the whole nation. Every coast, every
> risk band, and the live cyclone — all at once."

Do this: sweep across the map, point at the red **storm track + eye** over the
Bay of Bengal, then read the **Threat Ranking** list off the right rail.

### 3:00–3:30 — STORY MODE (navigate to "Story Mode")
> "We turned the data into understanding. Story Mode guides you through ocean
> science — every number on screen is real, live sensor data."

Do this: click **Marine Heatwaves**, flip a chapter, point at the bar chart
showing **Goa elevated** and the "Hottest right now: Goa Coast" fact.

### 3:30–4:00 — THE RISK REPORT (navigate to "Reports")
> "And this is what government stakeholders see: a National Risk Index. Every
> region scored, ranked, and explained — no black boxes."

Do this: point at the **Goa row** ranked #1 with its red status pill.
> "See the weightings at the bottom? You can verify every number and download
> the raw data as CSV."

### 4:00–4:30 — THE "PROOF" MOMENT (Story Mode → time explorer OR Reports → accuracy)
> "And because this is science, not magic — here's the forecast verification.
> The blue line is what the AI predicted. The green line is what the ocean
> actually did. They nearly overlap. That's a trustworthy model."

Do this: on Story Mode use the **Time Explorer slider**, or on Reports point to
the accuracy metrics; the Safety Center's trust sparklines also show rolling
MAE + "model drift" flags.

### 4:30–5:00 — CLOSING + IMPACT
> "In five minutes you've seen: live data ingestion, a 3D digital twin with
> storm tracking and forecast playback, AI anomaly detection, a national risk
> map, multilingual voice safety alerts pushed over live WebSockets, guided
> storytelling, and executive decision reports — in one platform. The same twin
> can be pointed at any coastline on Earth. This is data in, decisions out."

---

## Backup Plan (if an API fails)
- If the live backend is down, the frontend still renders — keep the
  conversation calm: "let me restart the service", restart uvicorn.
- If the simulate step wasn't run, "Run AI Radar Scan" still works on normal
  data — say "the ocean is calm today, which is why our AI is quiet — that's
  exactly what it's supposed to do."
- If the WebSocket feed stays "connecting…", skip the LIVE feed point and carry
  on with SMS + Voice bulletins (they work over plain HTTP).

## What NOT to do
- ❌ Don't read code aloud.
- ❌ Don't say "it's just statistical" — say "statistics + machine learning".
- ❌ Don't open Risk Map and Digital Twin at the same time — pick one map moment.
- ❌ Don't apologize for anything. It's a hackathon demo, not a launch.