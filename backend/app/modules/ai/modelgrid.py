"""
TidalTwin - Real Ocean-Model Grid Query Layer
==============================================
Serves the REAL ocean model 3D fields (temperature / salinity / current speed
by horizontal depth slice) stored in `netcdf_readings` after `scripts.ingest_netcdf`
ingests a file produced by `scripts.fetch_model` (or any CF NetCDF with the same
variables at multiple depth levels).

Honest by construction, like `realdata`: every lookup returns a reason when no
real grid (or no depth level) is present, and never fabricates a value.

Variable names come straight from the source files:
  - temperature   : sea_water_temperature / thetao / water_temperature
  - salinity      : sea_water_salinity / so / salinity
  - current_speed : current_speed (composited from u/v by fetch_model)
"""

import math
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.netcdf import NetcdfReadings

GRID_SOURCES: dict[str, dict] = {
    "temperature": {
        "labels": ["sea_water_temperature", "thetao", "water_temperature", "temperature"],
        "unit": "degC", "label": "Real ocean-model sea temperature",
        "default_max_deg": 0.5,
        "reason_no_data": "No real ocean-model grid ingested yet (run python -m scripts.fetch_model then ingest).",
    },
    "salinity": {
        "labels": ["sea_water_salinity", "so", "salinity"],
        "unit": "PSU", "label": "Real ocean-model salinity",
        "default_max_deg": 0.5,
        "reason_no_data": "No real ocean-model grid ingested yet (run python -m scripts.fetch_model then ingest).",
    },
    "current_speed": {
        "labels": ["current_speed", "sea_water_current_speed", "sea_water_speed"],
        "unit": "m/s", "label": "Real ocean-model current speed",
        "default_max_deg": 0.5,
        "reason_no_data": "No real ocean-model grid ingested yet (run python -m scripts.fetch_model then ingest).",
    },
    "current_u": {
        "labels": ["sea_water_current_u", "eastward_sea_water_velocity", "uo"],
        "unit": "m/s", "label": "Real ocean-model eastward current velocity",
        "default_max_deg": 0.5,
        "reason_no_data": "No real ocean-model grid ingested yet (run python -m scripts.fetch_model then ingest).",
    },
    "current_v": {
        "labels": ["sea_water_current_v", "northward_sea_water_velocity", "vo"],
        "unit": "m/s", "label": "Real ocean-model northward current velocity",
        "default_max_deg": 0.5,
        "reason_no_data": "No real ocean-model grid ingested yet (run python -m scripts.fetch_model then ingest).",
    },
}

REASON_NO_DEPTH = "Latest model month has no cells at that depth level."


def _as_utc(t) -> datetime:
    dt = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _info(variable: str) -> dict:
    if variable not in GRID_SOURCES:
        raise ValueError(f"unknown model-grid variable {variable!r}; use one of {sorted(GRID_SOURCES)}")
    return GRID_SOURCES[variable]


def latest_for(db: Session, variable: str) -> tuple[datetime | None, list[str]]:
    """(latest UTC time, sorted YYYY-MM month labels) or (None, []) with no rows."""
    labels = GRID_SOURCES[variable]["labels"]
    times = (
        db.query(func.distinct(NetcdfReadings.time))
        .filter(NetcdfReadings.variable_name.in_(labels))
        .filter(NetcdfReadings.value.isnot(None))
        .all()
    )
    if not times:
        return None, []
    utc = sorted(_as_utc(t[0]) for t in times)
    return utc[-1], sorted({t.strftime("%Y-%m") for t in utc})


def _base(db: Session, variable: str) -> tuple[datetime | None, list[str], list[str]]:
    latest_t, months = latest_for(db, variable)
    return latest_t, months, GRID_SOURCES[variable]["labels"]


def depths_for(db: Session, variable: str) -> list[float]:
    """Distinct depth levels (m) present in the latest model month — i.e. the
    available horizontal depth slices (surface = 0)."""
    latest_t, _, labels = _base(db, variable)
    if latest_t is None:
        return []
    rows = (
        db.query(func.distinct(NetcdfReadings.depth_m))
        .filter(NetcdfReadings.time == latest_t)
        .filter(NetcdfReadings.variable_name.in_(labels))
        .filter(NetcdfReadings.value.isnot(None))
        .all()
    )
    return sorted(float(d[0]) if d[0] is not None else 0.0 for d in rows)


def summary(db: Session, variable: str) -> dict:
    """3D field overview: latest month, note, all depth levels + cell counts."""
    info = _info(variable)
    latest_t, months, labels = _base(db, variable)
    if latest_t is None:
        return {"available": False, "variable": variable, "unit": info["unit"],
                "source": info["label"], "reason": info["reason_no_data"]}
    depths: list[dict] = []
    rows = (
        db.query(NetcdfReadings.depth_m, func.count(NetcdfReadings.id))
        .filter(NetcdfReadings.time == latest_t)
        .filter(NetcdfReadings.variable_name.in_(labels))
        .filter(NetcdfReadings.value.isnot(None))
        .group_by(NetcdfReadings.depth_m)
        .all()
    )
    for d, n in rows:
        depths.append({"depth_m": float(d) if d is not None else 0.0, "cells": int(n)})
    depths.sort(key=lambda x: x["depth_m"])
    return {
        "available": True,
        "variable": variable,
        "month": months[-1],
        "unit": info["unit"],
        "source": info["label"],
        "levels": depths,
    }


