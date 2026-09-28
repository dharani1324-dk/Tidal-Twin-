"""
TidalTwin - Deoxygenation: engine
==================================
Orchestrates the module end to end and owns the honesty contract for the API:

    fetch (sources) -> normalise -> map (regions)
        -> persist (DissolvedOxygenSample) -> score (hotspots) -> trends -> project

DESIGN NOTES
------------
* ``ingest()`` is idempotent.  Rows are matched on
  ``(source, source_record_id)``, so re-running the connector updates rather
  than duplicates.

* The overview payload is cached in-process with a TTL, the same pattern the
  TIDE engine uses.  There is no Redis in this project and no reason to add one.

* Nothing here fabricates.  Every empty result carries a reason, and the
  coverage report states how much of the picture is real measurements versus
  interpolation.

* Simulated or synthetic rows are never written by this module.  Everything it
  stores is an actual published observation with ``origin_status="REAL"``.
  Literature references are REAL published data, clearly labelled.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.dissolved_oxygen import DissolvedOxygenSample
from app.models.location import OceanLocation
from app.modules.ai.deoxygenation import sources
from app.modules.ai.deoxygenation.hotspots import (
    ANOMALY_CATEGORY,
    detect_hypoxic_hotspots,
)
from app.modules.ai.deoxygenation.normalize import normalize_batch
from app.modules.ai.deoxygenation.regions import (
    DEFAULT_RADIUS_KM,
    MAX_ASSIGNMENT_RADIUS_KM,
    assign_records,
    resolve_monitored_regions,
)
from app.modules.ai.deoxygenation.trends import (
    analyze_trends,
    project_hypoxic_expansion as trends_project_hypoxic_expansion,
)
from app.modules.ai.deoxygenation.zones import ZONE_GRID_STEP, build_zones

logger = logging.getLogger("tidaltwin.deoxygenation.engine")

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
_FIELD_MAP = {
    "region_id": "region_id",
    "region_distance_km": "region_distance_km",
    "latitude": "latitude",
    "longitude": "longitude",
    "sampled_at": "sampled_at",
    "confidence_score": "confidence_score",
    "source_dataset": "source_dataset",
    "source_record_link": "source_record_link",
    "organization": "organization",
    "reference": "reference",
    "doi": "doi",
    "do_umol_kg": "do_umol_kg",
    "do_mg_l": "do_mg_l",
    "depth_m": "depth_m",
    "temperature_c": "temperature_c",
    "salinity_psu": "salinity_psu",
    "pressure_dbar": "pressure_dbar",
    "severity_label": "severity_label",
    "severity_ordinal": "severity_ordinal",
    "is_hypoxic": "is_hypoxic",
    "is_dead_zone": "is_dead_zone",
    "origin_status": "origin_status",
    "qc_flag": "qc_flag",
    "quality_note": "quality_note",
    "source_file": "source_file",
    "float_id": "float_id",
    "cycle": "cycle",
}


def _validate_field_map() -> None:
    """Fail loudly at import time if a mapped column does not exist."""
    columns = set(DissolvedOxygenSample.__table__.columns.keys())
    unknown = {target for target in _FIELD_MAP.values() if target not in columns}
    if unknown:
        raise RuntimeError(
            "deoxygenation field map references non-existent columns: "
            + ", ".join(sorted(unknown))
        )


_validate_field_map()


def persist_records(db: Session, records: list[dict]) -> dict:
    """Upsert normalised records keyed on ``(source, source_record_id)``."""
    inserted = 0
    updated = 0

    for record in records:
        existing = (
            db.query(DissolvedOxygenSample)
            .filter(
                DissolvedOxygenSample.source == record["source"],
                DissolvedOxygenSample.source_record_id == record["source_record_id"],
            )
            .first()
        )
        if existing is None:
            row = DissolvedOxygenSample(
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
    """Normalise a stored timestamp to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stored_to_normalized(row: DissolvedOxygenSample) -> dict:
    """Reshape a stored row back into the normalised dict the scorers expect."""
    return {
        "region_id": row.region_id,
        "region_distance_km": row.region_distance_km,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "sampled_at": _as_utc(row.sampled_at),
        "do_umol_kg": row.do_umol_kg,
        "do_mg_l": row.do_mg_l,
        "depth_m": row.depth_m,
        "temperature_c": row.temperature_c,
        "salinity_psu": row.salinity_psu,
        "pressure_dbar": row.pressure_dbar,
        "severity_label": row.severity_label,
        "severity_ordinal": row.severity_ordinal,
        "is_hypoxic": row.is_hypoxic,
        "is_dead_zone": row.is_dead_zone,
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
        "qc_flag": row.qc_flag,
        "quality_note": row.quality_note,
        "source_file": row.source_file,
    }


