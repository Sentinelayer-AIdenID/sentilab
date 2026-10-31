"""CLI/MCP process parity on signed fixtures, without running a conductor."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sentilab_cli.__main__ import dispatch
from sentilab_core.ledger import Ledger
from sentilab_core.memory import MemoryStore
from sentilab_core.operations import Context
from sentilab_core.test_ledger import RuntimeSigner
from sentilab_core.test_memory import FIXTURE
from sentilab_mcp import TOOLS
from sentilab_mcp.__main__ import handle, schema

ROUTING = FIXTURE.with_name("routing-fixtures.json")


class MemoryTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(FIXTURE.read_text())
        self.scope = self.fixture["scope"]
        signer = RuntimeSigner()
        self.keys = {signer.key_id: signer.public_key}
        run = {"run_id": self.scope["run"], **{k: self.scope[k] for k in ("arm", "family", "seed")},
               "ticket_id": "23a5285a"}
        self.ledger = Ledger(self.root, run, public_keys=self.keys, signer=signer)
        for index, event in enumerate(self.fixture["events"]):
            self.ledger.append(event["type"], event["body"], event_id=f"fixture-{index}")
        self.store = MemoryStore(self.root / "memory", ledger_root=self.root, public_keys=self.keys,
                                 tenant=self.scope["tenant"], held_out_families=self.fixture["held_out_families"])
        for memory in self.fixture["memories"]:
            self.store.write(self.scope, **memory)
        self.context = Context(self.root, self.keys, memory_tenant=self.scope["tenant"],
                               held_out_families=self.fixture["held_out_families"], routing_fixture=ROUTING)
        self.environment = {**os.environ, "SENTILAB_LIVE_DIR": str(self.root),
                            "SENTILAB_VIEW_PUBLIC_KEYS": json.dumps({k: v.hex() for k, v in self.keys.items()}),
                            "SENTILAB_MEMORY_TENANT": self.scope["tenant"],
                            "SENTILAB_MEMORY_HELD_OUT": json.dumps(self.fixture["held_out_families"]),
                            "SENTILAB_ROUTING_FIXTURE": str(ROUTING)}
        self.environment.pop("SENTILAB_SIGNER_FACTORY", None)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "sentilab_cli", *args],
                              env=self.environment, capture_output=True, text=True)

    def mcp(self, name, arguments):
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": name, "arguments": arguments}}]
        result = subprocess.run([sys.executable, "-m", "sentilab_mcp"], env=self.environment,
                                input="".join(json.dumps(r) + "\n" for r in requests),
                                text=True, capture_output=True, check=True)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual({t["name"] for t in responses[0]["result"]["tools"]}, set(TOOLS))
        return responses[1]

    def test_real_cli_mcp_recall_audit_and_withdrawal_parity(self):
        for withdrawn in (False, True):
            if withdrawn:
                correction = self.fixture["correction"]
                self.ledger.append(correction["type"], correction["body"], event_id="withdraw")
            for command in ("recall", "audit"):
                with self.subTest(withdrawn=withdrawn, command=command):
                    cli = self.cli("memory", command, "--scope", json.dumps(self.scope))
                    self.assertEqual(cli.returncode, 0, cli.stderr)
                    mcp = self.mcp("sentilab_memory_" + command, {"scope": self.scope})
                    actual = json.loads(cli.stdout)
                    self.assertEqual(actual, json.loads(mcp["result"]["content"][0]["text"]))
                    records = actual["items" if command == "recall" else "records"]
                    expected = self.fixture["expected_after" if withdrawn and command == "recall" else "expected_before"]
                    self.assertEqual([r["item"]["id"] for r in records], expected)

    def test_real_cli_mcp_route_suggestion_abstention_and_report_parity(self):
        for args in ({"task": {"candidate": "thermal-lab", "score": .9}},
                     {"task": {"candidate": "thermal-lab", "score": .3}}, {"calibrate": True}):
            with self.subTest(args=args):
                flags = ["--calibrate"] if args.get("calibrate") else ["--task", json.dumps(args["task"])]
                cli = self.cli("route", *flags)
                self.assertEqual(cli.returncode, 0, cli.stderr)
                mcp = self.mcp("sentilab_route", args)
                result = json.loads(cli.stdout)
                self.assertEqual(result, json.loads(mcp["result"]["content"][0]["text"]))
                self.assertTrue(result["advisory"])
                if "task" in args:
                    self.assertEqual(result["choice"], "thermal-lab" if args["task"]["score"] == .9 else None)
                else:
                    self.assertEqual(result["count"], 8)
                    self.assertEqual(result["abstention_rate"], 3 / 8)

    def test_cli_mcp_unknown_route_and_scope_refuse_equally(self):
        for task in ({"candidate": "not-registered", "score": 0},
                     {"candidate": "thermal-lab", "score": True}):
            cli = self.cli("route", "--task", json.dumps(task))
            self.assertNotEqual(cli.returncode, 0)
            self.assertIn("error", self.mcp("sentilab_route", {"task": task}))
        foreign = {**self.scope, "tenant": "foreign"}
        self.assertNotEqual(self.cli("memory", "recall", "--scope", json.dumps(foreign)).returncode, 0)
        self.assertIn("error", self.mcp("sentilab_memory_recall", {"scope": foreign}))

    def test_shared_dispatch_queries_and_authority_negative_inputs(self):
        args = {"scope": self.scope, "query": "Independent"}
        cli = asyncio.run(dispatch("memory_recall", self.context, **args))
        self.assertEqual(cli, TOOLS["sentilab_memory_recall"](self.context, **args))
        self.assertEqual([r["item"]["id"] for r in cli["items"]], ["alternative"])
        for name, args in (("sentilab_memory_recall", {"scope": self.scope, "tenant": "foreign"}),
                           ("sentilab_route", {"task": {"candidate": "thermal-lab", "score": .9}, "accept": True}),
                           ("sentilab_route", {"calibrate": True, "task": {"candidate": "thermal-lab", "score": .9}}),
                           ("sentilab_route", {}), ("sentilab_route", {"calibrate": "true"})):
            with self.subTest(name=name, args=args), self.assertRaises((ValueError, TypeError)):
                asyncio.run(handle({"method": "tools/call", "params": {"name": name, "arguments": args}}, self.context))
        self.assertNotIn("sentilab_memory_write", TOOLS)
        self.assertEqual(set(schema("sentilab_memory_recall")["properties"]), {"scope", "query"})
        self.assertFalse(self.context.options, "advisory config must not become conductor options")


if __name__ == "__main__":
    unittest.main()
