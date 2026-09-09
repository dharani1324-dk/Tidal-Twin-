"""OceanVerse AI - Safety & Advisory API"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.safety.advisory import (
    merged_timeseries,
    model_trust,
    safety_advisory,
    storm_track,
)

router = APIRouter(prefix="/api/v1/safety", tags=["Safety & Advisory"])


@router.get("/advisory")
def advisory(db: Session = Depends(get_db)) -> dict:
    return {
        "regions": safety_advisory(db),
    }


@router.get("/storm")
def storm() -> dict:
    return storm_track()


@router.get("/trust")
def trust(db: Session = Depends(get_db)) -> dict:
    return model_trust(db)


@router.get("/timeseries")
def timeseries(db: Session = Depends(get_db)) -> dict:
    from datetime import datetime, timezone

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regions": merged_timeseries(db),
    }