"""Offline prospective-owner fixtures. These records authorize NO real job."""
import base64
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from scripts import ci_transition as t
from scripts import ci_owner_source as loader
from scripts.ci_admit import GitHubRefs, read_admission
from scripts.ci_allocation import Identity, Ledger, RefAdmission, RefConflict
from scripts.ci_policy import LEGACY, SOURCE_FILES, digest, grant_policy, receipt_policy, selection
from scripts.ci_reconcile import reconcile, main as reconcile_main
from scripts.tests.test_ci_allocation import IDENTITY as EXAMPLE_IDENTITY
from scripts.tests.test_ci_admission_handoff import GitHubFixture
from scripts.tests.test_ci_workflow import ROOT, shell_step, job

OLD = '898982800967ee76621112c61a8dfd6764ec9e8d'
IDENTITY = replace(EXAMPLE_IDENTITY, repository='Sentinelayer-AIdenID/sentilab')
BOOT = '1' * 40
TREE = '2' * 40
ACTIVATION = '3' * 40


class OwnerFixture(GitHubFixture):
    def __init__(self):
        super().__init__()
        self.payload['repository']['full_name'] = IDENTITY.repository
        self.payload['workflow_run']['repository']['full_name'] = IDENTITY.repository
        self.run['repository']['full_name'] = IDENTITY.repository
        self.pull['base']['repo']['full_name'] = IDENTITY.repository
        self.files = {name: (ROOT / name).read_bytes() for name in SOURCE_FILES}
        self.blobs = {hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(): raw
                      for raw in self.files.values()}
        self.tree = [{'path': name, 'type': 'blob', 'mode': '100644', 'size': len(raw),
                      'sha': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}
                     for name, raw in self.files.items()]
        self.grant = {'schema': 'ci-allocation-grant-v2', 'allocation_id': 'offline-example',
            'repository': IDENTITY.repository, 'workflow_path': '.github/workflows/ci.yml',
            'authorization_id': 'OFFLINE-NOT-A-GRANT', 'approved_by': 'synthetic test fixture only',
            'historical_runs_debit': 0, 'historical_consumption': 'synthetic empty new namespace',
            'predecessor': {'allocation_id': '56314', 'bootstrap_sha': OLD, 'accounted_runs': 200,
                            'closure_sha256': '0' * 64},
            'policy': {'not_before': 1, 'expires_at': 4000000000, 'run_cap': 150,
                       'launch_cap': 100, 'cpu_cap': 900},
            'transition': {'head_sha': IDENTITY.head_sha, 'base_sha': 'c' * 40, 'slot': 1},
            'source_files': {name: hashlib.sha256(raw).hexdigest() for name, raw in self.files.items()},
            'ruleset_id': 77}
        self.chosen = {'schema': 'ci-allocation-selection-v1', 'allocation_id': 'offline-example',
            'bootstrap_sha': BOOT, 'grant_sha256': digest(self.grant), 'source_commit': IDENTITY.head_sha,
            'loader_sha256': self.grant['source_files']['scripts/ci_owner_source.py'], 'activation_sha': None}
        self.ruleset = {'id': 77, 'target': 'tag', 'enforcement': 'active', 'bypass_actors': [],
            'conditions': {'ref_name': {'include': ['refs/tags/ci-allocation-offline-example/**'], 'exclude': []}},
            'rules': [{'type': name} for name in ('update', 'deletion', 'non_fast_forward')]}
        self.old_debit = 200
        self.new_slots = {}
        self.jobs = {'total_count': 3, 'jobs': [{'name': name, 'status': 'completed', 'conclusion': 'success'}
                      for name in ('container', 'contracts', 'secret-scan')]}
        self.fail_claim = None

    def refresh(self):
        self.chosen['grant_sha256'] = digest(self.grant)

    def store(self, **kwargs):
        return t.selected_store(IDENTITY.repository, '', self.chosen, request=self.request, **kwargs)

    def respond(self, method, path, body):
        if path == '':
            return self.payload['repository']
        if path == '/rulesets/77':
            return self.ruleset
        if path == '/actions/runs/123/attempts/1/jobs?per_page=100':
            return self.jobs
        if path == '/git/ref/tags/ci-allocation-offline-example/bootstrap':
            return {'object': {'type': 'commit', 'sha': BOOT}}
        if path == '/git/commits/' + BOOT:
            return {'sha': BOOT, 'tree': {'sha': TREE}, 'message': json.dumps(self.grant)}
        if path == '/git/ref/tags/ci-allocation-56314/bootstrap':
            return {'object': {'type': 'commit', 'sha': OLD}}
        if path == '/git/commits/' + OLD:
            return {'sha': OLD, 'tree': {'sha': TREE}, 'message': json.dumps({
                'allocation_id': '56314', 'historical_runs_debit': self.old_debit,
                'historical_consumption': 'synthetic historical accounting'})}
        if path == '/git/matching-refs/tags/ci-allocation-56314/slot-':
            return []
        if path == '/git/matching-refs/tags/ci-allocation-offline-example/slot-':
            return [{'ref': name, 'object': {'type': 'commit', 'sha': sha}}
                    for name, sha in self.new_slots.items()]
        if path in ('/git/commits/' + IDENTITY.head_sha, '/git/commits/' + IDENTITY.build_sha,
                    '/git/commits/' + ACTIVATION):
            value = copy.deepcopy(self.merge)
            value.update(sha=path.rsplit('/', 1)[1], tree={'sha': TREE})
            return value
        if path == '/git/trees/' + TREE + '?recursive=1':
            return {'sha': TREE, 'tree': self.tree, 'truncated': False}
        if path.startswith('/git/blobs/'):
            sha = path.rsplit('/', 1)[1]
            return {'sha': sha, 'encoding': 'base64', 'content': base64.b64encode(self.blobs[sha]).decode()}
        if method == 'POST' and path == '/git/commits':
            sha = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()
            self.commits[sha] = dict(body, sha=sha, parents=[{'sha': parent} for parent in body['parents']])
            return {'sha': sha}
        if method == 'POST' and path == '/git/refs':
            if self.fail_claim == 'conflict' or body['ref'] in self.new_slots:
                raise RefConflict('synthetic concurrent claim')
            self.new_slots[body['ref']] = body['sha']
            if self.fail_claim == 'lost':
                raise RuntimeError('synthetic lost response after durable write')
            return {}
        if path in ('/compare/' + IDENTITY.head_sha + '...' + ACTIVATION,
                    '/compare/' + ACTIVATION + '...' + ACTIVATION):
            return {'status': 'ahead' if IDENTITY.head_sha in path else 'identical'}
        return super().respond(method, path, body)

    def reserve(self):
        store, grant = self.store()
        return t.reserve_transition(store, grant, self.chosen, IDENTITY.run_id)


