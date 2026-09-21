"""
TidalTwin - NetCDF Reading Model
==================================
Represents ONE measurement extracted from a NetCDF model file.

A NetCDF file is a 4D box of ocean data (latitude x longitude x depth x time)
with variables inside such as temperature or salinity.  When we "ingest" such
a file, we unpack that box into individual rows — one measurement per grid
point — so they can be queried with SQL like any other observation.

Columns mirror the flavour of `ocean_observations` (real values only, NULL
where a variable was not present in the source file).
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.core.database import Base


class NetcdfReadings(Base):
    __tablename__ = "netcdf_readings"

    id = Column(Integer, primary_key=True, index=True)

    # Where the measurement was taken (grid point)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    depth_m = Column(Float, nullable=True, default=0.0)  # meters below surface

    # When the model produced this value
    time = Column(DateTime(timezone=True), nullable=False, index=True)

    # Which variable this value belongs to (e.g. "sea_water_temperature")
    variable_name = Column(String(100), nullable=False, index=True)
    value = Column(Float, nullable=True)

    # CF convention metadata carried from the source file (feature #2)
    standard_name = Column(String(120), nullable=True)  # e.g. sea_surface_temperature
    units = Column(String(60), nullable=True)           # e.g. degC

    # Which NetCDF file this row came from (provenance / data honesty)
    source_file = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<NetcdfReadings id={self.id} var={self.variable_name} lat={self.latitude:.2f} lon={self.longitude:.2f}>"