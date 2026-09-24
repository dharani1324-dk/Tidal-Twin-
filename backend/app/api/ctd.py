"""
TidalTwin - CTD API Router (feature #17)
==========================================
Exposes real ship CTD / moored mini-CTD casts ingested by `scripts.ingest_ctd`:
the stations we have samples for, and one station's full measured depth profile
(temperature / salinity / pressure + optional BGC sensors).

Honest by construction, like the glider and Argo routers: NULL means the sensor
or sample genuinely wasn't there in the real source file. Nothing is
interpolated or simulated.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.ctd import CtdProfile

router = APIRouter(prefix="/api/v1/ctd", tags=["CTD casts"])

BGC_FIELDS = ("dissolved_oxygen", "chlorophyll", "nitrate")


def _station_row(db: Session, station_id: str) -> dict | None:
    """One station's headline info, or None if the station isn't ingested."""
    agg = (
        db.query(
            func.count(CtdProfile.id),
            func.max(CtdProfile.time),
            func.min(CtdProfile.time),
            func.min(CtdProfile.depth_m),
            func.max(CtdProfile.depth_m),
            func.min(CtdProfile.latitude),
            func.max(CtdProfile.latitude),
            func.min(CtdProfile.longitude),
            func.max(CtdProfile.longitude),
            func.max(CtdProfile.instrument).isnot(None),
        )
        .filter(CtdProfile.station_id == station_id)
        .first()
    )
    if agg is None or agg[0] == 0:
        return None
    counts = {
        field: db.query(func.count(CtdProfile.id))
        .filter(CtdProfile.station_id == station_id,
                getattr(CtdProfile, field).isnot(None))
        .scalar() or 0
        for field in BGC_FIELDS
    }
    return {
        "station_id": station_id,
        "samples": agg[0],
        "time_start": agg[2],
        "time_end": agg[1],
        "depth_min_m": agg[3],
        "depth_max_m": agg[4],
        "lat_min": agg[5],
        "lat_max": agg[6],
        "lon_min": agg[7],
        "lon_max": agg[8],
        "bgc_samples": counts,
    }


@router.get("/stations")
def list_stations(db: Session = Depends(get_db)):
    """Every ingested real CTD station with its time/depth/position extent and
    how many BGC samples it carried (0 = sensor not on the payload)."""
    ids = [row[0] for row in db.query(CtdProfile.station_id).distinct().order_by(CtdProfile.station_id).all()]
    stations = [_station_row(db, s) for s in ids]
    stations = [s for s in stations if s is not None]
    return {"count": len(stations), "stations": stations}


@router.get("/{station_id}/profile")
def station_profile(
    station_id: str,
    limit: int = Query(1000, ge=1, le=20000),
    db: Session = Depends(get_db),
):
    """The station's real CTD profile (depth/time + measured fields). NULL values
    = not present in the file."""
    info = _station_row(db, station_id)
    if info is None:
        raise HTTPException(status_code=404, detail="CTD station not found")
    rows = (
        db.query(CtdProfile)
        .filter(CtdProfile.station_id == station_id)
        .order_by(CtdProfile.depth_m.asc())
        .limit(limit)
        .all()
    )
    return {
        "station_id": station_id,
        "instrument": rows[0].instrument if rows else None,
        "unit_note": "temperature degC, salinity PSU, depth m, oxygen mol m-3, chlorophyll mg m-3, nitrate mmol m-3",
        "samples": [
            {
                "time": r.time.isoformat(),
                "latitude": r.latitude,
                "longitude": r.longitude,
                "depth_m": r.depth_m,
                "temperature": r.temperature,
                "salinity": r.salinity,
                "pressure": r.pressure,
            }
            for r in rows if r.temperature is not None or r.salinity is not None
        ],
        "bgc_samples": [
            {
                "time": r.time.isoformat(),
                "depth_m": r.depth_m,
                "dissolved_oxygen": r.dissolved_oxygen,
                "chlorophyll": r.chlorophyll,
                "nitrate": r.nitrate,
            }
            for r in rows if r.dissolved_oxygen is not None or r.chlorophyll is not None or r.nitrate is not None
        ],
    }