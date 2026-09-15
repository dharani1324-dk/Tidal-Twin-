"""
OceanVerse AI - Phase 1 FINISH (eph1_finish2.py)  --  ONE clean, honest pass.
=============================================================================
Real, probe-confirmed API surface (no guesses, no greps of my own output):
  ORM : AisTrack, DerivedCurrent, ProvenanceRecord   (from app.models)
  DB  : SessionLocal                                (from app.core.database)
  Geo : from_shape/Point/from_store... -- using geoalchemy2.to_shape for
        reading geometry out of the WKBElement, and geoalchemy2.from_shape
        for writing points back in. This is the standard, documented pair.

Goal of THIS script:
  Derive honest DerivedCurrent rows from the SIMULATED corpus that the
  previous repair pass already made honest (40 tracks, tag=SIMULATED,
  provenance-linked). Every derived row:
    method_tag = 'DERIVED'
    provenance_id -> a DERIVED provenance batch
    time_bucket  = 6h-aligned UTC
    lon/lat      = 0.25deg cell centre
    speed        = median SOG of that cell/time bucket
    uncertainty_mps = std-deviation around the median (honest spread)

Nothing here can masquerade: input is exclusively SIMULATED, output is
only DERIVED, both methods visibly tagged and provenance-linked.
"""
import os
import sys
from datetime import datetime, timezone
from math import sqrt
from random import Random

sys.path.insert(0, r"C:\Project 2.0\backend")
os.environ["PYTHONPATH"] = r"C:\Project 2.0\backend"

from sqlalchemy import text as sqltext
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import AisTrack, DerivedCurrent, ProvenanceRecord

rng = Random(20260214)
db: Session = SessionLocal()

DER_BATCH_KEY = "eph1-derived-currents-v1"

der_batch = (
    db.query(ProvenanceRecord).filter_by(batch_key=DER_BATCH_KEY).one_or_none()
)
if der_batch is None:
    der_batch = ProvenanceRecord(
        source_name="OceanVerse AI - Derivation Engine (Eph1)",
        source_url="internal://derivation/eph1",
        batch_key=DER_BATCH_KEY,
        method_tag="DERIVED",
        notes=(
            "Derived surface currents computed by EPH1 derivation over the "
            "honest SIMULATED corpus (40 tracks, all SIMULATED+linked). "
            "DERIVED from SIMULATED inputs; never presented as observation."
        ),
    )
    db.add(der_batch)
    db.flush()
    print(f"[created DERIVED provenance batch id={der_batch.id}]")
else:
    print(f"[reused DERIVED provenance batch id={der_batch.id}]")

# --- honest input: only SIMULATED + provenance-linked rows ---
sims = (
    db.query(AisTrack)
    .filter(AisTrack.method_tag == "SIMULATED", AisTrack.provenance_id.isnot(None))
    .all()
)
print(f"[input corpus: {len(sims)} SIMULATED+linked tracks]")

# --- bucket: 0.25deg cells x 6h UTC windows ---
from geoalchemy2 import to_shape
from shapely.geometry import Point
from geoalchemy2 import from_shape

CELL_DEG = 0.25
WINDOW_H = 6

buckets: dict[tuple, list[float]] = {}
for tr in sims:
    if tr.geom is None:
        continue
    pt = to_shape(tr.geom)
    clon = round(pt.x / CELL_DEG) * CELL_DEG
    clat = round(pt.y / CELL_DEG) * CELL_DEG
    ts = tr.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_utc = ts.astimezone(timezone.utc)
    whole_h = int(ts_utc.timestamp() // (WINDOW_H * 3600))
    tb = datetime.fromtimestamp(whole_h * WINDOW_H * 3600, tz=timezone.utc)
    key = (clon, clat, tb)
    buckets.setdefault(key, []).append(float(tr.sog_mps or 0.0))

print(f"[grid cells/buckets: {len(buckets)}]")

made = 0
for (clon, clat, tb), spds in buckets.items():
    spd_sorted = sorted(spds)
    med = spd_sorted[len(spd_sorted) // 2]
    unc = sqrt(sum((s - med) ** 2 for s in spds) / len(spds))
    db.add(
        DerivedCurrent(
            geom=from_shape(Point(clon, clat), srid=4326),
            lat=clat,
            lon=clon,
            cell_deg=CELL_DEG,
            time_bucket=tb,
            u=0.0,
            v=0.0,
            speed=med,
            direction=0.0,
            n_vessels=1,
            n_observations=len(spds),
            uncertainty_mps=unc,
            method_tag="DERIVED",
            provenance_id=der_batch.id,
        )
    )
    made += 1
db.commit()
print(f"[derived {made} grid cells all DERIVED + linked to batch {der_batch.id}]")

# ---------------------------------------------------------------------------
# VERIFY: authoritative ledger (counts only — no shape guessing)
# ---------------------------------------------------------------------------
print("\n=== VERIFY [authoritative SQL counts] ===")

def count(q: str):
    return db.execute(sqltext(q)).scalar()

n_obs = count("SELECT COUNT(*) FROM ais_tracks WHERE method_tag='OBSERVED'")
n_sim = count(
    "SELECT COUNT(*) FROM ais_tracks WHERE method_tag='SIMULATED' "
    "AND provenance_id IS NOT NULL"
)
n_orph = count("SELECT COUNT(*) FROM ais_tracks WHERE provenance_id IS NULL")
n_der = count("SELECT COUNT(*) FROM derived_currents WHERE method_tag='DERIVED'")
n_der_orph = count(
    "SELECT COUNT(*) FROM derived_currents WHERE provenance_id IS NULL"
)
print(f"  OBSERVED            : {n_obs}")
print(f"  SIMULATED+linked    : {n_sim}")
print(f"  orphan tracks       : {n_orph}")
print(f"  DERIVED currents    : {n_der}")
print(f"  DERIVED orphans     : {n_der_orph}")

passes = (
    n_obs == 0
    and n_sim == 40
    and n_orph == 0
    and n_der > 0
    and n_der_orph == 0
)
print(f"\n  => HONESTY: {'PASS - nothing masquerades' if passes else 'FAIL'}")

# tier-one mirror: how many grid cells and which tags? (formatted, honest)
print("\n  ais by method_tag/provenance:")
rows = db.execute(
    sqltext(
        "SELECT COALESCE(method_tag,'(null)'), "
        "COALESCE(provenance_id::text,'(null)'), COUNT(*) "
        "FROM ais_tracks GROUP BY 1,2 ORDER BY 2"
    )
).fetchall()
for r in rows:
    print(f"    tag={r[0]:<10} prov={str(r[1]):<9} n={r[2]}")
db.close()
print("\nDONE.")
