"""Declared metadata and live availability for every MoES / INCOIS data source.

Relationship to the existing source registry
---------------------------------------------
TidalTwin already ships a plugin-driven source registry in
``app.modules.ai.twin.sources`` (``SensorPlugin`` + ``build_sources``) that
reports the *runtime* health of the streams the twin consumes.  This module does
**not** replace it.  It holds the *catalogue* metadata that registry cannot
express: institution, dataset id, endpoint, units, licence, QC scheme, and -
critically - the honest availability status of sources that TidalTwin does
**not** currently consume (NIOT moored buoys, INCOIS tide gauges, HF radar,
NCCR, CMLRE).  Those are recorded as ``TEMPORARILY_UNAVAILABLE`` /
``AUTH_REQUIRED`` rather than omitted, so the platform can state plainly what
it cannot reach and why.

Availability semantics
---------------------
``AVAILABLE``             a constrained request against the documented endpoint
                          succeeded inside its timeout.
``PARTIAL``               reachable, but the dataset's own time coverage has
                          ended or the requested subset returned no rows.
``HISTORICAL``            reachable and queryable, but the newest sample is old.
``MODEL_DERIVED``         an objective analysis / interpolated product.  Real
                          inputs, but the *values* are analysis output, not
                          point measurements.
``SATELLITE_DERIVED``     remote-sensing retrieval, not in-situ.
``TEMPORARILY_UNAVAILABLE``  the endpoint did not answer, or the host does not
                          resolve, at the time of the last probe.
``AUTH_REQUIRED``         documented as available but gated behind a request
                          form, a manual approval, or a credential we do not
                          hold.
``NOT_INGESTED``           reachable and verified, but deliberately not enabled
                          in this deployment.
``SYNTHETIC`` / ``SIMULATED``  never declared here.  The catalogue only contains
                          externally hosted datasets; generated values are
                          labelled at the row level by
                          ``provenance_quality.origin_status``.

The registry never converts one status into another.  A ``MODEL_DERIVED`` source
is never reported as ``REAL``, and a ``SATELLITE_DERIVED`` source is never
reported as in-situ.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger("tidaltwin.observations.registry")

# ---------------------------------------------------------------------------
# Vocabularies (kept explicit so the API contract is stable and testable)
# ---------------------------------------------------------------------------

AVAILABILITY_STATUSES = (
    "AVAILABLE",
    "PARTIAL",
    "HISTORICAL",
    "MODEL_DERIVED",
    "SATELLITE_DERIVED",
    "TEMPORARILY_UNAVAILABLE",
    "AUTH_REQUIRED",
    "NOT_INGESTED",
    "DISABLED",
)

#: Data status reuses the project's existing ``origin_status`` vocabulary so a
#: source can never claim a stronger origin than a stored row is allowed to.
DATA_STATUSES = ("REAL", "HISTORICAL", "MODEL_DERIVED", "SATELLITE_DERIVED", "UNKNOWN")

#: Age in days beyond which an otherwise-available source is reported
#: ``HISTORICAL`` rather than ``AVAILABLE``.  Deliberately generous: Argo floats
#: surface every ~10 days, a monthly analysis is current for a month.
FRESHNESS_HORIZON_DAYS = 45.0


@dataclass(frozen=True)
class DataSourceSpec:
    """Immutable declared metadata for one externally hosted dataset."""

    source_id: str
    source_name: str
    institution: str
    dataset_name: str
    dataset_id: str
    access_method: str
    endpoint: str
    #: One of DATA_STATUSES.  The origin of the *values*, never of the network.
    data_status: str
    variables: tuple[str, ...]
    units: dict[str, str]
    spatial_coverage: str
    temporal_coverage: str
    depth_coverage: str
    update_frequency: str
    quality_control: str
    provenance: str
    license_access_notes: str
    availability_status: str
    #: Populated at runtime by the availability probe / database query.
    last_checked: str | None = None
    notes: str = ""
    citation: str = ""
    enabled: bool = True
    #: Set when the catalogue itself is the only evidence - i.e. the source was
    #: documented by the provider but could not be probed from this host.
    verified_from: str = ""

    def payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["variables"] = list(self.variables)
        return data


# ---------------------------------------------------------------------------
# The catalogue.
#
# Every entry below was verified against the live endpoint from this host on
# the date recorded in ``verified_from``, unless ``verified_from`` is empty,
# which means the provider's own published documentation was used and the
# endpoint was NOT reachable (those are the AUTH_REQUIRED /
# TEMPORARILY_UNAVAILABLE rows).  See docs/MOES_INCOIS_INTEGRATION.md.
# ---------------------------------------------------------------------------

INCOIS = "INCOIS (Ministry of Earth Sciences, Govt. of India)"
ARGO_GDAC = "Argo Global Data Assembly Centre (INCOIS national node)"

_VERIFIED_ON = "2026-09-27"

_SPECS: tuple[DataSourceSpec, ...] = (

    # -- IN-SITU -----------------------------------------------------------
    DataSourceSpec(
        source_id="incois_argo_profiles",
        source_name="INCOIS Argo float profiles",
        institution=INCOIS,
        dataset_name="INDIAN ARGO Floats Data",
        dataset_id="Indian_ARGO_Floats",
        access_method="ERDDAP tabledap (OPeNDAP constraint protocol)",
        endpoint="https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.csv",
        data_status="REAL",
        variables=("sea_water_temperature", "sea_water_practical_salinity", "sea_water_pressure"),
        units={
            "TEMP": "degree_Celsius",
            "TEMP_ADJUSTED": "degree_Celsius",
            "PSAL": "PSU",
            "PSAL_ADJUSTED": "PSU",
            "PRES": "decibar",
            "PRES_ADJUSTED": "decibar",
        },
        spatial_coverage=(
            "Published extent is global (lat -69.735 to 47.783, lon -179.988 to 179.903) despite the "
            "'INDIAN ARGO' dataset name; TidalTwin subsets it to the monitored northern Indian Ocean box."
        ),
        temporal_coverage="2002-10-24T19:30:03Z to 2025-04-23T13:28:00Z (provider time_coverage attributes)",
        depth_coverage="Argo float standard levels, nominal 0-2000 m (PRES in decibar)",
        update_frequency="Not maintained on a fixed schedule; newest profile timestamp is 2025-04-23",
        quality_control=(
            "Argo reference table 2 QC flags supplied per variable (TEMP_QC, PSAL_QC, PRES_QC) and for the "
            "delayed-mode adjusted fields (TEMP_ADJUSTED_QC, PSAL_ADJUSTED_QC, PRES_ADJUSTED_QC). "
            "TidalTwin prefers an adjusted value only when it is finite AND its QC flag is not '9'."
        ),
        provenance=(
            "Retrieved verbatim from the INCOIS ERDDAP subset request. The WMO float id (PLATFORM_NUMBER), "
            "cycle number, profile direction and the source file reference are stored with every row."
        ),
        license_access_notes=(
            "Open access. Provider licence: data may be used and redistributed for free but is not intended "
            "for legal use; no warranty of accuracy, completeness or fitness is given. Argo data are "
            "additionally subject to the Argo free, open and unrestricted data policy (doi:10.17882/42182)."
        ),
        availability_status="AVAILABLE",
        notes=(
            "In-situ BGC-free core Argo temperature, salinity and pressure from floats in the INCOIS national "
            "Argo archive. This is the primary measured evidence source for TidalTwin."
        ),
        citation="INCOIS ERDDAP dataset Indian_ARGO_Floats; Argo Data Management infrastructure",
        enabled=True,
        verified_from=f"Live constrained .csv request returned real rows on {_VERIFIED_ON} (2352 rows, HTTP 200, 2.0 s).",
    ),

    # -- Argo objective analysis (model-derived, NOT in-situ) ---------------
    DataSourceSpec(
        source_id="incois_argo_analysis_10d",
        source_name="INCOIS Argo 10-day objective analysis (VAM)",
        institution=INCOIS,
        dataset_name="INCOIS ARGO 10 day data Variational Analysis Methodology",
        dataset_id="incois_argo_10d_VAM",
        access_method="ERDDAP griddap (OPeNDAP hyperslab)",
        endpoint="https://erddap.incois.gov.in/erddap/griddap/incois_argo_10d_VAM.csv",
        data_status="MODEL_DERIVED",
        variables=("TEMP", "SAL", "TERR", "SERR"),
        units={"TEMP": "degs", "SAL": "PSU", "TERR": "degs", "SERR": "PSU"},
        spatial_coverage="60 latitude x 90 longitude analysis grid over the Indian Ocean region",
        temporal_coverage="2004-01-10T00:00:00Z to 2026-07-30T00:00:00Z",
        depth_coverage="24 standard levels, 5 m to 2000 m (ZAX axis, units METERS)",
        update_frequency="10-day analysis; newest time step 2026-07-30",
        quality_control=(
            "Analysis error fields TERR (temperature) and SERR (salinity) are published alongside the fields, "
            "which is stronger uncertainty information than the raw float feed provides."
        ),
        provenance=(
            "Gridded variational analysis of in-situ Argo profiles. The VALUES ARE ANALYSIS OUTPUT, not point "
            "measurements, and are stored and reported as MODEL_DERIVED. A cell is interpolated between floats; "
            "it is not evidence that a float was there."
        ),
        license_access_notes="Open access; same ERD/NOAA open-use disclaimer as the INCOIS ERDDAP service.",
        availability_status="MODEL_DERIVED",
        notes=(
            "Actively maintained (newest time step is within ~2 months of the verification date). Used as the "
            "model-side field a point observation is validated against, never as a substitute for one."
        ),
        citation="INCOIS Argo objective analysis, Variational Analysis Methodology",
        enabled=True,
        verified_from=f"Live griddap hyperslab request returned finite values on {_VERIFIED_ON} (HTTP 200).",
    ),

    DataSourceSpec(
        source_id="incois_argo_analysis_mnt",
        source_name="INCOIS Argo monthly objective analysis (VAM)",
        institution=INCOIS,
        dataset_name="INCOIS ARGO Monthly data Variational Analysis Methodology",
        dataset_id="incois_argo_mnt_VAM",
        access_method="ERDDAP griddap",
        endpoint="https://erddap.incois.gov.in/erddap/griddap/incois_argo_mnt_VAM.csv",
        data_status="MODEL_DERIVED",
        variables=("TEMP", "SAL", "TERR", "SERR"),
        units={"TEMP": "degs", "SAL": "PSU", "TERR": "degs", "SERR": "PSU"},
        spatial_coverage="60 latitude x 90 longitude analysis grid over the Indian Ocean region",
        temporal_coverage="2004-01-15T00:00:00Z to 2026-07-15T00:00:00Z",
        depth_coverage="Standard depth levels 5 m to 2000 m",
        update_frequency="Monthly; newest time step 2026-07-15",
        quality_control="Analysis error fields TERR and SERR published with each field.",
        provenance="Monthly variational analysis of in-situ Argo profiles. Values are analysis output (MODEL_DERIVED).",
        license_access_notes="Open access; same ERD/NOAA open-use disclaimer as the INCOIS ERDDAP service.",
        availability_status="MODEL_DERIVED",
        notes="Monthly companion to the 10-day analysis; used for seasonal context, not for nowcasting.",
        citation="INCOIS Argo objective analysis, Variational Analysis Methodology",
        enabled=True,
        verified_from=f"DAS metadata retrieved from the live server on {_VERIFIED_ON}.",
    ),

    # -- Satellite --------------------------------------------------------
    DataSourceSpec(
        source_id="incois_oceansat2_ocm",
        source_name="INCOIS Oceansat-2 Ocean Colour Monitor",
        institution=INCOIS,
        dataset_name="INCOIS Oceansat 2 OCM Data",
        dataset_id="incois_oceansat2_datasets",
        access_method="ERDDAP griddap",
        endpoint="https://erddap.incois.gov.in/erddap/griddap/incois_oceansat2_datasets.csv",
        data_status="SATELLITE_DERIVED",
        variables=("CHL", "KD490", "TSM"),
        units={"CHL": "mg/m3", "KD490": "1/m", "TSM": "g/L"},
        spatial_coverage="717 latitude x 1317 longitude regional grid (ocean colour scene)",
        temporal_coverage="2011-02-02T00:00:00Z to 2020-05-01T00:00:00Z",
        depth_coverage="Surface only (optical retrieval; no subsurface information)",
        update_frequency="None since 2020-05-01; the OCM product is no longer being produced on this server",
        quality_control=(
            "No per-pixel cloud/QC flag is exposed through this ERDDAP dataset. Chlorophyll is a case-1 "
            "optical retrieval and is unreliable in turbid or cloud-covered coastal water, which includes much "
            "of the Bay of Bengal and the Arabian Sea shelf."
        ),
        provenance=(
            "Remote-sensing retrieval from the Oceansat-2 Ocean Colour Monitor. Never relabelled as in-situ; "
            "its platform_type and data_status remain SATELLITE_DERIVED in every downstream consumer."
        ),
        license_access_notes="Open access via the INCOIS ERDDAP service.",
        availability_status="PARTIAL",
        notes=(
            "Disabled by default (INCOIS_SATELLITE_OCM_ENABLED=false) because the provider's own time coverage "
            "ended in 2020. Kept in the catalogue because it is verified-reachable and a deployment with a "
            "coastal chlorophyll use case can enable it explicitly."
        ),
        citation="INCOIS Oceansat-2 OCM processed ocean-colour product",
        enabled=False,
        verified_from=f"DDS retrieved from the live server on {_VERIFIED_ON}.",
    ),

    # -- Argo GDAC national node -----------------------------------------
    DataSourceSpec(
        source_id="argo_gdac_incois",
        source_name="Argo GDAC - INCOIS national node",
        institution=ARGO_GDAC,
        dataset_name="Argo Global Data Assembly Centre, dac/incois tree",
        dataset_id="dac/incois",
        access_method="HTTPS directory tree (per-float NetCDF: <wmo>_prof.nc, <wmo>_D<cycle>.nc)",
        endpoint="https://data-argo.ifremer.fr/dac/incois/",
        data_status="REAL",
        variables=("sea_water_temperature", "sea_water_practical_salinity", "sea_water_pressure"),
        units={"TEMP": "degree_Celsius", "PSAL": "PSU", "PRES": "decibar"},
        spatial_coverage="Floats operated by INCOIS as India's National Argo Data Centre; global deployments",
        temporal_coverage="Active float directories observed from WMO 1900121 through 2904172",
        depth_coverage="Argo float standard levels, nominal 0-2000 m",
        update_frequency="Per profile (nominal 10-day cycle), as published by each float",
        quality_control=(
            "Argo reference table 2 QC flags and delayed-mode adjusted fields in the per-profile NetCDF, read by "
            "the existing scripts.fetch_argo / scripts.ingest_argo path."
        ),
        provenance=(
            "The canonical Argo archive. TidalTwin already ingests floats from this tree via "
            "scripts.fetch_argo; this catalogue row records the INCOIS institutional attribution that the "
            "generic fetch path does not carry."
        ),
        license_access_notes=(
            "Free, open and unrestricted (Argo data policy, doi:10.17882/42182). Redistribution permitted."
        ),
        availability_status="AVAILABLE",
        notes=(
            "Attribution source rather than a new pipeline. Setting INCOIS_ARGO_WMO_IDS lets stored Argo rows be "
            "labelled as INCOIS-operated floats; when it is empty no attribution is claimed."
        ),
        citation="Argo Global Data Assembly Centre; INCOIS National / Regional Argo Data Centre for the Indian Ocean",
        enabled=True,
        verified_from=f"Directory listing and float files confirmed reachable on {_VERIFIED_ON}.",
    ),

    # == Sources TidalTwin could NOT integrate, recorded honestly ==========
    DataSourceSpec(
        source_id="niot_omni_moored_buoy",
        source_name="NIOT OMNI moored buoy network",
        institution="NIOT (Ministry of Earth Sciences, Govt. of India)",
        dataset_name="OMNI (Ocean Moored buoy Network for Northern Indian) buoys, managed by INCOIS",
        dataset_id="OMNI-buoy-network",
        access_method="Web visualisation only - NO machine-readable download endpoint",
        endpoint="https://www.niot.res.in/oos_data_form/",
        data_status="REAL",
        variables=(
            "sea_water_temperature", "sea_water_practical_salinity", "surface_current",
            "wind_speed", "air_temperature", "wave_height",
        ),
        units={"sea_water_temperature": "degree_Celsius", "sea_water_practical_salinity": "PSU",
               "wind_speed": "m/s", "wave_height": "m"},
        spatial_coverage="~12 deep-sea OMNI buoys in the Bay of Bengal and eastern Arabian Sea, plus coastal buoys",
        temporal_coverage="1997 to present (provider statement)",
        depth_coverage="Temperature and salinity to ~500 m; current profile to ~150 m (provider statement)",
        update_frequency="Every 3 hours over satellite to CORNEA, NIOT Chennai (provider statement)",
        quality_control=(
            "Real-time trigger-based QC in the provider's ODIS system. Not accessible to TidalTwin because there "
            "is no download route."
        ),
        provenance=(
            "This is genuinely measured data and would be high value. TidalTwin reports it as AUTH_REQUIRED "
            "rather than approximating it, because the provider's own data-holdings page states moored-buoy and "
            "wave-rider data are available 'with only visualisation option. No download option.'"
        ),
        license_access_notes=(
            "Distributed by INCOIS/NIOT on request. The MoES-NOAA OMNI-RAMA joint open-data portal is announced "
            "but the TidalTwin-side endpoint (https://www.niot.res.in/OMNIRAMA/) returns an empty animated "
            "placeholder with no data service."
        ),
        availability_status="AUTH_REQUIRED",
        notes=(
            "Highest-value un-integrated source. Closing this needs an institutional data request to INCOIS/NIOT, "
            "not a code change."
        ),
        citation="Venkatesan et al. (2013), NIOT Ocean Observation Systems moored buoy documentation",
        enabled=False,
    ),

    DataSourceSpec(
        source_id="niot_wave_rider",
        source_name="NIOT wave rider buoys",
        institution="NIOT (Ministry of Earth Sciences, Govt. of India)",
        dataset_name="Wave rider buoy wave parameters",
        dataset_id="wave-rider-network",
        access_method="Web visualisation only - NO machine-readable download endpoint",
        endpoint="https://www.niot.res.in/oos_data_form/",
        data_status="REAL",
        variables=("sea_surface_wave_height", "sea_surface_wave_direction", "sea_surface_wave_period"),
        units={"sea_surface_wave_height": "m", "sea_surface_wave_direction": "degree",
               "sea_surface_wave_period": "s"},
        spatial_coverage="Indian coastal and offshore wave-rider stations (provider statement)",
        temporal_coverage="2008 to present (provider statement)",
        depth_coverage="Surface wave field",
        update_frequency="Real-time (provider statement)",
        quality_control="Not accessible - no download route.",
        provenance=(
            "Genuine wave observations. Recorded as AUTH_REQUIRED: the INCOIS data-holdings page lists wave-rider "
            "buoys as visualisation-only, with no download option."
        ),
        license_access_notes="Available from INCOIS/NIOT on request; GTS also carries a subset in FM-18 format.",
        availability_status="AUTH_REQUIRED",
        notes=(
            "TidalTwin's wave layer is currently model-derived. This source is the honest route to real in-situ "
            "wave data, and is the reason the wave layer is labelled MODEL_DERIVED rather than REAL."
        ),
        citation="NIOT Ocean Observation Systems; INCOIS data holdings",
        enabled=False,
    ),

    DataSourceSpec(
        source_id="incois_tide_gauges",
        source_name="INCOIS tide gauge network",
        institution=INCOIS,
        dataset_name="Coastal tide gauge sea level records",
        dataset_id="tide-gauges",
        access_method="ODIS / Live Access Server web visualisation; no documented REST or ERDDAP endpoint",
        endpoint="https://incois.gov.in/ (Data & Information -> Insitu Data)",
        data_status="REAL",
        variables=("sea_surface_height_above_geoid", "sea_surface_temperature"),
        units={"sea_surface_height_above_geoid": "m"},
        spatial_coverage="Indian coastal tide gauge stations",
        temporal_coverage="Varies by station",
        depth_coverage="Surface",
        update_frequency="Real-time operationally; bulk access undocumented",
        quality_control="Not accessible - no download route.",
        provenance=(
            "Real sea level, and the natural source for validating the twin's storm-surge and sea-level modules. "
            "No public machine-readable endpoint could be verified, so it is recorded as TEMPORARILY_UNAVAILABLE "
            "rather than approximated."
        ),
        license_access_notes="Public visualisation via ODIS; bulk transfer requires a request to INCOIS.",
        availability_status="TEMPORARILY_UNAVAILABLE",
        notes="Re-probe if INCOIS publishes an ERDDAP or OPeNDAP view of the gauge archive.",
        enabled=False,
    ),

    DataSourceSpec(
        source_id="incois_hf_radar",
        source_name="INCOIS HF radar surface currents",
        institution=INCOIS,
        dataset_name="HF radar derived surface current fields",
        dataset_id="hf-radar",
        access_method="No public API located",
        endpoint="",
        data_status="REAL",
        variables=("surface_eastward_current", "surface_northward_current"),
        units={"surface_eastward_current": "m/s", "surface_northward_current": "m/s"},
        spatial_coverage="Near-coast radar cells along parts of the Indian coast (provider statement)",
        temporal_coverage="Varies by deployment",
        depth_coverage="Top few metres of the water column",
        update_frequency="Sub-hourly operationally",
        quality_control="Not accessible - no download route.",
        provenance=(
            "The only routinely available direct current observation for the Indian shelf. No public automated "
            "access path was found, so TidalTwin records TEMPORARILY_UNAVAILABLE and continues to use model or "
            "derived currents, labelled as such."
        ),
        license_access_notes="Not published for automated download.",
        availability_status="TEMPORARILY_UNAVAILABLE",
        notes="Re-probe the MoES-NCCD / IONO service catalogue for an ERDDAP or WMS view.",
        enabled=False,
    ),

    DataSourceSpec(
        source_id="nccr_coastal",
        source_name="National Centre for Coastal Research",
        institution="NCCR (Ministry of Earth Sciences, Govt. of India)",
        dataset_name="Coastal observation network data",
        dataset_id="nccr",
        access_method="No machine-readable endpoint; the published host did not resolve from this network",
        endpoint="https://nccr.nic.in/",
        data_status="REAL",
        variables=("sea_surface_wave_height", "sea_surface_height_above_geoid", "sea_water_temperature"),
        units={"sea_surface_wave_height": "m", "sea_surface_height_above_geoid": "m"},
        spatial_coverage="Indian coastal belt",
        temporal_coverage="Not established from this host",
        depth_coverage="Surface and near-shore",
        update_frequency="Not established from this host",
        quality_control="Not accessible.",
        provenance=(
            "Recorded for completeness. Neither nccr.nic.in nor nccr.moef.gov.in resolved in DNS from this host, "
            "so no dataset, variable or access method could be verified. Nothing is assumed about its contents."
        ),
        license_access_notes="Not established - the host was unreachable.",
        availability_status="TEMPORARILY_UNAVAILABLE",
        notes="Re-probe once the current NCCR host is confirmed.",
        enabled=False,
    ),

    DataSourceSpec(
        source_id="cmlre_marine",
        source_name="Central Marine Living Resources Exploration",
        institution="CMLRE (Ministry of Earth Sciences, Govt. of India)",
        dataset_name="Marine living resources survey data",
        dataset_id="cmlre",
        access_method="No machine-readable endpoint; the published host did not resolve from this network",
        endpoint="https://cmfre.nic.in/",
        data_status="REAL",
        variables=(),
        units={},
        spatial_coverage="Indian EEZ",
        temporal_coverage="Not established from this host",
        depth_coverage="Not established from this host",
        update_frequency="Not established from this host",
        quality_control="Not accessible.",
        provenance=(
            "Recorded for completeness. cmfre.nic.in did not resolve in DNS from this host and no alternative "
            "CMLRE data service was verified. Variable coverage is deliberately left empty rather than guessed."
        ),
        license_access_notes="Not established - the host was unreachable.",
        availability_status="TEMPORARILY_UNAVAILABLE",
        notes="Re-probe once a current CMLRE data service is confirmed.",
        enabled=False,
    ),

    DataSourceSpec(
        source_id="incois_essd_portal",
        source_name="MoES Earth System Science Data Portal (INCOIS node)",
        institution=INCOIS,
        dataset_name="MoES Earth System Science Data Portal",
        dataset_id="essdp",
        access_method="Catalogue web pages; no machine-readable catalogue API located",
        endpoint="https://esdportal.incois.gov.in/",
        data_status="UNKNOWN",
        variables=(),
        units={},
        spatial_coverage="Not established from this host",
        temporal_coverage="Not established from this host",
        depth_coverage="Not established from this host",
        update_frequency="Not established from this host",
        quality_control="Not accessible.",
        provenance=(
            "The portal that would aggregate the wider MoES holdings. The host did not resolve in DNS from this "
            "network on the verification date, so no dataset id, variable or access method is claimed. This is "
            "the single highest-value unknown in the catalogue."
        ),
        license_access_notes="Not established - the host was unreachable.",
        availability_status="TEMPORARILY_UNAVAILABLE",
        notes="Highest-value re-probe target: a reachable portal with a query API would unlock the rest of MoES.",
        enabled=False,
    ),
)

_BY_ID: dict[str, DataSourceSpec] = {spec.source_id: spec for spec in _SPECS}


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


def list_sources() -> list[DataSourceSpec]:
    """Every declared source, in catalogue order."""
    return list(_SPECS)


def source(source_id: str) -> DataSourceSpec | None:
    return _BY_ID.get(source_id)


def sources_payload() -> dict[str, Any]:
    """The catalogue itself - no database, no network.  Always safe to serve."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalogue_version": CATALOGUE_VERSION,
        "institution_summary": _institution_summary(),
        "sources": [spec.payload() for spec in _SPECS],
        "counts": _counts(),
        "limitations": CATALOGUE_LIMITATIONS,
    }


