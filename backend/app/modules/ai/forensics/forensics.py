"""Ocean Forensics Engine — investigate *why* a change occurred.

Given a location (or a specific event), this module analyses observations,
model output, confidence, skill, and environmental context to produce a
structured investigation with contributing factors, evidence, and a
confidence estimate.

Also includes the Event Autopsy compositing function.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.observation import OceanObservation
from app.models.location import OceanLocation
from app.modules.ai.validation.engine import (
    classify_events,
    difference_engine,
    model_skill,
    observation_confidence,
    provenance,
)
from app.modules.physics.ocean_profiles import depth_profile, region_context, thermocline
from app.modules.ai.forensics.fingerprint import similar_events, fingerprint


def _last_loc_pair(db, loc_id):
    obs = (db.query(OceanObservation)
           .filter(OceanObservation.location_id == loc_id)
           .order_by(OceanObservation.timestamp.desc()).limit(48).all())[::-1]
    if not obs:
        return None, None, None, None
    m = obs[-1]
    p = (db.query(OceanObservation)
         .filter(OceanObservation.location_id == loc_id,
                 OceanObservation.timestamp < m.timestamp - timedelta(hours=24))
         .order_by(OceanObservation.timestamp.desc()).first())
    return m, p, obs, len(obs)


def _detect_change(m, p):
    if m is None or p is None or p.sea_surface_temperature is None or m.sea_surface_temperature is None:
        return None
    dT = (m.sea_surface_temperature or 0) - (p.sea_surface_temperature or 0)
    dW = (m.wave_height or 0) - (p.wave_height or 0)
    dS = (m.salinity or 0) - (p.salinity or 0)
    return {"dT": round(dT, 2), "dW": round(dW, 2), "dS": round(dS, 2)}


def _factors(ch, prof, skill, conf):
    factors = []
    if ch:
        if abs(ch["dT"]) > 0.5:
            factors.append({
                "factor": "Temperature",
                "description": f"{'Increase' if ch['dT'] > 0 else 'Decrease'} of {abs(ch['dT']):.2f}°C "
                               f"({('significantly ' if abs(ch['dT']) > 1.5 else '')}above normal)",
                "weight": round(min(1.0, abs(ch['dT']) / 2.5), 2),
                "confidence": 85,
            })
        if abs(ch["dW"]) > 0.3:
            factors.append({
                "factor": "Wind/Wave",
                "description": f"Wave {'rise' if ch['dW'] > 0 else 'drop'} of {abs(ch['dW']):.2f}m",
                "weight": round(min(1.0, abs(ch["dW"]) / 2.0), 2),
                "confidence": 80,
            })
        if abs(ch["dS"]) > 0.1:
            factors.append({
                "factor": "Salinity",
                "description": f"Salinity shift of {ch['dS']:+.2f} PSU",
                "weight": round(min(1.0, abs(ch["dS"]) / 0.5), 2),
                "confidence": 75,
            })
    if prof and prof.get("thermocline"):
        tc = prof["thermocline"]
        factors.append({
            "factor": "Thermocline",
            "description": f"Thermocline depth {tc['thermocline_depth']}m, strength {tc['strength_c_per_m']:.3f} °C/m",
            "weight": min(1.0, tc["strength_c_per_m"] * 2),
            "confidence": 90,
        })
    if skill:
        overall = skill.get("overall_skill") or skill.get("overall_skill_percentage")
        if overall is not None:
            factors.append({
                "factor": "Model agreement",
                "description": f"Model skill is {overall:.0f}% — {'the model tracks observations well' if overall > 60 else 'there is notable disagreement with observations'}",
                "weight": max(0.1, 1.0 - overall / 100),
                "confidence": 95,
            })
    if conf:
        components = conf.get("components") or []
        for c in components:
            if c.get("weight") and c["weight"] >= 0.25:
                factors.append({
                    "factor": c.get("label", "Data quality"),
                    "description": f"{c['label']} contributes {c.get('weight', 0)*100:.0f}% to confidence",
                    "weight": c["weight"],
                    "confidence": 90,
                })
    return factors


def investigate(db: Session, loc_id: int) -> dict:
    """Full forensics investigation for a specific location."""
    loc = db.query(OceanLocation).filter(OceanLocation.id == loc_id).first()
    if not loc:
        return {"error": f"Location {loc_id} not found"}

    m, p, obs, n = _last_loc_pair(db, loc_id)
    ch = _detect_change(m, p)
    prof = depth_profile(loc, m.sea_surface_temperature, m.salinity, m.wave_height, m.current_speed)
    thermo = prof["thermocline"]
    skill = model_skill(db)
    conf = observation_confidence(db)
    dev = difference_engine(db)

    dev_loc = next((d for d in dev.get("results", []) if d.get("location_id") == loc_id), None)
    started_at = None
    variables_affected = []
    if ch:
        if abs(ch["dT"]) > 0.4:
            variables_affected.append("sea_surface_temperature")
        if abs(ch["dW"]) > 0.3:
            variables_affected.append("wave_height")
        if abs(ch["dS"]) > 0.1:
            variables_affected.append("salinity")
        for o in obs[:-1]:
            if m and abs((o.sea_surface_temperature or 0) - (m.sea_surface_temperature or 0)) > 1.0:
                started_at = o.timestamp.isoformat()
                break
    if not started_at and obs:
        started_at = obs[0].timestamp.isoformat()

    factors = _factors(ch, prof, skill, conf)

    evidence = []
    if m:
        evidence.append({"label": "Latest SST", "value": f"{m.sea_surface_temperature:.1f}°C", "source": "observation"})
        evidence.append({"label": "Wave height", "value": f"{m.wave_height:.2f}m", "source": "observation"})
        evidence.append({"label": "Chlorophyll", "value": f"{prof.get('chlorophyll', [0])[0]:.2f} mg/m³", "source": "profile"})
        evidence.append({"label": "Dissolved oxygen", "value": f"{prof.get('dissolved_oxygen', [0])[0]:.2f} mg/L", "source": "profile"})
    if dev_loc:
        evidence.append({"label": "Model deviation", "value": f"{dev_loc.get('mean_absolute_difference', 0):.2f}°C", "source": "validation"})
    if conf:
        evidence.append({"label": "Data confidence", "value": f"{conf.get('confidence', 0)}%", "source": "quality"})

    origin_skills = skill.get("variables", {}) if skill else {}
    overall_conf = conf.get("confidence", 75) if conf else 75

    return {
        "location": loc.name,
        "location_id": loc.id,
        "change": ch or {"dT": 0, "dW": 0, "dS": 0},
        "started_at": started_at,
        "variables_affected": variables_affected,
        "depth_range": {
            "mld": thermo["mixed_layer_depth"],
            "thermocline_depth": thermo["thermocline_depth"],
            "modeled_to_depth": prof["depths"][-1],
        },
        "contributing_factors": factors,
        "evidence": evidence,
        "confidence": overall_conf,
        "profile_metrics": thermo,
    }


def autopsy(db: Session, loc_id: int) -> dict:
    """Event Autopsy — comprehensive post-event investigation."""
    inv = investigate(db, loc_id)
    loc = db.query(OceanLocation).filter(OceanLocation.id == loc_id).first()
    events = classify_events(db)["events"]
    region_events = [e for e in events if e.get("location_id") == loc_id]
    fp = fingerprint(region_events[0]) if region_events else fingerprint({"label": "detected"})
    sim = similar_events(db, fp, limit=3)
    prov = provenance(db, loc_id) if prov_available(db, loc_id) else None

    return {
        "title": f"Ocean Autopsy — {loc.name if loc else 'Unknown'}",
        "what_happened": inv.get("change", {}),
        "started_at": inv.get("started_at"),
        "contributing_factors": inv.get("contributing_factors", []),
        "evidence": inv.get("evidence", []),
        "confidence": inv.get("confidence", 0),
        "depth_range": inv.get("depth_range"),
        "similar_historical_events": sim,
        "uncertainty": _uncertainty_summary(inv),
        "observation_priorities": _priorities(inv, loc),
        "fingerprint": fp,
    }


def _uncertainty_summary(inv):
    factors = inv.get("contributing_factors", [])
    total_weight = sum(f.get("weight", 0) for f in factors) or 1.0
    dominant = max(factors, key=lambda f: f.get("weight", 0)) if factors else {}
    return {
        "overall_confidence": inv.get("confidence", 0),
        "dominant_factor": dominant.get("factor", "N/A"),
        "message": (
            f"Confidence is {inv.get('confidence', 0)}%. "
            f"Primary contributor: {dominant.get('factor', 'N/A')}. "
            f"{'Add more observations to narrow uncertainty.' if inv.get('confidence', 100) < 80 else 'Observation coverage is adequate.'}"
        ),
    }


def _priorities(inv, loc):
    obs_density = inv.get("depth_range", {}).get("mld", 20)
    priorities = [
        "Increase observation frequency during event onset",
        "Deploy subsurface profilers below the mixed layer",
        "Monitor thermocline depth daily",
    ]
    if inv.get("confidence", 100) < 70:
        priorities.insert(0, "CRITICAL: observation coverage too low for reliable analysis")
    return priorities


def prov_available(db, loc_id):
    try:
        provenance(db, loc_id)
        return True
    except Exception:
        return False
