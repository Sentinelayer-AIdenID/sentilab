"""Registry and execution conformance over real CLI/MCP, with recorded fixtures.

Mid-call STOP-file creation remains distinct from the proven request-cancellation
checks. Pending owner contracts are explicit; see generated COVERAGE.md.
"""
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

from sentilab_cli.__main__ import build_parser, chiplet_parser, dataset_parser
from sentilab_core.capabilities import CAPABILITIES, assert_surfaces, coverage_markdown, implemented


ROOT = Path(__file__).resolve().parents[1]

# Both shipped entry points accept a host-injected Context. The fixture supplies
# only an oracle configuration/cleanup object; it replaces no transport, handler,
# conductor method or gate. STOP is present before run, so it cannot measure.
FIXTURE_HOST = r'''
import asyncio
import sys
from sentilab_core.operations import environment_context
from sentilab_core.test_cleanup import BarrierOracle
context = environment_context()
oracle = BarrierOracle()
oracle.release.set()
context.options = {"oracle": oracle, "fixture": "recorded-test"}
if sys.argv[1] == "cli":
    from sentilab_cli.__main__ import main
    sys.argv = sys.argv[1:]
    main(context=context)
else:
    from sentilab_mcp.__main__ import serve
    asyncio.run(serve(context))
'''


