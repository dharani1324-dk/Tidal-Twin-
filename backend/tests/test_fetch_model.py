"""Offline tests for scripts/fetch_model (real HYCOM 3D grid provisioning)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import xarray as xr

import scripts.fetch_model as fm

DEFAULT_BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)

LATS = (5.0, 6.0, 7.0)
LONS = (60.0, 61.0, 62.0, 63.0)


def _ds(alias: str, depth: float, base: float):
    """A tiny griddap-shaped NetCDF with two time frames; var has no depth dim
    (constrained to one level), depth kept as a scalar coord — just like ERDDAP."""
    data = np.full((2, 3, 4), float(base), dtype="float32")
    data[:, 1, 2] = base + 0.5  # a gradient so means are meaningful
    arr = xr.DataArray(
        data,
        dims=("time", "lat", "lon"),
        coords={
            "time": np.array(["2021-09-25", "2021-09-26"], dtype="datetime64[s]"),
            "lat": list(LATS),
            "lon": list(LONS),
        },
        name=alias,
    )
    return xr.Dataset({alias: arr}, coords={"depth": [float(depth)], "lat": list(LATS), "lon": list(LONS)})


def _handler(base_by_var: dict):
    """Build a requests.get side effect that returns the right tiny dataset per URL."""
    def handler(*args, **kwargs):
        url = args[0]
        var = url.split(".nc?")[1].split("[")[0]
        import re
        m = re.search(r"\[\(([-\d.]+)\):1:\(", url)
        depth = float(m.group(1))
        if var not in base_by_var:
            raise AssertionError(f"unexpected request for {var!r}: {url}")
        if base_by_var[var] is None:
            # Simulate the variable being absent from the server: only an
            # unrelated field (air_temp) is returned.
            content = xr.Dataset(
                {"air_temp": (("time", "lat", "lon"), np.full((2, 3, 4), 30.0, dtype="float32"))},
                coords={"time": np.array(["2021-09-25", "2021-09-26"], dtype="datetime64[s]"),
                        "lat": list(LATS), "lon": list(LONS)},
            ).to_netcdf()
            resp = Mock()
            resp.content = content
            resp.raise_for_status = Mock()
            return resp
        content = _ds(var, depth, base_by_var[var]).to_netcdf()
        resp = Mock()
        resp.content = content
        resp.raise_for_status = Mock()
        return resp
    return handler


class MonthWindowTest(unittest.TestCase):
    def test_month_window_december_wraps(self):
        t0, t1 = fm._month_window("2020-12")
        self.assertEqual(t0, "2020-12-01T00:00:00Z")
        self.assertEqual(t1, "2021-01-01T00:00:00Z")


class BuildUrlTest(unittest.TestCase):
    def test_build_url_pins_var_level_and_box(self):
        url = fm.build_url("2021-09", DEFAULT_BOX, 100.0, "water_temp")
        self.assertTrue(url.startswith(
            "https://coastwatch.pfeg.noaa.gov/erddap/griddap/nrlHycomGLBu008e909D_LonPM180.nc?"))
        self.assertIn("water_temp[(2021-09-01T00:00:00Z):1:(2021-10-01T00:00:00Z)]", url)
        self.assertIn("[(100.0):1:(100.0)]", url)
        self.assertIn("[(0.0):1:(26.0)]", url)
        self.assertIn("[(60.0):1:(100.0)]", url)


class FetchModelTest(unittest.TestCase):
    def test_composites_3d_grid_with_current_speed(self):
        bases = {"water_temp": 21.0, "sea_water_salinity": 35.0, "water_u": 0.3, "water_v": 0.4}
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "hycom_3d_2021-09.nc"
            with patch.object(fm.requests, "get", side_effect=_handler(bases)):
                summary = fm.fetch_model("2021-09", [0.0, 100.0], DEFAULT_BOX, str(out_path))

            self.assertEqual(summary["month"], "2021-09")
            self.assertEqual(sorted(summary["depths"]), [0.0, 100.0])
            self.assertEqual(sorted(summary["variables"]),
                             ["sea_water_current_speed", "sea_water_current_u",
                              "sea_water_current_v", "sea_water_salinity", "sea_water_temperature"])
            self.assertEqual(summary["warnings"], [])
            self.assertTrue(out_path.exists())

            out = xr.open_dataset(out_path)
            try:
                self.assertEqual(out["sea_water_temperature"].values.shape, (1, 2, 3, 4))
                self.assertEqual(list(out["depth"].values), [0.0, 100.0])
                # temp frames 21.5 & 21.5 -> mean 21.5 at cell (lat=1, lon=2)
                self.assertAlmostEqual(float(out["sea_water_temperature"].values[0, 0, 1, 2]),
                                       21.5, places=3)
                # speed = hypot(0.3, 0.4) = 0.5
                self.assertAlmostEqual(float(out["sea_water_current_speed"].values[0, 0, 0, 0]),
                                       0.5, places=5)
                # true components preserved (feature #14): arrows are real u/v
                self.assertAlmostEqual(float(out["sea_water_current_u"].values[0, 0, 0, 0]),
                                       0.3, places=5)
                self.assertAlmostEqual(float(out["sea_water_current_v"].values[0, 0, 0, 0]),
                                       0.4, places=5)
                # CF metadata so ingest_netcdf can find every axis
                for axis in ("time", "lat", "lon", "depth"):
                    self.assertEqual(out[axis].attrs["axis"], {"time": "T", "lat": "Y", "lon": "X", "depth": "Z"}[axis])
                self.assertEqual(out["sea_water_temperature"].attrs["standard_name"], "sea_water_temperature")
                self.assertEqual(out["sea_water_current_speed"].attrs["standard_name"], "sea_water_speed")
                self.assertEqual(out["sea_water_current_u"].attrs["standard_name"], "eastward_sea_water_velocity")
                self.assertEqual(out["sea_water_current_v"].attrs["standard_name"], "northward_sea_water_velocity")
                self.assertEqual(out.attrs["dataset_id"], fm.DATASET_ID)
                self.assertIn("HYCOM", out.attrs["title"])
                self.assertIn("scripts.fetch_model", out.attrs["history"])
            finally:
                out.close()

    def test_missing_variable_is_reported_not_fabricated(self):
        # Salinity never arrives -> the file simply omits it and warns, honestly.
        bases = {"water_temp": 21.0, "sea_water_salinity": None, "water_u": 0.3, "water_v": 0.4}
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "hycom_3d_2021-09.nc"
            with patch.object(fm.requests, "get", side_effect=_handler(bases)):
                summary = fm.fetch_model("2021-09", [0.0], DEFAULT_BOX, str(out_path))
            self.assertTrue(any("salinity" in w.lower() for w in summary["warnings"]))
            self.assertNotIn("sea_water_salinity", summary["variables"])
            self.assertIn("sea_water_temperature", summary["variables"])


class MainTest(unittest.TestCase):
    def test_invalid_box_exits(self):
        with patch.object(sys, "argv", ["fetch_model", "--lat0", "26.0", "--lat1", "0.0"]):
            with self.assertRaises(SystemExit):
                fm.main()


if __name__ == "__main__":
    unittest.main()