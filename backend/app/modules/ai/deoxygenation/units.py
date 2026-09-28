"""
TidalTwin - Deoxygenation: units, the hypoxia ladder and the alert tiers
=========================================================================
This is the load-bearing honesty file of the dissolved-oxygen module.

UNITS
-----
Argo BGC floats publish ``DOXY`` in umol/kg and that number is stored verbatim.
The classic alternative unit, mg/L, is derived with the standard factor:

    1 umol O2/kg  =  32e-6 g O2/kg  ~  0.032 mg O2/L

because seawater has a density close to 1 kg/L.  The derivation is an
approximation and is labelled as such; we never transform the stored umol/kg.

THE SEVERITY LADDER IS A DOCUMENTED POLICY CLASSIFIER
-----------------------------------------------------
Hypoxia is conventionally defined as dissolved oxygen below ~2 mg/L
(~62.5 umol/kg).  Around that anchor we define five bands so samples can be
colour-coded and ranked on ONE scale - dissolved oxygen, unlike microplastics,
has a single physical medium, so a single ladder is legitimate:

    mg/L         label      ordinal
    >= 2.0       NORMAL     0
    1.5 - 2.0    LOW        1      (near-hypoxic)
    1.0 - 1.5    MODERATE   2      (hypoxic)
    0.5 - 1.0    HIGH       3      (severely hypoxic)
    < 0.5        CRITICAL   4      (near anoxic / OMZ core)

``is_hypoxic`` is true below 2.0 mg/L; ``is_dead_zone`` below 0.5 mg/L.
"""

from __future__ import annotations

# Canonical + derived unit strings.
UNIT_UMOL_KG = "umol/kg"
UNIT_MG_L = "mg/L"

# 1 umol O2/kg ~ 0.032 mg O2/L (density ~1 kg/L).
MOLAR_MASS_O2_G_PER_MOL = 32.0
UMOL_KG_TO_MG_L_FACTOR = MOLAR_MASS_O2_G_PER_MOL / 1e6 * 1e3  # 0.032

# Conventional hypoxia anchors.
HYPOXIC_THRESHOLD_MG_L = 2.0
DEAD_ZONE_THRESHOLD_MG_L = 0.5

# Severity ordinals are 1-based and run NORMAL(1) -> CRITICAL(5).
# 1-based (rather than 0-based) so that "no classification" is None instead of
# colliding with NORMAL=0. These are the values persisted in
# dissolved_oxygen_samples.severity_ordinal; changing the scale would silently
# re-rank every stored row.
SEVERITY_ORDINALS = {
    "NORMAL": 1,
    "LOW": 2,
    "MODERATE": 3,
    "HIGH": 4,
    "CRITICAL": 5,
}

SEVERITY_LABEL_DISPLAY = {
    "NORMAL": "Normal",
    "LOW": "Low",
    "MODERATE": "Moderate",
    "HIGH": "High",
    "CRITICAL": "Critical",
}

# Inverse of SEVERITY_ORDINALS, for rendering a stored ordinal back to a label.
# Consumers that only hold an ordinal (the zone grid aggregates the worst
# ordinal in a cell) must use this - reading SEVERITY_ORDINALS with an ordinal
# key silently yields None because that dict is keyed by label.
SEVERITY_ORDINAL_TO_LABEL: dict[int, str] = {
    ordinal: label for label, ordinal in SEVERITY_ORDINALS.items()
}


def severity_label_for_ordinal(ordinal: int | None) -> str:
    """Display label for a severity ordinal, never a misleading default.

    An unknown ordinal is reported as "Unknown" rather than "Normal": quietly
    labelling an unclassified cell as normal would understate a dead zone.
    """
    if ordinal is None:
        return "Unknown"
    label = SEVERITY_ORDINAL_TO_LABEL.get(ordinal)
    if label is None:
        return "Unknown"
    return SEVERITY_LABEL_DISPLAY.get(label, label)

