"""Independent-parent and lifetime-accounting probes; zero thermal solves."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sundai_controller import headroom as h
from sundai_controller import headroom_supervisor as s
from sundai_controller import test_headroom_v4 as v4

EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/SLAB-039'


class FakeTree:
    """Rate-respecting workload independent of parent observation events.

    A phase may be a synchronous 2-second asyncio stall, 7 CPU-s of work then
    4 of cleanup, or setup/lanes/output. The parent samples during every phase.
    """
    def __init__(self, q, phases, kill_reap=0.0, observation_delay=0.0):
        self.q, self.phases = q, phases
        self.kill_reap, self.observation_delay = kill_reap, observation_delay
        self.wall = self.used = 0.0
        self.started = self.restored = False
        self.kill_at = None
        self.returncode = None

    def clock(self):
        return self.wall

    def sleep(self, seconds):
        duration = seconds + self.observation_delay
        end = self.wall + duration
        natural_end = sum(self.phases) / self.q
        stop = natural_end if self.kill_at is None else min(natural_end, self.kill_at + self.kill_reap)
        self.used += self.q * max(0, min(end, stop) - min(self.wall, stop))
        self.wall = end

    def cpu(self):
        return self.used

    def start(self, work):
        self.started = True
        work()

    def done(self):
        if self.used >= sum(self.phases) - 1e-10:
            self.returncode = 0
            return True
        if self.kill_at is not None and self.wall >= self.kill_at + self.kill_reap:
            self.returncode = -9
            return True
        return False

    def kill(self):
        if self.kill_at is None:
            self.kill_at = self.wall

    def restore(self):
        self.restored = True


class SupervisorTests(unittest.TestCase):
    def run_fake(self, phases, allowance, q=8, **kwargs):
        tree = FakeTree(q, phases, **kwargs)
        result = s.supervise(lambda: None, allowance=allowance, policy=s.Policy(rate_q=q),
                             backend=tree, clock=tree.clock, sleep=tree.sleep)
        return result, tree

    def test_runner_asyncio_stalled_two_seconds_cannot_stall_parent(self):
        for q in (1, 2, 8):
            with self.subTest(q=q):
                result, tree = self.run_fake([q * 2], q + 1, q=q)
                self.assertTrue(tree.started)
                self.assertEqual(result['status'], 'stopped')
                self.assertLessEqual(result['metered_cpu_seconds'] + s.Policy(rate_q=q).settlement_tail_cpu_seconds, q + 1)
                self.assertLess(tree.wall, 2)

    def test_seven_work_plus_four_cleanup_cannot_escape_parent(self):
        # Cleanup after SIGKILL/reap also consumes 4 CPU-s, within declared .5 s.
        result, tree = self.run_fake([7, 4], 9, kill_reap=0.5)
        self.assertEqual(result['status'], 'stopped')
        self.assertAlmostEqual(result['cpu_after_stop_seconds'], 4.0)
        self.assertLessEqual(result['metered_cpu_seconds'] + 0.25, 9)
        self.assertTrue(result['reaping_confirmed'])

    def test_point_one_remaining_refuses_before_setup_or_generation(self):
        result, tree = self.run_fake([2], 0.1)
        self.assertFalse(tree.started)
        self.assertEqual(result['status'], 'refused_before_start')
        self.assertEqual(result['metered_cpu_seconds'], 0)

    def test_lifecycle_three_setup_two_point_four_lanes_six_output_is_settled(self):
        receipt, tree = self.run_fake([3, 2.4, 6], 20)
        self.assertAlmostEqual(receipt['metered_cpu_seconds'], 11.4)
        before = json.loads((EVIDENCE / 'SPEND.json').read_text())
        state = copy.deepcopy(before)
        # Inner SolveBudget reported only lanes. Outer settlement replaces it.
        state['cpu_seconds'] += 2.4
        state['fixtures']['micro150'] = {'calls': 0, 'cpu_seconds': 2.4}
        result = s.settle(state, before, receipt, s.Policy(rate_q=8), 20)
        self.assertAlmostEqual(state['cpu_seconds'], 1440.294565 + 11.4 + 0.25)
        self.assertAlmostEqual(state['fixtures']['micro150']['cpu_seconds'], 11.65)
        self.assertEqual(state['fixtures']['ascend910'], before['fixtures']['ascend910'])
        self.assertTrue(result['result_accepted'])
        with tempfile.TemporaryDirectory() as tmp:
            s._write(Path(tmp) / 'SPEND.json', state)
            saved = json.loads((Path(tmp) / 'SPEND.json').read_text())
        self.assertEqual(saved['cpu_seconds'], state['cpu_seconds'])
        # A conservative charge already persisted by the worker cannot be erased,
        # nor can a smaller final meter reading make that run resource-acceptable.
        state['cpu_seconds'] = before['cpu_seconds'] + 30
        state['fixtures']['micro150']['cpu_seconds'] = 30
        result = s.settle(state, before, receipt, s.Policy(rate_q=8), 20)
        self.assertEqual(result['charged_cpu_seconds'], 30)
        self.assertFalse(result['result_accepted'])

    def test_late_parent_observation_is_reported_as_breach_not_hard_cap(self):
        receipt, tree = self.run_fake([16], 9, observation_delay=2)
        self.assertEqual(receipt['metered_cpu_seconds'], 16)
        self.assertFalse(receipt['latency_assumptions_met'])
        before = json.loads((EVIDENCE / 'SPEND.json').read_text())
        result = s.settle(copy.deepcopy(before), before, receipt, s.Policy(rate_q=8), 9)
        self.assertFalse(result['result_accepted'])
        self.assertFalse(result['hard_cap'])
        self.assertIsNone(result['unconditional_overshoot_bound'])
        self.assertEqual(result['overshoot_cpu_seconds'], 7.25)

    def test_policy_reserves_each_latency_and_quantifies_conditional_overshoot(self):
        for q in (1, 2, 8):
            policy = s.Policy(rate_q=q)
            self.assertAlmostEqual(policy.reserve, q * 0.76 + 0.27)
            self.assertAlmostEqual(policy.conditional_overshoot(.25, .25, .25, .25), 0)
            self.assertAlmostEqual(policy.conditional_overshoot(2, .25, .25, .25), q * 1.75)

    def test_pending_operational_decision_cannot_start_worker(self):
        with patch.object(s.LinuxTree, 'start') as start:
            with self.assertRaisesRegex(RuntimeError, 'operational approval required'):
                s.run(EVIDENCE / 'PREREG-v4.json', EVIDENCE / 'SPEND.json',
                      EVIDENCE / 'never-created', EVIDENCE / 'SUPERVISOR-POLICY.json')
        start.assert_not_called()

    def test_prior_charges_and_unreconciled_reservation_cannot_be_reset(self):
        state = json.loads((EVIDENCE / 'SPEND.json').read_text())
        prereg = json.loads((EVIDENCE / 'PREREG-v4.json').read_text())
        self.assertLessEqual(s.remaining_cpu(state, prereg), 2879.705435)
        state['outer_active'] = {'reserved_cpu_seconds': 2879.705435}
        with self.assertRaisesRegex(RuntimeError, 'unreconciled'):
            s.remaining_cpu(state, prereg)
        state.pop('outer_active')
        state['fixtures']['ascend910']['cpu_seconds'] = 0
        with self.assertRaisesRegex(ValueError, 'cannot be reset'):
            s.remaining_cpu(state, prereg)

    def test_real_parent_reaps_forked_session_and_counts_output_cpu(self):
        # Dedicated interpreter: never subreap or kill the test harness's children.
        program = '''
import json, os, time
from sundai_controller import headroom_supervisor as s
policy = s.Policy()
backend = s.LinuxTree(policy)
def work():
    if os.fork() == 0:
        os.setsid()
        end = time.process_time() + .08
        while time.process_time() < end: pass
        os._exit(0)
    end = time.process_time() + .04
    while time.process_time() < end: pass
result = s.supervise(work, allowance=5, policy=policy, backend=backend)
assert result['reaping_confirmed']
assert backend.scope.reaped_pids and len(backend.scope.reaped_pids) == 2
assert result['metered_cpu_seconds'] >= .04
assert s.tree_snapshot()[1] == {}
print(json.dumps(result))
'''
        result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['reaping_confirmed'])

    def test_production_parent_and_worker_settle_synthetic_run_under_one_lock(self):
        program = '''
import asyncio, json, pathlib, tempfile
from dataclasses import asdict
from sundai_controller import headroom as h, headroom_supervisor as s
from sundai_controller.test_headroom import CountingOracle
from sundai_controller.controller import ThermalResult
evidence = pathlib.Path('docs/sentilab/evidence/SLAB-039')
class Fake(CountingOracle):
    centers_for = lambda self, design: design.positions
    _wirelength_mm = lambda self, centers: 1.0
    async def __call__(self, design, *, timeout_s):
        assert timeout_s == 45.0
        assert json.loads((root / 'SPEND.json').read_text())['active']['timeout_s'] == 45.0
        return ThermalResult(design.hash, 100., 'fake-version', problem_hash='fake-problem')
async def forbidden(*args, **kwargs):
    raise AssertionError('redundant asyncio CPU watcher invoked')
h._LaneOracle._metered_call = forbidden
original = h.run_headroom
async def synthetic(*args, **kwargs):
    return await original(*args, **kwargs, oracle_factory=Fake)
h.run_headroom = synthetic
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    prereg = json.loads((evidence / 'PREREG-v4.json').read_text())
    prereg['allocation']['per_fixture']['total_solves'] = 24
    (root / 'PREREG.json').write_text(json.dumps(prereg))
    (root / 'SPEND.json').write_bytes((evidence / 'SPEND.json').read_bytes())
    (root / 'POLICY.json').write_text(json.dumps({
        'limits': asdict(s.Policy()), 'status': 'approved', 'approved_by': 'synthetic-test-only',
        'accept_unbounded_scheduler_and_cleanup_risk': True}))
    # Pin clock inside the parent too; no date-dependent prospective test failure.
    from datetime import datetime, timezone
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026,10,31,8,tzinfo=timezone.utc)
    s.datetime = h.datetime = Clock
    receipt = s.run(root / 'PREREG.json', root / 'SPEND.json', root / 'out', root / 'POLICY.json')
    assert receipt['result_accepted'], receipt
    state = json.loads((root / 'SPEND.json').read_text())
    result = json.loads(next((root / 'out').glob('attempt-*/RESULT.json')).read_text())
    assert state['fixtures']['ascend910'] == json.loads((evidence / 'SPEND.json').read_text())['fixtures']['ascend910']
    assert state['fixtures']['micro150']['calls'] == 24
    assert state['outer_active'] is None
    assert result['resource_status'] == 'awaiting_supervisor_settlement'
    assert result['supervisor_reservation_id'] == receipt['reservation_id']
    assert state['fixtures']['micro150']['cpu_seconds'] > result['cpu_seconds']
    assert state['lifetime_settlements'][-1] == receipt
    assert s.tree_snapshot()[1] == {}
print('whole runner, inherited lock, provisional result and terminal receipt checked')
'''
        result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_worker_primitive_refuses_without_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp, patch('sundai_hotspot.tap_oracle.HotSpotOracle') as oracle:
            import asyncio
            with self.assertRaisesRegex(RuntimeError, 'independent headroom_supervisor'):
                asyncio.run(h.run_headroom('micro150', .79, EVIDENCE / 'PREREG-v4.json', Path(tmp)))
        oracle.assert_not_called()


class RunnerRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_generation_is_not_admitted_with_point_one_cpu_left(self):
        case = v4.V4Tests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.spend['cpu_seconds'] = 4319.9
        generated = []
        def generation(initial, *args):
            generated.append(True)
            case.cpu += 2
            return [initial]
        with patch.object(h, '_shared_designs', side_effect=generation):
            result = await case.run_fixture()
        self.assertEqual(generated, [])
        self.assertEqual(case.calls, [])
        self.assertEqual(result['cpu_seconds'], 0)

    async def test_worker_accounting_also_includes_prereg_and_report_work(self):
        case = v4.V4Tests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.prereg['allocation']['per_fixture']['total_solves'] = 24
        case.cpu_per_call = 0.1
        parse = h._parse_prereg
        report = h._write_report
        def setup(*args, **kwargs):
            case.cpu += 3
            return parse(*args, **kwargs)
        def output(*args, **kwargs):
            case.cpu += 6
            return report(*args, **kwargs)
        with patch.object(h, '_parse_prereg', side_effect=setup), patch.object(h, '_write_report', side_effect=output):
            result = await case.run_fixture()
        self.assertAlmostEqual(result['cpu_seconds'], 11.4)
        state = json.loads((case.directory / 'SPEND.json').read_text())
        self.assertAlmostEqual(state['fixtures']['micro150']['cpu_seconds'], 11.4)

    def test_binary64_threshold_semantics_are_frozen(self):
        prereg = json.loads((EVIDENCE / 'PREREG-v4.json').read_text())
        self.assertEqual(prereg['rule']['arithmetic'], h.V4_ARITHMETIC)
        self.assertEqual(h._gate_pass(100.1, 96.15, .79), (False, 3.9499999999999886))
        self.assertEqual(h._gate_pass(3.95, 0, .79), (True, 3.95))
        winner = dict(winner_verified=True, solver_version='fake', problem_hash='fake',
                      best_temperature_c=96.15)
        baseline = dict(cheap_median_c=100.1, winners=[winner], solver_version='fake', problem_hash='fake')
        verdict, _, gap, _, _ = h._v4_verdict(json.loads(json.dumps(baseline)), [])
        self.assertEqual((verdict, gap), ('INCONCLUSIVE', 3.9499999999999886))
        prereg['rule']['arithmetic'] = 'decimal'
        with self.assertRaisesRegex(ValueError, 'binary64'):
            h._validate_v4(prereg)


if __name__ == '__main__':
    unittest.main()
