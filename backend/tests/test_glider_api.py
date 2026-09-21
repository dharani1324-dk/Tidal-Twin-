"""Real glider deployment API tests (features #16/#17).

The real deployments are downloaded off-line by `scripts.fetch_glider`; until
then the DB has no glider rows, so the endpoints must honestly report none.
These tests prove the honest empty state and a full synthetic round-trip: a
tiny GliderDAC-format NetCDF (physical + BGC fields, one QC-NaN) is ingested
exactly like `scripts.ingest_glider` would, then served through /deployments,
/{deployment}/samples and /{deployment}/bgc.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from app.core.database import SessionLocal
from app.models.glider import GliderProfile as G
from scripts.ingest_glider import ingest_file

_TMP = tempfile.TemporaryDirectory()
GLIDER_FIXTURE = Path(_TMP.name) / "ngdac_test_001.nc"

DEPLOYMENT = "NGDAC-TEST-001"


def _clear_gliders() -> None:
    db = SessionLocal()
    try:
        db.query(G).filter(G.deployment_id == DEPLOYMENT).delete()
        db.commit()
    finally:
        db.close()


def tearDownModule():
    _clear_gliders()
    _TMP.cleanup()


def _ingest_synthetic_deployment() -> None:
    times = np.array([f"2026-01-0{i+1}T03:00:00Z" for i in range(5)], dtype="datetime64[s]")
    ds = xr.Dataset(
        {
            "trajectory": ("time", np.array([DEPLOYMENT] * 5)),
            "latitude": ("time", np.array([25.0, 25.02, 25.04, 25.06, 25.08])),
            "longitude": ("time", np.array([-70.0, -70.03, -70.06, -70.09, -70.12])),
            "pressure": ("time", np.array([0.0, 50.0, 100.0, 150.0, 200.0])),
            "depth": ("time", np.array([0.0, 49.0, 99.0, 148.0, 199.0])),
            "temperature": ("time", np.array([21.0, 20.5, 20.0, 19.5, np.nan])),
            "salinity": ("time", np.array([35.0, 35.2, 35.1, 35.0, np.nan])),
            # sample 1: oxygen QC'd to NaN; sample 3: chlorophyll QC'd to NaN;
            # sample 4: NO measured field at all -> must be skipped on ingest.
            "dissolved_oxygen": ("time", np.array([0.22, np.nan, 0.21, 0.19, np.nan])),
            "chlorophyll": ("time", np.array([0.9, 0.5, 0.4, np.nan, np.nan])),
            "nitrate": ("time", np.array([8.0, 7.5, 7.0, 6.5, np.nan])),
        },
        coords={"time": times},
        attrs={"deployment_name": DEPLOYMENT, "platform_type": "SEAGLIDER"},
    )
    ds.to_netcdf(GLIDER_FIXTURE)
    ingest_file(GLIDER_FIXTURE, reingest=True)


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


class GliderEmptyTest(unittest.TestCase):
    def setUp(self):
        _clear_gliders()
        self.client = _client()

    def test_deployments_report_none_honestly(self):
        res = self.client.get("/api/v1/glider/deployments")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["count"], 0)

    def test_unknown_deployment_is_404_not_fabricated(self):
        res = self.client.get("/api/v1/glider/NGDAC-MISSING/samples")
        self.assertEqual(res.status_code, 404)


class GliderSyntheticRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.client = _client()

    def test_round_trip_physical_and_bgc(self):
        _ingest_synthetic_deployment()
        try:
            res = self.client.get("/api/v1/glider/deployments")
            body = res.json()
            self.assertEqual(body["count"], 1)
            dep = body["deployments"][0]
            self.assertEqual(dep["deployment_id"], DEPLOYMENT)
            self.assertEqual(dep["samples"], 4)  # sample 4 carried no measured field
            self.assertEqual(dep["depth_max_m"], 148.0)  # de/us: the 199 m sample carried no field
            self.assertEqual(dep["bgc_samples"]["dissolved_oxygen"], 3)
            self.assertEqual(dep["bgc_samples"]["chlorophyll"], 3)
            self.assertEqual(dep["bgc_samples"]["nitrate"], 4)

            samples = self.client.get(f"/api/v1/glider/{DEPLOYMENT}/samples").json()
            self.assertEqual(len(samples["samples"]), 4)
            self.assertEqual(samples["samples"][0]["temperature"], 21.0)
            self.assertEqual(samples["samples"][0]["salinity"], 35.0)
            self.assertEqual(samples["samples"][3]["temperature"], 19.5)

            bgc = self.client.get(f"/api/v1/glider/{DEPLOYMENT}/bgc").json()
            self.assertTrue(bgc["fields"]["dissolved_oxygen"])
            self.assertTrue(bgc["fields"]["chlorophyll"])
            oxy_vals = [s["dissolved_oxygen"] for s in bgc["samples"] if s["dissolved_oxygen"] is not None]
            self.assertTrue(any(abs(x - 0.22) < 1e-5 for x in oxy_vals))
            self.assertIn(None, [s["dissolved_oxygen"] for s in bgc["samples"]])  # QC-NaN -> NULL
            # sample 3's chlorophyll was QC'd to NaN inside a BGC sample row
            chl_at_nit65 = [s["chlorophyll"] for s in bgc["samples"] if s["nitrate"] is not None and abs(s["nitrate"] - 6.5) < 1e-5]
            self.assertEqual(chl_at_nit65, [None])
        finally:
            _clear_gliders()


if __name__ == "__main__":
    unittest.main()