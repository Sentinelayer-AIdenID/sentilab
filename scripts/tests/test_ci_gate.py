"""Real subprocesses and the shipped C entry guard, using a non-thermal C main."""
import ast
import os
import shlex
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


# Reviewed raw spawn inventory; new sites or changed command expressions need review.
# Native launches go through ci_gate; Python workers delegate to it.
RAW_SPAWNS = [('sentilab_core/conformance.py', 'subprocess.run', ("['node', '--input-type=module', '-e', script]",)),
 ('sentilab_core/conformance.py', 'subprocess.run', ("['node', '--input-type=module', '-e', script]",)),
 ('sentilab_core/conformance.py', 'subprocess.run', ("['node', '--input-type=module', '-e', script]",)),
 ('sentilab_core/conformance.py', 'subprocess.run', ("['node', '--input-type=module', '-e', script]",)),
 ('sentilab_core/conformance.py', 'subprocess.run', ("['node', '--input-type=module', '-e', script]",)),
 ('sentilab_core/conformance.py', 'subprocess.run', ("['node', str(adapter)]",)),
 ('sentilab_core/oracle.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', "'-m'", "'sentilab_core.worker'", 'str(ceiling)')),
 ('sentilab_core/test_cleanup.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable',
   "'-c'",
   'HOST',
   'directory',
   'str(release_read)',
   'str(notice_write)',
   "'error' if error else 'ok'")),
 ('sentilab_core/test_dataset.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', "'-m'", "'sentilab_mcp'")),
 ('sentilab_core/test_dataset.py',
  'subprocess.run',
  (("[sys.executable, '-m', 'sentilab_cli', 'dataset', 'export', '--run-id', 'fixture', '--output-dir', "
    "str(output), '--policy', str(policy_path)]"),)),
 ('sentilab_core/test_dataset_mcp.py', 'subprocess.Popen', ('command',)),
 ('sentilab_core/test_mcp_stdio.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', "'-c'", 'HOST', 'str(self.cleaned)')),
 ('sentilab_core/test_transports.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', 'live', 'verify', '--ai-off', '--run-id', 'wire-parity']",)),
 ('sentilab_core/test_transports.py', 'subprocess.run', ("[sys.executable, '-m', 'sentilab_mcp']",)),
 ('sundai_controller/mesh_study.py', 'subprocess.check_output', ("['git', 'rev-parse', 'HEAD']",)),
 ('sundai_controller/test_mesh_study.py', 'subprocess.run', ("[sys.executable, '-c', worker]",)),
 ('sundai_controller/test_trust.py',
  'subprocess.run',
  ("[sys.executable, str(ROOT / 'sundai_controller' / command[0]), *command[1:]]",)),
 ('sundai_hotspot/ci_gate.py', 'subprocess.Popen', ('command',)),
 ('sundai_hotspot/ci_gate.py', 'subprocess.run', ('command',)),
 ('sundai_hotspot/tap_oracle.py',
  'asyncio.create_subprocess_exec',
  ("'taskkill.exe'", "'/PID'", 'str(process.pid)', "'/T'", "'/F'")),
 ('sundai_hotspot/tap_oracle.py', 'asyncio.create_subprocess_exec', ('sys.executable', 'str(WORKER)')),
 ('sundai_hotspot/test_micro150.py', 'subprocess.run', ("[sys.executable, '-c', script]",)),
 ('sundai_tap/passive_interposer.py', 'os.system',
  ("'rm ' + self.path + filename + '{*.flp,*.lcf,*.ptrace,*.steady}'",))]

# Non-HotSpot sites reviewed after the main merge; see docs/ci-spawn-review.md.
# Node paging reducer against local recorded-ledger HTTP fixture; no run endpoint.
RAW_SPAWNS += [('app/check_view_paging.py',
  'subprocess.run',
  (("['node', str(Path(__file__).with_suffix('.mjs')), str(reference.resolve()), "
    "f'http://127.0.0.1:{fixture.port}', str(fixture.root)]"),))]

# Fixed SSH argv from _remote; stdin is gb10_readonly.py (file/proc inspection only).
RAW_SPAWNS += [('sentilab_core/gb10_backend.py', 'subprocess.Popen', ('argv',))]

