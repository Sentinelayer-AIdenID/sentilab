"""The owner pins actual runtime context before authorizing its next attempt."""
import hashlib
import json
import unittest

from scripts.tests import test_ci_workflow as workflow


def pin(entry, context):
    entry['context_json'] = json.dumps(context, sort_keys=True, separators=(',', ':'))
    entry['context_sha256'] = hashlib.sha256(entry['context_json'].encode()).hexdigest()


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workflow.WorkflowTests()

    def admitted(self):
        process, receipt, _ = self.fixture.bootstrap()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(receipt['identity']['attempt'], '2')
        return receipt

    def test_context_is_canonical_captured_before_checkout_and_uploaded_on_refusal(self):
        job = workflow.job('admission')
        first = job.split('    steps:\n', 1)[1]
        self.assertTrue(first.startswith('      - name: Record runtime context before admission\n'))
        self.assertLess(job.index('Preserve runtime context even on refusal'), job.index('actions/checkout@'))
        self.assertIn('name: Preserve runtime context even on refusal\n        if: always()', job)
        self.assertIn('name: allocation-context-${{ github.run_id }}-${{ github.run_attempt }}', job)
        process, receipt, base = self.fixture.bootstrap(
            authorization='', environment_overrides={'GITHUB_RUN_ATTEMPT': '1'})
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(receipt['state'], 'admission_refused')
        raw = receipt['runtime_context_json']
        self.assertEqual(json.loads(raw), self.fixture.context(base))
        self.assertEqual(raw, json.dumps(self.fixture.context(base), sort_keys=True, separators=(',', ':')))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(receipt['runtime_context_sha256'], digest)
        self.assertIn('CI runtime context sha256: ' + digest, process.stdout)
        self.assertEqual(receipt['rollout_debit']['charged_launches'], 0)

    def test_every_pinned_context_field_is_exact(self):
        changes = [('GITHUB_SHA', 'd' * 40), ('GITHUB_RUN_ID', '456'),
                   ('GITHUB_REPOSITORY', 'other/repo'),
                   ('GITHUB_WORKFLOW_REF', 'example/repo/.github/workflows/ci.yml@refs/heads/other'),
                   ('head_sha', 'd' * 40), ('base_sha', 'd' * 40),
                   ('job', 'other'), ('matrix', {'shard': 1})]
        for key, value in changes:
            with self.subTest(key=key):
                self.admitted()

                def authorization(auth, key=key, value=value):
                    entry = auth['runs'][0]
                    context = json.loads(entry['context_json'])
                    context[key] = value
                    pin(entry, context)
                    return auth

                self.refused(authorization)

    def refused(self, authorization):
        process, receipt, _ = self.fixture.bootstrap(authorization=authorization)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(receipt['state'], 'admission_refused')
        self.assertEqual(receipt['rollout_debit']['charged_launches'], 100)
        self.assertEqual(receipt['rollout_debit']['charged_cpu_seconds'], 900)

    def test_pinned_attempt_must_be_the_immediate_predecessor_without_normalization(self):
        for previous in ('2', '3', '0', '01', 1):
            with self.subTest(previous=previous):
                self.admitted()

                def authorization(auth, previous=previous):
                    entry = auth['runs'][0]
                    context = json.loads(entry['context_json'])
                    context['GITHUB_RUN_ATTEMPT'] = previous
                    pin(entry, context)
                    return auth

                self.refused(authorization)

    def test_missing_corrupt_noncanonical_or_extra_context_is_fully_charged(self):
        for kind in ('missing', 'digest', 'noncanonical', 'extra_field', 'missing_field', 'extra_entry_field'):
            with self.subTest(kind=kind):
                self.admitted()

                def authorization(auth, kind=kind):
                    entry = auth['runs'][0]
                    context = json.loads(entry['context_json'])
                    if kind == 'missing':
                        del entry['context_json']
                    elif kind == 'digest':
                        entry['context_sha256'] = 'd' * 64
                    elif kind == 'noncanonical':
                        entry['context_json'] += '\n'
                        entry['context_sha256'] = hashlib.sha256(entry['context_json'].encode()).hexdigest()
                    elif kind == 'extra_entry_field':
                        entry['unexpected'] = True
                    else:
                        if kind == 'extra_field':
                            context['extra'] = 'not runtime context'
                        else:
                            del context['job']
                        pin(entry, context)
                    return auth

                self.refused(authorization)


if __name__ == '__main__':
    unittest.main()
