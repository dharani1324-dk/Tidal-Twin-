"""
TidalTwin - Deoxygenation: normalize
=====================================
Normalises raw oxygen records from different sources into a unified schema
compatible with the DissolvedOxygenSample model.

Sources:
- Argo BGC float index metadata (DOXY measurements in NetCDF files)
- NOAA Hypoxia Watch CSV survey data
- Literature reference points

All outputs carry explicit provenance and confidence.
"""

from datetime import datetime, timezone
from typing import Any

from app.modules.ai.deoxygenation.units import (
    HYPOXIC_THRESHOLD_MG_L,
    SEVERITY_ORDINALS,
    severity_for_mg_l,
)


# Conversion factors
UMOL_KG_TO_MG_L = 0.032  # 1 umol/kg ≈ 0.032 mg/L (density ~1 kg/L)
MG_L_TO_UMOL_KG = 1 / UMOL_KG_TO_MG_L  # ~31.25

# Hypoxia thresholds
HYPOXIA_MG_L = HYPOXIC_THRESHOLD_MG_L
DEAD_ZONE_MG_L = 0.5
HYPOXIA_UMOL_KG = HYPOXIA_MG_L / UMOL_KG_TO_MG_L  # ~62.5
DEAD_ZONE_UMOL_KG = DEAD_ZONE_MG_L / UMOL_KG_TO_MG_L  # ~15.6


def _classify_severity(do_mg_l: float) -> tuple[str, int, int, int]:
    """Classify oxygen severity. Returns (label, ordinal, is_hypoxic, is_dead_zone).

    Delegates to ``units.severity_for_mg_l`` so ingest, the zone grid and the
    hotspot scorer cannot drift apart: this module previously carried its own
    copy of the ladder while ``units`` held a 0-based ladder with different
    breakpoints, which made a cell's stored ordinal render as the wrong label.
    """
    label, ordinal, is_hypoxic, is_dead_zone = severity_for_mg_l(do_mg_l)
    if label is None or ordinal is None:
        return "NORMAL", SEVERITY_ORDINALS["NORMAL"], 0, 0
    return label, ordinal, int(is_hypoxic), int(is_dead_zone)


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse various date formats to UTC datetime."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%Y%m%d%H%M%S",
        "%Y%m%d",
    ):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _safe_float(value: Any) -> float | None:
    """Safely convert to float, returning None for invalid values."""
    if value is None or value == "":
        return None
    try:
        f = float(value)
        return f if f == f else None  # NaN check
    except (ValueError, TypeError):
        return None


def normalize_argo_doxy_level(level: dict) -> dict | None:
    """Normalise ONE measured oxygen level from a real Argo BGC profile.

    This is the primary record shape for the module.  Unlike
    ``normalize_argo_bgc`` (which only reshapes float-index metadata and
    therefore cannot supply an oxygen value at all), every field the
    ``DissolvedOxygenSample`` table requires NOT NULL is populated from the
    measurement itself: ``do_umol_kg``, ``do_mg_l`` and ``depth_m``.

    The canonical unit is umol/kg exactly as Argo publishes it.  ``do_mg_l`` is
    a labelled approximation that assumes seawater density ~1 kg/L.

    Returns None if the level carries no finite oxygen value or no position, so
    padding cells can never reach the database.
    """
    do_umol_kg = _safe_float(level.get("do_umol_kg"))
    if do_umol_kg is None:
        return None

    lat = _safe_float(level.get("latitude"))
    lon = _safe_float(level.get("longitude"))
    if lat is None or lon is None:
        return None

    depth_m = _safe_float(level.get("depth_m"))
    if depth_m is None:
        return None
    # In-situ pressure can come back marginally negative when a float is
    # parked just above sea level. A negative depth is not a real measurement
    # and would fall outside every depth band, so clamp it to the surface.
    depth_m = max(0.0, depth_m)

    sampled_at = level.get("timestamp")
    if sampled_at is not None and sampled_at.tzinfo is None:
        sampled_at = sampled_at.replace(tzinfo=timezone.utc)

    float_id = level.get("float_id")
    cycle = level.get("cycle")
    source_file = level.get("source_file")
    source_url = level.get("source_url")
    depth_source = level.get("depth_source")

    do_mg_l = round(do_umol_kg * UMOL_KG_TO_MG_L, 4)
    severity_label, severity_ordinal, is_hypoxic, is_dead_zone = _classify_severity(do_mg_l)

    # Argo QC flag: 1 (good) and 2 (probably good) are usable; 3/4 are not.
    qc_flag = level.get("qc_flag")
    qc_usable = qc_flag in ("1", "2")
    confidence = 0.95 if qc_usable else 0.6

    notes = [
        "Measured dissolved oxygen from a real Argo BGC float profile "
        "(DOXY_ADJUSTED preferred over DOXY)."
    ]
    if depth_source == "PRES":
        notes.append(
            "Depth taken from in-situ pressure (PRES) because the file publishes "
            "no geometric DEPTH; 1 dbar approximates 1 m."
        )
    if not qc_usable:
        notes.append(
            f"Argo QC flag is {qc_flag or 'absent'} (not 1 or 2); value retained "
            "with reduced confidence."
        )

    # One measured level must map to exactly one row so re-running an ingest is
    # idempotent against the (source, source_record_id) unique constraint.
    # A BGC profile file stacks several sensor groups along the profile axis and
    # its optode samples repeat near-identical pressures, so depth alone is NOT
    # unique within a file - the profile and level indices are required.
    record_id = (
        f"{float_id or 'unknown'}_c{cycle}_{source_file or 'nofile'}"
        f"_p{level.get('profile_index')}_l{level.get('level_index')}"
    )

    return {
        "source": "Argo BGC float (real Argo GDAC)",
        "source_dataset": "Argo BGC profile (DOXY)",
        "source_record_id": record_id,
        "source_record_link": source_url,
        "organization": "Argo Program",
        "reference": "https://argo.ucsd.edu/",
        "doi": "10.17882/42182",
        "float_id": float_id,
        "cycle": cycle,
        "latitude": lat,
        "longitude": lon,
        "sampled_at": sampled_at,
        "do_umol_kg": do_umol_kg,
        "do_mg_l": do_mg_l,
        "depth_m": depth_m,
        "temperature_c": _safe_float(level.get("temperature_c")),
        "salinity_psu": _safe_float(level.get("salinity_psu")),
        "pressure_dbar": _safe_float(level.get("pressure_dbar")),
        "severity_label": severity_label,
        "severity_ordinal": severity_ordinal,
        "is_hypoxic": is_hypoxic,
        "is_dead_zone": is_dead_zone,
        "confidence_score": confidence,
        "origin_status": "REAL",
        "qc_flag": qc_flag,
        "quality_note": " ".join(notes),
        "source_file": source_file,
    }


