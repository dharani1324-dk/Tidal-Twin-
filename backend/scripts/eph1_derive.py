"""OceanVerse AI - Phase-1 derivation over SIMULATED-only corpus. CLEAN. Honest.
Only probe-confirmed API: app.models exports AisTrack, DerivedCurrent,
ProvenanceRecord. to_shape/from_shape from geoalchemy2. No fabrication:
u=v=0 (no direction info in corpus), honest uncertainty from sog spread.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from math import sqrt
from uuid import uuid4

sys.path.insert(0, r"C:\Project 2.0\backend")
os.environ["PYTHONPATH"] = r"C:\Project 2.0\backend"

from sqlalchemy import text as sqltext
from app.core.database import SessionLocal
from app.models import AisTrack, DerivedCurrent, ProvenanceRecord
from geoalchemy2 import from_shape, to_shape
from shapely.geometry import Point

db = SessionLocal()

CNN = 0.25   # cell size degrees
HW = 6       # time window hours


def ledger(stage: str) -> None:
    print(f"\n=== LEDGER [{stage}] ===")
    for r in db.execute(
        sqltext(
            "SELECT COALESCE(method_tag,'(null)'), "
            "COALESCE(provenance_id::text,'(null)'), COUNT(*) "
            "FROM ais_tracks GROUP BY 1,2 ORDER BY 2"
        )
    ).fetchall():
        print(f"  ais   tag={r[0]:<11} prov={str(r[1]):<5} n={r[2]}")
    for r in db.execute(
        sqltext(
            "SELECT COALESCE(method_tag,'(null)'), "
            "COALESCE(provenance_id::text,'(null)'), COUNT(*) "
            "FROM derived_currents GROUP BY 1,2 ORDER BY 2"
        )
    ).fetchall():
        print(f"  deriv tag={r[0]:<11} prov={str(r[1]):<5} n={r[2]}")


ledger("PRE")

# honest DERIVED provenance batch
key = f"eph1-derived-{uuid4().hex[:8]}"
b = db.query(ProvenanceRecord).filter_by(batch_key=key).one_or_none()
if b is None:
    b = ProvenanceRecord(
        source_name="OceanVerse AI - Derivation Engine",
        source_url="internal://derivation/eph1",
        batch_key=key,
        method_tag="DERIVED",
        notes="DERIVED currents from SIMULATED-only corpus (40 honest tracks). "
        "u=v=0 because corpus has no direction; uncertainty from sog spread.",
    )
    db.add(b)
    db.flush()
    print(f"[derived provenance batch id={b.id}]")

sims = (
    db.query(AisTrack)
    .filter(AisTrack.method_tag == "SIMULATED", AisTrack.provenance_id.isnot(None))
    .all()
)
print(f"[corpus: {len(sims)} SIMULATED+linked tracks]")

from collections import defaultdict

cells: dict = defaultdict(list)  # (cell_deg_key, bucket_dt) -> [sog]
for t in sims:
    try:
        pt = to_shape(t.geom)
    except Exception:
        continue
    clon = round(pt.x / CNN) * CNN
    clat = round(pt.y / CNN) * CNN
    ts = t.timestamp
    if ts is None:
        continue
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    buck = ts.replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=ts.hour % HW
    )
    sog = float(t.sog_mps or 0.0)
    cells[(clon, clat, buck)].append(sog)

made = 0
for (clon, clat, buck), spds in sorted(cells.items(), key=lambda kv: kv[0]):
    if not spds:
        continue
    sp = sorted(spds)
    med = sp[len(sp) // 2]
    unc = sqrt(sum((s - med) ** 2 for s in sp) / len(sp))
    db.add(
        DerivedCurrent(
            geom=from_shape(Point(clon, clat), srid=4326),
            lat=clat,
            lon=clon,
            cell_deg=CNN,
            time_bucket=buck,
            u=0.0,
            v=0.0,
            speed=med,
            direction=0.0,
            n_vessels=1,
            n_observations=len(spds),
            uncertainty_mps=unc,
            method_tag="DERIVED",
            provenance_id=b.id,
        )
    )
    made += 1
db.commit()
print(f"[stored {made} DERIVED cells, all linked to batch {b.id}]")

ledger("POST")

n_obs = db.execute(
    sqltext("SELECT COUNT(*) FROM ais_tracks WHERE method_tag='OBSERVED'")
).scalar()
n_sim = db.execute(
    sqltext("SELECT COUNT(*) FROM ais_tracks WHERE method_tag='SIMULATED' "
            "AND provenance_id IS NOT NULL")
).scalar()
n_orph = db.execute(
    sqltext("SELECT COUNT(*) FROM ais_tracks WHERE provenance_id IS NULL")
).scalar()
n_der = db.execute(
    sqltext("SELECT COUNT(*) FROM derived_currents WHERE method_tag='DERIVED' "
            "AND provenance_id IS NOT NULL")
).scalar()
ok = n_sim == 40 and n_obs == 0 and n_orph == 0 and n_der > 0
print(f"\nOBSERVED={n_obs} SIMULATED+linked={n_sim} orphan={n_orph} "
      f"DERIVED+linked={n_der} => {'HONEST PASS' if ok else 'FAIL'}")
db.close()
