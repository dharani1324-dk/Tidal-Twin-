"""
TidalTwin - Fetch real Argo BGC float profile files (dissolved oxygen) from the Argo GDAC
==========================================================================================
Downloads REAL Argo BGC float profile NetCDF files so `scripts.ingest_argobgc` can
ingest dissolved oxygen (DOXY) into `dissolved_oxygen_samples`.

How it works (fully documented, no private endpoints):
  1. Downloads the official Argo GDAC BGC float index
     `ar_index_global_prof.txt.gz` and filters for BGC floats (has DOXY variable).
  2. Filters floats whose most-recent profile falls inside the monitored region
     (default: Indian-Ocean box) and after `--since`.
  3. Downloads each float's `*_prof.nc` (the float-level file containing all
     its profiles) over HTTPS from a GDAC fileServer into data/argobgc.

Run on a machine with internet access, then ingest:

    python -m scripts.fetch_argobgc --limit 6
    python -m scripts.ingest_argobgc backend/data/argobgc

Provenance is printed on every run and preserved end-to-end: `ingest_argobgc`
stores `source_file` per row, and the twin future/live dashboards label real
rows with their GDAC file path.

References:
- https://argo.ucsd.edu/data/data-from-gdacs (GDACs + index files)
- USGODAE GDAC layout/directories: https://www.usgodae.org/pub/outgoing/argo
- Argo BGC data management: https://argo.ucsd.edu/biogeochemical-argo/
"""

import argparse
import gzip
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import requests

# GDAC roots that expose the same tree over HTTPS:
#   usgodae : the US GDAC directory (index + dac/... file hierarchy)
#   ifremer : the Euro-Argo GDAC mirrored via Ifremer THREDDS fileServer
GDACS = {
    "usgodae": "https://www.usgodae.org/pub/outgoing/argo",
    "ifremer": "https://tds0.ifremer.fr/thredds/fileServer/argo",
}
INDEX_FILENAME = "ar_index_global_prof.txt.gz"

# The monitored Indian-Ocean box (matches scripts.fetch_chlor / fetch_argo).
DEFAULT_BOX = dict(lat0=0.0, lat1=26.0, lon0=60.0, lon1=100.0)
DEFAULT_SINCE_DAYS = 120


def _date_parse(raw: str) -> datetime | None:
    """Argo index dates are YYYYMMDDHHMMSS; be lenient about QCs/bad rows."""
    raw = (raw or "").strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _load_float_index(root: str, timeout: int = 120) -> list[dict]:
    """Download + decompress the GDAC float index into order-preserving dicts."""
    url = f"{root}/{INDEX_FILENAME}"
    print(f"GET {url}")
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    text = gzip.decompress(resp.content).decode("utf-8", errors="replace")
    print(f"Loaded {len(resp.content) / 1e6:.1f} MB of index data")

    floats: list[dict] = []
    lines = text.splitlines()
    header = lines[0].split("\t")
    cols = {name: i for i, name in enumerate(header)}
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        row = {name: parts[i].strip() for name, i in cols.items()}
        floats.append(row)
    return floats


def _in_box(lat: str, lon: str, box: dict) -> bool:
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return box["lat0"] <= la <= box["lat1"] and box["lon0"] <= lo <= box["lon1"]


def _has_doxy(parameters: str) -> bool:
    """Check if the float's parameter list includes DOXY (dissolved oxygen)."""
    if not parameters:
        return False
    # Parameters are comma-separated like "TEMP,PSAL,DOXY,CHLA"
    return "DOXY" in parameters.upper()


def select_floats(floats: list[dict], box: dict, since: datetime,
                  limit: int, only_wmos: list[str] | None) -> list[dict]:
    """Order floats newest-first, then filter by box/time (or explicit WMOs).
    
    Only selects floats that have DOXY (dissolved oxygen) in their parameters.
    """
    dated: list[dict] = []
    for f in floats:
        wmo = f.get("wmo", "").strip()
        fpath = f.get("file", "").strip()
        parameters = f.get("parameters", "").strip()
        if not wmo or not fpath or not fpath.startswith("dac/"):
            continue
        if not _has_doxy(parameters):
            continue
        if only_wmos and wmo not in only_wmos:
            continue
        if not only_wmos:
            if not _in_box(f.get("latitude", ""), f.get("longitude", ""), box):
                continue
            d = _date_parse(f.get("date_last") or f.get("date") or f.get("date_update") or "")
            if d is None or d < since:
                continue
            f["_date"] = d
        else:
            f["_date"] = _date_parse(f.get("date_last") or f.get("date") or "") or since
        dated.append(f)

    dated.sort(key=lambda f: f["_date"], reverse=True)
    return dated[: max(limit, len(only_wmos or [])) if only_wmos else limit]


