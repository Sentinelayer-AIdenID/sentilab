"""Synthetic proposal-boundary proof: no model calls, thermal solves or devices."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core.admission import Admission, NotAdmitted
from sentilab_core.envelope import verify
from sentilab_core.operations import Context
from sentilab_core.proposals import (ProposalGrant, ProposalHarness, ProposalLab,
                                     PublicProblem, execute)
from sentilab_core.test_admission import registry_record, write_registry
from sentilab_core.test_ledger import RuntimeSigner, run_record

ORACLE_ID = "a" * 64
POSITIONS = [[2, 2], [8, 8]]
PROBLEM = PublicProblem(ORACLE_ID, 20, 20, (("cpu", 2, 2, 10), ("dram", 2, 2, 5)), 100)


class FixtureOracle:
    oracle_id = ORACLE_ID

    def __init__(self):
        self.calls = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.cleaned = False

    async def evaluate(self, positions, *, stop_file):
        self.calls.append(deepcopy(positions))
        self.entered.set()
        try:
            await self.release.wait()
            # Synthetic contract responses, not thermal calculations/results.
            if positions[0][0] < 0:
                return {"legal": False, "J": None, "wire_mm": None}
            return {"legal": True, "J": positions[0][0] + 10, "wire_mm": 20}
        finally:
            self.cleaned = True


def fixture_options(root, signer, keys, *, budget=2, timeout=1):
    labs = tuple(ProposalLab(name, "fixture-model", Admission(
        root / "registry.json", run_id="fixture-run", arm_id=name, spend_path=root / "spend.json"))
        for name in ("lab-a", "lab-b"))
    return dict(root=root, run=run_record("fixture-run"), signer=signer, public_keys=keys,
                problem=PROBLEM, labs=labs, solve_budget=budget, timeout=timeout,
                grant=ProposalGrant("fixture-run", "fixture-grant", "fixture-slab048",
                                    ORACLE_ID, "2099-01-01T00:00:00Z", budget, ("lab-a", "lab-b")),
                oracle_factory=FixtureOracle)


def prepare_registry(root):
    write_registry(root / "registry.json", [registry_record(arm_id=lab) for lab in ("lab-a", "lab-b")])


class ProposalHarnessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.signer = RuntimeSigner()
        self.keys = {self.signer.key_id: self.signer.public_key}
        prepare_registry(self.root)
        self.options = fixture_options(self.root, self.signer, self.keys)
        self.harness = ProposalHarness(**self.options)
        self.context = Context(self.root, self.keys, self.signer,
                               proposal_session=self.harness.bind("lab-a"))

    async def submit(self, request_id="first", positions=None, lab="lab-a", harness=None):
        return await (harness or self.harness).oracles[lab].submit(
            request_id=request_id, positions=POSITIONS if positions is None else positions)

    async def test_signed_reservation_precedes_oracle_and_illegal_layouts_exhaust_budget(self):
        backend = self.harness.oracles["lab-a"].backend
        original = backend.evaluate
        async def checked(positions, **kwargs):
            rows = self.harness._events()
            self.assertEqual(rows[-1]["event"]["type"], "proposal.reserved")
            for row in rows:
                verify(row, run_id="fixture-run", public_keys=self.keys)
            body = rows[-1]["event"]["body"]
            self.assertEqual(body["positions"], positions)
            self.assertEqual((body["model_id"], body["provider"], body["payer"], body["grant_ref"]),
                             ("fixture-model", "fixture-provider", "fixture-payer", "fixture-grant"))
            return await original(positions, **kwargs)
        backend.evaluate = checked
        first = await self.submit(positions=[[-1, 2], [8, 8]])
        second = await self.submit("second")
        refused = await self.submit("third")
        self.assertEqual((first["status"], second["status"]), ("illegal", "evaluated"))
        self.assertEqual((first["slot"], second["slot"]), (1, 2))
        self.assertEqual(refused["error"]["code"], "solve_budget")
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual((await self.submit(lab="lab-b"))["slot"], 1)

    async def test_restart_idempotency_and_frozen_budget(self):
        first = await self.submit()
        restored = ProposalHarness(**self.options)
        self.assertEqual(await self.submit(harness=restored), first)
        self.assertEqual(restored.oracles["lab-a"].backend.calls, [])
        with self.assertRaises(ValueError):
            await self.submit(positions=[[3, 3], [8, 8]], harness=restored)
        await self.submit("second", harness=restored)
        self.assertEqual((await self.submit("third", harness=restored))["error"]["code"], "solve_budget")
        changed = {**self.options, "solve_budget": 3,
                   "grant": replace(self.options["grant"], solve_budget=3)}
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            ProposalHarness(**changed)

    async def test_crash_after_reservation_never_retries_or_refunds(self):
        append = self.harness.ledger.append
        def crash(event_type, *args, **kwargs):
            if event_type == "proposal.finished":
                raise OSError("synthetic crash")
            return append(event_type, *args, **kwargs)
        with patch.object(self.harness.ledger, "append", side_effect=crash):
            with self.assertRaises(OSError):
                await self.submit()
        restored = ProposalHarness(**self.options)
        receipt = await self.submit(harness=restored)
        self.assertEqual(receipt["status"], "interrupted")
        self.assertTrue(receipt["charged"])
        self.assertEqual(restored.oracles["lab-a"].backend.calls, [])
        self.assertEqual((await self.submit("second", harness=restored))["slot"], 2)
        self.assertEqual((await self.submit("third", harness=restored))["error"]["code"], "solve_budget")

    async def test_concurrent_hosts_share_per_lab_lock_and_allow_other_labs(self):
        backend = self.harness.oracles["lab-a"].backend
        backend.release.clear()
        task = asyncio.create_task(self.submit())
        await backend.entered.wait()
        try:
            restored = ProposalHarness(**self.options)
            refused = await self.submit("concurrent", harness=restored)
            self.assertEqual(refused["error"]["code"], "lab_busy")
            self.assertEqual((await self.submit(lab="lab-b", harness=restored))["status"], "evaluated")
        finally:
            backend.release.set()
            await task
        self.assertEqual(self.harness.context("lab-a")["used"], 1)

    async def test_stop_during_call_cancels_adapter_and_records_charge(self):
        backend = self.harness.oracles["lab-a"].backend
        backend.release.clear()
        task = asyncio.create_task(self.submit())
        await backend.entered.wait()
        self.harness.stop_file.touch()
        receipt = await asyncio.wait_for(task, 1)
        self.assertEqual(receipt["status"], "stopped")
        self.assertTrue(backend.cleaned)
        self.assertEqual((await self.submit("second"))["error"]["code"], "stopped")
        self.assertEqual(self.harness.context("lab-a")["used"], 1)

    async def test_cancellation_and_timeout_keep_signed_charge_and_cleanup(self):
        backend = self.harness.oracles["lab-a"].backend
        backend.release.clear()
        task = asyncio.create_task(self.submit())
        await backend.entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(backend.cleaned)
        self.assertEqual((await self.submit())["status"], "cancelled")
        self.assertEqual((await self.submit("timeout"))["status"], "timeout")
        self.assertEqual(self.harness.context("lab-a")["used"], 2)

    async def test_grant_expiry_during_call_drains_adapter_and_keeps_charge(self):
        from datetime import datetime, timedelta, timezone
        root = self.root / "expiring"
        root.mkdir()
        prepare_registry(root)
        options = fixture_options(root, self.signer, self.keys, timeout=5)
        options["grant"] = replace(options["grant"], expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat())
        harness = ProposalHarness(**options)
        backend = harness.oracles["lab-a"].backend
        backend.release.clear()
        receipt = await self.submit(harness=harness)
        self.assertEqual(receipt["status"], "grant_expired")
        self.assertTrue(receipt["charged"])
        self.assertTrue(backend.cleaned)
        self.assertEqual(harness._events()[-1]["event"]["body"]["receipt"], receipt)

    async def test_stop_after_backend_completion_does_not_publish_result(self):
        backend = self.harness.oracles["lab-a"].backend
        async def stop_after(*args, **kwargs):
            self.harness.stop_file.touch()
            return {"legal": True, "J": 1, "wire_mm": 1}
        backend.evaluate = stop_after
        receipt = await self.submit()
        self.assertEqual(receipt["status"], "stopped")
        self.assertNotIn("J", receipt)

    async def test_bad_input_and_backend_output_never_echo_or_bypass_accounting(self):
        for arguments in ({"request_id": "../bad", "positions": POSITIONS},
                          {"request_id": "bad", "positions": [[float("nan"), 1]]},
                          {"request_id": "bad", "positions": [[True, 1]]}):
            with self.assertRaises(ValueError):
                await self.harness.oracles["lab-a"].submit(**arguments)
        self.assertEqual(self.harness.context("lab-a")["used"], 0)
        self.assertEqual((await self.submit(positions=[[1, 1]]))["status"], "illegal")
        backend = self.harness.oracles["lab-a"].backend
        async def bad(*args, **kwargs):
            return {"legal": True, "J": float("nan"), "wire_mm": 3, "answer": "private-marker"}
        backend.evaluate = bad
        receipt = await self.submit("bad-backend")
        self.assertEqual(receipt["status"], "oracle_error")
        self.assertNotIn("private-marker", json.dumps(self.harness.context("lab-a")))
        self.assertEqual(self.harness.context("lab-a")["used"], 2)

    async def test_host_bounds_and_oracle_identity_cannot_change_the_run(self):
        for changes in ({"solve_budget": True}, {"solve_budget": 0}, {"solve_budget": 10001},
                        {"timeout": 0}, {"timeout": float("inf")},
                        {"labs": ()}, {"labs": self.options["labs"] * 2}):
            with self.assertRaises(ValueError):
                ProposalHarness(**{**self.options, **changes})
        with self.assertRaisesRegex(ValueError, "10000 total slots"):
            ProposalHarness(**{**self.options, "solve_budget": 6000})
        class WrongOracle(FixtureOracle):
            oracle_id = "b" * 64
        with self.assertRaises(NotAdmitted):
            ProposalHarness(**{**self.options, "oracle_factory": WrongOracle})
        for value in (float("nan"), -1, True):
            with self.assertRaises(ValueError):
                replace(PROBLEM, width_mm=value)

    async def test_admission_revocation_grant_scope_and_signer_fail_closed(self):
        grant = self.options["grant"]
        for changed in (None, replace(grant, expires_at="2000-01-01T00:00:00Z"),
                        replace(grant, run_id="wrong"), replace(grant, oracle_id="b" * 64),
                        replace(grant, solve_budget=3), replace(grant, lab_ids=("lab-a",)),
                        replace(grant, readiness_ref="")):
            with self.assertRaises(NotAdmitted):
                ProposalHarness(**{**self.options, "grant": changed})
        with self.assertRaises(NotAdmitted):
            ProposalHarness(**{**self.options, "signer": None})
        write_registry(self.root / "registry.json", [])
        with self.assertRaises(NotAdmitted):
            await self.submit()
        self.assertEqual(self.harness.oracles["lab-a"].backend.calls, [])
        write_registry(self.root / "registry.json", [registry_record(arm_id="lab-a", roles=["judge"])])
        with self.assertRaises(NotAdmitted):
            await self.submit()

    async def test_lab_context_is_isolated_and_cannot_select_answers_or_identity(self):
        await self.submit("private-b", positions=[[9, 9], [8, 8]], lab="lab-b")
        await self.submit("own-a")
        view = await execute("context", self.context)
        serialized = json.dumps(view)
        self.assertNotIn("private-b", serialized)
        self.assertNotIn("lab-b", serialized)
        self.assertNotIn("payer", serialized)
        self.assertEqual([row["request_id"] for row in view["feedback"]], ["own-a"])
        view["problem"]["chiplets"][0][0] = "changed"
        self.assertEqual(self.harness.context("lab-a")["problem"]["chiplets"][0][0], "cpu")
        for field in ("lab_id", "budget", "oracle", "grant", "heldout", "answers"):
            with self.assertRaises(ValueError):
                await execute("submit", self.context, request_id="escape", positions=POSITIONS,
                              **{field: "rejected-value-marker"})
        with self.assertRaises(NotAdmitted):
            self.harness.bind("unknown")

    async def test_report_requires_matched_objective_and_budget_and_retains_incomplete(self):
        sa = {"oracle_id": ORACLE_ID, "J": 15, "wire_mm": 30, "solves": 2, "evidence_ref": "fixture-sa"}
        human = {"oracle_id": ORACLE_ID, "J": 11, "wire_mm": 18, "evidence_ref": "fixture-human"}
        await self.submit("first", [[5, 5], [8, 8]])
        await self.submit("best", [[1, 1], [8, 8]])
        report = self.harness.report(sa=sa, human=human)
        first, second = report["rows"]
        self.assertTrue(first["complete"])
        self.assertEqual((first["best_J"], first["wire_at_best_J_mm"], first["delta_J_sa"],
                          first["delta_J_human"]), (11, 20, -4, 0))
        self.assertEqual((first["delta_wire_sa_mm"], first["delta_wire_human_mm"]), (-10, 2))
        self.assertFalse(second["complete"])
        self.assertIsNone(second["best_J"])
        self.assertNotIn("fixture-human", json.dumps(self.harness.context("lab-a")))
        for change in ({"solves": 1}, {"oracle_id": "b" * 64}, {"J": float("nan")}):
            with self.assertRaises(ValueError):
                self.harness.report(sa={**sa, **change}, human=human)

    async def test_tampered_ledger_refuses_before_oracle(self):
        await self.submit()
        raw = self.harness.ledger.path.read_text()
        self.harness.ledger.path.write_text(raw.replace('"slot":1', '"slot":0'))
        with self.assertRaises(ValueError):
            await self.submit("second")
        self.assertEqual(len(self.harness.oracles["lab-a"].backend.calls), 1)


HOST = r'''
import asyncio, sys
from sentilab_core.operations import environment_context
from sentilab_core.proposals import ProposalHarness
from sentilab_core.test_proposals import FixtureOracle, fixture_options
context = environment_context()
class BarrierOracle(FixtureOracle):
    async def evaluate(self, positions, *, stop_file):
        if (context.root / "block").exists():
            (context.root / "entered").touch()
            try:
                await asyncio.Event().wait()
            finally:
                (context.root / "cleaned").touch()
        return await super().evaluate(positions, stop_file=stop_file)
options = fixture_options(context.root, context.signer, context.public_keys, timeout=10)
options["oracle_factory"] = BarrierOracle
context.proposal_session = ProposalHarness(**options).bind("lab-a")
if sys.argv[1] == "cli":
    from sentilab_cli.__main__ import main
    sys.argv = sys.argv[1:]
    main(context=context)
else:
    from sentilab_mcp.__main__ import serve
    asyncio.run(serve(context))
'''


class ProposalTransportTests(unittest.TestCase):
    """Real processes with an injected fixture oracle, unchanged CLI/MCP paths."""
    def setUp(self):
        import base64
        import os
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        from sundai_controller.trust import key_id_for
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        prepare_registry(self.root)
        material = os.urandom(32)
        public = Ed25519PrivateKey.from_private_bytes(material).public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw).hex()
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(("SENTILAB_", "FLIGHT_SIGNING_"))}
        self.environment.update(SENTILAB_LIVE_DIR=str(self.root),
                                SENTILAB_SIGNER_FACTORY="sentilab_core.signing:service_signer",
                                FLIGHT_SIGNING_SEED_B64=base64.b64encode(material).decode(),
                                SENTILAB_VIEW_PUBLIC_KEYS=json.dumps({key_id_for(public): public}),
                                OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")

    def command(self, surface, *arguments):
        import sys
        return [sys.executable, "-c", HOST, surface, *arguments]

    def cli(self, *arguments):
        import subprocess
        return subprocess.run(self.command("cli", *arguments), env=self.environment,
                              capture_output=True, timeout=15)

    def mcp(self):
        import subprocess
        process = subprocess.Popen(self.command("mcp"), env=self.environment, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.addCleanup(self.close, process)
        return process

    @staticmethod
    def close(process):
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
        import selectors
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(10), "MCP response timeout")
            return json.loads(process.stdout.readline())

    def call(self, process, command="submit", arguments=None):
        self.send(process, {"id": 1, "method": "tools/call", "params": {
            "name": "sentilab_proposal_" + command,
            "arguments": arguments if arguments is not None else {"request_id": "first", "positions": POSITIONS}}})

    def wait_file(self, name):
        import time
        deadline = time.monotonic() + 5
        while not (self.root / name).exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue((self.root / name).exists(), name)

    def test_real_cli_mcp_signed_submit_replay_context_and_refusal_parity(self):
        process = self.mcp()
        for command, arguments, flags in (
                ("submit", {"request_id": "first", "positions": POSITIONS},
                 ["--request-id", "first", "--positions", json.dumps(POSITIONS)]),
                ("context", {}, []),
                ("submit", {"request_id": "bad", "positions": []},
                 ["--request-id", "bad", "--positions", "[]"])):
            with self.subTest(command=command, arguments=arguments):
                cli = self.cli("proposal", command, *flags)
                self.call(process, command, arguments)
                response = self.receive(process)
                if "error" in response:
                    self.assertEqual(cli.returncode, 2)
                    self.assertEqual(json.loads(cli.stdout)["error"], response["error"])
                else:
                    self.assertEqual(cli.returncode, 0, cli.stdout)
                    self.assertEqual(cli.stdout, response["result"]["content"][0]["text"].encode() + b"\n")
                    value = json.loads(cli.stdout)
                    self.assertEqual(value["status"], "evaluated" if command == "submit" else "ready")
                self.assertEqual(cli.stderr, b"")

    def test_bound_proposer_cannot_discover_or_call_operator_tools(self):
        process = self.mcp()
        self.send(process, {"id": 2, "method": "tools/list"})
        tools = self.receive(process)["result"]["tools"]
        self.assertEqual({row["name"] for row in tools}, {"sentilab_proposal_context", "sentilab_proposal_submit"})
        for tool, argv, arguments in (
                ("sentilab_live_status", ["live", "status", "--ai-off"], {"ai_off": True}),
                ("sentilab_dataset_export", ["dataset", "export", "--run-id", "fixture-run"],
                 {"run_ids": ["fixture-run"]})):
            cli = self.cli(*argv)
            self.send(process, {"id": 3, "method": "tools/call", "params": {"name": tool, "arguments": arguments}})
            mcp = self.receive(process)
            self.assertEqual(cli.returncode, 2)
            self.assertEqual(json.loads(cli.stdout)["error"], mcp["error"])
            self.assertEqual(mcp["error"]["code"], -32001)

    def test_host_scope_refusal_precedes_proposal_side_effects(self):
        self.environment["SENTILAB_CAPABILITY_SCOPES"] = "[]"
        process = self.mcp()
        cli = self.cli("proposal", "submit", "--request-id", "first", "--positions", json.dumps(POSITIONS))
        self.call(process)
        mcp = self.receive(process)
        self.assertEqual(json.loads(cli.stdout)["error"], mcp["error"])
        self.assertEqual(mcp["error"]["code"], -32001)
        self.assertNotIn("proposal.reserved", (self.root / "fixture-run.jsonl").read_text())

    def test_mcp_mid_call_stop_and_cancellation_drain_and_preserve_charge(self):
        (self.root / "block").touch()
        process = self.mcp()
        self.call(process)
        self.wait_file("entered")
        (self.root / "STOP").touch()
        receipt = json.loads(self.receive(process)["result"]["content"][0]["text"])
        self.assertEqual(receipt["status"], "stopped")
        self.wait_file("cleaned")
        (self.root / "STOP").unlink()
        (self.root / "entered").unlink()
        (self.root / "cleaned").unlink()
        self.call(process, arguments={"request_id": "second", "positions": POSITIONS})
        self.wait_file("entered")
        self.send(process, {"method": "notifications/cancelled", "params": {"requestId": 1}})
        self.assertEqual(self.receive(process)["error"]["code"], -32800)
        self.wait_file("cleaned")
        self.call(process, "context", {})
        view = json.loads(self.receive(process)["result"]["content"][0]["text"])
        self.assertEqual(view["used"], 2)
        self.assertEqual([row["status"] for row in view["feedback"]], ["stopped", "cancelled"])

    def test_cli_interrupt_releases_oracle_and_retains_signed_charge(self):
        import signal
        import subprocess
        (self.root / "block").touch()
        process = subprocess.Popen(self.command("cli", "proposal", "submit", "--request-id", "first",
                                               "--positions", json.dumps(POSITIONS)), env=self.environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.close, process)
        self.wait_file("entered")
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 130)
        self.assertEqual(json.loads(stdout)["error"]["code"], -32800)
        self.assertEqual(stderr, b"")
        self.wait_file("cleaned")
        context = json.loads(self.cli("proposal", "context").stdout)
        self.assertEqual((context["used"], context["feedback"][0]["status"]), (1, "cancelled"))

    def test_parallel_cli_and_mcp_share_durable_budget(self):
        (self.root / "block").touch()
        process = self.mcp()
        self.call(process)
        self.wait_file("entered")
        flags = ["proposal", "submit", "--request-id", "second", "--positions", json.dumps(POSITIONS)]
        refused = json.loads(self.cli(*flags).stdout)
        self.assertEqual(refused["error"]["code"], "lab_busy")
        (self.root / "STOP").touch()
        self.assertEqual(json.loads(self.receive(process)["result"]["content"][0]["text"])["status"], "stopped")
        (self.root / "STOP").unlink()
        (self.root / "block").unlink()
        self.assertEqual(json.loads(self.cli(*flags).stdout)["slot"], 2)
        self.call(process, arguments={"request_id": "third", "positions": POSITIONS})
        receipt = json.loads(self.receive(process)["result"]["content"][0]["text"])
        self.assertEqual(receipt["error"]["code"], "solve_budget")
