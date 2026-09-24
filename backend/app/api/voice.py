"""TIDE Voice Agent - backend service endpoints.

Three thin endpoints power a realtime voice layer over the EXISTING platform:

1. ``GET /api/v1/voice/status`` - what the voice agent can do, which tools it
   routes, and whether the Realtime engine is reachable/configured.
2. ``POST /api/v1/voice/session`` - mints an OpenAI Realtime EPHEMERAL session
   key.  The project API key never leaves the backend; the browser receives a
   short-lived key it can hold directly.
3. ``POST /api/v1/voice/web-search`` - keyless server-side web search
   (DuckDuckGo Instant Answer API) for Category D questions about current,
   outside-world information.

Nothing here writes to the observation store, creates tables, or duplicates
existing data endpoints - the voice layer is an INTERACTION façade.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.voice import context as voice_context
from app.modules.voice import tools as voice_tools
from app.modules.voice.agent import (
    VoiceSessionError,
    build_instructions,
    create_gemini_session,
    create_realtime_session,
)
from app.schemas.voice import (
    VoiceSessionRequest,
    VoiceSessionResponse,
    WebSearchHit,
    WebSearchRequest,
    WebSearchResponse,
)

router = APIRouter(prefix="/api/v1/voice", tags=["Voice Agent"])

# How many of the registered tools we expose to the Realtime session.
_DEFAULT_TOOL_LIMIT = 36


def _status_payload(db: Session) -> dict:
    provider = settings.provider()
    model = settings.voice_model()
    voice = settings.voice_voice()
    if provider == "gemini":
        engine_blurb = "sessions are Gemini Live tokens; audio WebSockets straight to Google from the browser"
    elif provider == "openai":
        engine_blurb = "audio runs directly between the browser and OpenAI Realtime over WebRTC"
    else:
        engine_blurb = "no realtime engine is configured"
    return {
        "enabled": settings.voice_enabled(),
        "provider": provider,
        "model": model,
        "voice": voice,
        "tool_count": len(voice_tools.TOOL_SPECS),
        "tool_names": voice_tools.tool_names(),
        "ui_layers": list(voice_tools.UI_LAYERS),
        "ui_pages": list(voice_tools.UI_PAGES),
        "provenance": [
            "All ocean data comes from existing TidalTwin endpoints and is never invented by the voice model.",
            "Each data value reports REAL / HISTORICAL / SIMULATED / SYNTHETIC / MODEL_DERIVED provenance.",
            "TIDE recommendations follow the existing TIDE-Loop engine; nothing is recomputed or duplicated.",
        ],
        "limitations": [
            f"Requires {provider.upper() if provider != 'none' else 'a provider'} API key on the backend; {engine_blurb}.",
            "Simulated/demo data is clearly labelled, never reported as real.",
            "In the browser the voice UI degrades to the TidalTwin Copilot text fallback when the microphone or the realtime engine is unavailable.",
        ],
    }


@router.get("/status")
def voice_status(db: Session = Depends(get_db)) -> dict:
    """Voice agent capability + configuration, for the browser to show."""
    payload = _status_payload(db)
    payload["database"] = "healthy" if settings.voice_enabled() else "ready"
    return payload


@router.post("/session", response_model=VoiceSessionResponse)
def voice_session(
    request: VoiceSessionRequest,
    db: Session = Depends(get_db),
) -> VoiceSessionResponse:
    """Create a realtime ephemeral session for the browser.

    The provider is chosen by configuration (Gemini Live WebSocket by default
    when ``GEMINI_API_KEY`` is set; OpenAI Realtime WebRTC as the legacy
    provider).  The returned ephemeral credential is held only by the browser;
    the project API key stays on this backend.
    """
    instructions = build_instructions(request.brief)
    if request.include_context:
        synopsis = voice_context.tide_synopsis(db)
        if synopsis:
            instructions += (
                "\n\nSITUATIONAL CONTEXT (read-only snapshot, generated at "
                + synopsis.get("generated_at", "")
                + "). Treat as current state to ground your answer: "
                + str(synopsis)
            )
    tools = voice_tools.tool_payloads()[: _DEFAULT_TOOL_LIMIT]
    if request.brief:
        brief = request.brief[:120]
    else:
        brief = None
    session = None
    if settings.provider() == "gemini":
        try:
            session = create_gemini_session(
                tools=voice_tools.tool_payloads_gemini()[: _DEFAULT_TOOL_LIMIT],
                instructions=instructions,
                brief=brief,
            )
            model = settings.GEMINI_LIVE_MODEL
            voice = settings.GEMINI_LIVE_VOICE
        except VoiceSessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            session = create_realtime_session(tools=tools, instructions=instructions, brief=brief)
            model = settings.OPENAI_REALTIME_MODEL
            voice = settings.OPENAI_REALTIME_VOICE
        except VoiceSessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return VoiceSessionResponse(
        model=model,
        voice=voice,
        session_id=session.get("session_id"),
        ephemeral_key={"value": session["value"], "expires_at": session.get("expires_at")},
        instructions_bytes=len(instructions.encode("utf-8")),
        ips=[],
        tools=tools,
        includes_context=bool(request.include_context),
        setup=session.get("setup"),
    )


def _flatten_ddg(topic: dict, out: list[dict]) -> None:
    for item in topic.get("Topics", []) or []:
        _flatten_ddg(item, out)
    text = topic.get("Text")
    first_url = topic.get("FirstURL")
    if text and first_url:
        out.append({"title": topic.get("Result") or text[:80], "url": first_url, "snippet": text})


@router.post("/web-search", response_model=WebSearchResponse)
def voice_web_search(request: WebSearchRequest) -> WebSearchResponse:
    """Keyless web search (DuckDuckGo Instant Answer icon-URL API).

    Answers Category D questions about the current outside world without
    adding API keys to the platform.
    """
    endpoint = "https://api.duckduckgo.com/"
    params = {
        "q": request.query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
        "t": "tidal-twin-voice",
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        return WebSearchResponse(
            status="error",
            query=request.query,
            source="web",
            limitations=[f"Web search endpoint returned HTTP {exc.response.status_code}."],
        )
    except httpx.RequestError as exc:
        return WebSearchResponse(
            status="error",
            query=request.query,
            source="web",
            limitations=[f"Web search is unreachable ({type(exc).__name__})."],
        )

    results: list[dict] = []
    for topic in data.get("RelatedTopics", []) or []:
        _flatten_ddg(topic, results)
        if len(results) >= request.max_results:
            break

    answer = data.get("AbstractText") or None
    abstract_url = data.get("AbstractURL") or None
    if answer and abstract_url and len(results) < request.max_results:
        results.append({"title": "Abstract", "url": abstract_url, "snippet": answer[:220]})

    hits = [
        WebSearchHit(title=r["title"][:200], url=r["url"], snippet=r["snippet"][:300])
        for r in results[: request.max_results]
    ]
    if answer or hits:
        return WebSearchResponse(
            status="ok",
            query=request.query,
            answer=answer,
            results=hits,
            source="web",
            limitations=["Web results come from the public DuckDuckGo Instant Answer API - summaries, not subscriptions."],
        )
    return WebSearchResponse(
        status="no_results",
        query=request.query,
        source="web",
        limitations=["The web search returned nothing useful for this query."],
    )