def load_records(db: Session) -> list[DissolvedOxygenSample]:
    return (
        db.query(DissolvedOxygenSample)
        .order_by(DissolvedOxygenSample.sampled_at.asc().nullsfirst())
        .all()
    )


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------
def ingest(
    db: Session,
    limit: int = sources.ARGO_BGC_DEFAULT_LIMIT,
    since_days: int | None = None,
    only_wmos: list[str] | None = None,
    include_literature: bool = True,
) -> dict:
    """Run every connector, normalise, map to regions and persist.

    The Argo BGC connector returns MEASURED oxygen levels read out of the
    downloaded per-profile NetCDFs, so the records persisted here carry a real
    ``DOXY`` value and its QC flag.  No connector in this path synthesises an
    oxygen reading, and a connector that cannot reach its source reports the
    reason rather than returning an empty success.
    """
    connectors: list[dict] = []
    all_records: list[dict] = []
    rejection_total = 0

    # 1. Argo BGC DOXY - the primary, instrument-grade source.
    argo = sources.fetch_argo_bgc_profiles(
        limit=limit,
        since_days=since_days if since_days is not None else 120,
        only_wmos=only_wmos,
    )
    connectors.append(argo.as_status_dict())
    if argo.found:
        normalized = normalize_batch(argo.records, source_type="argo_doxy_level")
        rejection_total += normalized["rejected_count"]
        all_records.extend(normalized["normalized"])

    # 2. NOAA Hypoxia Watch - currently unavailable; reports its own reason.
    noaa = sources.fetch_noaa_hypoxia_samples()
    connectors.append(noaa.as_status_dict())
    if noaa.found:
        normalized = normalize_batch(noaa.records, source_type="noaa_hypoxia")
        rejection_total += normalized["rejected_count"]
        all_records.extend(normalized["normalized"])

    # 3. Published literature reference points (lower confidence, labelled).
    if include_literature:
        literature = sources.fetch_literature_references()
        connectors.append(literature.as_status_dict())
        if literature.found:
            normalized = normalize_batch(literature.records, source_type="literature")
            rejection_total += normalized["rejected_count"]
            all_records.extend(normalized["normalized"])

    # Map to the monitored coastal regions.  Samples further than
    # MAX_ASSIGNMENT_RADIUS_KM from every region stay unassigned rather than
    # being snapped to a distant coast.
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
                "Rejected records carried no finite oxygen value, position or depth."
                if rejection_total else None
            ),
        },
        "region_mapping": mapping,
        "persistence": persisted,
        "note": (
            "Only real published observations are written. Primary oxygen values are "
            "measured DOXY levels from Argo BGC float profiles, each stored with its "
            "source file, cycle, QC flag and a link to the published NetCDF. Curated "
            "literature reference points are labelled and stored at reduced confidence. "
            "This module never writes simulated or synthetic oxygen rows, and never "
            "substitutes an estimate for a source it could not reach."
        ),
    }