def normalize_argo_bgc(record: dict) -> dict | None:
    """Normalize an Argo BGC float INDEX entry (metadata only, no oxygen value).

    Retained for provenance/lineage use only.  An index row describes *which*
    file holds a float profile; it contains no measurement.  Because the
    ``DissolvedOxygenSample`` table requires a real oxygen value, this function
    returns None unless the caller has already merged a measured level into the
    record - it will not fabricate one to satisfy a NOT NULL constraint.

    Use ``normalize_argo_doxy_level`` for anything destined for the database.
    """
    if _safe_float(record.get("do_umol_kg")) is None:
        return None

    return normalize_argo_doxy_level(
        {
            "do_umol_kg": record.get("do_umol_kg"),
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "depth_m": record.get("depth_m"),
            "timestamp": _parse_date(record.get("date")) if isinstance(record.get("date"), str) else record.get("date"),
            "float_id": record.get("float_id") or record.get("wmo"),
            "cycle": record.get("cycle"),
            "source_file": record.get("file_path"),
            "source_url": record.get("source_url"),
            "temperature_c": record.get("temperature_c"),
            "salinity_psu": record.get("salinity_psu"),
            "pressure_dbar": record.get("pressure_dbar"),
            "qc_flag": record.get("qc_flag"),
            "depth_source": record.get("depth_source"),
        }
    )


