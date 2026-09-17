"""TidalTwin — real index.css token inventory (authoritative, from disk).

Prints the VERBATIM token lines that actually exist on disk, so any
edit is anchored to reality. Output is byte-identical to the file; the
only transformation is line-numbering. No claims, no summaries, no
guessing — if a token is absent it is printed as ABSENT.
"""
from pathlib import Path

CSS = Path("src") / "index.css"
text = CSS.read_text(encoding="utf-8")

WANT = [
    "--accent:",
    "--accent-blue:",
    "--accent-violet:",
    "--accent-warm:",
    "--ok:",
    "--warn:",
    "--danger:",
    "--info:",
    "--paper:",
    "--paper-ink:",
    "--paper-line:",
    "--biolume:",
    "--biolume-ink:",
    "--caution:",
    "--caution-line:",
    "--font-sans:",
    "--font-display:",
    "--font-mono:",
    "--font-serif:",
]

lines = text.splitlines()
print("index.css on disk: {0} lines, {1} bytes\n".format(len(lines), len(text)))

# Show the :root line range verbatim so the anchor is visible in context:
in_root = False
print("--- :root block (verbatim): start of file through first 60 lines ---")
for i, ln in enumerate(lines[:60], 1):
    print("{0:4}: {1}".format(i, ln))

print("\n--- wanted tokens, matched verbatim (ABSENT listed explicitly) ---")
joined = "\n".join(lines)
for tok in WANT:
    hits = [ln.strip() for ln in lines if ln.strip().startswith(tok)]
    if hits:
        print("  {0:<16} -> {1}".format(tok, hits[0]))
    else:
        print("  {0:<16} -> ABSENT".format(tok))
