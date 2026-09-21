"""
TidalTwin - Satellite Chlorophyll API Router
==============================================
Thin router over `app.modules.ai.realdata` serving the real satellite
ocean-colour chlorophyll-a grid ingested into `netcdf_readings`. The source
product is NOAA CoastWatch Geo-Polar Blended VIIRS-Himawari-NPP daily (5 km)
ocean-colour, averaged to a monthly mean over the Indian-Ocean region by
scripts.fetch_chlor (variable `chlor_a`).

Honest by construction: we return exactly the ingested satellite cells, never
an interpolated guess. Until the real .nc is fetched and ingested, the
endpoints report `available: false` (respectively `found: false`) so the UI
cannot present fake ocean colour.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.realdata import default_max_dist, latest_grid, near

router = APIRouter(prefix="/api/v1/chlor", tags=["Chlorophyll"])

VARIABLE = "chlor_a"


@router.get("/latest")
def chlor_latest(db: Session = Depends(get_db)):
    """Most recent satellite Chl month available: every ingested cell's real
    chlor_a value, plus a coverage summary and the min/max range for the
    colour scale. Nothing is simulated."""
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
        "samples": [{"latitude": la, "longitude": lo, "chlor_a": val} for la, lo, val in g["samples"]],
    }


@router.get("/near")
def chlor_near(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    max_dist_deg: float = Query(default_max_dist(VARIABLE), ge=0.01, le=5),
    db: Session = Depends(get_db),
):
    """Nearest real satellite Chl cell to a point. `found: false` when the
    closest cell is farther than `max_dist_deg` — the UI then shows
    "Data unavailable", never a fabricated value."""
    hit = near(db, VARIABLE, latitude, longitude, max_dist_deg)
    if not hit["found"]:
        return {"found": False, "month": hit["month"], "reason": hit["reason"]}
    return {
        "found": True,
        "month": hit["month"],
        "latitude": hit["latitude"],
        "longitude": hit["longitude"],
        "chlor_a": hit["value"],
        "distance_deg": hit["distance_deg"],
        "source": hit["source"],
    }