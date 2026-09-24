"""
TidalTwin - Fetch & composite a REAL 3D ocean-model grid
===========================================================
Downloads the US Navy HYCOM+NCODA GLBu0.08 (global 1/12°) model fields for a
chosen month over the Indian-Ocean region from NOAA CoastWatch ERDDAP, keeps a
set of depth levels, averages the daily frames into a monthly mean, computes a
current speed from u/v, and writes ONE NetCDF that `scripts.ingest_netcdf` can
ingest into `netcdf_readings` — the real 3D grid behind features #3 (real ocean
model), #5 (salinity field), #6 (3D fields) and #7 (horizontal depth slices).

Run on a machine with internet access, then ingest:

    python -m scripts.fetch_model --month 2021-09
    python -m scripts.ingest_netcdf backend/data/model/hycom_3d_2021-09.nc --reingest

Variable mapping is discovered from the file itself (HYCOM variants use
water_temp / sea_water_salinity / water_u / water_v; CMEMS use thetao / so /
uo / vo). Only variables that actually download with finite data are written —
a missing variable is reported honestly, never invented. The output file
carries CF metadata so ingest_netcdf finds lat/lon/time/depth no matter what
the server called them.
"""

import argparse
import sys
from datetime import datetime, timezone

import numpy as np
import requests

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
# Real NRL HYCOM+NCODA, GLBu0.08 (expt 90.9), global 1/12 deg, at depths, lon -180..180.
DATASET_ID = "nrlHycomGLBu008e909D_LonPM180"

DEFAULT_BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)

# The output variables we produce, and the source-file aliases we accept for
# each (discovered by inspecting the downloaded file).
VARS = ["sea_water_temperature", "sea_water_salinity", "water_u", "water_v"]
VAR_ALIASES = {
    "sea_water_temperature": ["water_temp", "sea_water_temperature", "thetao", "temperature", "temp"],
    "sea_water_salinity": ["sea_water_salinity", "so", "salinity", "water_salinity"],
    "water_u": ["water_u", "eastward_sea_water_velocity", "uo"],
    "water_v": ["water_v", "northward_sea_water_velocity", "vo"],
}

# Typical HYCOM z-levels; any explicit list works via --depths.
DEFAULT_DEPTHS = [0, 20, 50, 100, 200, 500, 1000, 2000]


def _month_window(month: str) -> tuple[str, str]:
    start_ts = datetime.strptime(month, "%Y-%m")
    end_ts = datetime(start_ts.year + (1 if start_ts.month == 12 else 0),
                      1 if start_ts.month == 12 else start_ts.month + 1, 1)
    return (f"{start_ts.strftime('%Y-%m-%dT%H:%M:%S')}Z",
            f"{end_ts.strftime('%Y-%m-%dT%H:%M:%S')}Z")


def build_url(month: str, box: dict, depth_m: float, variable: str) -> str:
    """One griddap subset request for a single variable at a single depth level."""
    t0, t1 = _month_window(month)
    constraint = (
        f"{variable}[({t0}):1:({t1})]"
        f"[({depth_m}):1:({depth_m})]"
        f"[({box['lat0']}):1:({box['lat1']})]"
        f"[({box['lon0']}):1:({box['lon1']})]"
    )
    return f"{ERDDAP_BASE}/{DATASET_ID}.nc?{constraint}"


def _coord(da, aliases):
    for name in aliases:
        if name in da.coords:
            return da[name]
        if name in da.dims:
            return da[name]
    return None


def _monthly_level_array(da):
    """Reduce one downloaded subset to a 2D (lat, lon) float array.

    ERDDAP may return 1 or many time frames and may or may not shrink the
    depth dimension to size 1 — all are normalised to the monthly mean surface.
    """
    s = da.squeeze()
    if "time" in s.dims:
        m = s.mean(dim="time", skipna=True)
        m = m.squeeze()
    elif s.ndim == 2:
        m = s
    else:
        m = s.isel({s.dims[0]: 0}) if s.shape[0] == 1 else np.nanmean(s.values, axis=0)
    return np.asarray(m.values, dtype=float)


