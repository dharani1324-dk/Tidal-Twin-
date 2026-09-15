"""
OceanVerse AI - Model vs Observation Comparison Engine
======================================================
Reusable comparison engine: for a chosen location, variable and depth,
computes the numerical-model estimate and the real observation value,
their difference, percentage difference, observation quality, temporal
and spatial alignment, and a transparent confidence score.

Honesty contract:
    * temperature / wave_height / wave_direction comparisons are REAL
      (Open-Meteo Marine observations vs the history-conditioned model).
    * salinity / current_speed have no in-situ columns populated yet, so
      they are reported as ``data_status = unavailable`` rather than faked.
    * demo rows (source SIMULATED_HEATWAVE) are flagged ``demo``.
"""

import math
from datetime import datetime, timezone

import numpy as np
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.twin import confidence as conf
from app.modules.ai.validation.engine import _baseline, _latest_rows

# Variables the engine knows how to compare.
VARIABLES = {
    "temperature": {
        "column": "sea_surface_temperature",
        "label": "Sea temperature",
        "unit": "\u00b0C",
        "high": 1.5,
        "moderate": 0.8,
        "role": "observation",
    },
    "wave_height": {
        "column": "wave_height",
        "label": "Wave height",
        "unit": "m",
        "high": 0.8,
        "moderate": 0.4,
        "role": "observation",
    },
    "wave_direction": {
        "column": "wave_direction",
        "label": "Wave direction",
        "unit": "\u00b0",
        "high": 45.0,
        "moderate": 20.0,
        "role": "observation",
    },
    "salinity": {
        "column": "salinity",
        "label": "Salinity",
        "unit": "PSU",
        "high": 0.8,
        "moderate": 0.4,
        "role": "unavailable",
    },
    "current_speed": {
        "column": "current_speed",
        "label": "Current speed",
        "unit": "m/s",
        "high": 0.35,
        "moderate": 0.18,
        "role": "unavailable",
    },
}

SIMULATED_PREFIX = "SIMULATED"


def _loc_latlon(loc: OceanLocation) -> dict:
    """Centroid (lon, lat) of a location polygon, mirroring ocean.py."""
    if loc.geom is None:
        return {"latitude": None, "longitude": None}
    try:
        geom = to_shape(loc.geom)
        lon, lat = geom.centroid.x, geom.centroid.y
        return {"latitude": round(lat, 3), "longitude": round(lon, 3)}
    except Exception:
        return {"latitude": None, "longitude": None}


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def data_status_for(source: str, ts: datetime | None, now: datetime | None = None) -> str:
    """Classify an observation row as live / recent / cached / demo."""
    if not ts:
        return "unavailable"
    if source and source.upper().startswith(SIMULATED_PREFIX):
        return "demo"
    now = now or datetime.now(timezone.utc)
    age_h = max(0.0, (now - _aware(ts)).total_seconds() / 3600.0)
    if age_h <= 6:
        return "live"
    if age_h <= 48:
        return "recent"
    return "cached"


def _values_for(obs: list, column: str) -> list:
    return [getattr(o, column) for o in obs]


def _agreement_degree(variable: str, diff: float | None) -> str:
    """HIGH / MODERATE / LOW DISAGREEMENT, thresholds from the variable registry."""
    if diff is None:
        return "unknown"
    meta = VARIABLES[variable]
    a = abs(diff)
    if a >= meta["high"]:
        return "high"
    if a >= meta["moderate"]:
        return "moderate"
    return "low"


def _band(status: str, diff: float | None, variable: str) -> str:
    """Green/Yellow/Orange/Red band for the disagreement globe layer."""
    if status == "unknown":
        return "unknown"
    meta = VARIABLES[variable]
    if status == "high":
        return "red"
    if status == "moderate":
        return "orange" if abs(diff or 0.0) >= meta["moderate"] * 1.5 else "yellow"
    if status == "low":
        # close agreement vs tight agreement
        return "green" if abs(diff or 0.0) < meta["moderate"] * 0.25 else "yellow"
    return "unknown"


def _model_value(variable: str, obs: list) -> tuple[float | None, str]:
    """
    Numerical-model estimate = history-conditioned normal (mean of all
    observations except the very latest), the same explainable statistical
    model used by the Model Validation engine.
    """
    meta = VARIABLES[variable]
    values = _values_for(obs, meta["column"])
    model = _baseline(values)
    if model is None:
        return None, "Not enough history to form a model estimate."
    return round(float(model), 3), None


def _observation_value(variable: str, obs: list) -> tuple[float | None, str | None]:
    meta = VARIABLES[variable]
    values = [v for v in _values_for(obs, meta["column"]) if v is not None]
    if not values:
        return None, "No in-situ observation available for this variable."
    return round(float(values[-1]), 3), None


def _percent_diff(model: float | None, observed: float | None) -> float | None:
    if model is None or observed is None or model == 0:
        return None
    return round((observed - model) / abs(model) * 100.0, 2)


