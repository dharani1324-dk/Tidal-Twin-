"""
TidalTwin - Microplastics: engine
==================================
Orchestrates the module end to end and owns the honesty contract for the API:

    fetch (sources) -> normalise (normalize) -> map (regions)
        -> persist (MicroplasticSample) -> score (hotspots) -> project (drift)

DESIGN NOTES
------------
* ``ingest()`` is idempotent.  Rows are matched on
  ``(source, source_record_id)``, so re-running the connector updates rather
  than duplicates.  NOAA republishes corrections under the same OBJECTID.

* The overview payload is cached in-process with a TTL, the same pattern the
  TIDE engine uses.  There is no Redis in this project and no reason to add one.

* Nothing here fabricates.  Every empty result carries a reason, and the
  coverage report states how much of the picture is real measurements versus
  interpolation.

* Simulated or synthetic rows are never written by this module.  Everything it
  stores is an actual published observation with ``origin_status="REAL"``.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.location import OceanLocation
from app.models.microplastics import MicroplasticSample
from app.modules.ai.microplastics import sources
from app.modules.ai.microplastics.hotspots import (
    ANOMALY_CATEGORY,
    collection_vintage,
    detect_hotspots,
)
from app.modules.ai.microplastics.normalize import (
    normalize_batch,
    normalize_literature_batch,
)
from app.modules.ai.microplastics.regions import (
    DEFAULT_RADIUS_KM,
    build_surface,
    distance_decay_confidence,
    resolve_monitored_regions,
)
from app.modules.ai.microplastics.regions import assign_records
from app.modules.ai.microplastics.units import (
    FAMILY_DESCRIPTIONS,
    FAMILY_NURDLE,
    FAMILY_SEDIMENT,
    FAMILY_UNKNOWN,
    FAMILY_WATER,
    MEDIUM_BEACH,
    MEDIUM_NURDLE,
    MEDIUM_SEDIMENT,
    MEDIUM_WATER,
)

logger = logging.getLogger("tidaltwin.microplastics.engine")

ALGORITHM_VERSION = "1.0"

# --------------------------------------------------------------------------
# In-process TTL cache for the expensive overview aggregate.
# --------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key: str, ttl: int):
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.time() - stored_at > ttl:
        return None
    return value


def _cache_set(key: str, value) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)


def clear_cache() -> None:
    """Drop the cached aggregate - called after an ingest so the UI refreshes."""
    with _CACHE_LOCK:
        _CACHE.clear()


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
# Normalised-record key -> model column name.
#
# This is an explicit map rather than a list of shared names because the two
# vocabularies genuinely differ (the unified schema says ``timestamp``; the
# column is ``sampled_at``).  Getting that wrong makes ``setattr`` attach a
# plain, unmapped Python attribute, so the write silently does nothing.  It is
# validated against the real table below for exactly that reason.
_FIELD_MAP = {
    "region_id": "region_id",
    "region_distance_km": "region_distance_km",
    "latitude": "latitude",
    "longitude": "longitude",
    "timestamp": "sampled_at",
    "confidence_score": "confidence_score",
    "source_dataset": "source_dataset",
    "source_record_link": "source_record_link",
    "organization": "organization",
    "reference": "reference",
    "doi": "doi",
    "medium": "medium",
    "unit_family": "unit_family",
    "measured_value": "measured_value",
    "measured_unit": "measured_unit",
    "canonical_value": "canonical_value",
    "canonical_unit": "canonical_unit",
    "sampling_method": "sampling_method",
    "mesh_size_mm": "mesh_size_mm",
    "water_depth_m": "water_depth_m",
    "sample_depth_m": "sample_depth_m",
    "published_class": "published_class",
    "published_class_range": "published_class_range",
    "severity_label": "severity_label",
    "severity_ordinal": "severity_ordinal",
    "origin_status": "origin_status",
    "quality_note": "quality_note",
}


def _validate_field_map() -> None:
    """Fail loudly at import time if a mapped column does not exist."""
    columns = set(MicroplasticSample.__table__.columns.keys())
    unknown = {target for target in _FIELD_MAP.values() if target not in columns}
    if unknown:  # pragma: no cover - guards against a future typo
        raise RuntimeError(
            "microplastics field map references non-existent columns: "
            + ", ".join(sorted(unknown))
        )


_validate_field_map()


def persist_records(db: Session, records: list[dict]) -> dict:
    """Upsert normalised records keyed on ``(source, source_record_id)``."""
    inserted = 0
    updated = 0

    for record in records:
        existing = (
            db.query(MicroplasticSample)
            .filter(
                MicroplasticSample.source == record["source"],
                MicroplasticSample.source_record_id == record["source_record_id"],
            )
            .first()
        )
        if existing is None:
            row = MicroplasticSample(
                source=record["source"],
                source_record_id=record["source_record_id"],
            )
            for source_key, column in _FIELD_MAP.items():
                setattr(row, column, record.get(source_key))
            db.add(row)
            inserted += 1
        else:
            for source_key, column in _FIELD_MAP.items():
                if source_key in record:
                    setattr(existing, column, record.get(source_key))
            updated += 1

    db.commit()
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise a stored timestamp to UTC.

    A timezone-aware column comes back in the database session's offset, so the
    same instant would render as ``-08:00`` on one machine and ``+05:30`` on
    another.  Every other timestamp this platform emits is UTC, so pin it here
    once rather than at each of the consumers.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stored_to_normalized(row: MicroplasticSample) -> dict:
    """Reshape a stored row back into the normalised dict the scorers expect."""
    return {
        "region_id": row.region_id,
        "region_distance_km": row.region_distance_km,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "timestamp": _as_utc(row.sampled_at),
        "concentration_value": row.canonical_value,
        "source": row.source,
        "confidence_score": row.confidence_score,
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
        "origin_status": row.origin_status,
        "organization": row.organization,
        "doi": row.doi,
        "sampling_method": row.sampling_method,
    }


def load_records(db: Session) -> list[MicroplasticSample]:
    return (
        db.query(MicroplasticSample)
        .order_by(MicroplasticSample.sampled_at.asc().nullsfirst())
        .all()
    )


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------
def ingest(db: Session, limit: int = sources.NOAA_DEFAULT_LIMIT, bbox: dict | None = None) -> dict:
    """Run every connector, normalise, map to regions and persist."""
    connectors: list[dict] = []
    all_records: list[dict] = []
    rejection_total = 0

    noaa = sources.fetch_noaa_samples(bbox=bbox, limit=limit)
    connectors.append(noaa.as_status_dict())

    if noaa.found:
        normalized = normalize_batch(noaa.records)
        rejection_total += normalized["rejected_count"]
        all_records.extend(normalized["normalized"])

    literature = sources.fetch_literature_samples()
    connectors.append(literature.as_status_dict())

    if literature.found:
        normalized = normalize_literature_batch(literature.records)
        rejection_total += normalized["rejected_count"]
        all_records.extend(normalized["normalized"])

    nasa = sources.fetch_nasa_plastic_signal(bbox=bbox)
    connectors.append(nasa.as_status_dict())
    # NASA records, when the connector is implemented, normalise through a
    # dedicated path; today it contributes nothing, which is stated explicitly.

    regions = resolve_monitored_regions(db)
    mapping = assign_records(all_records, regions)

    persisted = (
        persist_records(db, all_records) if all_records
        else {"inserted": 0, "updated": 0, "total": 0}
    )
    clear_cache()

    return {
        "status": "OK" if all_records else "NO_DATA",
        "algorithm_version": ALGORITHM_VERSION,
        "regions_monitored": len(regions),
        "connectors": connectors,
        "normalisation": {
            "records_accepted": len(all_records),
            "records_rejected": rejection_total,
            "rejection_reason": (
                "Rejected records carried no usable sample position, value or unit."
                if rejection_total else None
            ),
        },
        "region_mapping": mapping,
        "persistence": persisted,
        "note": (
            "Only real published observations are written: NOAA NCEI records "
            "plus hand-curated peer-reviewed measurements keyed by DOI. This "
            "module never stores simulated or synthetic microplastic rows."
        ),
    }


# --------------------------------------------------------------------------
# Coverage / honesty reporting
# --------------------------------------------------------------------------
def coverage_report(db: Session) -> dict:
    """State exactly how much real evidence exists, and where the gaps are."""
    rows = load_records(db)

    if not rows:
        return {
            "has_data": False,
            "total_samples": 0,
            "reason": (
                "No microplastic samples stored. Run the ingestion endpoint to "
                "pull the NOAA NCEI collection and the curated literature file; "
                "until then this module has no evidence to show and will not "
                "estimate any."
            ),
            "by_medium": {},
            "by_unit_family": {},
            "regions_with_data": 0,
            "regions_total": db.query(OceanLocation).count(),
        }

    by_medium: dict[str, int] = {}
    by_family: dict[str, int] = {}
    unassigned = 0
    unknown_unit = 0

    for row in rows:
        by_medium[row.medium] = by_medium.get(row.medium, 0) + 1
        by_family[row.unit_family] = by_family.get(row.unit_family, 0) + 1
        if row.region_id is None:
            unassigned += 1
        if row.unit_family == FAMILY_UNKNOWN:
            unknown_unit += 1

    region_ids = {row.region_id for row in rows if row.region_id is not None}
    total_regions = db.query(OceanLocation).count()
    vintage = collection_vintage([
        {"timestamp": _as_utc(row.sampled_at)} for row in rows
    ])

    return {
        "has_data": True,
        "total_samples": len(rows),
        "by_medium": by_medium,
        "by_unit_family": by_family,
        "unit_family_notes": {
            family: FAMILY_DESCRIPTIONS.get(family, "")
            for family in by_family
        },
        "unassigned_samples": unassigned,
        "unmappable_unit_samples": unknown_unit,
        "regions_with_data": len(region_ids),
        "regions_total": total_regions,
        "regions_without_data": sorted(
            row.name
            for row in db.query(OceanLocation).all()
            if row.id not in region_ids
        ),
        "data_vintage": vintage,
        "honesty_note": (
            f"{len(rows)} real published samples cover {len(region_ids)} of "
            f"{total_regions} monitored regions. Regions not listed have no "
            "published microplastic sample and are shown as data gaps."
        ),
    }


# --------------------------------------------------------------------------
# Overview - the main payload behind the page
# --------------------------------------------------------------------------
def compute_overview(db: Session, radius_km: float = DEFAULT_RADIUS_KM) -> dict:
    """Everything the microplastics workspace needs, in one call."""
    rows = load_records(db)
    if not rows:
        return {
            "status": "NO_DATA",
            "algorithm_version": ALGORITHM_VERSION,
            "coverage": coverage_report(db),
            "hotspots": {
                "anomaly_category": ANOMALY_CATEGORY,
                "hotspot_count": 0,
                "hotspots": [],
                "recommendations": {
                    "summary": "No microplastic samples stored yet.",
                    "actions": [],
                },
            },
            "surfaces": {},
            "reason": (
                "Trigger an ingest to pull the NOAA NCEI collection and the "
                "curated literature file. Nothing is drawn until real samples "
                "exist."
            ),
        }

    records = [_stored_to_normalized(row) for row in rows]
    regions = resolve_monitored_regions(db)

    hotspot_payload = detect_hotspots(records, regions)

    # ---- surfaces, strictly one per unit family / medium ------------------
    surfaces: dict[str, dict] = {}
    for key, family_filter, medium_filter in (
        ("water_column", FAMILY_WATER, MEDIUM_WATER),
        ("sediment_dry_weight", FAMILY_SEDIMENT, MEDIUM_SEDIMENT),
        ("beach", FAMILY_WATER, MEDIUM_BEACH),
        ("beach_nurdle", None, MEDIUM_NURDLE),
    ):
        subset = [
            r for r in records
            if r.get("medium") == medium_filter
            and r.get("canonical_value") is not None
            and r.get("unit_family") != FAMILY_UNKNOWN
        ]
        if not subset:
            surfaces[key] = {
                "nodes": [],
                "has_data": False,
                "reason": f"No normalised samples for the '{medium_filter}' medium.",
                "unit": None,
            }
            continue

        latitudes = [r["latitude"] for r in subset]
        longitudes = [r["longitude"] for r in subset]
        bbox = {
            "lat_min": max(0.0, min(latitudes) - 1.0),
            "lat_max": max(latitudes) + 1.0,
            "lon_min": min(longitudes) - 1.0,
            "lon_max": max(longitudes) + 1.0,
        }
        samples = [
            {
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "value": r["canonical_value"],
            }
            for r in subset
        ]
        surface = build_surface(samples, bbox, radius_km=radius_km)
        surface["has_data"] = True
        surface["unit"] = subset[0].get("canonical_unit")
        surface["unit_family"] = subset[0].get("unit_family")
        surface["medium"] = medium_filter
        surface["sample_count"] = len(subset)
        # Attach the decay-based confidence so the UI can shade thin areas.
        for node in surface["nodes"]:
            node["confidence"] = distance_decay_confidence(
                node.get("nearest_km"), radius_km
            )
        surfaces[key] = surface

    return {
        "status": "OK",
        "algorithm_version": ALGORITHM_VERSION,
        "coverage": coverage_report(db),
        "hotspots": hotspot_payload,
        "surfaces": surfaces,
        "sources": sources.source_catalogue(),
        "measurement_discipline": {
            "rule": (
                "Concentrations are only ever aggregated within a single unit "
                "family. Water-column (pieces/m3), sediment (pieces/kg dw) and "
                "nurdle-patrol (pieces/10 min) values are never summed, averaged "
                "or ranked against each other."
            ),
            "families": {
                family: FAMILY_DESCRIPTIONS[family]
                for family in (FAMILY_WATER, FAMILY_SEDIMENT, FAMILY_NURDLE, FAMILY_UNKNOWN)
            },
        },
    }


def cached_overview(db: Session) -> dict:
    """Overview with the project's standard in-process TTL cache."""
    ttl = max(0, int(settings.MICROPLASTICS_CACHE_TTL_SECONDS))
    if ttl:
        cached = _cache_get("overview", ttl)
        if cached is not None:
            payload = dict(cached)
            payload["cache"] = {"hit": True, "ttl_seconds": ttl}
            return payload

    payload = compute_overview(db)
    if ttl:
        _cache_set("overview", payload)
    payload = dict(payload)
    payload["cache"] = {"hit": False, "ttl_seconds": ttl}
    return payload


