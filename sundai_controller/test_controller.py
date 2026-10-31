import asyncio
import copy
import json
import math
import os
import random
import unittest
import urllib.error
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from controller import (Chiplet, Controller, Design, FlightRecord, JevRoutingAdapter,
                        Proposal, ThermalResult, choose_advisory_operation,
                        normalized_source_sha256)


def fixture_design():
    return Design(20, 10, 1, (Chiplet("a", 2, 2), Chiplet("b", 2, 2)), ((4, 1), (12, 1)))


class JsonHttpResponse:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


def jev_response(route="swap", *, model="jev-1.13.0", probabilities=None, confidence=0.75):
    probabilities = probabilities or {choice: 0.25 for choice in
                                      ("local_move", "swap", "global_resample", "stop")}
    return {"model": model, "usage": {"input_tokens": 12, "output_tokens": 3},
            "answers": {"route": {
        "type": "choice", "choice": route, "probabilities": probabilities, "confidence": confidence}}}


async def fixture_oracle(candidate):
    # Deliberately nonphysical deterministic oracle for controller invariant tests.
    return ThermalResult(candidate.hash, sum(x for x, _ in candidate.positions), "NONPHYSICAL-test-fixture")


class GridCheckingOracle:
    def __init__(self):
        self.calls = 0

    def centers_for(self, candidate):
        for chiplet, (x, y) in zip(candidate.chiplets, candidate.positions):
            center = (x + chiplet.width_mm / 2, y + chiplet.height_mm / 2)
            if any(abs(value - round(value)) > 1e-9 for value in center):
                raise ValueError(f"chiplet {chiplet.id} center is off the 1 mm placement grid")
        return ()

    async def __call__(self, candidate):
        self.calls += 1
        return await fixture_oracle(candidate)


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.c = Controller(fixture_design(), fixture_oracle, evaluation_ceiling_microdollars=10)
        self.c.register("worker", self.key, allowed_tasks=("move-a", "bad-op"))
        await self.c.initialize()

    def move(self, x=1, **kwargs):
        return self.c.proposal("worker", self.key, "move-a", "move", {"chiplet": "a", "x_mm": x, "y_mm": 1}, **kwargs)

    async def test_initialize_evaluates_shared_designs_with_its_own_oracle(self):
        initial = fixture_design()
        shared = Design(20, 10, 1, initial.chiplets, ((5, 1), (12, 1)))
        evaluated = []

        async def oracle(candidate):
            evaluated.append(candidate.hash)
            temperature = 50.0 if candidate.hash == initial.hash else 40.0
            return ThermalResult(candidate.hash, temperature, "OWNED-initialization-oracle")

        controller = Controller(initial, oracle, evaluation_ceiling_microdollars=10)
        await controller.initialize(shared_initial_designs=(shared,))

        self.assertEqual(evaluated, [initial.hash, shared.hash])
        self.assertEqual(controller.design.hash, shared.hash)
        self.assertEqual(controller.best_temperature, 40.0)
        self.assertEqual(set(controller.verified_designs), {initial.hash, shared.hash})
        baseline = next(event for event in controller.log.events if event["event"] == "baseline")
        self.assertEqual(baseline["payload"]["initialization_source"], "controller_oracle")
        self.assertEqual(baseline["payload"]["shared_initial_design_count"], 1)

    async def test_initialize_does_not_accept_caller_supplied_results(self):
        initial = fixture_design()
        evaluated = []

        async def oracle(candidate):
            evaluated.append(candidate.hash)
            return await fixture_oracle(candidate)

        controller = Controller(initial, oracle, evaluation_ceiling_microdollars=10)
        forged = ThermalResult(initial.hash, -100.0, "FABRICATED-caller-result")

        with self.assertRaises(TypeError):
            await controller.initialize(baseline_result=forged)
        with self.assertRaisesRegex(ValueError, "shared initial samples must be designs"):
            await controller.initialize(shared_initial_designs=((initial, forged),))

        self.assertIsNone(controller.best_temperature)
        self.assertEqual(evaluated, [])

    async def test_commits_only_improvement_and_rejects_replay(self):
        proposal = self.move()
        self.assertEqual((await self.c.submit(proposal)).status, "committed")
        self.assertEqual((await self.c.submit(proposal)).reason, "replayed proposal")
        self.assertEqual(self.c.revision, 1)

    async def test_proposal_ids_are_scoped_to_the_agent(self):
        other_key = Ed25519PrivateKey.generate()
        self.c.register("worker-2", other_key, allowed_tasks=("move-a",))
        first = self.c.proposal("worker", self.key, "move-a", "move",
                                {"chiplet": "a", "x_mm": 3, "y_mm": 1}, proposal_id="shared-id")
        second = self.c.proposal("worker-2", other_key, "move-a", "move",
                                 {"chiplet": "a", "x_mm": 2, "y_mm": 1}, proposal_id="shared-id")
        self.assertEqual((await self.c.submit(first)).status, "committed")
        self.assertEqual((await self.c.submit(second)).status, "committed")
        self.assertEqual((await self.c.submit(second)).reason, "replayed proposal")

    async def test_signed_payload_mutation_and_wrong_signature_rejected(self):
        proposal = self.move()
        proposal.payload["args"]["x_mm"] = 3
        self.assertIn("signature", (await self.c.submit(proposal)).reason)
        other = Ed25519PrivateKey.generate()
        fake = Proposal.sign(other, **self.move().payload)
        self.assertIn("signature", (await self.c.submit(fake)).reason)
        self.assertEqual(self.c.calls, 0)

    async def test_geometry_and_operation_gate_before_oracle(self):
        self.assertEqual((await self.c.submit(self.move(12))).reason, "invalid geometry or operation")
        invalid = self.c.proposal("worker", self.key, "bad-op", "resize", {"chiplet": "a", "width_mm": 0})
        self.assertEqual((await self.c.submit(invalid)).status, "rejected")
        self.assertEqual(self.c.calls, 0)

    async def test_stale_async_candidate_cannot_overwrite_new_incumbent(self):
        self.c.ceiling = 10
        begun = asyncio.Event()
        release = asyncio.Event()
        async def blocked(candidate):
            if candidate.positions[0][0] == 2:
                begun.set()
                await release.wait()
            return await fixture_oracle(candidate)
        self.c.oracle = blocked
        slow = asyncio.create_task(self.c.submit(self.move(2)))
        await begun.wait()
        self.assertEqual((await self.c.submit(self.move(3))).status, "committed")
        release.set()
        self.assertEqual((await slow).status, "committed")
        self.assertEqual(self.c.design.positions[0][0], 2)

    async def test_stop_invalidates_inflight_result(self):
        begun, release = asyncio.Event(), asyncio.Event()
        async def blocked(candidate):
            begun.set()
            await release.wait()
            return await fixture_oracle(candidate)
        self.c.oracle = blocked
        task = asyncio.create_task(self.c.submit(self.move()))
        await begun.wait()
        await self.c.stop()
        release.set()
        self.assertEqual((await task).reason, "stopped or invalidated epoch")
        self.assertEqual(self.c.revision, 0)

    async def test_exact_candidate_result_binding(self):
        async def wrong(candidate):
            return ThermalResult("0" * 64, -999, "wrong-hash-fixture")
        self.c.oracle = wrong
        self.assertEqual((await self.c.submit(self.move())).status, "failed")
        self.assertEqual(self.c.revision, 0)

    async def test_call_budget_and_three_attempt_limit(self):
        self.c.max_calls = 1
        self.assertEqual((await self.c.submit(self.move(5))).reason, "no verified improvement")
        self.assertEqual((await self.c.submit(self.move(3))).reason, "budget exhausted")
        self.assertEqual(self.c.calls, 1)
        self.c.max_calls = 100
        await self.c.submit(self.move(12))
        self.assertEqual((await self.c.submit(self.move(3))).reason, "attempt limit")

    async def test_reserved_cost_prevents_oversubscription(self):
        self.c.ceiling, self.c.max_cost = 100, 99
        self.assertEqual((await self.c.submit(self.move())).reason, "budget exhausted")
        self.assertEqual(self.c.calls, 0)

    async def test_unauthorized_task_cannot_reset_attempt_count(self):
        proposal = self.c.proposal("worker", self.key, "ungranted-task", "move",
                                  {"chiplet": "a", "x_mm": 1, "y_mm": 1})
        self.assertEqual((await self.c.submit(proposal)).reason, "task outside agent grant")
        self.assertEqual(self.c.calls, 0)

    async def test_concurrency_bound_and_stale_queued_recheck(self):
        self.c.ceiling = 10
        entered, release = asyncio.Event(), asyncio.Event()
        active = 0
        peak = 0
        async def blocked(candidate):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                entered.set()
            await release.wait()
            active -= 1
            return await fixture_oracle(candidate)
        self.c.oracle = blocked
        tasks = [asyncio.create_task(self.c.submit(self.move(x))) for x in [1, 2, 3]]
        await entered.wait()
        self.assertEqual(peak, 2)
        release.set()
        results = await asyncio.gather(*tasks)
        self.assertEqual(sum(r.status == "committed" for r in results), 1)
        self.assertLessEqual(peak, 2)
        self.assertEqual(self.c.reserved, 0)

    async def test_cost_overrun_preserves_incumbent_and_stops(self):
        async def costly(candidate):
            return ThermalResult(candidate.hash, 1, "NONPHYSICAL-test-fixture", cost_microdollars=2)
        self.c.oracle = costly
        self.c.ceiling = 1
        self.assertIn("cost ceiling", (await self.c.submit(self.move())).reason)
        self.assertTrue(self.c.stopped)
        self.assertEqual(self.c.revision, 0)

    async def test_changed_physics_cannot_claim_improvement(self):
        async def changed(candidate):
            return ThermalResult(candidate.hash, 1, "changed-boundary-or-material-fixture")
        self.c.oracle = changed
        self.assertEqual((await self.c.submit(self.move())).status, "failed")
        self.assertEqual(self.c.revision, 0)

    async def test_provider_failure_falls_back_without_commit_authority(self):
        async def bad(request):
            raise ConnectionError("fixture")
        async def good(request):
            return {"operation": "move", "args": {"chiplet": "a", "x_mm": 1, "y_mm": 1}}
        advice = await choose_advisory_operation([("bad", bad), ("fallback", good)], {})
        self.assertEqual(advice["provider_id"], "fallback")
        self.assertEqual(len(advice["prior_failures"]), 1)
        self.assertEqual(self.c.revision, 0)

    async def test_receipt_tampering_and_forged_signature(self):
        await self.c.submit(self.move())
        self.assertFalse(FlightRecord.verify(self.c.log.events, self.c.log.public_key))
        self.c.log.close()
        events = copy.deepcopy(self.c.log.events)
        self.assertTrue(FlightRecord.verify(events, self.c.log.public_key))
        events[-1]["payload"]["temperature_c"] = -999
        self.assertFalse(FlightRecord.verify(events, self.c.log.public_key))
        self.assertFalse(FlightRecord.verify(self.c.log.events, FlightRecord().public_key))

    async def test_expiry_and_redaction(self):
        self.assertEqual((await self.c.submit(self.move(ttl=-1))).reason, "expired proposal")
        self.c.log.append("redaction_test", api_key="private", nested={"authorization": "Bearer private"},
                          input_tokens=12, output_tokens=3)
        payload = self.c.log.events[-1]["payload"]
        self.assertEqual(payload["api_key"], "[REDACTED]")
        self.assertEqual(payload["nested"]["authorization"], "[REDACTED]")
        self.assertEqual(payload["input_tokens"], 12)
        self.assertEqual(payload["output_tokens"], 3)

    async def test_jev_disabled_without_network(self):
        with patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "0"}):
            result = await JevRoutingAdapter().route({"task": "fixture"})
        self.assertFalse(result["provider_called"])
        self.assertIsNone(result["route"])
        self.assertRegex(result["input_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["output_hash"], r"^[0-9a-f]{64}$")

    async def test_jev_configuration_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "nonnegative integer"):
            JevRoutingAdapter(max_calls=-1)
        with self.assertRaisesRegex(ValueError, "no greater than 60 seconds"):
            JevRoutingAdapter(timeout_s=61)

    async def test_jev_valid_choice_is_allowlisted_and_hashed(self):
        adapter = JevRoutingAdapter(max_calls=1, timeout_s=0.5)
        with patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "test-secret"}), \
                patch("urllib.request.urlopen", return_value=JsonHttpResponse(jev_response())) as urlopen:
            result = await adapter.route({"verified_history": [], "evaluations_remaining": 4})
        self.assertEqual(result["route"], "swap")
        self.assertTrue(result["model_validated"])
        self.assertTrue(result["provider_called"])
        self.assertEqual(result["input_tokens"], 12)
        self.assertEqual(result["output_tokens"], 3)
        self.assertEqual(result["retry_count"], 0)
        self.assertEqual(set(result["probabilities"]), JevRoutingAdapter.routes)
        self.assertEqual(sum(result["probabilities"].values()), 1.0)
        self.assertRegex(result["input_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["output_hash"], r"^[0-9a-f]{64}$")
        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data)["model"], "jev-1.13.0")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertNotIn(b"test-secret", request.data)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 0.5)
        self.assertNotIn("test-secret", repr(result))
        self.assertNotIn("jev-1.13.0", repr(result))

    async def test_jev_rejects_bad_probabilities_and_wrong_model(self):
        malformed = {"local_move": True, "swap": 0.0, "global_resample": 0.0, "stop": 0.0}
        responses = (jev_response(probabilities=malformed), jev_response(model="jev-9.9.9"))
        for body in responses:
            with self.subTest(body=body), \
                    patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "test-secret"}), \
                    patch("urllib.request.urlopen", return_value=JsonHttpResponse(body)):
                result = await JevRoutingAdapter(max_calls=1).route({"verified_history": []})
                self.assertIsNone(result["route"])
                self.assertTrue(result["provider_called"])
                self.assertEqual(result["error_type"], "ValueError")
                self.assertRegex(result["output_hash"], r"^[0-9a-f]{64}$")

    async def test_jev_retries_once_for_429_and_529(self):
        for status in (429, 529):
            with self.subTest(status=status), \
                    patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "test-secret"}), \
                    patch("urllib.request.urlopen", side_effect=[
                        urllib.error.HTTPError("https://api.typesafe.ai/v1/systemone", status,
                                               "retryable", {}, None),
                        JsonHttpResponse(jev_response("global_resample"))]) as urlopen, \
                    patch("time.sleep"):
                adapter = JevRoutingAdapter(max_calls=1, timeout_s=0.5)
                result = await adapter.route({"verified_history": [], "evaluations_remaining": 2})
                self.assertEqual(result["route"], "global_resample")
                self.assertEqual(result["retry_count"], 1)
                self.assertEqual(adapter.calls, 1)  # retries do not evade the logical call cap
                self.assertEqual(urlopen.call_count, 2)

        repeated_429 = [
            urllib.error.HTTPError("https://api.typesafe.ai/v1/systemone", 429, "rate", {}, None),
            urllib.error.HTTPError("https://api.typesafe.ai/v1/systemone", 429, "rate", {}, None),
        ]
        with patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "test-secret"}), \
                patch("urllib.request.urlopen", side_effect=repeated_429) as urlopen, \
                patch("time.sleep"):
            adapter = JevRoutingAdapter(max_calls=1, timeout_s=0.5)
            result = await adapter.route({"verified_history": []})
            self.assertIsNone(result["route"])
            self.assertEqual(result["retry_count"], 1)
            self.assertEqual(urlopen.call_count, 2)

    async def test_jev_timeout_and_oversized_body_fail_closed(self):
        for side_effect in (TimeoutError("private transport detail"), JsonHttpResponse(b"x" * 262145)):
            with self.subTest(type=type(side_effect).__name__), \
                    patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "test-secret"}), \
                    patch("urllib.request.urlopen", side_effect=side_effect):
                result = await JevRoutingAdapter(max_calls=1, timeout_s=0.05).route({"verified_history": []})
                self.assertIsNone(result["route"])
                self.assertTrue(result["provider_called"])
                self.assertRegex(result["input_hash"], r"^[0-9a-f]{64}$")
                self.assertRegex(result["output_hash"], r"^[0-9a-f]{64}$")
                self.assertNotIn("private transport detail", repr(result))

    async def test_jev_call_cap_and_state_size_are_bounded(self):
        with patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "test-secret"}), \
                patch("urllib.request.urlopen", return_value=JsonHttpResponse(jev_response())) as urlopen:
            adapter = JevRoutingAdapter(max_calls=1)
            first = await adapter.route({"verified_history": []})
            second = await adapter.route({"verified_history": []})
            oversized = await adapter.route({"history": "x" * 51000})
        self.assertEqual(first["route"], "swap")
        self.assertEqual(second["reason"], "call budget exhausted; deterministic fallback")
        self.assertFalse(second["provider_called"])
        self.assertEqual(oversized["reason"], "bounded state exceeded")
        self.assertEqual(urlopen.call_count, 1)

    def test_design_hash_normalizes_integer_and_float_coordinates(self):
        integer_design = fixture_design()
        float_design = Design(
            20.0, 10.0, 1.0,
            (Chiplet("a", 2.0, 2.0), Chiplet("b", 2.0, 2.0)),
            ((4.0, 1.0), (12.0, 1.0)),
        )
        self.assertEqual(integer_design.hash, float_design.hash)

    def test_design_hash_normalizes_signed_zero_coordinates(self):
        negative_zero = Design(20, 10, 1, (Chiplet("a", 2, 2), Chiplet("b", 2, 2)),
                               ((-0.0, 1.0), (12.0, 1.0)))
        positive_zero = Design(20, 10, 1, (Chiplet("a", 2, 2), Chiplet("b", 2, 2)),
                               ((0.0, 1.0), (12.0, 1.0)))
        self.assertEqual(negative_zero.hash, positive_zero.hash)

    def test_source_hash_normalizes_all_newline_conventions(self):
        self.assertEqual(normalized_source_sha256(b"alpha\r\nbeta\r"),
                         normalized_source_sha256(b"alpha\nbeta\n"))

    def test_full_layout_place_checks_catalog_and_geometry(self):
        placed = fixture_design().apply("place", {"positions": {"a": [0, 0], "b": [9, 1]}})
        self.assertEqual(placed.positions, ((0.0, 0.0), (9.0, 1.0)))
        tuple_placed = fixture_design().apply("place", {"positions": ((0, 0), (9, 1))})
        self.assertEqual(tuple_placed.positions, ((0.0, 0.0), (9.0, 1.0)))
        with self.assertRaises(ValueError):
            fixture_design().apply("place", {"positions": {"a": [0, 0]}})
        with self.assertRaises(ValueError):
            fixture_design().apply("place", {"positions": [[0, 0], [2, 1]]})

    def test_full_layout_place_rejects_malformed_coordinate_pairs(self):
        malformed_positions = (
            ({"a": "11", "b": [9, 1]}, "place coordinates must be two-element lists or tuples"),
            ({"a": b"11", "b": [9, 1]}, "place coordinates must be two-element lists or tuples"),
            ({"a": [1.0], "b": [9, 1]}, "place coordinates must be two-element lists or tuples"),
            ({"a": [1.0, 2.0, 3.0], "b": [9, 1]}, "place coordinates must be two-element lists or tuples"),
            ({"a": (True, 1.0), "b": [9, 1]}, "place coordinates must be real numbers"),
            ({"a": ["1", "2"], "b": [9, 1]}, "place coordinates must be real numbers"),
            ({"a": [b"1", 2], "b": [9, 1]}, "place coordinates must be real numbers"),
            ({"a": [1j, 1], "b": [9, 1]}, "place coordinates must be real numbers"),
            ({"a": [float("inf"), 1], "b": [9, 1]}, "place coordinates must be finite real numbers"),
            ({"a": [float("nan"), 1], "b": [9, 1]}, "place coordinates must be finite real numbers"),
            ({"a": [10 ** 1000, 1], "b": [9, 1]}, "place coordinates must be finite real numbers"),
            ([[0, 0]], "place must specify one coordinate pair per chiplet"),
            ({"a": [0, 0], "b": [9, 1], "extra": [1, 1]},
             "place must specify every chiplet exactly once"),
        )
        for positions, reason in malformed_positions:
            with self.subTest(positions=positions):
                with self.assertRaisesRegex(ValueError, reason):
                    fixture_design().apply("place", {"positions": positions})

    async def test_string_place_coordinates_are_rejected_before_oracle_or_commit(self):
        initial_hash = self.c.design.hash
        proposal = self.c.proposal("worker", self.key, "move-a", "place",
                                   {"positions": {"a": "11", "b": "91"}})

        result = await self.c.submit(proposal)

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason, "place coordinates must be two-element lists or tuples")
        self.assertEqual(self.c.design.hash, initial_hash)
        self.assertEqual(self.c.revision, 0)
        self.assertEqual(self.c.actual_oracle_calls, 0)
        self.assertEqual(self.c.calls, 0)

    async def test_move_coordinates_reject_coercible_and_nonfinite_values_before_oracle(self):
        initial = Design(30, 20, 1, (Chiplet("a", 3, 3), Chiplet("b", 2, 4)),
                         ((10, 8), (18, 8)))
        controller = Controller(initial, fixture_oracle, evaluation_ceiling_microdollars=10)
        cases = (
            ("12", "move coordinates must be real numbers"),
            (True, "move coordinates must be real numbers"),
            (b"1", "move coordinates must be real numbers"),
            (float("inf"), "move coordinates must be finite real numbers"),
            (float("nan"), "move coordinates must be finite real numbers"),
            (10 ** 1000, "move coordinates must be finite real numbers"),
        )
        for x, reason in cases:
            with self.subTest(direct_x=x):
                with self.assertRaisesRegex(ValueError, reason):
                    initial.apply("move", {"chiplet": "a", "x_mm": x, "y_mm": 8})

        serializable_cases = cases[:2]
        task_ids = tuple(f"move-{index}" for index in range(len(serializable_cases)))
        controller.register("worker", self.key, allowed_tasks=task_ids)
        await controller.initialize()
        initial_hash = controller.design.hash

        for index, (x, reason) in enumerate(serializable_cases):
            with self.subTest(x=x):
                proposal = controller.proposal("worker", self.key, task_ids[index], "move",
                                               {"chiplet": "a", "x_mm": x, "y_mm": 8})

                result = await controller.submit(proposal)

                self.assertEqual(result.status, "rejected")
                self.assertEqual(result.reason, reason)
                self.assertEqual(controller.design.hash, initial_hash)
                self.assertEqual(controller.revision, 0)
                self.assertEqual(controller.actual_oracle_calls, 0)
                self.assertEqual(controller.calls, 0)
                self.assertEqual(controller.reserved, 0)

    async def test_host_minted_task_is_single_step(self):
        task_id = self.c.mint_task("worker")
        first = self.c.proposal("worker", self.key, task_id, "move",
                                {"chiplet": "a", "x_mm": 3, "y_mm": 1})
        self.assertEqual((await self.c.submit(first)).status, "committed")
        second = self.c.proposal("worker", self.key, task_id, "move",
                                 {"chiplet": "a", "x_mm": 2, "y_mm": 1})
        self.assertEqual((await self.c.submit(second)).reason, "host task already consumed")

    async def test_annealing_walk_through_controller_accepts_verified_uphill_parent(self):
        controller = Controller(fixture_design(), fixture_oracle, lane_ids=("annealing", "ucb1"),
                                 evaluation_ceiling_microdollars=10)
        controller.register("worker", self.key, allowed_tasks=("move-a",))
        await controller.initialize()
        baseline = controller.design
        uphill = controller.proposal("worker", self.key, "move-a", "move",
                                     {"chiplet": "a", "x_mm": 5, "y_mm": 1}, lane_id="annealing")
        # Annealing can explore a verified worse state without replacing the lane best.
        uphill_candidate = baseline.apply("move", uphill.payload["args"])
        uphill_result = await controller.submit(uphill)
        self.assertEqual(uphill_result.reason, "no verified improvement")
        baseline_temperature = controller.lane_best["annealing"][1]
        self.assertGreater(uphill_result.temperature_c, baseline_temperature)
        acceptance_probability = math.exp(
            -(uphill_result.temperature_c - baseline_temperature) / 10.0)
        annealing_draw = random.Random(0).random()
        self.assertGreater(acceptance_probability, annealing_draw)
        current = baseline
        if (uphill_result.temperature_c <= baseline_temperature or
                annealing_draw < acceptance_probability):
            current = uphill_candidate
        self.assertEqual(current.hash, uphill_candidate.hash)
        self.assertIn(uphill_candidate.hash, controller.verified_designs)
        self.assertEqual(controller.lane_best["annealing"][0].hash, baseline.hash)

        downhill = controller.proposal("worker", self.key, "move-a", "move",
                                       {"chiplet": "a", "x_mm": 3, "y_mm": 1}, lane_id="annealing",
                                       parent_hash=current.hash)
        self.assertEqual((await controller.submit(downhill)).status, "committed")
        verified_parent = baseline.apply("move", {"chiplet": "a", "x_mm": 3, "y_mm": 1})
        second = controller.proposal("worker", self.key, "move-a", "move",
                                     {"chiplet": "a", "x_mm": 2, "y_mm": 1}, lane_id="ucb1",
                                     parent_hash=verified_parent.hash)
        self.assertEqual((await controller.submit(second)).status, "committed")
        invented = controller.proposal("worker", self.key, "move-a", "move",
                                       {"chiplet": "a", "x_mm": 1, "y_mm": 1}, lane_id="invented")
        self.assertEqual((await controller.submit(invented)).reason, "unknown lane")

    def test_boolean_oracle_cost_is_rejected(self):
        design = fixture_design()
        result = ThermalResult(design.hash, 100.0, "NONPHYSICAL-bool-cost-fixture",
                               cost_microdollars=True)
        with self.assertRaisesRegex(ValueError, "invalid cost"):
            Controller.validate_result(result, design)

    async def test_epsilon_requires_minimum_lane_improvement(self):
        initial = fixture_design()
        async def near_tie(candidate):
            temperature = 100.0 if candidate.hash == initial.hash else 99.98
            return ThermalResult(candidate.hash, temperature, "NONPHYSICAL-epsilon-fixture")
        controller = Controller(initial, near_tie, minimum_improvement_c=0.05,
                                 evaluation_ceiling_microdollars=10)
        controller.register("worker", self.key, allowed_tasks=("move-a",))
        await controller.initialize()
        proposal = controller.proposal("worker", self.key, "move-a", "move",
                                       {"chiplet": "a", "x_mm": 3, "y_mm": 1})
        self.assertEqual((await controller.submit(proposal)).reason, "no verified improvement")
        self.assertEqual(controller.revision, 0)

    def test_evaluation_ceiling_must_be_a_positive_integer(self):
        initial = fixture_design()
        for invalid in (None, 0, -1, True, 1.5):
            with self.subTest(ceiling=invalid):
                with self.assertRaisesRegex(ValueError, "evaluation ceiling must be a positive integer"):
                    Controller(initial, fixture_oracle, evaluation_ceiling_microdollars=invalid)

    async def test_tap_legality_rejects_before_evaluation_admission_but_counts_attempt(self):
        initial = fixture_design()
        oracle = GridCheckingOracle()
        controller = Controller(initial, oracle, evaluation_ceiling_microdollars=10,
                                 max_cost_microdollars=100, max_attempts=1)
        controller.register("worker", self.key, allowed_tasks=("off-grid",))
        await controller.initialize()
        oracle.calls = 0
        proposal = controller.proposal("worker", self.key, "off-grid", "move",
                                       {"chiplet": "a", "x_mm": 2.5, "y_mm": 1})

        outcome = await controller.submit(proposal)

        self.assertEqual(outcome.status, "rejected")
        self.assertIn("off the 1 mm placement grid", outcome.reason)
        self.assertEqual(controller.attempts[("worker", "off-grid")], 1)
        self.assertEqual(controller.calls, 0)
        self.assertEqual(controller.actual_oracle_calls, 0)
        self.assertEqual(controller.spent, 0)
        self.assertEqual(controller.reserved, 0)
        self.assertEqual(oracle.calls, 0)

    async def test_oracle_exception_charges_only_the_positive_evaluation_ceiling(self):
        initial = fixture_design()

        async def times_out(candidate):
            if candidate.hash == initial.hash:
                return await fixture_oracle(candidate)
            raise TimeoutError("simulator deadline")

        controller = Controller(initial, times_out, max_cost_microdollars=100,
                                 evaluation_ceiling_microdollars=10)
        controller.register("worker", self.key, allowed_tasks=("move-a",))
        await controller.initialize()
        result = await controller.submit(controller.proposal(
            "worker", self.key, "move-a", "move", {"chiplet": "a", "x_mm": 3, "y_mm": 1}))

        self.assertEqual(result.status, "failed")
        self.assertEqual(controller.spent, 10)
        self.assertEqual(controller.reserved, 0)
        self.assertFalse(controller.stopped)
        self.assertEqual(controller.log.events[-1]["payload"]["error_type"], "TimeoutError")

    async def test_bound_lane_rejects_another_agents_signed_proposal(self):
        controller = Controller(fixture_design(), fixture_oracle, lane_ids=("random", "annealing"),
                                 evaluation_ceiling_microdollars=10)
        random_key = Ed25519PrivateKey.generate()
        annealing_key = Ed25519PrivateKey.generate()
        controller.register("random-agent", random_key, allowed_tasks=("random-task",))
        controller.register("annealing-agent", annealing_key, allowed_tasks=("annealing-task",))
        controller.bind_lane("random", "random-agent")
        controller.bind_lane("annealing", "annealing-agent")
        await controller.initialize()

        cross_lane = controller.proposal("annealing-agent", annealing_key, "annealing-task", "move",
                                         {"chiplet": "a", "x_mm": 3, "y_mm": 1}, lane_id="random")
        result = await controller.submit(cross_lane)

        self.assertEqual(result.reason, "agent not bound to lane")
        self.assertNotIn(("annealing-agent", "annealing-task"), controller.attempts)
        self.assertEqual(controller.calls, 0)
        self.assertEqual(controller.spent, 0)

    async def test_cancel_while_waiting_for_slot_releases_reservation(self):
        begun, release = asyncio.Event(), asyncio.Event()
        async def blocked(candidate):
            begun.set()
            await release.wait()
            return await fixture_oracle(candidate)
        controller = Controller(fixture_design(), fixture_oracle, evaluation_ceiling_microdollars=10,
                                 max_concurrency=1)
        controller.register("worker", self.key, allowed_tasks=("move-a",))
        await controller.initialize()
        controller.oracle = blocked
        first = asyncio.create_task(controller.submit(controller.proposal(
            "worker", self.key, "move-a", "move", {"chiplet": "a", "x_mm": 3, "y_mm": 1})))
        await begun.wait()
        second = asyncio.create_task(controller.submit(controller.proposal(
            "worker", self.key, "move-a", "move", {"chiplet": "a", "x_mm": 2, "y_mm": 1})))
        for _ in range(10):
            if controller.calls == 2:
                break
            await asyncio.sleep(0)
        self.assertEqual(controller.calls, 2)
        second.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await second
        self.assertEqual(controller.reserved, 10)
        self.assertEqual(controller.spent, 0)
        event = controller.log.events[-1]
        self.assertEqual(event["event"], "proposal_cancelled")
        self.assertTrue(event["payload"]["final"])
        self.assertFalse(event["payload"]["oracle_started"])
        release.set()
        await first

    async def test_cancel_during_bounded_oracle_charges_one_ceiling(self):
        initial = fixture_design()
        begun = asyncio.Event()
        async def blocked(candidate):
            if candidate.hash != initial.hash:
                begun.set()
                await asyncio.Event().wait()
            return await fixture_oracle(candidate)
        controller = Controller(initial, blocked, max_cost_microdollars=50,
                                 evaluation_ceiling_microdollars=50)
        controller.register("worker", self.key, allowed_tasks=("move-a",))
        await controller.initialize()
        task = asyncio.create_task(controller.submit(controller.proposal(
            "worker", self.key, "move-a", "move", {"chiplet": "a", "x_mm": 3, "y_mm": 1})))
        await begun.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(controller.spent, 50)
        self.assertFalse(controller.stopped)
        event = controller.log.events[-1]
        self.assertEqual(event["event"], "proposal_cancelled")
        self.assertTrue(event["payload"]["final"])
        self.assertTrue(event["payload"]["oracle_started"])
        self.assertTrue(event["payload"]["uncertain_cost"])

    async def test_non_dictionary_proposal_payload_is_rejected_cleanly(self):
        outcome = await self.c.submit(Proposal(["not", "a", "mapping"], "unused"))
        self.assertEqual(outcome.reason, "malformed proposal")

    async def test_non_thermal_oracle_result_fails_with_safe_accounting(self):
        async def malformed(candidate):
            return {"candidate_hash": candidate.hash}
        self.c.ceiling = 10
        self.c.oracle = malformed
        outcome = await self.c.submit(self.move())
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(self.c.log.events[-1]["payload"]["error_type"], "ValueError")
        self.assertEqual(self.c.reserved, 0)
        self.assertEqual(self.c.spent, 10)

    async def test_epsilon_accepts_exact_minimum_improvement(self):
        initial = fixture_design()
        async def exact_threshold(candidate):
            temperature = 100.0 if candidate.hash == initial.hash else 99.875
            return ThermalResult(candidate.hash, temperature, "NONPHYSICAL-epsilon-boundary")
        controller = Controller(initial, exact_threshold, minimum_improvement_c=0.125,
                                 evaluation_ceiling_microdollars=10)
        controller.register("worker", self.key, allowed_tasks=("move-a",))
        await controller.initialize()
        proposal = controller.proposal("worker", self.key, "move-a", "move",
                                       {"chiplet": "a", "x_mm": 3, "y_mm": 1})
        self.assertEqual((await controller.submit(proposal)).status, "committed")

    async def test_zero_epsilon_still_rejects_a_tie(self):
        initial = fixture_design()
        async def tie(candidate):
            return ThermalResult(candidate.hash, 100.0, "NONPHYSICAL-epsilon-tie")
        controller = Controller(initial, tie, minimum_improvement_c=0,
                                 evaluation_ceiling_microdollars=10)
        controller.register("worker", self.key, allowed_tasks=("move-a",))
        await controller.initialize()
        proposal = controller.proposal("worker", self.key, "move-a", "move",
                                       {"chiplet": "a", "x_mm": 3, "y_mm": 1})
        self.assertEqual((await controller.submit(proposal)).reason, "no verified improvement")
        self.assertEqual(controller.revision, 0)

    def test_empty_and_open_flight_records_cannot_be_verified_or_closed(self):
        empty = FlightRecord()
        self.assertFalse(FlightRecord.verify([], empty.public_key))
        with self.assertRaises(RuntimeError):
            empty.close()
        record = FlightRecord()
        record.append("baseline", temperature_c=100)
        self.assertFalse(FlightRecord.verify(record.events, record.public_key))
        record.close()
        with self.assertRaises(RuntimeError):
            record.append("after_close")
        self.assertTrue(FlightRecord.verify(record.events, record.public_key))
        self.assertFalse(FlightRecord.verify(record.events[:-1], record.public_key))


if __name__ == "__main__":
    unittest.main(verbosity=2)
