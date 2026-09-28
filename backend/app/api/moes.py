"""MoES source registry backed by the public INCOIS ERDDAP catalog.

Only the catalog is queried here. Dataset rows are metadata, not downloaded
measurements; product endpoints remain linked to their source and existing
product-specific ingestion routes.
"""

import csv
import io
import math
import re
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib.parse import quote
from datetime import datetime, timezone

import httpx
import truststore
from fastapi import APIRouter, Query

from app.core.config import settings
from app.schemas.moes import UnifiedOceanRecord
from app.services.moes_normalizer import normalize_argo_grid, normalize_indobis_occurrences

router = APIRouter(prefix="/api/v1/moes", tags=["MoES Data"])
_catalog_cache: dict = {"at": 0.0, "payload": None}
_CACHE_SECONDS = 300
_grid_cache: dict[tuple, dict] = {}
_indobis_cache: dict = {"at": 0.0, "payload": None}
_niot_cache: dict = {"at": 0.0, "payload": None}
_iitm_cache: dict = {"at": 0.0, "payload": None}
_imd_cache: dict = {"at": 0.0, "payload": None}
_thredds_cache: dict[str, dict] = {}
_forecast_cache: dict[tuple, dict] = {}
_THREDDS_BASE = "https://incois.gov.in/thredds"
INDOBIS_NODE_ID = "1a3b0f1a-4474-4d73-9ee1-d28f92a83996"
INDOBIS_API = "https://api.obis.org/v3"

INSTITUTIONS = [
    {"id": "INCOIS", "name": "Indian National Centre for Ocean Information Services", "official_url": "https://www.incois.gov.in/", "endpoint": "https://erddap.incois.gov.in/erddap and https://incois.gov.in/thredds", "protocol": "ERDDAP tabledap / griddap / WMS; THREDDS WMS / NCSS", "dataset": "Public ERDDAP catalog, Argo products, and RSMC operational forecasts", "category": "ocean observations, satellite products, analyses, forecasts", "variable": "Dataset-specific; see per-dataset metadata", "units": "Dataset-specific", "temporal_resolution": "Dataset-specific", "coverage": "Per dataset; see catalog and metadata", "spatial_resolution": "Per dataset; see catalog and metadata", "attribution": "INCOIS ERDDAP / Ocean State Forecast; see dataset metadata", "license": "Dataset-specific; see source metadata"},
    {"id": "NIOT", "name": "National Institute of Ocean Technology", "official_url": "https://services.niot.res.in/BuoyNetwork/", "endpoint": "https://services.niot.res.in/oos_app/api/dashboard/GetAllBuoysList?is_all=false", "protocol": "NIOT Ocean Observation Systems JSON API", "dataset": "Buoy station and reported data-availability catalog", "category": "ocean observation station metadata", "variable": "Station position, deployment dates, reported data period", "units": "degrees, source date strings", "temporal_resolution": "Not exposed by station catalog", "coverage": "Station points are filtered by requested region", "spatial_resolution": "Station coordinates; no grid resolution", "attribution": "NIOT Ocean Observation Systems", "license": "See NIOT source terms"},
    {"id": "NCCR", "name": "National Centre for Coastal Research", "official_url": "https://www.nccr.gov.in/sites/default/files/schangenew.pdf", "endpoint": None, "protocol": "Public shoreline assessment PDF; no machine-readable service verified", "dataset": "National Assessment of Shoreline Changes (1990-2016)", "category": "coastal morphology and shoreline change", "variable": "Shoreline change rate and erosion/accretion/stable classes", "units": "Categorical and report-defined rate units", "temporal_resolution": "Assessment period 1990-2016", "coverage": "Indian mainland coastline", "spatial_resolution": "Assessment maps at 1:25,000 scale", "attribution": "National Centre for Coastal Research", "license": "Not listed"},
    {"id": "CMLRE", "name": "Centre for Marine Living Resources & Ecology", "official_url": "https://indobis.in/", "endpoint": INDOBIS_API, "protocol": "OBIS API v3 (IndOBIS node)", "dataset": "IndOBIS marine species occurrences", "category": "marine biodiversity", "variable": "Species occurrence", "units": "Not applicable", "temporal_resolution": "Per-record event date", "coverage": "Per occurrence coordinates and requested bounds", "spatial_resolution": "Point occurrences; no regular grid", "attribution": "CMLRE / IndOBIS via OBIS", "license": "Per occurrence record; see OBIS metadata"},
    {"id": "NCPOR", "name": "National Centre for Polar and Ocean Research", "official_url": "https://data.ncpor.res.in/", "endpoint": None, "protocol": "Public weather dashboard is HTML; individual archive downloads may require a request", "dataset": "Public Indian polar-station weather dashboard and polar data catalog", "category": "polar ocean and earth-system data", "variable": "Dashboard air temperature; archive variables vary by dataset", "units": "degC for current station temperatures", "temporal_resolution": "Hourly dashboard timestamp; archive varies by dataset", "coverage": "Maitri, Bharati, Himadri, Himansh; archive coverage varies", "spatial_resolution": "Station point observations", "attribution": "NCPOR National Polar Data Center", "license": "Per-dataset terms"},
    {"id": "IMD", "name": "India Meteorological Department", "official_url": "https://mausam.imd.gov.in/responsive/apis.php", "endpoint": "https://mausam.imd.gov.in/api/port_wx_api.php", "protocol": "Official JSON API; server IP/domain whitelist required", "dataset": "Port weather API availability probe", "category": "weather and atmospheric forcing", "variable": "Port weather (probe only; values not ingested)", "units": None, "temporal_resolution": None, "attribution": "India Meteorological Department", "license": "See IMD API terms"},
    {"id": "NCMRWF", "name": "National Centre for Medium Range Weather Forecasting", "official_url": "https://ncmrwf.gov.in/", "endpoint": "https://www.ncmrwf.gov.in/data/", "protocol": "Official public data access portal; no stable service was verified", "dataset": "Forecast data access portal", "category": "numerical weather prediction", "variable": "Dataset-specific", "units": "Dataset-specific", "temporal_resolution": "Dataset-specific", "attribution": "NCMRWF", "license": "See source terms"},
    {"id": "IITM", "name": "Indian Institute of Tropical Meteorology", "official_url": "https://www.tropmet.res.in/", "endpoint": "https://ardc.tropmet.res.in/thredds/", "protocol": "THREDDS OPeNDAP / NetCDF Subset Service", "dataset": "IITM/CCCR public climate and ocean-atmosphere archives", "category": "climate and ocean-atmosphere research", "variable": "Dataset-specific; includes SST and atmospheric fields", "units": "Dataset-specific", "temporal_resolution": "Dataset-specific; archive and hindcast products", "coverage": "Dataset-specific; regional South Asia and global datasets", "spatial_resolution": "Dataset-specific", "attribution": "IITM / CCCR; see dataset metadata", "license": "Dataset-specific; see source metadata"},
    {"id": "NCESS", "name": "National Centre for Earth Science Studies", "official_url": "https://ngdc.ncess.gov.in/", "endpoint": "https://ngdc.ncess.gov.in/", "protocol": "National Geoscience Data Portal (testing/trial)", "dataset": "Portal landing page", "category": "geoscience and coastal data", "variable": None, "units": None, "temporal_resolution": None, "attribution": "NCESS National Geoscience Data Centre", "license": "Not listed"},
]

