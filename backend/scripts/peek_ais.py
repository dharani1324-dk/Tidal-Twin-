import os, sys
sys.path.insert(0, r"C:\Project 2.0\backend")
os.environ.setdefault("PYTHONPATH", r"C:\Project 2.0\backend")
from app.core.database import SessionLocal
from app.models.ais import AisTrack
from app.models.provenance import ProvenanceRecord

db = SessionLocal()
n = db.query(AisTrack).count()
n_sim = db.query(AisTrack).filter(AisTrack.method_tag == "SIMULATED").count()
n_real = db.query(AisTrack).filter(AisTrack.method_tag == "OBSERVED").count()
n_prov = db.query(ProvenanceRecord).count()
rows = db.query(AisTrack).order_by(AisTrack.id.desc()).limit(3).all()

print(f"ais_tracks total      : {n}")
print(f"  SIMULATED (demo)    : {n_sim}")
print(f"  OBSERVED (real)     : {n_real}")
print(f"provenance_register   : {n_prov}")
for r in rows:
    sog = f"{r.sog_mps:.1f}" if r.sog_mps is not None else "NULL"
    prov = r.provenance_id if r.provenance_id is not None else "NULL"
    print(f"  track id={r.id} vessel={r.vessel_hash[:10]}... sog={sog} tag={r.method_tag} prov={prov}")

prov_rows = db.query(ProvenanceRecord).order_by(ProvenanceRecord.id.desc()).limit(3).all()
print("\nNewest provenance batches:")
for p in prov_rows:
    print(f"  id={p.id} method={p.method_tag} source={p.source_name[:40]}...")
db.close()