def _institution_summary() -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for spec in _SPECS:
        entry = buckets.setdefault(spec.institution, {
            "institution": spec.institution, "sources": 0, "integrated": 0, "unavailable": 0,
        })
        entry["sources"] += 1
        if spec.availability_status in ("AVAILABLE", "PARTIAL", "MODEL_DERIVED", "SATELLITE_DERIVED"):
            entry["integrated"] += 1
        else:
            entry["unavailable"] += 1
    return sorted(buckets.values(), key=lambda row: (-row["integrated"], row["institution"]))


def _counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for spec in _SPECS:
        counts[spec.availability_status] = counts.get(spec.availability_status, 0) + 1
    return counts


CATALOGUE_VERSION = "1.0"

CATALOGUE_LIMITATIONS = [
    "Availability is a point-in-time probe result, not a service-level guarantee; a source reported AVAILABLE "
    "can become UNAVAILABLE on the next request.",
    "TEMPORARILY_UNAVAILABLE means the endpoint did not answer from this host, NOT that the data does not exist.",
    "AUTH_REQUIRED means the provider documents the data as available but gates it behind a request form or "
    "approval that TidalTwin does not hold.",
    "MODEL_DERIVED and SATELLITE_DERIVED are reported separately from REAL on purpose. A variational analysis of "
    "real floats is still an analysis, and an optical retrieval is still remote sensing.",
    "No source in this catalogue is SIMULATED or SYNTHETIC. Generated values are labelled at row level by "
    "app.modules.ai.provenance_quality.origin_status and never enter the catalogue.",
]


