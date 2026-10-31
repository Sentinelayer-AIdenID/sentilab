"""Real stdio regressions use recorded evidence and never start a solver."""
import fcntl
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


FIXTURE = Path(__file__).resolve().parents[1] / 'docs/sentilab/evidence/SLAB-016'


class DatasetMCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'ledger'
        self.root.mkdir()
        shutil.copyfile(FIXTURE / 'fixture.jsonl', self.root / 'fixture.jsonl')
        self.output = Path(self.temp.name) / 'export'
        self.output.mkdir()
        self.lock = (self.output / '.export.lock').open('a+b')
        self.addCleanup(self.lock.close)
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.responses = {}
        self.buffer = b''

    def start(self, *, timeout=None):
        command = [sys.executable, '-m', 'sentilab_mcp']
        if timeout is not None:
            command = [sys.executable, '-c',
                       f'import sentilab_mcp; sentilab_mcp.EXPORT_TIMEOUT_SECONDS = {timeout!r}; '
                       'from sentilab_mcp.__main__ import main; main()']
        environment = {**os.environ, 'SENTILAB_LIVE_DIR': str(self.root),
                       'SENTILAB_VIEW_PUBLIC_KEYS': (FIXTURE / 'public-keys.json').read_text()}
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=environment, bufsize=0,
                                        start_new_session=True)
        self.addCleanup(self.close_process)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.addCleanup(self.selector.close)

    def close_process(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def send(self, request):
        self.process.stdin.write((json.dumps({'jsonrpc': '2.0', **request}) + '\n').encode())
        self.process.stdin.flush()

    def response(self, request_id, *, timeout=5):
        deadline = time.monotonic() + timeout
        while request_id not in self.responses:
            remaining = deadline - time.monotonic()
            self.assertGreater(remaining, 0, f'no MCP response for id {request_id!r}')
            self.assertTrue(self.selector.select(remaining), f'no MCP response for id {request_id!r}')
            chunk = os.read(self.process.stdout.fileno(), 65536)
            self.assertTrue(chunk, f'MCP exited without responding to {request_id!r}')
            self.buffer += chunk
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                response = json.loads(line)
                self.assertNotIn(response['id'], self.responses)
                self.responses[response['id']] = response
        return self.responses[request_id]

    def send_export(self):
        self.send({'id': 'export', 'method': 'tools/call', 'params': {
            'name': 'sentilab_dataset_export', 'arguments': {
                'run_ids': ['fixture'], 'output_dir': str(self.output)}}})

    def finish_without_export(self):
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.process.stdin.close()
        self.process.wait(timeout=5)
        self.assertEqual(self.process.returncode, 0, self.process.stderr.read().decode())
        with self.assertRaises(ProcessLookupError):
            os.killpg(self.process.pid, 0)
        self.assertEqual([path.name for path in self.output.iterdir()], ['.export.lock'])

    def test_locked_export_allows_stop_and_can_be_cancelled_by_request_id(self):
        self.start()
        self.send_export()
        self.send({'id': 'stop', 'method': 'tools/call', 'params': {
            'name': 'sentilab_live_stop', 'arguments': {'ai_off': True}}})
        stopped = self.response('stop')
        self.assertTrue(json.loads(stopped['result']['content'][0]['text'])['stopped'])
        self.assertTrue(json.loads((self.root / 'STOP').read_text())['stopped'])
        self.assertNotIn('export', self.responses)
        self.send({'id': 'status', 'method': 'tools/call', 'params': {
            'name': 'sentilab_live_status', 'arguments': {'ai_off': True}}})
        status = json.loads(self.response('status')['result']['content'][0]['text'])
        self.assertTrue(status['stopped'])
        self.assertEqual([run['run_id'] for run in status['runs']], ['fixture'])
        self.assertNotIn('export', self.responses)
        self.send({'method': 'notifications/cancelled', 'params': {'requestId': 'export'}})
        self.assertEqual(self.response('export')['error']['code'], -32800)
        self.send({'id': 'ping', 'method': 'ping'})
        self.assertEqual(self.response('ping')['result'], {})
        self.finish_without_export()

    def test_locked_export_times_out_and_cannot_publish_after_lock_release(self):
        self.start(timeout=0.25)
        self.send_export()
        self.assertEqual(self.response('export')['error']['message'], 'TimeoutError')
        self.send({'id': 'ping', 'method': 'ping'})
        self.assertEqual(self.response('ping')['result'], {})
        self.finish_without_export()

    def test_disconnect_reaps_blocked_export_worker_before_exit(self):
        self.start()
        self.send_export()
        self.send({'id': 'ping', 'method': 'ping'})
        self.assertEqual(self.response('ping')['result'], {})
        self.assertNotIn('export', self.responses)
        self.process.stdin.close()
        self.process.wait(timeout=5)
        self.assertEqual(self.process.returncode, 0, self.process.stderr.read().decode())
        with self.assertRaises(ProcessLookupError):
            os.killpg(self.process.pid, 0)
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.assertEqual([path.name for path in self.output.iterdir()], ['.export.lock'])


if __name__ == '__main__':
    unittest.main()
