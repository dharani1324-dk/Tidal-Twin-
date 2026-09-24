# TidalTwin — Design System Audit & Redesign Brief

> Purpose: a verified description of the current look/feel/UX, followed by a
> ready-to-paste prompt for a full visual redesign.
> Everything in Part A was read from source (files and line counts cited), not
> inferred from the README.

---

## Part A — Current design, verified

### A1. Product & audience (drives every design decision)

| | |
|---|---|
| What it is | 4D ocean digital twin + **model-validation decision engine** |
| Primary user | Coastal command-centre operator (the UI even says `CMD OPS`) |
| Secondary users | Scientists, judges, coastal managers, fishermen *(safety advisories)* |
| Core UX job | Walk an operator through `OBSERVE → DETECT → INVESTIGATE → UNDERSTAND → PRIORITIZE → OBSERVE NEXT → SIMULATE → DECIDE → VALIDATE` |
| Hard constraint | **Never imply more certainty than exists.** Missing data must render as `NOT AVAILABLE`, never as a plausible number |

### A2. Design tokens — the source of truth

`src/index.css` `:root` (~106 lines of tokens):

```
/* Background layers, abyss → panel */
--bg-abyss #01060f   --bg-0 #020c18   --bg-1 #061a2c   --bg-2 #093046
--bg-3 rgba(12,44,66,.6)   --bg-glass rgba(2,12,24,.74)   --bg-overlay rgba(1,7,16,.88)

/* Accents — described in-source as "data, not decoration" */
--accent #00d4ff        /* bioluminescent cyan — primary telemetry */
--accent-blue #38bdf8   /* satellite / currents */
--accent-violet #8b8cf8 /* spectral analysis */
--accent-warm #ffb800   /* warnings */
--teal #00ffb3          /* secondary bioluminescent teal */

/* Semantic */
--ok #00ffb3   --warn #ffb800   --danger #ff3366   --info #00d4ff

/* Text ramp */
--text-0 #f0f9ff  --text-1 #a6cbe0  --text-2 #6e9cba  --text-3 #3f6784

/* Borders — all cyan at 4 levels of alpha */
--line-0 rgba(0,212,255,.12) → --line-1 .22 → --line-2 .38 → --line-accent .66
```

**Typography** — three families, loaded from Google Fonts in `index.html`:

- `--font-display: Fraunces` (a **serif**, 300–700) — used for `h1`/`h2` and the brand wordmark
- `--font-sans: Inter` — body, UI
- `--font-mono: JetBrains Mono` — every number, unit, label, timestamp, ID

Scale: `--fs-display clamp(30px,4vw,50px)` · h1 28 · h2 21 · h3 15.5 · body 14 · sm 12.75 · xs 11 · **label 10px**. Weights 400/500/600/700. Line heights 1.55 / 1.25.

**Space:** 4→40px in 8 steps. **Radius:** 8 / 10 / 14 / 20 / 999. **Blur:** 10 / 18 / 28px. **Motion:** `--t-fast 120ms`, `--t-med 220ms`, `--t-slow 420ms`, `--ease-out cubic-bezier(.22,1,.36,1)`.

**Shadows** are deep and near-black (`rgba(2,8,20,.9x)`) so cards float in the abyss, plus one cyan `--sh-glow`.

Body background is a 4-layer fixed radial-gradient stack — blue bloom top-right, cyan bloom left, teal bloom at the bottom — over `--bg-0`.

### A3. The shell (`App.css`, 662 lines)

```
┌──────────┬───────────────────────────────────────────────────┐
│ SIDEBAR  │ SYSTEM BAR   clock IST · health · SAT LINK ·      │
│ 256px    │              N REGIONS · ALERTS · UPDATED Ns      │
│ floating ├───────────────────────────────────────────────────┤
│ glass,   │ MISSION RAIL  01 OBSERVE ─ 02 DETECT ─ … ─ 09     │
│ margin   ├───────────────────────────────────────────────────┤
│ 12px,    │                                                   │
│ r-lg     │  MAIN CONTENT  (max one route, lazy-loaded)       │
│          │                                                   │
│ brand    │                                                   │
│ + 4 nav  │                                                   │
│   groups │                                                   │
│ + footer │                                                   │
└──────────┴───────────────────────────────────────────────────┘
```

