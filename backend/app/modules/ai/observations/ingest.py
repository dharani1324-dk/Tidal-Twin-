"""The single resumable ingestion pipeline every observation adapter runs through.

One path, for every source: fetch candidates -> validate -> resolve a location
-> map onto the existing ``OceanObservation`` model -> write, skipping anything
already stored.  Adding a source means writing an adapter, never editing this
file.

Three properties matter more than throughput here.

**Idempotent / resumable.**  Every row gets a stable
``observation_uid`` derived from the physical identity of the sample (source,
platform, cycle, time, position, depth).  A re-run skips rows whose uid is
already stored, so a run interrupted half way can simply be run again.  Without
this, an operator who re-ran a failed ingestion would silently double the
observation count and the platform would then claim evidence it does not have.

**No re-labelling.**  ``data_status`` comes from the source's declared status,
and a row whose status is anything other than ``REAL`` never populates the
in-situ fields of the wide model in a way that could be read as a measurement.

**Subsurface is not surface.**  ``OceanObservation.sea_surface_temperature`` is
named for the sea surface.  An Argo profile at 500 dbar is a subsurface
measurement, and writing it into that column would be a small lie that every
downstream layer would then repeat.  Only the shallowest bin is treated as a
surface temperature; the full profile travels in ``extra`` instead.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.observations.adapters import BaseObservationAdapter, adapter_for
from app.modules.ai.observations.erddap import ErddapError
from app.modules.ai.observations.registry import list_sources
from app.modules.ai.observations.validation import (
    INFO,
    ValidationReport,
    summarise_reports,
    validate_candidate,
)

logger = logging.getLogger("tidaltwin.observations.ingest")

#: A profile bin at or shallower than this pressure is treated as the surface
#: observation.  Argo's shallowest bins are typically 0-5 dbar, so 10 dbar
#: captures them without claiming a 20 m reading is the surface.
SURFACE_PRESSURE_DBAR = 10.0

#: Half-width of the square zone created for a platform that has no region of its
#: own.  Matches scripts.seed_data so location polygons stay consistent.
PLATFORM_ZONE_HALF_DEG = 0.25

#: Ingest is single-flight: two concurrent runs would race on the unique uid.
_INGEST_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def observation_uid(candidate: dict[str, Any]) -> str:
    """A stable identity for one physical sample.

    Deliberately built from the sample's own coordinates rather than from a row
    id, so the same measurement fetched twice - from two runs, or from two
    mirrors of the same dataset - collapses to one stored row.
    """
    timestamp = candidate.get("timestamp")
    if isinstance(timestamp, datetime):
        stamp = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        stamp = str(timestamp)
    parts = (
        candidate.get("source_id") or "",
        candidate.get("platform_id") or "",
        str(candidate.get("cycle_number") or ""),
        stamp,
        f"{_round(candidate.get('latitude'), 4)}",
        f"{_round(candidate.get('longitude'), 4)}",
        f"{_round(candidate.get('pressure'), 3)}",
    )
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{candidate.get('source_id') or 'unknown'}:{digest}"


def _round(value: Any, places: int) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(numeric, places) if math.isfinite(numeric) else None


# ---------------------------------------------------------------------------
# Mapping a candidate onto the existing model
# ---------------------------------------------------------------------------


def to_model_kwargs(candidate: dict[str, Any], report: ValidationReport) -> dict[str, Any]:
    """Map a validated candidate onto ``OceanObservation`` column values.

    Anything that does not have a column of its own (institutional attribution,
    cycle number, published analysis error, provider limitations) is preserved as
    JSON in ``extra``.  Nothing is discarded, because the provenance of a number
    is part of the number.
    """
    pressure = candidate.get("pressure")
    temperature = candidate.get("temperature")

    kwargs: dict[str, Any] = {
        "timestamp": candidate.get("timestamp"),
        "depth_m": _depth_from_pressure(pressure),
        "pressure": _number(pressure),
        "salinity": _number(candidate.get("salinity")),
        "chlorophyll": _number(candidate.get("chlorophyll")),
        "wave_height": _number(candidate.get("wave_height")),
        "source": candidate.get("source"),
        "source_id": candidate.get("source_id"),
        "platform_id": candidate.get("platform_id"),
        "instrument_id": candidate.get("instrument_id"),
        "data_status": candidate.get("data_status"),
        "processing_level": candidate.get("processing_level"),
        "retrieval_time": datetime.now(timezone.utc),
        "source_reference": _clip(candidate.get("source_reference"), 500),
        "data_type": _clip(candidate.get("data_type"), 20),
        "observation_uid": observation_uid(candidate),
        "extra": _encode_extra(candidate, temperature, pressure),
    }

    # Only a genuinely shallow bin populates the surface temperature column.
    if temperature is not None and pressure is not None and _number(pressure) <= SURFACE_PRESSURE_DBAR:
        kwargs["sea_surface_temperature"] = _number(temperature)
    elif temperature is not None:
        report.add("SUBSURFACE_TEMPERATURE_NOT_SURFACE", INFO,
                   f"temperature {temperature} C at {_number(pressure)} dbar is subsurface; it is "
                   f"stored in the profile payload and not as sea_surface_temperature.",
                   "temperature", temperature)

    kwargs["quality_flag"] = _overall_quality_flag(candidate)
    kwargs["qc_flags"] = _encode_json(candidate.get("qc_flags"))
    kwargs["uncertainty"] = _encode_json(candidate.get("uncertainty"))
    kwargs["validation_flags"] = _encode_json([i.payload() for i in report.issues])
    return kwargs


def _depth_from_pressure(pressure: Any) -> float | None:
    """1 dbar of sea water is ~1 m, so depth and pressure share a scale."""
    value = _number(pressure)
    if value is None:
        return None
    return max(0.0, value)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _clip(value: Any, length: int) -> Any:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= length else text[: length - 1] + "\u2026"


def _encode_json(value: Any) -> str | None:
    if value in (None, {}, []):
        return None
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return json.dumps({"unserialisable": str(value)})


def _encode_extra(candidate: dict[str, Any], temperature: Any, pressure: Any) -> str | None:
    extra: dict[str, Any] = {}
    for key in ("institution", "dataset_id", "platform_type", "cycle_number",
                "profile_direction", "limitations"):
        if candidate.get(key) is not None:
            extra[key] = candidate[key]
    if temperature is not None:
        # The full profile value, so nothing measured is lost to the wide model's
        # surface-oriented column names.
        extra.setdefault("profile", {})["temperature"] = temperature
    if pressure is not None:
        extra.setdefault("profile", {})["pressure"] = pressure
    if extra.get("limitations"):
        extra["limitations"] = str(extra["limitations"])[:1000]
    return _encode_json(extra) if extra else None


def _overall_quality_flag(candidate: dict[str, Any]) -> str | None:
    """One short statement of the value's quality, or of its absence."""
    flags = candidate.get("qc_flags") or {}
    if not flags:
        return "DERIVED_NO_QC_FLAG" if candidate.get("data_status") != "REAL" else "NO_QC_FLAG_PROVIDED"
    values = {str(v).strip()[:1] for v in flags.values() if str(v).strip()}
    if not values:
        return "NO_QC_FLAG_PROVIDED"
    if values <= {"1"}:
        return "GOOD"
    if values <= {"1", "2"}:
        return "PROBABLY_GOOD"
    if "3" in values or "4" in values or "5" in values:
        return "CONTAINS_BAD"
    if values <= {"6", "7", "8"}:
        return "QC_NOT_GENERATED"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Location resolution
