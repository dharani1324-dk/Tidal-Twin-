"""Offline tests for scripts/fetch_chlor (real satellite Chl-a provisioning)."""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import xarray as xr

import scripts.fetch_chlor as fc

DEFAULT_BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)


class MonthWindowTest(unittest.TestCase):
    def test_month_window_normal(self):
        t0, t1 = fc._month_window("2021-09")
        self.assertEqual(t0, "2021-09-01T00:00:00Z")
        self.assertEqual(t1, "2021-10-01T00:00:00Z")

    def test_month_window_december_wraps_to_january(self):
        t0, t1 = fc._month_window("2020-12")
        self.assertEqual(t0, "2020-12-01T00:00:00Z")
        self.assertEqual(t1, "2021-01-01T00:00:00Z")


class BuildUrlTest(unittest.TestCase):
    def test_build_url_constrains_var_time_and_box(self):
        url, params = fc.build_url("2021-09", DEFAULT_BOX)
        self.assertEqual(url, "https://coastwatch.pfeg.noaa.gov/erddap/griddap/nesdisVHNchlaDaily.nc")
        (constraint,) = params.keys()
        self.assertIn("chlor_a[(2021-09-01T00:00:00Z):1:(2021-10-01T00:00:00Z)]", constraint)
        self.assertIn("[(0.0):1:(26.0)]", constraint)
        self.assertIn("[(60.0):1:(100.0)]", constraint)


class FetchAndCompositeTest(unittest.TestCase):
    def _daily_ds(self, data, lats=(73.0,), lons=(20.0, 30.0, 40.0)):
        return xr.Dataset(
            {"chlor_a": (("time", "lat", "lon"), data)},
            coords={
                "time": np.array(["2021-09-25", "2021-09-26"], dtype="datetime64[s]"),
                "lat": list(lats),
                "lon": list(lons),
            },
        )

    def _mock_get(self, ds: xr.Dataset):
        content = ds.to_netcdf()
        resp = Mock()
        resp.content = content
        resp.raise_for_status = Mock()
        return resp

    def test_composites_monthly_mean_and_writes_provenance(self):
        # Cell (73,20): 0.6 then 0.5 -> mean 0.55
        # Cell (73,30): 0.9 then NaN  -> mean 0.9 (single day, kept)
        # Cell (73,40): NaN both days -> mean NaN (kept missing)
        data = np.array([[[0.6, 0.9, np.nan]], [[0.5, np.nan, np.nan]]])
        ds = self._daily_ds(data)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "chl_monthly_2021-09.nc"
            with patch.object(fc.requests, "get", return_value=self._mock_get(ds)) as m:
                summary = fc.fetch_and_composite("2021-09", DEFAULT_BOX, str(out_path))
            self.assertEqual(summary["month"], "2021-09")
            self.assertEqual(summary["days"], 2)
            self.assertEqual(summary["cells"], 2)
            self.assertEqual(summary["dataset"], fc.DATASET_ID)
            self.assertTrue(out_path.exists())

            url, params = m.call_args
            self.assertIn("nesdisVHNchlaDaily.nc", url[0])

            out = xr.open_dataset(out_path)
            try:
                assert out.chlor_a.values.shape == (1, 1, 3)
                self.assertEqual(np.datetime64(out["time"].values[0], "s"),
                                 np.datetime64("2021-09-15T00:00:00Z"))
                self.assertAlmostEqual(float(out.chlor_a.values[0, 0, 0]), 0.55, places=5)
                self.assertAlmostEqual(float(out.chlor_a.values[0, 0, 1]), 0.9, places=5)
                self.assertTrue(np.isnan(float(out.chlor_a.values[0, 0, 2])))
                self.assertEqual(out.chlor_a.attrs["standard_name"], fc.STANDARD_NAME)
                self.assertEqual(out.chlor_a.attrs["units"], fc.UNITS)
                self.assertEqual(out.attrs["dataset_id"], fc.DATASET_ID)
                self.assertIn("monthly mean (2021-09)", out.attrs["title"])
                self.assertIn("Composited by scripts.fetch_chlor", out.attrs["history"])
            finally:
                out.close()

    def test_missing_variable_exits_cleanly(self):
        content = xr.Dataset({"other": (("lat", "lon"), [[1.0, 2.0]])},
                             coords={"lat": [73.0], "lon": [20.0, 30.0]}).to_netcdf()
        resp = Mock()
        resp.content = content
        resp.raise_for_status = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(fc.requests, "get", return_value=resp):
                with self.assertRaises(SystemExit):
                    fc.fetch_and_composite("2021-09", DEFAULT_BOX,
                                           str(Path(tmp) / "x.nc"))


class MainTest(unittest.TestCase):
    def test_invalid_box_exits(self):
        with patch.object(sys, "argv", ["fetch_chlor", "--lat0", "26.0", "--lat1", "0.0"]):
            with self.assertRaises(SystemExit):
                fc.main()


if __name__ == "__main__":
    unittest.main()