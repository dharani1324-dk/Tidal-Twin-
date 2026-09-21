"""Text/ASCII observation ingestion tests (feature #19).

Proves the honest rules of `scripts.ingest_ascii`:
  - rows near a monitored location are stored with full provenance
  - duplicates (same location + timestamp) are skipped
  - far-away rows are skipped (no invented locations)
  - malformed rows are skipped (no guessed values)
  - the whitespace/comment variation of the format also parses
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import SessionLocal
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.realdata import location_center
from scripts.ingest_ascii import ingest_file

_TMP = tempfile.TemporaryDirectory()
CHENNAI = (13.0, 80.3)
MARKER_SOURCE = "ASCII test import"
MARKER_TS = datetime(2026, 5, 1, 12, 0, 0)


def _utc_naive(dt):
    """sqlite reads back DateTime(timezone=True) as aware-LOCAL of the stored UTC wall-clock;
    strip the tz without shifting -> recovers the UTC wall time as stored."""
    return dt.replace(tzinfo=None)

CSV_TEXT = (
    "# buoy drop from ASCII test 'VirtualBuoy'\n"
    "latitude,longitude,time,sea_surface_temperature,salinity,wave_height,current_speed,depth_m\n"
    f"13.05,80.35,{MARKER_TS.isoformat()},29.1,34.5,1.2,0.4,0\n"
    f"13.05,80.35,{MARKER_TS.isoformat()},29.1,34.5,1.2,0.4,0\n"
    "35.0,130.0,2026-05-01T12:00:00Z,27.0,35.0,2.0,1.0,0\n"
    "abc,80.3,2026-05-01T12:00:00Z,28.0,34.0,1.0,0.1,0\n"
    f"13.06,80.36,,30.0,35.0,1.1,0.3,0\n"
)
WS_TEXT = (
    "# station\n"
    "latitude longitude time temperature salinity\n"
    f"13.07 80.37 {MARKER_TS.isoformat()} 29.6 34.8\n"
    f"13.07 80.37 {MARKER_TS.isoformat()} 29.6 34.8\n"
)


def tearDownModule():
    db = SessionLocal()
    try:
        db.query(OceanObservation).filter(OceanObservation.timestamp == MARKER_TS).delete()
        db.commit()
    finally:
        db.close()
    _TMP.cleanup()


def _clear_marker():
    db = SessionLocal()
    try:
        db.query(OceanObservation).filter(OceanObservation.timestamp == MARKER_TS).delete()
        db.commit()
    finally:
        db.close()


class AsciiIngestionTest(unittest.TestCase):
    def setUp(self):
        _clear_marker()
        db = SessionLocal()
        try:
            self.chennai = None
            near = db.query(OceanLocation).all()
            for loc in near:
                c = location_center(loc)
                if c and abs(c[0] - CHENNAI[0]) < 0.5 and abs(c[1] - CHENNAI[1]) < 0.5:
                    self.chennai = loc
                    break
            else:
                self.chennai = near[0]
        finally:
            db.close()

    def _count(self):
        db = SessionLocal()
        try:
            return db.query(OceanObservation).filter(
                OceanObservation.source == MARKER_SOURCE).count()
        finally:
            db.close()

    def test_csv_round_trip_dedupe_and_honest_skips(self):
        csv_path = Path(_TMP.name) / "buoy.csv"
        csv_path.write_text(CSV_TEXT, encoding="utf-8")
        summary = ingest_file(csv_path, source=MARKER_SOURCE, max_radius_km=100.0)
        self.assertEqual(summary["parsed"], 5)
        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["duplicates"], 1)
        self.assertEqual(summary["skipped_far"], 1)
        self.assertEqual(summary["skipped_bad"], 2)
        self.assertEqual(summary["source"], MARKER_SOURCE)

        db = SessionLocal()
        try:
            rows = db.query(OceanObservation).filter(
                OceanObservation.source == MARKER_SOURCE).all()
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row.location_id, self.chennai.id)
            self.assertEqual(_utc_naive(row.timestamp), MARKER_TS)
            self.assertEqual(row.sea_surface_temperature, 29.1)
            self.assertEqual(row.salinity, 34.5)
            self.assertEqual(row.wave_height, 1.2)
            self.assertEqual(row.current_speed, 0.4)
            self.assertEqual(row.data_type, "observation")
        finally:
            db.close()

    def test_rerun_is_all_duplicates(self):
        csv_path = Path(_TMP.name) / "buoy.csv"
        csv_path.write_text(CSV_TEXT, encoding="utf-8")
        ingest_file(csv_path, source=MARKER_SOURCE, max_radius_km=100.0)
        summary = ingest_file(csv_path, source=MARKER_SOURCE, max_radius_km=100.0)
        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["duplicates"], 2)  # both CSV rows already exist
        self.assertEqual(self._count(), 1)

    def test_whitespace_and_comment_format(self):
        ws_path = Path(_TMP.name) / "station.txt"
        ws_path.write_text(WS_TEXT, encoding="utf-8")
        summary = ingest_file(ws_path, source=MARKER_SOURCE, max_radius_km=100.0)
        self.assertEqual(summary["parsed"], 2)
        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["duplicates"], 1)
        db = SessionLocal()
        try:
            row = db.query(OceanObservation).filter(
                OceanObservation.source == MARKER_SOURCE).one()
            self.assertEqual(_utc_naive(row.timestamp), MARKER_TS)
            self.assertEqual(row.sea_surface_temperature, 29.6)
            self.assertEqual(row.salinity, 34.8)
        finally:
            db.close()

    def test_tight_radius_skips_even_near_rows(self):
        csv_path = Path(_TMP.name) / "tight.csv"
        csv_path.write_text(CSV_TEXT, encoding="utf-8")
        summary = ingest_file(csv_path, source=MARKER_SOURCE, max_radius_km=5.0)
        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["skipped_far"], 3)  # 2 near rows (7.8 km) + 1 far row
        self.assertEqual(self._count(), 0)


if __name__ == "__main__":
    unittest.main()