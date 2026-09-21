"""Offline tests for scripts/fetch_glider (real glider deployment provisioning)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import xarray as xr

import scripts.fetch_glider as fg


def _sample_ds(n=5):
    """A tiny GliderDAC-format dataset as ERDDAP tabledap would return it."""
    times = np.array([f"2026-01-0{i+1}T03:00:00Z" for i in range(n)], dtype="datetime64[s]")
    return xr.Dataset(
        {
            "trajectory": ("time", np.array(["NGDAC-TEST-001"] * n)),
            "latitude": ("time", np.array([25.0 + i * 0.02 for i in range(n)])),
            "longitude": ("time", np.array([-70.0 + i * 0.03 for i in range(n)])),
            "pressure": ("time", np.array([0.0, 50.0, 100.0, 150.0, 200.0])),
            "depth": ("time", np.array([0.0, 49.0, 99.0, 148.0, 199.0])),
            "temperature": ("time", np.linspace(21.0, 21.0 - 0.5 * (n - 1), n)),
            "salinity": ("time", np.full(n, 35.0)),
            "dissolved_oxygen": ("time", np.array([0.22, 0.21, np.nan, 0.19, 0.18])),
            "chlorophyll": ("time", np.array([0.9, 0.5, 0.4, np.nan, 0.2])),
            "nitrate": ("time", np.array([8.0, 7.5, 7.0, 6.5, 6.0])),
        },
        coords={"time": times},
        attrs={"deployment_name": "NGDAC-TEST-001", "platform_type": "SEAGLIDER"},
    )


def _mock(content):
    resp = Mock()
    resp.content = content
    resp.raise_for_status = Mock()
    return resp


class BuildUrlTest(unittest.TestCase):
    def test_build_url_lists_fields_without_window(self):
        url = fg.build_url("ioos-gliderdac-sp011-20160602T1624", None, None)
        self.assertTrue(url.startswith("https://gliders.ioos.us/erddap/tabledap/"
                                       "ioos-gliderdac-sp011-20160602T1624.nc?"))
        for field in ("trajectory", "time", "latitude", "longitude", "pressure",
                      "temperature", "salinity", "dissolved_oxygen", "chlorophyll", "nitrate"):
            self.assertIn(field, url)

    def test_build_url_appends_time_window(self):
        url = fg.build_url("ioos-gliderdac-x", "2016-06-02", "2016-09-01")
        self.assertIn("time>=2016-06-02T00:00:00Z", url)
        self.assertIn("time<=2016-09-01T23:59:59Z", url)


class FetchDeploymentTest(unittest.TestCase):
    def test_fetch_writes_subset_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "glider_mock.nc"
            with patch.object(fg.requests, "get", return_value=_mock(_sample_ds().to_netcdf())) as m:
                summary = fg.fetch_deployment("ioos-gliderdac-ngdac-test-001", str(out))
            self.assertEqual(summary["samples"], 5)
            self.assertEqual(summary["dataset"], "ioos-gliderdac-ngdac-test-001")
            self.assertEqual(len(summary["fields"]), 5)
            self.assertTrue(out.exists())
            url = m.call_args[0][0]
            self.assertIn("ioos-gliderdac-ngdac-test-001.nc", url)
            with xr.open_dataset(out) as ds:
                self.assertEqual(ds.sizes["time"], 5)
                self.assertIn("Fetched by scripts.fetch_glider", ds.attrs["history"])
                self.assertEqual(ds.attrs["dataset_id"], "ioos-gliderdac-ngdac-test-001")

    def test_no_measurements_exits_cleanly(self):
        empty = xr.Dataset(coords={"time": np.array([], dtype="datetime64[s]")},
                           attrs={"deployment_name": "EMPTY"})
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(fg.requests, "get", return_value=_mock(empty.to_netcdf())):
                with self.assertRaises(SystemExit):
                    fg.fetch_deployment("ioos-gliderdac-empty", str(Path(tmp) / "empty.nc"))


class MainTest(unittest.TestCase):
    def test_dataset_is_required(self):
        with patch.object(sys, "argv", ["fetch_glider"]):
            with self.assertRaises(SystemExit):
                fg.main()


if __name__ == "__main__":
    unittest.main()