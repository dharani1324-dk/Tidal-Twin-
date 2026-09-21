"""
TidalTwin - Glider API Router (features #16/#17)
====================================================
Exposes real glider deployment data to the frontend: the deployments we have
samples for, the physical transect (temperature/salinity vs depth along the
trajectory), and the biogeochemical (BGC) measurements — dissolved oxygen,
chlorophyll and nitrate — for deployments whose payload carried those sensors.

Honest by construction, like Argo: NULL means the sensor or sample genuinely
wasn't there in the real source file. Nothing is interpolated or simulated.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.glider import GliderProfile

router = APIRouter(prefix="/api/v1/glider", tags=["Glider"])

BGC_FIELDS = ("dissolved_oxygen", "chlorophyll", "nitrate")


def _deployment_row(db: Session, deployment_id: str) -> dict | None:
    """One deployment's headline info, or None if the deployment isn't ingested."""
    agg = (
        db.query(
            func.count(GliderProfile.id),
            func.max(GliderProfile.time),
            func.min(GliderProfile.time),
            func.min(GliderProfile.depth_m),
            func.max(GliderProfile.depth_m),
            func.min(GliderProfile.latitude),
            func.max(GliderProfile.latitude),
            func.min(GliderProfile.longitude),
            func.max(GliderProfile.longitude),
        )
        .filter(GliderProfile.deployment_id == deployment_id)
        .first()
    )
    if agg is None or agg[0] == 0:
        return None
    counts = {
        field: db.query(func.count(GliderProfile.id))
        .filter(GliderProfile.deployment_id == deployment_id,
                getattr(GliderProfile, field).isnot(None))
        .scalar() or 0
        for field in BGC_FIELDS
    }
    return {
        "deployment_id": deployment_id,
        "samples": agg[0],
        "time_start": agg[2],
        "time_end": agg[1],
        "depth_min_m": agg[3],
        "depth_max_m": agg[4],
        "lat_min": agg[5],
        "lat_max": agg[6],
        "lon_min": agg[7],
        "lon_max": agg[8],
        "bgc_samples": counts,
    }


@router.get("/deployments")
def list_deployments(db: Session = Depends(get_db)):
    """Every ingested real glider deployment with its time/depth/position extent
    and how many BGC samples it carried (0 = sensor not on the payload)."""
    ids = [row[0] for row in db.query(GliderProfile.deployment_id).distinct().order_by(GliderProfile.deployment_id).all()]
    deployments = [_deployment_row(db, d) for d in ids]
    deployments = [d for d in deployments if d is not None]
    return {"count": len(deployments), "deployments": deployments}


@router.get("/{deployment_id}/samples")
def deployment_samples(
    deployment_id: str,
    limit: int = Query(2000, ge=1, le=20000),
    db: Session = Depends(get_db),
):
    """The deployment's real measurement transect (position/depth/time + the
    physical fields measured on board). NULL values = not present in the file."""
    info = _deployment_row(db, deployment_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Glider deployment not found")
    rows = (
        db.query(GliderProfile)
        .filter(GliderProfile.deployment_id == deployment_id)
        .order_by(GliderProfile.time.asc())
        .limit(limit)
        .all()
    )
    return {
        "deployment_id": deployment_id,
        "instrument": rows[0].instrument if rows else None,
        "unit_note": "temperature degC, salinity PSU, depth m, oxygen mol m-3, chlorophyll mg m-3, nitrate mmol m-3",
        "samples": [
            {
                "time": r.time.isoformat(),
                "latitude": r.latitude,
                "longitude": r.longitude,
                "depth_m": r.depth_m,
                "temperature": r.temperature,
                "salinity": r.salinity,
                "pressure": r.pressure,
            }
            for r in rows
        ],
    }


@router.get("/{deployment_id}/bgc")
def deployment_bgc(deployment_id: str, db: Session = Depends(get_db)):
    """The deployment's real biogeochemical measurements (feature #17). A field
    is 'n/a' when the sensor wasn't carried; NULL per-sample when QC-flagged."""
    info = _deployment_row(db, deployment_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Glider deployment not found")
    rows = (
        db.query(GliderProfile)
        .filter(GliderProfile.deployment_id == deployment_id,
                GliderProfile.dissolved_oxygen.isnot(None) | GliderProfile.chlorophyll.isnot(None) | GliderProfile.nitrate.isnot(None))
        .order_by(GliderProfile.time.asc())
        .all()
    )
    return {
        "deployment_id": deployment_id,
        "bgc_samples": info["bgc_samples"],
        "fields": {f: (info["bgc_samples"][f] > 0) for f in BGC_FIELDS},
        "unit_note": "oxygen mol m-3, chlorophyll mg m-3, nitrate mmol m-3",
        "samples": [
            {
                "time": r.time.isoformat(),
                "latitude": r.latitude,
                "longitude": r.longitude,
                "depth_m": r.depth_m,
                "dissolved_oxygen": r.dissolved_oxygen,
                "chlorophyll": r.chlorophyll,
                "nitrate": r.nitrate,
            }
            for r in rows
        ],
    }