"""
TidalTwin - Acidification: engine
=================================
Orchestration layer: runs the connectors, normalises, maps to the 8 monitored
regions, persists idempotently, and produces the API payloads.

The persistence contract matches the deoxygenation module exactly - an upsert
on ``(source, source_record_id)`` - so re-running an ingest can never
half-apply or duplicate rows.
"""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.acidification import OceanAcidificationSample
from app.modules.ai.acidification import hotspots as _hotspots
from app.modules.ai.acidification import sources as _sources
from app.modules.ai.acidification import trends as _trends
from app.modules.ai.acidification import zones as _zones
from app.modules.ai.acidification.normalize import normalize_batch
from app.modules.ai.acidification.regions import (
    assign_records,
    resolve_monitored_regions,
)
from app.modules.ai.acidification.units import (
    ARAGONITE_SATURATION,
    DERIVED_OMEGA_NOTE,
    SEVERITY_ORDINAL_TO_LABEL,
    depth_band_for_depth,
)

logger = logging.getLogger("tidaltwin.acidification.engine")

ALGORITHM_VERSION = "1.0.0"

# Region attribution radius for this module. Wider than the deoxygenation
# module's 500 km, for a measured reason recorded in config.py: BGC floats
# sample open ocean, and the median pH observation sits 1047 km from the
# nearest of the 8 coastal labels. The shared haversine routing in
# ``regions.py`` is used unchanged - only this module's policy constant
# differs, and every attributed row still records its actual distance.
REGION_RADIUS_KM = float(settings.ACIDIFICATION_REGION_RADIUS_KM or 1500.0)

# Field map guards the hand-written column assignments below against model
# drift: a typo in a key would otherwise surface as a silently NULL column.
_FIELD_MAP = {
    "region_id",
    "region_distance_km",
    "source",
    "source_dataset",
    "source_record_id",
    "source_record_link",
    "organization",
    "reference",
    "doi",
    "float_id",
    "cycle",
    "source_file",
    "latitude",
    "longitude",
    "sampled_at",
    "ph_total",
    "ph_free",
    "omega_arag",
    "omega_calc",
    "omega_arag_derived",
    "dic_umol_kg",
    "pco2_uatm",
    "alk_umol_kg",
    "depth_m",
    "temperature_c",
    "salinity_psu",
    "pressure_dbar",
    "severity_label",
    "severity_ordinal",
    "is_acidic",
    "is_undersaturated",
    "confidence_score",
    "origin_status",
    "qc_flag",
    "quality_note",
    "source_file",
}

_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 300


def _validate_field_map() -> None:
    """Fail loudly at import if the model and the field map disagree."""
    columns = set(OceanAcidificationSample.__table__.columns.keys())
    unknown = _FIELD_MAP - columns
    if unknown:
        raise RuntimeError(
            f"acidification engine field map references unknown model columns: "
            f"{sorted(unknown)}"
        )


