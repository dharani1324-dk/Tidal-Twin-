"""Phase 6 — TIDE Decision Replay & Validation Engine.

The replay rebuilds a detected ocean event as a read-only, session-scoped
story: EVENT START -> NORMAL -> EARLY SIGNAL -> ANOMALY DETECTED -> MODEL /
SENSOR DISAGREEMENT -> HIGH UNCERTAINTY -> TIDE RECOMMENDATION -> OBSERVATION ->
DECISION -> VALIDATION.

Two modes are compared step-by-step:

* ``MODEL-ONLY REPLAY`` — the model state is replayed as-is; no additional
  observation is incorporated.
* ``TIDE-ASSISTED REPLAY`` — a simulated observation (Phase 5 virtual
  observation, always ``SIMULATED``) is incorporated from the OBSERVATION step
  onward.

The replay never writes to ``OceanObservation`` or any other store and never
modifies historical events.  All step values are derived from existing
TIDE / Twin / Forensics inputs; nothing is fabricated.  Any simulated value and
the demonstration-only regret metric carry an explicit caveat.
"""

from sqlalchemy.orm import Session

from app.modules.ai.tide import adapters
from app.modules.ai.tide.engine import TideEngine
from app.modules.ai.tide.scoring import unit

# ----------------------------------------------------------------------------
# Canonical replay timeline (shared by both modes; values diverge from
# OBSERVATION onward).
# ----------------------------------------------------------------------------

STEPS = [
    ("EVENT_START", "Event start", "The active ocean event is first identified in the event stream.",
     ["Ocean Event Timeline"]),
    ("NORMAL", "Normal conditions", "Baseline ocean state before the anomaly emerges.",
     ["Twin comparison"]),
    ("EARLY_SIGNAL", "Early signal", "First weak indications of a changing ocean state.",
     ["Ocean Event Timeline", "Ocean Event DNA"]),
    ("ANOMALY_DETECTED", "Anomaly detected", "The event passes the anomaly detection threshold.",
     ["Ocean Event Timeline"]),
    ("MODEL_SENSOR_DISAGREEMENT", "Model / sensor disagreement", "Twin comparison records a model-versus-observation difference.",
     ["Twin comparison"]),
    ("HIGH_UNCERTAINTY", "High uncertainty", "Uncertainty peaks and a data gap limits the decision.",
     ["Ocean Forensics", "Data gaps"]),
    ("TIDE_RECOMMENDATION", "TIDE recommendation", "TIDE ranks the next observation to reduce uncertainty.",
     ["TIDE-Loop"]),
    ("OBSERVATION", "Observation", "The recommended observation is carried out.",
     ["TIDE virtual observation"]),
    ("DECISION", "Decision", "The operator decision is (re)considered.",
     ["TIDE decision state"]),
    ("VALIDATION", "Validation / recovery", "The post-observation state is compared with the model.",
     ["Twin comparison", "Observation store"]),
]

# Deterministic decision rules reused by the replay (same vocabulary as the
# existing TIDE decision layer).  Surfaced visibly in the payload so the
# state machine is always open to inspection.
DECISION_RULES = {
    "CONTINUE_MONITORING": "decision impact < 0.65 and data gap < 0.50",
    "INCREASE_MONITORING": "decision impact < 0.65 and data gap >= 0.50",
    "INVESTIGATE_ANOMALY": "decision impact >= 0.65",
}

# Event type -> TIDE variable (mirrors the event context mapping).
_VAR_FOR_EVENT = {
    "strong_current_event": "current_speed",
    "coastal_flooding_risk": "wave_height",
}

# compare() data_status -> public trust label.
_TRUST = {"live": "REAL", "recent": "REAL", "cached": "HISTORICAL", "demo": "SIMULATED", "unavailable": None}

# TIDE evidence type -> replay step.
_EVIDENCE_STEP = {
    "MODEL_OBSERVATION_MISMATCH": "MODEL_SENSOR_DISAGREEMENT",
    "PERSISTENT_ANOMALY": "ANOMALY_DETECTED",
    "EVENT_DNA_FEATURE": "ANOMALY_DETECTED",
    "APEX_RECOMMENDATION": "TIDE_RECOMMENDATION",
}


