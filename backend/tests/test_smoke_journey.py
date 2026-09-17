"""Phase 9 - API smoke test for the complete TIDE user journey.

Exercises every endpoint the guided demonstration touches, against the live
dataset, and asserts graceful behaviour when data is missing.  Browser-only
surfaces (Cesium rendering) are out of scope for an API smoke test.
"""

import unittest

from fastapi.testclient import TestClient


class JourneySmokeTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)

    def test_full_journey(self):
        # 1. Health
        health = self.client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertIn("checks", health.json())

        # 2. Locations (Digital Twin data)
        locations = self.client.get("/api/v1/ocean/locations")
        self.assertEqual(locations.status_code, 200)
        self.assertIsInstance(locations.json(), list)

        # 3. Event index
        events = self.client.get("/api/v1/tide/events")
        self.assertEqual(events.status_code, 200)
        event_list = events.json().get("data", {}).get("events", [])

        # 4. TIDE candidates
        candidates_res = self.client.get("/api/v1/tide/candidates")
        self.assertEqual(candidates_res.status_code, 200)
        candidates = candidates_res.json().get("data", [])
        self.assertTrue(candidates, "TIDE must return candidates for the live dataset")
        first = candidates[0]

        # 5. Explanation / evidence
        explanation = self.client.get(
            "/api/v1/tide/explanation",
            params={"location_id": first["location_id"], "variable": first["variable"], "depth_m": first.get("depth_m", 0)},
        )
        self.assertIn(explanation.status_code, (200, 404))

        # 6. Verdict
        verdict = self.client.get("/api/v1/tide/verdict", params={"location_id": first["location_id"]})
        self.assertIn(verdict.status_code, (200, 404))

        # 7. What-if virtual observation (must not persist)
        sim = self.client.post(
            "/api/v1/tide/virtual-observation",
            json={"location_id": first["location_id"], "variable": "temperature", "depth_m": 0, "observation_type": "VIRTUAL_SENSOR"},
        )
        self.assertEqual(sim.status_code, 200)
        sim_data = sim.json()["data"]
        self.assertEqual(sim_data["simulated_observation"]["status"], "SIMULATED")

        # 8. Decision Replay (only if an event exists)
        if event_list:
            replay = self.client.get(f"/api/v1/tide/events/{event_list[0]['event_id']}/replay")
            self.assertEqual(replay.status_code, 200)
            body = replay.json()["data"]
            self.assertFalse(body.get("mutates_history", False))

        # 9. Validation
        validation = self.client.get("/api/v1/tide/validation")
        self.assertEqual(validation.status_code, 200)
        self.assertEqual(validation.json()["data"]["maturity"]["EMPIRICALLY_VALIDATED"], [])

        # 10. Benchmarks (budget 1 keeps the smoke test quick)
        benchmark = self.client.get("/api/v1/tide/benchmarks", params={"budget": 1})
        self.assertEqual(benchmark.status_code, 200)
        self.assertIn("data", benchmark.json())

        # 11. Demonstration status
        demo = self.client.get("/api/v1/demo/status")
        self.assertEqual(demo.status_code, 200)
        self.assertIn("demonstration_event", demo.json())

        # 12. Copilot
        answer = self.client.post(
            "/api/v1/assistant/ask",
            json={"question": "Is TIDE scientifically validated?", "context": {}},
        )
        self.assertEqual(answer.status_code, 200)


if __name__ == "__main__":
    unittest.main()
