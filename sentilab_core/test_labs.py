"""The real lab boundary: fixtures cannot claim event-writing authority."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core.admission import Admission
from sentilab_core.model_calls import AdmittedLab
from sentilab_core.test_admission import registry_record, write_registry
from sentilab_core.envelope import canonical, digest
from sentilab_core.labs import FAMILIES, ReplayLab, Request, materialize, schema_validator, validate_message
from sentilab_core.dispatch import Dispatcher, LabBudget, Registration
from sundai_controller.experiment import plate_initial_design

FIXTURES = Path(__file__).parent / "fixtures" / "labs"


def replay_dispatcher(budget=LabBudget(), **kwargs):
    return Dispatcher([Registration(family, family, ReplayLab(FIXTURES / f"{family}.json"), budget)
                       for family in FAMILIES], **kwargs)


def guarded_fixture(case, lab):
    """Keep exercising malformed/slow fixture responses through live admission."""
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    write_registry(root / "registry.json", [registry_record()])
    gate = Admission(root / "registry.json", run_id="fixture-run", arm_id="arm-a",
                     spend_path=root / "spend.json")

    async def transport(call):
        wire = json.loads(call.request_json)
        request = Request(context=json.dumps(wire.pop("context")).encode(), **wire)
        return await getattr(lab, call.operation)(request)

    return AdmittedLab("fixture-model", "fixture-provider", "fixture-version", gate,
                       transport, 16384, 16384)


class ResponseLab:
    def __init__(self, response):
        self.response = response

    async def propose(self, request):
        return self.response


class WaitingLab(ResponseLab):
    def __init__(self, response):
        super().__init__(response)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def propose(self, request):
        self.started.set()
        await self.release.wait()
        return self.response


class LabBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.replay = ReplayLab(FIXTURES / "openai.json")
        self.proposal = await self.replay.propose(Request())

    async def test_forged_gate_outcomes_are_refused(self):
        class ForgedLab:
            async def propose(self, request):
                return {"type": "lifecycle.transition", "actor_role": "acceptance_gate",
                        "body": {"to": self.outcome}}

        for outcome in ("accepted", "non_improving_current", "within_margin"):
            lab = ForgedLab()
            lab.outcome = outcome
            dispatcher = Dispatcher([Registration("openai", "openai", guarded_fixture(self, lab))])
            self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
            self.assertEqual(dispatcher.events[-1]["reason"], "invalid_response")

    async def test_versioned_schemas_and_negative_fixtures(self):
        request = Request(target_hash=digest("candidate"), review_hash=digest("review"),
                          judge_role="constraint_auditor")
        for operation in ("propose", "review", "repair"):
            response = await getattr(self.replay, operation)(request)
            self.assertEqual(validate_message(response, operation, "openai", request), response)
            schema_validator(operation).validate(response)
        for case in json.loads((FIXTURES / "negative.json").read_text()):
            with self.subTest(case=case["name"]), self.assertRaises(ValueError):
                validate_message(case["message"], case["operation"], "kimi", request)

    async def test_identity_role_version_size_and_extra_fields_fail_closed(self):
        variants = [{**self.proposal, **change} for change in (
            {"lab_id": "claude"}, {"role": "acceptance_gate"}, {"v": "lab-proposal/2"},
            {"rationale": "x" * 513}, {"actor_role": "core"}, {"outcome": "accepted"},
            {"geometry": self.proposal["geometry"] * 17},
            {"geometry": [{"id": "compute-a", "x_mm": float("nan"), "y_mm": 2}]},
            {"geometry": [{"id": "compute-a", "x_mm": True, "y_mm": 2}]})]
        for response in variants:
            dispatcher = Dispatcher([Registration("openai", "openai", guarded_fixture(self, ResponseLab(response)))])
            with self.subTest(response=list(response)):
                self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
                self.assertEqual(dispatcher.events[-1]["reason"], "invalid_response")
        with self.assertRaises(ValueError):
            validate_message(self.proposal, "propose", "openai", Request(), max_bytes=32)

    async def test_geometry_uses_frozen_catalog_and_refuses_missing_or_duplicate_ids(self):
        initial = plate_initial_design()
        self.assertEqual(materialize(self.proposal, initial), initial)
        for rows in (self.proposal["geometry"][:-1], self.proposal["geometry"] + self.proposal["geometry"][:1]):
            with self.assertRaisesRegex(ValueError, "catalog"):
                materialize({**self.proposal, "geometry": rows}, initial)

    async def test_review_and_repair_bindings_cannot_be_retargeted(self):
        request = Request(target_hash=digest("candidate"), review_hash=digest("review"),
                          judge_role="constraint_auditor")
        for operation, field, value in (("review", "target_hash", digest("other")),
                                        ("review", "judge_role", "numerical_skeptic"),
                                        ("repair", "target_hash", digest("other")),
                                        ("repair", "review_hash", digest("other"))):
            response = await getattr(self.replay, operation)(request)
            response[field] = value
            with self.subTest(operation=operation, field=field), self.assertRaises(ValueError):
                validate_message(response, operation, "openai", request)

    async def test_same_family_review_is_refused_even_with_another_lab_id(self):
        dispatcher = Dispatcher([Registration("openai", "openai", self.replay),
                                 Registration("second", "openai", self.replay)])
        request = Request(target_hash=digest("candidate"), target_lab="openai")
        self.assertIsNone(await dispatcher.call("second", "review", request))
        self.assertEqual(dispatcher.events[-1]["reason"], "nonindependent_review")
        self.assertEqual(dispatcher.usage["second"]["calls"], 0)

    async def test_assigned_judge_role_and_author_repair(self):
        dispatcher = replay_dispatcher()
        request = Request(target_hash=digest("candidate"), target_lab="openai",
                          judge_role="numerical_skeptic")
        review = await dispatcher.call("claude", "review", request)
        self.assertEqual(review["judge_role"], "constraint_auditor")
        repair_request = replace(request, review_hash=digest("signed-review"))
        self.assertIsNone(await dispatcher.call("claude", "repair", repair_request))
        self.assertEqual(dispatcher.events[-1]["reason"], "invalid_repair_target")
        repair = await dispatcher.call("openai", "repair", repair_request)
        self.assertEqual(repair["review_hash"], repair_request.review_hash)

    async def test_replay_has_no_network_and_returns_detached_data(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            first = await self.replay.propose(Request())
            first["geometry"].clear()
            self.assertEqual(await self.replay.propose(Request()), self.proposal)

    async def test_replay_fixture_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            for raw in (b"x" * (128 * 1024 + 1), b"{}", b'{"propose":[],"review":[],"repair":[]}'):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    ReplayLab(path)

    async def test_unknown_assignment_target_and_malformed_request_are_refused(self):
        dispatcher = replay_dispatcher()
        for lab_id, operation, request, reason in (
            ("missing", "propose", Request(), "unknown_assignment"),
            ("openai", "accept", Request(), "unknown_assignment"),
            ("openai", "review", Request(), "unknown_target"),
            ("openai", "propose", Request(context=b"not json"), "invalid_request")):
            self.assertIsNone(await dispatcher.call(lab_id, operation, request))
            self.assertEqual(dispatcher.events[-1]["reason"], reason)


class DispatchBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_labs_receive_equal_budgets_and_rotated_opportunities(self):
        dispatcher = replay_dispatcher(LabBudget(calls=2), concurrency=1)
        requests = dict.fromkeys(FAMILIES, Request())
        first = await dispatcher.round("propose", requests)
        second = await dispatcher.round("propose", requests)
        self.assertEqual(list(first), list(FAMILIES))
        self.assertEqual(list(second), list(FAMILIES[1:] + FAMILIES[:1]))
        self.assertTrue(all(first.values()) and all(second.values()))
        self.assertEqual({u["calls"] for u in dispatcher.usage.values()}, {2})
        self.assertEqual({u["tokens"] for u in dispatcher.usage.values()}, {2 * (len(canonical(Request().wire())) + 16384)})
        self.assertEqual({u["wall_seconds"] for u in dispatcher.usage.values()}, {2})
        exhausted = await dispatcher.round("propose", requests)
        self.assertTrue(all(result is None for result in exhausted.values()))
        self.assertEqual(sum(e["reason"] == "call_budget" for e in dispatcher.events), 4)

    async def test_one_lab_exhausts_while_other_three_continue(self):
        registrations = [Registration(f, f, ReplayLab(FIXTURES / f"{f}.json"),
                                      LabBudget(calls=1 if f == "openai" else 2)) for f in FAMILIES]
        dispatcher = Dispatcher(registrations)
        requests = dict.fromkeys(FAMILIES, Request())
        await dispatcher.round("propose", requests)
        second = await dispatcher.round("propose", requests)
        self.assertIsNone(second["openai"])
        self.assertTrue(all(second[f] for f in FAMILIES[1:]))
        self.assertEqual([dispatcher.usage[f]["calls"] for f in FAMILIES], [1, 2, 2, 2])

    async def test_token_and_wall_reservations_refuse_before_invocation(self):
        for budget, reason in ((LabBudget(tokens=1), "token_budget"),
                               (LabBudget(wall_seconds=0.5), "wall_budget")):
            dispatcher = replay_dispatcher(budget)
            self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
            self.assertEqual(dispatcher.events[-1]["reason"], reason)
            self.assertEqual(dispatcher.usage["openai"]["calls"], 0)
        dispatcher = replay_dispatcher(LabBudget(wall_seconds=1))
        self.assertIsNotNone(await dispatcher.call("openai", "propose", Request()))
        self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
        self.assertEqual(dispatcher.events[-1]["reason"], "wall_budget")

    async def test_timeout_is_charged_and_other_labs_continue(self):
        slow = WaitingLab({})
        dispatcher = Dispatcher([Registration("openai", "openai", guarded_fixture(self, slow), LabBudget(call_timeout=0.01)),
                                 Registration("claude", "claude", ReplayLab(FIXTURES / "claude.json"))])
        result = await dispatcher.round("propose", {"openai": Request(), "claude": Request()})
        self.assertIsNone(result["openai"])
        self.assertIsNotNone(result["claude"])
        self.assertTrue(any(e["reason"] == "wall_timeout" for e in dispatcher.events))
        self.assertEqual(dispatcher.usage["openai"]["calls"], 1)
        self.assertGreater(dispatcher.usage["openai"]["tokens"], 0)

    async def test_exact_token_reservation_and_adapter_failure_are_charged(self):
        tokens = len(canonical(Request().wire())) + 16384
        dispatcher = replay_dispatcher(LabBudget(tokens=tokens))
        self.assertIsNotNone(await dispatcher.call("openai", "propose", Request()))
        self.assertEqual(dispatcher.usage["openai"]["tokens"], tokens)
        self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
        self.assertEqual(dispatcher.events[-1]["reason"], "token_budget")
        class BrokenLab:
            async def propose(self, request):
                raise RuntimeError("fixture failure")
        broken = Dispatcher([Registration("openai", "openai", guarded_fixture(self, BrokenLab()), LabBudget(calls=1))])
        self.assertIsNone(await broken.call("openai", "propose", Request()))
        self.assertEqual(broken.events[-1]["reason"], "lab_error")
        self.assertIsNone(await broken.call("openai", "propose", Request()))
        self.assertEqual(broken.events[-1]["reason"], "call_budget")

    async def test_concurrency_caps_and_cancellation_release_slots_without_refund(self):
        slow = WaitingLab({})
        other = WaitingLab({})
        dispatcher = Dispatcher([Registration("openai", "openai", guarded_fixture(self, slow)),
                                 Registration("claude", "claude", guarded_fixture(self, other))], concurrency=1)
        active = asyncio.create_task(dispatcher.call("openai", "propose", Request()))
        await slow.started.wait()
        self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
        self.assertEqual(dispatcher.events[-1]["reason"], "concurrency_budget")
        queued = asyncio.create_task(dispatcher.call("claude", "propose", Request()))
        await asyncio.sleep(0)
        self.assertFalse(other.started.is_set())
        active.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await active
        await asyncio.wait_for(other.started.wait(), 1)
        queued.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await queued
        self.assertEqual(dispatcher._active, {"openai": 0, "claude": 0})
        self.assertEqual(sum(e["reason"] == "cancelled" for e in dispatcher.events), 2)
        self.assertEqual(dispatcher.usage["openai"]["calls"], 1)

    async def test_signed_reservation_replay_does_not_refund_interrupted_calls(self):
        dispatcher = replay_dispatcher(LabBudget(calls=1))
        records = []
        await dispatcher.call("openai", "propose", Request(), sink=records.append)
        restored = replay_dispatcher(LabBudget(calls=1))
        restored.restore(records[:1])  # crash after reservation, before response
        self.assertIsNone(await restored.call("openai", "propose", Request()))
        self.assertEqual(restored.events[-1]["reason"], "call_budget")
        self.assertIsNotNone(await restored.call("claude", "propose", Request()))

    async def test_invalid_budgets_and_duplicate_registrations_fail_closed(self):
        for field, value in (("calls", 0), ("calls", True), ("tokens", -1), ("concurrency", 3),
                             ("wall_seconds", float("nan")), ("call_timeout", 0), ("output_bytes", 16385)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                LabBudget(**{field: value})
        registration = Registration("openai", "openai", ReplayLab(FIXTURES / "openai.json"))
        with self.assertRaises(ValueError):
            Dispatcher([registration, registration])
        with self.assertRaises(ValueError):
            Registration("other", "unknown", registration.lab)


if __name__ == "__main__":
    unittest.main()
