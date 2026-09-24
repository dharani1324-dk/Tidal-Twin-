import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.modules.ai.tide.replay import build_replay, regret_value


def candidate(**overrides):
    data = {
        "candidate_id": "tide-1-temperature-0-buoy",
        "location_id": 1,
        "location": "Test Bay",
        "latitude": None,
        "longitude": None,
        "depth_m": 0,
        "variable": "temperature",
        "observation_type": "BUOY",
        "status": "MODEL_DERIVED",
        "uncertainty": 0.72,
        "data_gap": 0.68,
        "anomaly_persistence": 0.7,
        "decision_impact": 0.75,
        "observation_cost": 0.4,
        "expected_uncertainty_reduction": 0.4,
        "confidence": 0.42,
        "observed_value": 29.7,
        "model_value": 28.4,
    }
    data.update(overrides)
    return data


def event_context(**overrides):
    ctx = {
        "event_id": "event-0",
        "event": {
            "event_type": "sst_anomaly",
            "label": "Warm water anomaly",
            "icon": "W",
            "location_id": 1,
            "location": "Test Bay",
            "variable": "temperature",
            "severity": "high",
            "intensity": "high",
            "confidence": 92,
            "model": 28.4,
            "observed": 29.7,
            "model_observed_diff": 1.3,
            "persistence": 5,
            "began_hours_ago": 36,
            "data_status": "demo",
            "evolution": "SST drifted +1.3C over 36h.",
        },
        "event_dna": {"tags": ["marine-heatwave", "west-coast"]},
        "uncertainty": {"score": 0.72, "level": "high"},
        "data_gaps": [{"variable": "temperature", "location_id": 1, "depth_m": 0}],
        "disagreement": {
            "variable": "temperature",
            "depth_m": 0.0,
            "model_value": 28.4,
            "observed_value": 29.7,
            "difference": 1.3,
            "normalized_severity": 0.72,
        },
        "top_candidates": [candidate()],
        "evidence": [
            {"type": "MODEL_OBSERVATION_MISMATCH", "strength": 0.8, "description": "Existing mismatch of 1.3C."},
        ],
        "confidence": {"score": 0.6},
        "verdict": None,
        "decision_context": {"active_decision": "INVESTIGATE_ANOMALY"},
        "evidence_chain": [],
    }
    ctx.update(overrides)
    return ctx


def simulation(**overrides):
    sim = {
        "candidate_id": "tide-1-temperature-0-virtual_sensor",
        "location_id": 1,
        "location": "Test Bay",
        "variable": "temperature",
        "depth_m": 0,
        "observation_type": "VIRTUAL_SENSOR",
        "before": {"uncertainty": 0.72, "anomaly_risk": 0.7, "ranking": 1,
                   "decision": "INVESTIGATE_ANOMALY", "confidence": 0.42, "observation_value": 29.7},
        "simulated_observation": {"value": 29.7, "variable": "temperature", "depth_m": 0,
                                  "location": "Test Bay", "location_id": 1,
                                  "observation_type": "VIRTUAL_SENSOR", "status": "SIMULATED"},
        "after": {"uncertainty": 0.46, "anomaly_risk": 0.8, "ranking": 1,
                  "decision": "INVESTIGATE_ANOMALY", "confidence": 0.66, "observation_value": 29.7},
        "uncertainty_change": {"before": 0.72, "after": 0.46, "delta": -0.26},
        "risk_change": {"before": 0.7, "after": 0.8, "delta": 0.1},
        "confidence_change": {"before": 0.42, "after": 0.66, "delta": 0.24},
        "decision_changed": False,
        "decision_result": "DECISION_UNCHANGED",
        "supports_model_hypothesis": False,
        "notes": ["SIMULATED OBSERVATION - DEMONSTRATION ONLY"],
        "method": "deterministic_heuristic",
    }
    sim.update(overrides)
    return sim


def build_replay_fixture(**overrides):
    return build_replay(event_context(), candidate(), simulation(),
                        event_id="event-0", variable="temperature", depth_m=0.0, **overrides)


class ReplayRegretTests(unittest.TestCase):
    def test_positive_when_observation_reduces_uncertainty_and_raises_confidence(self):
        self.assertEqual(regret_value(0.8, 0.4, 0.5, 0.6), 0.25)

    def test_clamps_to_zero(self):
        self.assertEqual(regret_value(0.4, 0.9, 0.9, 0.2), 0.0)

    def test_clamps_to_one(self):
        self.assertEqual(regret_value(1.0, 0.0, 0.0, 1.0), 1.0)


