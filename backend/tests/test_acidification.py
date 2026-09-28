"""
Tests for the ocean acidification module.

The point of this suite is not coverage percentage - it is to pin down the
invariants that make the module scientifically defensible:

  * there is exactly ONE pH severity ladder, shared by ingest, the hotspot
    scorer and the zone grid (divergent copies silently mislabel stored rows);
  * a pH value outside the seawater plausibility window is REJECTED, and the
    Argo QC flag does not decide acceptance - because real-time BGC pH puts
    good values on flags 0/3 and sensor nonsense on flag 4;
  * an impossible pH is never classified, never stored and never used to
    derive carbonate chemistry;
  * aragonite is always derived, never presented as measured, and is absent
    rather than guessed when temperature or salinity is missing;
  * a derived aragonite is not scored as though it were an observation;
  * re-running an ingest is idempotent, so ingest cannot half-apply;
  * spatial mapping does not destroy measurement confidence.

All tests are pure: no database, no network, no NetCDF.
"""

import unittest
from datetime import datetime, timedelta, timezone

from app.modules.ai.acidification import hotspots, normalize, trends, units, zones
from app.modules.ai.acidification.regions import assign_records
from app.modules.ai.acidification.units import (
    ALERT_TIER_RULES,
    ARAGONITE_SATURATION,
    PH_PLAUSIBLE_MAX,
    PH_PLAUSIBLE_MIN,
    SEVERITY_LADDER,
    SEVERITY_ORDINAL_TO_LABEL,
    SEVERITY_ORDINALS,
    alert_for_ordinal,
    derive_carbonate_chemistry,
    is_ph_plausible,
    is_undersaturated,
    severity_for_ph,
    severity_label_for_ordinal,
    total_alkalinity_from_salinity,
)

# (pH, expected label) spanning every band and both boundaries.
LADDER_CASES = [
    (7.40, "CRITICAL"),
    (7.60, "CRITICAL"),
    (7.74, "CRITICAL"),
    (7.75, "HIGH"),
    (7.80, "HIGH"),
    (7.89, "HIGH"),
    (7.90, "MODERATE"),
    (7.95, "MODERATE"),
    (7.99, "MODERATE"),
    (8.00, "LOW"),
    (8.04, "LOW"),
    (8.05, "NORMAL"),
    (8.30, "NORMAL"),
]


def _level(depth=10.0, profile_index=2, level_index=0, ph_total=7.95,
           qc_flag="3", temperature_c=28.0, salinity_psu=35.0):
    """A plausible raw parser level, shaped exactly as parse.py emits it."""
    return {
        "latitude": 18.9, "longitude": 72.0,
        "depth_m": depth, "ph_total": ph_total,
        "timestamp": None, "float_id": "2903464", "cycle": 116,
        "source_file": "BR2903464_116.nc",
        "source_url": "https://example.invalid/BR2903464_116.nc",
        "depth_source": "PRES", "qc_flag": qc_flag,
        "ph_variable": "PH_IN_SITU_TOTAL",
        "ph_scale": "total",
        "profile_index": profile_index, "level_index": level_index,
        "temperature_c": temperature_c, "salinity_psu": salinity_psu,
    }


class TestPhysicalPlausibilityIsThePrimaryGate(unittest.TestCase):
    """The finding that shapes the whole module.

    Inspected directly in the monitored box, BGC-Argo pH profiles flagged QC
    '3'/'0' carry ordinary 7.44-8.47 values, while profiles flagged QC '4'
    carry -1.6 to 6.2. So QC is a confidence signal, not an acceptance test.
    """

    def test_normal_seawater_is_plausible(self):
        for ph in (7.44, 7.8, 8.05, 8.47, PH_PLAUSIBLE_MIN, PH_PLAUSIBLE_MAX):
            self.assertTrue(is_ph_plausible(ph), ph)

    def test_impossible_values_are_not_plausible(self):
        # These exact ranges were observed in real profiles flagged QC '4'.
        for ph in (-1.5877, 4.6834, 5.1980, 6.2072, 0.0, 12.0):
            self.assertFalse(is_ph_plausible(ph), ph)

    def test_none_and_nan_are_not_plausible(self):
        self.assertFalse(is_ph_plausible(None))
        self.assertFalse(is_ph_plausible(float("nan")))
        self.assertFalse(is_ph_plausible(float("inf")))

    def test_qc_flag_alone_does_not_decide_acceptance(self):
        # A physically ordinary value on a bad flag MUST survive ingest.
        good_value_bad_flag = normalize.normalize_argo_ph_level(
            _level(ph_total=7.90, qc_flag="4", temperature_c=28.0, salinity_psu=35.0)
        )
        self.assertIsNotNone(good_value_bad_flag)
        self.assertEqual(good_value_bad_flag["ph_total"], 7.90)

        # And a physically impossible value on a GOOD flag MUST NOT survive.
        # This is the direction that matters: accepting it would launder a
        # broken sensor into a scientific claim.
        impossible_good_flag = normalize.normalize_argo_ph_level(
            _level(ph_total=6.2072, qc_flag="1", temperature_c=28.0, salinity_psu=35.0)
        )
        self.assertIsNone(impossible_good_flag)

    def test_qc_modulates_confidence_but_not_acceptance(self):
        good = normalize.normalize_argo_ph_level(
            _level(ph_total=8.00, qc_flag="1"))
        none = normalize.normalize_argo_ph_level(
            _level(ph_total=8.00, qc_flag="0"))
        unchecked = normalize.normalize_argo_ph_level(
            _level(ph_total=8.00, qc_flag="3")
        )
        self.assertIsNotNone(good)
        self.assertIsNotNone(none)
        self.assertIsNotNone(unchecked)
        self.assertGreater(good["confidence_score"], none["confidence_score"])
        self.assertGreater(none["confidence_score"], unchecked["confidence_score"])


