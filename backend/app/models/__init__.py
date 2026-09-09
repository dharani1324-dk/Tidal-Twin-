"""
OceanVerse AI - Models Package
==============================
Importing all models here makes SQLAlchemy aware of every table.
We must import them so `Base.metadata` can create the tables.
"""

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.models.alert import OceanAlert

__all__ = ["OceanLocation", "OceanObservation", "OceanAlert"]