def compare(
    db: Session,
    loc: OceanLocation,
    variable: str = "temperature",
    depth_m: float = 0.0,
    window: int = 96,
) -> dict:
    """
    Full model-vs-observation comparison for one location + variable.

    Returns a dict suitable for serialisation by the twin router. Every
    value is derived from database rows; nothing is randomised.
    """
    meta = VARIABLES.get(variable)
    if meta is None:
        return {"error": f"Unknown variable '{variable}'", "data_status": "unavailable"}
    role = meta.get("role", "observation")
    obs = _latest_rows(db, loc, window=window)
    ll = _loc_latlon(loc)
    now = datetime.now(timezone.utc)

    observed, obs_note = _observation_value(variable, obs)
    model, model_note = _model_value(variable, obs)

    if not obs:
        return {
            "location_id": loc.id,
            "location": loc.name,
            **ll,
            "variable": variable,
            "label": meta["label"],
            "unit": meta["unit"],
            "depth_m": depth_m,
            "model": None,
            "observed": None,
            "difference": None,
            "percent_difference": None,
            "status": "no data",
            "severity": "none",
            "data_status": "unavailable",
            "note": "No observations exist for this location yet.",
            "model_note": "n/a",
            "observation_note": "n/a",
        }

    latest = _aware(obs[-1].timestamp)
    observation_time = latest.isoformat()
    model_time = latest.isoformat()
    observation_source = obs[-1].source or "unknown"
    ds = data_status_for(observation_source, latest)

    diff = round(observed - model, 3) if (observed is not None and model is not None) else None
    pct = _percent_diff(model, observed)
    status = _agreement_degree(variable, diff)
    band = _band(status, diff, variable)

    freshness_h = max(0.0, (now - latest).total_seconds() / 3600.0)

    confidence = conf.compare_confidence(
        variable=variable,
        values=_values_for(obs, meta["column"]),
        model_value=model,
        observed_value=observed,
        source=observation_source,
        freshness_h=freshness_h,
        temporal_gap_h=0.0,
        co_located=True,
        obs_count=len(obs),
        window=window,
    )

    severity = (
        "high" if status == "high"
        else "medium" if status == "moderate"
        else "low" if status == "low"
        else "none"
    )

    if role == "unavailable" and observed is None:
        return {
            "location_id": loc.id,
            "location": loc.name,
            **ll,
            "variable": variable,
            "label": meta["label"],
            "unit": meta["unit"],
            "depth_m": depth_m,
            "model": None,
            "observed": None,
            "difference": None,
            "percent_difference": None,
            "status": "no data",
            "severity": "none",
            "band": "unknown",
            "data_status": "unavailable",
            "note": (
                f"{meta['label']} has no in-situ data stream connected yet. "
                "Reported as Data unavailable rather than fabricated."
            ),
            "model_note": "n/a",
            "observation_note": obs_note,
        }

    return {
        "location_id": loc.id,
        "location": loc.name,
        **ll,
        "variable": variable,
        "label": meta["label"],
        "unit": meta["unit"],
        "depth_m": depth_m,
        "model": model,
        "observed": observed,
        "difference": diff,
        "percent_difference": pct,
        "status": status,
        "band": band,
        "severity": severity,
        "data_status": ds,
        "observation_time": observation_time,
        "model_time": model_time,
        "observation_source": observation_source,
        "temporal_distance_h": round(0.0, 2),
        "spatial_distance_km": round(0.0, 2),
        "spatial_note": "co-located: observed and model grid refer to the same station point.",
        "confidence": confidence[0],
        "confidence_level": confidence[1],
        "confidence_factors": confidence[2],
        "confidence_reasons": confidence[3],
        "model_note": model_note,
        "observation_note": obs_note,
        "note": "Model estimate = history-conditioned normal; observed = latest in-situ reading.",
    }


def disagreement_map(
    db: Session,
    variable: str = "temperature",
    depth_m: float = 0.0,
    threshold: float | None = None,
) -> dict:
    """
    Spatial model-observation disagreement for every location, used to
    colour the 3D globe layer (green = agree, yellow = small,
    orange = moderate, red = large). ``threshold`` scales the moderate
    band (user-adjustable).
    """
    locations = db.query(OceanLocation).all()
    points = []
    for loc in locations:
        res = compare(db, loc, variable=variable, depth_m=depth_m)
        if res.get("status") == "no data":
            band = "unknown"
        else:
            band = res.get("band", "unknown")
            if threshold is not None and res.get("difference") is not None:
                meta = VARIABLES[variable]
                a = abs(res["difference"])
                if a < meta["moderate"] * threshold:
                    band = "green"
                elif a >= meta["high"]:
                    band = "red"
                elif a >= meta["moderate"] * threshold * 1.5:
                    band = "orange"
                else:
                    band = "yellow"
        points.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "latitude": res.get("latitude"),
                "longitude": res.get("longitude"),
                "variable": variable,
                "model": res.get("model"),
                "observed": res.get("observed"),
                "difference": res.get("difference"),
                "percent_difference": res.get("percent_difference"),
                "status": res.get("status"),
                "severity": res.get("severity"),
                "band": band,
                "confidence": res.get("confidence"),
                "confidence_level": res.get("confidence_level"),
                "data_status": res.get("data_status"),
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "variable": variable,
        "depth_m": depth_m,
        "threshold": threshold,
        "points": points,
    }