"""
TidalTwin - Deoxygenation: trends
==================================
Analyzes historical oxygen time series per region to detect trends
(expanding, shrinking, stable hypoxic zones) and project future expansion.

Uses simple linear regression on regional aggregates with explicit uncertainty.
All projections are labelled PROJECTION (not forecast) with confidence bands.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone


def _finite(value) -> float | None:
    """Return a finite float, or None for None/NaN/inf.

    Guards every arithmetic path below: a single NaN would silently propagate
    into the regression sums and turn a whole region's trend into NaN.
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _prepare_time_series(records: list[dict], region_id: int, depth_layer: str = "all") -> list[dict]:
    """Extract and sort time series for a region/depth layer."""
    def depth_match(d):
        if depth_layer == "surface":
            return d <= 50
        elif depth_layer == "mid":
            return 50 < d <= 200
        elif depth_layer == "deep":
            return d > 200
        return True
    
    series = []
    for r in records:
        if r.get("region_id") != region_id:
            continue
        do_mg_l = _finite(r.get("do_mg_l"))
        if do_mg_l is None:
            continue
        if r.get("sampled_at") is None:
            continue
        depth = _finite(r.get("depth_m"))
        if depth is None or not depth_match(depth):
            continue
        series.append({
            "date": r["sampled_at"],
            "do_mg_l": do_mg_l,
            "severity_ordinal": r.get("severity_ordinal", 1),
            "is_hypoxic": r.get("is_hypoxic", 0),
            "is_dead_zone": r.get("is_dead_zone", 0),
            "confidence": r.get("confidence_score", 0.5),
        })
    
    series.sort(key=lambda x: x["date"])
    return series


def _compute_trend(series: list[dict], min_points: int = 5) -> dict:
    """Compute linear trend on oxygen time series.
    
    Returns trend info: slope, direction, significance, etc.
    """
    if len(series) < min_points:
        return {
            "direction": "insufficient_data",
            "slope_mg_l_per_year": None,
            "r_squared": None,
            "p_value": None,
            "n_points": len(series),
            "note": f"Need at least {min_points} time points for trend analysis",
        }
    
    # Convert dates to years since first observation
    dates = [s["date"] for s in series]
    values = [s["do_mg_l"] for s in series]
    
    t0 = dates[0]
    x = [(d - t0).days / 365.25 for d in dates]
    y = values
    
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(x[i] * y[i] for i in range(n))
    sum_x2 = sum(xi * xi for xi in x)
    sum_y2 = sum(yi * yi for yi in y)
    
    # Linear regression
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return {"direction": "flat", "slope_mg_l_per_year": 0, "r_squared": 0}
    
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    
    # R-squared
    y_pred = [intercept + slope * xi for xi in x]
    ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
    ss_tot = sum((yi - sum_y / n) ** 2 for yi in y)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    
    # Simple significance test (t-test on slope)
    if n > 2:
        mse = ss_res / (n - 2)
        se_slope = (mse / sum((xi - sum_x / n) ** 2 for xi in x)) ** 0.5
        t_stat = slope / se_slope if se_slope > 0 else 0
        # Two-tailed p-value approximation
        import math
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2)))) if n > 2 else 1.0
    else:
        p_value = 1.0
    
    # Classify direction
    if p_value < 0.1:
        if slope < -0.1:
            direction = "declining"
        elif slope > 0.1:
            direction = "improving"
        else:
            direction = "stable"
    else:
        direction = "no_significant_trend"
    
    return {
        "direction": direction,
        "slope_mg_l_per_year": round(slope, 3),
        "intercept_mg_l": round(intercept, 3),
        "r_squared": round(r_squared, 3),
        "p_value": round(p_value, 3),
        "n_points": n,
        "time_span_years": round(x[-1] - x[0], 2) if x else 0,
    }


def _compute_hypoxic_trend(series: list[dict]) -> dict:
    """Compute trend specifically on hypoxic fraction over time."""
    if len(series) < 3:
        return {"direction": "insufficient_data"}
    
    # Bin by year and compute hypoxic fraction
    yearly = defaultdict(list)
    for s in series:
        year = s["date"].year
        yearly[year].append(s)
    
    years = sorted(yearly.keys())
    if len(years) < 3:
        return {"direction": "insufficient_data"}
    
    hypoxic_fractions = []
    for year in years:
        year_samples = yearly[year]
        hypoxic = sum(1 for s in year_samples if s["is_hypoxic"])
        hypoxic_fractions.append(hypoxic / len(year_samples))
    
    # Linear trend on hypoxic fraction
    x = list(range(len(years)))
    y = hypoxic_fractions
    n = len(x)
    
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(x[i] * y[i] for i in range(n))
    sum_x2 = sum(xi * xi for xi in x)
    
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return {"direction": "stable", "slope_per_year": 0}
    
    slope = (n * sum_xy - sum_x * sum_y) / denom
    
    if slope > 0.05:
        direction = "expanding"
    elif slope < -0.05:
        direction = "shrinking"
    else:
        direction = "stable"
    
    return {
        "direction": direction,
        "slope_per_year": round(slope, 3),
        "years_analyzed": years,
        "hypoxic_fractions": [round(f, 2) for f in hypoxic_fractions],
    }


