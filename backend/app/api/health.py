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

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.demo import _simulated_filter
from app.core.config import settings
from app.core.database import get_db
from app.models.location import OceanLocation
from app.models.observation import OceanObservation

router = APIRouter(tags=["System"])

AVAILABLE = "AVAILABLE"
LIMITED = "LIMITED"
UNAVAILABLE = "UNAVAILABLE"
OPTIONAL = "OPTIONAL / UNAVAILABLE"

# Small in-process TTL cache so frequent status polling does not re-run the
# heavier TIDE candidate build on every request.
_TIDE_CACHE: dict[str, tuple[float, dict]] = {}
_TIDE_TTL_SECONDS = 30.0


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
        observations = db.query(func.count(OceanObservation.id)).scalar() or 0
        simulated = (
            db.query(func.count(OceanObservation.id)).filter(_simulated_filter()).scalar() or 0
        )
    except Exception as exc:  # pragma: no cover - depends on live DB
        return {"status": UNAVAILABLE, "detail": f"Ocean data unavailable: {type(exc).__name__}."}
    if observations == 0:
        return {
            "status": UNAVAILABLE,
            "detail": "No ocean observations are stored. Run the seed/refresh scripts.",
            "locations": locations,
            "observations": observations,
            "simulated_observations": simulated,
        }
    status = AVAILABLE if locations >= 1 else LIMITED
    detail = f"{locations} locations, {observations} observations available."
    if simulated:
        detail += f" ({simulated} labelled demonstration rows.)"
    return {
        "status": status,
        "detail": detail,
        "locations": locations,
        "observations": observations,
        "simulated_observations": simulated,
    }


def _check_tide(db: Session) -> dict:
    """Lightweight TIDE probe.

    Building the full candidate ranking is intentionally NOT done here: it is a
    request-time computation over every location, and folding it into a health
    poll would make the endpoint slow.  Instead we verify the scoring contract
    loads and responds, and report that candidate ranking is computed per request.
    """
    now = time.monotonic()
    cached = _TIDE_CACHE.get("tide")
    if cached and now - cached[0] < _TIDE_TTL_SECONDS:
        return cached[1]
    try:
        from app.modules.ai.tide import scoring

        probe = scoring.calculate_observation_value(
            {
                "decision_impact": 0.5,
                "uncertainty": 0.5,
                "data_gap": 0.5,
                "anomaly_persistence": 0.5,
                "observation_cost": scoring.METHOD_COSTS["BUOY"],
            }
        )
        value = probe.get("observation_value")
        result = {
            "status": AVAILABLE if value is not None else LIMITED,
            "detail": f"TIDE scoring v{scoring.TIDE_ALGORITHM_VERSION} loaded; candidate ranking is computed per request.",
        }
    except Exception as exc:  # pragma: no cover - defensive
        result = {"status": UNAVAILABLE, "detail": f"TIDE scoring unavailable: {type(exc).__name__}."}
    _TIDE_CACHE["tide"] = (now, result)
    return result


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
    core = [checks["ocean_data"], checks["tide"]]
    if any(c["status"] == UNAVAILABLE for c in core):
        return "degraded"
    return "healthy"


def build_health(db: Session) -> dict:
    """Compose the full health payload. Never raises."""
    checks = {
        "backend": _check_backend(),
        "database": _check_database(db),
        "ocean_data": _check_ocean_data(db),
        "tide": _check_tide(db),
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
