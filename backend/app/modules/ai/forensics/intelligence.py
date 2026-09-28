"""Observation Intelligence + Ocean Indexes + Causal/Relationship engines.

Covers:
  • Data Gap Detector  (coverage scoring per region)
  • Uncertainty Heatmap (1 − confidence)
  • AI Observation Priority Map  (gap × uncertainty × anomaly)
  • Observation Coverage Simulator
  • Ocean Health Score  (0–100 composite)
  • Ocean Threat Early-Warning Chain  (Normal→Watch→Warning→Critical)
  • Ocean-to-Coast Impact Bridge
  • Ocean Relationship Graph  (variable correlations)
  • Causal Chain  (wind→mixing→thermocline→temp→oxygen→ecosystem)
"""

import math
import statistics
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.observation import OceanObservation
from app.models.location import OceanLocation
from app.modules.ai.validation.engine import classify_events, observation_confidence, model_skill
from app.modules.ai.forensics.fingerprint import _normalise_dim, DIMENSIONS
from app.modules.physics.ocean_profiles import derive_surface, thermocline, depth_profile

# --------------------------------------------------------------------------
# Coverage / Data Gap
# --------------------------------------------------------------------------

def _obs_stats(db, loc_id, window_hours=72):
    from datetime import datetime, timedelta, timezone
    from app.modules.ai.provenance_quality import origin_status
    now = datetime.now(timezone.utc)
    rows = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc_id,
                OceanObservation.timestamp >= now - timedelta(hours=window_hours))
        .order_by(OceanObservation.timestamp.asc()).all()
    )
    rows = [row for row in rows
            if origin_status(row.source, row.data_type) in ("REAL", "HISTORICAL", "SATELLITE_DERIVED")]
    n = len(rows)
    if n == 0:
        return {"count": 0, "density": 0, "recency_h": window_hours, "span_h": 0, "std_t": 0, "coverage_pct": 0}

    times = [r.timestamp for r in rows]
    temps = [r.sea_surface_temperature for r in rows if r.sea_surface_temperature is not None]
    span = (times[-1] - times[0]).total_seconds() / 3600 if n > 1 else 0
    recency = (now - times[-1]).total_seconds() / 3600 if times[-1] else window_hours
    density = n / max(1, span or 1)
    std_t = statistics.stdev(temps) if len(temps) >= 2 else 0.0
    coverage_pct = round(min(100, (density / 1.0) * 60 + (n / max(1, window_hours / 2)) * 40), 1)

    return {
        "count": n,
        "density": round(density, 3),
        "recency_h": round(recency, 1),
        "span_h": round(span, 1),
        "std_t": round(std_t, 3),
        "coverage_pct": coverage_pct,
    }


def region_coverage(db):
    results = []
    for loc in db.query(OceanLocation).all():
        stats = _obs_stats(db, loc.id)
        conf = observation_confidence(db)
        events = classify_events(db)["events"]
        anomaly = any(e["location_id"] == loc.id and e["confidence"] > 70 for e in events)

        gap_score = round(max(0, 100 - stats["coverage_pct"]), 1)
        uncertainty = round(100 - (conf.get("confidence", 70) if conf else 70), 1)
        priority = round(0.5 * gap_score + 0.3 * uncertainty + (0.2 * 80 if anomaly else 0.1 * gap_score), 1)
        tier = "CRITICAL" if priority > 70 else ("HIGH" if priority > 50 else ("MEDIUM" if priority > 30 else "LOW"))

        results.append({
            "location_id": loc.id,
            "location": loc.name,
            **stats,
            "gap_score": gap_score,
            "confidence": conf.get("confidence", 0) if conf else 0,
            "uncertainty": uncertainty,
            "anomaly": anomaly,
            "priority": min(100, priority),
            "tier": tier,
        })
    results.sort(key=lambda x: -x["priority"])
    return results


def priority_map(db):
    cov = region_coverage(db)
    return {
        "generated_at": "now",
        "zones": [
            {"location": c["location"], "location_id": c["location_id"],
             "priority": c["priority"], "tier": c["tier"], "gap": c["gap_score"],
             "uncertainty": c["uncertainty"]}
            for c in cov
        ],
    }


