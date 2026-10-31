"""Allocation invariants: no thermal solver is executed by this suite."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.ci_allocation import Identity, Ledger, RefAdmission, CPUAccount, RefConflict


IDENTITY = Identity('example/repo', '123', '1', 'container', {}, 'a' * 40, 'b' * 40)


class LedgerTests(unittest.TestCase):
    def test_reservation_precedes_launch_and_all_terminal_states_consume_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / 'events.jsonl', IDENTITY)
            for state in ('success', 'failure', 'timeout', 'killed', 'launch_error'):
                slot = ledger.reserve('fake-binary')
                self.assertEqual(ledger.events()[-1]['event'], 'reserved')
                ledger.settle(slot, state, 0 if state == 'success' else 1)
            self.assertEqual(ledger.summary()['launches_reserved'], 5)
            self.assertEqual(ledger.summary()['launches_settled'], 5)

    def test_launch_101_is_refused_even_after_successful_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / 'events.jsonl', IDENTITY)
            for _ in range(100):
                slot = ledger.reserve('fake-binary')
                ledger.settle(slot, 'success', 0)
            with self.assertRaisesRegex(RuntimeError, 'launch cap'):
                ledger.reserve('fake-binary')
            self.assertEqual(ledger.summary()['launches_reserved'], 100)

    def test_finalize_settles_orphans_and_binds_both_shas(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / 'events.jsonl', IDENTITY)
            ledger.reserve('fake-binary')
            ledger.finish('cancelled', {'cpu_seconds': 12.5, 'measurement': 'cgroup-v2'})
            data = ledger.summary()
            self.assertEqual(data['launches_settled'], 1)
            self.assertEqual(data['identity']['head_sha'], 'a' * 40)
            self.assertEqual(data['identity']['build_sha'], 'b' * 40)
            self.assertEqual(data['cpu']['cpu_seconds'], 12.5)
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                ledger.reserve('fake-binary')


class CPUTests(unittest.TestCase):
    def test_cpu_not_wall_time_and_stop_reserve(self):
        meter = CPUAccount(100, 0, 0)
        self.assertFalse(meter.observe(100, .1, 1))
        self.assertAlmostEqual(meter.used, .1)
        self.assertTrue(meter.observe(969.9, .1, 2))
        self.assertAlmostEqual(meter.used, 870)

    def test_meter_failure_regression_or_observation_gap_fails_closed(self):
        for usage, monitor, clock in ((99, 0, 1), (100, 0, 3), (float('nan'), 0, 1)):
            with self.subTest(usage=usage, clock=clock):
                with self.assertRaises(RuntimeError):
                    CPUAccount(100, 0, 0).observe(usage, monitor, clock)


class FakeRefs:
    def __init__(self):
        self.refs = {}
        self.bootstrap = {'allocation_id': '56314', 'historical_runs_debit': 2,
                          'historical_consumption': 'unknown; conservative owner debit'}

    def read_bootstrap(self):
        if self.bootstrap is None:
            raise RuntimeError('missing bootstrap')
        return self.bootstrap

    def read_slots(self):
        return dict(self.refs)

    def claim(self, slot, identity):
        if slot in self.refs:
            raise RefConflict()
        self.refs[slot] = identity


class AdmissionTests(unittest.TestCase):
    def test_expiry_cap_and_missing_counter_fail_closed(self):
        store = FakeRefs()
        admit = RefAdmission(store)
        receipt = admit.admit(IDENTITY, now=1793448000)
        self.assertEqual(receipt['slot'], 3)
        for args in ((IDENTITY, 1793556000),):
            with self.assertRaisesRegex(RuntimeError, 'expired'):
                admit.admit(args[0], now=args[1])
        store.bootstrap = None
        with self.assertRaises(RuntimeError):
            admit.admit(IDENTITY, now=1793448000)

    def test_global_slot_200_and_rerun_rejection(self):
        store = FakeRefs()
        store.bootstrap['historical_runs_debit'] = 199
        self.assertEqual(RefAdmission(store).admit(IDENTITY, now=1793448000)['slot'], 200)
        second = Identity('example/repo', '124', '1', 'container', {}, 'a' * 40, 'b' * 40)
        with self.assertRaisesRegex(RuntimeError, 'run cap'):
            RefAdmission(store).admit(second, now=1793448000)
        rerun = Identity('example/repo', '123', '2', 'container', {}, 'a' * 40, 'b' * 40)
        with self.assertRaisesRegex(RuntimeError, 'attempt'):
            RefAdmission(FakeRefs()).admit(rerun, now=1793448000)


if __name__ == '__main__':
    unittest.main()


class MoreAdmissionTests(unittest.TestCase):
    def test_contention_is_retried_without_overbooking(self):
        store = FakeRefs()
        original = store.claim
        calls = []
        def race(slot, identity):
            calls.append(slot)
            if len(calls) == 1:
                other = dict(identity, run_id='999')
                original(slot, other)
                raise RefConflict()
            original(slot, identity)
        store.claim = race
        self.assertEqual(RefAdmission(store).admit(IDENTITY, now=1793448000)['slot'], 4)
        self.assertEqual(calls, [3, 4])

    def test_lost_reply_and_duplicate_run_do_not_reset_budget(self):
        store = FakeRefs()
        RefAdmission(store).admit(IDENTITY, now=1793448000)
        with self.assertRaisesRegex(RuntimeError, 'already admitted'):
            RefAdmission(store).admit(IDENTITY, now=1793448000)
        self.assertEqual(len(store.refs), 1)

    def test_invalid_bootstrap_or_slots_are_not_an_empty_counter(self):
        for debit in (-1, 201, True, '0'):
            store = FakeRefs()
            store.bootstrap['historical_runs_debit'] = debit
            with self.subTest(debit=debit), self.assertRaises(RuntimeError):
                RefAdmission(store).admit(IDENTITY, now=1793448000)
        store = FakeRefs()
        store.refs[201] = {}
        with self.assertRaises(RuntimeError):
            RefAdmission(store).admit(IDENTITY, now=1793448000)


class MoreLedgerTests(unittest.TestCase):
    def test_parallel_reservations_share_one_cap(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            Ledger(path, IDENTITY)
            def reserve(_):
                try:
                    return Ledger(path, IDENTITY).reserve('fake')
                except RuntimeError:
                    return None
            with ThreadPoolExecutor(max_workers=12) as pool:
                slots = list(pool.map(reserve, range(115)))
            self.assertEqual(len(set(slots) - {None}), 100)
            self.assertEqual(slots.count(None), 15)

    def test_corruption_identity_mismatch_and_duplicate_settlement_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            ledger = Ledger(path, IDENTITY)
            slot = ledger.reserve('fake')
            ledger.settle(slot, 'success', 0)
            with self.assertRaises(RuntimeError):
                ledger.settle(slot, 'failure', 1)
            with self.assertRaises(RuntimeError):
                ledger.settle(50, 'success', 0)
            other = Identity('example/repo', '124', '1', 'container', {}, 'a' * 40, 'b' * 40)
            with self.assertRaises(RuntimeError):
                Ledger(path, other)
            with path.open('a') as stream:
                stream.write('{')
            with self.assertRaises(RuntimeError):
                ledger.reserve('fake')
