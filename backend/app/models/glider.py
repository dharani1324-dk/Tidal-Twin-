"""
TidalTwin - Glider Profile Model (feature #16), with BGC fields (feature #17)
================================================================================
Represents ONE measurement sample from a real ocean glider deployment.

Underwater gliders sample the water column continuously along a trajectory,
measuring temperature, salinity, pressure and — on gliders carrying
biogeochemical (BGC) sensors — dissolved oxygen, chlorophyll fluorescence and
nitrate (features #16 Glider + #17 CTD/BGC).

Only real in-situ values are stored per row; a sensor that was not carried on
a deployment (or a QC-flagged sample) stays NULL, and the UI shows
"Data unavailable". Nothing is simulated or interpolated here.
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.core.database import Base


class GliderProfile(Base):
    __tablename__ = "glider_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Deployment identifier from the source NetCDF (GliderDAC trajectory/deployment name)
    deployment_id = Column(String(120), nullable=False, index=True)
    instrument = Column(String(60), nullable=True)  # e.g. "SLOCUM", "SEAGLIDER", "SPRAY"

    # Where this sample was taken (the glider position at that measurement)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    # When the sample was taken
    time = Column(DateTime(timezone=True), nullable=False, index=True)

    # Depth of this sample in metres (pressure in dbar ~ 1 m, as in Argo)
    depth_m = Column(Float, nullable=False, index=True)

    # Physical fields (NULL = not measured / QC-flagged in the source file)
    temperature = Column(Float, nullable=True)  # degrees Celsius
    salinity = Column(Float, nullable=True)     # PSU (practical salinity units)
    pressure = Column(Float, nullable=True)     # decibars (dbar)

    # Biogeochemical fields (feature #17) — optional sensors on the payload
    dissolved_oxygen = Column(Float, nullable=True)   # mol m-3 (or raw sensor units from file)
    chlorophyll = Column(Float, nullable=True)        # mg m-3 chlorophyll fluorescence proxy
    nitrate = Column(Float, nullable=True)            # mmol m-3

    # CF/ACDD metadata carried from the source file for provenance & humility
    qc_flags = Column(String(60), nullable=True)      # summary QC flag of the sample
    source_file = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<GliderProfile id={self.id} deployment={self.deployment_id} depth={self.depth_m:.0f}m>"