def map_to_regions(db: Session) -> dict:
    """Assign still-unassigned oxygen samples to the monitored coastal regions.

    Reuses the same nearest-region assignment and distance-decay confidence that
    ``ingest()`` applies, so a backfill of older rows scores identically to rows
    assigned at ingest time.  Samples further than MAX_ASSIGNMENT_RADIUS_KM from
    every region stay unassigned and are reported as such - they are never
    snapped to a distant coast.
    """
    regions = resolve_monitored_regions(db)
    if not regions:
        return {
            "assigned": 0,
            "skipped": 0,
            "message": "No monitored regions are configured in ocean_locations.",
        }

    unassigned = (
        db.query(DissolvedOxygenSample)
        .filter(DissolvedOxygenSample.region_id.is_(None))
        .all()
    )
    if not unassigned:
        return {
            "assigned": 0,
            "skipped": 0,
            "message": "No unassigned oxygen samples; every stored sample already has a region.",
        }

    candidates = [
        {
            "region_id": row.id,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "sampled_at": row.sampled_at,
        }
        for row in unassigned
    ]
    mapping = assign_records(candidates, regions)

    assigned = 0
    for row, candidate in zip(unassigned, candidates):
        if candidate.get("region_id") is None:
            continue
        row.region_id = candidate["region_id"]
        row.region_distance_km = candidate.get("region_distance_km")
        row.confidence_score = candidate.get("confidence_score")
        assigned += 1

    db.commit()
    clear_cache()

    return {
        "assigned": assigned,
        "skipped": len(unassigned) - assigned,
        "max_radius_km": MAX_ASSIGNMENT_RADIUS_KM,
        "region_counts": mapping,
    }


# --------------------------------------------------------------------------
# Trend / projection entry points used by the API layer
# --------------------------------------------------------------------------
def trend_analysis(db: Session, region_id: int | None = None) -> dict:
    """Oxygen trend analysis per monitored region.

    The API layer calls this rather than the pure ``trends.analyze_trends``
    helper because region *names* live in the database, not in the sample
    records.  This resolves the regions once and passes the name mapping down.
    """
    rows = load_records(db)
    if not rows:
        return {
            "status": "NO_DATA",
            "regions": {},
            "reason": (
                "No dissolved oxygen samples stored. Ingest Argo BGC DOXY data "
                "before requesting trends."
            ),
        }

    records = [_stored_to_normalized(row) for row in rows]
    regions = resolve_monitored_regions(db)
    payload = analyze_trends(records, region_id=region_id, regions=regions)
    payload["status"] = "OK"
    payload["samples_analysed"] = len(records)
    return payload


def project_hypoxic_expansion(
    db: Session, region_id: int, horizon_days: int = 30
) -> dict:
    """Statistical PROJECTION of hypoxic extent for one region (not a forecast)."""
    rows = load_records(db)
    if not rows:
        return {
            "status": "NO_DATA",
            "region_id": region_id,
            "horizon_days": horizon_days,
            "projection": None,
            "message": (
                "No dissolved oxygen samples stored, so there is no basis for a "
                "projection. Ingest Argo BGC DOXY data first."
            ),
        }

    records = [_stored_to_normalized(row) for row in rows]
    regions = resolve_monitored_regions(db)
    region = next((r for r in regions if r["region_id"] == region_id), None)
    if region is None:
        known = [r["region_id"] for r in regions]
        return {
            "status": "UNKNOWN_REGION",
            "region_id": region_id,
            "known_region_ids": known,
            "projection": None,
            "message": (
                f"region_id {region_id} is not a monitored region. "
                f"Known ids: {known}"
            ),
        }

    projection = trends_project_hypoxic_expansion(
        records, region, horizon_days=horizon_days
    )
    projection["anomaly_category"] = ANOMALY_CATEGORY
    return projection


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
                "No dissolved oxygen samples stored. Run the ingestion endpoint to "
                "pull Argo BGC, NOAA Hypoxia, and literature data; "
                "until then this module has no evidence to show and will not "
                "estimate any."
            ),
            "by_region": {},
            "by_source": {},
            "by_severity": {},
            "regions_with_data": 0,
            "regions_total": db.query(OceanLocation).count(),
        }

    by_region: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    unassigned = 0
    hypoxic_count = 0
    dead_zone_count = 0

    for row in rows:
        # By region
        if row.region_id:
            loc = db.query(OceanLocation).filter(OceanLocation.id == row.region_id).first()
            region_name = loc.name if loc else f"Region {row.region_id}"
            by_region[region_name] = by_region.get(region_name, 0) + 1
        else:
            unassigned += 1
        
        # By source
        src = row.source.split("(")[0].strip() if "(" in row.source else row.source
        by_source[src] = by_source.get(src, 0) + 1
        
        # By severity
        sev = row.severity_label or "UNKNOWN"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        
        if row.is_hypoxic:
            hypoxic_count += 1
        if row.is_dead_zone:
            dead_zone_count += 1

    region_ids = {row.region_id for row in rows if row.region_id is not None}
    total_regions = db.query(OceanLocation).count()

    return {
        "has_data": True,
        "total_samples": len(rows),
        "by_region": by_region,
        "by_source": by_source,
        "by_severity": by_severity,
        "hypoxic_samples": hypoxic_count,
        "dead_zone_samples": dead_zone_count,
        "unassigned_samples": unassigned,
        "regions_with_data": len(region_ids),
        "regions_total": total_regions,
        "regions_without_data": sorted(
            row.name
            for row in db.query(OceanLocation).all()
            if row.id not in region_ids
        ),
        "honesty_note": (
            f"{len(rows)} real published samples cover {len(region_ids)} of "
            f"{total_regions} monitored regions. Regions not listed have no "
            "published oxygen sample and are shown as data gaps. "
            f"{hypoxic_count} samples indicate hypoxia (<2 mg/L); "
            f"{dead_zone_count} indicate dead zone conditions (<0.5 mg/L)."
        ),
    }


