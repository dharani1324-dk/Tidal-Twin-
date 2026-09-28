"""
TidalTwin - Configuration
=============================
This module reads our settings (mostly from the .env file).
It's the central place where all configuration lives,
so our code never has hard-coded passwords or addresses.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    App settings loaded from the .env file.
    Pydantic automatically reads DATABASE_URL and API_* from .env.
    """

    # Backend root directory (used for server-local NetCDF validation paths).
    BASE_DIR: Path = Path(__file__).resolve().parents[2]

    # Database connection string (required for all data-backed features)
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/tidaltwin"

    # Backend hosting details
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # Project name used in the API metadata
    PROJECT_NAME: str = "TidalTwin"
    # Release identity (NOT a scientific maturity claim - see
    # docs/SCIENTIFIC_LIMITATIONS.md).
    VERSION: str = "1.0.0"
    RELEASE_NAME: str = "TIDE-Loop"

    # "development" | "production" - controls startup warnings/logging verbosity.
    ENVIRONMENT: str = "development"

    # Comma-separated CORS origins. Defaults to "*" so the local demo works
    # out of the box; set explicitly for any real deployment.
    CORS_ORIGINS: str = "*"

    # Optional Cesium Ion token for terrain/imagery. Base globe works without it.
    CESIUM_ION_TOKEN: str = ""

    # ---- Microplastics module -------------------------------------------
    # Master switch. The NOAA NCEI connector needs no key, so the module is
    # enabled by default and degrades honestly when the network is unavailable.
    MICROPLASTICS_ENABLED: bool = True

    # NOAA NCEI global Marine Microplastics collection (ArcGIS Feature Service).
    # Public, open, no key required. Fully overridable for a mirror/proxy.
    MICROPLASTICS_NOAA_URL: str = (
        "https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/"
        "Marine_Microplastics_WGS84/FeatureServer/0"
    )

    # Optional NASA Earthdata token for satellite-derived plastic-signal data.
    # Empty => the connector reports UNAVAILABLE with a reason instead of
    # inventing numbers. This mirrors how the voice module handles absent keys.
    NASA_EARTHDATA_TOKEN: str = ""

    # Optional path to the curated published-literature sample CSV. Empty =>
    # the module uses its bundled ``literature_samples.csv`` (columns and
    # header documented inside that file).
    MICROPLASTICS_LITERATURE_CSV: str = ""

    # Seconds to cache the expensive microplastics aggregate computation.
    MICROPLASTICS_CACHE_TTL_SECONDS: int = 300

    # ---- Dissolved oxygen (deoxygenation) module -------------------------
    # Master switch. All Argo data is open-source and keyless, so the module is
    # enabled by default and degrades honestly when the network is unavailable.
    DEOXYGENATION_ENABLED: bool = True

    # Argo BGC (biogeochemical) profile index.  This is the index that actually
    # lists floats carrying oxygen (``DOXY``); the core index
    # ``ar_index_global_prof.txt`` only ever lists TEMP/PSAL/PRES and therefore
    # contains no oxygen at all.  Served gzip.  Format 2.2, comma-delimited,
    # with a leading block of '#' comment lines.
    DEOXYGENATION_ARGO_INDEX_URL: str = (
        "https://data-argo.ifremer.fr/argo_bio-profile_index.txt.gz"
    )

    # Root that serves the per-profile NetCDF files referenced by the index.
    # The index 'file' column is relative to this root's ``dac/`` directory,
    # e.g. coriolis/6990514/profiles/BR6990514_151.nc
    DEOXYGENATION_ARGO_DAC_ROOT: str = "https://data-argo.ifremer.fr/dac"

    # Retained for compatibility with older deployments; the Ifremer
    # THREDDS tree that used to serve Argo has been retired upstream.
    DEOXYGENATION_THREDDS_FILE_SERVER: str = ""
    DEOXYGENATION_THREDDS_CATALOG: str = ""

    # Seconds to wait on the GDAC index / per-profile NetCDF downloads.
    DEOXYGENATION_HTTP_TIMEOUT_SECONDS: int = 120

    # Local cache directory for downloaded per-profile Argo files.
    # Empty => the module uses ``backend/data/argobgc`` next to the repo layout.
    DEOXYGENATION_DATA_DIR: str = ""

    # Seconds to cache the expensive deoxygenation aggregate computation.
    DEOXYGENATION_CACHE_TTL_SECONDS: int = 300

    # ---- Ocean acidification module --------------------------------------
    # Master switch. Same reasoning as deoxygenation: the primary source is
    # open and keyless, so it is enabled by default and degrades honestly.
    ACIDIFICATION_ENABLED: bool = True

    # The acidification module reads pH from the SAME BGC profile index as
    # deoxygenation - the pH sensors ride the same biogeochemical floats that
    # carry DOXY.  It is a separate setting so a deployment can point the two
    # modules at different mirrors independently.
    ACIDIFICATION_ARGO_INDEX_URL: str = (
        "https://data-argo.ifremer.fr/argo_bio-profile_index.txt.gz"
    )
    ACIDIFICATION_ARGO_DAC_ROOT: str = "https://data-argo.ifremer.fr/dac"

    # Seconds to wait on the GDAC index / per-profile NetCDF downloads.
    ACIDIFICATION_HTTP_TIMEOUT_SECONDS: int = 120

    # Local cache directory for downloaded per-profile Argo files.  Empty =>
    # backend/data/argobgc, deliberately SHARED with the deoxygenation module
    # so a profile pulled for oxygen is not downloaded again for its pH.
    ACIDIFICATION_DATA_DIR: str = ""

    # Seconds to cache the expensive acidification aggregate computation.
    ACIDIFICATION_CACHE_TTL_SECONDS: int = 300

    # Secondary sources. Both are catalogued with honest availability status
    # rather than being silently treated as working; see sources.py.
    ACIDIFICATION_SOCAT_ENABLED: bool = True
    ACIDIFICATION_NOAA_OAP_ENABLED: bool = True

    # Kilometres within which a float profile is attributed to the nearest
    # monitored region.
    #
    # This is deliberately LARGER than the deoxygenation module's 500 km, and
    # the reason is measured rather than assumed. The 8 monitored "regions" are
    # coastal labels standing in for whole basins, and BGC-Argo floats sample
    # open ocean: across 3,245 ingested pH observations the distance to the
    # nearest region runs from 565 km (p10) to 1431 km (max), median 1047 km.
    # At the inherited 500 km radius, ZERO of them would be attributed to any
    # region and the module would report no data for all 8 - which is true but
    # useless, and would misrepresent basin-wide coverage as absent.
    #
    # The attribution is therefore kept, but never anonymous: every row stores
    # `region_distance_km`, every hotspot reports `mean_distance_km`, and the
    # spatial confidence decay is exposed separately from the measurement
    # confidence. An observer of an Arabian Sea float 1000 km from Mumbai is
    # still sampling the Arabian Sea, and the UI says so.
    ACIDIFICATION_REGION_RADIUS_KM: float = 1500.0

    # ---- National ocean observation layer (MoES / INCOIS) -----------------
    # INCOIS (Indian National Centre for Ocean Information Services), an
    # autonomous body under the Ministry of Earth Sciences, operates a public
    # ERDDAP server.  Every endpoint below was verified with a live request
    # before being added; see docs/MOES_INCOIS_INTEGRATION.md for the
    # per-dataset verification log (coverage, freshness, and what is NOT
    # reachable).  Nothing here is invented: if a host is unreachable the
    # registry reports TEMPORARILY_UNAVAILABLE instead of failing the app.
    OBSERVATIONS_ENABLED: bool = True

    # INCOIS ERDDAP root.  Verified: HTTP 200, 17 active datasets.
    INCOIS_ERDDAP_BASE: str = "https://erddap.incois.gov.in/erddap"

    # Per-request timeouts (seconds) and connect timeout.  Every external call
    # is bounded so an unreachable MoES host can never stall a request.
    INCOIS_HTTP_TIMEOUT_SECONDS: int = 60
    INCOIS_HTTP_CONNECT_TIMEOUT_SECONDS: int = 15
    INCOIS_HTTP_RETRIES: int = 2
    INCOIS_RETRY_BACKOFF_SECONDS: float = 1.5

    # Hard cap on rows a single constrained request may return.  The adapters
    # always pass a bounding box + time window + depth limit, so this is a
    # circuit breaker, not the normal path.
    INCOIS_MAX_ROWS: int = 50000

    # Master switches per source, so a deployment can disable an individual
    # remote dataset without touching code.
    INCOIS_ARGO_INSITU_ENABLED: bool = True
    INCOIS_ARGO_ANALYSIS_ENABLED: bool = True
    INCOIS_SATELLITE_OCM_ENABLED: bool = False   # Oceansat-2 OCM: ends 2020-05, off by default

    # Argo Global Data Assembly Centre mirror that carries the INCOIS national
    # Argo Data Centre tree.  Verified: https://data-argo.ifremer.fr/dac/incois/
    ARGO_GDAC_BASE: str = "https://data-argo.ifremer.fr"

    # WMO ids of Indian Argo floats held in the INCOIS GDAC tree, used to mark
    # an observation as institutionally attributable to INCOIS.  Discovered by
    # directory listing, not by assumption; empty => no attribution claim.
    INCOIS_ARGO_WMO_IDS: str = ""

    # Region of interest for automatic ingestion (the northern Indian Ocean
    # box the twin monitors - matches scripts.fetch_argo / scripts.fetch_chlor).
    OBSERVATIONS_LAT_MIN: float = 0.0
    OBSERVATIONS_LAT_MAX: float = 26.0
    OBSERVATIONS_LON_MIN: float = 60.0
    OBSERVATIONS_LON_MAX: float = 100.0

    # Seconds to cache registry availability probes and coverage aggregation.
    OBSERVATIONS_CACHE_TTL_SECONDS: int = 300

    # Tell pydantic to read from a .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def cors_origins(self) -> list[str]:
        """Parse the CORS origins string into a list for the middleware."""
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    def validate_environment(self) -> list[str]:
        """Return human-readable configuration issues (empty list == all good).

        This never raises and never prints secret values.  It is used at startup
        to warn loudly about configuration that would degrade the app.
        """
        issues: list[str] = []
        if not (self.DATABASE_URL or "").strip():
            issues.append("DATABASE_URL is empty - all database-backed features will fail.")
        elif "localhost" in self.DATABASE_URL and self.ENVIRONMENT == "production":
            issues.append("DATABASE_URL still points at localhost while ENVIRONMENT=production.")
        if not (self.CORS_ORIGINS or "").strip():
            issues.append("CORS_ORIGINS is empty - the frontend will be blocked by CORS.")
        if not (self.CESIUM_ION_TOKEN or "").strip():
            issues.append("CESIUM_ION_TOKEN not set - Cesium Ion terrain/imagery is optional and disabled.")
        if not (self.INCOIS_ERDDAP_BASE or "").strip():
            issues.append("INCOIS_ERDDAP_BASE is empty - national MoES observation sources report UNAVAILABLE.")
        elif not (self.INCOIS_ERDDAP_BASE or "").startswith("https://"):
            issues.append("INCOIS_ERDDAP_BASE is not HTTPS - MoES observation ingestion is disabled for safety.")
        return issues


# A single shared settings object the whole app can import.
settings = Settings()