- **Sidebar:** `256px`, floating (12px margin, `r-lg`, 3px blur), `linear-gradient(180deg, rgba(6,20,36,.85), rgba(3,11,20,.75))`. Brand name is a cyan→teal gradient-clipped text in Fraunces. Four nav groups labelled in 9px mono uppercase: **Mission** (5 items), **Analysis** (8), **Ocean & Coastal** (4), **Reporting** (2).
- **System bar:** live IST clock with pulsing dot, `SystemStatusPill`, satellite-link tag, region count, animated critical-alert chip, "UPDATED nS AGO" sync tag, `DemoGuide`, an `Ask Ocean AI ⌘K` CTA, a notification bell popover, and a `CMD OPS` user chip.
- **Mission rail:** 9 clickable stage cells with a `b` number / `i` label pair; states `done` (✓) / `active` / `future`. The `stageIndexFor(pathname)` function maps routes to stages — **the pipeline is literally the navigation.**
- **Nav badges:** live pills — red count on Monitoring, `GOA` warn on Validation, `TIDE` live on TIDE.
- **Mobile:** animated drawer with overlay, `x: -100% → 0`, `aria-modal`.
- **Keyboard:** `⌘K`/`Ctrl+K` → Copilot, `L` → theme toggle, `Esc` → close.

### A4. Two coexisting design languages

| | `.theme-classic` (legacy) | Ocean (default, v3) |
|---|---|---|
| Page bg | `#040b1a` flat | `#020c18` + 3 radial blooms + **64px cyan grid backdrop** |
| Accent | `#22d3ee` | `#00d4ff` |
| Type | Segoe UI everywhere (**no serif**) | Fraunces display + Inter + JetBrains Mono |
| Text | `#e8f1fc` | `#f0f9ff` |
| Borders | `rgba(150,182,230,.10–.28)` (**blue-grey**) | `rgba(0,212,255,.12–.66)` (**cyan**) |
| Signals | `#34d399` / `#fbbf24` / `#fb6b84` | `#00ffb3` / `#ffb800` / `#ff3366` |
| Texture | none | scanline overlay, particles, sonar pulse, depth markers |

The toggle is persisted to `localStorage` and reachable 3 ways (footer switch, `L` key, `/classic` route). `/` renders `OceanHome` or `Dashboard` depending on it.

### A5. Ocean design language (`components/ocean/ocean.css`, 420 lines)

A **second, parallel token set** (`--ocean-bg0`, `--ocean-accent`, `--ocean-teal`, `--ocean-glass`, `--ocean-font-*`…) that duplicates A2 with different names. Primitives in `OceanUI.tsx` — and their docstring is the best design principle in the codebase:

> *"Presentation-only: they never attach data semantics, so honesty labels always travel with the data passed in."*

- `ScientificBadge` — tones `cyan | teal | ref | live | off | warn`
- `DataSourceBadge` — **the mandatory "where does this come from" label**
- `LiveDot` — used only for real telemetry
- Also `GlowButton`, `RiskBar`, `SectionHeader`, `StatusIndicator`, `Timeline`, `AnimatedNumber`

Ambient effects live in `effects.tsx`: `OceanGrid`, `ParticleLayer`, `SonarPulse`, `DepthMarkers` — applied pervasively (`--ocean-*` is referenced ~270× across 5 files).

### A6. UX patterns worth keeping

- **Explainability drawer** — `workspace/EvidenceDrawer.tsx`, plus `TrustBadge`, `UncertaintyGauge`, `DataQualityIndicator`, `IntelligenceGraph`, `WorkflowHeader`.
- **What-if simulation** displayed as an explicit before/after pair.
- **Guided demo** — `DemoGuide` drives the real app through 8 stages, no fake animation.
- **Honesty states** — dedicated `empty-state`, `error-banner`, `skeleton` classes; missing data is textually `NOT AVAILABLE` / `INSUFFICIENT DATA`.
- **Resilience as UX** — every route, the Copilot FAB, and the voice agent each sit in their own `ErrorBoundary`, so one failure can't blank the app.
- **Live-feel telemetry** — pulsing dots, count-up numbers, `LIVE` vs `UPDATED 12S AGO`.

### A7. Measured problems (the redesign case)

