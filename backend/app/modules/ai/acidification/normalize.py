"""
TidalTwin - Acidification: normalize
=====================================
Normalises raw pH records from different sources into the unified schema
matching the ``OceanAcidificationSample`` model.

This module is where the module's central decision is made: whether a reported
pH number is a measurement of the ocean or a broken sensor.

THE ACCEPTANCE RULE
-------------------
``normalize_argo_ph_level`` rejects a pH value that falls outside the seawater
plausibility window in ``units`` (7.4 - 8.6), and accepts everything inside
it, *regardless of the Argo QC flag*.  That is the opposite of the dissolved
oxygen module's rule, and the inversion is deliberate:

  * BGC-Argo pH ships as real-time data (PARAMETER_DATA_MODE 'R'), so delayed
    mode QC has not run and the flag is close to meaningless as an acceptance
    test.  Observed profiles whose every value is flagged '3' (not evaluated)
    or '0' (no QC) carry pH of 7.44-8.47 - entirely normal seawater.
  * Observed profiles whose every value is flagged '4' (bad) carry pH from
    -1.6 to 6.2, which is not physically possible for seawater at all.

Rejecting on the flag would discard the good data and admit none of the
garbage.  The plausibility window separates the two populations cleanly, so it
is the primary gate and the flag only MODULATES CONFIDENCE.  Every rejection
is counted and reported by ``normalize_batch`` so a run that silently dropped
half its profiles is visible rather than invisible.
"""

from datetime import datetime, timezone
from typing import Any

from app.modules.ai.acidification.units import (
    DERIVED_OMEGA_NOTE,
    PH_PLAUSIBLE_MAX,
    PH_PLAUSIBLE_MIN,
    is_ph_plausible,
    is_undersaturated,
    derive_carbonate_chemistry,
    severity_for_ph,
)

# Confidence by Argo QC flag, applied only AFTER a value passes the physical
# plausibility gate.  Real-time pH is essentially never flagged 1/2, so the top
# tier is rare by design rather than by accident.
QC_CONFIDENCE = {
    "1": 0.95,  # good
    "2": 0.90,  # probably good
    "0": 0.75,  # no QC performed - real-time, unverified but plausible
    "3": 0.65,  # not evaluated - real-time, unverified
    "4": 0.0,   # bad
    "?": 0.60,  # flag absent
}
DEFAULT_QC_CONFIDENCE = 0.55


def _classify_severity(ph_total: float | None) -> tuple[str | None, int | None, int]:
    """Classify pH severity. Returns (label, ordinal, is_acidic).

    Delegates to ``units.severity_for_ph`` so ingest, the zone grid and the
    hotspot scorer cannot drift apart, exactly as the deoxygenation module does.
    Unlike that module's version this returns ``None`` rather than defaulting to
    NORMAL: there is no such thing as an unclassified pH that is "fine", and
    defaulting would launder a broken sensor into a healthy-looking reading.
    """
    label, ordinal, is_acidic = severity_for_ph(ph_total)
    if label is None or ordinal is None:
        return None, None, 0
    return label, ordinal, int(is_acidic)


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


