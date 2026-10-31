"""Registry/surface conformance over shipped parsers and real MCP stdio.

The common invalid-input and wire-bound checks run without importing lanes.
Valid execution, auth and STOP checks remain outstanding.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from sentilab_cli.__main__ import build_parser, dataset_parser
from sentilab_core.capabilities import CAPABILITIES, assert_surfaces, coverage_markdown, implemented


ROOT = Path(__file__).resolve().parents[1]


class BoundaryConformance(unittest.TestCase):
    def cli(self, row, extra):
        flags = ["--run-id", "fixture"] if row.name == "dataset.export" else ["--ai-off"]
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
                extra = (["--run-id", "fixture"] * 5000 if row.name == "dataset.export"
                         else ["--ai-off"] * 8200)
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
            branch = dataset_parser() if namespace == "dataset" else parser
            command = next(action for action in branch._actions if action.dest == "command")
            observed.update((namespace, choice) for choice in command.choices)
            invocation = [sys.executable, "-m", "sentilab_cli"]
            if namespace == "dataset":
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
