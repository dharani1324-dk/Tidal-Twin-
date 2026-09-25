import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.modules.ai.provenance_quality import assess_record, origin_status


class ProvenanceQualityTests(unittest.TestCase):
    def test_open_meteo_forecasts_are_never_real_observations(self):
        self.assertEqual(origin_status("Open-Meteo Marine forecast", "model_forecast"), "MODEL_DERIVED")
        self.assertEqual(origin_status("NOAA ERSST v5", "historical_grid"), "HISTORICAL")
        self.assertEqual(origin_status("Argo float", "observation"), "REAL")
        self.assertEqual(origin_status("unverified source", "observation"), "UNKNOWN")
        self.assertEqual(origin_status("SIMULATED_HEATWAVE", "simulation"), "SIMULATED")

    def test_assessment_reports_source_class_and_forecast_freshness(self):
        row = SimpleNamespace(
            source="Open-Meteo Marine forecast", data_type="model_forecast",
            timestamp=datetime.now(timezone.utc) + timedelta(hours=3),
            sea_surface_temperature=28.0, wave_height=1.2, wave_direction=180.0,
            dissolved_oxygen=7.0, chlorophyll=1.2, nutrients=2.0,
            salinity=None, current_speed=None, current_direction=None,
            ph=None, pressure=None, density=None, depth_m=0.0,
        )
        result = assess_record(row, now=datetime.now(timezone.utc))
        self.assertEqual(result["status"], "MODEL_DERIVED")
        self.assertEqual(result["freshness"]["status"], "FORECAST")
        self.assertEqual(result["qc_status"], "NOT_PROVIDED_BY_SOURCE")
        self.assertIsNone(result["variables"].get("salinity"))
        self.assertIsNone(result["variables"].get("chlorophyll"))


if __name__ == "__main__":
    unittest.main()
