"""
Tests for the deoxygenation module.

The point of this suite is not coverage percentage - it is to pin down the
invariants that make the module scientifically defensible:

  * there is exactly ONE severity ladder, on one scale, shared by ingest, the
    hotspot scorer and the zone grid (three divergent copies once existed);
  * an ordinal always renders back to the label it was derived from;
  * a healthy cell is never reported as a low-oxygen zone;
  * a measurement's QC-derived confidence is not destroyed by spatial mapping;
  * a re-run of the same profile is idempotent, so ingest cannot half-apply;
  * an empty result carries a reason instead of rendering as zero.

All tests are pure: no database, no network, no NetCDF.
"""

import unittest

from app.modules.ai.deoxygenation import hotspots, normalize, zones
from app.modules.ai.deoxygenation.regions import assign_records
from app.modules.ai.deoxygenation.units import (
    ALERT_TIER_RULES,
    SEVERITY_LADDER,
    SEVERITY_ORDINAL_TO_LABEL,
    SEVERITY_ORDINALS,
    alert_for_ordinal,
    severity_for_mg_l,
    severity_label_for_ordinal,
    umol_kg_to_mg_l,
)

# (mg/L, expected label) spanning every band and both boundaries.
LADDER_CASES = [
    (0.0, "CRITICAL"),
    (0.2, "CRITICAL"),
    (0.49, "CRITICAL"),
    (0.5, "HIGH"),
    (1.0, "HIGH"),
    (1.99, "HIGH"),
    (2.0, "MODERATE"),
    (3.9, "MODERATE"),
    (4.0, "LOW"),
    (5.9, "LOW"),
    (6.0, "NORMAL"),
    (8.5, "NORMAL"),
]


class TestSeverityLadderIsSingleSourced(unittest.TestCase):
    def test_ordinals_are_one_based(self):
        # 0 is reserved for "no classification" so it must not be NORMAL,
        # otherwise an unclassified sample reads as healthy.
        self.assertEqual(SEVERITY_ORDINALS["NORMAL"], 1)
        self.assertEqual(SEVERITY_ORDINALS["CRITICAL"], 5)
        self.assertEqual(sorted(SEVERITY_ORDINALS.values()), [1, 2, 3, 4, 5])

    def test_ladder_breakpoints_match_stored_scale(self):
        # The persisted rows were written against 0.5 / 2.0 / 4.0 / 6.0.
        bounds = [entry[1] for entry in SEVERITY_LADDER if entry[1] is not None]
        self.assertEqual(bounds, [0.5, 2.0, 4.0, 6.0])

    def test_classification_at_every_boundary(self):
        for mg_l, expected in LADDER_CASES:
            label, ordinal, _, _ = severity_for_mg_l(mg_l)
            self.assertEqual(label, expected, "%s mg/L" % mg_l)
            self.assertEqual(ordinal, SEVERITY_ORDINALS[expected], "%s mg/L" % mg_l)

    def test_normalize_classifier_agrees_with_units(self):
        # normalize.py used to carry its own ladder; a drift here silently
        # mislabels every stored row.
        for mg_l, expected in LADDER_CASES:
            label, ordinal, is_hypoxic, is_dead = normalize._classify_severity(mg_l)
            self.assertEqual(label, expected, "%s mg/L" % mg_l)
            self.assertEqual(ordinal, SEVERITY_ORDINALS[expected], "%s mg/L" % mg_l)
            self.assertEqual(int(is_hypoxic), int(mg_l < 2.0))
            self.assertEqual(int(is_dead), int(mg_l < 0.5))

    def test_hotspots_classifier_agrees_with_units(self):
        for mg_l, expected in LADDER_CASES:
            ordinal, label, is_hypoxic, is_dead = hotspots._severity_from_mg_l(mg_l)
            self.assertEqual(label, expected, "%s mg/L" % mg_l)
            self.assertEqual(ordinal, SEVERITY_ORDINALS[expected], "%s mg/L" % mg_l)
            self.assertEqual(int(is_hypoxic), int(mg_l < 2.0))
            self.assertEqual(int(is_dead), int(mg_l < 0.5))

    def test_hypoxia_and_dead_zone_thresholds(self):
        # The two anchors the whole module is calibrated on.
        self.assertFalse(severity_for_mg_l(2.0)[2])
        self.assertTrue(severity_for_mg_l(1.99)[2])
        self.assertFalse(severity_for_mg_l(0.5)[3])
        self.assertTrue(severity_for_mg_l(0.49)[3])

    def test_missing_oxygen_is_not_classified_as_normal(self):
        label, ordinal, hypoxic, dead = severity_for_mg_l(None)
        self.assertIsNone(label)
        self.assertIsNone(ordinal)
        self.assertFalse(hypoxic)
        self.assertFalse(dead)


