"""
TidalTwin - CTD Cast Model (feature #17)
==========================================
Represents ONE sample of a real ship CTD / moored mini-CTD cast.

CTD (conductivity–temperature–depth) instruments measure a vertical profile of
temperature and salinity down a water column; BGC-capable CTD payloads also
carry dissolved oxygen and chlorophyll sensors. Casts are the shipboard,
station-based companions to Argo floats and underwater gliders.

Honesty identical to the glider model: only real in-situ values are stored per
row; a sensor that was not carried (or a QC-flagged sample) stays NULL and the
UI shows "Data unavailable". Nothing is simulated or interpolated here.
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.core.database import Base


class CtdProfile(Base):
    __tablename__ = "ctd_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Station identifier from the source file / cruise name
    station_id = Column(String(120), nullable=False, index=True)
    instrument = Column(String(60), nullable=True)  # e.g. "SHIP-CTD", "MOORED-MINI-CTD"

    # Where the cast was taken
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # When the sample was taken
    time = Column(DateTime(timezone=True), nullable=False, index=True)

    # Depth of this sample in metres (~ dbar for CTD)
    depth_m = Column(Float, nullable=False, index=True)

    # Physical fields (NULL = not measured / QC-flagged in the source file)
    temperature = Column(Float, nullable=True)  # degrees Celsius
    salinity = Column(Float, nullable=True)     # PSU
    pressure = Column(Float, nullable=True)     # decibars

    # Biogeochemical fields (feature #17) — optional sensors on the payload
    dissolved_oxygen = Column(Float, nullable=True)   # mol m-3
    chlorophyll = Column(Float, nullable=True)        # mg m-3 fluorescence proxy
    nitrate = Column(Float, nullable=True)            # mmol m-3

    # Provenance & humility
    qc_flags = Column(String(60), nullable=True)
    source_file = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<CtdProfile id={self.id} station={self.station_id} depth={self.depth_m:.0f}m>"