"""Cautious heuristic model-versus-sensor verdicts for TIDE Phase 3."""

from app.modules.ai.tide.scoring import unit


def classify_verdict(*, severity: object, persistence: object, spatial_consistency: object,
                    quality: object | None = None, observation_count: int = 0,
                    agreeing_observations: int = 0, disagreeing_observations: int = 0) -> dict:
    """Return an explainable hypothesis, never a scientific diagnosis.

    ``agreeing_observations`` / ``disagreeing_observations`` let callers express
    contradictory evidence structure (e.g. one observation disagrees while
    several agree with the model).  When the disagreeing share reaches half of
    the available observations the evidence is treated as conflicting and the
    cautious ``INSUFFICIENT_EVIDENCE`` verdict is returned instead of a strong
    sensor/model/process hypothesis.  Defaults preserve the original behaviour.
    """
    sev, persist, spatial = unit(severity), unit(persistence), unit(spatial_consistency)
    qual = unit(quality, default=0.5) if quality is not None else 0.5
    total_obs = max(0, int(agreeing_observations)) + max(0, int(disagreeing_observations))
    contradiction = (max(0, int(disagreeing_observations)) / total_obs) if total_obs > 0 else 0.0
    if observation_count < 2 or sev < 0.20:
        return {"verdict": "INSUFFICIENT_EVIDENCE", "confidence": 0.25,
                "alternative_explanation": "Available observations do not establish a persistent, spatially coherent mismatch.",
                "recommended_observation": "Collect a colocated repeat measurement before attributing the mismatch."}
    if contradiction >= 0.5:
        return {"verdict": "INSUFFICIENT_EVIDENCE", "confidence": 0.30,
                "alternative_explanation": (
                    f"{disagreeing_observations} of {total_obs} observations disagree with the model while "
                    f"{agreeing_observations} agree — the evidence is internally conflicting."),
                "recommended_observation": "Resolve the conflicting observations with an independent colocated sample before attributing a cause."}
    if sev >= 0.65 and persist < 0.35 and spatial < 0.35:
        return {"verdict": "LIKELY_SENSOR_ISSUE", "confidence": round(unit((sev + (1 - persist) + (1 - spatial) + (1 - qual)) / 4), 2),
                "alternative_explanation": "A short-lived local phenomenon could also produce an isolated spike.",
                "recommended_observation": "Repeat the measurement with an independent nearby sensor."}
    if sev >= 0.55 and persist >= 0.60 and spatial >= 0.55:
        return {"verdict": "LIKELY_MODEL_ISSUE", "confidence": round(unit((sev + persist + spatial) / 3), 2),
                "alternative_explanation": "A coherent unrepresented regional process remains possible.",
                "recommended_observation": "Collect a depth-resolved profile across the mismatch area."}
    if sev >= 0.55 and persist >= 0.45 and spatial >= 0.45:
        return {"verdict": "LIKELY_MISSING_PHENOMENON", "confidence": round(unit((sev + persist + spatial) / 3), 2),
                "alternative_explanation": "The mismatch may instead reflect a persistent model bias.",
                "recommended_observation": "Increase multi-sensor sampling across the event boundary."}
    return {"verdict": "INSUFFICIENT_EVIDENCE", "confidence": 0.35,
            "alternative_explanation": "The available evidence does not separate sensor, model, and process explanations.",
            "recommended_observation": "Collect another time-separated observation at the target depth."}
