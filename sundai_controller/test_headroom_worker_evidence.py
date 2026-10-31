"""Raw worker evidence and phase accounting; every native invocation is mocked."""
import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sundai_hotspot import tap_oracle_worker as worker


class WorkerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.retained = self.root / 'raw'
        self.retained.mkdir()
        self.binary = self.root / 'fake-hotspot'
        self.binary.write_bytes(b'nonexecutable fake native binary')
        source = Path(worker.__file__).resolve()
        self.request = {
            'workspace_root': str(self.root), 'retained_output_root': str(self.retained),
            'hotspot_binary': str(self.binary), 'expected_binary_sha256': worker._sha256(self.binary),
            'expected_source_sha256': {str(source.relative_to(worker.REPO_ROOT)): worker._sha256(source)},
            'candidate_hash': 'a' * 64, 'problem_hash': 'b' * 64,
            'image_identity': {'image_digest': 'sha256:' + 'c' * 64},
            'grid_rows': 1, 'grid_cols': 1, 'solver_timeout_s': 1.0,
            'centers_mm': [[10.0, 10.0]],
            'tap_parameters': {
                'interposer_size_mm': 50.0, 'widths_mm': [8.0], 'heights_mm': [9.0],
                'powers_w': [150.0], 'connections': [[0.0]], 'link_type': 'nppl',
                'granularity_mm': 0.25, 'bump_halos_mm': [0.0], 'ambient_c': 45.0},
        }
        self.system = MagicMock()
        self.system.hubump = [0.0]
        self.system.set_path.side_effect = lambda value: setattr(self, 'output', Path(value))
        self.system.gen_flp.side_effect = self.generate
        self.cpu = self.wall = 0.0

    def generate(self, name):
        self.cpu += 2.0
        self.wall += 3.0
        for filename in ('new_hotspot.config', 'sampleL4_ChipLayer.flp', 'sample.ptrace'):
            (self.output / filename).write_bytes(b'original native input\n')
        (self.output / 'samplelayers.lcf').write_text('sampleL4_ChipLayer.flp\n')

    def solve(self, command, **kwargs):
        self.cpu += 4.0
        self.wall += 5.0
        self.assertEqual(kwargs['env'], {'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC'})
        archived = json.loads((self.output / 'COMMAND.json').read_text())
        self.assertEqual(archived['command'], command)
        self.assertEqual(archived['environment'], kwargs['env'])
        self.assertEqual(archived['cwd'], str(kwargs['cwd']))
        self.assertEqual(json.loads((self.output / 'PHASES.json').read_text())['status'], 'solving')
        kwargs['stdout'].write(b'native output\xff\n')
        kwargs['stderr'].write(b'native diagnostic\xfe\n')
        (self.output / 'sample.steady').write_bytes(b'original native steady bytes\n')
        (self.output / 'sample.grid.steady').write_text(''.join(
            f'Layer {layer}:\n0\t{320 + layer}.0\n' for layer in range(8)))
        return SimpleNamespace(returncode=0, stdout=None, stderr=None)

    def run_worker(self, solve=None):
        original = worker._retain_solver_output
        def archive(*args):
            self.cpu += 0.25
            self.wall += 0.5
            return original(*args)
        with ExitStack() as stack:
            stack.enter_context(patch.object(worker, 'PassiveInterposer', return_value=self.system))
            stack.enter_context(patch.object(worker.subprocess, 'run', side_effect=solve or self.solve))
            stack.enter_context(patch.object(worker, '_cpu_seconds', side_effect=lambda: self.cpu, create=True))
            stack.enter_context(patch.object(worker.time, 'perf_counter', side_effect=lambda: self.wall))
            stack.enter_context(patch.object(worker, '_worker_startup', return_value={
                'cpu_seconds': 0.75, 'wall_seconds': 1.25}, create=True))
            stack.enter_context(patch.object(worker, '_retain_solver_output', side_effect=archive))
            return worker.evaluate(self.request)

    def assert_retained_phases(self, values, status):
        record = json.loads((self.output / 'PHASES.json').read_text())
        self.assertEqual(record['status'], status)
        self.assertIsNone(record['active_phase'])
        self.assertEqual(record['phase_timings'], values)
        self.assertEqual(values['generate'], {'cpu_seconds': 2.0, 'wall_seconds': 3.0})
        self.assertEqual(values['solve'], {'cpu_seconds': 4.0, 'wall_seconds': 5.0})
        self.assertEqual(values['archive'], {'cpu_seconds': 0.25, 'wall_seconds': 0.5})
        self.assertEqual(values['worker_startup'], {'cpu_seconds': 0.75, 'wall_seconds': 1.25})

    def test_success_retains_native_bytes_command_identity_and_phase_costs(self):
        with patch.dict(worker.os.environ, {'UNRELATED_PRIVATE_SETTING': 'must not reach native process'}):
            result = self.run_worker()
        self.assert_retained_phases(result['phase_timings'], 'complete')
        self.assertEqual(result['raw_output_directory'], str(self.output))
        self.assertEqual((self.output / 'stdout.bin').read_bytes(), b'native output\xff\n')
        self.assertEqual((self.output / 'stderr.bin').read_bytes(), b'native diagnostic\xfe\n')
        identities = json.loads((self.output / 'IDENTITIES.json').read_text())
        self.assertEqual(identities['image_identity'], self.request['image_identity'])
        self.assertEqual(identities['source_sha256'], self.request['expected_source_sha256'])
        self.assertEqual(identities['binary_sha256'], self.request['expected_binary_sha256'])
        inputs = json.loads((self.output / 'INPUTS.json').read_text())
        self.assertEqual(inputs, result['input_sha256'])
        self.assertEqual(set(inputs), {'new_hotspot.config', 'sampleL4_ChipLayer.flp',
                                      'sample.ptrace', 'samplelayers.lcf'})
        artifacts = json.loads((self.output / 'ARTIFACTS.json').read_text())
        self.assertIn('sample.steady', artifacts)
        self.assertIn('sample.grid.steady', artifacts)
        for name, digest in artifacts.items():
            self.assertEqual(worker._sha256(self.output / name), digest)
        self.assertNotIn('UNRELATED_PRIVATE_SETTING', (self.output / 'COMMAND.json').read_text())

    def test_native_error_timeout_and_missing_grid_keep_charges_and_partial_bytes(self):
        for failure in ('exit', 'timeout', 'spawn', 'missing_grid'):
            with self.subTest(failure=failure):
                self.cpu = self.wall = 0.0
                def fail(command, **kwargs):
                    result = self.solve(command, **kwargs)
                    if failure == 'exit':
                        result.returncode = 7
                    elif failure == 'timeout':
                        raise worker.subprocess.TimeoutExpired(command, 1.0)
                    elif failure == 'spawn':
                        raise OSError('fake launch failure')
                    else:
                        (self.output / 'sample.grid.steady').unlink()
                    return result
                with self.assertRaises((RuntimeError, TimeoutError, OSError)) as raised:
                    self.run_worker(fail)
                self.assert_retained_phases(raised.exception.phase_timings, 'error')
                self.assertEqual((self.output / 'stdout.bin').read_bytes(), b'native output\xff\n')
                self.assertEqual((self.output / 'stderr.bin').read_bytes(), b'native diagnostic\xfe\n')
                self.assertTrue((self.output / 'ERROR.json').is_file())
                self.assertTrue((self.output / 'EXIT.json').is_file())
                self.assertTrue((self.output / 'ARTIFACTS.json').is_file())

    def test_generation_failure_preserves_request_partial_inputs_and_cost(self):
        def fail(name):
            self.generate(name)
            raise ValueError('fake generator failure')
        self.system.gen_flp.side_effect = fail
        with self.assertRaisesRegex(ValueError, 'fake generator failure') as raised:
            self.run_worker()
        self.assertEqual(json.loads((self.output / 'REQUEST.json').read_text()), self.request)
        self.assertTrue((self.output / 'sampleL4_ChipLayer.flp').exists())
        phases = json.loads((self.output / 'PHASES.json').read_text())
        self.assertEqual(phases['status'], 'error')
        self.assertEqual(phases['phase_timings'], raised.exception.phase_timings)
        self.assertEqual(phases['phase_timings']['generate']['cpu_seconds'], 2.0)
        self.assertEqual(phases['phase_timings']['solve']['cpu_seconds'], 0.0)

    def test_bad_binary_identity_is_retained_without_native_launch(self):
        self.request['expected_binary_sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'binary changed') as raised:
            self.run_worker()
        self.output = next(self.retained.iterdir())
        self.assertEqual(json.loads((self.output / 'REQUEST.json').read_text()), self.request)
        self.assertEqual(raised.exception.phase_timings['solve']['cpu_seconds'], 0.0)
        self.assertTrue((self.output / 'PHASES.json').is_file())
        self.system.gen_flp.assert_not_called()

    def test_worker_startup_is_charged_once_per_process(self):
        with patch.object(worker, '_STARTUP_ACCOUNTED', False, create=True):
            first = worker._worker_startup()
            second = worker._worker_startup()
        self.assertGreater(first['cpu_seconds'], 0.0)
        self.assertGreaterEqual(first['wall_seconds'], 0.0)
        self.assertEqual(second, {'cpu_seconds': 0.0, 'wall_seconds': 0.0})

    def test_error_protocol_exposes_phase_timings_for_parent_accounting(self):
        error = ValueError('fake worker failure')
        error.phase_timings = {'solve': {'cpu_seconds': 0.4, 'wall_seconds': 0.6}}
        error.raw_output_directory = str(self.retained)
        stdin = SimpleNamespace(buffer=io.BytesIO(b'{}\n'))
        stdout = io.StringIO()
        with patch.object(worker.sys, 'stdin', stdin), patch.object(worker.sys, 'stdout', stdout), \
                patch.object(worker, 'evaluate', side_effect=error):
            self.assertEqual(worker.main(), 1)
        response = json.loads(stdout.getvalue())
        self.assertFalse(response['ok'])
        self.assertEqual(response['phase_timings'], error.phase_timings)
        self.assertEqual(response['raw_output_directory'], str(self.retained))


if __name__ == '__main__':
    unittest.main()
