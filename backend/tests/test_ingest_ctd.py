"""CTD cast ingestion tests (feature #17).

Proves the honest rules of `scripts.ingest_ctd`:
  - a station cast with a header-declared position + real T/S at depth is stored
  - identical rows (same station+depth+time) are deduplicated
  - rerunning the same file inserts nothing (all duplicates)
  - rows with an unparseable depth or no T/S are skipped
  - a file with no station position is skipped entirely (no invented locations)
"""

import tempfile
import unittest
from pathlib import Path

from app.core.database import SessionLocal
from app.models.ctd import CtdProfile
from scripts.ingest_ctd import ingest_file

_TMP = tempfile.TemporaryDirectory()
MARKER_STATION = "TST-STN7"
MARKER_SOURCE = "CTD test import"
MARKER_TS = "2026-05-02T08:00:00Z"


def tearDownModule():
    db = SessionLocal()
    try:
        db.query(CtdProfile).filter(CtdProfile.station_id == MARKER_STATION).delete()
        db.commit()
    finally:
        db.close()
    _TMP.cleanup()


def _clear_marker():
    db = SessionLocal()
    try:
        db.query(CtdProfile).filter(CtdProfile.station_id == MARKER_STATION).delete()
        db.commit()
    finally:
        db.close()


CSV_TEXT = (
    "# station: TST-STN7\n"
    "# latitude: 13.05\n"
    "# longitude: 80.35\n"
    "# instrument: SHIP-CTD\n"
    "station,depth_m,temperature,salinity,dissolved_oxygen,time\n"
    f"{MARKER_STATION},0,29.2,34.1,0.21,{MARKER_TS}\n"
    f"{MARKER_STATION},0,29.2,34.1,0.21,{MARKER_TS}\n"
    f"{MARKER_STATION},50,24.1,35.0,0.18,{MARKER_TS}\n"
    f"{MARKER_STATION},abc,20.0,35.2,0.15,{MARKER_TS}\n"
    f"{MARKER_STATION},100,,35.3,,{MARKER_TS}\n"
)

NO_POS_TEXT = (
    "# station: TST-NOPOS\n"
    "depth_m,temperature,salinity\n"
    "0,29.2,34.1\n"
    "50,24.1,35.0\n"
)


class CtdIngestionTest(unittest.TestCase):
    def setUp(self):
        _clear_marker()

    def _count(self):
        db = SessionLocal()
        try:
            return db.query(CtdProfile).filter(CtdProfile.station_id == MARKER_STATION).count()
        finally:
            db.close()

    def test_round_trip_dedupe_and_honest_skips(self):
        path = Path(_TMP.name) / "ctd_cast.csv"
        path.write_text(CSV_TEXT, encoding="utf-8")
        summary = ingest_file(path, source=MARKER_SOURCE)
        self.assertEqual(summary["parsed"], 5)
        self.assertEqual(summary["inserted"], 3)     # 0m, 50m, 100m (100m has salinity)
        self.assertEqual(summary["skipped_bad"], 1)  # row 4 (depth "abc")
        self.assertEqual(summary["skipped_pos"], 0)

        db = SessionLocal()
        try:
            rows = db.query(CtdProfile).filter(CtdProfile.station_id == MARKER_STATION).order_by(CtdProfile.depth_m).all()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0].depth_m, 0)
            self.assertEqual(rows[0].temperature, 29.2)
            self.assertEqual(rows[0].salinity, 34.1)
            self.assertEqual(rows[0].dissolved_oxygen, 0.21)
            self.assertEqual(rows[0].latitude, 13.05)
            self.assertEqual(rows[0].longitude, 80.35)
            self.assertEqual(rows[0].instrument, "SHIP-CTD")
            self.assertEqual(rows[1].depth_m, 50)
            self.assertEqual(rows[1].temperature, 24.1)
            self.assertEqual(rows[2].depth_m, 100)
            self.assertEqual(rows[2].temperature, None)
            self.assertEqual(rows[2].salinity, 35.3)
        finally:
            db.close()

    def test_rerun_is_all_duplicates_and_bad(self):
        path = Path(_TMP.name) / "ctd_cast.csv"
        path.write_text(CSV_TEXT, encoding="utf-8")
        ingest_file(path, source=MARKER_SOURCE)
        summary = ingest_file(path, source=MARKER_SOURCE)
        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["skipped_bad"], 1)
        self.assertEqual(self._count(), 3)

    def test_no_position_file_is_skipped(self):
        path = Path(_TMP.name) / "no_pos.csv"
        path.write_text(NO_POS_TEXT, encoding="utf-8")
        summary = ingest_file(path, source=MARKER_SOURCE)
        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["skipped_pos"], 2)


if __name__ == "__main__":
    unittest.main()