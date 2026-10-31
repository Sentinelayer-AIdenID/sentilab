"""Read-only CI/trusted writer handoff against finite fake GitHub responses."""
import copy
import json
import os
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from scripts import ci_admit
from scripts.ci_allocation import EXPIRY, RefConflict
from scripts.tests import test_ci_workflow as workflow_fixture
from scripts.tests.test_ci_allocation import IDENTITY, FakeRefs


class GitHubFixture:
    def __init__(self):
        self.payload = {
            'action': 'requested',
            'repository': {'full_name': IDENTITY.repository, 'default_branch': 'main'},
            'workflow_run': {'id': 123, 'run_attempt': 1, 'workflow_id': 7,
                             'repository': {'full_name': IDENTITY.repository},
                             'path': '.github/workflows/ci.yml', 'event': 'pull_request',
                             'head_sha': IDENTITY.head_sha, 'head_branch': 'feature',
                             'pull_requests': [{'number': 37}]},
        }
        self.run = dict(self.payload['workflow_run'], status='in_progress')
        self.pull = {'state': 'open', 'head': {'sha': IDENTITY.head_sha},
                     'base': {'sha': 'c' * 40, 'ref': 'main',
                              'repo': {'full_name': IDENTITY.repository}},
                     'merge_commit_sha': IDENTITY.build_sha}
        self.merge = {'sha': IDENTITY.build_sha,
                      'parents': [{'sha': 'c' * 40}, {'sha': IDENTITY.head_sha}]}
        self.bootstrap = {'allocation_id': '56314', 'historical_runs_debit': 2,
                          'historical_consumption': 'unknown; fake owner debit'}
        self.slots, self.commits, self.calls = {}, {}, []
        self.writable = True

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method != 'GET' and not self.writable:
            raise AssertionError('read-only CI attempted a write')
        if path == '/actions/runs/123':
            return self.run
        if path == '/pulls/37':
            return self.pull
        if path == '/git/commits/' + IDENTITY.build_sha:
            return self.merge
        if path.endswith('/bootstrap'):
            return {'object': {'type': 'commit', 'sha': 'base-commit'}}
        if path == '/git/commits/base-commit':
            return {'message': json.dumps(self.bootstrap), 'tree': {'sha': 'base-tree'}}
        if path.startswith('/git/matching-refs/'):
            return [{'ref': name, 'object': {'type': 'commit', 'sha': sha}}
                    for name, sha in self.slots.items()]
        if method == 'POST' and path == '/git/commits':
            sha = 'commit-' + str(len(self.commits))
            self.commits[sha] = body
            return {'sha': sha}
        if method == 'POST' and path == '/git/refs':
            if body['ref'] in self.slots:
                raise RefConflict('already exists')
            self.slots[body['ref']] = body['sha']
            return {}
        if path.startswith('/git/commits/'):
            return self.commits[path.rsplit('/', 1)[1]]
        raise AssertionError((method, path))