def build_oxygen_zones(
    db: Session,
    band: str | None = None,
    min_depth: float | None = None,
    max_depth: float | None = None,
) -> dict:
    """Aggregate measured oxygen onto a 0.5-degree grid, per depth window.

    This is the plan-view counterpart to the region-scoped hotspots.  The 8
    monitored regions are coastal, so a float sitting in the open Arabian Sea
    OMZ - hundreds of kilometres from any of them - is correctly left
    unassigned and would otherwise never appear in any aggregate.  The zone
    grid needs no region, so the open-ocean oxygen minimum zone shows up here.

    Every cell is built only from stored real measurements and carries its own
    ``n_samples`` / ``n_floats`` so thin evidence is visible rather than hidden
    behind an average.
    """
    rows = load_records(db)
    if not rows:
        return {
            "has_data": False,
            "grid_step_deg": ZONE_GRID_STEP,
            "zones": [],
            "zone_count": 0,
            "dead_zone_count": 0,
            "cells_with_data": 0,
            "reason": (
                "No dissolved oxygen samples stored. Ingest Argo BGC DOXY data to "
                "build the oxygen grid; nothing is drawn until real samples exist."
            ),
        }

    records = [_stored_to_normalized(row) for row in rows]
    payload = build_zones(
        records, band=band, min_depth=min_depth, max_depth=max_depth
    )
    payload["has_data"] = True
    return payload


