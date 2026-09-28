"""
TidalTwin - Microplastics: open-source data connectors
======================================================
Three connectors, all open-source, no hardware:

  1. NOAA NCEI global Marine Microplastics collection.
     A public ArcGIS Feature Service - no key, no registration.  391 real
     records fall inside the Indian Ocean window this platform already
     monitors (lon 60-100, lat 0-25), spanning 2013-06 to 2021-12.

  2. Published-literature microplastic surveys (curated CSV).
     NOAA simply publishes no samples near several monitored coasts (Mumbai,
     Chennai, Goa, Kochi, Odisha, Lakshadweep).  Those gaps are only filled
     with genuinely published peer-reviewed measurements, entered manually
     into ``literature_samples.csv`` with a DOI and reference per row.  An
     empty file is an honest empty state, never an estimated number.

  3. NASA Earthdata satellite-derived plastic signal.  Credential-gated: an
     Earthdata token is required.  When it is absent the connector returns
     UNAVAILABLE with a reason rather than inventing numbers, exactly as the
     voice module treats a missing provider key.

CONNECTOR CONTRACT
------------------
Every connector returns a :class:`ConnectorResult`.  The invariant is:

    ``found=False`` ALWAYS carries a human-readable ``reason``.

Callers must never treat an empty ``records`` list as "the ocean is clean".
An empty list from a failed request means *we do not know*, and the result
object keeps those two situations distinguishable.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger("tidaltwin.microplastics.sources")

# --------------------------------------------------------------------------
# The Indian Ocean window this platform monitors.  Matches the bbox the
# currents router already uses (lat 3-25, lon 66-92) but widened slightly so a
# sample just outside the EEZ still maps to its nearest monitored coast.
# --------------------------------------------------------------------------
INDIA_BBOX = {"lon_min": 60.0, "lat_min": 0.0, "lon_max": 100.0, "lat_max": 25.0}

NOAA_MAX_RECORD_COUNT = 2000
NOAA_DEFAULT_LIMIT = 2000

NOAA_SOURCE_NAME = "NOAA NCEI Marine Microplastics"
NOAA_DATASET = "Global Marine Microplastics Database (1972-present)"
NOAA_LICENCE = "U.S. Government work - public domain (NOAA NCEI)"
NOAA_HOMEPAGE = "https://www.ncei.noaa.gov/products/microplastics"

# --------------------------------------------------------------------------
# Published-literature connector (curated CSV).
#
# NOAA publishes no samples near six of the eight monitored coasts.  The only
# honest way to cover them is published peer-reviewed measurements keyed by
# DOI.  Operators add rows to ``literature_samples.csv`` (columns documented in
# that file); the connector parses and structurally validates them here, and
# ``normalize.normalize_literature_record`` turns each into the unified schema.
# --------------------------------------------------------------------------
LITERATURE_SOURCE_NAME = "Published literature (curated)"
LITERATURE_DATASET = "Curated peer-reviewed microplastic surveys"
LITERATURE_LICENCE = "By-study; each row carries its own DOI and must be cited"
LITERATURE_HOMEPAGE = "https://doi.org/"
LITERATURE_FILENAME = "literature_samples.csv"

# Columns the connector will read.  Kept in one place so the CSV header and the
# parser cannot drift apart silently.
LITERATURE_COLUMNS = (
    "latitude",
    "longitude",
    "sample_date",
    "medium",
    "unit",
    "value",
    "doi",
    "reference",
    "location_name",
    "organization",
    "sampling_method",
    "sample_depth_m",
    "country",
    "note",
)


def literature_csv_path() -> str:
    """Path to the curated literature file, overridable via settings."""
    configured = (settings.MICROPLASTICS_LITERATURE_CSV or "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parent / LITERATURE_FILENAME)


def _parse_literature_csv(csv_path: str) -> tuple[list[dict], list[str]]:
    """Read a curated CSV, returning ``(rows, structural_errors)``.

    ``#`` comment lines and blank lines are skipped so the header block can
    document the columns in place.  Rows missing the core fields (position,
    value, unit) are the source's responsibility to detect later, so here we
    only drop rows that cannot be read as CSV at all and record why.
    """
    rows: list[dict] = []
    errors: list[str] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for lineno, cells in enumerate(reader, start=1):
            if not cells:
                continue
            if cells[0].strip().startswith("#"):
                continue
            if not cells[0].strip():
                continue
            # One header line, matching the documented column names.
            if (
                cells[0].strip().lower() == LITERATURE_COLUMNS[0]
                and len(cells) >= len(LITERATURE_COLUMNS)
            ):
                continue
            if len(cells) < 4:
                errors.append(
                    f"row {lineno}: only {len(cells)} column(s), expected "
                    f"{len(LITERATURE_COLUMNS)}"
                )
                continue
            row: dict[str, str] = {}
            for index, column in enumerate(LITERATURE_COLUMNS):
                row[column] = cells[index].strip() if index < len(cells) else ""
            rows.append(row)
    return rows, errors


def fetch_literature_samples(csv_path: str | None = None) -> ConnectorResult:
    """Read the curated published-literature sample file.

    Missing file -> ERROR, empty file -> OK with ``found=False`` and a reason
    that names the path.  Structural validation happens here; the semantic
    validation (unit family, plausibility, severity) lives in ``normalize``,
    the same split the NOAA connector uses.
    """
    path = csv_path or literature_csv_path()
    started = datetime.now(timezone.utc)

    if not settings.MICROPLASTICS_ENABLED:
        return ConnectorResult(
            source=LITERATURE_SOURCE_NAME, status="DISABLED", found=False,
            reason="Microplastics module is disabled (MICROPLASTICS_ENABLED=false).",
            endpoint=path, licence=LITERATURE_LICENCE, homepage=LITERATURE_HOMEPAGE,
        )

    if not os.path.isfile(path):
        return ConnectorResult(
            source=LITERATURE_SOURCE_NAME, status="ERROR", found=False,
            reason=(
                "Curated literature file not found at "
                f"{path}. Set MICROPLASTICS_LITERATURE_CSV or add the file "
                "shipped with the module. Nothing is estimated in its place."
            ),
            endpoint=path, licence=LITERATURE_LICENCE, homepage=LITERATURE_HOMEPAGE,
        )

    try:
        rows, structural_errors = _parse_literature_csv(path)
    except Exception as exc:  # pragma: no cover - defensive, mirrors NOAA path
        logger.warning("Literature CSV read failed unexpectedly.", exc_info=True)
        return ConnectorResult(
            source=LITERATURE_SOURCE_NAME, status="ERROR", found=False,
            reason=f"Unexpected failure reading literature CSV: {exc.__class__.__name__}.",
            endpoint=path, licence=LITERATURE_LICENCE, homepage=LITERATURE_HOMEPAGE,
        )

    if not rows:
        reason = (
            f"Curated literature file {path} has no data rows. Add published "
            "measurements from peer-reviewed studies (columns are documented "
            "in the file's header) and re-ingest; until then these regions are "
            "reported as gaps, never filled with estimates."
        )
        if structural_errors:
            reason += " Structural issues skipped: " + "; ".join(structural_errors)
        return ConnectorResult(
            source=LITERATURE_SOURCE_NAME, status="OK", found=False,
            reason=reason, endpoint=path, licence=LITERATURE_LICENCE,
            homepage=LITERATURE_HOMEPAGE,
        )

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return ConnectorResult(
        source=LITERATURE_SOURCE_NAME, status="OK", found=True, records=rows,
        endpoint=path, licence=LITERATURE_LICENCE, homepage=LITERATURE_HOMEPAGE,
        retrieved_at=started.isoformat(), duration_ms=duration_ms,
    )

# Field names verified against the live layer, not guessed.
NOAA_OUT_FIELDS = (
    "OBJECTID",
    "Latitude__degree_",
    "Longitude_degree_",
    "Location_Oceans",
    "Location_Regions",
    "Location_SubRegions",
    "Country",
    "Medium",
    "Ocean_Bottom_Depth__m_",
    "Water_Sample_Depth__m_",
    "Sediment_Sample_Depth__m_",
    "Sampling_Method",
    "Mesh_size__mm_",
    "Microplastics_measurement",
    "Unit",
    "Concentration_class_text",
    "Concentration_class_range",
    "Short_Reference",
    "DOI",
    "ORGANIZATION",
    "NCEI_Accession_No",
    "Date_m_d_yyyy",
)


@dataclass
class ConnectorResult:
    """Outcome of one connector run, including the reasons it came up empty."""

    source: str
    status: str                       # OK | UNAVAILABLE | ERROR | DISABLED
    found: bool
    records: list[dict] = field(default_factory=list)
    reason: str | None = None
    endpoint: str | None = None
    licence: str | None = None
    homepage: str | None = None
    total_reported: int | None = None
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_ms: int | None = None

    def as_status_dict(self) -> dict:
        """Compact form for the API - never leaks the full record payload."""
        return {
            "source": self.source,
            "status": self.status,
            "found": self.found,
            "records_returned": len(self.records),
            "reason": self.reason,
            "endpoint": self.endpoint,
            "licence": self.licence,
            "homepage": self.homepage,
            "total_reported": self.total_reported,
            "retrieved_at": self.retrieved_at,
            "duration_ms": self.duration_ms,
        }


def _bbox_envelope(bbox: dict) -> str:
    return (
        f"{bbox['lon_min']},{bbox['lat_min']},"
        f"{bbox['lon_max']},{bbox['lat_max']}"
    )


def fetch_noaa_samples(
    bbox: dict | None = None,
    limit: int = NOAA_DEFAULT_LIMIT,
    timeout: float = 45.0,
) -> ConnectorResult:
    """Pull microplastic sample records from NOAA NCEI's public feature service.

    Pages through the layer with ``resultOffset`` until ``limit`` records are
    collected or the service stops returning more.  Never raises: a network or
    schema failure comes back as ``status="ERROR"`` with the reason attached.
    """
    bbox = bbox or INDIA_BBOX
    endpoint = settings.MICROPLASTICS_NOAA_URL
    started = datetime.now(timezone.utc)

    if not settings.MICROPLASTICS_ENABLED:
        return ConnectorResult(
            source=NOAA_SOURCE_NAME, status="DISABLED", found=False,
            reason="Microplastics module is disabled (MICROPLASTICS_ENABLED=false).",
            endpoint=endpoint, licence=NOAA_LICENCE, homepage=NOAA_HOMEPAGE,
        )

    if not endpoint:
        return ConnectorResult(
            source=NOAA_SOURCE_NAME, status="UNAVAILABLE", found=False,
            reason="No endpoint configured (MICROPLASTICS_NOAA_URL is empty).",
            licence=NOAA_LICENCE, homepage=NOAA_HOMEPAGE,
        )

    limit = max(1, min(int(limit), NOAA_MAX_RECORD_COUNT))
    params = {
        "where": "1=1",
        "geometry": _bbox_envelope(bbox),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(NOAA_OUT_FIELDS),
        "returnGeometry": "false",
        "orderByFields": "OBJECTID ASC",
        "f": "json",
    }
    url = f"{endpoint.rstrip('/')}/query"

    records: list[dict] = []
    total_reported: int | None = None
    page_size = min(NOAA_MAX_RECORD_COUNT, limit)
    offset = 0

    try:
        with httpx.Client(timeout=timeout) as client:
            while len(records) < limit:
                page_params = dict(params)
                page_params["resultRecordCount"] = page_size
                page_params["resultOffset"] = offset

                resp = client.get(url, params=page_params)
                resp.raise_for_status()
                payload = resp.json()

                # ArcGIS reports failures as HTTP 200 with an "error" object.
                error = payload.get("error")
                if error:
                    return ConnectorResult(
                        source=NOAA_SOURCE_NAME, status="ERROR", found=False,
                        reason=(
                            "NOAA service returned an error: "
                            f"{error.get('message', 'unknown')} "
                            f"(code {error.get('code', '?')})."
                        ),
                        endpoint=endpoint, licence=NOAA_LICENCE,
                        homepage=NOAA_HOMEPAGE,
                    )

                features = payload.get("features") or []
                if not features:
                    break

                for feature in features:
                    attrs = feature.get("attributes") or {}
                    if attrs:
                        records.append(attrs)

                if total_reported is None:
                    total_reported = payload.get("totalReported")
                if len(features) < page_size:
                    break
                if payload.get("exceededTransferLimit") is False and len(features) < page_size:
                    break
                offset += len(features)

                if offset >= NOAA_MAX_RECORD_COUNT * 4:  # hard safety stop
                    break
    except httpx.HTTPError as exc:
        return ConnectorResult(
            source=NOAA_SOURCE_NAME, status="ERROR", found=False,
            reason=f"Network/HTTP failure reaching NOAA NCEI: {exc.__class__.__name__}.",
            endpoint=endpoint, licence=NOAA_LICENCE, homepage=NOAA_HOMEPAGE,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("NOAA microplastics fetch failed unexpectedly.", exc_info=True)
        return ConnectorResult(
            source=NOAA_SOURCE_NAME, status="ERROR", found=False,
            reason=f"Unexpected failure reading NOAA NCEI: {exc.__class__.__name__}.",
            endpoint=endpoint, licence=NOAA_LICENCE, homepage=NOAA_HOMEPAGE,
        )

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    records = records[:limit]

    if not records:
        return ConnectorResult(
            source=NOAA_SOURCE_NAME, status="OK", found=False,
            reason=(
                "NOAA NCEI is reachable but publishes no microplastic samples "
                "inside the requested window. That is a genuine data gap, not a "
                "clean ocean."
            ),
            endpoint=endpoint, licence=NOAA_LICENCE, homepage=NOAA_HOMEPAGE,
            total_reported=total_reported or 0, duration_ms=duration_ms,
        )

    return ConnectorResult(
        source=NOAA_SOURCE_NAME, status="OK", found=True, records=records,
        endpoint=endpoint, licence=NOAA_LICENCE, homepage=NOAA_HOMEPAGE,
        total_reported=total_reported, duration_ms=duration_ms,
    )


def fetch_nasa_plastic_signal(
    bbox: dict | None = None,
    timeout: float = 30.0,
) -> ConnectorResult:
    """Satellite-derived plastic-signal connector (NASA Earthdata IMPACT).

    This one is credential-gated.  NASA Earthdata has no anonymous query
    endpoint, so with no token we report UNAVAILABLE and name the exact
    configuration needed.  We never fabricate a satellite layer to fill the
    gap - an absent product must look absent.
    """
    bbox = bbox or INDIA_BBOX
    token = (settings.NASA_EARTHDATA_TOKEN or "").strip()

    if not settings.MICROPLASTICS_ENABLED:
        return ConnectorResult(
            source="NASA Earthdata (satellite plastic signal)",
            status="DISABLED", found=False,
            reason="Microplastics module is disabled (MICROPLASTICS_ENABLED=false).",
        )

    if not token:
        return ConnectorResult(
            source="NASA Earthdata (satellite plastic signal)",
            status="UNAVAILABLE", found=False,
            reason=(
                "No NASA Earthdata token configured. Set NASA_EARTHDATA_TOKEN "
                "to enable the satellite-derived plastic-signal connector; "
                "without it this layer is absent rather than estimated."
            ),
            endpoint="https://data.earthdata.nasa.gov/",
            licence="NASA Earthdata - open, attribution required",
            homepage="https://www.earthdata.nasa.gov/",
        )

    # A token is present, but the retrieval itself is not implemented yet.
    # Reporting UNIMPLEMENTED is honest; fabricating a grid would not be.
    return ConnectorResult(
        source="NASA Earthdata (satellite plastic signal)",
        status="ERROR", found=False,
        reason=(
            "Credentials are present but the retrieval is not implemented in "
            "this build. No satellite plastic-signal values are produced, and "
            "none are estimated in its place."
        ),
        endpoint="https://data.earthdata.nasa.gov/",
        licence="NASA Earthdata - open, attribution required",
        homepage="https://www.earthdata.nasa.gov/",
    )


def source_catalogue() -> list[dict]:
    """Describe every configured source for the provenance panel."""
    return [
        {
            "key": "noaa_ncei",
            "name": NOAA_SOURCE_NAME,
            "dataset": NOAA_DATASET,
            "kind": "in-situ observations",
            "access": "Public ArcGIS Feature Service, no key required",
            "licence": NOAA_LICENCE,
            "homepage": NOAA_HOMEPAGE,
            "endpoint": settings.MICROPLASTICS_NOAA_URL,
            "requires_credentials": False,
            "used_for": "Measured microplastic concentration, by medium and unit.",
        },
        {
            "key": "literature_curated",
            "name": LITERATURE_SOURCE_NAME,
            "dataset": LITERATURE_DATASET,
            "kind": "curated published measurements",
            "access": "Rows added by hand into the module's literature_samples.csv",
            "licence": LITERATURE_LICENCE,
            "homepage": LITERATURE_HOMEPAGE,
            "endpoint": literature_csv_path(),
            "requires_credentials": False,
            "used_for": (
                "Measured concentrations for coasts NOAA does not publish "
                "samples for; each row carries its own DOI."
            ),
        },
        {
            "key": "nasa_earthdata",
            "name": "NASA Earthdata satellite plastic signal",
            "dataset": "Satellite-derived floating-plastic detection",
            "kind": "satellite-derived estimate",
            "access": "Requires a NASA Earthdata token",
            "licence": "NASA Earthdata - open, attribution required",
            "homepage": "https://www.earthdata.nasa.gov/",
            "endpoint": "https://data.earthdata.nasa.gov/",
            "requires_credentials": True,
            "used_for": "Optional enrichment; absent unless a token is configured.",
        },
    ]