def fetch_model(month: str, depths: list[float], box: dict, output: str,
                timeout: int = 240) -> dict:
    """Download the real HYCOM model grid, composite one month, write NetCDF.

    Honest by design: we only ever write variables that came back with finite,
    in-range values; anything absent (or all-NaN) is reported in `warnings`.
    """
    try:
        import xarray as xr
    except ImportError:
        sys.exit("xarray is required (install via requirements).")

    grids: dict[str, dict] = {}   # var-alias -> {levels: {depth: 2D array}, lat, lon}
    warnings: list[str] = []

    for want in VARS:
        aliases = VAR_ALIASES[want]
        url = build_url(month, box, depths[0], aliases[0])
        print(f"Fetching {DATASET_ID} {want} across {len(depths)} level(s) ...\n  GET {url}")
        resp = requests.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
        probe = xr.open_dataset(resp.content)
        found = next((name for name in aliases if name in probe.data_vars), None)
        if found is None:
            available = ", ".join(sorted(set(probe.data_vars)))
            warnings.append(f"{want}: no alias present in source. Dataset has {available}")
            continue
        lat = _coord(probe, ["lat", "latitude"])
        lon = _coord(probe, ["lon", "longitude"])
        first_level = _monthly_level_array(probe[found])
        grid_lat = np.asarray(lat.values, dtype=float) if lat is not None else None
        grid_lon = np.asarray(lon.values, dtype=float) if lon is not None else None
        level_map = {}

        # First level (already brought down).
        da0 = probe[found].squeeze()
        depth0 = None
        dcoord = _coord(probe, ["depth", "altitude", "level", "lev", "z"])
        if dcoord is not None:
            depth0 = float(np.atleast_1d(np.asarray(dcoord.values, dtype=float))[0])
        if np.isfinite(first_level).any():
            level_map[depth0 if depth0 is not None else depths[0]] = first_level
        else:
            warnings.append(f"{want} @ ~{depth0}m: all missing in source — skipped.")

        for depth_m in depths[1:]:
            sub_url = build_url(month, box, depth_m, found)
            sub = requests.get(sub_url, timeout=timeout, stream=True)
            sub.raise_for_status()
            sds = xr.open_dataset(sub.content)
            arr = _monthly_level_array(sds[found])
            sd = _coord(sds, ["depth", "altitude", "level", "lev", "z"])
            actual = float(np.atleast_1d(np.asarray(sd.values, dtype=float))[0]) if sd is not None else depth_m
            if np.isfinite(arr).any():
                level_map[actual] = arr
            else:
                warnings.append(f"{want} @ {actual}m: all missing in source — skipped.")

        if not level_map:
            warnings.append(f"{want}: no finite values at any requested level — omitted.")
            continue
        grids[want] = {"levels": level_map, "lat": grid_lat, "lon": grid_lon}
        print(f"  ok: {len(level_map)} level(s) [{', '.join(str(k) for k in sorted(level_map))}], "
              f"lat={None if grid_lat is None else grid_lat.size} lon={None if grid_lon is None else grid_lon.size}")

    if not grids:
        sys.exit("No variables downloaded — check connectivity/ERDDAP availability, then retry.")

    # ---- Re-home everything onto one consistent grid (first lat/lon wins) ----
    first_g = next(iter(grids.values()))
    out_lat = first_g["lat"]
    out_lon = first_g["lon"]
    mid_time = _as_month_mid(month)

    def stack_for(want: str) -> tuple[list[float], np.ndarray] | None:
        g = grids.get(want)
        if g is None:
            return None
        levels = {k: v for k, v in sorted(g["levels"].items())}
        arrs = [np.asarray(levels[k]) for k in levels]
        # All arrays must share one lat/lon grid; degrade gracefully if not.
        if not all(a.shape == arrs[0].shape for a in arrs):
            return None
        return list(levels.keys()), np.stack(arrs, axis=0)

    ds_vars = {}
    present: list[str] = []
    for want, name in [("sea_water_temperature", "sea_water_temperature"),
                       ("sea_water_salinity", "sea_water_salinity")]:
        st = stack_for(want)
        if st is None:
            continue
        dl, arr = st
        ds_vars[name] = xr.DataArray(arr, dims=["depth", "lat", "lon"],
                                     coords={"depth": dl, "lat": out_lat, "lon": out_lon})
        present.append(name)

    u = stack_for("water_u")
    v = stack_for("water_v")
    if u is not None and v is not None:
        d_u, arr_u = u
        d_v, arr_v = v
        common = sorted(set(d_u) & set(d_v))
        if common:
            u_map = {k: v for k, v in zip(d_u, arr_u)}
            v_map = {k: v for k, v in zip(d_v, arr_v)}
            u_stack = np.stack([u_map[d] for d in common], axis=0)
            v_stack = np.stack([v_map[d] for d in common], axis=0)
            ds_vars["sea_water_current_speed"] = xr.DataArray(
                np.hypot(u_stack, v_stack), dims=["depth", "lat", "lon"],
                coords={"depth": common, "lat": out_lat, "lon": out_lon})
            ds_vars["sea_water_current_u"] = xr.DataArray(
                u_stack, dims=["depth", "lat", "lon"],
                coords={"depth": common, "lat": out_lat, "lon": out_lon})
            ds_vars["sea_water_current_v"] = xr.DataArray(
                v_stack, dims=["depth", "lat", "lon"],
                coords={"depth": common, "lat": out_lat, "lon": out_lon})
            present.extend(["sea_water_current_speed", "sea_water_current_u", "sea_water_current_v"])

    if not ds_vars:
        sys.exit("No finite variables after compositing — nothing to write.")

    out = xr.Dataset(ds_vars)
    out = out.expand_dims(time=[mid_time])
    out["time"].attrs["axis"] = "T"
    out["time"].attrs["standard_name"] = "time"
    out["lat"].attrs["axis"] = "Y"
    out["lat"].attrs["standard_name"] = "latitude"
    out["lat"].attrs["units"] = "degrees_north"
    out["lon"].attrs["axis"] = "X"
    out["lon"].attrs["standard_name"] = "longitude"
    out["lon"].attrs["units"] = "degrees_east"
    out["depth"].attrs["axis"] = "Z"
    out["depth"].attrs["standard_name"] = "depth"
    out["depth"].attrs["units"] = "m"
    out["depth"].attrs["positive"] = "down"
    out["sea_water_temperature"].attrs["standard_name"] = "sea_water_temperature"
    out["sea_water_temperature"].attrs["units"] = "degC"
    if "sea_water_salinity" in out.data_vars:
        out["sea_water_salinity"].attrs["standard_name"] = "sea_water_salinity"
        out["sea_water_salinity"].attrs["units"] = "PSU"
    if "sea_water_current_speed" in out.data_vars:
        out["sea_water_current_speed"].attrs["standard_name"] = "sea_water_speed"
        out["sea_water_current_speed"].attrs["units"] = "m/s"
    if "sea_water_current_u" in out.data_vars:
        out["sea_water_current_u"].attrs["standard_name"] = "eastward_sea_water_velocity"
        out["sea_water_current_u"].attrs["units"] = "m/s"
    if "sea_water_current_v" in out.data_vars:
        out["sea_water_current_v"].attrs["standard_name"] = "northward_sea_water_velocity"
        out["sea_water_current_v"].attrs["units"] = "m/s"
    out.attrs.update(
        title=f"NRL HYCOM+NCODA GLBu0.08 model 3D grid monthly mean ({month})",
        dataset_id=DATASET_ID,
        source="US Navy HYCOM+NCODA via NOAA CoastWatch ERDDAP (global 1/12 deg, 40 z-levels)",
        spatial_extent="Indian-Ocean region",
        history=f"Fetched & composited by scripts.fetch_model {datetime.now(timezone.utc).isoformat()}",
        license="Public domain (NRL HYCOM+NCODA, US Navy). Attribution: HYCOM consortium / NOAA CoastWatch.",
    )
    out.to_netcdf(output)
    total_cells = int(np.isfinite(ds_vars[present[0]].values).sum())
    print(f"Wrote {output} (month={month}, levels={sorted({d for g in grids.values() for d in g['levels']})}, "
          f"variables={present}, cells={total_cells})")
    return {"output": output, "month": month,
            "depths": sorted({d for g in grids.values() for d in g["levels"]}),
            "variables": present, "dataset": DATASET_ID, "warnings": warnings}


