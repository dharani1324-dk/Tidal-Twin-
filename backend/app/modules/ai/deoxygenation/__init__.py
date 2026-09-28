"""
TidalTwin - Deoxygenation Intelligence Module
==============================================
Open-source dissolved oxygen monitoring, hypoxia detection, and forecasting
for the 8 Indian Ocean coastal regions.
"""

from app.modules.ai.deoxygenation.engine import (
    ingest,
    map_to_regions,
    coverage_report,
    compute_overview,
    cached_overview,
    emit_alerts,
)
from app.modules.ai.deoxygenation.hotspots import detect_hypoxic_hotspots
from app.modules.ai.deoxygenation.trends import analyze_trends, project_hypoxic_expansion
from app.modules.ai.deoxygenation.regions import resolve_monitored_regions, assign_records
from app.modules.ai.deoxygenation.sources import source_catalogue
from app.modules.ai.deoxygenation.normalize import normalize_batch

__all__ = [
    "ingest",
    "map_to_regions",
    "coverage_report",
    "compute_overview",
    "cached_overview",
    "emit_alerts",
    "detect_hypoxic_hotspots",
    "analyze_trends",
    "project_hypoxic_expansion",
    "resolve_monitored_regions",
    "assign_records",
    "source_catalogue",
    "normalize_batch",
]