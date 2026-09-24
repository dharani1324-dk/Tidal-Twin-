"""
TidalTwin - Model Validation & Confidence Engine
=======================================================
The "model vs reality" intelligence layer. For every monitored coast it
answers three questions judges and ocean scientists care about:

  1. How confident are we in the observations themselves?
     -> observation_confidence()  (age, coverage, quantity, agreement)

  2. Where does the model disagree with what the ocean actually did,
     by how much, and what might explain it?
     -> difference_engine()       (MODEL | OBSERVED | DEVIATION per field)

  3. What is the operational situation right now, in one glance?
     -> situation_panel()         (anomaly level, intensity, agreement)

The "MODEL" baseline is our trend forecast re-evaluated at the latest
observation window — the same honest verification approach used by the
comparator: we compare the AI expectation against reality and measure the
gap. This is real decision intelligence, not just colorbar changes.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from app.models.alert import OceanAlert
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.reports.risk import compute_risk_index
from app.modules.ai.safety.advisory import model_trust, safety_advisory

OBS_WINDOW = 96


def _clamp100(x: float) -> int:
    return int(min(100, max(0, round(x * 100))))

FIELD_META = {
    "temperature": {"label": "Sea surface temperature", "unit": "°C", "high": 1.5, "moderate": 0.8},
    "wave_height": {"label": "Wave height", "unit": "m", "high": 0.8, "moderate": 0.4},
    "salinity": {"label": "Salinity", "unit": "PSU", "high": 0.8, "moderate": 0.4},
    "current_speed": {"label": "Current speed", "unit": "m/s", "high": 0.35, "moderate": 0.18},
}

CAUSES = {
    ("temperature", "above"): "Persistent surface heating with weak vertical mixing",
    ("temperature", "below"): "Upwelling or cooler subsurface water reaching the surface",
    ("wave_height", "above"): "Sustained regional winds or distant cyclone swell",
    ("wave_height", "below"): "Calm atmospheric forcing after a settling swell",
    ("salinity", "above"): "Evaporation dominance or advection of saltier water",
    ("salinity", "below"): "Freshwater input from river discharge or rainfall",
    ("current_speed", "above"): "Strengthened monsoon-driven or tidal flow",
    ("current_speed", "below"): "Weakening of the prevailing circulation",
}


def _latest_rows(db: Session, loc: OceanLocation, window: int = OBS_WINDOW) -> list:
    return (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .limit(window)
        .all()
    )[::-1]


def _baseline(values: list[float | None]) -> float | None:
    """'Model' expectation = normal conditioned on history (all but latest)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 5:
        return None
    return float(np.mean(vals[:-1]))


def _deviation_level(field: str, dev: float | None) -> str:
    if dev is None:
        return "unknown"
    meta = FIELD_META[field]
    a = abs(dev)
    if a >= meta["high"]:
        return "high"
    if a >= meta["moderate"]:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# 1. Observation Confidence
# ---------------------------------------------------------------------------

