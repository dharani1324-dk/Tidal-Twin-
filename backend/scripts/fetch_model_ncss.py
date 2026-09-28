"""Fetch a real NRL HYCOM+NCODA 3D ocean-model grid to NetCDF, via the HYCOM NCSS service.

Why this exists
---------------
`scripts.fetch_model` pulls the same product from NOAA CoastWatch ERDDAP, but
`coastwatch.pfeg.noaa.gov` is not reachable from every host (TCP 443 blocked on
some networks). HYCOM publishes the *same* NRL HYCOM+NCODA GLB 1/12 deg analysis
through its own THREDDS server, which exposes a NetcdfSubset (NCSS) endpoint over
plain HTTPS. This script talks to that endpoint instead, and writes a file with
exactly the same contract as `fetch_model.py` so `scripts.ingest_netcdf` needs no
changes.

Honest by design
----------------
* Only variables that come back with finite, physically in-range values are written.
  Anything missing is reported in `warnings` rather than filled in.
* The composite is a mean over the timesteps actually sampled, and the exact
  window, stride and sample count are recorded in the file's global attributes.

Real source: NRL HYCOM+NCODA GLB 1/12 deg (GLBu0.08 expt_93.0), public domain.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import warnings
from datetime import datetime, timezone

import numpy as np
import requests

NCSS_BASE = "https://ncss.hycom.org/thredds/ncss/grid"
# NRL HYCOM+NCODA GLBu0.08, expt_93.0 - the same product the CoastWatch ERDDAP
# mirror serves (Hindcast Data: Sep-19-2018 to Dec-08-2018).
TS_DATASET = "GLBu0.08/expt_93.0/ts3z"
UV_DATASET = "GLBu0.08/expt_93.0/uv3z"
DATASET_ID = "GLBu0.08-expt_93.0"

# The published archive covers 2018-09-19 .. 2018-12-08.
DEFAULT_START = "2018-09-19T00:00:00Z"
DEFAULT_END = "2018-12-08T00:00:00Z"

# GLB 0.08 is 3-hourly, so this many 3-hour steps span roughly one day.
STEPS_PER_DAY = 8

DEFAULT_BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)
DEFAULT_DEPTHS = [0, 20, 50, 100, 200, 500, 1000, 2000]

# Guard rails so a bad subset can never be written out as if it were real data.
VALUE_RANGES = {
    "sea_water_temperature": (-2.0, 40.0),
    "sea_water_salinity": (0.0, 45.0),
    "sea_water_current_speed": (0.0, 5.0),
    "sea_water_current_u": (-5.0, 5.0),
    "sea_water_current_v": (-5.0, 5.0),
}


def _n_css_url(dataset: str) -> str:
    return f"{NCSS_BASE}/{dataset}"


def _time_stride(start: str, end: str, samples: int) -> int:
    """NCSS timeStride counts 3-hourly steps; pick one that yields ~`samples`."""
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(end.replace("Z", "+00:00"))
    total_hours = max((t1 - t0).total_seconds() / 3600.0, STEPS_PER_DAY)
    total_steps = max(int(total_hours / 3.0), 1)
    return max(1, total_steps // max(samples, 1))


def _fetch_subset(dataset: str, variables: list[str], box: dict,
                  start: str, end: str, stride: int, samples: int,
                  timeout: int) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """Download one NCSS subset and return (var -> (depth, lat, lon), depth, lat, lon).

    The time axis is reduced to its mean here so the caller only ever handles the
    3D fields the ingest contract expects.
    """
    url = _n_css_url(dataset)
    params = {
        "var": variables,
        "north": box["lat1"],
        "south": box["lat0"],
        "east": box["lon1"],
        "west": box["lon0"],
        "horizStride": stride,
        "time_start": start,
        "time_end": end,
        "timeStride": _time_stride(start, end, samples),
        "accept": "netcdf4",
    }
    print(f"  GET {url}\n      vars={variables} stride={stride} "
          f"timeStride={params['timeStride']} window={start}..{end}")
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()

    import xarray as xr

    fd, tmp = tempfile.mkstemp(suffix=".nc")
    os.close(fd)
    try:
        with open(tmp, "wb") as fh:
            fh.write(resp.content)
        ds = xr.open_dataset(tmp, decode_times=False)
        try:
            out: dict[str, np.ndarray] = {}
            for name in variables:
                if name not in ds.variables:
                    continue
                arr = np.asarray(ds[name].values, dtype=float)
                # (time, depth, lat, lon) -> (depth, lat, lon), NaN-safe.
                # The 40 z-levels include levels that are entirely land or below
                # the deepest wet cell, so an all-NaN slice here is expected.
                if arr.ndim == 4:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        arr = np.nanmean(arr, axis=0)
                out[name] = arr
            depth = np.asarray(ds["depth"].values, dtype=float).ravel()
            lat = np.asarray(ds["lat"].values, dtype=float).ravel()
            lon = np.asarray(ds["lon"].values, dtype=float).ravel()
        finally:
            ds.close()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return out, depth, lat, lon


def _select_levels(field: np.ndarray, depth: np.ndarray,
                   want: list[float]) -> tuple[list[float], np.ndarray]:
    """Pick the source level nearest each requested depth; keep only finite data."""
    picked: list[float] = []
    planes: list[np.ndarray] = []
    for target in want:
        if depth.size == 0:
            continue
        idx = int(np.argmin(np.abs(depth - target)))
        actual = float(depth[idx])
        plane = np.asarray(field[idx], dtype=float)
        plane = np.where(np.isfinite(plane) & (np.abs(plane) < 1e30), plane, np.nan)
        if not np.isfinite(plane).any():
            continue
        picked.append(actual)
        planes.append(plane)
    if not planes:
        return [], np.empty((0, 0, 0))
    return picked, np.stack(planes, axis=0)


def fetch_model(start: str, end: str, samples: int, depths: list[float], box: dict,
                stride: int, output: str, timeout: int = 600) -> dict:
    """Composite the real HYCOM grid over the sampled window and write NetCDF."""
    import xarray as xr

    warnings: list[str] = []
    print(f"Fetching {DATASET_ID} from HYCOM NCSS ...")

    print("[1/2] temperature + salinity")
    ts, ts_depth, ts_lat, ts_lon = _fetch_subset(
        TS_DATASET, ["water_temp", "salinity"], box, start, end, stride, samples, timeout)

    print("[2/2] currents")
    uv, uv_depth, uv_lat, uv_lon = _fetch_subset(
        UV_DATASET, ["water_u", "water_v"], box, start, end, stride, samples, timeout)

    if not ts and not uv:
        sys.exit("No variables downloaded - check connectivity to ncss.hycom.org, then retry.")

    # Re-home everything onto one consistent grid (the ts3z grid wins).
    out_lat = ts_lat if ts_lat.size else uv_lat
    out_lon = ts_lon if ts_lon.size else uv_lon

    def _regrid(field: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Nearest-neighbour resample onto the output grid."""
        if field.size == 0:
            return np.empty((0, out_lat.size, out_lon.size))
        if lat.size == out_lat.size and lon.size == out_lon.size:
            return field
        li = np.abs(out_lat[:, None] - lat[None, :]).argmin(axis=1)
        oi = np.abs(out_lon[:, None] - lon[None, :]).argmin(axis=0)
        return field[:, li][:, :, oi]

    ds_vars: dict[str, xr.DataArray] = {}
    present: list[str] = []

    def _add(name: str, levels: list[float], arr: np.ndarray) -> None:
        lo, hi = VALUE_RANGES[name]
        arr = np.where(np.isfinite(arr) & (arr >= lo) & (arr <= hi), arr, np.nan)
        arr = np.where(np.isfinite(arr), arr, np.nan)
        if not np.isfinite(arr).any():
            warnings.append(f"{name}: no finite in-range values - omitted.")
            return
        ds_vars[name] = xr.DataArray(
            arr, dims=["depth", "lat", "lon"],
            coords={"depth": levels, "lat": out_lat, "lon": out_lon})
        present.append(name)

    if "water_temp" in ts:
        lv, arr = _select_levels(ts["water_temp"], ts_depth, depths)
        if lv:
            _add("sea_water_temperature", lv, arr)
        else:
            warnings.append("sea_water_temperature: no finite values at any requested level.")
    else:
        warnings.append("sea_water_temperature: variable absent from source.")

    if "salinity" in ts:
        lv, arr = _select_levels(ts["salinity"], ts_depth, depths)
        if lv:
            _add("sea_water_salinity", lv, arr)
        else:
            warnings.append("sea_water_salinity: no finite values at any requested level.")
    else:
        warnings.append("sea_water_salinity: variable absent from source.")

    if "water_u" in uv and "water_v" in uv:
        lu, au = _select_levels(uv["water_u"], uv_depth, depths)
        lv_, av = _select_levels(uv["water_v"], uv_depth, depths)
        common = sorted(set(lu) & set(lv_))
        if common and au.shape[1:] == _regrid(av, uv_lat, uv_lon).shape[1:]:
            u_map = dict(zip(lu, au))
            v_grid = _regrid(av, uv_lat, uv_lon)
            v_map = dict(zip(lv_, v_grid))
            u_stack = np.stack([u_map[d] for d in common], axis=0)
            v_stack = np.stack([v_map[d] for d in common], axis=0)
            _add("sea_water_current_speed", common, np.hypot(u_stack, v_stack))
            _add("sea_water_current_u", common, u_stack)
            _add("sea_water_current_v", common, v_stack)
        else:
            warnings.append("currents: no common finite depth levels between u and v - omitted.")
    else:
        warnings.append("currents: water_u / water_v absent from source.")

    if not ds_vars:
        sys.exit("No finite variables after compositing - nothing to write.")

    mid_time = np.datetime64(
        datetime.fromtimestamp(
            (datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp()
             + datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp()) / 2,
            tz=timezone.utc).replace(tzinfo=None), "s")

    out = xr.Dataset(ds_vars).expand_dims(time=[mid_time])
    out["time"].attrs.update(axis="T", standard_name="time")
    out["lat"].attrs.update(axis="Y", standard_name="latitude", units="degrees_north")
    out["lon"].attrs.update(axis="X", standard_name="longitude", units="degrees_east")
    out["depth"].attrs.update(axis="Z", standard_name="depth", units="m", positive="down")
    out["sea_water_temperature"].attrs.update(standard_name="sea_water_temperature", units="degC")
    if "sea_water_salinity" in out.data_vars:
        out["sea_water_salinity"].attrs.update(standard_name="sea_water_salinity", units="PSU")
    if "sea_water_current_speed" in out.data_vars:
        out["sea_water_current_speed"].attrs.update(standard_name="sea_water_speed", units="m/s")
    if "sea_water_current_u" in out.data_vars:
        out["sea_water_current_u"].attrs.update(standard_name="eastward_sea_water_velocity", units="m/s")
    if "sea_water_current_v" in out.data_vars:
        out["sea_water_current_v"].attrs.update(standard_name="northward_sea_water_velocity", units="m/s")

    out.attrs.update(
        title="NRL HYCOM+NCODA GLBu0.08 model 3D grid, mean over sampled window",
        dataset_id=DATASET_ID,
        source=("US Navy HYCOM+NCODA GLB 1/12 deg, expt_93.0, via HYCOM THREDDS NetcdfSubset "
                "(ncss.hycom.org). Public domain."),
        spatial_extent="Indian-Ocean region",
        composite=("Arithmetic mean of the timesteps returned by NCSS. "
                   f"window={start}..{end}, timeStride={_time_stride(start, end, samples)} "
                   f"(3-hourly steps), horizStride={stride}, lat={box['lat0']}..{box['lat1']}, "
                   f"lon={box['lon0']}..{box['lon1']}."),
        history=f"Fetched & composited by scripts.fetch_model_ncss {datetime.now(timezone.utc).isoformat()}",
        license="Public domain (NRL HYCOM+NCODA, US Navy). Attribution: HYCOM consortium.",
    )
    parent = os.path.dirname(os.path.abspath(output))
    os.makedirs(parent, exist_ok=True)
    out.to_netcdf(output)

    cells = int(np.isfinite(ds_vars[present[0]].values).sum())
    levels = sorted({float(d) for d in ds_vars[present[0]].coords["depth"].values})
    print(f"Wrote {output}")
    print(f"  variables={present}")
    print(f"  levels={levels}")
    print(f"  grid={out_lat.size} lat x {out_lon.size} lon, cells={cells}")
    for w in warnings:
        print(f"  warning: {w}")
    return {"output": output, "dataset": DATASET_ID, "variables": present,
            "depths": levels, "warnings": warnings}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Fetch & composite a real HYCOM 3D ocean-model grid to NetCDF via HYCOM NCSS.")
    p.add_argument("--start", default=DEFAULT_START, help=f"ISO start (default {DEFAULT_START}).")
    p.add_argument("--end", default=DEFAULT_END, help=f"Iso end (default {DEFAULT_END}).")
    p.add_argument("--samples", type=int, default=8,
                   help="Approximate number of timesteps to average over (default 8).")
    p.add_argument("--stride", type=int, default=2,
                   help="NCSS horizStride; 2 = ~1/6 deg (default 2).")
    p.add_argument("--depths", default=None,
                   help="Comma-separated depth levels in metres "
                        f"(default {','.join(map(str, DEFAULT_DEPTHS))}).")
    p.add_argument("--lat0", type=float, default=DEFAULT_BOX["lat0"])
    p.add_argument("--lat1", type=float, default=DEFAULT_BOX["lat1"])
    p.add_argument("--lon0", type=float, default=DEFAULT_BOX["lon0"])
    p.add_argument("--lon1", type=float, default=DEFAULT_BOX["lon1"])
    p.add_argument("--output", default=None, help="Output .nc path.")
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()

    box = dict(lat0=args.lat0, lat1=args.lat1, lon0=args.lon0, lon1=args.lon1)
    if box["lat1"] <= box["lat0"] or box["lon1"] <= box["lon0"]:
        sys.exit("Invalid box: lat1>lat0 and lon1>lon0 required.")
    depths = [float(d) for d in (args.depths or ",".join(map(str, DEFAULT_DEPTHS))).split(",")]

    slug = f"{args.start[:10]}_{args.end[:10]}"
    output = args.output or f"C:\\Project 2.0\\backend\\data\\model\\hycom_ncss_{slug}.nc"

    try:
        fetch_model(args.start, args.end, args.samples, depths, box,
                    args.stride, output, timeout=args.timeout)
    except requests.RequestException as exc:
        sys.exit(f"Download failed ({exc}). Check connectivity to ncss.hycom.org, then retry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
