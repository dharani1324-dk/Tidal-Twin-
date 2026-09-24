import math
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.modules.ai.tide import validation
from app.modules.ai.tide.engine import decision_for
from app.modules.ai.tide.explanations import confidence_context, trace_evidence
from app.modules.ai.tide.scoring import calculate_observation_value
from app.modules.ai.tide.verdicts import classify_verdict


def synthetic_candidate(index, **overrides):
    uncertainty = 0.9 - index * 0.05
    data_gap = 0.4 + index * 0.05
    discovery = {"decision_impact": 0.5 + index * 0.03, "uncertainty": uncertainty,
                 "data_gap": data_gap, "anomaly_persistence": 0.1 * index,
                 "observation_cost": 0.3}
    return {
        "candidate_id": f"cand-{index}",
        "location_id": index,
        "location": f"Site {index}",
        "latitude": 10.0 + index,
        "longitude": 70.0 + index,
        "depth_m": 0.0,
        "variable": "temperature",
        "observation_type": "BUOY",
        "status": "MODEL_DERIVED",
        "evidence": [{"type": "DATA_GAP", "id": f"cand-{index}:e0"}],
        "_disagreement": {},
        **calculate_observation_value(discovery),
        **overrides,
    }


def synthetic_pool(n=6):
    return [synthetic_candidate(i) for i in range(n)]


def synthetic_sim(candidate):
    before_unc = candidate["uncertainty"]
    after_unc = before_unc * 0.5
    decision = decision_for(candidate["decision_impact"], candidate["data_gap"])
    changed = decision != decision_for(candidate["decision_impact"] + 0.5, candidate["data_gap"])
    after_decision = decision_for(candidate["decision_impact"] + 0.5, candidate["data_gap"])
    return {
        "before": {"uncertainty": before_unc, "decision": decision},
        "after": {"uncertainty": after_unc, "decision": after_decision},
        "decision_changed": decision != after_decision,
        "supports_model_hypothesis": changed,
        "notes": ["SIMULATED OBSERVATION - DEMONSTRATION ONLY"],
    }


def synthetic_cases(n=4):
    return [{"case_id": f"temperature@{i}", "label": f"temperature @ {i}", "variable": "temperature",
             "depth_m": float(i), "event_id": None, "began_hours_ago": None} for i in range(n)]


def run_synthetic(**overrides):
    params = {
        "cases": synthetic_cases(),
        "strategies": validation.STRATEGIES,
        "budget": 2,
        "seed": 7,
        "pool_fn": lambda case: synthetic_pool(),
        "sim_fn": synthetic_sim,
        "dataset": {"id": "synthetic", "version": "test", "status": "SYNTHETIC", "locations": 6, "observations": 0, "events": 0},
    }
    params.update(overrides)
    return validation.run_benchmark(**params)


class StrategySelectionTests(unittest.TestCase):
    def test_tide_orders_by_observation_value(self):
        pool = synthetic_pool()
        picked = validation.select_candidates("TIDE", pool, 2, __import__("random").Random(0))
        values = [c["observation_value"] for c in picked]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_every_strategy_respects_budget_and_pool(self):
        pool = synthetic_pool()
        for strategy in validation.STRATEGIES:
            picked = validation.select_candidates(strategy, pool, 2, __import__("random").Random(1))
            self.assertLessEqual(len(picked), 2, strategy)
            self.assertTrue(all(any(c is p for p in pool) for c in picked), strategy)

    def test_tide_never_sees_more_than_baselines(self):
        pool = synthetic_pool()
        tide = validation.select_candidates("TIDE", pool, 2, __import__("random").Random(0))
        baseline = validation.select_candidates("UNCERTAINTY_ONLY", pool, 2, __import__("random").Random(0))
        allowed = {"candidate_id", "location_id", "uncertainty", "anomaly_persistence", "data_gap", "observation_value"}
        self.assertTrue(all(set(c).issuperset(allowed) for c in tide + baseline))

    def test_random_is_seed_reproducible(self):
        import random
        pool = synthetic_pool()
        a = [c["candidate_id"] for c in validation.select_candidates("RANDOM", pool, 3, random.Random(5))]
        b = [c["candidate_id"] for c in validation.select_candidates("RANDOM", pool, 3, random.Random(5))]
        self.assertEqual(a, b)

    def test_unknown_strategy_rejected(self):
        with self.assertRaises(ValueError):
            validation.select_candidates("MAGIC", synthetic_pool(), 1, __import__("random").Random(0))