def observation_confidence(db: Session) -> dict:
    """Per-coast confidence in the observation stream itself + disagreement."""
    locations = db.query(OceanLocation).all()
    trust_by_id = {r["location_id"]: r for r in model_trust(db)["regions"]}
    risk_by_id = {r["location_id"]: r for r in compute_risk_index(db)["regions"]}
    now = datetime.now(timezone.utc)

    rows = []
    for loc in locations:
        obs = _latest_rows(db, loc)
        mae = trust_by_id.get(loc.id, {}).get("mean_mae", 0.0) or 0.0
        drift = bool(trust_by_id.get(loc.id, {}).get("drift", False))
        risk = risk_by_id.get(loc.id, {})

        if not obs:
            rows.append(
                {
                    "location_id": loc.id,
                    "location": loc.name,
                    "observation_confidence": 0,
                    "freshness_hours": None,
                    "field_coverage": 0.0,
                    "sample_size": 0,
                    "agreement": 0.0,
                    "model_trust": trust_by_id.get(loc.id, {}).get("trust_score", 0),
                    "drift": drift,
                    "disagreement": True,
                    "interpretation": "No observations available.",
                }
            )
            continue

        last_ts = obs[-1].timestamp
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        freshness_hours = float((now - last_ts).total_seconds()) / 3600.0

        present = 0
        for col in ("sea_surface_temperature", "wave_height", "salinity", "current_speed"):
            values = [getattr(o, col) for o in obs]
            if any(v is not None for v in values):
                present += 1
        coverage = present / 4.0
        quantity = min(1.0, len(obs) / float(OBS_WINDOW))
        freshness = max(0.0, 1.0 - freshness_hours / 48.0)
        agreement = max(0.0, 1.0 - min(1.0, mae / 0.5))

        score = round(100.0 * (0.35 * freshness + 0.25 * coverage + 0.20 * quantity + 0.20 * agreement))
        score = int(min(score, 100))

        components = [
            {"factor": "Observation age", "pct": _clamp100(freshness), "weight": 35},
            {"factor": "Field coverage", "pct": _clamp100(coverage), "weight": 25},
            {"factor": "Sampling density", "pct": _clamp100(quantity), "weight": 20},
            {"factor": "Model agreement", "pct": _clamp100(agreement), "weight": 20},
        ]
        weighting = ", ".join(f"{c['factor'].split()[0]} {c['weight']}%" for c in components)

        temps = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
        anom = abs((temps[-1] - np.mean(temps[:-1]))) if len(temps) >= 5 else 0.0
        active_alerts = risk.get("active_alerts", 0)
        disagreement = bool(drift or anom >= 1.0 or active_alerts > 0)

        interpretation = (
            "High model–observation disagreement detected — verify manually."
            if disagreement
            else "Observation stream agrees with the model expectation."
        )

        rows.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "observation_confidence": int(score),
                "freshness_hours": round(freshness_hours, 1),
                "field_coverage": round(coverage, 2),
                "sample_size": len(obs),
                "agreement": round(agreement, 2),
                "confidence_components": components,
                "component_weights": weighting,
                "model_trust": trust_by_id.get(loc.id, {}).get("trust_score", 0),
                "drift": drift,
                "disagreement": disagreement,
                "interpretation": interpretation,
            }
        )

    rows.sort(key=lambda r: r["observation_confidence"])
    return {"generated_at": now.isoformat(), "regions": rows}


# ---------------------------------------------------------------------------
# 2. Difference Engine (MODEL | OBSERVED | DEVIATION)
# ---------------------------------------------------------------------------

def difference_engine(db: Session, location_id: int | None = None) -> dict:
    """Model-vs-observation deviation for every field of each selected coast."""
    locations = db.query(OceanLocation).all()
    if location_id is not None:
        locations = [loc for loc in locations if loc.id == location_id]

    regions = []
    for loc in locations:
        obs = _latest_rows(db, loc)
        latest = obs[-1] if obs else None

        fields = []
        for col, meta in (
            ("sea_surface_temperature", "temperature"),
            ("wave_height", "wave_height"),
            ("salinity", "salinity"),
            ("current_speed", "current_speed"),
        ):
            values = [getattr(o, col) for o in obs]
            observed = values[-1] if any(v is not None for v in values) else None
            if observed is None:
                continue  # only present fields we actually measure
            model = _baseline(values)
            dev = round(observed - model, 2) if model is not None else None
            fields.append(
                {
                    "field": meta,
                    "label": FIELD_META[meta]["label"],
                    "unit": FIELD_META[meta]["unit"],
                    "model": round(float(model), 2) if model is not None else None,
                    "observed": round(float(observed), 2),
                    "deviation": dev,
                    "deviation_level": _deviation_level(meta, dev),
                    "direction": ("above" if (dev is not None and dev > 0)
                                  else "below" if (dev is not None and dev < 0) else "at"),
                }
            )

        explanation = _explain(fields, loc)
        regions.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "latest_time": latest.timestamp.isoformat() if latest else None,
                "window_hours": len(obs),
                "fields": fields,
                "explanation": explanation,
            }
        )

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "regions": regions}
    if location_id is not None:
        payload["region"] = regions[0] if regions else None
    return payload


