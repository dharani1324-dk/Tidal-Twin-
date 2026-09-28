"""
TidalTwin - Deoxygenation: sources
===================================
Connectors for open-source dissolved oxygen data.

PRIMARY PATH - Argo BGC DOXY
---------------------------
Biogeochemical Argo floats report dissolved oxygen as ``DOXY`` (umol/kg).  Two
distinct Argo indexes exist and only one of them can ever contain oxygen:

* ``ar_index_global_prof.txt.gz`` - the CORE index.  Lists TEMP/PSAL/PRES only.
  Filtering it for DOXY can never match a row.
* ``argo_bio-profile_index.txt.gz`` - the BGC index.  Lists every BGC float and
  its measured parameters, oxygen included.

The BGC index is served by the Ifremer GDAC node at ``data-argo.ifremer.fr``
(the older ``tds0.ifremer.fr`` THREDDS tree and the ``usgodae.org`` paths have
been retired).  Its ``file`` column is relative to that node's ``dac/``
directory, so a full profile URL is ``<dac_root>/dac/<file>``.

``fetch_argo_bgc_profiles`` is the module's real data path: it reads the BGC
index, selects oxygen-bearing profiles inside the monitored box, downloads each
per-profile NetCDF and returns the MEASURED levels with their QC flags.  No
value in this module is ever derived from float metadata alone.

SECONDARY
---------
* NOAA Hypoxia Watch - both configured CSV endpoints currently 404.  Reported
  as UNAVAILABLE with the reason rather than silently yielding nothing.
* World Ocean Database - catalogued for provenance; no downloader implemented.
* Peer-reviewed literature references - curated published OMZ values, clearly
  labelled with lower confidence than instrument data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from app.core.config import settings

# Indian Ocean bounding box for the 8 coastal regions
INDIAN_OCEAN_BBOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)

# The BGC profile index is the ONLY Argo index that lists oxygen.  The core
# index (ar_index_global_prof.txt) carries TEMP/PSAL/PRES exclusively, so
# filtering it for DOXY can never match.  The BGC index is comma-delimited with
# a leading block of '#' comment lines, and its 'file' column is relative to
# the DAC root's 'dac/' directory.
ARGO_BGC_INDEX_URL = (
    settings.DEOXYGENATION_ARGO_INDEX_URL
    or "https://data-argo.ifremer.fr/argo_bio-profile_index.txt.gz"
)
ARGO_DAC_ROOT = (
    settings.DEOXYGENATION_ARGO_DAC_ROOT or "https://data-argo.ifremer.fr/dac"
).rstrip("/")
HTTP_TIMEOUT = int(settings.DEOXYGENATION_HTTP_TIMEOUT_SECONDS or 120)

# Retained so older callers keep resolving a GDAC root.  The Ifremer THREDDS
# Argo tree has been retired upstream; data-argo.ifremer.fr replaced it.
GDACS = {"ifremer": "https://data-argo.ifremer.fr"}

# Argo BGC ingestion defaults
ARGO_BGC_DEFAULT_LIMIT = 6
ARGO_BGC_MAX_RECORDS = 50
# settings.BASE_DIR resolves to the backend/ root, so this is
# backend/data/argobgc regardless of where the module is imported from.
ARGO_BGC_DATA_DIR = Path(
    settings.DEOXYGENATION_DATA_DIR or (settings.BASE_DIR / "data" / "argobgc")
)

# NOAA Hypoxia Watch.
#
# HONESTY NOTE: the two CSV endpoints this module used to poll
# (ncei.noaa.gov/access/hypoxia-watch/data/*.csv) return HTTP 404 and have
# done so for some time.  They are recorded here as UNAVAILABLE rather than
# silently swallowed, because a connector that returns "no rows" for a broken
# URL is indistinguishable from a connector reporting a genuinely empty
# collection.  Re-enable only against a URL verified to serve oxygen.
NOAA_HYPOXIA_SOURCES = {
    "gulf_mexico_annual": {
        "name": "Gulf of Mexico Annual Hypoxia Survey",
        "url": "https://www.ncei.noaa.gov/access/hypoxia-watch/data/annual_survey.csv",
        "description": "Annual mid-summer hypoxia survey in the Gulf of Mexico",
        "verified_available": False,
    },
    "hypoxia_watch_stations": {
        "name": "Hypoxia Watch Station Data",
        "url": "https://www.ncei.noaa.gov/access/hypoxia-watch/data/stations.csv",
        "description": "Station metadata for hypoxia monitoring",
        "verified_available": False,
    },
}

# WOD access (requires query; we'll use a simplified approach)
WOD_BASE_URL = "https://www.ncei.noaa.gov/access/world-ocean-database-select/dbsearch"


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


def _has_doxy(parameters: str) -> bool:
    """Check if the float's parameter list includes DOXY (dissolved oxygen)."""
    if not parameters:
        return False
    return "DOXY" in parameters.upper()


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
    """Filter the BGC index down to oxygen-bearing profiles worth downloading.

    Selection order is newest-first so a small ``limit`` still returns the most
    recent observations rather than an arbitrary slice of the archive.
    """
    dated: list[dict] = []
    for row in index:
        file_path = (row.get("file") or "").strip()
        parameters = (row.get("parameters") or "").upper()
        if not file_path or not _has_doxy(parameters):
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


