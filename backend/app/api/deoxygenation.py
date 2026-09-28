"""TidalTwin - Deoxygenation Intelligence API
==============================================

A single vertical slice for dissolved oxygen monitoring, hypoxia detection,
and forecasting, built on open-source data only (Argo BGC floats, NOAA hypoxia
datasets, World Ocean Database).

Endpoints:
    GET  /overview          hotspots, zones, coverage, trends - one call for the page
    GET  /coverage          exactly how much real evidence exists per region
    GET  /samples           the stored samples, filtered
    GET  /hotspots          ranked hypoxic zones + plain-language recommendations
    GET  /zones             measured oxygen on a 0.5-degree grid, per depth band
    GET  /trends            historical trend analysis per region (expanding/shrinking/stable)
    GET  /forecast          projected hypoxic zone expansion (stretch goal)
    GET  /sources           provenance, licences and endpoint catalogue
    POST /ingest            download real Argo BGC DOXY profiles and store them now
    POST /map-regions       assign samples to 8 coastal regions
    POST /alerts/refresh    raise hypoxic hotspots into platform alert store

HONESTY CONTRACT, ENFORCED HERE
-------------------------------
* Every response can be empty, and when it is, it says why.  An unreachable
  connector returns a reason; it never returns a fabricated grid.
* Oxygen values are stored in canonical umol/kg (Argo native) with derived mg/L.
* Hypoxia is classified at ~2 mg/L (~62.5 umol/kg); dead zone at ~0.5 mg/L.
* A connector that cannot reach its source reports UNAVAILABLE with the reason.
  An empty success is never used to hide a broken endpoint.
* Interpolated grid cells with no sample in range are gaps, never zero.
* Predictive trends are labelled PROJECTION and carry explicit uncertainty.
* Region hotspots cover only the 8 coastal regions; the /zones grid is
  region-independent and is what surfaces offshore oxygen minimum zones.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.dissolved_oxygen import DissolvedOxygenSample
from app.models.location import OceanLocation
from app.models.alert import OceanAlert
from app.modules.ai.deoxygenation import engine, sources
from app.modules.ai.deoxygenation.regions import resolve_monitored_regions
from app.modules.ai.deoxygenation.hotspots import detect_hypoxic_hotspots

router = APIRouter(prefix="/api/v1/deoxygenation", tags=["Deoxygenation"])


class ForecastInput(BaseModel):
    region_id: int = Field(..., description="Monitored region to project from")
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    horizon_days: int = Field(30, ge=7, le=90, description="Projection horizon")
    sensitivity: float = Field(1.0, ge=0.5, le=2.0)


@router.get("/overview")
def get_overview(
    radius_km: float = Query(250, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    """Everything the deoxygenation workspace renders, in one request.

    Cached in-process for DEOXYGENATION_CACHE_TTL_SECONDS.
    """
    return engine.cached_overview(db, radius_km)


@router.get("/coverage")
def get_coverage(db: Session = Depends(get_db)):
    """Honest evidence report: how many real samples, over how many regions."""
    return engine.coverage_report(db)


@router.get("/samples")
def get_samples(
    region_id: int | None = Query(None),
    min_severity: str | None = Query(None, description="NORMAL|LOW|MODERATE|HIGH|CRITICAL"),
    is_hypoxic: bool | None = Query(None),
    is_dead_zone: bool | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """Stored oxygen samples with their native units, provenance and severity class."""
    query = db.query(DissolvedOxygenSample)
    
    if region_id is not None:
        query = query.filter(DissolvedOxygenSample.region_id == region_id)
    if min_severity:
        severity_order = {"NORMAL": 1, "LOW": 2, "MODERATE": 3, "HIGH": 4, "CRITICAL": 5}
        min_ordinal = severity_order.get(min_severity.upper(), 1)
        query = query.filter(DissolvedOxygenSample.severity_ordinal >= min_ordinal)
    if is_hypoxic is not None:
        query = query.filter(DissolvedOxygenSample.is_hypoxic == (1 if is_hypoxic else 0))
    if is_dead_zone is not None:
        query = query.filter(DissolvedOxygenSample.is_dead_zone == (1 if is_dead_zone else 0))

    rows = (
        query.order_by(DissolvedOxygenSample.sampled_at.desc().nullslast())
        .limit(limit)
        .all()
    )

    return {
        "count": len(rows),
        "has_data": bool(rows),
        "reason": None if rows else (
            "No oxygen samples match these filters. Either the Argo BGC / NOAA "
            "collections have not been ingested yet, or no sample meets the criteria."
        ),
        "samples": [
            {
                "id": row.id,
                "region_id": row.region_id,
                "region_distance_km": row.region_distance_km,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "sampled_at": row.sampled_at.isoformat() if row.sampled_at else None,
                "depth_m": row.depth_m,
                "do_umol_kg": row.do_umol_kg,
                "do_mg_l": row.do_mg_l,
                "temperature_c": row.temperature_c,
                "salinity_psu": row.salinity_psu,
                "pressure_dbar": row.pressure_dbar,
                "severity_label": row.severity_label,
                "severity_ordinal": row.severity_ordinal,
                "is_hypoxic": bool(row.is_hypoxic) if row.is_hypoxic is not None else None,
                "is_dead_zone": bool(row.is_dead_zone) if row.is_dead_zone is not None else None,
                "confidence_score": row.confidence_score,
                "origin_status": row.origin_status,
                "source": row.source,
                "source_dataset": row.source_dataset,
                "source_record_id": row.source_record_id,
                "source_record_link": row.source_record_link,
                "organization": row.organization,
                "reference": row.reference,
                "doi": row.doi,
                "float_id": row.float_id,
                "cycle": row.cycle,
                "source_file": row.source_file,
                "qc_flag": row.qc_flag,
                "quality_note": row.quality_note,
            }
            for row in rows
        ],
    }


@router.get("/hotspots")
def get_hotspots(
    min_priority: float = Query(0.0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Ranked hypoxic zones as a new anomaly category, with recommended actions."""
    rows = engine.load_records(db)
    if not rows:
        return {
            "anomaly_category": "Low Oxygen Zone",
            "hotspot_count": 0,
            "hotspots": [],
            "recommendations": {
                "summary": "No dissolved oxygen samples stored yet.",
                "actions": [],
            },
            "reason": "Ingest Argo BGC and NOAA hypoxia data first.",
        }

    records = [engine._stored_to_normalized(row) for row in rows]
    regions = resolve_monitored_regions(db)
    return detect_hypoxic_hotspots(records, regions, min_priority=min_priority)


