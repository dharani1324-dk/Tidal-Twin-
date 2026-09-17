"""Pure, configurable TIDE scoring primitives."""

from math import isfinite

# Explicit algorithm version.  Phase 8 benchmarks record this so results can be
# tied to a specific scoring behaviour.  Do not change scoring behaviour without
# bumping this version.
TIDE_ALGORITHM_VERSION = "1.0"

EPSILON = 0.05

METHOD_COSTS = {
    "BUOY": 0.35,
    "ARGO_FLOAT": 0.42,
    "RESEARCH_VESSEL": 0.92,
    "DRONE": 0.28,
    "AUTONOMOUS_VEHICLE": 0.62,
    "MANUAL_SAMPLE": 0.48,
    "VIRTUAL_SENSOR": 0.08,
}


def unit(value: object, default: float = 0.0) -> float:
    """Return a finite value clamped to the documented 0..1 input domain."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, number)) if isfinite(number) else default


def calculate_observation_value(candidate: dict, *, epsilon: float = EPSILON) -> dict:
    """Score a normalised candidate without permitting zero-cost inflation.

    This transparent heuristic is intentionally replaceable by a future value
    of information or Bayesian implementation.
    """
    impact = unit(candidate.get("decision_impact"))
    uncertainty = unit(candidate.get("uncertainty"))
    gap = unit(candidate.get("data_gap"))
    persistence = unit(candidate.get("anomaly_persistence"))
    cost = unit(candidate.get("observation_cost"), default=1.0)
    safe_cost = max(cost, epsilon)
    value = impact * uncertainty * gap * persistence / safe_cost
    reduction = unit(uncertainty * (0.30 + 0.40 * gap + 0.20 * persistence - 0.15 * cost))
    return {
        "decision_impact": impact,
        "uncertainty": uncertainty,
        "data_gap": gap,
        "anomaly_persistence": persistence,
        "observation_cost": cost,
        "observation_value": round(value, 4),
        "expected_uncertainty_reduction": round(reduction, 4),
    }
