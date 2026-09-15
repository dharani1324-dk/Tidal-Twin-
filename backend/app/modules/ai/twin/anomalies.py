"""
OceanVerse AI - Anomaly Intelligence / Ranking Engine
=====================================================
Automatically identifies and ranks the most significant model-vs-observation
anomalies across all monitored regions.

Ranking score is DEFINED, not random, and weights:
    magnitude, spatial extent, duration, confidence, number of supporting
    observations and rate of change.

Supports sorting / filtering by severity, variable, region and confidence.
"""

from datetime import datetime, timezone

import numpy as np
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.modules.ai.twin.compare import VARIABLES, compare
from app.modules.ai.validation.engine import _latest_rows

# Variables eligible for anomaly ranking.
RANK_VARIABLES = ["temperature", "wave_height"]

# Score weights (sum = 1.0) - declared for transparency.
W_MAGNITUDE = 0.30
W_EXTENT = 0.15
W_DURATION = 0.15
W_CONFIDENCE = 0.15
W_SUPPORT = 0.10
W_RATE = 0.10


def _magnitude_score(res: dict) -> float:
    if res.get("difference") is None:
        return 0.0
    meta = VARIABLES[res["variable"]]
    a = abs(res["difference"])
    return min(100.0, a / meta["high"] * 100.0)


def _duration_h(column: str, loc: OceanLocation, db: Session) -> float:
    """Consecutive hours the series has sat beyond its history-conditioned normal."""
    obs = _latest_rows(db, loc)
    values = [getattr(o, column) for o in obs if getattr(o, column) is not None]
    if len(values) < 5:
        return 0.0
    mean = float(np.mean(values[:-1]))
    last = values[-1]
    if abs(last - mean) < (abs(mean) * 0.01 if mean else 0.05):
        return 0.0
    hours = 0
    for v in reversed(values[:-1]):
        if (v - mean) * (last - mean) > 0:  # same sign as the latest deviation
            hours += 1
        else:
            break
    return float(hours)


def _rate_per_h(column: str, db: Session) -> float:
    """Maximum hour-to-hour change in the latest window (indicative of impulse)."""
    locs = db.query(OceanLocation).all()
    vs: list[float] = []
    for loc in locs:
        obs = _latest_rows(db, loc)
        values = [getattr(o, column) for o in obs if getattr(o, column) is not None]
        if len(values) < 2:
            continue
        step = max(abs(b - a) for a, b in zip(values[-13:], values[-12:]))
        vs.append(step)
    return float(np.mean(vs)) if vs else 0.0


def _extent_pct(db: Session, variable: str, sign_positive: bool) -> float:
    """Fraction of the network deviating in the same direction."""
    locs = db.query(OceanLocation).all()
    total = 0
    same = 0
    for loc in locs:
        res = compare(db, loc, variable=variable)
        d = res.get("difference")
        if d is None:
            continue
        total += 1
        if (d > 0) == sign_positive:
            same += 1
    return (same / total * 100.0) if total else 0.0


def rank_anomalies(
    db: Session,
    variable: str | None = None,
    severity: str | None = None,
    region: str | None = None,
    min_confidence: int = 0,
    sort: str = "severity",
) -> dict:
    locs = db.query(OceanLocation).all()
    rows = []

    for loc in locs:
        for var in RANK_VARIABLES:
            if variable and var != variable:
                continue
            res = compare(db, loc, variable=var)
            if res.get("status") in ("no data", "unknown"):
                continue

            col = VARIABLES[var]["column"]
            mag = _magnitude_score(res)
            duration_h = _duration_h(col, loc, db)
            rate = _rate_per_h(col, db)
            extent = _extent_pct(db, var, (res.get("difference") or 0) > 0)
            conf = res.get("confidence", 0) or 0
            support = min(100.0, len(_latest_rows(db, loc)) / 96.0 * 100.0)

            score = round(
                W_MAGNITUDE * mag
                + W_EXTENT * extent
                + W_DURATION * min(100.0, duration_h * 10.0)
                + W_CONFIDENCE * conf
                + W_SUPPORT * support
                + W_RATE * min(100.0, rate * 100.0),
                1,
            )

            sev = res["severity"]
            # escalate when many factors align
            if score >= 65 and sev in ("low", "medium"):
                sev = "high" if score >= 75 else "medium"

            rows.append(
                {
                    "location_id": loc.id,
                    "location": loc.name,
                    "latitude": res.get("latitude"),
                    "longitude": res.get("longitude"),
                    "variable": var,
                    "label": VARIABLES[var]["label"],
                    "unit": VARIABLES[var]["unit"],
                    "model": res.get("model"),
                    "observed": res.get("observed"),
                    "difference": res.get("difference"),
                    "percent_difference": res.get("percent_difference"),
                    "severity": sev,
                    "status": res.get("status"),
                    "confidence": conf,
                    "confidence_level": res.get("confidence_level"),
                    "score": score,
                    "magnitude": round(mag, 1),
                    "spatial_extent_pct": round(extent, 1),
                    "duration_h": round(duration_h, 1),
                    "rate_per_h": round(rate, 3),
                    "supporting_observations": len(_latest_rows(db, loc)),
                    "data_status": res.get("data_status"),
                }
            )

    if severity:
        rows = [r for r in rows if r["severity"] == severity]
    if region:
        rows = [r for r in rows if region.lower() in r["location"].lower()]
    if min_confidence > 0:
        rows = [r for r in rows if r["confidence"] >= min_confidence]

    sorters = {
        "severity": lambda r: (_SEV_ORDER.get(r["severity"], 0), r["score"]),
        "magnitude": lambda r: r["score"],
        "confidence": lambda r: r["confidence"],
        "recency": lambda r: r["data_status"] != "unavailable",
    }
    key = sorters.get(sort, sorters["severity"])
    rows.sort(key=key, reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights": {
            "magnitude": W_MAGNITUDE,
            "spatial_extent": W_EXTENT,
            "duration": W_DURATION,
            "confidence": W_CONFIDENCE,
            "supporting_observations": W_SUPPORT,
            "rate_of_change": W_RATE,
        },
        "filters": {"variable": variable, "severity": severity, "region": region, "min_confidence": min_confidence},
        "anomalies": rows,
    }


_SEV_ORDER = {"high": 3, "medium": 2, "low": 1, "none": 0}