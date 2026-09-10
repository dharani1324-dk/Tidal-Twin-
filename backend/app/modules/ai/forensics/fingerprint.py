"""Ocean Fingerprint / Event DNA + Similar Historical Event Search.

Every ocean event is assigned a multi-dimensional vector ("DNA") based on its
observed characteristics. Historical events (both real DB rows and a synthetic
reference archive) are compared against this fingerprint to surface similar
past events with a quantitative similarity score.
"""

import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.observation import OceanObservation
from app.modules.ai.validation.engine import (
    classify_events,
    observation_confidence,
    difference_engine,
)


# Canonical dimensions of the Ocean DNA fingerprint
DIMENSIONS = [
    "temp_anomaly", "salinity", "oxygen", "chlorophyll", "nutrients",
    "wave_height", "current_speed", "duration_h", "peak_intensity",
]

# Characteristic tags for each range
TAG_RULES = [
    ("temp_anomaly", 1.2, "warm", "hot"),
    ("temp_anomaly", -0.6, "cold", "cool"),
    ("salinity", 35.4, "salty", "fresh"),
    ("chlorophyll", 2.5, "high_productivity", "low_productivity"),
    ("dissolved_oxygen", 6.0, "oxygenated", "hypoxic"),
    ("wave_height", 2.0, "rough", "calm"),
    ("current_speed", 1.2, "fast_current", "slow_current"),
    ("nutrients", 4.0, "nutrient_rich", "nutrient_poor"),
]


# --------------------------------------------------------------------------
# Build reference archive (synthetic + real)
# --------------------------------------------------------------------------

def _region_fingerprints(db: Session) -> list[dict]:
    """Build one fingerprint from the most-recent observation at each region."""
    from sqlalchemy import func
    subq = (
        db.query(
            OceanObservation.location_id,
            func.max(OceanObservation.timestamp).label("max_ts"),
        )
        .group_by(OceanObservation.location_id)
        .subquery()
    )
    rows = (
        db.query(OceanObservation)
        .join(
            subq,
            (OceanObservation.location_id == subq.c.location_id)
            & (OceanObservation.timestamp == subq.c.max_ts),
        )
        .all()
    )

    fps = []
    for o in rows:
        t = o.sea_surface_temperature
        fp = {
            "temp_anomaly": round((t or 28) - 28.0, 2),
            "salinity": round(o.salinity or 35.0, 2),
            "oxygen": round(o.dissolved_oxygen or 7.0, 2),
            "chlorophyll": round(o.chlorophyll or 1.0, 2),
            "nutrients": round(o.nutrients or 2.0, 2),
            "wave_height": round(o.wave_height or 1.0, 2),
            "current_speed": round(o.current_speed or 0.5, 2),
            "duration_h": 6.0,
            "peak_intensity": round(abs(t - 28.0) if t else 0.0, 2),
            "location_id": o.location_id,
            "location_name": "",
            "label": "Current snapshot",
        }
        fps.append(fp)
    return fps


def _canonical_events() -> list[dict]:
    """Reference fingerprints representing standard event archetypes."""
    rng = random.Random(42)
    return [
        {"temp_anomaly": 2.5, "salinity": 35.8, "oxygen": 5.2, "chlorophyll": 0.8,
         "nutrients": 1.5, "wave_height": 0.9, "current_speed": 0.3, "duration_h": 72,
         "peak_intensity": 2.8, "label": "Marine heatwave (stratified)"},
        {"temp_anomaly": 2.0, "salinity": 35.4, "oxygen": 6.8, "chlorophyll": 3.0,
         "nutrients": 3.5, "wave_height": 1.4, "current_speed": 0.7, "duration_h": 48,
         "peak_intensity": 2.3, "label": "Coastal upwelling warming"},
        {"temp_anomaly": -1.5, "salinity": 34.8, "oxygen": 7.8, "chlorophyll": 2.2,
         "nutrients": 5.0, "wave_height": 1.8, "current_speed": 1.1, "duration_h": 36,
         "peak_intensity": 1.8, "label": "Cold water intrusion"},
        {"temp_anomaly": 0.3, "salinity": 36.2, "oxygen": 4.8, "chlorophyll": 1.0,
         "nutrients": 2.0, "wave_height": 2.8, "current_speed": 1.5, "duration_h": 24,
         "peak_intensity": 2.0, "label": "Storm-driven mixing"},
        {"temp_anomaly": 1.8, "salinity": 35.0, "oxygen": 5.5, "chlorophyll": 1.8,
         "nutrients": 4.0, "wave_height": 1.1, "current_speed": 0.8, "duration_h": 60,
         "peak_intensity": 2.2, "label": "Low-oxygen coastal bloom"},
    ]