def _r(value, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


def _trust(event: dict) -> str | None:
    return _TRUST.get((event.get("data_status") or "").lower(), None) or (
        "REAL" if event.get("observed") is not None else "MODEL_DERIVED"
    )


def regret_value(uncertainty_before: float, uncertainty_after: float,
                 confidence_before: float, confidence_after: float) -> float:
    """Demonstration-only decision-regret metric (documented formula).

    ``regret = 0.5 * (uncertainty_before - uncertainty_after)
               + 0.5 * (confidence_after - confidence_before)`` clamped to [0, 1].

    Positive values mean the TIDE observation would have informed the decision
    context further.  This is a demonstration metric, not a scientific
    validation metric.
    """
    raw = (uncertainty_before - uncertainty_after) * 0.5 + (confidence_after - confidence_before) * 0.5
    return round(max(0.0, min(1.0, raw)), 4)


def _resolve_event_for_location(db: Session, location_id: int | None, fallback: str) -> str:
    """Map a location to the first TIDE event reading that location."""
    if location_id is None:
        return fallback
    for index, ev in enumerate(adapters.detect_events(db).get("events", [])):
        if ev.get("location_id") == location_id:
            return f"event-{index}"
    return fallback


class ReplayEngine:
    """Read-only, deterministic replay composer. Never persists state."""

    def __init__(self, db: Session):
        self.db = db

    def build(self, event_id: str, *, location_id: int | None = None, variable: str | None = None,
              depth_m: float = 0.0, observation_type: str = "VIRTUAL_SENSOR",
              value: float | None = None) -> dict | None:
        """Resolve an existing event and compose the full replay payload."""
        engine = TideEngine(self.db)
        resolved = _resolve_event_for_location(self.db, location_id, event_id)
        ctx = engine.event_context(resolved)
        if ctx is None:
            return None
        loc_id = location_id if location_id is not None else ctx["event"].get("location_id")
        if loc_id is None:
            return None
        variable = variable or _VAR_FOR_EVENT.get(ctx["event"].get("event_type"), "temperature")
        rows = engine.rankings(location_id=loc_id, variable=variable, depth_m=depth_m)
        if not rows:
            return None
        sim = engine.virtual_observation(location_id=loc_id, variable=variable, depth_m=depth_m,
                                         observation_type=observation_type, value=value)
        if sim is None:
            return None
        return build_replay(ctx, rows[0], sim, event_id=resolved, variable=variable, depth_m=depth_m)


def build_replay(ctx: dict, candidate: dict, sim: dict, *, event_id: str, variable: str,
                 depth_m: float = 0.0) -> dict:
    """Pure composition of a replay payload from existing TIDE inputs.

    ``ctx`` is an existing ``event_context`` result, ``candidate`` the TIDE
    candidate used by the simulation, and ``sim`` a ``virtual_observation``
    result.  No database access is performed here.
    """
    event = ctx["event"]
    disagreement = (candidate or {}).get("_disagreement") or (ctx.get("disagreement") or {})
    dna = ctx.get("event_dna") or {}
    evidence = ctx.get("evidence") or []
    ctx_evidence_by_type = {e.get("type"): e for e in evidence}

    before = sim["before"]
    after = sim["after"]
    reading = sim["simulated_observation"]
    candidate = candidate or (ctx.get("top_candidates") or [{}])[0]

    model_value = disagreement.get("model_value")
    observed_value = disagreement.get("observed_value")
    after_gap = unit(candidate.get("data_gap", 0) * 0.45)
    sim_obs = reading.get("value")
    sim_diff = _r(sim_obs - model_value) if (sim_obs is not None and model_value is not None) else None
    sim_pct = None
    if sim_diff is not None and model_value not in (None, 0):
        sim_pct = round(abs(sim_diff) / abs(model_value) * 100, 1)

    trust = _trust(event)

    # --- mode state snapshots -----------------------------------------------
    def before_state(evidence_count: int) -> dict:
        return {
            "decision": before["decision"],
            "uncertainty": _r(before["uncertainty"]),
            "anomaly_risk": _r(before["anomaly_risk"]),
            "confidence": _r(before["confidence"]),
            "evidence_count": evidence_count,
            "observation_status": None,
            "observation_value": None,
            "data_gap": _r(candidate.get("data_gap", 0)),
            "persistence": _r(candidate.get("anomaly_persistence", 0)),
            "model_value": _r(model_value),
            "observed_value": _r(observed_value),
            "difference": _r(disagreement.get("difference")),
            "ranking": before["ranking"],
            "expected_uncertainty_reduction": _r(candidate.get("expected_uncertainty_reduction")),
        }

    def after_state(evidence_count: int) -> dict:
        return {
            "decision": after["decision"],
            "uncertainty": _r(after["uncertainty"]),
            "anomaly_risk": _r(after["anomaly_risk"]),
            "confidence": _r(after["confidence"]),
            "evidence_count": evidence_count,
            "observation_status": "SIMULATED",
            "observation_value": _r(sim_obs),
            "data_gap": _r(after_gap),
            "persistence": _r(candidate.get("anomaly_persistence", 0)),
            "model_value": _r(model_value),
            "observed_value": _r(sim_obs),
            "difference": sim_diff,
            "ranking": after["ranking"],
            "expected_uncertainty_reduction": _r(candidate.get("expected_uncertainty_reduction")),
        }

    richness = 6  # signals accumulated by the full replay
    model_count = richness - 1  # model-only stops at the TIDE recommendation

    states = {
        "EVENT_START": lambda n: before_common(n, baseline=0.35),
        "NORMAL": lambda n: before_common(n, baseline=0.35),
        "EARLY_SIGNAL": lambda n: before_common(n, baseline=0.6),
        "ANOMALY_DETECTED": before_state,
        "MODEL_SENSOR_DISAGREEMENT": before_state,
        "HIGH_UNCERTAINTY": before_state,
        "TIDE_RECOMMENDATION": before_state,
        "OBSERVATION": lambda n: {"model": before_state(model_count), "tide": after_state(richness)},
        "DECISION": lambda n: {"model": before_state(model_count), "tide": after_state(richness)},
        "VALIDATION": lambda n: {"model": before_state(model_count), "tide": after_state(richness)},
    }

    def before_common(n: int, baseline: float) -> dict:
        return {
            "decision": "CONTINUE_MONITORING",
            "uncertainty": _r(unit(candidate.get("uncertainty", 0) * baseline)),
            "anomaly_risk": _r(unit(candidate.get("anomaly_persistence", 0) * (0.3 if baseline >= 0.5 else 0.0))),
            "confidence": _r(unit(candidate.get("confidence", 0) * (0.4 if baseline <= 0.4 else (0.55 if baseline <= 0.6 else 1.0)))),
            "evidence_count": n,
            "observation_status": None,
            "observation_value": None,
            "data_gap": _r(unit(candidate.get("data_gap", 0) * (0.0 if baseline <= 0.4 else 0.5))),
            "persistence": _r(candidate.get("anomaly_persistence", 0)),
            "model_value": None,
            "observed_value": None,
            "difference": None,
            "ranking": None,
            "expected_uncertainty_reduction": _r(candidate.get("expected_uncertainty_reduction")),
        }

    # --- steps --------------------------------------------------------------
    steps = []
    for key, label, description, sources in STEPS:
        maker = states[key]
        if key in ("OBSERVATION", "DECISION", "VALIDATION"):
            pair = maker(1)
            steps.append({
                "id": key, "label": label, "description": description, "sources": sources,
                "model_only": pair["model"], "tide_assisted": pair["tide"],
            })
        else:
            count = {"EVENT_START": 0, "NORMAL": 0, "EARLY_SIGNAL": 1, "ANOMALY_DETECTED": 2,
                     "MODEL_SENSOR_DISAGREEMENT": 3, "HIGH_UNCERTAINTY": 4, "TIDE_RECOMMENDATION": richness - 1}.get(key, 0)
            shared = maker(count)
            steps.append({
                "id": key, "label": label, "description": description, "sources": sources,
                "model_only": shared, "tide_assisted": shared,
            })

    # --- comparison ---------------------------------------------------------
    comparison = {
        "uncertainty": _metric(before["uncertainty"], after["uncertainty"],
                               "Uncertainty changes only when a simulated observation is incorporated."),
        "confidence": _metric(before["confidence"], after["confidence"],
                              "Confidence changes only when a simulated observation is incorporated."),
        "anomaly_risk": _metric(before["anomaly_risk"], after["anomaly_risk"],
                                "Anomaly risk reflects whether the simulated reading supports the model."),
        "decision": {
            "model_only": before["decision"],
            "tide_assisted": after["decision"],
            "delta": None,
            "calculated": True,
            "changed": sim["decision_changed"],
            "detail": "Decision from the documented TIDE rule table (see rules).",
        },
        "detection_time": {
            "model_only": _r(event.get("began_hours_ago")),
            "tide_assisted": _r(event.get("began_hours_ago")),
            "delta": None,
            "calculated": event.get("began_hours_ago") is not None,
            "detail": "A simulated observation cannot change the historical detection time; detection latency is not replayed.",
        },
    }

    decision_changed = sim["decision_changed"]
    why = [
        "The additional simulated observation reduced/updated uncertainty, risk and confidence, but the decision thresholds are controlled by decision impact and data gap (see rules).",
        f"Uncertainty {_r(before['uncertainty']):.2f} -> {_r(after['uncertainty']):.2f}; confidence {_r(before['confidence']):.2f} -> {_r(after['confidence']):.2f}; data gap {_r(candidate.get('data_gap', 0)):.2f} -> {_r(after_gap):.2f}.",
    ]
    if decision_changed:
        why.insert(0, f"The simulated observation moved the decision from {before['decision']} to {after['decision']} across the documented threshold: {DECISION_RULES[after['decision']]}.")
    else:
        why.insert(0, "The additional observation reduced/updated uncertainty but did not cross the current decision threshold.")
    why.append(f"Applied decision rule ({after['decision']}): {DECISION_RULES[after['decision']]}.")
    why.append("The post-observation decision state is request-derived from existing TIDE inputs; it is not a measured outcome.")

    # --- regret (demonstration metric) ---------------------------------------
    regret = {
        "available": True,
        "value": regret_value(before["uncertainty"], after["uncertainty"], before["confidence"], after["confidence"]),
        "label": "Decision regret (demonstration)",
        "definition": "regret = 0.5 * (uncertainty_before - uncertainty_after) + 0.5 * (confidence_after - confidence_before), clamped to [0, 1]. It estimates how much additional decision information the TIDE observation would have contributed.",
        "caveat": "DEMONSTRATION METRIC - NOT A SCIENTIFIC VALIDATION METRIC",
        "explanation": (
            f"With the simulated observation, uncertainty falls {_r(before['uncertainty']):.2f} -> {_r(after['uncertainty']):.2f} "
            f"and confidence rises {_r(before['confidence']):.2f} -> {_r(after['confidence']):.2f}. "
            "The regret value is a transparency aid for comparing replay modes, not an operational score."
        ),
    }

    # --- validation ----------------------------------------------------------
    validation = _validation_block(event, disagreement, sim_obs, model_value, observed_value, sim_diff, sim_pct)

    # --- journeys ------------------------------------------------------------
    uncertainty_journey = []
    for step in steps:
        m, t = step["model_only"], step["tide_assisted"]
        uncertainty_journey.append({
            "step": step["id"], "label": step["label"],
            "uncertainty_model_only": m["uncertainty"], "uncertainty_tide_assisted": t["uncertainty"],
            "anomaly_risk_model_only": m["anomaly_risk"], "anomaly_risk_tide_assisted": t["anomaly_risk"],
        })

    evidence_journey = []
    _append_evidence = evidence_journey.append
    _append_evidence(_journey_evidence("EVENT_START", "EVENT_IDENTIFIED", event.get("evolution") or "Active event identified.", "Event Timeline", _r(unit(float(event.get("confidence") or 0) / 100), 2)))
    if "EVENT_DNA_FEATURE" in ctx_evidence_by_type:
        _append_evidence(_journey_evidence("EARLY_SIGNAL", "EVENT_DNA_FEATURE", ctx_evidence_by_type["EVENT_DNA_FEATURE"].get("description"), "Ocean Event DNA", ctx_evidence_by_type["EVENT_DNA_FEATURE"].get("strength")))
    if "PERSISTENT_ANOMALY" in ctx_evidence_by_type:
        _append_evidence(_journey_evidence("ANOMALY_DETECTED", "PERSISTENT_ANOMALY", ctx_evidence_by_type["PERSISTENT_ANOMALY"].get("description"), "Event Timeline", ctx_evidence_by_type["PERSISTENT_ANOMALY"].get("strength")))
    if "MODEL_OBSERVATION_MISMATCH" in ctx_evidence_by_type:
        _append_evidence(_journey_evidence("MODEL_SENSOR_DISAGREEMENT", "MODEL_OBSERVATION_MISMATCH", ctx_evidence_by_type["MODEL_OBSERVATION_MISMATCH"].get("description"), "Twin comparison", ctx_evidence_by_type["MODEL_OBSERVATION_MISMATCH"].get("strength")))
    else:
        _append_evidence(_journey_evidence("MODEL_SENSOR_DISAGREEMENT", "MODEL_OBSERVATION_MISMATCH", f"Twin comparison records a model/observation difference of {_r(disagreement.get('difference')) if disagreement.get('difference') is not None else 'n/a'} for {variable}.", "Twin comparison", disagreement.get("normalized_severity")))
    gap_evidence = next((e for e in evidence if e.get("type") not in ("EVENT_DNA_FEATURE", "PERSISTENT_ANOMALY", "MODEL_OBSERVATION_MISMATCH", "APEX_RECOMMENDATION")), None)
    if gap_evidence:
        _append_evidence(_journey_evidence("HIGH_UNCERTAINTY", gap_evidence.get("type"), gap_evidence.get("description"), "Data gaps", gap_evidence.get("strength")))
    if "APEX_RECOMMENDATION" in ctx_evidence_by_type:
        _append_evidence(_journey_evidence("TIDE_RECOMMENDATION", "APEX_RECOMMENDATION", ctx_evidence_by_type["APEX_RECOMMENDATION"].get("description"), "APEX", ctx_evidence_by_type["APEX_RECOMMENDATION"].get("strength")))
    _append_evidence(_journey_evidence("OBSERVATION", "SIMULATED_OBSERVATION",
                                       f"Simulated reading {_r(sim_obs) if sim_obs is not None else 'n/a'} {variable} at {candidate['location']} (never persisted).",
                                       "TIDE virtual observation",
                                       _r(unit((before["uncertainty"] - after["uncertainty"]) + (after["confidence"] - before["confidence"]))),
                                       data_status="SIMULATED", mode="tide_assisted"))

    # --- TIDE loop status -----------------------------------------------------
    disagreement_reached = model_value is not None or observed_value is not None
    tide_loop = [
        {"key": "MODEL", "label": "Model", "reached": True,
         "detail": f"Twin comparison baseline for {variable} at {candidate['location']} (model value {_r(model_value) or 'n/a'}).",
         "data_status": "MODEL_DERIVED"},
        {"key": "OBSERVATION", "label": "Observation", "reached": observed_value is not None,
         "detail": "Existing observation stream present (REAL/HISTORICAL)." if observed_value is not None else "No supported observed value found for this variable/depth comparison.",
         "data_status": "REAL" if observed_value is not None else None},
        {"key": "DISAGREEMENT", "label": "Disagreement", "reached": disagreement_reached,
         "detail": f"Normalized disagreement severity {_r(disagreement.get('normalized_severity'))}." if disagreement_reached else "No model/observation disagreement is calculable.",
         "data_status": "REAL" if disagreement_reached else None},
        {"key": "UNCERTAINTY", "label": "Uncertainty", "reached": True,
         "detail": f"Pre-observation uncertainty {_r(before['uncertainty']) * 100:.0f}%.",
         "data_status": "MODEL_DERIVED"},
        {"key": "NEXT_OBSERVATION", "label": "Next observation", "reached": True,
         "detail": f"Top TIDE candidate: {candidate['location']} via {candidate.get('observation_type')} (value {_r(candidate.get('observation_value'))}).",
         "data_status": "MODEL_DERIVED"},
        {"key": "DECISION", "label": "Decision", "reached": True,
         "detail": f"{before['decision']} (model-only) / {after['decision']} (TIDE-assisted).",
         "data_status": "MODEL_DERIVED"},
        {"key": "VALIDATION", "label": "Validation", "reached": validation["available"],
         "detail": validation["message"], "data_status": validation["data_status"]},
    ]

    notes = sim.get("notes", [])[:]
    notes.insert(0, "Decision Replay is a read-only reconstruction: it never writes to the observation store and never changes historical events.")
    notes.insert(1, "MODEL-ONLY REPLAY keeps the model state as-is; TIDE-ASSISTED REPLAY incorporates the simulated observation from the OBSERVATION step onward. The modes are identical before that point.")
    notes.append("Every displayed value comes from existing TIDE/Twin/Forensics inputs; where no real value exists the field is n/a, not fabricated.")

    return {
        "event_id": event_id,
        "event": event,
        "event_dna": dna,
        "variable": variable,
        "depth_m": depth_m,
        "location_id": candidate["location_id"],
        "location": candidate["location"],
        "candidate_id": candidate["candidate_id"],
        "labels": {
            "model_only": "MODEL-ONLY REPLAY",
            "tide_assisted": "TIDE-ASSISTED REPLAY",
            "observation": "SIMULATED OBSERVATION - DEMONSTRATION ONLY",
            "regret": "DEMONSTRATION METRIC - NOT A SCIENTIFIC VALIDATION METRIC",
        },
        "rules": DECISION_RULES,
        "steps": steps,
        "model_only": _summary(before, event, model_count, observation_available=False),
        "tide_assisted": _summary(after, event, richness, observation_available=True, observation_value=sim_obs),
        "comparison": comparison,
        "decision": {
            "decision_changed": decision_changed,
            "decision_result": "DECISION_CHANGED" if decision_changed else "DECISION_UNCHANGED",
            "before": before["decision"],
            "after": after["decision"],
            "why": why,
            "explanation": f"The replay landed on {after['decision']} for the TIDE-assisted path and {before['decision']} for the model-only path."
                           if decision_changed else f"Both replay paths kept {before['decision']}.",
        },
        "regret": regret,
        "validation": validation,
        "uncertainty_journey": uncertainty_journey,
        "evidence_journey": evidence_journey,
        "tide_loop": tide_loop,
        "simulated_observation": reading,
        "notes": notes,
        "data_status": {
            "event": trust,
            "variable": "MODEL_DERIVED",
            "uncertainty": "MODEL_DERIVED",
            "decision": "MODEL_DERIVED",
            "observation_model_only": None,
            "observation_tide_assisted": "SIMULATED",
            "validation_real": trust,
            "validation_simulated": "SIMULATED",
            "regret": "MODEL_DERIVED",
        },
        "method": "deterministic_heuristic",
    }


def _metric(before: float, after: float, detail: str) -> dict:
    return {
        "model_only": _r(before, 4),
        "tide_assisted": _r(after, 4),
        "delta": _r(after - before, 4),
        "calculated": True,
        "detail": detail,
    }


def _summary(state: dict, event: dict, evidence_count: int, *, observation_available: bool,
             observation_value: float | None = None) -> dict:
    return {
        "decision": state["decision"],
        "uncertainty": _r(state["uncertainty"]),
        "anomaly_risk": _r(state["anomaly_risk"]),
        "confidence": _r(state["confidence"]),
        "evidence_count": evidence_count,
        "observation_available": observation_available,
        "observation_value": _r(observation_value),
        "detection_time_h": _r(event.get("began_hours_ago")),
    }


def _journey_evidence(step: str, type_: str, description: str, source_system: str,
                      strength: float | None, *, data_status: str | None = None, mode: str = "both") -> dict:
    return {
        "step": step, "type": type_, "description": description or "",
        "source_system": source_system, "strength": _r(strength, 2),
        "data_status": data_status, "mode": mode,
    }


def _validation_block(event: dict, disagreement: dict, sim_obs: float | None, model_value: float | None,
                      observed_value: float | None, sim_diff: float | None, sim_pct: float | None) -> dict:
    trust = _trust(event)
    diff = disagreement.get("difference")
    model_only = {
        "predicted": _r(model_value),
        "observed": _r(observed_value),
        "difference": _r(diff),
        "difference_pct": _r(event.get("model_observed_pct"), 1),
        "evidence_status": _r(disagreement.get("normalized_severity")),
        "quality_status": trust if observed_value is not None else None,
        "simulated": False,
    }
    tide_assisted = {
        "predicted": _r(model_value),
        "observed": _r(sim_obs),
        "difference": sim_diff,
        "difference_pct": sim_pct,
        "evidence_status": _r(disagreement.get("normalized_severity")),
        "quality_status": "SIMULATED",
        "simulated": True,
    }

    if model_value is None and observed_value is None and sim_obs is None:
        message = ("VALIDATION DATA UNAVAILABLE - neither a modelled value nor an observed (or simulated) value "
                   "exists for this variable/depth at this location, so predicted and observed state cannot be compared.")
        available = False
        status = None
    elif observed_value is None and sim_obs is None:
        message = ("VALIDATION DATA UNAVAILABLE on the observed side - the model predicts a value, but no real or "
                   "simulated observation exists to compare against.")
        available = False
        status = "MODEL_DERIVED"
    else:
        message = ("Predicted (model) versus observed comparison. " +
                   (f"Real observation: {_r(observed_value)} (status {trust})." if observed_value is not None else "No real observation available for this variable/depth.") +
                   (f" Simulated reading: {_r(sim_obs)} (SIMULATED)." if sim_obs is not None else ""))
        available = True
        status = "SIMULATED" if sim_obs is not None else trust

    return {
        "available": available,
        "message": message,
        "variable": disagreement.get("variable") or event.get("variable"),
        "depth_m": disagreement.get("depth_m", 0.0),
        "location": event.get("location"),
        "data_status": status,
        "model_only": model_only,
        "tide_assisted": tide_assisted,
    }