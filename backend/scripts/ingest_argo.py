"""
TidalTwin - Argo Profile Ingestion Script
============================================
Reads REAL Argo float profile files (NetCDF, from the Argo GDAC) and stores
one row per depth level in the `argo_profiles` table.

Argo floats drift in the open ocean, sink and rise, measuring temperature and
salinity down to ~2000 m.  Each profile file holds one vertical column
(N_PROF profiles x N_LEVELS depth levels).  This script reuses the NetCDF
parsing conventions from `scripts.ingest_netcdf` (CF metadata, UTC-normalised
times, NaN = "not present") and follows the same honesty rules:

    - NaN values are SKIPPED / stored as NULL (never invented)
    - profiles without a usable position or time are SKIPPED
    - duplicates are SKIPPED so re-running is safe

Depth is recorded as pressure in decibars (1 dbar ~ 1 m, the same convention
used by `modules/physics/ocean_profiles.py`).

Usage:
    .venv\\Scripts\\python -m scripts.ingest_argo path\\to\\file.nc
    .venv\\Scripts\\python -m scripts.ingest_argo data\\argo
    .venv\\Scripts\\python -m scripts.ingest_argo file1.nc file2.nc --limit 500
    .venv\\Scripts\\python -m scripts.ingest_argo data\\argo --reingest
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.core.database import SessionLocal
from app.models.argo import ArgoProfile
from scripts.ingest_netcdf import _as_utc

# Standard Argo variable names (see the Argo user's manual)
PLATFORM = "PLATFORM_NUMBER"
JULD = "JULD"
LAT = "LATITUDE"
LON = "LONGITUDE"
PRES = "PRES"
TEMP = "TEMP"
PSAL = "PSAL"
LEVELS = "N_LEVELS"
PROFILES = "N_PROF"

# Depth convention: pressure in dbar is used directly as metres (as the
# physics engine does).  Kept as a named constant so the approximation is
# explicit and easy to upgrade later.
_DBAR_AS_METRE = 1.0


def _cell(items, i, j):
    """Safe scalar access for a 2D array; returns None for NaN/None."""
    try:
        v = items[i][j]
    except (IndexError, TypeError):
        return None
    if v is None:
        return None
    v = float(np.asarray(v))
    if not np.isfinite(v):
        return None
    return v


def extract_profiles(ds: xr.Dataset, source_file: str, float_cell: int = 0):
    """Yield (float_id, lat, lon, time, depth, temp, sal, pres) per level."""
    if not all(k in ds.variables for k in (PLATFORM, JULD, LAT, LON, PRES)):
        return

    n_prof = int(ds.sizes.get(PROFILES, 1))
    juld = ds[JULD].values
    lat_v = ds[LAT].values
    lon_v = ds[LON].values
    pres_v = ds[PRES].values if PRES in ds.variables else None
    temp_v = ds[TEMP].values if TEMP in ds.variables else None
    sal_v = ds[PSAL].values if PSAL in ds.variables else None
    platform = ds[PLATFORM].values

    for i in range(n_prof):
        try:
            float_id = str(int(platform[i]))
        except (TypeError, ValueError):
            continue

        try:
            lat = float(lat_v[i])
            lon = float(lon_v[i])
        except (TypeError, IndexError, ValueError):
            continue
        if not (np.isfinite(lat) and np.isfinite(lon)):
            continue

        t_raw = juld[i] if i < len(juld) else None
        if not isinstance(t_raw, np.datetime64):
            continue  # time could not be decoded -> do not guess
        ts = _as_utc(pd.Timestamp(t_raw.astype("datetime64[ms]")).to_pydatetime())

        n_levels = int(ds.sizes.get(LEVELS, 0))
        for j in range(n_levels):
            pres = _cell(pres_v, i, j) if pres_v is not None else None
            depth = pres * _DBAR_AS_METRE if pres is not None else None
            temp = _cell(temp_v, i, j) if temp_v is not None else None
            sal = _cell(sal_v, i, j) if sal_v is not None else None
            if depth is None or (temp is None and sal is None):
                continue

            yield float_id, lat, lon, ts, depth, temp, sal, pres


def ingest_file(path: Path, limit: int | None = None, reingest: bool = False, verbose: bool = False) -> dict:
    """Ingest one Argo profile file. Returns a per-file summary."""
    source_file = str(path)

    if reingest:
        with SessionLocal.begin() as db:
            deleted = db.query(ArgoProfile).filter(
                ArgoProfile.source_file == source_file
            ).delete(synchronize_session=False)
        if verbose:
            print(f"[reingest] removed {deleted} row(s) for {source_file}")

    existing_keys: set = set()
    with SessionLocal() as db:
        for row in db.query(ArgoProfile.float_id, ArgoProfile.time, ArgoProfile.depth_m).filter(
            ArgoProfile.source_file == source_file
        ).all():
            existing_keys.add((row.float_id, _as_utc(row.time), row.depth_m))

    rows: list[ArgoProfile] = []
    total_profile_files = 0
    with xr.open_dataset(path) as ds:
        for float_id, lat, lon, ts, depth, temp, sal, pres in extract_profiles(ds, source_file):
            total_profile_files += 1
            key = (float_id, ts, depth)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            rows.append(
                ArgoProfile(
                    float_id=float_id,
                    latitude=lat,
                    longitude=lon,
                    time=ts,
                    depth_m=depth,
                    temperature=temp,
                    salinity=sal,
                    pressure=pres,
                    source_file=source_file,
                )
            )
            if limit is not None and len(rows) >= limit:
                break

    inserted = 0
    with SessionLocal() as db:
        for i in range(0, len(rows), 500):
            db.add_all(rows[i : i + 500])
            db.commit()
            inserted += len(rows[i : i + 500])

    return {"rows_inserted": inserted, "profiles_seen": total_profile_files}


def ingest_paths(paths: list[Path], limit: int | None = None, reingest: bool = False, verbose: bool = True) -> dict:
    """Ingest every Argo file (or all .nc files under every directory)."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.glob("*.nc")))
        elif p.is_file():
            files.append(p)
    files = sorted(set(files))

    total_inserted = 0
    total_profiles = 0
    total_files = 0
    for f in files:
        s = ingest_file(f, limit=limit, reingest=reingest, verbose=verbose)
        total_files += 1
        total_inserted += s["rows_inserted"]
        total_profiles += s["profiles_seen"]
        if verbose:
            print(f"  {f.name}: +{s['rows_inserted']} rows")
    return {"files_processed": total_files, "profiles_seen": total_profiles, "rows_inserted": total_inserted}


def main():
    parser = argparse.ArgumentParser(
        description="Ingest real Argo float profile NetCDF files into argo_profiles."
    )
    parser.add_argument("paths", nargs="+", help="One or more .nc files and/or directories")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N total rows")
    parser.add_argument(
        "--reingest",
        action="store_true",
        help="Delete existing rows for each source file before ingesting",
    )
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"Path(s) not found: {[str(p) for p in missing]}", file=sys.stderr)
        sys.exit(1)

    try:
        summary = ingest_paths(paths, limit=args.limit, reingest=args.reingest)
        print("Argo ingestion complete:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    except Exception as e:  # keep failures visible & friendly for beginners
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()