# Node projection adapters consume recorded JSON; no oracle or child process calls.
RAW_SPAWNS += [('sentilab_core/memory_conformance.py',
  'subprocess.run',
  ("['node', '--input-type=module', '-e', script]",)),
 ('sentilab_core/memory_conformance.py',
  'subprocess.run',
  ("['node', str(Path(__file__).with_name('projection.mjs'))]",)),
 ('sentilab_core/memory_conformance.py',
  'subprocess.run',
  ("['node', str(Path(__file__).with_name('projection.mjs'))]",))]

# MCP host scripts: recorded-data/advisory calls and refused live runs, no solver.
RAW_SPAWNS += [('sentilab_core/test_mcp_stdio.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', '*command'))]

# Saved Popen alias launches this interpreter as a fake SSH peer, never ssh/HotSpot.
RAW_SPAWNS += [('sentilab_core/test_gb10_backend.py', 'subprocess.Popen',
  ("[sys.executable, '-I', '-S', '-B', '-c', behavior]",))]

# CLI/MCP memory and advisory route requests only; no live.run request.
RAW_SPAWNS += [('sentilab_core/test_memory_transports.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', *args]",)),
 ('sentilab_core/test_memory_transports.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_mcp']",))]

# Python probe parses supplied model-list JSON and writes evidence; no model or solver call.
RAW_SPAWNS += [('sentilab_core/test_probe.py',
  'subprocess.run',
  (("[sys.executable, '-m', 'sentilab_core.probe', '--provider', 'fixture-provider', "
    "'--entitlement-source', 'fixture-entitlement', '--output', str(output)]"),))]

# CLI/MCP research request/status/export uses the offline fixture backend; no solver.
RAW_SPAWNS += [('sentilab_core/test_research_transports.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', 'research', command, *flags]",)),
 ('sentilab_core/test_research_transports.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_mcp']",)),
 ('sentilab_core/test_research_transports.py', 'subprocess.run', ('command',))]

# CLI/MCP offline ResultCheck and Node reference checker; recorded input only.
RAW_SPAWNS += [('sentilab_core/test_resultcheck.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', "'-m'", "'sentilab_mcp'")),
 ('sentilab_core/test_resultcheck.py',
  'subprocess.run',
  ("[sys.executable, str(ROOT / 'sentilab_cli' / 'sentilab'), 'resultcheck', str(file)]",)),
 ('sentilab_core/test_resultcheck.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(file)]",)),
 ('sentilab_core/test_resultcheck.py',
  'subprocess.run',
  ("['node', '--input-type=module', '-e', REFERENCE]",)),
 ('sentilab_core/test_resultcheck.py',
  'subprocess.run',
  ("['node', '--input-type=module', '-e', script]",)),
 ('sentilab_core/test_resultcheck.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(file)]",))]

# CLI ResultCheck file containment refusal; no evaluation.
RAW_SPAWNS += [('sentilab_core/test_resultcheck_boundary.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(outside)]",))]

# CLI/MCP ResultCheck I/O and cancellation workers; supplied scripts only delay the host.
RAW_SPAWNS += [('sentilab_core/test_resultcheck_io.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', "*(command or ('-m', 'sentilab_mcp'))")),
 ('sentilab_core/test_resultcheck_io.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', "'-m'", "'sentilab_cli'", "'resultcheck'", 'str(file)'))]

# CLI ResultCheck plus fixed OS/stdio hooks; no evaluation.
RAW_SPAWNS += [('sentilab_core/test_resultcheck_platform.py',
  'subprocess.run',
  ("[sys.executable, '-c', CRLF_STDIO + OS_HOOK, 'resultcheck', str(file)]",)),
 ('sentilab_core/test_resultcheck_platform.py',
  'subprocess.run',
  ("[sys.executable, '-c', (CRLF_STDIO if crlf else '') + CLI_HOOK, 'resultcheck', *arguments]",)),
 ('sentilab_core/test_resultcheck_platform.py',
  'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', 'resultcheck', str(file)]",))]

# ResultCheck CLI checks files; no thermal evaluation.
RAW_SPAWNS += [('sentilab_mcp/__init__.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable',
   "'-m'",
   "'sentilab_cli'",
   "'resultcheck'",
   "'--root'",
   'root',
   "'--'",
   'file'))]


# Execs the fixed supervisor; its forked headroom worker delegates to the gated TAP oracle.
RAW_SPAWNS += [('sundai_controller/headroom.py',
  'os.execv',
  ('sys.executable',
   ("[sys.executable, '-m', 'sundai_controller.headroom_supervisor', '--prereg', str(args.prereg), "
   "'--budget', str(args.budget or args.prereg.parent / 'SPEND.json'), '--out', str(args.out or "
   "args.prereg.parent / 'micro150-v4'), '--policy', str(args.resource_policy)]")))]

# Fork inherits CI environment; work calls run_headroom -> HotSpotOracle -> gated TAP worker.
RAW_SPAWNS += [('sundai_controller/headroom_supervisor.py', 'os.fork', ())]

# Dedicated synthetic CPU/reaping and fake-oracle workers; neither invokes HotSpot.
RAW_SPAWNS += [('sundai_controller/test_headroom_supervisor.py',
  'subprocess.run',
  ("[sys.executable, '-c', program]",)),
 ('sundai_controller/test_headroom_supervisor.py',
  'subprocess.run',
  ("[sys.executable, '-c', program]",))]

# Fixed sleep, orphan cleanup and CPU/affinity probes; no solver.
RAW_SPAWNS += [('sundai_controller/test_process_budget.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable', "'-c'", "'import time; time.sleep(5)'")),
 ('sundai_controller/test_process_budget.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable',
   "'-c'",
   ("f'import os,pathlib,time,signal\\npid=os.fork()\\nif pid: os._exit(0)\\nos.setsid()\\ndef "
   'stop(sig, frame):\\n end=time.process_time()+0.04\\n while time.process_time()<end: pass\\n '
   'os._exit(0)\\nsignal.signal(signal.SIGTERM, '
   'stop)\\npathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\\nend=time.monotonic()+0.6\\nwhile '
   "time.monotonic()<end: pass\\n'"))),
 ('sundai_controller/test_process_budget.py',
  'asyncio.create_subprocess_exec',
  ('sys.executable',
   "'-c'",
   ("f'import hashlib,os,threading,time\\nassert len(os.sched_getaffinity(0)) == "
   '{expected_cpus}\\nend=time.monotonic()+0.18\\ndef busy():\\n assert '
   'len(os.sched_getaffinity(0)) == {expected_cpus}\\n while time.monotonic()<end: '
   'hashlib.sha256(b"x"*131072).digest()\\nthreads=[threading.Thread(target=busy) for _ in '
   "range({q})]\\n[t.start() for t in threads]\\n[t.join() for t in threads]\\n'")))]

# Fixed cancellation host starts a sleeping Python descendant; no solver.
RAW_SPAWNS += [('sentilab_core/test_oracle.py', 'asyncio.create_subprocess_exec',
                ('sys.executable', "'-c'", 'script', 'str(ready)'))]

# Recorded capability worker excludes live.run; chiplet Node only projects recorded JSON.
RAW_SPAWNS += [('sentilab_core/execution.py', 'subprocess.Popen',
  ("[sys.executable, '-m', 'sentilab_core.execution']",)),
 ('sentilab_core/chiplet.py', 'subprocess.run',
  ("['node', '--input-type=module', '-e', source]",))]

# Saved Popen aliases: recorded worker before dispatch, or finite fork/pipe cleanup fixture.
RAW_SPAWNS += [('sentilab_core/test_execution.py', 'subprocess.Popen', ('*args',)),
 ('sentilab_core/test_execution.py', 'subprocess.Popen', ('command', '*args'))]

# Build metadata probes query the installed package/runtime and the fixed receipt script.
RAW_SPAWNS += [('sentilab_core/test_build_info.py', 'subprocess.check_output',
  ("['dpkg-query', '-W', '-f=${Version}', 'nodejs']",)),
 ('sentilab_core/test_build_info.py', 'subprocess.check_output',
  ("['/usr/bin/node', '--version']",)),
 ('sentilab_core/test_build_info.py', 'subprocess.run',
  ("[*command, '--base-image', base, '--node-package-version', package]",)),
 ('sentilab_core/test_build_info.py', 'subprocess.run',
  ("[*command, '--base-image', image, '--node-package-version', pin]",))]

# CLI/MCP conformance: recorded data, fake SSH, refused requests, help and registry output.
# Successful live.run uses FIXTURE_HOST with BarrierOracle and a preexisting STOP file.
RAW_SPAWNS += [('sentilab_core/test_conformance.py', 'subprocess.run',
  ('self.cli_command(row, arguments)',)),
 ('sentilab_core/test_conformance.py', 'subprocess.Popen', ('command',)),
 ('sentilab_core/test_conformance.py', 'subprocess.run', ('command',)),
 ('sentilab_core/test_conformance.py', 'subprocess.run', ('command',)),
 ('sentilab_core/test_conformance.py', 'subprocess.Popen',
  ('self.cli_command(row, arguments)',)),
 ('sentilab_core/test_conformance.py', 'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', *row.cli_command, *flags, *extra]",)),
 ('sentilab_core/test_conformance.py', 'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_mcp']",)),
 ('sentilab_core/test_conformance.py', 'subprocess.run', ('command',)),
 ('sentilab_core/test_conformance.py', 'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_core.capabilities']",)),
 ('sentilab_core/test_conformance.py', 'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_mcp']",)),
 ('sentilab_core/test_conformance.py', 'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', namespace, '--help']",)),
 ('sentilab_core/test_conformance.py', 'subprocess.run',
  ("[sys.executable, '-m', 'sentilab_cli', namespace, '--help']",)),
 ('sentilab_core/test_conformance.py', 'subprocess.run', ("[*invocation, '--help']",))]

# Proposal transport fixtures inject BarrierOracle; no native solver is dispatched.
RAW_SPAWNS += [('sentilab_core/test_proposals.py', 'subprocess.run',
                ("self.command('cli', *arguments)",)),
               ('sentilab_core/test_proposals.py', 'subprocess.Popen',
                ("self.command('mcp')",)),
               ('sentilab_core/test_proposals.py', 'subprocess.Popen',
                ("self.command('cli', 'proposal', 'submit', '--request-id', 'first', '--positions', json.dumps(POSITIONS))",))]

# SLAB-049 (docs/ci-spawn-review.md, SLAB-049 round). validate-reference is the grant host's one solver entry: it
# refuses under CI_ALLOCATION=1 before any reservation or launch, refuses binaries built with the CI entry guard,
# and runs the TAP argv on a private copy of the listed binary in its own process group under RLIMIT_CPU, only after
# its create-only launch claim succeeds.
RAW_SPAWNS += [('sundai_hotspot/reference_validation.py', 'subprocess.Popen', ('argv',))]

# SLAB-049 non-HotSpot sites, each under RLIMIT_CPU and a wall deadline: the binary's own dynamic loader listing its
# libraries (LD_TRACE_LOADED_OBJECTS=1, what ldd runs; the program never runs); TAP's own Python input generator;
# gcc building the assembly-only harness, which assembles HotSpot's conductance matrix and exits before direct_SLU;
# a one-second RLIMIT_CPU busy loop. Compiler and package identity are read in-process (no gcc --version or dpkg).
RAW_SPAWNS += [('sundai_hotspot/provenance.py', 'subprocess.Popen', ('[loader, str(executable)]',)),
               ('sundai_hotspot/slab049.py', 'subprocess.run',
                ("[sys.executable, '-c', script, json.dumps(spec), str(directory), *extra]",)),
               ('sundai_hotspot/slab049.py', 'subprocess.run', ('command',)),
               ('sundai_hotspot/slab049.py', 'subprocess.run',
                ('[str(binary), config, lcf, str(grid), str(grid), repr(float(r_convec)), str(probe[0]), '
                 'str(probe[1]), str(matrix_path)]',)),
               ('sundai_hotspot/test_gate_zero.py', 'subprocess.Popen',
                ("[sys.executable, '-c', 'while True: pass']",))]

# SLAB-049 operator supervisor (docs/ci-spawn-review.md, SLAB-049 follow-up round): warden's gate0_operator, which
# ran the gate on the grant host, launches validate-reference (the solver entry above, which refuses under
# CI_ALLOCATION=1) and the read-only record and report subcommands. No HotSpot of its own; never run in CI.
RAW_SPAWNS += [('sundai_hotspot/gate0_operator.py', 'subprocess.Popen', ('argv',)),
               ('sundai_hotspot/gate0_operator.py', 'subprocess.run', ('argv',))]

# The supervisor's synthetic cap-path test (root #57395): a fresh Python supervisor process running gate0_operator's
# run_call on Python stand-ins for validate-reference and the solver. The stand-in solver is under RLIMIT_CPU 5 s and
# a 10 s wall deadline. No HotSpot.
RAW_SPAWNS += [('sundai_hotspot/test_gate0_operator.py', 'subprocess.run',
                ("[sys.executable, '-c', SUPERVISOR, json.dumps(spec)]",))]

# Fresh Python import-path check of the reviewed operator; no HotSpot is launched.
RAW_SPAWNS += [('sundai_hotspot/test_coupling_allocation.py', 'subprocess.run',
                ("[sys.executable, '-c', code, str(stale), str(fixtures.REPO_ROOT)]",))]


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

        # Walk every module, including tests, rather than only the two known
        # native callers. Resolve import aliases and saved process functions too.
        paths = [path for area in ('sundai_hotspot', 'sundai_controller', 'sentilab_core', 'app',
                                  'sentilab_mcp', 'sentilab_cli')
                 for path in (ROOT / area).rglob('*.py')]
        paths.append(ROOT / 'sundai_tap/passive_interposer.py')
        raw_spawns = []
        for path in paths:
            tree = ast.parse(path.read_text())
            imports = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update((alias.asname or alias.name, alias.name) for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.update((alias.asname or alias.name, f'{node.module}.{alias.name}')
                                   for alias in node.names)
                elif isinstance(node, ast.Assign) and isinstance(node.value, (ast.Name, ast.Attribute)):
                    prefix, dot, suffix = ast.unparse(node.value).partition('.')
                    name = imports.get(prefix, prefix) + (dot + suffix if dot else '')
                    imports.update((target.id, name) for target in node.targets
                                   if isinstance(target, ast.Name))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = ast.unparse(node.func)
                prefix, dot, suffix = name.partition('.')
                name = imports.get(prefix, prefix) + (dot + suffix if dot else '')
                if (name in {f'subprocess.{method}' for method in
                             ('run', 'Popen', 'call', 'check_call', 'check_output', 'getoutput', 'getstatusoutput')}
                        or name in ('os.system', 'os.popen', 'os.fork', 'os.forkpty')
                        or name.startswith(('asyncio.create_subprocess_', 'os.exec', 'os.spawn', 'os.posix_spawn'))):
                    raw_spawns.append((path.relative_to(ROOT).as_posix(), name,
                                       tuple(ast.unparse(arg) for arg in node.args)))
        self.assertCountEqual(raw_spawns, RAW_SPAWNS, 'unreviewed direct process launch')

        # Vendored example scripts are outside CI. They retain direct commands,
        # which the compiled CI entry guard refuses, including copied binaries.
        example_launches = []
        for area in ('sundai_hotspot', 'sundai_controller', 'sentilab_core', 'app'):
            for path in (ROOT / area).rglob('*.sh'):
                for line in path.read_text().splitlines():
                    words = shlex.split(line, comments=True)
                    if words and Path(words[0]).name == 'hotspot':
                        example_launches.append(path.relative_to(ROOT).as_posix())
        self.assertCountEqual(example_launches, [
            f'sundai_hotspot/examples/example{number}/run.sh'
            for number in range(1, 6) for _ in range(2)
        ] + ['sundai_hotspot/examples/example2/newrun.sh'])

        # Frontends do not own a native launch: retain their shared oracle/worker
        # routing as well as the two gate calls checked above.
        for filename, callee in (
            ('sundai_hotspot/run_tap_probe.py', 'HotSpotOracle'),
            ('sundai_controller/mesh_study.py', 'HotSpotOracle'),
            ('sundai_controller/headroom.py', 'oracle_type'),
            ('sundai_controller/headroom_supervisor.py', 'run_headroom'),
            ('sundai_controller/tfl08_leaderboard.py', 'HotSpotOracle'),
            ('app/runs.py', 'HotSpotOracle'),
            ('sentilab_core/worker.py', 'evaluate'),
        ):
            with self.subTest(filename=filename):
                tree = ast.parse((ROOT / filename).read_text())
                if filename == 'sundai_controller/headroom.py':
                    self.assertTrue(any(isinstance(node, ast.Assign)
                                        and any(isinstance(target, ast.Name) and target.id == 'oracle_type'
                                                for target in node.targets)
                                        and ast.unparse(node.value) == 'oracle_factory or HotSpotOracle'
                                        for node in ast.walk(tree)))
                self.assertTrue(any(isinstance(node, ast.Call)
                                    and ast.unparse(node.func) == callee for node in ast.walk(tree)))

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
