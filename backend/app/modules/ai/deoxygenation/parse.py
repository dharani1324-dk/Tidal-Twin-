"""
TidalTwin - Deoxygenation: Argo NetCDF DOXY parser
=====================================================
Reads dissolved oxygen out of a real per-cycle Argo profile NetCDF using
xarray + netCDF4.  The parser's job is to extract MEASURED levels and nothing
else: NaN, absent variables and bad QC all stay absent.

WHAT IS READ
------------
* Position and time from the file's profile arrays (``LATITUDE``,
  ``LONGITUDE``, ``JULD`` as days since 1950-01-01).
* Oxygen: ``DOXY_ADJUSTED`` (+ ``DOXY_ADJUSTED_QC``) when present, else
  ``DOXY`` (+ ``DOXY_QC``).  Levels with no numeric value are skipped.
* Co-located ``TEMP``, ``PSAL``, ``PRES``/``DEPTH`` where published.

The parser never invents a vertical profile, fills a missing level, or smooths
a QC-3/4 reading into an apparently good one.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("tidaltwin.deoxygenation.parse")

ARGO_EPOCH = datetime(1950, 1, 1, tzinfo=timezone.utc)
MAX_LEVELS_PER_FILE = 8000

_WMO = re.compile(r"(\d{7})")


def _decode_qc(value) -> str:
    """Numpy bytes / str / int -> '1'..'4' style flag, or '?'."""
    if value is None:
        return "?"
    if isinstance(value, bytes):
        return value.decode("ascii", "replace").strip() or "?"
    if isinstance(value, float) and value != value:
        # NaN padding in a QC variable carries no flag.
        return "?"
    text = str(value).strip()
    return text or "?"


def _as_float(value) -> float | None:
    """Finite float or None.  NaN and +/-inf are treated as absent.

    A BGC profile file stacks several sensor groups along the profile axis and
    pads every level to the same length, so the overwhelming majority of cells
    in any one variable are NaN.  Only finite cells are real measurements, so
    this is the single gate that keeps padding out of the database.
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    if out in (float("inf"), float("-inf")):
        return None
    return out


def _pick_var(ds, names: tuple[str, ...]):
    """Return the first variable in ``names`` that exists and has real values."""
    for name in names:
        if name in ds.variables and _has_values(ds[name].values):
            return name
    return None


def parse_netcdf_doxy(path: str, source_url: str | None = None) -> dict:
    """Parse one per-cycle Argo profile NetCDF into measured DOXY levels."""
    try:
        import xarray as xr  # noqa: F401 - lazy import keeps tests light
    except ImportError as exc:  # pragma: no cover - environment guard
        return {
            "status": "ERROR",
            "reason": f"xarray is not available in this environment: {exc}",
            "profiles": [],
            "levels": 0,
            "levels_with_doxy": 0,
        }

    try:
        ds = xr.open_dataset(path, decode_times=False, engine="netcdf4")
    except Exception as exc:  # defensive: a corrupt file must not kill the run
        logger.warning("Cannot open %s: %s", path, exc.__class__.__name__)
        return {
            "status": "ERROR",
            "reason": f"cannot open NetCDF ({exc.__class__.__name__})",
            "profiles": [],
            "levels": 0,
            "levels_with_doxy": 0,
        }

    try:
        return _extract(ds, path, source_url)
    except Exception as exc:  # defensive
        logger.warning("Parse %s failed: %s", path, exc.__class__.__name__)
        return {
            "status": "ERROR",
            "reason": f"parse failed ({exc.__class__.__name__}: {exc})",
            "profiles": [],
            "levels": 0,
            "levels_with_doxy": 0,
        }
    finally:
        try:
            ds.close()
        except Exception:  # pragma: no cover
            pass


