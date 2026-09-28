"""Source adapters into the shared MoES ocean record shape.

Normalization preserves each provider's event time and product type. A gridded
analysis remains MODEL_DERIVED; it is never recast as an instrument reading.
"""

from hashlib import sha256
from datetime import datetime, timezone

from app.schemas.moes import UnifiedOceanRecord


def _utc_instant(value: str | None) -> str | None:
    """Return a UTC ISO timestamp only when the source provides a timed instant."""
    if not value or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_argo_grid(payload: dict) -> list[dict]:
    if not payload.get("available"):
        return []
    variable = payload.get("variable")
    common_variable = "sea_water_temperature" if variable == "TEMP" else "sea_water_salinity"
    units = payload.get("unit")
    source_url = payload.get("source_url", "")
    dataset_id = payload.get("dataset_id", "incois_argo_10d_VAM")
    dataset_name = payload.get("dataset", "INCOIS ARGO 10-day Variational Analysis")
    observed_at = payload.get("time")
    retrieved_at = payload.get("request_succeeded_at") or payload.get("checked_at") or ""
    depth_m = payload.get("depth_m")
    records = []
    for cell in payload.get("cells", []):
        latitude = cell.get("latitude")
        longitude = cell.get("longitude")
        value = cell.get("value")
        identity = f"INCOIS|{dataset_id}|{variable}|{observed_at}|{depth_m}|{latitude}|{longitude}"
        record = UnifiedOceanRecord(
            record_id=sha256(identity.encode("utf-8")).hexdigest(),
            source_id="INCOIS",
            institution="Indian National Centre for Ocean Information Services",
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            category="gridded_ocean_analysis",
            variable=common_variable,
            value=value,
            units=units,
            observed_at=observed_at,
            retrieved_at=retrieved_at,
            latitude=latitude,
            longitude=longitude,
            depth_m=depth_m,
            data_status="MODEL_DERIVED",
            quality_status="RANGE_SCREENED",
            quality_flags=["ERDDAP_MISSING_SENTINELS_REMOVED", "BASIC_PHYSICAL_RANGE_SCREENED", "ANALYSIS_NOT_RAW_SENSOR"],
            source_url=source_url,
            attribution="INCOIS ERDDAP",
            license=payload.get("license"),
        )
        records.append(record.model_dump())
    return records


def normalize_indobis_occurrences(payload: dict) -> list[dict]:
    if not payload.get("available"):
        return []
    retrieved_at = payload.get("checked_at", "")
    records = []
    for item in payload.get("records", []):
        identity = str(item.get("id") or f"{item.get('scientific_name')}|{item.get('event_date')}|{item.get('latitude')}|{item.get('longitude')}")
        source_event_date = item.get("event_date")
        record = UnifiedOceanRecord(
            record_id=sha256(f"CMLRE|{identity}".encode("utf-8")).hexdigest(),
            source_id="CMLRE",
            institution="Centre for Marine Living Resources & Ecology / IndOBIS",
            dataset_id=str(item.get("dataset_id") or "indobis_occurrence"),
            dataset_name="IndOBIS marine species occurrences",
            category="biodiversity_occurrence",
            variable="species_occurrence",
            value=item.get("scientific_name"),
            units=None,
            observed_at=_utc_instant(source_event_date),
            retrieved_at=retrieved_at,
            latitude=item.get("latitude"),
            longitude=item.get("longitude"),
            depth_m=float(item["depth_m"]) if item.get("depth_m") not in (None, "") else None,
            data_status="HISTORICAL_OR_RECENT_OCCURRENCE",
            quality_status="PROVIDER_PUBLISHED_RECORD",
            quality_flags=["EVENT_DATE_MAY_BE_HISTORICAL", "NOT_ABUNDANCE_OR_LIVE_TRACK"],
            source_url=item.get("source_url") or payload.get("source_url", "https://indobis.in/"),
            attribution=item.get("institution") or "CMLRE / IndOBIS via OBIS",
            license=None,
            attributes={
                "basis_of_record": item.get("basis_of_record"),
                "institution_code": item.get("institution"),
                "event_date": source_event_date,
            },
        )
        records.append(record.model_dump())
    return records
