"""
TidalTwin - Ocean Situation / Decision Intelligence Summary
===============================================================
Aggregates the full twin state into a single "Ocean Situation" payload:
normal / watch / high-risk split, active events, high disagreements,
observation coverage, model trust and data-source health.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.modules.ai.safety.advisory import model_trust
from app.modules.ai.twin.compare import disagreement_map
from app.modules.ai.twin.events import detect_events
from app.modules.ai.twin.sources import data_sources
from app.modules.ai.validation.engine import observation_confidence


def situation(db: Session) -> dict:
    now = datetime.now(timezone.utc)

    disc = disagreement_map(db, variable="temperature", depth_m=0.0)
    points = [p for p in disc["points"] if p["status"] != "no data"]
    n = max(1, len(points))
    normal = sum(1 for p in points if p["band"] == "green")
    watch = sum(1 for p in points if p["band"] in ("yellow", "orange"))
    high = sum(1 for p in points if p["band"] == "red")

    events = detect_events(db)
    active_events = [e for e in events["events"] if e.get("current_status", "").lower() in ("active", "developing")]

    high_disagreements = sum(1 for p in points if p["status"] == "high")

    obs_conf = observation_confidence(db)
    regions_conf = obs_conf.get("regions", [])
    coverage = 0
    if regions_conf:
        with_data = [r for r in regions_conf if r.get("observation_confidence", 0) > 0]
        coverage = round(len(with_data) / len(regions_conf) * 100.0)

    trust = model_trust(db)
    trust_regions = trust.get("regions", [])
    model_trust_avg = round(sum(r.get("trust_score", 0) for r in trust_regions) / max(1, len(trust_regions)))

    src = data_sources(db)
    locations = db.query(OceanLocation).count()

    return {
        "generated_at": now.isoformat(),
        "coast_count": locations,
        "split": {
            "normal_regions_pct": round(normal / n * 100.0),
            "watch_regions_pct": round(watch / n * 100.0),
            "high_risk_regions_pct": round(high / n * 100.0),
        },
        "active_events": len(active_events),
        "total_events": len(events["events"]),
        "high_disagreements": high_disagreements,
        "observation_coverage_pct": coverage,
        "model_trust": model_trust_avg,
        "data_sources": src["health"],
        "summary": (
            f"{len(active_events)} active event(s), {high_disagreements} high disagreement(s). "
            f"Observation coverage {coverage}%, model trust {model_trust_avg}%."
        ),
    }