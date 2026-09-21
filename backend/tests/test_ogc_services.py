"""OGC WMS / WCS endpoint tests (feature #21).

Seeds a small deterministic real-shape grid (sst + chlor_a) at time 2099-01
so the OGC services have something honest to publish, then asserts:
  - WMS 1.3.0 GetCapabilities lists the layers + GetMap operation
  - GetMap returns a genuine PNG raster (right size, colored, transparent gaps)
  - GetMap over empty territory -> OGC ServiceException with an honest reason
  - unknown layer -> 400 LayerNotDefined (never a fabricated image)
  - WCS 2.0.1 GetCapabilities lists the coverage ids + netCDF format
  - GetCoverage returns a CF-annotated netCDF we can open and read back
  - GetCoverage over empty territory / unknown id -> ServiceException
"""

import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import xarray as xr
from PIL import Image

from app.core.database import SessionLocal
from app.models.netcdf import NetcdfReadings as NR

_TMP = tempfile.TemporaryDirectory()
SYNTH_TIME = datetime(2099, 1, 1, 0, 0, 0)
LATS = [5.0, 8.0, 11.0, 14.0, 17.0]
LONS = [68.0, 70.0, 72.0, 74.0, 76.0]


def _seed_grid():
    db = SessionLocal()
    try:
        for var, standard_name, units in (("sst", "sea_surface_temperature", "degC"),
                                          ("chlor_a", "mass_concentration_of_chlorophyll_a_in_sea_water", "mg m-3")):
            for la in LATS:
                for lo in LONS:
                    value = 20.0 + 0.3 * la + 0.05 * lo
                    if var == "chlor_a":
                        value = 0.05 + 0.01 * la + 0.005 * lo
                    db.add(NR(
                        latitude=la, longitude=lo, depth_m=0.0, time=SYNTH_TIME,
                        variable_name=var, value=value,
                        standard_name=standard_name, units=units,
                        source_file="ogc-test-synthetic",
                    ))
        db.commit()
    finally:
        db.close()


def _clear_grid():
    db = SessionLocal()
    try:
        db.query(NR).filter(NR.source_file == "ogc-test-synthetic").delete()
        db.commit()
    finally:
        db.close()


def tearDownModule():
    _clear_grid()
    _TMP.cleanup()


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