def uncertainty_map(db):
    cov = region_coverage(db)
    return {
        "generated_at": "now",
        "regions": [
            {"location": c["location"], "location_id": c["location_id"],
             "uncertainty": c["uncertainty"], "confidence": c["confidence"],
             "coverage_pct": c["coverage_pct"]}
            for c in cov
        ],
    }


def coverage_simulator(db, loc_id, delta_pct=30):
    stats = _obs_stats(db, loc_id)
    conf = observation_confidence(db)
    current_conf = conf.get("confidence", 70) if conf else 70
    cov = stats["coverage_pct"]
    new_cov = min(100, cov + delta_pct)
    conf_gain = round((delta_pct / 100) * 25, 1)   # coverage weight = 25%
    new_conf = min(100, round(current_conf + conf_gain, 1))
    return {
        "location_id": loc_id,
        "current_coverage": cov,
        "projected_coverage": new_cov,
        "current_confidence": current_conf,
        "projected_confidence": new_conf,
        "confidence_gain": conf_gain,
        "message": f"If observation coverage increases by {delta_pct}%, analytical confidence "
                   f"could improve from {current_conf}% to {new_conf}% (+{conf_gain} percentage points).",
    }


# --------------------------------------------------------------------------
# Ocean Health Score (0-100)
# --------------------------------------------------------------------------

def health_score(db, loc_id=None):
    def _region(loc_id, loc_name):
        conf = observation_confidence(db)
        events = classify_events(db)["events"]
        region_events = [e for e in events if e.get("location_id") == loc_id]

        stats = _obs_stats(db, loc_id)
        conf_val = (conf.get("confidence", 70) if conf else 70)
        cov = stats.get("coverage_pct", 50)
        event_load = min(100, len(region_events) * 30)

        from app.modules.physics.ocean_profiles import depth_profile, region_context
        from sqlalchemy.orm import Session as _S
        loc = db.query(OceanLocation).filter(OceanLocation.id == loc_id).first()
        o = (db.query(OceanObservation)
             .filter(OceanObservation.location_id == loc_id)
             .order_by(OceanObservation.timestamp.desc()).first())
        temp = o.sea_surface_temperature if o and o.sea_surface_temperature is not None else 28.0
        anom = abs(temp - 28.0)

        temperature_score = max(0, 100 - anom * 40)
        oxygen = o.dissolved_oxygen if o and o.dissolved_oxygen is not None else 7.0
        oxygen_score = min(100, max(0, oxygen * 10))
        sal = o.salinity if o and o.salinity is not None else 35.0
        sal_score = max(0, 100 - abs(sal - 35.0) * 50)
        chl = o.chlorophyll if o and o.chlorophyll is not None else 1.0
        chl_score = min(100, chl * 25 + 20)
        wave = o.wave_height if o and o.wave_height is not None else 1.0
        wave_score = max(0, 100 - max(0, wave - 1.2) * 30)

        raw = (0.25 * temperature_score + 0.10 * oxygen_score + 0.10 * sal_score
               + 0.10 * chl_score + 0.15 * wave_score + 0.10 * (100 - event_load)
               + 0.10 * cov + 0.10 * conf_val)
        score = round(max(0, min(100, raw)), 1)
        label = "Healthy" if score >= 75 else ("Moderate" if score >= 55 else ("Stressed" if score >= 35 else "Critical"))
        return {"location_id": loc_id, "location": loc_name, "score": score, "label": label}

    if loc_id:
        loc = db.query(OceanLocation).filter(OceanLocation.id == loc_id).first()
        return [_region(loc_id, loc.name if loc else "?")] if loc else []

    return [_region(loc.id, loc.name) for loc in db.query(OceanLocation).all()]


# --------------------------------------------------------------------------
# Threat Early-Warning Chain
# --------------------------------------------------------------------------

def threat_chain(db):
    from app.modules.ai.validation.engine import compute_risk_index
    idx = compute_risk_index(db)
    results = []
    for r in idx.get("regions", []):
        band = r["band"]
        if band == "CRITICAL":
            stage, message = "CRITICAL", "Immediate action required. Seek shelter and avoid the ocean."
        elif band == "ELEVATED":
            stage, message = "WARNING", "Escalating risk. Small vessels should return to harbour."
        elif band == "MODERATE":
            stage, message = "WATCH", "Elevated conditions detected. Monitor closely."
        else:
            stage, message = "NORMAL", "Conditions are within normal ranges."
        results.append({
            "location_id": r["location_id"], "location": r["location"],
            "stage": stage, "risk_index": r["index"], "band": band, "message": message,
        })
    return results


