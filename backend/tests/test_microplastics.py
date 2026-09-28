"""
Tests for the microplastics module.

The point of this suite is not coverage percentage - it is to pin down the
handful of invariants that make the module scientifically defensible:

  * concentrations from different unit families are never combined;
  * the same number classifies differently in water and in sediment, because
    the source's ladder is per-medium;
  * an empty result always carries a reason and is never rendered as zero;
  * drift is not projected when there is no real forcing.

All tests are pure: no database, no network.  The connectors are exercised
through a patched httpx so their failure contract is asserted, not assumed.
"""

import unittest
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx

from app.modules.ai.microplastics import sources
from app.modules.ai.microplastics.drift import project_drift
from app.modules.ai.microplastics.hotspots import (
    ANOMALY_CATEGORY,
    collection_vintage,
    detect_hotspots,
    group_samples,
)
from app.modules.ai.microplastics.normalize import (
    normalize_batch,
    normalize_literature_batch,
    normalize_literature_record,
    normalize_noaa_record,
)
from app.modules.ai.microplastics.regions import (
    assign_records,
    build_surface,
    idw_at_point,
    nearest_region,
)
from app.modules.ai.microplastics.units import (
    FAMILY_NURDLE,
    FAMILY_SEDIMENT,
    FAMILY_UNKNOWN,
    FAMILY_WATER,
    MEDIUM_BEACH,
    MEDIUM_SEDIMENT,
    MEDIUM_WATER,
    classify_medium,
    normalize_unit,
    severity_for,
)


# --------------------------------------------------------------------------
# Fakes for the drift tests - no database needed.
# --------------------------------------------------------------------------
class _EmptyQuery:
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return []


class _EmptySession:
    def query(self, *args, **kwargs):
        return _EmptyQuery()


class _ObservedCurrent:
    location_id = 1
    current_speed = 0.5
    current_direction = 90.0
    timestamp = datetime(2021, 12, 1, tzinfo=timezone.utc)
    source = "Argo float"
    data_type = "observation"


class _ObservedQuery(_EmptyQuery):
    def all(self):
        return [_ObservedCurrent()]


class _ForcingSession:
    def query(self, *args, **kwargs):
        return _ObservedQuery()


def _noaa_attrs(**overrides) -> dict:
    """A realistic NOAA NCEI attribute dict, overridable per test."""
    attrs = {
        "OBJECTID": 1234,
        "Latitude__degree_": 8.493267,
        "Longitude_degree_": 78.127822,
        "Location_Oceans": "Indian Ocean",
        "Location_Regions": "Laccadive Sea",
        "Location_SubRegions": "Gulf of Mannar",
        "Country": None,
        "Medium": "Ocean water",
        "Water_Sample_Depth__m_": 0.0,
        "Sampling_Method": "manta trawl",
        "Mesh_size__mm_": 0.33,
        "Microplastics_measurement": 0.05,
        "Unit": "pieces/m3",
        "Concentration_class_text": "Medium",
        "Concentration_class_range": "0.005-1",
        "Short_Reference": "Test 2021",
        "DOI": "10.0000/test",
        "ORGANIZATION": "Fisheries College",
        "Date_m_d_yyyy": 1638921600000,  # 2021-12-08
    }
    attrs.update(overrides)
    return attrs


class UnitFamilyTests(unittest.TestCase):
    """The unit-family boundary is what keeps unlike values apart."""

    def test_units_map_to_the_right_family(self):
        self.assertEqual(normalize_unit("pieces/m3"), ("pieces/m3", 1.0, FAMILY_WATER))
        self.assertEqual(
            normalize_unit("pieces kg-1 d.w."), ("pieces/kg dw", 1.0, FAMILY_SEDIMENT)
        )
        self.assertEqual(
            normalize_unit("pieces/10 mins"), ("pieces/10 min", 1.0, FAMILY_NURDLE)
        )

    def test_within_family_conversion_is_allowed(self):
        unit, factor, family = normalize_unit("pieces/L")
        self.assertEqual(unit, "pieces/m3")
        self.assertEqual(factor, 1000.0)
        self.assertEqual(family, FAMILY_WATER)

    def test_published_sediment_synonyms_all_resolve_to_pieces_per_kg(self):
        for unit in ("items/kg", "items/kg dw", "items kg-1", "items kg-1 dw",
                     "items per kg", "particles/kg", "particles/kg dw",
                     "particles kg-1", "numbers/kg", "numbers kg-1"):
            canonical, factor, family = normalize_unit(unit)
            self.assertEqual(canonical, "pieces/kg dw")
            self.assertEqual(factor, 1.0)
            self.assertEqual(family, FAMILY_SEDIMENT)

    def test_water_volume_synonyms_support_curated_rows(self):
        self.assertEqual(
            normalize_unit("items/m3"), ("pieces/m3", 1.0, FAMILY_WATER)
        )
        self.assertEqual(
            normalize_unit("items/L"), ("pieces/m3", 1000.0, FAMILY_WATER)
        )

    def test_unknown_units_are_not_silently_treated_as_normalised(self):
        unit, factor, family = normalize_unit("bananas per fortnight")
        self.assertIsNone(unit)
        self.assertEqual(factor, 1.0)
        self.assertEqual(family, FAMILY_UNKNOWN)

    def test_medium_classification(self):
        self.assertEqual(classify_medium("Ocean water"), (MEDIUM_WATER, FAMILY_WATER))
        self.assertEqual(
            classify_medium("Ocean sediment"), (MEDIUM_SEDIMENT, FAMILY_SEDIMENT)
        )
        self.assertEqual(classify_medium("Beach"), (MEDIUM_BEACH, FAMILY_WATER))
        self.assertEqual(classify_medium(None), ("unknown", FAMILY_UNKNOWN))
        self.assertEqual(classify_medium("Martian regolith"), ("unknown", FAMILY_UNKNOWN))