def normalize_argo_ph_level(level: dict) -> dict | None:
    """Normalise ONE measured pH level from a real Argo BGC profile.

    Every field the ``OceanAcidificationSample`` table requires NOT NULL is
    populated from the measurement itself: ``ph_total`` and ``depth_m``.

    Returns None when the level carries no finite total-scale pH, no position,
    or a pH that is not physically possible for seawater.  The third case is
    counted separately by ``normalize_batch`` so the ingest report can say how
    many values were discarded as implausible rather than letting a faulty
    float look like a float with no data.
    """
    ph_total = _safe_float(level.get("ph_total"))

    # The plausibility gate. Applied BEFORE anything else, so an impossible
    # value can never be classified, never reach the database, and never have
    # carbonate chemistry derived from it.
    if not is_ph_plausible(ph_total):
        return None

    lat = _safe_float(level.get("latitude"))
    lon = _safe_float(level.get("longitude"))
    if lat is None or lon is None:
        return None

    depth_m = _safe_float(level.get("depth_m"))
    if depth_m is None:
        return None
    # In-situ pressure can come back marginally negative when a float is parked
    # just above sea level. A negative depth is not a real measurement and would
    # fall outside every depth band, so clamp it to the surface.
    depth_m = max(0.0, depth_m)

    sampled_at = level.get("timestamp")
    if sampled_at is not None and sampled_at.tzinfo is None:
        sampled_at = sampled_at.replace(tzinfo=timezone.utc)

    float_id = level.get("float_id")
    cycle = level.get("cycle")
    source_file = level.get("source_file")
    source_url = level.get("source_url")
    depth_source = level.get("depth_source")
    ph_variable = level.get("ph_variable")
    ph_scale = level.get("ph_scale")

    temperature_c = _safe_float(level.get("temperature_c"))
    salinity_psu = _safe_float(level.get("salinity_psu"))

    # Derived carbonate chemistry. Produces nothing at all when temperature or
    # salinity is missing - see units.DERIVED_OMEGA_NOTE for why a substitute
    # would be worse than a gap.
    chem = derive_carbonate_chemistry(ph_total, temperature_c, salinity_psu)

    severity_label, severity_ordinal, is_acidic = _classify_severity(ph_total)
    under = is_undersaturated(chem["omega_arag"])

    # QC flag modulates confidence only, never acceptance.
    qc_flag = level.get("qc_flag")
    confidence = QC_CONFIDENCE.get(str(qc_flag).strip(), DEFAULT_QC_CONFIDENCE)

    notes = [
        "Measured in-situ total-scale pH from a real Argo BGC float profile "
        f"(variable {ph_variable})."
    ]
    if ph_scale and ph_scale != "total":
        notes.append(
            f"The float reported free-scale pH only; the reading is stored on the "
            f"free scale and classified on the total-scale ladder with that stated "
            f"caveat."
        )
    if depth_source == "PRES":
        notes.append(
            "Depth taken from in-situ pressure (PRES) because the file publishes "
            "no geometric DEPTH; 1 dbar approximates 1 m."
        )
    if chem["derived"]:
        notes.append(
            f"Aragonite saturation {chem['omega_arag']} is DERIVED via CO2SYS, not "
            f"measured. {DERIVED_OMEGA_NOTE}"
        )
    elif chem["status"] != "OK":
        notes.append(f"No aragonite saturation derived: {chem['reason']}")
    if str(qc_flag).strip() not in ("1", "2"):
        notes.append(
            f"Argo QC flag is {qc_flag or 'absent'}; the value was retained on "
            "physical plausibility with reduced confidence."
        )

    # One measured level must map to exactly one row so re-running an ingest is
    # idempotent against the (source, source_record_id) unique constraint. A BGC
    # profile file stacks several sensor groups along the profile axis and its
    # pH sensor repeats near-identical pressures, so depth alone is NOT unique
    # within a file - the profile and level indices are required.
    record_id = (
        f"{float_id or 'unknown'}_c{cycle}_{source_file or 'nofile'}"
        f"_p{level.get('profile_index')}_l{level.get('level_index')}"
    )

    return {
        "source": "Argo BGC float (real Argo GDAC)",
        "source_dataset": "Argo BGC profile (in-situ pH)",
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
        "ph_total": ph_total,
        "ph_free": _safe_float(level.get("ph_free")),
        "omega_arag": chem["omega_arag"],
        "omega_calc": chem["omega_calc"],
        "omega_arag_derived": int(bool(chem["derived"])),
        "dic_umol_kg": chem["dic_umol_kg"],
        "pco2_uatm": chem["pco2_uatm"],
        "alk_umol_kg": chem["alk_umol_kg"],
        "depth_m": depth_m,
        "temperature_c": temperature_c,
        "salinity_psu": salinity_psu,
        "pressure_dbar": _safe_float(level.get("pressure_dbar")),
        "severity_label": severity_label,
        "severity_ordinal": severity_ordinal,
        "is_acidic": is_acidic,
        "is_undersaturated": int(under),
        "confidence_score": confidence,
        "origin_status": "REAL",
        "qc_flag": qc_flag,
        "quality_note": " ".join(notes),
        "source_file": source_file,
    }


def normalize_batch(records: list[dict], source_type: str = "argo_ph_level") -> dict:
    """Normalise a batch of records, reporting WHY anything was rejected.

    ``rejected_count`` is split into ``rejected_no_ph`` (padding/absent data)
    and ``rejected_implausible`` (a number that cannot be seawater) so an
    ingest report distinguishes "the float had no pH" from "the float's pH
    sensor is broken".  Conflating them is how a broken float ends up
    indistinguishable from a sparse float.
    """
    normalizers = {
        "argo_ph_level": normalize_argo_ph_level,
    }

    normalizer = normalizers.get(source_type)
    if not normalizer:
        return {
            "normalized": [],
            "rejected_count": len(records),
            "rejected_no_ph": len(records),
            "rejected_implausible": 0,
        }

    normalized = []
    rejected_no_ph = 0
    rejected_implausible = 0
    other = 0

    for record in records:
        try:
            norm = normalizer(record)
        except Exception:
            other += 1
            continue
        if norm is not None:
            normalized.append(norm)
            continue
        # Work out which of the two rejection reasons applied, so the count is
        # meaningful rather than a single opaque number.
        ph = _safe_float(record.get("ph_total"))
        if ph is None:
            rejected_no_ph += 1
        elif not is_ph_plausible(ph):
            rejected_implausible += 1
        else:
            # Plausible pH but missing position or depth.
            other += 1

    return {
        "normalized": normalized,
        "rejected_count": rejected_no_ph + rejected_implausible + other,
        "rejected_no_ph": rejected_no_ph,
        "rejected_implausible": rejected_implausible,
        "rejected_incomplete": other,
        "plausibility_window": [PH_PLAUSIBLE_MIN, PH_PLAUSIBLE_MAX],
    }
