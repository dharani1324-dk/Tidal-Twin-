# TIDE Voice Agent

Realtime speech-to-speech assistant for the TidalTwin platform. Tap the floating
orb, talk naturally, and the agent drives the **existing** platform — the globe,
TIDE, forensics, anomaly radar, what-if, replay and validation — using the same
API endpoints the UI already calls. It never fabricates ocean data: every
data-bearing answer comes from a real endpoint and every answer carries its
provenance (`source`, `confidence`, `limitations`).

- **No new AI systems.** The voice model is an orchestration layer over the
  existing Copilot fallback and public APIs. Nothing is persisted.
- **Keys stay on the backend.** Both `OPENAI_API_KEY` and `GEMINI_API_KEY` are
  only used server-side to mint short-lived **ephemeral** credentials; the
  browser talks to the model provider directly for low latency, but the secret
  never leaves the server.

---

## 1. Architecture

The default provider is **Gemini Live** (WebSocket transport). The OpenAI
Realtime (WebRTC) provider is retained as a drop-in secondary and selected when
no Gemini key is configured.

```
speech → (mic 16 kHz PCM16) → WS realtimeInput.frame → Gemini Live (ephemeral token)
              ↕  JSON setup / serverContent / functionCall / toolResponse frames
browser    GeminiClient  +(orchestrates)
              ↕
     TideVoiceSession  — executes model function calls
              ↕                        ↕
     voiceTools (34+ tidetwin.* tools)  voiceBus / voiceContext
              ↕                        ↕
     existing backend REST API          React pages (DigitalTwin, …)
```

| Layer | File | Role |
|---|---|---|
| Transport | `frontend/src/services/voice/geminiClient.ts` | Mic capture (16 kHz PCM16), live WS `realtimeInput`, 24 kHz PCM output, audio levels. `realtimeClient.ts` is the retained OpenAI/WebRTC transport (unused by default) |
| Session | `frontend/src/services/voice/voiceSession.ts` | Ephemeral session, model-driven function calls, transcript, phase machine, Copilot fallback |
| Tools | `frontend/src/services/voice/voiceTools.ts` | Executor registry mapping model tool names → backend APIs |
| Routing | `frontend/src/services/voice/router.ts` | Free-text intent → command (Copilot fallback) |
| Context | `frontend/src/services/voice/voiceContext.ts` | Page-then-location context shared with the model + place resolution |
| Bus | `frontend/src/services/voice/voiceBus.ts` | Short-lived TTL command bus (UI events) |
| Validation | `frontend/src/services/voice/jsonSchema.ts` | JSON-Schema-ish arg validation for every tool call |
| Locations | `frontend/src/services/voice/gazetteer.ts` | Place-name matching + haversine helpers |
| Hook | `frontend/src/hooks/useTideVoice.ts` | React lifecycle: status, start/stop/clear, audio levels |
| UI | `frontend/src/components/voice/` | `TideVoiceAgent` (root), `VoiceOrb`, `VoiceTranscript`, `VoiceStatus`, `voice.css` |
| Backend | `backend/app/modules/voice/` + `app/api/voice.py` | Session minting, tool JSON-Schema, prompt assembly, health |
| Web search | `app/api/voice.py` → DuckDuckGo | Keyless instant answers (flagged `WEB`) |

### Security model

- `POST /api/v1/voice/session` — backend validates config, builds the system
  prompt + fastapi schema for the tool executor (34 tools), and mints an
  **ephemeral credential** for the configured provider:
  - **Gemini (default):** `POST /v1beta/auth_tokens` with an
    `x-goog-api-key` + 30-minute expiry and a server-locked
    `bidiGenerateContentSetup` (model, system prompt, `responseModalities:
    ["AUDIO"]`, voice, transcription, 34 `functionDeclarations`). Returns
    `{ model, voice, session_id, ephemeral_key:{value, expires_at},
      instructions_bytes, tools, includes_context, setup }` where `setup`
    is the exact frame the browser must echo as its first WS message.
  - **OpenAI (secondary):** `POST /realtime/client_secrets` GA session config
    (`type: "realtime"`, audio codec/VAD nested under `audio.input` /
    `audio.output`, 600s expiry; falls back to the flat legacy
    `/realtime/sessions` endpoint).
