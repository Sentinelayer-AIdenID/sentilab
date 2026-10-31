"""Tests call the shipped generator, statistics, checker and real HotSpot runner."""
import asyncio
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sundai_controller import mesh_study as mesh


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
        self.assertEqual(rank['eligible_pairs'], 3)
        self.assertFalse(rank['passes'])

    def test_tolerance_boundary_and_no_eligible_pairs(self):
        rank = mesh.rank_agreement([3, 2, 1], [0, 2, 4], 2)
        self.assertEqual(rank['eligible_pairs'], 1)
        self.assertEqual(rank['excluded_pairs'], 2)
        self.assertEqual(rank['violations'], 1)
        empty = mesh.rank_agreement([1, 0], [0, 1], 1)
        self.assertIsNone(empty['agreement_fraction'])
        self.assertTrue(empty['passes'])
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


class MeshRealRunTests(unittest.TestCase):
    def test_four_real_layouts_at_16_and_32(self):
        frozen = mesh.make_layout_set('ascend910', 1, 4)
        result = asyncio.run(mesh.evaluate_layouts(frozen, [16, 32]))
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
