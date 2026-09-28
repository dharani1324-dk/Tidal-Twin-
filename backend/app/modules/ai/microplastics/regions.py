"""
TidalTwin - Microplastics: regional mapping + spatial interpolation
===================================================================
Two jobs:

1. MAPPING - attach each sample to one of the coastal regions the platform
   already monitors.  A sample further than ``MAX_MAPPING_KM`` from every
   region stays unassigned.  We do not snap an Atlantic sample onto an Indian
   coast just to make the map look full, and the distance travels with the row
   so the strength of every mapping is inspectable.

2. INTERPOLATION - inverse distance weighting (IDW) to estimate concentration
   between sparse samples, so a heatmap can be drawn from a handful of points.

THE INTERPOLATION RULE
----------------------
IDW is an interpolation of *absence*, not evidence.  Two consequences shape the
implementation:

  * Interpolation happens **within one unit family at a time**.  A surface is
    built from water-column samples or from sediment samples, never both.

  * Grid nodes with no sample inside ``radius_km`` produce **no value at all**.
    They are returned as explicit gaps.  A node is never filled with zero,
    because zero means "sampled and clean" while a gap means "nobody looked".

Every estimated node carries ``n_sources``, ``nearest_km`` and
``is_estimate=True`` so the UI can render it differently from a measurement.
"""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.services.ocean_data import get_location_center

EARTH_R_KM = 6371.0088

# Beyond this, a sample is not attributed to a monitored region at all.
MAX_MAPPING_KM = 600.0

# Default IDW search radius.  Chosen to reach across the Gulf of Mannar
# cluster while staying well short of bridging unrelated basins.
DEFAULT_RADIUS_KM = 250.0
DEFAULT_POWER = 2.0
DEFAULT_MAX_SOURCES = 8


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    )
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


# --------------------------------------------------------------------------
# 1. Mapping
# --------------------------------------------------------------------------
def resolve_monitored_regions(db: Session) -> list[dict]:
    """The coastal regions this platform already monitors, with centroids."""
    regions: list[dict] = []
    for loc in db.query(OceanLocation).order_by(OceanLocation.id.asc()).all():
        lat, lon = get_location_center(loc)
        if lat is None or lon is None:
            continue
        regions.append({
            "region_id": loc.id,
            "name": loc.name,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "region_type": loc.region_type,
            "country": loc.country,
        })
    return regions


def nearest_region(
    latitude: float,
    longitude: float,
    regions: list[dict],
    max_km: float = MAX_MAPPING_KM,
) -> tuple[int | None, float | None]:
    """Return ``(region_id, distance_km)`` for the closest region within range.

    Returns ``(None, distance)`` when nothing is close enough - the distance is
    still reported so the coverage panel can show how far off it was.
    """
    if not regions:
        return None, None

    best_id: int | None = None
    best_km = float("inf")
    for region in regions:
        distance = haversine_km(
            latitude, longitude, region["latitude"], region["longitude"]
        )
        if distance < best_km:
            best_km = distance
            best_id = region["region_id"]

    if best_km > max_km:
        return None, round(best_km, 2)
    return best_id, round(best_km, 2)


def assign_records(records: list[dict], regions: list[dict], max_km: float = MAX_MAPPING_KM) -> dict:
    """Attach ``region_id``/``region_distance_km`` to normalised records in place."""
    assigned = 0
    unassigned = 0
    for record in records:
        region_id, distance = nearest_region(
            record["latitude"], record["longitude"], regions, max_km=max_km
        )
        record["region_id"] = region_id
        record["region_distance_km"] = distance
        if region_id is None:
            unassigned += 1
        else:
            assigned += 1

    return {
        "assigned": assigned,
        "unassigned": unassigned,
        "max_mapping_km": max_km,
        "note": (
            "Samples further than the mapping radius from every monitored region "
            "are stored unassigned rather than snapped to the nearest coast."
        ),
    }


