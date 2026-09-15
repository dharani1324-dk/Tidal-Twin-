"""OceanVerse AI - Coastal Intelligence API.

Decision-support endpoints built on the coastal module bundle:
fisheries, coral bleaching, oil-spill/SAR drift, sea-level rise,
beach/rip-current safety and disaster-economics impact.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.coastal.fisheries import compute_fisheries
from app.modules.ai.coastal.coral import compute_coral
from app.modules.ai.coastal.spill import simulate_drift
from app.modules.ai.coastal.slr import slr_inundation
from app.modules.ai.coastal.beach import compute_beach_safety
from app.modules.ai.coastal.impact import compute_economic_impact

router = APIRouter(prefix="/api/v1/coastal", tags=["Coastal Intelligence"])


class DriftInput(BaseModel):
    scenario: str = "spill"                     # "spill" | "sar"
    location_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    duration_h: int = 24
    drift_factor: float = 1.0


@router.get("/fisheries")
def get_fisheries(db: Session = Depends(get_db)):
    return compute_fisheries(db)


@router.get("/coral")
def get_coral(db: Session = Depends(get_db)):
    return compute_coral(db)


@router.post("/spill")
def post_spill(payload: DriftInput, db: Session = Depends(get_db)):
    return simulate_drift(
        db,
        scenario=payload.scenario,
        location_id=payload.location_id,
        lat=payload.lat,
        lon=payload.lon,
        duration_h=payload.duration_h,
        drift_factor=payload.drift_factor,
    )


@router.get("/slr")
def get_slr(scenario: float = Query(1.0, ge=0.1, le=5.0),
            db: Session = Depends(get_db)):
    return slr_inundation(db, scenario)


@router.get("/beach")
def get_beach(db: Session = Depends(get_db)):
    return compute_beach_safety(db)


@router.get("/impact")
def get_impact(db: Session = Depends(get_db)):
    return compute_economic_impact(db)