"""Shared provenance classification and basic quality checks for ocean records.

This module deliberately reports categorical evidence and validation flags rather
than an uncalibrated numeric quality score.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone


FIELD_UNITS = {
    "sea_surface_temperature": "degC",
    "wave_height": "m",
    "wave_direction": "degree",
    "salinity": "PSU",
    "current_speed": "m/s",
    "current_direction": "degree",
    "dissolved_oxygen": "source-dependent",
    "chlorophyll": "source-dependent",
    "ph": "pH",
    "pressure": "dbar or source-dependent",
    "density": "kg/m3",
    "nutrients": "source-dependent",
}

PHYSICAL_RANGES = {
    "sea_surface_temperature": (-2.5, 45.0),
    "wave_height": (0.0, 40.0),
    "wave_direction": (0.0, 360.0),
    "salinity": (0.0, 45.0),
    "current_speed": (0.0, 10.0),
    "current_direction": (0.0, 360.0),
    "dissolved_oxygen": (0.0, 600.0),
    "chlorophyll": (0.0, 1000.0),
    "ph": (0.0, 14.0),
    "pressure": (0.0, 12000.0),
    "density": (900.0, 1200.0),
    "nutrients": (0.0, 10000.0),
}


def origin_status(source: str | None, data_type: str | None) -> str:
    """Classify the value origin; Open-Meteo marine products are forecasts."""
    raw = f"{source or ''} {data_type or ''}".upper().replace("-", "_").replace(" ", "_")
    if any(tag in raw for tag in ("SIMULATED", "SIMULATION")):
        return "SIMULATED"
    if any(tag in raw for tag in ("SYNTHETIC", "DEMO")):
        return "SYNTHETIC"
    if any(tag in raw for tag in (
        "OPEN_METEO", "FORECAST", "MODEL", "VAM", "ANALYSIS", "OBJECTIVE", "GRIDDAP", "REANALYSIS",
    )):
        return "MODEL_DERIVED"
    if any(tag in raw for tag in ("SATELLITE", "VIIRS", "HIMAWARI", "OCEAN_COLOR", "OCM", "SAR", "ALTIMET")):
        return "SATELLITE_DERIVED"
    if "HISTORICAL" in raw or "ERSST" in raw or "CLIMATOLOGY" in raw:
        return "HISTORICAL"
    if any(tag in raw for tag in ("ARGO", "GLIDER", "BUOY", "CTD", "IN_SITU", "MEASUREMENT")):
        return "REAL"
    return "UNKNOWN"


#: Statuses a producer may assert explicitly on a row via ``data_status``.
EXPLICIT_STATUSES = ("REAL", "HISTORICAL", "MODEL_DERIVED", "SATELLITE_DERIVED", "SIMULATED", "SYNTHETIC")


def effective_origin_status(row) -> str:
    """Prefer the row's asserted ``data_status`` over string inference.

    Inference from a source name is only a fallback and it is ambiguous: an
    objective analysis *of* Argo floats contains the token ``ARGO`` but its
    values are analysis output, not measurements.  Letting the ingest path
    assert ``data_status`` explicitly keeps ``Indian_ARGO_Floats`` (``REAL``)
    and ``incois_argo_10d_VAM`` (``MODEL_DERIVED``) distinguishable even
    though both names contain "Argo".
    """
    asserted = getattr(row, "data_status", None)
    if asserted is not None:
        candidate = str(asserted).strip().upper()
        if candidate in EXPLICIT_STATUSES:
            return candidate
    return origin_status(getattr(row, "source", None), getattr(row, "data_type", None))


def _utc(timestamp: datetime) -> datetime:
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)


def assess_record(row, location=None, now: datetime | None = None) -> dict:
    """Return source-level provenance, completeness, freshness and range flags."""
    source = getattr(row, "source", None)
    data_type = getattr(row, "data_type", None)
    timestamp = getattr(row, "timestamp", None)
    status = effective_origin_status(row)
    values = {name: getattr(row, name, None) for name in FIELD_UNITS}
    source_key = (source or "").upper().replace("-", "_").replace(" ", "_")
    if "OPEN_METEO" in source_key:
        allowed = {"sea_surface_temperature", "wave_height", "wave_direction"}
        values = {name: value if name in allowed else None for name, value in values.items()}
    available = {name: value for name, value in values.items() if value is not None}
    flags: list[str] = []

    for name, value in available.items():
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            flags.append(f"{name}: non-numeric value")
            continue
        if not math.isfinite(numeric):
            flags.append(f"{name}: non-finite value")
            continue
        low, high = PHYSICAL_RANGES[name]
        if not low <= numeric <= high:
            flags.append(f"{name}: outside broad plausibility range [{low:g}, {high:g}] {FIELD_UNITS[name]}")

    expected_by_source = {
        "OPEN_METEO": ("sea_surface_temperature", "wave_height", "wave_direction"),
        "ARGO": ("sea_surface_temperature", "salinity", "pressure"),
        "GLIDER": ("sea_surface_temperature", "salinity", "pressure"),
        "CTD": ("sea_surface_temperature", "salinity", "pressure"),
    }
    expected = next((fields for key, fields in expected_by_source.items() if key in source_key),
                    ("sea_surface_temperature", "wave_height", "salinity", "current_speed"))
    present_expected = [field for field in expected if values[field] is not None]
    missing = [field for field in expected if values[field] is None]

    freshness = "UNKNOWN"
    age_hours = None
    lead_hours = None
    if timestamp is not None:
        now_utc = _utc(now or datetime.now(timezone.utc))
        ts_utc = _utc(timestamp)
        delta_hours = (now_utc - ts_utc).total_seconds() / 3600
        if status == "MODEL_DERIVED" and delta_hours < 0:
            lead_hours = round(-delta_hours, 1)
            freshness = "FORECAST"
        else:
            age_hours = round(max(0.0, delta_hours), 1)
            freshness = "FRESH" if age_hours <= 6 else "RECENT" if age_hours <= 48 else "STALE"

    coordinates = None
    spatial_validity = "LOCATION_UNAVAILABLE"
    if location is not None and getattr(location, "geom", None) is not None:
        try:
            from geoalchemy2.shape import to_shape
            point = to_shape(location.geom).centroid
            coordinates = {"latitude": point.y, "longitude": point.x, "crs": "EPSG:4326"}
            spatial_validity = "VALID" if -90 <= point.y <= 90 and -180 <= point.x <= 180 else "INVALID"
        except Exception:
            spatial_validity = "UNREADABLE"

    return {
        "status": status,
        "source": source or "unknown",
        "data_type": data_type or "unknown",
        "location": getattr(location, "name", None),
        "coordinates": coordinates,
        "timestamp": _utc(timestamp).isoformat() if timestamp is not None else None,
        "depth_m": getattr(row, "depth_m", None),
        "variables": {
            name: {"value": value, "unit": FIELD_UNITS[name], "status": status}
            for name, value in available.items()
        },
        "completeness": {"available": len(present_expected), "expected": len(expected),
                         "missing_variables": missing},
        "freshness": {"status": freshness, "age_hours": age_hours, "forecast_lead_hours": lead_hours},
        "spatial_validity": spatial_validity,
        "qc_status": "NOT_PROVIDED_BY_SOURCE",
        "quality_status": "LIMITED" if flags else "SCREENED_ONLY",
        "validation_flags": flags,
        "processing": "Stored source values; broad physical-range and location checks only. No source-specific QC was applied.",
    }