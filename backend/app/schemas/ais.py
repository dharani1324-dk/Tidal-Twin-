"""
OceanVerse AI - AIS / Derived-Current Pydantic Schemas
======================================================
Shapes for the Phase-1 (SIH26067 "ships as sensors") endpoints.

Every derived-current response carries:
  * the robust estimate (u, v, speed, direction)
  * the HONESTY statistics (n_vessels, n_observations, uncertainty_mps)
  * method_tag ("DERIVED") + provenance_id so the number can always be
    traced back to the batch of real vessel tracks that produced it.

A cell that does not meet the minimum vessel-count is NOT returned by
the API at all ("no data"), never filled with a guess.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DerivedCurrentBeforeOut(BaseModel):
    """Reserved; before any derivation runs, the API reports no data."""

    model_config = ConfigDict(from_attributes=True)


class DerivedCurrentOut(BaseModel):
    """One robust surface-current vector for a grid cell + time bucket."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    lat: float
    lon: float
    cell_deg: float
    time_bucket: datetime
    u: float
    v: float
    speed: float
    direction: float
    n_vessels: int
    n_observations: int
    uncertainty_mps: float
    method_tag: str
    provenance_id: int | None = None


class CurrentsGridOut(BaseModel):
    """Grid response: real vectors + an honest summary of coverage."""

    model_config = ConfigDict(from_attributes=True)

    bbox: dict
    generated_at: datetime
    cells_with_data: int
    cells_scanned: int
    currents: list[DerivedCurrentOut]
    honesty_note: str = (
        "Only cells meeting the minimum real-vessel count are returned. "
        "Cells with too few vessels are absent (no data), never guessed."
    )
