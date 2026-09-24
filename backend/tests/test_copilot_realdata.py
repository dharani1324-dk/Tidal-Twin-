"""Copilot / multimodal / anomaly detector REAL-grid integration tests.

Proves the "Copilot on real data" feature: the copilot answer, the claim
verifier and the anomaly detector now CITE the real NOAA grids ingested into
`netcdf_readings` (ERSST v5 SST + VIIRS·Himawari Chl) instead of only demo
observations — always honestly (no cell within range / nothing ingested ->
'no data', never a fabricated value).

The real ERSST data is already live in the DB (feature #1), so every SST lookup
here hits provenance "NOAA ERSST v5". For determinism we ALSO seed a synthetic
`sst` + `chlor_a` cell exactly at a monitored coast's centroid with a
future-dated month (2099-01) so the nearest-cell search is unambiguous, then we
delete those marker rows in teardown. The synthetic cell is plumbing only — it
never reaches the answer text as anything other than a cited cell.

Note: as of this feature the DB holds no real chlor_a rows (fetch_chlor +
ingest still pending on a networked machine), so the "nothing yet" honesty path
is exercised for chlor_a exactly like the /api/v1/chlor endpoints do.
"""

import unittest
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models.location import OceanLocation
from app.models.netcdf import NetcdfReadings as N
from app.models.observation import OceanObservation
from geoalchemy2.shape import to_shape

_MARKER = "synthetic-copilot-realdata"
_FAKE_MONTH = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _first_location_with_obs(db):
    return (
        db.query(OceanLocation)
        .filter(OceanLocation.id.in_(db.query(OceanObservation.location_id).distinct()))
        .order_by(OceanLocation.id.asc())
        .first()
    )


def _seed_grid(db):
    loc = _first_location_with_obs(db)
    lon, lat = to_shape(loc.geom).centroid.x, to_shape(loc.geom).centroid.y
    db.add_all([
        N(latitude=lat, longitude=lon, time=_FAKE_MONTH, variable_name="sst",
          value=28.4, standard_name="sea_surface_temperature", units="degC",
          source_file=_MARKER),
        N(latitude=lat, longitude=lon, time=_FAKE_MONTH, variable_name="chlor_a",
          value=0.85, standard_name="mass_concentration_of_chlorophyll_a_in_sea_water",
          units="mg m-3", source_file=_MARKER),
    ])
    db.commit()
    return loc


def _clear_markers(db):
    db.query(N).filter(N.source_file == _MARKER).delete()
    db.commit()


def tearDownModule():
    db = SessionLocal()
    try:
        _clear_markers(db)
    finally:
        db.close()


class AnomalyCrosscheckTest(unittest.TestCase):
    """The anomaly detector appends a real ERSST cross-check to its
    temperature-alert description when a real cell exists near the coast."""

    def setUp(self):
        self.db = SessionLocal()
        self.loc = _seed_grid(self.db)

    def tearDown(self):
        try:
            _clear_markers(self.db)
        finally:
            self.db.close()

    def test_crosscheck_cites_real_ersst_cell(self):
        from app.modules.ai.anomaly.detector import _real_grid_crosscheck

        sentence = _real_grid_crosscheck(self.db, self.loc)
        self.assertIsNotNone(sentence)
        self.assertIn("Cross-check vs real NOAA ERSST v5 grid (2099-01)", sentence)
        self.assertIn("28.4", sentence)

    def test_crosscheck_honest_when_base_data_cleared(self):
        from app.modules.ai.anomaly.detector import _real_grid_crosscheck

        _clear_markers(self.db)
        # real ERSST data is live, but no synthetic cell at the centroid now:
        # the sentence must still mention the product and never invent a value.
        sentence = _real_grid_crosscheck(self.db, self.loc) or ""
        self.assertTrue(sentence.startswith("Cross-check vs real NOAA ERSST v5 grid")
                        or "No real ERSST cell within" in sentence)


class CopilotRealDataTest(unittest.TestCase):
    """The current-conditions copilot answer cites the real grids."""

    def setUp(self):
        self.db = SessionLocal()
        self.loc = _seed_grid(self.db)

    def tearDown(self):
        try:
            _clear_markers(self.db)
        finally:
            self.db.close()

    def test_current_answer_cites_real_sst_and_chl(self):
        from app.modules.ai.nlp.copilot import ans_current

        out = ans_current(self.db, self.loc, ["temperature"])
        answer = out["answer"]
        self.assertIn("Real SST (2099-01): 28.4 °C", answer)
        self.assertIn("Real Chl-a (2099-01): 0.85 mg/m³", answer)
        self.assertIn("real NOAA ERSST v5 grid", answer)
        self.assertIn("real NOAA VIIRS", answer)
        self.assertIn("Cross-checked real NOAA grid(s)", out["steps"])
        self.assertTrue(any(s.startswith("NOAA ERSST v5") for s in out["sources"]))
        self.assertTrue(any(s.startswith("NOAA CoastWatch") for s in out["sources"]))

    def test_current_answer_handles_no_cell_honestly_without_sources(self):
        """Regression: a coast with no real grid cell within range must report
        it honestly and NOT crash on a missing provenance key."""
        from unittest.mock import patch

        import app.modules.ai.nlp.copilot as copilot

        def _mock_near(db, variable, lat, lon, max_dist_deg=None):
            if variable == "sst":
                return {"found": False, "month": "2099-01",
                        "reason": "No real ERSST cell within 3.5° of this location."}
            return {
                "found": True, "month": "2099-01", "latitude": 18.5, "longitude": 73.0,
                "value": 0.85, "distance_deg": 0.0, "units": "mg/m³",
                "source": "NOAA CoastWatch VIIRS-Himawari blended ocean-colour (5 km, monthly mean)",
                "short": "real NOAA VIIRS·Himawari satellite",
            }

        with patch.object(copilot, "near", new=_mock_near):
            out = copilot.ans_current(self.db, self.loc, ["temperature"])
        self.assertIn("No real ERSST cell within 3.5°", out["answer"])
        # The absent grid is NOT cited among sources; the found one is.
        self.assertTrue(any(s.startswith("NOAA CoastWatch") for s in out["sources"]))
        self.assertFalse(any(s.startswith("NOAA ERSST") for s in out["sources"]))


