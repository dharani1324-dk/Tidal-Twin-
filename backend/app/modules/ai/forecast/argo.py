"""
TidalTwin - Argo Float Trajectories
=====================================
Serves Argo float trajectories two ways - always honestly labelled:

  REAL    - when real Argo GDAC profiles have been ingested into
            `argo_profiles` (via scripts.fetch_argo + scripts.ingest_argo),
            each float's path is built from its actual stored profile levels
            (lat/lon/depth/time/temp/sal), explicitly marked "Real Argo GDAC".
  SIM     - otherwise we fall back to a deterministic simulator so the
            dashboards keep working, but every float is labelled "Simulated
            Argo" and the source registry reports the source as 'simulated'.

Each simulated float:
  - Has a unique WMO-style ID seeded from (location_id, float_index)
  - Follows a seeded random walk + sinusoidal depth cycle
  - Produces ~30 surface + subsurface points (6 hours apart)
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.argo import ArgoProfile
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.services.ocean_data import get_location_center

_SEED_ROOT = 42_000          # base seed so every location gets a stable id range


def _real_floats(db: Session, n_floats: int = 10) -> list[dict[str, Any]]:
    """Build float trajectories from REAL ingested argo_profiles rows.

    One float per float_id, ordered by most recent profile, capped at
    `n_floats`. A float with only NULL temperature/salinity everywhere is
    still shown - its values are 'Data unavailable' rather than invented.
    """
    latest_per_float = (
        db.query(
            ArgoProfile.float_id,
            func.count(ArgoProfile.id).label("levels"),
            func.max(ArgoProfile.depth_m).label("depth_max"),
            func.max(ArgoProfile.time).label("latest_time"),
        )
        .group_by(ArgoProfile.float_id)
        .order_by(func.max(ArgoProfile.time).desc())
        .limit(n_floats)
        .all()
    )
    floats: list[dict[str, Any]] = []
    for float_id, levels, depth_max, latest_time in latest_per_float:
        levels_rows = (
            db.query(
                ArgoProfile.latitude, ArgoProfile.longitude, ArgoProfile.time,
                ArgoProfile.depth_m, ArgoProfile.temperature, ArgoProfile.salinity,
            )
            .filter(ArgoProfile.float_id == float_id)
            .order_by(ArgoProfile.depth_m.asc())
            .all()
        )
        source_file = (
            db.query(ArgoProfile.source_file)
            .filter(ArgoProfile.float_id == float_id)
            .limit(1)
            .scalar()
        )
        points: list[dict] = []
        for la, lo, t, depth, temp, sal in levels_rows:
            points.append({
                "lat": round(la, 5),
                "lon": round(lo, 5),
                "depth_m": round(depth, 1) if depth is not None else None,
                "timestamp": t.isoformat(),
                "temperature": temp,
                "salinity": sal,
            })
        floats.append({
            "float_id": float_id,
            "label": str(float_id),
            # open-ocean float: no supervised coast owns it (transect uses 0)
            "location_id": 0,
            "location": "open ocean (Argo GDAC)",
            "platform": "Real Argo GDAC profile",
            "n_points": len(points),
            "points": points,
            "profile": {
                "max_depth_m": depth_max,
                "levels": levels,
                "latest_time": latest_time.isoformat() if latest_time else None,
            },
            "provenance": source_file,
        })
    return floats


def _seed_for(loc_id: int, idx: int) -> int:
    return _SEED_ROOT + loc_id * 1000 + idx


def _generate_float(loc: OceanLocation, idx: int,
                    n_points: int = 28) -> dict[str, Any]:
    """
    Generate one Argo float trajectory around `loc`.
    Returns the full path + metadata.
    """
    rng = random.Random(_seed_for(loc.id, idx))
    # Anchor the float at the REAL centroid of the monitored coast (from the
    # PostGIS geometry), falling back like the rest of the app if unavailable.
    center_lat, center_lon = get_location_center(loc)
    base_lat = center_lat if center_lat is not None else 15.0
    base_lon = center_lon if center_lon is not None else 73.0

    wmo_id = f"290{loc.id:03d}{idx:03d}"
    label = f"AR{idx}"

    # Drift params (degrees per 6-hour step — simulates ocean current)
    drift_lat = rng.uniform(-0.02, 0.02)
    drift_lon = rng.uniform(-0.02, 0.02)

    # Reference profiles: base T/S from location context
    base_sst = 27.5 + rng.uniform(-2.0, 2.0)
    base_sal = 34.8 + rng.uniform(-0.4, 0.4)
    # Thermocline depth (m)
    thermocline = rng.uniform(30, 80)

    # Cycle parameters
    cycle_len = rng.randint(20, 28)     # points per dive/surface cycle
    max_depth = rng.uniform(150, 500)

    points: list[dict] = []
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    lat, lon = base_lat, base_lon
    phase = 0.0        # 0-2π across the dive cycle

    for i in range(n_points):
        t = now - timedelta(hours=6 * (n_points - 1 - i))

        # Depth follows sinusoidal cycle: surface → deep → surface
        phase = 2 * math.pi * (i / cycle_len)
        depth = max(0, (max_depth / 2) * (1 - math.cos(phase)))

        # Temperature decreases with depth (simple exponential thermocline)
        temp = base_sst - (base_sst - 4.0) * (1 - math.exp(-depth / thermocline))
        temp += rng.uniform(-0.15, 0.15)

        # Salinity: slight increase with depth
        sal = base_sal + (35.6 - base_sal) * (1 - math.exp(-depth / (thermocline * 1.5)))
        sal += rng.uniform(-0.05, 0.05)

        points.append({
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "depth_m": round(depth, 1),
            "timestamp": t.isoformat(),
            "temperature": round(max(0, temp), 2),
            "salinity": round(max(0, sal), 2),
        })

        # Drift + small random perturbation (always move — never stationary)
        lat += drift_lat + rng.uniform(-0.005, 0.005)
        lon += drift_lon + rng.uniform(-0.005, 0.005)

        # Current speed from the latest observation (or default)
        current = (rng.uniform(0.05, 0.2))
        drift_lat = rng.uniform(-0.015, 0.015)
        drift_lon = rng.uniform(-0.015, 0.015)

    return {
        "float_id": wmo_id,
        "label": label,
        "location_id": loc.id,
        "location": loc.name,
        "platform": "Simulated Argo (6-hourly)",
        "n_points": len(points),
        "points": points,
        "profile": {
            "base_sst": round(base_sst, 2),
            "base_sal": round(base_sal, 2),
            "thermocline_depth_m": round(thermocline, 1),
            "max_depth_m": round(max_depth, 1),
        },
    }


def get_argo_trajectories(db: Session, location_id: int | None = None,
                          n_floats: int = 3) -> dict:
    """
    Argo float trajectories for one or all locations.

    If REAL profiles are ingested we serve them (objectively better and
    honestly labelled); otherwise we fall back to the deterministic simulator
    so the dashboards stay populated. `location_id` only applies to the
    simulated fallback — real floats live in the open ocean, not per coast.
    """
    if db.query(ArgoProfile).limit(1).first() is not None:
        real = _real_floats(db, n_floats=10 if not location_id else 3)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(real),
            "floats": real,
            "source": "argo_profiles (real Argo GDAC)",
        }

    q = db.query(OceanLocation)
    if location_id:
        q = q.filter(OceanLocation.id == location_id)
    locs = q.all()

    floats = []
    for loc in locs:
        # Seed a stable number of floats per location from the location_id
        n = min(n_floats, 5)
        for i in range(1, n + 1):
            floats.append(_generate_float(loc, i))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(floats),
        "floats": floats,
        "source": "argo trajectory simulator",
    }
