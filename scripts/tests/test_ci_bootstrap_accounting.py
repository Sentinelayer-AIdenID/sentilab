"""Attempt-specific bootstrap accounting at the terminal CLI boundary."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from scripts import ci_reconcile
from scripts.ci_allocation import Ledger
from scripts.tests import test_ci_workflow as workflow
from scripts.tests.test_ci_allocation import IDENTITY
from scripts.tests.test_ci_bootstrap_attempt import attempt_two
from scripts.tests.test_ci_context import pin


class BootstrapAccountingTests(unittest.TestCase):
    def setUp(self):
        self.authorization = attempt_two(workflow.WorkflowTests().authorization())
        self.event = {'id': 123, 'run_attempt': 2, 'conclusion': 'success',
                      'path': '.github/workflows/ci.yml', 'event': 'pull_request',
                      'head_sha': IDENTITY.head_sha,
                      'pull_requests': [{'head': {'sha': IDENTITY.head_sha},
                                         'base': {'sha': 'c' * 40}}]}
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        ledger = Ledger(self.root / 'events.jsonl', replace(IDENTITY, attempt='2'))
        slot = ledger.reserve('fake')
        ledger.started(slot, 123)
        ledger.settle(slot, 'success', 0)
        ledger.finish('success', {'cpu_seconds': 1.25, 'charged_cpu_seconds': 1.25})
        self.settlement = ledger.summary()
        context_json = json.dumps(workflow.WorkflowTests().context(attempt='2'), sort_keys=True, separators=(',', ':'))
        self.admission = dict(workflow.WorkflowTests().receipt(), identity=self.settlement['identity'],
                              mode='bootstrap', base_sha='c' * 40, runtime_context_json=context_json,
                              runtime_context_sha256=hashlib.sha256(context_json.encode()).hexdigest())

    def terminal(self, event=None, settlement=None, *, missing=False, admission=None,
                 missing_admission=False):
        event_path = self.root / 'event.json'
        event_path.write_text(json.dumps({'workflow_run': event or self.event}))
        output = self.root / 'terminal'
        artifact = output / 'download/settlement.json'
        artifact.parent.mkdir(parents=True, exist_ok=True)
        (artifact.parent / 'admission.json').write_text(json.dumps(
            self.admission if admission is None else admission))
        if missing_admission:
            (artifact.parent / 'admission.json').unlink()
        if missing:
            artifact.unlink(missing_ok=True)
        else:
            artifact.write_text(json.dumps(settlement or self.settlement))
        with patch.dict(os.environ, GITHUB_EVENT_PATH=str(event_path), GH_TOKEN='fake',
                        GITHUB_REPOSITORY=IDENTITY.repository,
                        CI_BOOTSTRAP_AUTHORIZATION=json.dumps(self.authorization)), \
             patch.object(sys, 'argv', ['ci_reconcile', str(output)]), \
             patch.object(ci_reconcile, 'GitHubRefs') as store:
            store.return_value.read_slots.return_value = {}
            ci_reconcile.main()
        return json.loads((output / 'terminal.json').read_text())

    def assert_admitted(self):
        result = self.terminal()
        self.assertEqual(result['measurement'], 'settlement artifact')
        self.assertEqual(result['identity'], self.settlement['identity'])
        self.assertEqual(result['rollout_debit']['attempt'], '2')
        self.assertEqual(result['rollout_debit']['charged_launches'], 100)
        self.assertEqual(result['rollout_debit']['charged_cpu_seconds'], 900)

    def test_exact_attempt_two_measurement_and_lost_artifact_charge(self):
        self.assert_admitted()
        result = self.terminal(missing=True)
        self.assertEqual(result['identity']['attempt'], '2')
        self.assertEqual(result['rollout_debit']['attempt'], '2')
        self.assertIsNone(result['cpu_seconds'])
        self.assertEqual(result['charged_cpu_seconds'], 900)
        self.assertEqual(result['charged_launches'], 100)

    def test_attempt_two_terminal_rejects_each_replay_without_claiming_measurement(self):
        cases = [('run_attempt', 3), ('run_attempt', 1), ('id', 456),
                 ('head_sha', 'd' * 40), ('base_sha', 'd' * 40),
                 ('build_sha', 'd' * 40), ('job', 'other'), ('matrix', {'shard': 1}),
                 ('path', '.github/workflows/other.yml')]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assert_admitted()
                event, settlement = copy.deepcopy(self.event), copy.deepcopy(self.settlement)
                if field == 'base_sha':
                    event['pull_requests'][0]['base']['sha'] = value
                elif field in ('build_sha', 'job', 'matrix'):
                    settlement['identity'][field] = value
                else:
                    event[field] = value
                result = self.terminal(event, settlement)
                self.assertNotIn('settlement', result)
                self.assertIsNone(result['cpu_seconds'])
                self.assertEqual(result['charged_cpu_seconds'], 900)
                self.assertEqual(result['charged_launches'], 100)
                if field == 'run_attempt':
                    self.assertEqual(result['attempt'], str(value))
                    self.assertNotIn('rollout_debit', result)

    def test_mismatched_or_missing_admission_cannot_supply_build_identity(self):
        for field, value in [('build_sha', 'd' * 40), ('job', 'other'), ('matrix', {'shard': 1}),
                             ('attempt', '3'), ('base_sha', 'd' * 40), ('missing', None)]:
            with self.subTest(field=field):
                self.assert_admitted()
                admission = copy.deepcopy(self.admission)
                if field == 'missing':
                    admission = {}
                elif field == 'base_sha':
                    admission[field] = value
                else:
                    admission['identity'][field] = value
                result = self.terminal(admission=admission, missing_admission=field == 'missing')
                self.assertNotIn('settlement', result)
                self.assertIsNone(result['cpu_seconds'])
                self.assertEqual(result['charged_launches'], 100)
                self.assertEqual(result['charged_cpu_seconds'], 900)

    def test_conflicting_owner_context_is_refused_even_when_artifact_copies_it(self):
        for key, value in [('GITHUB_SHA', 'd' * 40), ('GITHUB_RUN_ID', '456'),
                           ('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_RUN_ATTEMPT', '2'),
                           ('head_sha', 'd' * 40), ('base_sha', 'd' * 40),
                           ('job', 'other'), ('matrix', {'shard': 1}),
                           ('GITHUB_WORKFLOW_REF', 'example/repo/.github/workflows/other.yml@main')]:
            with self.subTest(key=key):
                self.authorization = attempt_two(workflow.WorkflowTests().authorization())
                self.assert_admitted()
                entry = self.authorization['runs'][0]
                pinned = json.loads(entry['context_json'])
                pinned[key] = value
                pin(entry, pinned)
                live = dict(pinned, GITHUB_RUN_ATTEMPT='2')
                raw = json.dumps(live, sort_keys=True, separators=(',', ':'))
                admission = dict(self.admission, runtime_context_json=raw,
                                 runtime_context_sha256=hashlib.sha256(raw.encode()).hexdigest())
                result = self.terminal(admission=admission)
                self.assertNotIn('settlement', result)
                self.assertIsNone(result['cpu_seconds'])
                self.assertEqual(result['charged_launches'], 100)
                self.assertEqual(result['charged_cpu_seconds'], 900)


if __name__ == '__main__':
    unittest.main()
