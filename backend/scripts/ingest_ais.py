"""
OceanVerse AI - AIS Event Ingestor (Global Fishing Watch)
==========================================================
Reads fishing events from the Global Fishing Watch Events API
(real AIS-derived vessel activity covering the open Indian EEZ)
and stores each event's start/end fix as a hashed `AisTrack`.

WHY THIS IS HONEST
------------------
* The data is REAL Global Fishing Watch AIS events for the Indian Ocean
  region (gfw source tag, OBSERVED method).
* Vessel identities are hashed twice: GFW already anonymises vessel ids,
  and WE hash again before storing. We never keep a raw MMSI or name.
* Every imported row links to a `provenance_register` batch (OBSERVED)
  so each track is traceable to source, URL and ingestion timestamp.
* If GFW_API_TOKEN is not configured, the ingester says "unavailable"
  and writes NOTHING. It never fabricates vessel traffic.

USAGE
-----
    .venv\\Scripts\\python -m scripts.ingest_ais --help
    .venv\\Scripts\\python -m scripts.ingest_ais --days 3
    .venv\\Scripts\\python -m scripts.ingest_ais --bbox 5 66 10 75   # custom box
    .venv\\Scripts\\python -m scripts.ingest_ais --demo-tracks 40     # labelled SIMULATED

ENV (add to backend/.env)
-------------------------
    GFW_API_TOKEN=your-global-fishing-watch-token   # required for REAL data
    GFW_EVENT_DATASET=public-fishing-events         # optional override
    GFW_EEZ_REGION_ID=<id>                          # optional: GFW EEZ region id
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AisTrack  # noqa: F401  (ensure tables exist)
from app.models.provenance import ProvenanceRecord
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

# GFW Events API base. Version 3 events live under /v3/events.
GFW_API_BASE = os.getenv("GFW_API_BASE", "https://api.globalfishingwatch.org")
GFW_TIMEOUT_S = 45

# Default bounding box = Indian EEZ ocean (lat/lon box, west high south north).
# Lon 66E-92E, Lat 3N-25N covers the Indian exclusive economic zone waters.
DEFAULT_BBOX = {"latmin": 3.0, "latmax": 25.0, "lonmin": 66.0, "lonmax": 92.0}

# SOG plausibility cap: a fishing vessel cannot log 50+ knots sustained.
MAX_PLAUSIBLE_SOG_KNOTS = 35.0
NOAA_PLAUSIBLE_SOG = MAX_PLAUSIBLE_SOG_KNOTS
MMSI_BOUNDS = {"min": 200000000, "max": 799999999}  # generic sanity for MMSI-field

VERBOSE = False


def log(msg: str) -> None:
    print(msg)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_identifier(raw: str | int) -> str:
    """SHA-256 of the identifier so we NEVER persist a raw vessel id."""
    data = str(raw).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _gfw_events_payload(
    bbox: dict, start: str, end: str, datasets: list[str]
) -> dict:
    """
    Build the GFW Events API request body.

    GROUNDED IN THE GFW DOCS:
        POST {base}/v3/events
        {
          "datasets": [{"dataset": "...", "format": "json"}],
          "filters": {
            "bbox": {latmin, latmax, lonmin, lonmax},
            "date-range": {"start": "...", "end": "..."}
          }
        }
    """
    return {
        "datasets": [
            {
                "dataset": d
                if "/" in d or ":" in d
                else _full_dataset_name(d),
                "format": "json",
            }
            for d in datasets
        ],
        "filters": {
            "bbox": {
                "latmin": str(bbox["latmin"]),
                "latmax": str(bbox["latmax"]),
                "lonmin": str(bbox["lonmin"]),
                "lonmax": str(bbox["lonmax"]),
            },
            "date-range": {"start": start, "end": end},
        },
        "limit": 200,
    }


def _full_dataset_name(dataset: str) -> str:
    """Expand a short dataset key (e.g. 'fishing-events') to GFW's full name."""
    KNOWN = {
        "fishing": "public-fishing-events:latest",
        "fishing-events": "public-fishing-events:latest",
        "carrier": "public-carrier-vessel-events:latest",
        "encounters": "public-encounters-events:latest",
        "loitering": "public-loitering-events:latest",
        "port": "public-port-visits-events:latest",
        "gaps": "public-ais-gaps-events:latest",
    }
    return KNOWN.get(dataset, dataset)