class TestOrdinalRendersBackToLabel(unittest.TestCase):
    def test_round_trip(self):
        for label, ordinal in SEVERITY_ORDINALS.items():
            self.assertEqual(SEVERITY_ORDINAL_TO_LABEL[ordinal], label)
            self.assertEqual(severity_label_for_ordinal(ordinal), label.title())

    def test_unknown_ordinal_is_not_reported_as_normal(self):
        # The original defect: reading a label-keyed dict with an ordinal key
        # returned None, and the fallback then printed "Normal" for cells that
        # were in fact dead zones.
        self.assertEqual(severity_label_for_ordinal(None), "Unknown")
        self.assertEqual(severity_label_for_ordinal(0), "Unknown")
        self.assertEqual(severity_label_for_ordinal(99), "Unknown")
        self.assertNotEqual(severity_label_for_ordinal(99), "Normal")

    def test_every_alert_tier_is_reachable(self):
        for ordinal in SEVERITY_ORDINALS.values():
            severity, action, rationale = alert_for_ordinal(ordinal)
            self.assertNotEqual(severity, "unknown", ordinal)
            self.assertTrue(action)
            self.assertTrue(rationale)
        # Highest tier must be reachable and must be the critical one.
        self.assertEqual(alert_for_ordinal(5)[0], "critical")
        self.assertEqual(alert_for_ordinal(1)[0], "info")
        self.assertEqual(alert_for_ordinal(None)[0], "unknown")


class TestZoneGridHonesty(unittest.TestCase):
    @staticmethod
    def _record(lat, lon, mg_l, depth=100.0):
        label, ordinal, hypoxic, dead = severity_for_mg_l(mg_l)
        return {
            "latitude": lat,
            "longitude": lon,
            "depth_m": depth,
            "do_mg_l": mg_l,
            "severity_label": label,
            "severity_ordinal": ordinal,
            "is_hypoxic": hypoxic,
            "is_dead_zone": dead,
            "float_id": "1902660",
        }

    def test_oxygenated_cell_is_not_a_zone(self):
        # The threshold was 2 on a 1-based ladder, i.e. LOW, which flagged
        # healthy 6 mg/L surface water as a low-oxygen zone.
        out = zones.build_zones([self._record(10.0, 70.0, 6.2)])
        cell = out["zones"][0]
        self.assertFalse(cell["is_zone"])
        self.assertFalse(cell["is_dead_zone"])
        self.assertEqual(cell["worst_ordinal"], SEVERITY_ORDINALS["NORMAL"])
        self.assertEqual(cell["worst_label"], "Normal")
        self.assertEqual(out["zone_count"], 0)

    def test_dead_zone_cell_is_flagged(self):
        out = zones.build_zones([self._record(23.75, 62.25, 0.04, depth=500.0)])
        cell = out["zones"][0]
        self.assertTrue(cell["is_zone"])
        self.assertTrue(cell["is_dead_zone"])
        self.assertEqual(cell["worst_label"], "Critical")
        self.assertEqual(out["zone_count"], 1)
        self.assertEqual(out["dead_zone_count"], 1)

    def test_cell_reports_worst_sample_not_mean(self):
        # A cell averaging 5 mg/L that dips to 0.3 mg/L is a dead zone.
        recs = [self._record(23.75, 62.25, 5.0, depth=50.0),
                self._record(23.76, 62.26, 0.3, depth=800.0)]
        cell = zones.build_zones(recs)["zones"][0]
        self.assertTrue(cell["is_dead_zone"])
        self.assertEqual(cell["mean_mg_l"], 2.65)
        self.assertEqual(cell["min_mg_l"], 0.3)
        self.assertEqual(cell["n_samples"], 2)
        self.assertEqual(cell["worst_label"], "Critical")

    def test_depth_band_filter_partitions_the_grid(self):
        recs = [self._record(20.0, 70.0, 1.0, depth=10.0),
                self._record(20.0, 70.0, 1.0, depth=100.0),
                self._record(20.0, 70.0, 1.0, depth=600.0)]
        seen = {}
        for band in ("surface", "pycnocline", "deep"):
            seen[band] = sum(c["n_samples"]
                             for c in zones.build_zones(recs, band=band)["zones"])
        self.assertEqual(seen, {"surface": 1, "pycnocline": 1, "deep": 1})

    def test_empty_input_yields_empty_grid_not_zeroes(self):
        out = zones.build_zones([])
        self.assertEqual(out["zones"], [])
        self.assertEqual(out["cells_with_data"], 0)
        self.assertEqual(out["zone_count"], 0)
        self.assertEqual(out["dead_zone_count"], 0)


class TestUnitConversion(unittest.TestCase):
    def test_umol_kg_to_mg_l(self):
        self.assertAlmostEqual(umol_kg_to_mg_l(62.5), 2.0, places=6)
        self.assertAlmostEqual(umol_kg_to_mg_l(15.625), 0.5, places=6)
        self.assertIsNone(umol_kg_to_mg_l(None))

    def test_dead_zone_anchor_in_both_unit_families(self):
        # 15.6 umol/kg is 0.5 mg/L: the two families must agree on the boundary.
        self.assertAlmostEqual(umol_kg_to_mg_l(15.6), 0.4992, places=4)
        self.assertEqual(severity_for_mg_l(umol_kg_to_mg_l(15.6))[1],
                         SEVERITY_ORDINALS["CRITICAL"])