# --------------------------------------------------------------------------
# Overview - the main payload behind the page
# --------------------------------------------------------------------------
def compute_overview(db: Session, radius_km: float = DEFAULT_RADIUS_KM) -> dict:
    """Everything the deoxygenation workspace needs, in one call."""
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
                    "summary": "No dissolved oxygen samples stored yet.",
                    "actions": [],
                },
            },
            "trends": {"regions": {}},
            "reason": (
                "Trigger an ingest to pull Argo BGC floats, NOAA Hypoxia Watch, "
                "and literature references. Nothing is drawn until real samples "
                "exist."
            ),
        }

    records = [_stored_to_normalized(row) for row in rows]
    regions = resolve_monitored_regions(db)

    # Hotspots
    hotspot_payload = detect_hypoxic_hotspots(records, regions)

    # Trends
    trends_payload = analyze_trends(records)

    # Open-ocean oxygen grid. Region hotspots only cover the 8 coastal
    # monitored regions, so this is what shows the offshore OMZ.
    zones_payload = build_zones(records)
    zones_payload["has_data"] = True

    return {
        "status": "OK",
        "algorithm_version": ALGORITHM_VERSION,
        "coverage": coverage_report(db),
        "hotspots": hotspot_payload,
        "trends": trends_payload,
        "zones": zones_payload,
        "sources": sources.source_catalogue(),
        "measurement_discipline": {
            "rule": (
                "Dissolved oxygen is stored in canonical umol/kg (Argo native) "
                "with derived mg/L. Hypoxia classified at ~2 mg/L (~62.5 umol/kg); "
                "dead zone at ~0.5 mg/L (~15.6 umol/kg). Values are never "
                "interpolated across gaps - gaps are explicitly reported."
            ),
            "region_vs_zone": (
                "Hotspots are scoped to the 8 coastal monitored regions, so a float "
                "beyond the 500 km mapping radius is stored unassigned and does not "
                "appear in a hotspot. The zones grid is region-independent and covers "
                "the full spatial extent of the ingested data, including offshore "
                "oxygen minimum zones."
            ),
            "severity_ladder": [
                {"ordinal": 1, "label": "NORMAL", "threshold_mg_l": ">6.0", "color": "#10b981"},
                {"ordinal": 2, "label": "LOW", "threshold_mg_l": "4.0-6.0", "color": "#22d3ee"},
                {"ordinal": 3, "label": "MODERATE", "threshold_mg_l": "2.0-4.0", "color": "#f59e0b"},
                {"ordinal": 4, "label": "HIGH (HYPOXIC)", "threshold_mg_l": "0.5-2.0", "color": "#f97316"},
                {"ordinal": 5, "label": "CRITICAL (DEAD ZONE)", "threshold_mg_l": "<0.5", "color": "#f43f5e"},
            ],
        },
    }


def cached_overview(db: Session, radius_km: float = DEFAULT_RADIUS_KM) -> dict:
    """Overview with the project's standard in-process TTL cache."""
    ttl = max(0, int(settings.DEOXYGENATION_CACHE_TTL_SECONDS))
    if ttl:
        cached = _cache_get("overview", ttl)
        if cached is not None:
            payload = dict(cached)
            payload["cache"] = {"hit": True, "ttl_seconds": ttl}
            return payload

    payload = compute_overview(db, radius_km)
    if ttl:
        _cache_set("overview", payload)
    payload = dict(payload)
    payload["cache"] = {"hit": False, "ttl_seconds": ttl}
    return payload


# --------------------------------------------------------------------------
# Alert emission into the platform's existing alert store
# --------------------------------------------------------------------------
def emit_alerts(db: Session, min_priority: float = 60.0) -> dict:
    """Raise hypoxic hotspots as OceanAlert rows.

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
        alert_type = f"hypoxic_zone_{hotspot['depth_layer']}"
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
            f"{ANOMALY_CATEGORY} - {hotspot['depth_layer']} water at "
            f"{hotspot['region']}: severity {hotspot['severity']}, "
            f"min O₂ {stats['min_do_mg_l']} {unit} across {stats['n_samples']} "
            f"sample(s), latest {str(hotspot['latest_sample_at'])[:10]}. "
            f"Trend: {hotspot['trend']}. "
            f"Recommended action: {hotspot['action'].replace('_', ' ').lower()}. "
            f"Priority {hotspot['priority']:.0f}/100. "
            f"Confidence {hotspot['confidence']}%. "
            "Based on real Argo BGC / NOAA / literature data."
        )

        if existing is None:
            db.add(OceanAlert(
                location_id=hotspot["region_id"],
                alert_type=alert_type,
                severity=hotspot["severity"].lower(),
                description=description[:2000],
                confidence=round(hotspot["confidence"] / 100.0, 3),
                latitude=hotspot["latitude"],
                longitude=hotspot["longitude"],
                source="deoxygenation",
                status="active",
            ))
            created += 1
        else:
            existing.severity = hotspot["severity"].lower()
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
            "Alerts describe real published observations from Argo BGC floats, "
            "NOAA Hypoxia Watch, and peer-reviewed literature. They carry "
            "source='deoxygenation' so they are distinguishable from other "
            "anomaly alerts in the platform."
        ),
    }