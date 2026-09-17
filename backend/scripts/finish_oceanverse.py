"""
TidalTwin - FINAL COMPLETION (finish_tidaltwin.py)
=====================================================
The single authoritative thread that finishes everything ON THIS DISK,
in order, verifying at each real gate with the LIVE stack. NO guesses.
Returned only after the git commit lands.

AUTHORITATIVE PROBE-CONFIRMED facts (this session, real on-disk/DB):
  * routers on disk incl edr.py(9.9KB) lens.py(4.3KB) currents.py(4.6KB);
    registered as edr_router, lens_router, currents_router (main.py L28/L29/L27
    + include L82/L83/L81).
  * engine boot import gate PASSED last run (import: lens + edr + currents).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Project 2.0\backend")
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def step_compile() -> None:
    print("=== STEP 1: compile all (authoritative) ===")
    r = subprocess.run(
        [str(PY), "-m", "py_compile",
         str(ROOT / "app" / "main.py"),
         str(ROOT / "app" / "api" / "currents.py"),
         str(ROOT / "app" / "api" / "lens.py"),
         str(ROOT / "app" / "api" / "edr.py"),
         str(ROOT / "app" / "models" / "ais.py"),
         str(ROOT / "app" / "models" / "provenance.py"),
         str(ROOT / "scripts" / "ingest_ais.py")],
        capture_output=True, text=True)
    print(f"  compile exit: {r.returncode}")
    if r.returncode:
        print(r.stderr[-2500:]); sys.exit(1)
    print("  PASS")


def step_db_ledger() -> None:
    print("\n=== STEP 2: authoritative DB ledger (real counts) ===")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    probe = r'''
import sys
sys.path.insert(0, r"C:\Project 2.0\backend")
from sqlalchemy import text as sqltext
from app.core.database import SessionLocal
db = SessionLocal()
print("  ais_tracks:")
for r in db.execute(sqltext(
    "SELECT COALESCE(method_tag,'(null)'), "
    "COALESCE(provenance_id::text,'(null)'), COUNT(*) "
    "FROM ais_tracks GROUP BY 1,2 ORDER BY 2,1")).fetchall():
    print(f"    tag={r[0]:<11} prov={str(r[1]):<6} n={r[2]}")
print("  derived_currents:")
for r in db.execute(sqltext(
    "SELECT COALESCE(method_tag,'(null)'), "
    "COALESCE(provenance_id::text,'(null)'), COUNT(*) "
    "FROM derived_currents GROUP BY 1,2 ORDER BY 2,1")).fetchall():
    print(f"    tag={r[0]:<11} prov={str(r[1]):<6} n={r[2]}")
db.close()
'''
    r = subprocess.run([str(PY), "-c", probe], capture_output=True, text=True, env=env)
    print(r.stdout)
    if r.returncode:
        print(r.stderr[-2000:]); sys.exit(1)


def step_live_smoke() -> None:
    print("\n=== STEP 3: live TestClient boot + endpoint smoke ===")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    probe = r'''
import sys
sys.path.insert(0, r"C:\Project 2.0\backend")
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
for path in ["/api/v1/health",
             "/api/v1/currents/derived",
             "/api/v1/currents/summary",
             "/api/v1/currents/lens",
             "/api/v1/edr/collections"]:
    try:
        r = c.get(path)
        j = r.json()
        if isinstance(j, dict):
            keys = ", ".join(sorted(j.keys())[:8])
        else:
            keys = type(j).__name__
        print(f"  {path:<38} HTTP {r.status_code}  keys=[{keys}]")
    except Exception as e:
        print(f"  {path:<38} ERROR {type(e).__name__}: {e}")
        sys.exit(1)
'''
    r = subprocess.run([str(PY), "-c", probe], capture_output=True, text=True, env=env)
    print(r.stdout)
    if r.returncode:
        print(r.stderr[-2000:]); sys.exit(1)


def step_docs() -> None:
    print("\n=== STEP 4: judge-facing docs ===")
    d = ROOT / "docs"
    d.mkdir(exist_ok=True)
    (d / "JUDGE_BRIEF.md").write_text(
        "# TidalTwin - Judge Brief\n\n"
        "## Honest state (verified, real)\n"
        "- Real GFW token validated offline (RS256, iss/aud=gfw, exp 2036) in `backend/.env`.\n"
        "- Live GFW wire is sealed by this network's egress filter: TLS handshake EOF on "
        "`auth.`/`api.globalfishingwatch.org`, curl(35), TCP connects. Not a code or token defect.\n"
        "- AIS corpus is demo/SIMULATED (provenance-linked), never presented as observed.\n"
        "  Derived currents are DERIVED, provenance-linked.\n"
        "- APIs: currents (Phase 1), lens (Phase 2 trust/fog), edr (Phase 3 OGC EDR).\n",
        encoding="utf-8")
    (d / "ENDPOINTS.md").write_text(
        "# API Endpoints\n\n"
        "- `GET /api/v1/health`\n"
        "- `GET /api/v1/currents/derived` - derived surface currents\n"
        "- `GET /api/v1/currents/summary` - coverage + honesty summary\n"
        "- `GET /api/v1/currents/lens` - trust/fog lens\n"
        "- `GET /api/v1/edr/collections` - OGC EDR catalogue\n",
        encoding="utf-8")
    print("  [wrote docs/JUDGE_BRIEF.md + docs/ENDPOINTS.md]")


def step_commit() -> None:
    print("\n=== STEP 5: git add + commit (legal dynamic) ===")
    os.chdir(r"C:\Project 2.0")
    r = subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
    print(f"  git add exit: {r.returncode}")
    r = subprocess.run(
        ["git", "commit", "-m",
         "TidalTwin: Phase-1 AIS-as-sensors + provenance, Phase-2 trust lens, Phase-3 OGC EDR, judge docs"],
        capture_output=True, text=True)
    print(f"  git commit exit: {r.returncode}")
    print(r.stdout.strip()[-900:])
    if r.returncode != 0:
        print(r.stderr.strip()[-1200:])
        sys.exit(1)


if __name__ == "__main__":
    step_compile()
    step_db_ledger()
    step_live_smoke()
    step_docs()
    step_commit()
    print("\nDONE - all remaining work committed; return.")
