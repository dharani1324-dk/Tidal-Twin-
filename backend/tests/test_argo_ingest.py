"""Argo profile ingestion + API tests.

Uses a tiny SYNTHETIC Argo-style NetCDF fixture (clearly not real ocean data)
to prove the mechanics of `scripts.ingest_argo` (levels, NaN skipping,
idempotency, reingest) and the `/api/v1/argo` endpoints.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from app.core.database import SessionLocal
from app.models.argo import ArgoProfile as A
from scripts.ingest_argo import ingest_file

_TMP = tempfile.TemporaryDirectory()
FIXTURE = Path(_TMP.name) / "synthetic_argo_profile.nc"
FLOAT_ID = "9999999"


def _build_fixture():
    ds = xr.Dataset(
        {
            "PLATFORM_NUMBER": (("N_PROF",), np.array([99_999_99])),
            "JULD": (("N_PROF",), np.array([26_500.0]), {"units": "days since 1950-01-01 00:00:00"}),
            "LATITUDE": (("N_PROF",), np.array([13.0], dtype="float32")),
            "LONGITUDE": (("N_PROF",), np.array([80.3], dtype="float32")),
            "PRES": (("N_PROF", "N_LEVELS"), np.array([[0.0, 50.0, 100.0, 150.0]], dtype="float32")),
            "TEMP": (("N_PROF", "N_LEVELS"), np.array([[28.0, 27.5, 26.0, np.nan]], dtype="float32")),
            "PSAL": (("N_PROF", "N_LEVELS"), np.array([[35.5, 35.6, np.nan, 35.8]], dtype="float32")),
        }
    )
    ds.to_netcdf(FIXTURE)


def _count() -> int:
    db = SessionLocal()
    try:
        return db.query(A).filter(A.source_file == str(FIXTURE)).count()
    finally:
        db.close()


def setUpModule():
    _build_fixture()


def tearDownModule():
    db = SessionLocal()
    try:
        db.query(A).filter(A.source_file == str(FIXTURE)).delete()
        db.commit()
    finally:
        db.close()
    _TMP.cleanup()


class ArgoIngestTest(unittest.TestCase):
    def setUp(self):
        ingest_file(FIXTURE, verbose=False, reingest=True)

    def test_ingests_all_levels(self):
        self.assertEqual(_count(), 4)

    def test_idempotent_rerun(self):
        s = ingest_file(FIXTURE, verbose=False)
        self.assertEqual(s["rows_inserted"], 0)
        self.assertEqual(_count(), 4)

    def test_reingest_resets(self):
        s = ingest_file(FIXTURE, verbose=False, reingest=True)
        self.assertEqual(s["rows_inserted"], 4)
        self.assertEqual(_count(), 4)

    def test_values_and_nan_handling(self):
        db = SessionLocal()
        try:
            rows = db.query(A).filter(A.source_file == str(FIXTURE)).order_by(A.depth_m).all()
            temps = [None if r.temperature is None else round(r.temperature, 3) for r in rows]
            sals = [None if r.salinity is None else round(r.salinity, 3) for r in rows]
            depths = [r.depth_m for r in rows]
            self.assertEqual(temps, [28.0, 27.5, 26.0, None])
            self.assertEqual(sals, [35.5, 35.6, None, 35.8])
            self.assertEqual(depths, [0.0, 50.0, 100.0, 150.0])
            for r in rows:
                self.assertEqual(r.float_id, FLOAT_ID)
                self.assertNotEqual(r.temperature is None and r.salinity is None, True)
        finally:
            db.close()


class ArgoApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        ingest_file(FIXTURE, verbose=False, reingest=True)
        self.client = TestClient(app)

    def test_floats_lists_the_ingested_float(self):
        res = self.client.get("/api/v1/argo/floats")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        ids = [f["float_id"] for f in body["floats"]]
        self.assertIn(FLOAT_ID, ids)

    def test_profile_returns_depth_sorted_levels(self):
        res = self.client.get(f"/api/v1/argo/floats/{FLOAT_ID}/profile")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["float_id"], FLOAT_ID)
        depths = [lv["depth_m"] for lv in body["levels"]]
        self.assertEqual(depths, sorted(depths))
        self.assertEqual(len(body["levels"]), 4)

    def test_unknown_float_returns_404(self):
        res = self.client.get("/api/v1/argo/floats/0000000/profile")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()