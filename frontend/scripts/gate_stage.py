# TidalTwin — frontend stage gates (authoritative, trusted on disk).
# Runs tsc --noEmit -> oxlint -> vite build in the REAL frontend, prints
# verbatim output, nonzero exit on any failure. No decoration, no claims.
import subprocess, sys
from pathlib import Path

ROOT = Path(r"C:\Project 2.0\frontend")
BIN = ROOT / "node_modules" / ".bin"
PY = Path(r"C:\Project 2.0\backend\.venv\Scripts\python.exe")


def run(name, cmd):
    print("=== GATE: {0} ===".format(name))
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if out:
        print(out[:2600])
    if err:
        print("  [stderr] " + err[:1600])
    ok = r.returncode == 0
    print("  -> {0} exit={1}".format("PASS" if ok else "FAIL", r.returncode))
    return ok


def node_bin(name):
    return str(BIN / (name + ".cmd"))


gates = [
    ("tsc", run("tsc --noEmit", [node_bin("tsc"), "--noEmit", "--pretty", "false"])),
    ("oxlint", run("oxlint src", [node_bin("oxlint"), "src"])),
    ("build", run("vite build", [node_bin("vite"), "build", "--logLevel", "warn"])),
]
print("=== GATE SUMMARY ===")
for name, ok in gates:
    print("  {0:<8} {1}".format(name, "PASS" if ok else "FAIL"))
print("  TOTAL  : {0}".format("ALL GREEN" if all(ok for _, ok in gates) else "FAILURES PRESENT"))
sys.exit(0 if all(ok for _, ok in gates) else 1)
