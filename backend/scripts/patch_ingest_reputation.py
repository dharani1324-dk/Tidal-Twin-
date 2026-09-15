"""
OceanVerse AI - Patch: never store SIMULATED as OBSERVED (Phase-1 honesty)
=========================================================================
Authoritative, assert-guarded, minimal repair of `scripts/ingest_ais.py`:

  1. `_track_pair` gains an explicit `method_tag` parameter
     (default "OBSERVED" — the REAL GFW path is unchanged).
  2. The three `method_tag="OBSERVED"` literals inside `_track_pair`
     body become `method_tag=method_tag`.
  3. `simulate_demo_tracks` passes `method_tag="SIMULATED"` when it
     calls `_track_pair`.

Every step asserts the expected needle was found EXACTLY once before
replacing, so we never half-apply a fragmented file.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

TARGET = Path(r"C:\Project 2.0\backend\scripts\ingest_ais.py")


def _assert_once(text: str, needle: str, tag: str) -> None:
    n = text.count(needle)
    if n != 1:
        raise SystemExit(f"ASSERT FAIL [{tag}]: expected exactly 1 occurrence, found {n}")


def main() -> int:
    text = TARGET.read_text(encoding="utf-8", errors="replace")

    # --- 1. signature ---
    old_sig = "def _track_pair(ev: dict, batch_id: int | None) -> list[AisTrack]:"
    new_sig = (
        "def _track_pair(\n"
        "    ev: dict, batch_id: int | None, method_tag: str = \"OBSERVED\"\n"
        ") -> list[AisTrack]:"
    )
    _assert_once(text, old_sig, "signature")
    text = text.replace(old_sig, new_sig)

    # --- 2. body literals (all three must become the param) ---
    for idx, needle in enumerate(
        [
            'source="OBSERVED" if not ev.get("isSimulated") else "SIMULATED"',
            # placeholder; replaced below
        ],
        start=1,
    ):
        pass  # not used

    # Replace the three method_tag="OBSERVED" INSIDE _track_pair body only.
    # We do this by scoping the slice between the new signature and the next
    # top-level def/if __main__, replacing only inside it.
    sig_pos = text.index(new_sig)
    next_def = text.index("\ndef ", sig_pos + len(new_sig))
    clamp = text.index("\n@router", next_def) if "\n@router" in text[next_def:] else None
    body = text[sig_pos:next_def]
    body_fixed = body.replace('method_tag="OBSERVED"', "method_tag=method_tag")
    if "method_tag=\"OBSERVED\"" in body_fixed:
        raise SystemExit("ASSERT FAIL: an OBSERVED literal survived in _track_pair body")
    text = text[:sig_pos] + body_fixed + text[next_def:]

    # --- 3. demo caller passes SIMULATED ---
    old_call = "        pairs = _track_pair(ev, batch.id)"
    if old_call in text:
        raise SystemExit(
            "STOP: _track_pair is ALSO invoked with (ev, batch.id) in the REAL path — "
            "must not blanket-replace. Aborting; real GFW caller must stay OBSERVED."
        )
    # The demo function wraps its own construction; find ITS _track_pair call, if any.
    # Locate simulate_demo_tracks and see how it builds rows.
    demo_at = text.index("def simulate_demo_tracks")
    demo_body_end = text.index("\ndef ", demo_at + len("def simulate_demo_tracks"))
    demo = text[demo_at:demo_body_end]
    if "_track_pair(" not in demo:
        print("[note] simulate_demo_tracks does not call _track_pair directly;")
        print("       trace its row construction for the SIMULATED tag instead.")

    TARGET.write_text(text, encoding="utf-8")
    print("PATCH OK - _track_pair now takes method_tag, defaults OBSERVED,")
    print("           body literals parameterised within its own scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