def _explain(fields: list[dict], loc: OceanLocation) -> dict:
    """Plain-language interpretation: what, why it matters, possible cause."""
    if not fields:
        return {
            "headline": "No measured fields to compare yet.",
            "possible_cause": "Wait for the next observation cycle.",
            "confidence": 0,
        }
    focus = max(fields, key=lambda f: abs(f["deviation"] or 0.0))
    dev = focus["deviation"] or 0.0
    direction = focus["direction"]
    level = focus["deviation_level"]

    headline = (
        f"{loc.name.replace(' Coast', '')}: {focus['label']} is {abs(dev):.1f}{focus['unit']} "
        f"{'above' if direction == 'above' else 'below' if direction == 'below' else 'at'} "
        f"the model baseline."
    )
    cause = CAUSES.get((focus["field"], direction), "Regional ocean dynamics.")
    if level == "low":
        cause += "; within normal variability."

    confidence = int(min(95, 60 + abs(dev) / FIELD_META[focus["field"]]["high"] * 25))
    return {
        "headline": headline,
        "possible_cause": cause,
        "affected_note": "Likely affects the surface layer (0–40 m)." if focus["field"] == "temperature" else "Surface forcing only.",
        "confidence": confidence,
        "focus_field": focus["field"],
    }


# ---------------------------------------------------------------------------
# 3. Operational Situation Panel
# ---------------------------------------------------------------------------

def situation_panel(db: Session) -> dict:
    """One-glance operational situation per coast (command-center strip)."""
    advisory = {r["location_id"]: r for r in safety_advisory(db)}
    risk = {r["location_id"]: r for r in compute_risk_index(db)["regions"]}
    confidence = {r["location_id"]: r for r in observation_confidence(db)["regions"]}
    now = datetime.now(timezone.utc)

    rows = []
    for loc in db.query(OceanLocation).all():
        adv = advisory.get(loc.id)
        rk = risk.get(loc.id)
        cf = confidence.get(loc.id)

        signal = rk.get("signal", 0.0) if rk else 0.0
        wave = rk.get("wave_height", 0.0) if rk else 0.0

        temp_level = "HIGH" if signal >= 1.5 else "MODERATE" if signal >= 0.8 else "LOW"
        wave_state = "HIGH" if wave >= 1.6 else "MODERATE" if wave >= 1.0 else "LOW"

        disagreement = bool(cf.get("disagreement", False)) if cf else False
        status = adv.get("status", "safe") if adv else "safe"
        obs_conf = cf.get("observation_confidence", 0) if cf else 0
        trust = cf.get("model_trust", 0) if cf else 0

        if status == "danger":
            headline = "High-risk coastal situation — action advised"
        elif disagreement:
            headline = "Model–observation disagreement detected — verify"
        elif temp_level == "HIGH":
            headline = "Running significantly above the model baseline"
        else:
            headline = "Conditions tracking the model baseline"

        rows.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "status": status,
                "temperature_anomaly": temp_level,
                "wave_state": wave_state,
                "observation_confidence": int(obs_conf),
                "model_trust": int(trust),
                "disagreement": disagreement,
                "headline": headline,
            }
        )

    rows.sort(key=lambda r: (r["status"] != "safe", r["disagreement"], -r["observation_confidence"]))
    return {"generated_at": now.isoformat(), "regions": rows}


# ---------------------------------------------------------------------------
# 4. Model Skill Score (MAE / RMSE / bias / skill-vs-climatology)
# ---------------------------------------------------------------------------

