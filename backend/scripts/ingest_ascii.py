"""
TidalTwin - ASCII / text observation ingestion (feature #19)
=================================================================
Reads a plain-text observation file (CSV or whitespace-delimited, with an
optional `#` comment header) and stores each real measurement into
`ocean_observations`, exactly like any other observation source.

Accepted columns (case-insensitive header names, aliases allowed):

  Required     : latitude / lat, longitude / lon, time / timestamp / date
  Optional     : sea_surface_temperature / sst / temperature, wave_height,
                 wave_direction, salinity, current_speed, current_direction,
                 depth_m / depth, dissolved_oxygen, chlorophyll, ph, pressure,
                 density, nutrients

Honesty rules (same as every other ingestion path):
    - rows with an unparseable lat/lon or time are SKIPPED (never guessed)
    - rows farther than --max-radius-km from every monitored location are
      SKIPPED (we link each reading to a monitored ocean region; we never
      invent a location for it)
    - rows that duplicate an existing (location, timestamp) are SKIPPED

Usage:
    .venv\\Scripts\\python -m scripts.ingest_ascii path\\to\\buoy.csv [--source "XBT casts"]
    .venv\\Scripts\\python -m scripts.ingest_ascii path\\to\\data.txt --max-radius-km 200
"""

import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import SessionLocal
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.realdata import location_center

# Column header -> OceanObservation attribute.
COLUMN_MAP = {
    "sea_surface_temperature": "sea_surface_temperature", "sst": "sea_surface_temperature",
    "temperature": "sea_surface_temperature",
    "wave_height": "wave_height", "waveheight": "wave_height",
    "wave_direction": "wave_direction", "wavedirection": "wave_direction",
    "salinity": "salinity",
    "current_speed": "current_speed", "currentspeed": "current_speed",
    "current_direction": "current_direction", "currentdirection": "current_direction",
    "depth": "depth_m", "depth_m": "depth_m", "depthm": "depth_m",
    "dissolved_oxygen": "dissolved_oxygen", "oxygen": "dissolved_oxygen",
    "chlorophyll": "chlorophyll", "chlorophyll_a": "chlorophyll",
    "ph": "ph",
    "pressure": "pressure",
    "density": "density",
    "nutrients": "nutrients",
}
LAT_KEYS = ("latitude", "lat")
LON_KEYS = ("longitude", "lon")
TIME_KEYS = ("time", "timestamp", "date", "datetime")

TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d")


def _distance_km(lat0, lon0, lat1, lon1) -> float:
    """Equirectangular approximation (~1% accurate at these scales)."""
    dlat = lat1 - lat0
    dlon = (lon1 - lon0) * math.cos(math.radians((lat0 + lat1) / 2.0))
    return math.hypot(dlat, dlon) * 111.32  # 1 degree of latitude ~ 111.32 km


def _parse_time(raw) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        for fmt in TIME_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def _rows_from(path: Path):
    """Yield dict rows (lowercased keys) from CSV or whitespace-delimited text."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return
    header = lines[0]
    delim = "," if "," in header else None
    if delim is None:
        header_tokens = header.split()
        for raw in lines[1:]:
            cells = raw.split()
            if len(cells) < len(header_tokens):
                continue
            yield {h.lower(): v for h, v in zip(header_tokens, cells)}
        return
    reader = csv.reader(lines)
    header_row = next(reader)
    for cells in reader:
        if len(cells) < len(header_row):
            continue
        yield {h.lower(): v for h, v in zip(header_row, cells)}


def _nearest_location(db, lat: float, lon: float, max_radius_km: float):
    """Nearest monitored location within radius, or None (honest skip)."""
    best, best_d = None, None
    for loc in db.query(OceanLocation).all():
        c = location_center(loc)
        if c is None:
            continue
        d = _distance_km(lat, lon, c[0], c[1])
        if best is None or d < best_d:
            best, best_d = loc, d
    if best is None or best_d > max_radius_km:
        return None, best_d
    return best, best_d


def ingest_file(path: Path, source: str = "ASCII file import",
                max_radius_km: float = 100.0, limit: int | None = None) -> dict:
    """Parse one ASCII file into ocean_observations. Returns an honest summary."""
    parsed = skipped_bad = skipped_far = duplicates = 0
    inserted = 0
    target_attr = COLUMN_MAP
    seen = set()

    with SessionLocal.begin() as db:
        for row in _rows_from(path):
            parsed += 1
            raw_lat = next((row.get(k) for k in LAT_KEYS if row.get(k)), None)
            raw_lon = next((row.get(k) for k in LON_KEYS if row.get(k)), None)
            raw_t = next((row.get(k) for k in TIME_KEYS if row.get(k)), None)
            if raw_lat is None or raw_lon is None or raw_t is None:
                skipped_bad += 1
                continue
            try:
                lat, lon = float(raw_lat), float(raw_lon)
            except (ValueError, TypeError):
                skipped_bad += 1
                continue
            ts = _parse_time(raw_t)
            if ts is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                skipped_bad += 1
                continue
            if ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)

            loc, dist = _nearest_location(db, lat, lon, max_radius_km)
            if loc is None:
                skipped_far += 1
                continue

            if (loc.id, ts) in seen:
                duplicates += 1
                continue
            exists = db.query(OceanObservation).filter(
                OceanObservation.location_id == loc.id,
                OceanObservation.timestamp == ts,
            ).first()
            if exists:
                duplicates += 1
                continue

            kwargs = {"timestamp": ts, "source": source, "data_type": "observation",
                      "depth_m": 0.0}
            for key, attr in target_attr.items():
                raw = row.get(key)
                if raw is None:
                    continue
                try:
                    val = float(raw)
                except (ValueError, TypeError):
                    continue
                if math.isnan(val) or math.isinf(val):
                    continue
                kwargs[attr] = val

            db.add(OceanObservation(location_id=loc.id, **kwargs))
            seen.add((loc.id, ts))
            inserted += 1
            if limit is not None and inserted >= limit:
                break

    return {
        "parsed": parsed,
        "inserted": inserted,
        "skipped_bad": skipped_bad,
        "skipped_far": skipped_far,
        "duplicates": duplicates,
        "source": source,
        "max_radius_km": max_radius_km,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Ingest a plain-text (CSV / whitespace) observation file into ocean_observations."
    )
    parser.add_argument("file", help="Path to the ASCII/CSV observation file")
    parser.add_argument("--source", default="ASCII file import",
                        help="Source label stored on each ingested row")
    parser.add_argument("--max-radius-km", type=float, default=100.0,
                        help="Max distance (km) from a monitored location to accept a row")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N insertions")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        summary = ingest_file(path, source=args.source, max_radius_km=args.max_radius_km,
                              limit=args.limit)
        print("ASCII ingestion complete:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()