def fetch_profiles(floats: list[dict], root: str, output_dir: Path,
                   force: bool = False, gdac_name: str = "usgodae",
                   timeout: int = 120) -> list[dict]:
    """Download each float's profile file. Returns a per-file summary list."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for f in floats:
        fpath = f["file"]                 # e.g. dac/coriolis/3901234/3901234_prof.nc
        name = Path(fpath).name           # e.g. 3901234_prof.nc
        dest = output_dir / name
        if dest.exists() and not force:
            print(f"  exists (skip): {name}")
            results.append({"file": name, "skipped": True})
            continue
        url = f"{root}/{fpath}"
        print(f"  GET {url}")
        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            print(f"  saved {name} ({len(resp.content) / 1e6:.2f} MB, float {f.get('wmo')})")
            results.append({"file": name, "float_id": f.get("wmo"),
                            "bytes": len(resp.content), "gdac": gdac_name})
        except requests.RequestException as exc:
            print(f"  failed {name}: {exc}")
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch real Argo BGC float profile NetCDFs (with DOXY) from the GDAC.")
    p.add_argument("--gdac", choices=sorted(GDACS), default="usgodae",
                   help="Which GDAC mirror to download from (default usgodae).")
    p.add_argument("--limit", type=int, default=6,
                   help="Max floats to download (default 6).")
    p.add_argument("--since", default=None,
                   help="Only floats with a profile newer than YYYY-MM-DD "
                        "(default: last 120 days).")
    p.add_argument("--lat0", type=float, default=DEFAULT_BOX["lat0"])
    p.add_argument("--lat1", type=float, default=DEFAULT_BOX["lat1"])
    p.add_argument("--lon0", type=float, default=DEFAULT_BOX["lon0"])
    p.add_argument("--lon1", type=float, default=DEFAULT_BOX["lon1"])
    p.add_argument("--floats", default=None, help="Comma-separated WMO ids to fetch (bypasses box/time).")
    p.add_argument("--output-dir", default=None, help="Output folder (default backend/data/argobgc).")
    p.add_argument("--dry-run", action="store_true", help="Print the plan without downloading.")
    p.add_argument("--force", action="store_true", help="Re-download files that already exist.")
    args = p.parse_args()

    box = dict(lat0=args.lat0, lat1=args.lat1, lon0=args.lon0, lon1=args.lon1)
    if box["lat1"] <= box["lat0"] or box["lon1"] <= box["lon0"]:
        sys.exit("Invalid box: lat1>lat0 and lon1>lon0 required.")

    since = (datetime.now(timezone.utc) - timedelta(days=DEFAULT_SINCE_DAYS))
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            sys.exit("--since must be YYYY-MM-DD.")
    only_wmos = [w.strip() for w in args.floats.split(",")] if args.floats else None

    outcome_dir = Path(args.output_dir) if args.output_dir else Path(r"C:\Project 2.0\backend\data\argobgc")
    root = GDACS[args.gdac]

    try:
        index = _load_float_index(root)
    except requests.RequestException as exc:
        sys.exit(f"Could not load the GDAC index ({exc}). "
                 "Check connectivity and GDAC availability (https://www.usgodae.org/pub/outgoing/argo), "
                 "then retry.")

    selected = select_floats(index, box, since, args.limit, only_wmos)
    if not selected:
        sys.exit(f"No BGC floats with DOXY matched (box={box}, since={since.date()}, "
                 f"limit={args.limit}). Broaden the region/window or use --floats.")

    total = f"{len(selected)} BGC float(s) for region {box}" if not only_wmos else \
        f"{len(selected)} requested BGC float(s)"
    print(f"Selected {total}: " + ", ".join(f.get("wmo", "?") for f in selected))
    if args.dry_run:
        print("Dry run (no downloads):")
        for f in selected:
            print(f"  {root}/{f['file']}")
        return 0

    results = fetch_profiles(selected, root, outcome_dir, force=force, gdac_name=args.gdac)
    ok = [r for r in results if not r.get("skipped")]
    print(f"\nDownloaded {len(ok)} BGC file(s) into {outcome_dir}.")
    print("Next step — ingest the real BGC profiles (DOXY):")
    print(f"\n    python -m scripts.ingest_argobgc {outcome_dir}")
    if not ok:
        print("Nothing downloaded. Check connectivity / GDAC availability, then re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())