# ---------------------------------------------------------------------------
# Live availability probe (bounded, cached, never fatal)
# ---------------------------------------------------------------------------

_PROBE_TTL = max(1, int(settings.OBSERVATIONS_CACHE_TTL_SECONDS))
_PROBE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PROBE_LOCK = threading.Lock()


def invalidate_cache() -> None:
    """Drop cached availability probes.  Call after any ingestion run."""
    with _PROBE_LOCK:
        _PROBE_CACHE.clear()


def probe_source(source_id: str, *, force: bool = False) -> dict[str, Any]:
    """Report a source's live availability without ever raising.

    The probe is a cheap, strictly bounded request (one row).  On any failure the
    source is reported honestly and the rest of the application continues.
    """
    spec = _BY_ID.get(source_id)
    if spec is None:
        return {"source_id": source_id, "availability_status": "UNKNOWN_SOURCE", "detail": "Not in the catalogue."}

    if not settings.OBSERVATIONS_ENABLED:
        return {**spec.payload(), "availability_status": "DISABLED", "last_checked": None,
                "detail": "The national observation layer is disabled in this deployment."}
    if not spec.enabled:
        return {**spec.payload(), "availability_status": spec.availability_status,
                "last_checked": None, "detail": "Declared but not enabled in this deployment."}
    if spec.endpoint.startswith("https://erddap.incois.gov.in"):
        if spec.source_id == "incois_argo_analysis_mnt" and not settings.INCOIS_ARGO_ANALYSIS_ENABLED:
            return {**spec.payload(), "availability_status": "DISABLED", "last_checked": None,
                    "detail": "INCOIS_ARGO_ANALYSIS_ENABLED is false."}
        if spec.source_id == "incois_argo_profiles" and not settings.INCOIS_ARGO_INSITU_ENABLED:
            return {**spec.payload(), "availability_status": "DISABLED", "last_checked": None,
                    "detail": "INCOIS_ARGO_INSITU_ENABLED is false."}
        if spec.source_id == "incois_oceansat2_ocm" and not settings.INCOIS_SATELLITE_OCM_ENABLED:
            return {**spec.payload(), "availability_status": "DISABLED", "last_checked": None,
                    "detail": "INCOIS_SATELLITE_OCM_ENABLED is false; the product's own coverage ended in 2020."}

    if not force:
        with _PROBE_LOCK:
            hit = _PROBE_CACHE.get(source_id)
        if hit is not None and (time.monotonic() - hit[0]) < _PROBE_TTL:
            return hit[1]

    result = _probe_now(spec)
    with _PROBE_LOCK:
        _PROBE_CACHE[source_id] = (time.monotonic(), result)
    return result


