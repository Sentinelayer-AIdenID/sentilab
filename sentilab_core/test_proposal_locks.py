"""Real flock races at the proposal authority and STOP boundaries; fixture only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import fcntl
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from sentilab_core.admission import NotAdmitted, publish_registry
from sentilab_core.envelope import verify
from sentilab_core.proposals import ProposalHarness
from sentilab_core.test_admission import registry_record, write_registry
from sentilab_core.test_ledger import RuntimeSigner
from sentilab_core.test_proposals import POSITIONS, fixture_options, prepare_registry


class ProposalLockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        signer = RuntimeSigner()
        self.keys = {signer.key_id: signer.public_key}
        prepare_registry(self.root)
        self.harness = ProposalHarness(**fixture_options(self.root, signer, self.keys))
        self.oracle = self.harness.oracles["lab-a"]

    def publish(self, records):
        reviewed = self.root / "reviewed.json"
        write_registry(reviewed, records)
        publish_registry(reviewed, registry_path=self.root / "registry.json")

    def during_wait(self, stage, action):
        """Hold a separate open file description until the real flock contends.

        The nonblocking probe proves contention; the subsequent blocking syscall
        is real. No sleeps or substituted lock implementation decide the outcome.
        """
        ledger = self.harness.ledger
        waiting, armed = Event(), Event()
        real_flock = fcntl.flock
        with open(ledger.lock_path, "a+b") as holder, ExitStack() as patches:
            def observe(handle, flags):
                if armed.is_set() and flags in (fcntl.LOCK_SH, fcntl.LOCK_EX):
                    try:
                        return real_flock(handle, flags | fcntl.LOCK_NB)
                    except BlockingIOError:
                        waiting.set()
                return real_flock(handle, flags)

            def hold():
                real_flock(holder, fcntl.LOCK_EX)
                armed.set()

            original_rows, original_append = self.harness._rows, ledger.append
            def rows(*args, **kwargs):
                hold()
                return original_rows(*args, **kwargs)

            def append(event_type, *args, **kwargs):
                if event_type == stage:
                    hold()
                result = original_append(event_type, *args, **kwargs)
                if stage == "start" and event_type == "proposal.reserved":
                    hold()
                return result

            patches.enter_context(patch("sentilab_core.ledger.fcntl.flock", side_effect=observe))
            if stage == "rows":
                patches.enter_context(patch.object(self.harness, "_rows", side_effect=rows))
            else:
                patches.enter_context(patch.object(ledger, "append", side_effect=append))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: asyncio.run(self.oracle.submit(
                    request_id="racing", positions=POSITIONS)))
                try:
                    self.assertTrue(waiting.wait(5), "proposal never contended on real flock")
                    self.assertFalse(future.done(), "proposal finished while its lock was held")
                    action()
                finally:
                    armed.clear()
                    real_flock(holder, fcntl.LOCK_UN)
                return future.result(timeout=5)

    def assert_uncharged(self):
        self.assertEqual(self.oracle.backend.calls, [])
        self.assertEqual([row["event"]["type"] for row in self.harness._events()], ["proposal.config"])

    def test_revocation_during_rows_wait_refuses_without_charge(self):
        with self.assertRaises(NotAdmitted):
            self.during_wait("rows", lambda: self.publish([]))
        self.assert_uncharged()

    def test_revocation_during_reservation_wait_refuses_without_charge(self):
        with self.assertRaises(NotAdmitted):
            self.during_wait("proposal.reserved", lambda: self.publish([]))
        self.assert_uncharged()

    def test_reservation_uses_current_provider_payer_and_policy_after_wait(self):
        old = self.harness.labs["lab-a"].check("fixture-run")
        records = [registry_record(arm_id=lab, payer="replacement-payer") for lab in ("lab-a", "lab-b")]
        for record in records:
            record["provider"] = record["probe"]["provider"] = "replacement-provider"
        receipt = self.during_wait("proposal.reserved", lambda: self.publish(records))
        current = self.harness.labs["lab-a"].check("fixture-run")
        self.assertNotEqual(old.policy_sha256, current.policy_sha256)
        body = self.harness._events()[1]["event"]["body"]
        self.assertEqual((body["provider"], body["payer"], body["admission_hash"]),
                         (current.provider, current.payer, current.policy_sha256))
        self.assertEqual(receipt["status"], "evaluated")
        self.assertEqual(len(self.oracle.backend.calls), 1)

    def test_stop_during_reservation_wait_refuses_without_charge(self):
        receipt = self.during_wait("proposal.reserved", self.harness.stop_file.touch)
        self.assertEqual(receipt, {"schema": "sentilab-proposal/1", "status": "refused",
                                  "error": {"code": "stopped"}})
        self.assert_uncharged()

    def test_stop_during_finish_wait_signs_stopped_and_keeps_charge(self):
        # A prior genuine adapter failure and its charge must remain byte exact.
        async def fail(*args, **kwargs):
            raise RuntimeError("fixture failure")
        with patch.object(self.oracle.backend, "evaluate", side_effect=fail):
            failed = asyncio.run(self.oracle.submit(request_id="failed", positions=POSITIONS))
        self.assertEqual(failed["status"], "oracle_error")
        prefix = self.harness.ledger.path.read_bytes()
        receipt = self.during_wait("proposal.finished", self.harness.stop_file.touch)
        self.assertEqual(receipt["status"], "stopped")
        self.assertNotIn("J", receipt)
        self.assertNotIn("wire_mm", receipt)
        rows = self.harness._events()
        self.assertEqual([row["event"]["type"] for row in rows],
                         ["proposal.config", "proposal.reserved", "proposal.finished",
                          "proposal.reserved", "proposal.finished"])
        self.assertTrue(self.harness.ledger.path.read_bytes().startswith(prefix))
        self.assertEqual(rows[2]["event"]["body"]["receipt"], failed)
        for row in rows:
            verify(row, run_id="fixture-run", public_keys=self.keys)
        self.assertEqual(rows[-1]["event"]["body"]["receipt"], receipt)
        self.assertEqual(receipt["reservation_hash"], rows[3]["hash"])
        self.assertEqual(receipt["slot"], 2)
        self.assertTrue(receipt["charged"])
        self.assertEqual(len(self.oracle.backend.calls), 1)
        # STOP must not reinterpret an already signed result on replay.
        self.assertEqual(asyncio.run(self.oracle.submit(request_id="failed", positions=POSITIONS)), failed)

    def assert_start_refused(self, action, status):
        receipt = self.during_wait("start", action)
        self.assertEqual(receipt["status"], status)
        self.assertTrue(receipt["charged"])
        self.assertEqual(self.oracle.backend.calls, [])
        rows = self.harness._events()
        self.assertEqual([row["event"]["type"] for row in rows],
                         ["proposal.config", "proposal.reserved", "proposal.finished"])
        self.assertEqual(receipt["reservation_hash"], rows[1]["hash"])
        self.assertEqual(rows[-1]["event"]["body"]["receipt"], receipt)
        for row in rows:
            verify(row, run_id="fixture-run", public_keys=self.keys)

    def test_revocation_during_start_wait_keeps_prior_charge_without_call(self):
        self.assert_start_refused(lambda: self.publish([]), "admission_revoked")

    def test_changed_provider_payer_during_start_wait_keeps_original_reservation(self):
        old = self.harness.labs["lab-a"].check("fixture-run")
        records = [registry_record(arm_id=lab, payer="replacement-payer") for lab in ("lab-a", "lab-b")]
        for record in records:
            record["provider"] = record["probe"]["provider"] = "replacement-provider"
        self.assert_start_refused(lambda: self.publish(records), "admission_revoked")
        body = self.harness._events()[1]["event"]["body"]
        self.assertEqual((body["provider"], body["payer"], body["admission_hash"]),
                         (old.provider, old.payer, old.policy_sha256))

    def test_stop_during_start_wait_keeps_prior_charge_without_call(self):
        self.assert_start_refused(self.harness.stop_file.touch, "stopped")

    def test_publication_waits_through_signed_reservation(self):
        ledger = self.harness.ledger
        committing, release, waiting = Event(), Event(), Event()
        real_append, real_flock = ledger._append, fcntl.flock
        old = self.harness.labs["lab-a"].check("fixture-run")

        def append(state, event_type, *args, **kwargs):
            if event_type == "proposal.reserved":
                committing.set()
                if not release.wait(5):
                    raise RuntimeError("test did not release reservation commit")
            return real_append(state, event_type, *args, **kwargs)

        def observe(handle, flags):
            if flags == fcntl.LOCK_EX:
                try:
                    return real_flock(handle, flags | fcntl.LOCK_NB)
                except BlockingIOError:
                    waiting.set()
            return real_flock(handle, flags)

        with patch.object(ledger, "_append", side_effect=append), \
                patch("sentilab_core.ledger.fcntl.flock", side_effect=observe), \
                ThreadPoolExecutor(max_workers=2) as pool:
            reserve = pool.submit(lambda: asyncio.run(self.oracle.submit(
                request_id="racing", positions=POSITIONS)))
            try:
                self.assertTrue(committing.wait(5))
                publish = pool.submit(self.publish, [])
                self.assertTrue(waiting.wait(2), "publication never contended on real flock")
                self.assertFalse(publish.done())
                self.assertEqual(self.harness.labs["lab-a"].check("fixture-run"), old)
            finally:
                release.set()
            reserve.result(timeout=5)
            publish.result(timeout=5)
        body = self.harness._events()[1]["event"]["body"]
        self.assertEqual(body["admission_hash"], old.policy_sha256)
        with self.assertRaises(NotAdmitted):
            self.harness.labs["lab-a"].check("fixture-run")


if __name__ == "__main__":
    unittest.main()