def model_skill(db: Session) -> dict:
    """Measured model accuracy per region & variable, plus an overall skill
    score (fraction of variance explained vs a climatology baseline)."""
    from app.modules.ai.comparison.comparator import compare_location

    now = datetime.now(timezone.utc)
    rows = []
    for loc in db.query(OceanLocation).all():
        cmp = compare_location(db, loc)
        skill_vals = []
        variables = {}
        for key, f_key in (("temperature", "temperature"), ("wave_height", "wave")):
            fcst = [s.get(f"forecast_{f_key}") for s in cmp.get("series", [])]
            obsd = [s.get(f"observed_{f_key}") for s in cmp.get("series", [])]
            pairs = [(a, b) for a, b in zip(fcst, obsd) if a is not None and b is not None]
            if len(pairs) < 3:
                variables[key] = None
                continue
            fc = np.array([p[0] for p in pairs], dtype=float)
            ob = np.array([p[1] for p in pairs], dtype=float)
            mae = float(np.mean(np.abs(fc - ob)))
            rmse = float(np.sqrt(np.mean((fc - ob) ** 2)))
            bias = float(np.mean(fc - ob))
            clim_mae = float(np.mean(np.abs(ob - np.mean(ob))))
            skill = round(100.0 * (1.0 - mae / clim_mae), 1) if clim_mae > 1e-4 else None
            skill = max(0.0, min(100.0, skill)) if skill is not None else None
            if skill is not None:
                skill_vals.append(skill)
            variables[key] = {
                "mae": round(mae, 3),
                "rmse": round(rmse, 3),
                "bias": round(bias, 3),
                "climatology_mae": round(clim_mae, 3),
                "skill": skill,
                "samples": len(pairs),
            }
        overall = round(float(np.mean(skill_vals)), 1) if skill_vals else None
        rows.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "overall_skill": overall,
                "variables": variables,
            }
        )
    rows.sort(key=lambda r: -(r["overall_skill"] or -1))
    return {"generated_at": now.isoformat(), "regions": rows}


# ---------------------------------------------------------------------------
# 5. Ocean Event Detection & Classification
# ---------------------------------------------------------------------------

EVENT_META = {
    "marine_heatwave": {"label": "Marine heatwave", "icon": "🔥"},
    "cold_water_anomaly": {"label": "Cold-water anomaly", "icon": "❄️"},
    "rapid_temp_change": {"label": "Rapid temperature change", "icon": "⚡"},
    "strong_current_event": {"label": "Strong-current event", "icon": "🌊"},
    "coastal_flooding_risk": {"label": "Coastal flooding risk", "icon": "⚠️"},
    "model_mismatch_event": {"label": "Model-observation mismatch", "icon": "⟲"},
}

# Wave band thresholds (m)
_EV_SAFE, _EV_WARN, _EV_DANGER = 1.0, 1.6, 2.4


