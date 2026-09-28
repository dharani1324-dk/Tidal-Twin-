"""API smoke test for the supported OceanVerse journey after TIDE removal."""

import unittest

from fastapi.testclient import TestClient


class JourneySmokeTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)

    def test_core_ocean_journey(self):
        health = self.client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertNotIn("tide", health.json()["checks"])

        locations = self.client.get("/api/v1/ocean/locations")
        self.assertEqual(locations.status_code, 200)
        self.assertIsInstance(locations.json(), list)

        demo = self.client.get("/api/v1/demo/status")
        self.assertEqual(demo.status_code, 200)
        self.assertEqual(len(demo.json()["guide_steps"]), 6)

        capabilities = self.client.get("/api/v1/assistant/capabilities")
        self.assertEqual(capabilities.status_code, 200)
        keys = {item["key"] for item in capabilities.json()["capabilities"]}
        self.assertNotIn("tide", keys)
        self.assertNotIn("tide_validation", keys)

        removed = self.client.get("/api/v1/tide/candidates")
        self.assertEqual(removed.status_code, 404)


if __name__ == "__main__":
    unittest.main()
