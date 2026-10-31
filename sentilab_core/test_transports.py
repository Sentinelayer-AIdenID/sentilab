import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from sentilab_cli.__main__ import dispatch
from sentilab_core.operations import Context, environment_context
from sentilab_core import test_conductor
from sentilab_mcp import TOOLS


class EnvironmentContextTests(unittest.TestCase):
    def test_research_and_memory_host_options_survive_together(self):
        namespace = {"run_id": "fixture", "arm": "baseline", "family": "plate",
                     "seed": 7, "lab": "thermal"}
        environment = {"SENTILAB_LIVE_DIR": "local-ledgers", "SENTILAB_VIEW_PUBLIC_KEYS": "{}",
                       "SENTILAB_RESEARCH_NAMESPACE": json.dumps(namespace),
                       "SENTILAB_MEMORY_TENANT": "local-tenant",
                       "SENTILAB_MEMORY_HELD_OUT": '["held-out"]',
                       "SENTILAB_ROUTING_FIXTURE": "routing-fixture.json"}
        for research_value, expected in ((json.dumps(namespace), namespace), ("malformed", {})):
            with self.subTest(research_value=research_value), patch.dict(
                    os.environ, {**environment, "SENTILAB_RESEARCH_NAMESPACE": research_value}, clear=True):
                context = environment_context()
                self.assertEqual(context.options, {"research_namespace": expected})
                self.assertEqual(context.memory_tenant, "local-tenant")
                self.assertEqual(context.held_out_families, ["held-out"])
                self.assertEqual(context.routing_fixture, "routing-fixture.json")


class TransportTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_conductor.ConductorTests.asyncSetUp

    async def test_each_cli_and_mcp_operation_returns_identical_receipts(self):
        await self.conductor.run(run_id="parity", max_ticks=1)
        self.conductor.finish("parity fixture complete")
        context = Context(Path(self.temp.name), self.keys, self.signer,
                          {key: value for key, value in self.options.items() if key not in ("signer", "public_keys")})
        for command in ("run", "status", "stop", "verify"):
            args = {"ai_off": True}
            if command != "stop":
                args["run_id"] = "parity"
            cli = await dispatch(command, context, **args)
            mcp = TOOLS["sentilab_live_" + command](context, **args)
            if hasattr(mcp, "__await__"):
                mcp = await mcp
            self.assertEqual(cli, mcp, command)
            with self.assertRaises(ValueError):
                await dispatch(command, context, **{**args, "ai_off": False})

    async def test_real_cli_process_and_mcp_stdio_verify_same_ledger(self):
        await self.conductor.run(run_id="wire-parity", max_ticks=1)
        environment = {**os.environ, "SENTILAB_LIVE_DIR": self.temp.name,
                       "SENTILAB_VIEW_PUBLIC_KEYS": json.dumps({k: v.hex() for k, v in self.keys.items()})}
        cli = subprocess.run([sys.executable, "-m", "sentilab_cli", "live", "verify", "--ai-off",
                              "--run-id", "wire-parity"], env=environment, capture_output=True, check=True)
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "sentilab_live_verify", "arguments": {"ai_off": True, "run_id": "wire-parity"}}}]
        mcp = subprocess.run([sys.executable, "-m", "sentilab_mcp"], env=environment,
                              input="".join(json.dumps(r) + "\n" for r in requests).encode(),
                              capture_output=True, check=True)
        responses = [json.loads(line) for line in mcp.stdout.splitlines()]
        self.assertEqual({t["name"] for t in responses[0]["result"]["tools"]}, set(TOOLS))
        self.assertEqual(json.loads(cli.stdout), json.loads(responses[1]["result"]["content"][0]["text"]))


if __name__ == "__main__":
    unittest.main()
