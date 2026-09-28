"""
TidalTwin - Microplastics: normalisation into the unified schema
================================================================
Turns a raw NOAA NCEI attribute dict into the unified record shape used
everywhere else in the platform:

    region_id, latitude, longitude, timestamp, concentration_value,
    source, confidence_score

extended with the fields this module genuinely needs in order to stay honest
(``unit_family``, ``measured_unit``, ``origin_status``, ``quality_note``).

WHAT NORMALISATION DELIBERATELY DOES NOT DO
-------------------------------------------
It does not convert ``pieces/kg dw`` into ``pieces/m3``.  There is no
defensible conversion: the relationship depends on sampling depth, grain size,
organic content and trawl mesh.  Rows keep their native unit, and the
``unit_family`` column is what stops a later aggregation from mixing them.

A row that cannot be placed in a family is stored with
``unit_family="unknown"`` and is excluded from scoring downstream - visible in
the coverage report, never silently dropped and never silently combined.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.modules.ai.microplastics.units import (
    FAMILY_UNKNOWN,
    MEDIUM_UNKNOWN,
    classify_medium,
    normalize_unit,
    severity_for,
)

# Values outside these broad plausibility bounds are flagged rather than
# trusted.  They are intentionally wide: this collection legitimately contains
# beach records in the tens of thousands per cubic metre.
PLAUSIBLE_VALUE_RANGE = (0.0, 1_000_000.0)


def _to_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric or numeric in (float("inf"), float("-inf")):  # NaN/inf
        return None
    return numeric


def _parse_epoch_ms(value) -> datetime | None:
    """NOAA publishes ``Date_m_d_yyyy`` as epoch milliseconds."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    try:
        # Millisecond epochs are ~1e12; a smaller number is probably seconds.
        seconds = numeric / 1000.0 if numeric > 1e11 else numeric
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _confidence(
    sampled_at: datetime | None,
    family: str,
    canonical_value: float | None,
    sample_depth_m: float | None,
    doi: str | None,
    now: datetime | None = None,
) -> tuple[float, list[str]]:
    """Transparent per-sample confidence in the *record*, not the ocean.

    Starts at 100 and subtracts for each documented weakness, so the number can
    always be reconstructed by reading this function.  It is deliberately not a
    claim about measurement accuracy, which the source does not publish.
    """
    score = 100.0
    notes: list[str] = []

    if sampled_at is None:
        score -= 25
        notes.append("no sample date published (-25)")
    else:
        current = now or datetime.now(timezone.utc)
        age_days = (current - sampled_at).days
        if age_days > 3650:
            score -= 25
            notes.append("sample older than 10 years (-25)")
        elif age_days > 1825:
            score -= 15
            notes.append("sample older than 5 years (-15)")

    if family == FAMILY_UNKNOWN:
        score -= 40
        notes.append("unit not recognised, excluded from aggregation (-40)")

    if canonical_value is None:
        score -= 30
        notes.append("no numeric concentration (-30)")
    elif not (PLAUSIBLE_VALUE_RANGE[0] <= canonical_value <= PLAUSIBLE_VALUE_RANGE[1]):
        score -= 30
        notes.append("concentration outside broad plausibility range (-30)")

    if sample_depth_m is None:
        score -= 5
        notes.append("no sample depth published (-5)")

    if not (doi or "").strip():
        score -= 5
        notes.append("no DOI (-5)")

    return max(0.0, min(100.0, round(score, 1))), notes