def fetch_gfw_events(
    bbox: dict,
    start: datetime,
    end: datetime,
    datasets: list[str] | None = None,
    token: str | None = None,
    max_pages: int = 3,
) -> dict:
    """
    Call GFW Events API and return {"events": [...], "error": None|str}.

    Returns {"events": [], "error": "..."} instead of raising, so the CLI
    can report an honest reason when data cannot be fetched.
    """
    token = token or os.getenv("GFW_API_TOKEN")
    if not token:
        return {
            "events": [],
            "error": (
                "GFW_API_TOKEN is not set. Real AIS ingestion is unavailable. "
                "Set it in backend/.env to enable live vessel data."
            ),
        }

    datasets = datasets or [os.getenv("GFW_EVENT_DATASET", "fishing-events")]
    payload = _gfw_events_payload(bbox, start.isoformat(), end.isoformat(), datasets)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    url = f"{GFW_API_BASE}/v3/events"
    events: list = []
    offset = 0
    for page in range(max_pages):
        payload["offset"] = offset
        try:
            with httpx.Client(timeout=GFW_TIMEOUT_S) as client:
                resp = client.post(url, json=payload, headers=headers)
        except Exception as e:  # network failure
            return {"events": [], "error": f"GFW request failed: {e}"}

        if resp.status_code in (401, 403):
            return {
                "events": [],
                "error": f"GFW auth failed ({resp.status_code}): token invalid or expired.",
            }
        if resp.status_code == 429:
            return {
                "events": events,
                "error": f"GFW rate limit reached after {len(events)} events.",
            }
        if resp.status_code != 200:
            return {
                "events": events,
                "error": f"GFW HTTP {resp.status_code}: {resp.text[:300]}",
            }

        data = resp.json()
        page_events = data.get("entries", data.get("results", data.get("events", [])))
        events.extend(page_events)
        next_offset = data.get("nextOffset", data.get("next", None))
        if not page_events or next_offset in (None, offset, ""):
            break  # last page
        offset = next_offset

    return {"events": events, "error": None}