def analyze_trends(
    records: list[dict],
    region_id: int | None = None,
    regions: list[dict] | None = None,
) -> dict:
    """Analyze oxygen trends for all regions or one specific region.

    ``regions`` is the resolved monitor list from the database, supplied by the
    engine purely so each result can be labelled with a human-readable region
    name.  Region membership itself is derived from the records, so this
    function performs no database access of its own and takes no Session.
    """
    name_by_id = {r["region_id"]: r.get("name") for r in (regions or [])}

    if region_id is not None:
        region_ids = [region_id]
    else:
        region_ids = sorted({
            r.get("region_id") for r in records if r.get("region_id") is not None
        })

    results = {}
    for rid in region_ids:
        region_records = [r for r in records if r.get("region_id") == rid]
        if not region_records:
            continue

        region_name = name_by_id.get(rid) or f"Region {rid}"

        # Overall oxygen trend
        all_series = _prepare_time_series(records, rid, "all")
        oxygen_trend = _compute_trend(all_series)
        
        # Hypoxic fraction trend
        hypoxic_trend = _compute_hypoxic_trend(all_series)
        
        # By depth layer
        depth_trends = {}
        for layer in ["surface", "mid", "deep"]:
            layer_series = _prepare_time_series(records, rid, layer)
            depth_trends[layer] = _compute_trend(layer_series)
        
        results[rid] = {
            "region_id": rid,
            "region_name": region_name,
            "oxygen_trend": oxygen_trend,
            "hypoxic_trend": hypoxic_trend,
            "depth_trends": depth_trends,
            "n_samples": len(region_records),
            "n_timed_samples": len(all_series),
        }
    
    return {"regions": results}


def project_hypoxic_expansion(records: list[dict], region: dict, 
                               horizon_days: int = 30) -> dict:
    """Project hypoxic zone expansion/shrinkage over the next horizon_days.
    
    Uses the hypoxic fraction trend to project future extent.
    Returns PROJECTION with explicit uncertainty - NOT a forecast.
    """
    region_id = region["region_id"]
    region_name = region["name"]
    
    series = _prepare_time_series(records, region_id, "all")
    if len(series) < 10:
        return {
            "status": "INSUFFICIENT_DATA",
            "region": region_name,
            "horizon_days": horizon_days,
            "message": "Need at least 10 time points for projection",
            "projection": None,
            "uncertainty": "HIGH",
        }
    
    # Get hypoxic trend
    hypoxic_trend = _compute_hypoxic_trend(series)
    trend_direction = hypoxic_trend.get("direction", "stable")
    slope = hypoxic_trend.get("slope_per_year", 0)
    
    # Current hypoxic fraction (last 30 days)
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = [s for s in series if s["date"] > recent_cutoff]
    current_hypoxic_frac = sum(1 for s in recent if s["is_hypoxic"]) / len(recent) if recent else 0
    
    # Project forward
    horizon_years = horizon_days / 365.25
    projected_frac = current_hypoxic_frac + slope * horizon_years
    projected_frac = max(0.0, min(1.0, projected_frac))
    
    # Uncertainty bands (wider for longer horizons, less data)
    n_points = len(series)
    base_uncertainty = 0.2 / (n_points / 10) if n_points > 10 else 0.5
    horizon_factor = 1 + horizon_years  # Uncertainty grows with horizon
    uncertainty = base_uncertainty * horizon_factor
    
    lower_bound = max(0.0, projected_frac - uncertainty)
    upper_bound = min(1.0, projected_frac + uncertainty)
    
    # Determine if expansion is significant
    if projected_frac - current_hypoxic_frac > 0.1:
        change = "EXPANDING"
    elif current_hypoxic_frac - projected_frac > 0.1:
        change = "SHRINKING"
    else:
        change = "STABLE"
    
    # Convert fraction to approximate area (very rough)
    # Assuming region area ~ 50,000 km² for coastal zone
    region_area_km2 = 50000
    current_area = current_hypoxic_frac * region_area_km2
    projected_area = projected_frac * region_area_km2
    
    return {
        "status": "PROJECTION",
        "region": region_name,
        "region_id": region_id,
        "horizon_days": horizon_days,
        "current": {
            "hypoxic_fraction": round(current_hypoxic_frac, 3),
            "estimated_area_km2": round(current_area, 0),
            "sample_count": len(recent),
        },
        "projected": {
            "hypoxic_fraction": round(projected_frac, 3),
            "estimated_area_km2": round(projected_area, 0),
            "change": change,
            "change_magnitude": round(abs(projected_frac - current_hypoxic_frac), 3),
        },
        "uncertainty": {
            "level": "HIGH" if uncertainty > 0.3 else "MEDIUM" if uncertainty > 0.15 else "LOW",
            "lower_bound_fraction": round(lower_bound, 3),
            "upper_bound_fraction": round(upper_bound, 3),
            "lower_bound_area_km2": round(lower_bound * region_area_km2, 0),
            "upper_bound_area_km2": round(upper_bound * region_area_km2, 0),
            "note": "Projection based on linear trend of hypoxic fraction; "
                    "does not account for seasonal cycles, climate modes, or policy interventions.",
        },
        "trend_basis": hypoxic_trend,
        "confidence": round(max(0, 1 - uncertainty) * 100, 1),
        "disclaimer": "This is a statistical PROJECTION, not a forecast. "
                      "It assumes recent trends continue unchanged. "
                      "Actual conditions will vary with monsoon, upwelling, river discharge, and climate variability.",
    }