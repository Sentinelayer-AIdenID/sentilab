"""Tests call the shipped generator, statistics, checker and real HotSpot runner."""
import asyncio
import copy
from contextlib import redirect_stdout
import io
from dataclasses import asdict, replace
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sundai_controller import mesh_study as mesh
from sundai_hotspot.tap_oracle import HotSpotThermalResult


def fake_thermal_result(oracle, design):
    return HotSpotThermalResult(
        design.hash, 100.0, oracle.solver_version, converged=True, cost_microdollars=0,
        problem_hash=oracle.problem_hash, wirelength_mm=10.0, wire_metric='test-only',
        heatmap_c=tuple((100.0,) * oracle.grid_cols for _ in range(oracle.grid_rows)),
        grid_rows=oracle.grid_rows, grid_cols=oracle.grid_cols, ambient_c=40.0,
        solver_seconds=0.05, evaluation_seconds=0.1, input_generation_seconds=0.02,
        input_sha256=(('sample.ptrace', hashlib.sha256(b'synthetic-input').hexdigest()),),
        all_layers_peak_c=101.0)


class MeshAccountingTests(unittest.TestCase):
    def test_cpu_accounting_includes_reaped_grandchild(self):
        # Use real processes, without spending any HotSpot solver executions.
        burn = 'import time; start = time.process_time()\nwhile time.process_time() - start < 0.15: pass'
        worker = ('import subprocess, sys\n'
                  f'subprocess.run([sys.executable, "-c", {burn!r}], check=True)')
        start = mesh.cpu_usage()
        subprocess.run([sys.executable, '-c', worker], check=True)
        accounting = mesh.run_accounting(start, 0)
        self.assertEqual(accounting['solver_executions'], 0)
        self.assertEqual(accounting['warmup_solver_executions'], 0)
        self.assertGreaterEqual(accounting['children_cpu_seconds'], 0.1)
        self.assertGreaterEqual(accounting['process_cpu_seconds'], 0)
        self.assertAlmostEqual(accounting['cpu_seconds'], accounting['process_cpu_seconds']
                               + accounting['children_cpu_seconds'])
        self.assertAlmostEqual(accounting['cpu_minutes'], accounting['cpu_seconds'] / 60)
        empty = mesh.run_accounting(mesh.cpu_usage(), 0)
        self.assertLess(empty['children_cpu_seconds'], 0.01)


class MeshStatisticsTests(unittest.TestCase):
    def test_resolution_uses_reference_gaps_including_coarse_ties(self):
        rows = [{'id': str(i), 'J_c': {'32': coarse, '64': fine}}
                for i, (coarse, fine) in enumerate(zip([2, 1, 6, 6], [0, 2, 5, 9]))]
        summary = mesh.summarize(rows, [32, 64], 0.01)
        # The reversal spans 2 C; the coarse tie loses a larger 4 C fine gap.
        self.assertEqual(summary['comparisons']['32']['max_misordered_reference_gap_c'], 4)
        for row in rows:
            row['J_c']['32'] = row['J_c']['64']
        ordered = mesh.summarize(rows, [32, 64], 0.01)
        self.assertEqual(ordered['comparisons']['32']['max_misordered_reference_gap_c'], 0)

    def test_mesh_error_uses_maximum_absolute_difference(self):
        self.assertEqual(mesh.mesh_error([8, 14, 9], [10, 10, 10]), 4)

    def test_rank_catches_inversion_and_coarse_tie(self):
        rank = mesh.rank_agreement([30, 10, 10], [10, 20, 30], 1)
        self.assertEqual(rank['violations'], 3)
        self.assertEqual(rank['inversions'], 2)
        self.assertEqual(rank['coarse_ties'], 1)
        self.assertEqual(rank['eligible_pairs'], 3)
        self.assertFalse(rank['passes'])

    def test_tolerance_boundary_and_no_eligible_pairs(self):
        rank = mesh.rank_agreement([3, 2, 1], [0, 2, 4], 2)
        self.assertEqual(rank['eligible_pairs'], 1)
        self.assertEqual(rank['excluded_pairs'], 2)
        self.assertEqual(rank['violations'], 1)
        empty = mesh.rank_agreement([1, 0], [0, 1], 1)
        self.assertIsNone(empty['agreement_fraction'])
        self.assertIsNone(empty['passes'])
        decimal = mesh.rank_agreement([3, 2, 1], [117.17, 117.18, 117.20], 0.01)
        self.assertEqual(decimal['eligible_pairs'], 2)

    def test_invalid_numeric_inputs_fail_closed(self):
        for coarse, fine in [([], []), ([1], [1, 2]), ([float('nan')], [1]),
                             ([1], [float('inf')]), ([True], [1])]:
            with self.subTest(coarse=coarse, fine=fine), self.assertRaises(ValueError):
                mesh.mesh_error(coarse, fine)
        for tolerance in [-1, float('nan'), float('inf'), True]:
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                mesh.rank_agreement([1, 2], [1, 2], tolerance)

    def test_result_checker_detects_planted_inversion(self):
        rows = [{'id': str(i), 'J_c': {'16': v + 0.5, '32': v + 0.1, '64': v}}
                for i, v in enumerate([10., 20., 30.])]
        result = {'grids': [16, 32, 64], 'layouts': rows, 'fixed_tolerance_c': 0.01}
        identity = {'hotspot_binary_sha256': 'test-binary', 'generator_sha256': [['source', 'test-source']]}
        result['evaluator_identity'] = identity
        result['provenance'] = {str(g): {'problem': identity} for g in result['grids']}
        result['summary'] = mesh.summarize(rows, result['grids'], 0.01)
        self.assertEqual(mesh.check_result(result), [])
        altered = copy.deepcopy(result)
        altered['layouts'][0]['J_c']['32'] = 40.
        errors = mesh.check_result(altered)
        self.assertTrue(any('32' in error and 'inversion' in error for error in errors), errors)
        self.assertTrue(any('summary' in error for error in errors), errors)