# --------------------------------------------------------------------------
# Timeline for scrubbing
# --------------------------------------------------------------------------
def timeline(db: Session) -> dict:
    """Per-region, per-medium sample series for the time scrubber.

    Buckets are yearly because that is the real resolution of the source: the
    collection holds a few hundred samples spread over a decade, not a
    continuous series.  Monthly buckets would imply precision that is not there.
    """
    rows = load_records(db)
    dated = [(row, _as_utc(row.sampled_at)) for row in rows]
    dated = [(row, ts) for row, ts in dated if ts is not None]

    if not dated:
        return {
            "has_data": False,
            "buckets": [],
            "reason": (
                "No stored sample publishes a date, so no trend can be shown. "
                "A timeline is not estimated in its place."
            ),
        }

    region_names = {loc.id: loc.name for loc in db.query(OceanLocation).all()}
    buckets: dict[tuple, dict] = {}

    for row, sampled_at in dated:
        year = sampled_at.year
        key = (year, row.region_id, row.medium)
        value = row.canonical_value if row.canonical_value is not None else row.measured_value
        bucket = buckets.setdefault(key, {
            "year": year,
            "region_id": row.region_id,
            "region": region_names.get(row.region_id) or "Unassigned",
            "medium": row.medium,
            "unit": row.canonical_unit or (row.measured_unit or "unknown"),
            "values": [],
            "ordinals": [],
        })
        if value is not None:
            bucket["values"].append(value)
        if row.severity_ordinal is not None:
            bucket["ordinals"].append(row.severity_ordinal)

    output = []
    for bucket in buckets.values():
        values = bucket.pop("values")
        ordinals = bucket.pop("ordinals")
        bucket["n_samples"] = len(values)
        bucket["mean"] = round(sum(values) / len(values), 6) if values else None
        bucket["max"] = round(max(values), 6) if values else None
        bucket["worst_ordinal"] = max(ordinals) if ordinals else None
        output.append(bucket)

    output.sort(key=lambda b: (b["year"], b["region"], b["medium"]))

    years = sorted({b["year"] for b in output})
    return {
        "has_data": True,
        "bucket_resolution": "year",
        "years": years,
        "buckets": output,
        "reason": None,
        "honesty_note": (
            "The source publishes discrete survey samples, not a continuous "
            "series. Buckets are yearly so the scrubber never implies more "
            "temporal resolution than exists."
        ),
    }


