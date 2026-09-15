"""
OceanVerse AI - Argo Float Trajectory Simulator
===============================================
Generates deterministic, reproducible simulated Argo float paths
around each monitored location. Floats drift with regional currents,
dive/surface in typical 10-day cycles, and carry T/S profiles.

Each float:
  - Has a unique WMO-style ID seeded from (location_id, float_index)
  - Follows a seeded random walk + sinusoidal depth cycle
  - Produces ~30 surface + subsurface points (6 hours apart)
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.services.ocean_data import get_location_center

_SEED_ROOT = 42_000          # base seed so every location gets a stable id range


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
    Generate Argo float trajectories for one or all locations.
    Returns a dict with `generated_at` and `floats` list.
    """
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
    }
