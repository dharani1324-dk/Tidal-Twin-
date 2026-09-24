"""
TidalTwin - Ocean Data Service
==================================
This service fetches REAL ocean data from the Open-Meteo Marine API
(no API key needed) and stores it in our database.

Why Open-Meteo Marine?
- Free and reliable, no registration
- Worldwide coverage including Indian Ocean
- Gives sea surface temperature, wave height, wave direction, salinity

The data comes from MeteoFrance / Copernicus ocean models behind the scenes.
"""

import httpx
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.physics.ocean_profiles import derive_surface

# The free Open-Meteo Marine API endpoint
MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"

# The ocean variables we want to fetch
# NOTE: Open-Meteo Marine supports temp & waves (not salinity).
# Salinity/currents will come from another source in a later module.
VARIABLES = "sea_surface_temperature,wave_height,wave_direction"


def fetch_marine_data(lat: float, lon: float, forecast_days: int = 2) -> dict | None:
    """
    Ask Open-Meteo for ocean data at a given latitude/longitude.
    Returns a JSON dict (or None if the call fails).
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": VARIABLES,
        "forecast_days": forecast_days,
        "timezone": "GMT",
    }
    try:
        resp = httpx.get(MARINE_API_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [!] Marine API error for ({lat},{lon}): {e}")
        return None


def store_observations(db: Session, location: OceanLocation, data: dict) -> int:
    """
    Take the JSON from Open-Meteo and write each hourly reading
    into the ocean_observations table for this location.

    Returns the number of new observations stored.
    """
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("sea_surface_temperature", [])
    waves = hourly.get("wave_height", [])
    wave_dir = hourly.get("wave_direction", [])
    salinity = hourly.get("salinity", [])

    count = 0
    for i, t in enumerate(times):
        # Convert the ISO timestamp string to a datetime object
        try:
            ts = datetime.fromisoformat(t)
        except ValueError:
            continue

        # Skip if we already have this observation (avoid duplicates)
        exists = (
            db.query(OceanObservation)
            .filter(
                OceanObservation.location_id == location.id,
                OceanObservation.timestamp == ts,
            )
            .first()
        )
        if exists:
            continue

        obs = OceanObservation(
            location_id=location.id,
            timestamp=ts,
            sea_surface_temperature=temps[i] if i < len(temps) else None,
            wave_height=waves[i] if i < len(waves) else None,
            wave_direction=wave_dir[i] if i < len(wave_dir) else None,
            salinity=salinity[i] if i < len(salinity) else None,
            depth_m=0.0,
            source="Open-Meteo Marine",
            data_type="observation",
        )

        # Enrich with derived bio-physical variables from the physics engine
        surf = derive_surface(
            location,
            obs.sea_surface_temperature,
            obs.salinity,
            obs.wave_height,
            getattr(obs, "current_speed", None),
        )
        obs.dissolved_oxygen = surf["dissolved_oxygen"]
        obs.chlorophyll = surf["chlorophyll"]
        obs.ph = surf["ph"]
        obs.pressure = surf["pressure"]
        obs.density = surf["density"]
        obs.nutrients = surf["nutrients"]

        db.add(obs)
        count += 1

    db.commit()
    return count


def refresh_all_locations(db: Session, forecast_days: int = 2) -> dict:
    """
    Fetch fresh ocean data for EVERY location in the database.
    This is the "sweep" we can run to keep our ocean twin up to date.
    """
    locations = db.query(OceanLocation).all()
    summary = {"locations_updated": 0, "observations_added": 0, "errors": 0}

    for loc in locations:
        # Recreate a point from stored coordinates would need geometry;
        # instead we store lat/lon on location for simplicity here.
        # For now, use a small offset to get the sea point.
        lat, lon = get_location_center(loc)
        if lat is None:
            summary["errors"] += 1
            continue
        data = fetch_marine_data(lat, lon, forecast_days)
        if data is None:
            summary["errors"] += 1
            continue
        added = store_observations(db, loc, data)
        summary["locations_updated"] += 1
        summary["observations_added"] += added

    return summary


def get_location_center(loc: OceanLocation) -> tuple[float | None, float | None]:
    """
    Extract the center latitude/longitude from the location's
    PostGIS geometry so we can query the API for that spot.
    """
    from geoalchemy2.shape import to_shape

    if loc.geom is None:
        return None, None
    try:
        geom = to_shape(loc.geom)
        lon, lat = geom.centroid.x, geom.centroid.y
        return lat, lon
    except Exception:
        return None, None
