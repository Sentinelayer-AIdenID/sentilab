"""Drive real lead/judge entry points with an in-memory transport, never inference."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from sentilab_core.admission import Admission, NotAdmitted, OverCap
from sentilab_core.dispatch import Dispatcher, Registration
from sentilab_core.envelope import digest
from sentilab_core.labs import ReplayLab, Request
from sentilab_core.ledger import lock
from sentilab_core.model_calls import AdmittedLab
from sentilab_core.test_admission import registry_record, write_registry

FIXTURE = Path(__file__).parent / "fixtures/labs/openai.json"


class ModelCallTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.registry = self.root / "registry.json"
        write_registry(self.registry, [registry_record()])
        self.gate = Admission(self.registry, run_id="fixture-run", arm_id="arm-a",
                              spend_path=self.root / "spend.json")
        self.calls = []

    async def transport(self, call):
        self.calls.append(call)
        wire = json.loads(call.request_json)
        request = Request(context=json.dumps(wire.pop("context")).encode(), **wire)
        return await getattr(ReplayLab(FIXTURE), call.operation)(request)

    def lab(self, **changes):
        options = dict(model_id="fixture-model", provider="fixture-provider", model_version="fixture-version",
                       admission=self.gate, transport=self.transport, input_tokens=1000, output_tokens=500)
        return AdmittedLab(**{**options, **changes})

    async def test_unadmitted_lead_judge_and_repair_refuse_before_transport(self):
        write_registry(self.registry, [])
        for operation in ("propose", "review", "repair"):
            with self.subTest(operation=operation), self.assertRaises(NotAdmitted):
                await getattr(self.lab(), operation)(Request())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gate.spent()["run_usd"], "0")

    def _call_waiting_for_spend_lock(self, change, operation="propose"):
        waiting = Event()
        real_flock = fcntl.flock

        def observed_flock(handle, flags):
            if flags == fcntl.LOCK_EX:
                try:
                    return real_flock(handle, flags | fcntl.LOCK_NB)
                except BlockingIOError:
                    waiting.set()
            return real_flock(handle, flags)

        with ThreadPoolExecutor(max_workers=1) as pool:
            with lock(self.gate.lock_path):
                with patch("sentilab_core.ledger.fcntl.flock", side_effect=observed_flock):
                    future = pool.submit(asyncio.run, getattr(self.lab(), operation)(Request()))
                    self.assertTrue(waiting.wait(5), "call never contended on the real spend flock")
                    self.assertFalse(future.done())
                    change()
            error = future.exception(timeout=5)
        reservations = json.loads(self.gate.spend_path.read_text())["reservations"]
        self.assertEqual((len(reservations), len(self.calls), self.gate.spent()["run_usd"], type(error)),
                         (0, 0, "0", NotAdmitted))

    async def test_lock_wait_revocation_refuses_without_reservation_or_transport(self):
        self._call_waiting_for_spend_lock(lambda: write_registry(self.registry, []))

    async def test_lock_wait_expiry_refuses_without_reservation_or_transport(self):
        now = datetime.now(timezone.utc)
        write_registry(self.registry, [registry_record(expires_at=(now + timedelta(minutes=1)).isoformat())])
        with patch("sentilab_core.admission.datetime", wraps=datetime) as clock:
            clock.now.return_value = now + timedelta(seconds=1)
            self._call_waiting_for_spend_lock(
                lambda: setattr(clock.now, "return_value", now + timedelta(minutes=2)))

    async def test_expiry_during_accounting_refuses_before_commit(self):
        now = datetime.now(timezone.utc) + timedelta(seconds=1)
        write_registry(self.registry, [registry_record(expires_at=(now + timedelta(minutes=1)).isoformat())])
        with patch("sentilab_core.admission.datetime", wraps=datetime) as clock:
            # Quote, locked validation, then the final check after reading spend.
            clock.now.side_effect = [now, now, now + timedelta(minutes=2)]
            with self.assertRaises(NotAdmitted):
                await self.lab().propose(Request())
        self.assertEqual(json.loads(self.gate.spend_path.read_text())["reservations"], [])
        self.assertEqual(self.calls, [])

    async def test_lock_wait_quote_change_refuses_without_reservation_or_transport(self):
        self._call_waiting_for_spend_lock(lambda: write_registry(
            self.registry, [registry_record(input_usd_per_million="10")]), operation="repair")

    async def test_lock_wait_policy_changes_refuse_judge_without_reservation_or_transport(self):
        for field, value in (("roles", ["lead"]), ("provider", "other-provider"),
                             ("model_version", "other-version"), ("payer", "other-payer"),
                             ("arm_cap_usd", "0.001"), ("run_cap_usd", "1"),
                             ("entitlement_source", "other-entitlement")):
            with self.subTest(field=field):
                row = registry_record()
                write_registry(self.registry, [row])
                def change():
                    row[field] = value
                    if field in ("provider", "entitlement_source"):
                        row["probe"][field] = value
                    write_registry(self.registry, [row])
                self._call_waiting_for_spend_lock(change, operation="review")

    async def test_committed_request_can_finish_after_revocation(self):
        staged = self.root / "reviewed.json"
        write_registry(staged, [])
        async def revoke_after_commit(call):
            from sentilab_core.admission import publish_registry
            self.assertEqual(self.gate.spent()["run_usd"], "0.002")
            publish_registry(staged, registry_path=self.registry)
            return await self.transport(call)
        await self.lab(transport=revoke_after_commit).propose(Request())
        with self.assertRaises(NotAdmitted):
            await self.lab().propose(Request())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.gate.spent()["run_usd"], "0.002")

    async def test_role_provider_version_and_input_ceiling_refuse(self):
        for change in ({"provider": "other"}, {"model_version": "other"}, {"input_tokens": 1}):
            with self.subTest(change=change), self.assertRaises((NotAdmitted, OverCap)):
                await self.lab(**change).propose(Request())
        for roles, operation in ((["lead"], "review"), (["judge"], "propose"), (["judge"], "repair")):
            write_registry(self.registry, [registry_record(roles=roles)])
            with self.subTest(roles=roles, operation=operation), self.assertRaises(NotAdmitted):
                await getattr(self.lab(), operation)(Request())
        self.assertEqual(self.calls, [])

    async def test_all_roles_reserve_priced_ceiling_before_transport(self):
        async def observe(call):
            self.assertEqual(self.gate.spent()["run_usd"], str((len(self.calls) + 1) * 0.002))
            self.assertEqual((call.record.provider, call.record.model_version),
                             ("fixture-provider", "fixture-version"))
            self.assertEqual((call.input_tokens, call.output_tokens), (1000, 500))
            return await self.transport(call)
        lab = self.lab(transport=observe)
        for operation in ("propose", "review", "repair"):
            await getattr(lab, operation)(Request())
        self.assertEqual([c.role for c in self.calls], ["lead", "judge", "lead"])
        self.assertEqual(self.gate.spent()["run_usd"], "0.006")

    async def test_over_cap_and_failure_or_cancellation_never_refund(self):
        write_registry(self.registry, [registry_record(arm_cap_usd="0.002")])
        async def fail(call):
            self.calls.append(call)
            raise RuntimeError("fixture transport failure")
        with self.assertRaises(RuntimeError):
            await self.lab(transport=fail).propose(Request())
        with self.assertRaises(OverCap):
            await self.lab().review(Request())
        self.assertEqual(len(self.calls), 1)
        write_registry(self.registry, [registry_record(arm_cap_usd="0.004")])
        async def cancel(call):
            raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.lab(transport=cancel).repair(Request())
        with self.assertRaises(OverCap):
            await self.lab().propose(Request())
        self.assertEqual(self.gate.spent()["run_usd"], "0.004")

    async def test_dispatch_refuses_unguarded_adapters_and_replay_subclasses(self):
        calls = []
        class RawLab:
            async def propose(self, request):
                calls.append(request)
            review = repair = propose
        class PretendReplay(ReplayLab):
            async def propose(self, request):
                calls.append(request)
            review = repair = propose
        for lab in (RawLab(), PretendReplay(FIXTURE)):
            dispatcher = Dispatcher([Registration("openai", "openai", lab),
                                     Registration("claude", "claude", ReplayLab(FIXTURE))])
            for operation in ("propose", "review", "repair"):
                request = Request(target_hash=digest("target"), review_hash=digest("review"),
                                  target_lab="claude" if operation == "review" else "openai")
                self.assertIsNone(await dispatcher.call("openai", operation, request))
                self.assertEqual(dispatcher.events[-1]["reason"], "model_not_admitted")
        self.assertEqual(calls, [])

    async def test_dispatch_uses_guard_and_preserves_specific_refusal(self):
        dispatcher = Dispatcher([Registration("openai", "openai", self.lab())])
        write_registry(self.registry, [])
        self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
        self.assertEqual(dispatcher.events[-1]["reason"], "model_not_admitted")
        write_registry(self.registry, [registry_record(arm_cap_usd="0.002")])
        self.assertIsNotNone(await dispatcher.call("openai", "propose", Request()))
        self.assertIsNone(await dispatcher.call("openai", "propose", Request()))
        self.assertEqual(dispatcher.events[-1]["reason"], "model_cost_cap")
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
