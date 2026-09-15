import os, sys
sys.path.insert(0, r"C:\Project 2.0\backend")
os.environ["PYTHONPATH"] = r"C:\Project 2.0\backend"
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
ok = True
rows = [
    ("/api/v1/health", "Phase 0"),
    ("/api/v1/currents/derived", "Phase 1"),
    ("/api/v1/currents/summary", "Phase 1"),
    ("/api/v1/currents/lens", "Phase 2"),
    ("/api/v1/edr/collections", "Phase 3"),
]
for path, phase in rows:
    try:
        r = c.get(path)
        j = r.json()
        if isinstance(j, dict):
            keys = sorted(j.keys())
            desc = "dict[" + ",".join(keys[:4]) + "]"
            if r.status_code >= 400:
                ok = False
        else:
            desc = "list[" + str(len(j)) + "]"
            if r.status_code >= 400:
                ok = False
        print("  {0:<42} HTTP {1}  {2}".format(path, r.status_code, desc))
    except Exception as e:
        ok = False
        print("  {0:<42} EXC {1}: {2}".format(path, type(e).__name__, e))

print("  VERDICT:", "ALL PHASES LIVE + PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
