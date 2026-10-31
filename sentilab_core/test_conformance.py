"""Registry/surface conformance over shipped parsers and real MCP stdio.

The five per-capability execution checks are not implemented yet. This suite
must not be represented as proof of auth, STOP, errors or bound parity.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from sentilab_cli.__main__ import build_parser, dataset_parser
from sentilab_core.capabilities import CAPABILITIES, assert_surfaces, coverage_markdown


ROOT = Path(__file__).resolve().parents[1]


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