class ReplayBuildTests(unittest.TestCase):
    def test_full_timeline_is_present(self):
        steps = build_replay_fixture()["steps"]
        self.assertEqual([s["id"] for s in steps[:2]], ["EVENT_START", "NORMAL"])
        self.assertEqual(steps[-1]["id"], "VALIDATION")
        self.assertEqual(len(steps), 10)

    def test_modes_are_identical_before_observation(self):
        replay = build_replay_fixture()
        obs_index = next(i for i, s in enumerate(replay["steps"]) if s["id"] == "OBSERVATION")
        for step in replay["steps"][:obs_index]:
            self.assertEqual(step["model_only"], step["tide_assisted"])
            self.assertIsNone(step["model_only"]["observation_status"])

    def test_tide_assisted_diverge_at_observation_with_simulated_marker(self):
        replay = build_replay_fixture()
        obs = next(s for s in replay["steps"] if s["id"] == "OBSERVATION")
        self.assertNotEqual(obs["model_only"], obs["tide_assisted"])
        self.assertEqual(obs["tide_assisted"]["observation_status"], "SIMULATED")
        self.assertEqual(obs["tide_assisted"]["observed_value"], 29.7)
        self.assertIsNone(obs["model_only"]["observation_value"])
        self.assertTrue(any("SIMULATED" in n.upper() for n in replay["notes"]))

    def test_decision_summary_and_changed_flag(self):
        replay = build_replay_fixture()
        self.assertFalse(replay["decision"]["decision_changed"])
        self.assertEqual(replay["decision"]["decision_result"], "DECISION_UNCHANGED")
        self.assertEqual(replay["comparison"]["decision"]["model_only"], "INVESTIGATE_ANOMALY")
        self.assertEqual(replay["decision"]["before"], replay["comparison"]["decision"]["model_only"])

    def test_comparison_metrics_are_numeric_for_continuous_fields(self):
        replay = build_replay_fixture()
        for key in ("uncertainty", "confidence", "anomaly_risk"):
            metric = replay["comparison"][key]
            self.assertTrue(metric["calculated"])
            self.assertIsInstance(metric["model_only"], (int, float))
            self.assertIsInstance(metric["delta"], (int, float))

    def test_validation_uses_real_block_and_simulated_block(self):
        replay = build_replay_fixture()
        self.assertTrue(replay["validation"]["available"])
        self.assertTrue(replay["validation"]["model_only"]["simulated"] is False)
        self.assertTrue(replay["validation"]["tide_assisted"]["simulated"] is True)
        self.assertEqual(replay["validation"]["tide_assisted"]["quality_status"], "SIMULATED")
        self.assertEqual(replay["validation"]["tide_assisted"]["observed"], 29.7)

    def test_validation_unavailable_when_no_values_exist(self):
        ctx = event_context(disagreement={"variable": "temperature", "depth_m": 0.0})
        sim = simulation()
        sim["simulated_observation"]["value"] = None
        replay = build_replay(ctx, candidate(), sim, event_id="event-0", variable="temperature")
        self.assertFalse(replay["validation"]["available"])
        self.assertIn("VALIDATION DATA UNAVAILABLE", replay["validation"]["message"])

    def test_data_status_maps_demo_to_simulated_trust(self):
        replay = build_replay_fixture()
        self.assertEqual(replay["data_status"]["event"], "SIMULATED")
        self.assertEqual(replay["data_status"]["validation_real"], "SIMULATED")
        self.assertEqual(replay["data_status"]["observation_tide_assisted"], "SIMULATED")

    def test_evidence_journey_arranges_signals_by_step(self):
        replay = build_replay_fixture()
        first = replay["evidence_journey"][0]
        self.assertEqual(first["step"], "EVENT_START")
        self.assertIn("OBSERVATION", [e["step"] for e in replay["evidence_journey"]])


class ReplayApiTests(unittest.TestCase):
    def setUp(self):
        from app.main import app
        self.client = TestClient(app)

    def test_events_index_orders_playable_events(self):
        evs = [{"event_type": "sst_anomaly", "label": "Warm anomaly", "icon": "W",
                "intensity": "high", "confidence": 92, "location_id": 3, "location": "Kelp Bay",
                "variable": "temperature", "began_hours_ago": 12, "data_status": "demo"}]
        with patch("app.api.tide.adapters.detect_events", return_value={"events": evs}):
            response = self.client.get("/api/v1/tide/events")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]["events"]
        self.assertEqual(data[0]["event_id"], "event-0")
        self.assertEqual(data[0]["location_id"], 3)
        self.assertEqual(data[0]["confidence"], 0.92)

    def test_replay_returns_contract_payload(self):
        replay = build_replay_fixture()
        with patch("app.api.tide.ReplayEngine.build", return_value=replay):
            response = self.client.get("/api/v1/tide/events/event-0/replay")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["event_id"], "event-0")
        self.assertEqual(len(payload["data"]["steps"]), 10)
        self.assertEqual(payload["data"]["regret"]["caveat"],
                         "DEMONSTRATION METRIC - NOT A SCIENTIFIC VALIDATION METRIC")
        self.assertIn("SIMULATED", payload["data"]["labels"]["observation"])

    def test_replay_carries_replay_mode_labels(self):
        replay = build_replay_fixture()
        with patch("app.api.tide.ReplayEngine.build", return_value=replay):
            response = self.client.get("/api/v1/tide/events/event-0/replay")
        labels = response.json()["data"]["labels"]
        self.assertIn("MODEL-ONLY", labels["model_only"])
        self.assertIn("TIDE-ASSISTED", labels["tide_assisted"])

    def test_replay_not_found_when_engine_cannot_build(self):
        with patch("app.api.tide.ReplayEngine.build", return_value=None):
            response = self.client.get("/api/v1/tide/events/event-0/replay")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "TIDE_EVENT_NOT_FOUND")

    def test_replay_rejects_invalid_variable(self):
        response = self.client.get("/api/v1/tide/events/event-0/replay?variable=not_a_variable")
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()