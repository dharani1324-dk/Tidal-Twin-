"""
TidalTwin - NetCDF Ingestion Script
======================================
Reads a NetCDF file (the standard "box" format for numerical ocean model
output) and unpacks it into the `netcdf_readings` table — one row per grid
point, per variable.

A NetCDF file is 4D: latitude x longitude x depth x time.  It holds variables
like sea_water_temperature or salinity.  To find the coordinate axes this
script first reads the CF convention metadata baked into the file (via
`cf-xarray` — `standard_name` / `units` / axis attributes), which works even
when coordinates have unusual names like `nav_lat` or `time_counter` (typical
of CMEMS / NEMO ocean model output).  If the file has no CF metadata, it falls
back to matching coordinate names by common spelling.  Only real values are
stored:

    - NaN / fill values are SKIPPED (never "invented")
    - variables without a recognizable lat/lon/time axis are SKIPPED with a
      warning
    - duplicates are SKIPPED so re-running is safe

Usage:
    .venv\\Scripts\\python -m scripts.ingest_netcdf path\\to\\file.nc
    .venv\\Scripts\\python -m scripts.ingest_netcdf path\\to\\file.nc --limit 500
    .venv\\Scripts\\python -m scripts.ingest_netcdf path\\to\\file.nc --reingest
"""

import argparse
import sys
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import cf_xarray  # noqa: F401  (activates the xarray `.cf` accessor)

from app.core.database import SessionLocal
from app.models.netcdf import NetcdfReadings
from app.modules.ai.netcdf_validate import preflight

# Name aliases for each axis.  Used ONLY as a fallback when the file has no CF
# metadata: many NetCDF files use the same idea with different spellings.
LAT_ALIASES = ["latitude", "lat", "Lat", "LAT", "y"]
LON_ALIASES = ["longitude", "lon", "Lon", "LON", "x"]
TIME_ALIASES = ["time", "Time", "TIME", "time_counter", "datetime", "date"]
DEPTH_ALIASES = [
    "depth", "depth_m", "Depth", "z", "lev", "level", "pressure",
    "height", "altitude", "deptht",
]

# NetCDF files store 'time' in many date-unit flavours (e.g.
# "seconds since 2000-01-01"); pandas handles all of them.
TIME_UNITS_KEY = "units"


def _find_coord(coords, aliases):
    """Return the first name (in `aliases`) that exists in the file."""
    for name in aliases:
        if name in coords:
            return name
    return None


def _cf_axis_map(ds):
    """Identify axes from CF convention metadata via cf-xarray.

    Returns {role: coordinate_name} for each axis cf-xarray can identify
    (roles: 'lat', 'lon', 'time', 'depth').  May be empty for non-CF files.
    """
    mapping: dict[str, str] = {}

    # ds.cf.axes maps axis letters to dimension names, e.g. {'X': ['lon']}.
    try:
        axes = dict(ds.cf.axes)
    except Exception:
        axes = {}
    roles = {"X": "lon", "Y": "lat", "T": "time", "Z": "depth"}
    for axis_letter, dims in axes.items():
        role = roles.get(str(axis_letter).upper())
        if not role:
            continue
        dim = dims[0] if isinstance(dims, (list, tuple)) else dims
        if dim:
            mapping[role] = dim

    # Fall back on standard CF names ('latitude', 'longitude', 'vertical').
    if len(mapping) < 4:
        cf_keys = {"lat": "latitude", "lon": "longitude", "time": "time", "depth": "vertical"}
        for role, ck in cf_keys.items():
            if role in mapping:
                continue
            try:
                name = ds.cf[ck].name
                if name:
                    mapping[role] = name
            except Exception:
                continue
    return mapping


