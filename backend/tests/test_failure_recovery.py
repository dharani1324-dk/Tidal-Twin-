"""Phase 10 - failure recovery and edge-case API behaviour.

Every case here is an *expected missing-data or invalid-input condition*. The
requirement is the same throughout: respond with correct HTTP semantics and a
graceful body - never a crash or a fabricated value.
"""

import unittest

from fastapi.testclient import TestClient

UNKNOWN_ID = 999999


class FailureRecoveryTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)

    # --- missing / invalid resources -------------------------------------

    def test_unknown_event_replay_404(self):
        res = self.client.get("/api/v1/tide/events/event-99999/replay")
        self.assertEqual(res.status_code, 404)
        self.assertIn("detail", res.json())

    def test_unknown_event_context_404(self):
        res = self.client.get("/api/v1/tide/events/event-99999")
        self.assertEqual(res.status_code, 404)

    def test_unknown_benchmark_case_404(self):
        res = self.client.get("/api/v1/tide/benchmarks/not-a-case", params={"budget": 1})
        self.assertEqual(res.status_code, 404)

    def test_unknown_location_candidates_is_empty_not_error(self):
        res = self.client.get("/api/v1/tide/candidates", params={"location_id": UNKNOWN_ID})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"], [])

    def test_unknown_location_verdict_404(self):
        res = self.client.get("/api/v1/tide/verdict", params={"location_id": UNKNOWN_ID})
        self.assertIn(res.status_code, (404, 200))  # 404 preferred; 200 only if graceful empty
        if res.status_code == 200:
            self.assertIsNone(res.json()["data"])

    def test_virtual_observation_unknown_location_404(self):
        res = self.client.post(
            "/api/v1/tide/virtual-observation",
            json={"location_id": UNKNOWN_ID, "variable": "temperature"},
        )
        self.assertEqual(res.status_code, 404)

    # --- invalid parameters ----------------------------------------------

    def test_unknown_variable_422(self):
        res = self.client.get("/api/v1/tide/candidates", params={"variable": "not_a_variable"})
        self.assertEqual(res.status_code, 422)

    def test_negative_depth_422(self):
        res = self.client.get("/api/v1/tide/data-gaps", params={"depth_m": -1})
        self.assertEqual(res.status_code, 422)

    def test_benchmark_bad_budget_422(self):
        res = self.client.get("/api/v1/tide/benchmarks", params={"budget": 99})
        self.assertEqual(res.status_code, 422)

    def test_benchmark_bad_strategy_422(self):
        res = self.client.get("/api/v1/tide/benchmarks", params={"budget": 1, "strategies": "MAGIC"})
        self.assertEqual(res.status_code, 422)

    def test_virtual_observation_bad_method_422(self):
        res = self.client.post(
            "/api/v1/tide/virtual-observation",
            json={"location_id": 1, "variable": "temperature", "observation_type": "TELEPORT"},
        )
        self.assertEqual(res.status_code, 422)

    def test_virtual_observation_missing_body_422(self):
        res = self.client.post("/api/v1/tide/virtual-observation", json={})
        self.assertEqual(res.status_code, 422)

    def test_demo_seed_bad_kind_422(self):
        res = self.client.post("/api/v1/demo/seed", params={"kind": "tsunami"})
        self.assertEqual(res.status_code, 422)

    # --- Copilot graceful failure ----------------------------------------

    def test_assistant_empty_question_graceful(self):
        res = self.client.post("/api/v1/assistant/ask", json={"question": ""})
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json()["answer"], str)

    def test_assistant_missing_field_422(self):
        res = self.client.post("/api/v1/assistant/ask", json={})
        self.assertEqual(res.status_code, 422)

    # --- root / health resilience ----------------------------------------

    def test_root_online(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "online")

    def test_health_never_500(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertIn(res.json()["status"], ("healthy", "degraded", "unavailable"))


if __name__ == "__main__":
    unittest.main()
