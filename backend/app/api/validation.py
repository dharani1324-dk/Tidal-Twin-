"""OceanVerse AI - Model Validation & Confidence API"""

from pydantic import BaseModel

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.validation.engine import (
    classify_events,
    difference_engine,
    model_skill,
    observation_confidence,
    provenance,
    scenario_projection,
    situation_panel,
)

router = APIRouter(prefix="/api/v1/validation", tags=["Model Validation"])


class ScenarioRequest(BaseModel):
    location_id: int
    wind_percent: float = 0.0


@router.get("/confidence")
def confidence(db: Session = Depends(get_db)) -> dict:
    """Per-coast observation confidence + model agreement (component scores)."""
    return observation_confidence(db)


@router.get("/difference")
def difference(location_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    """MODEL | OBSERVED | DEVIATION fields + interpretation per coast."""
    return difference_engine(db, location_id)


@router.get("/situation")
def situation(db: Session = Depends(get_db)) -> dict:
    """Operational situation panel (command-center strip)."""
    return situation_panel(db)


@router.get("/skill")
def skill(db: Session = Depends(get_db)) -> dict:
    """Model skill score: MAE / RMSE / bias / skill-vs-climatology per variable."""
    return model_skill(db)


@router.get("/events")
def events(db: Session = Depends(get_db)) -> dict:
    """Classified ocean events (heatwave, cold anomaly, flood risk, mismatch...)."""
    return classify_events(db)


@router.get("/provenance")
def provenance_endpoint(db: Session = Depends(get_db)) -> dict:
    """Scientific traceability: source, dataset, time, processing, model run."""
    return provenance(db)


@router.post("/scenario")
def scenario(req: ScenarioRequest, db: Session = Depends(get_db)) -> dict:
    """Illustrative what-if projection (labelled simulation, not a forecast)."""
    return scenario_projection(db, req.location_id, req.wind_percent)