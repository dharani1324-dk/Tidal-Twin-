"""
TidalTwin - Real ingested-grid data provider
===============================================
One shared source of truth for reading the REAL gridded products already
ingested into `netcdf_readings` (features #1/#2 and the ERSST/Chl builds):
  - sea-surface temperature :  NOAA ERSST v5     -> variable_name 'sst'
  - chlorophyll-a           :  NOAA VIIRS/Himawari -> variable_name 'chlor_a'

Consumed by the /ersst and /chlor routers, the copilot, the multimodal
claim-verifier and the anomaly detector's real cross-check.

Honest by construction: every lookup returns `found: False` (with a reason)
when the latest grid has no cell within search range — callers must surface
that, never a fabricated value.
"""

import math
from datetime import datetime, timezone

from geoalchemy2.shape import to_shape
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.netcdf import NetcdfReadings

# Provenance & honest messaging per real product.
SOURCES = {
    "sst": {
        "label": "NOAA ERSST v5 (2-degree monthly gridded SST analysis, in-situ observations)",
        "short": "real NOAA ERSST v5",
        "variable": "Sea surface temperature",
        "units": "°C",
        "resolution_deg": 2.0,
        "default_max_deg": 3.5,
        "reason_no_data": "No ERSST readings ingested yet.",
        "reason_no_cell": "No real ERSST cell within {deg:g}° of this location.",
    },
    "chlor_a": {
        "label": "NOAA CoastWatch VIIRS-Himawari blended ocean-colour (5 km, monthly mean)",
        "short": "real NOAA VIIRS·Himawari satellite",
        "variable": "Chlorophyll (chlor_a)",
        "units": "mg/m³",
        "resolution_deg": 0.05,
        "default_max_deg": 0.2,
        "reason_no_data": "No satellite Chl readings ingested yet.",
        "reason_no_cell": "No satellite Chl cell within {deg:g}° of this location.",
    },
}


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _lon180(lon: float) -> float:
    """Grids are stored 0..360 where applicable; map to conventional -180..180."""
    return lon - 360.0 if lon > 180 else lon


def _deg_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = lat2 - lat1
    dlon = (_lon180(lon2) - _lon180(lon1)) * math.cos(math.radians((lat1 + lat2) / 2.0))
    return math.sqrt(dlat * dlat + dlon * dlon)


def _info(variable: str) -> dict:
    if variable not in SOURCES:
        raise KeyError(f"Unknown real variable '{variable}'. Known: {sorted(SOURCES)}")
    return SOURCES[variable]


def location_center(loc) -> tuple[float, float] | None:
    """(lat, lon) centre of a monitored ocean location, or None."""
    geom = getattr(loc, "geom", None)
    if geom is None:
        return None
    try:
        shape = to_shape(geom)
        return shape.centroid.y, shape.centroid.x
    except Exception:
        return None


def latest_for(db: Session, variable: str) -> tuple[datetime | None, str | None, list[str]]:
    """(latest UTC time, 'YYYY-MM' label, ordered month labels) for a variable."""
    times = [t[0] for t in db.query(func.distinct(NetcdfReadings.time))
             .filter(NetcdfReadings.variable_name == variable).all()]
    if not times:
        return None, None, []
    utc = sorted(_as_utc(t) for t in times)
    labels = [t.strftime("%Y-%m") for t in utc]
    return utc[-1], labels[-1], labels


def latest_grid(db: Session, variable: str) -> dict:
    """Latest month of a real grid: {available, time, months, resolution_deg,
    source, rows, stats, samples: [(lat, lon, value), ...]}. Nothing simulated."""
    info = _info(variable)
    latest_t, latest_label, months = latest_for(db, variable)
    if latest_t is None:
        return {"available": False, "error": info["reason_no_data"]}
    samples = (
        db.query(NetcdfReadings.latitude, NetcdfReadings.longitude, NetcdfReadings.value)
        .filter(
            NetcdfReadings.variable_name == variable,
            NetcdfReadings.time == latest_t,
            NetcdfReadings.value.isnot(None),
        )
        .all()
    )
    values = [val for _, _, val in samples if val is not None]
    if values:
        stats = {"min": round(min(values), 4), "max": round(max(values), 4), "count": len(values)}
    else:
        stats = {"min": None, "max": None, "count": 0}
    return {
        "available": True,
        "time": latest_label,
        "months": months,
        "resolution_deg": info["resolution_deg"],
        "source": info["label"],
        "rows": len(samples),
        "stats": stats,
        "samples": [(la, _lon180(lo), val) for la, lo, val in samples],
    }


def near(db: Session, variable: str, latitude: float, longitude: float,
         max_dist_deg: float | None = None) -> dict:
    """Nearest real grid cell to a point. Honest `found: False` (with reason)
    when the closest cell is farther than the product's max range."""
    info = _info(variable)
    limit = info["default_max_deg"] if max_dist_deg is None else max_dist_deg
    latest_t, latest_label, _ = latest_for(db, variable)
    if latest_t is None:
        return {"found": False, "month": None, "reason": info["reason_no_data"]}
    rows = (
        db.query(NetcdfReadings)
        .filter(
            NetcdfReadings.variable_name == variable,
            NetcdfReadings.time == latest_t,
            NetcdfReadings.value.isnot(None),
        )
        .all()
    )
    if not rows:
        return {"found": False, "month": latest_label,
                "reason": f"Latest month has no {info['short']} cells."}
    best = min(rows, key=lambda r: _deg_distance(latitude, longitude, r.latitude, r.longitude))
    dist = _deg_distance(latitude, longitude, best.latitude, best.longitude)
    if dist > limit:
        return {"found": False, "month": latest_label,
                "reason": info["reason_no_cell"].format(deg=limit)}
    return {
        "found": True,
        "month": latest_label,
        "latitude": best.latitude,
        "longitude": _lon180(best.longitude),
        "value": best.value,
        "distance_deg": round(dist, 2),
        "units": info["units"],
        "source": info["label"],
        "short": info["short"],
    }


def default_max_dist(variable: str) -> float:
    """Expose the product's default max search range for router Query defaults."""
    return _info(variable)["default_max_deg"]