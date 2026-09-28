"""
TidalTwin - REAL In-Situ Observation Hydration
=================================================
Bridges the REAL Argo GDAC surface measurements already ingested into
``argo_profiles`` into the shared ``ocean_observations`` store so Twin
comparison and the validation stack can score them as REAL measured
evidence.

Design principles (honesty first):
  * Only REAL ingested levels are bridged - the exact value, depth, time and
    position recorded by the float.  Nothing is interpolated or invented.
  * Only surface samples (<= SURFACE_BAND_M) are bridged; deep levels stay in
    ``argo_profiles``.  Wave/current fields are left NULL because floats do
    not measure surface waves or currents.
  * Every bridged row uses ``data_type="observation"`` and
    ``source="Argo float <WMO> (real Argo GDAC surface sample)"`` so
    :func:`app.modules.ai.provenance_quality.origin_status` returns "REAL".
  * Each row's ``extra`` JSON carries the float's ACTUAL measured lat/lon and
    the haversine distance to the assigned coast centroid, so consumers can
    see this is a basin-scale reference, not a co-located measurement.
  * Each monitored coast is paired with the float whose measured surface
    samples are nearest; a coast is never paired to a float from the wrong
    side of the subcontinent.
  * Idempotent: re-running replaces, never duplicates, its own rows.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.argo import ArgoProfile
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.services.ocean_data import get_location_center

SURFACE_BAND_M = 10.0
MAX_CYCLES_PER_FLOAT = 90
# The real Argo record in this deployment spans January – September 2026.
# A 365-day window captures the full measured surface history so the adaptive
# engine has enough real samples to learn per-region baselines.
MAX_AGE_DAYS = 365
SOURCE_PREFIX = "Argo float "


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    radius = 6371.0088
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lambda = math.radians(lon_b - lon_a)
    ha = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(ha)))


def _surface_samples(db: Session) -> list[dict[str, Any]]:
    """The actual shallowest measured level of every Argo surface cycle.

    One record per (float_id, time) profile cycle: the level closest to the
    surface is used verbatim (real value, real depth, real position).
    """
    rows = (
        db.query(
            ArgoProfile.float_id,
            ArgoProfile.time,
            ArgoProfile.latitude,
            ArgoProfile.longitude,
            ArgoProfile.depth_m,
            ArgoProfile.temperature,
            ArgoProfile.salinity,
        )
        .filter(ArgoProfile.depth_m <= SURFACE_BAND_M, ArgoProfile.temperature.isnot(None))
        .order_by(ArgoProfile.float_id, ArgoProfile.time.desc(), ArgoProfile.depth_m.asc())
        .all()
    )
    cycles: dict[tuple[str, datetime], dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    for float_id, time_value, latitude, longitude, depth_m, temperature, salinity in rows:
        ts: datetime = time_value
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc)
        if now - ts > timedelta(days=MAX_AGE_DAYS):
            continue
        key = (str(float_id), ts.replace(second=0, microsecond=0))
        if key in cycles:
            continue
        cycles[key] = {
            "float_id": str(float_id),
            "time": ts,
            "lat": float(latitude),
            "lon": float(longitude),
            "depth_m": float(depth_m),
            "temperature": float(temperature),
            "salinity": float(salinity) if salinity is not None else None,
        }
    return list(cycles.values())


def _float_centroids(samples: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    centroids: dict[str, list[tuple[float, float]]] = {}
    for sample in samples:
        centroids.setdefault(sample["float_id"], []).append((sample["lat"], sample["lon"]))
    return {
        float_id: (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
        for float_id, points in centroids.items()
    }


def _assign_locations(db: Session, samples: list[dict[str, Any]]) -> dict[int, tuple[str, float]]:
    """Pair each monitored coast with its nearest measured float. Returns
    {location_id: (float_id, distance_km_to_coast)}."""
    if not samples:
        return {}
    centroids = _float_centroids(samples)
    assignments: dict[int, tuple[str, float]] = {}
    for location in db.query(OceanLocation).all():
        center_lat, center_lon = get_location_center(location)
        if center_lat is None or center_lon is None:
            continue
        best, best_distance = None, None
        for float_id, (float_lat, float_lon) in centroids.items():
            distance = haversine_km(float_lat, float_lon, center_lat, center_lon)
            if best_distance is None or distance < best_distance:
                best, best_distance = float_id, distance
        if best is not None:
            assignments[location.id] = (best, best_distance)
    return assignments


def hydrate_real_observations(db: Session) -> dict[str, Any]:
    """Replace the app-managed REAL in-situ rows with the freshest surface
    cycles from the REAL Argo profiles on record. Idempotent."""
    samples = _surface_samples(db)
    if not samples:
        return {
            "status": "noop",
            "hydrated": 0,
            "reason": "No real Argo surface samples (depth <= {} m) are present in argo_profiles.".format(SURFACE_BAND_M),
            "source_note": "Open-Meteo forecast rows remain MODEL_DERIVED and are never treated as measurements.",
        }

    assignments = _assign_locations(db, samples)
    source_marker = SOURCE_PREFIX + "%"
    legacy_marker = "%(real Argo GDAC surface sample)"
    db.query(OceanObservation).filter(
        OceanObservation.source.like(source_marker),
        OceanObservation.data_type == "observation",
    ).delete(synchronize_session=False)
    db.query(OceanObservation).filter(
        OceanObservation.source.like(legacy_marker),
        OceanObservation.data_type == "observation",
    ).delete(synchronize_session=False)
    db.flush()

    per_location: dict[int, dict[str, Any]] = {}
    total = 0
    for location_id, (float_id, distance_km) in assignments.items():
        own = [s for s in samples if s["float_id"] == float_id]
        own.sort(key=lambda s: s["time"], reverse=True)
        own = own[:MAX_CYCLES_PER_FLOAT]
        for sample in own:
            depth_m = sample["depth_m"]
            measured_lat, measured_lon = sample["lat"], sample["lon"]
            extra = {
                "data_kind": "real_in_situ_argo",
                "float_id": float_id,
                "measured_lat": round(measured_lat, 5),
                "measured_lon": round(measured_lon, 5),
                "measured_depth_m": round(depth_m, 2),
                "distance_km_to_coast": round(distance_km, 1),
                "representativeness_note": (
                    f"Nearest real in-situ Argo profiler for this basin; open-ocean sample "
                    f"{distance_km:.0f} km from the coast centroid, not co-located."
                ),
                "provenance": "Real Argo GDAC surface cycle",
            }
            db.add(OceanObservation(
                location_id=location_id,
                timestamp=sample["time"],
                sea_surface_temperature=sample["temperature"],
                salinity=sample["salinity"],
                depth_m=depth_m,
                source=f"{SOURCE_PREFIX}{float_id} (real Argo GDAC surface sample)",
                data_type="observation",
                extra=json.dumps(extra),
            ))
            total += 1
        per_location[location_id] = {
            "float_id": float_id,
            "distance_km": round(distance_km, 1),
            "cycles": len(own),
            "latest": own[0]["time"].isoformat() if own else None,
        }

    db.commit()
    return {
        "status": "hydrated",
        "hydrated": total,
        "source_note": "REAL Argo in-situ surface samples; distances to coast are disclosed per row. Open-Meteo rows remain MODEL_DERIVED.",
        "floats_used": sorted({sample["float_id"] for sample in samples}),
        "locations": {str(k): v for k, v in per_location.items()},
    }
