"""
TidalTwin - Ocean Acidification API
===================================
Endpoints for pH monitoring, acidification hotspot detection and projection.

Mirrors the deoxygenation router so the two modules present the same shape to
the frontend: overview / coverage / samples / hotspots / trends / forecast /
zones / sources / ingest / map-regions / alerts-refresh.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.ai.acidification import engine, sources

router = APIRouter(prefix="/api/v1/acidification", tags=["Acidification"])


class ProjectionInput(BaseModel):
    region_id: int = Field(..., description="Monitored region to project from")
    horizon_days: int = Field(180, ge=30, le=1095, description="Projection horizon")


@router.get("/overview")
def get_overview(
    radius_km: float = Query(250, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    return engine.cached_overview(db, radius_km)


@router.get("/coverage")
def get_coverage(db: Session = Depends(get_db)):
    return engine.coverage_report(db)


@router.get("/samples")
def get_samples(
    region_id: int | None = Query(None),
    min_severity: str | None = Query(None),
    is_acidic: bool | None = Query(None),
    is_undersaturated: bool | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    records = engine.load_records(
        db,
        region_id=region_id,
        min_severity=min_severity,
        is_acidic=is_acidic,
        is_undersaturated=is_undersaturated,
        limit=limit,
    )
    return {
        "count": len(records),
        "has_data": bool(records),
        "reason": None if records else "No stored pH samples match these filters.",
        "samples": records,
    }


@router.get("/hotspots")
def get_hotspots(
    min_priority: float = Query(0.0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    return engine.detect_stress_zones(db, min_priority=min_priority)


@router.get("/trends")
def get_trends(
    region_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return engine.trend_analysis(db, region_id=region_id)


@router.get("/forecast")
def get_forecast(
    region_id: int = Query(...),
    horizon_days: int = Query(180, ge=30, le=1095),
    db: Session = Depends(get_db),
):
    """Statistical PROJECTION, not a forecast - see the returned disclaimer."""
    out = engine.project_ph_decline(db, region_id=region_id, horizon_days=horizon_days)
    if out.get("status") in ("UNKNOWN_REGION", "INSUFFICIENT_DATA"):
        # 200 with an explicit status: this is an honest "not enough evidence",
        # not a client error, and the frontend renders the reason.
        return out
    return out


@router.get("/zones")
def get_zones(
    band: Literal["surface", "pycnocline", "deep"] | None = Query(None),
    min_depth: float | None = Query(None, ge=0, le=6000),
    max_depth: float | None = Query(None, ge=0, le=6000),
    db: Session = Depends(get_db),
):
    return engine.build_acidification_zones(
        db, band=band, min_depth=min_depth, max_depth=max_depth
    )


@router.get("/sources")
def get_sources():
    return {
        "sources": sources.source_catalogue(),
        "bbox": sources.INDIAN_OCEAN_BBOX,
        "honesty_note": (
            "Status is reported per source as actually reached. A source marked "
            "UNAVAILABLE contributed no values, and no substitute was used in its "
            "place. Primary pH comes from Argo BGC floats; aragonite saturation is "
            "derived by CO2SYS, not observed."
        ),
    }


@router.post("/ingest")
def post_ingest(
    limit: int = Query(
        sources.ARGO_BGC_DEFAULT_LIMIT, ge=1, le=sources.ARGO_BGC_MAX_RECORDS
    ),
    since_days: int = Query(365, ge=1, le=3650),
    floats: str | None = Query(None),
    include_secondary: bool = Query(True),
    db: Session = Depends(get_db),
):
    if not settings.ACIDIFICATION_ENABLED:
        raise HTTPException(status_code=503, detail="Acidification module is disabled.")
    only_wmos = [f.strip() for f in floats.split(",")] if floats else None
    return engine.ingest(
        db,
        limit=limit,
        since_days=since_days,
        only_wmos=only_wmos,
        include_secondary=include_secondary,
    )


@router.post("/map-regions")
def post_map_regions(db: Session = Depends(get_db)):
    return engine.map_to_regions(db)


@router.post("/alerts/refresh")
def post_alerts_refresh(
    min_priority: float = Query(60.0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    return engine.emit_alerts(db, min_priority=min_priority)
