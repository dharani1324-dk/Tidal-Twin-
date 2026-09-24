"""TidalTwin - Demonstration Mode API (Phase 9).

Provides an explicit, honest demonstration layer:

* ``GET  /api/v1/demo/status`` - what demonstration data exists, how it is
  labelled, and which detected event is the best *demonstration* event based on
  the availability of downstream intelligence (not on any scientific ranking).
* ``POST /api/v1/demo/seed``   - create the existing SIMULATED anomaly dataset
  (idempotent unless ``force=true``). Reuses ``scripts.simulate_anomaly``.
* ``POST /api/v1/demo/reset``  - delete ONLY the labelled simulated/demo rows.
  Real observations are never touched.

Simulation safety
-----------------
Simulated rows are identified by ``source`` starting with ``SIMULATED`` /
``SYNTHETIC`` / ``DEMO``.  Every response that describes them carries the
``DEMONSTRATION DATA`` marker, and the reset/seed operations can only ever
select rows matching that filter.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.observation import OceanObservation
from app.modules.ai.forensics.fingerprint import fingerprint
from app.modules.ai.tide.adapters import invalidate_caches, observation_status
from app.modules.ai.tide.engine import TideEngine
from app.modules.ai.twin.events import detect_events

router = APIRouter(prefix="/api/v1/demo", tags=["Demonstration"])

DEMO_MARKER = "DEMONSTRATION DATA"
SIMULATED_MARKER = "SIMULATED OBSERVATION - DEMONSTRATION ONLY"

# Static, honest description of the guided tour. The frontend navigates the
# real application; nothing here pretends to compute anything.
DEMO_GUIDE_STEPS: list[dict] = [
    {"step": 1, "title": "Detect an ocean event", "route": "/anomalies",
     "description": "Browse events the detector actually found in the current dataset."},
    {"step": 2, "title": "Investigate why it happened", "route": "/forensics",
     "description": "Open Ocean Forensics for the event's region."},
    {"step": 3, "title": "Inspect Event DNA", "route": "/forensics",
     "description": "View the event fingerprint built from the available signals."},
    {"step": 4, "title": "See where information is missing", "route": "/tide",
     "description": "Inspect uncertainty and data-gap factors. Values that cannot be computed show as unavailable."},
    {"step": 5, "title": "TIDE recommends the next observation", "route": "/tide",
     "description": "Ranked candidates from the real TIDE scoring pipeline."},
    {"step": 6, "title": "Simulate the observation", "route": "/tide",
     "description": "Use 'What if we measure here?' - clearly labelled SIMULATED OBSERVATION."},
    {"step": 7, "title": "Replay the decision", "route": "/tide/replay",
     "description": "Compare model-only vs TIDE-assisted decision paths."},
    {"step": 8, "title": "Validate and ask Copilot", "route": "/tide/validation",
     "description": "Review the validation/benchmark framework, then ask the Copilot to explain."},
]


def _upper(col):
    return func.upper(func.coalesce(col, ""))


def _simulated_filter():
    return or_(
        _upper(OceanObservation.source).like("SIMULATED%"),
        _upper(OceanObservation.source).like("SYNTHETIC%"),
        _upper(OceanObservation.source).like("DEMO%"),
    )


def _count(db: Session, *criteria) -> int:
    q = db.query(func.count(OceanObservation.id))
    if criteria:
        q = q.filter(*criteria)
    return q.scalar() or 0


def _demo_analysis(db: Session) -> dict:
    total = _count(db)
    simulated = _count(db, _simulated_filter())
    rows = (
        db.query(OceanObservation.source, func.count(OceanObservation.id))
        .group_by(OceanObservation.source)
        .order_by(func.count(OceanObservation.id).desc())
        .all()
    )
    sources = []
    for source, count in rows:
        status = observation_status(OceanObservation(source=source, data_type="observation"))
        sources.append(
            {
                "source": source or "UNKNOWN",
                "count": count,
                "status": status,
                "is_simulated": status in ("SIMULATED", "SYNTHETIC"),
            }
        )
    return {
        "total_observations": total,
        "simulated_observations": simulated,
        "real_observations": total - simulated,
        "sources": sources,
    }


def _select_demonstration_event(db: Session, events: list[dict]) -> dict:
    """Pick the event with the most complete downstream intelligence available.

    This is a practical/availability selection only - it is explicitly NOT a
    scientific "best event" ranking.
    """
    if not events:
        return {
            "available": False,
            "event_id": None,
            "reason": (
                "No detected events exist in the current dataset. Use "
                "'Seed demonstration data' to create a labelled SIMULATED event."
            ),
            "criteria": [],
            "candidates_considered": 0,
        }

    engine = TideEngine(db)
    best: dict | None = None
    considered = events[:20]
    for index, event in enumerate(considered):
        event_id = f"event-{index}"
        variable = {
            "strong_current_event": "current_speed",
            "coastal_flooding_risk": "wave_height",
        }.get(event.get("event_type"), "temperature")
        try:
            dna = fingerprint(event)
        except Exception:
            dna = {}
        try:
            candidates = engine.rankings(location_id=event.get("location_id"), variable=variable)
        except Exception:
            candidates = []
        has_dna = bool(dna)
        has_candidates = bool(candidates)
        has_evidence = any(c.get("evidence") for c in candidates)
        has_timeline = event.get("began_hours_ago") is not None
        score = sum([has_dna, has_candidates, has_evidence, has_timeline])
        criteria = [
            label
            for ok, label in (
                (has_dna, "Event DNA available"),
                (has_candidates, "TIDE candidates available"),
                (has_evidence, "Evidence available"),
                (has_timeline, "Event timeline available"),
            )
            if ok
        ]
        entry = {
            "available": True,
            "event_id": event_id,
            "location_id": event.get("location_id"),
            "location": event.get("location"),
            "event_type": event.get("event_type"),
            "label": event.get("label"),
            "data_status": event.get("data_status") or "real",
            "completeness_score": score,
            "criteria": criteria,
            "candidate_count": len(candidates),
            "reason": (
                "Selected as the DEMONSTRATION EVENT because it has the most "
                f"downstream intelligence available ({score}/4 practical criteria). "
                "This is not a scientific ranking."
            ),
            "candidates_considered": len(considered),
        }
        if best is None or entry["completeness_score"] > best["completeness_score"]:
            best = entry
    return best or {}


@router.get("/status")
def demo_status(db: Session = Depends(get_db)) -> dict:
    """Honest description of demonstration data + the demonstration event."""
    analysis = _demo_analysis(db)
    try:
        events = detect_events(db).get("events", [])
    except Exception:
        events = []
    demonstration_event = _select_demonstration_event(db, events)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "demo_data_present": analysis["simulated_observations"] > 0,
        "labels": {"dataset": DEMO_MARKER, "simulated_observation": SIMULATED_MARKER},
        **analysis,
        "detected_events": len(events),
        "demonstration_event": demonstration_event,
        "guide_steps": DEMO_GUIDE_STEPS,
        "notes": [
            "Demonstration observations are stored alongside real observations but are "
            "always labelled SIMULATED via their source; they are never presented as real.",
            "RESET DEMO deletes only labelled simulated rows and never alters real observations.",
        ],
    }


def _detected_event_count(db: Session) -> int:
    try:
        return len(detect_events(db).get("events", []))
    except Exception:
        return 0


@router.post("/seed")
def demo_seed(
    location: str = Query("goa", description="Location alias or exact name"),
    kind: str = Query("heatwave", pattern="^(heatwave|surge)$"),
    force: bool = Query(False, description="Add another block even if demo data + events exist"),
    db: Session = Depends(get_db),
) -> dict:
    """Create the existing SIMULATED anomaly demonstration dataset.

    Repeated calls are safe: if demo data exists *and* already produces detected
    events the call is a no-op.  Stale demo rows that no longer produce an event
    are replaced so the demonstration always has an event to walk through.
    """
    existing = _count(db, _simulated_filter())
    events = _detected_event_count(db)
    replaced = 0
    if existing > 0 and events > 0 and not force:
        return {
            "created": 0,
            "skipped": True,
            "reason": "Demonstration data already present and detectable. Pass force=true to add another block.",
            "simulated_observations": existing,
            "detected_events": events,
            "label": SIMULATED_MARKER,
        }
    if existing > 0 and events == 0:
        replaced = db.query(OceanObservation).filter(_simulated_filter()).delete(synchronize_session=False)
        db.commit()
    from scripts.simulate_anomaly import LOCATION_ALIASES, simulate

    name = LOCATION_ALIASES.get(location.lower(), location)
    try:
        # scan=False: demonstration observations only, never AI alerts. This
        # keeps the demo fully removable and prevents simulation from leaking
        # into the real alert stream.
        alerts_created = simulate(db, name, kind, scan=False)
    except SystemExit as exc:
        return {"created": 0, "skipped": True, "reason": str(exc), "label": SIMULATED_MARKER}
    invalidate_caches()
    try:
        # Re-warm the shared TIDE inputs so the demonstration guide (which reads
        # /demo/status right after seeding) responds quickly.
        TideEngine(db).rankings()
    except Exception:
        pass
    simulated = _count(db, _simulated_filter())
    return {
        "created": simulated - (existing - replaced),
        "replaced": int(replaced or 0),
        "skipped": False,
        "location": name,
        "kind": kind,
        "alerts_created": alerts_created,
        "simulated_observations": simulated,
        "detected_events": _detected_event_count(db),
        "label": SIMULATED_MARKER,
        "note": "These rows are labelled SIMULATED and are excluded from real-observation reporting.",
    }


@router.post("/reset")
def demo_reset(db: Session = Depends(get_db)) -> dict:
    """Delete ONLY labelled simulated/demo observations. Real rows are untouched."""
    before = _count(db, _simulated_filter())
    deleted = db.query(OceanObservation).filter(_simulated_filter()).delete(synchronize_session=False)
    db.commit()
    invalidate_caches()
    remaining = _count(db, _simulated_filter())
    return {
        "deleted": int(deleted or 0),
        "simulated_before": before,
        "simulated_after": remaining,
        "real_observations_untouched": _count(db) - remaining,
        "label": DEMO_MARKER,
        "note": "Reset removed only simulation-labelled rows.",
    }
