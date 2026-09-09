"""
OceanVerse AI - Configuration
=============================
This module reads our settings (mostly from the .env file).
It's the central place where all configuration lives,
so our code never has hard-coded passwords or addresses.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    App settings loaded from the .env file.
    Pydantic automatically reads DATABASE_URL and API_* from .env.
    """

    # Database connection string
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/oceanverse"

    # Backend hosting details
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # Project name used in the API metadata
    PROJECT_NAME: str = "OceanVerse AI"
    VERSION: str = "0.1.0"

    # Tell pydantic to read from a .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# A single shared settings object the whole app can import.
settings = Settings()