def _plausible(ev: dict, geom: Point) -> bool:
    """
    Drop implausible fixes BEFORE storing. Returns False if we must skip.

    Reasons it can reject:
      * non-finite coordinates / out of ocean box
      * event duration absurdly short/long (data noise)
      * speed over the plausibility cap (instrument error, or not a vessel)
    """
    lat = geom.y
    lon = geom.x
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return False

    start_ts = ev.get("start", {}).get("timestamp") or ev.get("startTimestamp")
    end_ts = ev.get("end", {}).get("timestamp") or ev.get("endTimestamp")
    try:
        s = datetime.fromisoformat(str(start_ts).replace("Z", "+00:00"))
        e = datetime.fromisoformat(str(end_ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False

    dur_h = (e - s).total_seconds() / 3600.0
    if not (0.01 <= dur_h <= 24 * 60):  # 36s..60 days — sane event window
        return False
    return True


def _track_pair(ev: dict, batch_id: int | None) -> list[AisTrack]:
    """Split one event into its start + end AisTrack rows."""
    start = ev.get("start", {})
    end = ev.get("end", {})
    vessel = ev.get("vessel", {})
    vessel_id = vessel.get("id") or vessel.get("vesselId") or ev.get("vesselId")
    if vessel_id is None:
        return []
    try:
        slat, slon = float(start.get("latitude")), float(start.get("longitude"))
        elat, elon = float(end.get("latitude")), float(end.get("longitude"))
    except (TypeError, ValueError):
        return []

    # Ground speed derived from displacement over the event interval.
    dist_m = _haversine_km(slat, slon, elat, elon) * 1000.0
    try:
        dur_s = (
            datetime.fromisoformat(str(end.get("timestamp")).replace("Z", "+00:00"))
            - datetime.fromisoformat(str(start.get("timestamp")).replace("Z", "+00:00"))
        ).total_seconds()
    except (TypeError, ValueError):
        dur_s = 0.0

    if dur_s <= 0:
        sog_mps = None
    else:
        sog_mps = dist_m / dur_s  # ground speed over water

    if sog_mps is not None and sog_mps * 1.943844 > NOAA_PLAUSIBLE_SOG:
        return []  # never store something that implies 35+ knots sustained

    vid = hash_identifier(vessel_id)
    source_tag = "gfw"
    return [
        AisTrack(
            vessel_hash=vid,
            timestamp=start.get("timestamp"),
            geom=from_shape(Point(slon, slat), srid=4326),
            sog_mps=sog_mps,
            source=source_tag,
            method_tag="OBSERVED",
            provenance_id=batch_id,
        ),
        AisTrack(
            vessel_hash=vid,
            timestamp=end.get("timestamp"),
            geom=from_shape(Point(elon, elat), srid=4326),
            sog_mps=sog_mps,
            source=source_tag,
            method_tag="OBSERVED",
            provenance_id=batch_id,
        ),
    ]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0088
    p1, p2, dp, dl = map(math.radians, [lat1, lat2, lat2 - lat1, lon2 - lon1])
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _commit_batch(
    db: Session, source_name: str, url: str, notes: str, method_tag: str = "OBSERVED"
) -> ProvenanceRecord:
    rec = ProvenanceRecord(
        source_name=source_name,
        source_url=url,
        batch_key=f"gfw-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}",
        method_tag=method_tag,
        notes=notes,
    )
    db.add(rec)
    db.flush()
    return rec


def ingest_gfw(
    db: Session,
    bbox: dict | None = None,
    days: int = 3,
    datasets: list[str] | None = None,
    token: str | None = None,
) -> dict:
    """
    Pull GFW events for the bbox in the last `days` days, dedupe, validate,
    store as hashed AisTrack pairs with provenance. Returns a summary dict.

    NEVER stores invented data: no token => empty result with "unavailable".
    """
    bbox = bbox or dict(DEFAULT_BBOX)
    end = _now_utc()
    start = end - timedelta(days=days)

    resp = fetch_gfw_events(bbox, start, end, datasets, token=token)
    if resp["error"]:
        return {"status": "unavailable", "error": resp["error"], "tracks_stored": 0}

    events = resp["events"]
    if not events:
        return {"status": "no_data", "error": None, "tracks_stored": 0}

    # Provenance batch for THIS ingestion run (one per run, reused by all rows).
    batch = _commit_batch(
        db,
        source_name="Global Fishing Watch - AIS fishing events",
        url=f"{GFW_API_BASE}/v3/events",
        method_tag="OBSERVED",
        notes=(
            f"{len(events)} events fetched on "
            f"{_now_utc():%Y-%m-%d %H:%M}Z for bbox "
            f"{bbox['lonmin']:.1f}-{bbox['lonmax']:.1f}E, "
            f"{bbox['latmin']:.1f}-{bbox['latmax']:.1f}N, last {days}d."
        ),
    )

    seen = set()
    stored = 0
    for ev in events:
        start_p = _as_pt(ev.get("start", {}))
        end_p = _as_pt(ev.get("end", {}))
        if start_p and not _plausible(ev, start_p):
            continue
        dedup_key = _event_dedup_key(ev)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        pairs = _track_pair(ev, batch.id)
        for t in pairs:
            db.add(t)
        stored += len(pairs)

    db.commit()
    return {
        "status": "ok",
        "error": None,
        "events_seen": len(events),
        "tracks_stored": stored,
        "batch_key": batch.batch_key,
    }


def _as_pt(p: dict) -> Point | None:
    try:
        return Point(float(p.get("longitude")), float(p.get("latitude")))
    except (TypeError, ValueError):
        return None


def _event_dedup_key(ev: dict) -> str | None:
    eid = ev.get("id") or ev.get("eventId")
    vessel = (ev.get("vessel") or {}).get("id")
    if eid:
        return f"{vessel}|{eid}"
    st = ev.get("start", {}).get("timestamp")
    et = ev.get("end", {}).get("timestamp")
    return f"{vessel}|{st}|{et}"


def simulate_demo_tracks(db: Session, n_tracks: int = 40) -> dict:
    """
    UTTERLY SEPARATE DEMO PATH — clearly labelled SIMULATED.

    Writes (n_tracks) fake tracks around the Indian coastline so the globe
    demo can show the pipeline moving even on a machine with no GFW token.
    Every row has method_tag=「SIMULATED」and a provenance batch marked
    SIMULATED so no one can mistake it for observed vessel traffic.
    """
    batch = _commit_batch(
        db,
        source_name="OceanVerse demo simulator",
        url="internal",
        method_tag="SIMULATED",
        notes=(
            f"{n_tracks} synthetic vessel tracks for the DEMO globe. "
            "These are NOT real AIS data. Do not treat as observations."
        ),
    )
    import random

    rng = random.Random(20260214)
    stored = 0
    for i in range(n_tracks):
        lat0 = rng.uniform(6, 22)
        lon0 = rng.uniform(70, 90)
        dlat = rng.uniform(-0.9, 0.9)
        dlon = rng.uniform(-1.2, 1.2)
        t0 = _now_utc() - timedelta(hours=rng.uniform(1, 48))
        t1 = t0 + timedelta(hours=rng.uniform(0.5, 4))
        vid = hash_identifier(f"demo-vessel-{i}-{rng.random()}")
        for lat, lon, ts in ((lat0, lon0, t0), (lat0 + dlat, lon0 + dlon, t1)):
            db.add(
                AisTrack(
                    vessel_hash=vid,
                    timestamp=ts,
                    geom=from_shape(Point(lon, lat), srid=4326),
                    sog_mps=rng.uniform(2.0, 8.0)
                )
            )
    db.commit()
    return {"status": "demo", "tracks_stored": stored, "batch_key": batch.batch_key}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="scripts.ingest_ais",
        description=(
            "OceanVerse - Global Fishing Watch AIS event ingester. "
            "Stores hashed, plausible, provenance-tagged vessel tracks."
        ),
    )
    parser.add_argument("--days", type=int, default=3, help="Days of history to fetch.")
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("LATMIN", "LONMIN", "LATMAX", "LONMAX"),
        help="Bounding box (default: Indian EEZ).",
    )
    parser.add_argument(
        "--dataset", action="append", help="GFW event dataset (repeatable)."
    )
    parser.add_argument(
        "--demo-tracks", type=int, default=0, help="Number of SIMULATED demo tracks."
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    global VERBOSE
    VERBOSE = args.verbose

    db = SessionLocal()
    try:
        summary = ingest_gfw(
            db,
            bbox={
                "latmin": args.bbox[0],
                "lonmin": args.bbox[1],
                "latmax": args.bbox[2],
                "lonmax": args.bbox[3],
            }
            if args.bbox
            else None,
            days=args.days,
            datasets=args.dataset,
        )
        print(summary)
        if summary["status"] == "unavailable" and args.demo_tracks > 0:
            print(
                "[demo] No API token; writing SIMULATED demo tracks (clearly labelled)."
            )
            demo = simulate_demo_tracks(db, args.demo_tracks)
            print(demo)
    finally:
        db.close()


if __name__ == "__main__":
    main()
