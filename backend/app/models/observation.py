"""
OceanVerse AI - Ocean Observation Model
=======================================
Represents a single measurement of ocean conditions at a time and place.

This is the "heart" of the data — holds temperature, wave height,
salinity, and current readings gathered from public ocean APIs
(satellites / buoys).
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class OceanObservation(Base):
    __tablename__ = "ocean_observations"

    id = Column(Integer, primary_key=True, index=True)

    # Which location (region) this observation belongs to
    location_id = Column(
        Integer, ForeignKey("ocean_locations.id"), nullable=False, index=True
    )

    # When the measurement was taken
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # The actual measured values
    sea_surface_temperature = Column(Float, nullable=True)  # degrees Celsius
    wave_height = Column(Float, nullable=True)              # meters
    wave_direction = Column(Float, nullable=True)           # degrees
    salinity = Column(Float, nullable=True)                 # PSU (practical salinity units)
    current_speed = Column(Float, nullable=True)            # m/s
    current_direction = Column(Float, nullable=True)        # degrees

    # What source this data came from (e.g. "NOAA", "Copernicus", "model")
    source = Column(String(100), nullable=True)

    # Data type: real observation vs model output
    data_type = Column(String(20), nullable=False, default="observation")

    # Extra JSON for any other keys we don't model explicitly
    extra = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to the location
    location = relationship("OceanLocation", backref="observations")

    def __repr__(self):
        return f"<OceanObservation id={self.id} loc={self.location_id} temp={self.sea_surface_temperature}>"