class SeverityLadderTests(unittest.TestCase):
    """The ladder is per-medium; this is the module's central correctness claim."""

    def test_same_value_classifies_differently_across_media(self):
        water = severity_for(54.0, MEDIUM_WATER, FAMILY_WATER)
        sediment = severity_for(54.0, MEDIUM_SEDIMENT, FAMILY_SEDIMENT)

        self.assertEqual(water[0], "HIGH")       # water ladder tops out at >= 1
        self.assertEqual(sediment[0], "MEDIUM")  # sediment Medium is 20-150
        self.assertNotEqual(water[0], sediment[0])

    def test_published_source_class_always_wins(self):
        label, ordinal, note = severity_for(
            0.05, MEDIUM_WATER, FAMILY_WATER, published_class="Very High"
        )
        self.assertEqual(label, "VERY_HIGH")
        self.assertEqual(ordinal, 4)
        self.assertIn("published by source", note)

    def test_unclassifiable_input_reports_a_reason_instead_of_guessing(self):
        label, ordinal, note = severity_for(5.0, "unknown", FAMILY_UNKNOWN)
        self.assertIsNone(label)
        self.assertIsNone(ordinal)
        self.assertIn("no published concentration ladder", note)

    def test_nurdle_family_has_no_ladder_and_says_so(self):
        label, ordinal, _ = severity_for(3.0, "beach_nurdle", FAMILY_NURDLE)
        self.assertIsNone(label)
        self.assertIsNone(ordinal)

    def test_sediment_very_high_band_is_open_ended(self):
        self.assertEqual(severity_for(9999.0, MEDIUM_SEDIMENT, FAMILY_SEDIMENT)[0], "VERY_HIGH")


class NormalizeTests(unittest.TestCase):
    def test_normalizes_a_real_water_sample(self):
        record = normalize_noaa_record(_noaa_attrs())

        self.assertEqual(record["medium"], MEDIUM_WATER)
        self.assertEqual(record["unit_family"], FAMILY_WATER)
        self.assertEqual(record["measured_value"], 0.05)
        self.assertEqual(record["canonical_value"], 0.05)
        self.assertEqual(record["origin_status"], "REAL")
        self.assertEqual(record["severity_label"], "MEDIUM")
        self.assertEqual(record["severity_ordinal"], 2)
        self.assertEqual(record["timestamp"].year, 2021)
        self.assertEqual(record["timestamp"].month, 12)

    def test_sediment_sample_keeps_its_own_unit_and_is_never_converted(self):
        record = normalize_noaa_record(_noaa_attrs(
            Medium="Ocean sediment",
            Unit="pieces kg-1 d.w.",
            Microplastics_measurement=54,
            Concentration_class_text="Medium",
            Concentration_class_range="20-150",
        ))

        self.assertEqual(record["unit_family"], FAMILY_SEDIMENT)
        self.assertEqual(record["canonical_unit"], "pieces/kg dw")
        self.assertEqual(record["canonical_value"], 54.0)
        self.assertNotIn("m3", record["canonical_unit"])

    def test_unknown_unit_is_excluded_from_aggregation_not_dropped(self):
        record = normalize_noaa_record(_noaa_attrs(Unit="weird unit"))
        self.assertEqual(record["unit_family"], FAMILY_UNKNOWN)
        self.assertIsNone(record["canonical_value"])
        self.assertEqual(record["measured_value"], 0.05)  # native value preserved
        self.assertIn("could not be normalised", record["quality_note"])

    def test_missing_position_rejects_the_record(self):
        self.assertIsNone(normalize_noaa_record(_noaa_attrs(Latitude__degree_=None)))
        self.assertIsNone(normalize_noaa_record(_noaa_attrs(Longitude_degree_=400.0)))

    def test_360_longitude_is_wrapped(self):
        record = normalize_noaa_record(_noaa_attrs(Longitude_degree_=258.0))
        self.assertAlmostEqual(record["longitude"], -102.0, places=5)

    def test_conflict_batch_reports_what_was_rejected(self):
        result = normalize_batch([
            _noaa_attrs(OBJECTID=1),
            _noaa_attrs(OBJECTID=2, Latitude__degree_=None),
        ])
        self.assertEqual(result["kept"], 1)
        self.assertEqual(result["rejected_count"], 1)
        self.assertIn("position", result["rejected"][0]["reason"])

    def test_confidence_penalises_missing_date_and_unknown_unit(self):
        fresh = normalize_noaa_record(_noaa_attrs())
        stale = normalize_noaa_record(_noaa_attrs(Date_m_d_yyyy=None, Unit="weird"))
        self.assertGreater(fresh["confidence_score"], stale["confidence_score"])
        self.assertLessEqual(stale["confidence_score"], 75.0)


