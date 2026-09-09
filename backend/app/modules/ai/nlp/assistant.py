"""
OceanVerse AI - Natural Language Assistant
==========================================
This module understands plain-English questions about the ocean
and answers them using real data from our database.

How it works (3 stages):
1. INTENT — what does the user want? (temperature, waves, safety, compare, trend)
2. ENTITIES — which locations / variables matter?
3. ANSWER — query the DB and build a friendly, helpful response.

It's a rule-based NLP engine we control fully — no API keys,
works offline, and uses only real data (great for demos/judges).
"""

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation


# ---------------------------------------------------------------
# STAGE 1 & 2: Intent + Entity detection
# ---------------------------------------------------------------

# Words that hint at each intent
VARIABLE_WORDS = {
    "temperature": ["temperature", "temp", "warm", "hot", "heat", "sst"],
    "waves": ["wave", "sea", "swell", "rough", "calm", "height"],
    "salinity": ["salinity", "salt", "salty"],
    "safety": ["safe", "safety", "sail", "sailing", "fish", "fishing", "bath",
               "swim", "danger", "risky", "navigate", "navigation", "journey"],
    "trend": ["trend", "change", "changed", "rising", "falling", "warmer", "cooler",
              "compare", "versus", "vs", "difference", "increase", "decrease",
              "since", "over time", "recently"],
}

SUPERLATIVE_WORDS = {
    "warmest": ["warmest", "hottest", "highest temp", "max temp"],
    "coldest": ["coldest", "coolest"],
    "calmest": ["calmest", "smoothest", "lowest wave"],
    "waviest": ["waviest", "roughest", "highest wave", "largest wave"],
}


def detect_variables(text: str) -> set[str]:
    """Which ocean variables is the user asking about?"""
    found: set[str] = set()
    lower = text.lower()
    for var, words in VARIABLE_WORDS.items():
        if any(w.lower() in lower for w in words):
            found.add(var)
    return found


def detect_superlative(text: str) -> str | None:
    """Only/warmest/coldest/calmest requests (e.g. 'warmest sea in India')."""
    lower = text.lower()
    for kind, words in SUPERLATIVE_WORDS.items():
        if any(w.lower() in lower for w in words):
            return kind
    return None


def is_comparison(text: str) -> bool:
    lower = text.lower()
    return any(w in lower for w in ["compare", "versus", "vs.", " vs ", "vs "]) and " vs " not in lower[0:0]


def build_suggestion_prompt(text: str) -> str:
    lower = text.lower()
    if "safe" in lower or "sail" in lower or "fish" in lower:
        return "safety"
    if "temp" in lower or "warm" in lower or "hot" in lower:
        return "temperature"
    if "wave" in lower:
        return "waves"
    if "compare" in lower or "vs" in lower:
        return "compare"
    if "trend" in lower or "change" in lower or "rising" in lower:
        return "trend"
    return "general"


# ---------------------------------------------------------------
# STAGE 3: Data queries
# ---------------------------------------------------------------

def _latest(db: Session, loc: OceanLocation) -> OceanObservation | None:
    return (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .first()
    )


def _series(db: Session, loc: OceanLocation, n: int = 24) -> list[OceanObservation]:
    return (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .limit(n)
        .all()
    )


def _find_location(db: Session, text: str) -> OceanLocation | None:
    """Try to find which monitored location the user mentioned."""
    locations = db.query(OceanLocation).all()
    lower = text.lower()

    # Give each location a set of searchable keywords (cities, seas, bays)
    keyword_map = {
        "mumbai": ["mumbai", "arabian", "bombay", "maharastra", "maharashtra", "west coast"],
        "chennai": ["chennai", "bengal", "madras", "tamil", "east coast"],
        "mannar": ["mannar", "gulf"],
        "kochi": ["kochi", "kerala", "cochin"],
        "goa": ["goa", "panaji", "panjim"],
        "andaman": ["andaman", "port blair"],
        "lakshadweep": ["lakshadweep", "laccadive"],
        "puri": ["puri", "odisha", "orissa", "pur"]
    }

    # 1) exact/partial name match on the location name
    for loc in locations:
        if loc.name.lower() in lower:
            return loc

    # 2) keyword aliases
    for loc in locations:
        for key, aliases in keyword_map.items():
            if key in loc.name.lower():
                if any(al in lower for al in aliases):
                    return loc

    # 3) fall back to the first location
    return locations[0] if locations else None


# ---------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------