class TransitionTests(unittest.TestCase):
    def test_legacy_exhaustion_stays_closed_and_new_transition_is_one_of_150(self):
        f = OwnerFixture()
        old = GitHubRefs(IDENTITY.repository, '', request=f.request)
        with self.assertRaisesRegex(RuntimeError, 'exhausted'):
            RefAdmission(old).admit(IDENTITY, now=LEGACY.expires_at - 1)
        receipt = f.reserve()
        self.assertEqual(receipt['slot'], 1)
        self.assertEqual(receipt['allocation_id'], 'offline-example')
        self.assertEqual(len(f.new_slots), 1)
        self.assertEqual(f.old_debit, 200)
        store, grant = f.store()
        with self.assertRaisesRegex(ValueError, 'activation'):
            t.admit_activated(store, grant, f.chosen, f.payload)
        with self.assertRaisesRegex(ValueError, 'occupied'):
            f.reserve()
        # The same production allocator consumes slots2..150, never151.
        for run_id in range(124, 273):
            RefAdmission(store, store.policy).admit(replace(IDENTITY, run_id=str(run_id)))
        with self.assertRaisesRegex(RuntimeError, 'exhausted'):
            RefAdmission(store, store.policy).admit(replace(IDENTITY, run_id='273'))
        self.assertEqual(len(f.new_slots), 150)

    def test_exact_identity_read_and_container_validation_are_read_only(self):
        f = OwnerFixture()
        expected = f.reserve()
        f.writable = False
        store, grant = f.store()
        self.assertEqual(t.reader(store, grant, f.chosen, IDENTITY), expected)
        with patch.dict(os.environ, ADMISSION_RESULT='success'):
            self.assertEqual(t.validate(store, grant, f.chosen, expected, IDENTITY), expected)
            for key, bad in (('allocation_id', '56314'), ('slot', 2), ('bootstrap_sha', '0' * 40),
                             ('owner_grant_sha256', '0' * 64), ('launch_reservation', 101)):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    t.validate(store, grant, f.chosen, dict(expected, **{key: bad}), IDENTITY)
        for identity in (replace(IDENTITY, attempt='2'), replace(IDENTITY, head_sha='8' * 40),
                         replace(IDENTITY, build_sha='9' * 40)):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                t.reader(store, grant, f.chosen, identity)
        for result in ('failure', 'cancelled', 'skipped'):
            with patch.dict(os.environ, ADMISSION_RESULT=result), self.assertRaises(ValueError):
                t.validate(store, grant, f.chosen, expected, IDENTITY)

    def test_shipped_cli_reserve_read_validate_and_lost_response_charge(self):
        for failure in (None, 'lost'):
            f = OwnerFixture()
            f.fail_claim = failure
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / 'admission.json'
                with patch.object(GitHubRefs, '_request', side_effect=f.request), patch.dict(os.environ,
                    CI_ALLOCATION_SELECTION=json.dumps(f.chosen), GITHUB_REPOSITORY=IDENTITY.repository,
                    GITHUB_RUN_ID=IDENTITY.run_id, GITHUB_RUN_ATTEMPT='1', GITHUB_SHA=IDENTITY.build_sha,
                    PR_HEAD_SHA=IDENTITY.head_sha, ADMISSION_RESULT='success', GH_TOKEN='', GITHUB_ACTIONS=''):
                    with patch.object(sys, 'argv', ['transition', 'reserve-transition', str(output), '--run-id', '123']):
                        code = t.main()
                    receipt = json.loads(output.read_text())
                    if failure:
                        self.assertEqual(code, 1)
                        self.assertIsNone(receipt['cpu_seconds'])
                        self.assertEqual(receipt['charged_cpu_seconds'], 900)
                    else:
                        self.assertEqual(code, 0)
                        f.writable = False
                        for mode in ('read', 'validate'):
                            with patch.object(sys, 'argv', ['transition', mode, str(output)]):
                                self.assertEqual(t.main(), 0)
                            self.assertEqual(json.loads(output.read_text()), receipt)

    def test_meter_uses_selected_expiry_and_recovers_after_it(self):
        from scripts.ci_cpu_meter import run, recover, monitor
        from scripts.ci_allocation import CPUAccount
        from scripts.tests.test_ci_cpu_meter import Process
        f = OwnerFixture()
        admission = f.reserve()
        policy = receipt_policy(admission, json.dumps(f.chosen))
        # A time after the old expiry but within the new policy is permitted by
        # the same loop; reaching the new expiry stops before process polling.
        for wall, expected in ((LEGACY.expires_at + 1, ('success', 0)),
                               (policy.expires_at, ('expired', 1))):
            result = monitor(None, Process([0]), CPUAccount(0, 0, 0), cancelled=lambda: False,
                cpu=lambda _: 0, own_cpu=lambda: 0, clock=lambda: 1,
                wall_clock=lambda: wall, expiry=policy.expires_at)
            self.assertEqual(result, expected)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'admission.json').write_text(json.dumps(admission))
            ledger = Ledger(directory / 'events.jsonl', IDENTITY, policy)
            ledger.reserve('synthetic-executable-not-launched')
            with patch.dict(os.environ, CI_ALLOCATION_SELECTION=json.dumps(f.chosen)), \
                    patch('scripts.ci_policy.time.time', return_value=policy.expires_at + 1):
                recover(directory, root=directory)
            result = json.loads((directory / 'settlement.json').read_text())
            self.assertEqual((result['allocation_id'], result['state']), ('offline-example', 'interrupted'))
            self.assertEqual(result['cpu']['charged_cpu_seconds'], 900)

    def test_broker_uses_new_policy_interval_and_still_settles_after_expiry(self):
        from scripts.ci_hotspot_gate import serve
        from unittest.mock import Mock
        f = OwnerFixture()
        policy = grant_policy(f.grant, f.chosen)
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Ledger(Path(temporary) / 'events.jsonl', IDENTITY, policy)
            current = [LEGACY.expires_at + 1]
            with patch('scripts.ci_hotspot_gate.Broker') as broker, patch('scripts.ci_hotspot_gate.threading.Thread'):
                serve(ledger, now=lambda: current[0])
            handler_type = broker.call_args.args[1]
            def post(path, value):
                raw = json.dumps(value).encode()
                handler = object.__new__(handler_type)
                handler.path, handler.headers = path, {'Content-Length': str(len(raw))}
                handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
                handler.connection = Mock()
                handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()
                handler.do_POST()
                return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())
            self.assertEqual(post('/reserve', {'binary': '0' * 64}), (200, {'slot': 1}))
            for when in (0, policy.expires_at, policy.expires_at + 1):
                current[0] = when
                self.assertEqual(post('/reserve', {'binary': '0' * 64})[0], 409)
            self.assertEqual(post('/settle', {'slot': 1, 'state': 'interrupted', 'returncode': 1})[0], 200)
            self.assertEqual(ledger.summary()['launches_settled'], 1)

    def test_source_base_head_attempt_predecessor_and_ruleset_refuse_before_claim(self):
        mutations = [lambda f: f.pull['head'].update(sha='9' * 40),
            lambda f: f.run.update(run_attempt=2), lambda f: f.run.update(path='other.yml'),
            lambda f: f.merge.update(parents=[{'sha': 'c' * 40}, {'sha': '9' * 40}]),
            lambda f: setattr(f, 'old_debit', 199), lambda f: f.ruleset.update(enforcement='evaluate'),
            lambda f: f.ruleset.update(bypass_actors=[{'actor_id': 1}]),
            lambda f: f.ruleset.update(conditions={'ref_name': {'include': ['~ALL'], 'exclude': []}}),
            lambda f: f.ruleset.update(rules=[{'type': 'deletion'}]),
            lambda f: f.tree[0].update(mode='120000'),
            lambda f: f.blobs.update({f.tree[0]['sha']: b'tampered'})]
        for mutate in mutations:
            f = OwnerFixture()
            mutate(f)
            with self.subTest(mutation=mutate), self.assertRaises((ValueError, RuntimeError)):
                # Invalid merge parents fail immediately; no unbounded real polling.
                with patch('scripts.ci_admit.time.sleep', side_effect=AssertionError('unexpected wait')):
                    f.reserve()
            self.assertEqual(f.new_slots, {})
            self.assertFalse([call for call in f.calls if call[0] != 'GET'])

    def test_slot_one_conflict_or_lost_response_never_spills_into_slot_two(self):
        for failure in ('conflict', 'lost'):
            f = OwnerFixture()
            f.fail_claim = failure
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                f.reserve()
            claims = [body['ref'] for method, path, body in f.calls if method == 'POST' and path == '/git/refs']
            self.assertEqual(claims, ['refs/tags/ci-allocation-offline-example/slot-001'])
            f.fail_claim = None
            if failure == 'lost':
                with self.assertRaisesRegex(ValueError, 'occupied'):
                    f.reserve()
                store, grant = f.store()
                self.assertEqual(t.reader(store, grant, f.chosen, IDENTITY)['slot'], 1)

    def test_activation_requires_merged_source_and_real_successful_required_jobs(self):
        f = OwnerFixture()
        f.reserve()
        f.chosen['activation_sha'] = ACTIVATION
        f.tip = ACTIVATION
        f.run.update(status='completed', conclusion='success')
        store, grant = f.store()
        t.activated(store, grant, f.chosen)
        for name in ('container', 'contracts', 'secret-scan'):
            row = next(job for job in f.jobs['jobs'] if job['name'] == name)
            for state in ('failure', 'skipped', 'cancelled'):
                row['conclusion'] = state
                with self.subTest(job=name, state=state), self.assertRaisesRegex(ValueError, 'required gate'):
                    t.activated(store, grant, f.chosen)
            row['conclusion'] = 'success'
        f.run.update(conclusion='failure')
        with self.assertRaisesRegex(ValueError, 'workflow'):
            t.activated(store, grant, f.chosen)

    def test_strict_owner_selection_and_policy_cannot_be_inferred_from_receipts(self):
        f = OwnerFixture()
        self.assertIsNone(selection(''))
        for raw in ('{}', '[]', '{"schema":1,"schema":2}', 'NaN'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                selection(raw)
        receipt = f.reserve()
        with self.assertRaises(ValueError):
            receipt_policy(receipt, '')
        with self.assertRaises(ValueError):
            receipt_policy(receipt, json.dumps(dict(f.chosen, bootstrap_sha='7' * 40)))
        for field, value in (('run_cap', 151), ('cpu_cap', 901), ('launch_cap', 101),
                             ('run_cap', True), ('not_before', 4000000001)):
            bad = copy.deepcopy(f.grant)
            bad['policy'][field] = value
            chosen = dict(f.chosen, grant_sha256=digest(bad))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                grant_policy(bad, chosen)
        with self.assertRaises(ValueError):
            grant_policy(f.grant, f.chosen, now=4000000000)
        self.assertEqual(grant_policy(f.grant, f.chosen, now=4000000000, admitting=False).run_cap, 150)

    def test_activated_writer_and_reader_admit_a_new_run_into_slot_two(self):
        f = OwnerFixture()
        f.reserve()
        f.chosen['activation_sha'] = f.tip = ACTIVATION
        first = dict(f.run, status='completed', conclusion='success')
        next_id = replace(IDENTITY, run_id='456', head_sha='d' * 40, build_sha='e' * 40)
        f.run.update(id=456, head_sha=next_id.head_sha)
        f.payload['workflow_run'] = copy.deepcopy(f.run)
        f.pull['head']['sha'] = next_id.head_sha
        f.pull['base']['sha'] = ACTIVATION
        f.pull['merge_commit_sha'] = next_id.build_sha
        def request(method, path, body=None):
            if method == 'GET' and path == '/actions/runs/123':
                return copy.deepcopy(first)
            if method == 'GET' and path == '/actions/runs/456':
                return copy.deepcopy(f.run)
            if method == 'GET' and path == '/git/commits/' + next_id.build_sha:
                return {'sha': next_id.build_sha, 'tree': {'sha': TREE},
                        'parents': [{'sha': ACTIVATION}, {'sha': next_id.head_sha}]}
            return f.request(method, path, body)
        store, grant = t.selected_store(IDENTITY.repository, '', f.chosen, request=request)
        receipt = t.admit_activated(store, grant, f.chosen, f.payload)
        self.assertEqual((receipt['slot'], receipt['identity']), (2, asdict(next_id)))
        f.writable = False
        self.assertEqual(t.reader(store, grant, f.chosen, next_id), receipt)

    def test_terminal_detects_both_namespaces_and_retains_new_identity_on_old_outage(self):
        for failure in ('duplicate', 'old-unreadable'):
            f = OwnerFixture()
            f.reserve()
            def request(method, path, body=None):
                if path == '/git/ref/tags/ci-allocation-56314/bootstrap' and failure == 'old-unreadable':
                    raise RuntimeError('synthetic old namespace outage')
                if path == '/git/matching-refs/tags/ci-allocation-56314/slot-' and failure == 'duplicate':
                    return [{'ref': 'refs/tags/ci-allocation-56314/slot-001',
                             'object': {'type': 'commit', 'sha': '8' * 40}}]
                if path == '/git/commits/' + '8' * 40:
                    return {'message': json.dumps({'allocation_id': '56314', 'slot': 1,
                            'bootstrap_sha': OLD, 'identity': asdict(IDENTITY)})}
                return f.request(method, path, body)
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                event = directory / 'event.json'
                event.write_text(json.dumps({'workflow_run': {'id': 123, 'run_attempt': 1, 'conclusion': 'cancelled'}}))
                with patch.object(GitHubRefs, '_request', side_effect=request), patch.dict(os.environ,
                    GITHUB_REPOSITORY=IDENTITY.repository, GH_TOKEN='', CI_BOOTSTRAP_AUTHORIZATION='',
                    CI_ALLOCATION_SELECTION=json.dumps(f.chosen), GITHUB_EVENT_PATH=str(event)):
                    reconcile_main(directory)
                result = json.loads((directory / 'terminal.json').read_text())
                self.assertIsNone(result['cpu_seconds'])
                if failure == 'duplicate':
                    self.assertIsNone(result['allocation_id'])
                    self.assertEqual(len(result['durable_matches']), 2)
                    self.assertEqual(result['charged_cpu_seconds'], 1800)
                else:
                    self.assertEqual(result['allocation_id'], 'offline-example')
                    self.assertEqual(result['identity'], asdict(IDENTITY))
                    self.assertEqual(result['charged_cpu_seconds'], 900)
                    self.assertEqual(result['unreadable_namespaces'], ['56314'])

    def test_parent_and_canonical_ref_lineage_cannot_be_relabelled(self):
        for defect in ('parent', 'allocation', 'attempt', 'ref'):
            f = OwnerFixture()
            f.reserve()
            ref, commit_sha = next(iter(f.new_slots.items()))
            commit = f.commits[commit_sha]
            record = json.loads(commit['message'])
            if defect == 'parent':
                commit['parents'] = ['9' * 40]
            elif defect == 'allocation':
                record['allocation_id'] = '56314'
            elif defect == 'attempt':
                record['identity']['attempt'] = '2'
            else:
                f.new_slots[ref.replace('001', '01')] = f.new_slots.pop(ref)
            commit['message'] = json.dumps(record)
            store, _ = f.store()
            with self.subTest(defect=defect), self.assertRaises((ValueError, RuntimeError, TypeError)):
                store.read_slots()

    def test_loader_verifies_every_byte_before_any_write_or_import(self):
        f = OwnerFixture()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'source'
            value = loader.materialize(f.chosen, IDENTITY.repository, output,
                                       lambda path: f.request('GET', path))
            self.assertEqual(value, f.grant)
            self.assertEqual({p.relative_to(output).as_posix(): p.read_bytes()
                              for p in output.rglob('*') if p.is_file()}, f.files)
            t.verify_local(f.grant, output)
        for defect in ('blob', 'manifest', 'selection', 'symlink'):
            f = OwnerFixture()
            if defect == 'blob':
                f.blobs[f.tree[-1]['sha']] += b'changed'
            elif defect == 'manifest':
                f.grant['source_files']['unapproved.py'] = '0' * 64
                f.refresh()
            elif defect == 'selection':
                f.chosen['bootstrap_sha'] = '4' * 40
            else:
                f.tree[-1]['mode'] = '120000'
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / 'source'
                with self.subTest(defect=defect), self.assertRaises((ValueError, KeyError)):
                    loader.materialize(f.chosen, IDENTITY.repository, output, lambda path: f.request('GET', path))
                self.assertFalse(output.exists())

    def test_terminal_keeps_both_policy_identities_and_never_refunds_unknowns(self):
        f = OwnerFixture()
        receipt = f.reserve()
        policy = receipt_policy(receipt, json.dumps(f.chosen), admitting=False)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            ledger = Ledger(directory / 'events.jsonl', IDENTITY, policy)
            ledger.finish('interrupted', {'cpu_seconds': None, 'charged_cpu_seconds': 900,
                                         'measurement': 'supervisor lost; total unknown'})
            measured = ledger.summary()
            self.assertEqual(measured['allocation_id'], policy.allocation_id)
            with self.assertRaises(ValueError):
                reconcile(asdict(IDENTITY), 'failure', measured)  # old policy cannot consume new artifact
            result = reconcile(asdict(IDENTITY), 'failure', measured, policy=policy)
            self.assertEqual(result['settlement']['cpu']['charged_cpu_seconds'], 900)
            (directory / 'event.json').write_text(json.dumps({'workflow_run': {
                'id': 123, 'run_attempt': 1, 'conclusion': 'cancelled'}}))
            with patch.object(GitHubRefs, '_request', side_effect=f.request), patch.dict(os.environ,
                GITHUB_REPOSITORY=IDENTITY.repository, GH_TOKEN='', CI_BOOTSTRAP_AUTHORIZATION='',
                CI_ALLOCATION_SELECTION=json.dumps(f.chosen), GITHUB_EVENT_PATH=str(directory / 'event.json')):
                reconcile_main(directory)
            terminal = json.loads((directory / 'terminal.json').read_text())
            self.assertEqual(terminal['allocation_id'], policy.allocation_id)
            self.assertEqual(terminal['identity'], asdict(IDENTITY))
            self.assertEqual((terminal['charged_launches'], terminal['charged_cpu_seconds']), (100, 900))
            self.assertIsNone(terminal['cpu_seconds'])
            with self.assertRaises(RuntimeError):
                Ledger(directory / 'events.jsonl', IDENTITY)  # cannot relabel/reopen a new journal as old

    def test_real_workflow_bootstrap_refuses_bad_loader_hash_before_execution(self):
        # Execute the actual inline Python from both workflow blocks. A valid
        # owner hash is required before subprocess can execute even one byte.
        for name, step in (('admission', 'Read global run slot from trusted allocation controller'),
                           ('container', 'Validate admission before any workload')):
            shell = shell_step(name, step)
            inline = shell.split("python3 -I -S - <<'PY'\n", 1)[1].split('\nPY', 1)[0]
            chosen = OwnerFixture().chosen
            raw = b'raise AssertionError("unverified loader executed")\n'
            response = io.BytesIO(json.dumps({'encoding': 'base64', 'content': base64.b64encode(raw).decode()}).encode())
            with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,
                    CI_ALLOCATION_SELECTION=json.dumps(chosen), GITHUB_REPOSITORY=IDENTITY.repository,
                    RUNNER_TEMP=temporary, GH_TOKEN='fake'), \
                    patch('urllib.request.urlopen', return_value=response), patch('subprocess.run') as execute:
                with self.subTest(job=name), self.assertRaisesRegex(ValueError, 'source mismatch'):
                    exec(compile(inline, 'actual-workflow-inline', 'exec'), {})
                execute.assert_not_called()
                self.assertEqual(list(Path(temporary).iterdir()), [])
        container = job('container')
        self.assertIn('if: always()', container)
        self.assertIn('CI_CONTROLLER_DIRECTORY: ${{ steps.admission-check.outputs.controller-directory }}', container)
        self.assertIn('sudo --preserve-env=CI_ALLOCATION_SELECTION', container)
        self.assertIn('python3 -I -S -c', container)
        self.assertNotIn(': write', (ROOT / '.github/workflows/ci.yml').read_text())


if __name__ == '__main__':
    unittest.main()
