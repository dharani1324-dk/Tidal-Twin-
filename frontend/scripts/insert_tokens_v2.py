"""TidalTwin — idempotent design-token v2 inserter (trusted bytes on disk).
Adds ONLY the genuinely-missing tokens to frontend/src/index.css, verbatim
design values from the approved Step-1 plan (chart-paper narrative family
already exists at L33-35 as --paper/--paper-ink/--paper-line — never duped).

Missing families this inserts if (and only if) absent:
  * --biolume / --biolume-ink   (confirmed-telemetry green: the one accent)
  * --caution / --caution-line  (chart-magenta: hazards ONLY, strictly reserved)
  * --font-serif                (Source Serif 4 — narrative surfaces only;
                                 --font-sans stays Archivo/Segoe for instruments)

Runs to completion with a verbatim report of EXACTLY what changed (or that
nothing needed to). Atomic-ish: only writes if the content actually changed.
"""
from io import open
from pathlib import Path

CSS = Path(r"C:\Project 2.0\frontend\src\index.css")

TARGETS = {
    "--biolume":      "  --biolume: #4fe0b8;            /* confirmed-water green (penetrates) */\n",
    "--biolume-ink":  "  --biolume-ink: #052e22;         /* ink on biolume fill */\n",
    "--caution":      "  --caution: #d6336c;            /* chart magenta — hazards ONLY */\n",
    "--caution-line": "  --caution-line: rgba(214, 51, 108, 0.42);\n",
    "--font-serif":   '  --font-serif: "Source Serif 4", "Archivo", Georgia, "Times New Roman", serif;\n',
}

ANCHOR = "--font-mono:"   # insert additive tokens immediately after this line


def main() -> int:
    if not CSS.exists():
        print("FAIL: {0} not on disk".format(CSS))
        return 1

    text = CSS.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    present = {ln.strip().split(":", 1)[0] for ln in lines if ln.strip().startswith("--")}
    missing = [k for k in TARGETS if k not in present]

    if not missing:
        print("  nothing to insert — all Step-1 v2 tokens already present (no-op, PASS)")
        return 0

    idx = next((i for i, ln in enumerate(lines) if ln.startswith(ANCHOR)), None)
    if idx is None:
        print("FAIL: anchor {0!r} not found in index.css".format(ANCHOR))
        return 1

    orig = len(lines)
    block = ["\n", "  /* ---- TidalTwin v2: honesty accents (approved Step-1) ---- */\n"]
    block += [TARGETS[k] for k in missing]
    block.append("\n")
    lines[idx + 1:idx + 1] = block

    new_text = "".join(lines)
    CSS.write_text(new_text, encoding="utf-8")

    print("  inserted {0} missing token(s) after line containing {1!r}:".format(len(missing), ANCHOR))
    for k in missing:
        print("    + {0}".format(k))
    print("  file grew from {0} -> {1} lines".format(orig, len(new_text.splitlines(keepends=True))))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
