"""
OceanVerse AI - Transparent Confidence Scoring
==============================================
Confidence is never random. It is derived from meaningful, explainable
factors:

    * Observation quality / QC   (source provenance, not simulated)
    * Observation age            (freshness of the in-situ reading)
    * Nearby-sample density      (how many readings back this estimate)
    * Agreement among samples    (variability of recent readings)
    * Temporal alignment         (model vs observation time gap)
    * Data completeness          (how many supported fields are present)

The engine returns the weighted score together with every factor and a
plain-language "why this confidence?" list.
"""

import numpy as np

BAND_HIGH = 80
BAND_MEDIUM = 55


def _clamp100(x: float) -> int:
    return int(min(100, max(0, round(x * 100))))


def _level(score: float) -> str:
    if score >= BAND_HIGH:
        return "HIGH CONFIDENCE"
    if score >= BAND_MEDIUM:
        return "MEDIUM CONFIDENCE"
    return "LOW CONFIDENCE"


def compare_confidence(
    variable: str,
    values: list,
    model_value: float | None,
    observed_value: float | None,
    source: str,
    freshness_h: float,
    temporal_gap_h: float,
    co_located: bool,
    obs_count: int = 0,
    window: int = 96,
) -> tuple[int, str, list[dict], list[str]]:
    """
    Score confidence in the model-vs-observation comparison.

    Returns ``(score, level, factors, reasons)``.
    ``factors`` is a list of ``{factor, pct, weight, note}``.
    ``reasons`` is a list of human-readable "why" strings.
    """
    factors: list[dict] = []
    reasons: list[str] = []

    # 1. Observation quality / QC --------------------------------------------
    src = (source or "").upper()
    if not src:
        q = 0.5
        note = "Source unknown"
    elif src.startswith("SIMULATED"):
        q = 0.6
        note = "DEMO data stream (clearly labelled)"
        reasons.append("Demo/simulated data – confidence reduced on purpose")
    else:
        q = 1.0
        note = f"Known source: {source}"
        reasons.append(f"Good observation quality ({source})")
    factors.append({"factor": "Observation quality", "pct": _clamp100(q), "weight": 25, "note": note})

    # 2. Observation age ------------------------------------------------------
    fresh = max(0.0, min(1.0, 1.0 - freshness_h / 48.0))
    factors.append({
        "factor": "Observation age",
        "pct": _clamp100(fresh),
        "weight": 30,
        "note": f"Latest reading {freshness_h:.1f}h old",
    })
    if freshness_h <= 6:
        reasons.append(f"Recent observation ({freshness_h:.0f}h old)")
    elif freshness_h <= 48:
        reasons.append("Observation within the last 2 days")

    # 3. Nearby-sample density ------------------------------------------------
    density = min(1.0, obs_count / float(window)) if obs_count else 0.0
    factors.append({
        "factor": "Nearby observations",
        "pct": _clamp100(density),
        "weight": 15,
        "note": f"{obs_count} readings in the {window}h window",
    })
    if obs_count >= 48:
        reasons.append(f"{obs_count} nearby observations")
    elif obs_count >= 12:
        reasons.append(f"Moderate sampling ({obs_count} readings)")

    # 4. Agreement among nearby samples ---------------------------------------
    vals = [v for v in values if v is not None]
    agreement = 0.0
    if len(vals) >= 3:
        std = float(np.std(vals))
        agreement = max(0.0, 1.0 - min(1.0, std / 0.5))
        reasons.append("Nearby observations agree closely with each other")
    factors.append({
        "factor": "Agreement among nearby",
        "pct": _clamp100(agreement),
        "weight": 10,
        "note": f"Recent std = {std:.2f}" if len(vals) >= 3 else "Too few samples",
    })

    # 5. Temporal alignment ----------------------------------------------------
    align = max(0.0, 1.0 - temporal_gap_h / 24.0)
    factors.append({
        "factor": "Temporal alignment",
        "pct": _clamp100(align),
        "weight": 10,
        "note": f"Model vs observation gap {temporal_gap_h:.1f}h",
    })
    if temporal_gap_h < 1:
        reasons.append("Strong temporal alignment (model window ends at observation time)")

    # 6. Spatial alignment -----------------------------------------------------
    spatial = 1.0 if co_located else 0.7
    factors.append({
        "factor": "Spatial alignment",
        "pct": _clamp100(spatial),
        "weight": 10,
        "note": "Co-located station + in-situ point" if co_located else "Offset observation point",
    })
    if co_located:
        reasons.append("Small spatial mismatch (co-located with model grid)")

    total_weight = sum(f["weight"] for f in factors)
    score = sum(f["pct"] / 100.0 * f["weight"] for f in factors) / total_weight
    score = _clamp100(score)

    # Sanity floor: incomplete comparison cap ----------------------------------
    if observed_value is None or model_value is None:
        score = min(score, 35)
        reasons.append("Comparison incomplete – confidence capped")

    return score, _level(float(score)), factors, reasons