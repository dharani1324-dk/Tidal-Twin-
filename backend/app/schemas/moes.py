"""Normalized records emitted by public MoES source adapters."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UnifiedOceanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    record_id: str
    source_id: str
    institution: str
    dataset_id: str
    dataset_name: str
    category: str
    variable: str
    value: float | str | None
    units: str | None
    observed_at: str | None
    retrieved_at: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    depth_m: float | None = Field(default=None, ge=0)
    data_status: str
    quality_status: str
    quality_flags: list[str] = Field(default_factory=list)
    attributes: dict[str, str | None] = Field(default_factory=dict)
    source_url: str
    attribution: str | None = None
    license: str | None = None

    @field_validator("observed_at", "retrieved_at")
    @classmethod
    def require_utc_timestamp(cls, value: str | None, info):
        if value is None and info.field_name == "observed_at":
            return value
        if not value or "T" not in value:
            raise ValueError("timestamps must be ISO-8601 datetimes with a timezone")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be a valid ISO-8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
