"""Normalized records emitted by public MoES source adapters."""

from pydantic import BaseModel, ConfigDict, Field


class UnifiedOceanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    latitude: float | None
    longitude: float | None
    depth_m: float | None = None
    data_status: str
    quality_status: str
    quality_flags: list[str] = Field(default_factory=list)
    attributes: dict[str, str | None] = Field(default_factory=dict)
    source_url: str
    attribution: str | None = None
    license: str | None = None