class RegionMappingTests(unittest.TestCase):
    REGIONS = [
        {"region_id": 1, "name": "Gulf of Mannar", "latitude": 9.0, "longitude": 78.5},
        {"region_id": 2, "name": "Arabian Sea", "latitude": 18.9, "longitude": 72.0},
    ]

    def test_nearest_region_within_range(self):
        region_id, distance = nearest_region(8.49, 78.13, self.REGIONS)
        self.assertEqual(region_id, 1)
        self.assertLess(distance, 100)

    def test_far_sample_is_unassigned_but_distance_is_still_reported(self):
        region_id, distance = nearest_region(-40.0, 10.0, self.REGIONS, max_km=600)
        self.assertIsNone(region_id)
        self.assertGreater(distance, 600)

    def test_assign_records_marks_each_record(self):
        records = [
            {"latitude": 8.5, "longitude": 78.1},
            {"latitude": -40.0, "longitude": 10.0},
        ]
        result = assign_records(records, self.REGIONS)
        self.assertEqual(result["assigned"], 1)
        self.assertEqual(result["unassigned"], 1)
        self.assertEqual(records[0]["region_id"], 1)
        self.assertIsNone(records[1]["region_id"])


class InterpolationTests(unittest.TestCase):
    SAMPLES = [
        {"latitude": 9.0, "longitude": 78.5, "value": 10.0},
        {"latitude": 9.5, "longitude": 79.0, "value": 20.0},
    ]

    def test_no_sample_in_range_is_a_gap_not_zero(self):
        result = idw_at_point(-30.0, 20.0, self.SAMPLES, radius_km=100)
        self.assertIsNone(result)

    def test_exact_sample_is_not_marked_as_an_estimate(self):
        result = idw_at_point(9.0, 78.5, self.SAMPLES)
        self.assertEqual(result["value"], 10.0)
        self.assertFalse(result["is_estimate"])
        self.assertEqual(result["n_sources"], 1)

    def test_interpolated_value_lies_between_its_sources(self):
        result = idw_at_point(9.25, 78.75, self.SAMPLES, radius_km=100)
        self.assertTrue(result["is_estimate"])
        self.assertGreater(result["value"], 10.0)
        self.assertLess(result["value"], 20.0)

    def test_surface_counts_gaps_explicitly(self):
        surface = build_surface(
            self.SAMPLES,
            {"lat_min": 0.0, "lat_max": 5.0, "lon_min": 0.0, "lon_max": 5.0},
            step_deg=0.5,
        )
        self.assertEqual(surface["nodes"], [])
        self.assertGreater(surface["gap_cells"], 0)
        self.assertIn("never filled with zero", surface["honesty_note"])


