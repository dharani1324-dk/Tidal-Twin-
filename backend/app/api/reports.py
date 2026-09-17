"""
TidalTwin - Reports API
============================
Endpoints for the National Ocean Risk Index, the auto-generated executive
summary, and downloadable CSV exports.
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.observation import OceanObservation
from app.modules.ai.reports.risk import (
    compute_risk_index,
    build_executive_summary,
)

router = APIRouter(prefix="/api/v1/reports", tags=["Reports & Risk"])


@router.get("/index")
def get_risk_index(db: Session = Depends(get_db)):
    """National Ocean Risk Index - composite ranking of all regions."""
    return compute_risk_index(db)


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """Auto-generated executive summary in plain language."""
    return {
        "generated_at": datetime.now().isoformat(),
        "summary": build_executive_summary(db),
        "index": compute_risk_index(db),
    }


@router.get("/csv")
def download_csv(db: Session = Depends(get_db)):
    """Download all observations as a CSV report."""
    obs = (
        db.query(OceanObservation)
        .order_by(OceanObservation.timestamp.asc())
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp", "location_id", "location_name",
        "sea_surface_temperature_c", "wave_height_m", "wave_direction_deg",
        "source",
    ])
    for o in obs:
        writer.writerow([
            o.timestamp.isoformat(),
            o.location_id,
            o.location.name if o.location else "",
            o.sea_surface_temperature,
            o.wave_height,
            o.wave_direction,
            o.source,
        ])

    buf.seek(0)
    filename = f"tidaltwin_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )