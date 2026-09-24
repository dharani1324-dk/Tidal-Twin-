"""
TidalTwin - Provenance Registry Model
=========================================
One row per ingestion batch. Records, for that batch:

    * which source supplied the data (name + URL)
    * WHEN it was ingested (not when the data itself was measured)
    * the method tag (OBSERVED / DERIVED / MODEL / SIMULATED)
    * a free-form batch key so rows can be traced back to this batch

Every stored value should be traceable to its source through this
table. It backs the in-memory source registry used by
`app.modules.ai.twin.sources` and feeds the interoperability exports.
"""

from sqlalchemy import Column, Integer, String, DateTime, func

from app.core.database import Base


class ProvenanceRecord(Base):
    __tablename__ = "provenance_register"

    id = Column(Integer, primary_key=True, index=True)

    # Human-readable source label (e.g. "Global Fishing Watch AIS events")
    source_name = Column(String(200), nullable=False)

    # Where the data was fetched from (API/docs URL)
    source_url = Column(String(500), nullable=True)

    # Batch identifier used by ingesters to tag rows
    batch_key = Column(String(100), nullable=False, unique=True, index=True)

    # Method tag: OBSERVED, DERIVED, MODEL, SIMULATED
    method_tag = Column(String(20), nullable=False, default="OBSERVED")

    # Free-form notes (licence, coverage, caveats for that batch)
    notes = Column(String(1000), nullable=True)

    # When WE ingested this batch
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ProvenanceRecord id={self.id} {self.source_name} [{self.method_tag}]>"