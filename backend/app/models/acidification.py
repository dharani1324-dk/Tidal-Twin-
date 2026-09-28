"""
TidalTwin - Ocean Acidification Sample Model
=============================================
Persists real ocean carbonate-system observations, principally in-situ total
pH measured by BGC-Argo pH sensors, joined to the 8 monitored coastal regions.

WHY A SEPARATE TABLE RATHER THAN REUSING dissolved_oxygen_samples
----------------------------------------------------------------
Both modules draw on the same BGC-Argo float profiles, but the measured
quantity, the plausible range and the severity ladder are all different, and
oxygen already owns its own calibrated thresholds.  Sharing a table would mean
a single row could carry a "not applicable" pH column, and a pH row could be
picked up by the oxygen zone grid.  Separate tables keep each module's
invariants airtight, at the cost of a little duplicated provenance columns -
which is the same trade the deoxygenation module made for microplastics.

MEASURED VS DERIVED
-------------------
``ph_total`` is always a real measurement.  ``omega_arag`` is NOT: it is
derived from the measured pH plus measured temperature and salinity via
CO2SYS, assuming total alkalinity from a published salinity relation (see
``app/modules/ai/acidification/carbonate.py``).  The two are stored in
different columns and flagged separately so no consumer can mistake a derived
saturation state for a measured one.  ``omega_arag_derived`` says which.
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


class OceanAcidificationSample(Base):
    """One measured in-situ pH observation, with its depth and provenance."""

    __tablename__ = "acidification_samples"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_acid_source_record"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Region assignment (nullable - samples beyond the mapping radius stay
    # unassigned rather than being snapped to a distant coast).
    region_id = Column(Integer, ForeignKey("ocean_locations.id"), nullable=True, index=True)
    region_distance_km = Column(Float, nullable=True)

    # ---- Provenance -------------------------------------------------------
    source = Column(String(120), nullable=False, index=True)
    source_dataset = Column(String(200), nullable=True)
    source_record_id = Column(String(64), nullable=False)
    source_record_link = Column(String(300), nullable=True)
    organization = Column(String(200), nullable=True)
    reference = Column(String(400), nullable=True)
    doi = Column(String(160), nullable=True)

    # ---- Float identity ---------------------------------------------------
    float_id = Column(String(40), nullable=True, index=True)
    cycle = Column(Integer, nullable=True)
    source_file = Column(String(300), nullable=True, index=True)

    # ---- Position and time ------------------------------------------------
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    sampled_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # ---- The measurement (always measured, never derived) -----------------
    # In-situ pH on the TOTAL scale, which is the scale BGC-Argo pH sensors
    # report and the scale every threshold in this module is defined on.
    ph_total = Column(Float, nullable=False)

    # Free-scale pH, reported alongside when the float publishes both. Never
    # mixed with ph_total by the severity classifier.
    ph_free = Column(Float, nullable=True)

    # ---- Derived carbonate chemistry (explicitly NOT measured) ------------
    # Aragonite saturation state. DERIVED - see carbonate.py for the method and
    # its stated uncertainty. NULL whenever temperature or salinity was absent.
    omega_arag = Column(Float, nullable=True)
    omega_calc = Column(Float, nullable=True)
    omega_arag_derived = Column(Integer, nullable=True)  # 1 when omega_arag is a CO2SYS estimate
    dic_umol_kg = Column(Float, nullable=True)           # derived, for the Revelle/debug view
    pco2_uatm = Column(Float, nullable=True)             # derived
    alk_umol_kg = Column(Float, nullable=True)           # the TA actually assumed

    # ---- Depth and co-located physics ------------------------------------
    # These are not decoration: carbonate equilibria are strongly temperature
    # dependent, so a missing temperature means aragonite cannot be derived at
    # all rather than being filled with a climatological guess.
    depth_m = Column(Float, nullable=False)
    temperature_c = Column(Float, nullable=True)
    salinity_psu = Column(Float, nullable=True)
    pressure_dbar = Column(Float, nullable=True)

    # ---- Classification ---------------------------------------------------
    severity_label = Column(String(32), nullable=True, index=True)
    severity_ordinal = Column(Integer, nullable=True)
    is_acidic = Column(Integer, nullable=True)          # pH below the LOW threshold
    is_undersaturated = Column(Integer, nullable=True)  # omega_arag < 1.0

    # ---- Trust ------------------------------------------------------------
    confidence_score = Column(Float, nullable=True)
    origin_status = Column(String(32), nullable=False, default="REAL", index=True)
    qc_flag = Column(String(8), nullable=True)
    quality_note = Column(Text, nullable=True)

    extra = Column(Text, nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    region = relationship("OceanLocation", backref="acidification_samples")

    def __repr__(self):
        return (
            f"<OceanAcidificationSample id={self.id} ph={self.ph_total} "
            f"omega={self.omega_arag} region={self.region_id}>"
        )