# ---------------------------------------------------------------------------


def make_zone(lat: float, lon: float, half_deg: float = PLATFORM_ZONE_HALF_DEG):
    """A small square polygon around a point, matching scripts.seed_data."""
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    return from_shape(Point(lon, lat).buffer(half_deg), srid=4326)


def _zone_name(source_id: str, platform_id: str | None, lat: float, lon: float) -> str:
    label = platform_id or f"{lat:.2f},{lon:.2f}"
    return f"{source_id} {label} ({lat:.2f}N {lon:.2f}E)"


def resolve_location(db: Session, candidate: dict[str, Any], *,
                     cache: dict[str, OceanLocation] | None = None) -> OceanLocation:
    """Find or create the location a point observation belongs to.

    A platform gets a stable, self-describing zone of its own rather than being
    snapped to whichever seeded region happens to be nearest.  Snapping a float
    to "Bay of Bengal (Chennai Coast)" would assert a coastal position the float
    was never at, and the region name would then be quoted as provenance.
    """
    source_id = str(candidate.get("source_id") or "observation")
    platform_id = str(candidate.get("platform_id") or "")
    latitude = float(candidate.get("latitude") or 0.0)
    longitude = float(candidate.get("longitude") or 0.0)
    name = _zone_name(source_id, candidate.get("platform_id"), latitude, longitude)

    if cache is not None and name in cache:
        return cache[name]

    existing = db.query(OceanLocation).filter(OceanLocation.name == name).first()
    if existing is None:
        existing = db.query(OceanLocation).filter(
            OceanLocation.name.like(f"{source_id} {platform_id or ''}%")
        ).first()
    if existing is None:
        existing = OceanLocation(
            name=name,
            region_type="observation_site",
            country="India",
            geom=make_zone(latitude, longitude),
        )
        db.add(existing)
        db.flush()
        logger.info("created observation location %r", name)
    if cache is not None:
        cache[name] = existing
    return existing


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    source_id: str
    data_status: str
    fetched: int = 0
    accepted: int = 0
    rejected: int = 0
    inserted: int = 0
    skipped_existing: int = 0
    locations_created: int = 0
    flag_counts: dict[str, int] = field(default_factory=dict)
    rejected_samples: list[dict[str, Any]] = field(default_factory=list)
    unavailable: str | None = None
    notes: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


