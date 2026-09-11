"""OceanVerse AI - Apex Intelligence API.

New feature endpoints: adaptive identification, carbon monitoring,
light pollution, remote-sensing fusion, and observation recommendations.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.apex.adaptive import adaptive_identification
from app.modules.ai.apex.carbon import carbon_monitoring
from app.modules.ai.apex.light import light_pollution
from app.modules.ai.apex.sensing import remote_sensing_fusion
from app.modules.ai.apex.recommend import build_recommendations

router = APIRouter(prefix="/api/v1/apex", tags=["Apex Intelligence"])


@router.get("/adaptive")
def get_adaptive(location_id: int | None = Query(None), db: Session = Depends(get_db)):
    return adaptive_identification(db, location_id)


@router.get("/carbon")
def get_carbon(db: Session = Depends(get_db)):
    return carbon_monitoring(db)


@router.get("/light-pollution")
def get_light_pollution(db: Session = Depends(get_db)):
    return light_pollution(db)


@router.get("/remote-sensing")
def get_remote_sensing(db: Session = Depends(get_db)):
    return remote_sensing_fusion(db)


@router.get("/recommendations")
def get_recommendations(min_priority: float = Query(30.0), db: Session = Depends(get_db)):
    return build_recommendations(db, min_priority)