"""
TidalTwin - ERSST API Router
==============================
Thin router over `app.modules.ai.realdata` serving the real NOAA ERSST v5
sea-surface temperature already ingested into `netcdf_readings` (features
#1/#2). Honest by construction: ERSST v5 is a 2-degree monthly gridded
analysis built from in-situ ship/buoy observations - NOT a live feed and NOT
a satellite product. We return exactly what was ingested, never an
interpolated guess.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.realdata import default_max_dist, latest_grid, near

router = APIRouter(prefix="/api/v1/ersst", tags=["ERSST"])

VARIABLE = "sst"


@router.get("/latest")
def ersst_latest(db: Session = Depends(get_db)):
    """The most recent ERSST month available: every grid cell with a real SST
    value, plus a coverage summary and the min/max range for the colour scale.
    Nothing is simulated or interpolated here."""
    g = latest_grid(db, VARIABLE)
    if not g["available"]:
        return {"available": False, "error": g["error"]}
    return {
        "available": True,
        "time": g["time"],
        "months": g["months"],
        "resolution_deg": g["resolution_deg"],
        "source": g["source"],
        "rows": g["rows"],
        "stats": g["stats"],
        "samples": [{"latitude": la, "longitude": lo, "sst": val} for la, lo, val in g["samples"]],
    }


@router.get("/near")
def ersst_near(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    max_dist_deg: float = Query(default_max_dist(VARIABLE), ge=0.1, le=30),
    db: Session = Depends(get_db),
):
    """Nearest real ERSST grid cell to a point. `found: false` (and the caller
    should show "Data unavailable") when the closest cell is farther than
    `max_dist_deg` — e.g. coastal cells where the 2-degree grid has no sea."""
    hit = near(db, VARIABLE, latitude, longitude, max_dist_deg)
    if not hit["found"]:
        return {"found": False, "month": hit["month"], "reason": hit["reason"]}
    return {
        "found": True,
        "month": hit["month"],
        "latitude": hit["latitude"],
        "longitude": hit["longitude"],
        "sst": hit["value"],
        "distance_deg": hit["distance_deg"],
        "source": hit["source"],
    }