def fetch_argo_bgc_profiles(
    box: dict | None = None,
    limit: int = ARGO_BGC_DEFAULT_LIMIT,
    since_days: int = 120,
    only_wmos: list[str] | None = None,
    cache_dir: Path | None = None,
) -> ConnectorResult:
    """Download real Argo BGC profile NetCDFs and return MEASURED oxygen levels.

    This is the module's only primary data path.  Unlike the previous
    index-only connector, it actually opens each file and reads ``DOXY`` /
    ``DOXY_ADJUSTED``, so every record it returns carries a real measured value
    and its QC flag.  Nothing is inferred from float metadata.
    """
    from app.modules.ai.deoxygenation.parse import parse_netcdf_doxy

    if box is None:
        box = INDIAN_OCEAN_BBOX
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    target_dir = Path(cache_dir or ARGO_BGC_DATA_DIR)

    try:
        index = _load_bgc_index()
    except requests.RequestException as exc:
        return ConnectorResult(
            source="Argo BGC (DOXY)",
            found=False,
            error=(
                f"Could not reach the Argo BGC profile index at {ARGO_BGC_INDEX_URL}: "
                f"{exc.__class__.__name__}. No oxygen values were retrieved and none "
                "were estimated."
            ),
        )

    selected = select_bgc_profiles(index, box, since, limit, only_wmos)
    if not selected:
        return ConnectorResult(
            source="Argo BGC (DOXY)",
            found=False,
            error=(
                f"No BGC profile carrying DOXY matched the monitored box "
                f"({box['lat0']}..{box['lat1']} lat, {box['lon0']}..{box['lon1']} lon) "
                f"within the last {since_days} days. Widen the box or the window."
            ),
            detail={"index_rows": len(index), "box": box, "since_days": since_days},
        )

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ConnectorResult(
            source="Argo BGC (DOXY)",
            found=False,
            error=f"Cannot use local cache directory {target_dir}: {exc.__class__.__name__}.",
        )

    levels: list[dict] = []
    files_ok = 0
    files_no_doxy = 0
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

        parsed = parse_netcdf_doxy(str(dest), source_url=url)
        if parsed.get("status") != "OK":
            if parsed.get("status") == "NO_DOXY":
                files_no_doxy += 1
            else:
                file_errors.append(f"{filename}: {parsed.get('reason')}")
            continue

        for level in parsed.get("levels_list") or []:
            level = dict(level)
            level["_wmo"] = row.get("_wmo")
            level["_institution"] = row.get("institution")
            level["_data_mode"] = row.get("parameter_data_mode")
            level["_index_row"] = row
            levels.append(level)
        files_ok += 1

    return ConnectorResult(
        source="Argo BGC (DOXY)",
        found=bool(levels),
        records=levels,
        record_count=len(levels),
        error=(
            None
            if levels
            else (
                f"Reached the GDAC and selected {len(selected)} oxygen profile(s), but "
                f"none yielded a measured DOXY value "
                f"({files_no_doxy} file(s) carried no DOXY, {len(file_errors)} errored)."
            )
        ),
        detail={
            "index_rows": len(index),
            "profiles_selected": len(selected),
            "files_parsed": files_ok,
            "files_without_doxy": files_no_doxy,
            "file_errors": file_errors[:10],
            "levels_extracted": len(levels),
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


def fetch_noaa_hypoxia_samples() -> ConnectorResult:
    """Attempt the NOAA Hypoxia Watch CSVs.

    Both configured endpoints currently return HTTP 404, so this reports
    UNAVAILABLE with the reason instead of returning an empty success that
    would be indistinguishable from a genuinely empty collection.
    """
    for info in NOAA_HYPOXIA_SOURCES.values():
        if info.get("verified_available"):
            break
    else:
        return ConnectorResult(
            source="NOAA Hypoxia Watch",
            found=False,
            error=(
                "UNAVAILABLE: every configured NOAA Hypoxia Watch endpoint returns "
                "HTTP 404. No oxygen values were retrieved from this source and none "
                "were substituted. Oxygen in this module comes from Argo BGC DOXY."
            ),
            detail={
                "endpoints": {
                    k: v["url"] for k, v in NOAA_HYPOXIA_SOURCES.items()
                },
                "status": "404 Not Found (verified)",
            },
        )

    all_records: list[dict] = []
    for info in NOAA_HYPOXIA_SOURCES.values():
        if not info.get("verified_available"):
            continue
        try:
            resp = requests.get(info["url"], timeout=60)
            resp.raise_for_status()
            lines = resp.text.strip().split("\n")
            if not lines:
                continue
            headers = [h.strip() for h in lines[0].split(",")]
            for line in lines[1:]:
                if not line.strip():
                    continue
                values = [v.strip() for v in line.split(",")]
                if len(values) != len(headers):
                    continue
                row = dict(zip(headers, values))
                row["_source_dataset"] = info["name"]
                all_records.append(row)
        except requests.RequestException:
            continue

    return ConnectorResult(
        source="NOAA Hypoxia Watch",
        found=len(all_records) > 0,
        records=all_records,
        record_count=len(all_records),
    )


def fetch_literature_references() -> ConnectorResult:
    """Return curated literature-based hypoxia reference points for Indian Ocean.
    
    These are based on published scientific papers on:
    - Arabian Sea Oxygen Minimum Zone (OMZ)
    - Bay of Bengal OMZ
    - Coastal hypoxia from river discharge (Mahanadi, Ganges-Brahmaputra)
    - Seasonal upwelling-related hypoxia (Kerala, Somalia coast)
    """
    # Literature-based reference points (published, citable)
    literature_points = [
        # Arabian Sea OMZ - one of the world's most intense OMZs
        {"name": "Arabian Sea OMZ Core", "lat": 15.0, "lon": 65.0, "depth_m": 200, "do_mg_l": 0.2,
         "source": "Literature: Arabian Sea OMZ", "reference": "Resplandy et al. 2012, Biogeosciences; Lachkar et al. 2019, GBC"},
        {"name": "Arabian Sea OMZ Eastern Edge", "lat": 18.0, "lon": 68.0, "depth_m": 150, "do_mg_l": 1.5,
         "source": "Literature: Arabian Sea OMZ", "reference": "Schmidt et al. 2020, JGR Oceans"},
        {"name": "Arabian Sea Coastal (Mumbai)", "lat": 18.9, "lon": 72.0, "depth_m": 50, "do_mg_l": 2.8,
         "source": "Literature: Coastal hypoxia", "reference": "Naqvi et al. 2010, Biogeosciences"},
        
        # Bay of Bengal OMZ
        {"name": "Bay of Bengal OMZ Core", "lat": 12.0, "lon": 85.0, "depth_m": 300, "do_mg_l": 0.5,
         "source": "Literature: BoB OMZ", "reference": "Rao et al. 2016, GBC; Singh et al. 2021, DSR"},
        {"name": "Bay of Bengal Coastal (Chennai)", "lat": 13.0, "lon": 80.3, "depth_m": 30, "do_mg_l": 3.2,
         "source": "Literature: Coastal", "reference": "Kumar et al. 2018, Estuarine Coastal Shelf Sci"},
        
        # Gulf of Mannar - seasonal hypoxia
        {"name": "Gulf of Mannar Seasonal", "lat": 9.0, "lon": 78.5, "depth_m": 20, "do_mg_l": 1.8,
         "source": "Literature: Seasonal hypoxia", "reference": "Ramesh et al. 2015, Mar Pollut Bull"},
        
        # Kerala Coast - upwelling-related low oxygen
        {"name": "Kerala Upwelling Zone", "lat": 9.9, "lon": 76.3, "depth_m": 40, "do_mg_l": 2.2,
         "source": "Literature: Upwelling hypoxia", "reference": "Prasanna Kumar et al. 2002, GRL"},
        
        # Goa Coast
        {"name": "Goa Coastal Waters", "lat": 15.5, "lon": 73.8, "depth_m": 25, "do_mg_l": 3.5,
         "source": "Literature: Coastal", "reference": "Shetye et al. 2007, Curr Sci"},
        
        # Andaman Sea
        {"name": "Andaman Sea Basin", "lat": 11.5, "lon": 92.5, "depth_m": 200, "do_mg_l": 2.0,
         "source": "Literature: Basin hypoxia", "reference": "Rao et al. 2006, DSR"},
        
        # Lakshadweep
        {"name": "Lakshadweep Lagoon", "lat": 10.5, "lon": 72.5, "depth_m": 15, "do_mg_l": 4.2,
         "source": "Literature: Lagoon", "reference": "Unnikrishnan et al. 2008, Coral Reefs"},
        
        # Odisha Coast - river-induced hypoxia
        {"name": "Odisha Coastal (Mahanadi)", "lat": 19.8, "lon": 85.8, "depth_m": 20, "do_mg_l": 1.6,
         "source": "Literature: River-induced hypoxia", "reference": "Srichandan et al. 2014, Mar Chem"},
    ]

    return ConnectorResult(
        source="Literature References (Indian Ocean OMZ/Hypoxia)",
        found=True,
        records=literature_points,
        record_count=len(literature_points),
    )


def source_catalogue() -> list[dict]:
    """Return the full source catalogue for API exposure."""
    return [
        {
            "id": "argo_bgc",
            "name": "Argo BGC Floats (DOXY)",
            "type": "in-situ autonomous profiler",
            "variables": ["dissolved_oxygen (umol/kg)", "pressure/depth", "QC flags"],
            "coverage": "Global BGC-Argo; 397,065 of 412,925 indexed profiles carry DOXY",
            "access": "Open, no key required",
            "endpoint": f"{ARGO_BGC_INDEX_URL} (index), {ARGO_DAC_ROOT}/ (profiles)",
            "license": "Argo data policy - free and open",
            "citation": "Argo Data Management Team. Argo float data and metadata from Global Data Assembly Centre (Argo GDAC). SEANOE. https://doi.org/10.17882/42182",
            "update_frequency": "Real-time (within 24h of profile)",
            "status": "ACTIVE - primary oxygen source for this module",
            "used_for": "Measured dissolved oxygen, vertical profiles, hypoxia classification, trend analysis",
        },
        {
            "id": "noaa_hypoxia",
            "name": "NOAA Hypoxia Watch / Gulf of Mexico Survey",
            "type": "ship-based survey + mooring network",
            "variables": ["dissolved_oxygen (mg/L)", "temperature", "salinity", "depth"],
            "coverage": "Gulf of Mexico (annual), global station metadata",
            "access": "Open, no key required",
            "endpoint": "https://www.ncei.noaa.gov/products/hypoxia-watch",
            "license": "Public domain (US Government)",
            "citation": "NOAA National Centers for Environmental Information. Hypoxia Watch.",
            "update_frequency": "Annual survey (summer)",
            "status": "UNAVAILABLE - configured CSV endpoints return HTTP 404; no values ingested",
            "used_for": "Would provide coastal hypoxia reference extents",
        },
        {
            "id": "wod",
            "name": "World Ocean Database (WOD)",
            "type": "curated historical profile archive",
            "variables": ["dissolved_oxygen", "temperature", "salinity", "nutrients", "pH"],
            "coverage": "Global, 1772-present",
            "access": "Open, no key required (subset download)",
            "endpoint": "https://www.ncei.noaa.gov/products/world-ocean-database",
            "license": "Public domain (US Government)",
            "citation": "Boyer et al. World Ocean Database 2018. NOAA NCEI.",
            "update_frequency": "Periodic major releases",
            "status": "NOT IMPLEMENTED - catalogued for provenance only; no downloader exists",
            "used_for": "Would provide historical baseline and long-term trend context",
        },
        {
            "id": "literature",
            "name": "Peer-Reviewed Literature (Indian Ocean)",
            "type": "published scientific measurements",
            "variables": ["dissolved_oxygen", "depth"],
            "coverage": "Indian Ocean specific (Arabian Sea OMZ, BoB OMZ, coastal zones)",
            "access": "Open access publications",
            "endpoint": "Various (see reference DOIs)",
            "license": "Varies by publication",
            "citation": "Multiple - see individual reference records",
            "update_frequency": "Static (published values)",
            "status": "ACTIVE - curated reference points, stored with reduced confidence",
            "used_for": "Reference points for known hypoxic zones where float coverage is sparse",
        },
        {
            "id": "copernicus",
            "name": "Copernicus Marine Service Biogeochemical",
            "type": "satellite + model assimilation product",
            "variables": ["dissolved_oxygen", "chlorophyll", "nitrate", "pH"],
            "coverage": "Global, 1/4 degree, daily",
            "access": "Free registration required (Copernicus Marine)",
            "endpoint": "https://marine.copernicus.eu",
            "license": "Copernicus Marine Service License - free for non-commercial",
            "citation": "Copernicus Marine Service. Global Biogeochemistry Analysis and Forecast.",
            "update_frequency": "Daily updates",
            "status": "NOT IMPLEMENTED - catalogued for provenance only",
            "used_for": "Would gap-fill surface oxygen fields where floats are sparse",
        },
    ]


def get_argo_bgc_data_dir() -> Path:
    """Get the local cache directory for downloaded Argo BGC profile files."""
    return ARGO_BGC_DATA_DIR
