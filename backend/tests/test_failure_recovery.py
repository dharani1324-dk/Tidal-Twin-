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

    def test_removed_tide_api_is_not_registered(self):
        response = self.client.get("/api/v1/tide/candidates")
        self.assertEqual(response.status_code, 404)

    def test_demo_seed_bad_kind_422(self):
        response = self.client.post("/api/v1/demo/seed", params={"kind": "tsunami"})
        self.assertEqual(response.status_code, 422)

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