class TestSeverityLadderIsSingleSourced(unittest.TestCase):
    def test_ordinals_are_one_based(self):
        # 0 is reserved for "no classification" so it must not be NORMAL.
        self.assertEqual(SEVERITY_ORDINALS["NORMAL"], 1)
        self.assertEqual(SEVERITY_ORDINALS["CRITICAL"], 5)
        self.assertEqual(sorted(SEVERITY_ORDINALS.values()), [1, 2, 3, 4, 5])

    def test_ladder_breakpoints_match_stored_scale(self):
        bounds = [entry[1] for entry in SEVERITY_LADDER if entry[1] is not None]
        self.assertEqual(bounds, [7.75, 7.90, 8.00, 8.05])

    def test_classification_at_every_boundary(self):
        for ph, expected in LADDER_CASES:
            label, ordinal, _ = severity_for_ph(ph)
            self.assertEqual(label, expected, "pH %s" % ph)
            self.assertEqual(ordinal, SEVERITY_ORDINALS[expected], "pH %s" % ph)

    def test_normalize_classifier_agrees_with_units(self):
        # normalize.py used to carry its own ladder in the deoxygenation module;
        # a drift here silently mislabels every stored row.
        for ph, expected in LADDER_CASES:
            label, ordinal, acidic = normalize._classify_severity(ph)
            self.assertEqual(label, expected, "pH %s" % ph)
            self.assertEqual(ordinal, SEVERITY_ORDINALS[expected], "pH %s" % ph)
            self.assertEqual(int(acidic), int(ph < 8.00))

    def test_hotspots_ladder_agrees_with_units(self):
        self.assertEqual(
            [entry[:3] for entry in hotspots.SEVERITY_LADDER],
            [entry[:3] for entry in units.SEVERITY_LADDER],
            "hotspots.SEVERITY_LADDER has drifted from units.SEVERITY_LADDER",
        )

    def test_impossible_ph_is_never_classified(self):
        # The original defect class: defaulting an unclassifiable reading to
        # NORMAL turns a broken sensor into a healthy-looking measurement.
        label, ordinal, acidic = severity_for_ph(6.2072)
        self.assertIsNone(label)
        self.assertIsNone(ordinal)
        self.assertFalse(acidic)

        label, ordinal, acidic = severity_for_ph(None)
        self.assertIsNone(label)
        self.assertIsNone(ordinal)
        self.assertFalse(acidic)

    def test_missing_ph_is_not_classified_as_normal(self):
        label, ordinal, _ = severity_for_ph(None)
        self.assertIsNone(label)
        self.assertIsNone(ordinal)
        self.assertNotEqual(severity_label_for_ordinal(None), "Normal")


class TestOrdinalRendersBackToLabel(unittest.TestCase):
    def test_round_trip(self):
        for label, ordinal in SEVERITY_ORDINALS.items():
            self.assertEqual(SEVERITY_ORDINAL_TO_LABEL[ordinal], label)
            self.assertEqual(severity_label_for_ordinal(ordinal), label.title())

    def test_unknown_ordinal_is_not_reported_as_normal(self):
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
        self.assertEqual(alert_for_ordinal(5)[0], "critical")
        self.assertEqual(alert_for_ordinal(1)[0], "info")
        self.assertEqual(alert_for_ordinal(None)[0], "unknown")


