"""Synthetic resource-profile and freeze admission proofs; no thermal solves."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sundai_controller import evidence_profile as ep
from sundai_controller import profile_headroom as cli


def identity():
    return {'fixture': 'micro150', 'grid': 32,
            'problem_hash': hashlib.sha256(b'synthetic problem').hexdigest(),
            'solver_version': 'NONPHYSICAL-test',
            'binary_sha256': hashlib.sha256(b'synthetic binary').hexdigest(),
            'config_sha256': hashlib.sha256(b'synthetic config').hexdigest(),
            'source_sha256': hashlib.sha256(b'synthetic source').hexdigest(),
            'image_identity': {'status': 'unavailable', 'reason': 'synthetic test',
                               'dockerfile_sha256': hashlib.sha256(b'synthetic build').hexdigest()}}


def record(call=1, *, sample_identity=None):
    current = identity() if sample_identity is None else sample_identity
    return {'call': call, 'identity': current,
            'result': {'maximum_temperature_c': 100, 'fixture_id': current['fixture'],
                       'grid_rows': current['grid'], 'grid_cols': current['grid'],
                       'problem_hash': current['problem_hash'], 'config_sha256': current['config_sha256'],
                       'solver_version': current['solver_version']},
            'reaping_confirmed': True, 'metered_cpu_seconds': 3.0,
            'raw_directory': f'raw/{call}',
            'phase_timings': {phase: {'cpu_seconds': 0.5, 'wall_seconds': 1.0}
                              for phase in ep.PHASES}}


def prereg():
    # 2 * 2 * (3 + 1) reducer, 1 * 2 * 3 diagnostic, 1 * 5 long = 27.
    return {'fixture': 'micro150', 'grid': 32,
            'reducer_methods': {'methods': ['random', 'greedy'], 'seeds': [0, 1],
                                'search_evaluations_per_method': 3,
                                'reproduction_evaluations_per_method': 1},
            'extra_diagnostics': {'methods': ['ucb1']},
            'long_sa': {'seeds': [100], 'max_evaluations_per_restart': 5,
                        'search_evaluations_per_restart': 4,
                        'reproduction_evaluations_per_restart': 1},
            'evidence_profile': {'reserve_cpu_seconds': 9,
                                 'reserve_reason': 'startup and shutdown plus a runtime stop',
                                 'declared_calls': 27}}


class EvidenceProfileTests(unittest.TestCase):
    def setUp(self):
        self.identity = identity()
        self.prereg = prereg()
        self.profile = ep.build_profile([record()], self.identity)

    def admit(self, available=90):
        return ep.admission(self.prereg, self.profile, available, identity=self.identity)

    def test_fitting_declaration_has_phase_forecast_reserve_and_no_bound_claim(self):
        report = self.admit()
        self.assertEqual(report['declared_calls'], 27)
        self.assertEqual(report['reducer_calls'], 16)
        self.assertEqual(report['diagnostic_calls'], 6)
        self.assertEqual(report['long_calls'], 5)
        self.assertEqual(report['forecast_cpu_seconds'], 81)
        self.assertEqual(report['required_cpu_seconds'], 90)
        self.assertEqual(report['headroom_cpu_seconds'], 0)
        self.assertFalse(report['forecast_is_bound'])
        self.assertTrue(report['requires_runtime_stop'])

    def test_over_cap_declaration_names_shortfall(self):
        with self.assertRaisesRegex(ep.AdmissionRefused, r'shortfall: 0\.250000000 CPU-s.*27 calls'):
            self.admit(89.75)

    def test_profile_means_include_all_measured_phases_and_every_raw_reference(self):
        second = record(2)
        second['phase_timings']['archive']['cpu_seconds'] = 1.5
        second['metered_cpu_seconds'] = 4
        profile = ep.build_profile([record(), second], self.identity)
        self.assertEqual(profile['sample_count'], 2)
        self.assertEqual(profile['metered_cpu_seconds'], 7)
        self.assertEqual(profile['phase_means']['archive']['mean_cpu_seconds'], 1)
        self.assertEqual(profile['phase_means']['solve']['mean_wall_seconds'], 1)
        self.assertEqual(profile['records'][1]['raw_artifact_refs'], {'raw_directory': 'raw/2'})
        canonical = json.dumps(second, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(profile['records'][1]['record_sha256'], hashlib.sha256(canonical).hexdigest())
        second['error'] = 'mutated caller input'
        self.assertNotIn('error', profile['records'][1]['record'])

    def test_failed_and_incomplete_outcomes_keep_charges_and_refuse_admission(self):
        for mutation in ('error', 'missing_result', 'missing_phase', 'unreaped', 'under_metered',
                         'cleanup_error', 'incomplete_status', 'incomplete_profile'):
            with self.subTest(mutation=mutation):
                second = record(2)
                if mutation == 'error':
                    second['error'] = 'solver timed out'
                elif mutation == 'missing_result':
                    second.pop('result')
                elif mutation == 'missing_phase':
                    second['phase_timings'].pop('archive')
                elif mutation == 'unreaped':
                    second['reaping_confirmed'] = False
                elif mutation == 'cleanup_error':
                    second['cleanup_error'] = 'worker close failed'
                elif mutation == 'incomplete_status':
                    second['status'] = 'incomplete'
                elif mutation == 'incomplete_profile':
                    second['profile_complete'] = False
                else:
                    second['metered_cpu_seconds'] = 4
                self.profile = ep.build_profile([record(), second], self.identity)
                self.assertEqual(self.profile['record_count'], 2)
                self.assertEqual(self.profile['excluded_count'], 1)
                self.assertEqual(self.profile['sample_count'], 1)
                self.assertEqual(self.profile['metered_cpu_seconds'], 3 + second['metered_cpu_seconds'])
                self.assertEqual(self.profile['records'][1]['record'], second)
                with self.assertRaisesRegex(ep.AdmissionRefused, 'incomplete/error'):
                    self.admit()

    def test_missing_charge_is_unknown_and_cannot_be_reported_as_zero(self):
        missing = record()
        missing.pop('metered_cpu_seconds')
        profile = ep.build_profile([missing], self.identity)
        self.assertEqual(profile['unknown_charge_count'], 1)
        self.assertFalse(profile['usable_for_admission'])
        self.assertEqual(len(profile['excluded_records']), 1)

    def test_empty_profile_cannot_admit(self):
        self.profile = ep.build_profile([], self.identity)
        with self.assertRaisesRegex(ep.AdmissionRefused, 'sample_count'):
            self.admit()

    def test_every_identity_component_is_bound_to_current_execution(self):
        for field, replacement in (('fixture', 'ascend910'), ('grid', 64),
                                    ('binary_sha256', hashlib.sha256(b'other binary').hexdigest()),
                                    ('config_sha256', hashlib.sha256(b'other config').hexdigest()),
                                    ('source_sha256', hashlib.sha256(b'other source').hexdigest()),
                                    ('image_identity', {'status': 'different image'})):
            with self.subTest(field=field):
                changed = dict(self.identity, **{field: replacement})
                with self.assertRaisesRegex(ep.AdmissionRefused, 'identity differs'):
                    ep.admission(self.prereg, self.profile, 1000, identity=changed)
        with self.assertRaisesRegex(ep.AdmissionRefused, 'identity is required'):
            ep.admission(self.prereg, self.profile, 1000)

    def test_profile_fixture_grid_must_match_preregistration(self):
        for field, value in (('fixture', 'ascend910'), ('grid', 64)):
            with self.subTest(field=field):
                changed = dict(self.prereg, **{field: value})
                with self.assertRaisesRegex(ep.AdmissionRefused, 'fixture/grid'):
                    ep.admission(changed, self.profile, 1000, identity=self.identity)

    def test_missing_or_invalid_phase_means_are_refused(self):
        for value in (None, -1, float('nan'), float('inf'), True, '0.5'):
            for metric in ('mean_cpu_seconds', 'mean_wall_seconds'):
                with self.subTest(value=value, metric=metric):
                    self.profile['phase_means']['generate'][metric] = value
                    with self.assertRaises(ep.AdmissionRefused):
                        self.admit()
                    self.profile = ep.build_profile([record()], self.identity)
        self.profile['phase_means'].pop('worker_startup')
        with self.assertRaisesRegex(ep.AdmissionRefused, 'worker_startup'):
            self.admit()

    def test_invalid_cap_reserve_sample_count_and_zero_cost_are_refused(self):
        for value in (-1, float('nan'), float('inf'), True, '90'):
            with self.subTest(cap=value), self.assertRaises(ep.AdmissionRefused):
                self.admit(value)
        for value in (None, 0, -1, float('nan'), float('inf'), True):
            with self.subTest(reserve=value):
                self.prereg['evidence_profile']['reserve_cpu_seconds'] = value
                with self.assertRaisesRegex(ep.AdmissionRefused, 'reserve_cpu_seconds'):
                    self.admit()
        self.prereg = prereg()
        for value in (0, -1, 0.5, True):
            with self.subTest(sample_count=value):
                self.profile['sample_count'] = value
                with self.assertRaisesRegex(ep.AdmissionRefused, 'sample_count'):
                    self.admit()
        self.profile = ep.build_profile([record()], self.identity)
        for phase in ep.PHASES:
            self.profile['phase_means'][phase]['mean_cpu_seconds'] = 0
        with self.assertRaisesRegex(ep.AdmissionRefused, 'per-call CPU'):
            self.admit()

    def test_reserve_reason_and_declared_call_count_cannot_be_omitted_or_forged(self):
        self.prereg['evidence_profile']['reserve_reason'] = ' '
        with self.assertRaisesRegex(ep.AdmissionRefused, 'reserve_reason'):
            self.admit()
        self.prereg = prereg()
        self.prereg['evidence_profile']['declared_calls'] = 26
        with self.assertRaisesRegex(ep.AdmissionRefused, '26 differs from schedule 27'):
            self.admit()

    def test_schedule_rejects_invalid_counts_and_inconsistent_long_split(self):
        for value in (None, 0, -1, 1.5, True):
            with self.subTest(search=value):
                self.prereg['reducer_methods']['search_evaluations_per_method'] = value
                with self.assertRaises(ep.AdmissionRefused):
                    self.admit()
        self.prereg = prereg()
        self.prereg['long_sa']['search_evaluations_per_restart'] = 5
        with self.assertRaisesRegex(ep.AdmissionRefused, 'differs from maximum'):
            self.admit()

    def test_retained_v4_schedule_is_4768_without_double_counting_reproduction(self):
        path = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/SLAB-039/PREREG-v4.json'
        self.assertEqual(ep.declared_calls(json.loads(path.read_bytes()))['declared_calls'], 4768)

    def test_edited_summary_or_raw_record_cannot_understate_measured_cost(self):
        self.profile['phase_means']['solve']['mean_cpu_seconds'] = 0.1
        with self.assertRaisesRegex(ep.AdmissionRefused, 'phase_means differs from measured'):
            self.admit()
        self.profile = ep.build_profile([record()], self.identity)
        self.profile['records'][0]['record']['metered_cpu_seconds'] = 1
        with self.assertRaisesRegex(ep.AdmissionRefused, 'record SHA-256 differs'):
            self.admit()

    def test_invalid_binary_or_source_identity_is_not_a_measurement_binding(self):
        for field in ('binary_sha256', 'config_sha256', 'source_sha256'):
            with self.subTest(field=field), self.assertRaisesRegex(ep.AdmissionRefused, field):
                ep.build_profile([record()], dict(self.identity, **{field: 'unknown'}))

    def test_foreign_samples_are_excluded_without_erasing_charges(self):
        current = dict(self.identity, fixture='ascend910')
        declaration = dict(self.prereg, fixture='ascend910')
        mutations = (('fixture_id', 'micro150'), ('grid_rows', 64), ('grid_cols', 64),
                     ('problem_hash', hashlib.sha256(b'foreign problem').hexdigest()),
                     ('config_sha256', hashlib.sha256(b'foreign config').hexdigest()),
                     ('solver_version', 'foreign solver'))
        for field, value in mutations:
            with self.subTest(field=field):
                foreign = record(2, sample_identity=current)
                foreign['result'][field] = value
                profile = ep.build_profile([record(sample_identity=current), foreign], current)
                self.assertEqual(profile['sample_count'], 1)
                self.assertEqual(profile['excluded_count'], 1)
                self.assertEqual(profile['metered_cpu_seconds'], 6)
                self.assertEqual(profile['records'][1]['record'], foreign)
                self.assertIn(field, ' '.join(profile['excluded_records'][0]['reasons']))
                with self.assertRaises(ep.AdmissionRefused):
                    ep.admission(declaration, profile, 1000, identity=current)

    def test_relabelled_aggregate_with_rehashed_foreign_sample_cannot_admit(self):
        for field, value in (('fixture', 'ascend910'), ('grid', 64),
                             ('problem_hash', hashlib.sha256(b'foreign problem').hexdigest()),
                             ('binary_sha256', hashlib.sha256(b'foreign binary').hexdigest()),
                             ('source_sha256', hashlib.sha256(b'foreign source').hexdigest()),
                             ('solver_version', 'foreign solver'),
                             ('image_identity', {'status': 'foreign image'})):
            with self.subTest(field=field):
                # A caller edits the embedded sample and rehashes it. All cost
                # summary fields and the aggregate identity still look valid.
                profile = json.loads(json.dumps(self.profile))
                foreign = record(sample_identity=dict(self.identity, **{field: value}))
                entry = profile['records'][0]
                entry['record'] = foreign
                entry['record_sha256'] = hashlib.sha256(ep._json_bytes(foreign)).hexdigest()
                with self.assertRaises(ep.AdmissionRefused):
                    ep.admission(self.prereg, profile, 90, identity=self.identity)

    def test_sample_identity_is_required_and_bound_to_actual_result(self):
        for changed in ('missing', 'problem_hash', 'solver_version'):
            with self.subTest(changed=changed):
                sample = record()
                if changed == 'missing':
                    sample.pop('identity')
                else:
                    sample['identity'].pop(changed)
                profile = ep.build_profile([sample], self.identity)
                self.assertEqual(profile['sample_count'], 0)
                self.assertEqual(profile['metered_cpu_seconds'], 3)
                self.assertFalse(profile['usable_for_admission'])


class ProfileFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.identity = identity()
        self.profile_path = self.root / 'PHASE-PROFILE.json'
        self.profile_path.write_text(json.dumps(ep.build_profile([record()], self.identity)))
        self.prereg = prereg()
        self.prereg['evidence_profile'].update(path='PHASE-PROFILE.json',
            sha256=hashlib.sha256(self.profile_path.read_bytes()).hexdigest())
        self.prereg_path = self.root / 'PREREG.json'
        self.prereg_path.write_text(json.dumps(self.prereg))

    def test_admission_reads_profile_once_and_binds_exact_bytes(self):
        reads = []
        read_bytes = Path.read_bytes
        def measured_read(path):
            reads.append(path)
            return read_bytes(path)
        with patch.object(Path, 'read_bytes', measured_read):
            report = ep.load_admission(self.prereg, self.prereg_path, 90, identity=self.identity)
        self.assertEqual(reads, [self.profile_path])
        self.assertEqual(report['profile_sha256'], self.prereg['evidence_profile']['sha256'])

    def test_changed_profile_bytes_refuse_before_freeze_writes(self):
        self.profile_path.write_bytes(self.profile_path.read_bytes() + b' ')
        output = self.root / 'FROZEN.json'
        with self.assertRaisesRegex(ep.AdmissionRefused, 'SHA-256 differs'):
            ep.freeze(self.prereg_path, output, 90, identity=self.identity)
        self.assertFalse(output.exists())

    def test_missing_profile_requires_explicit_synthetic_opt_out(self):
        self.prereg.pop('evidence_profile')
        with self.assertRaisesRegex(ep.AdmissionRefused, 'required before freeze or start'):
            ep.load_admission(self.prereg, self.prereg_path, 90, identity=self.identity)
        self.assertIsNone(ep.load_admission(self.prereg, self.prereg_path, 90, required=False))

    def test_over_cap_freeze_has_no_output_and_fitting_freeze_is_exclusive(self):
        output = self.root / 'FROZEN.json'
        with self.assertRaisesRegex(ep.AdmissionRefused, 'shortfall'):
            ep.freeze(self.prereg_path, output, 89, identity=self.identity)
        self.assertFalse(output.exists())
        frozen = ep.freeze(self.prereg_path, output, 90, identity=self.identity)
        self.assertEqual(json.loads(output.read_bytes()), frozen)
        self.assertEqual(frozen['source_prereg_sha256'], hashlib.sha256(self.prereg_path.read_bytes()).hexdigest())
        self.assertEqual(frozen['evidence_profile_admission']['required_cpu_seconds'], 90)
        self.assertTrue(ep.load_admission(frozen, output, 90, identity=self.identity)['admitted'])
        before = output.read_bytes()
        with self.assertRaises(FileExistsError):
            ep.freeze(self.prereg_path, output, 90, identity=self.identity)
        self.assertEqual(output.read_bytes(), before)


class ProfileCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.identity = identity()
        self.identity_path = self.root / 'IDENTITY.json'
        self.identity_path.write_text(json.dumps(self.identity))
        self.records_path = self.root / 'calls'
        self.records_path.mkdir()
        self.record_path = self.records_path / '00001.json'
        self.record_path.write_text(json.dumps(record(), indent=2) + '\n')
        self.output = self.root / 'PROFILE.json'

    def test_summarize_cli_retains_source_bytes_digest_and_never_executes_solver(self):
        with patch('sundai_hotspot.tap_oracle.HotSpotOracle') as oracle, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(cli.main(['summarize', '--identity', str(self.identity_path),
                                      '--records', str(self.records_path), '--out', str(self.output)]), 0)
        oracle.assert_not_called()
        profile = json.loads(self.output.read_bytes())
        self.assertTrue(profile['usable_for_admission'])
        self.assertEqual(profile['record_sources'], [
            {'path': str(self.record_path), 'sha256': hashlib.sha256(self.record_path.read_bytes()).hexdigest(),
             'first_record_index': 0, 'record_count': 1}])

    def test_summarize_keeps_incomplete_records_and_never_overwrites_profile(self):
        incomplete = record(2)
        incomplete['status'] = 'incomplete'
        incomplete['cleanup_error'] = 'synthetic close failure'
        self.record_path.write_text(json.dumps([record(), incomplete]))
        report = cli.summarize(self.identity_path, [self.record_path], self.output)
        self.assertEqual(report['record_count'], 2)
        self.assertEqual(report['excluded_count'], 1)
        self.assertFalse(report['usable_for_admission'])
        before = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            cli.summarize(self.identity_path, [self.record_path], self.output)
        self.assertEqual(self.output.read_bytes(), before)

    def test_summarize_rejects_empty_and_duplicate_sources(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with self.assertRaisesRegex(ep.AdmissionRefused, 'no retained'):
            cli.summarize(self.identity_path, [empty], self.output)
        with self.assertRaisesRegex(ep.AdmissionRefused, 'duplicate retained'):
            cli.summarize(self.identity_path, [self.record_path, self.records_path], self.output)
        self.assertFalse(self.output.exists())

    def test_freeze_cli_uses_current_ledger_and_identity_without_a_solve(self):
        cli.summarize(self.identity_path, [self.records_path], self.output)
        declaration = prereg()
        declaration['schema'] = 'slab-039-prereg-v3'
        declaration['allocation'] = {'per_fixture': {'cpu_minutes': 1.5}}
        declaration['evidence_profile'].update(path=str(self.output),
            sha256=hashlib.sha256(self.output.read_bytes()).hexdigest())
        prereg_path, budget_path, frozen_path = [self.root / name for name in ('PREREG.json', 'SPEND.json', 'FROZEN.json')]
        prereg_path.write_text(json.dumps(declaration))
        budget_path.write_text(json.dumps({'cpu_seconds': 0, 'fixtures': {'micro150': {'cpu_seconds': 0}}}))
        fake = MagicMock()
        fake.__call__ = AsyncMock(side_effect=AssertionError('solve forbidden'))
        with patch('sundai_hotspot.tap_oracle.HotSpotOracle', return_value=fake) as oracle, \
                patch('sundai_controller.headroom_evidence.execution_identity', return_value=self.identity):
            report = cli.freeze_declaration(prereg_path, budget_path, frozen_path)
        oracle.assert_called_once_with(32, 32, fixture='micro150')
        fake.__call__.assert_not_called()
        self.assertEqual(report['available_cpu_seconds'], 90)
        frozen_path.unlink()
        budget_path.write_text(json.dumps({'cpu_seconds': 0, 'fixtures': {'micro150': {'cpu_seconds': 1}}}))
        with patch('sundai_hotspot.tap_oracle.HotSpotOracle', return_value=fake), \
                patch('sundai_controller.headroom_evidence.execution_identity', return_value=self.identity), \
                self.assertRaisesRegex(ep.AdmissionRefused, 'shortfall: 1.000000000 CPU-s'):
            cli.freeze_declaration(prereg_path, budget_path, frozen_path)
        self.assertFalse(frozen_path.exists())

    def test_freeze_binds_the_same_prereg_bytes_used_for_capacity(self):
        cli.summarize(self.identity_path, [self.records_path], self.output)
        declaration = prereg()
        declaration['schema'] = 'slab-039-prereg-v3'
        declaration['evidence_profile'].update(path=str(self.output),
            sha256=hashlib.sha256(self.output.read_bytes()).hexdigest())
        prereg_path, budget_path, frozen_path = [self.root / name for name in ('PREREG.json', 'SPEND.json', 'FROZEN.json')]
        original = json.dumps(declaration).encode()
        prereg_path.write_bytes(original)
        budget_path.write_text('{}')
        def identity_replacement(oracle):
            replacement = dict(declaration, grid=64)
            prereg_path.write_text(json.dumps(replacement))
            return self.identity
        with patch('sundai_hotspot.tap_oracle.HotSpotOracle'), \
                patch('sundai_controller.headroom_evidence.execution_identity', side_effect=identity_replacement):
            cli.freeze_declaration(prereg_path, budget_path, frozen_path)
        frozen = json.loads(frozen_path.read_bytes())
        self.assertEqual(frozen['grid'], 32)
        self.assertEqual(frozen['source_prereg_sha256'], hashlib.sha256(original).hexdigest())


if __name__ == '__main__':
    unittest.main()