_validate_field_map()


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _cached(key: str, builder):
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL_SECONDS:
            return hit[1]
    value = builder()
    with _CACHE_LOCK:
        _CACHE[key] = (now, value)
    return value


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------
def ingest(
    db: Session,
    limit: int = _sources.ARGO_BGC_DEFAULT_LIMIT,
    since_days: int = 365,
    only_wmos: list[str] | None = None,
    include_secondary: bool = True,
) -> dict:
    """Run every connector, normalise, map to regions and persist."""
    connectors: list[dict] = []
    all_records: list[dict] = []
    rejected_total = 0
    rejected_implausible = 0
    rejected_no_ph = 0

    # 1. Argo BGC in-situ pH - primary instrument-grade source.
    argo = _sources.fetch_argo_bgc_ph_profiles(
        limit=limit,
        since_days=since_days,
        only_wmos=only_wmos,
    )
    connectors.append(argo.as_status_dict())
    if argo.found:
        normalized = normalize_batch(argo.records, source_type="argo_ph_level")
        rejected_total += normalized["rejected_count"]
        rejected_implausible += normalized.get("rejected_implausible", 0)
        rejected_no_ph += normalized.get("rejected_no_ph", 0)
        all_records.extend(normalized["normalized"])

    # 2. Secondary sources, each reporting its own honest status.
    if include_secondary:
        for secondary in _sources.fetch_secondary_sources():
            connectors.append(secondary.as_status_dict())
            if secondary.found and secondary.records:
                normalized = normalize_batch(
                    secondary.records, source_type="argo_ph_level"
                )
                rejected_total += normalized["rejected_count"]
                rejected_implausible += normalized.get("rejected_implausible", 0)
                rejected_no_ph += normalized.get("rejected_no_ph", 0)
                all_records.extend(normalized["normalized"])

    # Map to the monitored coastal regions (shared haversine routing).
    regions = resolve_monitored_regions(db)
    mapping = assign_records(all_records, regions, REGION_RADIUS_KM)

    persisted = (
        persist_records(db, all_records)
        if all_records
        else {"inserted": 0, "updated": 0, "total": 0}
    )
    clear_cache()

    rejection_reason = None
    if rejected_implausible or rejected_no_ph:
        rejection_reason = (
            f"{rejected_implausible} pH value(s) were rejected as physically "
            f"impossible for seawater (outside 7.4-8.6 on the total scale) and "
            f"{rejected_no_ph} level(s) carried no pH value at all. "
            "Real-time BGC pH sensors do report impossible values, so this count "
            "is the sensor health signal, not a bug."
        )

    return {
        "status": "OK" if all_records else "NO_DATA",
        "algorithm_version": ALGORITHM_VERSION,
        "regions_monitored": len(regions),
        "connectors": connectors,
        "normalisation": {
            "records_accepted": len(all_records),
            "records_rejected": rejected_total,
            "rejected_implausible": rejected_implausible,
            "rejected_no_ph": rejected_no_ph,
            "rejection_reason": rejection_reason,
        },
        "region_mapping": mapping,
        "persistence": persisted,
        "note": (
            "Only real published observations are written. pH is measured "
            "in-situ total scale from Argo BGC float profiles, each stored with "
            "its source file, cycle, QC flag and a link to the published NetCDF. "
            "Aragonite saturation is DERIVED by CO2SYS and stored in a separate, "
            "explicitly flagged field. This module never writes simulated or "
            "synthetic pH rows, and never substitutes an estimate for a source it "
            "could not reach."
        ),
    }


def persist_records(db: Session, records: list[dict]) -> dict:
    """Upsert on ``(source, source_record_id)`` so re-ingest is idempotent."""
    inserted = 0
    updated = 0
    for record in records:
        key = (record["source"], record["source_record_id"])
        existing = (
            db.query(OceanAcidificationSample)
            .filter(
                OceanAcidificationSample.source == key[0],
                OceanAcidificationSample.source_record_id == key[1],
            )
            .first()
        )
        payload = {k: v for k, v in record.items() if k in _FIELD_MAP}
        if existing is None:
            db.add(OceanAcidificationSample(**payload))
            inserted += 1
        else:
            for field, value in payload.items():
                setattr(existing, field, value)
            updated += 1
    db.commit()
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


def map_to_regions(db: Session) -> dict:
    """Re-run region assignment over stored samples (e.g. after seeding regions)."""
    samples = db.query(OceanAcidificationSample).all()
    if not samples:
        return {"assigned": 0, "unassigned": 0, "by_region": {}}

    regions = resolve_monitored_regions(db)
    records = [
        {
            "latitude": s.latitude,
            "longitude": s.longitude,
            "region_id": s.region_id,
            "region_distance_km": s.region_distance_km,
        }
        for s in samples
    ]
    mapping = assign_records(records, regions, REGION_RADIUS_KM)
    by_id = {r["region_id"]: r for r in regions}
    for sample, rec in zip(samples, records):
        sample.region_id = rec["region_id"]
        sample.region_distance_km = rec["region_distance_km"]
    db.commit()
    clear_cache()
    assigned = sum(1 for s in samples if s.region_id is not None)
    return {
        "assigned": assigned,
        "unassigned": len(samples) - assigned,
        "by_region": mapping,
        "regions": list(by_id.values()),
    }


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load_records(
    db: Session,
    region_id: int | None = None,
    min_severity: str | None = None,
    is_acidic: bool | None = None,
    is_undersaturated: bool | None = None,
    limit: int = 5000,
) -> list[dict]:
    """Load stored samples as plain dicts, newest first."""
    query = db.query(OceanAcidificationSample)
    if region_id is not None:
        query = query.filter(OceanAcidificationSample.region_id == region_id)
    if is_acidic is not None:
        query = query.filter(
            OceanAcidificationSample.is_acidic == int(bool(is_acidic))
        )
    if is_undersaturated is not None:
        query = query.filter(
            OceanAcidificationSample.is_undersaturated == int(bool(is_undersaturated))
        )
    if min_severity:
        threshold = _severity_ordinal(min_severity)
        if threshold is not None:
            query = query.filter(
                OceanAcidificationSample.severity_ordinal.isnot(None),
                OceanAcidificationSample.severity_ordinal >= threshold,
            )
    rows = (
        query.order_by(OceanAcidificationSample.sampled_at.desc().nullslast())
        .limit(limit)
        .all()
    )
    return [_sample_to_dict(r) for r in rows]


