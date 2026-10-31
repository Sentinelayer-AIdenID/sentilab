"""Execute the actual workflow shell blocks without GitHub or thermal solves."""
import json
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from dataclasses import asdict
from pathlib import Path

from scripts.tests.test_ci_allocation import IDENTITY

ROOT = Path(__file__).resolve().parents[2]


def job(name):
    workflow = (ROOT / '.github/workflows/ci.yml').read_text()
    return re.search(rf'^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)',
                     workflow, re.MULTILINE | re.DOTALL).group(1)


def shell_step(job_name, name):
    block = job(job_name)
    step = re.search(rf'^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)',
                     block, re.MULTILINE | re.DOTALL)
    if step is None:
        raise AssertionError(f'missing workflow step: {name}')
    script = step.group(1).split('        run: ', 1)[1]
    if script.startswith('|\n'):
        return textwrap.dedent(script[2:])
    return script.splitlines()[0]


class WorkflowTests(unittest.TestCase):
    def authorization(self, base_sha='c' * 40):
        return {'schema': 'ci-hotspot-bootstrap-authorization-v1', 'allocation_id': '56314',
                'authorization_id': 'fake-owner-rollout', 'approved_by': 'fake owner approval',
                'repository': IDENTITY.repository, 'workflow_path': '.github/workflows/ci.yml',
                'expires_at': 1793556000,
                'runs': [{'identity': asdict(IDENTITY), 'base_sha': base_sha}]}

    def environment(self, directory):
        return dict(os.environ, RUNNER_TEMP=str(directory),
                    GITHUB_REPOSITORY=IDENTITY.repository, GITHUB_RUN_ID=IDENTITY.run_id,
                    GITHUB_RUN_ATTEMPT='1', GITHUB_SHA=IDENTITY.build_sha,
                    PR_HEAD_SHA=IDENTITY.head_sha, TRUSTED_BASE_SHA='c' * 40,
                    ADMISSION_RESULT='success',
                    GITHUB_WORKFLOW_REF=IDENTITY.repository + '/.github/workflows/ci.yml@refs/heads/main',
                    CI_BOOTSTRAP_AUTHORIZATION=json.dumps(self.authorization()))

    def receipt(self):
        return {'state': 'admitted', 'allocation_id': '56314', 'slot': 3,
                'identity': asdict(IDENTITY), 'launch_reservation': 100,
                'cpu_reservation_seconds': 900}

    def validate(self, receipt, *, result='success'):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            if receipt is not None:
                (directory / 'allocation').mkdir()
                (directory / 'allocation/admission.json').write_text(receipt)
            environment = self.environment(directory)
            environment['ADMISSION_RESULT'] = result
            return subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', shell_step(
                'container', 'Validate admission before any workload')],
                cwd=directory, env=environment, text=True, capture_output=True, check=False)

    def test_required_jobs_cannot_be_skipped_by_upstream_failure(self):
        for name in ('browser-verifier', 'container', 'contracts',
                     'live-conformance', 'secret-scan'):
            with self.subTest(job=name):
                header = job(name).split('    steps:', 1)[0]
                if '    needs:' in header:
                    self.assertRegex(header, r'(?m)^    if: always\(\)(?: #[^\n]*)?\n')
        container = job('container')
        self.assertIn('    needs: admission\n', container)
        self.assertIn('ADMISSION_RESULT: ${{ needs.admission.result }}', container)
        self.assertIn('continue-on-error: true', container.split('Validate admission')[0])
        self.assertLess(container.index('actions/download-artifact@'),
                        container.index('Validate admission before any workload'))
        self.assertLess(container.index('Validate admission before any workload'),
                        container.index('actions/checkout@'))
        self.assertNotIn('continue-on-error', container.split('Validate admission')[1])

    def test_container_rejects_missing_refused_invalid_or_failed_admission(self):
        valid = self.receipt()
        cases = [None, 'not json', '[]', '{}', json.dumps(dict(valid, state='admission_refused')),
                 json.dumps(dict(valid, allocation_id='other')),
                 json.dumps(dict(valid, launch_reservation=101)),
                 json.dumps(dict(valid, cpu_reservation_seconds=901)),
                 json.dumps(dict(valid, slot=True)), json.dumps(dict(valid, slot=201)),
                 json.dumps(dict(valid, mode='unknown')),
                 json.dumps(dict(valid, identity=dict(valid['identity'], run_id='456'))),
                 json.dumps(dict(valid, identity=dict(valid['identity'], build_sha='d' * 40))),
                 json.dumps(dict(valid, identity=dict(valid['identity'], attempt='2')))]
        for receipt in cases:
            with self.subTest(receipt=receipt):
                process = self.validate(receipt)
                self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
                self.assertIn('Container admission failed:', process.stderr)
        for result in ('failure', 'cancelled', 'skipped'):
            with self.subTest(upstream=result):
                process = self.validate(json.dumps(valid), result=result)
                self.assertEqual(process.returncode, 1)
                self.assertIn('admission job did not succeed', process.stderr)

    def test_container_accepts_current_run_durable_receipt(self):
        process = self.validate(json.dumps(self.receipt()))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def bootstrap(self, *, controller=None, remove_controller=False, authorization='valid'):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            tree = directory / 'base'
            tree.mkdir()
            if controller is not None:
                (tree / 'scripts').mkdir()
                (tree / 'scripts/ci_admit.py').write_text(controller)
            subprocess.run(['git', 'init', '-q', str(tree)], check=True)
            subprocess.run(['git', 'add', '.'], cwd=tree, check=True)
            subprocess.run(['git', '-c', 'user.name=CI test', '-c', 'user.email=ci@example.invalid',
                            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'trusted base', '--allow-empty'],
                           cwd=tree, check=True)
            base_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=tree, text=True).strip()
            if remove_controller:
                (tree / 'scripts/ci_admit.py').unlink()
            environment = self.environment(directory)
            environment['TRUSTED_BASE_SHA'] = base_sha
            environment['CI_BOOTSTRAP_AUTHORIZATION'] = (
                json.dumps(self.authorization(base_sha)) if authorization == 'valid' else authorization)
            if callable(authorization):
                environment['CI_BOOTSTRAP_AUTHORIZATION'] = json.dumps(authorization(self.authorization(base_sha)))
            process = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', shell_step(
                'admission', 'Read global run slot from trusted allocation controller')],
                cwd=tree, env=environment, text=True, capture_output=True, check=False)
            path = directory / 'allocation/admission.json'
            receipt = json.loads(path.read_text()) if path.exists() else None
            return process, receipt, base_sha

    def test_bootstrap_requires_bounded_owner_authorization_and_records_run_debit(self):
        for authorization in ('', '{}', lambda a: dict(a, runs=[]), lambda a: dict(a, expires_at=0),
                              lambda a: dict(a, workflow_path='other.yml'),
                              lambda a: dict(a, repository='other/repo'),
                              lambda a: dict(a, runs=a['runs'] * 2),
                              lambda a: dict(a, runs=a['runs'] * 201),
                              lambda a: dict(a, runs=[dict(a['runs'][0], base_sha='d' * 40)])):
            with self.subTest(authorization=authorization):
                process, receipt, _ = self.bootstrap(authorization=authorization)
                self.assertNotEqual(process.returncode, 0)
                self.assertIsNone(receipt)
        process, receipt, _ = self.bootstrap()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(receipt['bootstrap_authorization']['authorization_id'], 'fake-owner-rollout')
        self.assertEqual(receipt['rollout_debit']['run_id'], IDENTITY.run_id)
        self.assertEqual(receipt['rollout_debit']['charged_launches'], 100)
        self.assertEqual(receipt['rollout_debit']['charged_cpu_seconds'], 900)

    def test_absent_controller_at_base_bootstraps_without_pr_imports(self):
        process, receipt, base_sha = self.bootstrap()
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(receipt['mode'], 'bootstrap')
        self.assertEqual(receipt['reason'], 'controller absent at base ' + base_sha)
        self.assertEqual(receipt['base_sha'], base_sha)
        self.assertEqual(receipt['state'], 'admitted')
        self.assertEqual(receipt['identity'], asdict(IDENTITY))
        self.assertEqual(receipt['launch_reservation'], 100)
        self.assertEqual(receipt['cpu_reservation_seconds'], 900)
        self.assertIsNone(receipt.get('slot'))
        admission = job('admission')
        self.assertEqual(admission.count('actions/checkout@'), 1)
        self.assertIn('ref: ${{ github.event.pull_request.base.sha || github.sha }}', admission)
        self.assertIn('persist-credentials: false', admission)
        self.assertNotIn('actions/download-artifact@', admission)

    def test_existing_controller_failure_never_bootstraps(self):
        for remove in (False, True):
            with self.subTest(missing_worktree_file=remove):
                process, receipt, _ = self.bootstrap(controller='raise SystemExit(17)\n',
                                                      remove_controller=remove)
                self.assertNotEqual(process.returncode, 0)
                self.assertIsNone(receipt)

    def test_container_accepts_only_bootstrap_bound_to_trusted_base(self):
        valid = dict(self.receipt(), mode='bootstrap', slot=None, base_sha='c' * 40,
                     reason='controller absent at base ' + 'c' * 40)
        process = self.validate(json.dumps(valid))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        for invalid in (dict(valid, base_sha='d' * 40), dict(valid, reason='controller failed'),
                        dict(valid, slot=1), dict(valid, state='admission_refused')):
            with self.subTest(receipt=invalid):
                process = self.validate(json.dumps(invalid))
                self.assertEqual(process.returncode, 1)


if __name__ == '__main__':
    unittest.main()
