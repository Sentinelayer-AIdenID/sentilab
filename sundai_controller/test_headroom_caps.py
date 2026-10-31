"""Fake-clock proof for prospective call caps; no thermal evaluations."""
import asyncio
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sundai_controller import headroom as h
from sundai_hotspot import tap_oracle as tap

EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/SLAB-039'


class CallCapTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cpu = self.wall = 0.0
        self.now = datetime(2026, 10, 31, 8, tzinfo=timezone.utc)
        self.prereg = json.loads((EVIDENCE / 'PREREG-v4.json').read_text())
        self.state = json.loads((EVIDENCE / 'SPEND.json').read_text())
        case = self
        class Clock:
            @staticmethod
            def now(tz):
                return case.now + timedelta(seconds=case.wall)
            fromisoformat = datetime.fromisoformat
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(h, '_cpu_seconds', side_effect=lambda: self.cpu))
        self.stack.enter_context(patch.object(h.time, 'perf_counter', side_effect=lambda: self.wall))
        self.stack.enter_context(patch.object(h, 'datetime', Clock))
        self.stack.enter_context(patch.object(h.os, 'fsync'))

    def budget(self):
        path = self.root / 'SPEND.json'
        path.write_text(json.dumps(self.state))
        budget = h.SolveBudget(path, 'micro150', self.prereg)
        self.addCleanup(budget.close)
        return budget

    def test_default_call_is_capped_at_45_seconds(self):
        self.assertEqual(self.budget().call_timeout(), 45.0)

    def test_fixture_cpu_remainder_binds_call(self):
        self.prereg['allocation']['per_fixture']['cpu_minutes'] = 0.05
        self.assertEqual(self.budget().call_timeout(), 2.0)

    def test_headroom_cpu_remainder_includes_unrounded_prior_charge(self):
        self.state['cpu_seconds'] = 4317.75
        budget = self.budget()
        # Aggregate reservation normally ties this bound; isolate the headroom
        # check so deleting it cannot hide behind the independent aggregate cap.
        budget.aggregate_cpu_limit = 10000
        self.assertEqual(budget.call_timeout(), 1.25)

    def test_aggregate_cpu_remainder_includes_non_headroom_charge(self):
        self.state['non_headroom']['cpu_seconds'] = 5040 - self.state['cpu_seconds'] - 3.0
        self.assertEqual(self.budget().call_timeout(), 2.0)

    def test_noon_deadline_cannot_be_extended(self):
        self.now = datetime(2026, 10, 31, 11, 59, 58, tzinfo=timezone.utc)
        self.prereg['clock']['deadline'] = '2026-11-01T12:00:00Z'
        self.assertEqual(self.budget().call_timeout(), 2.0)

    def test_solving_wall_remainder_binds_call(self):
        self.state['solving_wall_seconds'] = 5398.5
        self.assertEqual(self.budget().call_timeout(), 1.5)

    def test_restart_cpu_remainder_binds_call(self):
        self.assertEqual(self.budget().call_timeout(1.75), 0.75)

    def test_p95_boundary_and_sub_p95_refusal_do_not_charge_call(self):
        budget = self.budget()
        self.assertEqual(budget.call_timeout(h.V4_P95_SECONDS + h.V4_CPU_RESERVE_SECONDS), h.V4_P95_SECONDS)
        budget.fixture_cpu_limit = h.V4_P95_SECONDS + h.V4_CPU_RESERVE_SECONDS - 1e-6
        before = budget.state['total_calls']
        with self.assertRaisesRegex(h.BudgetExhausted, 'fixture_cpu_cap_below_p95'):
            budget.reserve(MagicMock(hash='fake-design'), 'fake-lane')
        self.assertEqual(budget.state['total_calls'], before)
        self.assertIsNone(budget.state['active'])

    def test_p95_is_reproduced_from_pinned_measurements(self):
        metadata = self.prereg['call_admission']
        source = h.ROOT / metadata['timing_source']
        self.assertEqual(h._compute_prereg_digest(source), metadata['timing_sha256'])
        samples = json.loads(source.read_text())['fixtures']['micro150']['32x32']['times_seconds']
        self.assertEqual(sorted(samples)[-1], h.V4_P95_SECONDS)
        self.prereg['call_admission']['p95_seconds'] = 0.001
        with self.assertRaisesRegex(ValueError, 'frozen measured p95'):
            h._validate_v4(self.prereg)

    async def test_full_call_timeout_records_kill_latency_and_stops_next_call(self):
        budget = self.budget()
        budget.artifact_dir = self.root / 'attempt'
        budget.artifact_dir.mkdir()
        # All geometry is synthetic; no HotSpot constructor or subprocess.
        from sundai_controller.test_headroom import CountingOracle
        initial = CountingOracle().design_from_centers(h.MICRO150_INITIAL_CENTERS)
        case = self
        class Oracle(CountingOracle):
            last_kill_latency_s = None
            centers_for = lambda self, design: design.positions
            def retain_evaluation(self, directory):
                directory.mkdir(parents=True)
                # Simulate charged reservation/input I/O after admission.
                case.cpu += 0.25
                case.wall += 0.25
            async def __call__(self, design, *, timeout_s):
                self.timeout = timeout_s
                await asyncio.Event().wait()
            async def aclose(self):
                case.wall += 0.025
                self.last_kill_latency_s = 0.025
        oracle = Oracle()
        budget.fixture_cpu_limit = 2.25
        lane = h._LaneOracle(oracle, budget, 'fake', 2)
        async def fake_wait_for(coro, *, timeout):
            task = asyncio.create_task(coro)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertEqual(oracle.timeout, timeout)
            self.assertEqual(timeout, 1.0)  # admission I/O reduces the original 2.25 minus H
            self.wall += timeout
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            raise TimeoutError('fake deadline')
        before = budget.state['total_calls']
        with patch.object(h.asyncio, 'wait_for', side_effect=fake_wait_for), patch.object(
                h.os, 'sched_getaffinity', return_value={2, 3}), patch.object(h.os, 'sched_setaffinity') as affinity:
            with self.assertRaisesRegex(h.BudgetExhausted, 'call_timeout'):
                await lane(initial)
            with self.assertRaisesRegex(h.BudgetExhausted, 'call_timeout'):
                await lane(initial)
        self.assertEqual(affinity.call_args_list[0].args[1], {2})
        self.assertEqual(affinity.call_args_list[-1].args[1], {2, 3})
        self.assertEqual(budget.state['total_calls'], before + 1)
        self.assertIsNone(budget.state['active'])
        history = json.loads(next((budget.artifact_dir / 'evaluations').glob('*.json')).read_text())
        self.assertEqual(history['timeout_status'], 'timeout')
        self.assertEqual(history['timeout_s'], 1.0)
        self.assertEqual(history['kill_latency_s'], 0.025)

    async def test_bound_reaches_solver_and_worker_without_ten_second_grace(self):
        oracle = tap.HotSpotOracle(fixture='micro150')
        self.addAsyncCleanup(oracle.aclose)
        design = oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS)
        async def intercept(request, *, worker_timeout_s, **kwargs):
            self.assertEqual(request['solver_timeout_s'], 0.75)
            self.assertEqual(worker_timeout_s, 0.75)
            self.assertTrue(request['bounded_call'])
            raise tap.HotSpotTimeoutError('fake timeout')
        with patch.object(tap, '_run_worker', side_effect=intercept):
            with self.assertRaises(tap.HotSpotTimeoutError):
                await oracle(design, timeout_s=0.75)

    async def test_late_return_cannot_become_a_winner(self):
        from sundai_controller.test_headroom import CountingOracle
        from sundai_controller.controller import ThermalResult
        budget = self.budget()
        budget.fixture_cpu_limit = 2.0
        case = self
        class Oracle(CountingOracle):
            centers_for = lambda self, design: design.positions
            async def __call__(self, design, *, timeout_s):
                case.wall += timeout_s + 0.01
                return ThermalResult(design.hash, 90.0, 'fake-solver')
        oracle = Oracle()
        lane = h._LaneOracle(oracle, budget, 'late', 2)
        with self.assertRaisesRegex(h.BudgetExhausted, 'call_timeout'):
            await lane(oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS))
        self.assertIsNone(lane.best_result)
        self.assertEqual(budget.entry['calls'], 1)
        self.assertIsNone(budget.state['active'])

    async def test_bounded_group_kill_has_no_grace_and_measures_reap_latency(self):
        process = MagicMock(pid=12345)
        async def reap():
            self.wall += 0.012
        process.wait = AsyncMock(side_effect=reap)
        worker = object.__new__(tap._WarmWorker)
        worker.process, worker.immediate_kill = process, True
        worker.workspace, worker._stderr_task = MagicMock(), MagicMock()
        worker._stderr_task.done.return_value = True
        with patch.object(tap.os, 'killpg') as kill:
            await worker.close()
        kill.assert_called_once_with(12345, signal.SIGKILL)
        process.wait.assert_awaited_once()
        self.assertAlmostEqual(worker.kill_latency_s, 0.012)

    async def test_parent_timeout_keeps_file_backed_partial_output(self):
        raw = self.root / 'raw'
        output = raw / 'evaluation-fake'
        output.mkdir(parents=True)
        (output / 'stdout.bin').write_bytes(b'partial\xff stdout')
        (output / 'stderr.bin').write_bytes(b'partial\xfe stderr')
        oracle = tap.HotSpotOracle(fixture='micro150', retained_output_root=raw)
        self.addAsyncCleanup(oracle.aclose)
        design = oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS)
        async def intercept(*args, **kwargs):
            error = asyncio.CancelledError()
            error.kill_latency_s = 0.012
            raise error
        with patch.object(tap, '_run_worker', side_effect=intercept):
            with self.assertRaises(asyncio.CancelledError):
                await oracle(design, timeout_s=0.75)
        self.assertEqual((output / 'stdout.bin').read_bytes(), b'partial\xff stdout')
        self.assertEqual((output / 'stderr.txt').read_text(), 'partial\ufffd stderr')
        status = json.loads((output / 'EXIT.json').read_text())
        self.assertEqual(status['status'], 'parent_timeout')
        self.assertEqual(status['kill_latency_s'], 0.012)

    async def test_startup_cancellation_uses_immediate_kill_and_retains_latency(self):
        started, release = asyncio.Event(), asyncio.Event()
        worker = MagicMock()
        async def spawn():
            started.set()
            await release.wait()
            return worker
        async def close():
            self.assertIs(worker.immediate_kill, True)
            self.wall += 0.015
            worker.kill_latency_s = 0.015
        worker.close = AsyncMock(side_effect=close)
        pool = tap._WarmWorkerPool(max_workers=1)
        with patch.object(tap._WarmWorker, 'start', side_effect=spawn):
            task = asyncio.create_task(tap._run_worker({'bounded_call': True}, worker_timeout_s=0.75, pool=pool))
            await started.wait()
            task.cancel()
            await asyncio.sleep(0)
            release.set()
            with self.assertRaises(asyncio.CancelledError) as caught:
                await task
        self.assertEqual(caught.exception.kill_latency_s, 0.015)
        worker.close.assert_awaited_once()
        await pool.close()

    def test_exact_remaining_cpu_and_q_scaled_wall_bound(self):
        budget = self.budget()
        self.assertEqual(budget.fixture_cpu_limit, 2879.705435)
        self.assertAlmostEqual(budget.cpu_limit - budget.state['cpu_seconds'], 2879.705435)
        budget.fixture_cpu_limit = 9.0
        for q in (1, 2, 8):
            with self.subTest(q=q):
                budget.cpu_rate = q
                self.assertEqual(budget.call_timeout(), 8.0 / q)
                self.assertEqual(budget.call_cpu_allowance, 9.0)
                self.assertLessEqual(budget.call_timeout() * q + budget.cpu_reserve, 9.0)

    def test_rate_reserve_and_sampling_are_frozen(self):
        for field, invalid in (('rate_q', 0), ('rate_q', True), ('rate_q', 9),
                               ('reserve_h_cpu_seconds', 0), ('poll_seconds', 2)):
            with self.subTest(field=field, invalid=invalid):
                saved = self.prereg['cpu_enforcement'][field]
                self.prereg['cpu_enforcement'][field] = invalid
                with self.assertRaisesRegex(ValueError, 'CPU rate Q'):
                    h._validate_v4(self.prereg)
                self.prereg['cpu_enforcement'][field] = saved

    async def test_live_cpu_stop_counts_kill_to_reap_and_rejects_partial_result(self):
        from sundai_controller.test_headroom import CountingOracle
        from sundai_controller.controller import ThermalResult
        case = self
        class Oracle(CountingOracle):
            centers_for = lambda self, design: design.positions
            async def __call__(self, design, *, timeout_s):
                case.cpu += 2.0  # CPU + H reaches 3, before the wall cap.
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    case.cpu += 0.2  # work between cancellation/kill and reap
                    return ThermalResult(design.hash, 90.0, 'fake-solver')
            async def aclose(self):
                case.cpu += 0.1  # worker/descendant cleanup is also charged
                self.last_kill_latency_s = 0.025
        budget = self.budget()
        budget.fixture_cpu_limit = 3.0
        lane = h._LaneOracle(Oracle(), budget, 'cpu-stop', 2)
        design = lane.oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS)
        with self.assertRaisesRegex(h.BudgetExhausted, 'call_cpu_cap'):
            await lane(design)
        self.assertIsNone(lane.best_result)
        self.assertAlmostEqual(budget.entry['cpu_seconds'], 2.3)
        state = json.loads(budget.path.read_text())
        self.assertEqual(state['metered_runs'], 1)
        run = json.loads(Path(state['cpu_run_ledger']).read_text().splitlines()[-1])
        self.assertAlmostEqual(run['metered_cpu_seconds'], 2.3)
        self.assertAlmostEqual(run['cpu_at_stop_seconds'], 2.0)
        self.assertAlmostEqual(run['cpu_after_stop_seconds'], 0.3)
        self.assertTrue(run['reaping_confirmed'])
        self.assertNotIn('result', run)
        self.assertLessEqual(run['metered_cpu_seconds'], run['cpu_allowance_s'] + run['reserve_h_cpu_seconds'])
        with self.assertRaisesRegex(h.BudgetExhausted, 'call_cpu_cap'):
            await lane(design)

    def test_transient_proc_snapshot_dip_does_not_double_charge(self):
        budget = self.budget()
        self.cpu = 1.0
        budget.checkpoint()
        self.cpu = 0.9  # a child disappears mid-scan; its CPU appears on next read
        budget.checkpoint()
        self.cpu = 1.1
        budget.checkpoint()
        self.assertAlmostEqual(budget.entry['cpu_seconds'], 1.1)

    async def test_cleanup_cpu_is_charged_and_over_budget_result_is_rejected(self):
        from sundai_controller.test_headroom import CountingOracle
        from sundai_controller.controller import ThermalResult
        case = self
        class Oracle(CountingOracle):
            centers_for = lambda self, design: design.positions
            async def __call__(self, design, *, timeout_s):
                case.cpu += 0.1
                return ThermalResult(design.hash, 90.0, 'fake-solver')
            async def aclose(self):
                case.cpu += 3.0
        budget = self.budget()
        budget.fixture_cpu_limit = 3.0
        oracle = Oracle()
        lane = h._LaneOracle(oracle, budget, 'cleanup-over-budget', 2)
        with self.assertRaisesRegex(h.BudgetExhausted, 'call_cpu_cap'):
            await lane(oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS))
        self.assertIsNone(lane.best_result)
        self.assertAlmostEqual(budget.entry['cpu_seconds'], 3.1)
        run = json.loads(Path(budget.state['cpu_run_ledger']).read_text().splitlines()[-1])
        self.assertNotIn('result', run)
        self.assertIn('cleanup', run['error'])
        self.assertAlmostEqual(run['metered_cpu_seconds'], 3.1)
        self.assertLessEqual(run['metered_cpu_seconds'], 3.0 + budget.cpu_reserve)

    async def test_cpu_meter_failure_cancels_call_and_never_accepts_result(self):
        from sundai_controller.test_headroom import CountingOracle
        case = self
        case.fail_meter = False
        class Oracle(CountingOracle):
            centers_for = lambda self, design: design.positions
            async def __call__(self, design, *, timeout_s):
                case.fail_meter = True
                await asyncio.Event().wait()
        def cpu():
            if case.fail_meter:
                case.fail_meter = False
                raise OSError('fake unreadable /proc')
            return case.cpu
        budget = self.budget()
        oracle = Oracle()
        budget.fixture_cpu_limit = 1.75
        lane = h._LaneOracle(oracle, budget, 'meter-failure', 2)
        with patch.object(h, '_cpu_seconds', side_effect=cpu):
            with self.assertRaisesRegex(RuntimeError, 'CPU metering failed'):
                await lane(oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS))
        self.assertIsNone(lane.best_result)
        run = json.loads(Path(budget.state['cpu_run_ledger']).read_text().splitlines()[-1])
        self.assertTrue(run['reaping_confirmed'])
        self.assertNotIn('result', run)

    async def test_external_cancellation_retains_cleanup_charge_and_propagates(self):
        from sundai_controller.test_headroom import CountingOracle
        case = self
        started = asyncio.Event()
        class Oracle(CountingOracle):
            centers_for = lambda self, design: design.positions
            async def __call__(self, design, *, timeout_s):
                started.set()
                await asyncio.Event().wait()
            async def aclose(self):
                case.cpu += 0.2
        budget = self.budget()
        oracle = Oracle()
        lane = h._LaneOracle(oracle, budget, 'cancelled', 2)
        task = asyncio.create_task(lane(oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS)))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(lane.best_result)
        self.assertAlmostEqual(budget.entry['cpu_seconds'], 0.2)
        run = json.loads(Path(budget.state['cpu_run_ledger']).read_text().splitlines()[-1])
        self.assertTrue(run['reaping_confirmed'])
        self.assertAlmostEqual(run['metered_cpu_seconds'], 0.2)


if __name__ == '__main__':
    unittest.main()
