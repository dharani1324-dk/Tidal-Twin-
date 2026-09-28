"""TidalTwin - System Health API (Phase 9).

Reports factual, per-subsystem availability for the frontend status indicator.

Design notes
------------
* Every check is individually guarded: one failing subsystem can never make the
  endpoint itself fail.
* Status vocabulary is deliberately small and honest:
  ``AVAILABLE`` / ``LIMITED`` / ``UNAVAILABLE`` / ``OPTIONAL / UNAVAILABLE``.
* Optional infrastructure (e.g. Cesium Ion terrain/imagery tokens) is reported as
  optional rather than as a hard failure.
* No secrets or credentials are ever included in the payload.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.demo import _simulated_filter
from app.core.config import settings
from app.core.database import get_db
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.provenance_quality import origin_status

router = APIRouter(tags=["System"])

AVAILABLE = "AVAILABLE"
LIMITED = "LIMITED"
UNAVAILABLE = "UNAVAILABLE"
OPTIONAL = "OPTIONAL / UNAVAILABLE"

def _check_backend() -> dict:
    return {
        "status": AVAILABLE,
        "detail": f"{settings.PROJECT_NAME} API v{settings.VERSION} is serving requests.",
    }


def _check_database(db: Session) -> dict:
    from sqlalchemy import text

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on live DB
        return {"status": UNAVAILABLE, "detail": f"Database unreachable: {type(exc).__name__}."}
    detail = "Database connection is serving queries."
    try:
        row = db.execute(text("SELECT postgis_version()")).first()
        if row and row[0]:
            detail = f"Database + PostGIS reachable (PostGIS {row[0]})."
    except Exception:
        detail = "Database reachable; PostGIS version could not be read."
    return {"status": AVAILABLE, "detail": detail}


def _check_ocean_data(db: Session) -> dict:
    try:
        locations = db.query(func.count(OceanLocation.id)).scalar() or 0
        groups = (
            db.query(OceanObservation.source, OceanObservation.data_type, func.count(OceanObservation.id))
            .group_by(OceanObservation.source, OceanObservation.data_type)
            .all()
        )
    except Exception as exc:  # pragma: no cover - depends on live DB
        return {"status": UNAVAILABLE, "detail": f"Ocean data unavailable: {type(exc).__name__}."}

    counts = {"REAL": 0, "HISTORICAL": 0, "SATELLITE_DERIVED": 0,
              "MODEL_DERIVED": 0, "SIMULATED": 0, "SYNTHETIC": 0, "UNKNOWN": 0}
    for source, data_type, count in groups:
        counts[origin_status(source, data_type)] += count
    total = sum(counts.values())
    measured = counts["REAL"] + counts["HISTORICAL"] + counts["SATELLITE_DERIVED"]
    if total == 0:
        return {
            "status": UNAVAILABLE,
            "detail": "No ocean time-series records are stored. Run an enabled source ingestion.",
            "locations": locations, "records": 0, "direct_measurements": 0,
            "model_forecasts": 0, "simulated_records": 0,
        }
    status = AVAILABLE if measured else LIMITED
    detail = f"{locations} locations, {measured} measured/historical records, {counts['MODEL_DERIVED']} model-derived records."
    if counts["SIMULATED"] + counts["SYNTHETIC"]:
        detail += f" {counts['SIMULATED'] + counts['SYNTHETIC']} simulated/synthetic records are labelled."
    if measured == 0:
        detail += " Direct measurement evidence is currently unavailable."
    return {
        "status": status, "detail": detail, "locations": locations, "records": total,
        "direct_measurements": counts["REAL"],
        "historical_records": counts["HISTORICAL"],
        "satellite_derived_records": counts["SATELLITE_DERIVED"],
        "eligible_evidence_records": measured,
        "model_forecasts": counts["MODEL_DERIVED"],
        "simulated_records": counts["SIMULATED"], "synthetic_records": counts["SYNTHETIC"],
    }


def _check_copilot() -> dict:
    try:
        from app.modules.ai.nlp import copilot

        copilot.detect_intent("health check")
        return {
            "status": AVAILABLE,
            "detail": "Copilot is a local, rule-based NLP service with no external dependency.",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": UNAVAILABLE, "detail": f"Copilot unavailable: {type(exc).__name__}."}


def _check_cesium() -> dict:
    if settings.CESIUM_ION_TOKEN:
        return {"status": AVAILABLE, "detail": "CesiumJS token configured for Ion terrain/imagery."}
    return {
        "status": OPTIONAL,
        "detail": "CesiumJS loads from bundled assets; Ion terrain/imagery token not set (optional).",
    }



def _overall(checks: dict[str, dict]) -> str:
    if checks["backend"]["status"] != AVAILABLE:
        return "unavailable"
    if checks["database"]["status"] != AVAILABLE:
        return "unavailable"
    core = [checks["ocean_data"]]
    if any(c["status"] == UNAVAILABLE for c in core):
        return "degraded"
    return "healthy"


def build_health(db: Session) -> dict:
    """Compose the full health payload. Never raises."""
    checks = {
        "backend": _check_backend(),
        "database": _check_database(db),
        "ocean_data": _check_ocean_data(db),
        "copilot": _check_copilot(),
        "cesium": _check_cesium(),
    }
    return {
        "status": _overall(checks),
        "service": "TidalTwin Backend",
        "version": settings.VERSION,
        "release": settings.RELEASE_NAME,
        "environment": settings.ENVIRONMENT,
        "simulation_mode": bool(checks["ocean_data"].get("simulated_observations", 0)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.get("/api/v1/health")
def health_v1(db: Session = Depends(get_db)) -> dict:
    """Primary health endpoint (used by the frontend status indicator)."""
    return build_health(db)


@router.get("/api/health")
def health_alias(db: Session = Depends(get_db)) -> dict:
    """Short alias for external monitors and smoke tests."""
    return build_health(db)
