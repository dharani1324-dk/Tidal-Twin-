"""Offline tests for scripts/fetch_argo (real Argo GDAC provisioning)."""
import gzip
import tempfile
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import scripts.fetch_argo as fa

BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)
INDEX_HEADER = "file\tinstitution\tdate_update\twmo\tlatitude\tlongitude\tdate_last\n"


def _index_text(rows: list[str]) -> str:
    return INDEX_HEADER + "".join(rows)


def _float(wmo, path, lat, lon, date_last, **extra):
    row = {"file": path, "wmo": wmo, "latitude": str(lat), "longitude": str(lon),
           "date_last": date_last, "date_update": "", **extra}
    return row


class DateParseTest(unittest.TestCase):
    def test_full_timestamp(self):
        self.assertEqual(fa._date_parse("20260214120000"),
                         datetime(2026, 2, 14, 12, tzinfo=timezone.utc))

    def test_iso_and_date_only(self):
        self.assertEqual(fa._date_parse("2026-02-14T12:00:00Z"),
                         datetime(2026, 2, 14, 12, tzinfo=timezone.utc))
        self.assertEqual(fa._date_parse("20260214"),
                         datetime(2026, 2, 14, tzinfo=timezone.utc))

    def test_garbage_returns_none(self):
        self.assertIsNone(fa._date_parse(""))
        self.assertIsNone(fa._date_parse("N/A"))


class LoadFloatIndexTest(unittest.TestCase):
    def test_parses_tab_separated_rows_and_skips_short_rows(self):
        text = _index_text([
            "dac/aoml/2902936/2902936_prof.nc\tAOML\t20250201\t2902936\t72.0\t20.0\t20250201T000000\n",
            "dac/coriolis/3901234/3901234_prof.nc\tCORIOLIS\t20250202\t3901234\t73.0\t21.0\t20250202T120000\n",
            "truncated-line\n",
        ])
        resp = Mock()
        resp.content = gzip.compress(text.encode())
        resp.raise_for_status = Mock()
        with patch.object(fa.requests, "get", return_value=resp) as m:
            floats = fa._load_float_index("https://gdac.local/argo")
        self.assertEqual(len(floats), 2)
        self.assertEqual(floats[0]["wmo"], "2902936")
        self.assertEqual(floats[0]["file"], "dac/aoml/2902936/2902936_prof.nc")
        self.assertEqual(floats[1]["latitude"], "73.0")
        url, kwargs = m.call_args
        self.assertEqual(url[0], "https://gdac.local/argo/ar_index_global_prof.txt.gz")


class InBoxTest(unittest.TestCase):
    def test_in_and_out(self):
        self.assertTrue(fa._in_box("20.0", "72.0", BOX))
        self.assertTrue(fa._in_box("0.0", "100.0", BOX))
        self.assertFalse(fa._in_box("30.0", "72.0", BOX))
        self.assertFalse(fa._in_box("5.0", "140.0", BOX))

    def test_bad_values_false(self):
        self.assertFalse(fa._in_box("abc", "72.0", BOX))
        self.assertFalse(fa._in_box("", "", BOX))
        self.assertFalse(fa._in_box(None, None, BOX))


class SelectFloatsTest(unittest.TestCase):
    def setUp(self):
        self.float_in = _float("2902936", "dac/aoml/2902936/2902936_prof.nc", 20.0, 72.0, "20260214120000")
        self.float_old = _float("3901234", "dac/coriolis/3901234/3901234_prof.nc", 21.0, 73.0, "20200101T000000")
        self.float_far = _float("7902073", "dac/meds/7902073/7902073_prof.nc", 40.0, 120.0, "20260215000000")

    def test_filters_by_box_and_since_and_sorts_newest_first(self):
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        picked = fa.select_floats([self.float_far, self.float_old, self.float_in],
                                  BOX, since, limit=10, only_wmos=None)
        self.assertEqual([f["wmo"] for f in picked], ["2902936"])

    def test_empty_when_nothing_matches(self):
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        picked = fa.select_floats([self.float_old], BOX, since, limit=10, only_wmos=None)
        self.assertEqual(picked, [])

    def test_explicit_wmos_bypass_box_and_since(self):
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        picked = fa.select_floats([self.float_old, self.float_far],
                                  BOX, since, limit=6, only_wmos=["3901234"])
        self.assertEqual([f["wmo"] for f in picked], ["3901234"])

    def test_skips_rows_without_wmo_or_gdac_path(self):
        bad = [
            {"file": "dac/aoml/1/1_prof.nc", "wmo": "", "latitude": "20.0", "longitude": "72.0",
             "date_last": "20260214120000"},
            {"file": "other/2/2_prof.nc", "wmo": "2", "latitude": "20.0", "longitude": "72.0",
             "date_last": "20260214120000"},
        ]
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(fa.select_floats(bad, BOX, since, limit=10, only_wmos=None), [])

    def test_undated_float_within_box_is_excluded(self):
        no_date = _float("999", "dac/aoml/999/999_prof.nc", 20.0, 72.0, "")
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        picked = fa.select_floats([no_date], BOX, since, limit=10, only_wmos=None)
        self.assertEqual(picked, [])


class FetchProfilesTest(unittest.TestCase):
    def _response(self, payload: bytes):
        resp = Mock()
        resp.content = payload
        resp.raise_for_status = Mock()
        return resp

    def test_downloads_new_and_skips_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            float_row = _float("2902936", "dac/aoml/2902936/2902936_prof.nc", 20.0, 72.0, "20260214120000")
            with patch.object(fa.requests, "get", return_value=self._response(b"ARGO")) as m:
                results = fa.fetch_profiles([float_row], "https://gdac.local/argo", out_dir)
            self.assertEqual(results, [{"file": "2902936_prof.nc", "float_id": "2902936",
                                        "bytes": 4, "gdac": "usgodae"}])
            saved = (out_dir / "2902936_prof.nc")
            self.assertEqual(saved.read_bytes(), b"ARGO")
            m.assert_called_once()
            url, _ = m.call_args
            self.assertEqual(url[0], "https://gdac.local/argo/dac/aoml/2902936/2902936_prof.nc")

            # Second pass: same file exists -> skipped, no new download.
            with patch.object(fa.requests, "get") as m2:
                results = fa.fetch_profiles([float_row], "https://gdac.local/argo", out_dir)
            self.assertEqual(results, [{"file": "2902936_prof.nc", "skipped": True}])
            m2.assert_not_called()

            # --force re-downloads.
            with patch.object(fa.requests, "get", return_value=self._response(b"ARGO2")) as m3:
                results = fa.fetch_profiles([float_row], "https://gdac.local/argo", out_dir, force=True)
            self.assertEqual(results[0]["bytes"], 5)
            self.assertEqual(saved.read_bytes(), b"ARGO2")

    def test_failed_download_is_recorded_but_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            float_row = _float("2902936", "dac/aoml/2902936/2902936_prof.nc", 20.0, 72.0, "20260214120000")
            def _boom(*a, **k):
                raise requests.RequestException("connection refused")
            with patch.object(fa.requests, "get", side_effect=_boom):
                results = fa.fetch_profiles([float_row], "https://gdac.local/argo", Path(tmp))
            self.assertEqual(results, [])
            self.assertFalse((Path(tmp) / "2902936_prof.nc").exists())


if __name__ == "__main__":
    unittest.main()