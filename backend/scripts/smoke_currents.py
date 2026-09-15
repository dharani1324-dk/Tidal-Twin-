import os, sys, warnings
os.environ.setdefault("PYTHONPATH", r"C:\Project 2.0\backend")
sys.path.insert(0, r"C:\Project 2.0\backend")
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
print("OpenAPI paths containing 'currents':")
spec = c.get("/openapi.json").json()
for p in sorted(k for k in spec["paths"] if "current" in k):
    print("   ", p, sorted(spec["paths"][p].keys()))
print()
r = c.get("/api/v1/currents/derived")
print("GET /api/v1/currents/derived ->", r.status_code)
body = r.json()
print("   type:", type(body).__name__, "len:", len(body) if hasattr(body, "__len__") else "?")
print("   sample:", str(body)[:400])
print()
r2 = c.get("/api/v1/currents/derived/summary")
print("GET /api/v1/currents/derived/summary ->", r2.status_code)
print("   body keys:", list(r2.json().keys()) if r2.status_code == 200 else r2.text[:200])
