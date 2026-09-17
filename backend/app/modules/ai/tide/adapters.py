"""Adapters from existing TidalTwin services into TIDE's normalised inputs."""

import os
import threading
import time
from datetime import datetime, timezone

from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.apex.recommend import build_recommendations
from app.modules.ai.forensics.intelligence import _obs_stats, uncertainty_map
from app.modules.ai.twin.compare import compare
from app.modules.ai.twin.compare import VARIABLES as TWIN_VARIABLES
from app.modules.ai.twin.events import detect_events
from app.modules.ai.tide.scoring import unit
from app.schemas.tide import TideObservation


# ---------------------------------------------------------------------------
# Short-lived read cache for the two expensive shared context builders.
#
# Profiling (Phase 9) showed ``uncertainty_inputs`` and ``apex_candidates``
# dominate TIDE ranking latency (~2.3s + ~3.5s per call over the live dataset)
# while changing only when underlying data changes.  A short TTL cache removes
# the redundant recomputation across the several TIDE endpoints a single page
# load hits, without introducing Redis or any new infrastructure.
# ---------------------------------------------------------------------------

# Short-TTL read cache for the expensive TIDE shared inputs. Long enough that a
# demonstration session stays responsive between clicks, short enough that a
# live data change is reflected within a couple of minutes. Override with the
# TIDE_CACHE_TTL_SECONDS environment variable; set 0 to disable caching.
_CACHE_TTL_SECONDS = float(os.getenv("TIDE_CACHE_TTL_SECONDS", "120"))
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_LOCK = threading.Lock()


def invalidate_caches() -> None:
    """Drop cached shared inputs (call after demo seed/reset or data refresh)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _cached(key: str, build):
    if _CACHE_TTL_SECONDS <= 0:
        return build()
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None and now - hit[0] < _CACHE_TTL_SECONDS:
            return hit[1]
    value = build()
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
    return value


def location_coordinates(location: OceanLocation) -> tuple[float | None, float | None]:
    if location.geom is None:
        return None, None
    try:
        centroid = to_shape(location.geom).centroid
        return centroid.y, centroid.x
    except Exception:
        return None, None


def observation_status(row: OceanObservation) -> str:
    raw = f"{row.data_type or ''} {row.source or ''}".upper()
    if "SIMULATED" in raw:
        return "SIMULATED"
    if "SYNTHETIC" in raw or "DEMO" in raw:
        return "SYNTHETIC"
    if "MODEL" in raw or "FORECAST" in raw:
        return "MODEL_DERIVED"
    if "HISTORICAL" in raw:
        return "HISTORICAL"
    return "REAL"


def latest_observation(db: Session, location_id: int) -> OceanObservation | None:
    return (db.query(OceanObservation).filter(OceanObservation.location_id == location_id)
            .order_by(OceanObservation.timestamp.desc()).first())


def normalize_observation(row: OceanObservation, location: OceanLocation) -> TideObservation:
    """Adapt the existing ORM row without introducing a duplicate observation table."""
    lat, lon = location_coordinates(location)
    return TideObservation(
        id=f"observation-{row.id}", location_id=location.id, latitude=lat, longitude=lon,
        depth_m=row.depth_m or 0.0, timestamp=row.timestamp, variable="temperature",
        value=row.sea_surface_temperature, observation_type="OCEAN_OBSERVATION",
        status=observation_status(row), quality=None, source=row.source,
    )


def uncertainty_inputs(db: Session) -> dict[int, dict]:
    """Reuse Forensics' existing uncertainty calculation, normalized to 0..1."""
    def build() -> dict[int, dict]:
        try:
            rows = uncertainty_map(db).get("regions", [])
        except Exception:
            return {}
        return {r["location_id"]: {**r, "score": unit((r.get("uncertainty") or 0) / 100)} for r in rows}

    return _cached("uncertainty_inputs", build)


def event_inputs(db: Session) -> dict[int, list[dict]]:
    try:
        events = detect_events(db).get("events", [])
    except Exception:
        return {}
    grouped: dict[int, list[dict]] = {}
    for event in events:
        location_id = event.get("location_id")
        if location_id is not None:
            grouped.setdefault(location_id, []).append(event)
    return grouped


def apex_candidates(db: Session) -> dict[int, dict]:
    """Use APEX only for candidate generation; TIDE supplies the final score."""
    def build() -> dict[int, dict]:
        try:
            rows = build_recommendations(db, min_priority=0).get("recommendations", [])
        except Exception:
            return {}
        return {row["location_id"]: row for row in rows if row.get("location_id") is not None}

    return _cached("apex_candidates", build)


def gap_inputs(db: Session, location_id: int, depth_m: float) -> list[dict]:
    stats = _obs_stats(db, location_id)
    now = datetime.now(timezone.utc)
    latest = latest_observation(db, location_id)
    gaps: list[dict] = []
    if stats.get("count", 0) == 0:
        gaps.append({"type": "NO_OBSERVATION", "score": 1.0, "description": "No observations are available in the active 72-hour window."})
    elif stats.get("count", 0) < 8:
        gaps.append({"type": "SPARSE_OBSERVATION", "score": unit(1 - stats.get("count", 0) / 8), "description": "Observation density is below the TIDE minimum coverage threshold."})
    if stats.get("recency_h", 0) > 12:
        gaps.append({"type": "STALE_OBSERVATION", "score": unit(stats["recency_h"] / 72), "description": f"Latest observation is {stats['recency_h']:.1f} hours old."})
    if latest is not None and depth_m > 0 and abs((latest.depth_m or 0) - depth_m) > 25:
        gaps.append({"type": "DEPTH_GAP", "score": 0.7, "description": "No recent observation matches the requested depth band."})
    if latest is not None and latest.timestamp:
        timestamp = latest.timestamp if latest.timestamp.tzinfo else latest.timestamp.replace(tzinfo=timezone.utc)
        age_seconds = (now - timestamp).total_seconds()
    else:
        age_seconds = 0
    if age_seconds > 24 * 3600:
        gaps.append({"type": "TEMPORAL_GAP", "score": 0.8, "description": "The available observation is older than one day."})
    return gaps or [{"type": "NO_MATERIAL_GAP", "score": 0.05, "description": "Available observations meet the initial TIDE coverage checks."}]


def disagreement_input(db: Session, location: OceanLocation, variable: str, depth_m: float, events: list[dict]) -> dict:
    if variable not in TWIN_VARIABLES:
        return {"model_value": None, "observed_value": None, "difference": None,
                "severity": 0.0, "persistence": unit(min(1, len(events) / 3)),
                "spatial_consistency": 0.0, "status": "unavailable"}
    try:
        result = compare(db, location, variable=variable, depth_m=depth_m)
    except Exception:
        result = {"error": "comparison unavailable"}
    difference = result.get("difference") if isinstance(result, dict) else None
    severity = unit((result.get("severity_score") or 0) / 100) if isinstance(result, dict) else 0.0
    if isinstance(result, dict) and severity == 0:
        band = result.get("severity", "").lower()
        severity = {"high": 0.8, "moderate": 0.5, "low": 0.2}.get(band, 0.0)
    persistence = unit(min(1, len(events) / 3))
    spatial = unit((result.get("confidence") or 0) / 100) if isinstance(result, dict) else 0.0
    return {"model_value": result.get("model") if isinstance(result, dict) else None,
            "observed_value": result.get("observed") if isinstance(result, dict) else None,
            "difference": difference, "severity": severity, "persistence": persistence,
            "spatial_consistency": spatial, "status": result.get("data_status") if isinstance(result, dict) else "unavailable"}
