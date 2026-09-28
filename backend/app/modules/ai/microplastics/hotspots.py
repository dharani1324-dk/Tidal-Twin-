"""
TidalTwin - Microplastics: hotspot detection and decision output
================================================================
Turns normalised samples into the thing a decision-maker can act on: which
region has a microplastic problem, how strong the evidence is, and what to do
about it.  Every hotspot is emitted with ``anomaly_category =
"Microplastic Hotspot"`` so it can be consumed as a new anomaly class by the
platform's decision-intelligence layer alongside thermal and wave anomalies.

THE VINTAGE PROBLEM - READ THIS BEFORE TRUSTING A NUMBER HERE
-------------------------------------------------------------
The NOAA NCEI collection is an *archive*, not a live feed.  Inside the Indian
Ocean window its records span 2013-06 to 2021-12.  Ranking regions by how
"recent" a sample is relative to today would mark every region equally stale
and produce a meaningless uniform penalty.

So recency is measured against **the newest sample in the collection itself**,
and the basis is stated in the payload.  A hotspot therefore means "this is the
most recent evidence we have", never "this was measured today".  The API
surfaces ``data_vintage`` next to every hotspot so the UI is obliged to show it.

PRIORITY SCORE (fully transparent, no fitted weights)
-----------------------------------------------------
    priority = 100 x ( 0.55*severity + 0.10*evidence + 0.15*recency + 0.20*trust )

    severity  = published class ordinal / 4          (0..1)
    evidence  = min(1, n_samples / 10)               (0..1)
    recency   = 0.5 ** (age_years / 3)               half-life of 3 years
    trust     = mean sample confidence / 100         (0..1)

``severity`` dominates because the source's own classification is the strongest
signal available, and the weights are set so that **one class band outranks up
to ten times the sample count**: a single region with a ``High`` sample beats a
region with ten ``Medium`` samples.  That is deliberate - the class already
encodes concentration, so ten samples of a weaker class are ten repetitions of
a lesser signal, not a stronger one.

Evidence is deliberately the smallest weight because a sample count is not a
magnitude.  What a thin sample base actually undermines is *confidence*, so it
is reported there (``confidence``, plus the ``basis`` caveats) instead of being
allowed to inflate or bury the severity signal.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.modules.ai.microplastics.units import (
    FAMILY_DESCRIPTIONS,
    FAMILY_UNKNOWN,
    MEDIUM_BEACH,
    MEDIUM_SEDIMENT,
    MEDIUM_UNKNOWN,
    MEDIUM_WATER,
    SEVERITY_LABELS_BY_ORDINAL,
    alert_for_ordinal,
)

ANOMALY_CATEGORY = "Microplastic Hotspot"

PRIORITY_WEIGHTS = {
    "severity": 0.55,
    "evidence": 0.10,
    "recency": 0.15,
    "trust": 0.20,
}

RECENCY_HALF_LIFE_YEARS = 3.0
EVIDENCE_SATURATION_SAMPLES = 10

# Minimum ordinal that counts as a hotspot.  Ordinal 2 == the source's own
# "Medium" class.  Below that we report the region but do not raise it.
HOTSPOT_MIN_ORDINAL = 2

MEDIUM_DISPLAY = {
    MEDIUM_WATER: "Water column",
    MEDIUM_SEDIMENT: "Ocean sediment",
    MEDIUM_BEACH: "Beach",
    "beach_nurdle": "Beach (nurdle patrol)",
    MEDIUM_UNKNOWN: "Unknown medium",
}


def _mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _median(values: list[float]) -> float | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def _percentile(values: list[float], fraction: float) -> float | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    index = max(0, min(len(clean) - 1, int(round(fraction * (len(clean) - 1)))))
    return clean[index]


def collection_vintage(records: list[dict]) -> dict:
    """Newest and oldest sample dates across a record set.

    Everything downstream measures staleness against ``latest`` here, not
    against wall-clock now, and the returned ``basis`` says so out loud.
    """
    dated = [
        ts if ts.tzinfo is None else ts.astimezone(timezone.utc)
        for ts in (r.get("timestamp") for r in records)
        if ts is not None
    ]
    if not dated:
        return {
            "latest": None,
            "oldest": None,
            "span_years": None,
            "basis": (
                "No sample in this set publishes a date, so no recency signal "
                "could be computed."
            ),
            "is_live_feed": False,
        }

    latest = max(dated)
    oldest = min(dated)
    span_years = round((latest - oldest).days / 365.25, 2)
    return {
        "latest": latest.isoformat(),
        "oldest": oldest.isoformat(),
        "span_years": span_years,
        "basis": (
            "Recency is measured against the newest sample in the source "
            "collection, not against the current date. The NOAA NCEI "
            "microplastics collection is an archive, not a live feed."
        ),
        "is_live_feed": False,
        "age_of_newest_sample_days": (datetime.now(timezone.utc) - latest).days,
    }


def _recency_factor(latest_sample, collection_latest, half_life: float = RECENCY_HALF_LIFE_YEARS) -> float | None:
    if latest_sample is None or collection_latest is None:
        return None
    if latest_sample >= collection_latest:
        return 1.0
    age_years = (collection_latest - latest_sample).days / 365.25
    return round(0.5 ** (age_years / half_life), 4)


def group_samples(records: list[dict]) -> dict[tuple, list[dict]]:
    """Group by ``(region_id, medium)``.

    Grouping by medium rather than unit family matters: beach samples and
    water-column samples share the unit ``pieces/m3`` but are classified on
    different ladders, so they must never share a group.
    """
    groups: dict[tuple, list[dict]] = {}
    for record in records:
        region_id = record.get("region_id")
        if region_id is None:
            continue
        medium = record.get("medium") or MEDIUM_UNKNOWN
        groups.setdefault((region_id, medium), []).append(record)
    return groups


def score_group(
    region: dict,
    medium: str,
    samples: list[dict],
    collection_latest=None,
) -> dict:
    """Build one hotspot record from a homogeneous group of samples."""
    family = samples[0].get("unit_family", FAMILY_UNKNOWN)
    canonical_unit = samples[0].get("canonical_unit")

    values = [
        s["canonical_value"] if s.get("canonical_value") is not None else s.get("measured_value")
        for s in samples
    ]
    values = [v for v in values if v is not None]

    ordinals = [s["severity_ordinal"] for s in samples if s.get("severity_ordinal") is not None]
    worst_ordinal = max(ordinals) if ordinals else None
    median_ordinal = _median(ordinals)

    # Severity comes from the WORST sample, not the latest one.  Report both
    # classes explicitly: a group whose newest sample is 'Medium' while an older
    # one reached 'Very High' would otherwise read as a contradiction.
    worst_record = next(
        (s for s in samples if s.get("severity_ordinal") == worst_ordinal), None
    )
    worst_published_class = worst_record.get("published_class") if worst_record else None
    worst_sample_at = worst_record.get("timestamp") if worst_record else None

    latest_sample = max(
        (s["timestamp"] for s in samples if s.get("timestamp") is not None),
        default=None,
    )
    latest_record = next(
        (s for s in samples if s.get("timestamp") == latest_sample), samples[0]
    )

    confidence_mean = _mean([s.get("confidence_score") for s in samples]) or 0.0
    factor = _recency_factor(latest_sample, collection_latest)

    # ---- transparent priority ------------------------------------------
    severity_component = (worst_ordinal / 4.0) if worst_ordinal is not None else 0.0
    evidence_component = min(1.0, len(samples) / EVIDENCE_SATURATION_SAMPLES)
    recency_component = factor if factor is not None else 0.0
    trust_component = confidence_mean / 100.0

    priority = round(
        100.0 * (
            PRIORITY_WEIGHTS["severity"] * severity_component
            + PRIORITY_WEIGHTS["evidence"] * evidence_component
            + PRIORITY_WEIGHTS["recency"] * recency_component
            + PRIORITY_WEIGHTS["trust"] * trust_component
        ),
        1,
    )

    severity, action, rationale = alert_for_ordinal(worst_ordinal)
    is_hotspot = worst_ordinal is not None and worst_ordinal >= HOTSPOT_MIN_ORDINAL

    # ---- evidence-strength caveat --------------------------------------
    basis_notes: list[str] = []
    if len(samples) == 1:
        basis_notes.append(
            "Single published sample - this is a point observation, not a "
            "spatial pattern."
        )
    if len(samples) < 5:
        basis_notes.append(
            f"Only {len(samples)} sample(s) in this region and medium; "
            "the statistic is thin."
        )
    if latest_sample is not None and collection_latest is not None:
        age_years = (collection_latest - latest_sample).days / 365.25
        basis_notes.append(
            f"Newest sample for this group is {age_years:.1f} year(s) behind "
            "the newest sample in the collection."
            if age_years > 0.5
            else "Newest sample in this group is the most recent in the collection."
        )

    return {
        "anomaly_category": ANOMALY_CATEGORY,
        "hotspot_id": f"mp-{region['region_id']}-{medium}",
        "region_id": region["region_id"],
        "region": region["name"],
        "region_type": region.get("region_type"),
        "latitude": region["latitude"],
        "longitude": region["longitude"],
        "medium": medium,
        "medium_display": MEDIUM_DISPLAY.get(medium, medium),
        "unit_family": family,
        "unit_family_description": FAMILY_DESCRIPTIONS.get(family),
        "unit": canonical_unit or "native unit only",
        "is_hotspot": is_hotspot,
        "severity": severity,
        "severity_label": SEVERITY_LABELS_BY_ORDINAL.get(worst_ordinal),
        "severity_ordinal": worst_ordinal,
        "median_severity_ordinal": median_ordinal,
        # Severity is driven by the worst sample; say which class that was.
        "published_class": worst_published_class,
        "published_class_range": worst_record.get("published_class_range") if worst_record else None,
        "severity_basis": (
            "worst published class across the group" if worst_record else
            "no sample in this group carried a published class"
        ),
        "worst_sample_at": worst_sample_at.isoformat() if worst_sample_at else None,
        # ...while the newest sample is reported separately so "latest" and
        # "worst" cannot be confused for one another.
        "latest_published_class": latest_record.get("published_class"),
        "latest_severity_label": latest_record.get("severity_label"),
        "action": action,
        "action_rationale": rationale,
        "priority": priority,
        "priority_components": {
            "severity": round(severity_component, 4),
            "evidence": round(evidence_component, 4),
            "recency": round(recency_component, 4),
            "trust": round(trust_component, 4),
            "weights": PRIORITY_WEIGHTS,
        },
        "statistics": {
            "n_samples": len(samples),
            "median": round(_median(values), 6) if _median(values) is not None else None,
            "mean": round(_mean(values), 6) if _mean(values) is not None else None,
            "max": round(max(values), 6) if values else None,
            "min": round(min(values), 6) if values else None,
            "p90": round(_percentile(values, 0.9), 6) if _percentile(values, 0.9) is not None else None,
        },
        "latest_sample_at": latest_sample.isoformat() if latest_sample else None,
        "confidence": round(confidence_mean, 1),
        "basis": basis_notes,
        "origin_status": "REAL",
        "mapping": {
            # How far the contributing samples sat from the region centroid.
            "mean_distance_km": round(
                _mean([s.get("region_distance_km") for s in samples]) or 0.0, 2
            ),
            "max_distance_km": round(
                max(
                    (s.get("region_distance_km") for s in samples
                     if s.get("region_distance_km") is not None),
                    default=0.0,
                ),
                2,
            ),
        },
    }


def detect_hotspots(
    records: list[dict],
    regions: list[dict],
    min_priority: float = 0.0,
) -> dict:
    """Rank every (region, medium) group by priority and recommend actions."""
    region_index = {r["region_id"]: r for r in regions}
    vintage = collection_vintage(records)
    collection_latest = (
        datetime.fromisoformat(vintage["latest"]) if vintage["latest"] else None
    )

    hotspots: list[dict] = []
    for (region_id, medium), samples in group_samples(records).items():
        region = region_index.get(region_id)
        if region is None:
            continue
        scored = score_group(region, medium, samples, collection_latest=collection_latest)
        if scored["priority"] >= min_priority:
            hotspots.append(scored)

    hotspots.sort(key=lambda h: -h["priority"])

    live = [h for h in hotspots if h["is_hotspot"]]
    return {
        "anomaly_category": ANOMALY_CATEGORY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithm_version": "1.0",
        "threshold_note": (
            "A group becomes a Microplastic Hotspot at the source's own 'Medium' "
            "class or above. NOAA's class bands are unit-specific, so a hotspot "
            "is always reported per medium and never on a blended scale."
        ),
        "weights": PRIORITY_WEIGHTS,
        "data_vintage": vintage,
        "hotspot_count": len(live),
        "groups_evaluated": len(hotspots),
        "hotspots": hotspots,
        "recommendations": build_recommendations(live),
    }


# --------------------------------------------------------------------------
# Decision output
# --------------------------------------------------------------------------
def build_recommendations(hotspots: list[dict]) -> dict:
    """Plain-language actions for the decision-intelligence layer.

    Returns the same shape the rest of the platform's engines use: a summary
    sentence plus a ranked action list, so it can be dropped straight into a
    briefing without a translation layer.
    """
    actions: list[dict] = []

    for hotspot in hotspots:
        region = hotspot["region"]
        medium_label = hotspot["medium_display"].lower()
        unit = hotspot["unit"]
        stats = hotspot["statistics"]
        worst = (
            f"{stats['max']:g} {unit}" if stats.get("max") is not None else "an unquantified value"
        )
        class_label = hotspot.get("published_class") or hotspot.get("severity_label") or "unclassified"

        if hotspot["action"] == "CLEANUP_PRIORITY":
            headline = f"Prioritise a removal survey off {region}"
            detail = (
                f"{medium_label.capitalize()} samples at {region} reach the source's "
                f"'{class_label}' class, peaking at {worst} across "
                f"{stats['n_samples']} sample(s). Schedule a cleanup assessment and "
                "re-sample to confirm the extent before committing resources."
            )
        elif hotspot["action"] == "FURTHER_SAMPLING":
            headline = f"Re-sample {region} before acting"
            detail = (
                f"{medium_label.capitalize()} at {region} sits in the source's "
                f"'{class_label}' class (peak {worst}, {stats['n_samples']} sample(s)). "
                "Above background but too thin to justify intervention on its own - "
                "a repeat transect would firm it up."
            )
        elif hotspot["action"] == "POLICY_ALERT":
            headline = f"Raise a policy flag for {region}"
            detail = (
                f"{region} shows persistent microplastic loading in {medium_label} "
                f"(peak {worst}). Feed this into the regional discharge and riverine "
                "input review rather than treating it as a one-off cleanup."
            )
        else:
            headline = f"Keep monitoring {region}"
            detail = (
                f"{region} is classified '{class_label}' in {medium_label} "
                f"(peak {worst}). Below the intervention trigger; include it in the "
                "routine sampling cycle."
            )

        actions.append({
            "region_id": hotspot["region_id"],
            "region": region,
            "headline": headline,
            "detail": detail,
            "action": hotspot["action"],
            "severity": hotspot["severity"],
            "priority": hotspot["priority"],
            "medium": hotspot["medium"],
            "unit": unit,
            "evidence": f"{stats['n_samples']} published sample(s), "
                        f"newest {str(hotspot['latest_sample_at'])[:10]}",
            "anomaly_category": ANOMALY_CATEGORY,
            "confidence": hotspot["confidence"],
        })

    if not actions:
        summary = (
            "No monitored region currently reaches the source's 'Medium' "
            "microplastic class in any sampled medium. That is an honest reading "
            "of sparse evidence, not a clean bill of health."
        )
    else:
        top = actions[0]
        # The headline is used verbatim rather than lower-cased into the
        # sentence: lower-casing it mangles proper nouns like "Gulf of Mannar".
        summary = (
            f"{len(actions)} region/medium group(s) classify at or above 'Medium'. "
            f"Highest priority is **{top['region']}** ({top['medium']}) at "
            f"{top['priority']:.0f}/100 \u2014 {top['headline']}."
        )

    return {
        "engine": "Microplastics Decision Output",
        "algorithm_version": "1.0",
        "summary": summary,
        "action_count": len(actions),
        "actions": actions,
    }