# (low_inclusive_mg_l, high_exclusive_or_None_mg_l, label)
# Breakpoints follow the standard oceanographic anchors and must stay identical
# to hotspots.SEVERITY_LADDER / the classifier used at ingest:
#   < 0.5  CRITICAL  dead zone / near-anoxia
#   < 2.0  HIGH      hypoxic
#   < 4.0  MODERATE
#   < 6.0  LOW
#   >= 6.0 NORMAL
SEVERITY_LADDER: tuple[tuple[float, float | None, str], ...] = (
    (0.0, 0.5, "CRITICAL"),
    (0.5, 2.0, "HIGH"),
    (2.0, 4.0, "MODERATE"),
    (4.0, 6.0, "LOW"),
    (6.0, None, "NORMAL"),
)

# Depth bands used by the depth-layer and trend views.
DEPTH_BANDS = (
    ("surface", 0.0, 30.0, "Surface (0-30 m)"),
    ("pycnocline", 30.0, 200.0, "Pycnocline (30-200 m)"),
    ("deep", 200.0, 20000.0, "Deep (>200 m)"),
)


def umol_kg_to_mg_l(umol_kg: float | None) -> float | None:
    """Convert umol/kg to mg/L with the labelled density approximation."""
    if umol_kg is None:
        return None
    return umol_kg * UMOL_KG_TO_MG_L_FACTOR


def severity_for_mg_l(mg_l: float | None) -> tuple[str | None, int | None, bool, bool]:
    """Resolve a mg/L value into (label, ordinal, is_hypoxic, is_dead_zone).

    ``mg_l`` of ``None`` (no measured value) yields all-``None``/``False``
    rather than guessing a classification.
    """
    if mg_l is None:
        return None, None, False, False
    for low, high, label in SEVERITY_LADDER:
        if mg_l >= low and (high is None or mg_l < high):
            ordinal = SEVERITY_ORDINALS[label]
            return (
                label,
                ordinal,
                mg_l < HYPOXIC_THRESHOLD_MG_L,
                mg_l < DEAD_ZONE_THRESHOLD_MG_L,
            )
    return None, None, False, False


# --------------------------------------------------------------------------
# Alert tiers - our policy layer on top of the hypoxia science, mirroring the
# microplastics module's ALERT_TIER_RULES shape.
# --------------------------------------------------------------------------
ALERT_TIER_RULES = (
    (5, "critical", "IMMEDIATE_INVESTIGATION",
     "Oxygen below 0.5 mg/L - near-anoxic core, treat as a dead-zone event."),
    (4, "high", "PRIORITY_SURVEY",
     "Oxygen between 0.5 and 2.0 mg/L - hypoxic water, severely depleted."),
    (3, "medium", "REPEAT_MONITORING",
     "Oxygen between 2.0 and 4.0 mg/L - low oxygen, below the hypoxia threshold."),
    (2, "low", "MONITOR",
     "Oxygen between 4.0 and 6.0 mg/L - moderately depleted, keep watching."),
    (1, "info", "NONE",
     "Oxygen at or above 6.0 mg/L - normal conditions."),
)


def alert_for_ordinal(ordinal: int | None) -> tuple[str, str, str]:
    """Map a severity ordinal to (severity, action, rationale)."""
    if ordinal is None:
        return "unknown", "INSUFFICIENT_BASIS", "No measured oxygen value."
    for threshold, severity, action, rationale in ALERT_TIER_RULES:
        if ordinal >= threshold:
            return severity, action, rationale
    return "unknown", "INSUFFICIENT_BASIS", "Ordinal outside the known ladder."


def depth_band_for_depth(depth_m: float | None) -> str:
    """Which depth band a sample belongs to."""
    if depth_m is None:
        return "deep"
    for key, low, high, _label in DEPTH_BANDS:
        if low <= depth_m < high:
            return key
    return "deep"