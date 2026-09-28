"""
TidalTwin - National Ocean Observation layer
==============================================

Evidence-aware integration of validated Ministry of Earth Sciences (MoES)
ecosystem observations.

This package deliberately does **not** introduce a second observation store.
It extends the existing `OceanObservation` contract, the existing source
registry (`app.modules.ai.twin.sources`) and the existing TIDE scoring engine.

Modules
-------
registry    Declared metadata + live availability for every MoES/INCOIS data
            source, including sources that are honestly UNAVAILABLE.
erddap      Bounded, retrying, timeout-guarded ERDDAP client.
adapters    ``BaseObservationAdapter`` and the adapters that are actually
            supported by a verified endpoint (INCOIS Argo in-situ, INCOIS Argo
            objective analysis, INCOIS satellite ocean colour).
validation  Schema / unit / coordinate / timestamp / depth / range / duplicate /
            QC-flag validation. Flags, never silently deletes.
coverage    Observation coverage and observation-gap intelligence.
agreement   Multi-source agreement / disagreement engine.
modelobs    Model-vs-observation difference with cautious explanations.
methods     Observation-method capability comparison and honest cost reporting.
ingest      The single resumable ingestion pipeline every adapter runs through.

Data-honesty contract
---------------------
``MODEL_DERIVED`` is never promoted to ``REAL``. ``SIMULATED`` is never promoted
to ``REAL``. ``SATELLITE_DERIVED`` is never relabelled ``IN_SITU``. ``HISTORICAL``
is never relabelled ``REAL_TIME``. See ``app.modules.ai.provenance_quality``
for the single shared classifier.
"""

from app.modules.ai.observations.registry import (
    AVAILABILITY_STATUSES,
    DATA_STATUSES,
    DataSourceSpec,
    enabled_adapters,
    list_sources,
    probe_all,
    probe_source,
    source,
    sources_payload,
)

__all__ = [
    "AVAILABILITY_STATUSES",
    "DATA_STATUSES",
    "DataSourceSpec",
    "enabled_adapters",
    "list_sources",
    "probe_all",
    "probe_source",
    "source",
    "sources_payload",
]
