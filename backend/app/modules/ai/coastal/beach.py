"""
TidalTwin - Rip-Current & Beach Safety Index
================================================
Determines SAFE / CAUTION / DANGER flags for each beach/coast based on
wave height, current speed and a simulated nearshore-current intensity
(borrowed from our existing data).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation

WAVE_SAFE = 1.0       # m
WAVE_CAUTION = 1.8    # m
CURRENT_SAFE = 0.40    # m/s
CURRENT_CAUTION = 0.70 # m/s

META = {
    "safe":     {"label": "SAFE",     "color": "#22c55e", "action": "Enjoy the water — swim near lifeguard stations."},
    "caution":  {"label": "CAUTION",  "color": "#facc15", "action": "Exercise caution — avoid swimming beyond knee depth."},
    "danger":   {"label": "DANGER",   "color": "#ef4444", "action": "Do not enter the water — high rip-current / wave risk."},
}


def _classify(wave: float, current: float) -> str:
    if wave >= WAVE_CAUTION or current >= CURRENT_CAUTION:
        return "danger"
    if wave >= WAVE_SAFE or current >= CURRENT_SAFE:
        return "caution"
    return "safe"


def compute_beach_safety(db: Session) -> dict:
    regions: list[dict] = []
    for loc in db.query(OceanLocation).all():
        obs = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())
            .first()
        )
        wave = obs.wave_height if obs and obs.wave_height is not None else 0.8
        cur = obs.current_speed if obs and obs.current_speed is not None else 0.2
        sst = obs.sea_surface_temperature if obs and obs.sea_surface_temperature is not None else 28.0

        flag = _classify(wave, cur)
        meta = META[flag]

        rip_index = round(max(0, min(100, (wave / 3.0) * 45 + (cur / 1.0) * 55)), 1)

        reasons: list[str] = []
        if wave >= WAVE_CAUTION:
            reasons.append(f"High waves ({wave:.1f} m)")
        if wave >= WAVE_SAFE:
            reasons.append(f"Moderate waves ({wave:.1f} m)")
        if cur >= CURRENT_CAUTION:
            reasons.append(f"Strong nearshore current ({cur:.2f} m/s)")
        if cur >= CURRENT_SAFE:
            reasons.append(f"Moderate nearshore current ({cur:.2f} m/s)")
        if not reasons:
            reasons.append("Conditions within normal beach safety limits")

        regions.append({
            "location_id": loc.id,
            "location": loc.name,
            "wave_height": round(wave, 2),
            "current_speed": round(cur, 2),
            "sst": round(sst, 2),
            "flag": flag,
            "flag_label": meta["label"],
            "color": meta["color"],
            "rip_current_index": rip_index,
            "reasons": reasons,
            "action": meta["action"],
        })

    regions.sort(key=lambda r: -r["rip_current_index"])
    danger = sum(1 for r in regions if r["flag"] == "danger")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regions": regions,
        "summary": {
            "total": len(regions),
            "safe": sum(1 for r in regions if r["flag"] == "safe"),
            "caution": sum(1 for r in regions if r["flag"] == "caution"),
            "danger": danger,
        },
        "method": "Rip-current risk = w1·wave_height + w2·current_speed (threshold-based flags).",
    }