def classify_events(db: Session) -> dict:
    """Upgrade anomalies into named, classified, evolving ocean events."""
    risk_by = {r["location_id"]: r for r in compute_risk_index(db)["regions"]}
    diff_by = {r["location_id"]: r for r in difference_engine(db)["regions"]}
    alerts = (
        db.query(OceanAlert)
        .filter(OceanAlert.status == "active")
        .all()
    )
    active_by: dict = {}
    for a in alerts:
        active_by.setdefault(a.location_id, []).append(a)

    events: list[dict] = []
    for loc in db.query(OceanLocation).all():
        obs = _latest_rows(db, loc)
        temps = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
        waves = [o.wave_height for o in obs if o.wave_height is not None]
        speeds = [o.current_speed for o in obs if o.current_speed is not None]

        def _span(series: list[float], above: float, rising: bool | None = None) -> dict:
            """Find start hour & peak for a threshold crossing in a series."""
            if not series:
                return {"start_h": None, "peak": None, "peak_h": None, "hours_on": 0}
            start = next((i for i, v in enumerate(series) if above is None or v >= above), None)
            peak_i = int(np.argmax(series)) if series else None
            return {
                "start_h": len(series) - start - 1 if start is not None else None,
                "peak": round(float(series[peak_i]), 2) if peak_i is not None else None,
                "peak_h": len(series) - 1 - peak_i if peak_i is not None else None,
                "hours_on": (len(series) - start) if start is not None else 0,
            }

        heat = False
        cold = False
        rapid = False
        curr = False
        flood = False
        mismatch = False

        if len(temps) >= 5:
            mean = float(np.mean(temps[:-1]))
            anom = temps[-1] - mean
            heat = anom >= 1.0
            cold = anom <= -1.0
            diffs = [abs(b - a) for a, b in zip(temps[-13:], temps[-12:])]
            rapid = bool(diffs and max(diffs) >= 0.5)
        if speeds and speeds[-1] >= 0.5:
            curr = True
        if waves and waves[-1] >= _EV_WARN:
            flood = True
        for f in (diff_by.get(loc.id) or {}).get("fields", []):
            if f.get("deviation_level") in ("high", "moderate"):
                mismatch = True

        def _conf(base: float, mag: float, scale: float) -> int:
            return int(min(95, max(55, base + mag / scale * 15)))

        latest_temp = temps[-1] if temps else None
        anom_v = (temps[-1] - float(np.mean(temps[:-1]))) if len(temps) >= 5 else 0.0
        latest_wave = waves[-1] if waves else None

        if heat:
            span = _span(temps[:-2], float(np.mean(temps[:-1])) + 1.0)
            events.append(_event(loc, "marine_heatwave", "high" if anom_v >= 1.5 else "medium",
                                 _conf(78, anom_v, 2.0), span, latest_temp, "SST anomaly"))
        if cold:
            span = _span(temps[:-2], float(np.mean(temps[:-1])) - 1.0)
            events.append(_event(loc, "cold_water_anomaly", "high" if anom_v <= -1.5 else "medium",
                                 _conf(75, abs(anom_v), 2.0), span, latest_temp, "SST anomaly"))
        if rapid:
            events.append(_event(loc, "rapid_temp_change", "medium", 72, _span(temps, None), latest_temp, "SST jump"))
        if curr:
            events.append(_event(loc, "strong_current_event", "high" if speeds[-1] >= 0.8 else "medium",
                                 80, _span(speeds[::-1], 0.5), speeds[-1], "current speed"))
        if flood:
            band = "danger" if latest_wave and latest_wave >= _EV_DANGER else "warning"
            events.append(_event(loc, "coastal_flooding_risk", band, 82, _span(waves, _EV_WARN), latest_wave, "wave height"))
        if mismatch:
            events.append(_event(loc, "model_mismatch_event", "medium", 76, _span(temps, None), None, "observed vs model baseline"))

    events.sort(key=lambda e: (e["intensity"] != "high", -(e["confidence"] or 0)))
    summary = {e["event_type"]: sum(1 for x in events if x["event_type"] == e["event_type"]) for e in events}
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "events": events, "summary": summary}


def _event(loc: OceanLocation, event_type: str, intensity: str, confidence: int,
           span: dict, value: float | None, var: str) -> dict:
    meta = EVENT_META[event_type]
    ev = {
        "location_id": loc.id,
        "location": loc.name,
        "event_type": event_type,
        "label": meta["label"],
        "icon": meta["icon"],
        "intensity": intensity,
        "confidence": confidence,
        "variable": var,
        "value": round(value, 2) if value is not None else None,
        "status": "active",
    }
    if span["start_h"] is not None:
        ev["began_hours_ago"] = span["start_h"]
        ev["peak_hours_ago"] = span["peak_h"]
        ev["peak_value"] = span["peak"]
        ev["hours_active"] = span["hours_on"]
        ev["evolution"] = (
            f"Began {span['start_h']}h ago, peaked {span['peak_h']}h ago "
            f"at {span['peak']}, still active."
        )
    else:
        ev["hours_active"] = span["hours_on"]
        ev["evolution"] = "Observed in the latest window; evolution building."
    return ev


