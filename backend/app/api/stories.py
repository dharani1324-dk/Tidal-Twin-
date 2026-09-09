"""
OceanVerse AI - Story Mode & Comparison API
===========================================
Endpoints for guided narratives and AI forecast-vs-reality comparison.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import OceanLocation
from app.modules.ai.stories import all_stories
from app.modules.ai.comparison.comparator import compare_location, compare_all

router = APIRouter(prefix="/api/v1", tags=["Stories & Comparison"])


@router.get("/stories")
def get_stories(db: Session = Depends(get_db)):
    """Return all interactive ocean stories with live data hooks."""
    return {"stories": all_stories(db)}


@router.get("/comparison")
def get_comparison(db: Session = Depends(get_db)):
    """Forecast-vs-reality for every location."""
    return {"comparisons": compare_all(db)}


@router.get("/comparison/{location_id}")
def get_comparison_one(location_id: int, db: Session = Depends(get_db)):
    """Forecast-vs-reality for a single location."""
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    return compare_location(db, loc)