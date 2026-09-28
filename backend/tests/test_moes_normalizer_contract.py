import pytest
from pydantic import ValidationError

from app.schemas.moes import UnifiedOceanRecord
from app.services.moes_normalizer import normalize_indobis_occurrences


def _record(**overrides):
    fields = {
        "record_id": "r1", "source_id": "INCOIS", "institution": "Provider",
        "dataset_id": "d1", "dataset_name": "Dataset", "category": "forecast",
        "variable": "temperature", "value": 25.2, "units": "degC",
        "observed_at": "2026-09-28T10:00:00+05:30",
        "retrieved_at": "2026-09-28T10:30:00Z", "latitude": 10,
        "longitude": 80, "depth_m": 0, "data_status": "FORECAST",
        "quality_status": "RANGE_SCREENED", "source_url": "https://example.org",
    }
    return UnifiedOceanRecord(**(fields | overrides))


def test_record_timestamps_are_normalized_to_utc():
    record = _record()
    assert record.observed_at == "2026-09-28T04:30:00Z"
    assert record.retrieved_at == "2026-09-28T10:30:00Z"


@pytest.mark.parametrize("field,value", [
    ("latitude", 90.1), ("longitude", -181), ("depth_m", -0.1),
    ("value", float("nan")), ("value", float("inf")),
    ("observed_at", "2026-09-28T10:00:00"),
    ("retrieved_at", "not-a-timestamp"),
])
def test_record_rejects_out_of_contract_values(field, value):
    with pytest.raises(ValidationError):
        _record(**{field: value})


@pytest.mark.parametrize("raw_date", ["2008/2010", "1846", "2024-07-03"])
def test_occurrence_date_precision_is_preserved_without_fabricating_instant(raw_date):
    records = normalize_indobis_occurrences({
        "available": True,
        "checked_at": "2026-09-28T10:30:00Z",
        "records": [{"id": "x", "event_date": raw_date, "latitude": 10, "longitude": 80}],
    })
    assert records[0]["observed_at"] is None
    assert records[0]["attributes"]["event_date"] == raw_date


def test_occurrence_timestamp_is_normalized_when_provider_supplies_an_instant():
    records = normalize_indobis_occurrences({
        "available": True,
        "checked_at": "2026-09-28T10:30:00Z",
        "records": [{"id": "x", "event_date": "2024-07-03T12:00:00+05:30", "latitude": 10, "longitude": 80}],
    })
    assert records[0]["observed_at"] == "2024-07-03T06:30:00Z"
