"""NetCDF ingestion pipeline tests (features #1 + #2).

Uses tiny SYNTHETIC NetCDF fixtures (clearly not real ocean data) to prove the
mechanics of `scripts.ingest_netcdf`:

- CF metadata path (`cf-xarray`): coordinates with unusual names like
  `nav_lat` / `time_counter` (typical of CMEMS / NEMO ocean model output),
  recognised via `standard_name` / `units` attributes.
- name-lookup fallback path: plain `lat`/`lon`/`time` coordinate names with no
  CF metadata.
- grid unpacking, NaN skipping, boundary-variable skipping, idempotent
  re-runs, `--reingest` cleanup, and CF `standard_name` / `units` capture.
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
CF_FIXTURE = Path(_TMP.name) / "nemo_style_cf_fixture.nc"
PLAIN_FIXTURE = Path(_TMP.name) / "plain_names_fixture.nc"


def setUpModule():
    _build_fixtures()


def tearDownModule():
    db = SessionLocal()
    try:
        for p in (CF_FIXTURE, PLAIN_FIXTURE):
            db.query(N).filter(N.source_file == str(p)).delete()
        db.commit()
    finally:
        db.close()
    _TMP.cleanup()


def _build_fixtures():
    # --- CF / NEMO-style fixture -----------------------------------------
    # Unusual coordinate names, but fully self-describing via CF metadata.
    vals = np.arange(1, 17, dtype="float32").reshape((2, 2, 2, 2))
    vals[0, 0, 0, 1] = np.nan
    vals[0, 1, 1, 1] = np.nan
    vals[1, 1, 0, 0] = np.nan
    ds = xr.Dataset(
        {
            "thetao": (
                ("time_counter", "deptht", "nav_lat", "nav_lon"),
                vals,
                {"standard_name": "sea_water_potential_temperature", "units": "degC"},
            ),
            "time_instant_bnds": (("time_counter", "nb"), np.zeros((2, 2))),
        },
        coords={
            "nav_lat": (("nav_lat",), [10.0, 12.0], {"units": "degrees_north", "standard_name": "latitude"}),
            "nav_lon": (("nav_lon",), [80.0, 82.0], {"units": "degrees_east", "standard_name": "longitude"}),
            "time_counter": (
                ("time_counter",),
                [0.0, 86400.0],
                {"units": "seconds since 2020-01-01"},
            ),
            "deptht": (("deptht",), [5.0, 15.0], {"units": "m", "positive": "down"}),
            "nb": [0, 1],
        },
    )
    ds.to_netcdf(CF_FIXTURE)

    # --- Plain-name fixture (no CF metadata) ------------------------------
    # `y`/`x`/`date` are unrecognisable to cf-xarray but match our alias
    # fallback, proving the name-lookup path still works on any file.
    plain = xr.Dataset(
        {"temp": (("date", "y", "x"), np.ones((1, 2, 2)))},
        coords={
            "y": [10.0, 12.0],
            "x": [80.0, 82.0],
            "date": np.array(["2021-01-01"], dtype="datetime64[D]"),
        },
    )
    plain.to_netcdf(PLAIN_FIXTURE)


def _count(source: str) -> int:
    db = SessionLocal()
    try:
        return db.query(N).filter(N.source_file == source).count()
    finally:
        db.close()


class NetcdfCfIngestTest(unittest.TestCase):
    """CF-metadata path: NEMO-style coordinates recognised by cf-xarray."""

    def setUp(self):
        ingest_file(CF_FIXTURE, verbose=False, reingest=True)

    def test_uses_cf_metadata_path(self):
        summary = ingest_file(CF_FIXTURE, verbose=False)
        self.assertEqual(summary["axis_method"], "CF metadata")

    def test_count_and_idempotent_rerun(self):
        self.assertEqual(_count(str(CF_FIXTURE)), 13)  # 16 cells - 3 NaN
        second = ingest_file(CF_FIXTURE, verbose=False)
        self.assertEqual(second["rows_inserted"], 0)
        self.assertEqual(_count(str(CF_FIXTURE)), 13)

    def test_reingest_resets_to_same_count(self):
        summary = ingest_file(CF_FIXTURE, verbose=False, reingest=True)
        self.assertEqual(summary["rows_inserted"], 13)
        self.assertEqual(_count(str(CF_FIXTURE)), 13)

    def test_skips_nan_and_boundary_variables(self):
        db = SessionLocal()
        try:
            variables = {
                v
                for (v,) in (
                    db.query(N.variable_name)
                    .filter(N.source_file == str(CF_FIXTURE))
                    .distinct()
                    .all()
                )
            }
            self.assertEqual(variables, {"thetao"})
            self.assertEqual(
                db.query(N).filter(N.source_file == str(CF_FIXTURE), N.value.is_(None)).count(), 0
            )
        finally:
            db.close()

    def test_cf_metadata_captured(self):
        db = SessionLocal()
        try:
            row = db.query(N).filter(N.source_file == str(CF_FIXTURE)).first()
            self.assertEqual(row.standard_name, "sea_water_potential_temperature")
            self.assertEqual(row.units, "degC")
            depths = {
                d
                for (d,) in (
                    db.query(N.depth_m)
                    .filter(N.source_file == str(CF_FIXTURE))
                    .distinct()
                    .all()
                )
            }
            self.assertEqual(depths, {5.0, 15.0})
        finally:
            db.close()


class NetcdfNameFallbackTest(unittest.TestCase):
    """Name-lookup fallback path: plain lat/lon/time, no CF metadata."""

    def setUp(self):
        ingest_file(PLAIN_FIXTURE, verbose=False, reingest=True)

    def test_uses_name_lookup_when_no_cf_metadata(self):
        summary = ingest_file(PLAIN_FIXTURE, verbose=False)
        self.assertEqual(summary["axis_method"], "name lookup")
        self.assertEqual(_count(str(PLAIN_FIXTURE)), 4)  # every cell finite


if __name__ == "__main__":
    unittest.main()