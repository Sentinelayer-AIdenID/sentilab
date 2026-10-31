"""Execute the workflow's two-stage bootstrap and reject attempt-2 replays."""
import copy
import json
import unittest

from scripts.tests import test_ci_workflow as workflow


def attempt_two(authorization):
    authorization['runs'][0]['identity']['attempt'] = '2'
    return authorization


class BootstrapAttemptTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workflow.WorkflowTests()

    def admitted(self):
        process, receipt, base = self.fixture.bootstrap(
            authorization=attempt_two, environment_overrides={'GITHUB_RUN_ATTEMPT': '2'})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(receipt['identity']['attempt'], '2')
        self.assertEqual(receipt['rollout_debit']['attempt'], '2')
        self.assertEqual(receipt['rollout_debit']['run_id'], receipt['identity']['run_id'])
        self.assertEqual(receipt['rollout_debit']['charged_launches'], 100)
        self.assertEqual(receipt['rollout_debit']['charged_cpu_seconds'], 900)
        return receipt, base

    def test_attempt_two_is_admitted_and_validated_with_its_actual_debit(self):
        receipt, base = self.admitted()
        process = self.fixture.validate(json.dumps(receipt), environment_overrides={
            'GITHUB_RUN_ATTEMPT': '2', 'TRUSTED_BASE_SHA': base})
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_attempt_one_refusal_retains_a_separate_zero_workload_record(self):
        process, receipt, base = self.fixture.bootstrap(authorization='', environment_overrides={'GITHUB_RUN_ATTEMPT': '1'})
        self.assertNotEqual(process.returncode, 0)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt['state'], 'admission_refused')
        self.assertEqual(receipt['identity']['attempt'], '1')
        self.assertEqual(receipt['base_sha'], base)
        self.assertEqual(receipt['rollout_debit']['attempt'], '1')
        self.assertEqual(receipt['rollout_debit']['charged_launches'], 0)
        self.assertEqual(receipt['rollout_debit']['charged_cpu_seconds'], 0)
        self.assertEqual(self.fixture.validate(json.dumps(receipt)).returncode, 1)
        admission = workflow.job('admission')
        self.assertIn('name: allocation-admission-${{ github.run_id }}-${{ github.run_attempt }}', admission)
        self.assertIn('name: Preserve admission or refusal\n        if: always()', admission)
        admitted, _ = self.admitted()
        self.assertEqual(admitted['identity']['run_id'], receipt['identity']['run_id'])
        self.assertNotEqual(admitted['identity']['attempt'], receipt['identity']['attempt'])

    def test_attempt_two_authorization_refuses_each_replay(self):
        cases = [
            ('attempt_three', {}, {'GITHUB_RUN_ATTEMPT': '3'}),
            ('attempt_one', {}, {'GITHUB_RUN_ATTEMPT': '1'}),
            ('run_id', {}, {'GITHUB_RUN_ID': '456'}),
            ('repository', {}, {'GITHUB_REPOSITORY': 'other/repo'}),
            ('head_sha', {}, {'PR_HEAD_SHA': 'd' * 40}),
            ('build_sha', {}, {'GITHUB_SHA': 'd' * 40}),
            ('base_sha', {'base_sha': 'd' * 40}, {}),
            ('job', {'identity.job': 'other'}, {}),
            ('matrix', {'identity.matrix': {'shard': 1}}, {}),
            ('workflow_path', {'workflow_path': '.github/workflows/other.yml'}, {}),
            ('workflow_ref', {}, {'GITHUB_WORKFLOW_REF': 'other/repo/.github/workflows/ci.yml@main'}),
            ('expired', {'expires_at': 0}, {}),
            ('malformed_entry', {'entry': {}}, {}),
            ('duplicate_entry', {'duplicate': True}, {}),
            ('numeric_attempt', {'identity.attempt': 2}, {}),
            ('nondigit_attempt', {'identity.attempt': 'two'}, {}),
            ('empty_attempt', {'identity.attempt': ''}, {}),
        ]
        for name, changes, environment in cases:
            with self.subTest(replay=name):
                # A refusal is meaningful only alongside acceptance of the exact authorization.
                self.admitted()

                def authorization(value, changes=changes):
                    value = attempt_two(value)
                    entry = value['runs'][0]
                    for key, change in changes.items():
                        if key.startswith('identity.'):
                            entry['identity'][key.split('.')[1]] = change
                        elif key == 'base_sha':
                            entry[key] = change
                        elif key == 'entry':
                            value['runs'] = [change]
                        elif key == 'duplicate':
                            value['runs'].append(copy.deepcopy(entry))
                        else:
                            value[key] = change
                    return value

                process, receipt, _ = self.fixture.bootstrap(
                    authorization=authorization,
                    environment_overrides={'GITHUB_RUN_ATTEMPT': '2', **environment})
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual(receipt['state'], 'admission_refused')
                self.assertEqual(receipt['identity']['attempt'], environment.get('GITHUB_RUN_ATTEMPT', '2'))
                self.assertEqual(receipt['rollout_debit']['charged_launches'], 100)
                self.assertEqual(receipt['rollout_debit']['charged_cpu_seconds'], 900)

    def test_container_refuses_attempt_two_receipt_replayed_on_other_attempts(self):
        receipt, base = self.admitted()
        for attempt in ('1', '3', '', 'two'):
            with self.subTest(attempt=attempt):
                process = self.fixture.validate(json.dumps(receipt), environment_overrides={
                    'GITHUB_RUN_ATTEMPT': attempt, 'TRUSTED_BASE_SHA': base})
                self.assertEqual(process.returncode, 1)
        durable = dict(self.fixture.receipt(), identity=receipt['identity'])
        self.assertEqual(self.fixture.validate(json.dumps(durable), environment_overrides={
            'GITHUB_RUN_ATTEMPT': '2'}).returncode, 1)


if __name__ == '__main__':
    unittest.main()
