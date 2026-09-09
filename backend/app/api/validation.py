"""OceanVerse AI - Model Validation & Confidence API"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.validation.engine import (
    difference_engine,
    observation_confidence,
    situation_panel,
)

router = APIRouter(prefix="/api/v1/validation", tags=["Model Validation"])


@router.get("/confidence")
def confidence(db: Session = Depends(get_db)) -> dict:
    """Per-coast observation confidence + model agreement."""
    return observation_confidence(db)


@router.get("/difference")
def difference(location_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    """MODEL | OBSERVED | DEVIATION fields + interpretation per coast."""
    return difference_engine(db, location_id)


@router.get("/situation")
def situation(db: Session = Depends(get_db)) -> dict:
    """Operational situation panel (command-center strip)."""
    return situation_panel(db)