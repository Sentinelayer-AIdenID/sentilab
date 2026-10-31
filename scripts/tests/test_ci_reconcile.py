"""Terminal artifact validation through the shipped reconciler and CLI boundary."""
import copy
import json
import os
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from scripts.ci_allocation import Ledger
from scripts.ci_reconcile import main, reconcile
from scripts.tests.test_ci_allocation import IDENTITY


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        ledger = Ledger(self.root / 'events.jsonl', IDENTITY)
        slot = ledger.reserve('fake')
        ledger.started(slot, 123)
        ledger.settle(slot, 'success', 0)
        ledger.finish('success', {'cpu_seconds': 12.5, 'charged_cpu_seconds': 12.5,
                                  'measurement': 'cgroup-v2 plus supervisor rusage'})
        self.valid = ledger.summary()

    def malformed(self):
        yield 'array', []
        yield 'scalar', 'bad'
        yield 'identity only', {'identity': asdict(IDENTITY), 'allocation_id': '56314'}
        for field in ('schema', 'state', 'cpu', 'launches_reserved', 'launches_settled',
                      'executions_started', 'direct_call_violations'):
            value = copy.deepcopy(self.valid)
            del value[field]
            yield 'missing ' + field, value
        for field, invalid in (('schema', 'v999'), ('state', 'made_up'), ('state', []),
                               ('launches_reserved', -1), ('launches_reserved', 101),
                               ('launches_settled', 0), ('executions_started', 2),
                               ('executions_started', True), ('direct_call_violations', -1),
                               ('launches_reserved', 1.0), ('cpu', [])):
            value = copy.deepcopy(self.valid)
            value[field] = invalid
            yield field + '=' + repr(invalid), value
        for field in ('cpu_seconds', 'charged_cpu_seconds', 'cgroup_cpu_seconds', 'supervisor_cpu_seconds'):
            for invalid in (-1, float('nan'), float('inf'), '12.5', True):
                value = copy.deepcopy(self.valid)
                value['cpu'][field] = invalid
                yield field + '=' + repr(invalid), value
        for cpu in ({}, {'cpu_seconds': None}, {'cpu_seconds': None, 'charged_cpu_seconds': 900},
                    {'cpu_seconds': None, 'measurement': 'unavailable', 'charged_cpu_seconds': 899},
                    {'cpu_seconds': 12.5, 'charged_cpu_seconds': 10}):
            value = copy.deepcopy(self.valid)
            value['cpu'] = cpu
            yield 'invalid CPU ' + repr(cpu), value

    def assert_conservative(self, result):
        self.assertIsNone(result['cpu_seconds'])
        self.assertIsNone(result['executions_started'])
        self.assertEqual(result['charged_launches'], 100)
        self.assertEqual(result['charged_cpu_seconds'], 900)
        self.assertNotIn('settlement', result)

    def test_malformed_settlements_never_become_measured_evidence(self):
        self.check_known_measurement_and_explicit_unknown_full_charge_are_supported()
        for name, settlement in self.malformed():
            with self.subTest(name=name):
                result = reconcile(asdict(IDENTITY), 'failure', settlement)
                self.assert_conservative(result)

    def test_main_always_writes_conservative_terminal_for_malformed_artifacts(self):
        event_path = self.root / 'event.json'
        event_path.write_text(json.dumps({'workflow_run': {'id': 123, 'run_attempt': 1,
                                                         'conclusion': 'failure'}}))
        output = self.root / 'output'
        artifact = output / 'download/settlement.json'
        artifact.parent.mkdir(parents=True)
        with patch('scripts.ci_reconcile.GitHubRefs') as store, \
             patch.dict(os.environ, GITHUB_EVENT_PATH=str(event_path),
                        GITHUB_REPOSITORY=IDENTITY.repository, GH_TOKEN='fake'), \
             patch.object(sys, 'argv', ['ci_reconcile', str(output)]):
            store.return_value.read_slots.return_value = {1: asdict(IDENTITY)}
            for raw in ('[]', '{', 'NaN', json.dumps(dict(self.valid, state='not-terminal'))):
                with self.subTest(raw=raw[:40]):
                    (output / 'terminal.json').unlink(missing_ok=True)
                    artifact.write_text(raw)
                    main()
                    result = json.loads((output / 'terminal.json').read_text())
                    self.assert_conservative(result)
                    self.assertEqual(result['identity'], asdict(IDENTITY))

    def test_main_preserves_joint_violations_and_known_higher_charge(self):
        event_path = self.root / 'event.json'
        event_path.write_text(json.dumps({'workflow_run': {'id': 123, 'run_attempt': 1,
                                                         'conclusion': 'failure'}}))
        output = self.root / 'joint'
        artifact = output / 'download/settlement.json'
        artifact.parent.mkdir(parents=True)
        with patch('scripts.ci_reconcile.GitHubRefs') as store, \
             patch.dict(os.environ, GITHUB_EVENT_PATH=str(event_path),
                        GITHUB_REPOSITORY=IDENTITY.repository, GH_TOKEN='fake',
                        CI_BOOTSTRAP_AUTHORIZATION=''), \
             patch.object(sys, 'argv', ['ci_reconcile', str(output)]):
            store.return_value.read_slots.return_value = {1: asdict(IDENTITY)}
            for seconds in (901, 910):
                for state in ('cpu_limit_violated', 'launch_violation', 'inconclusive'):
                    for legacy in (False, True):
                        with self.subTest(seconds=seconds, state=state, legacy=legacy):
                            value = copy.deepcopy(self.valid)
                            value.update(state=state, direct_call_violations=1,
                                         violations=['cpu_limit_violated', 'launch_violation'])
                            if legacy:
                                del value['violations']
                            value['cpu'].update(cpu_seconds=seconds, charged_cpu_seconds=seconds)
                            artifact.write_text(json.dumps(value))
                            main()
                            result = json.loads((output / 'terminal.json').read_text())
                            self.assertEqual(result['settlement'], value)

    def test_joint_violation_validation_still_refuses_malformed_evidence(self):
        joint = copy.deepcopy(self.valid)
        joint.update(state='launch_violation', direct_call_violations=1,
                     violations=['cpu_limit_violated', 'launch_violation'])
        joint['cpu'].update(cpu_seconds=910, charged_cpu_seconds=910)
        for field, invalid in (('violations', None), ('violations', 'cpu_limit_violated'),
                               ('violations', []), ('violations', ['launch_violation']),
                               ('violations', ['cpu_limit_violated'] * 2),
                               ('direct_call_violations', 0), ('state', 'success'),
                               ('launches_settled', 0), ('executions_started', True)):
            with self.subTest(field=field, invalid=invalid):
                value = copy.deepcopy(joint)
                value[field] = invalid
                self.assert_conservative(reconcile(asdict(IDENTITY), 'failure', value))
        for field, invalid in (('cpu_seconds', float('nan')), ('cpu_seconds', '910'),
                               ('charged_cpu_seconds', 900), ('charged_cpu_seconds', float('inf'))):
            with self.subTest(field=field, invalid=invalid):
                value = copy.deepcopy(joint)
                value['cpu'][field] = invalid
                self.assert_conservative(reconcile(asdict(IDENTITY), 'failure', value))
        # Even a below-cap CPU record cannot invent a violation list.
        value = copy.deepcopy(self.valid)
        value['violations'] = ['cpu_limit_violated']
        self.assert_conservative(reconcile(asdict(IDENTITY), 'failure', value))

    def check_known_measurement_and_explicit_unknown_full_charge_are_supported(self):
        result = reconcile(asdict(IDENTITY), 'success', self.valid)
        self.assertEqual(result['settlement']['cpu']['cpu_seconds'], 12.5)
        for state in ('inconclusive', 'interrupted'):
            value = copy.deepcopy(self.valid)
            value['state'] = state
            value['cpu'] = {'cpu_seconds': None, 'charged_cpu_seconds': 900,
                            'measurement': 'supervisor lost; total unknown'}
            result = reconcile(asdict(IDENTITY), 'failure', value)
            self.assertEqual(result['settlement']['cpu']['charged_cpu_seconds'], 900)
            self.assertIsNone(result['settlement']['cpu']['cpu_seconds'])

    def test_bootstrap_is_reconciled_from_owner_provenance_without_a_slot(self):
        from scripts.tests.test_ci_workflow import WorkflowTests

        authorization = WorkflowTests().authorization()
        ledger = Ledger(self.root / 'bootstrap-events.jsonl', IDENTITY)
        for _ in range(2):
            slot = ledger.reserve('fake')
            ledger.started(slot, 123)
            ledger.settle(slot, 'success', 0)
        ledger.finish('success', {'cpu_seconds': 12.5, 'charged_cpu_seconds': 12.5})
        measured = json.dumps(ledger.summary())
        event_path = self.root / 'event.json'
        event_path.write_text(json.dumps({'workflow_run': {'id': 123, 'run_attempt': 1,
                            'conclusion': 'failure', 'path': '.github/workflows/ci.yml'}}))
        output = self.root / 'bootstrap'
        artifact = output / 'download/settlement.json'
        artifact.parent.mkdir(parents=True)
        with patch('scripts.ci_reconcile.GitHubRefs') as store, \
             patch.dict(os.environ, GITHUB_EVENT_PATH=str(event_path), GH_TOKEN='fake',
                        GITHUB_REPOSITORY=IDENTITY.repository,
                        CI_BOOTSTRAP_AUTHORIZATION=json.dumps(authorization)), \
             patch.object(sys, 'argv', ['ci_reconcile', str(output)]):
            store.return_value.read_slots.return_value = {}
            for raw in (measured, None, '[]'):
                with self.subTest(raw=raw):
                    artifact.unlink(missing_ok=True)
                    if raw is not None:
                        artifact.write_text(raw)
                    main()
                    result = json.loads((output / 'terminal.json').read_text())
                    self.assertEqual(result['admission_mode'], 'bootstrap')
                    self.assertEqual(result['identity'], asdict(IDENTITY))
                    self.assertEqual(result['rollout_debit']['charged_cpu_seconds'], 900)
                    self.assertEqual(result['rollout_debit']['charged_launches'], 100)
                    if raw == measured:
                        self.assertEqual(result['settlement']['executions_started'], 2)
                        self.assertEqual(result['settlement']['cpu']['cpu_seconds'], 12.5)
                    else:
                        self.assert_conservative(result)

    def test_absent_or_unverifiable_bootstrap_provenance_cannot_claim_zero_usage(self):
        event_path = self.root / 'event.json'
        event_path.write_text(json.dumps({'workflow_run': {'id': 123, 'run_attempt': 1,
                                                         'conclusion': 'cancelled'}}))
        output = self.root / 'lost-bootstrap'
        with patch('scripts.ci_reconcile.GitHubRefs') as store, \
             patch.dict(os.environ, GITHUB_EVENT_PATH=str(event_path), GH_TOKEN='fake',
                        GITHUB_REPOSITORY=IDENTITY.repository, CI_BOOTSTRAP_AUTHORIZATION=''), \
             patch.object(sys, 'argv', ['ci_reconcile', str(output)]):
            store.return_value.read_slots.return_value = {}
            main()
        self.assert_conservative(json.loads((output / 'terminal.json').read_text()))