class TestCarbonateChemistryIsDerivedAndBounded(unittest.TestCase):
    def test_alkalinity_relation_matches_reference(self):
        # Lee et al. (2006) global surface TA-S relation.
        self.assertAlmostEqual(total_alkalinity_from_salinity(35.0), 2305.0, places=1)
        self.assertGreater(total_alkalinity_from_salinity(34.0), 2250.0)
        self.assertLess(total_alkalinity_from_salinity(34.0), 2305.0)
        self.assertGreater(total_alkalinity_from_salinity(36.0), 2305.0)

    def test_benchmark_matches_known_ocean_chemistry(self):
        # Atlantic surface at pre-industrial pH: the published values for these
        # conditions are DIC ~2000 umol/kg and Omega_arag ~3.4. If this drifts,
        # every aragonite number in the module is wrong.
        out = derive_carbonate_chemistry(8.05, 25.0, 35.0, total_alkalinity_umol_kg=2300.0)
        self.assertEqual(out["status"], "OK")
        self.assertTrue(out["derived"])
        self.assertAlmostEqual(out["dic_umol_kg"], 2000.0, delta=40.0)
        self.assertAlmostEqual(out["omega_arag"], 3.4, delta=0.2)

    def test_alkalinity_uncertainty_is_small_and_bounded(self):
        # The module claims a +-50 umol/kg TA error moves Omega by ~+-0.08.
        # That claim is load-bearing in the user-facing note, so pin it.
        base = derive_carbonate_chemistry(7.95, 25.0, 35.0, total_alkalinity_umol_kg=2300.0)
        low = derive_carbonate_chemistry(7.95, 25.0, 35.0, total_alkalinity_umol_kg=2250.0)
        high = derive_carbonate_chemistry(7.95, 25.0, 35.0, total_alkalinity_umol_kg=2350.0)
        self.assertLess(abs(low["omega_arag"] - base["omega_arag"]), 0.15)
        self.assertLess(abs(high["omega_arag"] - base["omega_arag"]), 0.15)

    def test_aragonite_falls_monotonically_with_ph(self):
        previous = None
        for ph in (8.4, 8.2, 8.0, 7.9, 7.8, 7.6, 7.45):
            out = derive_carbonate_chemistry(ph, 28.0, 35.0)
            self.assertEqual(out["status"], "OK", ph)
            if previous is not None:
                self.assertLess(out["omega_arag"], previous, "pH %s" % ph)
            previous = out["omega_arag"]

    def test_no_derivation_without_temperature_or_salinity(self):
        # Carbonate equilibria are strongly temperature dependent, so a
        # climatological substitute would be worse than a gap.
        for temp, sal in ((None, 35.0), (28.0, None), (None, None)):
            out = derive_carbonate_chemistry(8.00, temp, sal)
            self.assertNotEqual(out["status"], "OK", (temp, sal))
            self.assertFalse(out["derived"], (temp, sal))
            self.assertIsNone(out["omega_arag"], (temp, sal))
            self.assertIn("temperature", out["reason"] + "salinity")

    def test_no_derivation_from_impossible_ph(self):
        out = derive_carbonate_chemistry(6.2072, 28.0, 35.0)
        self.assertEqual(out["status"], "NON_PHYSICAL")
        self.assertFalse(out["derived"])
        self.assertIsNone(out["omega_arag"])

    def test_no_derivation_without_ph(self):
        out = derive_carbonate_chemistry(None, 28.0, 35.0)
        self.assertEqual(out["status"], "NO_PH")
        self.assertFalse(out["derived"])

    def test_undertself_missing_omega_is_never_undersaturated(self):
        # Absence of a derivation is not evidence of undersaturation;
        # reporting it as such would manufacture an alert.
        self.assertFalse(is_undersaturated(None))
        self.assertTrue(is_undersaturated(0.5))
        self.assertFalse(is_undersaturated(2.0))
        self.assertFalse(is_undersaturated(ARAGONITE_SATURATION))