| Problem | Evidence |
|---|---|
| **Tokens duplicated 3×** | `index.css :root`, `ocean.css :root` (`--ocean-*` ×25), `.theme-classic` override block |
| **Token discipline has collapsed** | **568 hardcoded hex literals, 124 unique values** across the CSS |
| **~14.6k lines of hand-written CSS** | spread over 31 files; `DigitalTwin.css` alone is 1,199 lines |
| **Dual theme ≈ dual maintenance** | every colour decision must be made twice, and the two only superficially differ |
| **Accessibility is partial** | 71 `aria-*`, 29 `role=`, 6 files with `focus-visible` — but only **4 of 31** CSS files honour `prefers-reduced-motion`, and the app is animation-heavy |
| **Perf vs. beauty conflict** | **24 `backdrop-filter`** layers over a heavy CesiumJS 3D globe; Cesium is already a ~4.8 MB lazy chunk |
| **z-index sprawl** | values climb to **1210** with no documented layering scale |
| **10px uppercase mono labels everywhere** | `--fs-label: 10px` — below accessible minimum for the app's primary scan target |
| **Serif display font for a telemetry tool** | Fraunces set on `h1`/`h2` globally, in tension with "instrument panel" intent |
| **Scope sprawl in the UI** | 21 pages / 19 routes for a hackathon build; several overlap |

---

## Part B — The redesign prompt

Copy everything inside the fenced block.