# --------------------------------------------------------------------------
# Ocean-to-Coast Impact Bridge
# --------------------------------------------------------------------------

def impact_bridge(db):
    events = classify_events(db)["events"]
    from app.modules.ai.validation.engine import compute_risk_index
    idx = compute_risk_index(db)
    regions = {r["location_id"]: r for r in idx.get("regions", [])}
    impacts = []
    for e in events:
        loc_id = e.get("location_id")
        reg = regions.get(loc_id, {})
        band = reg.get("band", "LOW")
        severity = "high" if band in ("CRITICAL", "ELEVATED") else "moderate"
        areas = []
        if e["event_type"] == "marine_heatwave":
            areas = ["Fisheries (coral bleaching, stock migration)", "Coastal tourism", "Desalination intake"]
        elif e["event_type"] == "coastal_flooding_risk":
            areas = ["Port operations", "Coastal infrastructure", "Human safety"]
        elif e["event_type"] == "rapid_temp_change":
            areas = ["Aquaculture", "Marine biodiversity", "Fishing fleet routing"]
        elif e["event_type"] == "strong_current_event":
            areas = ["Navigation safety", "Offshore platforms", "Diving operations"]
        else:
            areas = ["Model data pipeline", "Analyst review queue"]
        impacts.append({
            "event_type": e["event_type"], "label": e["label"], "location": e["location"],
            "location_id": loc_id, "severity": severity, "band": band,
            "impact_areas": areas,
            "description": f"{e['label']} ({e['intensity']}) may impact coastal regions — {', '.join(areas[:2])}.",
        })
    return impacts


# --------------------------------------------------------------------------
# Ocean Relationship Graph (variable correlations)
# --------------------------------------------------------------------------

def relationship_graph(db):
    all_obs = (
        db.query(OceanObservation.sea_surface_temperature,
                 OceanObservation.wave_height,
                 OceanObservation.salinity,
                 OceanObservation.current_speed,
                 OceanObservation.dissolved_oxygen,
                 OceanObservation.chlorophyll,
                 OceanObservation.ph)
        .filter(OceanObservation.sea_surface_temperature.isnot(None))
        .all()
    )
    n = len(all_obs)
    if n < 5:
        return {"nodes": [], "edges": [], "message": "Insufficient data"}

    labels = ["SST", "Wave", "Salinity", "Current", "Oxygen", "Chlorophyll", "pH"]
    cols = [[r[i] for r in all_obs if r[i] is not None] for i in range(7)]
    avgs = [statistics.mean(c) if c else 0 for c in cols]
    stds = [statistics.stdev(c) if len(c) >= 2 else 1.0 for c in cols]

    edges = []
    for i in range(7):
        for j in range(i + 1, 7):
            pairs = [(row[i] if row[i] is not None else 0,
                      row[j] if row[j] is not None else 0)
                     for row in all_obs if row[i] is not None and row[j] is not None]
            if len(pairs) < 5:
                continue
            xa = [p[0] for p in pairs]
            xb = [p[1] for p in pairs]
            m_a, m_b = statistics.mean(xa), statistics.mean(xb)
            s_a, s_b = statistics.stdev(xa) or 1, statistics.stdev(xb) or 1
            r_val = statistics.mean((a - m_a) * (b - m_b) for a, b in pairs) / (s_a * s_b)
            if abs(r_val) >= 0.15:
                strength = "strong" if abs(r_val) > 0.6 else ("moderate" if abs(r_val) > 0.35 else "weak")
                edges.append({"from": labels[i], "to": labels[j], "r": round(r_val, 3),
                              "strength": strength, "direction": "positive" if r_val > 0 else "negative"})

    nodes = [{"id": labels[i], "avg": round(avgs[i], 2), "std": round(stds[i], 3)}
             for i in range(7)]
    return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------
