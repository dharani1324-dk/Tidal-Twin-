"""Satellite Chlorophyll (chlor_a) API tests.

The real NOAA CoastWatch VIIRS-Himawari grid is downloaded off-line by
`scripts.fetch_chlor`; until then the DB has no chlor_a rows, so the endpoints
must honestly report "no data" (never fabricate ocean colour). These tests prove:

- the honest empty state (no chlor_a rows -> available/found false),
- a full synthetic round-trip: ingest a tiny synthetic chlor_a .nc exactly like
  `scripts.ingest_netcdf` would, then read it back through /latest and /near.

The synthetic grid is obviously not real satellite data - it only proves the
plumbing, with real values still provisioned by fetch_chlor + ingest.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from app.core.database import SessionLocal
from app.models.netcdf import NetcdfReadings as N
from scripts.ingest_netcdf import ingest_file

_TMP = tempfile.TemporaryDirectory()
CHL_FIXTURE = Path(_TMP.name) / "synthetic_chlor_month.nc"


def tearDownModule():
    db = SessionLocal()
    try:
        db.query(N).filter(N.variable_name == "chlor_a").delete()
        db.commit()
    finally:
        db.close()
    _TMP.cleanup()


def _ingest_synthetic_chlor() -> None:
    vals = np.array(
        [
            [0.12, 0.45, 0.90, 1.40],
            [0.08, 0.22, 0.60, 2.10],
            [0.05, 0.10, 0.30, 0.80],
        ],
        dtype="float32",
    )
    vals[2, 3] = np.nan  # a missing cell, must be skipped like real ocean colour
    ds = xr.Dataset(
        {"chlor_a": (("time", "lat", "lon"), vals[None, :, :], {"standard_name": "mass_concentration_of_chlorophyll_a_in_sea_water", "units": "mg m-3"})},
        coords={
            "lat": [0.0, 1.0, 2.0],
            "lon": [60.0, 61.0, 62.0, 63.0],
            "time": [np.datetime64("2021-09-15T00:00:00")],
        },
    )
    ds.lat.attrs["axis"] = "Y"
    ds.lon.attrs["axis"] = "X"
    ds.time.attrs["axis"] = "T"
    ds.to_netcdf(CHL_FIXTURE)
    ingest_file(CHL_FIXTURE, reingest=True)


def _clear_chlor() -> None:
    db = SessionLocal()
    try:
        db.query(N).filter(N.variable_name == "chlor_a").delete()
        db.commit()
    finally:
        db.close()


class ChlorApiEmptyTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        _clear_chlor()
        self.client = TestClient(app)

    def test_latest_reports_no_data_honestly(self):
        res = self.client.get("/api/v1/chlor/latest")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["available"])
        self.assertIn("ingest", body["error"].lower())

    def test_near_reports_no_data_honestly(self):
        res = self.client.get("/api/v1/chlor/near", params={"latitude": 13.84, "longitude": 63.46})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["found"])
        self.assertIn("ingest", body["reason"].lower())


class ChlorSyntheticRoundTripTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_ingest_then_serve_grid(self):
        _ingest_synthetic_chlor()
        try:
            res = self.client.get("/api/v1/chlor/latest")
            self.assertEqual(res.status_code, 200)
            body = res.json()
            self.assertTrue(body["available"])
            self.assertEqual(body["months"], ["2021-09"])
            self.assertEqual(body["time"], "2021-09")
            self.assertEqual(body["rows"], 11)  # 3x4 minus one NaN cell
            self.assertIn("CoastWatch", body["source"])
            stats = body["stats"]
            self.assertEqual(stats["count"], body["rows"])
            self.assertIsNotNone(stats["min"])
            self.assertIsNotNone(stats["max"])
            self.assertLessEqual(stats["min"], stats["max"])
            self.assertGreaterEqual(stats["min"], 0.0)
            for s in body["samples"]:
                self.assertTrue(0 <= s["chlor_a"] <= 10)
                self.assertTrue(-180 <= s["longitude"] <= 180)

            near = self.client.get("/api/v1/chlor/near", params={"latitude": 1.0, "longitude": 61.0})
            self.assertEqual(near.status_code, 200)
            nb = near.json()
            self.assertTrue(nb["found"])
            self.assertIn("chlor_a", nb)
            self.assertLessEqual(nb["distance_deg"], 0.2)

            # Mid-cell point on an (unrealistic) 1-degree fixture grid is "no cell".
            far = self.client.get("/api/v1/chlor/near", params={"latitude": 1.5, "longitude": 61.5, "max_dist_deg": 0.05})
            self.assertFalse(far.json()["found"])
        finally:
            _clear_chlor()


if __name__ == "__main__":
    unittest.main()