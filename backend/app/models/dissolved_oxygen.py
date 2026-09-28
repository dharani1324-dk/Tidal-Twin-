"""
TidalTwin - Dissolved Oxygen Sample Model
=============================================
One row = one dissolved-oxygen measurement from a real Argo profiling-float
profile (BGC floats report ``DOXY``).  Only genuinely measured values are
stored - an unreachable GDAC produces an honest UNAVAILABLE, never an estimate.

UNITS
-----
Argo floats publish oxygen as ``DOXY`` in ``umol/kg`` (micromoles of O2 per
kilogram of seawater) and that is our canonical unit, stored verbatim.  We also
store ``do_mg_l`` - the classic oceanographer's concentration in milligrammes
of O2 per litre - derived with the standard factor:

    1 umol O2/kg = 32e-6 g O2/kg ~ 0.032 mg O2/L   (density ~ 1 kg/L)

The derivation is labelled approximate because it assumes seawater density of
about 1 kg/L; the canonical ``do_umol_kg`` is never transformed before storage.

SEVERITY
--------
Hypoxia is conventionally defined as dissolved oxygen below ~2 mg/L
(~62.5 umol/kg), with values below ~0.5 mg/L (~15.6 umol/kg) considered
near-anoxic.  Our severity ladder around those thresholds is a *policy*
classifier and says so in its documentation.
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


class DissolvedOxygenSample(Base):
    __tablename__ = "dissolved_oxygen_samples"
    __table_args__ = (
        # One measured oxygen level is ingested at most once, even across
        # re-runs of the same per-cycle Argo profile file.
        UniqueConstraint("source", "source_record_id", name="uq_do_source_record"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # The monitored coastal region this sample was mapped to. NULLABLE on
    # purpose: a float profile further than the mapping radius from every
    # region is stored unassigned rather than snapped to the nearest coast.
    region_id = Column(
        Integer, ForeignKey("ocean_locations.id"), nullable=True, index=True
    )
    region_distance_km = Column(Float, nullable=True)

    # ---- provenance -----------------------------------------------------
    source = Column(String(120), nullable=False, index=True)
    source_dataset = Column(String(200), nullable=True)
    source_record_id = Column(String(64), nullable=False)
    source_record_link = Column(String(300), nullable=True)
    organization = Column(String(200), nullable=True)
    reference = Column(String(400), nullable=True)
    doi = Column(String(160), nullable=True)

    # Argo float identity (WMO), cycle and the exact NetCDF file the value
    # came from, so every number is traceable back to a published file.
    float_id = Column(String(40), nullable=True, index=True)
    cycle = Column(Integer, nullable=True)
    source_file = Column(String(300), nullable=True, index=True)

    # ---- position + time -------------------------------------------------
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    sampled_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # ---- the oxygen measurement ------------------------------------------
    # Canonical: Argo's native dissolved oxygen in umol/kg.
    do_umol_kg = Column(Float, nullable=False)
    # Derived approximation in mg/L (see module docstring for the factor).
    do_mg_l = Column(Float, nullable=False)

    # Profile depth of this pressure level, in metres.
    depth_m = Column(Float, nullable=False)
    # Co-located profile physics when the file carries them.
    temperature_c = Column(Float, nullable=True)
    salinity_psu = Column(Float, nullable=True)
    pressure_dbar = Column(Float, nullable=True)

    # ---- severity (policy-classified, documented) ------------------------
    severity_label = Column(String(32), nullable=True, index=True)
    severity_ordinal = Column(Integer, nullable=True)
    # NORMAL | LOW | MODERATE | HIGH | CRITICAL
    is_hypoxic = Column(Integer, nullable=True)   # bool stored as 0/1
    is_dead_zone = Column(Integer, nullable=True) # bool stored as 0/1

    # ---- trust -----------------------------------------------------------
    confidence_score = Column(Float, nullable=True)
    # REAL | UNKNOWN - Argo DOXY is always REAL measured data.
    origin_status = Column(String(32), nullable=False, default="REAL", index=True)
    # Argo QC flag of the value used (1=good ... 4=bad).
    qc_flag = Column(String(8), nullable=True)
    quality_note = Column(Text, nullable=True)

    extra = Column(Text, nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    region = relationship("OceanLocation", backref="dissolved_oxygen_samples")

    def __repr__(self):
        return (
            f"<DissolvedOxygenSample id={self.id} region={self.region_id} "
            f"float={self.float_id} cycle={self.cycle} depth={self.depth_m}m "
            f"{self.do_umol_kg} umol/kg>"
        )