# --------------------------------------------------------------------------
# 2. Interpolation
# --------------------------------------------------------------------------
def idw_at_point(
    latitude: float,
    longitude: float,
    samples: list[dict],
    radius_km: float = DEFAULT_RADIUS_KM,
    power: float = DEFAULT_POWER,
    max_sources: int = DEFAULT_MAX_SOURCES,
) -> dict | None:
    """Inverse-distance-weighted estimate at one point, or ``None`` for a gap.

    ``samples`` entries need ``latitude``, ``longitude`` and ``value``.
    Returns ``None`` when no sample lies within ``radius_km`` - the caller must
    render that as missing data, not as zero.
    """
    if not samples:
        return None

    weighted: list[tuple[float, float]] = []
    nearest_km = float("inf")
    for sample in samples:
        distance = haversine_km(
            latitude, longitude, sample["latitude"], sample["longitude"]
        )
        if distance < nearest_km:
            nearest_km = distance
        if distance <= radius_km:
            weighted.append((distance, sample["value"]))

    if not weighted:
        return None

    weighted.sort(key=lambda pair: pair[0])
    weighted = weighted[:max_sources]

    exact = [value for distance, value in weighted if distance <= 1e-9]
    if exact:
        # A sample sits on the node; return it rather than an interpolation.
        return {
            "value": round(sum(exact) / len(exact), 6),
            "n_sources": len(exact),
            "nearest_km": 0.0,
            "is_estimate": False,
            "method": "exact sample at this location",
        }

    numerator = 0.0
    denominator = 0.0
    for distance, value in weighted:
        weight = 1.0 / (distance ** power)
        numerator += weight * value
        denominator += weight

    if denominator <= 0:
        return None

    return {
        "value": round(numerator / denominator, 6),
        "n_sources": len(weighted),
        "nearest_km": round(nearest_km, 2),
        "is_estimate": True,
        "method": f"inverse distance weighting (power={power}, radius={radius_km:g} km)",
    }


def build_surface(
    samples: list[dict],
    bbox: dict,
    step_deg: float = 0.5,
    radius_km: float = DEFAULT_RADIUS_KM,
    power: float = DEFAULT_POWER,
    max_nodes: int = 1200,
) -> dict:
    """Build a gridded IDW surface over ``bbox`` from one unit family's samples.

    Returns nodes plus a first-class count of the grid cells left empty, so the
    coverage ratio is always reported alongside the picture.
    """
    lat_min, lat_max = bbox["lat_min"], bbox["lat_max"]
    lon_min, lon_max = bbox["lon_min"], bbox["lon_max"]

    n_lat = max(1, int(round((lat_max - lat_min) / step_deg)) + 1)
    n_lon = max(1, int(round((lon_max - lon_min) / step_deg)) + 1)
    total_cells = n_lat * n_lon

    nodes: list[dict] = []
    gaps = 0

    for i in range(n_lat):
        latitude = lat_min + i * step_deg
        if latitude > lat_max:
            continue
        for j in range(n_lon):
            if len(nodes) >= max_nodes:
                break
            longitude = lon_min + j * step_deg
            if longitude > lon_max:
                continue

            estimate = idw_at_point(
                latitude, longitude, samples, radius_km=radius_km, power=power
            )
            if estimate is None:
                gaps += 1
                continue

            nodes.append({
                "latitude": round(latitude, 4),
                "longitude": round(longitude, 4),
                "value": estimate["value"],
                "n_sources": estimate["n_sources"],
                "nearest_km": estimate["nearest_km"],
                "is_estimate": estimate["is_estimate"],
            })

    cells_evaluated = gaps + len(nodes)

    return {
        "nodes": nodes,
        "gap_cells": gaps,
        "cells_evaluated": cells_evaluated,
        "grid_cells": total_cells,
        "step_deg": step_deg,
        "radius_km": radius_km,
        "power": power,
        "coverage_ratio": round(len(nodes) / cells_evaluated, 4) if cells_evaluated else 0.0,
        "method": "inverse distance weighting (no kriging variogram fitted)",
        "honesty_note": (
            f"{len(nodes)} of {cells_evaluated} grid cells lie within {radius_km:g} km "
            f"of a real sample and are interpolated; {gaps} cells have no sample in "
            "range and are reported as gaps, never filled with zero."
        ),
    }


def distance_decay_confidence(nearest_km: float | None, radius_km: float = DEFAULT_RADIUS_KM) -> float:
    """Confidence in an interpolated value, from its distance to real data.

    Linear decay to zero at the search radius.  Deliberately simple and
    readable rather than a fitted variogram we have no data to fit.
    """
    if nearest_km is None:
        return 0.0
    if nearest_km <= 0:
        return 100.0
    if nearest_km >= radius_km:
        return 0.0
    return round(100.0 * (1.0 - nearest_km / radius_km), 1)
