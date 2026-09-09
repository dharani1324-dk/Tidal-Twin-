"""
OceanVerse AI - Ocean Data API Router
=====================================
Endpoints that expose ocean locations and observations to the frontend.
"""

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.schemas.ocean import OceanLocationOut, ObservationOut

router = APIRouter(prefix="/api/v1/ocean", tags=["Ocean"])


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
def list_observations(location_id: int, db: Session = Depends(get_db)):
    """
    Returns the observation readings for a given location.
    """
    location = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    observations = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == location_id)
        .order_by(OceanObservation.timestamp.desc())
        .all()
    )
    return observations
