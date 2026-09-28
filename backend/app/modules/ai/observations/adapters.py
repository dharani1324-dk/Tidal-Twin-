"""Adapters that normalise verified MoES / INCOIS endpoints into candidates.

An adapter has exactly one job: turn one remote dataset into a stream of
*candidate observation dicts* in a single normalised shape.  It does not touch
the database, does not validate, and does not decide what a value means - that
is :mod:`validation` and :mod:`ingest`'s job.  Keeping the three apart is what
makes it possible to add a source without touching the pipeline.

Only adapters whose endpoint was verified from this host exist here:

* :class:`IncoisArgoProfilesAdapter`   - in-situ, REAL
* :class:`IncoisArgoAnalysisAdapter`   - objective analysis, MODEL_DERIVED
* :class:`IncoisOceanColorAdapter`     - optical retrieval, SATELLITE_DERIVED,
                                         disabled by default (coverage ended 2020)

There is deliberately **no** buoy, wave-rider, tide-gauge or HF-radar adapter:
those datasets are real and valuable, but no machine-readable endpoint could be
verified, and guessing an endpoint would produce confident, wrong data.  They
live in the catalogue as ``AUTH_REQUIRED`` / ``TEMPORARILY_UNAVAILABLE`` instead.

Candidate shape
---------------
``source_id, source_name, data_status, timestamp, latitude, longitude, pressure,
units, qc_flags, platform_id, instrument_id, processing_level, source_reference,
plus any canonical fields (temperature / salinity / chlorophyll / wave_height).``
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Iterator, Sequence

from app.core.config import settings
from app.modules.ai.observations.erddap import (
    ErddapConstraint,
    ErddapError,
    erddap_time,
    parse_erddap_time,
    request_table,
    to_float,
)
from app.modules.ai.observations.registry import DataSourceSpec, source as catalogue_source
from app.modules.ai.observations.validation import normalise_longitude, qc_label

logger = logging.getLogger("tidaltwin.observations.adapters")


def _iso(moment: datetime) -> str:
    """Human-readable ISO-8601 for stored references (never for a URL)."""
    return moment.astimezone(timezone.utc).isoformat()


class BaseObservationAdapter:
    """Common behaviour for every observation adapter."""

    #: Registry id of the source this adapter serves.
    source_id: str = ""
    #: Set to False to keep the class available but not selectable.
    default_enabled: bool = True

    def __init__(self, *, base_url: str | None = None, max_rows: int | None = None):
        self.base_url = (base_url or settings.INCOIS_ERDDAP_BASE).rstrip("/")
        self.max_rows = max_rows or settings.INCOIS_MAX_ROWS

    @property
    def spec(self) -> DataSourceSpec:
        spec = catalogue_source(self.source_id)
        if spec is None:  # pragma: no cover - guarded by tests
            raise KeyError(f"{self.source_id} is not in the observation catalogue")
        return spec

    def candidates(self, *, start: datetime | None = None, end: datetime | None = None,
                   bounds: tuple[float, float, float, float] | None = None,
                   limit: int | None = None) -> Iterator[dict[str, Any]]:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        spec = self.spec
        return {
            "source_id": spec.source_id,
            "source_name": spec.source_name,
            "data_status": spec.data_status,
            "endpoint": spec.endpoint,
            "variables": list(spec.variables),
            "units": dict(spec.units),
            "license_access_notes": spec.license_access_notes,
            "default_enabled": self.default_enabled,
        }


# ---------------------------------------------------------------------------
# 1. INCOIS Argo in-situ profiles  (REAL)
# ---------------------------------------------------------------------------


class IncoisArgoProfilesAdapter(BaseObservationAdapter):
    """``Indian_ARGO_Floats`` tabledap -> in-situ temperature / salinity / pressure.

    Correctness details that matter here:

    * The dataset is **global** despite its name, so the region of interest is
      always sent as an explicit server-side constraint.  Without it the ingest
      would silently mix in Atlantic and Pacific floats.
    * Delayed-mode adjusted values are preferred, but only when the value is
      finite *and* its QC flag is not BAD/MISSING.  Argo ships a column of
      "all-NaN" adjusted variables for real-time profiles, which is precisely
      the case where falling back to the raw variable with its own QC flag is
      correct.
    * The float's own ``PRES_QC`` is carried through, so validation can decide
      whether the depth is trustworthy.
    * ``<`` and ``>`` constraints are percent-encoded by the client; sending
      them raw returns HTTP 400 from the live server.
    """

    source_id = "incois_argo_profiles"

    #: Variable pairs: (adjusted, raw, adjusted QC, raw QC).
    VARIABLE_PAIRS = (
        ("TEMP_ADJUSTED", "TEMP", "TEMP_ADJUSTED_QC", "TEMP_QC", "temperature"),
        ("PSAL_ADJUSTED", "PSAL", "PSAL_ADJUSTED_QC", "PSAL_QC", "salinity"),
        ("PRES_ADJUSTED", "PRES", "PRES_ADJUSTED_QC", "PRES_QC", "pressure"),
    )

    #: Columns requested from ``Indian_ARGO_Floats``.
    #:
    #: The list is intersected with the dataset's own DDS declaration at request
    #: time (:func:`erddap.resolve_columns`), so a provider rename drops the
    #: field loudly instead of failing the run.  Names and case are the ones the
    #: live server actually publishes: the position columns are lower case, the
    #: Argo core variables are upper case, and ``PROJECT_NAME`` /
    #: ``DATA_CENTER`` / ``SCIENTIFIC_CALIB_EQUATION`` are **not** part of this
    #: dataset despite being standard in the Argo NetCDF files.
    REQUEST_COLUMNS = (
        "PLATFORM_NUMBER", "CYCLE_NUMBER", "DIRECTION", "time",
        "latitude", "longitude",
        "PRES", "PRES_QC", "PRES_ADJUSTED", "PRES_ADJUSTED_QC",
        "TEMP", "TEMP_QC", "TEMP_ADJUSTED", "TEMP_ADJUSTED_QC",
        "PSAL", "PSAL_QC", "PSAL_ADJUSTED", "PSAL_ADJUSTED_QC",
    )

    def candidates(self, *, start: datetime | None = None, end: datetime | None = None,
                   bounds: tuple[float, float, float, float] | None = None,
                   limit: int | None = None) -> Iterator[dict[str, Any]]:
        lat_min, lat_max, lon_min, lon_max = bounds or (
            settings.OBSERVATIONS_LAT_MIN, settings.OBSERVATIONS_LAT_MAX,
            settings.OBSERVATIONS_LON_MIN, settings.OBSERVATIONS_LON_MAX,
        )
        constraints: list[ErddapConstraint] = [
            ErddapConstraint("latitude", ">=", str(lat_min)),
            ErddapConstraint("latitude", "<=", str(lat_max)),
            ErddapConstraint("longitude", ">=", str(lon_min)),
            ErddapConstraint("longitude", "<=", str(lon_max)),
        ]
        if end is not None:
            constraints.append(ErddapConstraint("time", "<=", erddap_time(end)))
        if start is not None:
            constraints.append(ErddapConstraint("time", ">=", erddap_time(start)))

        table = request_table(
            self.base_url, "tabledap", self.spec.dataset_id,
            columns=self.REQUEST_COLUMNS, constraints=constraints,
            max_rows=min(limit or self.max_rows, self.max_rows),
        )
        logger.info("argo in-situ: %s row(s) retrieved from %s", len(table.rows), table.url)

        emitted = 0
        for row in table.rows:
            candidate = self._normalise(row)
            if candidate is None:
                continue
            yield candidate
            emitted += 1
            if limit and emitted >= limit:
                return

    def _normalise(self, row: dict[str, str]) -> dict[str, Any] | None:
        timestamp = parse_erddap_time(row.get("time") or row.get("JULDATE"))
        if timestamp is None:
            return None

        latitude = to_float(row.get("latitude"))
        longitude_raw = to_float(row.get("longitude"))
        if latitude is None or longitude_raw is None:
            return None

        units = {"latitude": "degrees_north", "longitude": "degrees_east",
                 "pressure": "decibar", "temperature": "degree_Celsius", "salinity": "PSU"}
        qc_flags: dict[str, str] = {}
        platform_id = (row.get("PLATFORM_NUMBER") or "").strip() or None
        candidate: dict[str, Any] = {
            "source_id": self.source_id,
            "source_name": self.spec.source_name,
            "institution": self.spec.institution,
            "dataset_id": self.spec.dataset_id,
            "data_status": "REAL",
            "data_type": "ARGO_PROFILE",
            "platform_type": "ARGO_FLOAT",
            "platform_id": platform_id,
            "instrument_id": f"ARGO_CTD:{platform_id}" if platform_id else None,
            "processing_level": "DELAYED_MODE_ADJUSTED" if self._any_adjusted(row) else "REAL_TIME",
            "cycle_number": to_float(row.get("CYCLE_NUMBER")),
            "profile_direction": (row.get("DIRECTION") or "").strip() or None,
            "timestamp": timestamp,
            "latitude": latitude,
            "longitude": longitude_raw,
            "units": units,
            "qc_flags": qc_flags,
            "platform": "TidalTwin MoES layer",
            "source": f"INCOIS ARGO {platform_id or 'UNKNOWN FLOAT'}",
            "source_reference": self._reference(row, timestamp),
        }

        for adjusted_name, raw_name, adjusted_qc, raw_qc, field_name in self.VARIABLE_PAIRS:
            value, flag, level = self._pick(row, adjusted_name, raw_name, adjusted_qc, raw_qc)
            if value is not None:
                candidate[field_name] = value
            if flag is not None:
                qc_flags[field_name] = flag
            if level:
                candidate["processing_level"] = level
        if candidate.get("temperature") is None and candidate.get("salinity") is None:
            # A depth-only row carries no evidence about water properties.
            return None
        if not platform_id:
            qc_flags["platform_id"] = "MISSING"
        return candidate

    def _any_adjusted(self, row: dict[str, str]) -> bool:
        return any(to_float(row.get(adjusted)) is not None
                   for adjusted, _raw, _aqc, _rqc, _field in self.VARIABLE_PAIRS)

    def _pick(self, row: dict[str, str], adjusted_name: str, raw_name: str,
              adjusted_qc: str, raw_qc: str) -> tuple[float | None, str | None, str | None]:
        """Prefer an adjusted value, falling back to raw only when it is usable."""
        adjusted = to_float(row.get(adjusted_name))
        adjusted_flag = (row.get(adjusted_qc) or "").strip() or None
        if adjusted is not None and qc_label(adjusted_flag) not in ("BAD", "MISSING"):
            return adjusted, adjusted_flag, "DELAYED_MODE_ADJUSTED"

        raw = to_float(row.get(raw_name))
        raw_flag = (row.get(raw_qc) or "").strip() or None
        if raw is not None:
            # The reason we fell back is worth carrying, not discarding.
            return raw, raw_flag, "REAL_TIME"
        return adjusted, adjusted_flag, None

    def _reference(self, row: dict[str, str], timestamp: datetime) -> str:
        float_id = (row.get("PLATFORM_NUMBER") or "").strip()
        cycle = (row.get("CYCLE_NUMBER") or "").strip()
        return (f"INCOIS ERDDAP tabledap {self.spec.dataset_id} | "
                f"WMO {float_id or 'unknown'} cycle {cycle or 'unknown'} | "
                f"{timestamp.isoformat()}")


# ---------------------------------------------------------------------------
# 2. INCOIS Argo objective analysis  (MODEL_DERIVED)
# ---------------------------------------------------------------------------


class IncoisArgoAnalysisAdapter(BaseObservationAdapter):
    """``incois_argo_10d_VAM`` / ``incois_argo_mnt_VAM`` griddap -> analysis cells.

    The values here are the output of a variational analysis: real floats were
    assimilated, but the field at a cell is an interpolation, not a
    measurement.  The adapter therefore sets ``data_status='MODEL_DERIVED'`` and
    carries the published ``TERR`` / ``SERR`` analysis error fields through as
    ``uncertainty``, so downstream consumers can see how much of the field is
    analysis and how much is constrained by data.

    The product is gridded, so a candidate is a *cell*, tagged with its grid
    indices as the platform reference.
    """

    source_id = "incois_argo_analysis_10d"
    default_dataset = "incois_argo_10d_VAM"

    def __init__(self, source_id: str | None = None, dataset_id: str | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        # The catalogue id and the ERDDAP dataset id are not the same string
        # (``incois_argo_analysis_mnt`` serves ``incois_argo_mnt_VAM``), so both
        # are explicit and the catalogue is looked up by source id.
        self.source_id = source_id or type(self).source_id
        self.dataset_id = dataset_id or type(self).default_dataset

    @property
    def spec(self) -> DataSourceSpec:
        spec = catalogue_source(self.source_id)
        if spec is None:  # pragma: no cover
            raise KeyError(f"{self.source_id} is not in the observation catalogue")
        return spec

    def candidates(self, *, start: datetime | None = None, end: datetime | None = None,
                   bounds: tuple[float, float, float, float] | None = None,
                   limit: int | None = None,
                   target_time: datetime | None = None) -> Iterator[dict[str, Any]]:
        lat_min, lat_max, lon_min, lon_max = bounds or (
            settings.OBSERVATIONS_LAT_MIN, settings.OBSERVATIONS_LAT_MAX,
            settings.OBSERVATIONS_LON_MIN, settings.OBSERVATIONS_LON_MAX,
        )
        moment = target_time or end or start
        if moment is None:
            # Without a time target the newest analysis step is the meaningful
            # one.  The time axis is small, so it is read first.
            moment = self._newest_time()
        if moment is None:
            logger.info("argo analysis %s: no time step available", self.dataset_id)
            return

        # A hyperslab: a single time step, the depth levels, and the region box.
        constraints = [
            ErddapConstraint("time", "=", erddap_time(moment)),
            ErddapConstraint("latitude", ">=", str(lat_min)),
            ErddapConstraint("latitude", "<=", str(lat_max)),
            ErddapConstraint("longitude", ">=", str(lon_min)),
            ErddapConstraint("longitude", "<=", str(lon_max)),
        ]
        table = request_table(
            self.base_url, "griddap", self.dataset_id,
            columns=("time", "latitude", "longitude", "ZAX", "TEMP", "SAL", "TERR", "SERR"),
            constraints=constraints,
            max_rows=min(limit or self.max_rows, self.max_rows),
        )
        logger.info("argo analysis %s: %s cell(s) for %s", self.dataset_id, len(table.rows), moment.date())

        emitted = 0
        for row in table.rows:
            candidate = self._normalise(row, moment)
            if candidate is None:
                continue
            yield candidate
            emitted += 1
            if limit and emitted >= limit:
                return

    def _newest_time(self) -> datetime | None:
        table = request_table(self.base_url, "griddap", self.dataset_id,
                              columns=("time",), max_rows=5000)
        newest: datetime | None = None
        for row in table.rows:
            parsed = parse_erddap_time(row.get("time"))
            if parsed is not None and (newest is None or parsed > newest):
                newest = parsed
        return newest

    def _normalise(self, row: dict[str, str], moment: datetime) -> dict[str, Any] | None:
        temperature = to_float(row.get("TEMP"))
        salinity = to_float(row.get("SAL"))
        if temperature is None and salinity is None:
            return None
        latitude = to_float(row.get("latitude"))
        longitude = to_float(row.get("longitude"))
        if latitude is None or longitude is None:
            return None
        depth = to_float(row.get("ZAX"))
        temp_error = to_float(row.get("TERR"))
        sal_error = to_float(row.get("SERR"))

        candidate: dict[str, Any] = {
            "source_id": self.source_id,
            "source_name": self.spec.source_name,
            "institution": self.spec.institution,
            "dataset_id": self.dataset_id,
            "data_status": "MODEL_DERIVED",
            "data_type": "ARGO_OBJECTIVE_ANALYSIS",
            "platform_type": "MODEL_GRID",
            "platform_id": f"{self.dataset_id}@{latitude:.2f},{longitude:.2f},{_iso(moment)[:10]}",
            "instrument_id": "VAM_VARIATIONAL_ANALYSIS",
            "processing_level": "ANALYSIS",
            "timestamp": moment,
            "latitude": latitude,
            "longitude": longitude,
            "depth_m": depth,
            "pressure": depth,
            "units": {"latitude": "degrees_north", "longitude": "degrees_east",
                      "temperature": "degree_Celsius", "salinity": "PSU", "pressure": "decibar"},
            "qc_flags": {},
            "uncertainty": {
                "temperature_degC": temp_error,
                "salinity_psu": sal_error,
                "method": "published analysis error field (TERR / SERR)",
            },
            "platform": "TidalTwin MoES layer",
            "source": f"INCOIS ARGO ANALYSIS {self.dataset_id}",
            "source_reference": (f"INCOIS ERDDAP griddap {self.dataset_id} | time {_iso(moment)} | "
                                 f"lat {latitude} lon {longitude} ZAX {depth}"),
        }
        if temperature is not None:
            candidate["temperature"] = temperature
            # The analysis error is a real, published uncertainty, so it is a
            # usable quality statement even though the source has no QC flags.
            candidate["qc_flags"]["temperature"] = "1" if (temp_error is None or temp_error < 1.0) else "2"
        if salinity is not None:
            candidate["salinity"] = salinity
            candidate["qc_flags"]["salinity"] = "1" if (sal_error is None or sal_error < 0.1) else "2"
        return candidate


# ---------------------------------------------------------------------------
# 3. INCOIS satellite ocean colour  (SATELLITE_DERIVED, off by default)
# ---------------------------------------------------------------------------


class IncoisOceanColorAdapter(BaseObservationAdapter):
    """``incois_oceansat2_datasets`` griddap -> chlorophyll and water clarity.

    Not ingested by default: the provider's own time coverage ends 2020-05-01,
    so enabling it would put a 5-year-old surface optical product next to live
    Argo profiles.  The adapter exists so the deployment can opt in explicitly
    (``INCOIS_SATELLITE_OCM_ENABLED=true``) for a coastal use case.

    Chlorophyll from an optical retrieval is unreliable in turbid, cloud-covered
    coastal water - which is most of the Bay of Bengal and the Arabian Sea
    shelf - and this product exposes no per-pixel cloud flag.  That limitation is
    recorded on every row rather than hidden.
    """

    source_id = "incois_oceansat2_ocm"
    default_enabled = False

    def candidates(self, *, start: datetime | None = None, end: datetime | None = None,
                   bounds: tuple[float, float, float, float] | None = None,
                   limit: int | None = None,
                   target_time: datetime | None = None) -> Iterator[dict[str, Any]]:
        lat_min, lat_max, lon_min, lon_max = bounds or (
            settings.OBSERVATIONS_LAT_MIN, settings.OBSERVATIONS_LAT_MAX,
            settings.OBSERVATIONS_LON_MIN, settings.OBSERVATIONS_LON_MAX,
        )
        moment = target_time or end or start
        if moment is None:
            moment = self._newest_time()
        if moment is None:
            return

        table = request_table(
            self.base_url, "griddap", self.spec.dataset_id,
            columns=("time", "latitude", "longitude", "CHL"),
            constraints=[
                ErddapConstraint("time", "=", erddap_time(moment)),
                ErddapConstraint("latitude", ">=", str(lat_min)),
                ErddapConstraint("latitude", "<=", str(lat_max)),
                ErddapConstraint("longitude", ">=", str(lon_min)),
                ErddapConstraint("longitude", "<=", str(lon_max)),
            ],
            max_rows=min(limit or self.max_rows, self.max_rows),
        )
        emitted = 0
        for row in table.rows:
            chlorophyll = to_float(row.get("CHL"))
            latitude = to_float(row.get("latitude"))
            longitude = to_float(row.get("longitude"))
            if chlorophyll is None or latitude is None or longitude is None:
                continue
            yield {
                "source_id": self.source_id,
                "source_name": self.spec.source_name,
                "institution": self.spec.institution,
                "dataset_id": self.spec.dataset_id,
                "data_status": "SATELLITE_DERIVED",
                "data_type": "OCEAN_COLOUR",
                "platform_type": "OCEANSAT2_OCM",
                "platform_id": f"OCM@{latitude:.2f},{longitude:.2f}",
                "instrument_id": "OCEANSAT2_OCM",
                "processing_level": "L2B_RETRIEVAL",
                "timestamp": parse_erddap_time(row.get("time")) or moment,
                "latitude": latitude,
                "longitude": longitude,
                "chlorophyll": chlorophyll,
                "units": {"chlorophyll": "mg/m3"},
                # No cloud/QC flag is published for this product.  The value is
                # therefore recorded as unverified evidence, not as good data.
                "qc_flags": {"chlorophyll": " "},
                "uncertainty": {"chlorophyll_mg_m3": None,
                                "method": "no per-pixel uncertainty published with this product"},
                "limitations": ("Optical retrieval: unreliable under cloud and in turbid coastal water. "
                                "No per-pixel QC flag is published with this dataset."),
                "platform": "TidalTwin MoES layer",
                "source": "INCOIS OCEANSAT2 OCM",
                "source_reference": f"INCOIS ERDDAP griddap {self.spec.dataset_id} | CHL {_iso(moment)}",
            }
            emitted += 1
            if limit and emitted >= limit:
                return

    def _newest_time(self) -> datetime | None:
        table = request_table(self.base_url, "griddap", self.spec.dataset_id,
                              columns=("time",), max_rows=5000)
        newest: datetime | None = None
        for row in table.rows:
            parsed = parse_erddap_time(row.get("time"))
            if parsed is not None and (newest is None or parsed > newest):
                newest = parsed
        return newest


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

ADAPTER_CLASSES: tuple[type[BaseObservationAdapter], ...] = (
    IncoisArgoProfilesAdapter,
    IncoisArgoAnalysisAdapter,
    IncoisOceanColorAdapter,
)

#: The two VAM products share one adapter class.
_MONTHLY_SOURCE = "incois_argo_analysis_mnt"
_MONTHLY_DATASET = "incois_argo_mnt_VAM"


def build_adapters(*, include_disabled: bool = False) -> list[BaseObservationAdapter]:
    """Instantiate the adapters this deployment is allowed to run."""
    adapters: list[BaseObservationAdapter] = [
        IncoisArgoProfilesAdapter(),
        IncoisArgoAnalysisAdapter(),
        IncoisArgoAnalysisAdapter(source_id=_MONTHLY_SOURCE, dataset_id=_MONTHLY_DATASET),
        IncoisOceanColorAdapter(),
    ]
    if include_disabled:
        return adapters
    enabled: list[BaseObservationAdapter] = []
    for adapter in adapters:
        if adapter.source_id == "incois_argo_profiles" and not settings.INCOIS_ARGO_INSITU_ENABLED:
            continue
        if adapter.source_id in ("incois_argo_analysis_10d", _MONTHLY_SOURCE) \
                and not settings.INCOIS_ARGO_ANALYSIS_ENABLED:
            continue
        if adapter.source_id == "incois_oceansat2_ocm" and not settings.INCOIS_SATELLITE_OCM_ENABLED:
            continue
        enabled.append(adapter)
    return enabled


def adapter_for(source_id: str, *, base_url: str | None = None) -> BaseObservationAdapter | None:
    if source_id == "incois_argo_profiles":
        return IncoisArgoProfilesAdapter(base_url=base_url)
    if source_id == "incois_argo_analysis_10d":
        return IncoisArgoAnalysisAdapter(base_url=base_url)
    if source_id == _MONTHLY_SOURCE:
        return IncoisArgoAnalysisAdapter(source_id=_MONTHLY_SOURCE, dataset_id=_MONTHLY_DATASET,
                                         base_url=base_url)
    if source_id == "incois_oceansat2_ocm":
        return IncoisOceanColorAdapter(base_url=base_url)
    return None


__all__ = [
    "ADAPTER_CLASSES",
    "BaseObservationAdapter",
    "IncoisArgoAnalysisAdapter",
    "IncoisArgoProfilesAdapter",
    "IncoisOceanColorAdapter",
    "adapter_for",
    "build_adapters",
]
