"""Observation Recommendation Engine — where to sample next and why.

Answers the "what should we observe?" decision-intelligence question by
combining observation density, recency, uncertainty, priority tiers and active
events into a ranked, actionable sampling plan:

  • which region → which variables → which platforms → how many samples
  • the expected confidence gain (reuses the coverage simulator)
  • a network-level aggregate (samples needed to lift average coverage ≥ 80%)
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.forensics.intelligence import coverage_simulator, uncertainty_map
from app.modules.ai.validation.engine import classify_events

# Variable → platform guidance by region type.
PLATFORMS = {
    ("coastal", "temperature"): ["Coastal AUV", "Mooring buoy (CTD + thermistor chain)"],
    ("coastal", "wave_height"): ["Coastal radar altimeter", "Tide-gauge wave rider"],
    ("coastal", "salinity"): ["Ship CTD", "Autonomous surface glider"],
    ("coastal", "current_speed"): ["ADCP mooring", "HF radar"],
    ("bay", "temperature"): ["Drifter buoys", "Ship CTD"],
    ("bay", "wave_height"): ["Wave rider buoy", "Satellite altimetry validation"],
    ("bay", "salinity"): ["Glider transect", "Moored salinity sensor"],
    ("bay", "current_speed"): ["Acoustic Doppler profiler", "Drifter array"],
    ("gulf", "temperature"): ["Drifter buoys", "Mooring string"],
    ("gulf", "wave_height"): ["Wave rider", "Coastal watch camera + altimeter"],
    ("gulf", "salinity"): ["Glider transect", "Ship underway logging"],
    ("gulf", "current_speed"): ["ADCP mooring", "HF radar"],
    ("sea", "temperature"): ["Argo float", "Satellite L2S corrected SST validation"],
    ("sea", "wave_height"): ["Altimetry satellite", "Moored wave buoy"],
    ("sea", "salinity"): ["Argo float", "SMOS/SMAP validation"],
    ("sea", "current_speed"): ["Drifter array", "Geostrophic + HF radar blend"],
}

DEFAULT_PLATFORMS = ["Drone/SAR flight", "Ship CTD cast", "Fixed coastal sensor"]

# Target cadence (obs / 96h window) for a healthy monitoring stream.
TARGET_COUNT = 48


def _platforms(region_type: str, variable: str) -> list[str]:
    fallback = PLATFORMS.get(("sea", variable)) or DEFAULT_PLATFORMS
    if "reef" in (region_type or ""):
        return ["Drone thermal/optical survey", "In-situ diver transect", "Moored mini-CTD"]
    if "port" in (region_type or ""):
        return ["Harbour AUV survey", "Tide-gauge suite", "Mobile wave rider"]
    if "coastal" in (region_type or ""):
        return PLATFORMS.get(("coastal", variable)) or fallback
    return PLATFORMS.get((region_type or "sea", variable)) or fallback


def _series_stats(db: Session, loc_id: int) -> tuple[list, int, object | None]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=12)      # tolerate the sim's look-ahead timestamps
    rows = (
        db.query(OceanObservation.timestamp, OceanObservation.sea_surface_temperature)
        .filter(OceanObservation.location_id == loc_id,
                OceanObservation.timestamp <= end)
        .order_by(OceanObservation.timestamp.desc())
        .limit(TARGET_COUNT)
        .all()
    )
    n = len(rows)
    latest_ts = rows[0][0] if rows else None
    return rows, n, latest_ts


def _observation_need(db: Session, loc_id: int) -> dict:
    """Fresh measure: count, recency, anomaly z-score and a 0–100 gap score."""
    now = datetime.now(timezone.utc)
    rows, n, latest_ts = _series_stats(db, loc_id)

    recency_h = (now - latest_ts).total_seconds() / 3600 if latest_ts is not None else None
    span_h = (rows[0][0] - rows[-1][0]).total_seconds() / 3600 if n >= 2 else 0

    temps = [r[1] for r in rows if r[1] is not None]
    anomaly_z = 0.0
    if len(temps) >= 5:
        mean = sum(temps) / len(temps)
        var = sum((t - mean) ** 2 for t in temps) / len(temps)
        std = var ** 0.5 or 1e-9
        anomaly_z = abs(temps[-1] - mean) / std

    density_score = min(100, n / TARGET_COUNT * 100)
    recency_penalty = 45 if recency_h is None or recency_h > 12 else 0
    count_gap = 100 - density_score
    # Anomalous regimes deserve targeted event-response sampling even when dense.
    anomaly_need = min(45, round(anomaly_z * 15, 1))
    need = round(min(100, count_gap * 0.5 + recency_penalty + anomaly_need), 1)

    return {
        "count_in_window": n,
        "target_count": TARGET_COUNT,
        "span_h": round(span_h, 1),
        "recency_h": round(recency_h, 1) if recency_h is not None else None,
        "anomaly_z": round(anomaly_z, 2),
        "obs_need": need,
    }


def _gap_reason(name: str, obs: dict, uncertainty: float, active_event: bool) -> str:
    if active_event:
        return (f"Active event signal at {name} — high-frequency sampling raises forensic "
                f"confidence while conditions keep evolving.")
    if obs["recency_h"] is not None and obs["recency_h"] > 12:
        return f"Last reading at {name} is {obs['recency_h']:.0f}h old ({uncertainty:.0f}% uncertainty) — refresh to reduce staleness."
    return f"Only {obs['count_in_window']} readings in the window ({obs['span_h']:.0f}h) — densify to sharpen the local baseline."


def build_recommendations(db: Session, min_priority: float = 30.0) -> dict:
    unc = {u["location_id"]: u for u in uncertainty_map(db).get("regions", [])}
    events = classify_events(db)["events"]
    event_vars: dict[int, set] = {}
    for e in events:
        event_vars.setdefault(e["location_id"], set()).add(e.get("variable", "temperature"))

    recommendations = []
    for loc in db.query(OceanLocation).all():
        obs = _observation_need(db, loc.id)
        u = unc.get(loc.id, {})
        uncertainty = u.get("uncertainty", 40)
        active_event = bool(event_vars.get(loc.id))

        # Which variables deserve sampling in this region?
        variable_gaps = []
        if obs["obs_need"] >= 15:
            variable_gaps.append("temperature")
        if active_event:
            variable_gaps.extend(["wave_height", "current_speed"])
        if u.get("coverage_pct", 100) < 60:
            variable_gaps.append("salinity")
        variable_gaps = list(dict.fromkeys(variable_gaps))[:3]

        needs = [{
            "variable": var,
            "platforms": _platforms(loc.region_type, var),
            "reason": _gap_reason(loc.name, obs, uncertainty, active_event),
        } for var in variable_gaps]

        # Expected confidence gain from closing the gap.
        sim = None
        if obs["obs_need"] >= 20:
            needed_pct = round(min(60, obs["obs_need"] * 0.6), 0)
            sim = coverage_simulator(db, loc.id, needed_pct)

        decision_impact = round(min(100, obs["obs_need"] * 0.55 + uncertainty * 0.25
                                    + (25 if active_event else 0)), 1)
        recommendations.append({
            "location_id": loc.id,
            "location": loc.name,
            "region_type": loc.region_type,
            "obs_need": obs["obs_need"],
            "count_in_window": obs["count_in_window"],
            "recency_h": obs["recency_h"],
            "uncertainty": uncertainty,
            "active_event": active_event,
            "decision_impact": decision_impact,
            "variables_to_sample": [n["variable"] for n in needs],
            "needs": needs,
            "coverage_simulation": sim,
            "action": (f"Deploy {len(needs) or 1} sampling plan(s) at {loc.name} to close the "
                       f"{obs['obs_need']:.0f}pt observational gap and reduce uncertainty."),
        })

    recommendations.sort(key=lambda r: -r["decision_impact"])

    always = [r for r in recommendations if r["obs_need"] >= 30 or r["active_event"]]
    avg_need = sum(r["obs_need"] for r in recommendations) / max(1, len(recommendations))
    total_samples = sum(
        max(1, int((100 - r["obs_need"]) * 0.30)) for r in always
    )
    return {
        "engine": "Observation Recommendation Engine",
        "network_average_obs_need": round(avg_need, 1),
        "target_obs_need": 30.0,
        "estimated_observations_needed": total_samples,
        "summary": (f"{len(always)} region(s) need closer observation today. ~**{total_samples}** extra "
                    f"sampling passes would bring the network average gap below the action threshold, "
                    f"prioritising **{always[0]['location']}** first." if always else
                    "Observation coverage is healthy network-wide — no immediate sampling action required."),
        "recommendations": recommendations,
    }