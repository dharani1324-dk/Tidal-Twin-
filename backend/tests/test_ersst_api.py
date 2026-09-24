"""Real NOAA ERSST v5 grid API tests.

Asserts on the 33,264 real readings ingested in features #1/#2: the latest
month's full grid and nearest-cell lookup. Values are the real ERSST archive
(Nov...Dec 2021 month boundary), never simulated.
"""

import unittest


class ErsstApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_latest_returns_real_month_grid(self):
        res = self.client.get("/api/v1/ersst/latest")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["available"])
        self.assertEqual(len(body["months"]), 12)
        self.assertEqual(body["time"], body["months"][-1])
        self.assertGreater(body["rows"], 1000)
        self.assertIn("NOAA ERSST", body["source"])
        for s in body["samples"][:50]:
            self.assertTrue(-90 <= s["latitude"] <= 90)
            self.assertTrue(-180 <= s["longitude"] <= 180)
            self.assertIsNotNone(s["sst"])
            self.assertTrue(-5 <= s["sst"] <= 40)
        # Dynamic colour-scale range: data-driven min/max over the real cells.
        stats = body["stats"]
        self.assertEqual(stats["count"], body["rows"])
        self.assertIsNotNone(stats["min"])
        self.assertIsNotNone(stats["max"])
        self.assertLessEqual(stats["min"], stats["max"])
        sample_vals = [s["sst"] for s in body["samples"]]
        self.assertAlmostEqual(stats["min"], min(sample_vals), places=4)
        self.assertAlmostEqual(stats["max"], max(sample_vals), places=4)

    def test_near_finds_an_ocean_cell(self):
        # Near the real Argo float 2902936 in the Arabian Sea.
        res = self.client.get("/api/v1/ersst/near", params={"latitude": 13.84, "longitude": 63.46})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["found"])
        self.assertIsNotNone(body["sst"])
        self.assertTrue(-5 <= body["sst"] <= 40)
        self.assertLessEqual(body["distance_deg"], 3.5)

    def test_near_reports_no_cell_honestly(self):
        # A 2-degree grid cannot have a cell within 0.1 degrees of an arbitrary point.
        res = self.client.get("/api/v1/ersst/near", params={"latitude": 13.84, "longitude": 63.46, "max_dist_deg": 0.1})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["found"])
        self.assertIn("no real ersst cell", body["reason"].lower())


if __name__ == "__main__":
    unittest.main()