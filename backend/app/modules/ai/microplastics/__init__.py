"""
TidalTwin - Microplastics Intelligence
=======================================
Microplastic detection, regional mapping, hotspot ranking and 24-72h drift
projection, built entirely from open-source data.  No hardware.

Pipeline:

    sources  -> NOAA NCEI (public, no key) and an optional, credential-gated
                NASA Earthdata connector that reports UNAVAILABLE without a token
    units    -> medium and unit families, plus the source's own severity ladder
    normalize-> one unified record shape, native units preserved
    regions  -> mapping onto the monitored coastal regions + IDW surfaces
    hotspots -> priority ranking, anomaly category, plain-language actions
    drift    -> Lagrangian corridor from real current forcing, or an honest
                refusal when no forcing exists

THE TWO RULES THIS MODULE WILL NOT BREAK
----------------------------------------
1. Concentrations are never combined across unit families.  ``pieces/m3``,
   ``pieces/kg dw`` and ``pieces/10 min`` measure different things under
   different sampling effort; every aggregate is grouped by family and medium.

2. Absence is never rendered as a number.  A region with no published sample
   is a gap, an unreachable connector returns a reason, and unpredicted drift
   is reported as unpredicted.
"""

from app.modules.ai.microplastics.engine import (  # noqa: F401
    ALGORITHM_VERSION,
    cached_overview,
    clear_cache,
    compute_overview,
    coverage_report,
    emit_alerts,
    ingest,
    load_records,
    persist_records,
    timeline,
)
from app.modules.ai.microplastics.hotspots import ANOMALY_CATEGORY  # noqa: F401

__all__ = [
    "ANOMALY_CATEGORY",
    "ALGORITHM_VERSION",
    "cached_overview",
    "clear_cache",
    "compute_overview",
    "coverage_report",
    "emit_alerts",
    "ingest",
    "load_records",
    "persist_records",
    "timeline",
]