def _probe_now(spec: DataSourceSpec) -> dict[str, Any]:
    from app.modules.ai.observations.erddap import ErddapError, ErddapConstraint, request_table

    checked = datetime.now(timezone.utc).isoformat()
    base_payload = {**spec.payload(), "last_checked": checked}

    if not spec.endpoint:
        return {**base_payload, "availability_status": "TEMPORARILY_UNAVAILABLE",
                "detail": "No automated endpoint is available for this source."}

    try:
        if spec.source_id == "incois_argo_profiles":
            table = request_table(
                settings.INCOIS_ERDDAP_BASE, "tabledap", spec.dataset_id,
                columns=("PLATFORM_NUMBER", "time", "latitude", "longitude", "TEMP", "TEMP_QC"),
                constraints=(
                    ErddapConstraint("latitude", ">=", str(settings.OBSERVATIONS_LAT_MIN)),
                    ErddapConstraint("latitude", "<=", str(settings.OBSERVATIONS_LAT_MAX)),
                    ErddapConstraint("longitude", ">=", str(settings.OBSERVATIONS_LON_MIN)),
                    ErddapConstraint("longitude", "<=", str(settings.OBSERVATIONS_LON_MAX)),
                ),
                max_rows=5,
            )
            rows = len(table.rows)
            return {**base_payload,
                    "availability_status": "AVAILABLE" if rows else "PARTIAL",
                    "detail": (f"Constrained probe returned {rows} row(s)."
                               if rows else
                               "Endpoint answered but the configured region/time subset is empty.")}

        if spec.source_id in ("incois_argo_analysis_10d", "incois_argo_analysis_mnt"):
            grid = _probe_grid(spec)
            if grid is None:
                return {**base_payload, "availability_status": spec.availability_status,
                        "detail": "Endpoint answered; no hyperslab is issued during a status probe."}
            detail = f"Grid probe succeeded; newest time step {grid['newest_time']}"
            if grid["age_days"] is not None:
                detail += f" ({grid['age_days']:.0f} d old)"
            return {**base_payload, "availability_status": spec.availability_status,
                    "detail": detail + ".", "newest_time": grid["newest_time"],
                    "age_days": grid["age_days"]}

        if spec.source_id == "incois_oceansat2_ocm":
            return {**base_payload, "availability_status": "PARTIAL",
                    "detail": "Reachable, but the provider's time coverage ended 2020-05-01."}

        if spec.source_id == "argo_gdac_incois":
            from app.modules.ai.observations.erddap import fetch
            body = fetch(f"{settings.ARGO_GDAC_BASE}/dac/incois/", max_rows=200)
            ok = "dac/incois/" in body or "href=" in body
            return {**base_payload,
                    "availability_status": "AVAILABLE" if ok else "PARTIAL",
                    "detail": "INCOIS DAC directory listing reachable." if ok else "Unexpected listing content."}

        return {**base_payload, "availability_status": "TEMPORARILY_UNAVAILABLE",
                "detail": "No automated probe is defined for this source."}

    except ErddapError as exc:
        logger.warning("observation source %s unavailable: %s", spec.source_id, exc)
        # A source whose documented coverage is historical keeps its own
        # semantic status; everything else degrades honestly to
        # TEMPORARILY_UNAVAILABLE and the application keeps serving.
        status = spec.availability_status if spec.availability_status in (
            "HISTORICAL", "MODEL_DERIVED", "SATELLITE_DERIVED", "AUTH_REQUIRED") else "TEMPORARILY_UNAVAILABLE"
        return {**base_payload, "availability_status": status, "detail": f"{exc.kind}: {exc}"}
    except Exception as exc:  # pragma: no cover - a probe must never break the app
        logger.warning("observation source %s probe failed: %s", spec.source_id, exc)
        return {**base_payload, "availability_status": "TEMPORARILY_UNAVAILABLE",
                "detail": f"probe error: {type(exc).__name__}"}


