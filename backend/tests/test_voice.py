"""TIDE Voice Agent - backend tests.

Covers: the /api/v1/voice/* contract, tool-registry parameter validation,
Realtime session creation (including fallback + error mapping), the rule that
the project API key never leaks, and the keyless web-search endpoint.
"""

import unittest
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.modules.voice import tools
from app.modules.voice.agent import VoiceSessionError


def _httpx_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/realtime/sessions")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


class FakeDdgResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeDdgClient:
    def __init__(self, payload):
        self._payload = payload
        self.captured = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None):
        self.captured = (url, params)
        return FakeDdgResponse(self._payload)


class ToolRegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = {spec["name"]: spec for spec in tools.TOOL_SPECS}

    def test_every_spec_is_openai_shape(self):
        for spec in tools.TOOL_SPECS:
            self.assertEqual(spec["type"], "function")
            self.assertIn("name", spec)
            self.assertIn("description", spec)
            self.assertIn("parameters", spec)
            params = spec["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertIsInstance(params["properties"], dict)
            self.assertEqual(params.get("additionalProperties"), False)

    def test_gemini_function_declarations_shape(self):
        declarations = tools.tool_payloads_gemini()
        self.assertEqual(len(declarations), len(tools.TOOL_SPECS))
        for decl in declarations:
            self.assertNotIn("type", decl)
            self.assertIn("name", decl)
            self.assertIn("description", decl)
            self.assertIn("parameters", decl)
            self.assertEqual(decl["parameters"]["type"], "object")
        names = {d["name"] for d in declarations}
        for tool in ("tidetwin_get_tide_candidates", "web_search", "ui_focus_region"):
            self.assertIn(tool, names)

    def test_gemini_declarations_drop_openai_only_schema_keys(self):
        # The Live wire parser rejects unknown proto fields (1007 close), so
        # OpenAI-only keys such as additionalProperties must never reach it.
        declarations = tools.tool_payloads_gemini()
        seen = []

        def walk(node):
            if isinstance(node, dict):
                if "additionalProperties" in node:
                    seen.append(node["additionalProperties"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        for decl in declarations:
            walk(decl["parameters"])
        self.assertEqual(seen, [])

    def test_ui_enums_cover_existing_vocabulary(self):
        expected_pages = ("home", "globe", "tide", "replay", "validation", "anomalies",
                          "forensics", "scenarios", "intelligence", "monitoring",
                          "assistant", "safety", "reports", "stories", "coastal")
        for name in expected_pages:
            self.assertIn(name, tools.UI_PAGES)
        expected_layers = ("temperature", "waves", "currents", "storm", "anomalies",
                           "tide", "realArgo", "realSST", "realChl", "disagreement",
                           "modelgrid", "glider", "isos", "vectors")
        for name in expected_layers:
            self.assertIn(name, tools.UI_LAYERS)
        for variable in ("temperature", "wave_height", "salinity", "chlorophyll"):
            self.assertIn(variable, tools.OCEAN_VARIABLES)

    def test_required_core_tools_exist(self):
        for name in (
            "tidetwin_get_project_status",
            "tidetwin_get_ui_context",
            "tidetwin_get_data_sources",
            "tidetwin_get_region_overview",
            "tidetwin_get_ocean_field",
            "tidetwin_get_depth_profile",
            "tidetwin_get_observations",
            "tidetwin_get_satellite_observations",
            "tidetwin_get_argo_observations",
            "tidetwin_get_anomalies",
            "tidetwin_get_anomaly_statistics",
            "tidetwin_get_events",
            "tidetwin_investigate_event",
            "tidetwin_get_event_timeline",
            "tidetwin_get_tide_candidates",
            "tidetwin_get_tide_explanation",
            "tidetwin_get_tide_evidence",
            "tidetwin_get_tide_verdict",
            "tidetwin_get_tide_uncertainty",
            "tidetwin_recommend_next_observation",
            "tidetwin_get_replay",
            "tidetwin_get_validation_status",
            "tidetwin_run_whatif",
            "tidetwin_compare_scenarios",
            "tidetwin_get_model_comparison",
            "web_search",
            "ui_focus_region",
            "ui_set_depth",
            "ui_set_time",
            "ui_set_variable",
            "ui_toggle_layer",
            "ui_navigate",
            "ui_reveal_panel",
        ):
            self.assertIn(name, self.registry, f"missing core tool {name}")

    def test_validate_accepts_valid_args(self):
        ok, err = tools.validate_tool_args("ui_set_depth", {"depth_m": 100})
        self.assertTrue(ok, err)
        ok, err = tools.validate_tool_args("ui_set_time", {"label": "now"})
        self.assertTrue(ok, err)
        ok, err = tools.validate_tool_args(
            "tidetwin_get_observations", {"region": "Bay of Bengal", "limit": 5}
        )
        self.assertTrue(ok, err)
        ok, err = tools.validate_tool_args("web_search", {"query": "current Indian Ocean cyclone"})
        self.assertTrue(ok, err)

    def test_validate_rejects_bad_args(self):
        self.assertFalse(tools.validate_tool_args("nope", {})[0])
        self.assertFalse(tools.validate_tool_args("ui_set_depth", {})[0])
        self.assertFalse(tools.validate_tool_args("ui_set_depth", {"depth_m": "deep"})[0])
        self.assertFalse(tools.validate_tool_args("ui_set_depth", {"depth_m": -5})[0])
        self.assertFalse(tools.validate_tool_args("ui_set_time", {"label": "yesterday"})[0])
        self.assertFalse(tools.validate_tool_args("ui_set_variable", {"variable": "invention"})[0])
        self.assertFalse(tools.validate_tool_args("ui_toggle_layer", {"layer": "photoshop"})[0])
        self.assertFalse(tools.validate_tool_args("web_search", {"query": ""})[0])
        self.assertFalse(tools.validate_tool_args("ui_navigate", {"page": "atlantis"})[0])
        self.assertFalse(tools.validate_tool_args("tidetwin_get_observations", {"region": "x", "limit": 500})[0])
        self.assertFalse(tools.validate_tool_args("ui_set_depth", {"depth_m": 100, "sneaky": 1})[0])
        self.assertFalse(tools.validate_tool_args("ui_set_depth", [] )[0])

    def test_get_tool_and_payloads(self):
        self.assertIsNone(tools.get_tool("missing"))
        self.assertEqual(tools.get_tool("web_search")["name"], "web_search")
        payloads = tools.tool_payloads()
        self.assertEqual(len(payloads), len(tools.TOOL_SPECS))
        self.assertEqual(len(tools.tool_names()), len(tools.TOOL_SPECS))


class VoiceStatusTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)

    def test_status_shape_and_provenance(self):
        res = self.client.get("/api/v1/voice/status")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn(body["enabled"], (True, False))
        self.assertIn("provider", body)
        self.assertIn(body["provider"], ("gemini", "openai", "none"))
        self.assertIn("model", body)
        self.assertIn("voice", body)
        self.assertGreaterEqual(body["tool_count"], 30)
        self.assertNotIn("OPENAI", "".join(body["tool_names"]).upper())
        for tool in ("tidetwin_get_tide_candidates", "web_search", "ui_focus_region"):
            self.assertIn(tool, body.get("tool_names", []))
        self.assertTrue(any("never invented" in p for p in body.get("provenance", [])))
        self.assertTrue(body.get("limitations"))

    def test_status_never_exposes_key_verb(self):
        res = self.client.get("/api/v1/voice/status")
        self.assertNotIn("sk-", res.text)
        self.assertNotIn("authorization", res.text.lower())


class VoiceSessionTests(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)
        self._orig_key = settings.OPENAI_API_KEY
        self._orig_auto = settings.VOICE_AGENT_ENABLED
        self._orig_provider = settings.VOICE_PROVIDER
        settings.OPENAI_API_KEY = "sk-project-placeholder"
        settings.VOICE_AGENT_ENABLED = "auto"
        settings.VOICE_PROVIDER = "openai"

    def tearDown(self):
        settings.OPENAI_API_KEY = self._orig_key
        settings.VOICE_AGENT_ENABLED = self._orig_auto
        settings.VOICE_PROVIDER = self._orig_provider

    def _session_payload_fake(self, value="ek_realtime_secret", session_id="sess_1"):
        return {"id": session_id, "client_secret": {"value": value, "expires_at": 9999999999.0}}

    def test_session_returns_ephemeral_key_and_tools(self):
        with mock.patch("app.modules.voice.agent._post_openai", return_value=self._session_payload_fake()) as post:
            res = self.client.post("/api/v1/voice/session", json={})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["ephemeral_key"]["value"], "ek_realtime_secret")
        self.assertEqual(body["session_id"], "sess_1")
        self.assertGreater(body["instructions_bytes"], 500)
        self.assertGreater(len(body["tools"]), 0)
        self.assertEqual(body["model"], settings.OPENAI_REALTIME_MODEL)
        self.assertEqual(body["voice"], settings.OPENAI_REALTIME_VOICE)
        self.assertEqual(post.call_count, 1)
        sent = post.call_args.args[1]
        self.assertIn("session", sent)
        self.assertIn("expires_after", sent)
        self.assertEqual(sent["expires_after"], {"anchor": "created_at", "seconds": 600})
        session = sent["session"]
        self.assertEqual(session["type"], "realtime")
        self.assertIn("instructions", session)
        self.assertIn("You are TIDE Voice", session["instructions"])
        self.assertTrue(session["audio"]["input"]["turn_detection"]["interrupt_response"])
        self.assertEqual(session["audio"]["input"]["format"], {"rate": 24000, "type": "audio/pcm"})
        self.assertEqual(session["audio"]["input"]["transcription"]["model"], "gpt-realtime-whisper")
        self.assertEqual(session["audio"]["output"]["voice"], settings.OPENAI_REALTIME_VOICE)
        self.assertEqual(session["audio"]["output"]["format"], {"rate": 24000, "type": "audio/pcm"})

    def test_project_key_never_leaks_to_browser(self):
        with mock.patch("app.modules.voice.agent._post_openai", return_value=self._session_payload_fake()):
            res = self.client.post("/api/v1/voice/session", json={})
            text = res.text.lower()
        self.assertNotIn("sk-project-placeholder", text)
        self.assertNotIn("openai_api_key", text)

    def test_fallback_to_legacy_sessions_when_client_secrets_absent(self):
        calls = []
        def fake_post(path, payload, api_key):
            calls.append((path, payload))
            if path == "/realtime/client_secrets":
                raise _httpx_error(404)
            return {"client_secret": {"value": "ek_fallback", "expires_at": 1}}
        with mock.patch("app.modules.voice.agent._post_openai", side_effect=fake_post):
            res = self.client.post("/api/v1/voice/session", json={})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["ephemeral_key"]["value"], "ek_fallback")
        self.assertEqual([c[0] for c in calls], ["/realtime/client_secrets", "/realtime/sessions"])
        # the fallback body is the flat (legacy) session config
        self.assertEqual(calls[1][1]["model"], settings.OPENAI_REALTIME_MODEL)
        self.assertEqual(calls[1][1]["voice"], settings.OPENAI_REALTIME_VOICE)
        self.assertNotIn("type", calls[1][1])
        self.assertNotIn("audio", calls[1][1])

    def test_auth_failure_maps_to_clean_error(self):
        def fake_post(path, payload, api_key):
            raise _httpx_error(401)
        with mock.patch("app.modules.voice.agent._post_openai", side_effect=fake_post):
            with self.assertRaises(VoiceSessionError) as ctx:
                from app.modules.voice.agent import create_realtime_session
                create_realtime_session(tools=tools.tool_payloads()[:3], instructions="go")
        self.assertEqual(ctx.exception.code, "VOICE_AUTH_FAILED")

    def test_network_failure_maps_to_clean_error(self):
        def fake_post(path, payload, api_key):
            raise httpx.RequestError("boom", request=httpx.Request("POST", path))
        with mock.patch("app.modules.voice.agent._post_openai", side_effect=fake_post):
            from app.modules.voice.agent import create_realtime_session
            with self.assertRaises(VoiceSessionError) as ctx:
                create_realtime_session(tools=[], instructions="go")
        self.assertEqual(ctx.exception.code, "VOICE_NETWORK_FAILED")

    def test_disabled_when_no_key(self):
        settings.OPENAI_API_KEY = ""
        from app.modules.voice.agent import create_realtime_session
        with self.assertRaises(VoiceSessionError) as ctx:
            create_realtime_session(tools=[], instructions="go")
        self.assertEqual(ctx.exception.code, "VOICE_DISABLED")
        res = self.client.post("/api/v1/voice/session", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("disabled", res.json()["detail"].lower())

    def test_include_context_sets_flag(self):
        with mock.patch("app.modules.voice.agent._post_openai", return_value=self._session_payload_fake()):
            res = self.client.post("/api/v1/voice/session", json={"include_context": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["includes_context"])


class VoiceGeminiSessionTests(unittest.TestCase):
    """Gemini Live provider: token mint, payload shape, fallback and safety."""

    def setUp(self):
        from app.main import app

        self.client = TestClient(app)
        self._orig_key = settings.GEMINI_API_KEY
        self._orig_provider = settings.VOICE_PROVIDER
        self._orig_auto = settings.VOICE_AGENT_ENABLED
        settings.GEMINI_API_KEY = "gem-project-placeholder"
        settings.VOICE_PROVIDER = "gemini"
        settings.VOICE_AGENT_ENABLED = "auto"

    def tearDown(self):
        settings.GEMINI_API_KEY = self._orig_key
        settings.VOICE_PROVIDER = self._orig_provider
        settings.VOICE_AGENT_ENABLED = self._orig_auto

    def _token_payload_fake(self, name="auth_tokens/abc123", exp="2026-09-23T06:00:22.716Z"):
        return {"name": name, "expireTime": exp, "newSessionExpireTime": "2026-09-23T05:01:22.716Z"}

    def test_mint_sends_locked_server_side_setup(self):
        with mock.patch("app.modules.voice.agent._post_gemini", return_value=self._token_payload_fake()) as post:
            res = self.client.post("/api/v1/voice/session", json={})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["ephemeral_key"]["value"], "auth_tokens/abc123")
        self.assertEqual(body["model"], settings.GEMINI_LIVE_MODEL)
        self.assertEqual(body["voice"], settings.GEMINI_LIVE_VOICE)
        self.assertGreater(body["instructions_bytes"], 500)
        self.assertEqual(body["tools"][0]["type"], "function")
        self.assertGreater(body["ephemeral_key"]["expires_at"], 1_700_000_000)
        self.assertEqual(post.call_count, 1)
        payload = post.call_args.args[0]
        self.assertEqual(payload["uses"], 1)
        self.assertIn("bidiGenerateContentSetup", payload)
        setup = payload["bidiGenerateContentSetup"]
        self.assertEqual(setup["model"], f"models/{settings.GEMINI_LIVE_MODEL}")
        self.assertIn("systemInstruction", setup)
        self.assertIn("You are TIDE Voice", setup["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(setup["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], settings.GEMINI_LIVE_VOICE)
        self.assertIn("inputAudioTranscription", setup)
        self.assertIn("outputAudioTranscription", setup)
        self.assertEqual(list(setup["tools"][0].keys()), ["functionDeclarations"])
        declarations = setup["tools"][0]["functionDeclarations"]
        self.assertTrue(declarations)
        self.assertNotIn("type", declarations[0])
        self.assertEqual(declarations[0]["name"], "tidetwin_get_project_status")
        # The response echoes the same contract so the browser can always send it.
        self.assertEqual(body["setup"]["model"], f"models/{settings.GEMINI_LIVE_MODEL}")
        self.assertIn("You are TIDE Voice", body["setup"]["systemInstruction"]["parts"][0]["text"])

    def test_project_key_never_leaks_to_browser(self):
        with mock.patch("app.modules.voice.agent._post_gemini", return_value=self._token_payload_fake()):
            res = self.client.post("/api/v1/voice/session", json={})
            text = res.text.lower()
        self.assertNotIn("gem-project-placeholder", text)
        self.assertNotIn("gemini_api_key", text)

    def test_falls_back_to_local_expiry_when_api_omits_expire_time(self):
        # Google's provisioning response only carries the token name.
        with mock.patch(
            "app.modules.voice.agent._post_gemini",
            return_value={"name": "auth_tokens/only-name"},
        ):
            from app.modules.voice.agent import create_gemini_session

            result = create_gemini_session(tools=[], instructions="go")
        self.assertEqual(result["value"], "auth_tokens/only-name")
        self.assertIsNotNone(result["expires_at"])
        self.assertGreater(result["expires_at"], 1_700_000_000)
        self.assertIn("setup", result)

    def test_falls_back_to_unlocked_shape_on_400(self):
        calls = []
        def fake_post(payload, api_key):
            calls.append(payload)
            if "bidiGenerateContentSetup" in payload:
                raise VoiceSessionError(
                    "refused",
                    code="VOICE_SESSION_FAILED",
                    status_code=400,
                    detail="locked shape rejected",
                )
            return {"name": "auth_tokens/unlocked", "expireTime": "2026-09-23T06:00:22.716Z"}
        with mock.patch("app.modules.voice.agent._post_gemini", side_effect=fake_post):
            res = self.client.post("/api/v1/voice/session", json={})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["ephemeral_key"]["value"], "auth_tokens/unlocked")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("bidiGenerateContentSetup", calls[1])

    def test_auth_failure_maps_to_clean_error(self):
        def fake_post(payload, api_key):
            raise VoiceSessionError("denied", code="VOICE_AUTH_FAILED", status_code=403)
        with mock.patch("app.modules.voice.agent._post_gemini", side_effect=fake_post):
            from app.modules.voice.agent import create_gemini_session
            with self.assertRaises(VoiceSessionError) as ctx:
                create_gemini_session(
                    tools=tools.tool_payloads_gemini()[:3],
                    instructions="go",
                )
        self.assertEqual(ctx.exception.code, "VOICE_AUTH_FAILED")

    def test_disabled_without_gemini_key(self):
        settings.GEMINI_API_KEY = ""
        from app.modules.voice.agent import create_gemini_session
        with self.assertRaises(VoiceSessionError) as ctx:
            create_gemini_session(tools=[], instructions="go")
        self.assertEqual(ctx.exception.code, "VOICE_DISABLED")
        with mock.patch("app.modules.voice.agent._post_gemini", return_value=self._token_payload_fake()):
            res = self.client.post("/api/v1/voice/session", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("disabled", res.json()["detail"].lower())


class VoiceSessionErrorTest(unittest.TestCase):
    def test_error_raised_without_key_in_api(self):
        orig_provider = settings.VOICE_PROVIDER
        orig_gemini = settings.GEMINI_API_KEY
        try:
            settings.OPENAI_API_KEY = ""
            settings.GEMINI_API_KEY = ""
            settings.VOICE_PROVIDER = "openai"
            from app.main import app
            client = TestClient(app)
            res = client.post("/api/v1/voice/session", json={})
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["detail"], "Voice agent is disabled (OPENAI_API_KEY not configured).")
        finally:
            settings.OPENAI_API_KEY = "sk-project-placeholder"
            settings.GEMINI_API_KEY = orig_gemini
            settings.VOICE_PROVIDER = orig_provider


class VoiceWebSearchTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)

    def test_ok_with_related_plus_abstract(self):
        payload = {
            "AbstractText": "An atmospheric river is bringing heavy rain to California.",
            "AbstractURL": "https://example.com/ar",
            "RelatedTopics": [
                {
                    "Text": "Atmospheric river - Wikipedia",
                    "FirstURL": "https://en.wikipedia.org/wiki/Atmospheric_river",
                    "Result": "Atmospheric river",
                }
            ],
        }
        with mock.patch("app.api.voice.httpx.Client", return_value=FakeDdgClient(payload)):
            res = self.client.post("/api/v1/voice/web-search", json={"query": "atmospheric river today", "max_results": 3})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["answer"])
        self.assertGreaterEqual(body["results"][0]["title"], "")
        self.assertTrue(all(h["url"].startswith("http") for h in body["results"]))

    def test_no_results(self):
        with mock.patch("app.api.voice.httpx.Client", return_value=FakeDdgClient({"RelatedTopics": []})):
            res = self.client.post("/api/v1/voice/web-search", json={"query": "zzzz this surely matches nothing 12345"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "no_results")
        self.assertIn("nothing useful", res.json()["limitations"][0])

    def test_network_error_returns_clean_error(self):
        class BoomClient(FakeDdgClient):
            def get(self, url, params=None):
                raise httpx.RequestError("boom", request=httpx.Request("GET", url))
        with mock.patch("app.api.voice.httpx.Client", return_value=BoomClient({})):
            res = self.client.post("/api/v1/voice/web-search", json={"query": "anything"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "error")

    def test_query_validation(self):
        res = self.client.post("/api/v1/voice/web-search", json={"query": ""})
        self.assertEqual(res.status_code, 422)
        res = self.client.post("/api/v1/voice/web-search", json={"query": "a", "max_results": 99})
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()