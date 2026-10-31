"""Read-only CI/trusted writer handoff against finite fake GitHub responses."""
import copy
import hashlib
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


def git_commit(tree, parents):
    """A real Git commit ID: it hashes the tree and the ORDERED parents."""
    data = ''.join(['tree ' + tree + '\n'] + ['parent ' + sha + '\n' for sha in parents]
                   + ['author CI test <ci@example.invalid> 0 +0000\n',
                      'committer CI test <ci@example.invalid> 0 +0000\n', '\nMerge\n']).encode()
    return hashlib.sha1(b'commit ' + str(len(data)).encode() + bytes(1) + data).hexdigest()


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
        # Default-branch history, oldest first, and the commit its ref points at.
        self.history, self.tip = ['c' * 40], 'c' * 40
        self.bootstrap = {'allocation_id': '56314', 'historical_runs_debit': 2,
                          'historical_consumption': 'unknown; fake owner debit'}
        self.slots, self.commits, self.calls = {}, {}, []
        self.writable = True
        # Fake clock for the writer's bounded merge poll; each sleep may change GitHub.
        self.now, self.slept, self.during_sleep = 0, [], []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method != 'GET' and not self.writable:
            raise AssertionError('read-only CI attempted a write')
        # Fresh JSON per call, as from the real API, so a cached response goes stale.
        return copy.deepcopy(self.respond(method, path, body))

    def respond(self, method, path, body):
        if path == '/actions/runs/123':
            return self.run
        if path == '/pulls/37':
            return self.pull
        if path == '/git/commits/' + IDENTITY.build_sha:
            return self.merge
        if path == '/git/ref/heads/main':
            return {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': self.tip}}
        if path.startswith('/compare/'):
            older, newer = path.removeprefix('/compare/').split('...')
            if older == newer:
                return {'status': 'identical'}
            if older in self.history and newer in self.history:
                ahead = self.history.index(older) < self.history.index(newer)
                return {'status': 'ahead' if ahead else 'behind'}
            return {'status': 'diverged'}
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

    def clock(self):
        return self.now

    def sleep(self, seconds):
        # A lost deadline must fail the test, not hang it.
        if len(self.slept) >= 100:
            raise AssertionError('unbounded merge poll')
        self.slept.append(seconds)
        self.now += seconds
        if self.during_sleep:
            self.during_sleep.pop(0)()

    def identity(self, payload=None, **options):
        store = ci_admit.GitHubRefs(IDENTITY.repository, '', request=self.request)
        return ci_admit.workflow_identity(store, self.payload if payload is None else payload,
                                          clock=self.clock, sleep=self.sleep, **options)

    def merged(self, onto, tree='e' * 40):
        """Register GitHub's merge of the PR head onto `onto`; return its commit ID."""
        sha = git_commit(tree, [onto, IDENTITY.head_sha])
        self.commits[sha] = {'sha': sha, 'tree': {'sha': tree},
                             'parents': [{'sha': onto}, {'sha': IDENTITY.head_sha}]}
        return sha


def run_cli(fixture, directory, mode, **overrides):
    """Run the shipped CLI as its workflow step does; return the exit code and receipt."""
    event = directory / 'event.json'
    event.write_text(json.dumps(fixture.payload))
    output = directory / 'receipt.json'
    environment = workflow_fixture.WorkflowTests().environment(directory)
    environment.update(GH_TOKEN='', GITHUB_EVENT_PATH=str(event), GITHUB_EVENT_NAME=(
        'workflow_run' if mode == '--workflow-run' else 'pull_request'), **overrides)
    with patch.dict(os.environ, environment), \
         patch.object(ci_admit.GitHubRefs, '_request', side_effect=fixture.request), \
         patch.object(sys, 'argv', ['ci_admit', mode, str(output)]):
        code = ci_admit.main()
    return code, output.read_text()


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
        # Up to date: base.sha is the tip, so binding the tip needs no compare call.
        self.assertEqual([path for _, path, _ in fixture.calls], [
            '/actions/runs/123', '/pulls/37', '/git/commits/' + IDENTITY.build_sha,
            '/git/ref/heads/main'])
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
            with self.subTest(path=path), self.assertRaises((ValueError, TypeError)):
                fixture.identity(payload)  # a pending merge polls on the fake clock
            self.assertTrue(all(method == 'GET' for method, _, _ in fixture.calls))
        fixture = GitHubFixture()
        fixture.payload['workflow_run']['event'] = 'push'
        fixture.run.update(fixture.payload['workflow_run'])
        store = ci_admit.GitHubRefs(IDENTITY.repository, '', request=fixture.request)
        with self.assertRaisesRegex(ValueError, 'default-branch'):
            ci_admit.workflow_identity(store, fixture.payload)


class MainHistoryBindingTests(unittest.TestCase):
    """The admitted build is the PR head merged onto main's CURRENT tip, never base.sha."""

    def test_pr64_stale_base_sha_merged_onto_the_current_tip_is_admitted(self):
        # Receipts of refused allocation run 41233113186 (upstream CI run 41233110052):
        # base.sha stayed at 551777a while GitHub merged e8acc48 onto main's tip 46791be.
        base, middle, tip = ('551777a9516cc81e905ccc2daf4955d32151ac14',
                             'd298cb007081e9ad9334e3d77d412d789c126b0c',
                             '46791be360555d0e24b4ad5f906abafb71f07118')
        head = 'e8acc48a0bbdf12a5722b42956708960f7526e19'
        build = 'abab075152ae067b1cf154cc87912b8b6c2b4ac5'
        fixture = GitHubFixture()
        fixture.payload['workflow_run']['head_sha'] = fixture.run['head_sha'] = head
        fixture.pull.update(head={'sha': head}, merge_commit_sha=build)
        fixture.pull['base']['sha'] = base
        fixture.history, fixture.tip = [base, middle, tip], tip
        fixture.commits[build] = {'sha': build, 'parents': [{'sha': tip}, {'sha': head}]}
        self.assertEqual(fixture.identity(), replace(IDENTITY, head_sha=head, build_sha=build))
        self.assertIn(('GET', '/compare/' + base + '...' + tip, None), fixture.calls)
        self.assertEqual(fixture.slept, [])

    def test_merge_onto_an_old_tip_or_off_main_is_stale_and_refused_at_the_deadline(self):
        older, base, newer, tip = '0' * 40, 'c' * 40, '1' * 40, '2' * 40
        for case, onto in (('older than base.sha', older), ('old tip at base.sha', base),
                           ('old tip after base.sha', newer), ('diverged from main', '9' * 40)):
            with self.subTest(case=case):
                fixture = GitHubFixture()
                fixture.history, fixture.tip = [older, base, newer, tip], tip
                build = fixture.pull['merge_commit_sha'] = fixture.merged(onto)
                with self.assertRaisesRegex(ValueError, 'stale merge commit'):
                    fixture.identity()
                self.assertEqual(fixture.now, 60)
                paths = [path for _, path, _ in fixture.calls]
                # Every iteration re-read the run, the PR, the merge and the tip.
                for path in ('/actions/runs/123', '/pulls/37', '/git/commits/' + build,
                             '/git/ref/heads/main'):
                    self.assertEqual(paths.count(path), 21, path)
                self.assertFalse([path for path in paths if path.startswith('/compare/')])

    def test_merged_tip_must_contain_the_recorded_base(self):
        # Defensive: even a merge onto the current tip is refused when that tip does
        # not contain base.sha (a rewound or rewritten default branch).
        tip, later = '1' * 40, '2' * 40
        for history, base, status in (([tip, later], later, 'behind'), ([tip], '9' * 40, 'diverged')):
            with self.subTest(status=status):
                fixture = GitHubFixture()
                fixture.history, fixture.tip = history, tip
                fixture.pull['base']['sha'] = base
                fixture.pull['merge_commit_sha'] = fixture.merged(tip)
                with self.assertRaisesRegex(ValueError, 'base is not an ancestor of the merged tip'):
                    fixture.identity()
                self.assertIn(('GET', '/compare/' + base + '...' + tip, None), fixture.calls)

    def test_merge_must_have_exactly_two_parents_ending_at_the_run_head(self):
        tip, head, other = 'c' * 40, IDENTITY.head_sha, 'd' * 40
        for parents in ([tip, other], [tip, 'A' * 40], [head, tip], [head], [],
                        [tip, head, other], [tip, other, head]):
            with self.subTest(parents=parents):
                fixture = GitHubFixture()
                fixture.merge['parents'] = [{'sha': sha} for sha in parents]
                with self.assertRaisesRegex(ValueError, 'does not bind the pull request head'):
                    fixture.identity()
                self.assertEqual(fixture.slept, [])  # refused at once, never polled

    def test_pending_merge_is_polled_and_admitted_once_github_computes_it(self):
        for computed_after in (1, 10):
            with self.subTest(sleeps=computed_after):
                fixture = GitHubFixture()
                fixture.pull['merge_commit_sha'] = None
                fixture.during_sleep = [lambda: None] * (computed_after - 1) + [
                    lambda fixture=fixture: fixture.pull.update(merge_commit_sha=IDENTITY.build_sha)]
                self.assertEqual(fixture.identity(), IDENTITY)
                self.assertEqual(fixture.slept, [3] * computed_after)

    def test_merge_still_pending_at_the_deadline_is_refused_within_60_seconds(self):
        fixture = GitHubFixture()
        fixture.pull['merge_commit_sha'] = None
        with self.assertRaisesRegex(ValueError, 'merge commit still pending'):
            fixture.identity()
        self.assertEqual((fixture.slept, fixture.now), ([3] * 20, 60))
        self.assertFalse([path for _, path, _ in fixture.calls if path.startswith('/git/')])
        # The last sleep is cut at the deadline, never past it.
        fixture = GitHubFixture()
        fixture.pull['merge_commit_sha'] = None
        with self.assertRaisesRegex(ValueError, 'merge commit still pending'):
            fixture.identity(merge_timeout=10)
        self.assertEqual((fixture.slept, fixture.now), ([3, 3, 3, 1], 10))

    def test_pull_request_drift_during_the_poll_is_refused(self):
        drift = {'head moved': lambda fixture: fixture.pull['head'].update(sha='d' * 40),
                 'closed': lambda fixture: fixture.pull.update(state='closed'),
                 'base branch': lambda fixture: fixture.pull['base'].update(ref='other'),
                 'base repository': lambda fixture: fixture.pull['base']['repo'].update(
                     full_name='other/repo')}
        for name, change in drift.items():
            with self.subTest(drift=name):
                fixture = GitHubFixture()
                fixture.pull['merge_commit_sha'] = None
                fixture.during_sleep = [lambda change=change, fixture=fixture: change(fixture)]
                with self.assertRaisesRegex(ValueError, 'pull request source or base changed'):
                    fixture.identity()
                self.assertEqual(fixture.slept, [3])

    def test_upstream_run_ending_or_changing_during_the_poll_is_refused(self):
        drift = {'upstream run already terminal': lambda fixture: fixture.run.update(status='completed'),
                 'upstream run identity changed': lambda fixture: fixture.run.update(run_attempt=2)}
        for reason, change in drift.items():
            with self.subTest(reason=reason):
                fixture = GitHubFixture()
                fixture.pull['merge_commit_sha'] = None
                fixture.during_sleep = [lambda change=change, fixture=fixture: change(fixture)]
                with self.assertRaisesRegex(ValueError, reason):
                    fixture.identity()
                self.assertEqual(fixture.slept, [3])

    def test_non_hex_shas_and_branch_names_are_refused_before_any_api_path(self):
        def branch(fixture, bad):
            fixture.payload['repository']['default_branch'] = fixture.pull['base']['ref'] = bad
        cases = [
            ('invalid or unsupported allocation identity', '../' + 'b' * 37,
             lambda fixture, bad: fixture.pull.update(merge_commit_sha=bad)),
            ('invalid merge parent SHA', 'C' * 40, lambda fixture, bad: fixture.merge.update(
                parents=[{'sha': bad}, {'sha': IDENTITY.head_sha}])),
            ('invalid merge parent SHA', None, lambda fixture, bad: fixture.merge.update(
                parents=[{'sha': bad}, {'sha': IDENTITY.head_sha}])),
            ('invalid default-branch tip SHA', 'c' * 39 + 'x',
             lambda fixture, bad: setattr(fixture, 'tip', bad)),
            ('invalid pull request base SHA', '0' * 39,
             lambda fixture, bad: fixture.pull['base'].update(sha=bad)),
            ('invalid default branch name', 'main/../tags', branch),
            ('invalid default branch name', None, branch),
        ]
        for reason, bad, inject in cases:
            with self.subTest(reason=reason, bad=bad):
                fixture = GitHubFixture()
                inject(fixture, bad)
                try:
                    fixture.identity()
                except Exception as exc:  # judged below, after the API calls
                    refusal = exc
                else:
                    refusal = None
                self.assertFalse([path for _, path, _ in fixture.calls if str(bad) in path])
                self.assertIsInstance(refusal, ValueError)  # never a TypeError or admission
                self.assertRegex(str(refusal), reason)

    def test_stale_merge_recomputed_inside_the_window_binds_the_fresh_tip(self):
        old, new, newer = 'c' * 40, '1' * 40, '2' * 40
        fixture = GitHubFixture()
        fixture.history, fixture.tip = [old, new], new
        fixture.pull['merge_commit_sha'] = fixture.merged(old)
        onto_new, onto_newer = fixture.merged(new), fixture.merged(newer)

        def main_moves_while_github_recomputes():
            fixture.history.append(newer)
            fixture.tip = newer
            fixture.pull['merge_commit_sha'] = onto_new  # already stale again

        fixture.during_sleep = [main_moves_while_github_recomputes,
                                lambda: fixture.pull.update(merge_commit_sha=onto_newer)]
        self.assertEqual(fixture.identity(), replace(IDENTITY, build_sha=onto_newer))
        self.assertEqual(fixture.slept, [3, 3])

    def test_build_sha_binds_tested_tree_base_and_head_so_no_other_checkout_reuses_it(self):
        tip, head = 'c' * 40, IDENTITY.head_sha
        fixture = GitHubFixture()
        tested = fixture.pull['merge_commit_sha'] = fixture.merged(tip)
        # A commit ID hashes its tree and ORDERED parents: another tree, base, head or
        # parent order is another build SHA, so it cannot match the admitted receipt.
        others = {'tree': (git_commit('f' * 40, [tip, head]), head),
                  'base': (git_commit('e' * 40, ['1' * 40, head]), head),
                  'head': (git_commit('e' * 40, [tip, 'd' * 40]), 'd' * 40),
                  'parent order': (git_commit('e' * 40, [head, tip]), head)}
        self.assertEqual(len({tested} | {build for build, _ in others.values()}), 5)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            code, receipt = run_cli(fixture, directory, '--workflow-run')
            self.assertEqual(code, 0, receipt)
            self.assertEqual(json.loads(receipt)['identity'], asdict(replace(IDENTITY, build_sha=tested)))
            fixture.writable = False
            for name, (checkout, checkout_head) in others.items():
                with self.subTest(differs=name):
                    actual = {'GITHUB_SHA': checkout, 'PR_HEAD_SHA': checkout_head}
                    code, receipt = run_cli(fixture, directory, '--read-only', **actual)
                    self.assertEqual((code, json.loads(receipt).get('reason')),
                                     (1, 'durable admission identity mismatch'))
                    self.assertEqual(workflow_fixture.WorkflowTests().validate(
                        receipt, environment_overrides=actual).returncode, 1)
            code, receipt = run_cli(fixture, directory, '--read-only', GITHUB_SHA=tested)
            self.assertEqual(code, 0, receipt)
            self.assertEqual(workflow_fixture.WorkflowTests().validate(
                receipt, environment_overrides={'GITHUB_SHA': tested}).returncode, 0)

    def test_delayed_requested_event_after_main_moved_cannot_run_its_old_checkout(self):
        old_tip, new_tip = 'c' * 40, '1' * 40
        fixture = GitHubFixture()
        checkout = fixture.merged(old_tip)  # the queued run's own GITHUB_SHA
        recomputed = fixture.pull['merge_commit_sha'] = fixture.merged(new_tip, tree='f' * 40)
        fixture.history, fixture.tip = [old_tip, new_tip], new_tip
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            # The late writer sees only GitHub's current merge and reserves (charges) it...
            code, receipt = run_cli(fixture, directory, '--workflow-run')
            self.assertEqual(code, 0, receipt)
            self.assertEqual(json.loads(receipt)['identity']['build_sha'], recomputed)
            fixture.writable = False
            # ...which the delayed run cannot use for its older checkout.
            code, receipt = run_cli(fixture, directory, '--read-only', GITHUB_SHA=checkout)
            self.assertEqual((code, json.loads(receipt).get('reason')),
                             (1, 'durable admission identity mismatch'))
            self.assertEqual(workflow_fixture.WorkflowTests().validate(
                receipt, environment_overrides={'GITHUB_SHA': checkout}).returncode, 1)
            # Only a run whose own head and merge still bind may execute.
            code, receipt = run_cli(fixture, directory, '--read-only', GITHUB_SHA=recomputed)
            self.assertEqual(code, 0, receipt)
        # Before GitHub recomputes, the old merge is stale: refused, nothing reserved.
        late = GitHubFixture()
        late.history, late.tip = [old_tip, new_tip], new_tip
        late.pull['merge_commit_sha'] = late.merged(old_tip)
        with self.assertRaisesRegex(ValueError, 'stale merge commit'):
            late.identity()
        self.assertFalse([body for method, _, body in late.calls if method != 'GET'])
        # A late event for a run that already ended, or whose PR moved on, is refused.
        for reason, change in (('already terminal', lambda late: late.run.update(status='completed')),
                               ('source or base changed', lambda late: late.pull['head'].update(
                                   sha='d' * 40))):
            with self.subTest(reason=reason):
                late = GitHubFixture()
                change(late)
                with self.assertRaisesRegex(ValueError, reason):
                    late.identity()


if __name__ == '__main__':
    unittest.main()
