"""
TidalTwin - Ocean Acidification Intelligence
============================================
Public API surface for the acidification module, mirroring the deoxygenation
module's exports.

The data path is real and open: in-situ total-scale pH measured by BGC-Argo
floats, pulled from the same GDAC index the deoxygenation module reads, and
stored joined to the 8 monitored coastal regions.  Aragonite and calcite
saturation are DERIVED from that measured pH via CO2SYS and are always
labelled as derived.

Nothing in this module writes a synthetic pH value, and no source is reported
as available unless it was actually reached.
"""

from app.modules.ai.acidification.engine import (
    ALGORITHM_VERSION,
    build_acidification_zones,
    cached_overview,
    clear_cache,
    compute_overview,
    coverage_report,
    emit_alerts,
    ingest,
    load_records,
    map_to_regions,
    persist_records,
    project_ph_decline,
    trend_analysis,
)
from app.modules.ai.acidification.hotspots import (
    ANOMALY_CATEGORY,
    detect_stress_zones,
)
from app.modules.ai.acidification.normalize import (
    normalize_argo_ph_level,
    normalize_batch,
)
from app.modules.ai.acidification.regions import (
    assign_records,
    distance_decay_confidence,
    resolve_monitored_regions,
)
from app.modules.ai.acidification.sources import (
    fetch_argo_bgc_ph_profiles,
    source_catalogue,
)
from app.modules.ai.acidification.trends import analyze_trends, project_ph_decline
from app.modules.ai.acidification.units import (
    ARAGONITE_SATURATION,
    ARAGONITE_STRESS,
    DERIVED_OMEGA_NOTE,
    PH_PLAUSIBLE_MAX,
    PH_PLAUSIBLE_MIN,
    alert_for_ordinal,
    derive_carbonate_chemistry,
    depth_band_for_depth,
    is_ph_plausible,
    is_undersaturated,
    severity_for_ph,
    severity_label_for_ordinal,
    total_alkalinity_from_salinity,
)
from app.modules.ai.acidification.zones import build_zones

__all__ = [
    "ALGORITHM_VERSION",
    "ANOMALY_CATEGORY",
    "ARAGONITE_SATURATION",
    "ARAGONITE_STRESS",
    "DERIVED_OMEGA_NOTE",
    "PH_PLAUSIBLE_MAX",
    "PH_PLAUSIBLE_MIN",
    "alert_for_ordinal",
    "analyze_trends",
    "assign_records",
    "build_acidification_zones",
    "build_zones",
    "cached_overview",
    "clear_cache",
    "compute_overview",
    "coverage_report",
    "depth_band_for_depth",
    "derive_carbonate_chemistry",
    "detect_stress_zones",
    "distance_decay_confidence",
    "emit_alerts",
    "fetch_argo_bgc_ph_profiles",
    "ingest",
    "is_ph_plausible",
    "is_undersaturated",
    "load_records",
    "map_to_regions",
    "normalize_argo_ph_level",
    "normalize_batch",
    "persist_records",
    "project_ph_decline",
    "resolve_monitored_regions",
    "severity_for_ph",
    "severity_label_for_ordinal",
    "source_catalogue",
    "total_alkalinity_from_salinity",
    "trend_analysis",
]
