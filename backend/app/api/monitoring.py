"""
TidalTwin - Monitoring API
==============================
Endpoints for AI anomaly detection, alerts feed, and forecasting.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import OceanAlert
from app.modules.ai.anomaly.detector import (
    scan_all_locations,
    resolve_stale_alerts,
)
from app.modules.ai.forecast.forecaster import forecast_all

router = APIRouter(prefix="/api/v1/monitoring", tags=["Monitoring"])


@router.get("/alerts")
def get_alerts(status: str = "all", limit: int = 50, db: Session = Depends(get_db)):
    """
    List alerts. `status` can be all | active | resolved.
    """
    q = db.query(OceanAlert).order_by(OceanAlert.created_at.desc())
    if status in ("active", "resolved"):
        q = q.filter(OceanAlert.status == status)
    alerts = q.limit(limit).all()

    return [
        {
            "id": a.id,
            "location_id": a.location_id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "description": a.description,
            "confidence": a.confidence,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "location_name": a.location.name if a.location else None,
        }
        for a in alerts
    ]


@router.post("/scan")
def run_scan(db: Session = Depends(get_db)):
    """
    Run the AI anomaly-detection radar across all regions,
    then resolve any stale alerts.
    """
    scan = scan_all_locations(db)
    resolved = resolve_stale_alerts(db)
    return {
        "scan": scan,
        "alerts_resolved": resolved,
        "ran_at": datetime.utcnow().isoformat(),
    }


@router.get("/forecast")
def get_forecast(db: Session = Depends(get_db)):
    """AI forecast for the next 12 hours across all regions."""
    return {"forecasts": forecast_all(db)}