```text
You are a senior product designer + front-end architect. Redesign the UI/UX of
"TidalTwin" — a 4D ocean digital twin and model-validation decision platform.
Deliver a design system + screen designs, not just a palette.

═══ THE PRODUCT ═══

TidalTwin streams live ocean observations (Open-Meteo, Argo floats, NOAA ERSST
v5 SST, VIIRS/Himawari chlorophyll, gliders, CTD, NetCDF model grids) onto a
CesiumJS 3D globe for the Indian Ocean, then does something no ocean viewer
does: it compares the MODEL against OBSERVED reality field by field, scores
observation confidence, flags model–observation disagreement, explains WHY, and
pushes a decision (safety advisory, alert, risk briefing) to a coastal command
centre.

Its core innovation is "TIDE-Loop":
  MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION → BETTER DECISION → VALIDATION ↺
TIDE scores where the next observation should be prioritised using a transparent
formula: value = decision_impact × uncertainty × data_gap × anomaly_persistence
÷ observation_cost. Every score must be inspectable and attributable.

The 3D globe is the INTERFACE. Validation is the PRODUCT.

═══ WHO USES IT ═══

1. Coastal command-centre operator ("CMD OPS") — primary. Wants status at a
   glance, alerts, and a defensible next action. Scans, rarely reads.
2. Marine scientist — wants evidence, provenance, uncertainty, and method.
3. Coastal manager / policymaker — wants impact and cost of being wrong.
4. Fisherman / field user — wants a plain-language safety advisory.
Design must let #1 fly through at speed while #2 can drill to raw evidence.

═══ THE 9-STAGE WORKFLOW (this IS the information architecture) ═══

OBSERVE → DETECT → INVESTIGATE → UNDERSTAND → PRIORITIZE → OBSERVE NEXT →
SIMULATE → DECIDE → VALIDATE   (then the loop repeats)

The current nav rail already exposes these 9 stages and each maps to a real
route. PRESERVE THIS CONCEPT — it is the strongest idea in the product. A user
must always know which stage they are in, what came before, and what is next.
Today it is a thin strip of tiny numbered cells; make it a first-class,
legible orientation device.

CURRENT ROUTES TO COVER (consolidate if it improves clarity — 19 routes is too
many, and several overlap):
  /                     Mission Control (overview)
  /globe                Digital Twin (Cesium 3D)
  /monitoring           Monitoring & Alerts
  /validate             Model Validation  ─┐ these two substantially overlap
  /tide/validation      TIDE Validation   ─┘
  /anomalies            Anomaly Intel
  /forensics            Ocean Forensics
  /intelligence         Decision Intelligence
  /tide                 TIDE Command Center (the hero screen)
  /tide/replay          Decision Replay (model-only vs TIDE-assisted)
  /oceanvision          Ocean Vision ("What If We Measure Here?")
  /coastal              Coastal Intel (beach, coral, fisheries, SLR, spill)
  /scenarios            Scenario Lab
  /safety               Safety Center (fisherman advisories)
  /risk                 Risk Map
  /stories              Story Mode
  /assistant            Ocean AI Copilot
  /reports              Risk Report

═══ NON-NEGOTIABLE UX INVARIANTS ═══

These are correctness requirements, not styling preferences. A beautiful design
that breaks them has failed.

1. NEVER IMPLY FALSE CERTAINTY. Missing data must read "NOT AVAILABLE",
   "INSUFFICIENT DATA" or "GROUND TRUTH UNAVAILABLE". Never a plausible-looking
   placeholder number, never a zero, never a dash alone. Design a distinct,
   unmistakable visual treatment for absence-of-data that is clearly NOT the
   same as a measured low value.
2. PROVENANCE ALWAYS TRAVELS WITH THE NUMBER. Every displayed value needs its
   source and status visible or one hover away. Statuses are:
   REAL | MODEL_DERIVED | SIMULATED | SYNTHETIC | HISTORICAL. Users must be able
   to tell instantly whether a number was measured, modelled, or simulated.
3. SIMULATED DATA IS UNMISSABLE. Virtual/"what-if" readings and demo rows are
   clearly labelled as simulation and are never persisted. They should look
   related-but-distinct — the same visual family, unmistakably not real.
4. CONFIDENCE ≠ UNCERTAINTY ≠ DATA GAP ≠ DECISION IMPACT ≠ OBSERVATION VALUE.
   These are five distinct quantities. Never merge them into one meter or imply
   they are interchangeable.
5. EVERY RECOMMENDATION IS INSPECTABLE. Any ranking or verdict must open into
   its evidence: the factors, their inputs, and the arithmetic. Design that
   drill-down as a core pattern.
6. DEGRADE HONESTLY. Backend, database, Copilot and voice agent can each be
   independently unavailable. Design the degraded states — partial data, no
   voice, no AI — so the app stays usable and explains what is missing.
7. ACCESSIBILITY. Honour prefers-reduced-motion. Never encode meaning in colour
   alone — colourblind-safe pairs plus a text/icon signal for every state.
   Minimum 12px for data labels (currently 10px, too small). Visible keyboard
   focus throughout; WCAG AA contrast in both themes.

═══ WHAT EXISTS TODAY (be specific about what you are improving) ═══

Design tokens currently live in three competing places: a :root block in
index.css, a duplicate "Ocean v3" token set (--ocean-*) in ocean.css, and a
.theme-classic override block. There are 568 hardcoded hex literals with 124
unique values across 14,600 lines of hand-written CSS in 31 files. There is no
single source of truth. FIX THIS: one canonical token layer, one scale.

Current visual language (default "ocean" theme) — a cinematic deep-ocean
cockpit:
  background   #020C18 deep abyss, with 3 large radial blooms + a 64px cyan grid
  accent       #00D4FF "bioluminescent cyan"; secondary teal #00FFB3
  semantic     ok #00FFB3 · warn #FFB800 · danger #FF3366
  text ramp    #F0F9FF → #A6CBE0 → #6E9CBA → #3F6784
  borders      cyan at 12/22/38/66% alpha
  display type Fraunces (a SERIF) on h1/h2 and the wordmark
  body type    Inter
  data type    JetBrains Mono — used for every number, unit, ID, timestamp
  surfaces     glassmorphism: blur 10/18/28px, near-black shadows, 8–20px radii
  motion       120/220/420ms with cubic-bezier(.22,1,.36,1)
  ambience     scanline card texture, particle layer, sonar pulse, depth markers
  layout       floating 256px glass sidebar + system status bar + 9-stage rail

A second "classic" theme is blue-slate (#22D3EE, Segoe UI, no serif, no
texture) and is switchable at runtime. Honestly assess whether maintaining two
themes is worth it, or whether one excellent theme with a contrast/light
variant serves users better. Recommend and justify.

═══ THE PROBLEMS TO SOLVE ═══

• Token chaos and 124 stray hex values → one canonical design system.
• Glassmorphism + 24 backdrop-filter layers sits on top of a heavy WebGL globe.
  Rebalance beauty vs. frame rate. Define a perf budget.
• Typography is in tension: a serif display face for an instrument panel, and
  10px uppercase mono labels for the app's most-scanned information.
• Only 4 of 31 CSS files honour prefers-reduced-motion, in an animation-heavy UI.
• z-index climbs to 1210 with no layering scale. Define one.
• 19 routes with overlapping purposes (two validation screens, two dashboards).
  Propose a clearer IA.
• First-time users see a dense cockpit. Getting to the TIDE value proposition
  requires a guided demo. The design should make the core value legible without
  a walkthrough.
• Dense data tables, evidence lists and 4D globe controls need real hierarchy,
  not just more glass cards.

═══ DELIVERABLES ═══

1. DESIGN PRINCIPLES — 5–7 named principles derived from the honesty invariants
   above, each with a concrete "so we always / we never" rule.
2. INFORMATION ARCHITECTURE — the 9-stage loop as the spine. Show how 19 routes
   collapse into a coherent, shallower structure. Include the overview screen,
   one stage-detail screen, and the evidence drill-down.
3. TOKEN SYSTEM — canonical colour (with light/contrast variant), type scale,
   spacing, radius, elevation, motion, and a documented z-index scale. Show
   semantic tokens, not raw hex. Every state mapped to a colourblind-safe pair
   PLUS a non-colour signal.
4. TYPOGRAPHY — re-evaluate the three families. Keep a data face (mono is
   correct for measurements). Fix the label sizes. Specify the scale.
5. COMPONENT LIBRARY — status chips, metric cards, evidence drawer, uncertainty
   gauge, before/after simulation pair, provenance badge, data-absence state,
   alert rows, timeline, tables, globe control overlay, the 9-stage rail, the
   Copilot panel. For each: purpose, anatomy, states, and accessibility notes.
6. SCREEN DESIGNS — describe precisely, and illustrate if you can: the TIDE
   Command Center (hero), Digital Twin globe with data overlay, Anomaly/Event
   detail, Validation & benchmark comparison, Decision Replay (model-only vs
   TIDE side by side), Safety advisory (plain-language, fisherman-facing),
   Copilot conversation, and the degraded/offline state.
7. DATA VISUALISATION — codify how MODEL / OBSERVED / DEVIATION are always
   visually distinguishable; how uncertainty is shown; how absence is shown;
   how 4D time is scrubbed. Colourblind-safe. No chartjunk, no 3D pie, no fake
   precision — never print more digits than the data supports.
8. MOTION & PERFORMANCE — motion that communicates state change (data
   arriving, event escalating, action confirmed) and nothing else; a
   reduced-motion variant for every animation; a frame-rate budget for the
   globe route.
9. INTERACTION MODEL — keyboard shortcuts (⌘K for Copilot, plus stage
   navigation), command palette, focus management, a "why am I seeing this?"
   affordance on every AI/derived number.
10. BEFORE / AFTER — a table contrasting current vs. proposed per screen and
    per problem, with the reasoning.

═══ TONE ═══

Operational, not decorative. This is an instrument, not a dashboard demo.
Precision, legibility, and warranted confidence. The aesthetic may stay
cinematic and ocean-derived — depth, light, currents — but every visual flourish
must earn its place at the cost of the operator's attention. When in doubt,
remove.

For each decision, state the trade-off you accepted and the alternative you
rejected. Flag anything that would compromise data honesty, even if it would
look better.
```

---

## Part C — How to use this

1. **Paste Part B as-is** into a design-capable model or a designer's brief.
2. **Attach evidence.** The prompt describes the design; a redesign goes much
   better with screenshots of `Mission Control`, `TIDE Command Center`,
   `/globe`, and `Validation`. `presentation/SCREENSHOT_CHECKLIST.md` already
   lists the shots to capture.
3. **If you want a quick visual before/after**, run the app first
   (`docker compose up --build` → <http://localhost:8080>) and capture the
   current look, so the redesign can be compared against something real.
4. **Land it incrementally.** A full restyle of 14.6k lines of CSS in one pass
   is high-risk. The natural first step is Deliverable 3 (the token system):
   collapse `index.css` `:root`, `ocean.css` `:root` and `.theme-classic` into
   one canonical layer, then replace the 124 stray hex values with semantic
   tokens. Everything after that becomes a mechanical, low-risk migration.
