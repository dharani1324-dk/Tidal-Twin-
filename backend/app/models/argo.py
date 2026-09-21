"""
TidalTwin - Argo Profile Model
=================================
Represents ONE measurement level inside a real Argo float profile.

Argo floats drift through the open ocean and measure temperature & salinity
as they sink and rise.  Each profile file contains a vertical column of
measurements (pressure increasing with depth).  When we ingest one file, we
unpack it into rows — one per depth level.

Only real, in-situ values are stored: a missing temperature or salinity for a
level stays NULL and the UI shows "Data unavailable".
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.core.database import Base


class ArgoProfile(Base):
    __tablename__ = "argo_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # The float that took this measurement (WMO id, e.g. "2902936")
    float_id = Column(String(20), nullable=False, index=True)

    # Where the profile was taken (the float's position at that cycle)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # When the profile was taken
    time = Column(DateTime(timezone=True), nullable=False, index=True)

    # Depth of this level in metres (derived from pressure: 1 dbar ~ 1 m)
    depth_m = Column(Float, nullable=False, index=True)

    # The actual measured values (NULL = not available in the source file)
    temperature = Column(Float, nullable=True)  # degrees Celsius
    salinity = Column(Float, nullable=True)     # PSU (practical salinity units)
    pressure = Column(Float, nullable=True)     # decibars (dbar)

    # Which NetCDF file this row came from (provenance / data honesty)
    source_file = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ArgoProfile id={self.id} float={self.float_id} depth={self.depth_m:.0f}m>"