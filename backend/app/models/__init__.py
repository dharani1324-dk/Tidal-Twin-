"""
OceanVerse AI - Models Package
==============================
Importing all models here makes SQLAlchemy aware of every table.
We must import them so `Base.metadata` can create the tables.
"""

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.models.alert import OceanAlert
from app.models.ais import AisTrack, DerivedCurrent
from app.models.provenance import ProvenanceRecord

__all__ = [
    "OceanLocation",
    "OceanObservation",
    "OceanAlert",
    "AisTrack",
    "DerivedCurrent",
    "ProvenanceRecord",
]
