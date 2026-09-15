"""Authoritative live probe: ledger + route inventory + route->HTTP map.
Trusted bytes on disk; run with PYTHONPATH=backend. No inline heredocs."""
import os
import sys

sys.path.insert(0, r"C:\Project 2.0\backend")
os.environ["PYTHONPATH"] = r"C:\Project 2.0\backend"
os.environ["PYTHONUTF8"] = "1"

from sqlalchemy import text as sql
from app.core.database import SessionLocal

from fastapi.testclient import TestClient
from app.main import app

print("=== ROUTE INVENTORY (registered on app, verbatim) ===")
routes = sorted({f"{r.path}".split("?")[0] for r in app.routes
                 if getattr(r, "path", "").startswith("/api/")})
for r in routes:
    print("  " + r)

print("\n=== LIVE HTTP SMOKE over every /api route ===")
c = TestClient(app)
bad = []
for r in routes:
    try:
        resp = c.get(r)
        body = resp.json() if resp.content else None
        n = len(body) if isinstance(body, (list, dict)) else "?"
        print(f"  HTTP {resp.status_code}  {r:<52} n={n}")
        if resp.status_code >= 400:
            bad.append(r)
    except Exception as e:
        print(f"  EXC {type(e).__name__}  {r:<52} {e}")
        bad.append(r)
print("\nNOT-OK:", bad if bad else "none (all green)")

print("\n=== LEDGER (live SQL, verbatim) ===")
db = SessionLocal()
print("  ais_tracks:")
for r in db.execute(sql(
    "SELECT COALESCE(method_tag,'(null)'), COALESCE(provenance_id::text,'(null)'), COUNT(*) "
    "FROM ais_tracks GROUP BY 1,2 ORDER BY 2,1")).fetchall():
    print(f"    tag={r[0]:<11} prov={str(r[1]):<6} n={r[2]}")
print("  derived_currents:")
for r in db.execute(sql(
    "SELECT COALESCE(method_tag,'(null)'), COALESCE(provenance_id::text,'(null)'), COUNT(*) "
    "FROM derived_currents GROUP BY 1,2 ORDER BY 2,1")).fetchall():
    print(f"    tag={r[0]:<11} prov={str(r[1]):<6} n={r[2]}")
db.close()

if bad:
    print("\nFINAL: FAIL (fix the listed routes)")
    sys.exit(1)
print("\nFINAL: ALL GREEN + HONEST LEDGER")