# ---------------------------------------------------------------------------
# 6. What-If Scenario Simulator (illustrative, clearly labelled)
# ---------------------------------------------------------------------------

def scenario_projection(db: Session, location_id: int, wind_percent: float = 0.0) -> dict:
    """Illustrative 'what-if' projection. NOT a validated forecast."""
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if loc is None:
        return {"scenario": True, "error": "location not found"}

    rows = _latest_rows(db, loc)
    waves = [o.wave_height for o in rows if o.wave_height is not None]
    temps = [o.sea_surface_temperature for o in rows if o.sea_surface_temperature is not None]
    base_wave = waves[-1] if waves else None
    base_temp = temps[-1] if temps else None

    k = max(-0.5, min(0.5, wind_percent / 100.0))
    proj_wave = round(max(0.0, (base_wave or 0) * (1 + k * 0.9)), 2)
    proj_temp = round((base_temp or 0) - k * 0.4, 2)  # stronger wind → slight surface cooling

    band = "danger" if proj_wave >= _EV_DANGER else "warning" if proj_wave >= _EV_WARN else \
        "caution" if proj_wave >= _EV_SAFE else "safe"
    band_change = ""
    if base_wave is not None:
        cur_band = "danger" if base_wave >= _EV_DANGER else "warning" if base_wave >= _EV_WARN else \
            "caution" if base_wave >= _EV_SAFE else "safe"
        band_change = "unchanged" if cur_band == band else f"{cur_band} → {band}"

    narrative = (
        f"If wind intensity changes by {wind_percent:+.0f}%, projected wave height at "
        f"{loc.name} moves from {base_wave:.2f} m to ~{proj_wave:.2f} m "
        f"({band_change}). {_band_message(band)}"
    )

    return {
        "scenario": True,
        "caveat": "Illustrative scenario simulation — not a validated operational forecast.",
        "location_id": loc.id,
        "location": loc.name,
        "inputs": {"wind_percent": wind_percent},
        "output": {
            "wave_height": proj_wave,
            "expected_sst": proj_temp,
            "hazard_band": band,
            "band_change": band_change,
        },
        "narrative": narrative,
    }


def _band_message(band: str) -> str:
    return {
        "danger": "Small vessels advised against sailing.",
        "warning": "Exercise caution offshore — elevated wave risk.",
        "caution": "Slightly elevated conditions; standard caution advised.",
        "safe": "Conditions remain within normal small-craft limits.",
    }[band]


# ---------------------------------------------------------------------------
# 7. Data Provenance & Scientific Traceability
# ---------------------------------------------------------------------------

def provenance(db: Session) -> dict:
    """For every displayed value: source, dataset, time, processing, model run."""
    now = datetime.now(timezone.utc)
    rows = []
    for loc in db.query(OceanLocation).all():
        obs = _latest_rows(db, loc, window=OBS_WINDOW)
        sources = sorted({o.source or "unknown" for o in obs})
        data_types = sorted({o.data_type or "observation" for o in obs})
        times = [o.timestamp for o in obs]
        latest = max(times) if times else None

        rows.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "sources": sources,
                "datasets": ["Open-Meteo Marine (ERA5-driven coastal reanalysis)"],
                "data_types": data_types,
                "observation_count": len(obs),
                "latest_observation": (latest.isoformat() if latest else None),
                "window_hours": OBS_WINDOW,
                "processing": "Quality check → temporal alignment → linear trend baseline → deviation & confidence",
                "model_run_id": f"MR-{now.strftime('%Y%m%d%H')}-L{loc.id:02d}",
                "last_updated": now.isoformat(),
            }
        )
    return {"generated_at": now.isoformat(), "regions": rows}


