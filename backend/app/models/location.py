"""
OceanVerse AI - Ocean Location Model
====================================
Represents a named ocean region (e.g. "Arabian Sea", "Bay of Bengal",
or a specific coastal point near a city).

Uses PostGIS geometry so each location can be a point, or a polygon zone.
"""

from sqlalchemy import Column, Integer, String, DateTime, func
from geoalchemy2 import Geometry

from app.core.database import Base


class OceanLocation(Base):
    __tablename__ = "ocean_locations"

    id = Column(Integer, primary_key=True, index=True)

    # Human-friendly name of the region
    name = Column(String(200), nullable=False)

    # Type: 'sea', 'bay', 'coastal', 'port', 'reef'
    region_type = Column(String(50), nullable=False, default="sea")

    # Country / state / territory (useful for India-focused app)
    country = Column(String(100), nullable=True)

    # Geographic zone stored as PostGIS geometry
    # SRID 4326 = standard GPS coordinate system (latitude/longitude)
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<OceanLocation id={self.id} name={self.name!r}>"
