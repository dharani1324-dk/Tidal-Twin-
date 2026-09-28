"""
TidalTwin - Argo BGC Profile Ingestion Script (Dissolved Oxygen)
==================================================================
Reads REAL Argo BGC float profile files (NetCDF, from the Argo GDAC) and stores
one row per depth level in the `dissolved_oxygen_samples` table.

Argo BGC floats measure dissolved oxygen (DOXY) in umol/kg, along with
temperature, salinity, and pressure.  This script follows the same honesty rules
as `scripts.ingest_argo`:

    - NaN values are SKIPPED / stored as NULL (never invented)
    - profiles without a usable position or time are SKIPPED
    - duplicates are SKIPPED so re-running is safe

Depth is recorded as pressure in decibars (1 dbar ~ 1 m, the same convention
used by `modules/physics/ocean_profiles.py`).

UNITS
-----
Argo floats publish oxygen as DOXY in umol/kg (micromoles of O2 per
kilogram of seawater) and that is our canonical unit, stored verbatim.
We also store do_mg_l - the classic oceanographer's concentration in
milligrammes of O2 per litre - derived with the standard factor:

    1 umol O2/kg = 32e-6 g O2/kg ~ 0.032 mg O2/L   (density ~ 1 kg/L)

The derivation is labelled approximate because it assumes seawater density of
about 1 kg/L; the canonical do_umol_kg is never transformed before storage.

SEVERITY
--------
Hypoxia is conventionally defined as dissolved oxygen below ~2 mg/L
(~62.5 umol/kg), with values below ~0.5 mg/L (~15.6 umol/kg) considered
near-anoxic/dead zone.  Our severity ladder around those thresholds is a
*policy* classifier and says so in its documentation.

Usage:
    python -m scripts.ingest_argobgc path\\to\\file.nc
    python -m scripts.ingest_argobgc data\\argobgc
    python -m scripts.ingest_argobgc file1.nc file2.nc --limit 500
    python -m scripts.ingest_argobgc data\\argobgc --reingest
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.core.database import SessionLocal
from app.models.dissolved_oxygen import DissolvedOxygenSample
from scripts.ingest_netcdf import _as_utc

# Standard Argo variable names (see the Argo user's manual)
PLATFORM = "PLATFORM_NUMBER"
JULD = "JULD"
LAT = "LATITUDE"
LON = "LONGITUDE"
PRES = "PRES"
TEMP = "TEMP"
PSAL = "PSAL"
DOXY = "DOXY"          # Dissolved oxygen in umol/kg
LEVELS = "N_LEVELS"
PROFILES = "N_PROF"

# Depth convention: pressure in dbar is used directly as metres (as the
# physics engine does).  Kept as a named constant so the approximation is
# explicit and easy to upgrade later.
_DBAR_AS_METRE = 1.0

# Conversion factor: 1 umol/kg ≈ 0.032 mg/L (assuming density ~ 1 kg/L)
UMOL_KG_TO_MG_L = 0.032

# Hypoxia thresholds (policy-based, documented)
HYPOXIA_UMOL_KG = 62.5      # ~2 mg/L
DEAD_ZONE_UMOL_KG = 15.6    # ~0.5 mg/L


def _classify_severity(do_umol_kg: float) -> tuple[str, int, int, int]:
    """Classify oxygen severity. Returns (label, ordinal, is_hypoxic, is_dead_zone).
    
    Ordinal: 1=NORMAL, 2=LOW, 3=MODERATE, 4=HIGH, 5=CRITICAL
    """
    if do_umol_kg <= DEAD_ZONE_UMOL_KG:
        return "CRITICAL", 5, 1, 1
    elif do_umol_kg <= HYPOXIA_UMOL_KG:
        return "HIGH", 4, 1, 0
    elif do_umol_kg <= 125:   # ~4 mg/L - moderate concern
        return "MODERATE", 3, 0, 0
    elif do_umol_kg <= 187:   # ~6 mg/L - low concern
        return "LOW", 2, 0, 0
    else:
        return "NORMAL", 1, 0, 0


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
    """Yield (float_id, lat, lon, time, depth, do_umol_kg, temp, sal, pres) per level."""
    if not all(k in ds.variables for k in (PLATFORM, JULD, LAT, LON, PRES, DOXY)):
        return

    n_prof = int(ds.sizes.get(PROFILES, 1))
    juld = ds[JULD].values
    lat_v = ds[LAT].values
    lon_v = ds[LON].values
    pres_v = ds[PRES].values if PRES in ds.variables else None
    temp_v = ds[TEMP].values if TEMP in ds.variables else None
    sal_v = ds[PSAL].values if PSAL in ds.variables else None
    doxy_v = ds[DOXY].values if DOXY in ds.variables else None
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
            doxy = _cell(doxy_v, i, j) if doxy_v is not None else None

            # Require at least depth and oxygen value
            if depth is None or doxy is None:
                continue

            yield float_id, lat, lon, ts, depth, doxy, temp, sal, pres


def ingest_file(path: Path, limit: int | None = None, reingest: bool = False, verbose: bool = False) -> dict:
    """Ingest one Argo BGC profile file. Returns a per-file summary."""
    source_file = str(path)

    if reingest:
        with SessionLocal.begin() as db:
            deleted = db.query(DissolvedOxygenSample).filter(
                DissolvedOxygenSample.source_file == source_file
            ).delete(synchronize_session=False)
        if verbose:
            print(f"[reingest] removed {deleted} row(s) for {source_file}")

    existing_keys: set = set()
    with SessionLocal() as db:
        for row in db.query(
            DissolvedOxygenSample.float_id,
            DissolvedOxygenSample.sampled_at,
            DissolvedOxygenSample.depth_m
        ).filter(DissolvedOxygenSample.source_file == source_file).all():
            existing_keys.add((row.float_id, _as_utc(row.sampled_at), row.depth_m))

    rows: list[DissolvedOxygenSample] = []
    total_profile_files = 0
    with xr.open_dataset(path) as ds:
        for float_id, lat, lon, ts, depth, doxy, temp, sal, pres in extract_profiles(ds, source_file):
            total_profile_files += 1
            key = (float_id, ts, depth)
            if key in existing_keys:
                continue
            existing_keys.add(key)

            do_mg_l = doxy * UMOL_KG_TO_MG_L
            severity_label, severity_ordinal, is_hypoxic, is_dead_zone = _classify_severity(doxy)

            rows.append(
                DissolvedOxygenSample(
                    region_id=None,  # Will be assigned by regional mapping later
                    source="Argo BGC float (real Argo GDAC)",
                    source_dataset="Argo GDAC BGC",
                    source_record_id=f"{float_id}_{ts.isoformat()}_{depth}",
                    source_record_link=None,
                    organization="Argo Program",
                    reference="https://argo.ucsd.edu/",
                    doi="10.17882/42182",
                    float_id=float_id,
                    cycle=None,
                    latitude=lat,
                    longitude=lon,
                    sampled_at=ts,
                    do_umol_kg=doxy,
                    do_mg_l=do_mg_l,
                    depth_m=depth,
                    temperature_c=temp,
                    salinity_psu=sal,
                    pressure_dbar=pres,
                    severity_label=severity_label,
                    severity_ordinal=severity_ordinal,
                    is_hypoxic=is_hypoxic,
                    is_dead_zone=is_dead_zone,
                    confidence_score=None,
                    origin_status="REAL",
                    qc_flag=None,
                    quality_note="Real Argo BGC float measurement",
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
    """Ingest every Argo BGC file (or all .nc files under every directory)."""
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
        description="Ingest real Argo BGC float profile NetCDF files (with DOXY) into dissolved_oxygen_samples."
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
        print("Argo BGC (DOXY) ingestion complete:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    except Exception as e:  # keep failures visible & friendly for beginners
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()