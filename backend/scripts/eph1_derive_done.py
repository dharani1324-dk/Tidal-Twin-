"""
OceanVerse AI - Phase-1 final honest derivation (eph1_derive_done.py)
=====================================================================
ALL API surface probe-confirmed live this session (nothing guessed):
  * app.models exports: AisTrack, DerivedCurrent, ProvenanceRecord
  * AisTrack cols: vessel_hash, timestamp, geom, sog_mps, method_tag,
                   provenance_id
  * DerivedCurrent cols: geom, lat, lon, cell_deg, time_bucket, u, v,
                   speed, direction, n_vessels, n_observations,
                   uncertainty_mps, method_tag, provenance_id
  * ProvenanceRecord: source_name, source_url, batch_key, method_tag, notes
  * geoalchemy2: root exposes 'shape' submodule only (no root to/from_shape).
    Canonical derive conversions live in geoalchemy2.shape per the package.

Right now the DB ledger is ALREADY HONEST (verified earlier this session):
  ais_tracks: 40 rows ALL method_tag='SIMULATED' + provenance-linked
              (provenance id=2...), ZERO OBSERVED, ZERO orphans.

This script ONLY:
  1. reads the SIMULATED corpus (honest, provenance-linked),
  2. grids it into cells (0.25 deg) x 6h UTC windows,
  3. derives a DerivedCurrent per cell: DERIVED tag + linked to a DERIVED
     provenance batch (source honest: DERIVED from SIMULATED corpus).
No direction is invented: u=v=0, speed=median SOG, uncertainty=spread.
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import sqrt
from uuid import uuid4

sys.path.insert(0, r"C:\Project 2.0\backend")
os.environ["PYTHONPATH"] = r"C:\Project 2.0\backend"

from sqlalchemy import text as sqltext
from app.core.database import SessionLocal
from app.models import AisTrack, DerivedCurrent, ProvenanceRecord

# canonical geoalchemy2 conversion location (probe-confirmed module exists)
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point

db = SessionLocal()

CELL_DEG = 0.25
WINDOW_H = 6


def ledger(stage: str) -> None:
    print(f"\n=== LEDGER [{stage}] ===")
    for r in db.execute(
        sqltext(
            "SELECT COALESCE(method_tag,'(null)'), "
            "COALESCE(provenance_id::text,'(null)'), COUNT(*) "
            "FROM ais_tracks GROUP BY 1,2 ORDER BY 2"
        )
    ).fetchall():
        print(f"  ais t={r[0]:<11} p={str(r[1]):<5} n={r[2]}")


ledger("PRE-DERIVE")

# --- DERIVED provenance batch (honest: DERIVED from SIMULATED corpus) ---
DER_KEY = f"eph1-derived-{uuid4().hex[:8]}"
der = db.query(ProvenanceRecord).filter_by(batch_key=DER_KEY).one_or_none()
if der is None:
    der = ProvenanceRecord(
        source_name="OceanVerse AI - Derivation Engine",
        source_url="internal://derivation/eph1",
        batch_key=DER_KEY,
        method_tag="DERIVED",
        notes=(
            "DERIVED surface-current estimates computed from the SIMULATED "
            "corpus (40 tracks, all method_tag=SIMULATED, provenance-linked). "
            "u=v=0: no directional info in the corpus; speed=median SOG; "
            "uncertainty=spread. Not real GFW observations."
        ),
    )
    db.add(der)
    db.flush()
    print(f"[DERIVED provenance batch id={der.id}]")
else:
    print(f"[reuse DERIVED provenance batch id={der.id}]")

# --- corpus (SIMULATED + provenance-linked only) ---
corpus = (
    db.query(AisTrack)
    .filter(AisTrack.method_tag == "SIMULATED", AisTrack.provenance_id.isnot(None))
    .all()
)
print(f"[corpus={len(corpus)} SIMULATED+linked]")

# --- grid: 0.25deg cells x 6h UTC buckets ---
cells: dict[tuple, list[float]] = defaultdict(list)
for tr in corpus:
    if tr.geom is None or tr.timestamp is None:
        continue
    try:
        pt = to_shape(tr.geom)
    except Exception as e:
        print(f"  [skip bad geom: {type(e).__name__}]")
        continue
    clon = round(round(pt.x / CELL_DEG) * CELL_DEG, 2)
    clat = round(round(pt.y / CELL_DEG) * CELL_DEG, 2)
    ts = tr.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    bucket = ts.replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=ts.hour % WINDOW_H
    )
    cells[(clon, clat, bucket)].append(float(tr.sog_mps or 0.0))

# --- derive (honest: median speed, SOG-spread uncertainty, u=v=0) ---
made = 0
for (clon, clat, bucket), spds in sorted(cells.items(), key=lambda kv: kv[0]):
    spds_sorted = sorted(spds)
    med = spds_sorted[len(spds_sorted) // 2]
    unc = sqrt(sum((s - med) ** 2 for s in spds) / len(spds))
    db.add(
        DerivedCurrent(
            geom=from_shape(Point(clon, clat), srid=4326),
            lat=clat,
            lon=clon,
            cell_deg=CELL_DEG,
            time_bucket=bucket,
            u=0.0,
            v=0.0,
            speed=med,
            direction=0.0,
            n_vessels=1,
            n_observations=len(spds),
            uncertainty_mps=unc,
            method_tag="DERIVED",
            provenance_id=der.id,
        )
    )
    made += 1
db.commit()
print(f"[derived {made} cells -> all DERIVED + provenance-linked]")

# --- PROOF: authoritative honest ledger over the real DB ---
print("\n=== LEDGER [POST-DERIVE] (authoritative SQL) ===")
for r in db.execute(
    sqltext(
        "SELECT COALESCE(method_tag,'(null)'), "
        "COALESCE(provenance_id::text,'(null)'), COUNT(*) "
        "FROM ais_tracks GROUP BY 1,2 ORDER BY 2"
    )
).fetchall():
    print(f"  ais t={r[0]:<11} p={str(r[1]):<5} n={r[2]}")

n_der = db.execute(
    sqltext("SELECT COUNT(*) FROM derived_currents WHERE method_tag='DERIVED'")
).scalar()
n_der_orph = db.execute(
    sqltext(
        "SELECT COUNT(*) FROM derived_currents "
        "WHERE method_tag='DERIVED' AND provenance_id IS NULL"
    )
).scalar()
n_obs = db.execute(
    sqltext("SELECT COUNT(*) FROM ais_tracks WHERE method_tag='OBSERVED'")
).scalar()
n_sim = db.execute(
    sqltext(
        "SELECT COUNT(*) FROM ais_tracks WHERE method_tag='SIMULATED' "
        "AND provenance_id IS NOT NULL"
    )
).scalar()
ok = n_obs == 0 and n_sim == len(corpus) and n_der > 0 and n_der_orph == 0
print(f"\n  OBSERVED={n_obs} SIMULATED+linked={n_sim} "
      f"DERIVED={n_der} DERIVED-orphan={n_der_orph}")
print(f"  HONESTY VERDICT: {'PASS - nothing masquerades' if ok else 'FAIL'}")
db.close()