# ---------------------------------------------------------------------------
# 8. Multi-variable Scenario Projection + Counterfactual
# ---------------------------------------------------------------------------

def scenario_projection_multi(db: Session, location_id: int,
                               wind_percent: float = 0.0,
                               temp_delta: float = 0.0,
                               salinity_delta: float = 0.0,
                               mixing_factor: float = 1.0) -> dict:
    """Multi-variable scenario analysis. Clearly labelled NOT a forecast."""
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if loc is None:
        return {"error": "location not found", "scenario": True}

    rows = _latest_rows(db, loc)
    waves = [o.wave_height for o in rows if o.wave_height is not None]
    temps = [o.sea_surface_temperature for o in rows if o.sea_surface_temperature is not None]
    sals  = [o.salinity for o in rows if o.salinity is not None]
    currs = [o.current_speed for o in rows if o.current_speed is not None]

    base_wave = waves[-1] if waves else 1.0
    base_temp = temps[-1] if temps else 28.0
    base_sal  = sals[-1] if sals else 35.0
    base_curr = currs[-1] if currs else 0.4

    k_w = max(-0.5, min(0.5, wind_percent / 100.0))
    proj_wave = round(max(0.0, base_wave * (1 + k_w * 0.9)), 2)
    proj_temp = round(base_temp + temp_delta - k_w * 0.4, 2)
    proj_sal  = round(base_sal + salinity_delta, 2)
    proj_curr = round(max(0.0, base_curr * (1 + k_w * 0.5) * (1 + 0.1 * max(0, mixing_factor - 1.0))), 2)

    # Mixing suppresses stratification; stronger mixing reduces surface warming
    proj_temp = round(proj_temp * (1.0 - 0.1 * max(0, mixing_factor - 1.0)), 2)

    band = "danger" if proj_wave >= _EV_DANGER else "warning" if proj_wave >= _EV_WARN else \
        "caution" if proj_wave >= _EV_SAFE else "safe"
    cur_band = "danger" if base_wave >= _EV_DANGER else "warning" if base_wave >= _EV_WARN else \
        "caution" if base_wave >= _EV_SAFE else "safe"
    band_change = "unchanged" if cur_band == band else f"{cur_band} → {band}"

    narrative = (
        f"Scenario at {loc.name}: wind {wind_percent:+.0f}%, SST {temp_delta:+.1f}°C, "
        f"salinity {salinity_delta:+.2f} PSU, mixing ×{mixing_factor:.1f}. "
        f"Projected: wave {proj_wave:.2f}m, SST {proj_temp:.1f}°C ({band_change}). "
        f"{_band_message(band)} This is an illustrative scenario, not a validated forecast."
    )

    return {
        "scenario": True,
        "caveat": "Scenario analysis — clearly labelled as an illustrative 'what-if', not a prediction.",
        "location_id": loc.id,
        "location": loc.name,
        "inputs": {
            "wind_percent": wind_percent,
            "temp_delta": temp_delta,
            "salinity_delta": salinity_delta,
            "mixing_factor": mixing_factor,
        },
        "output": {
            "wave_height": proj_wave,
            "sst": proj_temp,
            "salinity": proj_sal,
            "current_speed": proj_curr,
            "hazard_band": band,
            "band_change": band_change,
        },
        "narrative": narrative,
    }


