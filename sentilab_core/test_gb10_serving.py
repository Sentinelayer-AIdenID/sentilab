"""Host bridge tests use retained, bounded response fakes; no SSH invocation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

from sentilab_core import gb10_backend as backend
from sentilab_core import gb10_serving as bridge


class ServingBridge(unittest.TestCase):
    def payload(self, action='status', ok=True):
        value = {'schema': bridge.SCHEMA, 'action': action, 'ok': ok, 'scope_state': 'staged_open',
                 'identity': backend.EXPECTED_IDENTITY.copy(), 'controller_sha256': bridge.CONTROLLER_SHA256,
                 'policy_sha256': bridge.POLICY_SHA256}
        value.update({'result': {'phase': 'not_started'}} if ok else {'error': 'exact_independent_review_required'})
        return value

    def test_source_and_policy_pins_match_authored_controller(self):
        source = Path(__file__).resolve().parents[1] / 'scripts/gb10/serve047.py'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), bridge.CONTROLLER_SHA256)
        spec = importlib.util.spec_from_file_location('pin_only', source)
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        self.assertEqual(controller.POLICY_SHA, bridge.POLICY_SHA256)
        self.assertEqual(controller.POLICY['max_attempts'], 1)
        self.assertEqual(controller.POLICY['max_inference_requests'], 20)

    def test_each_valid_action_uses_fixed_ssh_and_exact_source_bootstrap(self):
        for action in ['start', 'status', 'stop']:
            with mock.patch.object(backend, '_capture', return_value=json.dumps(self.payload(action)).encode()) as call:
                value = backend.execute('serve', action=action)
            self.assertTrue(value['ok'])
            self.assertEqual(value['scope_state'], 'staged_open')
            self.assertFalse(value['final_deliverable_accepted'])
            argv, source = call.call_args.args
            self.assertEqual(argv[-2:], ['gb10', 'python3 -I -S -B - '+action])
            self.assertIn('StrictHostKeyChecking=yes', argv)
            self.assertIn('ClearAllForwardings=yes', argv)
            self.assertIn('ControlPath=none', argv)
            self.assertIn(bridge.CONTROLLER_SHA256.encode(), source)
            self.assertIn(b'compile(s,p', source)
            self.assertLess(len(source), backend.MAX_SCRIPT_BYTES)

    def test_caller_cannot_supply_host_path_source_approval_or_grant(self):
        with mock.patch.object(backend, '_capture', side_effect=AssertionError('unexpected SSH')):
            for key in ['host', 'path', 'source', 'approval', 'grant', 'image', 'request', 'context_override']:
                self.assertEqual(backend.execute('serve', action='start', **{key:'fixture'})['error']['code'], 'invalid_input')
            for action in [None, [], {}, 1, True, 'run', 'start; sh']:
                self.assertEqual(backend.execute('serve', action=action)['error']['code'], 'invalid_input')

    def test_remote_refusal_is_not_reported_as_gpu_or_capability_success(self):
        with mock.patch.object(backend, '_capture', return_value=json.dumps(self.payload('start',False)).encode()):
            result = backend.execute('serve', action='start')
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(result['error']['code'], 'exact_independent_review_required')

    def test_cross_operation_identity_source_and_policy_responses_rejected(self):
        mutations = [('action', 'stop'), ('schema', 'other'), ('scope_state', 'complete'),
                     ('controller_sha256', '0'*64), ('policy_sha256', '0'*64), ('identity', {}), ('ok', 'true'),
                     ('result', {'phase':None})]
        for key, value in mutations:
            payload = self.payload(); payload[key] = value
            with mock.patch.object(backend, '_capture', return_value=json.dumps(payload).encode()):
                result = backend.execute('serve')
            self.assertEqual(result['error']['code'], 'invalid_serving_response', key)

    def test_duplicate_keys_and_extra_fields_rejected(self):
        raw = json.dumps(self.payload()).encode()
        bad = [raw[:-1]+b',"ok":true}', json.dumps({**self.payload(), 'extra':True}).encode(), b'NaN']
        for data in bad:
            with mock.patch.object(backend, '_capture', return_value=data):
                self.assertEqual(backend.execute('serve')['error']['code'], 'invalid_serving_response')


if __name__ == '__main__': unittest.main()
