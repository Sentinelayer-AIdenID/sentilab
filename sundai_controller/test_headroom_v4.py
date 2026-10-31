"""Prospective micro150 rules and admission bounds; every evaluation is fake."""
import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from sundai_controller import headroom as h
from sundai_controller.controller import ThermalResult
from sundai_controller.test_headroom import CountingOracle
from sundai_hotspot import tap_oracle

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/sentilab/evidence/SLAB-039'


class V4Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.prereg = json.loads((EVIDENCE / 'PREREG-v4.json').read_text())
        self.spend = json.loads((EVIDENCE / 'SPEND.json').read_text())
        self.cpu = self.wall = 0.0
        self.now = datetime(2026, 10, 31, 8, tzinfo=timezone.utc)
        self.calls = []
        self.cpu_per_call = self.wall_per_call = 0.0
        self.temperature = lambda lane, call, design: 100.0
        self.mutate_result = lambda result, lane, call: result
        self.reject_geometry = False
        self.fake_wire = lambda centers: 1.0
        self.on_call = lambda: None

    async def run_fixture(self):
        case = self
        prereg_path = self.directory / 'PREREG-v4.json'
        prereg_path.write_text(json.dumps(self.prereg))
        spend_path = self.directory / 'SPEND.json'
        if not spend_path.exists():
            spend_path.write_text(json.dumps(self.spend))
        lane_counts = {}

        class Oracle(CountingOracle):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                case.selected_fixture = kwargs.get('fixture')

            def centers_for(self, design):
                design.check()
                if case.reject_geometry:
                    raise ValueError('fixture geometry rejected')
                return design.positions

            def _wirelength_mm(self, centers):
                return case.fake_wire(centers)

            async def __call__(self, design, *, timeout_s=None):
                case.on_call()
                ledger = json.loads(spend_path.read_text())
                reservation = ledger['active']
                case.assertEqual(reservation['design_hash'], design.hash)
                lane = reservation['lane']
                lane_counts[lane] = lane_counts.get(lane, 0) + 1
                count = lane_counts[lane]
                case.calls.append((lane, count, design.hash, len(design.chiplets)))
                if 'long-sa' in lane:
                    baseline = Path(ledger['attempts'][-1]['artifact_directory']) / 'CHEAP_BASELINE.json'
                    # A reference call only has a persisted C if all cheap checks passed.
                    if baseline.exists():
                        case.assertEqual(json.loads(baseline.read_text())['reproductions'], 96)
                case.last_timeout = timeout_s
                if timeout_s is not None and max(case.cpu_per_call, case.wall_per_call) > timeout_s:
                    case.cpu += min(case.cpu_per_call, timeout_s)
                    case.wall += timeout_s
                    self.last_kill_latency_s = 0.0
                    raise TimeoutError('fake in-flight timeout')
                case.cpu += case.cpu_per_call
                case.wall += case.wall_per_call
                value = case.temperature(lane, count, design)
                result = ThermalResult(design.hash, value, 'fake-solver-v1', problem_hash='fake-problem')
                return case.mutate_result(result, lane, count)

        class Clock:
            @staticmethod
            def now(tz):
                return case.now + timedelta(seconds=case.wall)
            fromisoformat = datetime.fromisoformat

        with ExitStack() as stack:
            stack.enter_context(patch.object(tap_oracle, 'HotSpotOracle', Oracle))
            stack.enter_context(patch.object(h, '_cpu_seconds', side_effect=lambda: case.cpu))
            stack.enter_context(patch.object(h.time, 'perf_counter', side_effect=lambda: case.wall))
            stack.enter_context(patch.object(h, 'datetime', Clock))
            # Keep real file writes/readbacks (including the pre-call reservation)
            # but omit disk barriers in fake-run tests; legacy budget tests cover fsync.
            stack.enter_context(patch.object(h.os, 'fsync'))
            return await h.run_headroom('micro150', 0.79, prereg_path, self.directory / 'out', oracle_factory=Oracle)

    def set_micro_calls(self, count):
        self.spend['fixtures']['micro150'] = {'calls': count, 'cpu_seconds': 0.0}
        self.spend['total_calls'] += count

    async def test_full_schedule_freezes_C_and_reserves_all_witness_calls(self):
        # Small permitted reproduction variation must not replace the frozen score.
        self.temperature = lambda lane, call, design: (100.0 - 0.5e-6 if
            (call > 28 if 'long-sa' not in lane else call == 1000) else 100.0)
        result = await self.run_fixture()
        self.assertEqual(self.selected_fixture, 'micro150')
        self.assertTrue(all(row[3] == 8 for row in self.calls))
        self.assertEqual(len(self.calls), 4768)
        self.assertTrue(result['cheap_baseline_complete'])
        self.assertEqual(result['cheap_median_c'], 100.0)
        self.assertEqual(result['best_c'], 100.0)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertTrue(result['reference_complete'])
        self.assertFalse(result['paid_scientific_model_authorized'])
        self.assertEqual(result['threshold_c'], 3.95)
        for lane in result['reducer_results']:
            self.assertEqual((lane['search_evaluation_count'], lane['reproduction_evaluation_count']), (28, 4))
            self.assertTrue(lane['winner_verified'])
            self.assertEqual(lane['best_temperature_c'], 100.0)
            self.assertTrue(all(r['agrees'] for r in lane['reproductions']))
            calls = [row for row in self.calls
                     if row[0] == f"slab039-micro150-{lane['method']}-{lane['prereg_seed']}"]
            self.assertEqual([row[2] for row in calls[-4:]], [lane['best_design_hash']] * 4)
        for lane in result['long_sa_results']:
            self.assertEqual((lane['search_evaluation_count'], lane['reproduction_evaluation_count']), (999, 1))
            self.assertEqual(lane['best_temperature_c'], 100.0)
            self.assertTrue(lane['winner_verified'])
            calls = [row for row in self.calls if row[0] == f"slab039-micro150-long-sa-{lane['seed']}"]
            self.assertEqual(calls[-1][2], lane['best_design_hash'])
        baseline = Path(result['artifact_directory']) / 'CHEAP_BASELINE.json'
        self.assertEqual(result['cheap_baseline_sha256'], h._compute_prereg_digest(baseline))
        self.assertEqual(result['allocation_spend']['fixtures']['ascend910'], self.spend['fixtures']['ascend910'])
        self.assertEqual(result['allocation_spend']['non_headroom'], self.spend['non_headroom'])

    async def test_partial_reference_can_pass_with_verified_witness(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 1769
        self.temperature = lambda lane, call, design: 96.0 if 'long-sa' in lane else 100.0
        result = await self.run_fixture()
        self.assertEqual(result['verdict'], 'PASS')
        self.assertFalse(result['reference_complete'])
        self.assertEqual(result['gap_c'], 4.0)
        self.assertEqual(len(self.calls), 1769)
        self.assertTrue(result['long_sa_results'][0]['winner_verified'])
        self.assertFalse(result['long_sa_results'][1]['winner_verified'])

    async def test_partial_reference_below_threshold_is_inconclusive(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 1769
        result = await self.run_fixture()
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        self.assertFalse(result['reference_complete'])

    async def test_exact_3_95_threshold_passes_with_verified_witness(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 1768
        self.temperature = lambda lane, call, design: 0.0 if 'long-sa' in lane else 3.95
        result = await self.run_fixture()
        self.assertEqual(result['gap_c'], result['threshold_c'])
        self.assertEqual(result['verdict'], 'PASS')
        self.assertFalse(result['reference_complete'])

    async def test_unverified_best_cannot_pass(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 1767
        self.temperature = lambda lane, call, design: 90.0 if 'long-sa' in lane else 100.0
        result = await self.run_fixture()
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        self.assertEqual(result['best_c'], 100.0)
        self.assertFalse(result['long_sa_results'][0]['winner_verified'])

    async def test_incomplete_cheap_baseline_cannot_pass(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 767
        self.temperature = lambda lane, call, design: 50.0 if '-random-0' in lane else 100.0
        result = await self.run_fixture()
        self.assertFalse(result['cheap_baseline_complete'])
        self.assertIsNone(result['cheap_median_c'])
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        self.assertFalse(list((self.directory / 'out').glob('attempt-*/CHEAP_BASELINE.json')))

    async def test_each_cheap_reproduction_must_agree(self):
        # All four reproduction positions independently exclude their winner.
        self.prereg['allocation']['per_fixture']['total_solves'] = 768
        def temp(lane, call, design):
            seed = int(lane.rsplit('-', 1)[1])
            return 100.0 + 2e-6 if call == 29 + seed % 4 else 100.0
        self.temperature = temp
        result = await self.run_fixture()
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        self.assertFalse(result['cheap_baseline_complete'])
        for lane in result['reducer_results']:
            self.assertFalse(lane['winner_verified'])
            self.assertEqual(lane['best_temperature_c'], 100.0)
            self.assertEqual(sum(not r['agrees'] for r in lane['reproductions']), 1)

    async def test_failed_baseline_stops_before_reference_and_retains_charges(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 769
        self.cpu_per_call = 0.01
        self.temperature = lambda lane, call, design: 101.0 if call == 29 else 100.0
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 768)
        self.assertEqual(result['long_sa_results'], [])
        self.assertEqual(result['reference_skip_reason'], 'cheap_baseline_incomplete')
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        self.assertFalse(result['cheap_baseline_complete'])
        self.assertAlmostEqual(result['cpu_seconds'], 7.68)
        attempt = result['allocation_spend']['attempts'][-1]
        self.assertEqual(attempt['ending_calls'] - attempt['starting_calls'], 768)
        self.assertEqual(attempt['status'], 'baseline_failed')
        self.assertTrue((Path(result['artifact_directory']) / 'RESULT.json').is_file())

    async def test_reference_disagreement_is_ineligible(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 1768
        self.temperature = lambda lane, call, design: 90.0 if 'long-sa' in lane else 100.0
        self.mutate_result = lambda r, lane, call: replace(r, maximum_temperature_c=90.000002) if call == 1000 else r
        result = await self.run_fixture()
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        self.assertEqual(result['best_c'], 100.0)
        self.assertFalse(result['long_sa_results'][0]['winner_verified'])

    async def test_cheap_solver_problem_and_candidate_identity_must_match(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 768
        def mutate(result, lane, call):
            if call != 29:
                return result
            if '-random-0' in lane:
                return replace(result, solver_version='changed-solver')
            if '-random-1' in lane:
                return replace(result, problem_hash='changed-problem')
            if '-random-2' in lane:
                return replace(result, candidate_hash='another-candidate')
            return result
        self.mutate_result = mutate
        result = await self.run_fixture()
        self.assertFalse(result['cheap_baseline_complete'])
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        for row in result['reducer_results'][:3]:
            self.assertFalse(row['winner_verified'])

    async def test_reference_solver_problem_and_invalid_results_are_ineligible(self):
        # Independent cases: none can be hidden behind another failed check.
        for field, value in [('solver_version', 'changed-solver'), ('problem_hash', 'changed-problem'),
                             ('candidate_hash', 'another-candidate'), ('converged', False)]:
            with self.subTest(field=field):
                self.directory = Path(self.tmp.name) / field
                self.directory.mkdir()
                self.calls = []
                self.prereg['allocation']['per_fixture']['total_solves'] = 1768
                self.temperature = lambda lane, call, design: 90.0 if 'long-sa' in lane else 100.0
                self.mutate_result = lambda r, lane, call: replace(r, **{field: value}) if call == 1000 else r
                result = await self.run_fixture()
                self.assertEqual(result['verdict'], 'INCONCLUSIVE')
                self.assertEqual(result['best_c'], 100.0)
                self.assertFalse(result['long_sa_results'][0]['winner_verified'])

    async def test_reference_witness_set_only_grows_and_gap_cannot_shrink(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 2769
        def temperature(lane, call, design):
            return 96.0 if '-long-sa-100' in lane else 97.0 if '-long-sa-101' in lane else 100.0
        self.temperature = temperature
        result = await self.run_fixture()
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['best_c'], 96.0)
        self.assertEqual(result['gap_c'], 4.0)
        self.assertEqual(len(result['eligible_reference_witnesses']), 26)
        self.assertFalse(result['reference_complete'])

    def test_initial_layout_is_legal_for_real_micro150_catalog_without_solves(self):
        oracle = tap_oracle.HotSpotOracle(fixture='micro150')
        initial = oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS)
        self.assertEqual(len(oracle.centers_for(initial)), 8)
        self.assertEqual(sum(oracle.problem.powers_w), 680.0)

    async def test_fixed_sample_discrepancy_cannot_be_replaced_dynamically(self):
        path = self.directory / 'PREREG-v4.json'
        path.write_text(json.dumps(self.prereg))
        with patch.object(tap_oracle, 'HotSpotOracle', side_effect=AssertionError('no oracle construction')):
            with self.assertRaisesRegex(ValueError, 'fixed PR 18 sample discrepancy'):
                await h.run_headroom('micro150', 0.79, path, self.directory / 'out', [100.0], [100.79])

    async def test_v4_output_cannot_overwrite_v3_evidence(self):
        path = self.directory / 'PREREG-v4.json'
        path.write_text(json.dumps(self.prereg))
        with self.assertRaisesRegex(ValueError, 'overwrite the retained v3'):
            await h.run_headroom('micro150', 0.79, path, self.directory)

    async def test_wire_ceiling_applies_to_every_lane_and_evaluation(self):
        self.prereg['allocation']['per_fixture']['total_solves'] = 40
        self.fake_wire = lambda centers: sum(x * x + y * y for x, y in centers)
        result = await self.run_fixture()
        root = Path(result['artifact_directory'])
        domain = json.loads((root / 'DOMAIN.json').read_text())
        self.assertEqual(result['wire_limit_mm'], domain['wire_limit_mm'])
        evaluations = list((root / 'evaluations').glob('*.json'))
        self.assertEqual(len(evaluations), 40)
        for path in evaluations:
            record = json.loads(path.read_text())
            self.assertLessEqual(self.fake_wire(record['design']['positions']), result['wire_limit_mm'])
            self.assertTrue(Path(record['raw_output_directory']).is_dir())

    async def test_wire_ceiling_stays_at_initial_and_rejects_excess(self):
        from sundai_controller.controller import Design, Chiplet
        class Oracle(CountingOracle):
            def centers_for(self, design):
                design.check()
                return design.positions
            def _wirelength_mm(self, centers):
                return sum(x + y for x, y in centers)
        initial = Design(50, 50, 0, (Chiplet('a', 2, 2),), ((10, 10),))
        oracle = h._ConstrainedOracle(Oracle(), initial)
        await oracle(replace(initial, positions=((5, 5),)))
        await oracle(replace(initial, positions=((7, 7),)))
        self.assertEqual(oracle.wire_limit, 20)
        with self.assertRaisesRegex(ValueError, 'fixed initial wirelength'):
            await oracle(replace(initial, positions=((11, 11),)))
        self.assertEqual(len(oracle.oracle.calls), 2)

    async def test_start_bytes_are_bound_even_if_live_prereg_changes(self):
        import hashlib
        self.prereg['allocation']['per_fixture']['total_solves'] = 1
        original = json.dumps(self.prereg).encode()
        def change_prereg():
            changed = copy.deepcopy(self.prereg)
            changed['rule']['k'] = 999
            (self.directory / 'PREREG-v4.json').write_text(json.dumps(changed))
        self.on_call = change_prereg
        result = await self.run_fixture()
        root = Path(result['artifact_directory'])
        self.assertEqual(result['k'], 5)
        self.assertEqual(result['prereg_digest_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual((root / 'PREREG.json').read_bytes(), original)
        self.assertEqual(result['runner_sha256'], hashlib.sha256((root / 'headroom.py').read_bytes()).hexdigest())

    async def test_attempts_preserve_results_and_full_signed_history(self):
        from sundai_controller.controller import FlightRecord
        self.prereg['allocation']['per_fixture']['total_solves'] = 6
        first = await self.run_fixture()
        root = Path(first['artifact_directory'])
        original = (root / 'RESULT.json').read_bytes()
        second = await self.run_fixture()
        self.assertNotEqual(first['artifact_directory'], second['artifact_directory'])
        self.assertEqual((root / 'RESULT.json').read_bytes(), original)
        self.assertEqual(len(second['allocation_spend']['attempts']), 2)
        lane = json.loads((root / 'lanes/slab039-micro150-random-0.json').read_text())
        self.assertTrue(FlightRecord.verify(lane['events'], lane['public_key']))
        persisted = [json.loads(row) for row in (root / 'lanes/slab039-micro150-random-0.ndjson').read_text().splitlines()]
        self.assertEqual(persisted, lane['events'])
        self.assertIn('proposal_admitted', {row['event'] for row in persisted})

    def test_raw_worker_directory_retains_output_on_success_and_error(self):
        from sundai_hotspot.tap_oracle_worker import _output_directory
        root = self.directory / 'raw'
        root.mkdir()
        for fail in (False, True):
            with self.subTest(fail=fail):
                try:
                    with _output_directory(self.directory, str(root)) as name:
                        output = Path(name)
                        (output / 'sample.grid.steady').write_text('fake raw grid')
                        if fail:
                            raise ValueError('fake solver error')
                except ValueError:
                    pass
                self.assertEqual((output / 'sample.grid.steady').read_text(), 'fake raw grid')
        with _output_directory(self.directory) as name:
            transient = Path(name)
        self.assertFalse(transient.exists())

    async def test_retention_reaches_worker_and_preserves_raw_failure(self):
        from unittest.mock import MagicMock
        from types import SimpleNamespace
        from sundai_hotspot import tap_oracle_worker as worker
        root = self.directory / 'raw'
        oracle = tap_oracle.HotSpotOracle(fixture='micro150', retained_output_root=root)
        design = oracle.design_from_centers(h.MICRO150_INITIAL_CENTERS)
        captured = {}
        async def intercept(request, **kwargs):
            captured.update(request)
            raise RuntimeError('intercepted before solve')
        try:
            with patch.object(tap_oracle, '_run_worker', side_effect=intercept):
                with self.assertRaisesRegex(RuntimeError, 'intercepted before solve'):
                    await oracle(design)
        finally:
            await oracle.aclose()
        self.assertEqual(captured['retained_output_root'], str(root))
        captured['workspace_root'] = str(self.directory)
        captured = json.loads(json.dumps(captured))  # actual JSON worker protocol
        system = MagicMock()
        system.hubump = oracle.problem.bump_halos_mm
        output = None
        def set_path(value):
            nonlocal output
            output = Path(value)
        def generate(_):
            for name in ('new_hotspot.config', 'sampleL4_ChipLayer.flp', 'sample.ptrace'):
                (output / name).write_text('fake generated input')
            (output / 'samplelayers.lcf').write_text('sampleL4_ChipLayer.flp\n')
        system.set_path.side_effect = set_path
        system.gen_flp.side_effect = generate
        with patch.object(worker, 'PassiveInterposer', return_value=system), patch.object(
                worker.subprocess, 'run', return_value=SimpleNamespace(returncode=17, stdout='fake stdout', stderr='fake stderr')):
            with self.assertRaisesRegex(RuntimeError, 'HotSpot exited 17'):
                worker.evaluate(captured)
        self.assertEqual((output / 'stdout.txt').read_text(), 'fake stdout')
        self.assertEqual((output / 'stderr.txt').read_text(), 'fake stderr')
        self.assertEqual(json.loads((output / 'REQUEST.json').read_text())['candidate_hash'], design.hash)
        self.assertEqual(json.loads((output / 'EXIT.json').read_text())['returncode'], 17)
        self.assertTrue((output / 'sample.ptrace').exists())

        # TimeoutExpired carries bytes even with text=True on supported Python;
        # adapters may supply text or no payload. Exercise both streams/types.
        for stdout, stderr in [(b'partial\xff out', b'partial\xfe err'),
                               ('partial out', 'partial err'), (None, None)]:
            with self.subTest(stdout_type=type(stdout).__name__):
                error = worker.subprocess.TimeoutExpired('fake solver', 0.5, output=stdout, stderr=stderr)
                with patch.object(worker, 'PassiveInterposer', return_value=system), patch.object(
                        worker.subprocess, 'run', side_effect=error):
                    with self.assertRaisesRegex(TimeoutError, 'TFL_ORACLE_TIMEOUT'):
                        worker.evaluate(captured)
                for name, value in [('stdout', stdout), ('stderr', stderr)]:
                    expected = value if isinstance(value, bytes) else (value or '').encode()
                    self.assertEqual((output / f'{name}.bin').read_bytes(), expected)
                    self.assertEqual((output / f'{name}.txt').read_text(), expected.decode(errors='replace'))
                status = json.loads((output / 'EXIT.json').read_text())
                self.assertEqual(status['status'], 'timeout')
                self.assertEqual(status['stdout_payload_type'], type(stdout).__name__)
                self.assertEqual(status['stderr_payload_type'], type(stderr).__name__)
                self.assertEqual(status['timeout_s'], captured['solver_timeout_s'])
                self.assertIsNone(status['returncode'])

    async def test_cpu_48_and_72_minute_caps_preserve_prior_actuals(self):
        self.spend['fixtures']['micro150'] = {'calls': 0, 'cpu_seconds': 2879.5}
        self.spend['cpu_seconds'] += 2879.5
        self.cpu_per_call = 0.3
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'total_cpu_cap_below_p95')
        self.assertEqual(result['allocation_spend']['overshoot']['headroom_cpu_seconds'], 0.0)
        self.assertEqual(result['allocation_spend']['fixtures']['ascend910']['cpu_seconds'], 1440.2945650000001)

    async def test_fixture_cpu_cap_cannot_be_increased_by_prereg(self):
        # A stricter cumulative charge can mask the fixture bound; inspect both limits.
        self.prereg['allocation']['per_fixture']['cpu_minutes'] = 999
        self.prereg['allocation']['headroom_cpu_minutes'] = 999
        path = self.directory / 'SPEND.json'
        path.write_text(json.dumps(self.spend))
        budget = h.SolveBudget(path, 'micro150', self.prereg)
        try:
            self.assertEqual(budget.fixture_cpu_limit, 2879.705435)
            self.assertEqual(budget.cpu_limit, 4320)
        finally:
            budget.close()

    async def test_micro150_4768_solve_cap_survives_reinvocation(self):
        self.set_micro_calls(4767)
        self.prereg['allocation']['per_fixture']['total_solves'] = 100000
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'fixture_solve_cap')
        await self.run_fixture()
        self.assertEqual(len(self.calls), 1)

    async def test_headroom_9700_cap_and_aggregate_10000_are_distinct(self):
        self.spend['total_calls'] = 9699
        self.prereg['allocation'].update(headroom_solve_limit=100000, aggregate_solve_limit=100000)
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['allocation_spend']['aggregate_calls_charged'], 10000)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'total_solve_cap')

    async def test_actual_non_headroom_charge_can_hit_aggregate_first(self):
        self.spend['total_calls'] = 9500
        self.prereg['allocation']['aggregate_solve_limit'] = 100000
        self.spend['non_headroom']['calls'] = 499
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'aggregate_solve_cap')

    async def test_aggregate_84_cpu_minutes_includes_non_headroom(self):
        self.prereg['allocation']['aggregate_cpu_minutes'] = 999
        self.spend['non_headroom']['cpu_seconds'] = 5040 - self.spend['cpu_seconds'] - 0.25
        self.cpu_per_call = 0.5
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'aggregate_cpu_cap_below_p95')
        self.assertEqual(result['allocation_spend']['overshoot']['aggregate_cpu_seconds'], 0.0)

    async def test_90_minute_cumulative_wall_cap_and_overshoot(self):
        self.prereg['clock']['solving_wall_minutes'] = 999
        self.spend['solving_wall_seconds'] = 5399.5
        self.wall_per_call = 1.0
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'solving_wall_cap_below_p95')
        self.assertEqual(result['allocation_spend']['overshoot']['solving_wall_seconds'], 0.0)

    async def test_deadline_and_admitted_call_overshoot(self):
        self.now = datetime(2026, 10, 31, 11, 59, 59, tzinfo=timezone.utc)
        self.prereg['clock']['deadline'] = '2026-11-01T12:00:00Z'
        self.wall_per_call = 2.0
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'call_timeout')
        self.assertEqual(result['allocation_spend']['overshoot']['deadline_seconds'], 0.0)
        self.assertEqual(self.last_timeout, 1.0)

    async def test_no_admission_at_deadline(self):
        self.now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')

    async def test_reset_prior_spend_is_refused(self):
        self.spend['fixtures']['ascend910']['cpu_seconds'] = 1440.0
        with self.assertRaisesRegex(ValueError, 'retained cumulative spend'):
            await self.run_fixture()
        self.assertEqual(self.calls, [])

    async def test_infeasible_geometry_never_reaches_oracle(self):
        self.reject_geometry = True
        with self.assertRaisesRegex(ValueError, 'fixture geometry rejected'):
            await self.run_fixture()
        self.assertEqual(self.calls, [])

    def test_prereg_cannot_change_fixture_schedule_error_or_tolerance(self):
        path = self.directory / 'p.json'
        path.write_text(json.dumps(self.prereg))
        self.assertEqual(h._parse_prereg(path)['fixture'], 'micro150')
        for section, field, value in [
                (None, 'fixture', 'ascend910'), (None, 'grid', 64),
                ('reducer_methods', 'seeds', [0]), ('reducer_methods', 'search_evaluations_per_method', 27),
                ('reducer_methods', 'reproduction_evaluations_per_method', 3),
                ('long_sa', 'reproduction_evaluations_per_restart', 0),
                ('domain', 'wire_tolerance_mm', 0.01),
                ('reproduction', 'absolute_tolerance_c', 0.1)]:
            with self.subTest(section=section, field=field):
                prereg = copy.deepcopy(self.prereg)
                (prereg if section is None else prereg[section])[field] = value
                path.write_text(json.dumps(prereg))
                with self.assertRaises(ValueError):
                    h._parse_prereg(path)


if __name__ == '__main__':
    unittest.main()
