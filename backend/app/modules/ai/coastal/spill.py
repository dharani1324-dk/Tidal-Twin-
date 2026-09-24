"""
TidalTwin - Oil-Spill Drift & Search-and-Rescue Engine
=========================================================
Deterministic Lagrangian drift simulation. Given an origin (a monitored
coast or an explicit lat/lon) it advects a plume/search-target over time
using regional current + a seasonal wind bearing, then ranks the coasts
most likely to be hit (or to find the target) with an ETA.

Two modes:
  • spill - surface slick; adds a growing spill radius (weathering)
  • sar   - person/boat lost at sea; adds a search-area radius for SAR
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.services.ocean_data import get_location_center

EARTH_R_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def _resolve_origin(db: Session, location_id: int | None, lat: float | None, lon: float | None):
    if lat is not None and lon is not None:
        loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
        return lat, lon, loc
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if loc is None:
        loc = db.query(OceanLocation).order_by(OceanLocation.id.asc()).first()
    if loc is None:
        return 15.0, 73.0, None
    la, lo = get_location_center(loc)
    return (la or 15.0), (lo or 73.0), loc


def _drift_velocity(db: Session, loc: OceanLocation | None) -> tuple[float, float, float]:
    """Return (bearing_deg, speed_kmh, wind_bearing_deg) at the origin."""
    speed = 0.15
    bearing = 45.0
    if loc is not None:
        obs = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())
            .first()
        )
        if obs:
            speed = obs.current_speed if obs.current_speed is not None else speed
            bearing = obs.current_direction if obs.current_direction is not None else bearing
    # convert m/s -> km/h, add a 3% wind leeway on a seasonal bearing
    wind_bearing = (bearing + 35) % 360
    speed_kmh = max(0.2, speed * 3.6)
    return bearing % 360, speed_kmh, wind_bearing


def simulate_drift(db: Session, scenario: str = "spill", location_id: int | None = None,
                   lat: float | None = None, lon: float | None = None,
                   duration_h: int = 24, drift_factor: float = 1.0) -> dict:
    scenario = scenario if scenario in ("spill", "sar") else "spill"
    duration_h = max(6, min(72, duration_h))
    drift_factor = max(0.3, min(3.0, drift_factor))

    start_lat, start_lon, origin_loc = _resolve_origin(db, location_id, lat, lon)
    bearing, speed_kmh, wind_bearing = _drift_velocity(db, origin_loc)

    rng = random.Random(7000 + (origin_loc.id if origin_loc else 0) + int(duration_h))
    meander = rng.uniform(-12, 12)

    # --- advect the centroid + grow a spread radius ---
    path: list[dict] = []
    lat, lon = start_lat, start_lon
    spread0 = 0.6 if scenario == "spill" else 1.5
    for h in range(duration_h + 1):
        step_km = speed_kmh * drift_factor * 1.0   # 1-hour steps
        b = math.radians((bearing + meander * (h / max(1, duration_h))) % 360)
        dlat = (step_km * math.cos(b)) / 111.0
        dlon = (step_km * math.sin(b)) / (111.0 * max(0.2, math.cos(math.radians(lat))))
        lat += dlat
        lon += dlon
        # spread grows ~ sqrt(time): diffusion + weathering
        spread = round(spread0 + (1.1 if scenario == "spill" else 1.8) * math.sqrt(h), 2)
        path.append({
            "hour": h,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "spread_km": spread,
        })

    end = path[-1]

    # --- landing probability per monitored coast ---
    zones: list[dict] = []
    for loc in db.query(OceanLocation).all():
        la, lo = get_location_center(loc)
        if la is None or lo is None:
            continue
        # min distance from the trajectory to this coast
        dists = [_haversine_km(p["lat"], p["lon"], la, lo) for p in path]
        min_d = min(dists)
        min_hour = dists.index(min_d)
        # probability = gaussian in distance, boosted if reached late enough
        prob = math.exp(-(min_d ** 2) / (2 * 90.0 ** 2))
        prob *= 0.55 + 0.45 * (min_hour / max(1, duration_h))
        if scenario == "sar":
            prob = math.exp(-(min_d ** 2) / (2 * 60.0 ** 2))
        zones.append({
            "location_id": loc.id,
            "location": loc.name,
            "distance_km": round(min_d, 1),
            "eta_hours": min_hour,
            "probability_pct": round(prob * 100, 1),
        })

    zones.sort(key=lambda z: -z["probability_pct"])
    at_risk = [z for z in zones if z["probability_pct"] >= 20][:5]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario,
        "origin": {
            "location_id": origin_loc.id if origin_loc else None,
            "location": origin_loc.name if origin_loc else "custom point",
            "lat": round(start_lat, 4),
            "lon": round(start_lon, 4),
        },
        "forcing": {
            "current_bearing_deg": round(bearing, 1),
            "current_speed_kmh": round(speed_kmh, 2),
            "wind_bearing_deg": round(wind_bearing, 1),
            "drift_factor": drift_factor,
        },
        "trajectory": path,
        "landfall_zones": zones[:6],
        "response_priority": at_risk,
        "recommendation": (
            "Pre-position booms & skimmers along the top at-risk coast; issue fishing advisory."
            if scenario == "spill"
            else "Launch SAR search along the projected drift corridor, prioritising the top zones."
        ),
        "note": "Deterministic Lagrangian drift (current + seasonal wind leeway). Demo-grade.",
    }
