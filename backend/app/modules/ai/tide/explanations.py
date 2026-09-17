"""Deterministic evidence, confidence, and recommendation explanations."""

from app.modules.ai.tide.scoring import unit

SOURCE_BY_TYPE = {
    "MODEL_OBSERVATION_MISMATCH": "Twin Comparison",
    "PERSISTENT_ANOMALY": "Event Timeline",
    "SPATIAL_CONSISTENCY": "Twin Comparison",
    "HIGH_UNCERTAINTY": "Ocean Forensics",
    "APEX_RECOMMENDATION": "APEX",
    "EVENT_DNA_FEATURE": "Ocean Event DNA",
}


def trace_evidence(candidate: dict, extra: list[dict] | None = None) -> list[dict]:
    """Attach stable IDs and provenance only to evidence that is already present."""
    items = [*candidate.get("evidence", []), *(extra or [])]
    traced = []
    for index, item in enumerate(items, 1):
        evidence_type = item["type"]
        source = item.get("source_system") or SOURCE_BY_TYPE.get(evidence_type, "Ocean Forensics" if evidence_type.endswith("GAP") else "TIDE Engine")
        traced.append({**item, "evidence_id": item.get("evidence_id") or f"{candidate['candidate_id']}:e{index}",
                       "source_system": source, "location_id": candidate["location_id"],
                       "depth_m": candidate.get("depth_m"), "data_status": item.get("data_status", candidate.get("status", "MODEL_DERIVED"))})
    return traced


def confidence_context(candidate: dict, evidence: list[dict]) -> dict:
    support = [f["description"] for f in candidate.get("confidence_factors", []) if unit(f.get("score")) >= .4]
    limitations = list(candidate.get("limitations", []))
    if not evidence:
        limitations.append("No supporting evidence was available for this candidate.")
    if candidate.get("confidence", 0) < .4:
        limitations.append("Evidence support is limited; do not infer a cause from this recommendation alone.")
    return {"overall_confidence": candidate.get("confidence", 0), "level": "HIGH" if candidate.get("confidence", 0) >= .75 else "MEDIUM" if candidate.get("confidence", 0) >= .45 else "LOW",
            "supporting_factors": support, "limiting_factors": list(dict.fromkeys(limitations)),
            "evidence_count": len(evidence), "data_coverage": "limited" if candidate.get("data_gap", 0) >= .5 else "available"}


def recommendation_explanation(candidate: dict, evidence: list[dict], confidence: dict) -> dict:
    reasons = []
    if candidate.get("uncertainty", 0) >= .5: reasons.append(f"{candidate['variable'].replace('_', ' ').title()} uncertainty is {_band(candidate['uncertainty'])}.")
    if candidate.get("anomaly_persistence", 0) >= .35: reasons.append("An active event provides persistence evidence at this location.")
    if any(item["type"] == "MODEL_OBSERVATION_MISMATCH" for item in evidence): reasons.append("The existing Twin reports model-observation disagreement.")
    if candidate.get("data_gap", 0) >= .35: reasons.append("Observation coverage contains a material data gap.")
    if candidate.get("decision_impact", 0) >= .45: reasons.append("Reducing this uncertainty could affect the current decision context.")
    reasons.append(f"The selected {candidate['observation_type'].replace('_', ' ').lower()} has a configured {_band(candidate['observation_cost'])} relative cost.")
    return {"summary": f"TIDE recommends {candidate['observation_type'].replace('_', ' ').lower()} sampling at {candidate['location']} for {candidate['variable'].replace('_', ' ')}.",
            "reasons": reasons, "expected_benefit": f"The initial heuristic estimates up to {candidate['expected_uncertainty_reduction'] * 100:.0f}% uncertainty reduction.",
            "affected_decision": candidate["affected_decision"], "confidence": confidence, "evidence": evidence}


def decision_context(candidate: dict) -> dict:
    decision = candidate["affected_decision"]
    return {"current_decision": "CONTINUE_MONITORING", "affected_decision": decision,
            "decision_impact_score": candidate["decision_impact"],
            "possible_decision_change": f"A confirming observation could support {decision}; this is not a simulated outcome.",
            "why_it_matters": f"Current uncertainty prevents a more confident distinction at {candidate['location']}."}


def verdict_summary(verdict: str, confidence: float) -> str:
    phrases = {
        "LIKELY_SENSOR_ISSUE": "The available evidence is more consistent with an isolated sensor or data-quality issue, but does not prove a fault.",
        "LIKELY_MODEL_ISSUE": "The available evidence is more consistent with a coherent model mismatch, but does not prove the model is incorrect.",
        "LIKELY_MISSING_PHENOMENON": "The available evidence is consistent with an unrepresented process, but does not confirm a phenomenon.",
        "INSUFFICIENT_EVIDENCE": "Available evidence cannot reliably distinguish sensor, model, or unrepresented-process explanations.",
    }
    return phrases[verdict] + f" Heuristic confidence: {confidence * 100:.0f}% ."


def _band(value: float) -> str:
    return "high" if value >= .65 else "moderate" if value >= .35 else "low"