class MeshLayoutTests(unittest.TestCase):
    def test_seeded_legal_balanced_unique_layouts(self):
        frozen = mesh.make_layout_set('ascend910', 1, 24)
        self.assertEqual(frozen, mesh.make_layout_set('ascend910', 1, 24))
        self.assertNotEqual(frozen['layouts'], mesh.make_layout_set('ascend910', 2, 24)['layouts'])
        oracle = mesh.make_oracle('ascend910', 16)
        self.assertEqual(len({row['design_hash'] for row in frozen['layouts']}), 24)
        for category in mesh.CATEGORIES:
            self.assertEqual(sum(row['category'] == category for row in frozen['layouts']), 8)
        for row in frozen['layouts']:
            design = oracle.design_from_centers(row['centers_mm'])
            design.check()
            oracle.centers_for(design)
            self.assertEqual(design.hash, row['design_hash'])
        cluster = [r['mean_pair_distance_mm'] for r in frozen['layouts'] if r['category'] == 'clustered']
        spread = [r['mean_pair_distance_mm'] for r in frozen['layouts'] if r['category'] == 'spread']
        self.assertLess(max(cluster), min(spread))

    def test_freeze_is_immutable_and_hash_checked(self):
        frozen = mesh.make_layout_set('ascend910', 1, 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'layouts.json'
            mesh.freeze_layouts(path, frozen)
            self.assertEqual(mesh.load_layouts(path)[0], frozen)
            with self.assertRaises(FileExistsError):
                mesh.freeze_layouts(path, mesh.make_layout_set('ascend910', 2, 4))
            path.write_text(path.read_text() + ' ', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'sha256'):
                mesh.load_layouts(path)

    def test_fixture_and_size_validation(self):
        for fixture in ['micro150', '../ascend910', 'unknown']:
            with self.subTest(fixture=fixture), self.assertRaises(ValueError):
                mesh.make_layout_set(fixture, 1, 4)
        for n in [0, 2, True]:
            with self.subTest(n=n), self.assertRaises(ValueError):
                mesh.make_layout_set('ascend910', 1, n)


class MeshIdentityTests(unittest.TestCase):
    def test_rejects_changed_evaluator_before_evaluating_next_grid(self):
        frozen, _ = mesh.load_layouts(mesh.EVIDENCE_ROOT / 'ascend910/layouts.json')
        make_oracle = mesh.make_oracle
        for field, value in [('hotspot_binary_sha256', 'changed-binary'),
                             ('generator_sha256', (('changed-source', 'changed-hash'),))]:
            calls = []

            def factory(fixture, grid):
                oracle = make_oracle(fixture, grid)
                if grid == 64:
                    oracle.problem = replace(oracle.problem, **{field: value})
                return oracle

            async def fake_call(oracle, design):
                calls.append(oracle.grid_rows)
                return fake_thermal_result(oracle, design)

            with self.subTest(field=field), patch.object(mesh, 'make_oracle', factory), \
                    patch.object(mesh.HotSpotOracle, '__call__', fake_call), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, 'evaluator identity changed'):
                    asyncio.run(mesh.evaluate_layouts(
                        frozen, [32, 64], ['clustered-01', 'spread-01'], evidence_dir=Path(directory)))
                self.assertEqual(calls, [32, 32])

    def test_checker_rejects_cross_grid_identity_changes(self):
        path = mesh.EVIDENCE_ROOT / 'ascend910/RESULT.json'
        recorded = json.loads(path.read_text())
        self.assertEqual(mesh.check_result(recorded), [])
        for field in ('hotspot_binary_sha256', 'generator_sha256'):
            altered = copy.deepcopy(recorded)
            altered['provenance']['64']['problem'][field] = 'changed'
            with self.subTest(field=field):
                self.assertTrue(any('evaluator identity' in error
                                    for error in mesh.check_result(altered)))


