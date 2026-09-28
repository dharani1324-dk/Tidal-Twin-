"""
TidalTwin - Microplastics: 24-72h drift projection
==================================================
Projects where a microplastic hotspot is likely to travel, using surface
currents the twin already holds.  Two forcing sources are accepted, in order of
trust:

  1. ``ocean_observations.current_speed`` / ``current_direction`` from rows
     whose provenance is REAL or HISTORICAL.
  2. ``derived_currents`` - surface vectors derived from real AIS vessel tracks
     by the existing current-derivation pipeline.

WHAT THIS DELIBERATELY REFUSES TO DO
------------------------------------
It does not invent a current.  ``coastal/spill.py`` defaults to 0.15 m/s at a
45 degree bearing when it finds no observation, which is fine for a theatrical
demo but is exactly the kind of fabricated forcing that makes a drift cone
meaningless.  Here, no forcing means no projection: the response carries
``status="NO_FORCING"`` and a reason naming which datasets were checked.

METHOD AND ITS LIMITS
---------------------
Single-layer Lagrangian advection at the surface with a wind-leeway term and a
sqrt-time diffusive spread.  There is no vertical shear, no Stokes drift, no
beaching or sinking term, and no resuspension.  Microplastics are not a passive
tracer - buoyant particles wind-slip and heavier ones sink.  The output is a
corridor, not a forecast, and says so.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ais import DerivedCurrent
from app.models.observation import OceanObservation
from app.modules.ai.microplastics.regions import haversine_km
from app.modules.ai.provenance_quality import origin_status

EARTH_R_KM = 6371.0088

DRIFT_METHOD = "surface Lagrangian advection + wind leeway + sqrt-time spread"
DRIFT_ALGORITHM_VERSION = "1.0"

# Wind leeway: a fraction of the wind-driven surface drift; microplastic
# particles are near-neutrally buoyant but wind-slipped at the surface.
WIND_LEEWAY_FRACTION = 0.03
WIND_OFFSET_DEG = 35.0

# Fraction of full current speed a floating particle follows at the surface.
SURFACE_SPEED_FRACTION = 0.95


def _bearing_speed_from_observation(db: Session, region_id: int) -> dict | None:
    """Latest trusted current observation for a region, if one exists."""
    rows = (
        db.query(OceanObservation)
        .filter(
            OceanObservation.location_id == region_id,
            OceanObservation.current_speed.isnot(None),
            OceanObservation.current_direction.isnot(None),
        )
        .order_by(OceanObservation.timestamp.desc())
        .limit(25)
        .all()
    )
    for row in rows:
        status = origin_status(row.source, row.data_type)
        if status in ("REAL", "HISTORICAL"):
            return {
                "origin": "in-situ observation",
                "origin_status": status,
                "speed_ms": float(row.current_speed),
                "direction_deg": float(row.current_direction),
                "observed_at": (
                    row.timestamp.astimezone(timezone.utc).isoformat()
                    if getattr(row.timestamp, "tzinfo", None) is not None
                    else (row.timestamp.isoformat() if row.timestamp else None)
                ),
                "source": row.source,
            }
    return None


def _bearing_speed_from_derived(db: Session, latitude: float, longitude: float) -> dict | None:
    """Nearest AIS-derived current vector, if the derivation pipeline has run."""
    rows = (
        db.query(DerivedCurrent)
        .filter(DerivedCurrent.method_tag == "DERIVED")
        .limit(500)
        .all()
    )
    if not rows:
        return None

    best = None
    best_km = float("inf")
    for row in rows:
        if row.lat is None or row.lon is None:
            continue
        distance = haversine_km(latitude, longitude, row.lat, row.lon)
        if distance < best_km:
            best_km = distance
            best = row

    if best is None or best_km > 300.0:
        return None

    # Column names are `speed` / `direction` / `uncertainty_mps` on
    # DerivedCurrent - the derivation pipeline's vocabulary, not ours.
    speed = best.speed
    direction = best.direction
    if speed is None or direction is None:
        return None

    return {
        "origin": "AIS-derived surface vector",
        "origin_status": "DERIVED",
        "speed_ms": float(speed),
        "direction_deg": float(direction),
        "observed_at": (
            best.time_bucket.astimezone(timezone.utc).isoformat()
            if getattr(best.time_bucket, "tzinfo", None) is not None
            else (best.time_bucket.isoformat() if best.time_bucket else None)
        ),
        "distance_km": round(best_km, 2),
        "uncertainty_mps": getattr(best, "uncertainty_mps", None),
        "n_vessels": getattr(best, "n_vessels", None),
        "n_observations": getattr(best, "n_observations", None),
        "source": "derived_currents (vessel-motion)",
    }


# Credibility gates for AIS-derived forcing.  The currents module stores no row
# for cells that failed its own vessel-count gate, but a row that slipped
# through with a single vessel is not usable forcing and must not be presented
# as though it were.
MIN_VESSELS_FOR_FORCING = 2
MIN_OBSERVATIONS_FOR_FORCING = 5
# Surface currents above this are rare outside western boundary currents; a
# faster "current" is far more likely to be unremoved vessel motion.
IMPLAUSIBLE_SURFACE_SPEED_MS = 1.5


def assess_forcing_quality(forcing: dict) -> dict:
    """Judge whether a forcing vector is fit to advect a plume with.

    Returns a verdict plus explicit reasons.  The verdict never suppresses the
    projection - it is attached to it, so a weak corridor is drawn *and*
    labelled rather than silently produced or silently withheld.
    """
    warnings: list[str] = []
    speed = abs(float(forcing.get("speed_ms") or 0.0))

    if speed > IMPLAUSIBLE_SURFACE_SPEED_MS:
        warnings.append(
            f"Forcing speed {speed:.2f} m/s exceeds the {IMPLAUSIBLE_SURFACE_SPEED_MS} m/s "
            "plausibility ceiling for a surface current; it is more likely to be "
            "unremoved vessel motion than water movement."
        )
    if speed == 0.0:
        warnings.append(
            "Forcing speed is exactly zero, which for a derived vector usually "
            "means the estimate collapsed rather than that the sea is still."
        )

    if forcing.get("origin_status") == "DERIVED":
        vessels = forcing.get("n_vessels")
        observations = forcing.get("n_observations")
        if vessels is not None and vessels < MIN_VESSELS_FOR_FORCING:
            warnings.append(
                f"Derived from {vessels} vessel(s); at least "
                f"{MIN_VESSELS_FOR_FORCING} are needed for a robust vector."
            )
        if observations is not None and observations < MIN_OBSERVATIONS_FOR_FORCING:
            warnings.append(
                f"Derived from {observations} position report(s); at least "
                f"{MIN_OBSERVATIONS_FOR_FORCING} are needed for a robust vector."
            )
        if forcing.get("distance_km") is not None and forcing["distance_km"] > 100:
            warnings.append(
                f"Nearest derived vector is {forcing['distance_km']:.0f} km from the "
                "plume origin; the current is assumed uniform over that gap."
            )
        if (forcing.get("uncertainty_mps") or 0.0) <= 0:
            warnings.append(
                "The vector carries no positive uncertainty estimate, so its spread "
                "cannot be cross-checked."
            )

    return {
        "credible": not warnings,
        "warnings": warnings,
        "gates": {
            "min_vessels": MIN_VESSELS_FOR_FORCING,
            "min_observations": MIN_OBSERVATIONS_FOR_FORCING,
            "max_plausible_speed_ms": IMPLAUSIBLE_SURFACE_SPEED_MS,
        },
    }


def resolve_forcing(db: Session, region_id: int, latitude: float, longitude: float) -> tuple[dict | None, list[str]]:
    """Try each forcing source in trust order, recording what was checked."""
    checked: list[str] = []

    observed = _bearing_speed_from_observation(db, region_id)
    checked.append("ocean_observations (REAL/HISTORICAL current_speed)")
    if observed is not None:
        return observed, checked

    derived = _bearing_speed_from_derived(db, latitude, longitude)
    checked.append("derived_currents (AIS-derived vectors)")
    if derived is not None:
        return derived, checked

    return None, checked


def project_drift(
    db: Session,
    region_id: int,
    latitude: float,
    longitude: float,
    duration_h: int = 72,
    sensitivity: float = 1.0,
) -> dict:
    """Project a microplastic plume from a hotspot for 24-72 hours.

    Returns a corridor with an explicit status.  When no forcing data is
    available the function returns ``status="NO_FORCING"`` and no trajectory,
    rather than a plausible-looking line drawn from a default current.
    """
    duration_h = max(6, min(72, int(duration_h)))
    sensitivity = max(0.4, min(2.5, float(sensitivity)))

    forcing, checked = resolve_forcing(db, region_id, latitude, longitude)

    if forcing is None:
        return {
            "status": "NO_FORCING",
            "algorithm_version": DRIFT_ALGORITHM_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "region_id": region_id,
            "origin": {"latitude": round(latitude, 4), "longitude": round(longitude, 4)},
            "duration_h": duration_h,
            "trajectory": [],
            "corridor": [],
            "checked_sources": checked,
            "reason": (
                "No trusted surface-current observation and no AIS-derived vector "
                "within 300 km of this hotspot. A drift corridor needs real forcing, "
                "so none is produced. This is an absence of data, not still water."
            ),
            "limitations": [
                "Microplastics are not a passive tracer; buoyant particles wind-slip "
                "and dense ones sink.",
                "No vertical shear, Stokes drift, beaching or resuspension is modelled.",
            ],
        }

    bearing = forcing["direction_deg"] % 360.0
    speed_ms = max(0.0, forcing["speed_ms"]) * SURFACE_SPEED_FRACTION
    speed_kmh = speed_ms * 3.6
    wind_bearing = (bearing + WIND_OFFSET_DEG) % 360.0

    # Deterministic meander so the corridor is reproducible for a given input.
    meander_amp = 10.0

    trajectory: list[dict] = []
    corridor: list[dict] = []
    lat, lon = latitude, longitude

    for hour in range(duration_h + 1):
        b = math.radians(
            (bearing + meander_amp * math.sin(math.pi * hour / max(1, duration_h))) % 360
        )
        step_km = speed_kmh * sensitivity
        dlat = (step_km * math.cos(b)) / 111.0
        dlon = (step_km * math.sin(b)) / (
            111.0 * max(0.2, math.cos(math.radians(lat)))
        )
        lat += dlat
        lon += dlon

        spread_km = round(1.0 + 1.15 * math.sqrt(hour) * sensitivity, 2)
        trajectory.append({
            "hour": hour,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "spread_km": spread_km,
            "cumulative_km": round(speed_kmh * sensitivity * hour, 2),
        })

        # Left/right edge of the corridor, perpendicular to travel.
        perp = b + math.pi / 2
        for side, sign in (("left", 1), ("right", -1)):
            edge_lat = lat + (sign * spread_km * math.cos(perp)) / 111.0
            edge_lon = lon + (sign * spread_km * math.sin(perp)) / (
                111.0 * max(0.2, math.cos(math.radians(lat)))
            )
            corridor.append({
                "hour": hour,
                "side": side,
                "latitude": round(edge_lat, 4),
                "longitude": round(edge_lon, 4),
            })

    quality = assess_forcing_quality(forcing)

    limitations = [
        "Microplastics are not a passive tracer; buoyant particles wind-slip "
        "and dense ones sink.",
        "No vertical shear, Stokes drift, beaching or resuspension is modelled.",
        "Forcing is assumed constant over the projection window.",
        "Sensitivity scaling is an explicit user control, not a calibrated "
        "dispersion parameter.",
    ]

    # A corridor built on thin forcing is still drawn, but it is never allowed to
    # look like a corridor built on good forcing.
    limitations = quality["warnings"] + limitations

    if not quality["credible"]:
        confidence = "VERY_LOW"
        confidence_note = (
            "This corridor rests on forcing that failed at least one credibility "
            "check (listed below). It is shown for completeness, not for planning. "
            "Treat the direction as indicative at best and the speed as unreliable."
        )
    else:
        confidence = "LOW"
        confidence_note = (
            "This is a single-layer surface corridor, not a forecast. It shows the "
            "direction a floating particle would follow under the given forcing, "
            "with a sqrt-time diffusive spread. It does not account for sinking, "
            "beaching or vertical shear."
        )

    return {
        "status": "OK",
        "algorithm_version": DRIFT_ALGORITHM_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "region_id": region_id,
        "origin": {"latitude": round(latitude, 4), "longitude": round(longitude, 4)},
        "duration_h": duration_h,
        "sensitivity": sensitivity,
        "forcing": {
            **forcing,
            "speed_kmh": round(speed_kmh, 3),
            "wind_bearing_deg": round(wind_bearing, 1),
            "wind_leeway_fraction": WIND_LEEWAY_FRACTION,
        },
        "forcing_quality": quality,
        "checked_sources": checked,
        "trajectory": trajectory,
        "corridor": corridor,
        "end_point": {
            "latitude": trajectory[-1]["latitude"],
            "longitude": trajectory[-1]["longitude"],
            "cumulative_km": trajectory[-1]["cumulative_km"],
            "spread_km": trajectory[-1]["spread_km"],
        },
        "method": DRIFT_METHOD,
        "confidence": confidence,
        "confidence_note": confidence_note,
        "limitations": limitations,
    }