def grid_at(db: Session, variable: str, depth_m: float = 0.0) -> dict:
    """One horizontal depth slice of the latest model month: every real cell at
    that depth + the depth list + 3D summary. Honest reasons when absent."""
    info = _info(variable)
    latest_t, months, labels = _base(db, variable)
    if latest_t is None:
        return {"available": False, "variable": variable, "reason": info["reason_no_data"]}
    cells = (
        db.query(NetcdfReadings.latitude, NetcdfReadings.longitude, NetcdfReadings.value)
        .filter(NetcdfReadings.time == latest_t)
        .filter(NetcdfReadings.variable_name.in_(labels))
        .filter(NetcdfReadings.value.isnot(None))
        .filter(NetcdfReadings.depth_m == depth_m)
        .all()
    )
    if not cells:
        return {"available": False, "variable": variable, "month": months[-1],
                "reason": REASON_NO_DEPTH}
    return {
        "available": True,
        "variable": variable,
        "month": months[-1],
        "unit": info["unit"],
        "source": info["label"],
        "depth_m": depth_m,
        "depths": depths_for(db, variable),
        "rows": len(cells),
        "cells": [(la, _lon180(lo), val) for la, lo, val in cells],
    }


def profile_at(db: Session, variable: str, latitude: float, longitude: float,
               max_dist_deg: float | None = None) -> dict:
    """Vertical profile of the variable at the nearest cell (all depth levels of
    the latest model month). Honest `found: False` w/ reason."""
    info = _info(variable)
    limit = info["default_max_deg"] if max_dist_deg is None else max_dist_deg
    latest_t, months, labels = _base(db, variable)
    if latest_t is None:
        return {"found": False, "variable": variable, "reason": info["reason_no_data"]}
    rows = (
        db.query(NetcdfReadings)
        .filter(NetcdfReadings.time == latest_t)
        .filter(NetcdfReadings.variable_name.in_(labels))
        .filter(NetcdfReadings.value.isnot(None))
        .all()
    )
    if not rows:
        return {"found": False, "variable": variable, "month": months[-1],
                "reason": info["reason_no_data"]}
    best = min(rows, key=lambda r: _deg_distance(latitude, longitude, r.latitude, r.longitude))
    dist = _deg_distance(latitude, longitude, best.latitude, best.longitude)
    if dist > limit:
        return {"found": False, "variable": variable, "month": months[-1],
                "reason": f"No real {info['label'].lower()} cell within {limit:g}° of this location."}
    levels = [r for r in rows if abs(r.latitude - best.latitude) < 1e-9
              and abs(r.longitude - best.longitude) < 1e-9]
    levels.sort(key=lambda r: r.depth_m or 0.0)
    return {
        "found": True,
        "variable": variable,
        "month": months[-1],
        "latitude": best.latitude,
        "longitude": _lon180(best.longitude),
        "distance_deg": round(dist, 2),
        "unit": info["unit"],
        "source": info["label"],
        "levels": [{"depth_m": r.depth_m, "value": r.value} for r in levels],
    }


def vectors_at(db: Session, depth_m: float = 0.0) -> dict:
    """True current velocity vectors for one depth slice of the latest model
    month: a real (u, v) pair at every cell that has BOTH components.

    Honest by construction (feature #14): a cell with u but no v (or vice
    versa) is simply omitted — never given a fabricated companion; `available`
    stays False with a plain reason until a real grid with u/v is ingested.
    """
    ug = grid_at(db, "current_u", depth_m)
    vg = grid_at(db, "current_v", depth_m)
    if not ug["available"]:
        return {"available": False, "variable": "current vectors",
                "reason": ug.get("reason") or GRID_SOURCES["current_u"]["reason_no_data"]}
    if not vg["available"]:
        return {"available": False, "variable": "current vectors",
                "reason": "The real model grid has eastward (u) cells but no northward (v) cells at this depth."}
    u_by_cell = {(la, lo): val for la, lo, val in ug["cells"]}
    vectors: list[dict] = []
    for la, lo, vv in vg["cells"]:
        uu = u_by_cell.get((la, lo))
        if uu is None:
            continue  # one component missing at this cell — honest gap, no guess
        vectors.append({
            "latitude": la,
            "longitude": lo,
            "u": round(uu, 4),
            "v": round(vv, 4),
            "speed": round(math.hypot(uu, vv), 4),
        })
    if not vectors:
        return {"available": False, "variable": "current vectors", "month": ug["month"],
                "reason": "No cells carrying BOTH u and v components at this depth."}
    return {
        "available": True,
        "variable": "current vectors",
        "month": ug["month"],
        "unit": "m/s",
        "source": "Real ocean-model (NRL HYCOM / CMEMS-style) current velocity",
        "depth_m": ug["depth_m"],
        "depths": ug["depths"],
        "rows": len(vectors),
        "cells": vectors,
    }


def _lon180(lon: float) -> float:
    return lon - 360.0 if lon > 180 else lon


def _deg_distance(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    dlat = lat0 - lat1
    dlon = (lon0 - lon1) * math.cos(math.radians(lat0))
    return math.sqrt(dlat * dlat + dlon * dlon)