@router.get("/trends")
def get_trends(
    region_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Historical trend analysis per region: expanding, shrinking, or stable hypoxic zones."""
    return engine.trend_analysis(db, region_id)


@router.get("/forecast")
def get_forecast(
    region_id: int = Query(..., description="Monitored region to project from"),
    horizon_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    """Projected hypoxic zone expansion/shrinkage over the next weeks.

    Returns PROJECTION (not forecast) with explicit uncertainty bands.
    Requires sufficient historical time series per region.
    """
    result = engine.project_hypoxic_expansion(
        db, region_id, horizon_days=horizon_days
    )
    if result.get("status") in ("NO_DATA", "UNKNOWN_REGION"):
        # 404 carries the reason, so the caller can distinguish "not enough
        # data yet" from "you asked for a region that does not exist".
        raise HTTPException(
            404,
            detail={
                "status": result.get("status"),
                "message": result.get("message"),
                "known_region_ids": result.get("known_region_ids"),
            },
        )
    return result


@router.get("/zones")
def get_zones(
    band: Literal["surface", "pycnocline", "deep"] | None = Query(
        None,
        description=(
            "Restrict to one depth band. Must be one of the canonical band keys; "
            "an unrecognised value is rejected rather than silently returning an "
            "empty grid."
        ),
    ),
    min_depth: float | None = Query(None, ge=0, le=6000),
    max_depth: float | None = Query(None, ge=0, le=6000),
    db: Session = Depends(get_db),
):
    """Measured oxygen aggregated onto a 0.5-degree grid, per depth window.

    Region-independent, so this also covers offshore oxygen minimum zones that
    fall outside the 500 km coastal mapping radius and therefore never appear in
    a hotspot. Every cell reports its own ``n_samples`` and ``n_floats``.
    """
    return engine.build_oxygen_zones(
        db, band=band, min_depth=min_depth, max_depth=max_depth
    )


@router.get("/sources")
def get_sources():
    """Provenance, licences, endpoints and what each source is used for."""
    return {
        "sources": sources.source_catalogue(),
        "indian_ocean_bbox": sources.INDIAN_OCEAN_BBOX,
        "note": (
            "All dissolved oxygen values in this platform originate from open, "
            "publicly documented datasets (Argo BGC floats, NOAA Hypoxia Watch, "
            "World Ocean Database, peer-reviewed literature). No hardware or "
            "proprietary feed is used, and no value is estimated when a source "
            "is unavailable."
        ),
    }


@router.post("/ingest")
def post_ingest(
    limit: int = Query(
        sources.ARGO_BGC_DEFAULT_LIMIT,
        ge=1,
        le=sources.ARGO_BGC_MAX_RECORDS,
        description="Max BGC float profiles to download and parse",
    ),
    since_days: int = Query(
        120, ge=1, le=3650,
        description="Only profiles with a DOXY observation newer than this",
    ),
    floats: str | None = Query(
        None,
        description="Comma-separated WMO float ids; bypasses the box/time filter",
    ),
    include_literature: bool = Query(
        True,
        description="Also ingest curated published literature reference points",
    ),
    db: Session = Depends(get_db),
):
    """Download real Argo BGC float profiles, extract measured DOXY, and store it.

    This is the endpoint that puts live data into the platform. It fetches the
    Argo BGC profile index, selects oxygen-bearing profiles inside the
    monitored Indian Ocean box, downloads each per-profile NetCDF from the GDAC
    and stores every finite measured level with its source file, cycle and QC
    flag. Idempotent: rows are keyed on (source, source_record_id).
    """
    if not settings.DEOXYGENATION_ENABLED:
        raise HTTPException(status_code=503, detail="Deoxygenation module is disabled.")

    only_wmos = [w.strip() for w in floats.split(",") if w.strip()] if floats else None

    summary = engine.ingest(
        db,
        limit=limit,
        since_days=since_days,
        only_wmos=only_wmos,
        include_literature=include_literature,
    )
    engine.clear_cache()
    return summary


@router.post("/map-regions")
def post_map_regions(db: Session = Depends(get_db)):
    """Assign unassigned oxygen samples to the 8 coastal regions with confidence scores."""
    summary = engine.map_to_regions(db)
    engine.clear_cache()
    return summary


@router.post("/alerts/refresh")
def post_alerts_refresh(
    min_priority: float = Query(60.0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Raise eligible hypoxic hotspots as OceanAlert rows (idempotent)."""
    return engine.emit_alerts(db, min_priority=min_priority)