# --------------------------------------------------------------------------
# Alert emission into the platform's existing alert store
# --------------------------------------------------------------------------
def emit_alerts(db: Session, min_priority: float = 60.0) -> dict:
    """Raise microplastic hotspots as OceanAlert rows.

    Idempotent: an active alert of the same type already attached to the same
    location is refreshed rather than duplicated, so this can be called from a
    scheduler without accumulating noise.
    """
    from app.models.alert import OceanAlert

    overview_hotspots = compute_overview(db)["hotspots"]["hotspots"]
    eligible = [
        h for h in overview_hotspots
        if h["is_hotspot"] and h["priority"] >= min_priority
    ]

    created = 0
    refreshed = 0
    for hotspot in eligible:
        alert_type = f"microplastic_hotspot_{hotspot['medium']}"
        existing = (
            db.query(OceanAlert)
            .filter(
                OceanAlert.location_id == hotspot["region_id"],
                OceanAlert.alert_type == alert_type,
                OceanAlert.status == "active",
            )
            .first()
        )

        stats = hotspot["statistics"]
        unit = hotspot["unit"]
        description = (
            f"{ANOMALY_CATEGORY} - {hotspot['medium_display']} at "
            f"{hotspot['region']}: source class "
            f"'{hotspot['published_class'] or hotspot['severity_label']}', "
            f"peak {stats['max']:g} {unit} across {stats['n_samples']} published "
            f"sample(s), newest {str(hotspot['latest_sample_at'])[:10]}. "
            f"Recommended action: {hotspot['action'].replace('_', ' ').lower()}. "
            f"priority {hotspot['priority']:.0f}/100. "
            "Archival or curated published evidence, not a live measurement."
        )

        if existing is None:
            db.add(OceanAlert(
                location_id=hotspot["region_id"],
                alert_type=alert_type,
                severity=hotspot["severity"],
                description=description[:2000],
                confidence=round(hotspot["confidence"] / 100.0, 3),
                latitude=hotspot["latitude"],
                longitude=hotspot["longitude"],
                source="microplastics",
                status="active",
            ))
            created += 1
        else:
            existing.severity = hotspot["severity"]
            existing.description = description[:2000]
            existing.confidence = round(hotspot["confidence"] / 100.0, 3)
            refreshed += 1

    db.commit()
    return {
        "evaluated": len(overview_hotspots),
        "eligible": len(eligible),
        "created": created,
        "refreshed": refreshed,
        "min_priority": min_priority,
        "note": (
            "Alerts describe archival, published observations. They carry "
            "source='microplastics' so they are distinguishable from live "
            "anomaly alerts elsewhere in the platform."
        ),
    }
