"""
TidalTwin - Glider Profile Ingestion Script (features #16/#17)
=================================================================
Reads a REAL glider deployment NetCDF (IOOS National GliderDAC format, CF/ACDD
conventions — the same files served by https://gliders.ioos.us/erddap and
mirrored at NCEI) and stores one row per measurement sample in
`glider_profiles`.

A glider deployment is one trajectory of continuous water-column samples:
position, time, pressure/depth and — depending on the payload — temperature,
salinity and biogeochemical (BGC) fields: dissolved oxygen, chlorophyll and
nitrate (feature #17).

Honesty rules (same as Argo / NetCDF ingest):
    - NaN / _FillValue samples are SKIPPED (never invented)
    - samples without a usable position or time are SKIPPED
    - a sensor not carried on the deployment stays NULL ("Data unavailable")
    - duplicates are SKIPPED so re-running is safe

Usage:
    .venv\\Scripts\\python -m scripts.ingest_glider path\\to\\deployment.nc
    .venv\\Scripts\\python -m scripts.ingest_glider data\\glider --reingest
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.core.database import SessionLocal
from app.models.glider import GliderProfile
from scripts.ingest_netcdf import _as_utc

# GliderDAC v2.0 / v3.0 variable names, with standard aliases across flavours.
TRAJ_VARS = ["trajectory", "trajectory_id"]
DIM_ALIASES = ["time", "obs", "sample"]
LAT_ALIASES = ["latitude", "lat"]
LON_ALIASES = ["longitude", "lon"]
FIELD_ALIASES = {
    "temperature": ["temperature", "sea_water_temperature", "temp"],
    "salinity": ["salinity", "sea_water_practical_salinity", "practical_salinity"],
    "pressure": ["pressure", "sea_water_pressure"],
    "depth": ["depth", "depth_m", "altitude"],
    "dissolved_oxygen": ["dissolved_oxygen", "oxygen", "mass_concentration_of_oxygen_in_sea_water"],
    "chlorophyll": ["chlorophyll", "chlorophyll_a", "mass_concentration_of_chlorophyll_in_sea_water"],
    "nitrate": ["nitrate", "moles_of_nitrate_per_unit_mass_in_sea_water"],
}

# 1 dbar of pressure ≈ 1 m of depth (as in Argo / physics engine)
_DBAR_AS_METRE = 1.0


def _find(ds: xr.Dataset, aliases: list[str], in_vars: bool = False):
    for name in aliases:
        if in_vars and name in ds.data_vars:
            return name
        if name in ds.coords or name in ds.variables:
            return name
    return None


def _val(x):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return v


def _deployment_id(ds: xr.Dataset) -> tuple[str, str]:
    """(deployment name, instrument) from global attrs or the trajectory var."""
    attrs = dict(getattr(ds, "attrs", {}) or {})
    name = attrs.get("deployment_name") or attrs.get("platform_name") or attrs.get("id")
    inst = attrs.get("platform_type") or attrs.get("instrument_name") or attrs.get("platform")
    for tv in TRAJ_VARS:
        if tv in ds.variables and not isinstance(ds[tv].values, np.ndarray):
            name = str(ds[tv].values)
            break
    return str(name or "unknown"), str(inst or "glider").upper()


def extract_samples(ds: xr.Dataset):
    """Yield (deployment, instrument, lat, lon, time, depth, temp, sal, pres,
    oxygen, chlorophyll, nitrate, qc) per measurement sample."""
    name, inst = _deployment_id(ds)
    time_name = _find(ds, DIM_ALIASES)
    lat_name = _find(ds, LAT_ALIASES)
    lon_name = _find(ds, LON_ALIASES)
    if time_name is None or lat_name is None or lon_name is None:
        return
    n = int(ds.sizes[time_name] if time_name in ds.sizes else 0)
    if n == 0:
        return

    lat_v = np.asarray(ds[lat_name].values)
    lon_v = np.asarray(ds[lon_name].values)
    time_v = np.asarray(ds[time_name].values)

    def col(role):
        f = _find(ds, FIELD_ALIASES.get(role, [role]), in_vars=True) or _find(ds, FIELD_ALIASES.get(role, [role]))
        return np.asarray(ds[f].values) if f else None

    temp_c, sal_c = col("temperature"), col("salinity")
    pres_c, depth_c = col("pressure"), col("depth")
    oxy_c, chl_c, nit_c = col("dissolved_oxygen"), col("chlorophyll"), col("nitrate")

    for i in range(n):
        lat = _val(lat_v[i] if i < len(lat_v) else None)
        lon = _val(lon_v[i] if i < len(lon_v) else None)
        if lat is None or lon is None:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        t_raw = time_v[i] if i < len(time_v) else None
        if not isinstance(t_raw, np.datetime64):
            continue  # undecodable time -> do not guess
        ts = _as_utc(pd.Timestamp(t_raw.astype("datetime64[ms]")).to_pydatetime())

        temp = _val(temp_c[i]) if temp_c is not None else None
        sal = _val(sal_c[i]) if sal_c is not None else None
        pres = _val(pres_c[i]) if pres_c is not None else None
        depth = _val(depth_c[i]) if depth_c is not None else (pres * _DBAR_AS_METRE if pres is not None else None)
        if depth is None:
            continue  # no depth/pressure -> no position in the water column
        oxy = _val(oxy_c[i]) if oxy_c is not None else None
        chl = _val(chl_c[i]) if chl_c is not None else None
        nit = _val(nit_c[i]) if nit_c is not None else None
        if temp is None and sal is None and oxy is None and chl is None and nit is None:
            continue  # nothing measured at this sample

        yield name, inst, lat, lon, ts, depth, temp, sal, pres, oxy, chl, nit, None


def ingest_file(path: Path, limit: int | None = None, reingest: bool = False, verbose: bool = False) -> dict:
    source_file = str(path)

    if reingest:
        with SessionLocal.begin() as db:
            deleted = db.query(GliderProfile).filter(
                GliderProfile.source_file == source_file
            ).delete(synchronize_session=False)
        if verbose:
            print(f"[reingest] removed {deleted} existing row(s) for {source_file}")

    existing_keys: set = set()
    with SessionLocal() as db:
        for row in db.query(GliderProfile.deployment_id, GliderProfile.time, GliderProfile.depth_m).filter(
            GliderProfile.source_file == source_file
        ).all():
            existing_keys.add((row.deployment_id, _as_utc(row.time), row.depth_m))

    rows: list[GliderProfile] = []
    seen = 0
    with xr.open_dataset(path) as ds:
        for name, inst, lat, lon, ts, depth, temp, sal, pres, oxy, chl, nit, qc in extract_samples(ds):
            seen += 1
            key = (name, ts, depth)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            rows.append(
                GliderProfile(
                    deployment_id=name,
                    instrument=inst,
                    latitude=lat,
                    longitude=lon,
                    time=ts,
                    depth_m=depth,
                    temperature=temp,
                    salinity=sal,
                    pressure=pres,
                    dissolved_oxygen=oxy,
                    chlorophyll=chl,
                    nitrate=nit,
                    qc_flags=qc,
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

    return {"rows_inserted": inserted, "samples_seen": seen, "deployment": name if rows else None}


def ingest_paths(paths: list[Path], limit: int | None = None, reingest: bool = False, verbose: bool = True) -> dict:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.glob("*.nc")))
        elif p.is_file():
            files.append(p)
    files = sorted(set(files))

    total_inserted, total_seen = 0, 0
    for f in files:
        s = ingest_file(f, limit=limit, reingest=reingest, verbose=verbose)
        total_inserted += s["rows_inserted"]
        total_seen += s["samples_seen"]
        if verbose:
            print(f"  {f.name}: +{s['rows_inserted']} rows")
    return {"files_processed": len(files), "samples_seen": total_seen, "rows_inserted": total_inserted}


def main():
    parser = argparse.ArgumentParser(
        description="Ingest real glider deployment NetCDF files into glider_profiles."
    )
    parser.add_argument("paths", nargs="+", help="One or more .nc files and/or directories")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N total rows")
    parser.add_argument("--reingest", action="store_true",
                        help="Delete existing rows for each source file before ingesting")
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"Path(s) not found: {[str(p) for p in missing]}", file=sys.stderr)
        sys.exit(1)
    try:
        summary = ingest_paths(paths, limit=args.limit, reingest=args.reingest)
        print("Glider ingestion complete:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()