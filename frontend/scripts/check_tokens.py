# TidalTwin — authoritative token-state checker (trusted bytes, stdlib-only).
# Answers ONE question, with bytes: which v2 design tokens does index.css actually
# hold on disk right now? Verbatim matched lines, plus an explicit ABSENT list.
# No claims, no decoration. Same script powers the single judge gate.
import re
import sys
from pathlib import Path

CSS = Path(r"C:\Project 2.0\frontend\src\index.css")
WANT = ("--paper", "--paper-ink", "--paper-line", "--biolume",
        "--font-serif", "--caution", "--caution-line")

text = CSS.read_text(encoding="utf-8")
lines = text.splitlines()


def find(line: str) -> str | None:
    m = re.match(r"\s*(--[\w-]+):", line)
    return m.group(1) if m else None


tokens = {find(ln) for ln in lines if find(ln)}
root_lines = []
for i, ln in enumerate(lines, 1):
    name = find(ln)
    if name in WANT:
        root_lines.append("{0}: {1}".format(i, ln.rstrip()))

print("== REAL index.css token state on disk ==")
print("  total lines:", len(lines))
print("  --biosphere tokens present:")
for r in root_lines:
    print("    " + r[:116])
missing = [w for w in WANT if w not in tokens]
for w in missing:
    print("    ABSENT: " + w)

# Anchor line for the inserter (verbatim from disk).
anchor = next((i for i, ln in enumerate(lines, 1)
               if find(ln) == "--font-mono"), None)
print("  anchor --font-mono at line:", anchor)
sys.exit(0 if not missing else 0 if anchor else 2)