class MeshReceiptTests(unittest.TestCase):
    def setUp(self):
        # Explicit test provenance keeps these synthetic runs independent of Git.
        self.revision = '248e6e640a9bfecbca04760a9a3f82355e3072bb'
        environment = patch.dict(mesh.os.environ, {'BUILD_SHA': self.revision})
        environment.start()
        self.addCleanup(environment.stop)

    def complete_fake_run(self, output):
        async def fake_call(oracle, design):
            return fake_thermal_result(oracle, design)

        with patch.object(mesh.HotSpotOracle, '__call__', fake_call), redirect_stdout(io.StringIO()):
            self.assertEqual(mesh.main(['--grids', '32', '64', '--layout-ids',
                'clustered-01', 'spread-01', '--output-dir', str(output)]), 0)
        result = json.loads((output / 'RESULT.json').read_text())
        records = [json.loads(line) for line in (output / 'rows.jsonl').read_text().splitlines()]
        self.assertEqual(mesh.check_result(result, output), [])
        return result, records

    def rewrite_journal(self, output, result, records):
        # Rehash mutations so the checker must validate content, not stale hashes.
        data = ''.join(json.dumps(record, sort_keys=True) + '\n' for record in records).encode()
        (output / 'rows.jsonl').write_bytes(data)
        result['rows_evidence']['sha256'] = hashlib.sha256(data).hexdigest()

    def test_receipt_heatmap_peak_uses_absolute_oracle_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result, records = self.complete_fake_run(output)
            for cell, valid in [(101.0, False), (100.0 + 2e-9, False),
                                (100.0 + 5e-10, True), (99.0, True)]:
                with self.subTest(cell=cell):
                    changed = copy.deepcopy(records)
                    entry = next(r for r in changed if r['kind'] == 'evaluation')
                    heatmap = entry['parsed_receipt']['heatmap_c']
                    heatmap[0][0] = cell
                    entry['heatmap_sha256'] = hashlib.sha256(mesh._json_bytes(heatmap)).hexdigest()
                    self.rewrite_journal(output, result, changed)
                    errors = mesh.check_result(result, output)
                    if valid:
                        self.assertEqual(errors, [])
                    else:
                        self.assertTrue(any('heatmap peak' in error for error in errors), errors)

    def test_receipt_heatmap_requires_finite_grid_shaped_numbers(self):
        heatmap = [[100.0] * 32 for _ in range(32)]
        cases = [('missing-row', heatmap[:-1]), ('extra-row', heatmap + [heatmap[0]]),
                 ('short-row', [heatmap[0][:-1]] + heatmap[1:]),
                 ('long-row', [heatmap[0] + [100.0]] + heatmap[1:]),
                 ('non-list-row', [100.0] + heatmap[1:]), ('empty', []), ('non-list', 100.0)]
        for value in (True, '100', None, float('nan'), float('inf'), float('-inf')):
            changed = copy.deepcopy(heatmap)
            changed[0][0] = value
            cases.append((repr(value), changed))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result, records = self.complete_fake_run(output)
            for name, heatmap in cases:
                with self.subTest(case=name):
                    changed = copy.deepcopy(records)
                    entry = next(r for r in changed if r['kind'] == 'evaluation')
                    entry['parsed_receipt']['heatmap_c'] = heatmap
                    # Permit non-finite JSON here specifically to exercise malformed evidence.
                    data = (json.dumps(heatmap, indent=2, sort_keys=True) + '\n').encode()
                    entry['heatmap_sha256'] = hashlib.sha256(data).hexdigest()
                    self.rewrite_journal(output, result, changed)
                    errors = mesh.check_result(result, output)
                    self.assertTrue(errors, name)

    def test_result_must_match_run_header(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result, records = self.complete_fake_run(output)
            for field, value in [('fixture', 'micro150'), ('grids', [64, 32]),
                                 ('layouts_sha256', '0' * 64)]:
                with self.subTest(result_field=field):
                    changed = copy.deepcopy(result)
                    changed[field] = value
                    self.assertTrue(any('run header' in error for error in mesh.check_result(changed, output)))
            with self.subTest(result_field='layouts'):
                changed = copy.deepcopy(result)
                changed['layouts'].reverse()
                self.assertTrue(any('run header' in error for error in mesh.check_result(changed, output)))
            # The one-field RESULT mutation must fail with the journal untouched.
            changed = copy.deepcopy(result)
            changed['layouts_sha256'] = '0' * 64
            (output / 'RESULT.json').write_bytes(mesh._json_bytes(changed))
            with self.subTest(case='one-field-cli-mutation'), redirect_stdout(io.StringIO()):
                self.assertEqual(mesh.main(['--check', str(output / 'RESULT.json')]), 1)
            for field, value in [('fixture', 'micro150'), ('grids', [16, 32, 64]),
                                 ('layout_ids', ['clustered-01']), ('layouts_sha256', '0' * 64),
                                 ('expected_evaluations', 5)]:
                with self.subTest(header_field=field):
                    changed = copy.deepcopy(records)
                    changed[0][field] = value
                    self.rewrite_journal(output, result, changed)
                    self.assertTrue(any('run header' in error for error in mesh.check_result(result, output)))

    def test_receipt_coverage_is_complete_and_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result, records = self.complete_fake_run(output)
            for case in ('extra', 'missing', 'duplicate', 'reused-sequence', 'extra-sequence', 'bool-sequence'):
                with self.subTest(case=case):
                    changed = copy.deepcopy(records)
                    altered = copy.deepcopy(result)
                    evaluations = [r for r in changed if r['kind'] == 'evaluation']
                    if case == 'extra':
                        extra = copy.deepcopy(evaluations[-1])
                        extra['sequence'] = 5
                        changed.insert(-1, extra)
                    elif case == 'missing':
                        changed.remove(evaluations[-1])
                    elif case == 'duplicate':
                        duplicate = copy.deepcopy(evaluations[0])
                        duplicate['sequence'] = 4
                        changed[changed.index(evaluations[-1])] = duplicate
                    else:
                        sequences = altered['layouts'][0]['receipt_sequence']
                        if case == 'reused-sequence':
                            sequences['64'] = sequences['32']
                        elif case == 'extra-sequence':
                            sequences['16'] = sequences['32']
                        else:
                            sequences['32'] = True
                    count = sum(r['kind'] == 'evaluation' for r in changed)
                    altered['evaluation_count'] = altered['rows_evidence']['evaluation_count'] = count
                    changed[0]['expected_evaluations'] = changed[-1]['evaluation_count'] = count
                    self.rewrite_journal(output, altered, changed)
                    self.assertTrue(mesh.check_result(altered, output), case)

    def test_run_header_binds_exact_frozen_file_bytes(self):
        async def fake_call(oracle, design):
            return fake_thermal_result(oracle, design)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            frozen_path = output / 'layouts.json'
            data = (mesh.EVIDENCE_ROOT / 'ascend910/layouts.json').read_bytes() + b'\n'
            sha = hashlib.sha256(data).hexdigest()
            frozen_path.write_bytes(data)
            frozen_path.with_suffix('.sha256').write_text(sha + '\n')
            with patch.object(mesh.HotSpotOracle, '__call__', fake_call), redirect_stdout(io.StringIO()):
                self.assertEqual(mesh.main(['--grids', '32', '64', '--layout-ids',
                    'clustered-01', 'spread-01', '--layouts', str(frozen_path),
                    '--output-dir', str(output)]), 0)
            result = json.loads((output / 'RESULT.json').read_text())
            header = json.loads((output / 'rows.jsonl').read_text().splitlines()[0])
            self.assertEqual(header['layouts_sha256'], sha)
            self.assertEqual(result['layouts_sha256'], sha)
            self.assertEqual(mesh.check_result(result, output), [])

    def test_execution_commit_is_optional_provenance(self):
        cases = [
            ('build', {'BUILD_SHA': self.revision}, FileNotFoundError('git'), self.revision, 0),
            ('git', {}, self.revision + '\n', self.revision, 1),
            ('missing-git', {}, FileNotFoundError('git'), None, 1),
            ('missing-checkout', {}, subprocess.CalledProcessError(128, ['git']), None, 1),
            ('empty-git-output', {}, '', None, 1),
        ]

        async def fake_call(oracle, design):
            self.assertIsNotNone(expected, 'unresolved provenance reached evaluation')
            self.assertEqual(git.call_count, git_calls, 'provenance was not captured before evaluation')
            return fake_thermal_result(oracle, design)

        for name, environment, git_result, expected, git_calls in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory, \
                    patch.dict(mesh.os.environ, environment, clear=True), \
                    patch.object(mesh.subprocess, 'check_output') as git, \
                    patch.object(mesh.HotSpotOracle, '__call__', fake_call), \
                    redirect_stdout(io.StringIO()):
                if isinstance(git_result, Exception):
                    git.side_effect = git_result
                else:
                    git.return_value = git_result
                output = Path(directory)
                arguments = ['--grids', '32', '64', '--layout-ids',
                             'clustered-01', 'spread-01', '--output-dir', str(output)]
                if expected is None:
                    with self.assertRaisesRegex(ValueError, 'full source revision'):
                        mesh.main(arguments)
                    self.assertEqual(git.call_count, git_calls)
                    self.assertEqual(list(output.iterdir()), [])
                    continue
                self.assertEqual(mesh.main(arguments), 0)
                result = json.loads((output / 'RESULT.json').read_text())
                self.assertEqual(result['execution_commit'], expected)
                self.assertEqual(git.call_count, git_calls)
                self.assertIn(f'Execution commit: `{expected}`.', (output / 'REPORT.md').read_text())
                self.assertEqual(set(result['evaluator_identity']),
                                 {'hotspot_binary_sha256', 'generator_sha256'})
                self.assertEqual(mesh.check_result(result, output), [])

    def test_invalid_build_revision_fails_before_evaluation(self):
        for revision in ('unknown', 'main', self.revision[:7], 'z' * 40):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as directory, \
                    patch.dict(mesh.os.environ, {'BUILD_SHA': revision}), \
                    patch.object(mesh.subprocess, 'check_output', side_effect=FileNotFoundError('git')), \
                    patch.object(mesh.HotSpotOracle, '__call__',
                                 side_effect=AssertionError('evaluation must not start')) as evaluate:
                with self.assertRaisesRegex(ValueError, 'full source revision'):
                    mesh.main(['--grids', '32', '64', '--layout-ids',
                               'clustered-01', 'spread-01', '--output-dir', directory])
                evaluate.assert_not_called()
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_completed_receipts_survive_failure_and_cancellation(self):
        for failure in (RuntimeError('second call failed'), asyncio.CancelledError()):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                calls = []

                async def fake_call(oracle, design):
                    if calls:
                        records = [json.loads(line) for line in (output / 'rows.jsonl').read_text().splitlines()]
                        self.assertEqual(sum(r['kind'] == 'evaluation' for r in records), 1)
                        raise failure
                    result = fake_thermal_result(oracle, design)
                    calls.append(result)
                    return result

                with patch.object(mesh.HotSpotOracle, '__call__', fake_call):
                    with self.assertRaises(type(failure)):
                        mesh.main(['--grids', '32', '64', '--layout-ids',
                            'clustered-01', 'spread-01', '--output-dir', str(output)])
                records = [json.loads(line) for line in (output / 'rows.jsonl').read_text().splitlines()]
                self.assertEqual(records[0]['status'], 'incomplete')
                self.assertFalse(any(r['kind'] == 'completion' for r in records))
                receipt = next(r for r in records if r['kind'] == 'evaluation')
                self.assertEqual(receipt['parsed_receipt'], json.loads(mesh._json_bytes(asdict(calls[0]))))
                self.assertEqual(receipt['heatmap_sha256'], hashlib.sha256(mesh._json_bytes(calls[0].heatmap_c)).hexdigest())
                self.assertEqual(receipt['layout_id'], 'clustered-01')
                self.assertEqual(receipt['grid'], 32)
                self.assertFalse((output / 'RESULT.json').exists())

    def test_complete_journal_binds_summary_and_refuses_reuse(self):
        frozen, _ = mesh.load_layouts(mesh.EVIDENCE_ROOT / 'ascend910/layouts.json')
        calls = []

        async def fake_call(oracle, design):
            calls.append(design.hash)
            return fake_thermal_result(oracle, design)

        with tempfile.TemporaryDirectory() as directory, patch.object(mesh.HotSpotOracle, '__call__', fake_call):
            output = Path(directory)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(mesh.main(['--grids', '32', '64', '--layout-ids',
                    'clustered-01', 'spread-01', '--output-dir', str(output)]), 0)
            result = json.loads((output / 'RESULT.json').read_text())
            journal = (output / 'rows.jsonl').read_bytes()
            self.assertIn('D02 is incomplete', (output / 'REPORT.md').read_text())
            records = [json.loads(line) for line in journal.splitlines()]
            self.assertEqual(result['rows_evidence']['sha256'], hashlib.sha256(journal).hexdigest())
            self.assertEqual(records[-1]['status'], 'complete')
            self.assertEqual(records[-1]['evaluation_count'], 4)
            self.assertEqual([r['sequence'] for r in records if r['kind'] == 'evaluation'], [1, 2, 3, 4])
            self.assertEqual([r['receipt_sequence'] for r in result['layouts']], [{'32': 1, '64': 3}, {'32': 2, '64': 4}])
            self.assertEqual(mesh.check_result(result, output), [])
            changed = copy.deepcopy(result)
            changed['layouts'][0]['seconds']['32'] = 9.0
            self.assertTrue(any('receipt differs' in e for e in mesh.check_result(changed, output)))
            with self.assertRaises(FileExistsError):
                asyncio.run(mesh.evaluate_layouts(frozen, [32, 64],
                    ['clustered-01', 'spread-01'], evidence_dir=output))
            self.assertEqual(len(calls), 4)
            self.assertEqual((output / 'rows.jsonl').read_bytes(), journal)
            (output / 'rows.jsonl').write_bytes(journal + b' ')
            self.assertTrue(any('sha256 mismatch' in e for e in mesh.check_result(result, output)))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(mesh.main(['--check', str(output / 'RESULT.json')]), 1)

    def test_oversized_receipt_is_rejected_before_append(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rows.jsonl'
            with path.open('xb') as stream:
                mesh.append_receipt(stream, {'kind': 'run', 'status': 'incomplete'})
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'exceeds 1 MiB'):
                    mesh.append_receipt(stream, {'oversized': 'x' * mesh.MAX_RECEIPT_BYTES})
            self.assertEqual(path.read_bytes(), before)


class MeshRealRunTests(unittest.TestCase):
    def test_four_real_layouts_at_16_and_32(self):
        frozen = mesh.make_layout_set('ascend910', 1, 4)
        with tempfile.TemporaryDirectory() as directory:
            result = asyncio.run(mesh.evaluate_layouts(frozen, [16, 32], evidence_dir=Path(directory)))
        self.assertEqual(len(result['layouts']), 4)
        self.assertEqual(result['evaluation_count'], 8)
        self.assertIsNone(result['summary']['e_c'])
        self.assertEqual(mesh.check_result(result), [])
        for row in result['layouts']:
            self.assertEqual(set(row['J_c']), {'16', '32'})
            for grid in ('16', '32'):
                self.assertGreater(row['J_c'][grid], 40)
                self.assertGreater(row['seconds'][grid], 0)
                self.assertEqual(row['candidate_hash'][grid], row['design_hash'])
        self.assertEqual(result['summary']['reference_grid'], 32)


if __name__ == '__main__':
    unittest.main()
