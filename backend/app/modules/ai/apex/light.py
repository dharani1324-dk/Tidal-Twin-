"""Light Pollution & Artificial-Light-at-Night (ALAN) impact on coasts.

Illuminates the human-influenced environmental dimension that satellite ocean
monitoring often ignores. Uses a deterministic exposure proxy (seeded per
region) so scores are stable, with biota-specific impact (turtle nesting,
zooplankton migration, fish behaviour, coral stress) and mitigation advice.

Note: the exposure proxy would be sourced from VIIRS Night-Lights (DNB) in a
connected deployment — this engine remains the offline, explainable estimate.
"""

import random

from sqlalchemy.orm import Session

from app.models.location import OceanLocation


def _rng(loc_id: int):
    return random.Random(loc_id * 977 + 31)


def _base_exposure(loc) -> float:
    """0–100 proxy from region type + name heuristics."""
    name = loc.name.lower()
    if any(k in name for k in ("mumbai", "chennai", "kochi", "puri", "kerala", "tamil")):
        base = _rng(loc.id).uniform(58, 82)
    elif any(k in name for k in ("goa", "bengal", "odisha", "andaman")):
        base = _rng(loc.id).uniform(30, 55)
    else:
        base = _rng(loc.id).uniform(8, 30)

    if loc.region_type == "coastal":
        base += 12
    elif loc.region_type == "port":
        base += 18
    elif loc.region_type in ("reef", "bay"):
        base -= 8
    return max(0.0, min(100.0, base))


def _impact_scores(exposure: float) -> dict:
    def _mul(weight: float) -> float:
        return round(min(100.0, exposure * weight), 1)

    return {
        "sea_turtle_hatchling_disorientation": _mul(0.95),
        "zooplankton_diel_migration_disruption": _mul(0.8),
        "fish_spawning_behaviour": _mul(0.7),
        "coral_polyp_stress": _mul(0.55),
    }


def _band(exposure: float) -> dict:
    if exposure >= 75:
        return {"severity": "extreme", "color": "#f43f5e",
                "advice": "Encourage shielded warm-LED retrofits and dark-sky curfews "
                          "within 2 km of turtle-nesting beaches."}
    if exposure >= 55:
        return {"severity": "high", "color": "#f97316",
                "advice": "Set lighting curfews during nesting/hatching season; "
                          "reduce upward spill on promenades."}
    if exposure >= 30:
        return {"severity": "moderate", "color": "#f59e0b",
                "advice": "Prefer fully-shielded downward fixtures; monitor hatchling traps."}
    return {"severity": "low", "color": "#10b981",
            "advice": "No immediate action — keep remote-reef lighting minimal to preserve habitat."}


def light_pollution(db: Session) -> dict:
    regions = []
    for loc in db.query(OceanLocation).all():
        exposure = round(_base_exposure(loc), 1)
        band = _band(exposure)
        regions.append({
            "location_id": loc.id,
            "location": loc.name,
            "aln_exposure_score": exposure,           # artificial light at night proxy (0-100)
            "severity": band["severity"],
            "color": band["color"],
            "biota_impact": _impact_scores(exposure),
            "recommendation": band["advice"],
            "source_proxy": "VIIRS Night-Lights DNB (synthetic proxy in offline mode)",
        })
    regions.sort(key=lambda r: -r["aln_exposure_score"])
    return {
        "engine": "Light Pollution & ALAN impact (offline proxy)",
        "regions": regions,
    }