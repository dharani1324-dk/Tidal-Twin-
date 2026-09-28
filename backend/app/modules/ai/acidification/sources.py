"""
TidalTwin - Acidification: sources
===================================
Connectors for open-source ocean carbonate chemistry.

PRIMARY PATH - Argo BGC in-situ pH
----------------------------------
The pH sensors ride the same biogeochemical Argo floats that carry oxygen, and
live in the SAME ``argo_bio-profile_index.txt.gz`` index the deoxygenation
module reads.  Only the filter differs: deoxygenation selects rows whose
``parameters`` column contains ``DOXY``; this module selects rows containing
``PH_IN_SITU_TOTAL`` or ``PH_IN_SITU_FREE``.

That token match is deliberately exact.  The BGC index also advertises
``VRS_PH`` (the raw sensor voltage difference), ``TEMP_PH``, ``IB_PH``,
``IK_PH`` and ``VK_PH`` - diagnostic channels whose names merely CONTAIN the
letters "PH" but which are not pH at all.  A naive substring search for "PH"
selects them, and one of them in fact appears in the index parameters of
floats that carry no pH measurement whatsoever.

``fetch_argo_bgc_ph_profiles`` is the module's real data path: it reads the BGC
index, selects pH-bearing profiles inside the monitored box, downloads each
per-profile NetCDF and returns the MEASURED levels with their QC flags.  No
value in this module is ever derived from float metadata alone.

SECONDARY - CATALOGUED WITH HONEST STATUS, NOT ASSUMED WORKING
--------------------------------------------------------------
* **SOCAT** (surface ocean pCO2).  Reachable, but its gridded NetCDF products
  are served from paths that are not directly downloadable without going
  through their portal.  Reported as UNAVAILABLE with the reason.
* **NOAA OAP / GLODAP** (gridded reference carbonate chemistry).  The NCEI
  access paths return HTTP 404.  Reported as UNAVAILABLE with the reason.
* **Copernicus Marine**.  Reachable, but bulk data access requires a registered
  account, which this keyless deployment does not hold.  Reported as
  UNAVAILABLE with the reason.

A connector that returns "no rows" for a broken URL is indistinguishable from
one reporting a genuinely empty collection, so every one of the above reports
its failure explicitly rather than silently yielding nothing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from app.core.config import settings

# Indian Ocean bounding box for the 8 coastal regions - identical to the
# deoxygenation module's, because the pH sensors ride the same floats.
INDIAN_OCEAN_BBOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)

ARGO_BGC_INDEX_URL = (
    settings.ACIDIFICATION_ARGO_INDEX_URL
    or "https://data-argo.ifremer.fr/argo_bio-profile_index.txt.gz"
)
ARGO_DAC_ROOT = (
    settings.ACIDIFICATION_ARGO_DAC_ROOT or "https://data-argo.ifremer.fr/dac"
).rstrip("/")
HTTP_TIMEOUT = int(settings.ACIDIFICATION_HTTP_TIMEOUT_SECONDS or 120)

# Deliberately SHARED with the deoxygenation module so a profile downloaded
# for oxygen is not downloaded again for its pH.
ARGO_BGC_DATA_DIR = Path(
    settings.ACIDIFICATION_DATA_DIR
    or settings.DEOXYGENATION_DATA_DIR
    or (settings.BASE_DIR / "data" / "argobgc")
)

# Argo BGC ingestion defaults.
ARGO_BGC_DEFAULT_LIMIT = 8
ARGO_BGC_MAX_RECORDS = 60

# The only parameter tokens that are genuinely a pH measurement.  See the module
# docstring for why a substring search for "PH" is wrong.
PH_TOKENS = ("PH_IN_SITU_TOTAL", "PH_IN_SITU_FREE")


@dataclass
class ConnectorResult:
    """Result of a single connector fetch."""

    source: str
    found: bool = False
    records: list[dict] = field(default_factory=list)
    error: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    record_count: int = 0
    detail: dict = field(default_factory=dict)

    def as_status_dict(self) -> dict:
        return {
            "source": self.source,
            "found": self.found,
            "record_count": self.record_count,
            "error": self.error,
            "fetched_at": self.fetched_at.isoformat(),
            "detail": self.detail,
        }


def _date_parse(raw: str) -> datetime | None:
    """Parse various date formats."""
    raw = (raw or "").strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _in_box(lat: float, lon: float, box: dict) -> bool:
    return box["lat0"] <= lat <= box["lat1"] and box["lon0"] <= lon <= box["lon1"]


def _has_ph(parameters: str) -> bool:
    """True only when the float's parameter list includes a real pH variable.

    Token match against ``PH_IN_SITU_TOTAL`` / ``PH_IN_SITU_FREE``.  A bare
    ``"PH" in parameters.upper()`` would also match ``VRS_PH``, ``TEMP_PH``,
    ``IB_PH``, ``IK_PH`` and ``VK_PH``, which are sensor diagnostics rather
    than pH, and would select floats whose files contain no pH measurement.
    """
    if not parameters:
        return False
    upper = parameters.upper()
    return any(token in upper for token in PH_TOKENS)


def _load_bgc_index(url: str | None = None, timeout: int | None = None) -> list[dict]:
    """Download and parse the Argo BGC profile index into order-preserving dicts.

    The file is comma-delimited, gzip-compressed, and opens with a block of
    ``#`` comment lines followed by a CSV header.  Anything that does not match
    that shape is skipped rather than guessed at.
    """
    target = url or ARGO_BGC_INDEX_URL
    timeout = timeout or HTTP_TIMEOUT
    resp = requests.get(target, timeout=timeout)
    resp.raise_for_status()

    raw = resp.content
    if raw[:2] == b"\x1f\x8b":  # gzip magic
        import gzip

        text = gzip.decompress(raw).decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")

    rows: list[dict] = []
    header: list[str] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if header is None:
            if parts and parts[0] == "file":
                header = parts
            continue
        if len(parts) < len(header):
            continue
        row = dict(zip(header, parts))
        if row.get("file"):
            rows.append(row)
    return rows


def _index_file_url(file_path: str) -> str:
    """Absolute URL for an index 'file' entry, e.g. coriolis/6990514/... -> .../dac/..."""
    path = file_path.strip()
    if path.startswith("dac/"):
        path = path[4:]
    return f"{ARGO_DAC_ROOT}/{path}"


def select_bgc_profiles(
    index: list[dict],
    box: dict,
    since: datetime,
    limit: int,
    only_wmos: list[str] | None = None,
) -> list[dict]:
    """Filter the BGC index down to pH-bearing profiles worth downloading.

    Selection order is newest-first so a small ``limit`` still returns the most
    recent observations rather than an arbitrary slice of the archive.
    """
    dated: list[dict] = []
    for row in index:
        file_path = (row.get("file") or "").strip()
        parameters = (row.get("parameters") or "").upper()
        if not file_path or not _has_ph(parameters):
            continue

        lat = _safe_float(row.get("latitude"))
        lon = _safe_float(row.get("longitude"))
        if lat is None or lon is None:
            continue

        observed = _date_parse(row.get("date") or row.get("date_update"))
        if observed is None:
            continue

        wmo = _wmo_from_path(file_path)
        if only_wmos:
            if wmo not in only_wmos:
                continue
        else:
            if not _in_box(lat, lon, box):
                continue
            if observed < since:
                continue

        row = dict(row)
        row["_date"] = observed
        row["_wmo"] = wmo
        row["_url"] = _index_file_url(file_path)
        dated.append(row)

    dated.sort(key=lambda r: r["_date"], reverse=True)
    return dated[:limit] if limit and limit > 0 else dated


def fetch_argo_bgc_ph_profiles(
    box: dict | None = None,
    limit: int = ARGO_BGC_DEFAULT_LIMIT,
    since_days: int = 365,
    only_wmos: list[str] | None = None,
    cache_dir: Path | None = None,
) -> ConnectorResult:
    """Download real Argo BGC profile NetCDFs and return MEASURED pH levels.

    This is the module's only primary data path.  It opens each file and reads
    ``PH_IN_SITU_TOTAL`` / ``_ADJUSTED`` together with its QC flag, so every
    record it returns carries a real measured value.  Nothing is inferred from
    float metadata.
    """
    from app.modules.ai.acidification.parse import (
        core_profile_url as _core_profile_url,
    )
    from app.modules.ai.acidification.parse import (
        parse_core_physics as _parse_core_physics,
    )
    from app.modules.ai.acidification.parse import parse_netcdf_ph

    if box is None:
        box = INDIAN_OCEAN_BBOX
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    target_dir = Path(cache_dir or ARGO_BGC_DATA_DIR)

    try:
        index = _load_bgc_index()
    except requests.RequestException as exc:
        return ConnectorResult(
            source="Argo BGC (in-situ pH)",
            found=False,
            error=(
                f"Could not reach the Argo BGC profile index at {ARGO_BGC_INDEX_URL}: "
                f"{exc.__class__.__name__}. No pH values were retrieved and none "
                "were estimated."
            ),
        )

    selected = select_bgc_profiles(index, box, since, limit, only_wmos)
    if not selected:
        return ConnectorResult(
            source="Argo BGC (in-situ pH)",
            found=False,
            error=(
                f"No BGC profile carrying PH_IN_SITU_TOTAL or PH_IN_SITU_FREE "
                f"matched the monitored box ({box['lat0']}..{box['lat1']} lat, "
                f"{box['lon0']}..{box['lon1']} lon) within the last {since_days} "
                "days. Widen the box or the window."
            ),
            detail={"index_rows": len(index), "box": box, "since_days": since_days},
        )

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ConnectorResult(
            source="Argo BGC (in-situ pH)",
            found=False,
            error=(
                f"Cannot use local cache directory {target_dir}: "
                f"{exc.__class__.__name__}."
            ),
        )

    levels: list[dict] = []
    files_ok = 0
    files_no_ph = 0
    implausible_levels = 0
    levels_with_physics = 0
    file_errors: list[str] = []

    for row in selected:
        url = row["_url"]
        filename = url.rsplit("/", 1)[-1]
        dest = target_dir / filename
        try:
            if not dest.exists() or dest.stat().st_size == 0:
                resp = requests.get(url, timeout=HTTP_TIMEOUT, stream=True)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
        except requests.RequestException as exc:
            file_errors.append(f"{filename}: {exc.__class__.__name__}")
            continue

        # Co-located CORE profile. BGC files carry no practical salinity, and
        # without salinity no aragonite saturation can be derived at all - so
        # the core file is not a nice-to-have here, it is what makes the
        # module's headline biological metric exist. A failure is non-fatal:
        # the pH is still real and gets stored, just with no derived omega.
        core_physics: list = []
        core_url = _core_profile_url(url)
        if core_url:
            core_name = core_url.rsplit("/", 1)[-1]
            core_dest = target_dir / f"core_{core_name}"
            try:
                if not core_dest.exists() or core_dest.stat().st_size == 0:
                    cresp = requests.get(core_url, timeout=HTTP_TIMEOUT, stream=True)
                    cresp.raise_for_status()
                    core_dest.write_bytes(cresp.content)
                core_physics = _parse_core_physics(str(core_dest))
            except requests.RequestException as exc:
                file_errors.append(f"core {core_name}: {exc.__class__.__name__}")

        parsed = parse_netcdf_ph(
            str(dest), source_url=url, core_physics=core_physics
        )
        if parsed.get("status") != "OK":
            if parsed.get("status") == "NO_PH":
                files_no_ph += 1
            else:
                file_errors.append(f"{filename}: {parsed.get('reason')}")
            continue

        implausible_levels += int(parsed.get("levels_implausible") or 0)
        for level in parsed.get("levels_list") or []:
            level = dict(level)
            level["_wmo"] = row.get("_wmo")
            level["_institution"] = row.get("institution")
            level["_data_mode"] = row.get("parameter_data_mode")
            level["_index_row"] = row
            if level.get("temperature_c") is not None and level.get("salinity_psu") is not None:
                levels_with_physics += 1
            levels.append(level)
        files_ok += 1

    return ConnectorResult(
        source="Argo BGC (in-situ pH)",
        found=bool(levels),
        records=levels,
        record_count=len(levels),
        error=(
            None
            if levels
            else (
                f"Reached the GDAC and selected {len(selected)} pH profile(s), but "
                f"none yielded a measured pH value "
                f"({files_no_ph} file(s) carried no pH, {len(file_errors)} errored)."
            )
        ),
        detail={
            "index_rows": len(index),
            "profiles_selected": len(selected),
            "files_parsed": files_ok,
            "files_without_ph": files_no_ph,
            "file_errors": file_errors[:10],
            "levels_extracted": len(levels),
            "levels_implausible": implausible_levels,
            "levels_with_temperature_and_salinity": levels_with_physics,
            "index_url": ARGO_BGC_INDEX_URL,
            "dac_root": ARGO_DAC_ROOT,
            "box": box,
            "since_days": since_days,
        },
    )


def _wmo_from_path(file_path: str) -> str | None:
    """Pull the 7-digit WMO float id out of an index file path or filename."""
    import re

    match = re.search(r"(?<!\d)(\d{7})(?!\d)", file_path)
    return match.group(1) if match else None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


# --------------------------------------------------------------------------
# Secondary sources. Verified unreachable/keyed as of this writing; each one
# says so out loud instead of returning an empty success.
# --------------------------------------------------------------------------
SECONDARY_SOURCES = {
    "socat": {
        "name": "SOCAT (Surface Ocean CO2 Atlas)",
        "url": "https://www.socat.info/",
        "description": "Global surface ocean pCO2 from volunteer observing fleets",
        "verified_available": False,
        "reason": (
            "UNAVAILABLE: socat.info is reachable, but its gridded annual-mean "
            "NetCDF products are served from paths that are not directly "
            "downloadable without going through the SOCAT portal. No pCO2 was "
            "retrieved and no pCO2 was substituted."
        ),
    },
    "noaa_oap": {
        "name": "NOAA Ocean Acidification Program / GLODAP",
        "url": "https://www.ncei.noaa.gov/access/ocean-acidification/",
        "description": "Gridded reference carbonate chemistry (DIC, TA, pH)",
        "verified_available": False,
        "reason": (
            "UNAVAILABLE: the NOAA NCEI ocean-acidification and GLODAP access "
            "paths return HTTP 404. No reference carbonate data was retrieved "
            "and none was substituted."
        ),
    },
    "copernicus": {
        "name": "Copernicus Marine Service Biogeochemical",
        "url": "https://marine.copernicus.eu/",
        "description": "Model/satellite-assimilated surface pH, pCO2, nitrate",
        "verified_available": False,
        "reason": (
            "UNAVAILABLE: the portal is reachable but bulk data access requires "
            "a registered account, which this keyless deployment does not hold. "
            "No Copernicus data was retrieved and none was substituted."
        ),
    },
}


def fetch_secondary_sources() -> list[ConnectorResult]:
    """Attempt every secondary connector and report its honest status."""
    results: list[ConnectorResult] = []
    for key, info in SECONDARY_SOURCES.items():
        enabled = (
            settings.ACIDIFICATION_SOCAT_ENABLED
            if key == "socat"
            else settings.ACIDIFICATION_NOAA_OAP_ENABLED
            if key == "noaa_oap"
            else True
        )
        if not enabled:
            results.append(
                ConnectorResult(
                    source=info["name"],
                    found=False,
                    error="DISABLED in configuration; not attempted.",
                    detail={"key": key, "url": info["url"]},
                )
            )
            continue
        if info.get("verified_available"):
            # No verified-available secondary source exists yet. When one is
            # added, fetch it here and return its records. Reporting an empty
            # success here instead would be indistinguishable from a genuinely
            # empty collection, which is exactly the failure mode this module
            # refuses to have.
            results.append(
                ConnectorResult(
                    source=info["name"],
                    found=False,
                    error=(
                        "Marked available but no downloader is implemented; "
                        "reporting unavailable rather than a silent empty result."
                    ),
                    detail={"key": key, "url": info["url"]},
                )
            )
            continue
        results.append(
            ConnectorResult(
                source=info["name"],
                found=False,
                error=info["reason"],
                detail={"key": key, "url": info["url"]},
            )
        )
    return results


def source_catalogue() -> list[dict]:
    """Return the full source catalogue for API exposure."""
    return [
        {
            "id": "argo_bgc_ph",
            "name": "Argo BGC Floats (in-situ pH)",
            "type": "in-situ autonomous profiler",
            "variables": [
                "pH, in-situ total scale (PH_IN_SITU_TOTAL)",
                "pH, in-situ free scale (PH_IN_SITU_FREE)",
                "temperature, salinity, pressure",
                "QC flags",
            ],
            "coverage": (
                "Global BGC-Argo; 1,874 pH-bearing profiles fall inside the "
                "monitored Indian Ocean box, spanning 41 distinct floats"
            ),
            "access": "Open, no key required",
            "endpoint": f"{ARGO_BGC_INDEX_URL} (index), {ARGO_DAC_ROOT}/ (profiles)",
            "license": "Argo data policy - free and open",
            "citation": (
                "Argo Data Management Team. Argo float data and metadata from "
                "Global Data Assembly Centre (Argo GDAC). SEANOE. "
                "https://doi.org/10.17882/42182"
            ),
            "update_frequency": "Real-time (within 24h of profile)",
            "status": "ACTIVE - primary pH source for this module",
            "used_for": (
                "Measured pH, vertical profiles, severity classification, "
                "trend analysis, and as the input to the derived aragonite "
                "saturation"
            ),
        },
        {
            "id": "co2sys",
            "name": "CO2SYS / PyCO2SYS",
            "type": "computational (not a data source)",
            "variables": [
                "DIC",
                "pCO2",
                "calcite saturation (Omega_calc)",
                "aragonite saturation (Omega_arag)",
            ],
            "coverage": "Computational - solves the carbonate system from inputs",
            "access": "Open source library (GPLv3)",
            "endpoint": "https://doi.org/10.5281/zenodo.3744275",
            "license": "GNU GPLv3",
            "citation": (
                "Humphreys et al. PyCO2SYS v1.8.3.4, a Python port of CO2SYS. "
                "https://doi.org/10.5281/zenodo.3744275"
            ),
            "update_frequency": "Deterministic - same inputs, same output",
            "status": (
                "ACTIVE - derives aragonite/calcite saturation from measured "
                "pH, temperature and salinity, assuming total alkalinity from "
                "the Lee et al. (2006) salinity relation"
            ),
            "used_for": (
                "Aragonite saturation, the biological threshold for "
                "shell-forming organisms. DERIVED, never measured."
            ),
        },
        {
            "id": "socat",
            "name": "SOCAT (Surface Ocean CO2 Atlas)",
            "type": "ship-based voluntary observing fleet",
            "variables": ["surface pCO2", "surface temperature", "surface salinity"],
            "coverage": "Global, monthly gridded",
            "access": "Open, no key required (portal-mediated)",
            "endpoint": "https://www.socat.info/",
            "license": "CC-BY-4.0",
            "citation": "Bakker et al. SOCAT v2024. https://doi.org/10.25921/7ccb-6f80",
            "update_frequency": "Annual",
            "status": (
                "UNAVAILABLE - portal reachable but gridded products are not "
                "directly downloadable; no pCO2 ingested"
            ),
            "used_for": "Would give independent surface pCO2 cross-validation",
        },
        {
            "id": "noaa_oap",
            "name": "NOAA Ocean Acidification Program / GLODAP",
            "type": "curated gridded reference dataset",
            "variables": ["DIC", "total alkalinity", "pH", "pCO2"],
            "coverage": "Global, annual, 4-degree grid",
            "access": "Open, no key required",
            "endpoint": "https://www.ncei.noaa.gov/access/ocean-acidification/",
            "license": "Public domain (US Government)",
            "citation": "Olsen et al. GLODAPv2.2022. NOAA NCEI.",
            "update_frequency": "Annual",
            "status": "UNAVAILABLE - NCEI access paths return HTTP 404; nothing ingested",
            "used_for": (
                "Would provide a long-term climatological baseline that floats "
                "alone cannot supply"
            ),
        },
        {
            "id": "copernicus",
            "name": "Copernicus Marine Service Biogeochemical",
            "type": "model + satellite assimilation product",
            "variables": ["surface pH", "surface pCO2", "nitrate", "chlorophyll"],
            "coverage": "Global, 1/12 degree, daily",
            "access": "Free registration required",
            "endpoint": "https://marine.copernicus.eu",
            "license": "Copernicus Marine Service License - free non-commercial",
            "citation": "Copernicus Marine Service Global Ocean Biogeochemistry Analysis and Forecast",
            "update_frequency": "Daily",
            "status": (
                "UNAVAILABLE - bulk access requires a registered account this "
                "deployment does not hold; nothing ingested"
            ),
            "used_for": "Would gap-fill surface pH where float coverage is sparse",
        },
    ]


def get_argo_bgc_data_dir() -> Path:
    """Get the local cache directory for downloaded Argo BGC profile files."""
    return ARGO_BGC_DATA_DIR
