import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.modules.ai.tide.scoring import calculate_observation_value, unit
from app.modules.ai.tide.verdicts import classify_verdict
from app.modules.ai.tide.explanations import confidence_context, recommendation_explanation, trace_evidence


def candidate(**overrides):
    data = {"decision_impact": 0.6, "uncertainty": 0.6, "data_gap": 0.6,
            "anomaly_persistence": 0.6, "observation_cost": 0.5}
    data.update(overrides)
    return data


class TideScoringTests(unittest.TestCase):
    def test_score_increases_with_each_benefit_component(self):
        baseline = calculate_observation_value(candidate())["observation_value"]
        for field in ("decision_impact", "uncertainty", "data_gap", "anomaly_persistence"):
            self.assertGreater(calculate_observation_value(candidate(**{field: .9}))["observation_value"], baseline)

    def test_score_decreases_with_cost(self):
        self.assertGreater(calculate_observation_value(candidate(observation_cost=.2))["observation_value"],
                           calculate_observation_value(candidate(observation_cost=.8))["observation_value"])

    def test_invalid_and_zero_values_are_safe(self):
        result = calculate_observation_value(candidate(observation_cost=0, uncertainty=float("nan")))
        self.assertEqual(result["uncertainty"], 0.0)
        self.assertEqual(result["observation_value"], 0.0)
        self.assertEqual(unit(float("inf")), 0.0)
        self.assertEqual(calculate_observation_value(candidate(observation_cost=None))["observation_cost"], 1.0)

    def test_equal_values_can_be_ranked_deterministically_by_id(self):
        rows = [{"id": "b", **calculate_observation_value(candidate())}, {"id": "a", **calculate_observation_value(candidate())}]
        self.assertEqual([x["id"] for x in sorted(rows, key=lambda x: (-x["observation_value"], x["id"]))], ["a", "b"])


class TideVerdictTests(unittest.TestCase):
    def test_isolated_spike_suggests_sensor_issue(self):
        self.assertEqual(classify_verdict(severity=.9, persistence=.1, spatial_consistency=.1, quality=.1, observation_count=3)["verdict"], "LIKELY_SENSOR_ISSUE")

    def test_coherent_persistent_mismatch_suggests_model_issue(self):
        self.assertEqual(classify_verdict(severity=.8, persistence=.8, spatial_consistency=.8, observation_count=4)["verdict"], "LIKELY_MODEL_ISSUE")

    def test_coherent_moderate_persistence_suggests_missing_phenomenon(self):
        self.assertEqual(classify_verdict(severity=.7, persistence=.5, spatial_consistency=.5, observation_count=4)["verdict"], "LIKELY_MISSING_PHENOMENON")

    def test_sparse_evidence_is_insufficient(self):
        self.assertEqual(classify_verdict(severity=.9, persistence=.9, spatial_consistency=.9, observation_count=1)["verdict"], "INSUFFICIENT_EVIDENCE")


class TideExplanationTests(unittest.TestCase):
    def _candidate(self):
        return {"candidate_id": "tide-1", "location_id": 1, "location": "Demo", "depth_m": 100, "status": "MODEL_DERIVED", "variable": "oxygen", "observation_type": "ARGO_FLOAT", "uncertainty": .8, "data_gap": .7, "anomaly_persistence": .6, "decision_impact": .7, "observation_cost": .4, "expected_uncertainty_reduction": .5, "affected_decision": "INVESTIGATE_ANOMALY", "confidence": .7, "confidence_factors": [{"description": "Spatial support", "score": .8}], "limitations": [], "evidence": [{"type": "MODEL_OBSERVATION_MISMATCH", "strength": .8, "description": "Existing mismatch"}, {"type": "DATA_GAP", "strength": .7, "description": "Sparse data"}]}

    def test_evidence_preserves_traceability(self):
        evidence = trace_evidence(self._candidate())
        self.assertEqual(evidence[0]["source_system"], "Twin Comparison")
        self.assertEqual(evidence[0]["location_id"], 1)

    def test_explanation_uses_actual_signals(self):
        candidate = self._candidate()
        evidence = trace_evidence(candidate)
        explanation = recommendation_explanation(candidate, evidence, confidence_context(candidate, evidence))
        self.assertTrue(any("uncertainty" in reason.lower() for reason in explanation["reasons"]))
        self.assertTrue(any("data gap" in reason.lower() for reason in explanation["reasons"]))


