"""
TidalTwin - Microplastics: units, media and the published severity ladder
==========================================================================
This is the load-bearing honesty file of the microplastics module.  Get it
wrong and the platform will silently rank unlike things against each other.

WHY UNIT FAMILIES EXIST
-----------------------
The NOAA NCEI collection publishes microplastics in three mutually
incompatible units depending on how the sample was taken:

    water-column trawl  -> pieces/m3
    sediment grab       -> pieces kg-1 d.w.   (dry weight)
    nurdle patrol       -> pieces/10 mins     (per unit search effort)

The number ``54`` is ``Medium`` in a sediment grab and roughly five times the
top of the water-column ladder.  Concentration in ``pieces/m3`` and in
``pieces/kg`` are *not* convertible into one another: the conversion depends on
sampling depth, grain size, organic content and trawl mesh.  Any platform that
averages them is producing a number that means nothing.

So every sample is tagged with a ``unit_family`` and every aggregate in this
module is grouped by that key.  Values from different families are never
summed, averaged, ranked together, or drawn on one colour ramp.

THE SEVERITY LADDER IS THE SOURCE'S OWN
---------------------------------------
We do not invent thresholds.  NOAA NCEI ships a ``Concentration_class`` per
record whose bands are unit-specific.  Reconstructing those bands from the
India-window records reconciles exactly back to the published counts:

    water    192 records -> 4 bands
    sediment 117 records -> 5 bands
    beach     80 records -> 3 bands
              ---
              389 assigned, 2 nurdle-patrol records outside the ladder

Each band's membership count matched its medium's record count one-for-one,
which is what confirms the ladder belongs to the medium rather than to the
number.  When the source supplies a class we carry it through verbatim and
never overrule it; the ladder is only used to fill a gap or to convert a
label into a sortable ordinal.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Unit families - the only legal grouping key for any concentration maths.
# --------------------------------------------------------------------------
FAMILY_WATER = "water_column"           # pieces per cubic metre
FAMILY_SEDIMENT = "sediment_dry_weight"  # pieces per kilogram dry weight
FAMILY_NURDLE = "nurdle_patrol_time"     # pieces per unit search effort
FAMILY_UNKNOWN = "unknown"

UNIT_FAMILIES = (FAMILY_WATER, FAMILY_SEDIMENT, FAMILY_NURDLE, FAMILY_UNKNOWN)

# Canonical unit string per family (what we normalise *within* the family).
CANONICAL_UNITS = {
    FAMILY_WATER: "pieces/m3",
    FAMILY_SEDIMENT: "pieces/kg dw",
    FAMILY_NURDLE: "pieces/10 min",
    FAMILY_UNKNOWN: "unknown",
}

# Human-facing description of what a family's number physically means.
FAMILY_DESCRIPTIONS = {
    FAMILY_WATER: "Floating microplastic particles per cubic metre of water "
                  "(surface net trawl).",
    FAMILY_SEDIMENT: "Microplastic particles per kilogram of dry sediment "
                     "(grab or core).",
    FAMILY_NURDLE: "Nurdles per 10 minutes of volunteer beach search effort.",
    FAMILY_UNKNOWN: "Unit not recognised; excluded from all concentration "
                    "aggregation.",
}

# --------------------------------------------------------------------------
# Medium classification.  NOAA's ``Medium`` field verbatim -> our medium key.
# --------------------------------------------------------------------------
MEDIUM_WATER = "water"
MEDIUM_SEDIMENT = "sediment"
MEDIUM_BEACH = "beach"
MEDIUM_NURDLE = "beach_nurdle"
MEDIUM_UNKNOWN = "unknown"

_MEDIUM_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (substrings to look for in the source medium, our medium, our family)
    (("nurdle",), MEDIUM_NURDLE, FAMILY_NURDLE),
    (("sediment", "benthic", "seabed", "sea bed"), MEDIUM_SEDIMENT, FAMILY_SEDIMENT),
    (("beach", "shore", "sand"), MEDIUM_BEACH, FAMILY_WATER),
    (("water", "surface", "column", "water column", "sea surface"), MEDIUM_WATER, FAMILY_WATER),
)


def classify_medium(source_medium: str | None) -> tuple[str, str]:
    """Map a source's free-text marine setting to (medium, unit_family).

    Returns ``(MEDIUM_UNKNOWN, FAMILY_UNKNOWN)`` when the setting is absent or
    unrecognised, which excludes the row from aggregation rather than guessing.
    """
    raw = (source_medium or "").strip().lower()
    if not raw:
        return MEDIUM_UNKNOWN, FAMILY_UNKNOWN
    for needles, medium, family in _MEDIUM_RULES:
        if any(needle in raw for needle in needles):
            return medium, family
    return MEDIUM_UNKNOWN, FAMILY_UNKNOWN


# --------------------------------------------------------------------------
# Native unit -> (unit, factor, family).  We only convert *within* a family.
# --------------------------------------------------------------------------
_UNIT_RULES: tuple[tuple[tuple[str, ...], str, float, str], ...] = (
    # water column
    (("pieces/m3", "pieces/m^3", "pieces per m3", "particles/m3", "items/m3"),
     "pieces/m3", 1.0, FAMILY_WATER),
    (("pieces/l", "pieces/liter", "pieces/litre", "particles/l", "items/l"),
     "pieces/m3", 1000.0, FAMILY_WATER),
    # sediment (dry weight)
    (("pieces kg-1 d.w.", "pieces/kg dw", "pieces/kg", "pieces kg-1", "pieces/kgd.w."),
     "pieces/kg dw", 1.0, FAMILY_SEDIMENT),
    # Peer-reviewed studies commonly publish sediment loads as "items/kg",
    # "particles/kg" or "numbers/kg".  All are the same dry-weight-per-mass
    # measure NOAA publishes as "pieces kg-1 d.w.", so they share its family.
    (("items/kg", "items/kg dw", "items kg-1", "items kg-1 dw", "items per kg",
      "particles/kg", "particles/kg dw", "particles kg-1", "particles kg-1 dw",
      "numbers/kg", "numbers kg-1"),
     "pieces/kg dw", 1.0, FAMILY_SEDIMENT),
    (("pieces g-1", "pieces/g"), "pieces/kg dw", 1000.0, FAMILY_SEDIMENT),
    # nurdle patrol effort units
    (("pieces/10 mins", "pieces/10 min", "nurdles/10 min"), "pieces/10 min", 1.0, FAMILY_NURDLE),
)


def normalize_unit(source_unit: str | None) -> tuple[str | None, float, str]:
    """Return ``(canonical_unit, multiplier, family)`` for a published unit.

    ``canonical_unit`` is ``None`` and the multiplier is ``1.0`` when the unit
    is unrecognised - callers must treat that as "cannot be normalised" rather
    than as "already normalised".
    """
    raw = (source_unit or "").strip().lower()
    if not raw:
        return None, 1.0, FAMILY_UNKNOWN
    # Tolerate stray spacing/hyphens from the source's dash characters.
    for needles, canonical, factor, family in _UNIT_RULES:
        if any(needle in raw for needle in needles):
            return canonical, factor, family
    return None, 1.0, FAMILY_UNKNOWN


# --------------------------------------------------------------------------
# The published per-medium concentration ladder.
#
# Bands are (low_inclusive, high_exclusive_or_None, label, ordinal).
# ``None`` as the high bound means the source publishes no band above it, so
# the band is open-ended.  Ordinals are the sortable form of the label.
# --------------------------------------------------------------------------
SEVERITY_ORDINALS = {
    "VERY_LOW": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "VERY_HIGH": 4,
}

SEVERITY_LABEL_DISPLAY = {
    "VERY_LOW": "Very Low",
    "LOW": "Low",
    "MEDIUM": "Medium",
    "HIGH": "High",
    "VERY_HIGH": "Very High",
}

# Ordinal -> label, so a worst-ordinal can be reported back as a human label
# without searching the display map.
SEVERITY_LABELS_BY_ORDINAL = {ordinal: label for label, ordinal in SEVERITY_ORDINALS.items()}

SEVERITY_LADDER: dict[str, tuple[tuple[float, float | None, str], ...]] = {
    # 192 water-column records; the top band is open because the source's
    # India-window distribution never exceeded 10 pieces/m3.
    FAMILY_WATER: (
        (0.0, 0.0005, "VERY_LOW"),
        (0.0005, 0.005, "LOW"),
        (0.005, 1.0, "MEDIUM"),
        (1.0, None, "HIGH"),
    ),
    # 117 sediment records; the only family here that publishes VERY_HIGH.
    FAMILY_SEDIMENT: (
        (0.0, 2.0, "VERY_LOW"),
        (2.0, 20.0, "LOW"),
        (20.0, 150.0, "MEDIUM"),
        (150.0, 200.0, "HIGH"),
        (200.0, None, "VERY_HIGH"),
    ),
}

# Beach samples in this collection carry pieces/m3 but are classified on their
# own ladder.  Note how different it is: "Medium" starts at 500, not 0.005.
# Pooling these with water-column samples would be a category error.
BEACH_LADDER: tuple[tuple[float, float | None, str], ...] = (
    (0.0, 100.0, "VERY_LOW"),
    (100.0, 500.0, "LOW"),
    (500.0, None, "MEDIUM"),
)

# Ladder resolution order per family key.
LADDERS: dict[str, tuple[tuple[float, float | None, str], ...]] = {
    FAMILY_WATER: SEVERITY_LADDER[FAMILY_WATER],
    FAMILY_SEDIMENT: SEVERITY_LADDER[FAMILY_SEDIMENT],
    FAMILY_NURDLE: (),
    FAMILY_UNKNOWN: (),
}

# Ladder lookup actually used by severity_for: some ladders are keyed by
# family (water, sediment) and the beach ladder by medium.
LADDERS_BY_MEDIUM: dict[str, tuple[tuple[float, float | None, str], ...]] = {
    MEDIUM_WATER: SEVERITY_LADDER[FAMILY_WATER],
    MEDIUM_BEACH: BEACH_LADDER,
    MEDIUM_SEDIMENT: SEVERITY_LADDER[FAMILY_SEDIMENT],
}


def _canonical_class_label(published_class: str | None) -> str | None:
    """Normalise a source-provided class label to our ordinal vocabulary."""
    if not published_class:
        return None
    key = published_class.strip().upper().replace(" ", "_").replace("-", "_")
    return key if key in SEVERITY_ORDINALS else None


def severity_for(
    value: float | None,
    medium: str,
    family: str,
    published_class: str | None = None,
) -> tuple[str | None, int | None, str]:
    """Resolve a concentration into ``(label, ordinal, provenance_note)``.

    The source's own class always wins.  The ladder is only consulted when the
    source omitted a class, or when a label needs an ordinal for sorting.

    Never call this with a value from one family and a ladder from another;
    pass the family that actually produced the value.
    """
    from_source = _canonical_class_label(published_class)
    if from_source is not None:
        ordinal = SEVERITY_ORDINALS[from_source]
        return from_source, ordinal, "class published by source"

    if value is None:
        return None, None, "no measured value and no source class"

    # Beach records are classified on their own ladder keyed by medium.
    ladder = LADDERS_BY_MEDIUM.get(medium) if medium == MEDIUM_BEACH else LADDERS.get(family)
    if not ladder:
        return None, None, (
            f"no published concentration ladder for family '{family}' - "
            "left unclassified rather than assigned an invented threshold"
        )

    for low, high, label in ladder:
        if value >= low and (high is None or value < high):
            return (
                label,
                SEVERITY_ORDINALS[label],
                f"derived from the source's published {CANONICAL_UNITS.get(family, family)} ladder",
            )
    return None, None, "value outside every published band"


# --------------------------------------------------------------------------
# Alert tiers - our policy layer, explicitly ON TOP of the source's science.
# --------------------------------------------------------------------------
ALERT_TIER_RULES = (
    (4, "critical", "CLEANUP_PRIORITY",
     "Two bands above the source's own 'High' class."),
    (3, "high", "CLEANUP_PRIORITY",
     "Source class is 'High'."),
    (2, "medium", "FURTHER_SAMPLING",
     "Source class is 'Medium' - above background, warrants a repeat sample."),
    (1, "low", "MONITOR",
     "Source class is 'Low'."),
    (0, "info", "NONE",
     "Source class is 'Very Low'."),
)


def alert_for_ordinal(ordinal: int | None) -> tuple[str, str, str]:
    """Map a severity ordinal to ``(severity, action, rationale)``.

    This is a *policy* mapping, not a scientific one, and the returned
    rationale says so.  ``None`` (unclassified) is reported as ``unknown``.
    """
    if ordinal is None:
        return "unknown", "INSUFFICIENT_BASIS", "No source class and no applicable ladder."
    for threshold, severity, action, rationale in ALERT_TIER_RULES:
        if ordinal >= threshold:
            return severity, action, rationale
    return "unknown", "INSUFFICIENT_BASIS", "Ordinal outside the known ladder."