- Gemini provider: the browser opens
  `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained?access_token=<value>`,
  sends the echoed `setup` frame, streams `realtimeInput.audio` and answers
  `toolCall` frames with `toolResponse` frames. The 34 function
  declarations are validated against Gemini's live schema server-side
  (OpenAI-only keys like `additionalProperties` are stripped).
- The browser stores only the ephemeral credential in memory. `GET
  /api/v1/voice/status` — capability + provider + enabled state (no secrets).
- `POST /api/v1/voice/web-search` — server-side DuckDuckGo query so the browser
  never needs an external key. Results are always surfaced as `WEB`-sourced so
  they are never confused with ocean data.

---

## 2. Backend

### Files

- `backend/app/api/voice.py` — `/api/v1/voice/session`, `/api/v1/voice/status`,
  `/api/v1/voice/web-search`; `VoiceSessionError` → 400 (with `status_code`).
- `backend/app/modules/voice/__init__.py` — capability flag.
- `backend/app/modules/voice/tools.py` — the model-vocabulary (tool list, JSON
  schemas, parameter defaults, prompt text; `tool_payloads_gemini()` emits
  live-schema-safe `functionDeclarations`).
- `backend/app/modules/voice/agent.py` — invocation → endpoint call
  (`create_gemini_session`, `create_realtime_session`, `_post_gemini`, …).
- `backend/app/modules/voice/context.py` — merge/snapshot/clear of the page +
  location context received from browsers.
- `backend/app/schemas/voice.py`, `backend/app/core/config.py`,
  `backend/app/api/health.py` — Pydantic models, provider settings,
  provider-aware `voice_enabled()` health check.

### Configuration (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `VOICE_PROVIDER` | `auto` | `auto` (Gemini if `GEMINI_API_KEY` set, else OpenAI if `OPENAI_API_KEY` set), `gemini`, `openai`, `off` |
| `GEMINI_API_KEY` | *(empty)* | Enables the Gemini Live provider |
| `GEMINI_LIVE_BASE_URL` | `https://generativelanguage.googleapis.com` | Provisioning host |
| `GEMINI_LIVE_MODEL` | `gemini-3.1-flash-live-preview` | Live model deployed to the key |
| `GEMINI_LIVE_VOICE` | `Kore` | Prebuilt voice name |
| `OPENAI_API_KEY` | *(empty)* | Enables the secondary OpenAI provider |
| `OPENAI_REALTIME_BASE_URL` | `https://api.openai.com/v1` | Realtime API base |
| `OPENAI_REALTIME_MODEL` | `gpt-realtime` | Realtime model deployed to the key |
| `OPENAI_REALTIME_VOICE` | `cedar` | Male voice (`cedar`/`marin`) |
| `VOICE_AGENT_ENABLED` | `auto` | `auto` (key? on : off), `on`, `off` |

### Tools the model can call (voiceTools executor)

Tool names use only letters, digits and underscores — a rule shared by the
OpenAI GA API and Gemini (`^[a-zA-Z0-9_]+$`). Actual registry (34 tools):

| Group | Tools |
|---|---|
| `tidetwin_*` (browser API-client adapters / context registry) | `tidetwin_get_project_status`, `tidetwin_get_ui_context`, `tidetwin_get_data_sources`, `tidetwin_get_region_overview`, `tidetwin_get_ocean_field`, `tidetwin_get_depth_profile`, `tidetwin_get_observations`, `tidetwin_get_satellite_observations`, `tidetwin_get_argo_observations`, `tidetwin_get_anomalies`, `tidetwin_get_anomaly_statistics`, `tidetwin_get_events`, `tidetwin_investigate_event`, `tidetwin_get_event_timeline`, `tidetwin_get_tide_candidates`, `tidetwin_get_tide_explanation`, `tidetwin_get_tide_evidence`, `tidetwin_get_tide_verdict`, `tidetwin_get_tide_uncertainty`, `tidetwin_recommend_next_observation`, `tidetwin_get_event_context`, `tidetwin_get_replay`, `tidetwin_get_validation_status`, `tidetwin_run_whatif`, `tidetwin_compare_scenarios`, `tidetwin_get_model_comparison` |
| `ui_*` (voice command bus) | `ui_focus_region`, `ui_set_depth`, `ui_set_time`, `ui_set_variable`, `ui_toggle_layer`, `ui_navigate`, `ui_reveal_panel` |
| `web_search` | keyless web search (always `WEB` flagged) |

