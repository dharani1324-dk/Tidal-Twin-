"""
TidalTwin - OGC / CF metadata validator (feature #22)
==========================================================
Validates a NetCDF file against the minimum CF conventions that matter for
the twin, so we never serve a malformed or physically impossible grid:

  axes          : at least one latitude axis and one longitude axis must exist
  ranges        : lat within [-90, 90], lon within [-180, 360]
  monotonicity  : grid axes must be monotonically increasing or decreasing
  conventions   : a `Conventions` global attribute should claim CF
  standard_name : data variables should carry a CF `standard_name`;
                  well-known ocean names are recognised, unknown names and
                  missing names are surfaced (missing = warning, unknown = warning,
                  RECOGNISED = ok) - CF is extensible, so this never over-claims
  units         : data variables should carry units; units with illegal
                  characters are an error

The report is honest by construction:

    {"valid": bool, "errors": [...], "warnings": [...],
     "passed": {...}, "variables": [{name, standard_name, units, shape}]}

`validate_netcdf(source)` accepts a path OR bytes. Ingest scripts use
`preflight()` before touching the database.
"""

import re
import tempfile
from pathlib import Path

import numpy as np
import xarray as xr

# Well-known ocean variables the twin understands (CF extensible).
KNOWN_STANDARD_NAMES = {
    "sea_surface_temperature",
    "sea_water_temperature",
    "sea_water_salinity",
    "seawater_practical_salinity",
    "seawater_salinity",
    "mass_concentration_of_chlorophyll_a_in_sea_water",
    "mass_concentration_of_oxygen_in_sea_water",
    "mole_concentration_of_oxygen_in_sea_water",
    "sea_water_speed",
    "eastward_sea_water_velocity",
    "northward_sea_water_velocity",
    "sea_water_pressure",
    "sea_water_pressure_at_sea_water_surface",
    "sea_water_density",
    "moisture_content_of_soil_layer",
    "surface_partial_pressure_of_carbon_dioxide_in_sea_water",
    "sea_surface_wave_significant_height",
    "sea_surface_wave_from_direction",
}

# Characters allowed in a CF/Udunits unit string.
_UNIT_BAD_CHARS = re.compile(r"[^A-Za-z0-9_°µμ%.\-+ /^()*]")

AXIS_ALIASES = {
    "lat": ("latitude", "lat", "y", "nav_lat", "rlat"),
    "lon": ("longitude", "lon", "x", "nav_lon", "rlon"),
    "time": ("time", "datetime", "date", "time_counter"),
}


def _monotonic(vals: np.ndarray) -> bool:
    if vals.ndim != 1 or len(vals) < 2:
        return len(vals) == 1 or vals.ndim == 1
    diff = np.diff(np.asarray(vals, dtype=float))
    return bool(np.all(diff > 0) or np.all(diff < 0))


def _axis_values(ds, role: str):
    """Return (name, values) for the first coordinate matching the role."""
    for name in AXIS_ALIASES[role]:
        if name in ds.coords:
            return name, ds.coords[name].values
    for name in ds.coords:
        std = getattr(ds.coords[name], "attrs", {}).get("standard_name", "")
        if role == "lat" and std == "latitude":
            return name, ds.coords[name].values
        if role == "lon" and std in ("longitude",):
            return name, ds.coords[name].values
        if role == "time" and std == "time":
            return name, ds.coords[name].values
    return None, None


def validate_netcdf(source) -> dict:
    """Validate one NetCDF file (path, Path or raw bytes). Honest report."""
    errors: list[str] = []
    warnings: list[str] = []
    passed = {
        "axes": False,
        "ranges": False,
        "monotonicity": False,
        "conventions": False,
        "standard_names": True,
        "units": True,
    }

    tmp = None
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            return {"valid": False, "errors": ["file not found"], "warnings": [],
                    "passed": passed, "variables": []}
        target = path
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
        tmp.write(source)
        tmp.close()
        target = Path(tmp.name)

    try:
        with xr.open_dataset(target) as ds:
            lat_name, lat_vals = _axis_values(ds, "lat")
            lon_name, lon_vals = _axis_values(ds, "lon")
            axis_names = {lat_name, lon_name, None}

            if lat_name is None or lon_name is None:
                errors.append("no latitude/longitude axis found (need one of "
                              f"lat: {AXIS_ALIASES['lat']}, lon: {AXIS_ALIASES['lon']})")
            else:
                passed["axes"] = True
                lat = np.asarray(lat_vals, dtype=float).ravel()
                lon = np.asarray(lon_vals, dtype=float).ravel()
                if np.all(np.isfinite(lat)) and np.all(np.isfinite(lon)):
                    passed["ranges"] = bool(
                        lat.min() >= -90.0 and lat.max() <= 90.0
                        and lon.min() >= -180.0 and lon.max() <= 360.0)
                    if not passed["ranges"]:
                        errors.append(
                            f"axis values out of the physical range "
                            f"(lat {lat.min():g}..{lat.max():g}, lon {lon.min():g}..{lon.max():g})")
                    passed["monotonicity"] = _monotonic(lat) and _monotonic(lon)
                    if not passed["monotonicity"]:
                        errors.append("grid axes are not monotonically increasing/decreasing")
                else:
                    errors.append("axis coordinates contain non-finite values")

            conventions = ds.attrs.get("Conventions", "")
            if isinstance(conventions, str) and conventions.upper().startswith("CF-"):
                passed["conventions"] = True
            else:
                warnings.append("no 'Conventions' global attribute claiming CF found")

            variables = []
            std_missing = False
            for var_name in ds.data_vars:
                if var_name in axis_names:
                    continue
                da = ds[var_name]
                std = getattr(da, "attrs", {}).get("standard_name")
                units = getattr(da, "attrs", {}).get("units")
                entry = {"name": var_name, "standard_name": std, "units": units,
                         "shape": list(da.dims)}
                variables.append(entry)
                if std:
                    if std not in KNOWN_STANDARD_NAMES:
                        warnings.append(
                            f"variable '{var_name}' standard_name '{std}' not in the "
                            f"twin's recognised set (CF extensible - preserved as-is)")
                else:
                    std_missing = True
                    warnings.append(f"variable '{var_name}' has no standard_name")
                if units:
                    if _UNIT_BAD_CHARS.search(str(units)):
                        passed["units"] = False
                        errors.append(f"variable '{var_name}' has illegal unit string '{units}'")
                else:
                    warnings.append(f"variable '{var_name}' has no units attribute")

            passed["standard_names"] = not std_missing

            return {
                "valid": not errors,
                "errors": errors,
                "warnings": warnings,
                "passed": passed,
                "variables": variables,
            }
    except Exception as e:
        return {"valid": False, "errors": [f"unreadable NetCDF file: {e}"],
                "warnings": [], "passed": passed, "variables": []}
    finally:
        if tmp is not None:
            Path(tmp.name).unlink(missing_ok=True)


def preflight(path) -> dict:
    """Short-form used by ingest scripts before touching the database."""
    report = validate_netcdf(path)
    return {
        "file": str(path),
        "ok": report["valid"],
        "errors": report["errors"],
        "warnings": report["warnings"],
    }