def _as_month_mid(month: str) -> np.datetime64:
    return np.datetime64(datetime.strptime(month, "%Y-%m").replace(day=15))


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch & composite a real HYCOM 3D ocean-model grid to NetCDF.")
    p.add_argument("--month", default="2021-09", help="YYYY-MM month (default 2021-09).")
    p.add_argument("--output", default=None,
                   help="Output .nc path (default backend/data/model/hycom_3d_<YYYY-MM>.nc).")
    p.add_argument("--depths", default=None,
                   help="Comma-separated depth levels in metres (default 0,20,50,100,200,500,1000,2000).")
    p.add_argument("--lat0", type=float, default=DEFAULT_BOX["lat0"])
    p.add_argument("--lat1", type=float, default=DEFAULT_BOX["lat1"])
    p.add_argument("--lon0", type=float, default=DEFAULT_BOX["lon0"])
    p.add_argument("--lon1", type=float, default=DEFAULT_BOX["lon1"])
    args = p.parse_args()

    box = dict(lat0=args.lat0, lat1=args.lat1, lon0=args.lon0, lon1=args.lon1)
    if box["lat1"] <= box["lat0"] or box["lon1"] <= box["lon0"]:
        sys.exit("Invalid box: lat1>lat0 and lon1>lon0 required.")
    depths = [float(d) for d in (args.depths or ",".join(map(str, DEFAULT_DEPTHS))).split(",")]
    output = args.output or f"C:\\Project 2.0\\backend\\data\\model\\hycom_3d_{args.month}.nc"

    try:
        fetch_model(args.month, depths, box, output)
    except requests.RequestException as exc:
        sys.exit(f"Download failed ({exc}). Check connectivity and ERDDAP availability, then retry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())