class HotspotTests(unittest.TestCase):
    REGIONS = [
        {"region_id": 1, "name": "Gulf of Mannar", "latitude": 9.0, "longitude": 78.5,
         "region_type": "gulf"},
        {"region_id": 2, "name": "Arabian Sea", "latitude": 18.9, "longitude": 72.0,
         "region_type": "sea"},
    ]

    def _record(self, region_id, medium, family, unit, value, ordinal, label,
                days_ago=0, confidence=90.0):
        return {
            "region_id": region_id,
            "region_distance_km": 12.0,
            "latitude": 8.5,
            "longitude": 78.1,
            "timestamp": datetime(2021, 12, 1, tzinfo=timezone.utc)
            - timedelta(days=days_ago),
            "medium": medium,
            "unit_family": family,
            "canonical_value": value,
            "canonical_unit": unit,
            "measured_value": value,
            "measured_unit": unit,
            "published_class": label,
            "severity_ordinal": ordinal,
            "severity_label": label,
            "confidence_score": confidence,
            "origin_status": "REAL",
        }

    def test_grouping_never_merges_different_media(self):
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 0.5, 2, "MEDIUM"),
            self._record(1, MEDIUM_SEDIMENT, FAMILY_SEDIMENT, "pieces/kg dw", 54, 2, "MEDIUM"),
        ]
        groups = group_samples(records)
        self.assertEqual(len(groups), 2)
        self.assertIn((1, MEDIUM_WATER), groups)
        self.assertIn((1, MEDIUM_SEDIMENT), groups)

    def test_unassigned_records_are_excluded(self):
        record = self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 0.5, 2, "MEDIUM")
        record["region_id"] = None
        self.assertEqual(group_samples([record]), {})

    def test_one_high_sample_outranks_many_medium_samples(self):
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 5.0, 3, "HIGH"),
        ] + [
            self._record(2, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 0.5, 2, "MEDIUM")
            for _ in range(10)
        ]
        result = detect_hotspots(records, self.REGIONS)
        top = result["hotspots"][0]
        self.assertEqual(top["region"], "Gulf of Mannar")
        self.assertEqual(top["severity_ordinal"], 3)

    def test_hotspot_carries_its_anomaly_category_and_action(self):
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 5.0, 3, "HIGH"),
        ]
        result = detect_hotspots(records, self.REGIONS)
        hotspot = result["hotspots"][0]

        self.assertEqual(hotspot["anomaly_category"], ANOMALY_CATEGORY)
        self.assertTrue(hotspot["is_hotspot"])
        self.assertEqual(hotspot["action"], "CLEANUP_PRIORITY")
        self.assertEqual(hotspot["unit"], "pieces/m3")
        self.assertIn("priority_components", hotspot)
        self.assertIsNotNone(hotspot["latest_sample_at"])

    def test_severity_reports_the_worst_class_and_the_latest_separately(self):
        """A group can be 'Medium' today while an older sample hit 'Very High'."""
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 0.05, 2, "MEDIUM"),
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 250.0, 4,
                         "Very High", days_ago=900),
        ]
        hotspot = detect_hotspots(records, self.REGIONS)["hotspots"][0]

        self.assertEqual(hotspot["severity_ordinal"], 4)
        self.assertEqual(hotspot["severity"], "critical")
        self.assertEqual(hotspot["published_class"], "Very High")
        self.assertEqual(hotspot["latest_published_class"], "MEDIUM")
        self.assertIn("worst published class", hotspot["severity_basis"])
        self.assertIsNotNone(hotspot["worst_sample_at"])

    def test_below_medium_is_not_a_hotspot(self):
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 0.0001, 0, "VERY_LOW"),
        ]
        result = detect_hotspots(records, self.REGIONS)
        self.assertEqual(result["hotspot_count"], 0)
        self.assertFalse(result["hotspots"][0]["is_hotspot"])

    def test_single_sample_is_flagged_as_a_point_observation(self):
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 5.0, 3, "HIGH"),
        ]
        result = detect_hotspots(records, self.REGIONS)
        basis = " ".join(result["hotspots"][0]["basis"])
        self.assertIn("point observation", basis)

    def test_vintage_is_measured_against_the_collection_not_today(self):
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 5.0, 3, "HIGH"),
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 5.0, 3, "HIGH",
                         days_ago=365),
        ]
        vintage = collection_vintage(records)
        self.assertFalse(vintage["is_live_feed"])
        self.assertIn("not against the current date", vintage["basis"])

    def test_recommendations_are_plain_language_and_ranked(self):
        records = [
            self._record(1, MEDIUM_WATER, FAMILY_WATER, "pieces/m3", 5.0, 3, "HIGH"),
            self._record(2, MEDIUM_SEDIMENT, FAMILY_SEDIMENT, "pieces/kg dw", 25, 2, "MEDIUM"),
        ]
        result = detect_hotspots(records, self.REGIONS)
        recommendations = result["recommendations"]

        self.assertEqual(recommendations["action_count"], 2)
        self.assertIn("Gulf of Mannar", recommendations["actions"][0]["headline"])
        self.assertIn("pieces/m3", recommendations["actions"][0]["detail"])
        self.assertEqual(recommendations["actions"][0]["priority"],
                         max(a["priority"] for a in recommendations["actions"]))

    def test_no_hotspots_promises_nothing(self):
        result = detect_hotspots([], self.REGIONS)
        self.assertEqual(result["hotspot_count"], 0)
        self.assertIn("not a clean bill of health",
                      result["recommendations"]["summary"])


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows

    def count(self):
        return len(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Sample:
    """Stands in for a persisted MicroplasticSample row."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _OverviewSession:
    """Minimal session so the whole scoring path can run with no database."""

    def __init__(self, samples, regions):
        self._samples = samples
        self._regions = regions

    def query(self, model):
        if model.__name__ == "MicroplasticSample":
            return _Rows(self._samples)
        return _Rows(self._regions)


class _RegionRow:
    """Stands in for an OceanLocation, with a real PostGIS zone geometry.

    ``resolve_monitored_regions`` reads the centroid through geoalchemy2, so a
    plain namespace object is not enough - the geometry has to be genuine for
    the mapping layer to be exercised rather than bypassed.
    """

    def __init__(self, id, name, latitude=9.0, longitude=78.5):
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point

        self.id = id
        self.name = name
        self.region_type = "gulf"
        self.country = "India"
        self.geom = from_shape(Point(longitude, latitude).buffer(0.75), srid=4326)


def _persisted_sample(**overrides):
    base = dict(
        id=1, region_id=1, region_distance_km=11.0,
        latitude=8.49, longitude=78.12,
        sampled_at=datetime(2021, 12, 8, tzinfo=timezone.utc),
        medium=MEDIUM_WATER, unit_family=FAMILY_WATER,
        measured_value=0.05, measured_unit="pieces/m3",
        canonical_value=0.05, canonical_unit="pieces/m3",
        published_class="High", published_class_range="1-10",
        severity_label="HIGH", severity_ordinal=3,
        confidence_score=90.0, origin_status="REAL",
        source="NOAA NCEI Marine Microplastics", organization="Test Org",
        doi="10.0000/test", sampling_method="manta trawl",
        quality_note="class published by source",
    )
    base.update(overrides)
    return _Sample(**base)


class EnginePathTests(unittest.TestCase):
    """Run the full compute path with a fake session.

    This is the test that would have caught a module-level NameError in the
    overview builder, which only fires once real rows exist.  It exercises
    every branch of compute_overview, coverage_report and timeline without
    needing a database.
    """

    def setUp(self):
        from app.modules.ai.microplastics import engine
        engine.clear_cache()
        self.engine = engine

    def _session(self, samples=None, regions=None):
        samples = samples if samples is not None else [_persisted_sample()]
        regions = (
            regions if regions is not None
            else [_RegionRow(1, "Gulf of Mannar", latitude=9.0, longitude=78.5)]
        )
        return _OverviewSession(samples, regions)

    def test_empty_dataset_returns_a_reason_not_a_number(self):
        overview = self.engine.compute_overview(self._session(samples=[]))
        self.assertEqual(overview["status"], "NO_DATA")
        self.assertIn("Nothing is drawn", overview["reason"])
        self.assertFalse(overview["coverage"]["has_data"])

    def test_populated_overview_builds_surfaces_and_hotspots(self):
        overview = self.engine.compute_overview(self._session())

        self.assertEqual(overview["status"], "OK")
        self.assertEqual(overview["hotspots"]["hotspot_count"], 1)
        self.assertIn("water_column", overview["surfaces"])

        water = overview["surfaces"]["water_column"]
        self.assertTrue(water["has_data"])
        self.assertEqual(water["unit"], "pieces/m3")
        self.assertGreater(water["sample_count"], 0)
        self.assertTrue(water["nodes"])
        self.assertIn("confidence", water["nodes"][0])

    def test_media_without_data_are_reported_as_gaps(self):
        overview = self.engine.compute_overview(self._session())
        sediment = overview["surfaces"]["sediment_dry_weight"]
        self.assertFalse(sediment["has_data"])
        self.assertIn("No normalised samples", sediment["reason"])

    def test_measurement_discipline_states_the_unit_rule(self):
        overview = self.engine.compute_overview(self._session())
        discipline = overview["measurement_discipline"]
        self.assertIn("never summed", discipline["rule"])
        self.assertIn(FAMILY_WATER, discipline["families"])

    def test_coverage_counts_regions_without_data(self):
        coverage = self.engine.coverage_report(self._session())
        self.assertTrue(coverage["has_data"])
        self.assertEqual(coverage["regions_with_data"], 1)
        self.assertEqual(coverage["total_samples"], 1)
        self.assertIn("data gaps", coverage["honesty_note"])

    def test_coverage_reports_a_reason_when_there_is_nothing(self):
        coverage = self.engine.coverage_report(self._session(samples=[]))
        self.assertFalse(coverage["has_data"])
        self.assertIn("will not estimate any", coverage["reason"])

    def test_timeline_buckets_by_year_and_keeps_units_apart(self):
        samples = [
            _persisted_sample(),
            _persisted_sample(
                id=2, sampled_at=datetime(2019, 6, 1, tzinfo=timezone.utc),
                medium=MEDIUM_SEDIMENT, unit_family=FAMILY_SEDIMENT,
                measured_value=54.0, measured_unit="pieces kg-1 d.w.",
                canonical_value=54.0, canonical_unit="pieces/kg dw",
            ),
        ]
        timeline = self.engine.timeline(self._session(samples=samples))

        self.assertTrue(timeline["has_data"])
        self.assertEqual(timeline["years"], [2019, 2021])
        units = {bucket["unit"] for bucket in timeline["buckets"]}
        self.assertEqual(units, {"pieces/m3", "pieces/kg dw"})
        self.assertIn("yearly", timeline["honesty_note"])

    def test_timeline_without_dates_refuses_to_invent_a_trend(self):
        timeline = self.engine.timeline(
            self._session(samples=[_persisted_sample(sampled_at=None)])
        )
        self.assertFalse(timeline["has_data"])
        self.assertIn("not estimated in its place", timeline["reason"])

    def test_cached_overview_reports_cache_state(self):
        session = self._session()
        first = self.engine.cached_overview(session)
        second = self.engine.cached_overview(session)
        self.assertFalse(first["cache"]["hit"])
        self.assertTrue(second["cache"]["hit"])

    def test_persisted_timestamp_is_normalised_to_utc(self):
        offset = timezone(timedelta(hours=-8))
        sample = _persisted_sample(
            sampled_at=datetime(2021, 12, 7, 16, 0, tzinfo=offset)
        )
        overview = self.engine.compute_overview(self._session(samples=[sample]))
        latest = overview["hotspots"]["data_vintage"]["latest"]
        self.assertTrue(latest.endswith("+00:00"), msg=latest)
        self.assertIn("2021-12-08", latest)


class PersistenceFieldMapTests(unittest.TestCase):
    """Regression guard: a bad field name makes setattr silently do nothing.

    The unified schema names the sample time ``timestamp`` while the column is
    ``sampled_at``.  That mismatch once caused every timestamp to be dropped on
    write without any error being raised - the vintage report noticed, not the
    ORM.  These tests pin the map down.
    """

    def test_every_mapped_target_is_a_real_column(self):
        from app.models.microplastics import MicroplasticSample
        from app.modules.ai.microplastics.engine import _FIELD_MAP

        columns = set(MicroplasticSample.__table__.columns.keys())
        for source_key, column in _FIELD_MAP.items():
            self.assertIn(
                column, columns,
                msg=f"'{source_key}' maps to '{column}', which is not a column",
            )

    def test_sample_time_is_mapped_to_its_column(self):
        from app.modules.ai.microplastics.engine import _FIELD_MAP

        self.assertEqual(_FIELD_MAP["timestamp"], "sampled_at")

    def test_no_mapped_target_is_a_plain_python_name(self):
        """Every target must be settable as a mapped column, not an attribute."""
        from app.models.microplastics import MicroplasticSample
        from app.modules.ai.microplastics.engine import _FIELD_MAP

        instrumented = set(MicroplasticSample.__mapper__.attrs.keys())
        for source_key, column in _FIELD_MAP.items():
            self.assertIn(
                column, instrumented,
                msg=f"'{source_key}' -> '{column}' is not ORM-instrumented",
            )

    def test_persisted_fields_cover_the_scoring_inputs(self):
        """Everything the scorers read back must survive the write."""
        from app.modules.ai.microplastics.engine import _FIELD_MAP

        required = {
            "region_id", "region_distance_km", "latitude", "longitude",
            "timestamp", "medium", "unit_family", "canonical_value",
            "canonical_unit", "severity_ordinal", "severity_label",
            "confidence_score", "origin_status",
        }
        missing = required - set(_FIELD_MAP.keys())
        self.assertEqual(missing, set(), msg=f"not persisted: {sorted(missing)}")


class LiteratureConnectorTests(unittest.TestCase):
    """The curated CSV connector must never invent numbers when it is empty."""

    HEADER = (
        "latitude,longitude,sample_date,medium,unit,value,doi,reference,"
        "location_name,organization,sampling_method,sample_depth_m,country,note"
    )

    def _write(self, directory, content: str) -> str:
        path = os.path.join(directory, "lit.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return path

    def test_missing_file_is_an_error_not_a_clean_ocean(self):
        result = sources.fetch_literature_samples(
            csv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "does-not-exist.csv"),
        )
        self.assertEqual(result.status, "ERROR")
        self.assertFalse(result.found)
        self.assertIn("not found", result.reason)

    def test_header_only_file_reports_an_honest_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self.HEADER + "\n")
            result = sources.fetch_literature_samples(csv_path=path)

        self.assertEqual(result.status, "OK")
        self.assertFalse(result.found)
        self.assertIn("no data rows", result.reason)
        self.assertEqual(result.records, [])

    def test_comments_and_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                "# a header comment\n\n"
                + self.HEADER + "\n"
                + "18.9,72.8,2021-01-01,water,pieces/m3,1.2,10.1/x,Ref A,,Org,,0.5,\n"
                + ",,,,,\n"
                + "# trailing comment\n",
            )
            result = sources.fetch_literature_samples(csv_path=path)

        self.assertTrue(result.found)
        self.assertEqual(len(result.records), 1)

    def test_normalizes_a_curated_water_sample(self):
        record = normalize_literature_record({
            "latitude": "18.9", "longitude": "72.8", "sample_date": "2021-06-01",
            "medium": "water", "unit": "pieces/m3", "value": "4.53",
            "doi": "10.1234/real", "reference": "Author et al. 2021",
            "location_name": "Juhu beach (Mumbai)", "sample_depth_m": "0.5",
        })

        self.assertIsNotNone(record)
        self.assertEqual(record["source"], "Published literature (curated)")
        self.assertEqual(record["origin_status"], "REAL")
        self.assertEqual(record["unit_family"], FAMILY_WATER)
        self.assertEqual(record["canonical_value"], 4.53)
        self.assertEqual(record["timestamp"].year, 2021)
        self.assertEqual(record["doi"], "10.1234/real")
        self.assertEqual(record["source_record_link"], "https://doi.org/10.1234/real")

    def test_liters_per_cubic_metre_are_converted_within_the_family(self):
        record = normalize_literature_record({
            "latitude": "19.0", "longitude": "72.9", "sample_date": "2021-01-01",
            "medium": "water", "unit": "pieces/L", "value": "0.05",
            "doi": "10.1234/real2", "reference": "Ref B",
        })
        self.assertEqual(record["canonical_unit"], "pieces/m3")
        self.assertEqual(record["canonical_value"], 50.0)

    def test_source_record_id_is_stable_across_reingests(self):
        row = {
            "latitude": "18.9", "longitude": "72.8", "sample_date": "2021-06-01",
            "medium": "water", "unit": "pieces/m3", "value": "4.53",
            "doi": "10.1234/real", "reference": "Author et al. 2021",
        }
        first = normalize_literature_record(row)
        second = normalize_literature_record(dict(row))
        self.assertEqual(
            first["source_record_id"], second["source_record_id"]
        )
        self.assertTrue(first["source_record_id"].startswith("lit-"))
        self.assertLessEqual(len(first["source_record_id"]), 64)

    def test_row_without_position_is_rejected_and_reasoned(self):
        self.assertIsNone(normalize_literature_record({
            "latitude": "", "longitude": "72.8", "sample_date": "2021-01-01",
            "medium": "water", "unit": "pieces/m3", "value": "1.0",
            "doi": "10.1234/x", "reference": "Ref C",
        }))
        batch = normalize_literature_batch([{
            "latitude": "", "longitude": "72.8",
            "medium": "water", "unit": "pieces/m3", "value": "1.0",
        }])
        self.assertEqual(batch["kept"], 0)
        self.assertEqual(batch["rejected_count"], 1)
        self.assertIn("position", batch["rejected"][0]["reason"])

    def test_row_without_value_or_unit_is_rejected(self):
        self.assertIsNone(normalize_literature_record({
            "latitude": "18.9", "longitude": "72.8",
            "medium": "water", "unit": "pieces/m3", "value": "",
        }))
        self.assertIsNone(normalize_literature_record({
            "latitude": "18.9", "longitude": "72.8",
            "medium": "water", "value": "1.0",
        }))

    def test_bad_date_keeps_the_row_but_penalises_confidence(self):
        good = normalize_literature_record({
            "latitude": "18.9", "longitude": "72.8", "sample_date": "2021-01-01",
            "medium": "water", "unit": "pieces/m3", "value": "1.0",
            "doi": "10.1234/y",
        })
        bad = normalize_literature_record({
            "latitude": "18.9", "longitude": "72.8", "sample_date": "not-a-date",
            "medium": "water", "unit": "pieces/m3", "value": "1.0",
            "doi": "10.1234/y",
        })
        self.assertIsNotNone(bad)
        self.assertGreater(good["confidence_score"], bad["confidence_score"])

    def test_curated_sediment_rows_with_published_units_resolve_to_the_family(self):
        row = {
            "latitude": "19.10", "longitude": "72.82",
            "medium": "sediment", "unit": "items/kg DW", "value": "9630",
            "doi": "10.1016/j.chemosphere.2021.132484",
            "reference": "Gurjar et al. (2022), Chemosphere 288:132484",
        }
        record = normalize_literature_record(row)
        self.assertEqual(record["unit_family"], FAMILY_SEDIMENT)
        self.assertEqual(record["canonical_unit"], "pieces/kg dw")
        self.assertEqual(record["canonical_value"], 9630.0)
        self.assertEqual(record["severity_label"], "VERY_HIGH")

    def test_items_per_litre_curated_water_row_scales_into_pieces_per_m3(self):
        record = normalize_literature_record({
            "latitude": "19.10", "longitude": "72.82",
            "medium": "water", "unit": "items/L", "value": "372",
            "doi": "10.1016/j.chemosphere.2021.132484",
            "reference": "Gurjar et al. (2022), Chemosphere 288:132484",
        })
        self.assertEqual(record["unit_family"], FAMILY_WATER)
        self.assertEqual(record["canonical_unit"], "pieces/m3")
        self.assertEqual(record["canonical_value"], 372000.0)
        self.assertEqual(record["severity_label"], "HIGH")

    def test_particles_per_kg_curated_row_uses_the_sediment_family(self):
        record = normalize_literature_record({
            "latitude": "19.80", "longitude": "85.83",
            "medium": "sediment", "unit": "particles/kg", "value": "948",
            "doi": "10.3389/frwa.2025.1749269",
            "reference": "Frontiers in Water (2026) 8:1749269",
        })
        self.assertEqual(record["unit_family"], FAMILY_SEDIMENT)
        self.assertEqual(record["canonical_value"], 948.0)
        self.assertEqual(record["severity_label"], "VERY_HIGH")


class ConnectorContractTests(unittest.TestCase):
    """A failed fetch must be distinguishable from a clean ocean."""

    def test_network_failure_returns_error_with_a_reason(self):
        with patch.object(sources.httpx, "Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                httpx.ConnectError("boom")
            )
            result = sources.fetch_noaa_samples()

        self.assertEqual(result.status, "ERROR")
        self.assertFalse(result.found)
        self.assertIn("NOAA", result.reason)
        self.assertEqual(result.records, [])

    def test_empty_response_is_ok_but_found_false_with_a_reason(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"features": []}

        with patch.object(sources.httpx, "Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            result = sources.fetch_noaa_samples()

        self.assertEqual(result.status, "OK")
        self.assertFalse(result.found)
        self.assertIn("data gap", result.reason)

    def test_successful_fetch_reports_records_and_licence(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"features": [{"attributes": _noaa_attrs()}]}

        with patch.object(sources.httpx, "Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            result = sources.fetch_noaa_samples()

        self.assertTrue(result.found)
        self.assertEqual(len(result.records), 1)
        self.assertIn("public domain", result.licence)

    def test_service_error_payload_is_treated_as_a_failure(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"error": {"code": 400, "message": "Invalid field"}}

        with patch.object(sources.httpx, "Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            result = sources.fetch_noaa_samples()

        self.assertEqual(result.status, "ERROR")
        self.assertIn("Invalid field", result.reason)

    def test_nasa_connector_is_honest_without_a_token(self):
        result = sources.fetch_nasa_plastic_signal()
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertFalse(result.found)
        self.assertIn("NASA_EARTHDATA_TOKEN", result.reason)

    def test_status_dict_does_not_leak_the_record_payload(self):
        result = sources.ConnectorResult(
            source="x", status="OK", found=True, records=[{"secret": "payload"}]
        )
        self.assertNotIn("records", result.as_status_dict())
        self.assertEqual(result.as_status_dict()["records_returned"], 1)


class _DerivedCurrentRow:
    """A row shaped like the real DerivedCurrent model.

    Field names here are the derivation pipeline's (`speed`, `direction`,
    `uncertainty_mps`), not the drift module's internal vocabulary.  Guessing
    them wrong raised an AttributeError on the live server, so they are pinned.
    """

    lat = 9.1
    lon = 78.6
    speed = 0.35
    direction = 135.0
    uncertainty_mps = 0.05
    n_vessels = 12
    n_observations = 340
    time_bucket = datetime(2021, 12, 1, tzinfo=timezone.utc)
    method_tag = "DERIVED"
    speed_ms = None  # must NOT be used


class _ModelAwareQuery(_EmptyQuery):
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DerivedOnlySession:
    """No in-situ current observations, but AIS-derived vectors exist."""

    def query(self, model):
        if model.__name__ == "OceanObservation":
            return _ModelAwareQuery([])
        return _ModelAwareQuery([_DerivedCurrentRow()])


class _StaleDerivedSession:
    """Derived row whose `speed_ms` attribute alone is set (the old bug)."""

    def query(self, model):
        if model.__name__ == "OceanObservation":
            return _ModelAwareQuery([])
        row = _DerivedCurrentRow()
        row.speed = None
        return _ModelAwareQuery([row])


class _ThinDerivedSession:
    """A derived vector that exists but is not fit to plan on."""

    def query(self, model):
        if model.__name__ == "OceanObservation":
            return _ModelAwareQuery([])
        row = _DerivedCurrentRow()
        row.speed = 2.05
        row.direction = 0.0
        row.n_vessels = 1
        row.n_observations = 1
        row.uncertainty_mps = 0.0
        row.lat = 10.0
        row.lon = 80.0
        return _ModelAwareQuery([row])


class DriftForcingSourceTests(unittest.TestCase):
    """The AIS-derived forcing path, using the real model's field names."""

    def test_ais_derived_forcing_uses_the_real_column_names(self):
        result = project_drift(_DerivedOnlySession(), region_id=1,
                               latitude=9.0, longitude=78.5, duration_h=48)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["forcing"]["origin_status"], "DERIVED")
        self.assertEqual(result["forcing"]["speed_ms"], 0.35)
        self.assertEqual(result["forcing"]["direction_deg"], 135.0)
        # Trust statistics must travel with the derived vector.
        self.assertEqual(result["forcing"]["n_vessels"], 12)
        self.assertEqual(result["forcing"]["uncertainty_mps"], 0.05)
        self.assertIn("derived_currents", result["forcing"]["source"])

    def test_derived_row_without_a_speed_is_not_used_as_forcing(self):
        result = project_drift(_StaleDerivedSession(), region_id=1,
                               latitude=9.0, longitude=78.5, duration_h=24)
        self.assertEqual(result["status"], "NO_FORCING")

    def test_credible_forcing_is_reported_as_such(self):
        result = project_drift(_DerivedOnlySession(), region_id=1,
                               latitude=9.0, longitude=78.5, duration_h=24)
        self.assertTrue(result["forcing_quality"]["credible"])
        self.assertEqual(result["forcing_quality"]["warnings"], [])
        self.assertEqual(result["confidence"], "LOW")

    def test_implausibly_fast_forcing_is_flagged_and_downgraded(self):
        from app.modules.ai.microplastics.drift import assess_forcing_quality

        quality = assess_forcing_quality({
            "origin_status": "DERIVED", "speed_ms": 2.05, "direction_deg": 0.0,
            "n_vessels": 1, "n_observations": 1, "uncertainty_mps": 0.0,
            "distance_km": 140.0,
        })
        self.assertFalse(quality["credible"])
        joined = " ".join(quality["warnings"])
        self.assertIn("plausibility ceiling", joined)
        self.assertIn("1 vessel(s)", joined)
        self.assertIn("140 km", joined)
        self.assertIn("no positive uncertainty", joined)

    def test_thin_forcing_reaches_the_consumer_downgraded(self):
        """A weak corridor is still drawn, but never looks like a strong one."""
        result = project_drift(_ThinDerivedSession(), region_id=1,
                               latitude=9.0, longitude=78.5, duration_h=72)

        self.assertEqual(result["status"], "OK")
        self.assertFalse(result["forcing_quality"]["credible"])
        self.assertEqual(result["confidence"], "VERY_LOW")
        self.assertIn("not for planning", result["confidence_note"])
        self.assertTrue(any("vessel" in item for item in result["limitations"]))

    def test_derived_observations_are_normalised_to_utc(self):
        result = project_drift(_DerivedOnlySession(), region_id=1,
                               latitude=9.0, longitude=78.5, duration_h=24)
        self.assertTrue(result["forcing"]["observed_at"].endswith("+00:00"))


