"""Drive the shipped durable-store adapter, artifact witness and workflow wiring."""
from dataclasses import asdict
import json
from pathlib import Path
import unittest

from scripts.ci_admit import GitHubRefs, PREFIX
from scripts.ci_reconcile import reconcile
from scripts.tests.test_ci_allocation import IDENTITY

ROOT = Path(__file__).resolve().parents[2]


class StoreTests(unittest.TestCase):
    def test_store_reads_durable_bootstrap_and_claims_an_immutable_slot(self):
        calls = []
        bootstrap = {'allocation_id': '56314', 'historical_runs_debit': 2,
                     'historical_consumption': 'unknown; owner debit'}
        def api(method, path, body=None):
            calls.append((method, path, body))
            if path.endswith('/bootstrap'):
                return {'object': {'type': 'commit', 'sha': 'base-commit'}}
            if path == '/git/commits/base-commit':
                return {'message': json.dumps(bootstrap), 'tree': {'sha': 'base-tree'}}
            if path.startswith('/git/matching-refs/'):
                return []
            if path == '/git/commits':
                return {'sha': 'new-commit'}
            if path == '/git/refs':
                return {}
            raise AssertionError(path)
        store = GitHubRefs('example/repo', '', request=api)
        self.assertEqual(store.read_bootstrap(), bootstrap)
        self.assertEqual(store.read_slots(), {})
        store.claim(3, asdict(IDENTITY))
        self.assertEqual(calls[-1], ('POST', '/git/refs', {
            'ref': 'refs/' + PREFIX + 'slot-003', 'sha': 'new-commit'}))
        record = json.loads(calls[-2][2]['message'])
        self.assertEqual(record['identity'], asdict(IDENTITY))
        self.assertEqual(record['bootstrap_sha'], 'base-commit')
        self.assertTrue(all(method in ('GET', 'POST') for method, _, _ in calls))

    def test_invalid_or_changed_lineage_never_reads_as_empty(self):
        def api(method, path, body=None):
            if path.startswith('/git/matching-refs/'):
                return [{'ref': 'refs/' + PREFIX + 'slot-003',
                         'object': {'type': 'commit', 'sha': 'slot-commit'}}]
            return {'message': json.dumps({'allocation_id': '56314', 'slot': 3,
                                           'bootstrap_sha': 'different',
                                           'identity': asdict(IDENTITY)})}
        store = GitHubRefs('example/repo', '', request=api)
        store.bootstrap_sha = 'original'
        with self.assertRaisesRegex(RuntimeError, 'lineage'):
            store.read_slots()


class SettlementTests(unittest.TestCase):
    def test_runner_loss_reserves_full_allowance_without_inventing_measurements(self):
        result = reconcile(asdict(IDENTITY), 'cancelled')
        self.assertIsNone(result['cpu_seconds'])
        self.assertIsNone(result['executions_started'])
        self.assertEqual(result['charged_cpu_seconds'], 900)
        self.assertEqual(result['charged_launches'], 100)
        self.assertEqual(result['identity']['build_sha'], 'b' * 40)

    def test_settlement_identity_and_complete_terminal_state_are_required(self):
        from scripts.ci_allocation import Ledger
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / 'events.jsonl', IDENTITY)
            self.assertEqual(reconcile(asdict(IDENTITY), 'failure', ledger.summary())['charged_launches'], 100)
            ledger.finish('success', {'cpu_seconds': 12.5})
            result = reconcile(asdict(IDENTITY), 'success', ledger.summary())
            self.assertEqual(result['settlement']['cpu']['cpu_seconds'], 12.5)
            with self.assertRaises(ValueError):
                reconcile(dict(asdict(IDENTITY), build_sha='c' * 40), 'success', ledger.summary())


class WiringTests(unittest.TestCase):
    def test_ci_retains_required_suites_and_meter_wraps_entire_container_job(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('needs: allocation-proof', workflow)
        self.assertIn('needs: admission', workflow)
        self.assertIn('scripts.ci_cpu_meter run', workflow)
        self.assertIn('scripts.ci_cpu_meter recover', workflow)
        self.assertIn('allocation-settlement-${{ github.run_id }}-${{ github.run_attempt }}', workflow)
        shell = (ROOT / 'scripts/ci_container_job.sh').read_text()
        for control in ('--cgroup-parent=', '--exec-opt=native.cgroupdriver=cgroupfs',
                        '--network=host', '--no-cache', '--build-arg CI_ALLOCATION=1',
                        'build_sha', 'ORIGIN_SHARED_TOKEN', ')" = 403', ')" = 200'):
            self.assertIn(control, shell)
        smoke = (ROOT / 'scripts/container_smoke.sh').read_text()
        for suite in ('test_controller.py', 'test_safety_property.py', 'test_experiment.py',
                      'test_tfl08_leaderboard.py', 'test_tap_oracle.py', 'test_tfl14_regression.py',
                      'app.test_runs', 'sentilab_core/test_*.py', 'run_tap_probe.py',
                      'tfl05_smoke.py --benchmark plate', 'tfl05_smoke.py --benchmark ascend910'):
            self.assertIn(suite, smoke)
        docker = (ROOT / 'Dockerfile').read_text()
        self.assertIn('CI_ALLOCATION=${CI_ALLOCATION}', docker)
        self.assertIn('bash /app/scripts/container_smoke.sh', docker)

    def test_write_permission_is_separated_from_pr_code_and_terminal_witness_is_trusted(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        admission = workflow.split('  admission:')[1].split('  container:')[0]
        self.assertIn('github.event.pull_request.base.sha || github.sha', admission)
        self.assertIn('persist-credentials: false', admission)
        container = workflow.split('  container:')[1].split('  contracts:')[0]
        self.assertNotIn('contents: write', container)
        terminal = (ROOT / '.github/workflows/ci-allocation-settlement.yml').read_text()
        self.assertIn('types: [completed]', terminal)
        self.assertIn('ref: ${{ github.event.repository.default_branch }}', terminal)
        self.assertIn('scripts.ci_reconcile', terminal)