class TestRecordIdentityIsStable(unittest.TestCase):
    def test_repeated_depths_yield_distinct_record_ids(self):
        # BGC files stack several sensor groups and the pH sensor repeats
        # near-identical pressures, so depth alone is not unique.
        a = normalize.normalize_argo_ph_level(
            _level(10.0, 2, 0))
        b = normalize.normalize_argo_ph_level(
            _level(10.0, 2, 1))
        c = normalize.normalize_argo_ph_level(
            _level(10.0, 3, 0))
        self.assertEqual(len({a["source_record_id"], b["source_record_id"],
                              c["source_record_id"]}), 3)

    def test_record_id_is_deterministic_for_a_repeat_ingest(self):
        first = normalize.normalize_argo_ph_level(
            _level(10.0, 2, 0))
        again = normalize.normalize_argo_ph_level(
            _level(10.0, 2, 0))
        self.assertEqual(first["source_record_id"], again["source_record_id"])

    def test_record_id_fits_the_column_width(self):
        # source_record_id is VARCHAR(64); an over-long id is truncated by some
        # backends, which would silently merge distinct samples.
        rec = normalize.normalize_argo_ph_level(
            _level(10.0, 10, 1000))
        self.assertLessEqual(len(rec["source_record_id"]), 64)

    def test_negative_pressure_is_clamped_to_the_surface(self):
        rec = normalize.normalize_argo_ph_level(
            _level(-0.1))
        self.assertEqual(rec["depth_m"], 0.0)

    def test_level_without_position_or_ph_is_rejected(self):
        self.assertIsNone(normalize.normalize_argo_ph_level(
            {"latitude": None, "longitude": 72.0, "depth_m": 10.0, "ph_total": 7.9}))
        self.assertIsNone(normalize.normalize_argo_ph_level(
            {"latitude": 18.9, "longitude": 72.0, "depth_m": 10.0, "ph_total": None}))

    def test_record_is_marked_real_never_synthetic(self):
        rec = normalize.normalize_argo_ph_level(
            _level(10.0))
        self.assertEqual(rec["origin_status"], "REAL")
        self.assertNotIn("synthetic", rec["quality_note"].lower())

    def test_derived_omega_is_flagged_as_derived(self):
        rec = normalize.normalize_argo_ph_level(
            _level(10.0))
        self.assertEqual(rec["omega_arag_derived"], 1)
        self.assertIn("DERIVED", rec["quality_note"])
        self.assertIsNotNone(rec["omega_arag"])

    def test_record_without_temperature_stores_no_omega(self):
        rec = normalize.normalize_argo_ph_level(
            _level(10.0, temperature_c=None)
        )
        self.assertIsNotNone(rec)
        self.assertIsNone(rec["omega_arag"])
        self.assertEqual(rec["omega_arag_derived"], 0)

    def test_batch_counts_implausible_rejections_separately(self):
        # Conflating "no pH data" with "broken pH sensor" is how a faulty float
        # becomes indistinguishable from a sparse one.
        batch = normalize.normalize_batch(
            [
                _level(10.0, 2, 0),                              # good
                {"latitude": 1.0, "longitude": 1.0, "ph_total": None},  # absent
                {"latitude": 1.0, "longitude": 1.0, "ph_total": 6.2,
                 "depth_m": 10.0},                                   # implausible
            ]
        )
        self.assertEqual(len(batch["normalized"]), 1)
        self.assertEqual(batch["rejected_no_ph"], 1)
        self.assertEqual(batch["rejected_implausible"], 1)
        self.assertEqual(batch["rejected_count"], 2)
        self.assertEqual(batch["plausibility_window"],
                         [PH_PLAUSIBLE_MIN, PH_PLAUSIBLE_MAX])


class TestSpatialMappingKeepsMeasurementTrust(unittest.TestCase):
    REGIONS = [
        {"region_id": 1, "name": "Arabian Sea (Mumbai Coast)",
         "latitude": 18.9, "longitude": 72.0},
    ]

    def test_confidence_is_not_clobbered_by_distance_decay(self):
        records = [{"latitude": 19.5, "longitude": 73.0, "confidence_score": 0.95}]
        assign_records(records, self.REGIONS, max_radius=500.0)
        self.assertEqual(records[0]["confidence_score"], 0.95)
        self.assertEqual(records[0]["region_id"], 1)

    def test_distant_sample_is_not_snapped_to_a_coast(self):
        records = [{"latitude": 0.5, "longitude": 90.0, "confidence_score": 0.6}]
        assign_records(records, self.REGIONS, max_radius=500.0)
        self.assertIsNone(records[0]["region_id"])