class DriftTests(unittest.TestCase):
    def test_no_forcing_produces_no_trajectory_and_says_why(self):
        result = project_drift(_EmptySession(), region_id=1,
                               latitude=9.0, longitude=78.5, duration_h=48)

        self.assertEqual(result["status"], "NO_FORCING")
        self.assertEqual(result["trajectory"], [])
        self.assertIn("absence of data, not still water", result["reason"])
        self.assertTrue(result["checked_sources"])
        self.assertTrue(result["limitations"])

    def test_real_forcing_produces_a_bounded_corridor(self):
        result = project_drift(_ForcingSession(), region_id=1,
                               latitude=9.0, longitude=78.5, duration_h=24)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(len(result["trajectory"]), 25)
        self.assertEqual(len(result["corridor"]), 50)
        self.assertEqual(result["forcing"]["origin_status"], "REAL")
        self.assertEqual(result["confidence"], "LOW")
        self.assertIn("not a forecast", result["confidence_note"])

    def test_duration_is_clamped_to_the_supported_window(self):
        short = project_drift(_ForcingSession(), region_id=1, latitude=9.0,
                              longitude=78.5, duration_h=1)
        long = project_drift(_ForcingSession(), region_id=1, latitude=9.0,
                             longitude=78.5, duration_h=999)
        self.assertEqual(short["duration_h"], 6)
        self.assertEqual(long["duration_h"], 72)

    def test_drift_is_deterministic_for_the_same_input(self):
        first = project_drift(_ForcingSession(), region_id=1, latitude=9.0,
                              longitude=78.5, duration_h=24)
        second = project_drift(_ForcingSession(), region_id=1, latitude=9.0,
                               longitude=78.5, duration_h=24)
        self.assertEqual(first["end_point"], second["end_point"])


if __name__ == "__main__":
    unittest.main()
