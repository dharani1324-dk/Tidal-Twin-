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
from app.modules.ai.validation.engine import OBS_WINDOW, _classify_series, _demo_rows, _latest_rows, classify_events

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


def _classify_demo_events(db: Session) -> list[dict]:
    """Classify clearly-labelled SIMULATED/SYNTHETIC rows into DEMONSTRATION
    events. Every event carries ``data_status = "demo"`` and a note so the UI
    shows them as a demonstration, never as a real ocean event.

    The demo rows are classified TOGETHER with the real background stream for
    that coast — exactly how the detector would see the full observation feed —
    so an engineered ~+2°C demo anomaly crosses the same thresholds a genuine
    anomaly would. Tagging stays ``demo`` whenever demo rows are present.
    """
    demo_events: list[dict] = []
    for loc in db.query(OceanLocation).all():
        demo = _demo_rows(db, loc, window=OBS_WINDOW)
        if not demo:
            continue
        merged = sorted(_latest_rows(db, loc, window=OBS_WINDOW) + demo, key=lambda o: o.timestamp)
        merged = merged[-OBS_WINDOW:]
        for ev in _classify_series(loc, merged, mismatch=False):
            ev["data_status"] = "demo"
            ev["note"] = ("Derived from clearly-labelled SIMULATED demo rows "
                          "(SIMULATED_*) — demonstration only, never a real ocean event.")
            demo_events.append(ev)
    return demo_events


def detect_events(db: Session, location_id: int | None = None) -> dict:
    base = classify_events(db)
    events = base.get("events", [])
    events.extend(_classify_demo_events(db))
    locs = {l.id: l for l in db.query(OceanLocation).all()}

    # Enrich with the twin compare view: model vs observed difference + evidence.
    for ev in events:
        loc = locs.get(ev.get("location_id"))
        if loc is None:
            continue
        var = _VAR_FOR_EVENT.get(ev.get("event_type"), "temperature")
        res = compare(db, loc, variable=var)
        demo = ev.get("data_status") == "demo"
        if isinstance(res, dict) and res.get("error") is None:
            ev["model"] = res.get("model")
            ev["observed"] = res.get("observed")
            ev["model_observed_diff"] = res.get("difference")
            ev["model_observed_pct"] = res.get("percent_difference")
            if not demo:
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
    summary = {e["event_type"]: sum(1 for x in events if x["event_type"] == e["event_type"]) for e in events}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "events": events,
    }