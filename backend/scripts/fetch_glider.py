"""
TidalTwin - Fetch a REAL glider deployment (features #16/#17)
=================================================================
Downloads one glider deployment's measurements (physical + biogeochemical:
dissolved oxygen, chlorophyll, nitrate) from the IOOS National Glider Data
Assembly Center ERDDAP into a NetCDF that `scripts.ingest_glider` can ingest.

Run on a machine with internet access, then ingest:

    python -m scripts.fetch_glider --dataset ioos-gliderdac-sp011-20160602T1624 \
        --start 2016-06-02 --end 2016-09-01
    python -m scripts.ingest_glider backend/data/glider/ioos-gliderdac-sp011-20160602T1624.nc --reingest

Real deployments are listed at https://gliders.ioos.us/erddap (dataset ids all
start with `ioos-gliderdac-`). Only the fields we actually requested on the URL
are returned from the server, and only real, finite values survive ingestion —
a deployment without a BGC sensor simply reports those fields as unavailable.
"""

import argparse
import sys
from datetime import datetime, timezone

import requests

TABLEDAP_BASE = "https://gliders.ioos.us/erddap/tabledap"

# Physical + BGC fields (feature #16 glider / #17 CTD-BGC) requested from ERDDAP.
FIELDS = (
    "trajectory,time,latitude,longitude,pressure,depth,"
    "temperature,salinity,dissolved_oxygen,chlorophyll,nitrate"
)


def build_url(dataset_id: str, start: str | None, end: str | None) -> str:
    q = f"{TABLEDAP_BASE}/{dataset_id}.nc?{FIELDS}"
    constraints = []
    if start:
        constraints.append(f"time>={start}T00:00:00Z")
    if end:
        constraints.append(f"time<={end}T23:59:59Z")
    return q + ("&" + "&".join(constraints) if constraints else "")


def fetch_deployment(dataset_id: str, output: str, start: str | None = None,
                     end: str | None = None, timeout: int = 240) -> dict:
    """Download one real glider deployment subset and write it to a NetCDF."""
    try:
        import xarray as xr
    except ImportError:
        sys.exit("xarray is required (install via requirements).")

    url = build_url(dataset_id, start, end)
    print(f"Fetching {dataset_id} from IOOS National GliderDAC ...\n  GET {url}")
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    print(f"Downloaded {len(resp.content) / 1e6:.2f} MB")

    ds = xr.open_dataset(resp.content)
    n = int(ds.sizes.get("time", ds.sizes.get("obs", 0)))
    if n == 0:
        sys.exit(f"Dataset {dataset_id!r} returned no measurements in the requested window.")
    present = sorted(v for v in ("temperature", "salinity", "dissolved_oxygen", "chlorophyll", "nitrate")
                     if v in ds.data_vars)
    print(f"Measurements: {n} samples; physical+BGC fields present: {present}")

    ds.attrs.update(
        history=f"Fetched by scripts.fetch_glider {datetime.now(timezone.utc).isoformat()}",
        source="IOOS National Glider Data Assembly Center (NGDAC) via ERDDAP",
        dataset_id=dataset_id,
        license="Real-time glider data are provisional; acknowledge DBPs and the NGDAC.",
    )
    ds.to_netcdf(output)
    print(f"Wrote {output} ({n} samples, {len(present)} measured fields)")
    return {"output": output, "dataset": dataset_id, "samples": n, "fields": present}


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch a real glider deployment from the IOOS National GliderDAC.")
    p.add_argument("--dataset", required=True,
                   help="ERDDAP dataset id, e.g. ioos-gliderdac-sp011-20160602T1624 "
                        "(browse https://gliders.ioos.us/erddap).")
    p.add_argument("--start", default=None, help="Inclusive start date YYYY-MM-DD (optional).")
    p.add_argument("--end", default=None, help="Inclusive end date YYYY-MM-DD (optional).")
    p.add_argument("--output", default=None,
                   help="Output .nc path (default backend/data/glider/<dataset>.nc).")
    args = p.parse_args()

    output = args.output or f"C:\\Project 2.0\\backend\\data\\glider\\{args.dataset}.nc"
    try:
        fetch_deployment(args.dataset, output, start=args.start, end=args.end)
    except requests.RequestException as exc:
        sys.exit(f"Download failed ({exc}). Check connectivity and ERDDAP availability, then retry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())