def _severity_ordinal(label: str) -> int | None:
    if not label:
        return None
    return next(
        (o for lbl, o in SEVERITY_ORDINAL_TO_LABEL.items() if lbl == label.upper()),
        None,
    )


def _sample_to_dict(row: OceanAcidificationSample) -> dict:
    return {
        "id": row.id,
        "region_id": row.region_id,
        "region_distance_km": row.region_distance_km,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "sampled_at": row.sampled_at,
        "depth_m": row.depth_m,
        "depth_band": depth_band_for_depth(row.depth_m),
        "ph_total": row.ph_total,
        "ph_free": row.ph_free,
        "omega_arag": row.omega_arag,
        "omega_calc": row.omega_calc,
        "omega_arag_derived": row.omega_arag_derived,
        "dic_umol_kg": row.dic_umol_kg,
        "pco2_uatm": row.pco2_uatm,
        "alk_umol_kg": row.alk_umol_kg,
        "temperature_c": row.temperature_c,
        "salinity_psu": row.salinity_psu,
        "pressure_dbar": row.pressure_dbar,
        "severity_label": row.severity_label,
        "severity_ordinal": row.severity_ordinal,
        "is_acidic": row.is_acidic,
        "is_undersaturated": row.is_undersaturated,
        "confidence_score": row.confidence_score,
        "origin_status": row.origin_status,
        "qc_flag": row.qc_flag,
        "source": row.source,
        "source_dataset": row.source_dataset,
        "source_record_link": row.source_record_link,
        "float_id": row.float_id,
        "cycle": row.cycle,
        "source_file": row.source_file,
        "organization": row.organization,
        "doi": row.doi,
    }


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------
def coverage_report(db: Session) -> dict:
    """Honest evidence report: what is actually stored, per region and source."""
    total = db.query(func.count(OceanAcidificationSample.id)).scalar() or 0
    by_region: dict[str, int] = {}
    for row in (
        db.query(
            OceanAcidificationSample.region_id,
            func.count(OceanAcidificationSample.id),
        )
        .group_by(OceanAcidificationSample.region_id)
        .all()
    ):
        by_region[str(row[0])] = row[1]

    by_source: dict[str, int] = {
        str(row[0]): row[1]
        for row in db.query(
            OceanAcidificationSample.source, func.count(OceanAcidificationSample.id)
        )
        .group_by(OceanAcidificationSample.source)
        .all()
    }
    by_severity: dict[str, int] = {
        str(row[0]): row[1]
        for row in db.query(
            OceanAcidificationSample.severity_label,
            func.count(OceanAcidificationSample.id),
        )
        .group_by(OceanAcidificationSample.severity_label)
        .all()
    }

    acidic = (
        db.query(func.count(OceanAcidificationSample.id))
        .filter(OceanAcidificationSample.is_acidic == 1)
        .scalar()
        or 0
    )
    undersat = (
        db.query(func.count(OceanAcidificationSample.id))
        .filter(OceanAcidificationSample.is_undersaturated == 1)
        .scalar()
        or 0
    )
    with_omega = (
        db.query(func.count(OceanAcidificationSample.id))
        .filter(OceanAcidificationSample.omega_arag.isnot(None))
        .scalar()
        or 0
    )
    unassigned = by_region.get("None", 0)

    regions = resolve_monitored_regions(db)
    regions_with_data = sum(1 for r in regions if by_region.get(str(r["region_id"]), 0))
    regions_without = [r["name"] for r in regions if not by_region.get(str(r["region_id"]))]

    return {
        "has_data": total > 0,
        "total_samples": total,
        "region_radius_km": REGION_RADIUS_KM,
        "by_region": by_region,
        "by_source": by_source,
        "by_severity": by_severity,
        "acidic_samples": acidic,
        "undersaturated_samples": undersat,
        "samples_with_derived_omega": with_omega,
        "unassigned_samples": unassigned,
        "regions_with_data": regions_with_data,
        "regions_total": len(regions),
        "regions_without_data": regions_without,
        "measurement_discipline": DERIVED_OMEGA_NOTE,
        "honesty_note": (
            "Counts reflect only rows actually stored from real Argo BGC pH "
            "observations. A region with no row means no float profile carrying "
            f"usable pH fell within {REGION_RADIUS_KM:.0f} km of it - that is "
            "absent evidence, not evidence of healthy conditions. Note that these "
            "floats sample open ocean, so region_distance_km on any given row is "
            "typically several hundred kilometres: an observation attributed to a "
            "coastal region is a basin-scale measurement, not a shore measurement."
        ),
    }