def normalize_noaa_record(attrs: dict, now: datetime | None = None) -> dict | None:
    """Convert one NOAA NCEI attribute dict into the unified sample shape.

    Returns ``None`` only when the record carries no usable position, because a
    microplastic sample with no location cannot be mapped, plotted or scored.
    Every other weakness is expressed in the returned flags instead.
    """
    if not isinstance(attrs, dict):
        return None

    latitude = _to_float(attrs.get("Latitude__degree_"))
    longitude = _to_float(attrs.get("Longitude_degree_"))
    if latitude is None or longitude is None:
        return None

    # Some sources publish 0-360 longitude.  Wrap BEFORE validating, otherwise
    # a perfectly valid 0-360 record is discarded as out of range.
    if 180.0 < longitude <= 360.0:
        longitude -= 360.0

    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None

    source_medium = attrs.get("Medium")
    medium, medium_family = classify_medium(source_medium)

    measured_unit = attrs.get("Unit")
    canonical_unit, factor, unit_family = normalize_unit(measured_unit)

    # When the unit carries no family, fall back to what the medium implies
    # only if the unit is absent entirely - never overrule a stated unit.
    if unit_family == FAMILY_UNKNOWN and not (measured_unit or "").strip() and medium_family != FAMILY_UNKNOWN:
        unit_family = medium_family
        canonical_unit = None

    measured_value = _to_float(attrs.get("Microplastics_measurement"))
    canonical_value = (
        round(measured_value * factor, 8)
        if (measured_value is not None and canonical_unit is not None)
        else None
    )

    sampled_at = _parse_epoch_ms(attrs.get("Date_m_d_yyyy"))
    sample_depth_m = _to_float(attrs.get("Water_Sample_Depth__m_"))
    doi = attrs.get("DOI")

    label, ordinal, severity_note = severity_for(
        value=canonical_value if canonical_value is not None else measured_value,
        medium=medium,
        family=unit_family,
        published_class=attrs.get("Concentration_class_text"),
    )

    confidence, confidence_notes = _confidence(
        sampled_at, unit_family, canonical_value, sample_depth_m, doi, now=now
    )

    quality_notes = confidence_notes + [severity_note]
    if medium == MEDIUM_UNKNOWN:
        quality_notes.append(
            f"marine setting '{source_medium}' not recognised; medium left unknown"
        )
    if canonical_value is None and measured_value is not None:
        quality_notes.append(
            f"unit '{measured_unit}' could not be normalised; native value kept only"
        )

    record_id = attrs.get("OBJECTID")
    if record_id is None:
        # Without a stable id we cannot deduplicate on re-ingest, so derive one
        # from the full tuple rather than inventing a sequence number.
        record_id = (
            f"{latitude:.5f}_{longitude:.5f}_"
            f"{sampled_at.timestamp() if sampled_at else 'nodate'}_"
            f"{measured_value if measured_value is not None else 'noval'}"
        )

    accession = attrs.get("NCEI_Accession_No")
    link = (
        f"https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id={accession}"
        if accession
        else None
    )

    return {
        # ---- the unified schema ------------------------------------------
        "region_id": None,          # resolved by the region mapping layer
        "region_distance_km": None,
        "latitude": round(latitude, 5),
        "longitude": round(longitude, 5),
        "timestamp": sampled_at,
        "concentration_value": canonical_value,
        "source": "NOAA NCEI Marine Microplastics",
        "confidence_score": confidence,
        # ---- provenance ---------------------------------------------------
        "source_dataset": "Global Marine Microplastics Database (1972-present)",
        "source_record_id": str(record_id),
        "source_record_link": link,
        "organization": attrs.get("ORGANIZATION"),
        "reference": attrs.get("Short_Reference"),
        "doi": doi,
        # ---- what was measured --------------------------------------------
        "medium": medium,
        "source_medium": source_medium,
        "unit_family": unit_family,
        "measured_value": measured_value,
        "measured_unit": measured_unit,
        "canonical_value": canonical_value,
        "canonical_unit": canonical_unit,
        "sampling_method": attrs.get("Sampling_Method"),
        "mesh_size_mm": _to_float(attrs.get("Mesh_size__mm_")),
        "water_depth_m": _to_float(attrs.get("Ocean_Bottom_Depth__m_")),
        "sample_depth_m": sample_depth_m,
        "sediment_sample_depth_m": _to_float(attrs.get("Sediment_Sample_Depth__m_")),
        # ---- severity -----------------------------------------------------
        "published_class": attrs.get("Concentration_class_text"),
        "published_class_range": attrs.get("Concentration_class_range"),
        "severity_label": label,
        "severity_ordinal": ordinal,
        # ---- trust ---------------------------------------------------------
        "origin_status": "REAL",
        "location_label": " | ".join(
            part for part in (
                attrs.get("Location_Oceans"),
                attrs.get("Location_Regions"),
                attrs.get("Location_SubRegions"),
            ) if part
        ) or None,
        "reported_region": attrs.get("Location_Regions"),
        "reported_subregion": attrs.get("Location_SubRegions"),
        "country": attrs.get("Country"),
        "quality_note": "; ".join(quality_notes),
    }


def normalize_batch(attrs_list: list[dict], now: datetime | None = None) -> dict:
    """Normalise a batch, reporting exactly what was kept and what was not."""
    kept: list[dict] = []
    rejected: list[dict] = []

    for attrs in attrs_list:
        record = normalize_noaa_record(attrs, now=now)
        if record is None:
            rejected.append({
                "source_record_id": str(attrs.get("OBJECTID")) if isinstance(attrs, dict) else None,
                "reason": "missing or out-of-range sample position",
            })
            continue
        kept.append(record)

    return {
        "normalized": kept,
        "kept": len(kept),
        "rejected": rejected,
        "rejected_count": len(rejected),
    }


