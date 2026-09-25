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
    variable = candidate["variable"].replace("_", " ").lower()
    method = candidate["observation_type"].replace("_", " ").lower()
    location = candidate["location"]
    reasons = []
    if candidate.get("uncertainty", 0) >= .5:
        reasons.append(f"The current {variable} uncertainty is {_band(candidate['uncertainty'])} ({candidate['uncertainty'] * 100:.0f}% on the engine scale).")
    if candidate.get("anomaly_persistence", 0) >= .35:
        reasons.append(f"A persistent event signal is present at {location} ({candidate['anomaly_persistence'] * 100:.0f}% on the engine scale).")
    mismatch = next((item for item in evidence if item.get("type") == "MODEL_OBSERVATION_MISMATCH"), None)
    if mismatch:
        mismatch_detail = (mismatch.get("description") or "details are unavailable").rstrip(". ")
        reasons.append(f"Twin comparison reports a model and observation mismatch: {mismatch_detail}.")
    if candidate.get("data_gap", 0) >= .35:
        reasons.append(f"Observation data gap is material ({candidate['data_gap'] * 100:.0f}% on the engine scale).")
    if candidate.get("decision_impact", 0) >= .45:
        reasons.append("Resolving some of this uncertainty could change the current decision context.")
    if not reasons:
        reasons.append("This is the highest-ranked available sampling option under the current TIDE scores; the ranking is heuristic.")
    reasons.append(f"TIDE assigns {method} a {_band(candidate['observation_cost'])} relative cost ({candidate['observation_cost'] * 100:.0f}% on the configured cost scale).")

    reduction = candidate.get("expected_uncertainty_reduction", 0) * 100
    return {
        "summary": f"TIDE ranks {method} sampling at {location} highest for reducing uncertainty in {variable} among the candidates it evaluated.",
        "reasons": reasons,
        "expected_benefit": f"The scoring heuristic estimates up to {reduction:.0f}% uncertainty reduction if this observation is collected. This is a model estimate, not a measured result or guarantee.",
        "affected_decision": candidate["affected_decision"],
        "confidence": confidence,
        "evidence": evidence,
    }


def decision_context(candidate: dict) -> dict:
    decision = candidate["affected_decision"]
    readable_decision = decision.replace("_", " ").lower()
    return {
        "current_decision": decision,
        "affected_decision": decision,
        "decision_impact_score": candidate["decision_impact"],
        "possible_decision_change": f"A confirming observation could provide evidence relevant to the '{readable_decision}' decision; the outcome has not been simulated.",
        "why_it_matters": f"At {candidate['location']}, current uncertainty limits confidence in the '{readable_decision}' decision.",
    }

def verdict_summary(verdict: str, confidence: float) -> str:
    phrases = {
        "LIKELY_SENSOR_ISSUE": "The available evidence is more consistent with an isolated sensor or data-quality issue, but does not prove a fault.",
        "LIKELY_MODEL_ISSUE": "The available evidence is more consistent with a coherent model mismatch, but does not prove the model is incorrect.",
        "LIKELY_MISSING_PHENOMENON": "The available evidence is consistent with an unrepresented process, but does not confirm a phenomenon.",
        "INSUFFICIENT_EVIDENCE": "Available evidence cannot reliably distinguish sensor, model, or unrepresented-process explanations.",
    }
    return phrases[verdict] + f" The heuristic confidence score is {confidence * 100:.0f}%; it is not a probability that this explanation is correct."


def _band(value: float) -> str:
    return "high" if value >= .65 else "moderate" if value >= .35 else "low"
