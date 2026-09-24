# TidalTwin — corrected token-state checker (trusted bytes, stdlib only).
# Reports verbatim what index.css really holds NOW + exact anchor lines for the
# next edit. WANT is fully defined here so the script cannot NameError.
import re
import sys
from pathlib import Path

CSS = Path(r"C:\Project 2.0\frontend\src\index.css")
WANT = ("--paper", "--paper-ink", "--paper-line",
        "--biolume", "--biolume-ink", "--caution", "--caution-line",
        "--font-serif")

text = CSS.read_text(encoding="utf-8")
lines = text.splitlines()

TOKEN = re.compile(r"^\s*(--[\w-]+):")


def ln_token(s: str):
    m = TOKEN.match(s)
    return m.group(1) if m else None


tokens = {t for ln in lines if (t := ln_token(ln))}

print("== REAL index.css token state on disk (verbatim anchor hunting) ==")
print("  file:", CSS)
print("  bytes:", CSS.stat().st_size, " lines:", len(lines))
print("  v2 tokens PRESENT:", sorted(w for w in WANT if w in tokens) or "(none)")
print("  v2 tokens ABSENT :", sorted(w for w in WANT if w not in tokens) or "(none)")

print("\n== VERBATIM :root block (lines 1-60) — the real bytes next edit will anchor on ==")
for i in range(min(len(lines), 60)):
    print("{0:4}: {1}".format(i + 1, lines[i]))

sys.exit(0)
