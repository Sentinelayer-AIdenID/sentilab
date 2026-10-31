"""Real subprocesses and the shipped C entry guard, using a non-thermal C main."""
import ast
import os
import shutil
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ci_allocation import Ledger
from scripts.ci_hotspot_gate import serve
from scripts.tests.test_ci_allocation import IDENTITY
from sundai_hotspot import ci_gate

ROOT = Path(__file__).resolve().parents[2]


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        source = cls.root / 'fake.c'
        source.write_text('''#include "ci_entry.h"
#include <signal.h>
#include <string.h>
int main(int argc, char **argv) {
  ci_hotspot_entry();
  if (argc > 1 && strcmp(argv[1], "timeout") == 0) sleep(10);
  if (argc > 1 && strcmp(argv[1], "kill") == 0) raise(SIGKILL);
  if (argc > 1 && strcmp(argv[1], "fail") == 0) return 7;
  puts("fake entry"); return 0;
}
''')
        cls.binary = cls.root / 'fake-hotspot'
        subprocess.run(['gcc', '-Wall', '-Wextra', '-Werror', '-DCI_ALLOCATION=1',
                        '-I', str(ROOT / 'sundai_hotspot'), str(source), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.ledger = Ledger(Path(self.directory.name) / 'events.jsonl', IDENTITY)

    def launch(self, *args, **kwargs):
        return ci_gate.run_reserved([str(self.binary), *args], reserve=self.ledger.reserve,
                                    settle=self.ledger.settle, started=self.ledger.started, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, **kwargs)

    def test_actual_entry_success_failure_kill_timeout_and_retry(self):
        self.assertEqual(self.launch().returncode, 0)
        self.assertEqual(self.launch('fail').returncode, 7)
        self.assertEqual(self.launch('kill').returncode, -signal.SIGKILL)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.launch('timeout', timeout=.05)
        self.assertEqual(self.launch().stdout.strip(), b'fake entry')
        settled = [row['state'] for row in self.ledger.events() if row['event'] == 'settled']
        self.assertEqual(settled, ['success', 'failure', 'killed', 'timeout', 'success'])
        self.assertEqual(self.ledger.summary()['launches_reserved'], 5)
        self.assertEqual(self.ledger.summary()['executions_started'], 5)

    def test_direct_copied_binary_and_environment_flag_cannot_enter(self):
        copy = Path(self.directory.name) / 'renamed'
        shutil.copy2(self.binary, copy)
        for binary in (self.binary, copy):
            for value in ('', '1', '9999999999999999999999999'):
                env = dict(os.environ, CI_HOTSPOT_ENTRY_FD=value)
                result = subprocess.run([str(binary)], capture_output=True, env=env, check=False)
                self.assertEqual(result.returncode, 125)
                self.assertNotIn(b'fake entry', result.stdout)

    def test_broker_refusal_prevents_process_and_launch_error_consumes_slot(self):
        for _ in range(100):
            self.ledger.reserve('fake')
        with self.assertRaisesRegex(RuntimeError, 'launch cap'):
            self.launch()
        self.assertEqual(self.ledger.summary()['launches_settled'], 0)
        other = Ledger(Path(self.directory.name) / 'other.jsonl', IDENTITY)
        bad = Path(self.directory.name) / 'not-executable'
        bad.write_text('fake')
        with self.assertRaises(PermissionError):
            ci_gate.run_reserved([str(bad)], reserve=other.reserve, settle=other.settle, started=other.started)
        self.assertEqual(other.events()[-1]['state'], 'launch_error')

    def test_real_http_broker_routes_ci_wrapper_and_refuses_after_close(self):
        server = serve(self.ledger, port=0, now=lambda: 1793448000)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with patch.object(ci_gate, 'BROKER_PORT', server.server_port), patch.dict(os.environ, CI_ALLOCATION='1'):
            result = ci_gate.run_hotspot([str(self.binary)], capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'fake entry')
            self.assertEqual(self.ledger.summary()['launches_settled'], 1)
            self.ledger.finish('success', {'cpu_seconds': 0})
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                ci_gate.run_hotspot([str(self.binary)])

    def test_shipped_hotspot_call_sites_use_the_gate(self):
        worker = (ROOT / 'sundai_hotspot/tap_oracle_worker.py').read_text()
        tree = ast.parse(worker)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertTrue(any(isinstance(node.func, ast.Name) and node.func.id == 'run_hotspot' for node in calls))
        self.assertFalse(any(isinstance(node.func, ast.Attribute)
                             and isinstance(node.func.value, ast.Name)
                             and node.func.value.id == 'subprocess'
                             and node.func.attr in ('run', 'Popen', 'call') for node in calls))
        tap = ast.parse((ROOT / 'sundai_tap/passive_interposer.py').read_text())
        method = next(node for node in ast.walk(tap) if isinstance(node, ast.FunctionDef)
                      and node.name == 'run_hotspot')
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr == 'Popen'
                             for node in ast.walk(method)))
        self.assertIn('ci_hotspot_entry();', (ROOT / 'sundai_hotspot/hotspot.c').read_text())

    def test_ignored_direct_call_still_poisoned_the_job_ledger(self):
        # The compiled entry reports a bypass attempt independently of its caller.
        server = serve(self.ledger, now=lambda: 1793448000)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        result = subprocess.run([str(self.binary)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 125)
        import time
        deadline = time.monotonic() + 2
        while not self.ledger.summary()['direct_call_violations'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.ledger.summary()['direct_call_violations'], 1)
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            self.launch()