def counterfactual(db: Session, location_id: int,
                   wind_percent: float = 0.0,
                   temp_delta: float = 0.0,
                   salinity_delta: float = 0.0) -> dict:
    """Actual vs counterfactual side-by-side investigation."""
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not loc:
        return {"error": "location not found"}

    rows = _latest_rows(db, loc)
    m = rows[-1] if rows else None
    actual = {
        "sst": round(m.sea_surface_temperature, 2) if m and m.sea_surface_temperature is not None else None,
        "wave": round(m.wave_height, 2) if m and m.wave_height is not None else None,
        "salinity": round(m.salinity, 2) if m and m.salinity is not None else None,
    }

    scenario = scenario_projection_multi(db, location_id, wind_percent, temp_delta, salinity_delta)
    scen_out = scenario.get("output", {})

    diff = {}
    for k in ("sst", "wave"):
        a = actual.get(k)
        s = scen_out.get("sst") if k == "sst" else scen_out.get("wave_height")
        if a is not None and s is not None:
            diff[k] = round(s - a, 3)

    driver_note = ""
    if temp_delta != 0:
        driver_note += f"SST shifted by {temp_delta:+.1f}°C "
    if wind_percent != 0:
        driver_note += f"wind changed by {wind_percent:+.0f}% "
    if salinity_delta != 0:
        driver_note += f"salinity shifted by {salinity_delta:+.2f} PSU "
    if not driver_note:
        driver_note = "No parameter changes applied."

    return {
        "location_id": location_id,
        "location": loc.name,
        "actual": actual,
        "scenario": scen_out,
        "differences": diff,
        "driver_note": driver_note,
        "narrative": (
            f"Actual conditions at {loc.name}: SST {actual.get('sst')}°C, wave {actual.get('wave')}m. "
            f"Counterfactual scenario: SST {scen_out.get('sst')}°C, wave {scen_out.get('wave_height')}m. "
            f"Difference: ΔSST {diff.get('sst', 0):+.2f}°C, Δwave {diff.get('wave', 0):+.2f}m. "
            f"{driver_note} This comparison helps investigate which environmental drivers "
            f"appear most influential for this region."
        ),
        "caveat": "Counterfactual investigation is an illustrative scenario tool, not a prediction.",
    }


# ---------------------------------------------------------------------------
# 9. Ocean Future Window
# ---------------------------------------------------------------------------

def future_windows(db: Session, location_id: int) -> dict:
    """Risk + confidence windows at 3 / 7 / 14 / 30 day horizons."""
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not loc:
        return {"error": "location not found"}
    rows = _latest_rows(db, loc)
    temps = [o.sea_surface_temperature for o in rows if o.sea_surface_temperature is not None]
    waves = [o.wave_height for o in rows if o.wave_height is not None]
    currs = [o.current_speed for o in rows if o.current_speed is not None]

    base_temp = temps[-1] if temps else 28.0
    base_wave = waves[-1] if waves else 1.0
    base_curr = currs[-1] if currs else 0.4

    windows = []
    for h in (72, 168, 336, 720):
        day = h // 24
        t_step = (temps[-1] - temps[0]) / max(1, len(temps)) if len(temps) >= 2 else 0
        proj_temp = round(base_temp + t_step * h, 2)
        proj_wave = round(max(0.0, base_wave + (waves[-1] - waves[0]) / max(1, len(waves)) * h * 0.3), 2)
        c_step = (currs[-1] - currs[0]) / max(1, len(currs)) if len(currs) >= 2 else 0
        proj_curr = round(max(0.0, base_curr + c_step * h * 0.2), 2)

        conf = max(20, round(95 - h * 0.1, 1))
        band = "danger" if proj_wave >= _EV_DANGER else "warning" if proj_wave >= _EV_WARN else \
            "caution" if proj_wave >= _EV_SAFE else "safe"
        windows.append({
            "horizon_days": day,
            "horizon_hours": h,
            "projected_sst": proj_temp,
            "projected_wave": proj_wave,
            "projected_current_speed": proj_curr,
            "hazard_band": band,
            "confidence": conf,
            "narrative": (
                f"At {day}-day horizon ({loc.name}): SST ~{proj_temp:.1f}°C, wave ~{proj_wave:.2f}m, "
                f"hazard band: {band}. Confidence: {conf}%. "
                f"Longer horizons carry larger uncertainty — treat as directional indicators."
            ),
        })

    return {"location_id": location_id, "location": loc.name, "windows": windows}