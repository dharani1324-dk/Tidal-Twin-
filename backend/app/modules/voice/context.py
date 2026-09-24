"""TIDE Voice Agent - optional situational synopsis.

When the user asks the agent to "include current context", the backend composes
a compact, read-only snapshot reusing existing subsystems (health counts,
TIDE rankings, intelligence events).  Every block is individually guarded so a
slow or failing subsystem degrades to an empty block rather than blocking the
session.  This is premium context ONLY - the regular tool layer never calls it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _compact_event(event: dict, index: int) -> dict:
    return {
        "id": f"event-{index}",
        "type": event.get("event_type"),
        "location": event.get("location"),
        "variable": event.get("variable"),
        "severity": event.get("data_status") or event.get("model_status"),
        "status": event.get("current_status"),
        "since": event.get("started"),
    }


def tide_synopsis(db: Session) -> dict:
    """Best-effort snapshot of what TidalTwin currently knows.

    Safe to call; never raises (each block has its own guard).
    """
    out: dict = {"generated_at": datetime.now(timezone.utc).isoformat()}

    # Block 1 - data footprint (reuses the health probe).
    try:
        from app.api.health import _check_ocean_data

        data = _check_ocean_data(db)
        if data.get("observations"):
            out["data"] = {
                "locations": data["locations"],
                "observations": data["observations"],
                "simulated_observations": data["simulated_observations"],
            }
    except Exception as exc:  # noqa: BLE001 - degradation strategy
        log.warning("voice synopsis: ocean data block skipped (%s)", type(exc).__name__)

    # Block 2 - TIDE top recommendation (request-time, existing engine).
    try:
        from app.modules.ai.tide import TideEngine

        ranking = TideEngine(db).rankings()
        if ranking:
            top = ranking[0]
            out["tide"] = {
                "top_candidate_id": top.get("candidate_id"),
                "location": top.get("location"),
                "variable": top.get("variable"),
                "observation_type": top.get("observation_type"),
                "observation_value": top.get("observation_value"),
                "reason": top.get("reason"),
                "limitations": top.get("limitations"),
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("voice synopsis: TIDE block skipped (%s)", type(exc).__name__)

    # Block 3 - active intelligence events (existing event adapter).
    try:
        from app.modules.ai.tide import adapters

        events = adapters.detect_events(db).get("events", []) or []
        active = []
        for idx, ev in enumerate(events):
            status = (ev.get("current_status") or "").lower()
            if status in ("active", "developing", "observed", "intensifying") or idx == 0:
                active.append(_compact_event(ev, idx))
        if active:
            out["events"] = active[:5]
    except Exception as exc:  # noqa: BLE001
        log.warning("voice synopsis: events block skipped (%s)", type(exc).__name__)

    return out