class HonestAbsenceTest(unittest.TestCase):
    """Nothing ingested for chlor_a -> the claim verifier says "no data" and
    the copilot shows no real Chl block (never a guess)."""

    def setUp(self):
        self.db = SessionLocal()
        _clear_markers(self.db)
        # No real chlor_a has ever been ingested in this DB (fetch_chlor still
        # pending on a networked machine), so 'no data' is the true state.
        self.db.query(N).filter(N.variable_name == "chlor_a").delete()
        self.db.commit()
        self.loc = _first_location_with_obs(self.db)

    def tearDown(self):
        try:
            _clear_markers(self.db)
        finally:
            self.db.close()

    def test_claim_verifier_reports_no_chlor_data_honestly(self):
        from app.modules.ai.nlp.multimodal import _compare_claim

        claim = {"variable": "chlorophyll", "value": 1.2, "unit": "mg/m³", "sentence": "the chlorophyll reached 5.0"}
        row = _compare_claim(self.db, claim, {}, self.loc)
        self.assertIsNotNone(row["real"])
        self.assertIn("No satellite Chl readings ingested yet", row["real"])

    def test_copilot_silent_about_absent_chlor_but_cites_real_sst(self):
        from app.modules.ai.nlp.copilot import ans_current

        out = ans_current(self.db, self.loc, ["temperature", "salinity"])
        self.assertIn("Real SST", out["answer"])     # real ERSST data is live
        self.assertNotIn("Real Chl-a", out["answer"])  # absent grid -> silent

    def test_multimodal_never_claims_satellite_data_without_rows(self):
        from app.modules.ai.nlp.multimodal import multimodal_fuse

        out = multimodal_fuse(self.db, f"At {self.loc.name} the chlorophyll reached 5.0")
        real_notes = [r.get("real") for r in out["data"]["rows"]]
        self.assertTrue(all(n is None or "ingested yet" in n for n in real_notes))
        self.assertNotIn("NOAA CoastWatch", " ".join(out["sources"]))


class MultimodalRealDataTest(unittest.TestCase):
    """The claim verifier cites the nearest real grid cell for a named coast."""

    def setUp(self):
        self.db = SessionLocal()
        self.loc = _seed_grid(self.db)

    def tearDown(self):
        try:
            _clear_markers(self.db)
        finally:
            self.db.close()

    def test_temperature_claim_gets_real_ersst_citation(self):
        from app.modules.ai.nlp.multimodal import _compare_claim

        claim = {"variable": "temperature", "value": 29.0, "unit": "°C", "sentence": "the SST reached 29"}
        row = _compare_claim(self.db, claim, {"sea_surface_temperature": 28.0}, self.loc)
        self.assertIn("real NOAA ERSST v5", row["real"])
        self.assertIn("28.4", row["real"])

    def test_chlorophyll_claim_gets_real_satellite_citation(self):
        from app.modules.ai.nlp.multimodal import _compare_claim

        claim = {"variable": "chlorophyll", "value": 0.9, "unit": "mg/m³", "sentence": "chl 0.9"}
        row = _compare_claim(self.db, claim, {"chlorophyll": 0.9}, self.loc)
        self.assertIn("real NOAA VIIRS", row["real"])
        self.assertIn("0.85", row["real"])

    def test_fuse_end_to_end_cites_real_grid(self):
        from app.modules.ai.nlp.multimodal import multimodal_fuse

        out = multimodal_fuse(
            self.db,
            f"At {self.loc.name} the SST reached 30 and chl 0.9",
            media={"type": "field", "instrument": "boat", "sensor": "manual"},
        )
        temp_rows = [r for r in out["data"]["rows"] if r["variable"] == "temperature"]
        self.assertTrue(temp_rows)
        self.assertIn("real NOAA ERSST v5", temp_rows[0]["real"])
        self.assertIn("real NOAA grids", " ".join(out["sources"]))


if __name__ == "__main__":
    unittest.main()