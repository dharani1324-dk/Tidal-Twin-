"""
TidalTwin - Acidification: regions
===================================
Shared region resolution and assignment for the acidification module.

THIS IS DELIBERATE SHARED INFRASTRUCTURE, NOT A COPY.
-----------------------------------------------------
The pH sensors ride the same BGC-Argo floats as the oxygen sensor, so both
modules need to answer the identical question - "which of the 8 monitored
coastal regions does this observation belong to, and how far away is it?" -
and they must answer it IDENTICALLY.  Two divergent copies of a haversine
routing rule is precisely how a float ends up counted for oxygen in one
region and for pH in another, and the two dashboards stop agreeing.

So the implementations are imported from the deoxygenation module rather than
re-derived.  The constants are re-exported under this module's namespace so
callers and tests read naturally, but there is exactly one implementation of
each rule.

The one acidification-specific concern is preserved verbatim from the original:
``region_distance_km`` records HOW FAR a sample sits from the region it was
assigned to, and is deliberately NOT folded into ``confidence_score``.
Confidence carries measurement trust (the Argo QC flag) and overwriting it
with a distance decay would destroy that signal - and for an open-ocean sample
beyond the mapping radius would pin a perfectly good delayed-mode measurement
to 0.0.  Spatial confidence is available separately via
``distance_decay_confidence``.
"""

from app.modules.ai.deoxygenation.regions import (  # noqa: F401 - re-exported
    DEFAULT_RADIUS_KM,
    MAX_ASSIGNMENT_RADIUS_KM,
    assign_records,
    distance_decay_confidence,
    get_region_bbox,
    haversine_km,
    resolve_monitored_regions,
)

__all__ = [
    "DEFAULT_RADIUS_KM",
    "MAX_ASSIGNMENT_RADIUS_KM",
    "assign_records",
    "distance_decay_confidence",
    "get_region_bbox",
    "haversine_km",
    "resolve_monitored_regions",
]
