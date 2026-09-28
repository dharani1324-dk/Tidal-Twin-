"""
TidalTwin - Microplastic Sample Model
=========================================
One row = one published microplastic measurement from an open dataset
(currently NOAA NCEI's global Marine Microplastics collection).

HONESTY CONTRACT
----------------
Microplastics are reported in *incompatible units depending on the medium*:
water-column trawls give `pieces/m3`, sediment grabs give `pieces/kg dw`,
nurdle beach patrols give `pieces/10 min`.  A value of 54 is ``Medium`` in
sediment but far off the top of the water-column ladder, so the two can never
be averaged, ranked against each other, or drawn on one colour ramp.

We therefore keep BOTH of these, always:
  * ``measured_value`` / ``measured_unit``  - exactly what the source published
  * ``canonical_value`` / ``canonical_unit`` - converted *within its own family*
    only, with ``unit_family`` naming that family.

``unit_family`` is the grouping key for every aggregate in this module.  If it
is ``unknown``, the row is stored but deliberately excluded from scoring.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class MicroplasticSample(Base):
    __tablename__ = "microplastic_samples"
    __table_args__ = (
        # One published record is ingested at most once, even across re-runs.
        UniqueConstraint("source", "source_record_id", name="uq_microplastic_source_record"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # The monitored coastal region this sample was mapped to. NULLABLE on
    # purpose: a sample further than the mapping radius from every region is
    # stored unassigned rather than snapped to the nearest coast.
    region_id = Column(
        Integer, ForeignKey("ocean_locations.id"), nullable=True, index=True
    )
    # Great-circle distance to that region's centroid, so the strength of the
    # mapping is visible instead of implied.
    region_distance_km = Column(Float, nullable=True)

    # ---- provenance -----------------------------------------------------
    source = Column(String(120), nullable=False, index=True)
    source_dataset = Column(String(200), nullable=True)
    source_record_id = Column(String(64), nullable=False)
    source_record_link = Column(String(300), nullable=True)
    organization = Column(String(200), nullable=True)
    reference = Column(String(400), nullable=True)
    doi = Column(String(160), nullable=True)

    # ---- position + time -------------------------------------------------
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    sampled_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # ---- what was measured ----------------------------------------------
    # "water" | "sediment" | "beach" | "beach_nurdle" | "unknown"
    medium = Column(String(32), nullable=False, default="unknown", index=True)
    # "water_column" | "sediment_dry_weight" | "nurdle_patrol_time" | "unknown"
    unit_family = Column(String(40), nullable=False, default="unknown", index=True)

    measured_value = Column(Float, nullable=True)
    measured_unit = Column(String(40), nullable=True)

    canonical_value = Column(Float, nullable=True)
    canonical_unit = Column(String(40), nullable=True)

    sampling_method = Column(String(120), nullable=True)
    mesh_size_mm = Column(Float, nullable=True)
    water_depth_m = Column(Float, nullable=True)
    sample_depth_m = Column(Float, nullable=True)

    # ---- severity, as published by the source ---------------------------
    # We do NOT invent thresholds: the source ships its own per-unit class
    # ladder, and we carry it through verbatim.
    published_class = Column(String(32), nullable=True)
    published_class_range = Column(String(40), nullable=True)
    severity_label = Column(String(32), nullable=True, index=True)
    severity_ordinal = Column(Integer, nullable=True)

    # ---- trust -----------------------------------------------------------
    confidence_score = Column(Float, nullable=True)
    # REAL | SATELLITE_DERIVED | MODEL_DERIVED | INTERPOLATED | UNKNOWN
    origin_status = Column(String(32), nullable=False, default="UNKNOWN", index=True)
    quality_note = Column(Text, nullable=True)

    extra = Column(Text, nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    region = relationship("OceanLocation", backref="microplastic_samples")

    def __repr__(self):
        return (
            f"<MicroplasticSample id={self.id} region={self.region_id} "
            f"{self.measured_value}{self.measured_unit}>"
        )
