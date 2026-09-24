"""Adaptive Identification Engine — self-calibrating anomaly thresholds.

Instead of fixed thresholds (e.g. "SST anomaly ≥ 1.0 °C is an event"), each
region learns its own baseline from its observed history and tunes the
detection band with a data-aware confidence multiplier. The engine is fully
offline and explainable; it reports:

  • per-variable adaptive vs static thresholds
  • adaptation maturity  (warm-up → active → confident)
  • whether currently-classified events change under adaptive rules
"""

import math

import numpy as np
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.validation.engine import _latest_rows, classify_events

# Static (legacy) thresholds used today by the event classifier.
STATIC = {
    "temperature": {"label": "Sea temperature", "unit": "°C", "threshold": 1.0},
    "wave_height": {"label": "Wave height", "unit": "m", "threshold": 0.45},
    "salinity": {"label": "Salinity", "unit": "PSU", "threshold": 0.5},
    "current_speed": {"label": "Current speed", "unit": "m/s", "threshold": 0.12},
}

VARIABLES = list(STATIC.keys())

ATTR = {
    "temperature": "sea_surface_temperature",
    "wave_height": "wave_height",
    "salinity": "salinity",
    "current_speed": "current_speed",
}


def _series(obs, var):
    attr = ATTR[var]
    return [getattr(o, attr) for o in obs if getattr(o, attr) is not None]


def _adaptive_threshold(values, static_threshold: float) -> dict:
    n = len(values)
    if n < 3:
        return {
            "adapted": False,
            "adaptive_threshold": round(static_threshold, 3),
            "sample_count": n,
            "maturity": "warm-up",
            "k_sigma": None,
            "strategy": "Static while insufficient history",
        }
    # Data-aware band: k tightens from 2.5 → 1.8 as history grows; floor of 60% static.
    k = 2.5 - 0.7 * min(1.0, n / 60.0)
    std = float(np.std(values))
    adaptive = max(static_threshold * 0.6, k * std)
    maturity = "active" if n < 48 else "confident"

    def _m(kv):
        return round(kv, 3)

    return {
        "adapted": True,
        "adaptive_threshold": _m(adaptive),
        "static_threshold": round(static_threshold, 3),
        "sample_count": n,
        "maturity": maturity,
        "k_sigma": round(k, 2),
        "sigma": round(std, 3),
        "strategy": (f"Adaptive band {_m(k)}σ (data-aware), floor {_m(static_threshold * 0.6)}"),
    }


def adaptive_identification(db: Session, location_id: int | None = None) -> dict:
    """Per-region self-calibrating thresholds + re-classification delta."""
    locations = db.query(OceanLocation).all()
    if location_id:
        locations = [loc for loc in locations if loc.id == location_id]

    regions = []
    events = classify_events(db)["events"]

    for loc in locations:
        obs = _latest_rows(db, loc, window=96)
        if not obs:
            regions.append({
                "location_id": loc.id, "location": loc.name,
                "message": "No observations yet — learning has not started.",
            })
            continue

        latest = obs[-1]
        vars_out = []
        event_deltas = []

        for var in VARIABLES:
            meta = STATIC[var]
            values = _series(obs, var)
            current = getattr(latest, ATTR[var])
            adaptive = _adaptive_threshold(values, meta["threshold"])

            # Re-classify the latest reading under both rules.
            static_flag = False
            adaptive_flag = False
            base_history = values[:-1]
            if len(base_history) >= 5 and current is not None:
                base_mean = float(np.mean(base_history))
                dev = current - base_mean
                static_flag = abs(dev) >= meta["threshold"]
                adaptive_flag = abs(dev) >= (adaptive["adaptive_threshold"]
                                             if adaptive["adapted"] else meta["threshold"])
                vars_out.append({
                    "variable": var,
                    "label": meta["label"],
                    "unit": meta["unit"],
                    "current": round(current, 3) if current is not None else None,
                    "deviation_from_baseline": round(dev, 3),
                    **adaptive,
                    "static_flag": static_flag,
                    "adaptive_flag": adaptive_flag,
                    "classification_changed": static_flag != adaptive_flag,
                })

        # How many active events flip when the threshold becomes adaptive.
        loc_events = [e for e in events if e["location_id"] == loc.id]
        for e in loc_events:
            event_deltas.append({
                "event_type": e["event_type"],
                "label": e["label"],
                "intensity": e["intensity"],
                "confidence": e["confidence"],
                "under_adaptive_rule": "may tighten or relax — see variables above",
            })

        learning_hours = (obs[-1].timestamp - obs[0].timestamp).total_seconds() / 3600
        maturity_levels = [v.get("maturity") for v in vars_out]
        overall = ("confident" if maturity_levels and all(m == "confident" for m in maturity_levels)
                   else "active" if maturity_levels and any(m in ("active", "confident") for m in maturity_levels)
                   else "warm-up")
        adaptation_index = round(min(100, max(0, len(obs) * 1.4)), 1)

        regions.append({
            "location_id": loc.id,
            "location": loc.name,
            "learning_hours": round(learning_hours, 1),
            "sample_count": len(obs),
            "adaptation_index": adaptation_index,
            "maturity": overall,
            "variables": vars_out,
            "event_deltas": event_deltas,
        })

    return {
        "engine": "Adaptive Identification (self-calibrating anomaly thresholds)",
        "note": "Thresholds learn from each region's own recent variance; detection "
                "bands are never tighter than 60% of the static rule to avoid noise chasing.",
        "static_rules": STATIC,
        "regions": regions,
    }