class HandoffTests(unittest.TestCase):
    def test_pr_workflow_has_no_write_permissions_and_writer_uses_only_default_branch(self):
        workflow = (workflow_fixture.ROOT / '.github/workflows/ci.yml').read_text()
        self.assertTrue(': write' not in workflow, 'pull_request workflow requests write permission')
        self.assertNotIn('write-all', workflow)
        admission = workflow_fixture.job('admission')
        self.assertIn('contents: read', admission)
        self.assertIn('scripts.ci_admit --read-only', admission)
        writer = (workflow_fixture.ROOT / '.github/workflows/ci-allocation-admission.yml').read_text()
        self.assertIn('workflow_run:', writer)
        self.assertIn('types: [requested]', writer)
        self.assertNotIn('pull_request:', writer)
        self.assertEqual(writer.count('actions/checkout@'), 1)
        self.assertIn('ref: ${{ github.sha }}', writer)
        self.assertIn('persist-credentials: false', writer)
        self.assertIn('contents: write', writer)
        self.assertIn('actions: read', writer)
        self.assertIn('pull-requests: read', writer)
        self.assertIn('scripts.ci_admit --workflow-run', writer)
        self.assertNotIn('download-artifact', writer)
        self.assertNotIn('pip install', writer)
        self.assertNotIn('head_sha }}', writer)
        terminal = (workflow_fixture.ROOT / '.github/workflows/ci-allocation-settlement.yml').read_text()
        self.assertIn('types: [completed]', terminal)
        self.assertNotIn(': write', terminal)

    def test_workflow_shell_selects_reader_even_when_controller_exists(self):
        process, _, _ = workflow_fixture.WorkflowTests().bootstrap(controller=(
            'import sys\n'
            'raise SystemExit(0 if sys.argv[1] == "--read-only" else 31)\n'))
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_cli_writer_reader_and_container_bind_the_same_durable_reservation(self):
        fixture = GitHubFixture()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            event = directory / 'event.json'
            event.write_text(json.dumps(fixture.payload))
            output = directory / 'receipt.json'
            environment = workflow_fixture.WorkflowTests().environment(directory)
            environment.update(GH_TOKEN='', GITHUB_EVENT_NAME='workflow_run',
                               GITHUB_EVENT_PATH=str(event))
            with patch.dict(os.environ, environment), \
                 patch.object(ci_admit.GitHubRefs, '_request', side_effect=fixture.request), \
                 patch.object(sys, 'argv', ['ci_admit', '--workflow-run', str(output)]):
                self.assertEqual(ci_admit.main(), 0)
            writer = json.loads(output.read_text())
            self.assertEqual(writer['identity'], asdict(IDENTITY))
            self.assertEqual(writer['slot'], 3)
            self.assertEqual(len(fixture.slots), 1)
            fixture.writable = False
            fixture.calls.clear()
            environment['GITHUB_EVENT_NAME'] = 'pull_request'
            with patch.dict(os.environ, environment), \
                 patch.object(ci_admit.GitHubRefs, '_request', side_effect=fixture.request), \
                 patch.object(sys, 'argv', ['ci_admit', '--read-only', str(output)]):
                self.assertEqual(ci_admit.main(), 0)
            reader = json.loads(output.read_text())
            self.assertEqual(reader['identity'], writer['identity'])
            self.assertEqual(reader['slot'], writer['slot'])
            self.assertTrue(all(method == 'GET' for method, _, _ in fixture.calls))
            self.assertEqual(workflow_fixture.WorkflowTests().validate(output.read_text()).returncode, 0)
            # Even an explicit writer invocation in PR context performs no API call.
            fixture.calls.clear()
            with patch.dict(os.environ, environment), \
                 patch.object(ci_admit.GitHubRefs, '_request', side_effect=fixture.request), \
                 patch.object(sys, 'argv', ['ci_admit', '--workflow-run', str(output)]):
                self.assertEqual(ci_admit.main(), 1)
            self.assertEqual(fixture.calls, [])
            self.assertEqual(json.loads(output.read_text())['state'], 'admission_refused')
            with patch.dict(os.environ, environment), \
                 patch.object(ci_admit.GitHubRefs, '_request', side_effect=RuntimeError('API unreadable')), \
                 patch.object(sys, 'argv', ['ci_admit', '--read-only', str(output)]):
                self.assertEqual(ci_admit.main(), 1)
            self.assertEqual(json.loads(output.read_text())['state'], 'admission_refused')
            self.assertEqual(workflow_fixture.WorkflowTests().validate(output.read_text()).returncode, 1)

    def test_reader_waits_without_writes_and_missing_or_unreadable_receipt_refuses(self):
        for outcome in ('arrives', 'missing', 'unreadable'):
            store = FakeRefs()
            clock = [0]

            def sleep(seconds, clock=clock, outcome=outcome, store=store):
                clock[0] += seconds
                if outcome == 'arrives':
                    store.refs[3] = asdict(IDENTITY)

            if outcome == 'unreadable':
                store.bootstrap = None
            with self.subTest(outcome=outcome), patch.object(store, 'claim', side_effect=AssertionError('write')):
                def read(store=store, clock=clock, sleep=sleep):
                    return ci_admit.read_admission(store, IDENTITY, timeout=10, now=lambda: EXPIRY - 1,
                                                   clock=lambda: clock[0], sleep=sleep)
                if outcome == 'arrives':
                    self.assertEqual(read()['slot'], 3)
                    self.assertEqual(clock[0], 5)
                else:
                    with self.assertRaises(RuntimeError):
                        read()
                    self.assertLessEqual(clock[0], 10)

    def test_reader_refuses_mismatch_duplicates_reruns_invalid_store_and_expiry(self):
        cases = [(FakeRefs(), IDENTITY)]
        cases[0][0].refs = {3: dict(asdict(IDENTITY), build_sha='d' * 40)}
        duplicate = FakeRefs()
        duplicate.refs = {3: asdict(IDENTITY), 4: asdict(IDENTITY)}
        cases.append((duplicate, IDENTITY))
        cases.append((FakeRefs(), replace(IDENTITY, attempt='2')))
        for debit in (True, -1, 201):
            store = FakeRefs()
            store.bootstrap['historical_runs_debit'] = debit
            cases.append((store, IDENTITY))
        for slot in (2, 201):
            store = FakeRefs()
            store.refs = {slot: asdict(IDENTITY)}
            cases.append((store, IDENTITY))
        exhausted = FakeRefs()
        exhausted.bootstrap['historical_runs_debit'] = 200
        cases.append((exhausted, IDENTITY))
        for store, identity in cases:
            with self.subTest(store=store.__dict__, identity=identity), self.assertRaises(RuntimeError):
                ci_admit.read_admission(store, identity, now=lambda: EXPIRY - 1)
        store = FakeRefs()
        store.refs = {3: asdict(IDENTITY)}
        for times in ([EXPIRY], [EXPIRY - 1, EXPIRY]):
            with self.subTest(times=times), self.assertRaisesRegex(RuntimeError, 'expired'):
                ci_admit.read_admission(store, IDENTITY, now=iter(times).__next__)
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            ci_admit.read_admission(store, IDENTITY, now=lambda: EXPIRY - 1,
                                   timeout=10, clock=iter([0, 10]).__next__)

    def test_writer_resolves_pr_merge_and_default_branch_push_from_github_metadata(self):
        fixture = GitHubFixture()
        store = ci_admit.GitHubRefs(IDENTITY.repository, '', request=fixture.request)
        self.assertEqual(ci_admit.workflow_identity(store, fixture.payload), IDENTITY)
        self.assertEqual([path for _, path, _ in fixture.calls], [
            '/actions/runs/123', '/pulls/37', '/git/commits/' + IDENTITY.build_sha])
        fixture.payload['workflow_run'].update(event='push', head_branch='main', pull_requests=[])
        fixture.run.update(fixture.payload['workflow_run'])
        fixture.calls.clear()
        self.assertEqual(ci_admit.workflow_identity(store, fixture.payload),
                         replace(IDENTITY, build_sha=IDENTITY.head_sha))
        self.assertEqual(len(fixture.calls), 1)

    def test_writer_refuses_wrong_workflow_reruns_drift_and_unverifiable_merges(self):
        changes = [
            ('action', 'completed'), ('repository.full_name', 'other/repo'),
            ('workflow_run.repository.full_name', 'other/repo'),
            ('workflow_run.path', '.github/workflows/other.yml'), ('workflow_run.run_attempt', 2),
            ('workflow_run.id', True), ('workflow_run.event', 'workflow_dispatch'),
            ('workflow_run.pull_requests', []), ('workflow_run.pull_requests', [{'number': '../bad'}]),
            ('run.run_attempt', 2), ('run.head_sha', 'd' * 40), ('run.status', 'completed'),
            ('pull.head.sha', 'd' * 40), ('pull.state', 'closed'), ('pull.base.ref', 'other'),
            ('pull.base.repo.full_name', 'other/repo'), ('pull.merge_commit_sha', None),
            ('pull.merge_commit_sha', '../bad'), ('merge.parents', [{'sha': IDENTITY.head_sha}]),
            ('merge.sha', 'e' * 40),
        ]
        for path, value in changes:
            fixture = GitHubFixture()
            source = {'run': fixture.run, 'pull': fixture.pull, 'merge': fixture.merge,
                      **fixture.payload}
            keys = path.split('.')
            target = source
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = copy.deepcopy(value)
            payload = {key: source[key] for key in fixture.payload}
            if path.startswith('workflow_run.'):
                fixture.run.update(payload['workflow_run'])
            store = ci_admit.GitHubRefs(IDENTITY.repository, '', request=fixture.request)
            with self.subTest(path=path), self.assertRaises((ValueError, TypeError)):
                ci_admit.workflow_identity(store, payload)
            self.assertTrue(all(method == 'GET' for method, _, _ in fixture.calls))
        fixture = GitHubFixture()
        fixture.payload['workflow_run']['event'] = 'push'
        fixture.run.update(fixture.payload['workflow_run'])
        store = ci_admit.GitHubRefs(IDENTITY.repository, '', request=fixture.request)
        with self.assertRaisesRegex(ValueError, 'default-branch'):
            ci_admit.workflow_identity(store, fixture.payload)


if __name__ == '__main__':
    unittest.main()
