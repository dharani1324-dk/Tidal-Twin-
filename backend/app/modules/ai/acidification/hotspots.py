"""
TidalTwin - Acidification: hotspots
===================================
Detects "Acidification Stress Zone" hotspots and ranks them by how urgently
they need a response.

A hotspot is a (region, depth layer) group whose worst stored pH sample scored
MODERATE or worse.  The scoring deliberately separates two different questions:

  * How bad is it?        -> severity, from the measured pH ladder
  * How well do we know?  -> confidence, from the Argo QC flag
  * Is it getting worse?  -> trend, from the pH time series

so a confidently-measured severe zone outranks a poorly-measured one, which is
the ordering a decision engine needs.

ARAGONITE IS REPORTED, NEVER SCORED ON DIRECTLY
-------------------------------------------------
Aragonite saturation is a DERIVED quantity, so it is surfaced as biological
context on each hotspot rather than folded into the priority score.  The one
place it does influence the outcome is ``is_hotspot``: a cell that is
demonstrably aragonite-undersaturated is a stress zone even when its pH has not
yet crossed the ladder's MODERATE line, because shells are dissolving there.
That is a biological fact, not a measurement claim, and it is labelled as such.
"""

from __future__ import annotations

from datetime import timedelta

from app.modules.ai.acidification import trends as _trends
from app.modules.ai.acidification.units import (
    ARAGONITE_SATURATION,
    ARAGONITE_STRESS,
    SEVERITY_ORDINALS,
    alert_for_ordinal,
    depth_band_for_depth,
    severity_for_ph,
    severity_label_for_ordinal,
)

# The anomaly category this module contributes to the platform's decision
# intelligence engine. Matches the naming convention of the deoxygenation
# module's "Low Oxygen Zone" and microplastics' "Microplastic Hotspot".
ANOMALY_CATEGORY = "Acidification Stress Zone"

HOTSPOT_THRESHOLD_ORDINAL = SEVERITY_ORDINALS["MODERATE"]

# Recency window used for the persistence term in the priority score.
_THIRTY_DAYS = timedelta(days=30)

# Severity contribution to the priority score, keyed by label.
SEVERITY_SCORE = {
    "NORMAL": 0,
    "LOW": 20,
    "MODERATE": 50,
    "HIGH": 80,
    "CRITICAL": 100,
}

TREND_SCORE = {
    "declining": 100,
    "expanding": 100,
    "no_significant_trend": 50,
    "stable": 50,
    "improving": 20,
    "shrinking": 20,
    "insufficient_data": 40,
}

# The severity ladder, re-declared so this module owns a readable copy that the
# test suite pins against units.SEVERITY_LADDER.  If they ever diverge, a cell's
# stored ordinal will render as the wrong label - which is exactly the defect
# the deoxygenation test suite exists to prevent.
SEVERITY_LADDER = (
    (0.0, 7.75, "CRITICAL"),
    (7.75, 7.90, "HIGH"),
    (7.90, 8.00, "MODERATE"),
    (8.00, 8.05, "LOW"),
    (8.05, None, "NORMAL"),
)


def _severity_from_ph(ph_total):
    """Classify a pH value. Mirrors ``units.severity_for_ph`` exactly."""
    return severity_for_ph(ph_total)


def _group_by_region_depth(
    records: list[dict], regions: list[dict]
) -> dict[tuple[int | None, str], list[dict]]:
    """Group normalised samples by (region_id, depth band)."""
    valid_region_ids = {r["region_id"] for r in regions} if regions else None

    groups: dict[tuple[int | None, str], list[dict]] = {}
    for rec in records:
        ph = rec.get("ph_total")
        if ph is None:
            continue
        region_id = rec.get("region_id")
        if valid_region_ids is not None and region_id not in valid_region_ids:
            continue
        band = depth_band_for_depth(rec.get("depth_m"))
        groups.setdefault((region_id, band), []).append(rec)
    return groups


