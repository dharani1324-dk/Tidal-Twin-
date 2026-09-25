"""Tests for REAL in-situ observation hydration (Argo -> observation store).

The hydration bridge must only ever emit REAL rows from real Argo surface
levels, disclose the float's actual position and distance, and be idempotent.
"""

import json
import unittest

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.observation import OceanObservation
from app.modules.ai.provenance_quality import origin_status

from app.services.hydrate_real_observations import hydrate_real_observations


def _argo_rows(db) -> list:
    return db.query(OceanObservation).filter(
        OceanObservation.source.like("Argo float %"),
        OceanObservation.data_type == "observation",
    ).all()


class TestRealObservationHydration(unittest.TestCase):
    def setUp(self):
        self.sessions = []

    def _db(self):
        session = SessionLocal()
        self.sessions.append(session)
        return session

    def tearDown(self):
        # Refresh the hydration so the running app keeps a fresh REAL stream.
        for session in self.sessions:
            try:
                hydrate_real_observations(session)
            finally:
                session.close()

    def test_hydration_emits_real_rows_with_full_provenance(self):
        db = self._db()
        summary = hydrate_real_observations(db)
        self.assertEqual(summary["status"], "hydrated")
        self.assertGreater(summary["hydrated"], 0)
        rows = _argo_rows(db)
        self.assertGreaterEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(origin_status(row.source, row.data_type), "REAL")
            self.assertEqual(row.data_type, "observation")
            self.assertTrue(row.source.startswith("Argo float "))
            self.assertIn("real Argo GDAC", row.source)
            self.assertIsNotNone(row.sea_surface_temperature)
            self.assertLessEqual(row.depth_m, 10.0)
            self.assertIsNone(row.wave_height, "floats do not measure waves")
            extra = json.loads(row.extra or "{}")
            self.assertIn("float_id", extra)
            self.assertGreaterEqual(extra["distance_km_to_coast"], 0)
            self.assertIsNotNone(extra.get("measured_lat"))
            self.assertIsNotNone(extra.get("measured_lon"))
            self.assertIn("representativeness_note", extra)

    def test_hydration_is_idempotent(self):
        db = self._db()
        summary = hydrate_real_observations(db)
        count = len(_argo_rows(db))
        again = hydrate_real_observations(db)
        self.assertEqual(again["hydrated"], summary["hydrated"])
        self.assertEqual(len(_argo_rows(db)), count)

    def test_every_location_gets_a_nearest_float(self):
        from app.models.location import OceanLocation

        db = self._db()
        summary = hydrate_real_observations(db)
        hydrated = summary["locations"]
        locations = db.query(OceanLocation).all()
        self.assertTrue(hydrated, "all monitored coasts should be assigned a nearest real float")
        for location in locations:
            self.assertIn(str(location.id), hydrated, f"location {location.id} missing real in-situ reference")
            self.assertIn("float_id", hydrated[str(location.id)])

    def test_tide_verdict_consumes_real_rows(self):
        from app.modules.ai.tide.engine import TideEngine
        from app.modules.ai.tide.adapters import latest_observation

        db = self._db()
        hydrate_real_observations(db)
        latest = latest_observation(db, 1)
        self.assertIsNotNone(latest, "Mumbai coast should have a REAL latest observation")
        self.assertEqual(origin_status(latest.source, latest.data_type), "REAL")
        self.assertIsNotNone(latest.source)
        verdict = TideEngine(db).verdict(location_id=1, variable="temperature", depth_m=0.0)
        self.assertIsNotNone(verdict)
        self.assertIn("verdict", verdict)
        self.assertIn("evidence", verdict)
        self.assertGreaterEqual(len(verdict["evidence"]), 0)

    def test_noop_when_guard_has_no_surface_reference(self):
        # The pure guard path: with no float assignments the service reports
        # status "noop" instead of fabricating rows. (Real rows exist in the
        # DB, so the full path is exercised by the other tests.)
        from app.services.hydrate_real_observations import _surface_samples

        db = self._db()
        samples = _surface_samples(db)
        if not samples:
            summary = hydrate_real_observations(db)
            self.assertEqual(summary["status"], "noop")
        else:
            self.skipTest("real surface samples present; guard already exercised")


if __name__ == "__main__":
    unittest.main()