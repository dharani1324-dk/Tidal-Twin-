"""
TidalTwin - Deoxygenation: regions
===================================
Resolves the 8 monitored coastal regions and assigns oxygen samples to them
with distance-based confidence decay.
"""

from sqlalchemy.orm import Session

from app.models.location import OceanLocation


DEFAULT_RADIUS_KM = 250.0
MAX_ASSIGNMENT_RADIUS_KM = 500.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    import math
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def resolve_monitored_regions(db: Session) -> list[dict]:
    """Return the 8 monitored coastal regions with their centroids."""
    from geoalchemy2.shape import to_shape
    
    regions = []
    for loc in db.query(OceanLocation).all():
        lat = lon = None
        if loc.geom is not None:
            geom = to_shape(loc.geom)
            lon, lat = geom.centroid.x, geom.centroid.y
        if lat is not None and lon is not None:
            regions.append({
                "region_id": loc.id,
                "name": loc.name,
                "region_type": loc.region_type,
                "country": loc.country,
                "latitude": lat,
                "longitude": lon,
            })
    return regions


def distance_decay_confidence(distance_km: float | None, radius_km: float = DEFAULT_RADIUS_KM) -> float:
    """Compute confidence based on distance from sample to region centroid.
    
    1.0 at center, decays to ~0.37 at radius_km, ~0.14 at 2*radius_km.
    """
    if distance_km is None:
        return 0.0
    import math
    return max(0.0, math.exp(-distance_km / radius_km))


def assign_records(records: list[dict], regions: list[dict], 
                   max_radius: float = MAX_ASSIGNMENT_RADIUS_KM) -> dict:
    """Assign each oxygen record to its nearest monitored region within max_radius.
    
    Returns a mapping summary: {region_name: count_assigned}.
    Modifies records in-place adding region_id and region_distance_km.
    
    ``region_distance_km`` records HOW FAR the sample sits from the region it was
    assigned to.  It is deliberately NOT folded into ``confidence_score``:
    that field carries measurement trust (Argo QC flag, data mode) and is what
    the hotspot scorer reads as data quality.  Overwriting it with a distance
    decay would silently destroy the QC signal and, for open-ocean samples
    beyond max_radius, drive it to 0.0 - making a perfectly good delayed-mode
    measurement look worthless.  Spatial confidence is available to callers as
    ``distance_decay_confidence(region_distance_km)``.
    """
    mapping: dict[str, int] = {r["name"]: 0 for r in regions}
    unassigned = 0
    
    for record in records:
        lat = record.get("latitude")
        lon = record.get("longitude")
        if lat is None or lon is None:
            unassigned += 1
            continue
        
        best_region = None
        best_dist = float('inf')
        
        for region in regions:
            dist = haversine_km(lat, lon, region["latitude"], region["longitude"])
            if dist < best_dist and dist <= max_radius:
                best_dist = dist
                best_region = region
        
        if best_region:
            record["region_id"] = best_region["region_id"]
            record["region_distance_km"] = round(best_dist, 1)
            mapping[best_region["name"]] += 1
        else:
            # Outside every mapping radius: stored unassigned rather than
            # snapped to a distant coast. Measurement confidence is left as-is.
            record["region_id"] = None
            record["region_distance_km"] = None
            unassigned += 1
    
    mapping["unassigned"] = unassigned
    return mapping


def get_region_bbox(region: dict, buffer_deg: float = 2.0) -> dict:
    """Get a bounding box around a region for spatial queries."""
    return {
        "lat_min": max(-90, region["latitude"] - buffer_deg),
        "lat_max": min(90, region["latitude"] + buffer_deg),
        "lon_min": max(-180, region["longitude"] - buffer_deg),
        "lon_max": min(180, region["longitude"] + buffer_deg),
    }