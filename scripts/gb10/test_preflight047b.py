"""Finite tests: no Docker, SSH, sockets, compiler or native execution."""
import ast
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('preflight047b', Path(__file__).with_name('preflight047b.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def proof():
    return {'schema': 'sentilab-047b-scratch-proof/1', 'error': None,
            'uid': 1000, 'gid': 1000, 'euid': 1000, 'egid': 1000, 'tmp_mode': 0o1777,
            'compiler_returncode': 0, 'library_result': 47, 'script_returncode': 47,
            'nvidia_devices': [], 'nvidia_visible_devices': 'void', 'cuda_visible_devices': '-1',
            'mountinfo': '36 29 0:30 / / ro,relatime - overlay overlay ro\n38 36 0:32 / /tmp rw,nosuid,nodev - tmpfs tmpfs rw,size=4194304k\n',
            'hashes': {'tiny.c': {'bytes': len(p.C_SOURCE), 'sha256': p.digest(p.C_SOURCE)},
                       'tiny.py': {'bytes': len(p.SCRIPT), 'sha256': p.digest(p.SCRIPT)},
                       'tiny.so': {'bytes': 15000, 'sha256': '1' * 64}}}


class FakeDocker:
    def __init__(self, case):
        self.case, self.calls, self.objects = case, [], {}
        self.cid = 'a' * 64
        self.fail_create = self.fail_remove = self.always_running = False
        self.wrong_image = self.gpu_injected = False
        self.proof = proof()

    def command(self, args, timeout=5):
        self.calls.append(args)
        self.case.clock.now += 0.1
        action = args[0]
        if action == 'create':
            if self.fail_create:
                raise p.Refusal('docker_command_timeout')
            labels = dict(value.split('=', 1) for i, value in enumerate(args) if i and args[i-1] == '--label')
            self.objects[self.cid] = {
                'Id': self.cid, 'Image': 'wrong' if self.wrong_image else p.IMAGE,
                'Name': '/' + args[args.index('--name')+1], 'Labels': labels,
                'User': '1000:1000', 'Entrypoint': ['/usr/bin/python3'], 'Mounts': [],
                'State': {'Running': False, 'ExitCode': 0},
                'HostConfig': {'Tmpfs': {'/tmp': p.TMPFS}, 'Runtime': 'runc',
                               'DeviceRequests': [{'Count': -1}] if self.gpu_injected else None,
                               'Devices': [], 'Binds': None, 'Mounts': [], 'Privileged': False,
                               'ReadonlyRootfs': True, 'NetworkMode': 'none', 'PortBindings': {},
                               'CapAdd': [], 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'],
                               'Memory': 96 * 1024 ** 3, 'NanoCpus': 12000000000,
                               'ShmSize': 2 * 1024 ** 3, 'PidsLimit': 64}}
            return 0, self.cid.encode(), b''
        if action == 'inspect':
            value = self.objects.get(args[-1])
            return (0, p.encode(value), b'') if value else (1, b'', b'absent')
        if action == 'ps':
            return 0, '\n'.join(self.objects).encode(), b''
        if action == 'logs':
            return 0, b'2026-10-31T11:30:00.000000000Z ' + p.encode(self.proof) + b'\n', b''
        self.case.assertRegex(args[-1], r'^[0-9a-f]{64}$')
        if action == 'start':
            self.objects[args[-1]]['State']['Running'] = self.always_running
        elif action in ('stop', 'kill'):
            self.objects[args[-1]]['State']['Running'] = False
        elif action == 'rm':
            if self.fail_remove:
                return 1, b'', b'removal failed'
            del self.objects[args[-1]]
        else:
            raise AssertionError(action)
        return 0, b'', b''


class Pure(unittest.TestCase):
    def test_probe_literal_sources_without_executing(self):
        tree = ast.parse(p.PROBE)
        values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id in ('c', 'script')}
        self.assertEqual(values, {'c': p.C_SOURCE, 'script': p.SCRIPT})
        self.assertIn("ctypes.CDLL(str(base/'tiny.so'))", p.PROBE)
        self.assertIn("subprocess.run([str(base/'tiny.py')]", p.PROBE)
        compile(p.PROBE, '<fixed-probe>', 'exec')

    def test_noexec_and_writable_root_are_refused(self):
        self.assertEqual(p.validate_proof(p.encode(proof()))['library_result'], 47)
        for old, new in [('rw,nosuid,nodev', 'rw,nosuid,nodev,noexec'), ('/ ro,relatime', '/ rw,relatime'),
                         ('/tmp rw,nosuid,nodev', '/tmp rw,nodev')]:
            value = proof()
            value['mountinfo'] = value['mountinfo'].replace(old, new)
            with self.assertRaises(p.Refusal):
                p.validate_proof(p.encode(value))

    def test_script_and_library_results_and_uid_are_checked(self):
        for key, value in [('library_result', 0), ('script_returncode', 0), ('uid', 0),
                           ('nvidia_devices', ['/dev/nvidia0']), ('error', 'compile_failed')]:
            data = proof()
            data[key] = value
            with self.assertRaises(p.Refusal):
                p.validate_proof(p.encode(data))

    def test_native_source_hash_is_bound(self):
        data = proof()
        data['hashes']['tiny.c']['sha256'] = '0' * 64
        with self.assertRaises(p.Refusal):
            p.validate_proof(p.encode(data))

    def test_fixed_args_have_no_gpu_network_or_host_mounts(self):
        intent = {'token': 'b' * 32, 'preflight_sha256': 'c' * 64,
                  'container_name': 'fixed', 'deadline_unix': 1000, 'deadline_monotonic': 1000}
        args = p.create_argv(intent)
        for required in ('--runtime=runc', '--pull=never', '--read-only', 'NVIDIA_VISIBLE_DEVICES=void',
                         'CUDA_VISIBLE_DEVICES=-1', '/tmp:rw,exec,nosuid,nodev,size=4g,mode=1777'):
            self.assertIn(required, args)
        for forbidden in ('--gpus', '--privileged', '--mount', '--volume', '--publish'):
            self.assertNotIn(forbidden, args)
        self.assertEqual(args[args.index('--network')+1], 'none')
        self.assertIn(str(intent['deadline_unix'] - p.CLEANUP_RESERVE), args[-1])
        compile(args[-1], '<fixed-wrapper>', 'exec')


@unittest.skipUnless(os.name == 'posix', 'bounded real Linux file/lock operations')
class Lifecycle(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='preflight047b-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        os.chmod(self.root, 0o700)
        self.source = Path(p.__file__).read_bytes()
        self.clock = SimpleNamespace(now=p.START_BY - 1000)
        clock = SimpleNamespace(time=lambda: self.clock.now, monotonic=lambda: self.clock.now,
                                sleep=lambda value: setattr(self.clock, 'now', self.clock.now+value))
        self.fake = FakeDocker(self)
        self.approval = {'schema': 'sentilab-047b-preflight-review/1', 'grant_source': p.GRANT,
                         'preflight_sha256': p.digest(self.source), 'decision': '+1',
                         'reviewer': 'independent-fixture-reviewer', 'review_record': 'fixture-only'}
        (self.root / 'APPROVED.json').write_bytes(p.encode(self.approval))
        for swap in (patch.object(p, 'ROOT', self.root), patch.object(p, 'time', clock),
                     patch.object(p, 'command', side_effect=self.fake.command),
                     patch.object(p.subprocess, 'Popen', side_effect=AssertionError('real process forbidden'))):
            swap.start()
            self.addCleanup(swap.stop)

    def test_success_has_bound_proof_and_exact_id_cleanup(self):
        result = p.run(self.source)
        self.assertTrue(result['preflight_ok'])
        self.assertTrue(result['cleanup_verified'])
        self.assertFalse(self.fake.objects)
        self.assertFalse(result['gpu_requested'])
        self.assertFalse(result['retry_allowed'])
        for name, expected in result['hashes'].items():
            self.assertEqual(p.digest((self.root / name).read_bytes()), expected)
        self.assertTrue((self.root / 'inspection-created.json').exists())
        self.assertTrue((self.root / 'probe.stdout.json').exists())
        self.assertLess(result['charged_seconds'], 120)

    def test_second_run_cannot_create_again(self):
        p.run(self.source)
        calls = len(self.fake.calls)
        with self.assertRaisesRegex(p.Refusal, 'preflight_attempt_consumed'):
            p.run(self.source)
        self.assertEqual(len(self.fake.calls), calls)

    def test_wrong_source_approval_refuses_before_intent(self):
        self.approval['preflight_sha256'] = '0' * 64
        (self.root / 'APPROVED.json').write_bytes(p.encode(self.approval))
        with self.assertRaisesRegex(p.Refusal, 'exact_preflight_review_required'):
            p.run(self.source)
        self.assertFalse((self.root / 'intent.json').exists())
        self.assertFalse(self.fake.calls)

    def test_stop_or_late_admission_refuses_without_intent(self):
        (self.root / 'STOP').touch()
        with self.assertRaises(p.Refusal):
            p.run(self.source)
        self.assertFalse((self.root / 'intent.json').exists())
        (self.root / 'STOP').unlink()
        self.clock.now = p.START_BY - 35
        with self.assertRaises(p.Refusal):
            p.run(self.source)
        self.assertFalse(self.fake.calls)

    def test_ambiguous_create_does_not_claim_absence(self):
        self.fake.fail_create = True
        result = p.run(self.source)
        self.assertFalse(result['preflight_ok'])
        self.assertFalse(result['cleanup_verified'])
        self.assertEqual(result['cleanup_error'], 'ambiguous_create_unresolved')
        self.assertGreaterEqual(result['charged_seconds'], 120)
        self.assertTrue((self.root / 'intent.json').exists())

    def test_wrong_identity_is_never_mutated(self):
        self.fake.wrong_image = True
        result = p.run(self.source)
        self.assertFalse(result['cleanup_verified'])
        self.assertFalse(any(args[0] in ('start', 'stop', 'kill', 'rm') for args in self.fake.calls))

    def test_gpu_injection_refuses_before_start_and_cleans_owned_id(self):
        self.fake.gpu_injected = True
        result = p.run(self.source)
        self.assertFalse(result['preflight_ok'])
        self.assertTrue(result['cleanup_verified'])
        self.assertFalse(any(args[0] == 'start' for args in self.fake.calls))
        self.assertFalse(self.fake.objects)

    def test_noexec_failure_keeps_proof(self):
        self.fake.proof['mountinfo'] = self.fake.proof['mountinfo'].replace('rw,nosuid,nodev', 'rw,nosuid,nodev,noexec')
        result = p.run(self.source)
        self.assertFalse(result['preflight_ok'])
        self.assertEqual(result['error'], 'effective_mount_policy_failed')
        self.assertTrue(result['cleanup_verified'])
        self.assertTrue((self.root / 'probe.stdout.json').exists())

    def test_unconfirmed_removal_keeps_full_charge(self):
        self.fake.fail_remove = True
        result = p.run(self.source)
        self.assertFalse(result['preflight_ok'])
        self.assertTrue(result['probe_verified'])
        self.assertFalse(result['cleanup_verified'])
        self.assertGreaterEqual(result['charged_seconds'], 120)

    def test_deadline_enters_cleanup_without_retry(self):
        self.fake.always_running = True
        result = p.run(self.source)
        self.assertFalse(result['preflight_ok'])
        self.assertEqual(result['error'], 'preflight_cleanup_reserve')
        self.assertTrue(result['cleanup_verified'])
        self.assertEqual(sum(args[0] == 'create' for args in self.fake.calls), 1)
        self.assertLess(result['charged_seconds'], 120)


if __name__ == '__main__':
    unittest.main(verbosity=2)