Executors validate args (unknown tool → error), derive the place from

1. explicit `location_id` → 2. named region (monitored + gazetteer) → 3. coords
→ 4. current context focus, and return `{status, source, feedback, data,
confidence?, limitations[]}` formatted for the model.

---

## 3. Frontend

### Setup

- Add to `backend/.env`:

  ```
  GEMINI_API_KEY=AIza...
  GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
  GEMINI_LIVE_VOICE=Kore
  # or the secondary provider:
  # OPENAI_API_KEY=sk-...
  # OPENAI_REALTIME_MODEL=gpt-realtime
  ```

- Start the stack as usual. The orb appears bottom-right (left of the Assistant
  FAB) when the backend reports the capability.

### Gemini Live transport (frontend)

- `geminiClient.ts` — `start({accessToken, setup})` opens the constrained WS
  with `?access_token=`, echoes the backend `setup` frame, captures 16 kHz mic
  audio (ScriptProcessor + linear resample), sends audio as base64
  `realtimeInput.audio` frames, resamples server PCM to 48 kHz and plays through
  scheduled `AudioBufferSource`s, and reports input/output `AudioLevels`.
- `voiceSession.ts` maps Gemini events to the existing session contract:
  `session_ready`, `user_turn`, `assistant_transcript` (streaming),
  `input_audio_transcription.completed`, `interrupted`, `turnComplete`, and
  `toolCall` → batched `executeTool` → single `toolResponse` frame.
- Temperature is not used to play domain audio; the browser only produces
  speech for the selected prebuilt voice.

### Voice commands handled by pages

| Command (bus) | Handler |
|---|---|
| `voice:focus` | DigitalTwin snaps the globe and leaves a marker |
| `voice:set-depth` | snaps depth to nearest modelgrid depth + enables its layer |
| `voice:set-time` | moves the timeline (start / end / now / hours ago) |
| `voice:set-variable` | switches the globe variable |
| `voice:toggle-layer` | toggles a layer |
| `voice:navigate` | App shell routes to a page |
| `voice:reveal-panel` | scrolls to + flashes a panel |

### Try it

Tap the orb (requests mic access), then:

- “focus the Bay of Bengal” — globe flies there.
- “what is the TIDE verdict here?” — real `tide/verdict` data for the focused
  region.
- “what happened at event 1?” / “replay it” — forensics + decision replay.
- “show me the latest ARGO floats in the Arabian Sea”.
- “go to the tide page” — routes reliably.
- “why did the model disagree with observations at Goa?” — disagreement tool.
- General questions (non-ocean) return `WEB`-flagged answers via the keyless
  search.

---

## 4. Governance

- Every tool response is **unwrapped defensively** and streamed back to the
  model as the *only* truth the voice prompt may quote.
- Poorly-formed or out-of-vocabulary requests return explicit error feedback
  (“Say a place or ‘here’”).
- Realtime connection failure auto-falls back to the existing **Copilot text
  assistant** — the platform is fully usable with the voice agent disabled.

## 5. Tests

- Backend: `backend/tests/test_voice.py` (28 voice tests incl. the Gemini mint /
  declaration shaping; full suite 235 passing) —
  `python -m unittest discover -s tests` from `backend/`.
- Frontend: `tests/voice.test.ts` — gazetteer, JSON-schema validation, intent
  router, voice bus (TTL + replay + clear), context registry and resolution
  (43 tests total across `tests/`), plus `tsc -b`, `oxlint`, `vite build`.