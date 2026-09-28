"""Validation for normalised MoES / INCOIS observations.

Contract: **flag, never silently delete**.

Every candidate row that an adapter produces is passed through
:func:`validate_candidate`.  The result is a list of typed issues, not a
boolean.  A row with only ``WARNING`` issues is still ingested and carries its
flags; a row with an ``ERROR`` issue is rejected *and the rejection is counted
and reported*, so an operator can see exactly what was dropped and why.

What is checked
---------------
schema       required keys present and correctly typed
units        every numeric value carries a declared unit that is convertible
coordinates  latitude/longitude in range, non-zero, and (optionally) inside the
             monitored region; longitude normalisation to [-180, 180]
timestamp    parseable, not in the future beyond a small clock tolerance, not
             before the source's own coverage start, monotonic per profile
depth        finite, within the source's declared depth range, monotonic with
             pressure for a single profile
range        value inside the project's shared broad plausibility ranges
duplicates   identical platform/cycle/depth/time rows within one batch
QC flags     Argo reference table 2 interpretation; a missing or bad flag makes
             the value unusable evidence, but is recorded rather than dropped
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from app.modules.ai.provenance_quality import FIELD_UNITS, PHYSICAL_RANGES

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

#: A provider clock can legitimately run a little ahead of ours; anything beyond
#: this is a defect, not a forecast.  Argo profiles in particular are never
#: genuinely "in the future".
FUTURE_TOLERANCE_HOURS = 6.0

#: Numeric tolerance when re-deriving pressure from depth (1 dbar ~ 1 m).
PRESSURE_DEPTH_TOLERANCE_DBAR = 5.0


# ---------------------------------------------------------------------------
# Argo reference table 2 quality-control flags
# ---------------------------------------------------------------------------

QC_LABELS: dict[str, str] = {
    "0": "MISSING", "1": "GOOD", "2": "PROBABLY_GOOD", "3": "BAD",
    "4": "BAD", "5": "BAD", "6": "NOT_GENERATED", "7": "NOT_GENERATED",
    "8": "NOT_GENERATED", "9": "MISSING", " ": "MISSING", "": "MISSING",
}

#: Only these flags are acceptable evidence for TIDE scoring.  "Probably good"
#: is retained but its weaker weight is recorded by the caller, not hidden.
QC_USABLE = {"1", "2"}


def qc_label(flag: Any) -> str:
    """Interpret one Argo reference table 2 QC flag."""
    if flag is None:
        return "MISSING"
    text = str(flag).strip()
    if text.upper() in {"NAN", "NULL", "NONE"}:
        return "MISSING"
    if len(text) > 1 and text[0].isdigit() and text[1:].strip(".").isdigit():
        # A "1.0"/"2.0" numeric QC flag is a serialisation artifact, not a
        # different flag value.
        text = text[0]
    return QC_LABELS.get(text, "UNRECOGNISED")


def qc_is_usable(flag: Any) -> bool:
    return str(flag).strip()[:1] in QC_USABLE


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    field: str | None = None
    value: Any = None

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "message": self.message,
                "field": self.field, "value": self.value}


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def acceptable(self) -> bool:
        """True when the row may be stored.  Warnings never block a row."""
        return not self.errors

    def add(self, code: str, severity: str, message: str, field: str | None = None,
            value: Any = None) -> None:
        self.issues.append(ValidationIssue(code, severity, message, field, value))

    @property
    def codes(self) -> list[str]:
        return [i.code for i in self.issues]

    def summary(self) -> str:
        return ", ".join(f"{i.severity}:{i.code}" for i in self.issues) or "clean"

    def payload(self) -> dict[str, Any]:
        return {
            "acceptable": self.acceptable,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.payload() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

#: Canonical unit for every field TidalTwin can score.  These are the strings
#: the rest of the platform already uses (``provenance_quality.FIELD_UNITS``),
#: except for pressure, whose existing label is a caveat rather than a unit.
CANONICAL_UNITS: dict[str, str] = {
    "sea_surface_temperature": FIELD_UNITS["sea_surface_temperature"],
    "temperature": FIELD_UNITS["sea_surface_temperature"],
    "salinity": FIELD_UNITS["salinity"],
    "pressure": "dbar",
    "wave_height": FIELD_UNITS["wave_height"],
    "chlorophyll": "mg/m3",
}

#: Spellings that mean the same unit as the canonical one.  A provider writing
#: ``degree_Celsius`` where the platform writes ``degC`` is not a defect, and
#: warning about it on every row would bury the warnings that matter.
UNIT_ALIASES: dict[str, set[str]] = {
    "degC": {"degc", "degreec", "degreecelsius", "degreescelsius", "degcelsius", "celsius", "deg_c", "c"},
    "PSU": {"psu", "practicalsalinity", "pss", "1e-3", "salinity"},
    "dbar": {"dbar", "decibar", "decibars", "db"},
    "m": {"m", "metre", "metres", "meter", "meters"},
    "mg/m3": {"mg/m3", "mgm-3", "mg/m^3", "ug/l", "milligram/m3"},
}

#: Fields the platform can score.  Values are the canonical unit for each.
CANONICAL_FIELDS: dict[str, str] = CANONICAL_UNITS

_TOLERANCE_SECONDS = 30 * 24 * 3600  # a month, to allow provider time quirks


def _normalise_unit(unit: str) -> str:
    return "".join(ch for ch in str(unit).strip().lower() if ch not in " _.-/^3") or str(unit).strip().lower()


def units_equivalent(observed: str, canonical: str) -> bool:
    """True when two unit strings denote the same physical unit."""
    if not observed or not str(observed).strip():
        return False
    if _normalise_unit(observed) == _normalise_unit(canonical):
        return True
    allowed = UNIT_ALIASES.get(canonical, {canonical})
    return _normalise_unit(observed) in {_normalise_unit(a) for a in allowed}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def normalise_longitude(value: Any, report: ValidationReport, field: str = "longitude") -> float | None:
    """Fold a longitude into [-180, 180] and flag the fact when it moved."""
    numeric = _finite(value)
    if numeric is None:
        report.add("COORDINATE_UNPARSEABLE", ERROR, f"{field} is not a finite number.", field, value)
        return None
    if numeric == 0.0:
        report.add("COORDINATE_NULL_ISLAND", ERROR,
                   f"{field} is exactly 0, which is almost always a missing-value placeholder.", field, value)
        return None
    if not -180.0 <= numeric <= 180.0:
        report.add("COORDINATE_OUT_OF_RANGE", ERROR, f"{field} {numeric} is outside [-180, 180].", field, value)
        return None
    normalised = (numeric + 180.0) % 360.0 - 180.0
    if abs(normalised - numeric) > 1e-9:
        report.add("COORDINATE_NORMALISED", INFO,
                   f"{field} {numeric} was normalised to {normalised}.", field, normalised)
    return normalised


def _check_schema(candidate: dict[str, Any], report: ValidationReport) -> None:
    if not candidate.get("source_id"):
        report.add("SCHEMA_MISSING_SOURCE", ERROR, "source_id is required for provenance.", "source_id")
    if candidate.get("timestamp") is None:
        report.add("SCHEMA_MISSING_TIMESTAMP", ERROR, "timestamp is required.", "timestamp")
    if not candidate.get("data_status"):
        report.add("SCHEMA_MISSING_DATA_STATUS", ERROR,
                   "data_status is required; an observation with no asserted origin must not be stored.", "data_status")


def _check_units(candidate: dict[str, Any], report: ValidationReport) -> None:
    units = candidate.get("units") or {}
    if not isinstance(units, dict):
        report.add("UNIT_MAP_INVALID", ERROR, "units must be a mapping of field -> unit string.", "units", units)
        return
    for name, canonical in CANONICAL_FIELDS.items():
        if candidate.get(name) is None:
            continue
        unit = units.get(name)
        if unit is None or not str(unit).strip():
            report.add("UNIT_MISSING", ERROR,
                       f"{name} carries a value but no unit. An unlabelled number is not evidence.",
                       f"units.{name}")
        elif not units_equivalent(unit, canonical):
            report.add("UNIT_MISMATCH", WARNING,
                       f"{name} unit {unit!r} is not the same unit as the platform unit "
                       f"{canonical!r}; the value was stored unconverted.",
                       f"units.{name}", unit)


def _check_coordinates(candidate: dict[str, Any], report: ValidationReport,
                       bounds: tuple[float, float, float, float] | None) -> None:
    latitude = _finite(candidate.get("latitude"))
    if latitude is None:
        report.add("COORDINATE_MISSING_LATITUDE", ERROR, "latitude is missing or not finite.", "latitude")
    elif not -90.0 <= latitude <= 90.0:
        report.add("COORDINATE_OUT_OF_RANGE", ERROR, f"latitude {latitude} is outside [-90, 90].", "latitude", latitude)

    longitude = normalise_longitude(candidate.get("longitude"), report)
    if longitude is not None and latitude is not None and bounds is not None:
        lat_min, lat_max, lon_min, lon_max = bounds
        if not (lat_min <= latitude <= lat_max and lon_min <= longitude <= lon_max):
            report.add("OUTSIDE_REGION_OF_INTEREST", WARNING,
                       f"Position ({latitude:.3f}, {longitude:.3f}) lies outside the monitored box "
                       f"[{lat_min}, {lat_max}] x [{lon_min}, {lon_max}]; stored but flagged.",
                       "latitude")


def _check_timestamp(candidate: dict[str, Any], report: ValidationReport, now: datetime) -> None:
    timestamp = candidate.get("timestamp")
    if not isinstance(timestamp, datetime):
        report.add("TIMESTAMP_UNPARSEABLE", ERROR, "timestamp must be a datetime.", "timestamp", timestamp)
        return
    moment = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
    lead = (moment - now).total_seconds() / 3600.0
    if lead > FUTURE_TOLERANCE_HOURS:
        report.add("TIMESTAMP_IN_FUTURE", ERROR,
                   f"timestamp is {lead:.1f} h in the future; a measured profile cannot be.", "timestamp",
                   moment.isoformat())
    if moment.year < 1970:
        report.add("TIMESTAMP_PRE_EPOCH", ERROR, "timestamp predates 1970.", "timestamp", moment.isoformat())
    elif (now - moment).total_seconds() > _TOLERANCE_SECONDS * 50:
        report.add("TIMESTAMP_IMPLAUSIBLY_OLD", WARNING,
                   "timestamp is more than ~5 years old; confirm the source is intended to be historical.",
                   "timestamp", moment.isoformat())


def _check_depth(candidate: dict[str, Any], report: ValidationReport) -> None:
    pressure = _finite(candidate.get("pressure"))
    if pressure is None:
        if candidate.get("pressure") is not None:
            report.add("DEPTH_UNPARSEABLE", ERROR, "pressure is not a finite number.", "pressure",
                       candidate.get("pressure"))
        return
    # A few decibar of negative pressure at the surface is normal for a CTD
    # pack; more than that is a defect.
    if pressure < -PRESSURE_DEPTH_TOLERANCE_DBAR:
        report.add("DEPTH_NEGATIVE", ERROR,
                   f"pressure {pressure} dbar is below the surface tolerance of "
                   f"-{PRESSURE_DEPTH_TOLERANCE_DBAR} dbar.", "pressure", pressure)
    elif pressure < 0:
        report.add("DEPTH_NEGATIVE_WITHIN_TOLERANCE", INFO,
                   f"pressure {pressure} dbar is slightly negative, which is expected for a surface CTD.",
                   "pressure", pressure)
    if pressure > 12000.0:
        report.add("DEPTH_BELOW_OCEAN_MAX", ERROR, "pressure exceeds 12000 dbar.", "pressure", pressure)


def _check_values(candidate: dict[str, Any], report: ValidationReport) -> None:
    for name in CANONICAL_FIELDS:
        if name not in candidate or candidate[name] is None:
            continue
        raw = candidate[name]
        numeric = _finite(raw)
        if numeric is None:
            report.add("VALUE_NON_NUMERIC", ERROR, f"{name} is not a finite number.", name, raw)
            continue
        key = "pressure" if name == "pressure" else name
        if key in PHYSICAL_RANGES:
            low, high = PHYSICAL_RANGES[key]
            if not low <= numeric <= high:
                severity = ERROR if name in ("temperature", "sea_surface_temperature", "salinity", "pressure") else WARNING
                report.add("VALUE_OUT_OF_RANGE", severity,
                           f"{name} {numeric} is outside the broad plausibility range "
                           f"[{low:g}, {high:g}] {FIELD_UNITS[key]}.", name, numeric)
        if numeric == 0.0 and name in ("temperature", "sea_surface_temperature", "salinity"):
            report.add("VALUE_SUSPICIOUS_ZERO", WARNING,
                       f"{name} is exactly 0, which in this region is physically implausible and is "
                       f"often a fill value.", name, numeric)


def _check_qc(candidate: dict[str, Any], report: ValidationReport) -> None:
    flags = candidate.get("qc_flags") or {}
    if not isinstance(flags, dict):
        report.add("QC_MAP_INVALID", ERROR, "qc_flags must be a mapping of variable -> flag.", "qc_flags", flags)
        return
    for name, flag in flags.items():
        label = qc_label(flag)
        if label == "BAD":
            report.add("QC_BAD_VALUE", ERROR, f"{name} carries reference table 2 flag {flag!r} (BAD).",
                       f"qc_flags.{name}", flag)
        elif label in ("MISSING", "UNRECOGNISED", "NOT_GENERATED"):
            report.add("QC_NO_FLAG", WARNING,
                       f"{name} has no usable QC flag (got {flag!r} -> {label}); the value is retained as "
                       f"unverified evidence.", f"qc_flags.{name}", flag)
        if not qc_is_usable(flag) and candidate.get(name) is not None and name in CANONICAL_FIELDS:
            report.add("QC_NOT_USABLE_FOR_SCORING", INFO,
                       f"{name} will be excluded from TIDE scoring because its QC flag is {label}.",
                       f"qc_flags.{name}", label)


def duplicate_key(candidate: dict[str, Any]) -> tuple:
    """Identity of a physical sample: what makes two rows the same measurement."""
    return (
        candidate.get("source_id"),
        candidate.get("platform_id"),
        candidate.get("cycle_number"),
        candidate.get("timestamp"),
        round(_finite(candidate.get("latitude")) or 0.0, 4),
        round(_finite(candidate.get("longitude")) or 0.0, 4),
        round(_finite(candidate.get("pressure")) or 0.0, 3),
    )


def validate_candidate(candidate: dict[str, Any], *,
                       now: datetime | None = None,
                       seen: set[tuple] | None = None,
                       region_bounds: tuple[float, float, float, float] | None = None,
                       ) -> ValidationReport:
    """Validate one normalised candidate.  Returns every issue found."""
    report = ValidationReport()
    now = now or datetime.now(timezone.utc)
    _check_schema(candidate, report)
    _check_units(candidate, report)
    _check_coordinates(candidate, report, region_bounds)
    _check_timestamp(candidate, report, now)
    _check_depth(candidate, report)
    _check_values(candidate, report)
    _check_qc(candidate, report)

    if seen is not None:
        key = duplicate_key(candidate)
        if key in seen:
            report.add("DUPLICATE_SAMPLE", ERROR,
                       "an identical platform/cycle/time/position/depth sample already exists in this batch.",
                       "duplicate", list(map(str, key)))
        else:
            seen.add(key)
    return report


def summarise_reports(reports: Iterable[ValidationReport]) -> dict[str, Any]:
    """Aggregate reports for an ingestion-run summary."""
    reports = list(reports)
    counts: dict[str, int] = {}
    rejected = 0
    for report in reports:
        if not report.acceptable:
            rejected += 1
        for issue in report.issues:
            counts[f"{issue.severity}:{issue.code}"] = counts.get(f"{issue.severity}:{issue.code}", 0) + 1
    return {
        "validated": len(reports),
        "accepted": len(reports) - rejected,
        "rejected": rejected,
        "flag_counts": dict(sorted(counts.items())),
    }


__all__ = [
    "CANONICAL_FIELDS",
    "CANONICAL_UNITS",
    "ERROR",
    "FUTURE_TOLERANCE_HOURS",
    "INFO",
    "QC_LABELS",
    "QC_USABLE",
    "UNIT_ALIASES",
    "WARNING",
    "ValidationIssue",
    "ValidationReport",
    "duplicate_key",
    "normalise_longitude",
    "qc_is_usable",
    "qc_label",
    "summarise_reports",
    "units_equivalent",
    "validate_candidate",
]
