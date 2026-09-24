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

    # ---- TIDE Voice Agent (optional realtime voice layer) ----------------
    # The voice agent is a façade over the existing platform.  Set GEMINI_API_KEY
    # (or OPENAI_API_KEY for the legacy WebRTC engine) to enable the realtime
    # voice assistant; without either the frontend degrades to the existing
    # Copilot text fallback.  The browser only ever receives short-lived
    # EPHEMERAL keys - never this project key.
    # "auto" selects the first configured provider (Gemini preferred); set
    # explicitly to "gemini" or "openai" to force one.
    VOICE_PROVIDER: str = "auto"
    # Gemini Live (primary provider). Temp tokens/voice/sessions are minted on
    # this backend via the provisioning API; the browser WebSockets straight to
    # Google with the short-lived token.
    GEMINI_API_KEY: str = ""
    GEMINI_LIVE_BASE_URL: str = "https://generativelanguage.googleapis.com"
    GEMINI_LIVE_MODEL: str = "gemini-3.1-flash-live-preview"
    GEMINI_LIVE_VOICE: str = "Kore"
    # OpenAI Realtime (legacy/secondary provider, WebRTC transport).
    OPENAI_API_KEY: str = ""
    OPENAI_REALTIME_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_REALTIME_MODEL: str = "gpt-realtime"
    OPENAI_REALTIME_VOICE: str = "cedar"
    # "auto" enables voice when the selected provider's key is set; "on"/"off"
    # force the state.
    VOICE_AGENT_ENABLED: str = "auto"

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

    def provider(self) -> str:
        """Which realtime voice engine this backend talks to.

        Returns ``"gemini"``, ``"openai"`` or ``"none"``.  With
        ``VOICE_PROVIDER=auto`` Gemini wins whenever its key is configured,
        otherwise OpenAI.  An explicit value forces that engine.
        """
        explicit = (self.VOICE_PROVIDER or "auto").strip().lower()
        has_gemini = bool((self.GEMINI_API_KEY or "").strip())
        has_openai = bool((self.OPENAI_API_KEY or "").strip())
        if explicit == "gemini":
            return "gemini"
        if explicit == "openai":
            return "openai"
        if has_gemini:
            return "gemini"
        if has_openai:
            return "openai"
        return "none"

    def provider_configured(self) -> bool:
        """Whether the selected provider has its API key set."""
        provider = self.provider()
        if provider == "gemini":
            return bool((self.GEMINI_API_KEY or "").strip())
        if provider == "openai":
            return bool((self.OPENAI_API_KEY or "").strip())
        return False

    def voice_model(self) -> str:
        """The realtime model name of the selected provider (for status/UIs)."""
        return self.GEMINI_LIVE_MODEL if self.provider() == "gemini" else self.OPENAI_REALTIME_MODEL

    def voice_voice(self) -> str:
        """The realtime voice name of the selected provider (for status/UIs)."""
        return self.GEMINI_LIVE_VOICE if self.provider() == "gemini" else self.OPENAI_REALTIME_VOICE

    def voice_enabled(self) -> bool:
        """Whether the realtime voice agent may start sessions."""
        mode = (self.VOICE_AGENT_ENABLED or "auto").strip().lower()
        if self.provider() not in ("gemini", "openai"):
            return False
        if mode == "on":
            return self.provider_configured()
        if mode == "off":
            return False
        return self.provider_configured()

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
        if self.voice_enabled():
            provider = self.provider()
            model = (self.GEMINI_LIVE_MODEL if provider == "gemini" else self.OPENAI_REALTIME_MODEL) or ""
            if not model.strip():
                issues.append(f"Voice model is empty while the {provider} voice agent is enabled.")
        else:
            issues.append(
                "Voice agent is disabled (neither GEMINI_API_KEY nor OPENAI_API_KEY set). The Copilot text fallback remains fully available."
            )
        return issues


# A single shared settings object the whole app can import.
settings = Settings()