def _as_utc(dt):
    """Normalise a datetime to timezone-aware UTC so keys always compare equal.

    The `time` column is timezone-aware; naive datetimes from the file are
    treated as UTC.  Without this, the dedupe keys would mismatch on a re-run
    (naive vs aware) and duplicate rows would creep in.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ingest_file(path: Path, limit: int | None = None, reingest: bool = False, verbose: bool = True) -> dict:
    """Ingest one NetCDF file into `netcdf_readings`. Returns a summary dict."""
    source_file = str(path)

    if reingest:
        with SessionLocal.begin() as db:
            deleted = db.query(NetcdfReadings).filter(
                NetcdfReadings.source_file == source_file
            ).delete(synchronize_session=False)
        if verbose:
            print(f"[reingest] removed {deleted} existing row(s) for {source_file}")

    with xr.open_dataset(path) as ds:
        # ---- Find the axes: CF metadata first, common names as fallback ----
        role_coord = _cf_axis_map(ds)
        axis_method = "CF metadata" if role_coord else "name lookup"

        if "lat" not in role_coord:
            role_coord["lat"] = _find_coord(ds.coords, LAT_ALIASES)
        if "lon" not in role_coord:
            role_coord["lon"] = _find_coord(ds.coords, LON_ALIASES)
        if "time" not in role_coord:
            role_coord["time"] = _find_coord(ds.coords, TIME_ALIASES)
        if "depth" not in role_coord:
            role_coord["depth"] = _find_coord(ds.coords, DEPTH_ALIASES)

        lat_name = role_coord.get("lat")
        lon_name = role_coord.get("lon")
        time_name = role_coord.get("time")
        depth_name = role_coord.get("depth")

        # Which variables actually describe the ocean axes themselves
        axis_names = {lat_name, lon_name, time_name, depth_name}

        data_vars = [name for name in ds.data_vars if name not in axis_names]

        if verbose:
            print(f"file:        {source_file}")
            print(f"axes found:  {axis_method}")
            print(f"lat axis:    {lat_name}")
            print(f"lon axis:    {lon_name}")
            print(f"time axis:   {time_name}")
            print(f"depth axis:  {depth_name}")
            print(f"variables:   {data_vars or '(none recognised)'}")

        if lat_name is None or lon_name is None or time_name is None:
            print("[!] This file has no recognisable latitude/longitude/time axes.")
            if verbose:
                for name in ds.coords:
                    print(f"    coord: {name}")
            return {"rows_inserted": 0, "rows_skipped": 0, "variables": []}

        # ---- Load existing keys so we never waste time re-inserting ----
        existing_keys = set()
        with SessionLocal() as db:
            rows = db.query(
                NetcdfReadings.latitude,
                NetcdfReadings.longitude,
                NetcdfReadings.depth_m,
                NetcdfReadings.time,
                NetcdfReadings.variable_name,
            ).filter(NetcdfReadings.source_file == source_file).all()
            for lat, lon, depth, t, var in rows:
                existing_keys.add((lat, lon, depth, _as_utc(t), var))

        candidates: list[NetcdfReadings] = []
        skipped_dims = 0
        total = 0
        for var_name in data_vars:
            da = ds[var_name]
            dims = da.dims
            if len(dims) == 0:  # a scalar constant — skip, no grid point
                if verbose:
                    print(f"    skip scalar variable: {var_name}")
                continue

            var_attrs = dict(getattr(da, "attrs", {}) or {})
            standard_name = var_attrs.get("standard_name")
            units = var_attrs.get("units")

            # Map each dimension back to a real axis coordinate
            dim_to_axis = {}
            for d in dims:
                if d == lat_name:
                    dim_to_axis[d] = "lat"
                elif d == lon_name:
                    dim_to_axis[d] = "lon"
                elif d == time_name:
                    dim_to_axis[d] = "time"
                elif d == depth_name:
                    dim_to_axis[d] = "depth"
                else:
                    skipped_dims += 1
                    if verbose:
                        print(f"    skip variable with non-axis dim: {var_name} (dims={dims})")
                    break
            else:
                values = da.values
                coords_by_dim = {
                    d: ds.coords[d].values for d in dims if d in ds.coords
                }

                for idx in np.ndindex(values.shape):
                    raw = values[idx]
                    if not np.isfinite(raw):
                        continue  # NaN/fill value — not real data

                    lat = lon = depth = time_val = None
                    for d, i in zip(dims, idx):
                        axis = dim_to_axis[d]
                        pos = coords_by_dim.get(d)
                        if pos is None:
                            continue
                        v = pos[i]
                        if axis == "lat":
                            lat = float(v)
                        elif axis == "lon":
                            lon = float(v)
                        elif axis == "depth":
                            depth = float(v)
                        elif axis == "time":
                            time_val = v

                    # A measurement without a lat/lon/time is not usable
                    if lat is None or lon is None or time_val is None:
                        continue

                    try:
                        ts = _as_utc(pd.Timestamp(time_val).to_pydatetime())
                    except (ValueError, TypeError) as e:
                        if verbose:
                            print(f"    unparseable time value {time_val!r}: {e}")
                        continue

                    key = (lat, lon, depth if depth is not None else 0.0, ts, var_name)
                    if key in existing_keys:
                        continue
                    existing_keys.add(key)

                    candidates.append(
                        NetcdfReadings(
                            latitude=lat,
                            longitude=lon,
                            depth_m=depth if depth is not None else 0.0,
                            time=ts,
                            variable_name=var_name,
                            value=float(raw),
                            standard_name=standard_name,
                            units=units,
                            source_file=source_file,
                        )
                    )
                    total += 1
                    if limit is not None and total >= limit:
                        break
                if limit is not None and total >= limit:
                    if verbose:
                        print(f"[limit] stopping after {limit} rows")
                    break

        # ---- Write in one transaction ----
        inserted = 0
        with SessionLocal() as db:
            for i in range(0, len(candidates), 500):
                db.add_all(candidates[i : i + 500])
                db.commit()
                inserted += len(candidates[i : i + 500])

    summary = {
        "rows_inserted": inserted,
        "axis_method": axis_method,
        "variables": data_vars,
    }
    if verbose:
        print(f"inserted:    {inserted} row(s) into netcdf_readings")
        print(f"source_file: {source_file}")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Ingest a NetCDF file into the netcdf_readings table."
    )
    parser.add_argument("file", help="Path to the .nc file")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N rows")
    parser.add_argument(
        "--reingest",
        action="store_true",
        help="Delete existing rows for this file before ingesting",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run the CF preflight validator (feature #22) and refuse to ingest invalid files",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    if args.validate:
        report = preflight(path)
        print(f"CF preflight (feature #22): ok={report['ok']}")
        for e in report["errors"]:
            print(f"  error:   {e}")
        for w in report["warnings"]:
            print(f"  warning: {w}")
        if not report["ok"]:
            print("Refusing to ingest a non-CF-valid file.", file=sys.stderr)
            sys.exit(2)

    try:
        ingest_file(path, limit=args.limit, reingest=args.reingest)
    except Exception as e:  # keep failures visible & friendly for beginners
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()