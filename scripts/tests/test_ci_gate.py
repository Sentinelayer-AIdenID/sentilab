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

    def test_finalizer_drains_delayed_compiled_entry_violation_and_cpu(self):
        self.check_finalizer_delayed_violation(release_during_close=True)

    def test_finalizer_marks_unresolved_broker_handlers_inconclusive(self):
        self.check_finalizer_delayed_violation(release_during_close=False)

    def check_finalizer_delayed_violation(self, *, release_during_close):
        import json
        import sys
        import threading
        from dataclasses import asdict

        from scripts.ci_cpu_meter import run

        directory = Path(self.directory.name)
        group = directory / 'group'
        (group / 'host').mkdir(parents=True)
        (group / 'cpu.stat').write_text('usage_usec 0\n')
        (group / 'cgroup.events').write_text('populated 0\n')
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        violation = Ledger.violation

        def delayed(ledger):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('fake handler timed out')
            (group / 'cpu.stat').write_text('usage_usec 1250000\n')
            violation(ledger)
            completed.set()

        timers = []

        def broker(ledger):
            server = serve(ledger, now=lambda: 1793448000)
            server.drain_timeout = .15 if not release_during_close else 2
            close = server.server_close

            def delayed_release():
                self.assertTrue(entered.wait(2), 'compiled entry request was never accepted')
                if release_during_close:
                    timer = threading.Timer(.1, release.set)
                    timers.append(timer)
                    timer.start()
                close()

            server.server_close = delayed_release
            return server

        admission = {'identity': asdict(IDENTITY), 'state': 'admitted', 'allocation_id': '56314',
                     'slot': 3, 'launch_reservation': 100, 'cpu_reservation_seconds': 900}
        try:
            with patch('scripts.ci_cpu_meter.create_group', return_value=group), \
                 patch('scripts.ci_cpu_meter.time.time', return_value=1793448000), \
                 patch('scripts.ci_cpu_meter.serve', side_effect=broker), patch.object(Ledger, 'violation', delayed):
                # Real compiled ci_entry.h refuses 125; caller deliberately ignores it.
                code = run(directory / 'meter', admission, [sys.executable, '-c',
                           'import subprocess,sys; p=subprocess.run([sys.argv[1]]); assert p.returncode == 125',
                           str(self.binary)])
                result = json.loads((directory / 'meter/settlement.json').read_text())
            self.assertEqual(code, 1)
            if release_during_close:
                self.assertEqual(result['state'], 'launch_violation')
                self.assertEqual(result['direct_call_violations'], 1)
                self.assertEqual(result['cpu']['cgroup_cpu_seconds'], 1.25)
                self.assertTrue(result['cpu']['broker_quiescent'])
            else:
                self.assertEqual(result['state'], 'inconclusive')
                self.assertFalse(result['cpu']['broker_quiescent'])
                self.assertGreaterEqual(result['cpu']['charged_cpu_seconds'], 900)
        finally:
            release.set()
            self.assertTrue(completed.wait(3))
            for timer in timers:
                timer.join()

    def test_broker_close_drains_requests_already_queued_on_listener(self):
        import socket

        server = serve(self.ledger, port=0)
        server.shutdown()  # enqueue after the accept loop exits, before final close
        try:
            with socket.create_connection(('127.0.0.1', server.server_port), timeout=2) as client:
                client.sendall(b'POST /violation HTTP/1.0\r\nContent-Length: 2\r\n\r\n{}')
                server.server_close()
            self.assertEqual(self.ledger.summary()['direct_call_violations'], 1)
            self.assertTrue(server.quiescent)
        finally:
            server.server_close()

    def test_fresh_process_oracle_preserves_ci_gate_without_forwarding_credentials(self):
        import asyncio
        import importlib.util
        import sys
        import types

        # Replace only the numerical base-class dependency; execute the actual
        # FreshProcessOracle transport and a real nonthermal subprocess/broker.
        dependency = types.ModuleType('sundai_hotspot.tap_oracle')
        dependency.HotSpotOracle = object
        spec = importlib.util.spec_from_file_location('ci_oracle_probe', ROOT / 'sentilab_core/oracle.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'sundai_hotspot.tap_oracle': dependency}):
            spec.loader.exec_module(module)
        oracle = module.FreshProcessOracle.__new__(module.FreshProcessOracle)
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        self.addCleanup(os.close, read_fd)
        oracle.reservation = {'ceiling_s': 5, 'lease_fd': read_fd, 'operation_id': 'fake'}
        oracle.stop_file = None
        server = serve(self.ledger, now=lambda: 1793448000)
        self.addCleanup(server.server_close)
        spawn = asyncio.create_subprocess_exec

        async def fake_worker(*args, **kwargs):
            self.assertNotIn('GH_TOKEN', kwargs['env'])
            self.assertNotIn('GITHUB_TOKEN', kwargs['env'])
            script = ('import json,sys; from sundai_hotspot.ci_gate import run_hotspot; '
                      'p=run_hotspot([sys.argv[1]],capture_output=True); '
                      'assert p.returncode == 0, p.stderr; '
                      'print(json.dumps(dict(result="fake-result", cpu_s=0.01, process_id="fake")))')
            return await spawn(sys.executable, '-c', script, str(self.binary), **kwargs)

        with patch.dict(os.environ, CI_ALLOCATION='1', GH_TOKEN='fake', GITHUB_TOKEN='fake'), \
             patch.object(asyncio, 'create_subprocess_exec', fake_worker):
            self.assertEqual(asyncio.run(oracle._evaluate({}, worker_timeout_s=5)), 'fake-result')
        self.assertEqual(self.ledger.summary()['launches_reserved'], 1)
        self.assertEqual(self.ledger.summary()['launches_settled'], 1)
        self.assertEqual(self.ledger.summary()['direct_call_violations'], 0)
