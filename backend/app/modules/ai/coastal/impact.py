"""
OceanVerse AI - Economic Impact Estimator
========================================
Converts classified ocean events into monetary impact (INR) for
decision-makers: fishing-fleet hours lost, port disruption, tourism loss.

Deterministic scales seeded per region (fleet size, port throughput,
tourism arrivals) — illustrative but consistent across runs.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.modules.ai.validation.engine import classify_events

# per-activity coeffs shared across event types
HOURLY_CATCH_VALUE_INR = 6_500      # fleet hour of potential catch value
INTENSITY_FACTOR = {"low": 0.35, "medium": 0.7, "high": 1.0}

# tourism seasonality: today's month weight (Nov-Feb peak for most coasts)
TOURISM_WEIGHT = {1: 1.0, 2: 1.0, 3: 0.8, 4: 0.6, 5: 0.45, 6: 0.4,
                  7: 0.4, 8: 0.5, 9: 0.7, 10: 0.9, 11: 1.0, 12: 1.0}


def _region_economy(loc: OceanLocation):
    rng = random.Random(5200 + loc.id)
    return {
        "fishing_boats": int(rng.uniform(120, 1900)),
        "port_throughput_inr_hr": rng.uniform(60_000, 420_000),
        "tourism_arrivals_yr": int(rng.uniform(120_000, 2_600_000)),
        "avg_tourist_spend_inr": rng.uniform(1_200, 4_500),
    }


def compute_economic_impact(db: Session) -> dict:
    events = classify_events(db)["events"]
    month = datetime.now(timezone.utc).month
    tourism_w = TOURISM_WEIGHT.get(month, 0.8)

    loc_by_id = {l.id: l for l in db.query(OceanLocation).all()}
    economy: dict[int, dict] = {l.id: _region_economy(l) for l in loc_by_id.values()}

    line_items: list[dict] = []
    by_coast: dict[int, dict] = {}

    for ev in events:
        loc = loc_by_id.get(ev.get("location_id"))
        if loc is None:
            continue
        econ = economy[loc.id]
        intensity = ev.get("intensity") or "medium"
        factor = INTENSITY_FACTOR.get(intensity, 0.7)

        hours = ev.get("span", {}).get("hours_on") or 6

        boats = econ["fishing_boats"]
        fleet_hours = int(boats * hours * factor)
        fishing_loss = int(fleet_hours * HOURLY_CATCH_VALUE_INR * 0.6)

        port_hours = min(hours, 24)
        port_disruption = int(econ["port_throughput_inr_hr"] * port_hours * factor * 0.55)

        arrivals_per_day = econ["tourism_arrivals_yr"] / 365
        days = min(max(hours / 24, 1), 5)
        tourism_loss = int(arrivals_per_day * econ["avg_tourist_spend_inr"] * days * factor * tourism_w * 0.4)

        total = fishing_loss + port_disruption + tourism_loss
        line_items.append({
            "location_id": loc.id,
            "location": loc.name,
            "event_type": ev.get("event_type"),
            "label": ev.get("label"),
            "intensity": intensity,
            "duration_h": int(hours),
            "fishing_loss_inr": fishing_loss,
            "port_disruption_inr": port_disruption,
            "tourism_loss_inr": tourism_loss,
            "total_inr": total,
        })

        by = by_coast.setdefault(loc.id, {"location": loc.name, "total_inr": 0, "events": []})
        by["total_inr"] += total
        by["events"].append(ev.get("event_type"))

    line_items.sort(key=lambda x: -x["total_inr"])
    coasts = [{"location_id": k, **v} for k, v in sorted(
        by_coast.items(), key=lambda kv: -kv[1]["total_inr"])]

    total = sum(i["total_inr"] for i in line_items)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "line_items": line_items,
        "coasts": coasts,
        "summary": {
            "active_events": len(line_items),
            "coasts_impacted": len(coasts),
            "total_estimated_loss_inr": total,
            "total_estimated_loss_cr": round(total / 1e7, 2),
            "largest_loss_inr": line_items[0]["total_inr"] if line_items else 0,
            "largest_loss_coast": line_items[0]["location"] if line_items else None,
            "breakdown": {
                "fishing_loss_inr": sum(i["fishing_loss_inr"] for i in line_items),
                "port_loss_inr": sum(i["port_disruption_inr"] for i in line_items),
                "tourism_loss_inr": sum(i["tourism_loss_inr"] for i in line_items),
            },
        },
        "note": "Illustrative disaster-economics scaling — calibrate with BPRS/SIH statistics for production.",
    }