class BenchmarkTests(unittest.TestCase):
    def test_report_is_deterministic_for_fixed_seed(self):
        first = run_synthetic()
        second = run_synthetic()
        self.assertEqual(first["rows"], second["rows"])

    def test_all_numeric_outputs_are_finite(self):
        report = run_synthetic()
        for row in report["rows"]:
            for key in ("initial_uncertainty", "final_uncertainty", "uncertainty_reduction",
                        "relative_uncertainty_reduction", "observation_cost"):
                value = row[key]
                self.assertTrue(value is None or math.isfinite(value), (key, value))
        self.assertFalse(report["selection"]["pool_is_degenerate"])

    def test_ground_truth_is_honestly_unavailable(self):
        report = run_synthetic()
        self.assertFalse(report["ground_truth"]["available"])
        self.assertEqual(report["ground_truth"]["false_alarm"], "GROUND TRUTH UNAVAILABLE")
        self.assertEqual(report["ground_truth"]["missed_event"], "GROUND TRUTH UNAVAILABLE")

    def test_aggregates_gate_on_minimum_sample(self):
        report = run_synthetic(cases=synthetic_cases(1), budget=1)
        for aggregate in report["aggregates"]:
            self.assertEqual(aggregate["uncertainty_reduction"]["status"], "INSUFFICIENT DATA (N=1)")

    def test_simulated_rows_are_labelled(self):
        report = run_synthetic()
        for row in report["rows"]:
            self.assertEqual(row["data_status"]["observation"], "SIMULATED")
            self.assertEqual(row["cost_label"], validation.COST_ASSUMPTION)

    def test_fairness_block_shared_pool(self):
        report = run_synthetic()
        self.assertTrue(report["fairness"]["same_pool_per_strategy"])
        self.assertEqual(report["fairness"]["budget_uniform"], 2)

    def test_validation_error_absent_when_no_pair(self):
        report = run_synthetic()
        for row in report["rows"]:
            self.assertFalse(row["validation_error"]["available"])
            self.assertIsNone(row["validation_error"]["absolute_error"])


class ConsistencyAndEdgeTests(unittest.TestCase):
    def test_sensitivity_is_monotonic(self):
        report = validation.sensitivity_report()
        self.assertTrue(report["all_consistent"])
        self.assertEqual(report["label"], "ALGORITHM CONSISTENCY TESTING")

    def test_edge_cases_never_nan_or_infinite(self):
        report = validation.edge_case_report()
        self.assertTrue(report["all_finite"])
        for result in report["results"]:
            self.assertTrue(math.isfinite(result["observation_value"]))

    def test_ranking_sensitivity_needs_sample(self):
        report = validation.ranking_sensitivity(synthetic_pool(2))
        self.assertFalse(report["available"])