FEATURE_DATASETS = {
    "temperature": ["incois_argo_10d_VAM", "incois_argo_10day_McCreary", "NOAA_AVHRR_AMSR_datasets"],
    "waves": [],
    "currents": ["incois_valueadded_products_datasets"],
    "salinity": ["incois_argo_10d_VAM", "incois_argo_10day_McCreary", "incois_argo_mnt_VAM"],
    "sea-level": [],
    "wind": ["ascat_daily_datasets", "ascat_mnt_datasets", "incois_quickscat_daily_datasets"],
    "chlorophyll": ["incois_oceansat2_datasets", "IRS_chlorophyll_datasets"],
    "biodiversity": [],
    "profiles": ["Indian_ARGO_Floats", "incois_argo_10d_VAM", "incois_argo_10day_McCreary"],
    "forecast": [],
    "coastal-change": [],
    "events": [],
    "model-observation": ["incois_argo_10d_VAM", "incois_argo_10day_McCreary"],
    "disagreement": [],
    "confidence": [],
    "fusion": [],
    "ocean-health": [],
    "data-explorer": [],
    "polar": [],
    "provenance": [],
}

FEATURE_LABELS = {
    "temperature": "Ocean Temperature", "waves": "Wave Intelligence",
    "currents": "Ocean Currents", "salinity": "Salinity",
    "sea-level": "Sea Level", "wind": "Wind & Atmospheric Forcing",
    "chlorophyll": "Chlorophyll", "biodiversity": "Marine Biodiversity",
    "profiles": "Ocean Depth Profiles", "forecast": "Ocean Forecast",
    "coastal-change": "Coastal Change", "events": "Ocean Events",
    "model-observation": "Model vs Observation", "disagreement": "Data Disagreement",
    "confidence": "Confidence Engine", "fusion": "Multi-Source Fusion",
    "ocean-health": "Ocean Health", "data-explorer": "MoES Data Explorer",
    "polar": "Polar Ocean", "provenance": "Data Provenance",
}


