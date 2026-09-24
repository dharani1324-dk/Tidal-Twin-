"""
TidalTwin - Argo API Router
===============================
Exposes real Argo float data to the frontend: the list of floats we have
profiles for, and the vertical temperature/salinity profile of each float.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.argo import ArgoProfile
from app.schemas.argo import ArgoFloatOut, ArgoProfileOut, ArgoProfileLevel

router = APIRouter(prefix="/api/v1/argo", tags=["Argo"])


@router.get("/floats", response_model=dict)
def list_floats(db: Session = Depends(get_db)):
    """
    Real Argo floats in the database, each with its latest known position,
    profile time and depth coverage.
    """
    floats: list[ArgoFloatOut] = []
    rows = (
        db.query(
            ArgoProfile.float_id,
            func.count(ArgoProfile.id).label("levels"),
            func.max(ArgoProfile.time).label("latest_time"),
            func.min(ArgoProfile.depth_m).label("depth_min"),
            func.max(ArgoProfile.depth_m).label("depth_max"),
        )
        .group_by(ArgoProfile.float_id)
        .order_by(ArgoProfile.float_id)
        .all()
    )
    for float_id, levels, latest_time, depth_min, depth_max in rows:
        pos = (
            db.query(ArgoProfile.latitude, ArgoProfile.longitude)
            .filter(ArgoProfile.float_id == float_id, ArgoProfile.time == latest_time)
            .limit(1)
            .first()
        )
        floats.append(
            ArgoFloatOut(
                float_id=float_id,
                latest_time=latest_time,
                latitude=pos[0] if pos else None,
                longitude=pos[1] if pos else None,
                depth_min_m=depth_min,
                depth_max_m=depth_max,
                levels=levels,
            )
        )
    return {"count": len(floats), "floats": floats}


@router.get("/floats/{float_id}/profile", response_model=ArgoProfileOut)
def float_profile(float_id: str, db: Session = Depends(get_db)):
    """
    The most recent vertical profile of one float: temperature & salinity
    vs depth (one level per point).  NULL fields mean the value wasn't
    present in the source data — the frontend shows "Data unavailable".
    """
    latest_time = (
        db.query(func.max(ArgoProfile.time))
        .filter(ArgoProfile.float_id == float_id)
        .scalar()
    )
    if latest_time is None:
        raise HTTPException(status_code=404, detail="Argo float not found")

    levels = (
        db.query(ArgoProfile)
        .filter(ArgoProfile.float_id == float_id, ArgoProfile.time == latest_time)
        .order_by(ArgoProfile.depth_m.asc())
        .all()
    )
    first = levels[0]
    return ArgoProfileOut(
        float_id=first.float_id,
        time=first.time,
        latitude=first.latitude,
        longitude=first.longitude,
        levels=[
            ArgoProfileLevel(
                depth_m=r.depth_m,
                temperature=r.temperature,
                salinity=r.salinity,
                pressure=r.pressure,
            )
            for r in levels
        ],
    )