class TestZoneGridHonesty(unittest.TestCase):
    @staticmethod
    def _record(lat, lon, ph, depth=100.0, omega=None):
        label, ordinal, acidic = severity_for_ph(ph)
        return {
            "latitude": lat, "longitude": lon, "depth_m": depth,
            "ph_total": ph, "omega_arag": omega,
            "severity_label": label, "severity_ordinal": ordinal,
            "is_acidic": acidic, "float_id": "2903464",
        }

    def test_healthy_cell_is_not_a_zone(self):
        out = zones.build_zones([self._record(10.0, 70.0, 8.10, omega=3.9)])
        cell = out["zones"][0]
        self.assertFalse(cell["is_zone"])
        self.assertFalse(cell["is_undersaturated"])
        self.assertEqual(cell["worst_ordinal"], SEVERITY_ORDINALS["NORMAL"])
        self.assertEqual(cell["worst_label"], "Normal")
        self.assertEqual(out["zone_count"], 0)

    def test_acidic_cell_is_flagged(self):
        out = zones.build_zones([self._record(18.75, 69.75, 7.70, depth=50.0, omega=1.4)])
        cell = out["zones"][0]
        self.assertTrue(cell["is_zone"])
        self.assertEqual(cell["worst_label"], "Critical")
        self.assertEqual(out["zone_count"], 1)

    def test_undersaturation_is_detected_independently(self):
        # pH 8.02 is LOW (not a zone on the ladder) but Omega 0.8 is genuinely
        # undersaturated, and a cell where shells dissolve IS a stress zone.
        out = zones.build_zones([self._record(10.0, 70.0, 8.02, omega=0.8)])
        self.assertFalse(out["zones"][0]["is_zone"])
        self.assertTrue(out["zones"][0]["is_undersaturated"])
        self.assertEqual(out["undersaturated_count"], 1)

    def test_cell_reports_worst_sample_not_mean(self):
        # A cell averaging 8.05 that dips to 7.6 is a stress zone.
        recs = [self._record(10.0, 70.0, 8.10), self._record(10.0, 70.0, 7.60)]
        cell = zones.build_zones(recs)["zones"][0]
        self.assertTrue(cell["is_zone"])
        self.assertEqual(cell["min_ph"], 7.60)
        self.assertEqual(cell["worst_label"], "Critical")
        self.assertEqual(cell["n_samples"], 2)

    def test_mean_omega_only_covers_samples_that_have_one(self):
        # A cell where only some levels had temperature must not report a mean
        # over the rest as though it were measured.
        recs = [self._record(10.0, 70.0, 8.00, omega=None),
                self._record(10.0, 70.0, 8.00, omega=2.0)]
        cell = zones.build_zones(recs)["zones"][0]
        self.assertEqual(cell["n_with_omega"], 1)
        self.assertEqual(cell["mean_omega"], 2.0)

    def test_cell_with_no_omega_reports_none_not_zero(self):
        cell = zones.build_zones([self._record(10.0, 70.0, 8.00, omega=None)])["zones"][0]
        self.assertIsNone(cell["mean_omega"])
        self.assertIsNone(cell["min_omega"])
        self.assertEqual(cell["n_with_omega"], 0)

    def test_depth_band_filter_partitions_the_grid(self):
        recs = [self._record(20.0, 70.0, 7.9, depth=10.0),
                self._record(20.0, 70.0, 7.9, depth=100.0),
                self._record(20.0, 70.0, 7.9, depth=600.0)]
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


class TestHotspotDetection(unittest.TestCase):
    REGIONS = [
        {"region_id": 1, "name": "Arabian Sea (Mumbai Coast)",
         "latitude": 18.9, "longitude": 72.0},
    ]

    @staticmethod
    def _sample(ph, depth=10.0, days_ago=0, omega=None, float_id="2903464"):
        return {
            "region_id": 1, "latitude": 18.9, "longitude": 72.0,
            "depth_m": depth, "ph_total": ph, "omega_arag": omega,
            "severity_ordinal": SEVERITY_ORDINALS[severity_for_ph(ph)[0]],
            "is_acidic": int(ph < 8.0), "is_undersaturated": int(
                omega is not None and omega < ARAGONITE_SATURATION),
            "confidence_score": 0.75,
            "sampled_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
            "float_id": float_id, "region_distance_km": 12.0,
        }

    def test_no_hotspot_when_all_samples_are_healthy(self):
        out = hotspots.detect_stress_zones(
            [self._sample(8.10) for _ in range(5)], self.REGIONS
        )
        self.assertEqual(out["hotspot_count"], 0)
        self.assertEqual(out["anomaly_category"], "Acidification Stress Zone")

    def test_hotspot_detected_and_ranked_by_priority(self):
        severe = [self._sample(7.65, days_ago=i) for i in range(6)]
        mild = [self._sample(7.92, days_ago=i) for i in range(6)]
        out = hotspots.detect_stress_zones(severe + mild, self.REGIONS)
        self.assertGreaterEqual(out["hotspot_count"], 1)
        top = out["hotspots"][0]
        self.assertEqual(top["region_id"], 1)
        self.assertEqual(top["severity"], "CRITICAL")
        self.assertGreater(top["priority"], 0)
        self.assertTrue(top["recommendations"])
        self.assertIn("shell", " ".join(top["recommendations"]).lower())

    def test_undersaturation_escalates_severity_and_recommends_shellfish(self):
        # pH 7.92 is only MODERATE, but Omega 0.6 is actively corrosive.
        out = hotspots.detect_stress_zones(
            [self._sample(7.92, omega=0.6, days_ago=i) for i in range(4)],
            self.REGIONS,
        )
        self.assertEqual(out["hotspot_count"], 1)
        top = out["hotspots"][0]
        self.assertEqual(top["severity"], "CRITICAL")
        joined = " ".join(top["recommendations"]).lower()
        self.assertIn("shellfish", joined)
        self.assertIn("dissolve", joined)

    def test_unassigned_samples_never_form_a_hotspot(self):
        recs = [self._sample(7.60, days_ago=i) for i in range(4)]
        for r in recs:
            r["region_id"] = None
        out = hotspots.detect_stress_zones(recs, self.REGIONS)
        self.assertEqual(out["hotspot_count"], 0)

    def test_min_priority_filters_results(self):
        recs = [self._sample(7.92, days_ago=i) for i in range(4)]
        everything = hotspots.detect_stress_zones(recs, self.REGIONS)
        self.assertEqual(everything["hotspot_count"], 1)
        self.assertEqual(
            hotspots.detect_stress_zones(recs, self.REGIONS, min_priority=100.0)[
                "hotspot_count"
            ],
            0,
        )