def _tags_for(fp: dict) -> list[str]:
    tags = []
    for key, thresh, tag_high, tag_low in TAG_RULES:
        val = fp.get(key)
        if val is None:
            continue
        tags.append(tag_high if val >= thresh else tag_low)
    return tags


def fingerprint(event: dict) -> dict:
    """Build the Ocean DNA vector for an event dict."""
    hook = event.get("hook", event)
    fp = {
        "temp_anomaly": round(abs(hook.get("anomaly") or hook.get("peak_intensity") or 0), 2),
        "salinity": round(hook.get("salinity") or 35.0, 2),
        "oxygen": round(hook.get("oxygen") or 7.0, 2),
        "chlorophyll": round(hook.get("chlorophyll") or 1.0, 2),
        "nutrients": round(hook.get("nutrients") or 2.0, 2),
        "wave_height": round(hook.get("wave_height") or 1.0, 2),
        "current_speed": round(hook.get("current_speed") or 0.5, 2),
        "duration_h": round(hook.get("duration_hours") or hook.get("duration_h") or 6, 1),
        "peak_intensity": round(hook.get("peak_intensity") or (hook.get("confidence") or 70) / 30.0, 2),
    }
    fp["tags"] = _tags_for(fp)
    fp["label"] = hook.get("label", event.get("label", "Detected event"))
    return fp


# --------------------------------------------------------------------------
# Similarity search
# --------------------------------------------------------------------------

def _normalise_dim(dim: str, val: float) -> float:
    """Scale each dimension to [0,1] roughly."""
    scales = {
        "temp_anomaly": 3.0, "salinity": 2.0, "oxygen": 10.0,
        "chlorophyll": 5.0, "nutrients": 10.0, "wave_height": 4.0,
        "current_speed": 2.0, "duration_h": 100.0, "peak_intensity": 3.0,
    }
    return max(0.0, min(1.0, val / scales.get(dim, 1.0)))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def similar_events(db: Session, event: dict, limit: int = 5) -> list[dict]:
    """Compare event DNA against real + reference archive."""
    tgt = fingerprint(event)
    tgt_vec = [_normalise_dim(d, tgt[d]) for d in DIMENSIONS]

    candidates: list[tuple[dict, float]] = []

    # Reference archetypes
    for ref in _canonical_events():
        vec = [_normalise_dim(d, ref[d]) for d in DIMENSIONS]
        sim = _cosine(tgt_vec, vec)
        candidates.append((ref, round(sim * 100, 1)))

    # Current regional snapshots as proxy historical references
    for reg in _region_fingerprints(db):
        vec = [_normalise_dim(d, reg[d]) for d in DIMENSIONS]
        sim = _cosine(tgt_vec, vec)
        candidates.append((reg, round(sim * 100, 1)))

    candidates.sort(key=lambda x: -x[1])
    seen_labels: set[str] = {tgt.get("label", "")}
    results = []
    for ref, score in candidates:
        lbl = ref.get("label", "")
        if lbl in seen_labels:
            continue
        seen_labels.add(lbl)
        diff = {d: round(ref[d] - tgt[d], 3) for d in DIMENSIONS
                if abs(ref[d] - tgt[d]) > 0.1}
        results.append({
            "label": lbl,
            "similarity": score,
            "ref_fingerprint": {d: round(ref[d], 2) for d in DIMENSIONS},
            "differences": diff,
            "duration": ref.get("duration_h"),
            "peak_intensity": ref.get("peak_intensity"),
        })
        if len(results) >= limit:
            break
    return results
