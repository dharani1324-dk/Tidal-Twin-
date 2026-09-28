"""
TidalTwin - Ocean Observation Model
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
    depth_m = Column(Float, nullable=True, default=0.0)     # meters below surface

    # Bio-physical profile variables (v2 feature foundation)
    dissolved_oxygen = Column(Float, nullable=True)         # mg/L
    chlorophyll = Column(Float, nullable=True)              # mg/m3
    ph = Column(Float, nullable=True)                       # pH units
    pressure = Column(Float, nullable=True)                 # dbar
    density = Column(Float, nullable=True)                  # kg/m3
    nutrients = Column(Float, nullable=True)                # nitrate equivalent µmol/L

    # What source this data came from (e.g. "NOAA", "Copernicus", "model")
    source = Column(String(100), nullable=True)

    # Data type: real observation vs model output
    data_type = Column(String(20), nullable=False, default="observation")

    # ---------------------------------------------------------------------
    # National ocean observation (MoES / INCOIS) metadata.
    #
    # These columns are additive and nullable, so every pre-existing row keeps
    # working unchanged and nothing that already exists is re-labelled.  They
    # exist because one `source` string cannot carry the information the
    # platform needs to be honest about an observation: which named dataset it
    # came from, what produced it, how it was processed, and what its own
    # quality documentation says.
    # ---------------------------------------------------------------------

    # Registry id of the declared source (app.modules.ai.observations.registry).
    source_id = Column(String(80), nullable=True, index=True)

    # The platform that produced the measurement: Argo WMO number, buoy id,
    # satellite, or the analysis grid cell.  This is the difference between "a
    # measurement somewhere" and "a measurement by a known instrument".
    platform_id = Column(String(120), nullable=True, index=True)
    instrument_id = Column(String(120), nullable=True)

    # Origin of the VALUES, reusing app.modules.ai.provenance_quality vocabulary:
    # REAL | HISTORICAL | MODEL_DERIVED | SATELLITE_DERIVED | SIMULATED |
    # SYNTHETIC | UNKNOWN.  An objective analysis of real floats is
    # MODEL_DERIVED, never REAL.
    data_status = Column(String(20), nullable=True, index=True)

    # Provider-supplied quality statement for the stored value, e.g. an Argo
    # reference-table-2 flag ('1' good, '2' probably good) or a composite such
    # as "DERIVED_FIELD_ESTIMATED".
    quality_flag = Column(String(30), nullable=True)

    # How far the value is from the raw measurement, e.g. REAL_TIME,
    # DELAYED_MODE_ADJUSTED, L2B_RETRIEVAL, ANALYSIS.
    processing_level = Column(String(40), nullable=True)

    # When TidalTwin fetched it.  Distinct from `timestamp`, which is when the
    # measurement was made: a re-ingestion must not look like new evidence.
    retrieval_time = Column(DateTime(timezone=True), nullable=True)

    # Where the exact value can be reproduced: dataset id, request, platform id,
    # cycle, and time.  Without this, a number in this table is unfalsifiable.
    source_reference = Column(String(500), nullable=True)

    # Per-variable provider QC flags and published uncertainty, as JSON text.
    qc_flags = Column(String, nullable=True)
    uncertainty = Column(String, nullable=True)

    # Validation issues raised at ingest time.  Flagged rows are stored; this
    # column is why a reviewer can see that a row was stored with a warning.
    validation_flags = Column(String, nullable=True)

    # Stable identity of a physical sample, used to make ingestion resumable
    # and idempotent.  Unique, and NULL for legacy rows.
    observation_uid = Column(String(200), nullable=True, unique=True)

    # Extra JSON for any other keys we don't model explicitly
    extra = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to the location
    location = relationship("OceanLocation", backref="observations")

    def __repr__(self):
        return f"<OceanObservation id={self.id} loc={self.location_id} temp={self.sea_surface_temperature}>"
