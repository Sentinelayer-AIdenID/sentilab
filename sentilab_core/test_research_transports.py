"""Byte parity through the real CLI and MCP stdio processes, with no solves."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sentilab_core.test_research import NS


class ResearchTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = {**os.environ, "SENTILAB_LIVE_DIR": self.temp.name,
                            "SENTILAB_VIEW_PUBLIC_KEYS": "{}",
                            "SENTILAB_RESEARCH_NAMESPACE": json.dumps(NS)}
        self.environment.pop("SENTILAB_SIGNER_FACTORY", None)

    def cli(self, command, args):
        flags = []
        for key, value in args.items():
            if key == "ai_off":
                if value:
                    flags.append("--ai-off")
            else:
                flags += ["--" + key.replace("_", "-"), json.dumps(value) if key == "namespace" else str(value)]
        return subprocess.run([sys.executable, "-m", "sentilab_cli", "research", command, *flags],
                              env=self.environment, capture_output=True, timeout=10)

    def mcp(self, command, args):
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "sentilab_research_" + command, "arguments": args}}]
        process = subprocess.run([sys.executable, "-m", "sentilab_mcp"],
                                 input="".join(json.dumps(r) + "\n" for r in requests).encode(),
                                 env=self.environment, capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, b"")
        responses = {r["id"]: r for r in map(json.loads, process.stdout.splitlines())}
        listed = {tool["name"]: tool for tool in responses[1]["result"]["tools"]}
        for name in ("request", "status", "export"):
            schema = listed["sentilab_research_" + name]["inputSchema"]
            self.assertFalse(schema["additionalProperties"])
            self.assertIn("namespace", schema["required"])
        return responses[2]["result"]

    def parity(self, command, args, code=0):
        cli = self.cli(command, args)
        self.assertEqual(cli.returncode, code, cli.stderr)
        self.assertEqual(cli.stderr, b"")
        mcp = self.mcp(command, args)
        self.assertEqual(cli.stdout, (mcp["content"][0]["text"] + "\n").encode())
        self.assertEqual(mcp["isError"], code != 0)
        return json.loads(cli.stdout)

    def test_real_request_status_export_have_identical_bytes(self):
        args = {"ai_off": True, "namespace": NS, "question": "fixture citation reproduction"}
        created = self.parity("request", args)
        lookup = {"ai_off": True, "namespace": NS, "request_id": created["request_id"]}
        self.assertEqual(self.parity("status", lookup)["status"], "completed")
        export = self.parity("export", lookup)
        self.assertEqual(export["type"], "untrusted_source_evidence")
        self.assertEqual(export["notes"][0]["type"], "untrusted_source_evidence")
        self.assertTrue(export["notes"][0]["citations"])
        self.assertFalse(list(self.root.glob("*.jsonl")))

    def test_real_errors_auth_stop_and_bounds_preserve_parity_without_echo(self):
        args = {"ai_off": True, "namespace": NS, "question": "private submitted text"}
        cases = [({**args, "ai_off": False}, "ai_off_required"),
                 ({**args, "namespace": {**NS, "arm": "other"}}, "namespace_not_authorized"),
                 ({**args, "namespace": {**NS, "seed": True}}, "invalid_namespace"),
                 ({**args, "question": "x" * 8193}, "oversize"),
                 ({k: v for k, v in args.items() if k != "question"}, "invalid_input")]
        for arguments, expected in cases:
            with self.subTest(expected=expected):
                result = self.parity("request", arguments, code=2)
                self.assertEqual(result["error"]["code"], expected)
                self.assertNotIn("private submitted text", json.dumps(result))
        self.assertEqual(list(self.root.iterdir()), [])
        (self.root / "STOP").touch()
        self.assertEqual(self.parity("request", args, code=2)["error"]["code"], "stopped")

    def test_transport_cannot_supply_backend_admission_or_privileged_fields(self):
        args = {"ai_off": True, "namespace": NS, "question": "private submitted text"}
        for key in ("backend", "admission_record", "actor_role", "accepted", "approver"):
            result = self.mcp("request", {**args, key: "private submitted text"})
            self.assertTrue(result["isError"])
            self.assertEqual(json.loads(result["content"][0]["text"])["error"]["code"], "invalid_input")
        cli = self.cli("request", {**args, "backend": "private submitted text"})
        self.assertEqual(cli.returncode, 2)
        self.assertNotIn(b"private submitted text", cli.stdout + cli.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_executable_cli_propagates_research_error_exit_code(self):
        command = [sys.executable, "sentilab_cli/sentilab", "research", "request",
                   "--namespace", json.dumps(NS), "--question", "private submitted text"]
        result = subprocess.run(command, env=self.environment, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "ai_off_required")
        self.assertEqual(result.stderr, b"")

    def test_missing_or_malformed_host_scope_refuses_both_transports(self):
        for value in (None, "malformed", "{}"):
            if value is None:
                self.environment.pop("SENTILAB_RESEARCH_NAMESPACE", None)
            else:
                self.environment["SENTILAB_RESEARCH_NAMESPACE"] = value
            result = self.parity("request", {"ai_off": True, "namespace": NS, "question": "scope"}, code=2)
            self.assertIn(result["error"]["code"], {"namespace_not_authorized", "invalid_namespace"})
        self.assertEqual(list(self.root.iterdir()), [])
