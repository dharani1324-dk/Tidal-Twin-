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
import os
import sys
from datetime import datetime, timezone

import numpy as np
import requests

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
DATASET_ID = "nesdisVHNchlaDaily"
VARIABLE = "chlor_a"
UNITS = "mg m-3"
STANDARD_NAME = "mass_concentration_of_chlorophyll_a_in_sea_water"

# `coastwatch.pfeg.noaa.gov` is unreachable from some networks (TCP 443 blocked),
# so we try a list of equivalent NOAA-operated ERDDAP mirrors before giving up.
# Every entry serves real, public-domain satellite ocean colour; the one that
# actually answered is recorded in the file's `dataset_id` / `source` attributes.
#   (base, dataset id, human-readable product)
MIRRORS = [
    (ERDDAP_BASE, DATASET_ID, "NOAA CoastWatch Geo-Polar Blended VIIRS-Himawari-NPP"),
    ("https://coastwatch.noaa.gov/erddap/griddap", "noaacwNPPVIIRSSQchlaMonthly",
     "NOAA CoastWatch NPP VIIRS square-pixel monthly Chlorophyll-a"),
    ("https://oceanwatch.pifsc.noaa.gov/erddap/griddap", "noaa_snpp_chla_monthly",
     "NASA OB.DAAC VIIRS-SNPP monthly ocean colour, via NOAA OceanWatch PIFSC"),
]

# Geo-Polar Blended VIIRS-Himawari-NPP ocean colour grid (~0.05 deg).
DEFAULT_BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)


def _month_window(month: str) -> tuple[str, str]:
    start_ts = datetime.strptime(month, "%Y-%m")
    end_ts = datetime(start_ts.year + (1 if start_ts.month == 12 else 0),
                      1 if start_ts.month == 12 else start_ts.month + 1, 1)
    return (f"{start_ts.strftime('%Y-%m-%dT%H:%M:%S')}Z",
            f"{end_ts.strftime('%Y-%m-%dT%H:%M:%S')}Z")


def _has_altitude(base: str, dataset_id: str, timeout: int) -> bool:
    """Some CoastWatch grids carry a length-1 `altitude` axis, making the data
    variable 4-D (time, altitude, lat, lon). A 3-index constraint then 404s."""
    try:
        dds = requests.get(f"{base}/{dataset_id}.dds", timeout=timeout)
        if dds.status_code != 200:
            return False
        return "altitude" in dds.text.split("NC_GLOBAL")[0]
    except requests.RequestException:
        return False


def build_url(base: str, dataset_id: str, month: str, box: dict,
              with_altitude: bool = False) -> tuple[str, dict]:
    t0, t1 = _month_window(month)
    lat_lon = (
        f"[(0.0):1:(1.0)]"
        f"[({box['lat0']}):1:({box['lat1']})]"
        f"[({box['lon0']}):1:({box['lon1']})]"
    )
    if with_altitude:
        constraint = f"{VARIABLE}[({t0}):1:({t1})]{lat_lon}"
    else:
        constraint = (
            f"{VARIABLE}[({t0}):1:({t1})]"
            f"[({box['lat0']}):1:({box['lat1']})]"
            f"[({box['lon0']}):1:({box['lon1']})]"
        )
    url = f"{base}/{dataset_id}.nc"
    return url, {constraint: ""}


def _download(url: str, params: dict, timeout: int) -> bytes:
    """Stream one griddap subset request."""
    resp = requests.get(url, params=params, timeout=timeout, stream=True)
    resp.raise_for_status()
    return resp.content


def fetch_and_composite(month: str, box: dict, output: str, timeout: int = 180,
                        mirrors: list[tuple[str, str, str]] | None = None) -> dict:
    import xarray as xr

    candidates = mirrors or MIRRORS
    payload = None
    used = None
    errors: list[str] = []

    for base, dataset_id, product in candidates:
        altitude = _has_altitude(base, dataset_id, timeout)
        url, params = build_url(base, dataset_id, month, box, with_altitude=altitude)
        print(f"Trying {dataset_id} for {month} over {box} (altitude axis: {altitude})")
        print(f"GET {url}")
        try:
            payload = _download(url, params, timeout)
        except (requests.RequestException, OSError) as exc:
            print(f"  unreachable ({type(exc).__name__}: {exc})")
            errors.append(f"{dataset_id}: {exc}")
            continue
        used = (base, dataset_id, product)
        print(f"  ok, {len(payload) / 1e6:.1f} MB")
        break

    if payload is None or used is None:
        sys.exit("No ERDDAP mirror answered.\n  " + "\n  ".join(errors)
                 + "\nCheck connectivity, then retry.")

    base, dataset_id, product = used
    ds = xr.open_dataset(payload)
    if VARIABLE not in ds.variables:
        available = ", ".join(sorted(ds.variables))
        sys.exit(f"Dataset {dataset_id} has no `{VARIABLE}` variable. Have: {available}")

    daily = ds[VARIABLE]
    if "altitude" in daily.dims:
        # Length-1 altitude axis: collapse it so the ingest contract stays 3-D.
        daily = daily.squeeze("altitude", drop=True)
    print(f"Loaded {len(daily.time)} frames; compositing monthly mean ...")
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
        title=f"Satellite Chlorophyll-a monthly mean ({month})",
        dataset_id=dataset_id,
        source=f"{product} via {base} (public domain)",
        variable=VARIABLE,
        spatial_extent="Indian-Ocean region",
        history=f"Composited by scripts.fetch_chlor {datetime.now(timezone.utc).isoformat()}",
        license="Public domain. Attribution: NASA OB.DAAC / NOAA CoastWatch.",
    )
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    out.to_netcdf(output)
    print(f"Wrote {output} (month={month}, cells={int(mean.notnull().sum())}, source={dataset_id})")
    return {"output": output, "month": month, "days": n_days,
            "cells": int(mean.notnull().sum()), "dataset": dataset_id, "product": product}


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch & composite real satellite Chl-a to NetCDF.")
    p.add_argument("--month", default="2021-09", help="YYYY-MM month to composite (default 2021-09).")
    p.add_argument("--output", default=None, help="Output .nc path (default backend/data/chl_monthly_<YYYY-MM>.nc).")
    p.add_argument("--lat0", type=float, default=DEFAULT_BOX["lat0"])
    p.add_argument("--lat1", type=float, default=DEFAULT_BOX["lat1"])
    p.add_argument("--lon0", type=float, default=DEFAULT_BOX["lon0"])
    p.add_argument("--lon1", type=float, default=DEFAULT_BOX["lon1"])
    p.add_argument("--base", default=None, help="Force a single ERDDAP griddap base URL.")
    p.add_argument("--dataset", default=None, help="Force a single ERDDAP dataset id.")
    args = p.parse_args()

    box = dict(lat0=args.lat0, lat1=args.lat1, lon0=args.lon0, lon1=args.lon1)
    if box["lat1"] <= box["lat0"] or box["lon1"] <= box["lon0"]:
        sys.exit("Invalid box: lat1>lat0 and lon1>lon0 required.")
    output = args.output or f"C:\\Project 2.0\\backend\\data\\chl_monthly_{args.month}.nc"

    if args.base or args.dataset:
        mirrors = [(args.base or ERDDAP_BASE, args.dataset or DATASET_ID,
                    args.dataset or DATASET_ID)]
    else:
        mirrors = None

    try:
        fetch_and_composite(args.month, box, output, mirrors=mirrors)
    except requests.RequestException as exc:
        sys.exit(f"Download failed ({exc}). Check connectivity and ERDDAP availability, then retry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())