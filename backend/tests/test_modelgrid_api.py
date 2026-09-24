"""Real ocean-model 3D grid API tests (features #3/#5/#6/#7).

The real HYCOM grid is downloaded off-line by `scripts.fetch_model`; until then
the DB has no 3D grid rows, so the endpoints must honestly report "no data".
These tests prove both the honest empty state and a full synthetic round-trip:
a tiny 3D NetCDF (temperature/salinity/current speed at two depth levels) is
ingested exactly like `scripts.ingest_netcdf` would, then served through
/summary, /latest (depth slices) and /profile.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from app.core.database import SessionLocal
from app.models.netcdf import NetcdfReadings as N
from scripts.ingest_netcdf import ingest_file

_TMP = tempfile.TemporaryDirectory()
GRID_FIXTURE = Path(_TMP.name) / "synthetic_hycom_3d.nc"

GRID_VARS = ["sea_water_temperature", "sea_water_salinity", "sea_water_current_speed",
             "sea_water_current_u", "sea_water_current_v"]


def _clear_grid() -> None:
    db = SessionLocal()
    try:
        db.query(N).filter(N.variable_name.in_(GRID_VARS)).delete()
        db.commit()
    finally:
        db.close()


def tearDownModule():
    _clear_grid()
    _TMP.cleanup()


def _ingest_synthetic_3d_grid() -> None:
    lats = [5.0, 6.0, 7.0]
    lons = [60.0, 61.0, 62.0, 63.0]
    depths = [0.0, 100.0]
    keep = np.ones((1, 2, 3, 4), dtype=bool)
    keep[0, 1, 1, 2] = False  # one 100 m-cell NaN -> skipped by ingest, surface stays real

    def var3d(name, base, sn, units):
        v = np.full((1, 2, 3, 4), float(base), dtype="float32")
        v[0, :, 0, 0] = base + 1.0  # a zonal gradient
        v = np.where(keep, v, np.nan)  # the deep NaN cell stays missing
        return xr.DataArray(v, dims=("time", "depth", "lat", "lon"),
                            coords={"time": [np.datetime64("2021-09-15T00:00:00")],
                                    "depth": depths, "lat": lats, "lon": lons},
                            attrs={"standard_name": sn, "units": units})

    ds = xr.Dataset(
        {
            "sea_water_temperature": var3d("t", 22.0, "sea_water_temperature", "degC"),
            "sea_water_salinity": var3d("s", 35.0, "sea_water_salinity", "PSU"),
            "sea_water_current_speed": var3d("c", 0.5, "sea_water_speed", "m/s"),
            "sea_water_current_u": var3d("u", 0.3, "eastward_sea_water_velocity", "m/s"),
            "sea_water_current_v": var3d("v", 0.4, "northward_sea_water_velocity", "m/s"),
        },
        coords={
            "time": [np.datetime64("2021-09-15T00:00:00")],
            "depth": depths, "lat": lats, "lon": lons,
        },
    )
    for axis, val in (("time", "T"), ("lat", "Y"), ("lon", "X"), ("depth", "Z")):
        ds[axis].attrs["axis"] = val
    ds.to_netcdf(GRID_FIXTURE)
    ingest_file(GRID_FIXTURE, reingest=True)


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


class ModelGridEmptyTest(unittest.TestCase):
    def setUp(self):
        _clear_grid()
        self.client = _client()

    def test_summary_reports_no_grid_honestly(self):
        res = self.client.get("/api/v1/modelgrid/summary")
        self.assertEqual(res.status_code, 200)
        body = res.json()["available_fields"]
        for var in body:
            self.assertFalse(body[var]["available"])
            self.assertIn("fetch_model", body[var]["reason"])

    def test_latest_and_profile_report_no_grid_honestly(self):
        res = self.client.get("/api/v1/modelgrid/latest",
                              params={"variable": "temperature", "depth_m": 0})
        body = res.json()
        self.assertFalse(body["available"])
        self.assertIn("fetch_model", body["reason"])

        prof = self.client.get("/api/v1/modelgrid/profile",
                               params={"variable": "salinity", "latitude": 6.0, "longitude": 61.0})
        pb = prof.json()
        self.assertFalse(pb["found"])
        self.assertIn("fetch_model", pb["reason"])

    def test_unknown_variable_is_rejected_honestly(self):
        res = self.client.get("/api/v1/modelgrid/latest",
                              params={"variable": "pressure", "depth_m": 0})
        body = res.json()
        self.assertFalse(body["available"])
        self.assertIn("Unknown variable", body["reason"])


class ModelGridSyntheticRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.client = _client()

    def test_3d_grid_round_trip(self):
        _ingest_synthetic_3d_grid()
        try:
            # --- summary: all three fields at two depth levels ---
            res = self.client.get("/api/v1/modelgrid/summary")
            fields = res.json()["available_fields"]
            for var in ("temperature", "salinity", "current_speed"):
                self.assertTrue(fields[var]["available"], var)
                self.assertEqual(fields[var]["month"], "2021-09")
                self.assertEqual([lvl["depth_m"] for lvl in fields[var]["levels"]], [0.0, 100.0])
                # 3 lat x 4 lon minus the one NaN deep cell at each level
                self.assertIn(fields[var]["levels"][0]["cells"], (11, 12))

            # --- depth slice: surface only returns surface cells ---
            sfc = self.client.get("/api/v1/modelgrid/latest",
                                  params={"variable": "temperature", "depth_m": 0})
            sb = sfc.json()
            self.assertTrue(sb["available"])
            self.assertEqual(sb["depth_m"], 0.0)
            self.assertEqual(sb["rows"], 12)  # 3x4, all finite at surface
            self.assertEqual(sb["depths"], [0.0, 100.0])
            for c in sb["cells"]:
                self.assertIn(c["value"], (22.0, 23.0))  # 23 = the zonal-gradient cell

            # --- depth slice: an absent level is honest, not empty craft ---
            missing = self.client.get("/api/v1/modelgrid/latest",
                                      params={"variable": "temperature", "depth_m": 500})
            mb = missing.json()
            self.assertFalse(mb["available"])
            self.assertIn("depth", mb["reason"].lower())
            self.assertEqual(mb["month"], "2021-09")

            # --- vertical profile at a grid point: two sorted levels ---
            prof = self.client.get("/api/v1/modelgrid/profile",
                                   params={"variable": "temperature", "latitude": 6.0, "longitude": 61.0})
            pb = prof.json()
            self.assertTrue(pb["found"])
            self.assertEqual([l["depth_m"] for l in pb["levels"]], [0.0, 100.0])
            self.assertTrue(all(l["value"] == 22.0 for l in pb["levels"]))
            self.assertLessEqual(pb["distance_deg"], 0.5)

            # --- profile far from any cell is reported honestly (nearest ~0.7°, limit 0.1°) ---
            far = self.client.get("/api/v1/modelgrid/profile",
                                  params={"variable": "salinity", "latitude": 6.5, "longitude": 62.5,
                                          "max_dist_deg": 0.1})
            fb = far.json()
            self.assertFalse(fb["found"])
            self.assertIn("no real", fb["reason"].lower())

            # --- current speed slice is served too (feature #14 vector field material) ---
            cur = self.client.get("/api/v1/modelgrid/latest",
                                  params={"variable": "current_speed", "depth_m": 100})
            cb = cur.json()
            self.assertTrue(cb["available"])
            self.assertEqual(cb["rows"], 11)  # the deep-level NaN cell is skipped

            # --- feature #14: TRUE current velocity vectors (real u/v per cell) ---
            vecs = self.client.get("/api/v1/modelgrid/vectors", params={"depth_m": 0})
            vb = vecs.json()
            self.assertTrue(vb["available"], vb)
            self.assertEqual(vb["month"], "2021-09")
            self.assertEqual(vb["rows"], 12)  # 3x4 surface cells, u AND v present
            for c in vb["cells"]:
                # (5.0, 60.0) carries the zonal-gradient cell (u=1.3, v=1.4)
                if c["latitude"] == 5.0 and c["longitude"] == 60.0:
                    self.assertAlmostEqual(c["u"], 1.3, places=4)
                    self.assertAlmostEqual(c["v"], 1.4, places=4)
                    self.assertAlmostEqual(c["speed"], 1.91, places=1)
                else:
                    self.assertAlmostEqual(c["u"], 0.3, places=4)
                    self.assertAlmostEqual(c["v"], 0.4, places=4)
                    self.assertAlmostEqual(c["speed"], 0.5, places=4)

            deep_vecs = self.client.get("/api/v1/modelgrid/vectors", params={"depth_m": 100})
            dvb = deep_vecs.json()
            self.assertTrue(dvb["available"])
            self.assertEqual(dvb["rows"], 11)  # the deep NaN cell drops out of BOTH components

            # u/v are also directly queryable as 2D slices
            u_slice = self.client.get("/api/v1/modelgrid/latest",
                                      params={"variable": "current_u", "depth_m": 0})
            self.assertTrue(u_slice.json()["available"])
            self.assertEqual(u_slice.json()["rows"], 12)
        finally:
            _clear_grid()


class ModelGridVectorsEmptyTest(unittest.TestCase):
    def setUp(self):
        _clear_grid()
        self.client = _client()

    def test_vectors_report_no_data_honestly(self):
        res = self.client.get("/api/v1/modelgrid/vectors", params={"depth_m": 0})
        body = res.json()
        self.assertFalse(body["available"])
        self.assertIn("fetch_model", body["reason"])


if __name__ == "__main__":
    unittest.main()