class TestTrendsRefuseToOverclaim(unittest.TestCase):
    def test_insufficient_points_reports_insufficient_data(self):
        series = [
            {"ph_total": 8.0, "date": datetime.now(timezone.utc), "is_acidic": 0}
            for _ in range(3)
        ]
        out = trends._compute_trend(series, min_points=5)
        self.assertEqual(out["direction"], "insufficient_data")
        self.assertIsNone(out["slope_ph_per_year"])

    def test_flat_series_is_not_declining(self):
        base = datetime(2020, 1, 1, tzinfo=timezone.utc)
        series = [
            {"ph_total": 8.05, "date": base + timedelta(days=30 * i), "is_acidic": 0}
            for i in range(12)
        ]
        out = trends._compute_trend(series)
        self.assertNotEqual(out["direction"], "declining")
        self.assertAlmostEqual(out["slope_ph_per_year"], 0.0, places=4)

    def test_projection_refuses_to_claim_a_direction_when_insignificant(self):
        base = datetime.now(timezone.utc) - timedelta(days=400)
        recs = [
            {
                "region_id": 1, "ph_total": 8.05 + (0.01 if i % 2 else 0.0),
                "depth_m": 10.0, "sampled_at": base + timedelta(days=7 * i),
                "is_acidic": 0, "omega_arag": 3.4,
            }
            for i in range(30)
        ]
        out = trends.project_ph_decline(
            recs, {"region_id": 1, "name": "Arabian Sea"}, horizon_days=180
        )
        self.assertEqual(out["status"], "PROJECTION")
        self.assertEqual(out["projected"]["change"], "INDETERMINATE")
        self.assertEqual(out["status"], out["status"])  # shape guard
        self.assertIn("PROJECTION", out["disclaimer"])

    def test_projection_declines_when_the_slope_is_real(self):
        base = datetime.now(timezone.utc) - timedelta(days=700)
        recs = [
            {
                "region_id": 1, "ph_total": 8.10 - 0.01 * i, "depth_m": 10.0,
                "sampled_at": base + timedelta(days=20 * i),
                "is_acidic": int(8.10 - 0.01 * i < 8.0), "omega_arag": 3.0,
            }
            for i in range(35)
        ]
        out = trends.project_ph_decline(
            recs, {"region_id": 1, "name": "Arabian Sea"}, horizon_days=180
        )
        self.assertEqual(out["projected"]["change"], "DECLINING")
        self.assertLess(out["projected"]["ph_total"], out["current"]["ph_total"])

    def test_projection_needs_enough_data(self):
        out = trends.project_ph_decline(
            [], {"region_id": 1, "name": "Arabian Sea"}, horizon_days=180
        )
        self.assertEqual(out["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(out["projection"])


class TestSourceIndexMatching(unittest.TestCase):
    def test_real_ph_tokens_match(self):
        from app.modules.ai.acidification.sources import _has_ph

        self.assertTrue(_has_ph("PRES TEMP PH_IN_SITU_FREE PH_IN_SITU_TOTAL"))
        self.assertTrue(_has_ph("PH_IN_SITU_TOTAL"))

    def test_sensor_diagnostics_do_not_match(self):
        # VRS_PH is a voltage difference, TEMP_PH a temperature, IB_PH/IK_PH/
        # VK_PH diagnostics. None is a pH measurement, and a bare "PH" in the
        # string would wrongly select floats whose files carry no pH at all.
        from app.modules.ai.acidification.sources import _has_ph

        self.assertFalse(_has_ph("PRES TEMP_DOXY VRS_PH TEMP_PH"))
        self.assertFalse(_has_ph("PRES IB_PH IK_PH VK_PH"))
        self.assertFalse(_has_ph("PRES DOXY CHLA BBP700"))
        self.assertFalse(_has_ph(""))


class TestCoLocatedCoreProfileJoin(unittest.TestCase):
    """The join that makes aragonite possible at all.

    Real pH-bearing BGC files carry no practical salinity. Without PSAL the
    alkalinity estimate has no basis and no aragonite can be derived, so the
    module reads the co-located CORE profile, which publishes measured PSAL
    and TEMP for the same cast.
    """

    def test_core_url_strips_the_bgc_marker_only(self):
        from app.modules.ai.acidification.parse import core_profile_url

        self.assertEqual(
            core_profile_url(
                "https://data-argo.ifremer.fr/dac/aoml/2903464/profiles/BR2903464_116.nc"
            ),
            "https://data-argo.ifremer.fr/dac/aoml/2903464/profiles/R2903464_116.nc",
        )
        # Delayed-mode BGC maps to the delayed-mode core file, not to real-time.
        self.assertTrue(
            core_profile_url(
                "https://data-argo.ifremer.fr/dac/x/1/profiles/BD6990514_151.nc"
            ).endswith("D6990514_151.nc")
        )

    def test_non_conforming_names_yield_no_core_url(self):
        from app.modules.ai.acidification.parse import core_profile_url

        # An empty result lets the caller skip the join rather than guess at a
        # path that might not exist.
        self.assertEqual(core_profile_url(""), "")
        self.assertEqual(core_profile_url("https://x/R1.nc"), "")
        self.assertEqual(core_profile_url("https://x/B.nc"), "")

    def test_core_fills_the_salinity_gap_the_bgc_file_leaves(self):
        from app.modules.ai.acidification.parse import apply_core_physics

        # This is the exact shape of a real pH-bearing BGC level: a pH, a
        # co-located optode temperature, and no practical salinity at all.
        level = apply_core_physics(
            {"temperature_c": 29.84, "salinity_psu": None},
            {"temperature_c": 12.5, "salinity_psu": 35.1},
        )
        self.assertAlmostEqual(level["salinity_psu"], 35.1, places=6)
        # The BGC file's own temperature is kept - same instrument package.
        self.assertAlmostEqual(level["temperature_c"], 29.84, places=6)

    def test_core_fills_a_missing_temperature_too(self):
        from app.modules.ai.acidification.parse import apply_core_physics

        level = apply_core_physics(
            {"temperature_c": None, "salinity_psu": None},
            {"temperature_c": 12.5, "salinity_psu": 35.1},
        )
        self.assertAlmostEqual(level["temperature_c"], 12.5, places=6)
        self.assertAlmostEqual(level["salinity_psu"], 35.1, places=6)

    def test_bgc_own_reading_is_never_overwritten(self):
        from app.modules.ai.acidification.parse import apply_core_physics

        # Both files measured these. The BGC optode sits in the same package
        # as the pH sensor, so it wins; the core CTD does not overwrite it.
        level = apply_core_physics(
            {"temperature_c": 29.84, "salinity_psu": 33.61},
            {"temperature_c": 12.5, "salinity_psu": 35.1},
        )
        self.assertAlmostEqual(level["salinity_psu"], 33.61, places=6)
        self.assertAlmostEqual(level["temperature_c"], 29.84, places=6)

    def test_absent_core_leaves_the_gap_open_rather_than_guessing(self):
        from app.modules.ai.acidification.parse import apply_core_physics

        # A failed or absent core fetch must not be papered over with a
        # climatological salinity: that would be a fabricated input to a
        # scientific claim. The gap stays, and derivation stays skipped.
        for core in (None, {}, {"temperature_c": None, "salinity_psu": None}):
            level = apply_core_physics(
                {"temperature_c": None, "salinity_psu": None}, core
            )
            self.assertIsNone(level["salinity_psu"])
            self.assertIsNone(level["temperature_c"])

    def test_joined_physics_actually_unlocks_aragonite(self):
        from app.modules.ai.acidification.parse import apply_core_physics
        from app.modules.ai.acidification.units import derive_carbonate_chemistry

        # Before the join, a pH with no salinity can produce no aragonite at
        # all - this is exactly the state the module was in.
        before = derive_carbonate_chemistry(
            ph_total=8.05, temperature_c=None, salinity_psu=None
        )
        self.assertEqual(before["status"], "MISSING_T_S")
        self.assertIsNone(before.get("omega_arag"))

        level = apply_core_physics(
            {"temperature_c": None, "salinity_psu": None},
            {"temperature_c": 12.5, "salinity_psu": 35.1},
        )
        after = derive_carbonate_chemistry(
            ph_total=8.05,
            temperature_c=level["temperature_c"],
            salinity_psu=level["salinity_psu"],
        )
        self.assertEqual(after["status"], "OK")
        self.assertIsNotNone(after["omega_arag"])
        self.assertTrue(after["derived"])


class TestCoreJoinIsByPressureNotArrayIndex(unittest.TestCase):
    """Regression cover for the join that silently produced nothing.

    Real file BR6990700_072.nc: the BGC pH lives in profile index 5 (304
    levels, 0.3-1999.5 dbar) while the co-located core file's PSAL lives in
    profile index 6 (84 levels, same 0.3-1999.5 dbar span). Both files report
    an identical cast time, so neither index nor time identifies the pair. An
    index join returns nothing for every level, and a miss is indistinguishable
    from an absent measurement downstream.
    """

    @staticmethod
    def _core_profile(pressures, temperature=12.0, salinity=35.0):
        return [
            {
                "pressure_dbar": p,
                "temperature_c": temperature,
                "salinity_psu": salinity,
            }
            for p in pressures
        ]

    def test_matches_profiles_by_pressure_span_across_differing_indices(self):
        from app.modules.ai.acidification.parse import build_core_lookup

        # BGC profile 5 carries pH across this span...
        bgc_pressures = {5: [0.3, 500.0, 1000.0, 1999.5]}
        # ...and the core file happens to keep its salinity in profile 6.
        core_profiles = [[] for _ in range(6)]
        core_profiles.append(self._core_profile([0.3, 1000.0, 1999.5]))

        lookup = build_core_lookup(bgc_pressures, core_profiles)

        self.assertEqual(len(lookup), 4, "every pH level must find its core cast")
        self.assertAlmostEqual(lookup[(5, 0)]["salinity_psu"], 35.0, places=6)
        self.assertAlmostEqual(lookup[(5, 3)]["salinity_psu"], 35.0, places=6)

    def test_interpolates_between_bracketing_measurements(self):
        from app.modules.ai.acidification.parse import _interpolate_by_pressure

        profile = self._core_profile(
            [0.0, 1000.0, 2000.0], temperature=10.0, salinity=34.0
        )
        # Halfway between the 0 and 1000 dbar measurements.
        mid = _interpolate_by_pressure(profile, 500.0)
        self.assertIsNotNone(mid)
        self.assertAlmostEqual(mid["temperature_c"], 10.0, places=6)
        self.assertAlmostEqual(mid["salinity_psu"], 34.0, places=6)

    def test_interpolates_a_real_gradient(self):
        from app.modules.ai.acidification.parse import _interpolate_by_pressure

        # Temperature falls linearly 20 -> 10 C over 0-1000 dbar, as it does in
        # a real thermocline. The midpoint must be 15 C, not either endpoint.
        profile = [
            {"pressure_dbar": 0.0, "temperature_c": 20.0, "salinity_psu": 34.5},
            {"pressure_dbar": 1000.0, "temperature_c": 10.0, "salinity_psu": 35.5},
        ]
        mid = _interpolate_by_pressure(profile, 500.0)
        self.assertAlmostEqual(mid["temperature_c"], 15.0, places=6)
        self.assertAlmostEqual(mid["salinity_psu"], 35.0, places=6)

    def test_never_extrapolates_beyond_the_measured_span(self):
        from app.modules.ai.acidification.parse import _interpolate_by_pressure

        profile = self._core_profile([10.0, 500.0, 1000.0])
        # Both of these are outside what the CTD actually sampled. Inventing a
        # value here would be fabricating the input to a scientific claim.
        self.assertIsNone(_interpolate_by_pressure(profile, 5.0))
        self.assertIsNone(_interpolate_by_pressure(profile, 1500.0))
        # The span edges themselves are real measurements.
        self.assertIsNotNone(_interpolate_by_pressure(profile, 10.0))
        self.assertIsNotNone(_interpolate_by_pressure(profile, 1000.0))

    def test_coarse_cast_still_covers_its_whole_span(self):
        from app.modules.ai.acidification.parse import _interpolate_by_pressure

        # An 84-level cast over 2000 dbar has ~24 dbar gaps. A nearest-
        # neighbour join left a third of the pH levels with nothing; the
        # interpolating join must cover the entire measured range.
        grid = [float(p) for p in range(0, 2000, 24)]
        profile = self._core_profile(grid)
        for p in (1.0, 7.3, 11.9, 999.5, 1500.2, grid[-1]):
            self.assertIsNotNone(
                _interpolate_by_pressure(profile, p), f"no value at {p} dbar"
            )
        # Past the last real bin is still out of reach, and stays out.
        self.assertIsNone(_interpolate_by_pressure(profile, grid[-1] + 5.0))

    def test_a_legitimately_slightly_negative_top_bin_is_not_discarded(self):
        from app.modules.ai.acidification.parse import build_core_lookup

        # R4902626_145's core cast spans -0.1 to 1968.2 dbar. A validity test
        # of "span starts above 0" threw this whole cast away, costing 482
        # samples their aragonite.
        core_profiles = [self._core_profile([-0.1, 500.0, 1968.2])]
        lookup = build_core_lookup({0: [0.0, 500.0, 1900.0]}, core_profiles)
        self.assertEqual(len(lookup), 3)

    def test_empty_core_profile_never_invents_a_value(self):
        from app.modules.ai.acidification.parse import build_core_lookup

        self.assertEqual(build_core_lookup({0: [0.0, 10.0]}, []), {})
        # A file whose core profiles are all empty is not a usable match.
        self.assertEqual(build_core_lookup({0: [0.0, 10.0]}, [[], []]), {})

    def test_levels_without_pressure_get_no_join(self):
        from app.modules.ai.acidification.parse import build_core_lookup

        core_profiles = [self._core_profile([0.0, 100.0])]
        lookup = build_core_lookup({0: [None, None]}, core_profiles)
        self.assertEqual(lookup, {})


if __name__ == "__main__":
    unittest.main()