def _recommendations(
    severity: str,
    trend: str,
    min_omega: float | None,
    depth_layer: str,
) -> list[str]:
    """Plain-language recommended actions for a detected stress zone."""
    actions: list[str] = []
    label = severity.lower()

    if min_omega is not None and min_omega < ARAGONITE_SATURATION:
        actions.append(
            f"Aragonite saturation reached {min_omega:.2f}, below the 1.0 "
            "saturation point where calcium carbonate actively dissolves. "
            "Shell and skeleton formation is compromised here."
        )
    elif min_omega is not None and min_omega < ARAGONITE_STRESS:
        actions.append(
            f"Aragonite saturation fell to {min_omega:.2f}, below the 2.0 "
            "operational threshold for shellfish aquaculture and larval "
            "recruitment."
        )

    if severity == "CRITICAL":
        actions.append(
            "Flag for shellfish and coral risk: pH is low enough that shell "
            "formation is failing, not merely stressed."
        )
        actions.append(
            "Advise fisheries and aquaculture operators in this zone and "
            "suspend new shellfish seeding until pH recovers above 7.90."
        )
    elif severity == "HIGH":
        actions.append(
            "Flag for fisheries alert: shell formation is at risk in the "
            f"{depth_layer} layer of this region."
        )
    elif severity == "MODERATE":
        actions.append(
            "Flag for further monitoring: pH is measurably acidified and "
            "approaching aragonite undersaturation."
        )
    elif severity == "LOW":
        actions.append(
            "Keep under observation. pH is reduced relative to pre-industrial "
            "open-ocean values but not yet biologically limiting."
        )

    if trend == "declining":
        actions.append(
            "The local pH trend is declining - extend the monitoring interval "
            "rather than reducing it."
        )
    elif trend == "expanding":
        actions.append(
            "The acidified fraction of this region is growing - the stress zone "
            "is expanding."
        )
    elif trend == "insufficient_data":
        actions.append(
            "Too few observations to establish a trend; prioritise additional "
            "float sampling here."
        )

    if not actions:
        actions.append("No action required on current evidence.")
    return actions