def build_acidification_zones(
    db: Session,
    band: str | None = None,
    min_depth: float | None = None,
    max_depth: float | None = None,
) -> dict:
    """Grid the stored samples for the plan-view / 3D heat layer."""
    records = load_records(db, limit=20000)
    out = _zones.build_zones(records, min_depth=min_depth, max_depth=max_depth, band=band)
    if not out["zones"]:
        return {
            "has_data": False,
            "reason": "No stored pH samples matched this depth window.",
            **out,
        }
    return {"has_data": True, **out}


def compute_overview(db: Session, radius_km: float = 250.0) -> dict:
    """The one-call payload the dashboard uses."""
    records = load_records(db, limit=20000)
    regions = resolve_monitored_regions(db)

    if not records:
        return {
            "status": "NO_DATA",
            "algorithm_version": ALGORITHM_VERSION,
            "regions_monitored": len(regions),
            "coverage": coverage_report(db),
            "hotspots": {
                "anomaly_category": _hotspots.ANOMALY_CATEGORY,
                "hotspot_count": 0,
                "hotspots": [],
                "recommendations": {
                    "summary": (
                        "No pH observations stored yet. Run an ingest to pull real "
                        "Argo BGC profiles."
                    ),
                    "actions": [],
                },
            },
            "trends": {"regions": {}},
            "zones": {"has_data": False, "zones": []},
            "sources": _sources.source_catalogue(),
            "measurement_discipline": DERIVED_OMEGA_NOTE,
        }

    hotspot_payload = _hotspots.detect_stress_zones(records, regions)
    trend_payload = _trends.analyze_trends(records, regions=regions)
    zone_payload = _zones.build_zones(records)

    phs = [r["ph_total"] for r in records if r.get("ph_total") is not None]
    omegas = [r["omega_arag"] for r in records if r.get("omega_arag") is not None]

    return {
        "status": "OK",
        "algorithm_version": ALGORITHM_VERSION,
        "regions_monitored": len(regions),
        "summary": {
            "n_samples": len(records),
            "min_ph": round(min(phs), 4) if phs else None,
            "mean_ph": round(sum(phs) / len(phs), 4) if phs else None,
            "max_ph": round(max(phs), 4) if phs else None,
            "min_omega_arag": round(min(omegas), 3) if omegas else None,
            "mean_omega_arag": round(sum(omegas) / len(omegas), 3) if omegas else None,
            "n_acidic": sum(1 for r in records if r.get("is_acidic")),
            "n_undersaturated": sum(
                1 for r in records if r.get("is_undersaturated")
            ),
            "n_floats": len({r.get("float_id") for r in records if r.get("float_id")}),
            "aragonite_saturation_threshold": ARAGONITE_SATURATION,
        },
        "coverage": coverage_report(db),
        "hotspots": hotspot_payload,
        "trends": trend_payload,
        "zones": {"has_data": True, **zone_payload},
        "sources": _sources.source_catalogue(),
        "measurement_discipline": DERIVED_OMEGA_NOTE,
    }


