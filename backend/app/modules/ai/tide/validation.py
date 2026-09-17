"""Phase 8 — TIDE Scientific Validation, Benchmarking & Reliability Framework.

This module measures how the existing TIDE decision layer behaves.  It is
deliberately honest by construction:

* Only metrics actually supported by the available data are computed.
* When a metric cannot be computed it returns ``NOT AVAILABLE`` /
  ``GROUND TRUTH UNAVAILABLE`` / ``INSUFFICIENT DATA`` (never a fabricated value).
* It never writes to the observation store and never modifies historical events.
* It introduces no new scoring engine: candidate selection reuses the existing
  ranking output and outcome estimation reuses the existing pure
  :func:`~app.modules.ai.tide.engine.simulate_candidate` primitive.

Vocabulary used throughout (see ``docs/TIDE_BENCHMARK_PROTOCOL.md``)::

    IMPLEMENTED            code exists and runs
    DEMONSTRATED           observable on the current dataset
    TESTED                 verified by automated tests
    EMPIRICALLY VALIDATED  supported by independent ground-truth data + review

TIDE is *implemented*, *demonstrated* and (as of Phase 8) *tested*.  It is NOT
empirically validated — no independent ground truth exists in this project.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from statistics import mean, median
from time import perf_counter

from sqlalchemy.orm import Session

from app.modules.ai.tide import adapters
from app.modules.ai.tide.scoring import (
    METHOD_COSTS,
    TIDE_ALGORITHM_VERSION,
    calculate_observation_value,
    unit,
)
from app.modules.ai.tide.engine import simulate_candidate

# ---------------------------------------------------------------------------
# Framework constants
# ---------------------------------------------------------------------------

STRATEGIES = ("RANDOM", "UNIFORM", "UNCERTAINTY_ONLY", "ANOMALY_ONLY", "DATA_GAP_ONLY", "TIDE")

STRATEGY_LABELS = {
    "RANDOM": "Random valid observation location",
    "UNIFORM": "Uniform spatial selection",
    "UNCERTAINTY_ONLY": "Highest uncertainty",
    "ANOMALY_ONLY": "Strongest anomaly persistence",
    "DATA_GAP_ONLY": "Largest data gap",
    "TIDE": "TIDE observation value",
}

# Minimum number of evaluated cases before aggregate statistics are reported.
MIN_SAMPLE = 3

# Variables a non-event benchmark case id may be built from (mirrors the TIDE
# domain vocabulary). Any other non-event id is an invalid case -> 404.
CASE_VARIABLES = (
    "temperature", "salinity", "oxygen", "chlorophyll", "current_speed",
    "wave_height", "pressure", "nutrients", "ph", "density",
)

COST_ASSUMPTION = "NORMALIZED OBSERVATION COST - DEMONSTRATION ASSUMPTION"

GROUND_TRUTH = {
    "available": False,
    "reason": (
        "The project has no independent, externally labelled event ground truth. "
        "Events are classified by the system's own thresholds and model baselines, "
        "so they cannot be used as independent labels."
    ),
    "false_alarm": "GROUND TRUTH UNAVAILABLE",
    "missed_event": "GROUND TRUTH UNAVAILABLE",
}

SCIENTIFIC_BOUNDARY = {
    "can_show": [
        "implementation consistency with the documented scoring formula",
        "reproducibility of rankings, simulations and benchmarks for fixed inputs",
        "ranking behaviour and sensitivity to each factor",
        "deterministic behaviour (seeded random strategy)",
        "observed benchmark outcomes on the current dataset, with sample size",
        "simulation isolation (no writes to the observation store)",
    ],
    "cannot_show": [
        "universal superiority of TIDE over any baseline",
        "operational ocean-forecasting performance",
        "causal truth about sensor / model / phenomenon attribution",
        "real-world deployment success",
        "universal decision improvement",
        "scientifically calibrated uncertainty",
        "guaranteed observation value",
    ],
    "statement": (
        "TIDE is implemented, demonstrated and computationally tested. It is NOT "
        "scientifically or empirically validated: no independent ground-truth dataset, "
        "field campaign or expert review supports its scores."
    ),
}


# ---------------------------------------------------------------------------
# Small numeric helpers (safe against zero/null)
# ---------------------------------------------------------------------------

def _r(value, digits: int = 4):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return round(number, digits)


def _safe_reduction(before, after):
    """Uncertainty reduction and relative reduction, null-safe."""
    if before is None or after is None:
        return None, None
    reduction = before - after
    relative = (reduction / before) if before > 0 else None
    return _r(reduction), _r(relative)


def _stats(values: list[float]) -> dict:
    clean = [v for v in values if v is not None]
    if len(clean) < MIN_SAMPLE:
        return {"N": len(clean), "status": f"INSUFFICIENT DATA (N={len(clean)})", "values": [_r(v) for v in clean]}
    return {
        "N": len(clean),
        "mean": _r(mean(clean)),
        "median": _r(median(clean)),
        "min": _r(min(clean)),
        "max": _r(max(clean)),
    }


# ---------------------------------------------------------------------------
# Strategy selection — all strategies see the exact same candidate pool
# ---------------------------------------------------------------------------

def _candidate_sort_key(candidate: dict):
    return (-unit(candidate.get("observation_value")), candidate.get("candidate_id", ""))


def select_candidates(strategy: str, pool: list[dict], budget: int, rng: random.Random) -> list[dict]:
    """Select up to ``budget`` candidates from ``pool`` using one strategy.

    Every strategy receives the identical ``pool`` and ``budget`` and may only
    use fields that are already part of the public TIDE candidate.  TIDE is
    given no information the baselines cannot see (fairness rule).
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    n = len(pool)
    if n == 0 or budget <= 0:
        return []
    budget = min(budget, n)

    if strategy == "RANDOM":
        return rng.sample(pool, budget)
    if strategy == "UNIFORM":
        ordered = sorted(pool, key=lambda c: (
            c.get("longitude") if c.get("longitude") is not None else 0.0,
            c.get("latitude") if c.get("latitude") is not None else 0.0,
            c.get("candidate_id", ""),
        ))
        if budget == 1:
            return [ordered[n // 2]]
        picks = {round(i * (n - 1) / (budget - 1)) for i in range(budget)}
        return [ordered[i] for i in sorted(picks)]
    if strategy == "UNCERTAINTY_ONLY":
        key = lambda c: (-unit(c.get("uncertainty")), c.get("candidate_id", ""))
    elif strategy == "ANOMALY_ONLY":
        key = lambda c: (-unit(c.get("anomaly_persistence")), c.get("candidate_id", ""))
    elif strategy == "DATA_GAP_ONLY":
        key = lambda c: (-unit(c.get("data_gap")), c.get("candidate_id", ""))
    else:  # TIDE
        key = _candidate_sort_key
    return sorted(pool, key=key)[:budget]


# ---------------------------------------------------------------------------
# Case evaluation
# ---------------------------------------------------------------------------

def _validation_error(candidate: dict, variable: str) -> dict:
    """Model-vs-observed error where a real comparison exists."""
    disagreement = candidate.get("_disagreement") or {}
    model_value = disagreement.get("model_value")
    observed_value = disagreement.get("observed_value")
    if model_value is None or observed_value is None:
        return {
            "available": False,
            "reason": "NOT AVAILABLE - no model/observed pair exists for this variable/depth.",
            "model_value": None, "observed_value": None, "difference": None, "absolute_error": None,
        }
    difference = observed_value - model_value
    return {
        "available": True,
        "reason": "Model-vs-observed difference from the existing Twin comparison (trend baseline, not a forecast).",
        "model_value": _r(model_value),
        "observed_value": _r(observed_value),
        "difference": _r(difference),
        "absolute_error": _r(abs(difference)),
    }


def evaluate_case(*, case: dict, strategy: str, pool: list[dict], budget: int,
                  rng: random.Random, sim_fn) -> list[dict]:
    """Evaluate one (case, strategy) pair and return one row per selected candidate."""
    selected = select_candidates(strategy, pool, budget, rng)
    rows = []
    detection_available = case.get("began_hours_ago") is not None
    for candidate in selected:
        sim = sim_fn(candidate)
        before = sim["before"]
        after = sim["after"]
        reduction, relative = _safe_reduction(before["uncertainty"], after["uncertainty"])
        rows.append({
            "case_id": case["case_id"],
            "case_label": case.get("label", case["case_id"]),
            "event_id": case.get("event_id"),
            "strategy": strategy,
            "budget": budget,
            "selected": {
                "candidate_id": candidate.get("candidate_id"),
                "location_id": candidate.get("location_id"),
                "location": candidate.get("location"),
                "variable": candidate.get("variable"),
                "depth_m": candidate.get("depth_m"),
                "observation_type": candidate.get("observation_type"),
                "observation_cost": _r(candidate.get("observation_cost")),
                "status": candidate.get("status"),
            },
            "initial_uncertainty": _r(before["uncertainty"]),
            "final_uncertainty": _r(after["uncertainty"]),
            "uncertainty_reduction": reduction,
            "relative_uncertainty_reduction": relative,
            "decision_before": before["decision"],
            "decision_after": after["decision"],
            "decision_changed": sim["decision_changed"],
            "validation_error": _validation_error(candidate, case.get("variable", "temperature")),
            "detection_time": {
                "available": detection_available,
                "value_h": _r(case.get("began_hours_ago")) if detection_available else None,
                "reason": "Event timing available." if detection_available
                          else "NOT AVAILABLE - no detected event provides a detection time.",
            },
            "evidence_count": len(candidate.get("evidence", []) or []),
            "observation_cost": _r(candidate.get("observation_cost")),
            "cost_label": COST_ASSUMPTION,
            "data_status": {"candidate": candidate.get("status"), "observation": "SIMULATED"},
            "supports_model_hypothesis": sim["supports_model_hypothesis"],
            "simulated": True,
            "notes": sim["notes"][:1],
        })
    return rows


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate(rows: list[dict], strategies: tuple[str, ...]) -> list[dict]:
    out = []
    for strategy in strategies:
        srows = [r for r in rows if r["strategy"] == strategy]
        reductions = [r["uncertainty_reduction"] for r in srows if r["uncertainty_reduction"] is not None]
        errors = [r["validation_error"]["absolute_error"] for r in srows
                  if r["validation_error"]["available"] and r["validation_error"]["absolute_error"] is not None]
        detections = [r["detection_time"]["value_h"] for r in srows if r["detection_time"]["available"]]
        costs = [r["observation_cost"] for r in srows if r["observation_cost"] is not None]
        out.append({
            "strategy": strategy,
            "strategy_label": STRATEGY_LABELS[strategy],
            "N": len(srows),
            "cases_with_selection": len({r["case_id"] for r in srows}),
            "decision_changes": sum(1 for r in srows if r["decision_changed"]),
            "decision_change_rate": _r(sum(1 for r in srows if r["decision_changed"]) / len(srows)) if srows else None,
            "uncertainty_reduction": _stats(reductions),
            "validation_error": _stats(errors) if errors else {"N": 0, "status": "NOT AVAILABLE"},
            "detection_time": _stats(detections) if detections else {"N": 0, "status": "NOT AVAILABLE"},
            "observation_cost": _stats(costs) if costs else {"N": 0, "status": "NOT AVAILABLE"},
        })
    return out


# ---------------------------------------------------------------------------
# Benchmark runner (reusable: accepts any pool/simulation provider)
# ---------------------------------------------------------------------------

def run_benchmark(*, cases: list[dict], strategies: tuple[str, ...], budget: int,
                  seed: int, pool_fn, sim_fn, dataset: dict) -> dict:
    """Run the benchmark over ``cases`` with a fair, shared candidate pool.

    ``pool_fn(case) -> list[candidate]`` and ``sim_fn(candidate) -> simulation``
    are injected so the framework is reusable and unit-testable without a
    database.  The default providers are built in
    :func:`run_database_benchmark`.
    """
    started = perf_counter()
    rng = random.Random(seed)
    rows: list[dict] = []
    pool_size_by_case: dict[str, int] = {}
    pool_value_nonzero: dict[str, int] = {}
    generation_ms = 0.0
    evaluation_ms = 0.0

    for case in cases:
        t0 = perf_counter()
        pool = pool_fn(case)
        generation_ms += (perf_counter() - t0) * 1000
        pool_size_by_case[case["case_id"]] = len(pool)
        pool_value_nonzero[case["case_id"]] = sum(1 for c in pool if unit(c.get("observation_value")) > 0)
        t1 = perf_counter()
        for strategy in strategies:
            # A fresh RNG per (case, strategy) keeps RANDOM reproducible and
            # independent of evaluation order.
            case_rng = random.Random(f"{seed}:{case['case_id']}:{strategy}")
            rows.extend(evaluate_case(case=case, strategy=strategy, pool=pool, budget=budget,
                                      rng=case_rng, sim_fn=sim_fn))
        evaluation_ms += (perf_counter() - t1) * 1000

    degeneracy = {
        "pool_size_by_case": pool_size_by_case,
        "nonzero_observation_value_by_case": pool_value_nonzero,
        "pool_is_degenerate": bool(pool_size_by_case) and all(v == 0 for v in pool_value_nonzero.values()),
        "note": (
            "observation_value is zero for every candidate in these cases because anomaly "
            "persistence is zero (no detected events), so score-based strategies tie and fall "
            "back to a deterministic candidate_id ordering. Selection differentiation is "
            "therefore not measurable on this dataset; outcome metrics remain valid."
            if pool_size_by_case and all(v == 0 for v in pool_value_nonzero.values())
            else "At least one case has non-zero observation_value."
        ),
    }

    return {
        "algorithm_version": TIDE_ALGORITHM_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "configuration": {
            "budget": budget,
            "strategies": list(strategies),
            "cases": [c["case_id"] for c in cases],
            "seed": seed,
            "cost_assumption": COST_ASSUMPTION,
            "ground_truth_available": GROUND_TRUTH["available"],
        },
        "fairness": {
            "same_pool_per_strategy": True,
            "budget_uniform": budget,
            "pool_size_by_case": pool_size_by_case,
            "note": (
                "All strategies receive the identical candidate pool, observation budget and "
                "factor fields. TIDE is not given any information unavailable to the baselines."
            ),
        },
        "selection": degeneracy,
        "rows": rows,
        "aggregates": aggregate(rows, strategies),
        "ground_truth": GROUND_TRUTH,
        "timing_ms": {
            "candidate_generation": round(generation_ms, 1),
            "evaluation": round(evaluation_ms, 1),
            "total": round((perf_counter() - started) * 1000, 1),
        },
        "scientific_boundary": SCIENTIFIC_BOUNDARY,
        "limitations": [
            "Outcome values are DEMONSTRATION heuristics derived from existing inputs, not field measurements.",
            "No independent ground truth exists, so false-alarm and missed-event rates are unavailable.",
            "Observation cost is a normalised demonstration assumption, not a monetary figure.",
            "A non-zero decision_change_rate reflects a threshold crossing of the documented heuristic, not a measured operational improvement.",
        ],
    }


# ---------------------------------------------------------------------------
# Database-backed providers (default)
# ---------------------------------------------------------------------------

def database_dataset_meta(db: Session) -> dict:
    from app.models.location import OceanLocation
    from app.models.observation import OceanObservation

    events = adapters.detect_events(db).get("events", [])
    return {
        "id": "tidaltwin-live-store",
        "version": "live",
        "status": "REAL observation stream (Open-Meteo Marine) with system-derived events",
        "locations": db.query(OceanLocation).count(),
        "observations": db.query(OceanObservation).count(),
        "events": len(events),
        "source": "app.modules.ai.tide.adapters (existing TIDE inputs)",
    }


def _case_from_variable(variable: str, depth_m: float) -> dict:
    return {"case_id": f"{variable}@{depth_m:g}", "label": f"{variable} @ {depth_m:g} m",
            "variable": variable, "depth_m": depth_m, "event_id": None, "began_hours_ago": None}


def build_cases(db: Session, variables: tuple[str, ...], depth_m: float, use_events: bool = False) -> list[dict]:
    """Cases are detected events when available, otherwise per-variable pools."""
    if use_events:
        events = adapters.detect_events(db).get("events", [])
        cases = []
        for index, ev in enumerate(events):
            case = _case_from_variable(ev.get("variable") or "temperature", depth_m)
            case.update({"case_id": f"event-{index}", "event_id": f"event-{index}",
                         "label": ev.get("label") or ev.get("event_type") or f"event-{index}",
                         "location_id": ev.get("location_id"), "began_hours_ago": ev.get("began_hours_ago")})
            cases.append(case)
        if cases:
            return cases
    return [_case_from_variable(v, depth_m) for v in variables]


def run_database_benchmark(db: Session, *, variables: tuple[str, ...] = ("temperature", "wave_height", "salinity", "current_speed"),
                           depth_m: float = 0.0, budget: int = 1,
                           strategies: tuple[str, ...] = STRATEGIES, seed: int = 42,
                           use_events: bool = False, engine=None) -> dict:
    """Run the benchmark against the live store using the existing engines."""
    from app.modules.ai.tide.engine import TideEngine

    engine = engine or TideEngine(db)
    cases = build_cases(db, variables, depth_m, use_events=use_events)
    fallback_cache: dict[int, float | None] = {}

    def pool_fn(case: dict) -> list[dict]:
        return engine.rankings(location_id=case.get("location_id"), variable=case["variable"], depth_m=case["depth_m"])

    def sim_fn(candidate: dict) -> dict:
        fallback = None
        disagreement = candidate.get("_disagreement") or {}
        if candidate.get("variable") == "temperature" and disagreement.get("observed_value") is None \
                and disagreement.get("model_value") is None:
            loc_id = candidate.get("location_id")
            if loc_id not in fallback_cache:
                row = adapters.latest_observation(db, loc_id) if loc_id is not None else None
                fallback_cache[loc_id] = row.sea_surface_temperature if row is not None else None
            fallback = fallback_cache.get(loc_id)
        return simulate_candidate(candidate, observation_type=candidate.get("observation_type", "VIRTUAL_SENSOR"),
                                  fallback_value=fallback)

    return run_benchmark(cases=cases, strategies=strategies, budget=budget, seed=seed,
                         pool_fn=pool_fn, sim_fn=sim_fn, dataset=database_dataset_meta(db))


# ---------------------------------------------------------------------------
# Algorithm consistency testing (NOT scientific validation)
# ---------------------------------------------------------------------------

_BASE_VECTOR = {"decision_impact": 0.6, "uncertainty": 0.6, "data_gap": 0.6,
                "anomaly_persistence": 0.6, "observation_cost": 0.5}


def sensitivity_report(base: dict | None = None) -> dict:
    """Monotonicity of the documented formula when each factor changes."""
    base = {**_BASE_VECTOR, **(base or {})}
    factors = []
    for factor in ("decision_impact", "uncertainty", "data_gap", "anomaly_persistence"):
        low = calculate_observation_value({**base, factor: 0.1})["observation_value"]
        high = calculate_observation_value({**base, factor: 0.9})["observation_value"]
        factors.append({"factor": factor, "low_score": low, "high_score": high,
                        "delta": _r(high - low), "expected_direction": "increase",
                        "consistent": high > low})
    cost_low = calculate_observation_value({**base, "observation_cost": 0.1})["observation_value"]
    cost_high = calculate_observation_value({**base, "observation_cost": 0.9})["observation_value"]
    factors.append({"factor": "observation_cost", "low_score": cost_low, "high_score": cost_high,
                    "delta": _r(cost_high - cost_low), "expected_direction": "decrease",
                    "consistent": cost_high < cost_low})
    return {
        "label": "ALGORITHM CONSISTENCY TESTING",
        "caveat": "This checks that the implementation matches its documented formula. It is not scientific validation.",
        "base_vector": {k: _r(v) for k, v in base.items()},
        "factors": factors,
        "all_consistent": all(f["consistent"] for f in factors),
    }


def ranking_sensitivity(pool: list[dict]) -> dict:
    """How a target candidate's rank responds when one of its factors changes."""
    if len(pool) < MIN_SAMPLE:
        return {"available": False, "reason": f"INSUFFICIENT DATA (N={len(pool)}) - need at least {MIN_SAMPLE} candidates."}
    target = pool[0]
    results = []
    for factor in ("decision_impact", "uncertainty", "data_gap", "anomaly_persistence", "observation_cost"):
        ranks = []
        for level in (0.05, 0.95):
            varied = [{**c, factor: level} if c is target else dict(c) for c in pool]
            scored = sorted(varied, key=lambda c: (-calculate_observation_value(c)["observation_value"], c.get("candidate_id", "")))
            ranks.append(next(i for i, c in enumerate(scored, 1) if c.get("candidate_id") == target.get("candidate_id")))
        results.append({"factor": factor, "rank_at_low": ranks[0], "rank_at_high": ranks[1],
                        "rank_moved": ranks[0] != ranks[1]})
    return {"available": True, "target_candidate_id": target.get("candidate_id"),
            "pool_size": len(pool), "factors": results,
            "label": "ALGORITHM CONSISTENCY TESTING"}


_EDGE_VECTORS = [
    ("all_zero", {"decision_impact": 0, "uncertainty": 0, "data_gap": 0, "anomaly_persistence": 0, "observation_cost": 0}),
    ("all_one", {"decision_impact": 1, "uncertainty": 1, "data_gap": 1, "anomaly_persistence": 1, "observation_cost": 1}),
    ("zero_cost", {**_BASE_VECTOR, "observation_cost": 0}),
    ("tiny_cost", {**_BASE_VECTOR, "observation_cost": 1e-9}),
    ("huge_cost", {**_BASE_VECTOR, "observation_cost": 1e9}),
    ("nulls", {"decision_impact": None, "uncertainty": None, "data_gap": None, "anomaly_persistence": None, "observation_cost": None}),
    ("nan", {**_BASE_VECTOR, "uncertainty": float("nan")}),
    ("infinity", {**_BASE_VECTOR, "observation_cost": float("inf")}),
    ("out_of_range", {**_BASE_VECTOR, "uncertainty": 5.0, "data_gap": -3.0}),
]


def edge_case_report() -> dict:
    """Confirm the scorer never returns NaN / Infinity / undefined."""
    import math

    results = []
    for name, vector in _EDGE_VECTORS:
        result = calculate_observation_value(dict(vector))
        value = result["observation_value"]
        finite = isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
        results.append({"case": name, "observation_value": value, "finite_nonnegative": finite,
                        "expected_uncertainty_reduction": result["expected_uncertainty_reduction"]})
    return {
        "label": "EDGE CASE TESTING",
        "results": results,
        "all_finite": all(r["finite_nonnegative"] for r in results),
    }


# ---------------------------------------------------------------------------
# Validation status (implementation maturity + reproducibility)
# ---------------------------------------------------------------------------

def validation_status(db: Session) -> dict:
    """High-level validation status: maturity, dataset, ground truth, boundary."""
    dataset = database_dataset_meta(db)
    temperature_pool = []
    try:
        from app.modules.ai.tide.engine import TideEngine
        temperature_pool = TideEngine(db).rankings(variable="temperature", depth_m=0.0)
    except Exception:
        temperature_pool = []

    return {
        "algorithm_version": TIDE_ALGORITHM_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "maturity": {
            "IMPLEMENTED": [
                "TIDE scoring and normalisation",
                "candidate generation and deterministic ranking",
                "evidence traceability (stable ids)",
                "confidence (distinct from uncertainty and observation value)",
                "verdict classification (four states)",
                "data gaps, persistence, decision impact, observation cost",
                "what-if virtual observation",
                "decision replay",
                "this validation & benchmark framework",
            ],
            "DEMONSTRATED": [
                "ranking on the live candidate pool",
                "uncertainty-reduction simulation on real candidates",
                "decision change under the documented rule table",
            ],
            "TESTED": [
                "formula and edge-case behaviour",
                "ranking determinism and ties",
                "verdict and confidence behaviour",
                "evidence id stability",
                "simulation isolation (no observation-store writes)",
                "benchmark reproducibility and baseline fairness",
            ],
            "EMPIRICALLY_VALIDATED": [],
            "empirical_note": (
                "Nothing is empirically validated. Empirical validation requires independent "
                "ground-truth observations, a field campaign and expert review, none of which exist here."
            ),
        },
        "dataset": dataset,
        "ground_truth": GROUND_TRUTH,
        "cost_assumption": COST_ASSUMPTION,
        "candidate_pool": {
            "variable": "temperature",
            "size": len(temperature_pool),
            "nonzero_observation_value": sum(1 for c in temperature_pool if unit(c.get("observation_value")) > 0),
        },
        "reproducibility": {
            "algorithm_version": TIDE_ALGORITHM_VERSION,
            "dataset_id": dataset["id"],
            "dataset_version": dataset["version"],
            "default_seed": 42,
            "default_budget": 1,
            "cost_assumption": COST_ASSUMPTION,
        },
        "sensitivity": sensitivity_report(),
        "ranking_sensitivity": ranking_sensitivity(temperature_pool),
        "edge_cases": edge_case_report(),
        "scientific_boundary": SCIENTIFIC_BOUNDARY,
        "limitations": [
            "No independent ground truth: false-alarm and missed-event metrics are unavailable.",
            "Simulated outcomes are demonstration heuristics, not measured field results.",
            "Observation cost is a normalised demonstration assumption.",
            "The current dataset has no threshold-crossing events, so anomaly persistence is zero and TIDE's score-based ranking is degenerate (ties resolved by candidate id).",
        ],
    }


def benchmark_case_detail(db: Session, case_id: str, *, variable: str = "temperature",
                          depth_m: float = 0.0, budget: int = 1, strategies: tuple[str, ...] = STRATEGIES,
                          seed: int = 42) -> dict | None:
    """Event/case-level drill-down: candidate -> strategy -> before/after -> validation."""
    from app.modules.ai.tide.engine import TideEngine

    engine = TideEngine(db)
    if case_id.startswith("event-"):
        ctx = engine.event_context(case_id)
        if ctx is None:
            return None
        ev = ctx["event"]
        variable = {"strong_current_event": "current_speed", "coastal_flooding_risk": "wave_height"}.get(ev.get("event_type"), "temperature")
        pool = engine.rankings(location_id=ev.get("location_id"), variable=variable, depth_m=depth_m)
        case = {"case_id": case_id, "label": ev.get("label") or case_id, "variable": variable,
                "depth_m": depth_m, "event_id": case_id, "location_id": ev.get("location_id"),
                "began_hours_ago": ev.get("began_hours_ago")}
    else:
        # A non-event case id must encode a known variable ("<variable>" or
        # "<variable>@<depth>"); anything else is an invalid case -> 404.
        base = case_id.split("@", 1)[0]
        if base not in CASE_VARIABLES:
            return None
        variable = base
        pool = engine.rankings(variable=variable, depth_m=depth_m)
        case = {"case_id": case_id, "label": case_id, "variable": variable, "depth_m": depth_m,
                "event_id": None, "began_hours_ago": None}
    if not pool:
        return None
    fallback = None
    if variable == "temperature":
        row = adapters.latest_observation(db, pool[0]["location_id"])
        fallback = row.sea_surface_temperature if row is not None else None

    def sim_fn(candidate: dict) -> dict:
        return simulate_candidate(candidate, observation_type=candidate.get("observation_type", "VIRTUAL_SENSOR"),
                                  fallback_value=fallback)

    rows = []
    for strategy in strategies:
        rng = random.Random(f"{seed}:{case_id}:{strategy}")
        rows.extend(evaluate_case(case=case, strategy=strategy, pool=pool, budget=budget,
                                  rng=rng, sim_fn=sim_fn))
    return {
        "algorithm_version": TIDE_ALGORITHM_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case": case,
        "candidate_pool_size": len(pool),
        "rows": rows,
        "ground_truth": GROUND_TRUTH,
        "cost_assumption": COST_ASSUMPTION,
        "note": "Each row shows exactly how a benchmark number was produced: candidate -> strategy -> before/after -> validation.",
    }
