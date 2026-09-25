"""
TidalTwin - Model vs Observation Depth Profile Comparison
==============================================================
Interactive profile comparison: for a selected location and variable,
returns a model column (physics-based sub-surface profile, depth_profiles
module) and an observed column. Row-by-row data_status keeps the
comparison honest:

    * a qualifying measured surface value is the only observation.
    * deeper levels are illustrative model-derived profile values.
    * no profile is generated if no eligible surface measurement is available.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.twin.compare import data_status_for, _loc_latlon
from app.modules.ai.validation.engine import OBS_WINDOW, _latest_rows
from app.modules.physics.ocean_profiles import depth_profile

# Depth levels sampled for the comparison profile.
DEPTH_LEVELS = [0, 10, 25, 50, 100, 150, 200, 300, 500]

PROFILE_VARIABLES = {
    "temperature": {"key": "temperature", "label": "Sea temperature", "unit": "\u00b0C", "threshold": 1.0},
    "salinity": {"key": "salinity", "label": "Salinity", "unit": "PSU", "threshold": 0.5},
}


def profile(db: Session, loc: OceanLocation, variable: str = "temperature") -> dict:
    """Return a measured surface value and clearly labelled illustrative physics profile."""
    from app.modules.ai.provenance_quality import origin_status

    meta = PROFILE_VARIABLES.get(variable, {"key": variable, "label": variable, "unit": "value", "threshold": 1.0})
    obs = _latest_rows(db, loc, window=OBS_WINDOW)
    forecast = db.query(OceanObservation).filter(
        OceanObservation.location_id == loc.id,
        OceanObservation.source.like("%Open-Meteo%"),
    ).first() is not None
    column = "sea_surface_temperature" if variable == "temperature" else "salinity"
    eligible = [row for row in obs if getattr(row, column, None) is not None]
    if not eligible:
        return {
            "location_id": loc.id, "location": loc.name, **_loc_latlon(loc),
            "variable": variable, "label": meta["label"], "unit": meta["unit"],
            "depths": [], "rows": [], "surface_observed": None, "surface_source": None,
            "surface_data_status": "unavailable", "available": False,
            "data_status": "MODEL_DERIVED" if forecast else "UNKNOWN",
            "model_note": "No measured surface input is available, so no depth profile was generated.",
            "observation_note": "A forecast is not used as an in-situ profile measurement.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    latest = eligible[-1]
    surface = float(getattr(latest, column))
    wave = float(latest.wave_height) if latest.wave_height is not None else None
    phys = depth_profile(loc, surface_temp=surface if variable == "temperature" else None,
                         salinity=surface if variable == "salinity" else None,
                         wave=wave, current=None)
    series = phys.get(meta["key"], []) or phys.get("temperature", [])
    by_depth = {d: float(v) for d, v in zip(phys.get("depths", []), series) if v is not None}
    rows = []
    for depth in DEPTH_LEVELS:
        model_val = by_depth.get(depth)
        if model_val is None:
            continue
        measured_val = round(surface, 2) if depth == 0 else None
        rows.append({
            "depth_m": float(depth), "model": round(model_val, 2),
            "observed": measured_val,
            "difference": round(measured_val - model_val, 2) if measured_val is not None else None,
            "disagreement": abs(measured_val - model_val) >= meta["threshold"] if measured_val is not None else None,
            "data_status": "measured" if depth == 0 else "MODEL_DERIVED",
        })
    return {
        "location_id": loc.id, "location": loc.name, **_loc_latlon(loc),
        "variable": variable, "label": meta["label"], "unit": meta["unit"],
        "depths": [row["depth_m"] for row in rows], "rows": rows,
        "surface_observed": round(surface, 2), "surface_source": latest.source,
        "surface_data_status": origin_status(latest.source, latest.data_type),
        "available": True, "data_status": origin_status(latest.source, latest.data_type),
        "model_note": "Illustrative physics-derived water-column profile initialized from one measured surface value; not an independently validated forecast.",
        "observation_note": "Only the surface point is measured. Deeper profile values are model-derived and are not observations.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