def normalize_noaa_hypoxia(record: dict) -> dict | None:
    """Normalize a NOAA Hypoxia Watch CSV record."""
    # Try various column names for lat/lon
    lat = None
    for key in ['latitude', 'LATITUDE', 'lat', 'Lat']:
        if key in record:
            lat = _safe_float(record[key])
            if lat is not None:
                break
    
    lon = None
    for key in ['longitude', 'LONGITUDE', 'lon', 'Lon', 'LONG']:
        if key in record:
            lon = _safe_float(record[key])
            if lon is not None:
                break
    
    if lat is None or lon is None:
        return None
    
    # Try various column names for oxygen
    do_mg_l = None
    for key in ['oxygen', 'DOXY', 'dissolved_oxygen', 'DO_mgL', 'DO_mg_l', 
                'oxygen_ml_l', 'O2_mg_L', 'oxygen_concentration']:
        if key in record:
            do_mg_l = _safe_float(record[key])
            if do_mg_l is not None:
                # Convert ml/L to mg/L if needed
                if key == 'oxygen_ml_l':
                    do_mg_l = do_mg_l * 1.43
                break
    
    if do_mg_l is None:
        return None
    
    # Depth
    depth_m = 0.0
    for key in ['depth', 'DEPTH', 'depth_m', 'pressure', 'PRESSURE']:
        if key in record:
            depth_m = _safe_float(record[key]) or 0.0
            break
    
    # Date
    sampled_at = None
    for key in ['date', 'DATE', 'time', 'TIME', 'sampled_at', 'sample_date']:
        if key in record:
            sampled_at = _parse_date(record[key])
            if sampled_at:
                break
    if sampled_at is None:
        sampled_at = datetime.now(timezone.utc)
    
    do_umol_kg = do_mg_l / UMOL_KG_TO_MG_L
    severity_label, severity_ordinal, is_hypoxic, is_dead_zone = _classify_severity(do_mg_l)
    
    source_dataset = record.get("_source_dataset", "NOAA Hypoxia Watch")
    source_record_id = f"noaa_hypoxia_{lat}_{lon}_{depth_m}_{sampled_at.isoformat()}"
    
    return {
        "source": "NOAA Hypoxia Watch",
        "source_dataset": source_dataset,
        "source_record_id": source_record_id,
        "source_record_link": None,
        "organization": "NOAA NCEI",
        "reference": "https://www.ncei.noaa.gov/products/hypoxia-watch",
        "doi": None,
        "float_id": None,
        "cycle": None,
        "latitude": lat,
        "longitude": lon,
        "sampled_at": sampled_at,
        "do_umol_kg": do_umol_kg,
        "do_mg_l": do_mg_l,
        "depth_m": depth_m,
        "temperature_c": _safe_float(record.get('temperature') or record.get('TEMP')),
        "salinity_psu": _safe_float(record.get('salinity') or record.get('PSAL')),
        "pressure_dbar": _safe_float(record.get('pressure') or record.get('PRES')),
        "severity_label": severity_label,
        "severity_ordinal": severity_ordinal,
        "is_hypoxic": is_hypoxic,
        "is_dead_zone": is_dead_zone,
        "confidence_score": 0.9,
        "origin_status": "REAL",
        "qc_flag": None,
        "quality_note": "NOAA hypoxia survey reference measurement",
        "source_file": None,
    }


def normalize_literature(record: dict) -> dict | None:
    """Normalize a literature reference point."""
    lat = _safe_float(record.get("lat") or record.get("latitude"))
    lon = _safe_float(record.get("lon") or record.get("longitude"))
    if lat is None or lon is None:
        return None
    
    do_mg_l = _safe_float(record.get("do_mg_l") or record.get("oxygen"))
    if do_mg_l is None:
        return None
    
    depth_m = _safe_float(record.get("depth_m") or record.get("depth")) or 0.0
    
    do_umol_kg = do_mg_l / UMOL_KG_TO_MG_L
    severity_label, severity_ordinal, is_hypoxic, is_dead_zone = _classify_severity(do_mg_l)
    
    source_record_id = f"literature_{record.get('name', '').lower().replace(' ', '_')}"
    
    return {
        "source": "Literature Reference (Indian Ocean OMZ/Hypoxia)",
        "source_dataset": "Published Oceanographic Literature",
        "source_record_id": source_record_id,
        "source_record_link": None,
        "organization": "Scientific Literature",
        "reference": record.get("reference"),
        "doi": None,
        "float_id": None,
        "cycle": None,
        "latitude": lat,
        "longitude": lon,
        # A curated literature value has no single observation date.  Storing
        # "now" would fabricate a timestamp and make the value look like a fresh
        # measurement to any recency-based scoring, so it stays NULL and the
        # record is labelled as a published reference instead.
        "sampled_at": _parse_date(record.get("date")),
        "do_umol_kg": do_umol_kg,
        "do_mg_l": do_mg_l,
        "depth_m": depth_m,
        "temperature_c": None,
        "salinity_psu": None,
        "pressure_dbar": None,
        "severity_label": severity_label,
        "severity_ordinal": severity_ordinal,
        "is_hypoxic": is_hypoxic,
        "is_dead_zone": is_dead_zone,
        "confidence_score": 0.7,
        "origin_status": "REAL",
        "qc_flag": None,
        "quality_note": f"Literature reference: {record.get('source', 'Published literature')}",
        "source_file": None,
    }


def normalize_batch(records: list[dict], source_type: str) -> dict:
    """Normalize a batch of records from a specific source."""
    normalizers = {
        "argo_bgc": normalize_argo_bgc,
        "argo_doxy_level": normalize_argo_doxy_level,
        "noaa_hypoxia": normalize_noaa_hypoxia,
        "literature": normalize_literature,
    }
    
    normalizer = normalizers.get(source_type)
    if not normalizer:
        return {"normalized": [], "rejected_count": len(records)}
    
    normalized = []
    rejected = 0
    
    for record in records:
        try:
            norm = normalizer(record)
            if norm is not None:
                normalized.append(norm)
            else:
                rejected += 1
        except Exception:
            rejected += 1
    
    return {"normalized": normalized, "rejected_count": rejected}