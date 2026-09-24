"""
TidalTwin - CTD cast ingestion (feature #17)
=================================================
Reads a ship CTD / moored mini-CTD cast file (CSV with a `#` header, one sample
per row: depth against time) and stores every real measurement into
`ctd_profiles`, exactly like any other in-situ source.

Accepted columns (case-insensitive, aliases allowed):

  Required     : station / station_id / cast, depth / depth_m,
                 temperature / t / temp   (else salinity / sal / s)
  Optional     : latitude / lat, longitude / lon, time / timestamp / date,
                 salinity / sal / s, pressure, dissolved_oxygen / oxygen,
                 chlorophyll, nitrate, qc_flags

The station position is taken either per-row or from an optional
`latitude=`/`longitude=` line in the `#` header block (e.g. `# longitude: 83.2`).

Honesty rules (same as every other ingestion path):
  - rows with an unparseable depth or no T/sal are SKIPPED (never guessed)
  - rows with a station position uncorrectable into a real lat/lon are SKIPPED
  - when a file supplies neither a station position nor a per-row one, the
    cast is SKIPPED as "no position" — we never invent a location

Usage:
  .venv\\Scripts\\python -m scripts.ingest_ctd path\\to\\station_07.csv
  .venv\\Scripts\\python -m scripts.ingest_ctd path\\to\\ctd_dir --source "Cruise AR07"
"""

import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import SessionLocal
from app.models.ctd import CtdProfile

LAT_KEYS = ("latitude", "lat")
LON_KEYS = ("longitude", "lon")
TIME_KEYS = ("time", "timestamp", "date", "datetime")
STATION_KEYS = ("station", "station_id", "cast")
DEPTH_KEYS = ("depth", "depth_m", "depthm", "pressure_dbar")
TEMP_KEYS = ("temperature", "temp", "t", "temperature_c")
SAL_KEYS = ("salinity", "sal", "s", "psu")
OXY_KEYS = ("dissolved_oxygen", "oxygen", "o2", "oxygen_umol_l")
CHL_KEYS = ("chlorophyll", "chlorophyll_a", "chla")
NIT_KEYS = ("nitrate", "no3")
PRES_KEYS = ("pressure", "pressure_dbar_ctd")
QC_KEYS = ("qc_flags", "qc", "quality_flag")

TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d")


def _parse_time(raw) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _to_float(raw):
    if raw is None:
        return None
    try:
        v = float(str(raw).strip())
    except (ValueError, TypeError):
        return None
    return v if math.isfinite(v) else None


def _read_header(path: Path) -> dict:
    """Collect `# key: value` / `# key=value` header lines as metadata (e.g. the
    cast's fixed position or instrument name)."""
    meta = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("#"):
                break
            body = line.lstrip("# ").strip()
            if ":" in body:
                k, _, v = body.partition(":")
            elif "=" in body:
                k, _, v = body.partition("=")
            else:
                continue
            meta[k.strip().lower().replace(" ", "_")] = v.strip()
    return meta


def _rows_from(path: Path):
    """Yield dict rows (lowercased keys) from CSV with an optional `#` header."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return
    reader = csv.reader(lines)
    header = next(reader)
    for cells in reader:
        if len(cells) < len(header):
            continue
        yield {h.strip().lower(): v for h, v in zip(header, cells)}


def ingest_file(path: Path, source: str = "CTD cast import", limit: int | None = None) -> dict:
    """Parse one CTD cast file into ctd_profiles. Returns an honest summary."""
    parsed = skipped_bad = skipped_pos = inserted = 0
    meta = _read_header(path)
    station = meta.get("station") or meta.get("cast") or path.stem
    instrument = meta.get("instrument") or meta.get("instrument_type")

    rows = list(_rows_from(path))
    if not rows:
        return {"station": station, "parsed": 0, "inserted": 0,
                "skipped_bad": 0, "skipped_pos": 0, "source": source}

    # Station position: header metadata first, then the first valid per-row.
    fixed_lat = _to_float(meta.get("latitude") or meta.get("lat"))
    fixed_lon = _to_float(meta.get("longitude") or meta.get("lon"))

    samples = []
    for row in rows:
        parsed += 1
        depth = _to_float(next((row.get(k) for k in DEPTH_KEYS if row.get(k)), None))
        temp = _to_float(next((row.get(k) for k in TEMP_KEYS if row.get(k)), None))
        sal = _to_float(next((row.get(k) for k in SAL_KEYS if row.get(k)), None))
        if depth is None or (temp is None and sal is None):
            skipped_bad += 1
            continue
        lat = fixed_lat
        lon = fixed_lon
        if lat is None or lon is None:
            lat = _to_float(next((row.get(k) for k in LAT_KEYS if row.get(k)), None))
            lon = _to_float(next((row.get(k) for k in LON_KEYS if row.get(k)), None))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            skipped_pos += 1
            continue
        ts = _parse_time(next((row.get(k) for k in TIME_KEYS if row.get(k)), None))
        ts = ts or datetime(1970, 1, 1, tzinfo=timezone.utc)
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)

        pressure = _to_float(next((row.get(k) for k in PRES_KEYS if row.get(k)), None))
        oxy = _to_float(next((row.get(k) for k in OXY_KEYS if row.get(k)), None))
        chl = _to_float(next((row.get(k) for k in CHL_KEYS if row.get(k)), None))
        nit = _to_float(next((row.get(k) for k in NIT_KEYS if row.get(k)), None))
        qc = next((row.get(k) for k in QC_KEYS if row.get(k)), None) or None

        samples.append(dict(
            station_id=station, instrument=instrument, latitude=lat, longitude=lon,
            time=ts, depth_m=depth, temperature=temp, salinity=sal, pressure=pressure,
            dissolved_oxygen=oxy, chlorophyll=chl, nitrate=nit,
            qc_flags=str(qc) if qc is not None else None, source_file=str(path),
        ))
        if limit is not None and len(samples) >= limit:
            break

    with SessionLocal.begin() as db:
        seen: set[tuple[str, float, datetime]] = set()
        for s in samples:
            key = (s["station_id"], s["depth_m"], s["time"])
            if key in seen:
                continue
            exists = db.query(CtdProfile.id).filter(
                CtdProfile.station_id == s["station_id"],
                CtdProfile.depth_m == s["depth_m"],
                CtdProfile.time == s["time"],
            ).first()
            if exists:
                continue
            db.add(CtdProfile(**s))
            seen.add(key)
            inserted += 1

    return {
        "station": station,
        "parsed": parsed,
        "inserted": inserted,
        "skipped_bad": skipped_bad,
        "skipped_pos": skipped_pos,
        "source": source,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Ingest a ship CTD / mini-CTD cast file (CSV) into ctd_profiles."
    )
    parser.add_argument("file", help="Path to the CTD cast CSV file")
    parser.add_argument("--source", default="CTD cast import",
                        help="Source label stored on each ingested row")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N insertions")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        summary = ingest_file(path, source=args.source, limit=args.limit)
        print("CTD ingestion complete:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()