def _load_catalog() -> dict:
    now = time.monotonic()
    cached = _catalog_cache.get("payload")
    if cached is not None and now - _catalog_cache["at"] < _CACHE_SECONDS:
        return {**cached, "served_from_cache": True}
    columns = "datasetID,title,institution,dataStructure,accessible,minTime,maxTime,summary,minLatitude,maxLatitude,latitudeSpacing,minLongitude,maxLongitude,longitudeSpacing,minAltitude,maxAltitude,timeSpacing"
    endpoint = settings.INCOIS_ERDDAP_BASE.rstrip("/") + "/tabledap/allDatasets.csv?" + columns
    checked = datetime.now(timezone.utc).isoformat()
    try:
        # Use the operating system's trusted CA store (also works behind
        # managed Windows TLS inspection) while retaining normal validation.
        response = httpx.get(
            endpoint,
            timeout=httpx.Timeout(20, connect=8),
            follow_redirects=True,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        datasets = []
        for row in reader:
            if not row.get("datasetID") or row["datasetID"] == "allDatasets":
                continue
            temporal_end = row.get("maxTime") or None
            observation_age_days = None
            if temporal_end:
                try:
                    source_time = datetime.fromisoformat(temporal_end.replace("Z", "+00:00"))
                    observation_age_days = max(0, (datetime.now(timezone.utc) - source_time).days)
                except ValueError:
                    pass
            datasets.append({
                "id": row.get("datasetID", ""), "name": row.get("title", ""),
                "institution": row.get("institution", "INCOIS"),
                "protocol": "ERDDAP griddap" if row.get("dataStructure") == "grid" else "ERDDAP tabledap",
                "access": row.get("accessible", "unknown"),
                "temporal_start": row.get("minTime") or None,
                "temporal_end": temporal_end,
                # ERDDAP maxTime is the latest observation time, not a claim
                # that the dataset itself was refreshed at that time.
                "observation_age_days": observation_age_days,
                "last_updated": temporal_end,
                "temporal_resolution_seconds": _float_or_none(row.get("timeSpacing")),
                "spatial_resolution": {"latitude_deg": _float_or_none(row.get("latitudeSpacing")), "longitude_deg": _float_or_none(row.get("longitudeSpacing"))},
                "coverage": {"south": _float_or_none(row.get("minLatitude")), "north": _float_or_none(row.get("maxLatitude")), "west": _float_or_none(row.get("minLongitude")), "east": _float_or_none(row.get("maxLongitude"))},
                "status": "CATALOGED" if row.get("accessible") == "public" else "ACCESS_RESTRICTED",
                "variable": None,
                "units": None,
                "attribution": row.get("institution") or "INCOIS ERDDAP",
                "license": "See per-dataset metadata; license terms may differ.",
                "description": row.get("summary", ""),
                "url": settings.INCOIS_ERDDAP_BASE.rstrip("/") + "/info/" + row["datasetID"] + "/index.html",
            })
        payload = {"status": "LIVE" if datasets else "TEMPORARILY_UNAVAILABLE", "checked_at": checked, "endpoint": endpoint, "datasets": datasets, "error": None if datasets else "The catalog returned no datasets.", "served_from_cache": False}
    except (httpx.HTTPError, csv.Error, ValueError) as exc:
        payload = {"status": "TEMPORARILY_UNAVAILABLE", "checked_at": checked, "endpoint": endpoint, "datasets": [], "error": str(exc)[:300], "served_from_cache": False}
    _catalog_cache.update(at=now, payload=payload)
    return payload


def _float_or_none(value: str | None) -> float | None:
    try:
        number = float(value) if value is not None else float("nan")
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _check_imd_api() -> dict:
    """Probe the documented API and retain its actual current access result."""
    checked = datetime.now(timezone.utc).isoformat()
    try:
        response = httpx.get("https://mausam.imd.gov.in/api/port_wx_api.php",
                             timeout=httpx.Timeout(5, connect=3), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        if "whitelist" in response.text.casefold():
            return {"status": "ACCESS_RESTRICTED", "error": "IMD requires this server IP/domain to be whitelisted.", "checked_at": checked}
        if response.is_success:
            return {"status": "LIVE", "error": None, "checked_at": checked}
        return {"status": "TEMPORARILY_UNAVAILABLE", "error": f"IMD API returned HTTP {response.status_code}.", "checked_at": checked}
    except httpx.HTTPError as exc:
        return {"status": "TEMPORARILY_UNAVAILABLE", "error": str(exc)[:200], "checked_at": checked}


def _load_imd_status() -> dict:
    now = time.monotonic()
    cached = _imd_cache.get("payload")
    if cached is not None and now - _imd_cache["at"] < _CACHE_SECONDS:
        return {**cached, "served_from_cache": True}
    payload = {**_check_imd_api(), "served_from_cache": False}
    _imd_cache.update(at=now, payload=payload)
    return payload


@router.get("/registry")
def registry():
    """Return uniform source metadata plus statuses from real endpoint checks."""
    # These are independent upstream services; probe concurrently so one slow
    # institution does not serialize the entire source registry response.
    with ThreadPoolExecutor(max_workers=5) as pool:
        catalog_future = pool.submit(_load_catalog)
        indobis_future = pool.submit(_load_indobis_status)
        niot_future = pool.submit(_load_niot_buoys)
        imd_future = pool.submit(_load_imd_status)
        iitm_future = pool.submit(_load_iitm_status)
        catalog = catalog_future.result()
        indobis = indobis_future.result()
        niot = niot_future.result()
        imd = imd_future.result()
        iitm = iitm_future.result()
    checks = {
        "INCOIS": {"status": catalog["status"], "checked_at": catalog["checked_at"], "cached": catalog["served_from_cache"], "error": catalog["error"], "live": catalog["status"] == "LIVE"},
        "NIOT": {"status": niot["status"], "checked_at": niot["checked_at"], "cached": niot["served_from_cache"], "error": niot["error"], "live": niot["status"] == "LIVE"},
        "CMLRE": {"status": indobis["status"], "checked_at": indobis["checked_at"], "cached": indobis["served_from_cache"], "error": indobis["error"], "live": indobis["status"] == "LIVE"},
        "IMD": {"status": imd["status"], "checked_at": imd["checked_at"], "cached": imd["served_from_cache"], "error": imd["error"], "live": imd["status"] == "LIVE"},
    }
    unavailable = {"NCCR": "PUBLIC_ENDPOINT_NOT_AVAILABLE", "NCMRWF": "PUBLIC_ENDPOINT_NOT_AVAILABLE", "NCPOR": "PUBLIC_ENDPOINT_NOT_AVAILABLE", "NCESS": "PORTAL_IN_TRIAL"}
    explanatory_errors = {
        "NCCR": "Official portal is linked; no public machine-readable endpoint has been verified for this integration.",
        "NCMRWF": "Official portal is linked; no public machine-readable endpoint has been verified for this integration.",
        "NCPOR": "Public station dashboard is HTML only; no stable machine-readable weather API is verified. Individual archive downloads may require a request.",
        "NCESS": "The official portal identifies itself as testing/trial; no stable API is connected.",
    }
    checks["IITM"] = {"status": iitm["status"], "checked_at": iitm["checked_at"], "cached": iitm["served_from_cache"], "error": iitm["error"], "live": iitm["status"] == "LIVE"}
    records = []
    for item in INSTITUTIONS:
        check = checks[item["id"]] if item["id"] in checks else {"status": unavailable[item["id"]], "checked_at": None, "cached": False, "error": explanatory_errors[item["id"]], "live": False}
        record = {
            **item,
            "institution": item["name"],
            "endpoint": item.get("endpoint"),
            "spatial_resolution": item.get("spatial_resolution", "Not listed by source"),
            "temporal_resolution": item.get("temporal_resolution", "Not listed by source"),
            "coverage": item.get("coverage", "Not listed by source"),
            "last_updated": None,
            "checked_at": None,
            "url": item["official_url"],
            "live": False,
            "cached": False,
            "error": None,
            **check,
        }
        records.append(record)
    return {"checked_at": catalog["checked_at"], "sources": records, "dataset_count": len(catalog["datasets"]), "catalog_status": catalog["status"]}


def _load_indobis_status() -> dict:
    now = time.monotonic()
    cached = _indobis_cache.get("payload")
    if cached is not None and now - _indobis_cache["at"] < _CACHE_SECONDS:
        return {**cached, "served_from_cache": True}
    checked = datetime.now(timezone.utc).isoformat()
    try:
        response = httpx.get(f"{INDOBIS_API}/node/{INDOBIS_NODE_ID}",
                             timeout=httpx.Timeout(15, connect=8), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        response.raise_for_status()
        payload = {"status": "LIVE", "checked_at": checked, "error": None, "served_from_cache": False}
    except (httpx.HTTPError, ValueError) as exc:
        payload = {"status": "TEMPORARILY_UNAVAILABLE", "checked_at": checked, "error": str(exc)[:250], "served_from_cache": False}
    _indobis_cache.update(at=now, payload=payload)
    return payload


def _load_niot_buoys() -> dict:
    now = time.monotonic()
    cached = _niot_cache.get("payload")
    if cached is not None and now - _niot_cache["at"] < _CACHE_SECONDS:
        return {**cached, "served_from_cache": True}
    checked = datetime.now(timezone.utc).isoformat()
    endpoint = "https://services.niot.res.in/oos_app/api/dashboard/GetAllBuoysList?is_all=false"
    try:
        response = httpx.get(endpoint, timeout=httpx.Timeout(20, connect=8), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        response.raise_for_status()
        body = response.json()
        raw = body.get("GetAllBuoysResp") or []
        stations = []
        for row in raw:
            try:
                lat, lon = float(row.get("dep_latitude")), float(row.get("dep_longitude"))
            except (TypeError, ValueError):
                continue
            station_type = {"OB": "Omni buoy", "DB": "Data buoy", "TB2": "Tsunami buoy"}.get(row.get("s_type"), row.get("s_type"))
            stations.append({
                "station_id": row.get("stationid"), "buoy_id": row.get("b_buoyid"),
                "type": station_type, "status": row.get("s_status"),
                "latitude": lat, "longitude": lon,
                "deployed_at": row.get("b_depdt"), "retrieved_at": row.get("b_retrivaldate"),
                "data_period": row.get("b_data_avail"),
                "record_available": bool(row.get("b_data_avail")),
            })
        payload = {"status": "LIVE" if stations else "TEMPORARILY_UNAVAILABLE", "checked_at": checked,
                   "endpoint": endpoint, "stations": stations,
                   "error": None if stations else "NIOT returned no buoy station records.", "served_from_cache": False}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        payload = {"status": "TEMPORARILY_UNAVAILABLE", "checked_at": checked,
                   "endpoint": endpoint, "stations": [], "error": str(exc)[:250], "served_from_cache": False}
    _niot_cache.update(at=now, payload=payload)
    return payload


def _load_iitm_status() -> dict:
    """Probe IITM's documented institutional THREDDS catalog with TLS validation."""
    now = time.monotonic()
    cached = _iitm_cache.get("payload")
    if cached is not None and now - _iitm_cache["at"] < _CACHE_SECONDS:
        return {**cached, "served_from_cache": True}
    checked = datetime.now(timezone.utc).isoformat()
    endpoint = "https://ardc.tropmet.res.in/thredds/catalog/las/catalog.xml"
    try:
        response = httpx.get(endpoint, timeout=httpx.Timeout(12, connect=6), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        response.raise_for_status()
        payload = {"status": "LIVE", "checked_at": checked, "error": None, "served_from_cache": False}
    except httpx.HTTPError as exc:
        payload = {"status": "TEMPORARILY_UNAVAILABLE", "checked_at": checked,
                   "error": f"IITM THREDDS endpoint did not pass the current validated request: {str(exc)[:220]}",
                   "served_from_cache": False}
    _iitm_cache.update(at=now, payload=payload)
    return payload


@router.get("/datasets")
def datasets(q: str = Query(default="", max_length=120), limit: int = Query(default=200, ge=1, le=500)):
    """Search INCOIS's live ERDDAP catalog. The data server remains the source of record."""
    catalog = _load_catalog()
    needle = q.casefold().strip()
    rows = catalog["datasets"]
    if needle:
        rows = [r for r in rows if needle in (r["name"] + " " + r["id"] + " " + r["description"] + " " + r["institution"] + " " + _dataset_search_terms(r["id"])).casefold()]
    return {"status": catalog["status"], "checked_at": catalog["checked_at"], "endpoint": catalog["endpoint"], "count": len(rows), "datasets": rows[:limit], "error": catalog["error"]}


@router.get("/features/{feature_id}")
def feature_sources(feature_id: str):
    """Resolve feature cards to real catalog entries and report evidence limits."""
    if feature_id not in FEATURE_DATASETS:
        return {"available": False, "status": "FEATURE_NOT_FOUND", "feature_id": feature_id}
    catalog = _load_catalog()
    dataset_ids = set(FEATURE_DATASETS[feature_id])
    matches = [dataset for dataset in catalog["datasets"] if dataset["id"] in dataset_ids]
    source_status = catalog["status"]
    source_ids = ["INCOIS"]
    notes = []
    live_measurements = False
    if feature_id == "biodiversity":
        node = _load_indobis_status()
        source_ids = ["CMLRE"]
        source_status = node["status"]
        live_measurements = node["status"] == "LIVE"
        notes.append("The endpoint returns published occurrence records with event dates, not live abundance or animal tracks.")
    elif feature_id in ("waves", "currents"):
        buoy = _load_niot_buoys()
        source_ids = ["INCOIS", "NIOT"]
        try:
            operational_file = _latest_thredds_file("wave" if feature_id == "waves" else "ocean")
            source_status = "LIVE"
            notes.append(f"INCOIS RSMC {('WaveWatch III' if feature_id == 'waves' else 'HYCOM')} forecast file is available; model output is distinct from buoy observations.")
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            operational_file = None
            source_status = buoy["status"]
            notes.append(f"Operational INCOIS forecast catalog could not be read: {str(exc)[:180]}")
        notes.append("NIOT's connected public endpoint returns station metadata and reported historical data periods, not buoy sensor values.")
    elif feature_id in ("temperature", "salinity", "profiles", "model-observation"):
        notes.append("The connected Argo gridded product is an analysis; its observation timestamp and age are shown separately from request time.")
        if feature_id in ("temperature", "salinity"):
            try:
                operational_file = _latest_thredds_file("ocean")
                source_status = "LIVE"
                source_ids = ["INCOIS"]
                notes.append("An operational INCOIS HYCOM forecast is also available and is labeled as model forecast output.")
            except (httpx.HTTPError, ET.ParseError, ValueError):
                operational_file = None
    elif feature_id in ("sea-level", "wind", "forecast"):
        try:
            operational_file = _latest_thredds_file("wave" if feature_id == "wind" else "ocean")
            source_status = "LIVE"
            source_ids = ["INCOIS"]
            notes.append("An operational INCOIS THREDDS forecast file is available. Forecast values are kept separate from observations.")
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            operational_file = None
            notes.append(f"No current operational forecast file was resolved: {str(exc)[:180]}")
    if feature_id == "data-explorer":
        matches = catalog["datasets"]
    if feature_id == "polar":
        source_ids = ["INCOIS", "NCPOR"]
        notes.append("No polar dataset matched the connected INCOIS catalog; NCPOR portal remains linked in the institution registry.")
    if feature_id == "coastal-change":
        source_ids = ["NCCR"]
    if feature_id in ("coastal-change", "events", "disagreement", "confidence", "fusion", "ocean-health"):
        notes.append("The existing project workspace is available, but no matching public MoES machine-readable product is connected in this integration.")
    operational_file = locals().get("operational_file")
    forecast_available = bool(operational_file)
    forecast_age_hours = None
    forecast_freshness = None
    if operational_file and operational_file.get("run_time"):
        forecast_age_hours = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(operational_file["run_time"])).total_seconds() / 3600)
        forecast_freshness = "LIVE" if forecast_age_hours <= 30 else "STALE"
    data_available = bool(matches) or (feature_id == "biodiversity" and source_status == "LIVE") or forecast_available
    data_status = f"{forecast_freshness}_FORECAST_AVAILABLE" if forecast_freshness else ("CATALOGED" if matches else ("LIVE_ARCHIVE" if feature_id == "biodiversity" and source_status == "LIVE" else "PUBLIC_ENDPOINT_NOT_AVAILABLE"))
    return {
        "available": data_available, "feature_id": feature_id,
        "feature": FEATURE_LABELS[feature_id], "status": source_status,
        "data_status": data_status, "live_endpoint": source_status == "LIVE",
        "live_measurements": live_measurements,
        "forecast_available": forecast_available,
        "forecast_freshness": forecast_freshness,
        "forecast_age_hours": round(forecast_age_hours, 1) if forecast_age_hours is not None else None,
        "forecast_file": operational_file.get("filename") if forecast_available else None,
        "forecast_run": operational_file.get("run_time") if forecast_available else None,
        "forecast_source_url": operational_file.get("source_url") if forecast_available else None,
        "checked_at": catalog["checked_at"], "sources": source_ids,
        "dataset_count": len(matches), "datasets": matches,
        "notes": notes,
    }


def _dataset_search_terms(dataset_id: str) -> str:
    """Known product keywords used for discovery, never for data inference."""
    normalized = dataset_id.casefold()
    if "argo" in normalized:
        return "argo profile temperature salinity temp sal depth"
    if "oceansat" in normalized or "chlorophyll" in normalized:
        return "chlorophyll ocean colour kd490 satellite"
    if "ascat" in normalized or "quickscat" in normalized:
        return "wind speed direction scatterometer"
    return ""


@router.get("/datasets/{dataset_id}")
def dataset_metadata(dataset_id: str):
    """Retrieve official ERDDAP variable units, coverage, and usage metadata."""
    catalog = _load_catalog()
    dataset = next((item for item in catalog["datasets"] if item["id"] == dataset_id), None)
    if dataset is None:
        return {"available": False, "status": "DATASET_NOT_FOUND", "error": "Dataset is not in the current public catalog."}
    url = settings.INCOIS_ERDDAP_BASE.rstrip("/") + f"/info/{dataset_id}/index.json"
    try:
        response = httpx.get(url, timeout=httpx.Timeout(15, connect=8), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        response.raise_for_status()
        table = response.json().get("table", {})
        attrs: dict[str, dict[str, str]] = {}
        variables = []
        for row in table.get("rows", []):
            if len(row) < 5:
                continue
            row_type, variable, attr, _, value = row[:5]
            if row_type == "variable":
                variables.append({"name": variable, "dimensions": value, "attributes": {}})
                attrs.setdefault(variable, {})
            elif row_type == "attribute":
                attrs.setdefault(variable, {})[attr] = value
        for variable in variables:
            variable["attributes"] = attrs.get(variable["name"], {})
        global_attrs = attrs.get("NC_GLOBAL", {})
        checked = datetime.now(timezone.utc).isoformat()
        return {
            "available": True, "status": "CATALOGED", "checked_at": checked,
            "institution": global_attrs.get("institution", dataset["institution"]),
            "dataset_id": dataset_id, "dataset": global_attrs.get("title", dataset["name"]),
            "variables": variables, "temporal_coverage": {"start": global_attrs.get("time_coverage_start", dataset["temporal_start"]), "end": global_attrs.get("time_coverage_end", dataset["temporal_end"])},
            "spatial_coverage": dataset["coverage"], "spatial_resolution": dataset["spatial_resolution"],
            "license": global_attrs.get("license"), "attribution": global_attrs.get("institution", dataset["institution"]),
            "source_url": dataset["url"], "error": None,
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"available": False, "status": "TEMPORARILY_UNAVAILABLE", "dataset_id": dataset_id, "source_url": dataset["url"], "error": str(exc)[:250]}


@router.get("/buoys")
def niot_buoys(
    south: float = Query(default=-30, ge=-90, le=90),
    north: float = Query(default=30, ge=-90, le=90),
    west: float = Query(default=30, ge=-180, le=180),
    east: float = Query(default=120, ge=-180, le=180),
):
    """Live NIOT buoy station catalog and the source-reported data periods.

    This endpoint lists stations and metadata; it does not expose buoy sensor
    time series. Historical availability periods are not current readings.
    """
    if south >= north or west >= east:
        return {"available": False, "status": "INVALID_BOUNDS", "error": "south must be below north and west below east."}
    source = _load_niot_buoys()
    if source["status"] != "LIVE":
        return {"available": False, "status": source["status"], "checked_at": source["checked_at"], "error": source["error"], "source_url": "https://services.niot.res.in/BuoyNetwork/"}
    stations = [s for s in source["stations"] if south <= s["latitude"] <= north and west <= s["longitude"] <= east]
    return {
        "available": True, "status": "LIVE", "checked_at": source["checked_at"],
        "provider": "NIOT Ocean Observation Systems", "dataset": "Met-ocean buoy station and data-availability catalog",
        "station_count": len(stations), "stations": stations,
        "data_status_note": "The API lists stations and date ranges with data. It does not return the sensor time series on this route.",
        "source_url": "https://services.niot.res.in/BuoyNetwork/",
    }


@router.get("/argo-grid")
def argo_grid(
    variable: str = Query(default="TEMP", pattern="^(TEMP|SAL)$"),
    depth_m: float = Query(default=5, ge=0, le=2000),
    south: float = Query(default=-5, ge=-29.5, le=29.5),
    north: float = Query(default=25, ge=-29.5, le=29.5),
    west: float = Query(default=60, ge=30.5, le=119.5),
    east: float = Query(default=100, ge=30.5, le=119.5),
):
    """Fetch a real, bounded INCOIS 10-day Argo analysis grid subset.

    This is a gridded analysis, not raw sensor data or a real-time forecast.
    A successful latest-source request and a recent source timestamp are both
    required before freshness can be reported as LIVE.
    """
    if south >= north or west >= east:
        return {"available": False, "status": "INVALID_BOUNDS", "error": "south must be below north and west below east."}
    cache_key = (variable, round(depth_m, 2), round(south, 2), round(north, 2), round(west, 2), round(east, 2))
    cached_grid = _grid_cache.get(cache_key)
    if cached_grid and time.monotonic() - cached_grid["cached_at"] < _CACHE_SECONDS:
        return {**cached_grid["payload"], "cached": True}
    catalog = _load_catalog()
    if catalog["status"] != "LIVE":
        return {"available": False, "status": "TEMPORARILY_UNAVAILABLE", "error": catalog["error"], "source": "INCOIS"}
    dataset = next((d for d in catalog["datasets"] if d["id"] == "incois_argo_10d_VAM"), None)
    if not dataset or not dataset.get("temporal_end"):
        return {"available": False, "status": "PUBLIC_ENDPOINT_NOT_AVAILABLE", "error": "INCOIS Argo analysis metadata is unavailable."}
    # Snap the requested depth to the nearest reported model level.
    axis_url = settings.INCOIS_ERDDAP_BASE.rstrip("/") + "/griddap/incois_argo_10d_VAM.csv?ZAX"
    try:
        axis = httpx.get(axis_url, timeout=httpx.Timeout(15, connect=8), follow_redirects=True,
                         verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        axis.raise_for_status()
        axis_rows = list(csv.reader(io.StringIO(axis.text)))
        levels = [float(row[0]) for row in axis_rows[2:] if row and row[0] not in ("", "NaN")]
        if not levels:
            raise ValueError("No depth levels returned")
        level = min(levels, key=lambda value: abs(value - depth_m))
        source_time = dataset["temporal_end"]
        expression = f"{variable}[({source_time})][({level:g})][({south:g}):1:({north:g})][({west:g}):1:({east:g})]"
        data_url = settings.INCOIS_ERDDAP_BASE.rstrip("/") + "/griddap/incois_argo_10d_VAM.csv"
        response = httpx.get(data_url + "?" + quote(expression, safe="():,"),
                             timeout=httpx.Timeout(30, connect=8), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        if response.status_code == 400 and "No data" in response.text:
            return {"available": False, "status": "NO_DATA_FOR_REQUEST", "source": "INCOIS", "dataset": dataset["name"], "time": source_time, "depth_m": level, "error": response.text[:250]}
        response.raise_for_status()
        reader = csv.reader(io.StringIO(response.text))
        parsed = list(reader)
        cells = []
        for row in parsed[2:]:
            if len(row) < 5:
                continue
            try:
                value = float(row[4])
                latitude, longitude = float(row[2]), float(row[3])
                valid_range = -3 <= value <= 45 if variable == "TEMP" else 0 <= value <= 45
                if value > -9000 and valid_range and south <= latitude <= north and west <= longitude <= east:
                    cells.append({"latitude": latitude, "longitude": longitude, "value": value})
            except ValueError:
                continue
        timestamp = datetime.fromisoformat(source_time.replace("Z", "+00:00"))
        age_days = max(0, (datetime.now(timezone.utc) - timestamp).total_seconds() / 86400)
        freshness = "LIVE" if age_days <= 14 else "STALE"
        payload = {
            "available": bool(cells), "status": freshness if cells else "NO_DATA_FOR_REQUEST",
            "freshness": freshness, "age_days": round(age_days, 1), "source": "INCOIS",
            "dataset_id": dataset["id"], "dataset": dataset["name"],
            "product_type": "10-day gridded Argo variational analysis (not raw in-situ readings)",
            "variable": variable, "unit": "degC" if variable == "TEMP" else "PSU",
            "time": source_time, "depth_m": level,
            "coverage": {"south": south, "north": north, "west": west, "east": east},
            "resolution_deg": 1.0, "cells": cells, "cell_count": len(cells),
            "request_succeeded_at": datetime.now(timezone.utc).isoformat(),
            "source_url": settings.INCOIS_ERDDAP_BASE.rstrip("/") + "/griddap/incois_argo_10d_VAM.html",
            "license": "Use and redistribution are free; ERDDAP disclaims warranty and legal use. See source metadata.",
            "cached": False,
        }
        _grid_cache[cache_key] = {"cached_at": time.monotonic(), "payload": payload}
        return payload
    except (httpx.HTTPError, ValueError, IndexError) as exc:
        return {"available": False, "status": "TEMPORARILY_UNAVAILABLE", "source": "INCOIS", "dataset": dataset["name"], "error": str(exc)[:300]}


@router.get("/normalized/argo-grid")
def normalized_argo_grid(
    variable: str = Query(default="TEMP", pattern="^(TEMP|SAL)$"),
    depth_m: float = Query(default=5, ge=0, le=2000),
    south: float = Query(default=-5, ge=-29.5, le=29.5),
    north: float = Query(default=25, ge=-29.5, le=29.5),
    west: float = Query(default=60, ge=30.5, le=119.5),
    east: float = Query(default=100, ge=30.5, le=119.5),
):
    """Serve INCOIS cells using the platform-wide provenance record shape."""
    payload = argo_grid(variable, depth_m, south, north, west, east)
    if south >= north or west >= east:
        return payload
    normalized = normalize_argo_grid(payload)
    return {
        **{key: value for key, value in payload.items() if key != "cells"},
        "record_count": len(normalized),
        "records": normalized,
        "normalization_schema": "UnifiedOceanRecord/v1",
    }


@router.get("/biodiversity")
def biodiversity(
    south: float = Query(default=-30, ge=-90, le=90),
    north: float = Query(default=30, ge=-90, le=90),
    west: float = Query(default=30, ge=-180, le=180),
    east: float = Query(default=120, ge=-180, le=180),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """Fetch published marine species occurrences from CMLRE's IndOBIS node.

    Occurrence records can be historical. They are never represented as live
    animal tracks or current abundance measurements.
    """
    if south >= north or west >= east:
        return {"available": False, "status": "INVALID_BOUNDS", "error": "south must be below north and west below east."}
    checked = datetime.now(timezone.utc).isoformat()
    try:
        response = httpx.get(f"{INDOBIS_API}/occurrence", params={
            "nodeid": INDOBIS_NODE_ID, "size": min(limit * 3, 1000), "start": 0,
            "marine": "true",
        }, timeout=httpx.Timeout(25, connect=8), follow_redirects=True,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        response.raise_for_status()
        body = response.json()
        records = []
        for row in body.get("results", []):
            try:
                latitude, longitude = float(row["decimalLatitude"]), float(row["decimalLongitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (south <= latitude <= north and west <= longitude <= east):
                continue
            records.append({
                "id": row.get("occurrenceID") or row.get("id"),
                "scientific_name": row.get("scientificName"),
                "event_date": row.get("eventDate"), "latitude": latitude,
                "longitude": longitude, "depth_m": row.get("minimumDepthInMeters"),
                "basis_of_record": row.get("basisOfRecord"),
                "institution": row.get("institutionCode"),
                "dataset_id": row.get("dataset_id"),
                "source_url": f"https://obis.org/occurrence/{row.get('id')}" if row.get("id") else "https://indobis.in/",
            })
            if len(records) >= limit:
                break
        return {
            "available": True, "status": "LIVE", "checked_at": checked,
            "provider": "CMLRE / IndOBIS via OBIS API v3", "node_id": INDOBIS_NODE_ID,
            "total_node_records": body.get("total"), "returned": len(records),
            "spatial_filter_applied": {"south": south, "north": north, "west": west, "east": east},
            "temporal_coverage": "Occurrence record dates vary; inspect each event_date.",
            "data_type": "Historical and recent species occurrence records; not a live abundance stream.",
            "checked_at": checked, "source_url": "https://indobis.in/",
            "records": records,
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"available": False, "status": "TEMPORARILY_UNAVAILABLE", "checked_at": checked,
                "provider": "CMLRE / IndOBIS", "error": str(exc)[:300], "source_url": "https://indobis.in/"}


@router.get("/normalized/biodiversity")
def normalized_biodiversity(
    south: float = Query(default=-30, ge=-90, le=90),
    north: float = Query(default=30, ge=-90, le=90),
    west: float = Query(default=30, ge=-180, le=180),
    east: float = Query(default=120, ge=-180, le=180),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """Serve IndOBIS occurrences in the shared ocean record shape."""
    payload = biodiversity(south, north, west, east, limit)
    if south >= north or west >= east:
        return payload
    normalized = normalize_indobis_occurrences(payload)
    return {
        **{key: value for key, value in payload.items() if key != "records"},
        "record_count": len(normalized),
        "records": normalized,
        "normalization_schema": "UnifiedOceanRecord/v1",
    }


def _latest_thredds_file(product: str) -> dict:
    """Resolve the newest public operational INCOIS forecast file from THREDDS."""
    cached = _thredds_cache.get(product)
    if cached and time.monotonic() - cached["cached_at"] < _CACHE_SECONDS:
        return cached["value"]
    if product == "wave":
        directory, prefix = "osf/ww3", "rsmc_combined_ww3_"
    elif product == "ocean":
        directory, prefix = "osf/currents2", "RSMC_hycom_"
    else:
        raise ValueError("Unknown operational product")
    catalog_url = f"{_THREDDS_BASE}/catalog/{directory}/catalog.xml"
    response = httpx.get(catalog_url, timeout=httpx.Timeout(20, connect=8), follow_redirects=True,
                         verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    response.raise_for_status()
    root = ET.fromstring(response.content)
    files = sorted({
        node.attrib.get("name", "") for node in root.iter()
        if node.tag.endswith("dataset")
        and node.attrib.get("name", "").startswith(prefix)
        and node.attrib.get("name", "").endswith(".nc")
    })
    if not files:
        raise ValueError(f"No public {product} forecast files are listed in the THREDDS catalog.")
    filename = files[-1]
    run_match = re.search(r"(20\d{6})", filename)
    run_time = datetime.strptime(run_match.group(1), "%Y%m%d").replace(tzinfo=timezone.utc) if run_match else None
    value = {
        "product": product, "directory": directory, "filename": filename,
        "run_time": run_time.isoformat() if run_time else None,
        "catalog_url": catalog_url,
        "wms_url": f"{_THREDDS_BASE}/wms/{directory}/{filename}",
        "ncss_url": f"{_THREDDS_BASE}/ncss/grid/{directory}/{filename}",
        "source_url": f"https://incois.gov.in/oceanservices/LSF/index.html",
    }
    _thredds_cache[product] = {"cached_at": time.monotonic(), "value": value}
    return value


def _csv_number(row: dict, variable: str) -> float | None:
    raw = next((value for key, value in row.items() if key == variable or key.startswith(variable + "[")), None)
    try:
        number = float(raw)
        return number if math.isfinite(number) and -9000 < number < 1.0e10 else None
    except (TypeError, ValueError):
        return None


@router.get("/forecast/hydrodynamics")
def incois_hydrodynamic_forecast(
    product: str = Query(default="currents", pattern="^(currents|temperature|salinity|sea-level)$"),
    latitude: float = Query(default=10, ge=-60, le=31),
    longitude: float = Query(default=80, ge=20, le=120),
    hours: int = Query(default=168, ge=6, le=168),
):
    """Fetch current-run INCOIS HYCOM point forecasts via public THREDDS NCSS."""
    now = datetime.now(timezone.utc)
    cache_key = (product, round(latitude, 3), round(longitude, 3), hours)
    cached = _forecast_cache.get(cache_key)
    if cached and time.monotonic() - cached["cached_at"] < _CACHE_SECONDS:
        return {**cached["payload"], "cached": True}
    try:
        source = _latest_thredds_file("ocean")
        variables = {
            "currents": ["UVEL", "VVEL"], "temperature": ["TEMP"],
            "salinity": ["SALN"], "sea-level": ["SSH"],
        }[product]
        # Operational HYCOM analyses/forecasts use 6-hourly valid times.
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=hours)
        params: list[tuple[str, str]] = [("var", var) for var in variables]
        params.extend([
            ("latitude", str(latitude)), ("longitude", str(longitude)),
            ("time_start", start.isoformat().replace("+00:00", "Z")),
            ("time_end", end.isoformat().replace("+00:00", "Z")),
            ("vertCoord", "0"), ("accept", "csv"),
        ])
        response = httpx.get(source["ncss_url"], params=params,
                             timeout=httpx.Timeout(35, connect=8), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        records = []
        for row in reader:
            observed_at = row.get("time")
            lat = _csv_number(row, "latitude")
            lon = _csv_number(row, "longitude")
            attrs: dict[str, str | None] = {"model_run": source["run_time"]}
            if product == "currents":
                u, v = _csv_number(row, "UVEL"), _csv_number(row, "VVEL")
                if u is None or v is None or abs(u) > 10 or abs(v) > 10:
                    continue
                value = math.hypot(u, v)
                attrs.update({"eastward_velocity_m_s": str(u), "northward_velocity_m_s": str(v), "direction_towards_deg": str(round((math.degrees(math.atan2(u, v)) + 360) % 360, 2))})
                variable, units, category = "sea_water_velocity", "m/s", "ocean_current_forecast"
            else:
                source_variable = variables[0]
                value = _csv_number(row, source_variable)
                if value is None:
                    continue
                valid = {
                    "temperature": -3 <= value <= 45,
                    "salinity": 0 <= value <= 50,
                    "sea-level": -15 <= value <= 15,
                }[product]
                if not valid:
                    continue
                variable = {"temperature": "sea_water_temperature", "salinity": "sea_water_salinity", "sea-level": "sea_surface_height"}[product]
                units = {"temperature": "degC", "salinity": "PSU", "sea-level": "m"}[product]
                category = {"temperature": "ocean_temperature_forecast", "salinity": "ocean_salinity_forecast", "sea-level": "sea_level_forecast"}[product]
            identity = f"INCOIS|{source['filename']}|{product}|{observed_at}|{latitude}|{longitude}"
            record = UnifiedOceanRecord(
                record_id=__import__("hashlib").sha256(identity.encode()).hexdigest(),
                source_id="INCOIS", institution="Indian National Centre for Ocean Information Services",
                dataset_id=source["filename"], dataset_name="INCOIS RSMC HYCOM forecast",
                category=category, variable=variable, value=round(value, 5), units=units,
                observed_at=observed_at, retrieved_at=now.isoformat(), latitude=lat,
                longitude=lon, depth_m=0, data_status="FORECAST",
                quality_status="RANGE_SCREENED_FORECAST_FIELD",
                quality_flags=["MODEL_FORECAST_NOT_OBSERVATION", "BASIC_PHYSICAL_RANGE_SCREENED"], attributes=attrs,
                source_url=source["source_url"], attribution="INCOIS Ocean State Forecast / RSMC",
                license="See INCOIS Ocean State Forecast service terms",
            )
            records.append(record.model_dump())
        run_time = datetime.fromisoformat(source["run_time"]) if source["run_time"] else None
        age_hours = (now - run_time).total_seconds() / 3600 if run_time else None
        freshness = "LIVE" if age_hours is not None and age_hours <= 30 else "STALE"
        payload = {
            "available": bool(records), "status": freshness if records else "NO_DATA_FOR_REQUEST",
            "freshness": freshness if records else "NO_DATA_FOR_REQUEST",
            "age_hours": round(age_hours, 1) if age_hours is not None else None,
            "product": product, "provider": "INCOIS RSMC HYCOM",
            "dataset": source["filename"], "model_run": source["run_time"],
            "requested_position": {"latitude": latitude, "longitude": longitude},
            "forecast_window_hours": hours, "record_count": len(records),
            "records": records, "checked_at": now.isoformat(),
            "source_url": source["source_url"], "catalog_url": source["catalog_url"],
            "cached": False, "error": None,
        }
        _forecast_cache[cache_key] = {"cached_at": time.monotonic(), "payload": payload}
        return payload
    except (httpx.HTTPError, ET.ParseError, ValueError, KeyError) as exc:
        return {"available": False, "status": "TEMPORARILY_UNAVAILABLE", "product": product,
                "provider": "INCOIS RSMC HYCOM", "checked_at": now.isoformat(),
                "error": str(exc)[:300], "source_url": "https://incois.gov.in/oceanservices/LSF/index.html"}


@router.get("/forecast/waves")
def incois_wave_forecast(
    latitude: float = Query(default=10, ge=-60, le=30),
    longitude: float = Query(default=80, ge=30, le=120),
    variable: str = Query(default="HS", pattern="^(HS|PWP|T02|DIR|PWD|SPR|STP|WIND)$"),
    valid_at: str | None = Query(default=None, max_length=40),
):
    """Sample an official INCOIS RSMC WW3 wave/wind forecast through THREDDS WMS."""
    now = datetime.now(timezone.utc)
    cache_key = ("wave", round(latitude, 3), round(longitude, 3), variable, valid_at or "latest")
    cached = _forecast_cache.get(cache_key)
    if cached and time.monotonic() - cached["cached_at"] < _CACHE_SECONDS:
        return {**cached["payload"], "cached": True}
    try:
        source = _latest_thredds_file("wave")
        capabilities = httpx.get(source["wms_url"], params={"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"},
                                 timeout=httpx.Timeout(25, connect=8), follow_redirects=True,
                                 verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        capabilities.raise_for_status()
        root = ET.fromstring(capabilities.content)
        layer_name = "UWND:VWND-mag" if variable == "WIND" else variable
        time_range = None
        for layer in root.iter():
            if not layer.tag.endswith("Layer"):
                continue
            name_node = next((c for c in layer if c.tag.endswith("Name")), None)
            if name_node is None or (name_node.text or "").strip() != layer_name:
                continue
            dim = next((c for c in layer if c.tag.endswith("Dimension") and c.attrib.get("name") == "time"), None)
            if dim is not None:
                time_range = (dim.text or "").strip()
                break
        if not time_range:
            raise ValueError(f"Forecast layer {layer_name} has no advertised time dimension.")
        parts = time_range.split("/")
        start_time = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(parts[1].replace("Z", "+00:00"))
        interval_match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", parts[2]) if len(parts) > 2 else None
        interval = timedelta(hours=int(interval_match.group(1) or 0), minutes=int(interval_match.group(2) or 0)) if interval_match else timedelta(hours=3)
        valid_times = []
        t = start_time
        while t <= end_time and len(valid_times) < 100:
            valid_times.append(t)
            t += interval
        if valid_at:
            requested_time = datetime.fromisoformat(valid_at.replace("Z", "+00:00"))
            selected_time = min(valid_times, key=lambda candidate: abs((candidate - requested_time).total_seconds()))
        else:
            future_times = [candidate for candidate in valid_times if candidate >= now]
            selected_time = future_times[0] if future_times else valid_times[-1]
        bbox = f"{longitude - 0.05},{latitude - 0.05},{longitude + 0.05},{latitude + 0.05}"
        query = {
            "service": "WMS", "version": "1.3.0", "request": "GetFeatureInfo",
            "layers": layer_name, "query_layers": layer_name, "crs": "CRS:84",
            "bbox": bbox, "width": "10", "height": "10", "i": "5", "j": "5",
            "time": selected_time.isoformat().replace("+00:00", "Z"), "info_format": "text/plain",
        }
        response = httpx.get(source["wms_url"], params=query,
                             timeout=httpx.Timeout(25, connect=8), follow_redirects=True,
                             verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        response.raise_for_status()
        body = response.text
        value_match = re.search(r"Value:\s*([-+0-9.eE]+)", body)
        value = float(value_match.group(1)) if value_match else None
        if value is not None and (not math.isfinite(value) or value <= -9000):
            value = None
        if value is not None:
            valid_range = {
                "HS": 0 <= value <= 50, "PWP": 0 < value <= 100,
                "T02": 0 < value <= 100, "DIR": 0 <= value <= 360,
                "PWD": 0 <= value <= 360, "SPR": 0 <= value <= 360,
                "STP": 0 <= value <= 2, "WIND": 0 <= value <= 100,
            }[variable]
            if not valid_range:
                value = None
        units = {"HS": "m", "PWP": "s", "T02": "s", "DIR": "deg", "PWD": "deg", "SPR": "deg", "STP": "1", "WIND": "m/s"}[variable]
        names = {"HS": "significant_wave_height", "PWP": "peak_wave_period", "T02": "mean_wave_period", "DIR": "mean_wave_direction", "PWD": "principal_wave_direction", "SPR": "directional_spread", "STP": "wave_steepness", "WIND": "wind_speed"}
        forecast_age = (now - datetime.fromisoformat(source["run_time"])).total_seconds() / 3600 if source["run_time"] else None
        freshness = "LIVE" if forecast_age is not None and forecast_age <= 30 else "STALE"
        records = []
        if value is not None:
            identity = f"INCOIS|{source['filename']}|{variable}|{selected_time.isoformat()}|{latitude}|{longitude}"
            record = UnifiedOceanRecord(
                record_id=__import__("hashlib").sha256(identity.encode()).hexdigest(),
                source_id="INCOIS", institution="Indian National Centre for Ocean Information Services",
                dataset_id=source["filename"], dataset_name="INCOIS RSMC WaveWatch III forecast",
                category="wave_forecast" if variable != "WIND" else "wind_forecast",
                variable=names[variable], value=round(value, 5), units=units,
                observed_at=selected_time.isoformat(), retrieved_at=now.isoformat(),
                latitude=latitude, longitude=longitude, data_status="FORECAST",
                quality_status="RANGE_SCREENED_FORECAST_FIELD", quality_flags=["MODEL_FORECAST_NOT_OBSERVATION", "BASIC_PHYSICAL_RANGE_SCREENED"],
                attributes={"model_run": source["run_time"], "requested_variable": variable},
                source_url=source["source_url"], attribution="INCOIS Ocean State Forecast / RSMC",
                license="See INCOIS Ocean State Forecast service terms",
            )
            records.append(record.model_dump())
        payload = {
            "available": bool(records), "status": freshness if records else "NO_DATA_FOR_REQUEST",
            "freshness": freshness if records else "NO_DATA_FOR_REQUEST",
            "age_hours": round(forecast_age, 1) if forecast_age is not None else None,
            "provider": "INCOIS RSMC WaveWatch III", "dataset": source["filename"],
            "variable": variable, "valid_at": selected_time.isoformat(),
            "forecast_times": [stamp.isoformat() for stamp in valid_times],
            "requested_position": {"latitude": latitude, "longitude": longitude},
            "record_count": len(records), "records": records,
            "checked_at": now.isoformat(), "source_url": source["source_url"],
            "catalog_url": source["catalog_url"], "cached": False,
            "error": None if records else "The source returned no valid value at this position and time.",
        }
        _forecast_cache[cache_key] = {"cached_at": time.monotonic(), "payload": payload}
        return payload
    except (httpx.HTTPError, ET.ParseError, ValueError, IndexError) as exc:
        return {"available": False, "status": "TEMPORARILY_UNAVAILABLE", "provider": "INCOIS RSMC WaveWatch III",
                "checked_at": now.isoformat(), "error": str(exc)[:300],
                "source_url": "https://incois.gov.in/oceanservices/LSF/index.html"}