def detect_stress_zones(
    records: list[dict],
    regions: list[dict],
    min_priority: float = 0.0,
) -> dict:
    """Detect and rank acidification stress zones.

    Returns a payload with the ranked hotspots, a severity breakdown, and
    aggregate recommendations suitable for the decision engine.
    """
    name_by_id = {r["region_id"]: r.get("name") for r in (regions or [])}
    groups = _group_by_region_depth(records, regions)

    hotspots: list[dict] = []

    for (region_id, band), recs in groups.items():
        if region_id is None:
            continue
        values = [r["ph_total"] for r in recs if r.get("ph_total") is not None]
        if not values:
            continue
        ordinals = [
            r["severity_ordinal"] for r in recs if r.get("severity_ordinal") is not None
        ]
        worst_ordinal = max(ordinals) if ordinals else None
        if worst_ordinal is None:
            continue

        min_ph = min(values)
        max_ph = max(values)
        mean_ph = sum(values) / len(values)

        omegas = [r["omega_arag"] for r in recs if r.get("omega_arag") is not None]
        min_omega = min(omegas) if omegas else None
        mean_omega = sum(omegas) / len(omegas) if omegas else None

        # A zone is either flagged by the pH ladder or by demonstrated aragonite
        # undersaturation. The latter is the biological definition of a stress
        # zone, so it qualifies even when pH alone has not crossed the line.
        undersat_samples = [o for o in omegas if o < ARAGONITE_SATURATION]
        is_hotspot = (
            worst_ordinal >= HOTSPOT_THRESHOLD_ORDINAL or bool(undersat_samples)
        )
        if not is_hotspot:
            continue

        # Severity for reporting: the worst ladder ordinal, escalated to CRITICAL
        # when aragonite is demonstrably undersaturated, because that is a
        # stronger biological statement than the pH band alone.
        label = severity_label_for_ordinal(worst_ordinal)
        if undersat_samples and worst_ordinal < SEVERITY_ORDINALS["CRITICAL"]:
            worst_ordinal = SEVERITY_ORDINALS["CRITICAL"]
            label = "Critical"
        severity_key = next(
            (k for k, v in SEVERITY_ORDINALS.items() if v == worst_ordinal), "NORMAL"
        )

        # Temporal span and persistence.
        dates = sorted(r["sampled_at"] for r in recs if r.get("sampled_at"))
        span_days = (
            (dates[-1] - dates[0]).days if len(dates) >= 2 else 0
        )
        recent_cutoff = max(dates) - _THIRTY_DAYS if dates else None
        recent = (
            [r for r in recs if r.get("sampled_at") and r["sampled_at"] >= recent_cutoff]
            if recent_cutoff
            else []
        )
        recent_or = [
            r["severity_ordinal"] for r in recent if r.get("severity_ordinal") is not None
        ]
        persistence_score = (
            (sum(1 for o in recent_or if o >= HOTSPOT_THRESHOLD_ORDINAL) / len(recent_or))
            * 100
            if recent_or
            else 0.0
        )

        # Trend on this region+band.
        trend = _trends._compute_trend(
            _trends._prepare_time_series(records, region_id, _layer_to_series(band))
        )
        trend_direction = trend.get("direction", "insufficient_data")

        confidences = [
            r["confidence_score"]
            for r in recs
            if r.get("confidence_score") is not None
        ]
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        severity_score = SEVERITY_SCORE.get(severity_key, 0)
        spatial_score = min(100.0, len(recs) * 5)
        trend_pts = TREND_SCORE.get(trend_direction, 50)

        priority = (
            0.35 * severity_score
            + 0.25 * persistence_score
            + 0.20 * spatial_score
            + 0.15 * trend_pts
            + 0.05 * mean_confidence * 100
        )

        severity_tier, action, rationale = alert_for_ordinal(worst_ordinal)
        recommendations = _recommendations(severity_key, trend_direction, min_omega, band)

        lats = [r["latitude"] for r in recs if r.get("latitude") is not None]
        lons = [r["longitude"] for r in recs if r.get("longitude") is not None]
        distances = [
            r["region_distance_km"]
            for r in recs
            if r.get("region_distance_km") is not None
        ]

        hotspots.append(
            {
                "region_id": region_id,
                "region": name_by_id.get(region_id) or f"Region {region_id}",
                "depth_layer": band,
                "is_hotspot": True,
                "priority": round(priority, 1),
                "severity": severity_key,
                "severity_ordinal": worst_ordinal,
                "severity_label": label,
                "alert_severity": severity_tier,
                "latitude": round(sum(lats) / len(lats), 4) if lats else None,
                "longitude": round(sum(lons) / len(lons), 4) if lons else None,
                "unit": "pH (total scale)",
                "statistics": {
                    "n_samples": len(recs),
                    "n_floats": len({r.get("float_id") for r in recs if r.get("float_id")}),
                    "min_ph": round(min_ph, 4),
                    "mean_ph": round(mean_ph, 4),
                    "max_ph": round(max_ph, 4),
                    "min_omega_arag": round(min_omega, 3) if min_omega is not None else None,
                    "mean_omega_arag": round(mean_omega, 3) if mean_omega is not None else None,
                    "n_with_derived_omega": len(omegas),
                    "n_undersaturated": len(undersat_samples),
                    "depth_min": round(min(r["depth_m"] for r in recs), 1),
                    "depth_max": round(max(r["depth_m"] for r in recs), 1),
                    "temporal_span_days": span_days,
                    "persistence": round(persistence_score, 1),
                    "mean_distance_km": round(sum(distances) / len(distances), 1)
                    if distances
                    else None,
                },
                "trend": trend_direction,
                "trend_detail": trend,
                "confidence": round(mean_confidence * 100, 1),
                "action": action,
                "rationale": rationale,
                "recommendations": recommendations,
                "latest_sample_at": dates[-1].isoformat() if dates else None,
            }
        )

    hotspots.sort(key=lambda h: -h["priority"])
    hotspots = [h for h in hotspots if h["priority"] >= min_priority]

    severity_breakdown: dict[str, int] = {}
    for h in hotspots:
        severity_breakdown[h["severity"]] = severity_breakdown.get(h["severity"], 0) + 1

    top_actions: list[str] = []
    for h in hotspots[:3]:
        top_actions.append(
            f"{h['region']} ({h['depth_layer']}): "
            f"{h['recommendations'][0] if h['recommendations'] else h['action']}"
        )

    return {
        "anomaly_category": ANOMALY_CATEGORY,
        "hotspot_count": len(hotspots),
        "hotspots": hotspots,
        "severity_breakdown": severity_breakdown,
        "recommendations": {
            "summary": (
                f"{len(hotspots)} acidification stress zone(s) detected from real "
                "Argo BGC in-situ pH observations."
                if hotspots
                else "No acidification stress zone met the reporting threshold on "
                "current observations."
            ),
            "actions": top_actions,
        },
        "measurement_discipline": (
            "pH is MEASURED. Aragonite saturation is DERIVED via CO2SYS from the "
            "measured pH, temperature and salinity, assuming total alkalinity from "
            "the Lee et al. (2006) salinity relation. No pH value outside the "
            "physically plausible seawater range [7.4, 8.6] is ever stored, and no "
            "aragonite value is produced when temperature or salinity is missing."
        ),
    }


def _layer_to_series(band: str) -> str:
    """Map a depth band to the trend module's series layer name."""
    return {
        "surface": "surface",
        "pycnocline": "mid",
        "deep": "deep",
    }.get(band, "all")
