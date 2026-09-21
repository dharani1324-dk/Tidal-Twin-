"""
TidalTwin - Fetch & composite a real satellite Chlorophyll-a grid
====================================================================
Downloads the NOAA CoastWatch Geo-Polar Blended VIIRS-Himawari-NPP daily
ocean-colour product (`nesdisVHNchlaDaily`, 5 km) from ERDDAP for a chosen
month over the Indian-Ocean region, averages the daily frames into a single
monthly mean, and writes one NetCDF that `scripts.ingest_netcdf` can ingest.

Run on a machine with internet access, then ingest:

    python -m scripts.fetch_chlor --month 2021-09
    python -m scripts.ingest_netcdf backend/data/chl_monthly_2021-09.nc --reingest

Provenance is printed on every run and embedded in the file global attrs so
the ingested rows stay attributable to the real satellite source.
"""

import argparse
import sys
from datetime import datetime, timezone

import numpy as np
import requests

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
DATASET_ID = "nesdisVHNchlaDaily"
VARIABLE = "chlor_a"
UNITS = "mg m-3"
STANDARD_NAME = "mass_concentration_of_chlorophyll_a_in_sea_water"

# Geo-Polar Blended VIIRS-Himawari-NPP ocean colour grid (~0.05 deg).
DEFAULT_BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)


def _month_window(month: str) -> tuple[str, str]:
    start_ts = datetime.strptime(month, "%Y-%m")
    end_ts = datetime(start_ts.year + (1 if start_ts.month == 12 else 0),
                      1 if start_ts.month == 12 else start_ts.month + 1, 1)
    return (f"{start_ts.strftime('%Y-%m-%dT%H:%M:%S')}Z",
            f"{end_ts.strftime('%Y-%m-%dT%H:%M:%S')}Z")


def build_url(month, box) -> tuple[str, dict]:
    t0, t1 = _month_window(month)
    constraint = (
        f"{VARIABLE}[({t0}):1:({t1})]"
        f"[({box['lat0']}):1:({box['lat1']})]"
        f"[({box['lon0']}):1:({box['lon1']})]"
    )
    url = f"{ERDDAP_BASE}/{DATASET_ID}.nc"
    return url, {constraint: ""}


def fetch_and_composite(month: str, box: dict, output: str, timeout: int = 180) -> dict:
    try:
        import xarray as xr
    except ImportError:
        sys.exit("xarray is required (install via requirements).")

    url, params = build_url(month, box)
    print(f"Fetching {DATASET_ID} for {month} over the region box {box} ...")
    print(f"GET {url}")
    resp = requests.get(url, params=params, timeout=timeout, stream=True)
    resp.raise_for_status()
    total = len(resp.content)
    print(f"Downloaded {total / 1e6:.1f} MB")

    ds = xr.open_dataset(resp.content)
    if VARIABLE not in ds.variables:
        available = ", ".join(sorted(ds.variables))
        sys.exit(f"Dataset has no `{VARIABLE}` variable. Have: {available}")

    daily = ds[VARIABLE]
    print(f"Loaded {len(daily.time)} daily frames; compositing monthly mean ...")
    mean = daily.mean(dim="time", skipna=True)
    n_days = len(daily.time)
    if float(mean.isnull().sum()) == 0:
        land = float((daily.isnull()).all(dim="time").sum())
        print(f"Warning: {int(land)} cells have no valid satellite retrievals (all-NaN) and are kept missing.")

    mid_time = np.datetime64(datetime.strptime(month, "%Y-%m").replace(day=15))
    mean = mean.expand_dims(time=[mid_time])
    out = mean.rename("chlor_a").to_dataset()
    out["time"].attrs["axis"] = "T"
    out["time"].attrs["standard_name"] = "time"
    out["lat"].attrs["axis"] = "Y"
    out["lat"].attrs["standard_name"] = "latitude"
    out["lon"].attrs["axis"] = "X"
    out["lon"].attrs["standard_name"] = "longitude"
    out["chlor_a"].attrs["standard_name"] = STANDARD_NAME
    out["chlor_a"].attrs["units"] = UNITS
    out.attrs.update(
        title=f"NOAA CoastWatch VIIRS-Himawari blended Chlorophyll-a monthly mean ({month})",
        dataset_id=DATASET_ID,
        variable=VARIABLE,
        spatial_extent="Indian-Ocean region",
        history=f"Composited by scripts.fetch_chlor {datetime.now(timezone.utc).isoformat()}",
        license="NOAA CoastWatch data are public. Attribution: NOAA CoastWatch/VIIRS-Himawari (5 km).",
    )
    out.to_netcdf(output)
    print(f"Wrote {output} (month={month}, cells={int(mean.notnull().sum())}, source={DATASET_ID})")
    return {"output": output, "month": month, "days": n_days, "cells": int(mean.notnull().sum()), "dataset": DATASET_ID}


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch & composite real satellite Chl-a to NetCDF.")
    p.add_argument("--month", default="2021-09", help="YYYY-MM month to composite (default 2021-09).")
    p.add_argument("--output", default=None, help="Output .nc path (default backend/data/chl_monthly_<YYYY-MM>.nc).")
    p.add_argument("--lat0", type=float, default=DEFAULT_BOX["lat0"])
    p.add_argument("--lat1", type=float, default=DEFAULT_BOX["lat1"])
    p.add_argument("--lon0", type=float, default=DEFAULT_BOX["lon0"])
    p.add_argument("--lon1", type=float, default=DEFAULT_BOX["lon1"])
    args = p.parse_args()

    box = dict(lat0=args.lat0, lat1=args.lat1, lon0=args.lon0, lon1=args.lon1)
    if box["lat1"] <= box["lat0"] or box["lon1"] <= box["lon0"]:
        sys.exit("Invalid box: lat1>lat0 and lon1>lon0 required.")
    output = args.output or f"C:\\Project 2.0\\backend\\data\\chl_monthly_{args.month}.nc"

    try:
        fetch_and_composite(args.month, box, output)
    except requests.RequestException as exc:
        sys.exit(f"Download failed ({exc}). Check connectivity and ERDDAP availability, then retry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())