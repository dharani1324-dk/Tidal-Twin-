"""
TidalTwin - Real Ocean-Model 3D Grid API Router
==================================================
Serves the REAL ocean-model 3D fields (temperature / salinity / current speed)
ingested into `netcdf_readings` from scripts.fetch_model + scripts.ingest_netcdf.
This is features #3 (real ocean model dataset), #5 (salinity field), #6 (3D
fields) and #7 (horizontal depth slices).

Honest by construction: a request returns `available: false` (with a reason)
until the real model file has been fetched and ingested; a depth slice returns
`available: false` when the latest model month has no cells at that depth. No
interpolation, no fabrication.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai import modelgrid

router = APIRouter(prefix="/api/v1/modelgrid", tags=["Ocean model grid"])


@router.get("/summary")
def modelgrid_summary(db: Session = Depends(get_db)):
    """Overview of the real ocean-model 3D fields: latest month and the
    available horizontal depth slices (with cell counts) per variable."""
    return {
        "available_fields": {
            var: modelgrid.summary(db, var)
            for var in sorted(modelgrid.GRID_SOURCES)
        }
    }


@router.get("/latest")
def modelgrid_latest(
    variable: str = Query(..., description="temperature | salinity | current_speed"),
    depth_m: float = Query(0.0, ge=0, le=10000),
    db: Session = Depends(get_db),
):
    """One horizontal depth slice of the latest model month. `available: false`
    (with a plain-language reason) until a real grid / that depth level exists."""
    if variable not in modelgrid.GRID_SOURCES:
        return {"available": False, "variable": variable,
                "reason": f"Unknown variable {variable!r}; use one of {sorted(modelgrid.GRID_SOURCES)}."}
    g = modelgrid.grid_at(db, variable, depth_m)
    if not g["available"]:
        return {k: g[k] for k in ("available", "variable", "month", "reason") if k in g}
    return {
        "available": True,
        "variable": variable,
        "month": g["month"],
        "unit": g["unit"],
        "source": g["source"],
        "depth_m": g["depth_m"],
        "depths": g["depths"],
        "rows": g["rows"],
        "cells": [{"latitude": la, "longitude": lo, "value": val} for la, lo, val in g["cells"]],
    }


@router.get("/vectors")
def modelgrid_vectors(
    depth_m: float = Query(0.0, ge=0, le=10000),
    db: Session = Depends(get_db),
):
    """True current velocity vectors for one depth slice of the latest model
    month: a real (u, v) pair per cell (feature #14). `available: false` (with
    a plain reason) until a real grid with both components is ingested."""
    g = modelgrid.vectors_at(db, depth_m)
    if not g["available"]:
        return {k: g[k] for k in ("available", "variable", "month", "reason") if k in g}
    return {
        "available": True,
        "variable": g["variable"],
        "month": g["month"],
        "unit": g["unit"],
        "source": g["source"],
        "depth_m": g["depth_m"],
        "depths": g["depths"],
        "rows": g["rows"],
        "cells": g["cells"],
    }


@router.get("/profile")
def modelgrid_profile(
    variable: str = Query(..., description="temperature | salinity | current_speed"),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    max_dist_deg: float | None = Query(None, ge=0.1, le=30),
    db: Session = Depends(get_db),
):
    """The variable's vertical profile at the nearest real model cell to a point
    (all depth levels of the latest month). `found: false` + reason when too far
    from any cell or before any grid is ingested."""
    if variable not in modelgrid.GRID_SOURCES:
        return {"found": False, "variable": variable,
                "reason": f"Unknown variable {variable!r}; use one of {sorted(modelgrid.GRID_SOURCES)}."}
    p = modelgrid.profile_at(db, variable, latitude, longitude, max_dist_deg)
    if not p["found"]:
        return {k: p[k] for k in ("found", "variable", "month", "reason") if k in p}
    return {
        "found": True,
        "variable": variable,
        "month": p["month"],
        "latitude": p["latitude"],
        "longitude": p["longitude"],
        "distance_deg": p["distance_deg"],
        "unit": p["unit"],
        "source": p["source"],
        "levels": p["levels"],
    }