class TideApiTests(unittest.TestCase):
    def setUp(self):
        from app.main import app
        self.client = TestClient(app)

    def test_invalid_variable_is_rejected(self):
        response = self.client.get("/api/v1/tide/candidates?variable=not_a_variable")
        self.assertEqual(response.status_code, 422)

    def test_empty_verdict_returns_not_found(self):
        with patch("app.api.tide._engine") as engine:
            engine.return_value.verdict.return_value = None
            response = self.client.get("/api/v1/tide/verdict?location_id=99")
        self.assertEqual(response.status_code, 404)

    def test_candidate_response_has_envelope(self):
        row = {"candidate_id": "tide-1-temperature-0-buoy", "location_id": 1, "location": "Demo", "latitude": None, "longitude": None,
               "depth_m": 0, "variable": "temperature", "observation_type": "BUOY", "status": "MODEL_DERIVED",
               **calculate_observation_value(candidate()), "affected_decision": "INCREASE_MONITORING", "reason": "test", "evidence": [],
               "confidence": .5, "confidence_factors": [], "limitations": []}
        with patch("app.api.tide._engine") as engine:
            engine.return_value.rankings.return_value = [row]
            response = self.client.get("/api/v1/tide/candidates")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["data"][0]["candidate_id"], row["candidate_id"])

    def _simulation(self):
        state = {"uncertainty": .6, "anomaly_risk": .5, "ranking": 1, "decision": "INVESTIGATE_ANOMALY", "confidence": .5, "observation_value": .03}
        change = {"before": .6, "after": .5, "delta": -0.1}
        return {"candidate_id": "tide-1-temperature-0-virtual_sensor", "location_id": 1, "location": "Demo", "variable": "temperature",
                "depth_m": 0, "observation_type": "VIRTUAL_SENSOR", "before": state, "after": state,
                "simulated_observation": {"value": 18.2, "variable": "temperature", "depth_m": 0, "location": "Demo",
                                          "location_id": 1, "observation_type": "VIRTUAL_SENSOR", "status": "SIMULATED"},
                "uncertainty_change": change, "risk_change": change, "confidence_change": change,
                "decision_changed": False, "decision_result": "DECISION_UNCHANGED", "supports_model_hypothesis": False,
                "notes": ["SIMULATED OBSERVATION - DEMONSTRATION ONLY"], "method": "deterministic_heuristic"}

    def test_virtual_observation_validates_variable(self):
        response = self.client.post("/api/v1/tide/virtual-observation",
                                    json={"location_id": 1, "variable": "not_a_variable"})
        self.assertEqual(response.status_code, 422)

    def test_virtual_observation_returns_simulated_payload(self):
        with patch("app.api.tide._engine") as engine:
            engine.return_value.virtual_observation.return_value = self._simulation()
            response = self.client.post("/api/v1/tide/virtual-observation",
                                        json={"location_id": 1, "variable": "temperature", "value": 18.2})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["simulated_observation"]["status"], "SIMULATED")
        self.assertEqual(payload["data"]["decision_result"], "DECISION_UNCHANGED")

    def test_virtual_observation_without_candidate_returns_not_found(self):
        with patch("app.api.tide._engine") as engine:
            engine.return_value.virtual_observation.return_value = None
            response = self.client.post("/api/v1/tide/virtual-observation", json={"location_id": 99})
        self.assertEqual(response.status_code, 404)
