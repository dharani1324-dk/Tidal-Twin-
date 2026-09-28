"""
TidalTwin - Regional Mapping for Dissolved Oxygen Samples
===========================================================
Assigns dissolved oxygen samples to the 8 monitored coastal regions and
computes confidence scores based on data density and proximity.

This script:
1. Loads all unassigned dissolved_oxygen_samples (region_id IS NULL)
2. Finds the nearest coastal region (from ocean_locations) within a search radius
3. Assigns region_id and computes confidence_score based on:
   - Distance to region centroid
   - Number of samples in the region (data density)
   - Temporal recency
   - Source reliability (Argo BGC = high, literature = medium)
4. Updates the samples with region_id, region_distance_km, confidence_score

Run after ingesting Argo BGC and NOAA hypoxia data:
    python -m scripts.map_oxygen_to_regions
"""

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.dissolved_oxygen import DissolvedOxygenSample
from app.models.location import OceanLocation


# Search radius for assigning samples to regions (km)
MAX_ASSIGNMENT_RADIUS_KM = 500.0

# Confidence scoring weights
DISTANCE_WEIGHT = 0.4
DENSITY_WEIGHT = 0.3
RECENCY_WEIGHT = 0.2
SOURCE_WEIGHT = 0.1

# Source confidence base scores
SOURCE_CONFIDENCE = {
    "Argo BGC float": 0.95,
    "Argo float": 0.95,
    "NOAA Hypoxia Watch": 0.90,
    "Literature Reference": 0.70,
    "World Ocean Database": 0.85,
    "Copernicus Marine": 0.90,
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def get_region_centroids(db: Session) -> dict[int, tuple[float, float]]:
    """Get centroid (lat, lon) for each ocean location."""
    from geoalchemy2.shape import to_shape
    centroids = {}
    for loc in db.query(OceanLocation).all():
        if loc.geom is not None:
            geom = to_shape(loc.geom)
            centroids[loc.id] = (geom.centroid.y, geom.centroid.x)
    return centroids


def compute_confidence(
    distance_km: float,
    sample_count: int,
    days_old: float,
    source: str,
    max_radius: float = MAX_ASSIGNMENT_RADIUS_KM
) -> float:
    """Compute confidence score 0-1 based on multiple factors."""
    
    # Distance score: 1.0 at center, 0.0 at max_radius
    distance_score = max(0.0, 1.0 - (distance_km / max_radius))
    
    # Density score: log scale, saturates around 50 samples
    density_score = min(1.0, math.log10(max(1, sample_count) + 1) / math.log10(51))
    
    # Recency score: 1.0 for <7 days, 0.5 for 30 days, 0.0 for >90 days
    if days_old <= 7:
        recency_score = 1.0
    elif days_old <= 30:
        recency_score = 0.7
    elif days_old <= 90:
        recency_score = 0.4
    else:
        recency_score = 0.1
    
    # Source score
    source_score = SOURCE_CONFIDENCE.get(source, 0.5)
    
    # Weighted combination
    confidence = (
        DISTANCE_WEIGHT * distance_score +
        DENSITY_WEIGHT * density_score +
        RECENCY_WEIGHT * recency_score +
        SOURCE_WEIGHT * source_score
    )
    
    return round(confidence, 3)


def main():
    print("=" * 60)
    print("TidalTwin - Regional Mapping for Dissolved Oxygen Samples")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Get region centroids
        centroids = get_region_centroids(db)
        print(f"Found {len(centroids)} monitored coastal regions")
        
        # Get all unassigned oxygen samples
        unassigned = db.query(DissolvedOxygenSample).filter(
            DissolvedOxygenSample.region_id.is_(None)
        ).all()
        print(f"Found {len(unassigned)} unassigned oxygen samples")
        
        if not unassigned:
            print("No unassigned samples to map.")
            return
        
        # Count samples per region (for density scoring)
        region_counts = db.query(
            DissolvedOxygenSample.region_id,
            func.count(DissolvedOxygenSample.id)
        ).filter(
            DissolvedOxygenSample.region_id.isnot(None)
        ).group_by(DissolvedOxygenSample.region_id).all()
        region_sample_counts = {r[0]: r[1] for r in region_counts}
        
        now = datetime.now(timezone.utc)
        assigned = 0
        skipped = 0
        
        for sample in unassigned:
            lat, lon = sample.latitude, sample.longitude
            best_region_id = None
            best_distance = float('inf')
            
            # Find nearest region within radius
            for region_id, (c_lat, c_lon) in centroids.items():
                dist = haversine_km(lat, lon, c_lat, c_lon)
                if dist < best_distance and dist <= MAX_ASSIGNMENT_RADIUS_KM:
                    best_distance = dist
                    best_region_id = region_id
            
            if best_region_id is None:
                skipped += 1
                continue
            
            # Compute confidence
            sample_count = region_sample_counts.get(best_region_id, 0)
            days_old = (now - sample.sampled_at).total_seconds() / 86400 if sample.sampled_at else 365
            source_key = sample.source.split("(")[0].strip() if "(" in sample.source else sample.source
            confidence = compute_confidence(best_distance, sample_count, days_old, source_key)
            
            # Update sample
            sample.region_id = best_region_id
            sample.region_distance_km = round(best_distance, 1)
            sample.confidence_score = confidence
            
            assigned += 1
            region_sample_counts[best_region_id] = sample_count + 1
        
        db.commit()
        print(f"\nAssigned: {assigned} samples")
        print(f"Skipped (out of radius): {skipped} samples")
        
        # Summary by region
        print("\nSamples per region:")
        for region_id, count in sorted(region_sample_counts.items()):
            loc = db.query(OceanLocation).filter(OceanLocation.id == region_id).first()
            if loc:
                print(f"  {loc.name}: {count} samples")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()