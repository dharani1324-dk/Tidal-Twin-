"""Phase 9 - health endpoint + demonstration mode + simulation safety tests."""

import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.demo import (
    DEMO_MARKER,
    SIMULATED_MARKER,
    _simulated_filter,
)
from app.api.health import AVAILABLE, UNAVAILABLE, _overall
from app.core.database import SessionLocal
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.tide.adapters import observation_status
from app.modules.ai.tide.engine import TideEngine


class HealthEndpointTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)

    def test_health_v1_shape(self):
        res = self.client.get("/api/v1/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn(body["status"], ("healthy", "degraded", "unavailable"))
        self.assertEqual(body["service"], "TidalTwin Backend")
        for key in ("backend", "database", "ocean_data", "tide", "copilot", "cesium"):
            self.assertIn(key, body["checks"])
            self.assertIn(body["checks"][key]["status"], (AVAILABLE, "LIMITED", UNAVAILABLE, "OPTIONAL / UNAVAILABLE"))
            self.assertTrue(body["checks"][key]["detail"])

    def test_health_alias_matches(self):
        a = self.client.get("/api/v1/health").json()
        b = self.client.get("/api/health").json()
        self.assertEqual(set(a["checks"].keys()), set(b["checks"].keys()))
        self.assertEqual(a["status"], b["status"])

    def test_health_never_exposes_secrets(self):
        text = self.client.get("/api/v1/health").text.lower()
        for secret in ("password", "postgres:postgres", "database_url", "cesium_ion_token="):
            self.assertNotIn(secret, text)

    def test_overall_status_logic(self):
        def c(status):
            return {"status": status}

        self.assertEqual(
            _overall({"backend": c(AVAILABLE), "database": c(AVAILABLE), "ocean_data": c(AVAILABLE), "tide": c(AVAILABLE)}),
            "healthy",
        )
        self.assertEqual(
            _overall({"backend": c(AVAILABLE), "database": c(UNAVAILABLE), "ocean_data": c(AVAILABLE), "tide": c(AVAILABLE)}),
            "unavailable",
        )
        self.assertEqual(
            _overall({"backend": c(AVAILABLE), "database": c(AVAILABLE), "ocean_data": c("LIMITED"), "tide": c(UNAVAILABLE)}),
            "degraded",
        )


class DemoStatusTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)

    def test_demo_status_shape_and_labels(self):
        res = self.client.get("/api/v1/demo/status")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("demo_data_present", body)
        self.assertEqual(body["labels"]["dataset"], DEMO_MARKER)
        self.assertEqual(body["labels"]["simulated_observation"], SIMULATED_MARKER)
        self.assertEqual(len(body["guide_steps"]), 8)
        self.assertIsInstance(body["sources"], list)
        self.assertGreaterEqual(body["total_observations"], body["simulated_observations"])

    def test_demonstration_event_honesty_when_no_events(self):
        body = self.client.get("/api/v1/demo/status").json()
        event = body["demonstration_event"]
        if body["detected_events"] == 0:
            self.assertFalse(event["available"])
            self.assertIn("No detected events", event["reason"])
        else:
            self.assertTrue(event["available"])
            self.assertTrue(event["event_id"].startswith("event-"))
            # The selection is documented as practical, not scientific.
            self.assertIn("not a scientific ranking", event["reason"])

    def test_simulated_sources_are_labelled(self):
        body = self.client.get("/api/v1/demo/status").json()
        for source in body["sources"]:
            if source["source"].upper().startswith("SIMULATED"):
                self.assertTrue(source["is_simulated"])
                self.assertIn(source["status"], ("SIMULATED", "SYNTHETIC"))


class SimulationSafetyTest(unittest.TestCase):
    """SIMULATED rows must never be reported as REAL, and reset must be safe."""

    def setUp(self):
        self.db: Session = SessionLocal()
        self.location = OceanLocation(name="__PHASE9_TEST__", region_type="sea")
        self.db.add(self.location)
        self.db.flush()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _obs(self, source: str, data_type: str = "observation") -> OceanObservation:
        return OceanObservation(
            location_id=self.location.id,
            timestamp=datetime.now(timezone.utc),
            sea_surface_temperature=28.0,
            source=source,
            data_type=data_type,
        )

    def test_observation_status_classification(self):
        self.assertEqual(observation_status(self._obs("SIMULATED_HEATWAVE")), "SIMULATED")
        self.assertEqual(observation_status(self._obs("DEMO_SYNTHETIC")), "SYNTHETIC")
        self.assertEqual(observation_status(self._obs("Open-Meteo Marine")), "REAL")
        self.assertEqual(observation_status(self._obs("model-run-01", "model")), "MODEL_DERIVED")

    def test_reset_filter_selects_only_simulated(self):
        real = self._obs("Open-Meteo Marine")
        sim = self._obs("SIMULATED_PHASE9_TEST")
        self.db.add_all([real, sim])
        self.db.flush()
        matched = (
            self.db.query(OceanObservation)
            .filter(_simulated_filter())
            .filter(OceanObservation.id.in_([real.id, sim.id]))
            .all()
        )
        self.assertEqual([o.id for o in matched], [sim.id])

    def test_virtual_observation_is_not_persisted(self):
        before = self.db.query(OceanObservation).count()
        candidates = TideEngine(self.db).rankings(location_id=self.location.id)
        if candidates:
            TideEngine(self.db).virtual_observation(
                location_id=self.location.id, variable="temperature", depth_m=0.0
            )
        after = self.db.query(OceanObservation).count()
        self.assertEqual(before, after, "A simulated observation must never be written to the store.")

    def test_tide_candidate_never_claims_real(self):
        candidates = TideEngine(self.db).rankings()
        for candidate in candidates:
            self.assertNotEqual(candidate["status"], "REAL")
            self.assertEqual(candidate["status"], "MODEL_DERIVED")


if __name__ == "__main__":
    unittest.main()