def answer_current(loc: OceanLocation, obs: OceanObservation | None, variables: set[str]) -> str:
    if obs is None:
        return f"I don't have live readings for *{loc.name}* yet. Try syncing the data first."

    parts: list[str] = [f"Here's what I see at *{loc.name}* right now:"]
    if not variables or "temperature" in variables:
        if obs.sea_surface_temperature is not None:
            parts.append(
                f"- 🌡️ Sea temperature is **{obs.sea_surface_temperature:.1f}°C**"
            )
    if "waves" in variables or not variables:
        if obs.wave_height is not None:
            parts.append(
                f"- 🌊 Waves are about **{obs.wave_height:.2f} m** high"
            )
    if "salinity" in variables:
        if obs.salinity is not None:
            parts.append(f"- 🧂 Salinity is **{obs.salinity:.1f} PSU**")
    return "\n".join(parts)


def answer_safety(loc: OceanLocation, obs: OceanObservation | None) -> str:
    if obs is None or obs.wave_height is None:
        return f"I need wave data for *{loc.name}* to assess safety."
    h = obs.wave_height
    if h < 0.8:
        verdict = "very calm and **safe** ✅"
        advice = "Excellent conditions for fishing, sailing, and swimming."
    elif h < 1.5:
        verdict = "moderately calm — generally **safe** ✅"
        advice = "Good for experienced fishers and sailors; light to moderate swell."
    elif h < 2.5:
        verdict = "**unsettled** ⚠️"
        advice = "Small craft advised with caution. Swimming less recommended."
    else:
        verdict = "**rough / hazardous** 🚨"
        advice = "Avoid small-vessel journeys; follow coast guard advisories."
    temp = obs.sea_surface_temperature
    temp_note = ""
    if temp is not None:
        if temp > 30:
            temp_note = f" Sea temperature is high ({temp:.1f}°C) — watch for heat stress."
        elif temp < 25:
            temp_note = f" Sea is cooler than usual ({temp:.1f}°C)."
    return (
        f"Safety check for *{loc.name}*: waves are **{h:.2f} m** — this is {verdict}.{temp_note}\n\n"
        f"💡 *{advice}*"
    )


def answer_trend(loc: OceanLocation, series: list[OceanObservation]) -> str:
    if not series:
        return f"No history available for *{loc.name}* yet."
    latest = series[0]
    oldest = series[-1]
    if latest.sea_surface_temperature is None or oldest.sea_surface_temperature is None:
        return f"I have readings for *{loc.name}* but no temperature history to compare."
    delta = latest.sea_surface_temperature - oldest.sea_surface_temperature
    direction = "warming up" if delta > 0.1 else "cooling down" if delta < -0.1 else "holding steady"
    emoji = "📈" if delta > 0.1 else "📉" if delta < -0.1 else "➡️"
    return (
        f"{emoji} Ocean temperature at *{loc.name}* is **{direction}** over the last "
        f"{len(series)} readings: from {oldest.sea_surface_temperature:.1f}°C to "
        f"{latest.sea_surface_temperature:.1f}°C "
        f"(Δ {delta:+.1f}°C)."
    )


def answer_comparison(db: Session, locs: list[OceanLocation]) -> str:
    reports: list[str] = []
    for loc in locs:
        obs = _latest(db, loc)
        if obs and obs.sea_surface_temperature is not None and obs.wave_height is not None:
            reports.append(
                f"- **{loc.name}**: {obs.sea_surface_temperature:.1f}°C, waves {obs.wave_height:.2f} m"
            )
    if not reports:
        return "I need recent observations to compare regions."
    return "Comparing monitored regions:\n" + "\n".join(reports)


def _find_two_locations(db: Session, text: str) -> list[OceanLocation]:
    """Find up to two distinct locations mentioned in a comparison question."""
    locations = db.query(OceanLocation).all()
    found: list[OceanLocation] = []
    lower = text.lower()

    city_keywords = {
        "mumbai": "Arabian Sea (Mumbai Coast)",
        "chennai": "Bay of Bengal (Chennai Coast)",
        "mannar": "Gulf of Mannar",
        "kochi": "Kerala Coast (Kochi)",
        "goa": "Goa Coast (Panaji)",
        "andaman": "Andaman Sea",
        "lakshadweep": "Lakshadweep Sea",
        "puri": "Odisha Coast (Puri)",
    }

    for word, name in city_keywords.items():
        if word in lower:
            match = next((l for l in locations if l.name == name), None)
            if match and match not in found:
                found.append(match)

    return found[:2]


