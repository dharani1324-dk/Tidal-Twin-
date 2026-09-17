"""
TidalTwin - Sea-Level-Rise Inundation Simulator
===================================================
For a chosen sea-level-rise scenario (e.g. +0.5 m, +1.0 m) estimates which
coastal settlements, land area and population would be inundated.

Each monitored coast gets a deterministic, seed-stable set of nearby
settlements with elevations and populations (illustrative coastal-town
profiles — replace with real DEM/GIS data in production).
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation

SCENARIOS = [0.3, 0.5, 1.0, 2.0]

_NAME_POOL = [
    "Versova", "Colaba", "Sewri", "Ennore", "Kovalam", "Fort Kochi", "Vypin",
    "Calangute", "Baga", "Havelock", "Port Blair", "Kavaratti", "Minicoy",
    "Puri Beach", "Chandipur", "Dhanushkodi", "Rameswaram", "Nagapattinam",
    "Bakkhali", "Digha", "Kollam", "Alappuzha", "Karwar", "Malpe", "Kadmat",
]


def _towns_for(loc: OceanLocation) -> list[dict]:
    rng = random.Random(3100 + loc.id)
    n = 4
    start = (loc.id * 3) % len(_NAME_POOL)
    towns = []
    for i in range(n):
        name = _NAME_POOL[(start + i) % len(_NAME_POOL)]
        elevation = round(max(0.1, rng.gauss(0.9, 0.75)), 2)     # metres above MSL
        population = int(rng.uniform(8_000, 220_000))
        distance_km = round(rng.uniform(0.3, 9.0), 1)
        towns.append({
            "name": name,
            "elevation_m": elevation,
            "population": population,
            "distance_from_coast_km": distance_km,
        })
    towns.sort(key=lambda t: t["elevation_m"])
    return towns


def slr_inundation(db: Session, scenario_m: float = 1.0) -> dict:
    scenario_m = max(0.1, min(5.0, scenario_m))
    locations = db.query(OceanLocation).all()

    regions: list[dict] = []
    total_area = 0.0
    total_pop = 0
    all_towns: list[dict] = []

    for loc in locations:
        towns = _towns_for(loc)
        affected = [t for t in towns if t["elevation_m"] <= scenario_m]
        affected_pop = sum(t["population"] for t in affected)
        # crude area: ~0.35 km² per 1000 affected people, capped
        area_km2 = round(affected_pop / 1000 * 0.35, 1)
        impact_pct = round(100 * len(affected) / len(towns))

        level = "severe" if impact_pct >= 75 else "high" if impact_pct >= 50 else "moderate" if impact_pct > 0 else "minimal"

        total_area += area_km2
        total_pop += affected_pop
        for t in affected:
            all_towns.append({**t, "location": loc.name})

        regions.append({
            "location_id": loc.id,
            "location": loc.name,
            "towns": towns,
            "affected_towns": [t["name"] for t in affected],
            "affected_count": len(affected),
            "impact_pct": impact_pct,
            "land_area_lost_km2": area_km2,
            "population_at_risk": affected_pop,
            "level": level,
        })

    regions.sort(key=lambda r: -r["population_at_risk"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_m": scenario_m,
        "available_scenarios": SCENARIOS,
        "regions": regions,
        "summary": {
            "coasts_analyzed": len(regions),
            "towns_inundated": len(all_towns),
            "total_land_area_lost_km2": round(total_area, 1),
            "total_population_at_risk": total_pop,
            "most_affected": regions[0]["location"] if regions else None,
        },
        "note": "Illustrative settlement elevations — swap in a real DEM for operational use.",
    }