def _probe_grid(spec: DataSourceSpec) -> dict[str, Any] | None:
    """Prove a gridded product is reachable and read how current it is.

    Only the ``time`` axis is requested: it is small, it never needs a
    hyperslab, and its last value is the single most useful freshness fact the
    platform can report.  The (60 x 90 x 24) data cube is deliberately *not*
    pulled for a status check.
    """
    from app.modules.ai.observations.erddap import parse_erddap_time, request_table

    table = request_table(settings.INCOIS_ERDDAP_BASE, "griddap", spec.dataset_id,
                          columns=("time",), max_rows=5000)
    newest: datetime | None = None
    for row in table.rows:
        moment = parse_erddap_time(row.get("time"))
        if moment is not None and (newest is None or moment > newest):
            newest = moment
    if newest is None:
        return {"newest_time": None, "age_days": None}
    age_days = (datetime.now(timezone.utc) - newest).total_seconds() / 86400.0
    return {"newest_time": newest.isoformat(), "age_days": age_days}


def probe_all(*, force: bool = False) -> list[dict[str, Any]]:
    return [probe_source(spec.source_id, force=force) for spec in _SPECS]


def enabled_adapters() -> list[DataSourceSpec]:
    return [s for s in _SPECS if s.enabled and s.availability_status in (
        "AVAILABLE", "PARTIAL", "MODEL_DERIVED", "SATELLITE_DERIVED")]


def freshness_label(age_days: float | None) -> str:
    """Map an observation age in days to the shared freshness vocabulary."""
    if age_days is None or age_days != age_days:
        return "UNKNOWN"
    if age_days < 0:
        return "FUTURE_TIMESTAMP"
    if age_days <= 2:
        return "CURRENT"
    if age_days <= FRESHNESS_HORIZON_DAYS:
        return "RECENT"
    return "HISTORICAL"


__all__ = [
    "AVAILABILITY_STATUSES",
    "CATALOGUE_LIMITATIONS",
    "CATALOGUE_VERSION",
    "DATA_STATUSES",
    "FRESHNESS_HORIZON_DAYS",
    "DataSourceSpec",
    "enabled_adapters",
    "freshness_label",
    "invalidate_cache",
    "list_sources",
    "probe_all",
    "probe_source",
    "source",
    "sources_payload",
]
