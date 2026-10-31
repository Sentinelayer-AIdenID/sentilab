"""Real conductor with the existing synthetic plate solver, no HotSpot required."""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import resource
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from sundai_controller.controller import thermal_plate_adapter
from sundai_controller.experiment import plate_initial_design

from sentilab_core.budget import Limits
from sentilab_core.conductor import Conductor
from sentilab_core.envelope import canonical
from sentilab_core.ledger import BrokenLedger, replay
from sentilab_core.projection import project
from sentilab_core.test_ledger import RuntimeSigner


class PlateOracle:
    """Test adapter around the shipped plate solver; no mock of the conductor."""
    initial = plate_initial_design()
    wire_cap_mm = 100.0

    async def initialize(self):
        self.solve = thermal_plate_adapter(grid_size=8)
        result = await self.solve(self.initial)
        self.problem_hash, self.solver_version = result.problem_hash, result.solver_version
        self.calls = 0
        return self

    def centers_for(self, candidate):
        candidate.check()
        return candidate.positions

    def _wirelength_mm(self, centers):
        return sum(abs(x - centers[0][0]) + abs(y - centers[0][1]) for x, y in centers)

    async def measure(self, candidate, reservation, stop_file):
        before = resource.getrusage(resource.RUSAGE_SELF)
        result = await self.solve(candidate)
        after = resource.getrusage(resource.RUSAGE_SELF)
        self.calls += 1
        return (SimpleNamespace(**asdict(result), wirelength_mm=self._wirelength_mm(candidate.positions),
                                input_sha256=()),
                {"cpu_s": max(0, after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime),
                 "process_id": "synthetic-test-execution-" + str(self.calls)})

    async def aclose(self):
        pass


class ConductorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.signer = RuntimeSigner()
        self.keys = {self.signer.key_id: self.signer.public_key}
        self.oracle = await PlateOracle().initialize()
        self.options = dict(signer=self.signer, public_keys=self.keys, oracle=self.oracle,
                            fixture="synthetic-test", limits=Limits(evals_per_run=12))
        self.conductor = Conductor(self.temp.name, **self.options)

    async def test_live_state_matches_full_contract_replay_and_survives_restart(self):
        first = await self.conductor.run(run_id="test-live", max_ticks=2, interval=0)
        self.assertEqual(first["spend"]["solves"], 4)
        self.assertIsNotNone(first["board"])
        restarted = Conductor(self.temp.name, **self.options)
        resumed = await restarted.run(run_id="test-live", max_ticks=1, interval=0)
        self.assertEqual(resumed["spend"]["solves"], 6)
        prefix = restarted.ledger.read()["prefix"]
        self.assertEqual(resumed["projection"], project(prefix))
        self.assertEqual(len({e["event"]["event_id"] for e in prefix}), len(prefix))
        self.assertTrue(all(e["event"]["body"]["ai_mode"] == "AI off" for e in prefix))
        self.assertTrue(all(e["event"]["body"]["margin_label"] == "provisional margin" for e in prefix))
        gates = [e for e in prefix if e["event"]["body"].get("to") in
                 ("accepted", "within_margin", "non_improving_current")]
        self.assertTrue(gates)
        self.assertTrue(all(e["event"]["actor_role"] == "acceptance_gate" for e in gates))

    async def test_contract_javascript_projection_equals_real_conductor_state(self):
        result = await self.conductor.run(run_id="test-contract", max_ticks=2, interval=0)
        prefix = self.conductor.ledger.read()["prefix"]
        adapter = Path(__file__).with_name("projection.mjs")
        actual = subprocess.run(["node", str(adapter)], input=canonical([e["event"] for e in prefix]),
                                capture_output=True, timeout=30, check=True)
        self.assertEqual(json.loads(actual.stdout), result["projection"])

    async def test_deleted_envelope_freezes_state_and_refuses_restart(self):
        await self.conductor.run(run_id="test-broken", max_ticks=2, interval=0)
        rows = self.conductor.ledger.path.read_bytes().splitlines(keepends=True)
        self.conductor.ledger.path.write_bytes(b"".join(rows[:5] + rows[6:]))
        state = replay(self.temp.name, "test-broken", public_keys=self.keys)
        self.assertEqual(state["last_seq"], 5)
        self.assertEqual(project(state["prefix"]), project([json.loads(row) for row in rows[:5]]))
        with self.assertRaises(BrokenLedger):
            Conductor(self.temp.name, **self.options).open_run("test-broken")

    async def test_stop_and_crashed_reservation_never_repeat_a_solve(self):
        self.conductor.open_run("test-stop")
        self.conductor.budget.stop_file.touch()
        result = await self.conductor.run(run_id="test-stop", max_ticks=1)
        self.assertEqual(self.oracle.calls, 0)
        self.assertEqual(result["status"], "stopped")
        self.conductor.budget.stop_file.unlink()
        other = Conductor(self.temp.name, **self.options)
        other.open_run("test-crash")
        with other.budget.reserve("test-crash", "test-crash:candidate-0:evaluate"):
            pass
        result = await other.run(run_id="test-crash", max_ticks=1, interval=0)
        self.assertEqual(self.oracle.calls, 0)
        self.assertEqual(result["spend"]["solves"], 1)
        self.assertEqual(result["projection"]["nodes"]["test-crash:candidate-0"]["lifecycle"], "failed_run")


if __name__ == "__main__":
    unittest.main()
