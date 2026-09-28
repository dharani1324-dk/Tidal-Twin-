"""TidalTwin - Microplastics Intelligence API.

A single vertical slice for microplastic detection and decision support,
built on open-source data only.

    GET  /overview          hotspots, surfaces, coverage - one call for the page
    GET  /coverage          exactly how much real evidence exists
    GET  /samples           the stored samples, filtered
    GET  /hotspots          ranked hotspots + plain-language recommendations
    GET  /timeline          yearly buckets per region and medium, for scrubbing
    GET  /sources           provenance, licences and endpoint catalogue
    POST /ingest            pull the NOAA NCEI collection now
    POST /drift             project a 24-72h corridor from a hotspot
    POST /alerts/refresh    raise hotspots into the platform alert store

HONESTY CONTRACT, ENFORCED HERE
-------------------------------
* Every response can be empty, and when it is, it says why.  An unreachable
  connector returns a reason; it never returns a fabricated grid.
* Concentrations are grouped strictly by unit family and medium.  There is no
  endpoint that returns a single blended "microplastic risk number", because
  such a number would be meaningless.
* The NOAA collection is an archive ending in 2021, not a live feed.  The
  vintage is attached to every payload that depends on recency.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.microplastics import MicroplasticSample
from app.modules.ai.microplastics import engine, sources
from app.modules.ai.microplastics.drift import project_drift
from app.modules.ai.microplastics.hotspots import (
    ANOMALY_CATEGORY,
    PRIORITY_WEIGHTS,
    detect_hotspots,
)
from app.modules.ai.microplastics.regions import (
    DEFAULT_RADIUS_KM,
    build_surface,
    distance_decay_confidence,
    resolve_monitored_regions,
)
from app.modules.ai.microplastics.units import (
    ALERT_TIER_RULES,
    BEACH_LADDER,
    CANONICAL_UNITS,
    FAMILY_DESCRIPTIONS,
    SEVERITY_LADDER,
)

router = APIRouter(prefix="/api/v1/microplastics", tags=["Microplastics"])


class DriftInput(BaseModel):
    region_id: int = Field(..., description="Monitored region to project from")
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    duration_h: int = Field(72, ge=6, le=72)
    sensitivity: float = Field(1.0, ge=0.4, le=2.5)


@router.get("/overview")
def get_overview(radius_km: float = Query(DEFAULT_RADIUS_KM, ge=10, le=1000),
                 db: Session = Depends(get_db)):
    """Everything the microplastics workspace renders, in one request.

    Cached in-process for ``MICROPLASTICS_CACHE_TTL_SECONDS``.
    """
    return engine.cached_overview(db)


@router.get("/coverage")
def get_coverage(db: Session = Depends(get_db)):
    """Honest evidence report: how many real samples, over how many regions."""
    return engine.coverage_report(db)


@router.get("/samples")
def get_samples(
    region_id: int | None = Query(None),
    medium: str | None = Query(None, description="water | sediment | beach | beach_nurdle"),
    unit_family: str | None = Query(None),
    min_ordinal: int | None = Query(None, ge=0, le=4),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """Stored samples with their native units, provenance and severity class."""
    query = db.query(MicroplasticSample)
    if region_id is not None:
        query = query.filter(MicroplasticSample.region_id == region_id)
    if medium:
        query = query.filter(MicroplasticSample.medium == medium)
    if unit_family:
        query = query.filter(MicroplasticSample.unit_family == unit_family)
    if min_ordinal is not None:
        query = query.filter(MicroplasticSample.severity_ordinal >= min_ordinal)

    rows = (
        query.order_by(MicroplasticSample.sampled_at.desc().nullslast())
        .limit(limit)
        .all()
    )

    return {
        "count": len(rows),
        "has_data": bool(rows),
        "reason": None if rows else (
            "No stored samples match these filters. Either the collection has "
            "not been ingested yet, or no published sample meets the criteria."
        ),
        "samples": [
            {
                "id": row.id,
                "region_id": row.region_id,
                "region_distance_km": row.region_distance_km,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "sampled_at": row.sampled_at.isoformat() if row.sampled_at else None,
                "medium": row.medium,
                "unit_family": row.unit_family,
                "measured_value": row.measured_value,
                "measured_unit": row.measured_unit,
                "canonical_value": row.canonical_value,
                "canonical_unit": row.canonical_unit,
                "published_class": row.published_class,
                "published_class_range": row.published_class_range,
                "severity_label": row.severity_label,
                "severity_ordinal": row.severity_ordinal,
                "confidence_score": row.confidence_score,
                "origin_status": row.origin_status,
                "source": row.source,
                "organization": row.organization,
                "reference": row.reference,
                "doi": row.doi,
                "sampling_method": row.sampling_method,
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
    """Ranked hotpots as a new anomaly category, with recommended actions."""
    rows = engine.load_records(db)
    if not rows:
        return {
            "anomaly_category": ANOMALY_CATEGORY,
            "hotspot_count": 0,
            "hotspots": [],
            "recommendations": {
                "summary": "No microplastic samples stored yet.",
                "actions": [],
            },
            "reason": "Ingest the NOAA NCEI collection first.",
        }

    records = [engine._stored_to_normalized(row) for row in rows]
    regions = resolve_monitored_regions(db)
    return detect_hotspots(records, regions, min_priority=min_priority)


@router.get("/timeline")
def get_timeline(db: Session = Depends(get_db)):
    """Yearly buckets per region and medium, for the time scrubber."""
    return engine.timeline(db)


@router.get("/surface")
def get_surface(
    medium: str = Query("water", description="water | sediment | beach"),
    radius_km: float = Query(DEFAULT_RADIUS_KM, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    """IDW concentration surface for one medium, with explicit gap reporting.

    Grid cells with no sample in range are returned as counted gaps, never as
    zero - a zero would claim the water was sampled and found clean.
    """
    rows = engine.load_records(db)
    subset = [
        row for row in rows
        if row.medium == medium and row.canonical_value is not None
    ]
    if not subset:
        return {
            "has_data": False,
            "medium": medium,
            "nodes": [],
            "reason": (
                f"No normalised {medium} samples are stored. Nothing is "
                "interpolated from an empty sample set."
            ),
        }

    latitudes = [row.latitude for row in subset]
    longitudes = [row.longitude for row in subset]
    bbox = {
        "lat_min": max(0.0, min(latitudes) - 1.0),
        "lat_max": max(latitudes) + 1.0,
        "lon_min": min(longitudes) - 1.0,
        "lon_max": max(longitudes) + 1.0,
    }
    surface = build_surface(
        [
            {"latitude": row.latitude, "longitude": row.longitude,
             "value": row.canonical_value}
            for row in subset
        ],
        bbox,
        radius_km=radius_km,
    )
    surface["has_data"] = True
    surface["medium"] = medium
    surface["unit"] = subset[0].canonical_unit
    surface["sample_count"] = len(subset)
    for node in surface["nodes"]:
        node["confidence"] = distance_decay_confidence(node.get("nearest_km"), radius_km)
    return surface


@router.get("/sources")
def get_sources():
    """Provenance, licences, endpoints and what each source is used for."""
    return {
        "sources": sources.source_catalogue(),
        "noaa_bbox": sources.INDIA_BBOX,
        "note": (
            "All microplastic values in this platform originate from open, "
            "publicly documented datasets. No hardware or proprietary feed is "
            "used, and no value is estimated when a source is unavailable."
        ),
    }


@router.get("/method")
def get_method():
    """The measurement discipline, ladders and scoring weights, exposed openly."""
    return {
        "algorithm_version": engine.ALGORITHM_VERSION,
        "unit_families": {
            family: {
                "canonical_unit": CANONICAL_UNITS[family],
                "description": FAMILY_DESCRIPTIONS[family],
                "ladder": [
                    {"low": low, "high": high, "label": label}
                    for low, high, label in
                    (SEVERITY_LADDER.get(family) or ())
                ],
            }
            for family in (CANONICAL_UNITS.keys())
        },
        "beach_ladder": [
            {"low": low, "high": high, "label": label}
            for low, high, label in BEACH_LADDER
        ],
        "hotspot_priority_weights": PRIORITY_WEIGHTS,
        "alert_tiers": [
            {"min_ordinal": ordinal, "severity": severity, "action": action,
             "rationale": rationale}
            for ordinal, severity, action, rationale in ALERT_TIER_RULES
        ],
        "rules": [
            "Concentrations are grouped by unit family and medium, never pooled.",
            "The severity class comes from the source's own published class "
            "field wherever it exists; our ladder only fills gaps.",
            "Interpolated grid cells with no sample in range are gaps, never zero.",
            "Drift is projected only when real current forcing exists.",
        ],
        "limitations": [
            "The NOAA NCEI microplastics collection is an archive spanning "
            "1972-2021 in this window; it is not a live monitoring feed.",
            "IDW is a distance-weighted interpolation, not a kriged field with a "
            "fitted variogram.",
            "Sample counts in individual regions are small, so per-region "
            "statistics carry wide uncertainty that is reported alongside them.",
            "Microplastic drift treats particles as a single-layer surface "
            "tracer; sinking, beaching and vertical shear are not modelled.",
        ],
    }


@router.post("/ingest")
def post_ingest(
    limit: int = Query(sources.NOAA_DEFAULT_LIMIT, ge=1, le=sources.NOAA_MAX_RECORD_COUNT),
    db: Session = Depends(get_db),
):
    """Pull, normalise, map and store the NOAA NCEI microplastics collection."""
    if not settings.MICROPLASTICS_ENABLED:
        raise HTTPException(status_code=503, detail="Microplastics module is disabled.")

    summary = engine.ingest(db, limit=limit)
    engine.clear_cache()
    return summary


@router.post("/drift")
def post_drift(payload: DriftInput, db: Session = Depends(get_db)):
    """Project a 24-72h microplastic drift corridor from a region's hotspot.

    Returns ``status="NO_FORCING"`` with a reason when no trusted surface
    current exists, instead of drawing a corridor from a default velocity.
    """
    region = next(
        (r for r in resolve_monitored_regions(db) if r["region_id"] == payload.region_id),
        None,
    )
    if region is None:
        raise HTTPException(status_code=404, detail="Unknown region_id.")

    latitude = payload.latitude if payload.latitude is not None else region["latitude"]
    longitude = payload.longitude if payload.longitude is not None else region["longitude"]

    projection = project_drift(
        db,
        region_id=payload.region_id,
        latitude=latitude,
        longitude=longitude,
        duration_h=payload.duration_h,
        sensitivity=payload.sensitivity,
    )
    projection["region"] = region["name"]
    projection["anomaly_category"] = ANOMALY_CATEGORY
    return projection


@router.post("/alerts/refresh")
def post_alerts_refresh(
    min_priority: float = Query(60.0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Raise eligible hotspots into the platform's existing alert store.

    Idempotent for a given region and medium, so it is safe to schedule.
    """
    return engine.emit_alerts(db, min_priority=min_priority)
