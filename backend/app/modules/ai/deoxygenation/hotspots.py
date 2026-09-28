"""
TidalTwin - Deoxygenation: hotspots
====================================
Detects and ranks hypoxic zones (low oxygen areas) from oxygen samples,
producing actionable hotspots with plain-language recommendations.

Hypoxia threshold: ~2 mg/L (~62.5 umol/kg)
Dead zone threshold: ~0.5 mg/L (~15.6 umol/kg)
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.modules.ai.deoxygenation.regions import DEFAULT_RADIUS_KM
from app.modules.ai.deoxygenation.units import (
    SEVERITY_ORDINALS,
    severity_for_mg_l,
)


ANOMALY_CATEGORY = "Low Oxygen Zone"

# Priority weights for ranking hotspots
PRIORITY_WEIGHTS = {
    "severity": 0.35,        # How low is the oxygen (dead zone > hypoxic > low)
    "persistence": 0.25,     # How many recent samples show hypoxia
    "spatial_extent": 0.20,  # How many nearby samples agree
    "trend": 0.15,           # Is it getting worse?
    "confidence": 0.05,      # Data quality confidence
}

# Alert tier rules (ordinal -> action)
ALERT_TIER_RULES = [
    # (min_ordinal, severity_label, action, rationale)
    (5, "CRITICAL", "immediate_investigation", 
     "Near-anoxic conditions (dead zone) - ecosystem collapse risk"),
    (4, "HIGH", "fisheries_alert", 
     "Hypoxic conditions (<2 mg/L) - fish kill risk, habitat loss"),
    (3, "MODERATE", "enhanced_monitoring", 
     "Low oxygen (2-4 mg/L) - stress on marine life, monitor closely"),
    (2, "LOW", "routine_monitoring", 
     "Moderate oxygen (4-6 mg/L) - continue routine observation"),
    (1, "NORMAL", "no_action", 
     "Healthy oxygen levels (>6 mg/L)"),
]

# Severity ladder for display
SEVERITY_LADDER = [
    {"ordinal": 1, "label": "NORMAL", "threshold_mg_l": 6.0, "color": "#10b981"},
    {"ordinal": 2, "label": "LOW", "threshold_mg_l": 4.0, "color": "#22d3ee"},
    {"ordinal": 3, "label": "MODERATE", "threshold_mg_l": 2.0, "color": "#f59e0b"},
    {"ordinal": 4, "label": "HIGH (HYPOXIC)", "threshold_mg_l": 0.5, "color": "#f97316"},
    {"ordinal": 5, "label": "CRITICAL (DEAD ZONE)", "threshold_mg_l": 0.0, "color": "#f43f5e"},
]


def _severity_from_mg_l(do_mg_l: float) -> tuple[int, str, bool, int]:
    """Return (ordinal, label, is_hypoxic, is_dead_zone) for a DO value in mg/L.

    Delegates to ``units.severity_for_mg_l``.  This used to be a third literal
    copy of the ladder (alongside normalize.py and units.py); the copies had
    already drifted, so a cluster could be labelled with an ordinal the rest of
    the module read on a different scale.
    """
    label, ordinal, is_hypoxic, is_dead_zone = severity_for_mg_l(do_mg_l)
    if label is None or ordinal is None:
        return SEVERITY_ORDINALS["NORMAL"], "NORMAL", False, False
    return ordinal, label, is_hypoxic, int(is_dead_zone)


def _worst_severity(stats: dict) -> str:
    """The most severe label present in a group's severity distribution.

    Single source of truth for "how bad is this cluster".  Previously this
    loop was copy-pasted into three places and one of them referenced the
    variable without ever assigning it, which raised NameError at the exact
    moment a real hotspot was found.
    """
    distribution = stats.get("severity_distribution") or {}
    for label in ("CRITICAL", "HIGH", "MODERATE", "LOW", "NORMAL"):
        if distribution.get(label, 0) > 0:
            return label
    return "NORMAL"


def _group_by_region_depth(records: list[dict], regions: list[dict]) -> dict:
    """Group oxygen records by region and depth layer for spatial analysis."""
    groups = defaultdict(list)
    for record in records:
        region_id = record.get("region_id")
        depth = record.get("depth_m", 0)
        if region_id is None:
            continue
        # Bin depths: surface (0-50m), mid (50-200m), deep (200m+)
        if depth <= 50:
            layer = "surface"
        elif depth <= 200:
            layer = "mid"
        else:
            layer = "deep"
        key = (region_id, layer)
        groups[key].append(record)
    return groups


def _compute_hotspot_stats(samples: list[dict], region: dict) -> dict:
    """Compute statistics for a cluster of hypoxic samples."""
    if not samples:
        return {}
    
    do_values = [s["do_mg_l"] for s in samples if s.get("do_mg_l") is not None]
    if not do_values:
        return {}
    
    lats = [s["latitude"] for s in samples]
    lons = [s["longitude"] for s in samples]
    
    # Centroid of hypoxic samples
    centroid_lat = sum(lats) / len(lats)
    centroid_lon = sum(lons) / len(lons)
    
    # Distance from region centroid
    from app.modules.ai.deoxygenation.regions import haversine_km
    dist_to_region = haversine_km(centroid_lat, centroid_lon, region["latitude"], region["longitude"])
    
    # Severity distribution
    severity_counts = defaultdict(int)
    for s in samples:
        sev = s.get("severity_label", "UNKNOWN")
        severity_counts[sev] += 1
    
    # Temporal span
    dates = [s["sampled_at"] for s in samples if s.get("sampled_at")]
    if dates:
        dates.sort()
        temporal_span_days = (dates[-1] - dates[0]).days
        latest_date = dates[-1]
    else:
        temporal_span_days = 0
        latest_date = None
    
    # Persistence: fraction of recent samples that are hypoxic
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = [s for s in samples if s.get("sampled_at") and s["sampled_at"] > recent_cutoff]
    hypoxic_recent = [s for s in recent if s.get("is_hypoxic")]
    persistence = len(hypoxic_recent) / len(recent) if recent else 0
    
    return {
        "n_samples": len(samples),
        "n_hypoxic": len([s for s in samples if s.get("is_hypoxic")]),
        "n_dead_zone": len([s for s in samples if s.get("is_dead_zone")]),
        "min_do_mg_l": round(min(do_values), 2),
        "mean_do_mg_l": round(sum(do_values) / len(do_values), 2),
        "max_do_mg_l": round(max(do_values), 2),
        "centroid_lat": round(centroid_lat, 4),
        "centroid_lon": round(centroid_lon, 4),
        "distance_to_region_km": round(dist_to_region, 1),
        "severity_distribution": dict(severity_counts),
        "temporal_span_days": temporal_span_days,
        "latest_sample_at": latest_date.isoformat() if latest_date else None,
        "persistence": round(persistence, 2),
    }


def _compute_priority(stats: dict, region: dict, trend: str = "stable") -> float:
    """Compute 0-100 priority score for a hotspot."""
    # Severity score (0-100)
    severity_map = {"CRITICAL": 100, "HIGH": 80, "MODERATE": 50, "LOW": 20, "NORMAL": 0}
    severity_score = severity_map[_worst_severity(stats)]
    
    # Persistence score
    persistence_score = stats.get("persistence", 0) * 100
    
    # Spatial extent score (more samples = larger extent)
    spatial_score = min(100, stats.get("n_samples", 0) * 5)
    
    # Trend score
    trend_map = {
        "expanding": 100,
        "stable": 50,
        "shrinking": 20,
        "insufficient_data": 30,
    }
    trend_score = trend_map.get(trend, 30)
    
    # Confidence score (from sample confidence)
    confidence_score = stats.get("mean_confidence", 0.5) * 100
    
    priority = (
        PRIORITY_WEIGHTS["severity"] * severity_score +
        PRIORITY_WEIGHTS["persistence"] * persistence_score +
        PRIORITY_WEIGHTS["spatial_extent"] * spatial_score +
        PRIORITY_WEIGHTS["trend"] * trend_score +
        PRIORITY_WEIGHTS["confidence"] * confidence_score
    )
    
    return round(priority, 1)


def _generate_recommendations(stats: dict, region: dict, trend: str) -> list[dict]:
    """Generate plain-language recommendations for a hotspot."""
    recommendations = []
    
    worst_severity = _worst_severity(stats)
    
    if worst_severity == "CRITICAL":
        recommendations.append({
            "action": "immediate_investigation",
            "priority": "critical",
            "text": f"DEAD ZONE detected at {region['name']} (O₂ ≤ 0.5 mg/L). "
                    f"Deploy emergency monitoring; alert fisheries and coastal authorities. "
                    f"Ecosystem collapse risk is imminent.",
        })
        recommendations.append({
            "action": "fisheries_closure_assessment",
            "priority": "high",
            "text": "Assess need for temporary fisheries closure in affected zone. "
                    "Coordinate with state fisheries department.",
        })
    
    elif worst_severity == "HIGH":
        recommendations.append({
            "action": "fisheries_alert",
            "priority": "high",
            "text": f"HYPOXIC ZONE detected at {region['name']} (O₂ < 2 mg/L). "
                    f"Issue fisheries advisory: avoid bottom trawling, monitor fish kills. "
                    f"Increase sampling frequency to weekly.",
        })
        recommendations.append({
            "action": "enhanced_monitoring",
            "priority": "medium",
            "text": "Deploy additional Argo BGC floats or gliders to track zone expansion. "
                    "Request Copernicus Marine forecast for oxygen fields.",
        })
    
    elif worst_severity == "MODERATE":
        recommendations.append({
            "action": "enhanced_monitoring",
            "priority": "medium",
            "text": f"Low oxygen zone at {region['name']} (2-4 mg/L). "
                    f"Marine life stress likely. Increase monitoring to bi-weekly. "
                    f"Check for seasonal upwelling or river discharge drivers.",
        })
    
    elif worst_severity == "LOW":
        recommendations.append({
            "action": "routine_monitoring",
            "priority": "low",
            "text": f"Moderate oxygen at {region['name']} (4-6 mg/L). "
                    f"Continue routine monthly monitoring. "
                    f"Watch for declining trend toward hypoxia threshold.",
        })
    
    # Trend-based recommendations
    if trend == "expanding":
        recommendations.append({
            "action": "trend_alert",
            "priority": "high",
            "text": f"Hypoxic zone at {region['name']} is EXPANDING. "
                    f"Project expansion trajectory; prepare contingency plans.",
        })
    elif trend == "shrinking":
        recommendations.append({
            "action": "recovery_monitoring",
            "priority": "medium",
            "text": f"Hypoxic zone at {region['name']} is SHRINKING. "
                    f"Continue monitoring to confirm recovery; document drivers.",
        })
    
    return recommendations


def _hotspot_trend(
    records: list[dict],
    region_id: int,
    layer: str,
    stats: dict,
) -> str:
    """Direction of the hypoxic fraction for one region + depth layer.

    Uses the same yearly hypoxic-fraction regression as the trends module, so
    the label on a hotspot always agrees with ``GET /trends``.  Returns
    "insufficient_data" rather than a fabricated "stable" when the time series
    is too short to support a direction.
    """
    from app.modules.ai.deoxygenation.trends import (
        _compute_hypoxic_trend,
        _prepare_time_series,
    )

    series = _prepare_time_series(records, region_id, layer)
    if not series:
        return "insufficient_data"
    return _compute_hypoxic_trend(series).get("direction", "insufficient_data")


def detect_hypoxic_hotspots(records: list[dict], regions: list[dict], 
                            min_priority: float = 0.0) -> dict:
    """Main entry point: detect and rank hypoxic hotspots from oxygen records."""
    if not records:
        return {
            "anomaly_category": ANOMALY_CATEGORY,
            "hotspot_count": 0,
            "hotspots": [],
            "recommendations": {
                "summary": "No dissolved oxygen samples stored yet.",
                "actions": [],
            },
            "reason": "Ingest Argo BGC and NOAA hypoxia data first.",
        }
    
    # Only samples with a real, finite oxygen value can describe a zone.
    valid_records = []
    for r in records:
        value = r.get("do_mg_l")
        if value is None:
            continue
        try:
            if float(value) != float(value):  # NaN
                continue
        except (TypeError, ValueError):
            continue
        valid_records.append(r)
    
    # Group by region and depth layer
    groups = _group_by_region_depth(valid_records, regions)
    
    hotspots = []
    region_map = {r["region_id"]: r for r in regions}
    
    for (region_id, layer), samples in groups.items():
        region = region_map.get(region_id)
        if not region:
            continue
        
        # Only consider groups with at least some hypoxic samples
        hypoxic_samples = [s for s in samples if s.get("is_hypoxic")]
        if not hypoxic_samples:
            continue
        
        # Compute statistics
        stats = _compute_hotspot_stats(samples, region)
        if not stats:
            continue
        
        stats["mean_confidence"] = sum(s.get("confidence_score", 0.5) for s in samples) / len(samples)
        
        # Real trend from the hypoxic-fraction time series for this exact
        # region + depth layer, rather than a hardcoded "stable".
        trend = _hotspot_trend(records, region_id, layer, stats)
        
        # Compute priority
        priority = _compute_priority(stats, region, trend)
        
        if priority < min_priority:
            continue
        
        # Generate recommendations
        recommendations = _generate_recommendations(stats, region, trend)
        
        # Determine display severity
        worst_ordinal = max(
            (s.get("severity_ordinal", 1) for s in samples if s.get("severity_ordinal")),
            default=1
        )
        severity_labels = {1: "NORMAL", 2: "LOW", 3: "MODERATE", 4: "HIGH", 5: "CRITICAL"}
        published_class = _worst_severity(stats)
        
        hotspot = {
            "region_id": region_id,
            "region": region["name"],
            "depth_layer": layer,
            "latitude": stats["centroid_lat"],
            "longitude": stats["centroid_lon"],
            "distance_to_region_km": stats["distance_to_region_km"],
            "priority": priority,
            "severity": severity_labels.get(worst_ordinal, "UNKNOWN"),
            "severity_ordinal": worst_ordinal,
            "is_hotspot": priority >= 30,  # Threshold for "actionable"
            "statistics": stats,
            "trend": trend,
            "medium_display": f"{layer} water ({layer})",
            "unit": "mg/L",
            "published_class": published_class,
            "latest_sample_at": stats["latest_sample_at"],
            "action": recommendations[0]["action"] if recommendations else "monitor",
            "recommendations": recommendations,
            "confidence": round(stats["mean_confidence"] * 100, 1),
        }
        hotspots.append(hotspot)
    
    # Sort by priority descending
    hotspots.sort(key=lambda h: -h["priority"])
    
    # Generate summary
    critical_count = len([h for h in hotspots if h["severity"] == "CRITICAL"])
    high_count = len([h for h in hotspots if h["severity"] == "HIGH"])
    moderate_count = len([h for h in hotspots if h["severity"] == "MODERATE"])
    
    if critical_count > 0:
        summary = f"{critical_count} DEAD ZONE(s), {high_count} HYPOXIC zone(s) - IMMEDIATE ACTION REQUIRED"
    elif high_count > 0:
        summary = f"{high_count} HYPOXIC zone(s), {moderate_count} moderate - fisheries alert recommended"
    elif moderate_count > 0:
        summary = f"{moderate_count} low oxygen zone(s) - enhanced monitoring advised"
    else:
        summary = "No hypoxic hotspots detected above threshold"
    
    all_actions = []
    for h in hotspots:
        all_actions.extend(h["recommendations"])
    
    return {
        "anomaly_category": ANOMALY_CATEGORY,
        "hotspot_count": len(hotspots),
        "hotspots": hotspots,
        "recommendations": {
            "summary": summary,
            "actions": all_actions,
        },
        "severity_breakdown": {
            "critical": critical_count,
            "high": high_count,
            "moderate": moderate_count,
        },
    }