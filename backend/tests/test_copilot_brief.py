"""Phase 7 — Copilot Ocean Intelligence Brief.

Covers the structured `brief` intent: intent detection, the five-section
ANSWER / EVIDENCE / CONFIDENCE / LIMITATIONS / NEXT ACTION surface, honest
degradation when data is unavailable, and the assistant API envelope.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.modules.ai.nlp.copilot import ans_brief, detect_intent


class _Obs:
    def __init__(self, sst=None, wave=None, sal=None):
        self.location_id = 1
        self.sea_surface_temperature = sst
        self.wave_height = wave
        self.salinity = sal
        self.current_speed = None


class _Query:
    def __init__(self, row=None):
        self._row = row

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, obs=None):
        self._obs = obs

    def query(self, _model):
        return _Query(self._obs)


class _FakeLoc:
    id = 1
    name = "Goa"


def _tide_rankings():
    return [{
        "candidate_id": "tide-1-temperature-0-buoy",
        "location_id": 1, "location": "Goa", "depth_m": 0, "variable": "temperature",
        "observation_type": "BUOY", "status": "MODEL_DERIVED", "decision_impact": 0.6,
        "uncertainty": 0.6, "data_gap": 0.6, "anomaly_persistence": 0.5,
        "observation_cost": 0.5, "observation_value": 0.1800,
        "expected_uncertainty_reduction": 0.4, "affected_decision": "INVESTIGATE_ANOMALY",
        "reason": "High uncertainty and a persistent model-observer gap make an observation high-value.",
        "evidence": [{"evidence_id": "ev-1", "type": "MODEL_OBSERVATION_MISMATCH", "strength": 0.8,
                      "description": "Model runs warm against the nearest buoy.", "source_system": "Twin Comparison"}],
        "confidence": 0.7, "confidence_factors": [], "limitations": [],
    }]


def _situation():
    return {"generated_at": "now", "regions": [
        {"location_id": 1, "location": "Goa", "status": "caution", "temperature_anomaly": "MODERATE",
         "wave_state": "LOW", "observation_confidence": 72, "model_trust": 68, "disagreement": True,
         "headline": "Model-observation disagreement detected - verify"},
    ]}


def _event():
    return {"event_type": "marine_heatwave", "location_id": 1, "location": "Goa", "severity": "moderate",
            "confidence": 0.8, "model": 29.0, "observed": 30.2, "model_observed_diff": 1.2,
            "persistence": 12, "status": "watch"}


class BriefIntentTests(unittest.TestCase):
    def test_intent_detection_recognizes_brief_phrasing(self):
        for phrase in ("Give me the ocean intelligence brief.",
                       "Summarize the situation for Goa.",
                       "What's the picture for the network?"):
            self.assertEqual(detect_intent(phrase), "brief")

    def test_brief_assembles_structured_sections_from_real_data(self):
        db = _FakeDB(_Obs(sst=30.2, wave=1.1, sal=35.0))
        with patch("app.modules.ai.nlp.copilot.TideEngine") as engine, \
                patch("app.modules.ai.nlp.copilot.situation_panel", return_value=_situation()), \
                patch("app.modules.ai.nlp.copilot.classify_events", return_value={"events": [_event()]}), \
                patch("app.modules.ai.nlp.copilot.intelligence_health", return_value=[{"location_id": 1, "location": "Goa", "score": 74, "label": "Moderate"}]):
            engine.return_value.rankings.return_value = _tide_rankings()
            result = ans_brief(db, _FakeLoc())

        self.assertEqual(result["intent"], "brief")
        self.assertEqual(result["location"], "Goa")
        for section in ("**ANSWER**", "**EVIDENCE**", "**CONFIDENCE**", "**LIMITATIONS**", "**NEXT ACTION**"):
            self.assertIn(section, result["answer"])
        self.assertIn("30.2", result["answer"])
        self.assertIn("INVESTIGATE ANOMALY", result["answer"])
        self.assertTrue(any(i["label"] == "Top obs value" for i in result["data"]["items"]))
        self.assertTrue(any("Twin Comparison" in s for s in result["sources"]))

    def test_brief_degrades_honestly_when_data_is_missing(self):
        db = _FakeDB(None)
        with patch("app.modules.ai.nlp.copilot.TideEngine") as engine, \
                patch("app.modules.ai.nlp.copilot.situation_panel", return_value={"regions": []}), \
                patch("app.modules.ai.nlp.copilot.classify_events", return_value={"events": []}), \
                patch("app.modules.ai.nlp.copilot.intelligence_health", return_value=[]):
            engine.return_value.rankings.return_value = []
            result = ans_brief(db, _FakeLoc())

        self.assertEqual(result["intent"], "brief")
        for section in ("**ANSWER**", "**EVIDENCE**", "**CONFIDENCE**", "**LIMITATIONS**", "**NEXT ACTION**"):
            self.assertIn(section, result["answer"])
        self.assertIn("No live observations", result["answer"])
        self.assertIn("unavailable", result["answer"])  # honest confidence statement
        self.assertEqual(len(result["data"]["items"]), 2)  # Health —, Events 0


class BriefApiTests(unittest.TestCase):
    def setUp(self):
        from app.main import app
        self.client = TestClient(app)

    def test_ask_routes_brief_and_keeps_context(self):
        result = {
            "answer": "**ANSWER**\nTest brief\n\n**EVIDENCE**\n- [Twin Comparison] x\n\n**CONFIDENCE**\n- model trust **68%**\n\n**LIMITATIONS**\n- Demonstration only\n\n**NEXT ACTION**\n- Observe Goa",
            "intent": "brief", "location": "Goa", "location_id": 1,
            "data": {"type": "metrics", "items": [{"label": "Model trust", "value": "68%", "color": "#38bdf8"}]},
            "suggestions": ["Replay the decision."], "sources": ["Twin Comparison"],
            "steps": ["Fused engines"], "context": {"last_location_id": 1, "last_intent": "brief"},
        }
        with patch("app.api.assistant.copilot_answer", return_value=result):
            response = self.client.post("/api/v1/assistant/ask",
                                        json={"question": "Give me the ocean intelligence brief.", "context": {}})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "brief")
        self.assertEqual(payload["location"], "Goa")
        self.assertIn("NEXT ACTION", payload["answer"])
        self.assertEqual(payload["context"], {"last_location_id": 1, "last_intent": "brief"})


if __name__ == "__main__":
    unittest.main()