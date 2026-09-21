"""
TidalTwin - Argo Pydantic Schemas
====================================
Shapes of the data the Argo API sends/receives.
"""

from datetime import datetime

from pydantic import BaseModel


class ArgoFloatOut(BaseModel):
    """One real Argo float, with its latest known profile summary."""

    float_id: str
    latest_time: datetime
    latitude: float | None = None
    longitude: float | None = None
    depth_min_m: float | None = None
    depth_max_m: float | None = None
    levels: int = 0


class ArgoProfileLevel(BaseModel):
    depth_m: float
    temperature: float | None = None
    salinity: float | None = None
    pressure: float | None = None


class ArgoProfileOut(BaseModel):
    """One vertical profile (one cycle) of a float, depth-sorted."""

    float_id: str
    time: datetime
    latitude: float | None = None
    longitude: float | None = None
    levels: list[ArgoProfileLevel]

    class Config:
        from_attributes = True