def _extract(ds, path: str, source_url: str | None) -> dict:
    names = set(ds.variables)

    # Prefer the delayed-mode adjusted oxygen; fall back to real-time.
    doxy_var = _pick_var(ds, ("DOXY_ADJUSTED", "DOXY"))
    if doxy_var is not None:
        qc_var = "DOXY_ADJUSTED_QC" if doxy_var == "DOXY_ADJUSTED" else "DOXY_QC"
        if qc_var not in names:
            qc_var = None
    else:
        qc_var = None

    if doxy_var is None:
        return {
            "status": "NO_DOXY",
            "reason": "file carries no measured DOXY values (not a BGC file, or data absent)",
            "profiles": int(ds.sizes.get("N_PROF", 0)),
            "levels": 0,
            "levels_with_doxy": 0,
            "variables_present": sorted(names),
        }

    lat_values = ds["LATITUDE"].values if "LATITUDE" in names else None
    lon_values = ds["LONGITUDE"].values if "LONGITUDE" in names else None
    juld = ds["JULD"].values if "JULD" in names else None

    # BGC per-profile files publish pressure, not geometric depth.  Prefer a
    # real DEPTH when the file carries one, else use PRES and say so.
    depth_var = _pick_var(ds, ("DEPTH", "PRES"))
    pres_var = "PRES" if "PRES" in names else None
    depth_from = "DEPTH" if depth_var == "DEPTH" else ("PRES" if depth_var == "PRES" else None)
    depth_values = ds[depth_var].values if depth_var else None
    pres_values = ds[pres_var].values if pres_var else None
    temp_values = ds[_pick_var(ds, ("TEMP_ADJUSTED", "TEMP"))].values if _pick_var(ds, ("TEMP_ADJUSTED", "TEMP")) else None
    psal_values = ds[_pick_var(ds, ("PSAL_ADJUSTED", "PSAL"))].values if _pick_var(ds, ("PSAL_ADJUSTED", "PSAL")) else None

    doxy_values = ds[doxy_var].values
    qc_values = ds[qc_var].values if qc_var in names else None

    # Float and cycle identity, fall back to the filename.
    float_id = _first_scalar(ds.get("PLATFORM_NUMBER"))
    cycle = _first_scalar(ds.get("CYCLE_NUMBER")) or _first_scalar(ds.get("NC_CYCLE_NUMBER"))
    filename = path.replace("\\", "/").split("/")[-1]
    if not float_id:
        match = _WMO.search(filename)
        float_id = match.group(1) if match else None
    float_id = _clean_text(float_id)
    if cycle is None:
        # BGC profile files are named BR<wmo>_<cycle>.nc / BD / SD / B / R.
        match = re.search(r"_(\d{3,5})\.nc$", filename) or re.search(r"_(\d{3})_prof\.nc$", filename)
        cycle = int(match.group(1)) if match else None
    else:
        try:
            cycle = int(float(cycle))
        except (TypeError, ValueError):
            cycle = None

    n_prof, n_levels = doxy_values.shape[:2]
    levels: list[dict] = []
    considered = 0

    for i in range(n_prof):
        latitude = _as_float(_index_value(lat_values, i, n_levels))
        longitude = _as_float(_index_value(lon_values, i, n_levels))
        timestamp = _juld_to_dt(_index_value(juld, i, n_levels))
        if latitude is None or longitude is None:
            continue
        for j in range(n_levels):
            if len(levels) >= MAX_LEVELS_PER_FILE:
                break
            considered += 1
            value = _as_float(_index_2d(doxy_values, i, j))
            if value is None:
                # NaN padding - not a measurement.
                continue
            depth = _as_float(_index_2d(depth_values, i, j))
            if depth is None:
                continue
            qc = "?"
            if qc_values is not None:
                qc = _decode_qc(_index_2d(qc_values, i, j))
            levels.append({
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": timestamp,
                "depth_m": depth,
                "depth_source": depth_from,
                "do_umol_kg": value,
                "qc_flag": qc,
                "source_file": filename,
                "source_url": source_url,
                "profile_index": i,
                "level_index": j,
                "float_id": float_id,
                "cycle": cycle,
                "temperature_c": _as_float(_index_2d(temp_values, i, j)),
                "salinity_psu": _as_float(_index_2d(psal_values, i, j)),
                "pressure_dbar": _as_float(_index_2d(pres_values, i, j)),
            })

    return {
        "status": "OK",
        "reason": None,
        "float_id": float_id,
        "cycle": cycle,
        "doxy_var_used": doxy_var,
        "qc_var_used": qc_var,
        "depth_var_used": depth_from,
        "profiles": n_prof,
        "levels": len(levels),
        "levels_considered": considered,
        "levels_with_doxy": len(levels),
        "variables_present": sorted(names),
        "levels_list": levels,
        "source_url": source_url,
    }


def _clean_text(value) -> str | None:
    """Bytes/str/numpy scalar -> stripped string, or None."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    text = str(value).strip()
    return text or None


def _has_values(values) -> bool:
    """True when the array holds at least one finite (real, non-NaN) number."""
    if values is None or not hasattr(values, "shape") or values.size == 0:
        return False
    try:
        import numpy as np

        arr = np.asarray(values)
        if arr.dtype.kind in "SU":
            return arr.size > 0
        if arr.dtype.kind not in "fiu":
            return arr.size > 0
        return bool(np.any(np.isfinite(arr.astype("float64", copy=False))))
    except Exception:  # pragma: no cover - defensive
        return False


def _index_value(values, idx: int, n_levels: int):
    """Position array indexed by profile; flatten 1xN arrays as Argo stores."""
    if values is None:
        return None
    if getattr(values, "ndim", None) == 2 and values.shape[1] == n_levels:
        return values[idx, 0] if idx < values.shape[0] else None
    if values.ndim >= 1 and idx < values.shape[0]:
        return values[idx]
    return None


def _index_2d(values, i: int, j: int):
    if values is None:
        return None
    if len(values.shape) >= 2 and i < values.shape[0] and j < values.shape[1]:
        return values[i, j]
    return None


def _first_scalar(var):
    if var is None:
        return None
    try:
        return var.values.item()
    except Exception:  # pragma: no cover - defensive
        vals = var.values
        if getattr(vals, "size", 0):
            try:
                return vals.ravel()[0]
            except Exception:  # pragma: no cover
                return None
    return None


def _juld_to_dt(days: float | None) -> datetime | None:
    if days is None:
        return None
    try:
        return ARGO_EPOCH + timedelta(days=float(days))
    except (OverflowError, TypeError, ValueError):  # pragma: no cover
        return None