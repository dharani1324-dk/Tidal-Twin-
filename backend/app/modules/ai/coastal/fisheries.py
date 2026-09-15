"""
OceanVerse AI - Fisheries Advisory
==================================
Computes Fish Aggregation Zones (FAZ): where fish are most likely to
concentrate *right now* (temperature + chlorophyll + nutrients + currents)
and a 12-month seasonal fishing calendar per coast.

Explainable output: each score lists the drivers that pushed it up/down.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.services.ocean_data import get_location_center

# Preferred sea-surface temperature band for tropical Indian fisheries (°C)
SST_OPTIMAL = (25.0, 30.5)

# Region -> species priors (deterministic; illustrative of Indian waters)
SPECIES_BY_REGION = {
    "arabian": [("Indian mackerel", 0.92), ("Sardine", 0.88), ("Bombay duck", 0.74), ("Ribbonfish", 0.66)],
    "bengal": [("Hilsa", 0.9), ("Indian mackerel", 0.8), ("Pomfret", 0.72), ("Prawn", 0.68)],
    "mannar": [("Prawn", 0.9), ("Seer fish", 0.82), ("Reef fish", 0.78), ("Cuttlefish", 0.6)],
    "kerala": [("Oil sardine", 0.94), ("Indian mackerel", 0.86), ("Anchovy", 0.8), ("Seer fish", 0.62)],
    "goa": [("Indian mackerel", 0.9), ("Sardine", 0.82), ("Pomfret", 0.7), ("Shark", 0.5)],
    "andaman": [("Tuna", 0.9), ("Reef fish", 0.84), ("Grouper", 0.72), ("Sea cucumber", 0.5)],
    "lakshadweep": [("Tuna", 0.92), ("Flying fish", 0.78), ("Reef fish", 0.74), ("Snapper", 0.6)],
    "puri": [("Hilsa", 0.88), ("Pomfret", 0.8), ("Indian mackerel", 0.74), ("Prawn", 0.7)],
}

# Monsoon-driven seasonal phase (peak month) per region for the calendar
_PHASE_MONTH = {
    "arabian": 10, "kerala": 10, "goa": 11, "lakshadweep": 11,
    "bengal": 7, "puri": 8, "mannar": 6, "andaman": 3,
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _region_key(name: str) -> str:
    lower = name.lower()
    for key in SPECIES_BY_REGION:
        if key in lower:
            return key
    return "arabian"


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _seasonal_calendar(region_key: str) -> list[dict]:
    """12-month expected catch index (0-100) shaped by monsoon peaks."""
    peak = _PHASE_MONTH.get(region_key, 10)
    out: list[dict] = []
    for m in range(12):
        # gaussian bump around the peak, wider window = good season
        d = min((m - peak) % 12, (peak - m) % 12)
        idx = 100 * math.exp(-(d ** 2) / (2 * 2.2 ** 2))
        # monsoon (Jun-Sep) is the lean/closed season on most coasts
        if 5 <= m <= 8:
            idx *= 0.35
        out.append({"month": MONTHS[m], "index": round(idx)})
    return out


def compute_fisheries(db: Session) -> dict:
    """Build FAZ scores + seasonal calendar for every monitored coast."""
    locations = db.query(OceanLocation).all()
    regions: list[dict] = []
    now_month = datetime.now(timezone.utc).month - 1

    for loc in locations:
        rows = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())
            .limit(48)
            .all()
        )
        if not rows:
            continue
        obs = rows[0]

        sst = obs.sea_surface_temperature or 28.0
        chl = obs.chlorophyll or 0.5
        nut = obs.nutrients or 1.5
        cur = obs.current_speed or 0.15

        # --- productivity drivers (each normalised 0..1) ---
        temp_factor = 1.0 - min(1.0, abs(sst - 27.5) / 5.0)        # peak near 27.5°C
        chl_factor = _clamp01(chl / 4.0)                            # richer bloom = more fish
        nut_factor = _clamp01(nut / 4.0)
        current_factor = _clamp01(cur / 0.6)                        # mixing feeds the food web

        score = round(100 * (
            0.35 * temp_factor + 0.35 * chl_factor + 0.2 * nut_factor + 0.1 * current_factor
        ))
        if score >= 72:
            category = "prime"
        elif score >= 55:
            category = "good"
        elif score >= 35:
            category = "fair"
        else:
            category = "poor"

        rk = _region_key(loc.name)
        rng = random.Random(9000 + loc.id)
        species = []
        for name, base in SPECIES_BY_REGION[rk]:
            likelihood = round(100 * _clamp01(base * (0.6 + 0.5 * score / 100) + rng.uniform(-0.05, 0.05)), 0)
            species.append({"name": name, "likelihood": int(min(98, likelihood))})
        species.sort(key=lambda s: -s["likelihood"])

        drivers = sorted(
            [
                {"driver": "Temperature", "contribution": round(35 * temp_factor), "note": f"{sst:.1f}°C"},
                {"driver": "Chlorophyll", "contribution": round(35 * chl_factor), "note": f"{chl:.2f} mg/m³"},
                {"driver": "Nutrients", "contribution": round(20 * nut_factor), "note": f"{nut:.2f} µmol/L"},
                {"driver": "Currents", "contribution": round(10 * current_factor), "note": f"{cur:.2f} m/s"},
            ],
            key=lambda d: -d["contribution"],
        )

        regions.append({
            "location_id": loc.id,
            "location": loc.name,
            "faz_score": score,
            "category": category,
            "sst": round(sst, 2),
            "chlorophyll": round(chl, 2),
            "top_species": species[:3],
            "drivers": drivers,
            "seasonal_calendar": _seasonal_calendar(rk),
            "this_month_index": _seasonal_calendar(rk)[now_month]["index"],
        })

    regions.sort(key=lambda r: -r["faz_score"])
    prime = [r for r in regions if r["category"] in ("prime", "good")]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regions": regions,
        "summary": {
            "coasts": len(regions),
            "productive_now": len(prime),
            "best_zone": regions[0]["location"] if regions else None,
            "best_score": regions[0]["faz_score"] if regions else None,
        },
        "note": "FAZ blends SST, chlorophyll, nutrients and currents — advisory only.",
    }