# Causal Chain
# --------------------------------------------------------------------------
#
# SCIENTIFIC BOUNDARY - read before trusting any number this function returns.
#
# This is a HEURISTIC DIAGNOSTIC, not a causal model and not a physical
# simulation. Every link in the chain is a weighted indicator computed from the
# latest observation plus the deterministic physics engine
# (`app.modules.physics.ocean_profiles`), whose own coefficients are
# uncalibrated. Concretely:
#
#   * Thermocline depth/strength are DERIVED, never measured here.
#   * Dissolved oxygen is a Henry's-law proxy, not an observation.
#   * A missing oxygen reading is NOT treated as 7.0 mg/L. A missing value is
#     reported as missing and the oxygen link is emitted as `available: false`.
#   * The indicators, their weights and the level thresholds below are
#     engineering heuristics chosen to order severity, not values published by
#     or calibrated against any observational study.
#   * `basis` on every node states whether that node rests on a measured
#     variable, a derived one, or nothing at all.
#
# The chain must never be presented as a probability. It carries no calibrated
# confidence, which is why the per-node `confidence` field that earlier
# returned hard-coded 90/85/88/92/78/80 has been removed entirely.


def _node(step, node, value, level, basis, description):
    return {"step": step, "node": node, "value": value, "level": level,
            "basis": basis, "description": description}


