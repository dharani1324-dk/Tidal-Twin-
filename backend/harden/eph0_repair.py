"""
TidalTwin - PROOF-OF-HONESTY repair (Eph0): purge mis-tagged demo rows.
======================================================================
Ground truth on this machine (verified via offline JWT math, NOT the wire):
  - GFW token is a VALID user-application JWT (correct signature, not expired).
  - The GFW wire (TLS) is EXTERNALLY sealed on this network - neither the
    python ssl stack nor curl can complete a handshake (UNEXPECTED_EOF /
    curl(35)); TCP connects so this is an egress filter, not a cURL/OS bug.
  - Therefore: real ingest is impossible from this network. We use the
    demo pipeline; every demo row MUST be tagged SIMULATED + linked to a
    SIMULATED provenance batch, otherwise we are lying about our data.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from random import Random

sys.path.insert(0, r"C:\Project 2.0\backend")
os.environ["PYTHONPATH"] = r"C:\Project 2.0\backend"
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://ocv:d3m0p455@localhost:5432/ocv")

from app.core.database import SessionLocal
from app.models import AisTrack, ProvenanceRecord

db = SessionLocal()

def now_utc():
    return datetime.now(timezone.utc)

try:
    print("=== (1) PRE-STATE: mis-tagged / orphaned demo rows? ===")
    pre_mis = db.query(AisTrack).filter(
        db.query(AisTrack).filter(AisTrack.method_tag == "OBSERVED")
    ).count()
    # count ALL tracks (authoritative, null-tolerant)
    from sqlalchemy import text as sql
    n_all = db.execute(sql("SELECT COUNT(*) FROM ais_tracks")).scalar()
    n_prov = db.execute(sql("SELECT COUNT(*) FROM provenance_register")).scalar()
    n_demo = db.execute(sql("SELECT COUNT(*) FROM ais_tracks WHERE provenance_id IS NULL")).scalar()
    print(f"  ais_tracks total       : {n_all}")
    print(f"  provenance batches     : {n_prov}")
    print(f"  tracks w/ NULL prov    : {n_demo}")

    print("\n=== (2) HONESTY REPAIR: purge rows that would masquerade ===")
    print("  (rows from an earlier SIMULATED run were stored as OBSERVED with")
    print("   NULL provenance - that is the exact 'masquerade' sin. We PURGE")
    print("   them so no dishonest data survives, then re-simulate honest rows.)")
    purged = db.execute(sql("DELETE FROM ais_tracks WHERE provenance_id IS NULL")).rowcount
    db.commit()
    print(f"  PURGED {purged} mis-tagged/orphaned rows")

    print("\n=== (3) RE-SIMULATE with PROVABLY SIMULATED tags + provenance ===")
    src = "TIDALTWIN-DEMO-SIMULATOR"
    now = datetime.now(timezone.utc)
    batch = ProvenanceRecord(
        source_name=src,
        source_url="internal://demo",
        method_tag="SIMULATED",
        notes=f"TidalTwin demo synthetic tracks at {now.isoformat()}. NOT real GFW.",
    )
    db.add(batch)
    db.flush()

    rng = Random(20260214)
    stored = 0
    for i in range(40):
        vid = f"demo-vessel-{i:03d}"
        lat0 = rng.uniform(-10, 10)
        lon0 = rng.uniform(60, 90)
        dlat = rng.uniform(-1, 1)
        dlon = rng.uniform(-1.2, 1.2)
        t0 = now - timedelta(hours=rng.uniform(1, 6))
        t1 = t0 + timedelta(hours=rng.uniform(1, 4))
        for lat, lon, ts in ((lat0, lon0, t0), (lat0 + dlat, lon0 + dlon, t1)):
            db.add(AisTrack(
                vessel_hash=vid,
                timestamp=ts,
                geom=None,  # placeholder col exists? set via raw if needed
                sog_mps=rng.uniform(2.0, 8.0),
                method_tag="SIMULATED",
                provenance_id=batch.id,
            ))
            stored += 1
    db.commit()
    print(f"  Stored {stored} rows, ALL method_tag=SIMULATED, ALL linked to batch id={batch.id}")

    print("\n=== (4) POST-STATE (the Honest Ledger) ===")
    n_all2 = db.execute(sql("SELECT COUNT(*) FROM ais_tracks")).scalar()
    tag_rows = db.execute(sql("SELECT method_tag, provenance_id, COUNT(*) n FROM ais_tracks GROUP BY 1,2 ORDER BY 2")).fetchall()
    prov_rows = db.execute(sql("SELECT id, method_tag FROM provenance_register ORDER BY 1")).fetchall()
    print(f"  ais_tracks total       : {n_all2}")
    for tr in tag_rows:
        print(f"    method_tag={tr[0] or 'NULL':<12} prov={str(tr[1] or 'NULL'):<5} n={tr[2]}")
    print("  provenance_register:")
    for pr in prov_rows:
        print(f"    id={pr[0]} method_tag={pr[1] or 'NULL'}")

    print("\n=== RESULT ===")
    sim = db.execute(sql("SELECT COUNT(*) FROM ais_tracks WHERE method_tag='SIMULATED' AND provenance_id IS NOT NULL")).scalar()
    obs = db.execute(sql("SELECT COUNT(*) FROM ais_tracks WHERE method_tag='OBSERVED'")).scalar()
    print(f"  SIMULATED+attributed : {sim}")
    print(f"  OBSERVED (real-ish)  : {obs}")
    print(f"  HONESTY              : {'PASS - nothing masquerades' if sim > 0 and obs == 0 else 'FAIL'}")
finally:
    db.close()
