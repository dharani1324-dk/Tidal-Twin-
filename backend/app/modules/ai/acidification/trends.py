"""
TidalTwin - Acidification: trends
==================================
Analyzes historical pH time series per region to detect acidification trends
and project them forward over weeks to months.

Uses simple linear regression on regional aggregates with explicit uncertainty.
Every projection is labelled PROJECTION, never forecast.

AN IMPORTANT CAVEAT, STATED UP FRONT
-------------------------------------
Ocean acidification is a DECADAL process.  The global surface ocean pH has
fallen roughly 0.1 units since the industrial era, which is about 0.004 pH
units per year.  A float sampling a 500 km box every few days cannot resolve a
signal that small over a one-year window, and any "trend" it does show is
overwhelmingly seasonal and spatial - the monsoon, upwelling and river plume
dynamics that move Indian Ocean surface pH by +/-0.3 units between seasons.

So this module reports the measured slope AND its p-value, and the projection
refuses to claim a direction when the regression is not significant.  A
declining pH slope over a few months is presented as what it is: an observation
that needs more data, not a prediction of the century's ocean.
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


def _prepare_time_series(
    records: list[dict], region_id: int, depth_layer: str = "all"
) -> list[dict]:
    """Extract and sort time series for a region/depth layer."""

    def depth_match(d):
        if depth_layer == "surface":
            return d <= 30
        elif depth_layer == "mid":
            return 30 < d <= 200
        elif depth_layer == "deep":
            return d > 200
        return True

    series = []
    for r in records:
        if r.get("region_id") != region_id:
            continue
        ph = _finite(r.get("ph_total"))
        if ph is None:
            continue
        if r.get("sampled_at") is None:
            continue
        depth = _finite(r.get("depth_m"))
        if depth is None or not depth_match(depth):
            continue
        series.append(
            {
                "date": r["sampled_at"],
                "ph_total": ph,
                "omega_arag": _finite(r.get("omega_arag")),
                "severity_ordinal": r.get("severity_ordinal"),
                "is_acidic": r.get("is_acidic", 0),
                "is_undersaturated": r.get("is_undersaturated", 0),
                "confidence": r.get("confidence_score", 0.5),
            }
        )

    series.sort(key=lambda x: x["date"])
    return series


def _compute_trend(series: list[dict], min_points: int = 5) -> dict:
    """Compute linear trend on a pH time series.

    Returns trend info: slope in pH units per year, direction, significance.
    """
    if len(series) < min_points:
        return {
            "direction": "insufficient_data",
            "slope_ph_per_year": None,
            "r_squared": None,
            "p_value": None,
            "n_points": len(series),
            "note": f"Need at least {min_points} time points for trend analysis",
        }

    dates = [s["date"] for s in series]
    values = [s["ph_total"] for s in series]

    t0 = dates[0]
    x = [(d - t0).days / 365.25 for d in dates]
    y = values

    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(x[i] * y[i] for i in range(n))
    sum_x2 = sum(xi * xi for xi in x)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return {
            "direction": "flat",
            "slope_ph_per_year": 0.0,
            "r_squared": 0.0,
            "n_points": n,
        }

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    y_pred = [intercept + slope * xi for xi in x]
    ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
    ss_tot = sum((yi - sum_y / n) ** 2 for yi in y)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    if n > 2:
        import math

        mse = ss_res / (n - 2)
        se_slope = (mse / sum((xi - sum_x / n) ** 2 for xi in x)) ** 0.5
        t_stat = slope / se_slope if se_slope > 0 else 0.0
        p_value = 2 * (
            1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2)))
        )
    else:
        p_value = 1.0

    # Direction. The significant-slope threshold is 0.002 pH units/year: below
    # the decadal anthropogenic signal itself, so anything smaller is treated as
    # noise rather than reported as a trend.
    if p_value < 0.1:
        if slope < -0.002:
            direction = "declining"
        elif slope > 0.002:
            direction = "improving"
        else:
            direction = "stable"
    else:
        direction = "no_significant_trend"

    return {
        "direction": direction,
        "slope_ph_per_year": round(slope, 5),
        "intercept_ph": round(intercept, 4),
        "r_squared": round(r_squared, 3),
        "p_value": round(p_value, 3),
        "n_points": n,
        "time_span_years": round(x[-1] - x[0], 2) if x else 0,
    }


def _compute_acidic_trend(series: list[dict]) -> dict:
    """Compute trend specifically on the acidic-sample fraction over time."""
    if len(series) < 3:
        return {"direction": "insufficient_data"}

    yearly = defaultdict(list)
    for s in series:
        year = s["date"].year
        yearly[year].append(s)

    years = sorted(yearly.keys())
    if len(years) < 3:
        return {"direction": "insufficient_data"}

    acidic_fractions = []
    for year in years:
        year_samples = yearly[year]
        acidic = sum(1 for s in year_samples if s["is_acidic"])
        acidic_fractions.append(acidic / len(year_samples))

    x = list(range(len(years)))
    y = acidic_fractions
    n = len(x)

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(x[i] * y[i] for i in range(n))
    sum_x2 = sum(xi * xi for xi in x)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return {"direction": "stable", "slope_per_year": 0.0}

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
        "acidic_fractions": [round(f, 2) for f in acidic_fractions],
    }


def analyze_trends(
    records: list[dict],
    region_id: int | None = None,
    regions: list[dict] | None = None,
) -> dict:
    """Analyze pH trends for all regions or one specific region.

    ``regions`` is the resolved monitor list from the database, supplied by the
    engine purely so each result can be labelled with a human-readable region
    name.  Region membership itself is derived from the records, so this
    function performs no database access of its own and takes no Session.
    """
    name_by_id = {r["region_id"]: r.get("name") for r in (regions or [])}

    if region_id is not None:
        region_ids = [region_id]
    else:
        region_ids = sorted(
            {r.get("region_id") for r in records if r.get("region_id") is not None}
        )

    results = {}
    for rid in region_ids:
        region_records = [r for r in records if r.get("region_id") == rid]
        if not region_records:
            continue

        region_name = name_by_id.get(rid) or f"Region {rid}"

        all_series = _prepare_time_series(records, rid, "all")
        ph_trend = _compute_trend(all_series)
        acidic_trend = _compute_acidic_trend(all_series)

        depth_trends = {}
        for layer in ["surface", "mid", "deep"]:
            layer_series = _prepare_time_series(records, rid, layer)
            depth_trends[layer] = _compute_trend(layer_series)

        current = [s for s in all_series if s["date"]]
        latest = current[-1] if current else None

        results[rid] = {
            "region_id": rid,
            "region_name": region_name,
            "ph_trend": ph_trend,
            "acidic_trend": acidic_trend,
            "depth_trends": depth_trends,
            "current": {
                "ph_total": latest["ph_total"] if latest else None,
                "omega_arag": latest["omega_arag"] if latest else None,
                "sampled_at": latest["date"].isoformat() if latest else None,
            },
            "n_samples": len(region_records),
            "n_timed_samples": len(all_series),
        }

    return {"regions": results}


def project_ph_decline(
    records: list[dict], region: dict, horizon_days: int = 180
) -> dict:
    """Project regional pH over the next ``horizon_days``.

    Uses the measured pH slope to project forward.  Returns PROJECTION with
    explicit uncertainty - NOT a forecast.
    """
    region_id = region["region_id"]
    region_name = region["name"]

    series = _prepare_time_series(records, region_id, "all")
    if len(series) < 10:
        return {
            "status": "INSUFFICIENT_DATA",
            "region": region_name,
            "region_id": region_id,
            "horizon_days": horizon_days,
            "message": (
                f"Need at least 10 time points for a projection; this region has "
                f"{len(series)}"
            ),
            "projection": None,
            "uncertainty": "HIGH",
        }

    trend = _compute_trend(series)
    slope = trend.get("slope_ph_per_year") or 0.0

    # Current state: the most recent 30 days of observations.
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = [s for s in series if s["date"] > recent_cutoff]
    if not recent:
        recent = series[-5:]
    current_ph = sum(s["ph_total"] for s in recent) / len(recent)
    current_omegas = [s["omega_arag"] for s in recent if s["omega_arag"] is not None]
    current_omega = (
        sum(current_omegas) / len(current_omegas) if current_omegas else None
    )
    current_acidic_frac = sum(1 for s in recent if s["is_acidic"]) / len(recent)

    horizon_years = horizon_days / 365.25
    projected_ph = current_ph + slope * horizon_years

    # Uncertainty widens with the horizon and narrows with more data. Floored
    # at 0.02 pH units, which is the measurement resolution of the sensor
    # itself - no projection is ever more precise than the instrument.
    n_points = len(series)
    residual = 0.05 / (n_points / 10) if n_points > 10 else 0.2
    uncertainty = max(0.02, residual * (1 + horizon_years))

    lower_bound = projected_ph - uncertainty
    upper_bound = projected_ph + uncertainty

    significant = trend.get("p_value") is not None and trend["p_value"] < 0.1
    if not significant:
        change = "INDETERMINATE"
    elif projected_ph < current_ph - 0.01:
        change = "DECLINING"
    elif projected_ph > current_ph + 0.01:
        change = "RECOVERING"
    else:
        change = "STABLE"

    return {
        "status": "PROJECTION",
        "region": region_name,
        "region_id": region_id,
        "horizon_days": horizon_days,
        "current": {
            "ph_total": round(current_ph, 4),
            "omega_arag": round(current_omega, 3) if current_omega else None,
            "acidic_fraction": round(current_acidic_frac, 3),
            "sample_count": len(recent),
        },
        "projected": {
            "ph_total": round(projected_ph, 4),
            "change": change,
            "change_magnitude": round(abs(projected_ph - current_ph), 4),
        },
        "uncertainty": {
            "level": (
                "HIGH"
                if uncertainty > 0.1
                else "MEDIUM"
                if uncertainty > 0.05
                else "LOW"
            ),
            "lower_bound_ph": round(lower_bound, 4),
            "upper_bound_ph": round(upper_bound, 4),
            "note": (
                "Projection from a linear fit to observed pH. Ocean "
                "acidification is a decadal process and a float network cannot "
                "resolve the underlying signal over a short window, so short-term "
                "movement here is dominated by monsoon, upwelling and river-plume "
                "seasonality rather than by the long-term trend."
            ),
        },
        "trend_basis": trend,
        "significant": significant,
        "confidence": round(max(0.0, 1 - uncertainty / 0.5) * 100, 1),
        "disclaimer": (
            "This is a statistical PROJECTION, not a forecast. It assumes the "
            "observed local trend continues unchanged and does not model the "
            "anthropogenic carbon trajectory."
        ),
    }