class ExecutionConformance(unittest.TestCase):
    """Actual CLI and stdio processes, signed recorded data, zero solves."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture = ROOT / "docs/sentilab/evidence/SLAB-016"
        shutil.copyfile(fixture / "fixture.jsonl", self.root / "fixture.jsonl")
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(("SENTILAB_", "FLIGHT_SIGNING_"))}
        self.environment.update(SENTILAB_LIVE_DIR=str(self.root),
                                SENTILAB_VIEW_PUBLIC_KEYS=(fixture / "public-keys.json").read_text(),
                                OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
        self.fixture_context = False

    def arguments(self, row):
        if row.name == "live.run":
            return {"ai_off": True, "run_id": "stopped-fixture"}
        if row.name == "live.stop":
            return {"ai_off": True}
        if row.name.startswith("live."):
            return {"ai_off": True, "run_id": "fixture"}
        if row.name == "chiplet.build":
            return {"fixture": "plate"}
        if row.name == "dataset.export":
            return {"run_ids": ["fixture"], "output_dir": str(self.root / "datasets")}
        if row.name == "chiplet.export":
            return {"run_id": "fixture", "output_dir": str(self.root / "datasets")}
        return {"run_id": "fixture"}

    def cli_command(self, row, arguments):
        command = [sys.executable, "-m", "sentilab_cli", *row.cli_command]
        if row.name == "live.run" and self.fixture_context:
            command = [sys.executable, "-c", FIXTURE_HOST, "cli", *row.cli_command]
        for name, value in arguments.items():
            if name == "ai_off":
                if value:
                    command.append("--ai-off")
            elif name == "run_ids":
                for run in value:
                    command.extend(["--run-id", run])
            else:
                command.extend(["--" + name.replace("_", "-"),
                                json.dumps(value) if isinstance(value, (list, dict)) else str(value)])
        return command

    def cli(self, row, arguments):
        return subprocess.run(self.cli_command(row, arguments), env=self.environment,
                              cwd=ROOT, capture_output=True, timeout=10)

    def start_mcp(self):
        command = ([sys.executable, "-c", FIXTURE_HOST, "mcp"] if self.fixture_context else
                   [sys.executable, "-m", "sentilab_mcp"])
        process = subprocess.Popen(command, env=self.environment,
                                   cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, bufsize=0)
        self.addCleanup(self.close, process)
        return process

    def close(self, process):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                stream.close()

    def send(self, process, request):
        process.stdin.write(json.dumps({"jsonrpc": "2.0", **request}).encode() + b"\n")
        process.stdin.flush()

    def receive(self, process):
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(10), "MCP response timed out")
            line = process.stdout.readline()
        self.assertTrue(line, "MCP exited without a response")
        return json.loads(line)

    def call(self, process, row, arguments):
        self.send(process, {"id": 1, "method": "tools/call", "params": {
            "name": row.mcp_tool, "arguments": arguments}})

    def mcp(self, row, arguments):
        process = self.start_mcp()
        self.call(process, row, arguments)
        response = self.receive(process)
        process.stdin.close()
        process.wait(timeout=5)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stderr.read(), b"")
        return response

    def prepare_stopped_run(self):
        # Generate only in RAM and pass to the existing signer via environment.
        # No private material is written to fixtures, logs or the workspace.
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        from sundai_controller.trust import key_id_for
        seed = os.urandom(32)
        public = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw).hex()
        keys = json.loads(self.environment["SENTILAB_VIEW_PUBLIC_KEYS"])
        keys[key_id_for(public)] = public
        self.environment.update(FLIGHT_SIGNING_SEED_B64=base64.b64encode(seed).decode(),
                                SENTILAB_SIGNER_FACTORY="sentilab_core.signing:service_signer",
                                SENTILAB_VIEW_PUBLIC_KEYS=json.dumps(keys))
        (self.root / "STOP").touch()
        self.fixture_context = True

    def test_each_capability_returns_identical_bytes_and_output_schema(self):
        from jsonschema import Draft202012Validator
        from sundai_controller.experiment import plate_initial_design
        required = {"chiplet." + command for command in ("build", "render", "replay", "export")}
        self.assertTrue(required <= {row.name for row in implemented()})
        self.prepare_stopped_run()
        for row in implemented():
            with self.subTest(capability=row.name):
                self.environment["SENTILAB_CAPABILITY_SCOPES"] = json.dumps([row.name])
                arguments = self.arguments(row)
                cli = self.cli(row, arguments)
                self.assertEqual(cli.returncode, 0, cli.stdout)
                self.assertEqual(cli.stderr, b"")
                response = self.mcp(row, arguments)
                self.assertNotIn("error", response, response)
                payload = response["result"]["content"][0]["text"].encode()
                self.assertEqual(cli.stdout, payload + b"\n")
                value = json.loads(payload)
                Draft202012Validator(row.output_schema).validate(value)
                if row.name == "live.run":
                    self.assertEqual(value["status"], "stopped")
                    self.assertEqual(value["spend"]["solves"], 0)
                if row.name == "chiplet.render":
                    self.assertTrue(value["view"]["cards"])
                if row.name == "chiplet.build":
                    self.assertEqual(value["design_hash"], plate_initial_design().hash)
                if row.name in ("chiplet.replay", "live.status", "live.verify"):
                    self.assertTrue(value["ok"])
                    self.assertEqual(value["prefix_end"], len((self.root / "fixture.jsonl").read_bytes().splitlines()))
                if row.name in ("dataset.export", "chiplet.export"):
                    import hashlib
                    self.assertEqual(value["counts"]["candidates"], 7)
                    for name, digest in value["sha256"].items():
                        self.assertEqual(hashlib.sha256((Path(value["directory"]) / name).read_bytes()).hexdigest(), digest)

    def test_each_capability_refuses_wrong_types_or_bounds_without_echo(self):
        cases = {
            "live.run": {"ai_off": True, "duration": -1},
            "live.status": {"ai_off": True, "run_id": ""},
            "live.stop": {"ai_off": False},
            "live.verify": {"ai_off": True, "run_id": ""},
            "dataset.export": {"run_ids": []},
            "chiplet.build": {"fixture": "rejected-value-marker"},
            "chiplet.render": {"run_id": "fixture", "cursor": -1},
            "chiplet.replay": {"run_id": ""},
            "chiplet.export": {"run_id": ""},
        }
        self.assertEqual(set(cases), {row.name for row in implemented()})
        for row in implemented():
            with self.subTest(capability=row.name):
                arguments = cases[row.name]
                cli = self.cli(row, arguments)
                response = self.mcp(row, arguments)
                self.assertEqual(cli.returncode, 2, cli.stdout)
                self.assertEqual(json.loads(cli.stdout)["error"], response["error"])
                self.assertEqual(response["error"]["code"], -32602)
                self.assertNotIn("rejected-value-marker", json.dumps(response))
                self.assertNotIn(b"rejected-value-marker", cli.stdout + cli.stderr)

    def test_each_capability_requires_host_granted_scope_before_side_effects(self):
        self.environment["SENTILAB_CAPABILITY_SCOPES"] = "[]"
        def snapshot():
            return {str(path.relative_to(self.root)): None if path.is_dir() else path.read_bytes()
                    for path in self.root.rglob("*")}
        before = snapshot()
        for row in implemented():
            with self.subTest(capability=row.name):
                cli = self.cli(row, self.arguments(row))
                response = self.mcp(row, self.arguments(row))
                self.assertEqual(cli.returncode, 2)
                self.assertEqual(json.loads(cli.stdout)["error"], response["error"])
                self.assertEqual(response["error"], {"code": -32001, "message": "capability scope refused"})
        self.assertEqual(before, snapshot())

    def freeze_worker(self, process):
        # Stop the real OS child after dispatch, before its result can race the
        # cancellation. This changes scheduling, not any shipped function.
        deadline = time.monotonic() + 10
        children = Path(f"/proc/{process.pid}/task/{process.pid}/children")
        while time.monotonic() < deadline and process.poll() is None:
            for child in children.read_text().split():
                pid = int(child)
                try:
                    if os.getpgid(pid) != pid:
                        continue  # wait until subprocess isolation is installed
                    # setsid precedes exec. Pausing before exec would keep the
                    # spawn handshake open, so no transport can reap it yet.
                    if b"sentilab_core.execution" not in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0"):
                        continue
                    os.kill(pid, signal.SIGSTOP)
                    self.addCleanup(self.reap_frozen_group, pid)
                    return pid
                except (ProcessLookupError, FileNotFoundError):
                    pass
            time.sleep(0.001)
        self.fail("recorded worker was not dispatched")

    def reap_frozen_group(self, pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def test_recorded_capability_cancellation_reaps_real_workers_on_both_surfaces(self):
        for row in implemented():
            if row.name == "live.run":
                # The signer stays in the parent; its lane owns conductor cleanup.
                continue
            with self.subTest(capability=row.name):
                arguments = self.arguments(row)
                cli = subprocess.Popen(self.cli_command(row, arguments), env=self.environment, cwd=ROOT,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.addCleanup(self.close, cli)
                child = self.freeze_worker(cli)
                cli.send_signal(signal.SIGINT)
                stdout, stderr = cli.communicate(timeout=10)
                self.assertEqual(cli.returncode, 130, (stdout, stderr))
                self.assertEqual(stderr, b"")
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)
                process = self.start_mcp()
                self.call(process, row, arguments)
                child = self.freeze_worker(process)
                self.send(process, {"method": "notifications/cancelled", "params": {"requestId": 1}})
                response = self.receive(process)
                self.assertEqual(json.loads(stdout)["error"], response["error"])
                self.assertEqual(response["error"]["code"], -32800)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)
                self.send(process, {"id": 2, "method": "ping"})
                self.assertEqual(self.receive(process)["result"], {})

    def test_chiplet_replay_render_export_refuse_tampered_history(self):
        required = {"chiplet.render", "chiplet.replay", "chiplet.export"}
        self.assertTrue(required <= {row.name for row in implemented()})
        path = self.root / "fixture.jsonl"
        data = path.read_text()
        path.write_text(data.replace('"fixture"', '"tampered"', 1))
        for row in implemented():
            if row.name not in required:
                continue
            with self.subTest(capability=row.name):
                cli = self.cli(row, self.arguments(row))
                response = self.mcp(row, self.arguments(row))
                self.assertEqual(cli.returncode, 2)
                self.assertEqual(json.loads(cli.stdout)["error"], response["error"])
                self.assertEqual(response["error"]["code"], -32602)
        self.assertFalse((self.root / "datasets").exists())


class BoundaryConformance(unittest.TestCase):
    def cli(self, row, extra):
        flags = (["--ai-off"] if row.name.startswith("live.") else
                 ["--fixture", "plate"] if row.name == "chiplet.build" else ["--run-id", "fixture"])
        return subprocess.run([sys.executable, "-m", "sentilab_cli", *row.cli_command,
                               *flags, *extra], capture_output=True, cwd=ROOT, timeout=10)

    def mcp(self, requests):
        result = subprocess.run([sys.executable, "-m", "sentilab_mcp"],
                                input=requests, capture_output=True, cwd=ROOT, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b"")
        return [json.loads(line) for line in result.stdout.splitlines()]

    def call(self, row, arguments):
        return json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": row.mcp_tool, "arguments": arguments}}).encode()

    def assert_refused(self, cli, mcp):
        self.assertEqual(cli.returncode, 2)
        self.assertEqual(cli.stderr, b"")
        self.assertEqual(json.loads(cli.stdout)["error"], mcp["error"])
        self.assertEqual(mcp["error"], {"code": -32602, "message": "ValueError"})

    def test_each_capability_rejects_unknown_input_without_echo(self):
        for row in implemented():
            with self.subTest(capability=row.name):
                marker = "rejected-value-marker"
                cli = self.cli(row, ["--unregistered-input", marker])
                responses = self.mcp(self.call(row, {"unregistered_input": marker}) + b"\n")
                self.assert_refused(cli, responses[0])
                self.assertNotIn(marker.encode(), cli.stdout + cli.stderr)
                self.assertNotIn(marker, json.dumps(responses))

    def test_each_capability_rejects_oversize_wire_input(self):
        for row in implemented():
            with self.subTest(capability=row.name):
                # Repeated valid flags and JSON whitespace keep these inputs
                # syntactically valid; a parser error cannot stand in for a cap.
                extra = (["--ai-off"] * 8200 if row.name.startswith("live.") else
                         ["--fixture", "plate"] * 5000 if row.name == "chiplet.build" else
                         ["--run-id", "fixture"] * 5000)
                cli = self.cli(row, extra)
                arguments = {"run_ids": ["fixture"]} if row.name == "dataset.export" else {"ai_off": True}
                wire = self.call(row, arguments) + b" " * 65536 + b"\n"
                responses = self.mcp(wire)
                self.assert_refused(cli, responses[0])

    def test_malformed_mcp_frames_refuse_safely_and_leave_ping_usable(self):
        cases = [b'{"rejected-value-marker":', b'[]', b'null', b'"rejected-value-marker"',
                 b'{"id":[],"method":"ping"}',
                 b'{"id":1,"method":"tools/call","params":[]}',
                 b'{"id":1,"method":"tools/call","params":{"name":[]}}',
                 b'{"id":1,"method":"tools/call","params":{"name":"sentilab_live_stop","arguments":[]}}',
                 b'{"id":1,"method":"tools/call","params":{"name":"sentilab_live_run","arguments":{"duration":NaN}}}',
                 b'\xff', b'[' * 1100 + b']' * 1100]
        ping = b'{"jsonrpc":"2.0","id":2,"method":"ping"}\n'
        for raw in cases:
            with self.subTest(raw=raw):
                responses = self.mcp(raw + b"\n" + ping)
                self.assertEqual(len(responses), 2)
                self.assertEqual(responses[0]["error"], {"code": -32602, "message": "ValueError"})
                self.assertEqual(responses[1], {"jsonrpc": "2.0", "id": 2, "result": {}})
                self.assertNotIn("rejected-value-marker", json.dumps(responses))

    def test_mcp_wire_limit_accepts_exactly_64_kib(self):
        ping = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
        for size in (65535, 65536, 65537):
            with self.subTest(size=size):
                responses = self.mcp(ping + b" " * (size - len(ping)) + b"\n")
                self.assertEqual(len(responses), 1)
                if size <= 65536:
                    self.assertEqual(responses[0], {"jsonrpc": "2.0", "id": 1, "result": {}})
                else:
                    self.assertEqual(responses[0]["error"], {"code": -32602, "message": "ValueError"})

    def test_cli_wire_limit_accepts_exactly_64_kib(self):
        # --help exits without importing or executing any lane. The otherwise
        # valid output path fills argv to the requested UTF-8 byte count.
        prefix = ["live", "verify", "--help", "--export"]
        prefix_size = sum(len(argument.encode()) + 1 for argument in prefix)
        for size in (65535, 65536, 65537):
            with self.subTest(size=size):
                command = [sys.executable, "-m", "sentilab_cli", *prefix,
                           "x" * (size - prefix_size - 1)]
                result = subprocess.run(command, capture_output=True, cwd=ROOT, timeout=10)
                self.assertEqual(result.stderr, b"")
                if size <= 65536:
                    self.assertEqual(result.returncode, 0)
                    self.assertIn(b"usage: sentilab", result.stdout)
                else:
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(json.loads(result.stdout)["error"],
                                     {"code": -32602, "message": "ValueError"})


class RegistryConformance(unittest.TestCase):
    def advertised_tools(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        result = subprocess.run([sys.executable, "-m", "sentilab_mcp"],
                                input=json.dumps(request) + "\n", text=True,
                                capture_output=True, cwd=ROOT, timeout=10, check=True)
        self.assertEqual(result.stderr, "")
        response = json.loads(result.stdout)
        self.assertEqual(response["id"], 1)
        self.assertNotIn("error", response, response)
        return response["result"]["tools"]

    def test_real_surfaces_match_registry(self):
        # Read argparse's actual grammar, including any independently added
        # choices; do not derive the observed commands from the registry.
        parser = build_parser()
        actions = {action.dest: action for action in parser._actions}
        observed = set()
        for namespace in actions["namespace"].choices:
            branch = {"dataset": dataset_parser, "chiplet": chiplet_parser}.get(namespace, lambda: parser)()
            command = next(action for action in branch._actions if action.dest == "command")
            observed.update((namespace, choice) for choice in command.choices)
            invocation = [sys.executable, "-m", "sentilab_cli"]
            if namespace in ("dataset", "chiplet"):
                invocation.append(namespace)
            result = subprocess.run([*invocation, "--help"], text=True, capture_output=True,
                                    cwd=ROOT, timeout=10, check=True)
            self.assertEqual(result.stderr, "")
            self.assertIn("{" + ",".join(command.choices) + "}", result.stdout)
        assert_surfaces(observed, self.advertised_tools())

    def test_pending_capabilities_are_owned_and_not_advertised(self):
        names = [row.name for row in CAPABILITIES]
        cli = [row.cli_command for row in CAPABILITIES]
        tools = [row.mcp_tool for row in CAPABILITIES]
        self.assertEqual(len(names), len(set(names)), "duplicate capability")
        self.assertEqual(len(cli), len(set(cli)), "duplicate CLI command")
        self.assertEqual(len(tools), len(set(tools)), "duplicate MCP tool")
        advertised = {tool["name"] for tool in self.advertised_tools()}
        for row in CAPABILITIES:
            with self.subTest(capability=row.name):
                self.assertIn(row.status, ("done", "pending"))
                self.assertTrue(row.owner.strip())
                self.assertTrue(row.auth_scope.strip())
                self.assertTrue(row.stop_behaviour.strip())
                if row.status == "pending":
                    self.assertTrue(row.pending_reason.strip())
                    self.assertNotIn(row.mcp_tool, advertised)
                    self.assertEqual(row.input_schema, {"not": {}})
                    self.assertEqual(row.output_schema, {"not": {}})

    def test_coverage_document_matches_registry(self):
        path = ROOT / "docs/sentilab/evidence/SLAB-043/COVERAGE.md"
        self.assertEqual(path.read_text(encoding="utf-8"), coverage_markdown())


if __name__ == "__main__":
    unittest.main()
