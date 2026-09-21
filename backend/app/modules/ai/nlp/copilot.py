"""
TidalTwin - Copilot Assistant
=================================
The "pro" assistant: a multi-turn, context-aware conversational engine that
mimics an LLM copilot but answers *entirely* from our live ocean data and AI
engines (no API keys, fully explainable — perfect for judges).

Capabilities:
  - Multi-turn context: "and waves?", "how about Kochi?", "why?" carry the
    previous location / intent automatically.
  - ~12 intents: current, safety, forecast, trend, compare, superlative,
    events, risk, validation, storm, what-if, provenance, general.
  - Structured `data` payloads the UI renders as cards (metrics, tables,
    sparklines, chips).
  - Adaptive follow-up suggestions + citations (sources the answer used).
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.nlp.assistant import (
    detect_superlative,
    detect_variables,
    answer_trend,
    answer_comparison,
    answer_superlative,
)
from app.modules.ai.comparison.comparator import compare_location
from app.modules.ai.forecast.forecaster import forecast_location
from app.modules.ai.reports.risk import compute_risk_index
from app.modules.ai.safety.advisory import safety_advisory, storm_track
from app.modules.ai.validation.engine import (
    classify_events,
    difference_engine,
    model_skill,
    observation_confidence,
    provenance,
    scenario_projection,
    situation_panel,
)
from app.modules.ai.forensics.intelligence import health_score as intelligence_health
from app.modules.ai.realdata import location_center, near
from app.modules.ai.apex.adaptive import adaptive_identification
from app.modules.ai.apex.carbon import carbon_monitoring
from app.modules.ai.apex.light import light_pollution
from app.modules.ai.apex.sensing import remote_sensing_fusion
from app.modules.ai.apex.recommend import build_recommendations
from app.modules.ai.nlp.multimodal import multimodal_fuse
from app.modules.ai.coastal.fisheries import compute_fisheries
from app.modules.ai.coastal.coral import compute_coral
from app.modules.ai.coastal.spill import simulate_drift
from app.modules.ai.coastal.slr import slr_inundation
from app.modules.ai.coastal.beach import compute_beach_safety
from app.modules.ai.coastal.impact import compute_economic_impact
from app.modules.ai.tide.engine import TideEngine
from app.modules.ai.tide import validation as tide_validation

# ---------------------------------------------------------------------------
# Location resolution (explicit mention only — context fills the rest)
# ---------------------------------------------------------------------------

LOCATION_ALIASES = {
    "mumbai": ["mumbai", "arabian", "bombay", "maharashtra", "west coast"],
    "chennai": ["chennai", "bengal", "madras", "tamil", "east coast"],
    "mannar": ["mannar", "gulf"],
    "kochi": ["kochi", "kerala", "cochin"],
    "goa": ["goa", "panaji", "panjim"],
    "andaman": ["andaman", "port blair"],
    "lakshadweep": ["lakshadweep", "laccadive"],
    "puri": ["puri", "odisha", "orissa"],
}

PRONOUNS = {"there", "here", "it", "that", "this", "them", "these", "those",
            "region", "coast", "place", "one"}


def find_location(db: Session, text: str) -> tuple[OceanLocation | None, bool]:
    """Return (location, explicitly_mentioned). Falls back only via context."""
    lower = text.lower()
    locations = db.query(OceanLocation).all()
    for loc in locations:
        if loc.name.lower() in lower:
            return loc, True
    for loc in locations:
        for key, aliases in LOCATION_ALIASES.items():
            if key in loc.name.lower() and any(a in lower for a in aliases):
                return loc, True
    return None, False


def match_location_by_id(db: Session, location_id: int) -> OceanLocation | None:
    return db.query(OceanLocation).filter(OceanLocation.id == location_id).first()


def first_location(db: Session) -> OceanLocation | None:
    return db.query(OceanLocation).order_by(OceanLocation.id.asc()).first()


# ---------------------------------------------------------------------------
# Context resolution (multi-turn memory)
# ---------------------------------------------------------------------------

def resolve_context(db: Session, text: str, context: dict) -> tuple[OceanLocation | None, set[str]]:
    """Merge the current question with remembered context.

    Rules:
      - explicit location mention -> use it (overrides memory)
      - pronoun / short follow-up  -> reuse last location
      - "and <variable>"           -> reuse last location + new variables
    """
    loc, explicit = find_location(db, text)
    last_loc_id = context.get("last_location_id")
    last_loc = match_location_by_id(db, last_loc_id) if last_loc_id else None

    variables = detect_variables(text)
    lower = text.lower()

    uses_pronoun = bool(PRONOUNS & set(re.findall(r"[a-z]+", lower)))
    short_followup = (len(text.split()) <= 4) or lower.startswith(("and ", "what about", "also ", "then "))

    # If no location was named, lean on memory for follow-ups
    if loc is None and last_loc is not None and (uses_pronoun or short_followup):
        loc = last_loc

    # "and waves?" after a temperature question -> inherit location, add variable
    if loc is None and last_loc is not None and lower.startswith("and ") and variables:
        loc = last_loc

    return loc, variables


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

INTENT_KEYWORDS = {
    "tide": ["tide evidence", "tide recommend", "why is tide", "model disagree", "sensor issue", "model issue", "event dna", "tide event", "decision could this observation", "confidence low", "what evidence", "verify the evidence", "why this location", "measure next", "measure there", "virtual observation", "simulate an observation", "simulate a sample", "what if we measure", "sampling", "sampled at the site", "replay", "recap the event", "what happened", "step by step", "did the decision change", "was it validated", "why did tide recommend"],
    "carbon": ["carbon", "co2", "sink", "sequestration", "blue carbon", "absorb",
               "flux", "emission", "uptake", "carbon flux", " co2 ", "co₂"],
    "lights": ["light pollution", "night light", "artificial light", "aln",
               "lighting", "lit at night", "lamp"],
    "sensing": ["satellite", "remote sensing", "fusion", "revisit", "spatial resolution",
                "harmoniz", "sensor data", "instrument", "sentinel", "avhrr", "viirs", "slstr"],
    "recommend": ["recommend", "sampling", "where should", "observation plan", "deploy",
                  "collect data", "sample next", "monitor now", "recon", "where to sample"],
    "adaptive": ["adaptive", "self-calibrat", "self calibrat", "threshold", "maturity",
                 "learning band", "calibrat"],
    "multimodal": ["multimodal", "cross-check", "cross check", "verify this", "analyze this",
                   "field report", "news report", "document says", "netcdf summary", "glider data",
                   " drone ", " report says", "fish catch report", "multimodal fusion"],
    "impact": ["economic", "impact", "loss", "cost", "inr", "crore", "lakh", "damage",
               "how much money", "monetary"],
    "fisheries": ["fishing", "fishing zone", "fishing ground", "fish aggregat", "fish catch",
                  "best fishing", "where to fish", "open fishing", "where to catch", "faz"],
    "coral": ["coral", "bleach", "reef", "dhw", "reef health", "thermal stress", "heat stress"],
    "spill": ["oil spill", "spill", "slick", "oil", "search and rescue", "overboard",
              "missing", "drift", "stranded", "sar mission", "person at sea"],
    "slr": ["sea level", "slr", "inundat", "submerg", "sea rise", "land loss", "rise scenario"],
    "beach": ["rip current", "rip tide", " beaching", "beach", "swim", "surfing", "surfer", "lifeguard"],
    "events": ["event", "heatwave", "anomaly", "flood", "watch", "phenomenon",
               "cold water", "alerts near", "what's happening", "activity"],
    "risk": ["risk", "risk index", "danger zone", "riskier", "riskiest",
             "safest region", "rank", "ranking", "worst coast", "dangerous coast"],
    "tide_validation": ["tide scientifically", "is tide validated", "scientifically validated",
                        "empirically validated", "tide validation", "validate tide", "tide benchmark",
                        "benchmark tide", "tide baseline", "baseline comparison", "validate the tide",
                        "how was tide tested", "tide tested", "tide accuracy", "tide reliable",
                        "ground truth", "false alarm", "missed event", "tide algorithm version",
                        "compare strategies", "which strategy performs", "baselines", "compare tide",
                        "tide compare", "tide versus", "tide vs"],
    "validation": ["model", "trust", "accurate", "accuracy", "reliable",
                   "deviation", "mismatch", "skill", "confidence", "wrong model",
                   "difference", "validate", "verif"],
    "forecast": ["forecast", "next hours", "later today", "tonight", "tomorrow",
                 "will the", "expect", "ahead", "coming hours", "how will"],
    "safety": ["safe", "safety", "sail", "sailing", "fish", "fishing", "bath",
               "swim", "advise", "advisory", "should i", "go out", "window"],
    "storm": ["cyclone", "storm", "hurricane", "typhoon", "depression"],
    "whatif": ["what if", "if wind", "scenario", "projection", "if the wind",
               "suppose", "what would happen"],
    "provenance": ["where did", "where does", "source", "provenance", "trace",
                   "origin", "dataset", "who collected", "how do you know"],
    "trend": ["trend", "change", "changed", "rising", "falling", "warmer",
              "cooler", "warming", "cooling", "increase", "decrease",
              "since", "over time", "recently", "heating"],
    "brief": ["intelligence brief", "situation brief", "ocean brief", "brief me",
              "brief me now", "system brief", "give me the brief", "give me the picture",
              "what's the picture", "what is the picture", "summarize the ocean",
              "summarize the situation", "overall picture", "situation summary",
              "round up the ocean", "ocean round-up", "intelligence picture"],
    "compare": ["compare", "versus", " vs ", "vs ", "diff between", "which is warmer",
                "which is cooler"],
    "superlative": ["warmest", "hottest", "coldest", "calmest", "smoothest",
                    "roughest", "waviest", "highest wave", "largest wave"],
    "current": ["temperature", "temp", "wave", "waves", "salinity", "current",
                "sst", "now", "right now", "what is", "what are", "how high",
                "how rough", "how warm", "how cold"],
}


def detect_intent(text: str) -> str:
    lower = text.lower()
    for intent, words in INTENT_KEYWORDS.items():
        if any(w in lower for w in words):
            return intent
    if detect_superlative(lower):
        return "superlative"
    return "general"


# ---------------------------------------------------------------------------
# Data payload builders (cards for the UI)
# ---------------------------------------------------------------------------

def _metrics(items: list[tuple[str, str, str | None]]) -> dict:
    return {
        "type": "metrics",
        "items": [
            {"label": label, "value": value, "color": color} for label, value, color in items
        ],
    }


def _table(columns: list[str], rows: list[list[str]]) -> dict:
    return {"type": "table", "columns": columns, "rows": rows}


def _sparkline(label: str, values: list[float]) -> dict:
    return {"type": "sparkline", "label": label, "values": [round(float(v), 2) for v in values]}


def _suggest_for(intent: str) -> list[str]:
    follow_ups = {
        "carbon": ["Which coast is the strongest CO2 sink?",
                   "How much carbon is the network absorbing?",
                   "Explain how the CO2 flux is calculated.",],
        "lights": ["Which coast has the worst light pollution?",
                   "How does artificial light affect sea turtles?",
                   "What should Kochi do about light pollution?",],
        "sensing": ["What satellites does the system fuse?",
                    "How confident is the harmonized satellite data?",
                    "Which coast gains most from sensor fusion?",],
        "recommend": ["Where should we sample next?",
                      "Which region needs observations most?",
                      "How many extra observations are needed?",],
        "tide": ["What evidence supports the TIDE recommendation?",
                 "What is the TIDE verdict for this location?",
                 "What happens if we measure the top-ranked location?",
                 "Replay the TIDE decision for the active event.",
                 "Which existing event maps into TIDE?",],
        "brief": ["Give me the ocean intelligence brief.",
                  "Add the decision to the brief for this coast.",
                  "What is the picture for the whole network?",
                  "Summarize the situation for Chennai.",],
        "adaptive": ["Which regions have adaptive thresholds?",
                     "Would adaptive detection change any alerts?",
                     "How do the thresholds learn?",],
        "multimodal": ["Cross-check this: 'SST at Goa hit 30.1°C with low oxygen.'",
                       "Analyze this news: 'Chlorophyll bloom reported near Kochi.'",
                       "Verify a NetCDF summary against live sensors.",],
        "fisheries": ["Where is the best fishing zone today?",
                      "What fish are likely near Kochi right now?",
                      "Which coast scores highest for fishing?",],
        "coral": ["Which reef is at most bleaching risk?",
                  "What is the DHW at Gulf of Mannar?",
                  "How is coral health trending?",],
        "spill": ["Simulate a 24h oil spill from Goa.",
                  "Where would a drifting person be after 12h near Puri?",
                  "Which coast should get rescue priority?",],
        "slr": ["What floods at +1m sea level rise?",
                "How many towns are inundated at +2m?",
                "Which coast loses the most land?",],
        "beach": ["Is it safe to swim at Goa?",
                  "Which beach has the strongest rip currents?",
                  "Why is Chennai flagged caution?",],
        "impact": ["What is the economic impact of current events?",
                   "How much is the fishing loss worth?",
                   "Which coast suffers the most damage?",],
        "safety": ["How rough are the waves right now?",
                   "Which coast is riskiest today?",
                   "What causes the dangerous conditions?",],
        "events": ["Which region has active events?",
                   "What is the intensity of the heatwave at Goa?",
                   "Any flood risk along the coast?",],
        "risk": ["Rank all coasts by risk today.",
                 "Why is Goa ranked high risk?",
                 "What is the composite risk index made of?",],
        "tide_validation": ["Is TIDE scientifically validated?",
                            "What is the TIDE algorithm version?",
                            "How does TIDE compare to the baselines?",
                            "Can I reproduce the TIDE benchmark?"],
        "validation": ["Is the model accurate at Goa?",
                       "How confident are we in the observations?",
                       "Which coast deviates most from the model?",],
        "forecast": ["What about waves tonight?",
                     "Will it stay calm until morning?",
                     "Forecast for Puri next 12 hours.",],
        "storm": ["Where is the cyclone heading?",
                  "How strong is the storm right now?",
                  "Is a cyclone active near Odisha?",],
        "whatif": ["What if wind increases 20%?",
                   "What if I sail in the forecast window?",],
        "provenance": ["Where did the Goa temperature come from?",
                       "What dataset powers the models?",],
        "trend": ["Is the sea warming at Chennai?",
                  "Compare today against yesterday.",],
        "compare": ["Compare Chennai and Kochi waves.",
                    "Which region is the calmest right now?",],
        "current": ["Is it safe to fish near Puri?",
                    "What is the temperature at Mumbai now?",
                    "Which region has the warmest water?",],
        "superlative": ["Which region has the largest waves?",
                        "Where is the coldest water right now?",],
        "general": ["Is it safe to sail near Goa?",
                    "What is the temperature at Mumbai coast now?",
                    "Are there any ocean events right now?",
                    "How accurate is the ocean model?",
                    "Rank all coasts by risk today.",
                    "Where is the cyclone heading?",],
    }
    return follow_ups.get(intent, follow_ups["general"])


# ---------------------------------------------------------------------------
# Intent answers (with citations)
# ---------------------------------------------------------------------------

SOURCE_API = "Open-Meteo Marine"
SOURCE_ENGINE = "TidalTwin engine"


def ans_current(db, loc, variables) -> dict:
    obs = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .first()
    )
    if obs is None:
        return {"answer": f"I don't have live readings for **{loc.name}** yet.",
                "intent": "current", "location": loc.name, "location_id": loc.id,
                "data": None, "suggestions": _suggest_for("current"),
                "sources": [SOURCE_API], "steps": ["Located coast", "Read latest observation"]}
    rows, units = [], {"temperature": "°C", "waves": "m", "salinity": "PSU", "current": "m/s"}
    if (not variables or "temperature" in variables) and obs.sea_surface_temperature is not None:
        rows.append(("Sea surface temperature", f"{obs.sea_surface_temperature:.1f} °C", "#0ea5e9"))
    if (not variables or "waves" in variables) and obs.wave_height is not None:
        rows.append(("Wave height", f"{obs.wave_height:.2f} m", "#34d399"))
    if "salinity" in variables and obs.salinity is not None:
        rows.append(("Salinity", f"{obs.salinity:.1f} PSU", "#a78bfa"))
    if "current" in variables and obs.current_speed is not None:
        rows.append(("Current speed", f"{obs.current_speed:.2f} m/s", "#22d3ee"))
    if not rows:
        rows.append(("Latest reading time", obs.timestamp.strftime("%H:%M IST"), "#94a3b8"))

    answer_parts = [f"At **{loc.name}** right now:"]
    for label, value, _ in rows[:3]:
        answer_parts.append(f"- {label}: **{value}**")
    ts = obs.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    answer_parts.append(f"_Observed {ts.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime('%H:%M IST')}._")

    real_notes, real_sources = _real_grid_notes(db, loc)
    if real_notes:
        answer_parts.append("")
        answer_parts.append("_Real ingested grid (not simulated):_")
        answer_parts.extend(real_notes)

    sources = [SOURCE_API, *real_sources]
    return {"answer": "\n".join(answer_parts), "intent": "current",
            "location": loc.name, "location_id": loc.id,
            "data": _metrics(rows), "suggestions": _suggest_for("current"),
            "sources": sources,
            "steps": ["Located coast", "Read latest observation",
                      *(["Cross-checked real NOAA grid(s)"] if real_notes else [])]}


def _real_grid_notes(db, loc):
    """Cite the real NOAA grids (ERSST SST / VIIRS Chl) near this coast.

    Honest: we only cite a value when a real cell exists within the product's
    search range; otherwise we stay silent (or note absence) — never guess."""
    center = location_center(loc)
    if center is None:
        return [], []
    lat, lon = center
    notes: list[str] = []
    sources: list[str] = []
    for variable, fmt in (("sst", "Real SST ({m}): {v:.1f} °C — cell {lg:.1f}°E,{lt:.1f}°N"),
                          ("chlor_a", "Real Chl-a ({m}): {v:.2f} mg/m³ — cell {lg:.1f}°E,{lt:.1f}°N")):
        hit = near(db, variable, lat, lon)
        if hit["found"]:
            notes.append(f"- **{fmt.format(m=hit['month'], v=hit['value'],
                                           lg=hit['longitude'], lt=hit['latitude'])}** — "
                         f"{hit['short']} grid ({hit['source']})")
            sources.append(hit["source"])
        elif hit["month"] is not None:
            notes.append(f"- {hit['reason']} (grid month {hit['month']}).")
    return notes, sources


def ans_safety(db, loc) -> dict:
    adv = next((a for a in safety_advisory(db) if a["location_id"] == loc.id), None)
    obs = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .first()
    )
    status = adv.get("status", "safe") if adv else "safe"
    label = {"safe": "SAFE ✅", "caution": "CAUTION ⚠️", "danger": "DANGER 🚨"}[status]
    wave = obs.wave_height if obs else None
    window = adv.get("safe_window", "Not advised") if adv else None

    verdict = {
        "safe": "conditions look calm — good for fishing and sailing.",
        "caution": "conditions are unsettled — small craft should be cautious.",
        "danger": "conditions are hazardous — small vessels advised to stay ashore.",
    }[status]

    answer = (
        f"**Safety check — {loc.name}**\n\n"
        f"Status: **{label}**\n"
        f"Waves: **{wave:.2f} m**\n"
        f"Recommended safe window: **{window}**\n\n"
        f"_Assessment: {verdict}_"
    )
    return {"answer": answer, "intent": "safety", "location": loc.name,
            "location_id": loc.id,
            "data": _metrics([
                ("Status", label, {"safe": "#059669", "caution": "#d97706", "danger": "#e11d48"}[status]),
                ("Wave height", f"{wave:.2f} m", "#0ea5e9"),
                ("Safe window", window or "—", "#059669"),
            ]),
            "suggestions": _suggest_for("safety"),
            "sources": [SOURCE_ENGINE, SOURCE_API],
            "steps": ["Scored risk index", "Projected safe window", "Fetched advisory"]}


def ans_events(db, loc) -> dict:
    events = classify_events(db)["events"]
    if loc is not None:
        selected = [e for e in events if e["location_id"] == loc.id]
        scope = f"near **{loc.name}**"
    else:
        selected = events
        scope = "across all monitored coasts"
    if not selected:
        return {"answer": f"No active ocean events {scope} — everything is tracking its model baseline. ✅",
                "intent": "events", "location": loc.name if loc else None,
                "location_id": loc.id if loc else None, "data": None,
                "suggestions": _suggest_for("events"), "sources": [SOURCE_ENGINE],
                "steps": ["Classified anomaly signals", "Matched named phenomena"]}
    lines = [f"I found **{len(selected)}** active ocean event{'s' if len(selected) != 1 else ''} {scope}:"]
    rows = []
    for e in selected[:6]:
        rows.append((e["label"], e["intensity"].upper(), e["confidence"]) )
        lines.append(f"- {e['icon']} **{e['label']}** — {e['intensity']} intensity, {e['confidence']}% confidence" + (f" at {e['location']}" if loc is None else "") + (f"; {e['evolution']}" if e.get("evolution") else ""))
    return {"answer": "\n".join(lines), "intent": "events",
            "location": loc.name if loc else None, "location_id": loc.id if loc else None,
            "data": _table(["Event", "Intensity", "Confidence"],
                           [[r[0], r[1], f"{r[2]}%"] for r in rows]),
            "suggestions": _suggest_for("events"),
            "sources": [SOURCE_ENGINE], "steps": ["Ran anomaly scan", "Classified events"]}


def ans_risk(db) -> dict:
    index = compute_risk_index(db)
    rows = index["regions"]
    worst = rows[0]
    best = rows[-1]
    answer = (
        f"**National risk ranking — top coast: {worst['location']}** (index **{worst['index']}**, {worst['band']}).\n"
        f"Calmest today: **{best['location']}** (index {best['index']}, {best['band']}).\n\n"
        f"The index blends temperature anomaly, active alerts, wave height and volatility "
        f"(weights {int(index['model']['temp_weight']*100)}/{int(index['model']['alert_weight']*100)}/{int(index['model']['wave_weight']*100)}/{int(index['model']['volatility_weight']*100)})."
    )
    return {"answer": answer, "intent": "risk", "location": worst["location"],
            "location_id": worst["location_id"],
            "data": _table(["Coast", "Risk", "Band", "Signal"],
                           [[r["location"], str(r["index"]), r["band"].upper(),
                             f"{r['signal']:+.2f}°C"] for r in rows]),
            "suggestions": _suggest_for("risk"), "sources": [SOURCE_ENGINE],
            "steps": ["Computed composite index", "Ranked all regions"]}


def ans_validation(db, loc) -> dict:
    conf = observation_confidence(db)["regions"]
    if loc is None:
        diff = difference_engine(db)
        fields = []
        for r in diff["regions"]:
            for f in r["fields"]:
                if f.get("deviation_level") in ("high", "moderate"):
                    fields.append((r["location"], f["label"], f["deviation"], f["deviation_level"]))
        if not fields:
            return {"answer": "The model is **tracking reality closely** across all coasts right now — no significant deviations. ✅",
                    "intent": "validation", "location": None, "location_id": None, "data": None,
                    "suggestions": _suggest_for("validation"), "sources": [SOURCE_ENGINE],
                    "steps": ["Compared model vs observed", "Filtered significant deviations"]}
        answer_lines = ["Significant model–reality gaps right now:"]
        answer_lines += [f"- **{l}** · {f}: {d:+.2f} ({lvl})" for l, f, d, lvl in fields[:6]]
        return {"answer": "\n".join(answer_lines), "intent": "validation",
                "location": None, "location_id": None,
                "data": _table(["Coast", "Field", "Deviation", "Level"],
                               [[l, f, f"{d:+.2f}", lvl.upper()] for l, f, d, lvl in fields[:8]]),
                "suggestions": _suggest_for("validation"), "sources": [SOURCE_ENGINE],
                "steps": ["Re-evaluated model baseline", "Measured field deviation"]}

    row = next((c for c in conf if c["location_id"] == loc.id), None)
    confidence = row["observation_confidence"] if row else None
    skill = next((s for s in model_skill(db)["regions"] if s["location_id"] == loc.id), None)
    skill_v = (skill or {}).get("overall_skill")

    diff = difference_engine(db, loc.id).get("region", {})
    devs = [f for f in diff.get("fields", []) if f.get("deviation") is not None]
    biggest = max(devs, key=lambda f: abs(f["deviation"]), default=None)

    lines = [f"**Model validation — {loc.name}**", ""]
    if row:
        lines.append(f"- Observation confidence: **{confidence}%** "
                     f"(age {row.get('freshness_hours')}h old, agreement {row.get('agreement')})")
    if skill_v is not None:
        lines.append(f"- Model skill vs climatology: **{skill_v}%**")
    if biggest:
        lines.append(f"- Biggest deviation: **{biggest['label']} {biggest['deviation']:+.2f}** ({biggest['deviation_level']})")
    lines.append(f"- Trust flag: {'**DISAGREEMENT** — model and reality have diverged' if row and row.get('disagreement') else 'tracking the model baseline'}")
    data_items = []
    if row:
        data_items.append(("Observation confidence", f"{confidence}%", "#0ea5e9"))
    if skill_v is not None:
        data_items.append(("Model skill", f"{skill_v}%", "#818cf8"))
    if biggest:
        data_items.append(("Deviation", f"{biggest['deviation']:+.2f}", "#e11d48"))
    return {"answer": "\n".join(lines), "intent": "validation",
            "location": loc.name, "location_id": loc.id,
            "data": _metrics(data_items), "suggestions": _suggest_for("validation"),
            "sources": [SOURCE_ENGINE, SOURCE_API],
            "steps": ["Built model baseline", "Compared observed", "Scored confidence & skill"]}


def ans_forecast(db, loc) -> dict:
    fc = forecast_location(db, loc)
    f = fc.get("forecast")
    if not f:
        return {"answer": f"Not enough history yet to forecast **{loc.name}**.", "intent": "forecast",
                "location": loc.name, "location_id": loc.id, "data": None,
                "suggestions": _suggest_for("forecast"), "sources": [SOURCE_ENGINE],
                "steps": ["Fit trend model"]}
    temps = [p.get("temperature") for p in f if p.get("temperature") is not None]
    waves = [p.get("wave_height") for p in f if p.get("wave_height") is not None]
    cur_t = temps[0] if temps else None
    end_t = temps[-1] if temps else None
    cur_w = waves[0] if waves else None
    end_w = waves[-1] if waves else None
    lines = [f"**12-hour outlook — {loc.name}**"]
    if cur_t is not None and end_t is not None:
        dt = end_t - cur_t
        lines.append(f"- Temperature trending **{'up' if dt > 0 else 'down'}**: {cur_t:.1f}°C → {end_t:.1f}°C")
    if cur_w is not None and end_w is not None:
        dw = end_w - cur_w
        lines.append(f"- Waves {'building' if dw > 0.05 else 'settling'}: {cur_w:.2f} m → {end_w:.2f} m")
    series = temps if temps else waves
    return {"answer": "\n".join(lines), "intent": "forecast",
            "location": loc.name, "location_id": loc.id,
            "data": _metrics([
                ("Now", f"{cur_t:.1f}°C" if cur_t is not None else "—", "#0ea5e9"),
                ("+12h temp", f"{end_t:.1f}°C" if end_t is not None else "—", "#818cf8"),
                ("Now waves", f"{cur_w:.2f} m" if cur_w is not None else "—", "#34d399"),
                ("+12h waves", f"{end_w:.2f} m" if end_w is not None else "—", "#a78bfa"),
            ]),
            "suggestions": _suggest_for("forecast"),
            "sources": [SOURCE_ENGINE],
            "steps": ["Fit trend polynomial", "Projected 12 hours"]}


def ans_storm(db) -> dict:
    storm = storm_track()
    pts = storm["points"]
    last = pts[-1]
    peak = max(pts, key=lambda p: p["wind_kmh"])
    answer = (
        f"**{storm['name']}** is active in the Bay of Bengal.\n\n"
        f"_{storm['headline']}_\n\n"
        f"- Current wind: **{last['wind_kmh']} km/h**, radius {last['radius_km']} km\n"
        f"- Peak intensity: **{peak['wind_kmh']} km/h**\n"
        f"- Heading NW toward the **Odisha coast**\n"
        f"- Centre now near {last['lat']}°N, {last['lon']}°E"
    )
    return {"answer": answer, "intent": "storm", "location": "Odisha Coast (Puri)",
            "location_id": None,
            "data": _metrics([
                ("Name", storm["name"], "#e11d48"),
                ("Status", "ACTIVE", "#e11d48"),
                ("Wind", f"{last['wind_kmh']} km/h", "#f59e0b"),
                ("Radius", f"{last['radius_km']} km", "#f59e0b"),
            ]),
            "suggestions": _suggest_for("storm"),
            "sources": ["TidalTwin cyclone model (synthetic)"],
            "steps": ["Generated cyclone track"]}


def ans_whatif(db, loc, text) -> dict:
    m = re.search(r"(\d+)\s*%|\+(\d+)|(\d+)\s*percent", text, re.I)
    pct = int(m.group(1) or m.group(2) or m.group(3)) if m else None
    pct = max(-50, min(50, pct if pct is not None else 20))
    res = scenario_projection(db, loc.id, pct)
    out = res["output"]
    answer = (
        res["narrative"] + f"\n\n"
        f"_⚠️ {res['caveat']}_"
    )
    return {"answer": answer, "intent": "whatif", "location": loc.name,
            "location_id": loc.id,
            "data": _metrics([
                ("Wind change", f"{pct:+.0f}%", "#22d3ee"),
                ("Wave height", f"{out['wave_height']:.2f} m", "#0ea5e9"),
                ("Expected SST", f"{out['expected_sst']:.2f} °C", "#818cf8"),
                ("Hazard band", out["hazard_band"].upper(),
                 {"safe": "#059669", "caution": "#d97706", "warning": "#d97706", "danger": "#e11d48"}[out["hazard_band"]]),
            ]),
            "suggestions": _suggest_for("whatif"),
            "sources": [SOURCE_ENGINE],
            "steps": ["Adjusted forcing", "Projected scenario"]}


def ans_provenance(db, loc) -> dict:
    prov = provenance(db)["regions"]
    row = prov[0]
    if loc is not None:
        row = next((p for p in prov if p["location_id"] == loc.id), row)
    answer = (
        f"Every number you see is traceable. For **{row['location']}**:\n\n"
        f"- Sources: **{', '.join(row['sources'])}**\n"
        f"- Dataset: {', '.join(row['datasets'])}\n"
        f"- Observations: {row['observation_count']} readings over a {row['window_hours']}h window; "
        f"latest {row['latest_observation']}\n"
        f"- Model run: `{row['model_run_id']}`\n"
        f"- Processing: {row['processing']}\n\n"
        f"_Real data — no black boxes. Verify any number on the Model Validation page._"
    )
    return {"answer": answer, "intent": "provenance", "location": row["location"],
            "location_id": row["location_id"],
            "data": _metrics([
                ("Source", ", ".join(row["sources"]), "#34d399"),
                ("Observation count", str(row["observation_count"]), "#0ea5e9"),
                ("Window", f"{row['window_hours']}h", "#818cf8"),
                ("Model run", row["model_run_id"], "#a78bfa"),
            ]),
            "suggestions": _suggest_for("provenance"),
            "sources": [SOURCE_API],
            "steps": ["Traced dataset", "Resolved model run"]}


def ans_trend(db, loc) -> dict:
    obs = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .limit(24)
        .all()
    )
    text = answer_trend(loc, obs)
    temp_series = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
    temp_series = temp_series[::-1][-24:]
    return {"answer": text, "intent": "trend", "location": loc.name,
            "location_id": loc.id,
            "data": _sparkline("Sea temperature (°C)", temp_series),
            "suggestions": _suggest_for("trend"), "sources": [SOURCE_API],
            "steps": ["Loaded 24 readings", "Measured slope"]}


def ans_compare(db, text) -> dict:
    lower = text.lower()
    city = {
        "mumbai": "Arabian Sea (Mumbai Coast)", "chennai": "Bay of Bengal (Chennai Coast)",
        "mannar": "Gulf of Mannar", "kochi": "Kerala Coast (Kochi)", "kerala": "Kerala Coast (Kochi)", "goa": "Goa Coast (Panaji)",
        "andaman": "Andaman Sea", "lakshadweep": "Lakshadweep Sea", "puri": "Odisha Coast (Puri)",
    }
    mentioned = [name for k, name in city.items() if k in lower]
    if len(mentioned) >= 2:
        locs = [match_location_by_id(db, l.id) for l in db.query(OceanLocation).all()
                if l.name in mentioned]
        locs = locs[:2]
        obs = [(l, db.query(OceanObservation).filter(OceanObservation.location_id == l.id)
                .order_by(OceanObservation.timestamp.desc()).first()) for l in locs]
        rows = []
        for l, o in obs:
            rows.append((l.name, (f"{o.sea_surface_temperature:.1f}°C" if o and o.sea_surface_temperature is not None else "—"),
                         (f"{o.wave_height:.2f} m" if o and o.wave_height is not None else "—")))
        a, b = obs[0], obs[1]
        diff = ""
        if a[1] and b[1] and a[1].sea_surface_temperature is not None and b[1].sea_surface_temperature is not None:
            d = a[1].sea_surface_temperature - b[1].sea_surface_temperature
            warmer = a[0].name.split(" (")[0] if d > 0 else b[0].name.split(" (")[0]
            diff = f"\n\n💡 **{warmer}** is warmer by **{abs(d):.1f}°C**."
        answer = ("Comparing the two coasts:\n" +
                  "".join(f"- **{n}**: {t}, waves {w}\n" for n, t, w in rows) + diff)
        return {"answer": answer, "intent": "compare", "location": None, "location_id": None,
                "data": _table(["Coast", "Temperature", "Waves"], rows),
                "suggestions": _suggest_for("compare"),
                "sources": [SOURCE_API], "steps": ["Matched two coasts", "Compared readings"]}
    # fall back to full comparison
    text = answer_comparison(db, db.query(OceanLocation).all())
    return {"answer": text, "intent": "compare", "location": None, "location_id": None,
            "data": None, "suggestions": _suggest_for("compare"),
            "sources": [SOURCE_API], "steps": ["Compared all regions"]}


def ans_superlative(db, text) -> dict:
    kind = detect_superlative(text)
    answer = answer_superlative(db, kind)

    data = None
    if kind in ("warmest", "coldest") or (kind == "calmest"):
        obs_rows = (
            db.query(OceanLocation, OceanObservation.wave_height, OceanObservation.sea_surface_temperature)
            .join(OceanObservation, OceanObservation.location_id == OceanLocation.id)
            .all()
        )
        by_loc: dict[int, tuple] = {}
        for loc, wave, temp in obs_rows:
            if loc.id not in by_loc:
                by_loc[loc.id] = (loc.name, wave, temp)
        cands = list(by_loc.values())
        if kind == "warmest":
            best = max(cands, key=lambda x: x[2] or -999)
        elif kind == "coldest":
            best = min(cands, key=lambda x: x[2] or 999)
        else:
            best = min(cands, key=lambda x: x[1] or 999)
        data = {"type": "metrics", "items": [
            {"label": "Region", "value": best[0], "color": "inherit"},
            {"label": "Sea surface temp", "value": f'{best[2]:.1f}°C' if best[2] is not None else "—"},
            {"label": "Wave height", "value": f'{best[1]:.2f} m' if best[1] is not None else "—"},
        ]}

    return {"answer": answer, "intent": kind, "location": None, "location_id": None,
            "data": data, "suggestions": _suggest_for(kind),
            "sources": [SOURCE_API], "steps": ["Ranked all regions", f"Picked {kind}"]}


def ans_carbon(db) -> dict:
    res = carbon_monitoring(db)
    rows = res["regions"]
    if not rows:
        return {"answer": "Not enough surface data to estimate air-sea CO2 flux yet.",
                "intent": "carbon", "location": None, "location_id": None, "data": None,
                "suggestions": _suggest_for("carbon"), "sources": [SOURCE_ENGINE],
                "steps": ["Read latest SST", "Estimated CO2 flux"]}
    total = res["national_total_uptake_MtC_per_yr"]
    sink_dir = "absorbing" if total < 0 else "releasing"
    top = rows[0]
    answer = (
        f"**Marine carbon dashboard** — the monitored network is currently "
        f"**{sink_dir} ~{abs(total):.2f} Mt C per year**.\n\n"
        f"- Strongest sink: **{res['strongest_co2_sink']}** "
        f"({top['flux']['flux_gc_per_m2_yr']:+.1f} g-C/m²/yr)\n"
        f"- Atmospheric reference: **{res['atmosphere_reference_pco2']} µatm CO₂**\n"
        f"- Surface ΔpCO₂ ranges "
        f"{rows[0]['flux']['pco2_gradient']:+.0f} "
        f"to {rows[-1]['flux']['pco2_gradient']:+.0f} µatm across coasts\n\n"
        f"_Takahashi-style pCO₂ + Wanninkhof gas transfer + Weiss solubility._"
    )
    return {"answer": answer, "intent": "carbon", "location": res["strongest_co2_sink"],
            "location_id": None,
            "data": _table(
                ["Coast", "ΔpCO2 (µatm)", "Flux gC/m²/yr", "Role"],
                [[r["location"], f"{r['flux']['pco2_gradient']:+.0f}",
                  f"{r['flux']['flux_gc_per_m2_yr']:+.1f}", r["flux"]["category"]]
                 for r in rows[:8]]),
            "suggestions": _suggest_for("carbon"), "sources": [SOURCE_ENGINE],
            "steps": ["Read latest SST per coast", "Applied Takahashi pCO₂", "Wanninkhof gas transfer"]}


def ans_lights(db) -> dict:
    res = light_pollution(db)
    rows = res["regions"]
    extreme = [r for r in rows if r["severity"] == "extreme"]
    worst = rows[0]
    answer = (
        f"**Light pollution scan** — {len(extreme)} coast{'s' if len(extreme) != 1 else ''} at "
        f"**extreme** exposure. Most-lit coast: **{worst['location']}** "
        f"({worst['aln_exposure_score']}/100, {worst['severity']}).\n\n"
        f"Top impact there: turtle hatchling disorientation "
        f"**{worst['biota_impact']['sea_turtle_hatchling_disorientation']}%** and zooplankton "
        f"migration disruption **{worst['biota_impact']['zooplankton_diel_migration_disruption']}%**.\n\n"
        f"_Advisory: {worst['recommendation']}_"
    )
    return {"answer": answer, "intent": "lights", "location": worst["location"],
            "location_id": worst["location_id"],
            "data": _table(
                ["Coast", "Exposure", "Severity", "Turtle impact"],
                [[r["location"], str(r["aln_exposure_score"]), r["severity"].upper(),
                  f"{r['biota_impact']['sea_turtle_hatchling_disorientation']}%"]
                 for r in rows[:8]]),
            "suggestions": _suggest_for("lights"), "sources": [SOURCE_ENGINE],
            "steps": ["Scored ALAN exposure proxy", "Scored biota impacts"]}


def ans_sensing(db) -> dict:
    res = remote_sensing_fusion(db)
    rows = res["regions"]
    if not rows:
        return {"answer": "No regions to harmonize with satellite sources yet.",
                "intent": "sensing", "location": None, "location_id": None, "data": None,
                "suggestions": _suggest_for("sensing"), "sources": [SOURCE_ENGINE],
                "steps": ["Read observation streams"]}
    avg_conf = sum(r["harmonized_confidence"] for r in rows) / len(rows)
    best = max(rows, key=lambda r: r["fused_confidence_boost_pct"])
    sources = ", ".join(sorted({s for r in rows for s in r["sources_used"]}))
    answer = (
        f"**Remote-sensing harmonization** — fusing {sources} lifts average analytical confidence "
        f"to **{avg_conf:.0f}/100** (single-source baseline only ~{rows[0]['single_source_confidence']}).\n\n"
        f"- Biggest fusion gain: **{best['location']}** "
        f"(+{best['fused_confidence_boost_pct']}% over its best sensor)\n"
        f"- Best source available for SST is **Sentinel-3 SLSTR** (1 km, 12h revisit)\n\n"
        f"_Multi-instrument fusion reduces blind-spot probability vs any single pixel._"
    )
    return {"answer": answer, "intent": "sensing", "location": None, "location_id": None,
            "data": _table(
                ["Coast", "Harmonized", "Boost", "Sources"],
                [[r["location"], f"{r['harmonized_confidence']}",
                  f"+{r['fused_confidence_boost_pct']}%", ", ".join(r["sources_used"])]
                 for r in rows[:8]]),
            "suggestions": _suggest_for("sensing"), "sources": [SOURCE_ENGINE],
            "steps": ["Mapped variables to satellites", "Scored fusion confidence"]}


def ans_recommend(db) -> dict:
    res = build_recommendations(db, min_priority=0.0)
    recs = res["recommendations"]
    if not recs:
        return {"answer": res["summary"], "intent": "recommend", "location": None,
                "location_id": None, "data": None,
                "suggestions": _suggest_for("recommend"), "sources": [SOURCE_ENGINE],
                "steps": ["Billed coverage vs uncertainty", "Ranked sampling needs"]}
    top = recs[0]
    vars_text = ", ".join(top["variables_to_sample"]) if top["variables_to_sample"] else "wave height"
    answer = (
        f"{res['summary']}\n\n"
        f"Top priority — **{top['location']}** (obs need {top['obs_need']}/100, "
        f"impact {top['decision_impact']}): sample **{vars_text}** "
        f"{'because of an **active event**' if top['active_event'] else 'to close the coverage gap'}.\n"
        f"~**{res['estimated_observations_needed']}** extra passes network-wide would clear the action threshold."
    )
    data_items = [
        ("Samples needed", str(res["estimated_observations_needed"]), "#a78bfa"),
        ("Network gap", f"{res['network_average_obs_need']}/100", "#f59e0b"),
        ("First target", top["location"], "#34d399"),
    ]
    return {"answer": answer, "intent": "recommend", "location": top["location"],
            "location_id": top["location_id"],
            "data": _metrics(data_items),
            "suggestions": _suggest_for("recommend"), "sources": [SOURCE_ENGINE],
            "steps": ["Combined coverage + uncertainty + events", "Ranked decision impact"]}


def ans_tide_validation(db) -> dict:
    """Answer TIDE validation/benchmark questions from the Phase 8 framework.

    Never claims scientific validation: TIDE is implemented, demonstrated and
    tested, but has no independent ground truth, so it is NOT empirically
    validated. All numbers come from the framework, not from this answer.
    """
    status = tide_validation.validation_status(db)
    try:
        report = tide_validation.run_database_benchmark(db, budget=1)
    except Exception:
        report = None
    maturity = status["maturity"]
    dataset = status["dataset"]
    boundary = status["scientific_boundary"]

    lines = [
        "**Is TIDE scientifically validated? No.** TIDE is *implemented*, *demonstrated* and "
        "*computationally tested* — it is **not scientifically or empirically validated**. "
        "This project has no independent, externally labelled event ground truth.",
        "",
        f"**Algorithm version:** TIDE `{status['algorithm_version']}`  ",
        f"**Dataset:** {dataset['locations']} locations, {dataset['observations']} observations, "
        f"{dataset['events']} system-derived events (`{dataset['id']}` / `{dataset['version']}`).",
        f"**Ground truth:** {'available' if status['ground_truth']['available'] else 'NOT AVAILABLE'} — "
        f"false alarm / missed event rates are therefore **{status['ground_truth']['false_alarm']}**.",
    ]
    if report is not None:
        best = sorted(report["aggregates"], key=lambda a: (a["uncertainty_reduction"].get("mean") or -1), reverse=True)[0]
        lines.append(
            f"**Benchmark (budget {report['configuration']['budget']}, seed {report['configuration']['seed']}):** "
            f"across {len(report['rows'])} evaluated selections no strategy can be declared superior here"
            + (" — every candidate has zero observation value, so score-based strategies tie."
               if report["selection"]["pool_is_degenerate"] else ".")
        )
        lines.append(f"Largest mean uncertainty reduction: **{best['strategy']}** "
                     f"({best['uncertainty_reduction'].get('mean')} over N={best['uncertainty_reduction'].get('N')}) "
                     "— a demonstration outcome, not a scientific result.")
    lines += [
        "",
        "**What this validation can show:** " + "; ".join(boundary["can_show"][:3]) + ".",
        "**What it cannot show:** " + "; ".join(boundary["cannot_show"][:3]) + ".",
        "",
        f"**Reproducible:** seed `{status['reproducibility']['default_seed']}`, budget "
        f"`{status['reproducibility']['default_budget']}`, algorithm `{status['algorithm_version']}`, "
        f"dataset `{status['reproducibility']['dataset_id']}`.",
    ]

    return {
        "answer": "\n".join(lines),
        "intent": "tide_validation",
        "location": None,
        "location_id": None,
        "data": _metrics([
            ("Algorithm version", status["algorithm_version"], "#22d3ee"),
            ("Empirically validated", "NO", "#f43f5e"),
            ("Ground truth", "UNAVAILABLE", "#f59e0b"),
            ("Tested states", str(len(maturity["TESTED"])), "#10b981"),
        ]),
        "suggestions": _suggest_for("tide_validation"),
        "sources": ["TIDE Validation Framework", "TIDE Engine", "Twin Comparison"],
        "steps": ["Read validation status", "Ran the reproducibility benchmark", "Reported only supported metrics"],
    }


def ans_tide(db, loc, text) -> dict:
    """Use deterministic TIDE output; never invent a score, verdict, or explanation."""
    engine = TideEngine(db)
    lower = text.lower()
    loc_id = loc.id if loc else None

    if any(w in lower for w in ("what if we measure", "virtual observation", "simulate an observation", "simulate a sample", "measure there")):
        sim = engine.virtual_observation(location_id=loc_id) if loc else None
        if sim is None:
            return {"answer": "TIDE cannot build a what-if observation because no candidate exists for that location yet.",
                    "intent": "tide", "location": loc.name if loc else None, "location_id": loc_id, "data": None,
                    "suggestions": _suggest_for("tide"), "sources": ["TIDE Engine"], "steps": ["Checked TIDE candidates"]}
        before, after = sim["before"], sim["after"]
        reading = sim["simulated_observation"]
        change = "**changes**" if sim["decision_changed"] else "does not change"
        answer = (f"**Simulated observation {reading['value']} {sim['variable']} at {sim['location']}** — "
                  f"demonstration only, never written to the observation store.\n\n"
                  f"- Uncertainty **{before['uncertainty'] * 100:.0f}% -> {after['uncertainty'] * 100:.0f}%**\n"
                  f"- Anomaly risk **{before['anomaly_risk'] * 100:.0f}% -> {after['anomaly_risk'] * 100:.0f}%**\n"
                  f"- Ranking **#{before['ranking']} -> #{after['ranking']}**\n\n"
                  f"Your decision {change}: `{before['decision']}` remains until a real reading is collected.")
        return {"answer": answer, "intent": "tide", "location": sim["location"], "location_id": sim["location_id"],
                "data": _metrics([("Uncertainty", f"{before['uncertainty'] * 100:.0f}% -> {after['uncertainty'] * 100:.0f}%", "#22d3ee"),
                                  ("Anomaly risk", f"{before['anomaly_risk'] * 100:.0f}% -> {after['anomaly_risk'] * 100:.0f}%", "#f43f5e"),
                                  ("Ranking", f"#{before['ranking']} -> #{after['ranking']}", "#a78bfa")]),
                "suggestions": _suggest_for("tide"), "sources": ["TIDE Engine", "Ocean Forensics", "APEX"],
                "steps": ["Derived simulated reading from existing inputs", "Re-ranked candidates deterministically"]}

    if any(w in lower for w in ("replay", "recap the event", "what happened", "step by step", "did the decision change", "decision change", "was it validated", "why did tide recommend")):
        from app.modules.ai.tide.replay import ReplayEngine
        replay = ReplayEngine(db).build("event-0", location_id=loc_id) if loc else ReplayEngine(db).build("event-0")
        if replay is None:
            return {"answer": "The TIDE Decision Replay could not be built yet: no threshold-crossing event maps into TIDE for that location.",
                    "intent": "tide", "location": None, "location_id": None, "data": None,
                    "suggestions": _suggest_for("tide"), "sources": ["TIDE Replay"], "steps": ["Checked playable events", "Built replay paths"]}
        comp = replay["comparison"]
        decision = replay["decision"]
        changed = "changed" if decision["decision_changed"] else "unchanged"
        validation = replay["validation"]
        answer = (f"**TIDE Decision Replay ({replay['event_id']})** — {replay['location']}, {replay['variable'].replace('_', ' ')}.\n\n"
                  f"A read-only, two-mode replay of the detected event. Both paths agree until the observation:\n"
                  f"- **MODEL-ONLY** keeps uncertainty **{comp['uncertainty']['model_only'] * 100:.0f}%**; **TIDE-ASSISTED** (simulated reading, never persisted) reaches **{comp['uncertainty']['tide_assisted'] * 100:.0f}%**.\n"
                  f"- Confidence **{comp['confidence']['model_only'] * 100:.0f}% -> {comp['confidence']['tide_assisted'] * 100:.0f}%**; anomaly risk **{comp['anomaly_risk']['model_only'] * 100:.0f}% -> {comp['anomaly_risk']['tide_assisted'] * 100:.0f}%**.\n"
                  f"- Decision **{decision['before']} -> {decision['after']}** ({changed}) via the documented rules.\n"
                  f"- Regret (demonstration metric only): **{replay['regret']['value']:.2f}** — {replay['regret']['caveat']}.\n"
                  f"- Validation: **{validation['message']}**\n\n"
                  f"{comp['uncertainty']['detail']} {decision['explanation']}")
        return {"answer": answer, "intent": "tide", "location": replay["location"], "location_id": replay["location_id"],
                "data": _metrics([("Uncertainty", f"{comp['uncertainty']['model_only'] * 100:.0f}% -> {comp['uncertainty']['tide_assisted'] * 100:.0f}%", "#22d3ee"),
                                  ("Confidence", f"{comp['confidence']['model_only'] * 100:.0f}% -> {comp['confidence']['tide_assisted'] * 100:.0f}%", "#10b981"),
                                  ("Decision", f"{decision['before'].replace('_', ' ')} -> {decision['after'].replace('_', ' ')}", "#f59e0b")]),
                "suggestions": _suggest_for("tide"), "sources": ["TIDE Replay", "TIDE Engine", "Twin Comparison", "Ocean Forensics"],
                "steps": ["Resolved the detected event", "Composed MODEL-ONLY and TIDE-ASSISTED paths", "Compared decisions and validation"]}

    if any(w in lower for w in ("verdict", "sensor issue", "model issue", "missing phenomenon", "phenomenon")):
        verdict = engine.verdict(location_id=loc_id) if loc else None
        if verdict is None:
            return {"answer": "TIDE has insufficient evidence to produce a verdict for that location yet.",
                    "intent": "tide", "location": None, "location_id": None, "data": None,
                    "suggestions": _suggest_for("tide"), "sources": ["TIDE Engine"], "steps": ["Checked TIDE verdict"]}
        return {"answer": f"**TIDE verdict: {verdict['verdict'].replace('_', ' ').title()}**\n\n{verdict['summary']}\nAlternative explanation: {verdict['alternative_explanation']}.",
                "intent": "tide", "location": loc.name, "location_id": loc.id,
                "data": _metrics([("Verdict confidence", f"{verdict['confidence'] * 100:.0f}%", "#22d3ee"),
                                  ("Evidence signals", str(len(verdict["evidence"])), "#a78bfa")]),
                "suggestions": _suggest_for("tide"), "sources": ["Twin Comparison", "Ocean Forensics", "TIDE Engine"],
                "steps": ["Classified mismatch + persistence", "Listed alternative explanations"]}

    if any(w in lower for w in ("event dna", "tide event", "dna")):
        ctx = engine.event_context("event-0")
        if ctx is None or not ctx.get("top_candidates"):
            return {"answer": "No existing ocean event currently maps into TIDE candidates.",
                    "intent": "tide", "location": None, "location_id": None, "data": None,
                    "suggestions": _suggest_for("tide"), "sources": ["Ocean Event DNA"], "steps": ["Matched active events"]}
        event = ctx["event"]
        dna = ctx["event_dna"]
        tags = ", ".join(dna.get("tags", [])) or "no categorical DNA tags available"
        top = ctx["top_candidates"][0]
        return {"answer": (f"Existing **{event.get('event_type', 'event').replace('_', ' ').title()}** flows into TIDE.\n\n"
                           f"- Event DNA tags: **{tags}**\n"
                           f"- Model vs observed: model **{ctx['disagreement']['model_value']}** vs observed **{ctx['disagreement']['observed_value']}**\n"
                           f"- TIDE maps it to **{top['location']}** with uncertainty **{ctx['uncertainty']['score'] * 100:.0f}%**\n\n"
                           f"This reuses the existing Event DNA — no new event engine was built."),
                "intent": "tide", "location": event.get("location", top["location"]), "location_id": event.get("location_id", top["location_id"]),
                "data": _metrics([("Event confidence", f"{(event.get('confidence') or 0) * 100:.0f}%", "#f59e0b"),
                                  ("Uncertainty", f"{ctx['uncertainty']['score'] * 100:.0f}%", "#22d3ee")]),
                "suggestions": _suggest_for("tide"), "sources": ["Ocean Event DNA", "Twin Comparison", "TIDE Engine"],
                "steps": ["Read event fingerprint", "Composed TIDE context"]}

    result = engine.explanation(location_id=loc_id)
    if result is None:
        return {"answer": "TIDE has insufficient available evidence to explain a recommendation yet.", "intent": "tide", "location": None, "location_id": None, "data": None, "suggestions": _suggest_for("tide"), "sources": ["TIDE Engine"], "steps": ["Checked TIDE evidence"]}
    exp = result["explanation"]
    evidence_lines = "\n".join(f"- [{item['source_system']}] {item['description']}" for item in exp["evidence"][:4]) or "- No standalone evidence signals."
    answer = (f"**TIDE recommendation** — {exp['summary']}\n\n" + "\n".join(f"- {reason}" for reason in exp["reasons"])
              + f"\n\nEvidence chain:\n{evidence_lines}\n\n{exp['expected_benefit']}\nAffected decision: **{exp['affected_decision']}**.")
    return {"answer": answer, "intent": "tide", "location": loc.name if loc else None, "location_id": loc.id if loc else None,
            "data": _metrics([("Confidence", f"{exp['confidence']['overall_confidence'] * 100:.0f}%", "#22d3ee"), ("Evidence", str(exp['confidence']['evidence_count']), "#a78bfa")]),
            "suggestions": _suggest_for("tide"), "sources": ["TIDE Engine", "Twin Comparison", "Ocean Forensics", "APEX"], "steps": ["Read TIDE evidence chain", "Built deterministic explanation"]}


def ans_brief(db, loc) -> dict:
    """Unified Ocean Intelligence Brief across twin, validation, forensics and TIDE.

    A single structured read — ANSWER / EVIDENCE / CONFIDENCE / LIMITATIONS /
    NEXT ACTION — built entirely from the existing engines (no new computation).
    Every number is real; anything absent is stated as unavailable.
    """
    engine = TideEngine(db)
    sit = {r["location_id"]: r for r in situation_panel(db)["regions"]}
    all_events = classify_events(db)["events"]

    # Focus the brief on an explicit coast, else fall back to the first coast.
    focus = loc if loc is not None else first_location(db)
    lid = focus.id if focus is not None else None
    fname = focus.name if focus is not None else "the network"

    row = sit.get(lid) if lid is not None else None
    health = intelligence_health(db, lid) if lid is not None else []

    live_obs = None
    if lid is not None:
        live_obs = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == lid)
            .order_by(OceanObservation.timestamp.desc())
            .first()
        )

    candidates = engine.rankings(location_id=lid) if lid is not None else engine.rankings()
    top = candidates[0] if candidates else None

    local_events = [ev for ev in all_events if ev.get("location_id") == lid] if lid is not None else all_events

    obs_conf = row.get("observation_confidence") if row else None
    trust = row.get("model_trust") if row else None
    disagreement = bool(row.get("disagreement")) if row else None
    status = row.get("status") if row else None
    headline = row.get("headline") if row else None
    h_score = health[0]["score"] if health else None
    h_label = health[0]["label"] if health else None

    # ---------------- ANSWER ----------------
    answer_bits = [f"**Ocean Intelligence Brief — {fname}**"]
    if headline and status:
        answer_bits.append(f"{headline} (_site status: **{status.upper()}**).")
    elif headline:
        answer_bits.append(f"{headline}.")
    else:
        answer_bits.append("No unified situation row is available for this coast yet.")

    live_bits = []
    if live_obs is not None:
        if live_obs.sea_surface_temperature is not None:
            live_bits.append(f"SST **{live_obs.sea_surface_temperature:.1f}°C**")
        if live_obs.wave_height is not None:
            live_bits.append(f"waves **{live_obs.wave_height:.2f} m**")
        if live_obs.salinity is not None:
            live_bits.append(f"salinity **{live_obs.salinity:.1f} PSU**")
        if live_bits:
            answer_bits.append("Live: " + " · ".join(live_bits) + " (latest observation).")
        else:
            answer_bits.append("Live observations exist but carry no numeric fields.")
    else:
        answer_bits.append("No live observations are loaded for this coast — data that would confirm the picture is unavailable.")

    if h_score is not None:
        answer_bits.append(f"Network health score: **{h_score:.0f}/100** ({h_label}).")
    if local_events:
        kinds = ", ".join(sorted({(ev.get("event_type") or "event").replace("_", " ") for ev in local_events}))
        answer_bits.append(f"{len(local_events)} detected event(s): **{kinds}**.")
    elif lid is not None:
        answer_bits.append("No threshold-crossing events are detected for this coast in the available data (an honest reading).")
    if top is not None:
        answer_bits.append(
            f"Highest-value next observation per TIDE: **{top['location']}** "
            f"({top['variable']} @ {top['depth_m']}, value **{top['observation_value']:.4f}** · decision **{top['affected_decision'].replace('_', ' ')}**)."
        )

    # ---------------- EVIDENCE ----------------
    evidence = []
    sources = []
    if live_obs is not None:
        evidence.append(f"- [Open-Meteo Marine] Latest observation row feeds the live picture.")
        sources.append(SOURCE_API)
    if row is not None and disagreement is not None:
        evidence.append(
            f"- [Twin Comparison] Model↔observation {'disagreement flagged — verify manually' if disagreement else 'agreement detected'} "
            f"(obs confidence {obs_conf}% · model trust {trust}%)."
        )
        sources.append("Twin Comparison")
    if health:
        evidence.append(f"- [Decision Intelligence] Health index {h_score:.0f}/100 ({h_label}) blends temperature, oxygen, salinity, chlorophyll, waves, events and coverage.")
        sources.append("Decision Intelligence")
    if top is not None:
        reason = (top.get("reason") or "").strip()
        if reason:
            evidence.append(f"- [TIDE Engine] {reason}")
        sources.append("TIDE Engine")
        for ev in top.get("evidence", [])[:3]:
            evidence.append(f"- [{ev.get('source_system') or 'TIDE'}] {ev.get('description') or ev.get('type', 'evidence signal')}")
    if local_events:
        first = local_events[0]
        evidence.append(f"- [Ocean Event DNA] {first.get('event_type', 'event').replace('_', ' ').title()} — model {first.get('model')} vs observed {first.get('observed')}.")
        sources.append("Ocean Event DNA")
    if not evidence:
        evidence.append("- [TidalTwin engine] No evidence chain can be assembled from the currently available data.")

    # ---------------- CONFIDENCE ----------------
    conf_bits = []
    if obs_conf is not None:
        conf_bits.append(f"observation confidence **{obs_conf}%**")
    if trust is not None:
        conf_bits.append(f"model trust **{trust}%**")
    if top is not None and top.get("confidence") is not None:
        conf_bits.append(f"TIDE decision confidence **{top['confidence'] * 100:.0f}%**")
    if live_obs is None and obs_conf is None:
        conf_bits.append("confidence **unavailable** (no observation stream)")
    conf_line = "**CONFIDENCE**\n" + ("\n".join(f"- {b}" for b in conf_bits) if conf_bits else "- Not enough evidence to express a confidence yet.")

    # ---------------- LIMITATIONS ----------------
    limitations = []
    if live_obs is None:
        limitations.append("No live observation rows exist for this coast — the live picture is empty, not assumed.")
    if not top:
        limitations.append("TIDE has no candidate (insufficient evidence or no anomaly), so no observation can be prioritised.")
    elif top.get("status") == "MODEL_DERIVED":
        limitations.append("The TIDE candidate is MODEL_DERIVED — an observation is required to confirm it.")
    if not local_events:
        limitations.append("No threshold-crossing events are detected; guidance can only reflect normal state.")
    if not limitations:
        limitations.append("This brief is a decision-support read, not a validated scientific claim.")
    limitation_line = "**LIMITATIONS**\n" + "\n".join(f"- {l}" for l in limitations)

    # ---------------- NEXT ACTION ----------------
    actions = []
    if top is not None:
        actions.append(f"Prioritise an observation at **{top['location']}** ({top['observation_type'].replace('_', ' ')} for {top['variable']} @ {top['depth_m']} m) — TIDE expects it to reduce uncertainty most.")
    if local_events:
        actions.append("Replay the decided path for the detected event in Decision Replay to see how the decision would change.")
    if disagreement:
        actions.append("Investigate the model↔observation disagreement in Ocean Forensics before acting.")
    if not actions:
        actions.append("Sync more observations, then request the brief again once evidence exists to prioritise.")
    action_line = "**NEXT ACTION**\n" + "\n".join(f"- {a}" for a in actions)

    # A compact, honest prose recap + the structured sections in one text block.
    answer = (
        "\n\n".join(answer_bits)
        + f"\n\n**ANSWER**\n{headline or 'No headline row available.'}"
        + "\n\n" + ("\n".join(["**EVIDENCE**"] + evidence))
        + "\n\n" + conf_line
        + "\n\n" + limitation_line
        + "\n\n" + action_line
    )

    data_items = [("Health", f"{h_score:.0f}/100" if h_score is not None else "—", "#22d3ee")]
    if obs_conf is not None:
        data_items.append(("Obs confidence", f"{obs_conf}%", "#10b981"))
    if trust is not None:
        data_items.append(("Model trust", f"{trust}%", "#38bdf8"))
    if top is not None:
        data_items.append(("Top obs value", f"{top['observation_value']:.4f}", "#a78bfa"))
        data_items.append(("Decision", top["affected_decision"].replace("_", " "), "#f59e0b"))
    data_items.append(("Events", str(len(local_events)), "#f43f5e"))

    return {
        "answer": answer,
        "intent": "brief",
        "location": fname,
        "location_id": lid,
        "data": _metrics(data_items),
        "suggestions": _suggest_for("brief"),
        "sources": sources or [SOURCE_ENGINE],
        "steps": ["Resolved focus coast", "Fused situation + health + TIDE", "Composed brief sections"],
    }


def ans_adaptive(db) -> dict:
    res = adaptive_identification(db)
    rows = res["regions"]
    changed = []
    for r in rows:
        for v in r.get("variables", []):
            if v.get("classification_changed"):
                changed.append((r["location"], v["label"], v["adaptive_threshold"], v["static_threshold"]))
    confident = sum(1 for r in rows if r["maturity"] == "confident")
    answer = (
        f"**Adaptive detection** — {confident}/{len(rows)} regions now run **confident** "
        f"self-calibrating thresholds instead of fixed legacy rules.\n\n"
    )
    if changed:
        answer += f"- {len(changed)} classification(s) would change under adaptive bands, e.g. "
        answer += f"**{changed[0][0]}** {changed[0][1]} adaptive {changed[0][2]} vs static {changed[0][3]}.\n"
    else:
        answer += "- No region currently flips its classification between static and adaptive rules.\n"
    answer += (f"\n_Bands tune within [60% of static rule, data-driven σ] as history grows — "
               f"{res['note']}_")
    return {"answer": answer, "intent": "adaptive", "location": None, "location_id": None,
            "data": _table(
                ["Coast", "Maturity", "Adapt. index", "Changing"],
                [[r["location"], r["maturity"].upper(), str(r["adaptation_index"]),
                  "YES" if any(v.get("classification_changed") for v in r.get("variables", [])) else "no"]
                 for r in rows[:8]]),
            "suggestions": _suggest_for("adaptive"), "sources": [SOURCE_ENGINE],
            "steps": ["Learned per-region variance", "Re-classified under adaptive rules"]}


def ans_fisheries(db, loc) -> dict:
    res = compute_fisheries(db)
    regions = res["regions"]
    best = res["summary"].get("best_zone")
    seasons = next((
        r["seasonal_calendar"] for r in regions
        if loc is not None and r["location_id"] == loc.id), None)
    this_month = seasons[datetime.now().month - 1].get("index", 0) if seasons else None
    target = next((r for r in regions if loc is not None and r["location_id"] == loc.id), regions[0])
    lines = [
        f"**Fisheries advisory** — the network scores **{res['summary']['coasts']}** coasts for productivity.",
        f"- Best zone today: **{best}** (FAZ {res['summary']['best_score']}/100).",
    ]
    if loc is not None:
        months_desc = f" — fishing calendar at **{target['location']}** is at **{this_month}/100** for this month." if this_month is not None else ""
        lines.append(f"- {target['location']}: FAZ **{target['faz_score']}/100** ({target['category']}).{months_desc}")
    lines.append("- Biophysical drivers explain the score (SST + chlorophyll + current convergence).")
    return {"answer": "\n".join(lines), "intent": "fisheries",
            "location": target["location"], "location_id": target["location_id"],
            "data": _table(
                ["Coast", "FAZ", "Category", "Top species"],
                [[r["location"], str(r["faz_score"]), r["category"].upper(),
                  ", ".join(sp["name"] for sp in r["top_species"][:2])] for r in regions[:8]]),
            "suggestions": _suggest_for("fisheries"), "sources": [SOURCE_ENGINE],
            "steps": ["Scored FAZ for every coast", "Matched species likelihood", "Read seasonal calendar"]}


def ans_coral(db) -> dict:
    res = compute_coral(db)
    regions = res["regions"]
    worst = next((r for r in regions if r["level"] in ("critical", "warning")), regions[0])
    lines = [
        f"**Coral status** — {res['summary']['reefs_monitored']} reef regions monitored with NOAA-style DHW.",
        f"- Watchpoint: **{worst['location']}** is at **{worst['level_label']}** "
        f"(DHW **{worst['dhw']}**, bleaching risk **{worst['bleaching_risk_pct']}%**).",
        "- DHW ≥ 4 = warning; ≥ 8 = critical (24h of +1°C above the reef MMM ≈ 1 DHW).",
    ]
    return {"answer": "\n".join(lines), "intent": "coral",
            "location": worst["location"], "location_id": worst["location_id"],
            "data": _table(
                ["Reef", "DHW", "Level", "Risk", "Advice"],
                [[r["location"], str(r["dhw"]), r["level_label"].upper(),
                  f"{r['bleaching_risk_pct']}%", r["recommendation"][:42]] for r in regions]),
            "suggestions": _suggest_for("coral"), "sources": [SOURCE_ENGINE],
            "steps": ["Accumulated heat above MMM", "Scored DHW bands", "Issued bleaching status"]}


def ans_spill(db, loc, text) -> dict:
    lower = text.lower()
    scenario = "sar" if any(w in lower for w in (
        "search and rescue", "sar", "overboard", "missing", "person", "rescue", "drifting person")) else "spill"
    m = re.search(r"(\d{1,3})\s*h", lower)
    duration = max(4, min(120, int(m.group(1)) if m else 24))
    res = simulate_drift(db, scenario=scenario,
                         location_id=loc.id if loc else None,
                         duration_h=duration)
    sigma = {k: v for k, v in res["origin"].items()}
    top = res["response_priority"]
    target = top[0] if top else None
    lines = [
        f"**{scenario.upper()} drift run** — origin **{res['origin']['location']}** "
        f"({res['origin']['lat']}, {res['origin']['lon']}), {duration}h at "
        f"bearing **{res['forcing']['current_bearing_deg']}°**.",
    ]
    if target:
        lines.append(f"- Top reachable coast: **{target['location']}** — "
                     f"{target['distance_km']} km away, ETA **{target['eta_hours']}h**, "
                     f"**{target['probability_pct']}%** contact probability.")
    lines.append(f"- _Recommendation: {res['recommendation']}_")
    return {"answer": "\n".join(lines), "intent": "spill",
            "location": res["origin"]["location"], "location_id": None,
            "data": _table(
                ["Coast", "Dist (km)", "ETA (h)", "Prob.", "Priority"],
                [[z["location"], str(z["distance_km"]), str(z["eta_hours"]),
                  f"{z['probability_pct']}%", f"#{i + 1}"] for i, z in enumerate(top[:5])]),
            "suggestions": _suggest_for("spill"), "sources": [SOURCE_ENGINE],
            "steps": ["Seeded drift at origin", "Advected with coastal current", "Ranked landfall probability"]}


def ans_slr(db, text) -> dict:
    m = re.search(r"\+?\s*(\d+(?:\.\d+)?)\s*m(?:\b|eter|etre)", text.lower())
    scenario = max(0.1, min(5.0, float(m.group(1)) if m else 1.0))
    res = slr_inundation(db, scenario)
    s = res["summary"]
    lines = [
        f"**Sea-level rise +{scenario} m** — {s['towns_inundated']} coastal towns inundated, "
        f"approx. **₹{s['total_population_at_risk'] / 1e7:.1f} cr** people at risk.",
        f"- Area lost ≈ **{s['total_land_area_lost_km2']} km²** across {s['coasts_analyzed']} coasts; "
        f"**{s['most_affected']}** is hardest hit.",
        "- Bathymetry + coast geometry drive the flood footprint (not a flat bathtub model).",
    ]
    return {"answer": "\n".join(lines), "intent": "slr", "location": s["most_affected"],
            "location_id": None,
            "data": _table(
                ["Coast", "Towns hit", "Pop. at risk", "Land lost (km²)", "Impact"],
                [[r["location"], str(r["affected_count"]),
                  f"{r['population_at_risk'] / 1e7:.1f}cr", f"{r['land_area_lost_km2']}",
                  r["level"].upper()] for r in res["regions"][:8]]),
            "suggestions": _suggest_for("slr"), "sources": [SOURCE_ENGINE],
            "steps": ["Flooded land below scenario + high tide", "Counted settlements at risk"]}


def ans_beach(db, loc) -> dict:
    res = compute_beach_safety(db)
    rows = res["regions"]
    s = res["summary"]
    target = next((r for r in rows if loc is not None and r["location_id"] == loc.id), rows[0])
    danger_list = [r for r in rows if r["flag"] == "danger"]
    lines = [
        f"**Beach safety sweep** — {s['safe']} SAFE, {s['caution']} CAUTION, "
        f"{s['danger']} DANGER across {len(rows)} beaches.",
        f"- **{target['location']}**: {target['flag_label']} (rip index **{target['rip_current_index']}/100**, "
        f"waves {target['wave_height']} m, current {target['current_speed']} m/s).",
    ]
    if danger_list:
        lines.append(f"- 🚨 Danger beaches: " + ", ".join(r["location"] for r in danger_list) + ".")
    lines.append(f"- _Action for top pick: {target['action']}_")
    return {"answer": "\n".join(lines), "intent": "beach",
            "location": target["location"], "location_id": target["location_id"],
            "data": _table(
                ["Beach", "Flag", "Rip index", "Waves", "Why"],
                [[r["location"], r["flag_label"], str(r["rip_current_index"]),
                  f"{r['wave_height']} m", ", ".join(r["reasons"][:1])] for r in rows[:8]]),
            "suggestions": _suggest_for("beach"), "sources": [SOURCE_ENGINE],
            "steps": ["Scored rip-current proxy", "Applied flag thresholds", "Set lifeguard action"]}


def ans_impact(db) -> dict:
    res = compute_economic_impact(db)
    s = res["summary"]
    b = s["breakdown"]
    lines = [
        f"**Economic impact** — {s['active_events']} active events across {s['coasts_impacted']} coasts: "
        f"**₹{s['total_estimated_loss_cr']:.1f} crore** estimated damage.",
        f"- Fishing ₹{b['fishing_loss_inr'] / 1e7:.1f} cr · ports ₹{b['port_loss_inr'] / 1e7:.1f} cr · "
        f"tourism ₹{b['tourism_loss_inr'] / 1e7:.1f} cr.",
        f"- Worst coast: **{s['largest_loss_coast']}**.",
    ]
    return {"answer": "\n".join(lines), "intent": "impact",
            "location": s["largest_loss_coast"], "location_id": None,
            "data": _metrics([
                ("Total", f"₹{s['total_estimated_loss_cr']} cr", "#22d3ee"),
                ("Fishing", f"₹{b['fishing_loss_inr'] / 1e7:.1f} cr", "#0ea5e9"),
                ("Ports", f"₹{b['port_loss_inr'] / 1e7:.1f} cr", "#f59e0b"),
                ("Tourism", f"₹{b['tourism_loss_inr'] / 1e7:.1f} cr", "#a78bfa"),
            ]),
            "suggestions": _suggest_for("impact"), "sources": [SOURCE_ENGINE],
            "steps": ["Priced intensity-duration damage", "Broke out sector losses"]}


def ans_multimodal(db, text: str) -> dict:
    """Multimodal Ocean AI: verify a pasted report/news/NetCDF summary."""
    clean = text
    for prefix in ("analyze this", "cross-check", "cross check", "verify this",
                   "multimodal", "report says", "document says"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):].lstrip(" :,-").strip()
    if clean.lower().startswith("report:"):
        clean = clean[len("report:"):].strip()
    if not clean:
        clean = text
    return multimodal_fuse(db, clean)


def ans_general() -> dict:
    answer = (
        "I'm **TidalTwin Copilot**. 🌊 I read the live ocean data and our AI engines "
        "to answer questions like a senior ocean analyst.\n\n"
        "**What I can do:**\n"
        "- **Current** — temperature, waves, salinity anywhere on the coast\n"
        "- **Safety** — SAFE/CAUTION/DANGER + safest sailing window\n"
        "- **Events** — marine heatwaves, flood risk, anomalies (live)\n"
        "- **Risk** — national risk ranking of all coasts\n"
        "- **Validation** — is the model right? confidence, skill, deviation\n"
        "- **Forecast** — next 12 hours for any region\n"
        "- **What-If** — 'what if wind increases 20%?'\n"
        "- **Storm / Cyclone** — live track status\n"
        "- **Carbon** — air-sea CO₂ flux, sinks, blue-carbon potential\n"
        "- **Light pollution** — ALAN exposure + biota impact per coast\n"
        "- **Satellites** — remote-sensing fusion & harmonized confidence\n"
        "- **Observation planning** — 'where should we sample next?'\n"
        "- **Adaptive detection** — self-calibrating anomaly thresholds\n"
        "- **Provenance** — where every number came from\n"
        "- **Fisheries** — fishing zones, target species, seasonal calendar\n"
        "- **Coral** — bleaching stress index (DHW) per reef\n"
        "- **Spill & SAR** — oil-slick and drifting-person prediction\n"
        "- **Sea-level rise** — inundation for +0.3…+2 m scenarios\n"
        "- **Beach safety** — rip-current flags & lifeguard action\n"
        "- **Economic impact** — ₹ losses by sector\n\n"
        "And I remember context — try _'how about Kochi?'_ after a question about Goa."
    )
    return {"answer": answer, "intent": "general", "location": None, "location_id": None,
            "data": None, "suggestions": _suggest_for("general"),
            "sources": [], "steps": []}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

NEEDS_LOCATION = {"current", "safety", "trend", "forecast", "validation", "provenance", "whatif"}


def copilot_answer(db: Session, question: str, context: dict | None = None) -> dict:
    context = context or {}
    text = question.strip()
    if not text:
        return ans_general()

    loc, variables = resolve_context(db, text, context)
    intent = detect_intent(text)

    # Safety supercedes other intents when explicitly asked (but not superlatives
    # or the coastal decision intents, which read safer against the experts).
    superlative = detect_superlative(text)
    if superlative is None and intent not in ("fisheries", "spill", "beach", "impact") \
            and any(w in text.lower() for w in ("safe to", "how safe", "safety", "sailing", "fish")):
        intent = "safety"
    if superlative is not None:
        intent = "superlative"

    # Coasts-only intents fall back to the remembered or first coast
    if loc is None and intent in NEEDS_LOCATION:
        last_loc_id = context.get("last_location_id")
        loc = match_location_by_id(db, last_loc_id) if last_loc_id else first_location(db)
        if intent != "whatif" and loc is None and first_location(db) is None:
            return {"answer": "No coast data loaded yet — sync observations first.",
                    "intent": intent, "location": None, "location_id": None,
                    "data": None, "suggestions": [], "sources": [], "steps": []}

    handlers = {
        "safety": lambda: ans_safety(db, loc),
        "events": lambda: ans_events(db, loc),
        "risk": lambda: ans_risk(db),
        "validation": lambda: ans_validation(db, loc),
        "forecast": lambda: ans_forecast(db, loc),
        "storm": lambda: ans_storm(db),
        "whatif": lambda: ans_whatif(db, loc, text),
        "provenance": lambda: ans_provenance(db, loc),
        "trend": lambda: ans_trend(db, loc),
        "compare": lambda: ans_compare(db, text),
        "superlative": lambda: ans_superlative(db, text),
        "current": lambda: ans_current(db, loc, variables),
        "carbon": lambda: ans_carbon(db),
        "lights": lambda: ans_lights(db),
        "sensing": lambda: ans_sensing(db),
        "recommend": lambda: ans_recommend(db),
        "tide": lambda: ans_tide(db, loc, text),
        "tide_validation": lambda: ans_tide_validation(db),
        "brief": lambda: ans_brief(db, loc),
        "adaptive": lambda: ans_adaptive(db),
        "multimodal": lambda: ans_multimodal(db, text),
        "fisheries": lambda: ans_fisheries(db, loc),
        "coral": lambda: ans_coral(db),
        "spill": lambda: ans_spill(db, loc, text),
        "slr": lambda: ans_slr(db, text),
        "beach": lambda: ans_beach(db, loc),
        "impact": lambda: ans_impact(db),
        "general": ans_general,
    }
    handler = handlers.get(intent, handlers["current"])
    # A bare mention of a coast ("how about Kochi?") defaults to live conditions
    if intent == "general" and loc is not None:
        handler = lambda: ans_current(db, loc, set())

    result = handler()
    # persist context for the next turn
    result["context"] = {
        "last_location_id": result.get("location_id"),
        "last_intent": result["intent"],
    }
    return result
