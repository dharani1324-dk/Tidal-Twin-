"""
OceanVerse AI - Pydantic Schemas
================================
These define the "shape" of data sent/received by the API.
They validate incoming data and shape outgoing JSON.
"""

from pydantic import BaseModel
from datetime import datetime


class OceanLocationBase(BaseModel):
    name: str
    region_type: str = "sea"
    country: str | None = None


class OceanLocationCreate(OceanLocationBase):
    latitude: float
    longitude: float


class OceanLocationOut(OceanLocationBase):
    id: int
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ObservationOut(BaseModel):
    id: int
    location_id: int
    timestamp: datetime
    sea_surface_temperature: float | None = None
    wave_height: float | None = None
    salinity: float | None = None
    current_speed: float | None = None
    source: str | None = None
    data_type: str

    class Config:
        from_attributes = True
