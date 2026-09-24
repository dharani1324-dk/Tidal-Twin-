"""
TidalTwin - Ocean Event Detection
=====================================
Surface-level events are detected only when the available data satisfies
defined thresholds (reusing the core classifier). Each event is enriched
with a model-vs-observation difference, evidence and a data-status label.
No event is claimed without data crossing its threshold.

Events originating from clearly-labelled demo rows (SIMULATED_*) carry
``data_status = demo`` so the UI can show them as a demonstration, never
as a real ocean event.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.modules.ai.twin.compare import VARIABLES, compare
from app.modules.ai.validation.engine import classify_events

# Rank (bigger = more important) attached per event type for UI ordering.
EVENT_RANK = {
    "marine_heatwave": 5,
    "coastal_flooding_risk": 5,
    "cold_water_anomaly": 4,
    "model_mismatch_event": 4,
    "strong_current_event": 3,
    "rapid_temp_change": 2,
}

_VAR_FOR_EVENT = {
    "marine_heatwave": "temperature",
    "cold_water_anomaly": "temperature",
    "rapid_temp_change": "temperature",
    "strong_current_event": "current_speed",
    "coastal_flooding_risk": "wave_height",
    "model_mismatch_event": "temperature",
}


def detect_events(db: Session, location_id: int | None = None) -> dict:
    base = classify_events(db)
    events = base.get("events", [])
    locs = {l.id: l for l in db.query(OceanLocation).all()}

    # Enrich with the twin compare view: model vs observed difference + evidence.
    for ev in events:
        loc = locs.get(ev.get("location_id"))
        if loc is None:
            continue
        var = _VAR_FOR_EVENT.get(ev.get("event_type"), "temperature")
        res = compare(db, loc, variable=var)
        if isinstance(res, dict) and res.get("error") is None:
            ev["model"] = res.get("model")
            ev["observed"] = res.get("observed")
            ev["model_observed_diff"] = res.get("difference")
            ev["model_observed_pct"] = res.get("percent_difference")
            ev["data_status"] = res.get("data_status")
            ev["meta"] = {
                "label": VARIABLES.get(var, {}).get("label", var),
                "unit": VARIABLES.get(var, {}).get("unit", ""),
            }
        ev["current_status"] = "active"
        ev["rank"] = EVENT_RANK.get(ev.get("event_type"), 0)

    if location_id is not None:
        events = [e for e in events if e.get("location_id") == location_id]

    events.sort(key=lambda e: (e.get("rank", 0), e.get("confidence", 0) or 0), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": base.get("summary", {}),
        "events": events,
    }