# --------------------------------------------------------------------------
# Published-literature records (curated CSV rows)
# --------------------------------------------------------------------------
def _parse_literature_date(value: str | None) -> datetime | None:
    """Parse a curated row's ``sample_date`` (ISO ``YYYY-MM-DD`` preferred).

    Returns ``None`` when absent or unparseable - the row is kept and the
    confidence penalty documents it, exactly like a NOAA row without a date.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _literature_record_id(row: dict) -> str:
    """Deterministic, stable id for one curated row.

    Built from the full citation tuple so the same row produces the same id on
    every re-ingest (the upsert key is ``(source, source_record_id)``) and two
    genuinely different rows never collide.
    """
    parts = "|".join(str(row.get(key) or "") for key in (
        "doi", "reference", "latitude", "longitude", "sample_date",
        "medium", "value", "unit",
    )).strip("|")
    return "lit-" + hashlib.sha1(parts.encode("utf-8")).hexdigest()[:14]


def normalize_literature_record(row: dict, now: datetime | None = None) -> dict | None:
    """Convert one curated literature CSV row into the unified sample shape.

    Returns ``None`` only for rows without a usable position, value or unit -
    a curated file is small and hand-checked, so anything else is expressed in
    the returned flags rather than the row being dropped.
    """
    latitude = _to_float(row.get("latitude"))
    longitude = _to_float(row.get("longitude"))
    if latitude is None or longitude is None:
        return None

    if 180.0 < longitude <= 360.0:
        longitude -= 360.0

    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None

    source_medium = row.get("medium")
    medium, medium_family = classify_medium(source_medium)

    measured_unit = row.get("unit")
    if not (measured_unit or "").strip():
        return None

    measured_value = _to_float(row.get("value"))
    if measured_value is None:
        return None
    if measured_value < 0:
        return None

    canonical_unit, factor, unit_family = normalize_unit(measured_unit)

    if unit_family == FAMILY_UNKNOWN and not (measured_unit or "").strip() and medium_family != FAMILY_UNKNOWN:
        unit_family = medium_family
        canonical_unit = None

    canonical_value = (
        round(measured_value * factor, 8)
        if (measured_value is not None and canonical_unit is not None)
        else None
    )

    sampled_at = _parse_literature_date(row.get("sample_date"))
    sample_depth_m = _to_float(row.get("sample_depth_m"))
    doi = row.get("doi") or None
    reference = row.get("reference") or None

    label, ordinal, severity_note = severity_for(
        value=canonical_value if canonical_value is not None else measured_value,
        medium=medium,
        family=unit_family,
    )

    confidence, confidence_notes = _confidence(
        sampled_at, unit_family, canonical_value, sample_depth_m, doi, now=now
    )

    quality_notes = confidence_notes + [severity_note]
    if medium == MEDIUM_UNKNOWN:
        quality_notes.append(
            f"marine setting '{source_medium}' not recognised; medium left unknown"
        )
    if canonical_value is None and measured_value is not None:
        quality_notes.append(
            f"unit '{measured_unit}' could not be normalised; native value kept only"
        )
    if sampled_at is None:
        quality_notes.append(f"sample_date '{row.get('sample_date')}' not parsed (-25)")

    doi_link = f"https://doi.org/{doi}" if doi else None

    return {
        # ---- the unified schema ------------------------------------------
        "region_id": None,          # resolved by the region mapping layer
        "region_distance_km": None,
        "latitude": round(latitude, 5),
        "longitude": round(longitude, 5),
        "timestamp": sampled_at,
        "concentration_value": canonical_value,
        "source": "Published literature (curated)",
        "confidence_score": confidence,
        # ---- provenance ---------------------------------------------------
        "source_dataset": "Curated peer-reviewed microplastic surveys",
        "source_record_id": _literature_record_id(row),
        "source_record_link": doi_link,
        "organization": row.get("organization") or None,
        "reference": reference,
        "doi": doi,
        # ---- what was measured --------------------------------------------
        "medium": medium,
        "source_medium": source_medium,
        "unit_family": unit_family,
        "measured_value": measured_value,
        "measured_unit": measured_unit,
        "canonical_value": canonical_value,
        "canonical_unit": canonical_unit,
        "sampling_method": row.get("sampling_method") or None,
        "mesh_size_mm": None,
        "water_depth_m": None,
        "sample_depth_m": sample_depth_m,
        "sediment_sample_depth_m": None,
        # ---- severity -----------------------------------------------------
        "published_class": None,
        "published_class_range": None,
        "severity_label": label,
        "severity_ordinal": ordinal,
        # ---- trust ---------------------------------------------------------
        "origin_status": "REAL",
        "location_label": row.get("location_name") or None,
        "reported_region": None,
        "reported_subregion": None,
        "country": row.get("country") or None,
        "quality_note": "; ".join(quality_notes),
    }


def normalize_literature_batch(rows: list[dict], now: datetime | None = None) -> dict:
    """Normalise a curated batch, reporting exactly what was kept and why not."""
    kept: list[dict] = []
    rejected: list[dict] = []

    for row in rows:
        record = normalize_literature_record(row, now=now)
        if record is None:
            rejected.append({
                "source_record_id": row.get("doi") or row.get("reference") or None,
                "reason": "missing or invalid position, value or unit",
            })
            continue
        kept.append(record)

    return {
        "normalized": kept,
        "kept": len(kept),
        "rejected": rejected,
        "rejected_count": len(rejected),
    }
