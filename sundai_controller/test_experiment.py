import json
import os
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from controller import Chiplet, Design, FlightRecord, JevRoutingAdapter, ThermalResult
from experiment import LANE_IDS, run_four_lanes


class CountingOracle:
    def __init__(self):
        self.calls = []

    async def __call__(self, candidate):
        self.calls.append(candidate.hash)
        temperature = float(sum(x + y for x, y in candidate.positions))
        return ThermalResult(candidate.hash, temperature, "NONPHYSICAL-tfl05-test",
                             problem_hash="same-problem-for-all-lanes")


@dataclass(frozen=True)
class WiredThermalResult(ThermalResult):
    wirelength_mm: float = field(kw_only=True)
    wire_metric: str = field(kw_only=True)


class WiredOracle:
    async def __call__(self, candidate):
        temperature = float(sum(x + y for x, y in candidate.positions))
        return WiredThermalResult(candidate.hash, temperature, "NONPHYSICAL-tfl05-test",
                                  problem_hash="same-problem-for-all-lanes",
                                  wirelength_mm=7.25,
                                  wire_metric="connectivity-weighted Manhattan center distance (mm)")


class MockJevResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


def small_design():
    return Design(20, 10, 1, (Chiplet("a", 2, 2), Chiplet("b", 2, 2)), ((4, 1), (12, 1)))


class StrategyExperimentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service_key = Ed25519PrivateKey.from_private_bytes(os.urandom(32))

    async def test_four_lanes_share_initial_samples_and_verify_equal_budget_records(self):
        oracle = CountingOracle()
        result = await run_four_lanes(small_design(), oracle, service_key=self.service_key, run_id="test-run", seed=7,
                                      evaluations_per_lane=3, shared_sample_count=2,
                                      evaluation_ceiling_microdollars=10)

        self.assertEqual(result["lane_ids"], LANE_IDS)
        self.assertEqual(result["shared_initial_sample_count"], 3)
        self.assertTrue(result["evaluation_counts_equal"])
        self.assertTrue(result["flight_records_valid"])
        # Each controller independently verifies the same three designs; those
        # initialization calls are outside each lane's three proposal evaluations.
        self.assertEqual(len(oracle.calls), 4 * 3 + 4 * 3)
        self.assertEqual(len(set(result["shared_initial_sample_hashes"])), 3)

        lanes = result["lane_results"]
        self.assertEqual({lane["evaluation_count"] for lane in lanes.values()}, {3})
        self.assertEqual({lane["evaluation_admissions"] for lane in lanes.values()}, {3})
        self.assertEqual(len({lane["agent_id"] for lane in lanes.values()}), 4)
        self.assertEqual(len({lane["identity_public_key"] for lane in lanes.values()}), 4)
        for lane in lanes.values():
            self.assertEqual(lane["shared_initial_sample_hashes"], result["shared_initial_sample_hashes"])
            self.assertGreater(lane["wall_time_s"], 0)
            self.assertEqual(lane["noop_evaluations"], sum(
                event["payload"].get("noop") is True for event in lane["record"]
                if event["event"] == "lane_decision"))
            self.assertTrue(FlightRecord.verify(lane["record"], lane["record_public_key"]))
            baseline = next(event for event in lane["record"] if event["event"] == "baseline")
            self.assertEqual(tuple(sample["design_hash"] for sample in
                                   baseline["payload"]["shared_initial_samples"]),
                             result["shared_initial_sample_hashes"])
            self.assertEqual(sum(event["event"] == "task_granted" for event in lane["record"]), 3)

        annealing_scales = [event["payload"]["state"]["temperature_scale_c"]
                            for event in lanes["simulated_annealing"]["record"]
                            if event["event"] == "lane_decision"]
        self.assertEqual(annealing_scales[0], 0.5)
        self.assertAlmostEqual(annealing_scales[-1], 0.05)
        self.assertTrue(all(left > right for left, right in zip(annealing_scales, annealing_scales[1:])))

    async def test_signal_router_advice_is_logged_and_stays_inside_lane_record(self):
        oracle = CountingOracle()
        routes = []
        probabilities = {"local_move": 0.1, "swap": 0.1, "global_resample": 0.7, "stop": 0.1}

        async def router(state):
            routes.append(state)
            return {"route": "global_resample", "reason": "validated fixture advice",
                    "provider_called": True, "input_hash": "a" * 64, "output_hash": "b" * 64,
                    "probabilities": probabilities, "confidence": 0.8, "duration_ms": 12.5,
                    "retry_count": 0, "model": "jev-1.13.0", "api_key": "fixture-secret-value"}

        result = await run_four_lanes(small_design(), oracle, service_key=self.service_key, run_id="signal-test", seed=2,
                                      evaluations_per_lane=1, shared_sample_count=0,
                                      signal_router=router)
        signal = result["lane_results"]["signal_portfolio"]
        decision = next(event for event in signal["record"] if event["event"] == "lane_decision")
        signal_decision = next(event for event in signal["record"] if event["event"] == "signal_decision")

        self.assertEqual(len(routes), 1)
        self.assertEqual(decision["payload"]["operator"], "global_resample")
        self.assertEqual(routes[0]["horizon_evaluations"], 1)
        self.assertEqual(routes[0]["evaluations_remaining"], 1)
        self.assertEqual(routes[0]["stagnation_count"], 0)
        self.assertEqual(routes[0]["current_tmax_c"], routes[0]["verified_history"][-1]["tmax_c"])
        self.assertIsNone(routes[0]["current_wirelength_mm"])
        self.assertEqual(signal_decision["payload"]["input_hash"], "a" * 64)
        self.assertEqual(signal_decision["payload"]["output_hash"], "b" * 64)
        self.assertEqual(signal_decision["payload"]["probabilities"], probabilities)
        self.assertEqual(signal_decision["payload"]["confidence"], 0.8)
        self.assertEqual(signal_decision["payload"]["latency_ms"], 12.5)
        self.assertTrue(signal_decision["payload"]["provider_called"])
        self.assertNotIn("jev-1.13.0", repr(signal["record"]))
        self.assertNotIn("fixture-secret-value", repr(signal["record"]))
        self.assertTrue(FlightRecord.verify(signal["record"], signal["record_public_key"]))

    async def test_signal_stop_disables_provider_but_preserves_equal_evaluations(self):
        oracle = CountingOracle()
        calls = 0
        probabilities = {"local_move": 0.1, "swap": 0.1, "global_resample": 0.1, "stop": 0.7}

        async def router(state):
            nonlocal calls
            calls += 1
            return {"route": "stop", "provider_called": True,
                    "input_hash": "c" * 64, "output_hash": "d" * 64,
                    "probabilities": probabilities, "confidence": 0.9, "duration_ms": 4.0}

        result = await run_four_lanes(small_design(), oracle, service_key=self.service_key, run_id="signal-stop", seed=4,
                                      evaluations_per_lane=4, shared_sample_count=0,
                                      signal_router=router)
        signal = result["lane_results"]["signal_portfolio"]
        decisions = [event["payload"] for event in signal["record"] if event["event"] == "signal_decision"]
        self.assertEqual(calls, 1)
        self.assertEqual(signal["evaluation_count"], 4)
        self.assertEqual(len(decisions), 4)
        self.assertTrue(decisions[0]["stop_requested"])
        self.assertEqual(decisions[0]["requested_choice"], "stop")
        self.assertFalse(decisions[1]["provider_called"])
        self.assertEqual(decisions[1]["fallback_reason"], "signal-layer advice stopped for this lane")
        self.assertTrue(FlightRecord.verify(signal["record"], signal["record_public_key"]))

    async def test_invalid_choice_probabilities_use_host_fallback(self):
        oracle = CountingOracle()

        async def router(state):
            return {"route": "global_resample", "provider_called": True,
                    "input_hash": "e" * 64, "output_hash": "f" * 64,
                    "probabilities": {"local_move": True, "swap": 0.0,
                                       "global_resample": 0.0, "stop": 0.0},
                    "confidence": 0.9, "duration_ms": 3.0}

        result = await run_four_lanes(small_design(), oracle, service_key=self.service_key, run_id="signal-invalid", seed=6,
                                      evaluations_per_lane=1, shared_sample_count=0,
                                      signal_router=router)
        signal = result["lane_results"]["signal_portfolio"]
        event = next(event for event in signal["record"] if event["event"] == "signal_decision")
        lane = next(event for event in signal["record"] if event["event"] == "lane_decision")
        self.assertIsNone(event["payload"]["requested_choice"])
        self.assertEqual(event["payload"]["applied_operator"], "swap")
        self.assertEqual(event["payload"]["fallback_reason"],
                         "invalid advisory response; deterministic fallback")
        self.assertEqual(lane["payload"]["operator"], "swap")
        self.assertTrue(FlightRecord.verify(signal["record"], signal["record_public_key"]))

    async def test_jev_adapter_is_wired_into_the_signal_lane_without_model_or_key_in_record(self):
        probabilities = {"local_move": 0.1, "swap": 0.6, "global_resample": 0.2, "stop": 0.1}
        provider_response = {"model": "jev-1.13.0", "usage": {"input_tokens": 12, "output_tokens": 3},
                             "answers": {"route": {
            "type": "choice", "choice": "swap", "probabilities": probabilities, "confidence": 0.7}}}
        adapter = JevRoutingAdapter(max_calls=1, timeout_s=0.5)
        with patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "fixture-secret-value"}), \
                patch("urllib.request.urlopen", return_value=MockJevResponse(provider_response)):
            result = await run_four_lanes(small_design(), CountingOracle(), service_key=self.service_key, run_id="signal-live-mock", seed=7,
                                          evaluations_per_lane=1, shared_sample_count=0,
                                          signal_router=adapter)
        signal = result["lane_results"]["signal_portfolio"]
        event = next(event for event in signal["record"] if event["event"] == "signal_decision")
        lane = next(event for event in signal["record"] if event["event"] == "lane_decision")
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(event["payload"]["requested_choice"], "swap")
        self.assertEqual(event["payload"]["input_tokens"], 12)
        self.assertEqual(event["payload"]["output_tokens"], 3)
        self.assertEqual(event["payload"]["probabilities"], probabilities)
        self.assertEqual(lane["payload"]["operator"], "swap")
        self.assertNotIn("jev-1.13.0", repr(signal["record"]))
        self.assertNotIn("fixture-secret-value", repr(signal["record"]))
        self.assertTrue(FlightRecord.verify(signal["record"], signal["record_public_key"]))

    async def test_signal_state_uses_only_verified_measured_wire(self):
        states = []

        def router(state):
            states.append(state)
            return "local_move", "test advice"

        result = await run_four_lanes(small_design(), WiredOracle(), service_key=self.service_key, run_id="signal-wire", seed=5,
                                      evaluations_per_lane=1, shared_sample_count=0,
                                      signal_router=router)
        state = states[0]
        signal = result["lane_results"]["signal_portfolio"]
        self.assertEqual(state["current_wirelength_mm"], 7.25)
        self.assertEqual(state["current_wire_metric"],
                         "connectivity-weighted Manhattan center distance (mm)")
        self.assertTrue(all(sample["wirelength_mm"] == 7.25 for sample in state["verified_history"]))
        self.assertTrue(FlightRecord.verify(signal["record"], signal["record_public_key"]))

    async def test_oracle_failure_cannot_count_as_a_completed_lane_evaluation(self):
        calls = 0

        async def failing_oracle(candidate):
            nonlocal calls
            calls += 1
            if calls == 2:  # shared baseline succeeds; first lane proposal fails
                raise TimeoutError("simulator unavailable")
            temperature = float(sum(x + y for x, y in candidate.positions))
            return ThermalResult(candidate.hash, temperature, "NONPHYSICAL-tfl05-test",
                                 problem_hash="same-problem-for-all-lanes")

        with self.assertRaisesRegex(RuntimeError, "random oracle evaluation failed"):
            await run_four_lanes(small_design(), failing_oracle, service_key=self.service_key, run_id="failure-test", seed=3,
                                 evaluations_per_lane=1, shared_sample_count=0,
                                 evaluation_ceiling_microdollars=10)

    async def test_provider_ceiling_violation_cannot_complete_a_lane(self):
        calls = 0

        async def over_ceiling_oracle(candidate):
            nonlocal calls
            calls += 1
            cost = 0 if calls == 1 else 11  # shared baseline is free; first proposal exceeds ceiling 10
            temperature = float(sum(x + y for x, y in candidate.positions))
            return ThermalResult(candidate.hash, temperature, "NONPHYSICAL-tfl05-test",
                                 cost_microdollars=cost, problem_hash="same-problem-for-all-lanes")

        with self.assertRaisesRegex(RuntimeError, "random controller stopped: provider exceeded declared cost ceiling"):
            await run_four_lanes(small_design(), over_ceiling_oracle, service_key=self.service_key, run_id="ceiling-test", seed=3,
                                 evaluations_per_lane=1, shared_sample_count=0,
                                 evaluation_ceiling_microdollars=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