def answer_superlative(db: Session, kind: str) -> str:
    rows = (
        db.query(OceanLocation, OceanObservation.wave_height, OceanObservation.sea_surface_temperature)
        .join(OceanObservation, OceanObservation.location_id == OceanLocation.id)
        .all()
    )
    # uniquify per location by taking any row
    by_loc: dict[int, Any] = {}
    for loc, wave, temp in rows:
        if loc.id not in by_loc:
            by_loc[loc.id] = {"loc": loc, "wave": wave, "temp": temp}
    items = list(by_loc.values())
    if not items:
        return "No data available yet — please sync live ocean data first."

    if kind == "warmest":
        best = max(items, key=lambda x: x["temp"] or -1)
        return f"🔥 The **warmest** region right now is *{best['loc'].name}* at **{best['temp']:.1f}°C**."
    if kind == "coldest":
        best = min(items, key=lambda x: x["temp"] or 99)
        return f"❄️ The **coolest** region right now is *{best['loc'].name}* at **{best['temp']:.1f}°C**."
    if kind == "calmest":
        best = min(items, key=lambda x: x["wave"] or 99)
        return f"🌊 The **calmest** water right now is at *{best['loc'].name}* with waves of **{best['wave']:.2f} m**."
    if kind == "waviest":
        best = max(items, key=lambda x: x["wave"] or -1)
        return f"🌊 The **roughest** water right now is at *{best['loc'].name}* with waves of **{best['wave']:.2f} m**."
    return "I couldn't determine that."


def answer_general() -> str:
    return (
        "I'm your Ocean Intelligence Assistant. 🌊 I can help with questions like:\n\n"
        "- *Is it safe to sail near Goa?*\n"
        "- *What's the temperature at Mumbai coast now?*\n"
        "- *Which region is the warmest?*\n"
        "- *Compare Chennai and Kochi conditions.*\n"
        "- *Is the sea warming up recently?*\n\n"
        "Ask me anything about your monitored regions!"
    )


# ---------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------

def answer_question(db: Session, question: str) -> dict[str, Any]:
    """
    The one function the API calls. Takes a question, returns:
    { answer, intent, location }
    """
    text = question.strip()
    if not text:
        return {"answer": "Please ask me something!", "intent": "general", "location": None}

    loc = _find_location(db, text)
    sup = detect_superlative(text)
    variables = detect_variables(text)
    comparison = is_comparison(text) or "compare" in text.lower()

    if sup:
        return {
            "answer": answer_superlative(db, sup),
            "intent": sup,
            "location": loc.name if loc else None,
        }

    if comparison or "both" in text.lower():
        pair = _find_two_locations(db, text)
        if len(pair) == 2:
            names = " vs ".join(l.name.split(" (")[0] for l in pair)
            # Build a per-location answer for a true 1-vs-1 comparison
            parts = [f"Comparing **{names}**:", ""]
            for loc in pair:
                obs = _latest(db, loc)
                if obs and obs.sea_surface_temperature is not None and obs.wave_height is not None:
                    parts.append(
                        f"- **{loc.name}**: {obs.sea_surface_temperature:.1f}°C, waves {obs.wave_height:.2f} m"
                    )
            if len(pair) == 2:
                a, b = pair
                oa, ob = _latest(db, a), _latest(db, b)
                if oa and ob and oa.sea_surface_temperature is not None and ob.sea_surface_temperature is not None:
                    diff = oa.sea_surface_temperature - ob.sea_surface_temperature
                    warmer = a.name.split(" (")[0] if diff > 0 else b.name.split(" (")[0]
                    parts.append("")
                    parts.append(f"💡 **{warmer}** is currently warmer by {abs(diff):.1f}°C.")
            return {"answer": "\n".join(parts), "intent": "compare", "location": None}

        return {
            "answer": answer_comparison(db, db.query(OceanLocation).limit(2).all()),
            "intent": "compare",
            "location": None,
        }

    if "safe" in text.lower() or "sail" in text.lower() or "fish" in text.lower() or "swim" in text.lower():
        return {
            "answer": answer_safety(loc, _latest(db, loc)),
            "intent": "safety",
            "location": loc.name if loc else None,
        }

    if "trend" in text.lower() or "ris" in text.lower() or "warm" in text.lower() and "how" not in text.lower():
        return {
            "answer": answer_trend(loc, _series(db, loc)),
            "intent": "trend",
            "location": loc.name if loc else None,
        }

    if variables:
        return {
            "answer": answer_current(loc, _latest(db, loc), variables),
            "intent": "current",
            "location": loc.name if loc else None,
        }

    return {
        "answer": answer_general(),
        "intent": "general",
        "location": loc.name if loc else None,
    }