class VerdictContradictionTests(unittest.TestCase):
    def test_defaults_preserve_original_behaviour(self):
        strong = classify_verdict(severity=.8, persistence=.8, spatial_consistency=.8, observation_count=4)
        self.assertEqual(strong["verdict"], "LIKELY_MODEL_ISSUE")

    def test_conflicting_evidence_downgrades_to_insufficient(self):
        conflicting = classify_verdict(severity=.8, persistence=.8, spatial_consistency=.8,
                                       observation_count=4, agreeing_observations=1, disagreeing_observations=3)
        self.assertEqual(conflicting["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("conflicting", conflicting["alternative_explanation"].lower())

    def test_majority_agreement_can_still_classify(self):
        agreeing = classify_verdict(severity=.8, persistence=.8, spatial_consistency=.8,
                                    observation_count=4, agreeing_observations=4, disagreeing_observations=1)
        self.assertEqual(agreeing["verdict"], "LIKELY_MODEL_ISSUE")


class EvidenceAndConfidenceTests(unittest.TestCase):
    def _candidate(self):
        return {"candidate_id": "tide-9", "location_id": 2, "location": "Demo", "depth_m": 0,
                "status": "MODEL_DERIVED", "variable": "temperature", "observation_type": "BUOY",
                "uncertainty": .8, "data_gap": .7, "anomaly_persistence": .6, "decision_impact": .7,
                "observation_cost": .4, "expected_uncertainty_reduction": .5,
                "affected_decision": "INVESTIGATE_ANOMALY", "confidence": .7, "confidence_factors": [],
                "limitations": [], "evidence": [{"type": "MODEL_OBSERVATION_MISMATCH", "strength": .8, "description": "mismatch"}]}

    def test_evidence_ids_are_stable(self):
        first = trace_evidence(self._candidate())
        second = trace_evidence(self._candidate())
        self.assertEqual([e["evidence_id"] for e in first], [e["evidence_id"] for e in second])

    def test_confidence_is_not_uncertainty_or_observation_value(self):
        candidate = self._candidate()
        context = confidence_context(candidate, trace_evidence(candidate))
        self.assertIn("overall_confidence", context)
        self.assertNotIn("observation_value", context)
        self.assertNotEqual(context["overall_confidence"], candidate["uncertainty"])


class SimulationIsolationTests(unittest.TestCase):
    def test_benchmark_does_not_modify_observation_store(self):
        from app.core.database import SessionLocal
        from app.models.observation import OceanObservation
        db = SessionLocal()
        try:
            before = db.query(OceanObservation).count()
            validation.validation_status(db)
            validation.run_database_benchmark(db, budget=2)
            after = db.query(OceanObservation).count()
            self.assertEqual(before, after)
        finally:
            db.close()


class CopilotValidationTests(unittest.TestCase):
    def setUp(self):
        from app.core.database import SessionLocal
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_validation_questions_route_to_tide_validation(self):
        from app.modules.ai.nlp.copilot import detect_intent
        for question in (
            "Is TIDE scientifically validated?",
            "What is the TIDE algorithm version?",
            "Can I reproduce the TIDE benchmark?",
            "How does TIDE compare to the baselines?",
        ):
            self.assertEqual(detect_intent(question), "tide_validation", question)

    def test_answer_never_claims_scientific_validation(self):
        from app.modules.ai.nlp.copilot import copilot_answer
        result = copilot_answer(self.db, "Is TIDE scientifically validated?")
        self.assertEqual(result["intent"], "tide_validation")
        self.assertIn("not scientifically", result["answer"].lower())
        self.assertIn("ground truth", result["answer"].lower())
        self.assertIn("algorithm version", result["answer"].lower())

    def test_benchmark_question_returns_metrics_card(self):
        from app.modules.ai.nlp.copilot import copilot_answer
        result = copilot_answer(self.db, "How does TIDE compare to the baselines?")
        self.assertEqual(result["intent"], "tide_validation")
        self.assertEqual(result["data"]["type"], "metrics")


class ValidationApiTests(unittest.TestCase):
    def setUp(self):
        from app.main import app
        self.client = TestClient(app)

    def test_validation_status_endpoint(self):
        response = self.client.get("/api/v1/tide/validation")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["maturity"]["EMPIRICALLY_VALIDATED"], [])
        self.assertFalse(payload["data"]["ground_truth"]["available"])
        self.assertTrue(payload["data"]["edge_cases"]["all_finite"])

    def test_benchmarks_endpoint(self):
        response = self.client.get("/api/v1/tide/benchmarks?budget=1&variables=temperature&strategies=TIDE,RANDOM")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["configuration"]["budget"], 1)
        self.assertEqual([a["strategy"] for a in data["aggregates"]], ["TIDE", "RANDOM"])
        self.assertTrue(all("N" in a for a in data["aggregates"]))

    def test_benchmarks_rejects_bad_budget(self):
        self.assertEqual(self.client.get("/api/v1/tide/benchmarks?budget=99").status_code, 422)

    def test_benchmarks_rejects_bad_strategy(self):
        self.assertEqual(self.client.get("/api/v1/tide/benchmarks?strategies=MAGIC").status_code, 422)

    def test_benchmarks_rejects_bad_variable(self):
        self.assertEqual(self.client.get("/api/v1/tide/benchmarks?variables=not_a_variable").status_code, 422)

    def test_benchmark_case_detail_and_not_found(self):
        ok = self.client.get("/api/v1/tide/benchmarks/temperature@0?budget=1")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["data"]["case"]["case_id"], "temperature@0")
        missing = self.client.get("/api/v1/tide/benchmarks/event-999")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
