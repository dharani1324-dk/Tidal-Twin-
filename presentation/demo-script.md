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
- [ ] **Fullscreen** — the side nav now has 8 pages: Digital Twin, Monitoring,
  Model Validation, Safety Center, Risk Map, Story Mode, Ocean AI, Reports.
- [ ] The **Ocean Situation strip** on the Dashboard shows a disagreement flag
  on Goa (proof the validation engine is live).
- [ ] Screen brightness up, no clutter on desktop, fonts at readable size.

---

## The Script

### 0:00–0:30 — OPENING (on the Dashboard)
> "This is OceanVerse AI — an interactive ocean **model-validation** and
> decision-intelligence platform. Everything here runs on live data and
> machine learning."

Do this: sweep the hero, then stop on the **Ocean Situation strip**:
> "Every coast is scored against a model baseline — confidence, anomaly level,
> and live disagreement flags. One glows right now: **Goa**. We'll find out
> why in a minute."

### 0:30–1:00 — THE GLOBE + EVENT REPLAY (navigate to "Digital Twin")
> "Here's the ocean itself. Eight regions, live markers, a real cyclone watch."

Do this: toggle **Storm Track** on. Then press **Play** on Event Replay, and
switch the mode to **Difference** — the heat patches recolor to show how far
reality drifted from the model hour by hour.
> "This is a 4D event replay: observed hours, then model projection — and now
> the difference between them, live."

### 1:00–1:30 — AI WATCHES FOR DANGER (navigate to "Monitoring")
> "Under the hood, the anomaly engine — z-score statistics plus Isolation
> Forest, the same machine-learning trick used in fraud detection — flags
> anything unusual."

Do this: **Run AI Radar Scan**, point at the active alert:
> "A temperature anomaly off Goa, 85% confidence — caught before it became
> dangerous."

### 1:30–2:00 — THE DIFFERENTIATOR: VALIDATION WORKSPACE (navigate to "Model Validation")
> "Now — the part that makes this more than a viewer. Pick **Goa**. The system
> puts the model side by side with reality."

Do this: point at the **MODEL · OBSERVED · DEVIATION** row (+1.8°C, red), then
the "Why it matters" panel, then the confidence meters:
> "Sea surface temperature is 1.8 degrees above the model baseline. Possible
> cause: persistent surface heating with weak mixing. Confidence high,
> disagreement flagged. That's a scientist's workflow, automated — not just a
> prettier colorbar."

### 2:00–2:15 — THE ASSISTANT (navigate to "Ocean AI")
Do this: ask ONE question — `is it safe to go fishing in goa today?` — and read
the answer aloud.

### 2:15–2:45 — SAFETY CENTER: THE "WOW" (navigate to "Safety Center")
> "And here is the decision side — what a fisherman actually sees."

Do this: on the **Goa** card click **SMS Alert** (phone mock fills with a
WhatsApp-style bulletin), then switch the voice to **हिन्दी** and press Voice.
> "SMS, WhatsApp or voice — in six Indian languages, the warning reaches the
> beach before the storm does."

### 2:45–3:10 — NATIONAL RISK MAP (navigate to "Risk Map")
> "One screen, the whole nation: every coast, every risk band, and the live
> cyclone moving toward Odisha."

Do this: sweep the map, point at the storm track + eye, read the **Threat
Ranking** rail.

### 3:10–3:35 — STORY MODE (navigate to "Story Mode")
Do this: open **Marine Heatwaves**, flip a chapter, point at the bar chart
showing **Goa elevated**.

### 3:35–4:00 — THE RISK REPORT (navigate to "Reports")
> "And this is the stakeholder view — a National Risk Index, ranked and
> explained. No black boxes: you can verify the weightings and download the CSV."

### 4:00–4:30 — THE "PROOF" MOMENT
> "And because this is science, not magic — verification. The blue line is
> what the model predicted; the green line is what the ocean did. They nearly
> overlap. That's a trustworthy model."

Do this: on **Model Validation**, scroll to the verification charts (or use
Story Mode's Time Explorer / Reports accuracy metrics).

### 4:30–5:00 — CLOSING + IMPACT
> "In five minutes you've seen: live data ingestion, a 4D event replay, AI
> anomaly detection, a model-validation engine with confidence scores, a
> national risk map, multilingual voice safety bulletins pushed over live
> WebSockets, and executive reports — one platform. Not another ocean viewer:
> a system that tells you where the model disagrees with reality, by how much,
> why it matters, and what to do. This is data in, decisions out."

---

## Backup Plan (if an API fails)
- If the live backend is down, the frontend still renders — keep the
  conversation calm: "let me restart the service", restart uvicorn.
- If the simulate step wasn't run, "Run AI Radar Scan" still works on normal
  data — say "the ocean is calm today, which is why our AI is quiet — that's
  exactly what it's supposed to do."
- If the WebSocket feed stays "connecting…", skip the LIVE feed point and carry
  on with SMS + Voice bulletins (they work over plain HTTP).
- If Goa shows no deviation, re-point the same moment at whichever coast is
  reddest in the Validation Workspace.

## What NOT to do
- ❌ Don't open Risk Map and Digital Twin at the same time — pick one map moment.
- ❌ Don't lead with "it's a 3D ocean globe" — lead with **validation**.
- ❌ Don't read code aloud.
- ❌ Don't say "it's just statistical" — say "statistics + machine learning".
- ❌ Don't apologize for anything. It's a hackathon demo, not a launch.