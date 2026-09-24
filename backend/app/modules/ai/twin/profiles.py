"""
TidalTwin - Model vs Observation Depth Profile Comparison
==============================================================
Interactive profile comparison: for a selected location and variable,
returns a model column (physics-based sub-surface profile, depth_profiles
module) and an observed column. Row-by-row data_status keeps the
comparison honest:

    * depth 0 uses the REAL latest in-situ surface observation.
    * deeper levels are physics-derived climatology profiles and are
      labelled ``derived`` (no in-situ profiler connected yet).
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
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
    """
    Build a model-vs-observation depth profile for one location.

    Returns ``{location_id, location, variable, label, unit, depths,
    rows: [{depth_m, model, observed, difference, disagreement,
    data_status}], surface_observed, surface_source}``.
    """
    meta = PROFILE_VARIABLES.get(variable)
    if meta is None:
        # Fall back to any variable the physics engine emits
        meta = {"key": variable, "label": variable, "unit": "value", "threshold": 1.0}

    obs = _latest_rows(db, loc, window=OBS_WINDOW)
    temps = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
    waves = [o.wave_height for o in obs if o.wave_height is not None]
    surface_t = temps[-1] if temps else 28.0
    surface_w = waves[-1] if waves else 1.0

    surf_src = obs[-1].source if obs else None
    surf_ts = obs[-1].timestamp if obs else None
    surf_status = data_status_for(surf_src or "", surf_ts)

    phys = depth_profile(
        loc,
        surface_temp=float(surface_t or 28.0),
        salinity=None,
        wave=float(surface_w or 1.0),
        current=None,
    )
    model_depths = phys.get("depths", [])
    model_series = phys.get(meta["key"], []) or phys.get("temperature", [])

    by_depth = {}
    for d, mv in zip(model_depths, model_series):
        if mv is None:
            continue
        by_depth[d] = float(mv)

    # Observed column: use the real surface value at 0 m; deeper levels are
    # physics-derived (clearly labelled) because no profiler feeds them yet.
    rows = []
    for d in DEPTH_LEVELS:
        model_val = by_depth.get(d)
        if model_val is None:
            continue
        observed_val = round(float(surface_t), 2) if d == 0 else round(model_val, 2)
        diff = round(observed_val - model_val, 2)
        disagree = abs(diff) >= meta["threshold"]
        rows.append(
            {
                "depth_m": float(d),
                "model": round(model_val, 2),
                "observed": observed_val,
                "difference": diff,
                "disagreement": disagree,
                "data_status": surf_status if d == 0 else "derived",
            }
        )

    return {
        "location_id": loc.id,
        "location": loc.name,
        **(_loc_latlon(loc)),
        "variable": variable,
        "label": meta["label"],
        "unit": meta["unit"],
        "depths": [d for d in DEPTH_LEVELS],
        "rows": rows,
        "surface_observed": round(float(surface_t), 2),
        "surface_source": surf_src,
        "surface_data_status": surf_status,
        "model_note": "Physics-based sub-surface model profile (region climatology + surface state).",
        "observation_note": (
            "Surface level = real in-situ reading; deeper levels = physics-derived "
            "climatology (no profiling floater connected) - identified as derived."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }