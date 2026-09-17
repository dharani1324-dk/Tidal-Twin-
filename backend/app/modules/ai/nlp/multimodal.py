"""
TidalTwin - Multimodal Ocean Intelligence
=============================================
Fuses *different kinds of input* (a pasted field report / news snippet /
satellite metadata / NetCDF summary + our live sensor engines) into one
evidence-based answer.

How it works (fully explainable — no external API):
  1. Location parsing  — which coast(s) does the document mention?
  2. Claim extraction  — sentences with a variable keyword + a number
                         are treated as "claims" ("SST reached 30.2°C").
  3. Live comparison   — each claim is checked against our latest real
                         observation: SUPPORTS / DISAGREES / UNVERIFIABLE.
  4. Sensor verdict    — active alerts + classified events for those coasts.
  5. Fusion            — a single answer quoting document + sensor evidence
                         with agreement scoring and citations.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation

# variable keyword → observation column + unit
CLAIM_VARIABLES: dict[str, dict] = {
    "temperature": {"col": "sea_surface_temperature", "unit": "°C", "words": ["temperature", "temp", "sst", "water warmth"]},
    "waves": {"col": "wave_height", "unit": "m", "words": ["wave", "waves", "swell", "wave height"]},
    "salinity": {"col": "salinity", "unit": "PSU", "words": ["salinity", "salt"]},
    "oxygen": {"col": "dissolved_oxygen", "unit": "mg/L", "words": ["oxygen", "dissolved oxygen", "o2", "hypoxia"]},
    "chlorophyll": {"col": "chlorophyll", "unit": "mg/m³", "words": ["chlorophyll", "chl", "algal bloom", "algae"]},
}

_LOCATION_ALIASES: dict[str, list[str]] = {
    "mumbai": ["mumbai", "arabian", "bombay", "maharashtra"],
    "chennai": ["chennai", "bengal", "madras", "tamil"],
    "mannar": ["mannar", "gulf of mannar"],
    "kochi": ["kochi", "kerala", "cochin"],
    "goa": ["goa", "panaji", "panjim"],
    "andaman": ["andaman"],
    "lakshadweep": ["lakshadweep"],
    "puri": ["puri", "odisha", "orissa"],
}

_TOLERANCE = {"temperature": 1.5, "waves": 0.4, "salinity": 0.5, "oxygen": 1.0, "chlorophyll": 1.0}
_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def _resolve_locations(db: Session, text: str) -> list[OceanLocation]:
    """Return every location whose name / alias appears in the text."""
    lower = text.lower()
    found: list[OceanLocation] = []
    for loc in db.query(OceanLocation).all():
        if loc.name.lower() in lower:
            found.append(loc)
            continue
        hit = False
        for key, aliases in _LOCATION_ALIASES.items():
            if key in loc.name.lower() and any(a in lower for a in aliases):
                hit = True
                break
        if hit:
            found.append(loc)
    return found


def _sentence_claims(text: str) -> list[dict]:
    """Pull (variable, value) claims: the number nearest each variable keyword
    in the same sentence (so 'SST 30.2°C, waves 1.8 m' pairs correctly)."""
    clean = re.sub(r"\s+", " ", text).replace("\n", " ")
    claims: list[dict] = []
    seen: set[tuple[str, str, float]] = set()
    for sentence in [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean)]:
        lower = sentence.lower()
        if not _NUM.search(sentence):
            continue
        matches = list(_NUM.finditer(sentence))
        if not matches:
            continue
        for var, cfg in CLAIM_VARIABLES.items():
            hits = [w for w in cfg["words"] if w in lower]
            if not hits:
                continue
            # anchor = the keyword hit position (use its END so an occurrence
            # like "wave height" doesn't sit between two numbers)
            anchor_idx = lower.index(hits[0])
            anchor_end = anchor_idx + len(hits[0])
            after = [m for m in matches if m.start() >= anchor_end]
            before = [m for m in matches if m.start() < anchor_idx]
            # Prefer numbers that follow the keyword ("wave height of 1.8 m"),
            # otherwise fall back to the nearest number before it.
            if after:
                nearest = min(after, key=lambda m: abs(m.start() - anchor_end))
            else:
                nearest = min(before, key=lambda m: abs(anchor_idx - m.start())) if before else None
            if nearest is None:
                continue
            v = float(nearest.group())
            key = (var, sentence[:60], v)
            if key in seen:
                continue
            seen.add(key)
            claims.append({"variable": var, "sentence": sentence[:280], "value": v, "unit": cfg["unit"]})
    return claims


def _latest_obs(db: Session, loc: OceanLocation) -> OceanObservation | None:
    return (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .first()
    )


def _active_alerts(db: Session, loc_id: int) -> list[dict]:
    from app.models.alert import OceanAlert

    alerts = (
        db.query(OceanAlert)
        .filter(OceanAlert.location_id == loc_id, OceanAlert.status == "active")
        .order_by(OceanAlert.created_at.desc())
        .limit(3)
        .all()
    )
    return [{"type": a.alert_type, "severity": a.severity, "description": a.description} for a in alerts]


def _live_events(db: Session, loc_id: int) -> list[dict]:
    from app.modules.ai.validation.engine import classify_events

    events = classify_events(db).get("events", [])
    return [
        {"type": e["event_type"], "label": e.get("label"), "intensity": e.get("intensity"), "confidence": e.get("confidence")}
        for e in events
        if e.get("location_id") == loc_id
    ]


def _compare_claim(db: Session, claim: dict, live: dict) -> dict:
    """Grade one claim against a live observation."""
    col = CLAIM_VARIABLES[claim["variable"]]["col"]
    live_val = live.get(col)
    if live_val is None:
        verdict, note = "unverifiable", "no live reading for this variable right now"
    else:
        tol = _TOLERANCE[claim["variable"]]
        diff = claim["value"] - live_val
        if abs(diff) <= tol:
            verdict, note = "supports", (
                f"document agrees with live sensor ({live_val:.1f} {claim['unit']})"
            )
        else:
            verdict, note = "disagrees", (
                f"document differs from live sensor ({live_val:.1f} {claim['unit']}, Δ {diff:+.1f})"
            )
    return {
        "variable": claim["variable"],
        "sentence": claim["sentence"],
        "claimed": claim["value"],
        "unit": claim["unit"],
        "live": round(live_val, 2) if live_val is not None else None,
        "verdict": verdict,
        "note": note,
    }


def multimodal_fuse(db: Session, text: str, media: dict | None = None) -> dict:
    """
    Core fusion entry-point used by both the REST endpoint and the Copilot
    'multimodal' intent. Returns the standard assistant response shape.
    """
    text = text or ""
    doc = media or {}
    doc_type = doc.get("type") or "document"
    instrument = doc.get("instrument") or doc.get("detector") or doc.get("sensor")
    source_label = {
        "satellite": "satellite remote-sensing pass",
        "netcdf": "NetCDF model/observation file summary",
        "buoy": "in-situ buoy / mooring feed",
        "field": "field survey report",
        "news": "news / situational report",
        "document": "attached document",
    }.get(doc_type, "attached input")

    locations = _resolve_locations(db, text)
    if not locations:
        locations = db.query(OceanLocation).order_by(OceanLocation.id.asc()).limit(1).all()
        note_loc = "No coast was named in the input — fell back to the first monitored coast:"
    else:
        note_loc = "Document mentions coast(s):"

    claims = _sentence_claims(text)
    rows: list[dict] = []
    live_map: dict[int, dict] = {}
    evs: list[dict] = []
    alerts: list[dict] = []

    for loc in locations:
        obs = _latest_obs(db, loc)
        live = {
            "sea_surface_temperature": getattr(obs, "sea_surface_temperature", None),
            "wave_height": getattr(obs, "wave_height", None),
            "salinity": getattr(obs, "salinity", None),
            "dissolved_oxygen": getattr(obs, "dissolved_oxygen", None),
            "chlorophyll": getattr(obs, "chlorophyll", None),
        } if obs else {}
        live_map[loc.id] = live
        alerts += _active_alerts(db, loc.id)
        evs += _live_events(db, loc.id)

        loc_claims = [c for c in claims]  # claims are coast-agnostic — attach to each
        for c in loc_claims:
            rows.append({**_compare_claim(db, c, live), "location": loc.name})

    # De-duplicate rows where the same (variable,claimed) appears for the same coast.
    seen_rows: set[tuple[str, str, float]] = set()
    unique_rows: list[dict] = []
    for r in rows:
        key = (r["location"], r["variable"], r["claimed"])
        if key in seen_rows:
            continue
        seen_rows.add(key)
        unique_rows.append(r)
    rows = unique_rows

    verifiable = [r for r in rows if r["verdict"] != "unverifiable"]
    agrees = sum(1 for r in verifiable if r["verdict"] == "supports")
    score = round(agrees / len(verifiable) * 100) if verifiable else None

    loc_names = ", ".join(l.name for l in locations)
    if rows:
        agree_lines = "\n".join(f"  • {r['location']} · {r['variable']}: {r['claimed']}{r['unit']} → {r['verdict']} — {r['note']}" for r in rows)
    else:
        agree_lines = "  • No numeric claims were found in the input text — nothing to verify."

    alert_line = (
        "  • Active sensor alerts: " + "; ".join(
            f"{a['type']} ({a['severity']})" for a in alerts[:3]
        )
        if alerts else "  • No active sensor alerts on the mentioned coasts."
    )
    event_line = (
        "  • Classified events: " + "; ".join(
            f"{e['label']} ({e['intensity']}, conf {e['confidence']}%)" for e in evs[:3]
        )
        if evs else "  • No classified events on the mentioned coasts."

    )

    media_clause = (
        f" Input carrier: a {source_label} ({instrument} mode), enriched with platform sensors."
        if instrument else f" Input carrier: a {source_label}, cross-checked with platform sensors."
    )

    if verifiable:
        verdict_sentence = (
            f"Across {len(verifiable)} verifiable claim(s), the attached input agrees with live sensors "
            f"{agrees}/{len(verifiable)} of the time (overall agreement {score}%)."
        )
    else:
        verdict_sentence = "The attachment contains no sensor-verifiable numbers — I summarized its narrative themes instead."

    answer = (
        f"{note_loc} **{loc_names}**\n\n"
        f"**Fusion summary** — {source_label} cross-checked against the TidalTwin live network. "
        f"{verdict_sentence}{media_clause}\n\n"
        f"**Claim-by-claim traceability:**\n{agree_lines}\n\n"
        f"**Sensor context on the ground:**\n{alert_line}\n{event_line}"
    )

    theme_words = detect_themes(text)
    chips = [
        {"label": "locations", "value": [l.name for l in locations]},
        {"label": "carrier", "value": source_label},
        {"label": "themes", "value": theme_words},
    ]
    if verifiable:
        chips.append({"label": "agreement", "value": f"{score}%"})

    data = {
        "type": "chips",
        "items": chips,
        "rows": rows,
        "alerts": alerts,
        "events": evs,
    }

    return {
        "answer": answer,
        "intent": "multimodal",
        "location": locations[0].name if locations else None,
        "location_id": locations[0].id if locations else None,
        "data": data,
        "sources": [
            "live observation history (sea_surface_temperature, wave_height, salinity, dissolved_oxygen, chlorophyll)",
            "anomaly detector active alerts" if alerts else "anomaly detector (no active alerts)",
            "REST /validation/events classification",
            f"attached {doc_type} input (metadata only, not stored)",
        ],
        "steps": [
            "parse document for named coasts & numeric claims",
            "grade each claim against the latest live sensor reading",
            "attach alarms (anomaly detector) + classified events for those coasts",
            "fuse into a single evidence-chain answer",
        ],
        "suggestions": [
            "Show the live conditions behind these claims.",
            "What would happen if this event continued for 48 hours?",
            "Which coast should we observe to confirm the disagreement?",
        ],
        "context": {
            "last_location_id": locations[0].id if locations else None,
            "last_intent": "multimodal",
        },
    }


def detect_themes(text: str) -> list[str]:
    """Squash free text down to a few ocean theme tags (document analysis)."""
    lower = text.lower()
    themes: list[str] = []
    if any(w in lower for w in ("marine heatwave", "heat wave", "warming", "temperature spike")):
        themes.append("thermal stress")
    if any(w in lower for w in ("algal bloom", "algae", "chlorophyll")):
        themes.append("algal bloom")
    if any(w in lower for w in ("hypoxia", "deoxygenation", "oxygen", "dead zone")):
        themes.append("oxygen stress")
    if any(w in lower for w in ("flood", "storm", "cyclone", "surge", "wave")):
        themes.append("maritime hazard")
    if any(w in lower for w in ("carbon", "co2", "emission", "sink")):
        themes.append("carbon cycle")
    if any(w in lower for w in ("light pollution", "artificial light", "turtle", "bioluminescence")):
        themes.append("coastal ecology")
    if any(w in lower for w in ("salinity", "salt", "freshwater", "river")):
        themes.append("water mixing")
    return themes or (["narrative / general"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()