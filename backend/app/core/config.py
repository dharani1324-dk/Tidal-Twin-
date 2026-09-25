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
        return issues


# A single shared settings object the whole app can import.
settings = Settings()
