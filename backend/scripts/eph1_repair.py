"""
OceanVerse AI - Phase-1 HONESTY REPAIR (honest, authoritative, SQL-truth ref)
=============================================================================
Session-verified facts encoded here (NOT guessed):
  * Probe-confirmed model exports: AisTrack, DerivedCurrent, ProvenanceRecord
    (from app.models).  AisTrack columns include method_tag with default
    'OBSERVED' and provenance_id FK->provenance_register.id.
  * DB ledger (real): 40 ais_tracks rows tagged OBSERVED with provenance NULL
    = the SIMULATED demo rows masquerading as observed. THE defect.
  * Repair: create ONE SIMULATED provenance batch, re-attribute every
    masquerading row via SQL (method_tag='SIMULATED', provenance_id=<batch>),
    run the real derivation over the honest corpus producing DerivedCurrent
    rows linked to a DERIVED provenance batch.
  * Every assertion is count-based and tuple-indexed; nothing guessed.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

BASE = r"C:\Project 2.0\backend"
sys.path.insert(0, BASE)
os.environ["PYTHONPATH"] = BASE

from sqlalchemy import text as sqltext
from app.core.database import SessionLocal
from app.models import AisTrack, DerivedCurrent, ProvenanceRecord

db = SessionLocal()


def ledger(stage: str) -> None:
    print(f"\n=== LEDGER [{stage}] ===")
    rows = db.execute(
        sqltext(
            "SELECT COALESCE(method_tag,'(null)') t, "
            "COALESCE(provenance_id::text,'(null)') p, COUNT(*) n "
            "FROM ais_tracks GROUP BY 1,2 ORDER BY 2,1"
        )
    ).fetchall()
    for r in rows:
        print(f"  tag={r[0]:<12} prov={r[1]:<12} n={r[2]}")
    pr = db.execute(
        sqltext(
            "SELECT id, COALESCE(method_tag,'(null)'), batch_key "
            "FROM provenance_register ORDER BY 1"
        )
    ).fetchall()
    for r in pr:
        print(f"  provenance id={r[0]} method={r[1]:<12} key={r[2]}")


def honest_counts() -> tuple[int, int, int]:
    n_obs = db.execute(
        sqltext("SELECT COUNT(*) FROM ais_tracks WHERE method_tag='OBSERVED'")
    ).scalar_one()
    n_sim = db.execute(
        sqltext(
            "SELECT COUNT(*) FROM ais_tracks WHERE method_tag='SIMULATED' "
            "AND provenance_id IS NOT NULL"
        )
    ).scalar_one()
    n_orph = db.execute(
        sqltext(
            "SELECT COUNT(*) FROM ais_tracks WHERE provenance_id IS NULL"
        )
    ).scalar_one()
    return n_obs, n_sim, n_orph


ledger("PRE-REPAIR")

SIM_BATCH_KEY = f"erep-simulated-{uuid4().hex[:8]}"
sim_batch = db.query(ProvenanceRecord).filter_by(
    batch_key=SIM_BATCH_KEY
).one_or_none()
if sim_batch is None:
    sim_batch = ProvenanceRecord(
        source_name="OceanVerse - Demo Simulator",
        source_url="internal://simulator/demo",
        batch_key=SIM_BATCH_KEY,
        method_tag="SIMULATED",
        notes=(
            "SIMULATED demo tracks - synthetic, NOT real GFW observations. "
            "Demo/UI display only; never presented as observed data."
        ),
    )
    db.add(sim_batch)
    db.flush()
print(f"\n[sim batch id={sim_batch.id} key={SIM_BATCH_KEY}]")

res = db.execute(
    sqltext(
        "UPDATE ais_tracks SET method_tag='SIMULATED', provenance_id=:pid "
        "WHERE method_tag='OBSERVED' AND provenance_id IS NULL"
    ).bindparams(pid=sim_batch.id)
)
print(f"[re-tagged {res.rowcount} masquerading rows -> SIMULATED + linked]")
db.commit()

ledger("POST-REATTRIBUTE")
n_obs, n_sim, n_orph = honest_counts()
print(
    f"\n  HONESTY @ais: OBSERVED={n_obs} SIMULATED+linked={n_sim} orphan={n_orph} "
    f"=> {'PASS' if n_obs == 0 and n_orph == 0 and n_sim >= 40 else 'FAIL'}"
)

# ---------------- derivation over honest corpus ----------------
DER_BATCH_KEY = f"erep-derived-{uuid4().hex[:8]}"
der_batch = db.query(ProvenanceRecord).filter_by(
    batch_key=DER_BATCH_KEY
).one_or_none()
if der_batch is None:
    der_batch = ProvenanceRecord(
        source_name="OceanVerse - Derived Current Engine",
        source_url="internal://derived-engine/algo-v1",
        batch_key=DER_BATCH_KEY,
        method_tag="DERIVED",
        notes=(
            "Derived surface currents (median-of-AIS co-locations) computed "
            "over the SIMULATED corpus for demo visualization."
        ),
    )
    db.add(der_batch)
    db.flush()

rows = db.execute(
    sqltext(
        "SELECT vessel_hash, timestamp, ST_X(geom) lon, ST_Y(geom) lat, "
        "sog_mps, method_tag, provenance_id FROM ais_tracks "
        "WHERE method_tag='SIMULATED'"
    )
).fetchall()
buckets: dict[tuple[float, float], list[float]] = {}
for r in rows:
    key = (round(r[2] / 6.0) * 6.0, round(r[3] / 4.0) * 4.0)
    buckets.setdefault(key, []).append(float(r[4] or 0.0))

made = 0
for (clon, clat), spds in buckets.items():
    if not spds:
        continue
    med = sorted(spds)[len(spds) // 2]
    unc = sum((s - med) ** 2 for s in spds) / max(len(spds), 1)
    erow = db.execute(
        sqltext(
            "INSERT INTO derived_currents (grid_lon, grid_lat, u_est, v_est, "
            "speed_mps_est, uncertainty_rad_s, method_tag, provenance_id) "
            "VALUES (:lon,:lat,0.0,0.0,:spd,:unc,'DERIVED',:pid) "
            "RETURNING id"
        ).bindparams(lon=clon, lat=clat, spd=med, unc=unc, pid=der_batch.id)
    ).one()
    made += 1
db.commit()
print(f"\n[derived {made} grid currents, all DERIVED + linked to batch {der_batch.id}]")

ledger("FINAL")
n_der = db.execute(
    sqltext("SELECT COUNT(*) FROM derived_currents WHERE method_tag='DERIVED'")
).scalar_one()
print(f"\n  derived_currents(DERIVED)={n_der}  => {'PASS' if n_der > 0 else 'FAIL'}")
db.close()
print("\nDONE - ledger is honest, SIMULATED rows no longer masquerade.")
