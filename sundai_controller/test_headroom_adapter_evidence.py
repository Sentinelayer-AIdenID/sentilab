"""Adapter evidence tests launch a small protocol fake, never a thermal solver."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from sundai_hotspot import tap_oracle as tap


class AdapterEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='slab050-adapter-evidence-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.retained = self.root / 'raw'
        self.script = self.root / 'fake_worker.py'
        self.expected_environment = {
            'PATH': os.defpath, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'OPENBLAS_CORETYPE': 'Haswell', 'OPENBLAS_NUM_THREADS': '1',
            'OMP_NUM_THREADS': '1', 'PYTHONUNBUFFERED': '1'}
        # Only explicitly named harmless settings are inspected. The fake never
        # writes the ambient environment, including on the unfixed base.
        self.script.write_text(
            'import json, os, sys\n'
            f'allowed_names = {list(self.expected_environment)!r}\n'
            'for line in sys.stdin.buffer:\n'
            ' request = json.loads(line)\n'
            " mode = request.get('mode', 'ok')\n"
            " if mode in ('stderr', 'malformed'):\n"
            "  sys.stderr.buffer.write(b'begin\\xff' + b'long worker diagnostic\\n' * 1000 + b'end\\xfe')\n"
            '  sys.stderr.buffer.flush()\n'
            " if mode == 'malformed':\n"
            "  sys.stdout.buffer.write(b'\\xffmalformed response\\r\\n')\n"
            '  sys.stdout.buffer.flush()\n'
            '  continue\n'
            " result = {'request': request, 'environment': {name: os.environ.get(name) for name in allowed_names},\n"
            "           'unrelated_setting': os.environ.get('SLAB050_UNRELATED_SETTING')}\n"
            " response = (' \\t' + json.dumps({'ok': True, 'result': result}, sort_keys=True) + ' \\r\\n').encode()\n"
            ' sys.stdout.buffer.write(response)\n'
            ' sys.stdout.buffer.flush()\n',
            encoding='utf-8')

    @asynccontextmanager
    async def worker(self):
        with patch.object(tap, 'WORKER', self.script):
            instance = await tap._WarmWorker.start()
            try:
                yield instance
            finally:
                await instance.close()

    def request(self, mode='ok'):
        return {'mode': mode, 'retained_output_root': str(self.retained),
                'candidate_label': 'synthetic protocol fixture'}

    async def test_complete_worker_stderr_survives_close_beyond_diagnostic_tail(self):
        async with self.worker() as instance:
            workspace = Path(instance.workspace.name)
            await instance.evaluate(self.request('stderr'), worker_timeout_s=3.0)
        expected = b'begin\xff' + b'long worker diagnostic\n' * 1000 + b'end\xfe'
        self.assertGreater(len(expected), 8192)
        self.assertEqual((self.retained / 'worker-stderr.bin').read_bytes(), expected)
        self.assertFalse(workspace.exists())

    async def test_worker_stderr_is_retained_before_close_for_external_kill(self):
        expected = b'begin\xff' + b'long worker diagnostic\n' * 1000 + b'end\xfe'
        async with self.worker() as instance:
            await instance.evaluate(self.request('stderr'), worker_timeout_s=3.0)
            path = self.retained / 'worker-stderr.bin'
            for _ in range(50):
                if path.exists() and path.stat().st_size == len(expected):
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(path.exists(), 'stderr must be retained before supervisor SIGKILL bypasses close')
            self.assertEqual(path.read_bytes(), expected)

    async def test_launch_metadata_matches_received_request_and_raw_response_bytes(self):
        request = self.request()
        async with self.worker() as instance:
            result = await instance.evaluate(request, worker_timeout_s=3.0)
        metadata = json.loads((self.retained / 'WORKER.json').read_text())
        self.assertEqual(metadata['command'], [sys.executable, str(self.script)])
        self.assertEqual(metadata['cwd'], str(tap.TAP_ROOT))
        self.assertEqual(metadata['environment'], self.expected_environment)
        self.assertEqual(metadata['request'], result['request'])
        self.assertEqual(result['request'], {**request, 'workspace_root': instance.workspace.name})
        expected_request = json.dumps({**request, 'workspace_root': instance.workspace.name},
                                      separators=(',', ':'), allow_nan=False).encode() + b'\n'
        self.assertEqual((self.retained / 'worker-request.bin').read_bytes(), expected_request)
        expected_response = (' \t' + json.dumps({'ok': True, 'result': result}, sort_keys=True) + ' \r\n').encode()
        self.assertEqual((self.retained / 'worker-response.bin').read_bytes(), expected_response)

    async def test_child_receives_only_explicit_settings_without_parent_setting(self):
        with patch.dict(os.environ, {'SLAB050_UNRELATED_SETTING': 'excluded-parent-setting'}):
            async with self.worker() as instance:
                result = await instance.evaluate(self.request(), worker_timeout_s=3.0)
        self.assertIsNone(result['unrelated_setting'])
        self.assertEqual(result['environment'], self.expected_environment)
        self.assertNotIn('SLAB050_UNRELATED_SETTING', (self.retained / 'WORKER.json').read_text())

    async def test_malformed_response_preserves_original_bytes_and_stderr(self):
        async with self.worker() as instance:
            with self.assertRaisesRegex(tap.HotSpotOracleError, 'invalid JSON'):
                await instance.evaluate(self.request('malformed'), worker_timeout_s=3.0)
        self.assertEqual((self.retained / 'worker-response.bin').read_bytes(), b'\xffmalformed response\r\n')
        self.assertEqual((self.retained / 'worker-stderr.bin').read_bytes(),
                         b'begin\xff' + b'long worker diagnostic\n' * 1000 + b'end\xfe')

    async def test_partial_stdout_survives_timeout_cancel_and_forced_stop(self):
        prefix = b'partial worker response, no LF!'
        self.assertEqual(len(prefix), 31)
        for stop in ('timeout', 'cancel', 'forced_stop'):
            with self.subTest(stop=stop):
                self.retained = self.root / stop
                witness = self.root / (stop + '-emitted')
                self.script.write_text(
                    'import pathlib, sys, time\n'
                    'sys.stdin.buffer.readline()\n'
                    f'sys.stdout.buffer.write({prefix!r})\n'
                    'sys.stdout.buffer.flush()\n'
                    f'pathlib.Path({str(witness)!r}).touch()\n'
                    'time.sleep(10)\n')
                async with self.worker() as instance:
                    workspace = Path(instance.workspace.name)
                    task = asyncio.create_task(instance.evaluate(self.request(), worker_timeout_s=0.3))
                    if stop != 'timeout':
                        for _ in range(100):
                            if witness.exists():
                                break
                            await asyncio.sleep(0.001)
                        self.assertTrue(witness.exists())
                        if stop == 'cancel':
                            task.cancel()
                        else:
                            await tap._terminate_process_group(instance.process, immediate=True)
                    with self.assertRaises((tap.HotSpotOracleError, asyncio.CancelledError)):
                        await task
                self.assertTrue(witness.exists())
                self.assertEqual((self.retained / 'worker-response.bin').read_bytes(), prefix)
                status = json.loads((self.retained / 'WORKER-RESPONSE.json').read_bytes())
                self.assertEqual(status['retained_bytes'], 31)
                self.assertEqual(status['status'], 'partial')
                self.assertFalse(status['has_terminator'])
                self.assertFalse(status['truncated'])
                self.assertTrue(status['eof'])
                self.assertFalse(workspace.exists())
                self.assertIsNotNone(instance.process.returncode)

    async def test_oversized_frame_retention_is_separate_from_parser_limit(self):
        data = b'x' * 65536 + b'\n'
        witness = self.root / 'oversized-emitted'
        self.script.write_text(
            'import pathlib, sys, time\n'
            'sys.stdin.buffer.readline()\n'
            f'sys.stdout.buffer.write({data!r})\n'
            'sys.stdout.buffer.flush()\n'
            f'pathlib.Path({str(witness)!r}).touch()\n'
            'time.sleep(10)\n')
        with patch.object(tap, 'MAX_WORKER_RESPONSE_BYTES', 1024):
            async with self.worker() as instance:
                with self.assertRaises(tap.HotSpotOracleError):
                    await instance.evaluate(self.request(), worker_timeout_s=3)
                for _ in range(100):
                    if witness.exists():
                        break
                    await asyncio.sleep(0.001)
                self.assertTrue(witness.exists())
        self.assertEqual((self.retained / 'worker-response.bin').read_bytes(), data)
        status = json.loads((self.retained / 'WORKER-RESPONSE.json').read_bytes())
        self.assertEqual(status['parser_error'], 'frame_limit_exceeded')
        self.assertEqual(status['retained_bytes'], len(data))
        self.assertFalse(status['truncated'])


if __name__ == '__main__':
    unittest.main()
