"""
OceanVerse AI - AIS Track & Derived Current Models
===================================================
The "ships as sensors" pipeline. Two additive tables:

`ais_tracks`
    One row per vessel position report received from an AIS source.
    Vessel identifiers are hashed before storage (no raw MMSI/ship
    identity is kept). SOG/COG are the vessel's ground motion as
    reported by its transponder.

`derived_currents`
    One row per grid cell + time bucket. `u`/`v` are the east/north
    components of the ocean surface current ESTIMATED from the robust
    statistics of vessel motion in that cell. Low-count cells store NO
    row (we never guess). Every row is tagged `DERIVED` and points to
    a provenance batch.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from geoalchemy2 import Geometry

from app.core.database import Base


class AisTrack(Base):
    __tablename__ = "ais_tracks"

    id = Column(Integer, primary_key=True, index=True)

    # Hashed vessel identifier (e.g. sha256 of MMSI) - never the raw id
    vessel_hash = Column(String(64), nullable=False, index=True)

    # When the position was broadcast
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Position as PostGIS point (lon/lat, SRID 4326)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)

    # Reported ground motion
    sog_mps = Column(Float, nullable=True)    # speed over ground, m/s
    cog_deg = Column(Float, nullable=True)    # course over ground, degrees true

    # Which ingestion stream this came from: "gfw", "marine_cadastre", "demo"
    source = Column(String(30), nullable=False, default="gfw")

    # Method tag for provenance
    method_tag = Column(String(20), nullable=False, default="OBSERVED")

    # Provenance batch reference
    provenance_id = Column(Integer, ForeignKey("provenance_register.id"), nullable=True)

    # Extra JSON (e.g. raw source-specific fields, QC flags)
    extra = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AisTrack id={self.id} vessel={self.vessel_hash[:10]} ts={self.timestamp}>"


class DerivedCurrent(Base):
    __tablename__ = "derived_currents"

    id = Column(Integer, primary_key=True, index=True)

    # Grid cell represented by its centre point
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    # Nominal cell size in degrees (grid we snapped to)
    cell_deg = Column(Float, nullable=False, default=0.25)

    # Time bucket start (all tracks within one bucket snap here)
    time_bucket = Column(DateTime(timezone=True), nullable=False, index=True)

    # Estimated surface current vector (east, north), m/s
    u = Column(Float, nullable=False)
    v = Column(Float, nullable=False)

    # Derived speed (magnitude, m/s) and direction (degrees true)
    speed = Column(Float, nullable=False)
    direction = Column(Float, nullable=False)

    # Honesty statistics
    n_vessels = Column(Integer, nullable=False, default=0)  # distinct vessels in cell
    n_observations = Column(Integer, nullable=False, default=0)  # total position reports
    uncertainty_mps = Column(Float, nullable=False, default=-1.0)  # robust spread + sample size

    # Provenance
    method_tag = Column(String(20), nullable=False, default="DERIVED")
    provenance_id = Column(Integer, ForeignKey("provenance_register.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<DerivedCurrent id={self.id} ({self.lat:.2f},{self.lon:.2f}) {self.time_bucket}>"