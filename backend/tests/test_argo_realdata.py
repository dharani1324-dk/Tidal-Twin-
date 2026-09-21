"""Argo REAL-data integration tests.

Proves the "Argo on real data" feature:

- the twin source registry reports Argo as `online` with real provenance once
  profile rows exist in `argo_profiles`, and stays honestly `simulated` when
  none do;
- `get_argo_trajectories` serves the REAL ingested profile levels (labelled
  "Real Argo GDAC profile") when rows exist, and falls back to the simulator
  otherwise - the `/api/v1/argo` API already reads `argo_profiles` directly.

NOTE: this database already holds REAL Argo profiles (backend/data/argo/*.nc,
ingested with scripts.ingest_argo), so:
  * the "online" tests are exactly what production will see;
  * the "simulated fallback" test temporarily empties `argo_profiles`, proves
    the fallback, then carefully restores the exact rows it removed, so no
    real data is lost.

The marker rows added by this test are synthetic plumbing, clearly tagged by
`source_file`, and always deleted.
"""

import unittest
from datetime import datetime, timezone

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.argo import ArgoProfile as A

_MARKER = "synthetic-argo-realdata"
_FAKE_TIME = datetime(2099, 3, 1, tzinfo=timezone.utc)


def _seed_rows(db):
    # One float, two profile levels (a deep profile 0 m -> 200 m). Same shape
    # `ingest_argo` writes from a real GDAC *_prof.nc.
    db.add_all([
        A(float_id="2901908", latitude=18.5, longitude=73.0, time=_FAKE_TIME,
          depth_m=0.0, temperature=28.4, salinity=35.2, pressure=0.0,
          source_file=_MARKER),
        A(float_id="2901908", latitude=18.5, longitude=73.0, time=_FAKE_TIME,
          depth_m=200.0, temperature=13.1, salinity=35.7, pressure=202.0,
          source_file=_MARKER),
    ])
    db.commit()


def _clear_rows(db):
    db.query(A).filter(A.source_file == _MARKER).delete()
    db.commit()


def _snapshot_all_rows(db):
    return [
        (r.float_id, r.latitude, r.longitude, r.time, r.depth_m,
         r.temperature, r.salinity, r.pressure, r.source_file)
        for r in db.query(A).all()
    ]


def _restore_rows(db, snapshot):
    for float_id, la, lo, t, depth, temp, sal, pres, src in snapshot:
        db.add(A(float_id=float_id, latitude=la, longitude=lo, time=t,
                 depth_m=depth, temperature=temp, salinity=sal,
                 pressure=pres, source_file=src))
    db.commit()


def tearDownModule():
    db = SessionLocal()
    try:
        _clear_rows(db)
    finally:
        db.close()


class ArgoRegistryStatusTest(unittest.TestCase):
    """Twin data-source registry flips honestly between simulated/online."""

    def setUp(self):
        self.db = SessionLocal()
        _clear_rows(self.db)

    def tearDown(self):
        try:
            _clear_rows(self.db)
        finally:
            self.db.close()

    def argo_status(self):
        from app.modules.ai.twin.sources import data_sources

        sources = data_sources(self.db)
        return next(s for s in sources["sources"] if s["id"] == "argo")

    def test_registry_is_online_when_real_rows_exist(self):
        _seed_rows(self.db)
        try:
            argo = self.argo_status()
            self.assertEqual(argo["status"], "online")
            self.assertIn("Real Argo GDAC float profiles ingested", argo["note"])
            self.assertIn("fetch_argo", argo["note"])
        finally:
            _clear_rows(self.db)

    def test_registry_exposes_real_coverages_of_existing_data(self):
        # The DB already holds real Argo profiles -> coverage must be > 0 and
        # the source must list real floats, not a 0% simulator.
        argo = self.argo_status()
        self.assertEqual(argo["status"], "online")
        self.assertGreater(argo["coverage_pct"], 0)
        self.assertIsNotNone(argo["last_update"])

    def test_registry_is_simulated_only_when_table_empty(self):
        all_rows = _snapshot_all_rows(self.db)
        try:
            db_empty = SessionLocal()
            db_empty.query(A).delete()
            db_empty.commit()
            try:
                from app.modules.ai.twin.sources import data_sources

                sources = data_sources(db_empty)
                argo = next(s for s in sources["sources"] if s["id"] == "argo")
                self.assertEqual(argo["status"], "simulated")
                self.assertIn("simulated", argo["note"].lower())
            finally:
                db_empty.close()
        finally:
            self.db.expire_all()
            _restore_rows(self.db, all_rows)


class ArgoTrajectoryRealTest(unittest.TestCase):
    """Trajectories serve REAL ingested levels when present."""

    def setUp(self):
        self.db = SessionLocal()
        _clear_rows(self.db)
        _seed_rows(self.db)

    def tearDown(self):
        try:
            _clear_rows(self.db)
        finally:
            self.db.close()

    def test_trajectories_serve_real_profile_levels_including_marker(self):
        from app.modules.ai.forecast.argo import get_argo_trajectories

        out = get_argo_trajectories(self.db, n_floats=5)
        self.assertEqual(out["source"], "argo_profiles (real Argo GDAC)")
        marker = next(f for f in out["floats"] if f["float_id"] == "2901908")
        assert marker is not None
        self.assertEqual(marker["platform"], "Real Argo GDAC profile")
        self.assertEqual(marker["n_points"], 2)
        by_depth = {p["depth_m"]: p for p in marker["points"]}
        self.assertEqual(by_depth[0.0]["temperature"], 28.4)
        self.assertEqual(by_depth[200.0]["salinity"], 35.7)
        self.assertEqual(marker["profile"]["levels"], 2)
        self.assertEqual(marker["provenance"], _MARKER)
        # Existing real floats stay visible alongside the seeded one.
        self.assertGreaterEqual(out["count"], 2)

    def test_fallback_is_simulated_when_table_empty(self):
        from app.modules.ai.forecast.argo import get_argo_trajectories

        # Temporarily empty argo_profiles, prove the fallback, restore fully.
        all_rows = _snapshot_all_rows(self.db)
        try:
            db_empty = SessionLocal()
            db_empty.query(A).delete()
            db_empty.commit()
            try:
                out = get_argo_trajectories(db_empty)
                self.assertEqual(out["source"], "argo trajectory simulator")
                self.assertTrue(out["floats"])
                self.assertIn("Simulated Argo", out["floats"][0]["platform"])
            finally:
                db_empty.close()
        finally:
            self.db.expire_all()
            _restore_rows(self.db, all_rows)


if __name__ == "__main__":
    unittest.main()