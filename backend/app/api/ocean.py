"""
TidalTwin - Ocean Data API Router
=====================================
Endpoints that expose ocean locations and observations to the frontend.
"""

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.provenance_quality import assess_record, origin_status
from app.schemas.ocean import OceanLocationOut, ObservationOut

router = APIRouter(prefix="/api/v1/ocean", tags=["Ocean"])


@router.post("/refresh")
def refresh_ocean_data(db: Session = Depends(get_db)):
    """
    Fetch Open-Meteo marine forecasts for all locations and store them
    separately from direct measurements. Called by the frontend or a schedule.
    """
    from app.services.ocean_data import refresh_all_locations

    summary = refresh_all_locations(db, forecast_days=2)
    return {"status": "refreshed", "details": summary}


@router.post("/hydrate-real-observations")
def hydrate_real_in_situ(db: Session = Depends(get_db)):
    """
    Rebuild the REAL in-situ observation stream from the real Argo GDAC
    profiles on record (nearest measured float per basin, distance disclosed).
    Forecast rows are never rewritten; this only manages REAL measurements.
    """
    from app.services.hydrate_real_observations import hydrate_real_observations

    return hydrate_real_observations(db)


@router.get("/locations", response_model=list[OceanLocationOut])
def list_locations(db: Session = Depends(get_db)):
    """
    Returns all ocean locations (regions) in the database,
    including their center coordinates.
    """
    locations = db.query(OceanLocation).all()
    result = []
    for loc in locations:
        lat = lon = None
        if loc.geom is not None:
            # Convert PostGIS geometry to a simple point (center)
            geom = to_shape(loc.geom)
            lon, lat = geom.centroid.x, geom.centroid.y
        result.append(
            OceanLocationOut(
                id=loc.id,
                name=loc.name,
                region_type=loc.region_type,
                country=loc.country,
                latitude=lat,
                longitude=lon,
                created_at=loc.created_at,
            )
        )
    return result


@router.get("/locations/{location_id}/observations", response_model=list[ObservationOut])
def list_observations(
    location_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Returns the latest mixed-source time-series records for a location. Each row carries an evidence class; forecast rows are not observations.
    `limit` controls how many records to return (default 50).
    """
    location = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    observations = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == location_id)
        .order_by(OceanObservation.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "location_id": row.location_id,
            "timestamp": row.timestamp,
            "sea_surface_temperature": row.sea_surface_temperature,
            "wave_height": row.wave_height,
            "salinity": row.salinity,
            "current_speed": row.current_speed,
            "source": row.source,
            "data_type": row.data_type,
            "provenance_status": origin_status(row.source, row.data_type),
            "quality": assess_record(row, location),
        }
        for row in observations
    ]
