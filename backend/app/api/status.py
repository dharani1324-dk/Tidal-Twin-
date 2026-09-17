"""
TidalTwin - API Router for System Status
============================================
Endpoints that tell us about the system health,
including the database connection.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/api/v1", tags=["System"])


@router.get("/db-status")
def db_status(db: Session = Depends(get_db)):
    """
    Checks that the database is reachable and PostGIS is active.
    Returns info useful for confirming the full stack works.
    """
    try:
        postgis_version = db.execute(
            text("SELECT postgis_version();")
        ).scalar()
        return {
            "database": "connected",
            "postgis": postgis_version,
            "service": "TidalTwin",
        }
    except Exception as e:  # pragma: no cover
        return {
            "database": "error",
            "detail": str(e),
            "service": "TidalTwin",
        }