def ingest_source(db: Session, source_id: str, *,
                  start: datetime | None = None,
                  end: datetime | None = None,
                  bounds: tuple[float, float, float, float] | None = None,
                  limit: int | None = None,
                  target_time: datetime | None = None,
                  commit_every: int = 250) -> IngestResult:
    """Fetch, validate and store one source's observations.

    Never raises for an unreachable source: the failure is recorded on the result
    so a scheduled run reports honestly instead of crashing the worker.
    """
    spec = next((s for s in list_sources() if s.source_id == source_id), None)
    result = IngestResult(source_id=source_id, data_status=spec.data_status if spec else "UNKNOWN")
    if spec is None:
        result.unavailable = "UNKNOWN_SOURCE"
        return result

    adapter = adapter_for(source_id)
    if adapter is None:
        # A declared-but-unreachable source (buoys, tide gauges, HF radar) is a
        # real gap in the evidence base, and is reported as such rather than
        # quietly skipped.
        result.unavailable = spec.availability_status
        result.notes.append(
            "No automated adapter exists for this source; it requires a manual data request. "
            "See the catalogue entry for the provider's access terms."
        )
        return result

    existing_uids = _load_existing_uids(db, source_id)
    seen: set[tuple] = set()
    reports: list[ValidationReport] = []
    location_cache: dict[str, OceanLocation] = {}
    pending: list[OceanObservation] = []

    def _flush() -> None:
        if pending:
            db.add_all(pending)
            db.commit()
            result.inserted += len(pending)
            pending.clear()

    try:
        for candidate in _iter_candidates(adapter, start, end, bounds, limit, target_time):
            result.fetched += 1
            report = validate_candidate(
                candidate, seen=seen,
                region_bounds=bounds or (settings.OBSERVATIONS_LAT_MIN, settings.OBSERVATIONS_LAT_MAX,
                                         settings.OBSERVATIONS_LON_MIN, settings.OBSERVATIONS_LON_MAX),
            )
            reports.append(report)
            if not report.acceptable:
                result.rejected += 1
                if len(result.rejected_samples) < 25:
                    result.rejected_samples.append({
                        "source_reference": _clip(candidate.get("source_reference"), 200),
                        "issues": [i.payload() for i in report.errors][:5],
                    })
                continue

            kwargs = to_model_kwargs(candidate, report)
            uid = kwargs["observation_uid"]
            if uid in existing_uids:
                result.skipped_existing += 1
                continue
            existing_uids.add(uid)
            before = len(location_cache)
            location = resolve_location(db, candidate, cache=location_cache)
            if len(location_cache) > before:
                result.locations_created += 1
            kwargs["location_id"] = location.id
            pending.append(OceanObservation(**kwargs))
            result.accepted += 1
            if len(pending) >= commit_every:
                _flush()
    except ErddapError as exc:
        _flush()
        result.unavailable = exc.kind
        result.notes.append(f"{exc.kind}: {exc}")
        logger.warning("ingest of %s stopped: %s", source_id, exc)
    except Exception as exc:  # pragma: no cover - a pipeline must not kill the worker
        _flush()
        result.unavailable = f"ERROR:{type(exc).__name__}"
        result.notes.append(f"{type(exc).__name__}: {exc}")
        logger.exception("ingest of %s failed", source_id)
    else:
        _flush()

    summary = summarise_reports(reports)
    result.flag_counts = summary["flag_counts"]
    return result


def _iter_candidates(adapter: BaseObservationAdapter, start, end, bounds, limit,
                     target_time) -> Iterator[dict[str, Any]]:
    if target_time is not None and hasattr(adapter, "candidates"):
        try:
            yield from adapter.candidates(start=start, end=end, bounds=bounds, limit=limit,
                                          target_time=target_time)
            return
        except TypeError:
            pass  # the adapter does not accept a point-in-time target
    yield from adapter.candidates(start=start, end=end, bounds=bounds, limit=limit)


def _load_existing_uids(db: Session, source_id: str) -> set[str]:
    """Uids already stored for this source, so a re-run is a no-op."""
    rows = (
        db.query(OceanObservation.observation_uid)
        .filter(OceanObservation.source_id == source_id)
        .filter(OceanObservation.observation_uid.isnot(None))
        .all()
    )
    return {row[0] for row in rows if row[0]}


def ingest_all(db: Session, *, source_ids: Iterable[str] | None = None, **kwargs) -> list[IngestResult]:
    """Ingest several sources, one at a time, under a single lock."""
    wanted = list(source_ids) if source_ids else [
        s.source_id for s in list_sources()
        if s.enabled and s.availability_status in ("AVAILABLE", "PARTIAL", "MODEL_DERIVED", "SATELLITE_DERIVED")
    ]
    results: list[IngestResult] = []
    with _INGEST_LOCK:
        for source_id in wanted:
            results.append(ingest_source(db, source_id, **kwargs))
    from app.modules.ai.observations.registry import invalidate_cache
    invalidate_cache()
    return results


__all__ = [
    "PLATFORM_ZONE_HALF_DEG",
    "SURFACE_PRESSURE_DBAR",
    "IngestResult",
    "ingest_all",
    "ingest_source",
    "make_zone",
    "observation_uid",
    "resolve_location",
    "to_model_kwargs",
]
