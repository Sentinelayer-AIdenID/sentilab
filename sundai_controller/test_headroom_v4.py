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

            async def __call__(self, design):
                ledger = json.loads(spend_path.read_text())
                reservation = ledger['active']
                case.assertEqual(reservation['design_hash'], design.hash)
                lane = reservation['lane']
                lane_counts[lane] = lane_counts.get(lane, 0) + 1
                count = lane_counts[lane]
                case.calls.append((lane, count, design.hash, len(design.chiplets)))
                if 'long-sa' in lane:
                    baseline = case.directory / 'out/CHEAP_BASELINE.json'
                    # A reference call only has a persisted C if all cheap checks passed.
                    if baseline.exists():
                        case.assertEqual(json.loads(baseline.read_text())['reproductions'], 96)
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
            return await h.run_headroom('micro150', 0.79, prereg_path, self.directory / 'out')

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
        baseline = self.directory / 'out/CHEAP_BASELINE.json'
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
        self.assertFalse((self.directory / 'out/CHEAP_BASELINE.json').exists())

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

    async def test_cpu_48_and_72_minute_caps_preserve_prior_actuals(self):
        self.spend['fixtures']['micro150'] = {'calls': 0, 'cpu_seconds': 2879.5}
        self.spend['cpu_seconds'] += 2879.5
        self.cpu_per_call = 0.3
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'total_cpu_cap')
        self.assertAlmostEqual(result['allocation_spend']['overshoot']['headroom_cpu_seconds'], 0.094565)
        self.assertEqual(result['allocation_spend']['fixtures']['ascend910']['cpu_seconds'], 1440.2945650000001)

    async def test_fixture_cpu_cap_cannot_be_increased_by_prereg(self):
        # A stricter cumulative charge can mask the fixture bound; inspect both limits.
        self.prereg['allocation']['per_fixture']['cpu_minutes'] = 999
        self.prereg['allocation']['headroom_cpu_minutes'] = 999
        path = self.directory / 'SPEND.json'
        path.write_text(json.dumps(self.spend))
        budget = h.SolveBudget(path, 'micro150', self.prereg)
        try:
            self.assertEqual(budget.fixture_cpu_limit, 2880)
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
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'aggregate_cpu_cap')
        self.assertAlmostEqual(result['allocation_spend']['overshoot']['aggregate_cpu_seconds'], 0.25)

    async def test_90_minute_cumulative_wall_cap_and_overshoot(self):
        self.prereg['clock']['solving_wall_minutes'] = 999
        self.spend['solving_wall_seconds'] = 5399.5
        self.wall_per_call = 1.0
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'solving_wall_cap')
        self.assertEqual(result['allocation_spend']['overshoot']['solving_wall_seconds'], 0.5)

    async def test_deadline_and_admitted_call_overshoot(self):
        self.now = datetime(2026, 10, 31, 11, 59, 59, tzinfo=timezone.utc)
        self.prereg['clock']['deadline'] = '2026-11-01T12:00:00Z'
        self.wall_per_call = 2.0
        result = await self.run_fixture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['reducer_results'][0]['stop_reason'], 'deadline')
        self.assertEqual(result['allocation_spend']['overshoot']['deadline_seconds'], 1.0)

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
                ('reproduction', 'absolute_tolerance_c', 0.1)]:
            with self.subTest(section=section, field=field):
                prereg = copy.deepcopy(self.prereg)
                (prereg if section is None else prereg[section])[field] = value
                path.write_text(json.dumps(prereg))
                with self.assertRaises(ValueError):
                    h._parse_prereg(path)


if __name__ == '__main__':
    unittest.main()