def cached_overview(db: Session, radius_km: float = 250.0) -> dict:
    """TTL-cached ``compute_overview``; the dashboard polls this."""
    return _cached(
        f"overview:{radius_km}", lambda: compute_overview(db, radius_km)
    )


def detect_stress_zones(
    db: Session, min_priority: float = 0.0
) -> dict:
    """Rank acidification stress zones from the stored samples.

    Façade over ``hotspots.detect_stress_zones`` so the API layer talks to one
    module. The region list is resolved here rather than in the caller, so a
    sample is never scored against a region set the caller forgot to load.
    """
    records = load_records(db, limit=20000)
    regions = resolve_monitored_regions(db)
    return _hotspots.detect_stress_zones(records, regions, min_priority=min_priority)


def trend_analysis(db: Session, region_id: int | None = None) -> dict:
    records = load_records(db, limit=20000)
    regions = resolve_monitored_regions(db)
    return _trends.analyze_trends(records, region_id=region_id, regions=regions)


def project_ph_decline(db: Session, region_id: int, horizon_days: int = 180) -> dict:
    records = load_records(db, limit=20000)
    regions = resolve_monitored_regions(db)
    region = next((r for r in regions if r["region_id"] == region_id), None)
    if region is None:
        return {
            "status": "UNKNOWN_REGION",
            "message": f"No monitored region with id {region_id}.",
        }
    out = _trends.project_ph_decline(records, region, horizon_days=horizon_days)
    out["anomaly_category"] = _hotspots.ANOMALY_CATEGORY
    return out


# --------------------------------------------------------------------------
# Decision intelligence integration
# --------------------------------------------------------------------------
def emit_alerts(db: Session, min_priority: float = 60.0) -> dict:
    """Raise acidification stress zones as OceanAlert rows.

    Idempotent: an active alert of the same type already attached to the same
    location is refreshed rather than duplicated, so this can be called from a
    scheduler without accumulating noise.
    """
    from app.models.alert import OceanAlert

    overview_hotspots = compute_overview(db)["hotspots"]["hotspots"]
    eligible = [
        h for h in overview_hotspots if h["is_hotspot"] and h["priority"] >= min_priority
    ]

    created = 0
    refreshed = 0
    for hotspot in eligible:
        alert_type = f"acidification_zone_{hotspot['depth_layer']}"
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
        omega = stats.get("min_omega_arag")
        omega_text = (
            f", minimum DERIVED aragonite saturation {omega}"
            f" ({'below' if omega < ARAGONITE_SATURATION else 'above'} the 1.0 "
            "saturation point)"
            if omega is not None
            else ", aragonite saturation not derivable on these levels"
        )
        description = (
            f"{_hotspots.ANOMALY_CATEGORY} - {hotspot['depth_layer']} water at "
            f"{hotspot['region']}: severity {hotspot['severity']}, "
            f"min pH {stats['min_ph']} across {stats['n_samples']} sample(s), "
            f"latest {str(hotspot['latest_sample_at'])[:10]}. "
            f"Trend: {hotspot['trend']}. "
            f"Recommended action: {hotspot['action'].replace('_', ' ').lower()}. "
            f"Priority {hotspot['priority']:.0f}/100. "
            f"Confidence {hotspot['confidence']}%. "
            f"Aragonite: {omega_text}. "
            "pH measured in-situ by Argo BGC floats; aragonite derived via CO2SYS. "
            f"{_hotspots.ANOMALY_CATEGORY} advisory: "
            f"{hotspot['recommendations'][0] if hotspot['recommendations'] else 'monitor'}"
        )

        if existing is None:
            db.add(
                OceanAlert(
                    location_id=hotspot["region_id"],
                    alert_type=alert_type,
                    severity=hotspot["alert_severity"],
                    description=description[:2000],
                    confidence=round(hotspot["confidence"] / 100.0, 3),
                    latitude=hotspot["latitude"],
                    longitude=hotspot["longitude"],
                    source="acidification",
                    status="active",
                )
            )
            created += 1
        else:
            existing.severity = hotspot["alert_severity"]
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
            "Alerts describe real measured in-situ pH from Argo BGC floats. They "
            "carry source='acidification' so they are distinguishable from other "
            "anomaly alerts in the platform, and every description states whether "
            "aragonite saturation was measured or derived."
        ),
    }
