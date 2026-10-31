"""Portable CLI intake, with Windows descriptor semantics simulated on Linux."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sentilab_core import resultcheck


ROOT = Path(__file__).resolve().parents[1]
ERROR = {"error": {"code": "file_unreadable"}}

CRLF_STDIO = r'''
import sys
sys.stdout.reconfigure(newline='\r\n')
sys.stderr.reconfigure(newline='\r\n')
'''

# Immediate process exit also proves that the CLI flushes its own output.
CLI_HOOK = r'''
import os
from sentilab_cli.__main__ import main
try:
    main()
except SystemExit as error:
    os._exit(error.code)
'''

# Replace only the core's OS dependency. The real CLI, descriptor operations,
# parser and receipt serializer run in a child, so exit 1 cannot hide a crash.
OS_HOOK = r'''
import json
import os
from pathlib import Path
from types import SimpleNamespace
from sentilab_core import resultcheck
from sentilab_cli.__main__ import main

windows = os.environ['RC_PLATFORM'] == 'windows'
fault = os.environ.get('RC_FAULT', '')
events, delivered = [], []
binary = False
api = dict(vars(os))
if windows:
    api.pop('O_NONBLOCK', None)
    api.pop('O_NOFOLLOW', None)
    api['O_BINARY'] = getattr(os, 'O_BINARY', 0x8000)

def fail(stage):
    if fault == stage:
        raise OSError('injected intake failure')
    if fault == stage + '_unexpected':
        raise AttributeError('injected unavailable OS operation')

def opened(file, flags):
    global binary
    events.append(['open', flags])
    fail('open')
    if fault == 'nonregular':
        reader, writer = os.pipe()
        os.close(writer)
        return reader
    binary = windows and bool(flags & api['O_BINARY'])
    # Only strip the synthetic flag on hosts whose os.open cannot accept it.
    # Native Windows needs the real O_BINARY or the CRT translates CRLF first.
    if windows and not hasattr(os, 'O_BINARY'):
        flags &= ~api['O_BINARY']
    return os.open(file, flags)

def fstat(fd):
    events.append(['fstat'])
    fail('fstat')
    return os.fstat(fd)

def read(fd, count):
    events.append(['read', count])
    fail('read')
    data = os.read(fd, count)
    if windows and not binary:
        data = data.replace(b'\r\n', b'\n')
    delivered.append(len(data))
    return data

def close(fd):
    events.append(['close'])
    os.close(fd)
    fail('close')

api.update(open=opened, fstat=fstat, read=read, close=close)
resultcheck.os = SimpleNamespace(**api)
try:
    main()
finally:
    Path(os.environ['RC_PROBE']).write_text(json.dumps({
        'events': events, 'delivered_bytes': sum(delivered), 'binary': binary}))
'''


class PlatformIntakeTests(unittest.TestCase):
    def invoke(self, file, platform, fault=''):
        probe = file.parent / 'probe.json'
        process = subprocess.run(
            [sys.executable, '-c', CRLF_STDIO + OS_HOOK, 'resultcheck', str(file)],
            cwd=ROOT, capture_output=True, timeout=5,
            env={**os.environ, 'RC_PLATFORM': platform, 'RC_FAULT': fault,
                 'RC_PROBE': str(probe)})
        return process, json.loads(probe.read_text())

    def assert_error(self, process):
        self.assertEqual(process.returncode, 2, process.stderr.decode())
        self.assertEqual(process.stdout, (resultcheck.canonical(ERROR) + '\n').encode())
        self.assertEqual(process.stderr, b'')

    def test_windows_crlf_is_binary_and_matches_native_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.json'
            for raw in (b'[]\r\n', b'not JSON\r\n'):
                with self.subTest(raw=raw):
                    file.write_bytes(raw)
                    native = subprocess.run(
                        [sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(file)],
                        cwd=ROOT, capture_output=True, timeout=5)
                    windows, probe = self.invoke(file, 'windows')
                    expected = (resultcheck.canonical(resultcheck.check_raw(raw)) + '\n').encode()
                    self.assertEqual(windows.returncode, 2, windows.stderr.decode())
                    self.assertEqual(windows.stderr, b'')
                    self.assertEqual(windows.stdout, expected)
                    self.assertEqual((native.returncode, native.stdout, native.stderr),
                                     (2, windows.stdout, b''))
                    self.assertTrue(probe['binary'])
                    self.assertEqual(probe['delivered_bytes'], len(raw))

    def test_nonregular_descriptor_returns_exit_two_without_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.json'
            file.write_bytes(b'[]\r\n')
            for platform in ('native', 'windows'):
                with self.subTest(platform=platform):
                    process, probe = self.invoke(file, platform, 'nonregular')
                    self.assert_error(process)
                    self.assertEqual([event[0] for event in probe['events']],
                                     ['open', 'fstat', 'close'])
                    self.assertEqual(probe['delivered_bytes'], 0)

    def test_intake_exceptions_always_return_structured_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.json'
            file.write_bytes(b'[]\r\n')
            for platform in ('native', 'windows'):
                for stage in ('open', 'fstat', 'read', 'close'):
                    for suffix in ('', '_unexpected'):
                        with self.subTest(platform=platform, fault=stage + suffix):
                            process, probe = self.invoke(file, platform, stage + suffix)
                            self.assert_error(process)
                            self.assertIn(stage, [event[0] for event in probe['events']])
                            if stage != 'open':
                                self.assertEqual(probe['events'][-1], ['close'])

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW'), 'OS has no O_NOFOLLOW')
    def test_native_open_rejects_final_symlink_without_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.json'
            file.write_bytes(b'[]\r\n')
            link = file.with_name('link.json')
            link.symlink_to(file)
            process, probe = self.invoke(link, 'native')
            self.assert_error(process)
            self.assertEqual([event[0] for event in probe['events']], ['open'])
            self.assertEqual(probe['delivered_bytes'], 0)


class OutputBytesTests(unittest.TestCase):
    def invoke(self, arguments, crlf):
        return subprocess.run(
            [sys.executable, '-c', (CRLF_STDIO if crlf else '') + CLI_HOOK,
             'resultcheck', *arguments],
            cwd=ROOT, capture_output=True, timeout=5)

    def assert_lf(self, data):
        self.assertTrue(data.endswith(b'\n'), data)
        self.assertFalse(data.endswith(b'\n\n'), data)
        self.assertNotIn(b'\r', data)

    def test_receipts_are_exact_utf8_bytes_with_one_lf(self):
        vectors = json.loads((ROOT / 'contracts/contract-0.2/vectors-resultcheck.json').read_text())['vectors']
        cases = [(b'[]\r\n', 2), (b'not JSON\r\n', 2)]
        for vector, code in zip(vectors[:2], (1, 0)):
            request = dict(schema_version='resultcheck.request.v2', request_id='vector', **vector['request'])
            cases.append((json.dumps(request).encode('utf-8'), code))
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.json'
            for raw, code in cases:
                file.write_bytes(raw)
                expected = (resultcheck.canonical(resultcheck.check_raw(raw)) + '\n').encode('utf-8')
                for crlf in (False, True):
                    with self.subTest(raw=raw, crlf=crlf):
                        process = self.invoke([str(file)], crlf)
                        self.assertEqual(process.returncode, code, process.stderr)
                        self.assertEqual(process.stderr, b'')
                        self.assertEqual(process.stdout, expected)
                        self.assert_lf(process.stdout)

    def test_unreadable_error_is_exact_utf8_bytes_with_one_lf(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'missing.json'
            for crlf in (False, True):
                with self.subTest(crlf=crlf):
                    process = self.invoke([str(file)], crlf)
                    self.assertEqual(process.returncode, 2, process.stderr)
                    self.assertEqual(process.stderr, b'')
                    self.assertEqual(process.stdout, b'{"error":{"code":"file_unreadable"}}\n')
                    self.assert_lf(process.stdout)

    def test_usage_errors_are_utf8_with_lf_on_stderr(self):
        for arguments in ([], ['--root'], ['--unknown-é', 'input.json']):
            baseline = None
            for crlf in (False, True):
                with self.subTest(arguments=arguments, crlf=crlf):
                    process = self.invoke(arguments, crlf)
                    self.assertEqual(process.returncode, 2)
                    self.assertEqual(process.stdout, b'')
                    self.assertTrue(process.stderr.startswith(b'usage: sentilab resultcheck '))
                    self.assertIn(b'sentilab resultcheck: error:', process.stderr)
                    self.assert_lf(process.stderr)
                    if arguments and arguments[0].startswith('--unknown'):
                        self.assertIn('--unknown-é'.encode('utf-8'), process.stderr)
                    if baseline is None:
                        baseline = process.stderr
                    self.assertEqual(process.stderr, baseline)

    def test_help_is_utf8_with_lf_on_stdout(self):
        baseline = None
        for crlf in (False, True):
            with self.subTest(crlf=crlf):
                process = self.invoke(['--help'], crlf)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(process.stderr, b'')
                self.assertTrue(process.stdout.startswith(b'usage: sentilab resultcheck '))
                self.assert_lf(process.stdout)
                if baseline is None:
                    baseline = process.stdout
                self.assertEqual(process.stdout, baseline)


if __name__ == '__main__':
    unittest.main()