def causal_chain(db, loc_id):
    loc = db.query(OceanLocation).filter(OceanLocation.id == loc_id).first()
    o = (db.query(OceanObservation)
         .filter(OceanObservation.location_id == loc_id)
         .order_by(OceanObservation.timestamp.desc()).first())
    if not loc or not o:
        return {"location_id": loc_id, "chain": [], "message": "Insufficient data"}

    prof = depth_profile(loc, o.sea_surface_temperature, o.salinity, o.wave_height, o.current_speed)
    thermo = prof["thermocline"]

    tc_depth = thermo["thermocline_depth"]
    tc_strength = thermo["strength_c_per_m"]
    temp = o.sea_surface_temperature
    o2 = o.dissolved_oxygen
    wave = o.wave_height
    current = o.current_speed

    def _level(v, thresholds):
        if v < thresholds[0]:
            return "low"
        if v < thresholds[1]:
            return "moderate"
        return "high"

    chain = []
    # --- 1. Wind / wave forcing ------------------------------------------------
    if wave is not None and current is not None:
        wind_ind = round(wave * 0.6 + current * 0.3, 2)
        chain.append(_node(
            1, "Wind/Wave input", wind_ind, _level(wind_ind, [0.4, 0.8]), "MEASURED",
            f"Wave height {wave:.1f}m, current {current:.1f}m/s"))
    else:
        missing = [n for n, v in (("wave height", wave), ("current speed", current)) if v is None]
        chain.append(_node(
            1, "Wind/Wave input", None, "unknown", "UNAVAILABLE",
            f"Not computable - no {' and no '.join(missing)} recorded for this observation."))

    # --- 2. Mixing intensity (derived) ----------------------------------------
    mixing_ind = round(max(0, 1.0 - thermo["mixed_layer_depth"] / 40.0), 2)
    chain.append(_node(
        2, "Mixing intensity", mixing_ind, _level(mixing_ind, [0.3, 0.6]), "DERIVED_HEURISTIC",
        f"Thermocline modelled at {tc_depth:.0f}m — mixing "
        f"{'enhanced' if mixing_ind > 0.4 else 'suppressed'}. Derived, not measured."))

    # --- 3. Thermocline response (derived) ------------------------------------
    tc_ind = round(tc_strength, 3)
    chain.append(_node(
        3, "Thermocline response", tc_ind, _level(tc_ind, [0.3, 0.6]), "DERIVED_HEURISTIC",
        f"Modelled temperature gradient {tc_ind:.3f} °C/m "
        f"{'(sharp)' if tc_ind > 0.4 else '(gradual)'}. Derived, not measured."))

    # --- 4. Sea surface temperature (measured) ---------------------------------
    if temp is not None:
        temp_ind = round(abs(temp - 28.0), 2)
        chain.append(_node(
            4, "Sea surface temperature", temp_ind, _level(temp_ind, [0.8, 1.6]), "MEASURED",
            f"Deviation from the 28.0 °C tropical reference {temp_ind:+.2f}°C"))
    else:
        temp_ind = None
        chain.append(_node(
            4, "Sea surface temperature", None, "unknown", "UNAVAILABLE",
            "No sea surface temperature recorded for this observation."))

    # --- 5. Dissolved oxygen (measured, or explicitly absent) -----------------
    if o2 is not None:
        oxygen_ind = round(max(0, 7.5 - o2), 2)
        chain.append(_node(
            5, "Dissolved oxygen", oxygen_ind, _level(oxygen_ind, [1.0, 2.0]), "MEASURED",
            f"Oxygen deficit {oxygen_ind:.2f} mg/L against the 7.5 mg/L adequacy "
            f"reference (measured {o2:.1f} mg/L)"))
    else:
        oxygen_ind = None
        chain.append(_node(
            5, "Dissolved oxygen", None, "unknown", "UNAVAILABLE",
            "No dissolved oxygen measured for this observation. The physics engine's "
            "oxygen proxy is deliberately NOT substituted for a measurement here."))

    # --- 6. Ecosystem risk (only from the links that actually exist) -----------
    parts, weights, notes = [], [], []
    if temp_ind is not None:
        parts.append(temp_ind * 0.4)
        weights.append(0.4)
    if oxygen_ind is not None:
        parts.append(oxygen_ind * 0.3)
        weights.append(0.3)
    if wave is not None:
        parts.append(wave * 0.2)
        weights.append(0.2)
    parts.append(mixing_ind * 0.1)
    weights.append(0.1)

    if sum(weights) <= 0:
        ecosystem_risk = None
        risk_basis = "UNAVAILABLE"
    else:
        # Renormalise over the links that are present so a missing measurement
        # lowers the score's evidence base instead of silently scoring as zero.
        ecosystem_risk = round(min(1.0, sum(parts) / sum(weights)), 2)
        risk_basis = ("MEASURED_AND_DERIVED" if len(weights) == 4 else "PARTIAL_MIXED_BASIS")
        if oxygen_ind is None:
            notes.append("Ecosystem risk excludes the dissolved-oxygen term: no oxygen measurement.")
        if temp_ind is None:
            notes.append("Ecosystem risk excludes the SST term: no temperature measurement.")
        if wave is None:
            notes.append("Ecosystem risk excludes the wave term: no wave height measurement.")

    chain.append(_node(
        6, "Ecosystem risk", ecosystem_risk,
        "unknown" if ecosystem_risk is None else _level(ecosystem_risk, [0.3, 0.6]),
        risk_basis,
        "Composite ecosystem stress indicator"
        + (f" = {ecosystem_risk:.2f}" if ecosystem_risk is not None else " (not computable)")))

    measured = [n for n in chain if n["basis"] == "MEASURED"]
    derived = [n for n in chain if "DERIVED" in n["basis"]]
    unavailable = [n for n in chain if n["basis"] == "UNAVAILABLE"]

    def _phrase(v, t, up, down, unknown="is unknown"):
        if v is None:
            return unknown
        return up if v > t else down

    narrative = (
        f"Wind energy {_phrase(chain[0]['value'], 0.4, 'increases', 'is modest')} → "
        f"{_phrase(mixing_ind, 0.4, 'enhances', 'suppresses')} vertical mixing → "
        f"thermocline modelled at {tc_depth:.0f}m "
        f"{_phrase(tc_ind, 0.4, 'sharpens', 'remains gradual')} → "
        f"SST {_phrase(temp_ind, 0.8, 'is elevated', 'is near-normal', 'is unknown')} → "
        f"oxygen {_phrase(oxygen_ind, 1.0, 'is under stress', 'is adequate', 'is unknown')} → "
        f"ecosystem risk {_phrase(ecosystem_risk, 0.3, 'is elevated', 'is low', 'is unknown')}."
    )

    return {
        "location_id": loc_id,
        "location": loc.name if loc else None,
        "chain": chain,
        "ecosystem_risk": ecosystem_risk,
        "narrative": narrative,
        "scientific_basis": "HEURISTIC_DIAGNOSTIC",
        "calibrated": False,
        "evidence_summary": {
            "measured_links": len(measured),
            "derived_links": len(derived),
            "unavailable_links": len(unavailable),
        },
        "limitations": [
            "Thermocline depth, mixing intensity and gradient are derived by the "
            "deterministic physics engine, not measured.",
            "Indicator weights and level thresholds are engineering heuristics used to "
            "order severity. They are not calibrated against observational data and "
            "carry no probability meaning.",
            "This chain is a diagnostic ordering aid, not a causal model or a forecast.",
        ]
        + notes,
    }

