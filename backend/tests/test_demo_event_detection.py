"""Regression tests: clearly-labelled demo detection vs real-only stream.

The real event classifier (``classify_events``) must stay honest — SIMULATED
rows never create *real* events. Demonstration events surface only through the
detector layer (``detect_events``), always tagged ``data_status = "demo"`` with
the DEMONSTRATION note, so the UI shows them as a demonstration.
"""

import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.ai.twin.events import _classify_demo_events, detect_events
from app.modules.ai.validation.engine import classify_events


class DemoDetectorTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.client = TestClient(app)
        self.db: Session = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _demo_present(self) -> bool:
        from app.api.demo import _count, _simulated_filter

        return _count(self.db, _simulated_filter()) > 0

    def test_detect_events_surfaces_labelled_demo_events(self):
        if not self._demo_present():
            self.skipTest("No demo rows in the current dataset.")
        events = detect_events(self.db).get("events", [])
        demo = [e for e in events if e.get("data_status") == "demo"]
        self.assertTrue(demo, "Demo rows must produce at least one labelled demo event.")
        for ev in demo:
            self.assertEqual(ev["data_status"], "demo")
            self.assertTrue(ev.get("note", "").startswith("Derived from clearly-labelled SIMULATED"),
                            "Demo events must carry the DEMONSTRATION note.")
            self.assertTrue(ev.get("event_type"))

    def test_classify_events_never_leaks_demo_rows(self):
        events = classify_events(self.db).get("events", [])
        for ev in events:
            self.assertNotEqual(ev.get("data_status"), "demo")

    def test_demo_classifier_tags_all_events(self):
        for ev in _classify_demo_events(self.db):
            self.assertEqual(ev.get("data_status"), "demo")
            self.assertIn("demo", ev.get("note", "").lower())

    def test_enrichment_preserves_demo_label(self):
        if not self._demo_present():
            self.skipTest("No demo rows in the current dataset.")
        for ev in detect_events(self.db).get("events", []):
            if ev.get("data_status") == "demo":
                self.assertEqual(ev["data_status"], "demo",
                                 "Twin compare enrichment must never relabel a demo event as real.")


if __name__ == "__main__":
    unittest.main()