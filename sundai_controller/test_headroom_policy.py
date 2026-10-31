"""Approved operating bounds, using synthetic charges and cgroup files only."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sundai_controller import headroom as h
from sundai_controller import headroom_supervisor as s

EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/SLAB-039'


class PolicyTests(unittest.TestCase):
    def test_approval_without_measured_latency_cannot_start_worker(self):
        declaration = {'status': 'approved', 'approved_by': 'synthetic-test-only',
                       'accept_unbounded_scheduler_and_cleanup_risk': True,
                       'limits': asdict(s.Policy())}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / 'policy.json'
            policy.write_text(json.dumps(declaration))
            budget = root / 'SPEND.json'
            original = (EVIDENCE / 'SPEND.json').read_bytes()
            budget.write_bytes(original)
            with patch.object(s.LinuxTree, 'start') as start, \
                    patch.object(s, 'supervise', return_value={
                        'status': 'completed', 'returncode': 0, 'metered_cpu_seconds': .1,
                        'latency_assumptions_met': True}):
                with self.assertRaisesRegex(RuntimeError, 'measured observation-plus-kill'):
                    s.run(EVIDENCE / 'PREREG-v4.json', budget, root / 'out', policy)
            start.assert_not_called()
            self.assertEqual(budget.read_bytes(), original)

    def test_measured_h_is_twice_observation_plus_kill_times_q(self):
        for q in (1, 2, 8):
            policy = s.Policy(rate_q=q, measured_observation_plus_kill_seconds=.8)
            self.assertEqual(policy.reserve, 2 * .8 * q)
        for value in (0, -1, float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                s.Policy(measured_observation_plus_kill_seconds=value)

    def test_measured_h_drives_supervisor_stop_before_remaining_allowance(self):
        from sundai_controller.test_headroom_supervisor import FakeTree
        policy = s.Policy(rate_q=2, measured_observation_plus_kill_seconds=.8)
        tree = FakeTree(2, [20], kill_reap=.2)
        receipt = s.supervise(lambda: None, allowance=10, policy=policy,
                              backend=tree, clock=tree.clock, sleep=tree.sleep)
        self.assertEqual(receipt['status'], 'stopped')
        self.assertLessEqual(tree.kill_at * 2, 10 - policy.reserve + .02)
        self.assertLessEqual(receipt['metered_cpu_seconds'] + .25, 10)

    def test_measured_reserve_must_cover_declared_tail_and_latency_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            for latency, evidence in ((.6, ''), (.001, 'synthetic-test-only')):
                path.write_text(json.dumps({
                    'limits': asdict(s.Policy(measured_observation_plus_kill_seconds=latency)),
                    'status': 'approved', 'approved_by': 'synthetic-test-only',
                    'accept_unbounded_scheduler_and_cleanup_risk': True,
                    'latency_measurement_evidence': evidence}))
                with self.subTest(latency=latency), self.assertRaises((RuntimeError, ValueError)):
                    s.load_policy(path)

    def test_container_cpu_max_must_equal_q(self):
        for q in (1, 2, 8):
            for value in (f'{q * 100000} 100000', 'max 100000',
                          f'{(q + 1) * 100000} 100000', '1 0', 'invalid'):
                def read(path):
                    if str(path) == '/proc/self/cgroup':
                        return '0::/synthetic-allocation\n'
                    self.assertEqual(str(path), '/sys/fs/cgroup/synthetic-allocation/cpu.max')
                    return value
                with self.subTest(q=q, value=value), patch.object(Path, 'read_text', read):
                    if value == f'{q * 100000} 100000':
                        cap = s.verify_cpu_max(s.Policy(rate_q=q))
                        self.assertEqual(cap['value'], value)
                        self.assertEqual(cap['rate_q'], q)
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'cpu.max must equal Q'):
                            s.verify_cpu_max(s.Policy(rate_q=q))

    def test_missing_or_escaping_cgroup_refuses_rate_cap(self):
        for membership in ('1:cpu:/legacy', '0::/../../outside', '0::/\n0::/duplicate'):
            with self.subTest(membership=membership), \
                    patch.object(Path, 'read_text', return_value=membership), \
                    self.assertRaises(RuntimeError):
                s.verify_cpu_max(s.Policy())

    def test_run_refuses_mismatched_container_rate_before_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = root / 'policy.json'
            policy.write_text(json.dumps({
                'status': 'approved', 'approved_by': 'synthetic-test-only',
                'accept_unbounded_scheduler_and_cleanup_risk': True,
                'latency_measurement_evidence': 'synthetic-test-only',
                'limits': asdict(s.Policy(measured_observation_plus_kill_seconds=.6))}))
            budget = root / 'SPEND.json'
            original = (EVIDENCE / 'SPEND.json').read_bytes()
            budget.write_bytes(original)
            read_text = Path.read_text
            def read(path):
                if str(path) == '/proc/self/cgroup':
                    return '0::/'
                if str(path) == '/sys/fs/cgroup/cpu.max':
                    return '200000 100000'  # Q=2 cap cannot admit a Q=1 policy.
                return read_text(path)
            with patch.object(Path, 'read_text', read), patch.object(s, 'supervise') as launch:
                with self.assertRaisesRegex(RuntimeError, 'cpu.max must equal Q'):
                    s.run(EVIDENCE / 'PREREG-v4.json', budget, root / 'out', policy)
            launch.assert_not_called()
            self.assertEqual(budget.read_bytes(), original)

    def test_overshoot_exceeding_h_durably_halts_all_fixtures(self):
        before = json.loads((EVIDENCE / 'SPEND.json').read_text())
        prereg = json.loads((EVIDENCE / 'PREREG-v4.json').read_text())
        # Exactly representable H and charges make the strict > boundary explicit.
        policy = s.Policy(poll_seconds=.125, observation_delay_seconds=.125,
                          kill_seconds=.125, reap_seconds=.125,
                          burst_cpu_seconds=.25, settlement_tail_cpu_seconds=.25)
        self.assertEqual(policy.reserve, 1)
        with tempfile.TemporaryDirectory() as tmp:
            budget = Path(tmp) / 'SPEND.json'
            for overshoot in (.5, 1., 1.5):
                state = copy.deepcopy(before)
                receipt = {'status': 'completed', 'returncode': 0,
                           'latency_assumptions_met': True,
                           'metered_cpu_seconds': 10 + overshoot - .25,
                           'reservation_id': 'synthetic-reservation'}
                result = s.settle(state, before, receipt, policy, 10)
                self.assertEqual(result['overshoot_cpu_seconds'], overshoot)
                self.assertFalse(result['result_accepted'])
                self.assertEqual(state['cpu_seconds'], before['cpu_seconds'] + 10 + overshoot)
                self.assertEqual(state['fixtures']['ascend910'], before['fixtures']['ascend910'])
                s._write(budget, state)
                saved = json.loads(budget.read_text())
                if overshoot <= policy.reserve:
                    self.assertFalse(saved.get('allocation_halted'))
                    self.assertGreater(s.remaining_cpu(saved, prereg), 0)
                    continue
                self.assertTrue(saved['allocation_halted']['requires_human_review'])
                self.assertTrue(result['allocation_halted'])
                with self.assertRaisesRegex(RuntimeError, 'allocation halted'):
                    s.remaining_cpu(saved, prereg)
                for fixture, spec in (('micro150', prereg), ('ascend910', {})):
                    with self.subTest(fixture=fixture), self.assertRaisesRegex(RuntimeError, 'allocation halted'):
                        h.SolveBudget(budget, fixture, spec)


if __name__ == '__main__':
    unittest.main()