class OgcWmsTest(unittest.TestCase):
    def setUp(self):
        self.client = _client()
        _seed_grid()

    def tearDown(self):
        _clear_grid()

    def test_getcapabilities_lists_layers_and_operations(self):
        res = self.client.get("/api/v1/ogc/wms",
                              params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/xml", res.headers["content-type"])
        xml = res.text
        self.assertIn("TidalTwin", xml)
        self.assertIn("<Name>sst</Name>", xml)
        self.assertIn("<Name>chlor_a</Name>", xml)
        self.assertIn("GetMap", xml)
        self.assertIn("<Format>image/png</Format>", xml)

    def test_getmap_returns_real_png_raster(self):
        res = self.client.get("/api/v1/ogc/wms", params={
            "service": "WMS", "request": "GetMap", "version": "1.3.0",
            "layers": "sst", "bbox": "65,0,80,20", "width": "200", "height": "100",
            "format": "image/png", "transparent": "true",
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("image/png", res.headers["content-type"])
        self.assertTrue(res.content.startswith(b"\x89PNG\r\n\x1a\n"))
        img = Image.open(io.BytesIO(res.content))
        self.assertEqual(img.size, (200, 100))
        alpha = np.array(img)[:, :, 3]
        self.assertGreater((alpha == 255).sum(), 0)  # some real cells painted

    def test_getmap_with_full_bounds_paints_cells_with_varying_colors(self):
        res = self.client.get("/api/v1/ogc/wms", params={
            "service": "WMS", "request": "GetMap",
            "layers": "sst", "bbox": "65,0,80,20", "width": "120", "height": "80",
            "format": "image/png", "transparent": "false",
        })
        img = np.array(Image.open(io.BytesIO(res.content)).convert("RGB"))
        colors = {tuple(px) for row in img for px in row if tuple(px) != (200, 200, 200)}
        self.assertGreater(len(colors), 1)  # gradient -> more than one colour

    def test_getmap_over_empty_territory_is_honest_exception(self):
        res = self.client.get("/api/v1/ogc/wms", params={
            "service": "WMS", "request": "GetMap",
            "layers": "sst", "bbox": "120,50,140,60", "width": "50", "height": "50",
            "format": "image/png",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("ServiceException", res.text)
        self.assertIn("no real", res.text.lower())

    def test_getmap_unknown_layer_is_layer_not_defined(self):
        res = self.client.get("/api/v1/ogc/wms", params={
            "service": "WMS", "request": "GetMap",
            "layers": "not_a_layer", "bbox": "65,0,80,20", "width": "50", "height": "50",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("ServiceException", res.text)
        self.assertIn("LayerNotDefined", res.text)
        self.assertIn("application/xml", res.headers["content-type"])

    def test_getmap_invalid_bbox_is_honest(self):
        res = self.client.get("/api/v1/ogc/wms", params={
            "service": "WMS", "request": "GetMap",
            "layers": "sst", "bbox": "not-a-bbox", "width": "50", "height": "50",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("BBOX", res.text)


class OgcWcsTest(unittest.TestCase):
    def setUp(self):
        self.client = _client()
        _seed_grid()

    def tearDown(self):
        _clear_grid()

    def test_getcapabilities_lists_coverages(self):
        res = self.client.get("/api/v1/ogc/wcs",
                              params={"service": "WCS", "request": "GetCapabilities", "version": "2.0.1"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/xml", res.headers["content-type"])
        self.assertIn("<wcs:CoverageId>sst</wcs:CoverageId>", res.text)
        self.assertIn("<wcs:CoverageId>chlor_a</wcs:CoverageId>", res.text)
        self.assertIn("application/x-netcdf", res.text)

    def test_getcoverage_returns_cf_netcdf(self):
        res = self.client.get("/api/v1/ogc/wcs", params={
            "service": "WCS", "request": "GetCoverage", "version": "2.0.1",
            "CoverageID": "sst",
            "subset": ["Lat(0,20)", "Long(65,80)"],
            "format": "application/x-netcdf",
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("x-netcdf", res.headers["content-type"])
        self.assertTrue(res.content.startswith(b"CDF") or res.content.startswith(b"\x89HDF"))
        nc_path = Path(_TMP.name) / "coverage.nc"
        nc_path.write_bytes(res.content)
        ds = xr.open_dataset(nc_path)
        try:
            self.assertEqual(ds.attrs["Conventions"], "CF-1.8")
            self.assertEqual(ds["sst"].attrs["standard_name"], "sea_surface_temperature")
            self.assertEqual(ds["sst"].attrs["units"], "degC")
            vals = ds["sst"].values
            self.assertGreater(np.count_nonzero(~np.isnan(vals)), 0)
            self.assertLessEqual(np.nanmax(vals), 32.0)
            self.assertLessEqual(np.abs(np.diff(ds["lat"].values)).max(), 20.0)
        finally:
            ds.close()

    def test_getcoverage_over_empty_territory_is_honest(self):
        res = self.client.get("/api/v1/ogc/wcs", params={
            "service": "WCS", "request": "GetCoverage",
            "CoverageID": "sst",
            "subset": ["Lat(50,60)", "Long(120,140)"],
            "format": "application/x-netcdf",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("ServiceException", res.text)
        self.assertIn("no real", res.text.lower())

    def test_getcoverage_unknown_identifier(self):
        res = self.client.get("/api/v1/ogc/wcs", params={
            "service": "WCS", "request": "GetCoverage",
            "CoverageID": "bogus",
            "subset": ["Lat(0,20)", "Long(65,80)"],
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("NoSuchCoverage", res.text)
        self.assertIn("bogus", res.text)

    def test_getcoverage_rejects_unsupported_format(self):
        res = self.client.get("/api/v1/ogc/wcs", params={
            "service": "WCS", "request": "GetCoverage",
            "CoverageID": "sst",
            "subset": ["Lat(0,20)", "Long(65,80)"],
            "format": "application/geotiff",
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unsupported FORMAT", res.text)


if __name__ == "__main__":
    unittest.main()