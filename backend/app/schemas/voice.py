"""TIDE Voice Agent API schemas.

Contracts for the voice add-on endpoints.  Minimal on purpose: the heavy
session state lives in the browser voice client; the backend only signs
ephemeral sessions and answers server-side web searches.
"""

from pydantic import BaseModel, Field


class VoiceSessionRequest(BaseModel):
    """Optional situational hint scraped by the browser for the session
    instructions.  Never contains secrets or full user transcripts."""

    brief: str | None = Field(None, max_length=500, description="Short one-line situational note for the session prompt.")
    include_context: bool = Field(
        False,
        description="When true, the backend appends a compact read-only synopsis of current TidalTwin data to the instructions.",
    )


class EphemeralSecret(BaseModel):
    value: str = Field(..., description="Short-lived session credential issued to the browser.")
    expires_at: float | None = None


class VoiceSessionResponse(BaseModel):
    model: str
    voice: str
    session_id: str | None = None
    ephemeral_key: EphemeralSecret
    instructions_bytes: int
    ips: list[str]
    tools: list[dict]
    includes_context: bool = False
    setup: dict | None = Field(None, description="Provider session contract to send as the first WS frame (Gemini default).")


class WebSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=250)
    max_results: int = Field(3, ge=1, le=5)


class WebSearchHit(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    status: str = Field(..., description="ok | no_results | error")
    query: str
    answer: str | None = None
    results: list[WebSearchHit] = []
    source: str = "web"
    limitations: list[str] = []