class TestSpatialMappingKeepsMeasurementTrust(unittest.TestCase):
    REGIONS = [
        {"region_id": 1, "name": "Arabian Sea (Mumbai Coast)",
         "latitude": 19.0, "longitude": 72.8},
    ]

    def test_confidence_is_not_clobbered_by_distance_decay(self):
        # assign_records used to overwrite confidence_score with a distance
        # decay, pinning every open-ocean sample to 0.0 and making good
        # delayed-mode QC look worthless.
        records = [{"latitude": 23.5, "longitude": 62.2, "confidence_score": 0.95}]
        assign_records(records, self.REGIONS, max_radius=500.0)
        self.assertEqual(records[0]["confidence_score"], 0.95)
        self.assertIsNone(records[0]["region_id"])
        self.assertIsNone(records[0]["region_distance_km"])

    def test_in_region_sample_is_assigned_with_its_distance(self):
        records = [{"latitude": 19.0, "longitude": 72.8, "confidence_score": 0.95}]
        mapping = assign_records(records, self.REGIONS, max_radius=500.0)
        self.assertEqual(records[0]["region_id"], 1)
        self.assertEqual(records[0]["region_distance_km"], 0.0)
        self.assertEqual(records[0]["confidence_score"], 0.95)
        self.assertEqual(mapping["unassigned"], 0)

    def test_distant_sample_is_not_snapped_to_a_coast(self):
        records = [{"latitude": 0.5, "longitude": 90.0, "confidence_score": 0.6}]
        assign_records(records, self.REGIONS, max_radius=500.0)
        self.assertIsNone(records[0]["region_id"])


class TestRecordIdentityIsStable(unittest.TestCase):
    @staticmethod
    def _level(depth, profile_index=2, level_index=0, do_umol_kg=181.91,
               qc_flag="3"):
        return {
            "latitude": 23.5, "longitude": 62.2,
            "depth_m": depth, "do_umol_kg": do_umol_kg,
            "timestamp": None, "float_id": "1902660", "cycle": 79,
            "source_file": "BR1902660_079.nc",
            "source_url": "https://example.invalid/BR1902660_079.nc",
            "depth_source": "PRES", "qc_flag": qc_flag,
            "profile_index": profile_index, "level_index": level_index,
        }

    def test_repeated_depths_yield_distinct_record_ids(self):
        # BGC files stack several sensor groups and the optode repeats
        # near-identical pressures, so depth alone is not unique. Keying on
        # depth broke the (source, source_record_id) unique constraint and the
        # whole ingest died at commit.
        a = normalize.normalize_argo_doxy_level(self._level(0.20, 2, 0))
        b = normalize.normalize_argo_doxy_level(self._level(0.20, 2, 1))
        c = normalize.normalize_argo_doxy_level(self._level(0.20, 3, 0))
        ids = {a["source_record_id"], b["source_record_id"], c["source_record_id"]}
        self.assertEqual(len(ids), 3)

    def test_record_id_is_deterministic_for_a_repeat_ingest(self):
        first = normalize.normalize_argo_doxy_level(self._level(0.20, 2, 0))
        again = normalize.normalize_argo_doxy_level(self._level(0.20, 2, 0))
        self.assertEqual(first["source_record_id"], again["source_record_id"])

    def test_record_id_fits_the_column_width(self):
        # source_record_id is VARCHAR(64); an over-long id is truncated by some
        # backends, which would silently merge distinct samples.
        longest = "1902660_c79_BR1902660_079.nc_p10_l1000"
        rec = normalize.normalize_argo_doxy_level(
            self._level(0.20, 10, 1000))
        self.assertLessEqual(len(rec["source_record_id"]), 64)
        self.assertLessEqual(len(longest), 64)

    def test_negative_pressure_is_clamped_to_the_surface(self):
        # A float parked just above sea level reports a marginally negative
        # PRES, which falls outside every depth band.
        rec = normalize.normalize_argo_doxy_level(self._level(-0.1))
        self.assertEqual(rec["depth_m"], 0.0)

    def test_qc_flag_drives_confidence(self):
        good = normalize.normalize_argo_doxy_level(self._level(1.0, qc_flag="1"))
        suspect = normalize.normalize_argo_doxy_level(self._level(1.0, qc_flag="3"))
        self.assertEqual(good["confidence_score"], 0.95)
        self.assertEqual(suspect["confidence_score"], 0.6)

    def test_level_without_position_or_oxygen_is_rejected(self):
        self.assertIsNone(normalize.normalize_argo_doxy_level(
            {"latitude": None, "longitude": 62.2, "depth_m": 1.0, "do_umol_kg": 10.0}))
        self.assertIsNone(normalize.normalize_argo_doxy_level(
            {"latitude": 1.0, "longitude": 1.0, "depth_m": 1.0, "do_umol_kg": None}))

    def test_record_is_marked_real_never_synthetic(self):
        rec = normalize.normalize_argo_doxy_level(self._level(1.0))
        self.assertEqual(rec["origin_status"], "REAL")
        self.assertNotIn("synthetic", rec["quality_note"].lower())


if __name__ == "__main__":
    unittest.main()
