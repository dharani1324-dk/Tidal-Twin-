"""OGC / CF metadata validation tests (feature #22).

Proves the honest validator + endpoints:
  - a well-formed CF file validates cleanly (axes, ranges, monotonicity,
    conventions, known standard_name and units)
  - lat out of physical range -> invalid with a specific reason
  - non-monotonic axes -> invalid
  - unknown / missing standard_name and missing units -> surfaced honestly
  - unreadable / missing files are reported, not hand-waved
  - the ingest preflight hook reports ok / errors / warnings
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from app.modules.ai import netcdf_validate as V

_TMP = tempfile.TemporaryDirectory()


def tearDownModule():
    _TMP.cleanup()


def _write(ds, name):
    path = Path(_TMP.name) / name
    ds.to_netcdf(path)
    return path


def _valid_ds():
    ds = xr.Dataset(
        {
            "sst": (("lat", "lon"), np.full((3, 4), 27.5)),
            "chlor_a": (("lat", "lon"), np.full((3, 4), 0.6)),
        },
        coords={
            "lat": ("lat", [5.0, 10.0, 15.0]),
            "lon": ("lon", [65.0, 70.0, 75.0, 80.0]),
        },
        attrs={"Conventions": "CF-1.8"},
    )
    ds["sst"].attrs = {
        "standard_name": "sea_surface_temperature",
        "units": "degC",
    }
    ds["chlor_a"].attrs = {
        "standard_name": "mass_concentration_of_chlorophyll_a_in_sea_water",
        "units": "mg m-3",
    }
    return ds


class CfValidatorTest(unittest.TestCase):
    def test_valid_file_passes_all_checks(self):
        report = V.validate_netcdf(_write(_valid_ds(), "ok.nc"))
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["passed"]["axes"])
        self.assertTrue(report["passed"]["ranges"])
        self.assertTrue(report["passed"]["monotonicity"])
        self.assertTrue(report["passed"]["conventions"])
        self.assertTrue(report["passed"]["standard_names"])
        self.assertTrue(report["passed"]["units"])
        self.assertEqual(len(report["variables"]), 2)

    def test_lat_out_of_physical_range_is_invalid(self):
        ds = _valid_ds()
        ds = ds.assign_coords(lat=("lat", [5.0, 10.0, 95.0]))
        report = V.validate_netcdf(_write(ds, "bad-lat.nc"))
        self.assertFalse(report["valid"])
        self.assertFalse(report["passed"]["ranges"])
        self.assertTrue(any("physical range" in e for e in report["errors"]))

    def test_non_monotonic_axes_are_invalid(self):
        ds = _valid_ds()
        ds = ds.assign_coords(lon=("lon", [65.0, 80.0, 75.0, 70.0]))
        report = V.validate_netcdf(_write(ds, "zigzag.nc"))
        self.assertFalse(report["valid"])
        self.assertFalse(report["passed"]["monotonicity"])
        self.assertTrue(any("monotonically" in e for e in report["errors"]))

    def test_missing_axes_are_an_error(self):
        ds = xr.Dataset({"sst": ("x", [1.0, 2.0])},
                        coords={"x": [0, 1]}, attrs={"Conventions": "CF-1.8"})
        ds["sst"].attrs = {"standard_name": "sea_surface_temperature", "units": "degC"}
        report = V.validate_netcdf(_write(ds, "no-axis.nc"))
        self.assertFalse(report["valid"])
        self.assertTrue(any("no latitude/longitude axis" in e for e in report["errors"]))

    def test_missing_metadata_is_warned_but_axes_still_pass(self):
        ds = _valid_ds()
        ds["sst"].attrs = {}
        ds["chlor_a"].attrs = {"standard_name": "totally_custom_thing", "units": "X"}
        report = V.validate_netcdf(_write(ds, "sparse.nc"))
        self.assertTrue(report["valid"], report["errors"])
        self.assertTrue(any("no standard_name" in w for w in report["warnings"]))
        self.assertTrue(any("not in the twin's recognised set" in w for w in report["warnings"]))
        self.assertFalse(report["passed"]["standard_names"])

    def test_illegal_units_are_invalid(self):
        ds = _valid_ds()
        ds["sst"].attrs = {"standard_name": "sea_surface_temperature", "units": "degC !"}
        report = V.validate_netcdf(_write(ds, "units.nc"))
        self.assertFalse(report["valid"])
        self.assertTrue(any("illegal unit" in e for e in report["errors"]))
        self.assertFalse(report["passed"]["units"])

    def test_missing_file_is_honest(self):
        report = V.validate_netcdf(Path(_TMP.name) / "nope.nc")
        self.assertFalse(report["valid"])
        self.assertIn("file not found", report["errors"])

    def test_preflight_short_form(self):
        report = V.preflight(_write(_valid_ds(), "preflight.nc"))
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], [])
        bad = V.preflight(_write(_valid_ds().assign_coords(lat=("lat", [5.0, 10.0, 95.0]), ),
                                  "bad-preflight.nc"))
        self.assertFalse(bad["ok"])
        self.assertTrue(any("physical range" in e for e in bad["errors"]))


class CfApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_upload_valid_file(self):
        path = _write(_valid_ds(), "upload-ok.nc")
        raw = path.read_bytes()
        res = self.client.post("/api/v1/cf/validate",
                               content=raw,
                               headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["valid"])
        self.assertTrue(body["passed"]["axes"])
        self.assertTrue(body["passed"]["conventions"])
        self.assertEqual(len(body["variables"]), 2)

    def test_upload_invalid_file(self):
        ds = _valid_ds().assign_coords(lat=("lat", [5.0, 10.0, 200.0]))
        path = _write(ds, "upload-bad.nc")
        res = self.client.post("/api/v1/cf/validate",
                               content=path.read_bytes(),
                               headers={"Content-Type": "application/octet-stream"})
        body = res.json()
        self.assertFalse(body["valid"])
        self.assertTrue(any("physical range" in e for e in body["errors"]))

    def test_get_missing_path_is_honest_404_body(self):
        res = self.client.get("/api/v1/cf/validate",
                              params={"path": "data/nonexistent/x.nc"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["valid"])
        self.assertTrue(any("file not found" in e for e in body["errors"]))

    def test_get_real_file_path(self):
        path = _write(_valid_ds(), "real-path.nc")
        res = self.client.get("/api/v1/cf/validate", params={"path": str(path)})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["valid"])


if __name__ == "__main__":
    unittest.main()