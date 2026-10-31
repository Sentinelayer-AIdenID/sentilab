"""SLAB-050 runner integration: synthetic evaluations, never thermal solves."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sundai_controller import headroom as h
from sundai_controller import headroom_evidence as e
from sundai_controller import headroom_supervisor as s
from sundai_controller.test_headroom import CountingOracle
from sundai_controller.evidence_profile import AdmissionRefused


class EvidenceRunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prereg = {'schema': 'slab-039-prereg-v3', 'fixture': 'ascend910', 'grid': 32,
                       'rule': {'k': 5}, 'reducer_methods': {'methods': ['random'], 'seeds': [0],
                           'search_evaluations_per_method': 3, 'reproduction_evaluations_per_method': 2},
                       'long_sa': {'seeds': [1], 'max_evaluations_per_restart': 2, 'max_cpu_minutes': 1}}

    def budget(self):
        budget = h.SolveBudget(self.root / 'SPEND.json', 'ascend910', self.prereg)
        self.addCleanup(budget.close)
        budget.artifact_dir = self.root / 'attempt'
        return budget

    async def test_noop_proposals_skip_calls_but_fresh_reproductions_still_run(self):
        oracle = CountingOracle()
        initial = oracle.design_from_centers(h.TAP_INITIAL_CENTERS)
        original = h._candidate
        attempts = 0
        def candidate(*args):
            nonlocal attempts
            attempts += 1
            if attempts <= 3:
                return args[0], 'move', {}
            return original(*args)
        budget = self.budget()
        with patch.object(h, '_candidate', side_effect=candidate), patch.object(h.os, 'fsync'):
            result = await h._run_lane(initial, oracle, 'random', 17, 3, [initial],
                                       'skip-check', budget=budget, reproduction_evaluations=2)
        self.assertTrue(result['complete'])
        self.assertGreaterEqual(result['noop_skipped'], 3)
        self.assertEqual(result['noop_evaluations'], 0)
        self.assertEqual(len(oracle.calls), 5)
        self.assertEqual(oracle.calls[-2:], [result['best_design_hash']] * 2)
        self.assertEqual(budget.state['total_calls'], 5)
        events = (budget.artifact_dir / 'lanes/skip-check.ndjson').read_text()
        self.assertIn('noop_skipped', events)

    async def test_cleanup_failure_retains_incomplete_outcome_and_charge(self):
        class BrokenCleanup(CountingOracle):
            async def aclose(self):
                raise RuntimeError('synthetic reap failure')
        oracle = BrokenCleanup()
        budget = self.budget()
        counted = h._LaneOracle(oracle, budget, 'cleanup', 1)
        with self.assertRaisesRegex(RuntimeError, 'synthetic reap failure'):
            await counted(oracle.design_from_centers(h.TAP_INITIAL_CENTERS))
        receipt = json.loads((budget.artifact_dir / 'evaluations/00001.json').read_bytes())
        self.assertEqual(receipt['status'], 'incomplete')
        self.assertIn('synthetic reap failure', receipt['error'])
        self.assertGreater(receipt['metered_cpu_seconds'], 0)
        self.assertEqual(budget.state['total_calls'], 1)
        self.assertIsNone(budget.state['active'])
        self.assertIn('synthetic reap failure', budget.path.with_suffix('.runs.jsonl').read_text())

    async def test_call_error_keeps_started_raw_directory_and_ledger(self):
        class Broken(CountingOracle):
            async def __call__(self, design):
                (self.retained_output_root / 'native-partial.bin').write_bytes(b'partial-native-evidence')
                raise RuntimeError('synthetic native failure')
        budget = self.budget()
        oracle = Broken()
        with self.assertRaisesRegex(RuntimeError, 'synthetic native failure'):
            await h._LaneOracle(oracle, budget, 'failed', 1)(oracle.design_from_centers(h.TAP_INITIAL_CENTERS))
        receipt = json.loads((budget.artifact_dir / 'evaluations/00001.json').read_bytes())
        self.assertEqual(receipt['status'], 'incomplete')
        self.assertEqual((Path(receipt['raw_output_directory']) / 'native-partial.bin').read_bytes(),
                         b'partial-native-evidence')
        self.assertEqual(budget.state['metered_runs'], 1)
        self.assertGreaterEqual(budget.state['cpu_seconds'], receipt['metered_cpu_seconds'])

    async def test_real_entry_refuses_missing_profile_before_any_call_or_artifact(self):
        class ProductionMarker(CountingOracle):
            requires_evidence_profile = True
        prereg = self.root / 'prereg.json'
        prereg.write_text(json.dumps(self.prereg))
        with patch.object(e, 'execution_identity', return_value={'synthetic': True}), \
                patch.object(ProductionMarker, '__call__') as call:
            with self.assertRaisesRegex(AdmissionRefused, 'required before freeze or start'):
                await h.run_headroom('ascend910', .16, prereg, self.root / 'out', oracle_factory=ProductionMarker)
        call.assert_not_called()
        self.assertFalse((self.root / 'out').exists())
        self.assertFalse((self.root / 'SPEND.json').exists())

    async def test_fitting_profile_admits_run_and_retains_attempt(self):
        from sundai_controller.test_evidence_profile import identity, record
        from sundai_controller.evidence_profile import build_profile
        import hashlib
        class ProductionMarker(CountingOracle):
            requires_evidence_profile = True
        current = dict(identity(), fixture='ascend910')
        profile = self.root / 'profile.json'
        profile.write_text(json.dumps(build_profile([record(sample_identity=current)], current)))
        self.prereg['evidence_profile'] = {'path': profile.name,
            'sha256': hashlib.sha256(profile.read_bytes()).hexdigest(),
            'reserve_cpu_seconds': 2, 'reserve_reason': 'synthetic setup and settlement'}
        prereg = self.root / 'prereg.json'
        prereg.write_text(json.dumps(self.prereg))
        import os
        relative_output = Path(os.path.relpath(self.root / 'out', Path.cwd()))
        with patch.object(e, 'execution_identity', return_value=current), patch.object(h.os, 'fsync'):
            result = await h.run_headroom('ascend910', .16, prereg, relative_output,
                                          oracle_factory=ProductionMarker)
        self.assertTrue(result['evidence_profile_admission']['admitted'])
        self.assertEqual(result['aggregate_evaluations'], 7)
        attempt = Path(result['artifact_directory'])
        self.assertEqual(len(list((attempt / 'evaluations').glob('*.json'))), 7)
        first = json.loads((attempt / 'evaluations/00001.json').read_bytes())
        self.assertTrue(Path(first['raw_output_directory']).is_absolute())
        self.assertEqual(first['identity'], current)
        self.assertTrue((attempt / 'PHASE_PROFILE.json').exists())
        self.assertEqual(json.loads((attempt / 'PHASE_PROFILE.json').read_bytes())['record_count'], 7)

    async def run_partition_case(self, *, mesh=0, noops=False, report_error=False):
        from contextlib import ExitStack
        from sundai_controller.evidence_profile import declared_calls
        self.prereg['reducer_methods'].update(search_evaluations_per_method=3,
                                              reproduction_evaluations_per_method=1)
        self.prereg['long_sa'].update(max_evaluations_per_restart=5,
                                     search_evaluations_per_restart=4,
                                     reproduction_evaluations_per_restart=1)
        self.prereg['evidence_profile'] = {'synthetic': 'admission isolated in execution test'}
        path = self.root / 'partition.json'
        path.write_text(json.dumps(self.prereg))
        with ExitStack() as stack:
            stack.enter_context(patch('sundai_controller.evidence_profile.load_admission',
                                      return_value=declared_calls(self.prereg)))
            stack.enter_context(patch.object(h.os, 'fsync'))
            if noops:
                stack.enter_context(patch.object(h, '_shared_designs', side_effect=lambda initial, *a: [initial]))
                stack.enter_context(patch.object(h, '_candidate', side_effect=lambda parent, *a: (parent, 'move', {})))
            if report_error:
                stack.enter_context(patch.object(h, '_write_report', side_effect=OSError('report disk failure')))
            return await h.run_headroom('ascend910', mesh, path, self.root / 'out', oracle_factory=CountingOracle)

    async def test_new_v3_executes_declared_long_search_and_fresh_reproduction(self):
        result = await self.run_partition_case()
        lane = result['long_sa_results'][0]
        self.assertEqual(result['aggregate_evaluations'], 9)
        self.assertEqual(lane['search_evaluation_count'], 4)
        self.assertEqual(lane['reproduction_evaluation_count'], 1)
        self.assertEqual(lane['reproductions'][0]['design_hash'], lane['best_design_hash'])
        records = [json.loads(path.read_bytes()) for path in
                   sorted((Path(result['artifact_directory']) / 'evaluations').glob('*.json'))]
        self.assertEqual(records[-1]['design_hash'], lane['best_design_hash'])
        self.assertEqual(records[-1]['call'], 9)
        self.assertTrue(lane['complete'])

    async def test_new_v3_verdicts_have_durable_terminal_attempts(self):
        for verdict, mesh, noops in (('PASS', 0, False), ('FAIL', 1000000, False), ('INCONCLUSIVE', 0, True)):
            with self.subTest(verdict=verdict):
                result = await self.run_partition_case(mesh=mesh, noops=noops)
                self.assertEqual(result['verdict'], verdict)
                state = json.loads((self.root / 'SPEND.json').read_bytes())
                attempt = state['attempts'][-1]
                self.assertEqual(attempt['status'], 'finished')
                self.assertEqual(attempt['verdict'], verdict)
                self.assertEqual(attempt['ending_calls'], state['total_calls'])
                self.assertEqual(result['allocation_spend']['attempts'][-1], attempt)
                self.assertIsNone(state['active'])

    async def test_result_persistence_failure_closes_attempt_and_releases_ledger(self):
        with self.assertRaisesRegex(OSError, 'report disk failure'):
            await self.run_partition_case(report_error=True)
        state = json.loads((self.root / 'SPEND.json').read_bytes())
        self.assertEqual(state['attempts'][-1]['status'], 'failed')
        self.assertEqual(state['attempts'][-1]['ending_calls'], 9)
        self.budget()  # A second owner can acquire the released ledger lock.

    async def test_start_rechecks_capacity_after_acquiring_ledger_lock(self):
        from sundai_controller.test_evidence_profile import identity, record
        from sundai_controller.evidence_profile import build_profile
        import hashlib
        class ProductionMarker(CountingOracle):
            requires_evidence_profile = True
        current = dict(identity(), fixture='ascend910')
        profile = self.root / 'profile.json'
        profile.write_text(json.dumps(build_profile([record(sample_identity=current)], current)))
        self.prereg['evidence_profile'] = {'path': profile.name,
            'sha256': hashlib.sha256(profile.read_bytes()).hexdigest(),
            'reserve_cpu_seconds': 2, 'reserve_reason': 'synthetic setup and settlement'}
        prereg = self.root / 'prereg.json'
        prereg.write_text(json.dumps(self.prereg))
        budget_type = h.SolveBudget
        def competing_spend(*args):
            budget = budget_type(*args)
            budget.state['cpu_seconds'] = 1439
            budget.entry['cpu_seconds'] = 1439
            return budget
        with patch.object(e, 'execution_identity', return_value=current), \
                patch.object(h, 'SolveBudget', side_effect=competing_spend), \
                patch.object(ProductionMarker, '__call__') as call:
            with self.assertRaisesRegex(AdmissionRefused, 'CPU cap shortfall'):
                await h.run_headroom('ascend910', .16, prereg, self.root / 'out', oracle_factory=ProductionMarker)
        call.assert_not_called()
        self.assertFalse((self.root / 'out').exists())

    async def test_profile_failure_still_closes_and_charges_ledger(self):
        import fcntl
        class ProductionMarker(CountingOracle):
            requires_evidence_profile = True
        prereg = self.root / 'prereg.json'
        prereg.write_text(json.dumps(self.prereg))
        with patch.object(e, 'execution_identity', return_value={'image_identity': {}}), \
                patch('sundai_controller.evidence_profile.load_admission', return_value={'declared_calls': 7}), \
                patch('sundai_controller.evidence_profile.build_profile', side_effect=ValueError('profile fault')), \
                patch.object(h.os, 'fsync'):
            with self.assertRaisesRegex(ValueError, 'profile fault'):
                await h.run_headroom('ascend910', .16, prereg, self.root / 'out', oracle_factory=ProductionMarker)
        state = json.loads((self.root / 'SPEND.json').read_bytes())
        self.assertEqual(state['total_calls'], 7)
        self.assertGreater(state['cpu_seconds'], 0)
        with (self.root / 'SPEND.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    async def test_setup_archive_failure_closes_ledger_and_records_charge(self):
        import fcntl
        class ProductionMarker(CountingOracle):
            requires_evidence_profile = True
        prereg = self.root / 'prereg.json'
        prereg.write_text(json.dumps(self.prereg))
        write = h._write_json
        def fault(path, value):
            if path.name == 'IDENTITY.json':
                raise OSError('identity archive fault')
            return write(path, value)
        with patch.object(e, 'execution_identity', return_value={'image_identity': {}}), \
                patch('sundai_controller.evidence_profile.load_admission', return_value={'declared_calls': 7}), \
                patch.object(h, '_write_json', side_effect=fault):
            with self.assertRaisesRegex(OSError, 'identity archive fault'):
                await h.run_headroom('ascend910', .16, prereg, self.root / 'out', oracle_factory=ProductionMarker)
        state = json.loads((self.root / 'SPEND.json').read_bytes())
        self.assertEqual(state['total_calls'], 0)
        self.assertGreater(state['cpu_seconds'], 0)
        self.assertEqual(state['attempts'][-1]['status'], 'setup_failed')
        with (self.root / 'SPEND.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    async def test_all_noops_end_as_bounded_incomplete_lane(self):
        oracle = CountingOracle()
        initial = oracle.design_from_centers(h.TAP_INITIAL_CENTERS)
        budget = self.budget()
        with patch.object(h, '_candidate', return_value=(initial, 'move', {})), patch.object(h.os, 'fsync'):
            result = await h._run_lane(initial, oracle, 'greedy', 0, 2, [initial], 'all-noops', budget=budget)
        self.assertFalse(result['complete'])
        self.assertEqual(result['stop_reason'], 'proposal_attempt_cap')
        self.assertEqual(result['evaluation_count'], 1)
        self.assertEqual(len(oracle.calls), 1)

    def test_historical_charges_reduce_admission_allowance(self):
        prereg = dict(self.prereg, allocation={'headroom_cpu_minutes': 25,
                                              'per_fixture': {'cpu_minutes': 24}})
        state = {'cpu_seconds': 50, 'fixtures': {'ascend910': {'cpu_seconds': 12}}}
        self.assertEqual(e.available_cpu(prereg, state), 1428)
        self.assertEqual(state['cpu_seconds'], 50)


class SupervisorAdmissionTests(unittest.TestCase):
    def test_missing_profile_refuses_before_reservation_or_launch(self):
        from dataclasses import asdict
        evidence = h.ROOT / 'docs/sentilab/evidence/SLAB-039'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            budget = root / 'SPEND.json'
            original = (evidence / 'SPEND.json').read_bytes()
            budget.write_bytes(original)
            policy = root / 'policy.json'
            policy.write_text(json.dumps({'status': 'approved', 'approved_by': 'synthetic-test-only',
                'limits': asdict(s.Policy(measured_observation_plus_kill_seconds=.6)),
                'latency_measurement_evidence': 'synthetic-test-only',
                'accept_unbounded_scheduler_and_cleanup_risk': True}))
            with patch.object(s, 'verify_cpu_max', return_value={'rate_q': 1}), \
                    patch.object(s, 'supervise') as launch:
                with self.assertRaisesRegex(AdmissionRefused, 'required before freeze or start'):
                    s.run(evidence / 'PREREG-v4.json', budget, root / 'out', policy)
            launch.assert_not_called()
            self.assertEqual(budget.read_bytes(), original)
            self.assertFalse((root / 'out').exists())

    def test_forced_stop_rebuilds_incomplete_profile_and_preserves_settlement_charge(self):
        from dataclasses import asdict
        from sundai_controller.test_evidence_profile import record, identity
        evidence = h.ROOT / 'docs/sentilab/evidence/SLAB-039'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            budget = root / 'SPEND.json'
            original = json.loads((evidence / 'SPEND.json').read_bytes())
            budget.write_text(json.dumps(original))
            policy = root / 'policy.json'
            policy.write_text(json.dumps({'status': 'approved', 'approved_by': 'synthetic-test-only',
                'limits': asdict(s.Policy(measured_observation_plus_kill_seconds=.6)),
                'latency_measurement_evidence': 'synthetic-test-only',
                'accept_unbounded_scheduler_and_cleanup_risk': True}))
            out = root / 'out'
            def stopped(*args, **kwargs):
                attempt = out / 'attempt-synthetic'
                directory = attempt / 'evaluations'
                directory.mkdir(parents=True)
                (directory / '00001.json').write_text(json.dumps(record()))
                (directory / '00002.json').write_text(json.dumps({'call': 2, 'status': 'started'}))
                (directory / '00003.json').write_text('{partial')
                state = json.loads(budget.read_bytes())
                state.setdefault('attempts', []).append({'artifact_directory': str(attempt)})
                budget.write_text(json.dumps(state))
                return {'status': 'stopped', 'returncode': -9, 'metered_cpu_seconds': 7,
                        'reaping_confirmed': True, 'latency_assumptions_met': True}
            with patch.object(e, 'execution_identity', return_value=identity()), \
                    patch.object(s, 'verify_cpu_max', return_value={'rate_q': 1}), \
                    patch('sundai_controller.evidence_profile.load_admission', return_value={'declared_calls': 4768}), \
                    patch.object(s, 'supervise', side_effect=stopped), patch.object(s.LinuxTree, 'cpu', return_value=7):
                receipt = s.run(evidence / 'PREREG-v4.json', budget, out, policy)
            profile = json.loads(next(out.glob('PHASE_PROFILE-*.json')).read_bytes())
            self.assertEqual(profile['record_count'], 4)
            self.assertEqual(profile['sample_count'], 1)
            self.assertFalse(profile['usable_for_admission'])
            self.assertEqual(profile['excluded_count'], 3)
            self.assertTrue((out / profile['supervisor_settlement']).exists())
            state = json.loads(budget.read_bytes())
            self.assertGreaterEqual(state['cpu_seconds'], original['cpu_seconds'] + 7)
            self.assertFalse(receipt['result_accepted'])


class ForecastCapacityTests(unittest.TestCase):
    def test_call_cap_refuses_even_when_cpu_would_fit(self):
        prereg = {'schema': 'slab-039-prereg-v3', 'fixture': 'ascend910',
                  'allocation': {'per_fixture': {'total_solves': 10}}}
        state = {'total_calls': 4, 'fixtures': {'ascend910': {'calls': 4}}}
        with self.assertRaisesRegex(ValueError, 'shortfall: 1 calls'):
            e.check_declared_calls(prereg, state, 7)
        e.check_declared_calls(prereg, state, 6)

    def test_nonfinite_charge_cannot_be_ignored_by_minimum(self):
        prereg = {'schema': 'slab-039-prereg-v3', 'fixture': 'ascend910'}
        for value in (float('nan'), float('inf'), -1, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'finite and nonnegative'):
                e.available_cpu(prereg, {'fixtures': {'ascend910': {'cpu_seconds': value}}})
            with self.subTest(non_headroom=value), self.assertRaisesRegex(ValueError, 'finite and nonnegative'):
                e.available_cpu(prereg, {'non_headroom': {'cpu_seconds': value}})

    def test_image_identity_records_host_digest_and_rejects_invalid_values(self):
        import hashlib
        import os
        from sundai_hotspot.tap_oracle import HotSpotOracle
        oracle = HotSpotOracle()
        digest = 'sha256:' + hashlib.sha256(b'synthetic image identity').hexdigest()
        with patch.dict(os.environ, {'SENTILAB_IMAGE_DIGEST': digest}):
            self.assertEqual(e.execution_identity(oracle)['image_identity']['digest'], digest)
            self.assertEqual(e.execution_identity(oracle)['image_identity']['status'], 'host_declared')
        with patch.dict(os.environ, {'SENTILAB_IMAGE_DIGEST': 'not-an-image-digest'}):
            with self.assertRaisesRegex(ValueError, 'resolved sha256'):
                e.execution_identity(oracle)
