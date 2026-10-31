"""TFL-09-min run service: start, one-run lock, persisted result, list, restart recovery, input validation.

Runs the real run_four_lanes with a fast nonphysical oracle; the HotSpot and plate oracles are covered elsewhere."""
import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from app import runs
from sundai_controller.controller import Chiplet, Design, FlightRecord, ThermalResult


class SlowOracle:
    async def __call__(self, candidate):
        await asyncio.sleep(0.02)
        return ThermalResult(candidate.hash, float(sum(x + y for x, y in candidate.positions)),
                             "NONPHYSICAL-tfl09-test", problem_hash="one-problem")


def fake_oracle(benchmark, grid):
    return Design(20, 10, 1, (Chiplet("a", 2, 2), Chiplet("b", 2, 2)), ((4, 1), (12, 1))), SlowOracle()


class RunServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["RUNS_DIR"] = self.tmp.name
        self.real_oracle, runs._oracle = runs._oracle, fake_oracle

    def tearDown(self):
        if not runs._busy.acquire(timeout=30):  # let any run a test started finish before the next test
            self.fail("a run was still holding the lock")
        runs._busy.release()
        runs._oracle = self.real_oracle
        os.environ.pop("RUNS_DIR", None)
        self.tmp.cleanup()

    def wait(self, run_id, timeout=30.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            run = json.loads(runs.get(run_id))
            if run["status"] != "running":
                return run
            time.sleep(0.05)
        self.fail("run did not finish")

    def test_run_completes_with_verifiable_equal_budget_lanes_and_holds_the_lock_meanwhile(self):
        started = runs.start({"benchmark": "plate", "grid": 16, "seed": 3, "proposals": 3})
        self.assertEqual(started["status"], "running")
        self.assertIsNone(runs.start({"benchmark": "plate"}), "a second run must be refused while one runs")
        run = self.wait(started["id"])
        self.assertEqual(run["status"], "done", run.get("error"))
        result = run["result"]
        self.assertTrue(result["flight_records_valid"])
        self.assertTrue(result["evaluation_counts_equal"])
        self.assertEqual(len(result["lane_results"]), 4)
        for lane in result["lane_results"].values():
            self.assertEqual(lane["evaluation_count"], 3)
            self.assertTrue(FlightRecord.verify(lane["record"], lane["record_public_key"]),
                            "the stored record must verify after a JSON round trip")
        again = runs.start({"benchmark": "plate", "proposals": 1})
        self.assertIsNotNone(again, "the lock is released after a run")
        self.assertEqual(self.wait(again["id"])["status"], "done")
        listed = runs.recent()
        self.assertIn(started["id"], {r["id"] for r in listed})
        best = next(r for r in listed if r["id"] == started["id"])["best"]
        self.assertEqual(best["best_temperature_c"],
                         min(lane["best_temperature_c"] for lane in result["lane_results"].values()))

    def test_a_failed_oracle_is_recorded_and_releases_the_lock(self):
        async def broken(candidate):
            raise RuntimeError("simulator crashed")
        runs._oracle = lambda benchmark, grid: (fake_oracle(benchmark, grid)[0], broken)
        run = self.wait(runs.start({"benchmark": "plate"})["id"])
        self.assertEqual(run["status"], "failed")
        self.assertIn("simulator crashed", run["error"])
        runs._oracle = fake_oracle
        again = runs.start({"benchmark": "plate", "proposals": 1})
        self.assertIsNotNone(again, "a failed run must release the lock")
        self.assertEqual(self.wait(again["id"])["status"], "done")

    def test_runs_in_flight_at_restart_are_marked_interrupted(self):
        stale = {"id": "a" * 32, "status": "running", "result": None}
        Path(self.tmp.name, f"{stale['id']}.json").write_text(json.dumps(stale), encoding="utf-8")
        runs.recover()
        self.assertEqual(json.loads(runs.get(stale["id"]))["status"], "interrupted")

    def test_live_signal_mode_routes_only_the_signal_lane_and_signs_the_advice(self):
        seen = []

        async def router(state):
            seen.append(state["evaluations_remaining"])
            return ("swap", "test advice")
        real_router, runs._signal_router = runs._signal_router, lambda run: router if run["signal"] == "live" else None
        try:
            run = self.wait(runs.start({"benchmark": "plate", "proposals": 3, "signal": "live"})["id"])
        finally:
            runs._signal_router = real_router
        self.assertEqual(run["status"], "done", run.get("error"))
        self.assertEqual(run["signal"], "live")
        self.assertEqual(len(seen), 3, "one router call per signal-lane proposal")
        lanes = run["result"]["lane_results"]
        signal_events = [e["payload"] for e in lanes["signal_portfolio"]["record"] if e["event"] == "signal_decision"]
        self.assertEqual([p["applied_operator"] for p in signal_events], ["swap"] * 3)
        for lane_id in ("random", "simulated_annealing", "ucb1"):
            self.assertFalse(any(e["event"] == "signal_decision" for e in lanes[lane_id]["record"]))
        self.assertTrue(run["result"]["flight_records_valid"])

    def test_local_signal_mode_is_the_default_and_builds_no_router(self):
        self.assertEqual(runs.validate({})["signal"], "local")
        self.assertIsNone(runs._signal_router({"signal": "local", "proposals": 4}))
        live = runs._signal_router({"signal": "live", "proposals": 4})
        self.assertEqual((live.max_calls, live.timeout_s), (4, float(runs.SIGNAL_TIMEOUT_S)))

    def test_rejects_bad_requests_and_unsafe_ids(self):
        for body in ({"signal": "turbo"}, {"signal": True}, {"benchmark": "moon"}, {"grid": 64}, {"grid": "16"}, {"seed": True}, {"proposals": 0},
                     {"proposals": 9}, {"seed": -1}, [1]):
            with self.assertRaises(ValueError, msg=repr(body)):
                runs.validate(body)
        for run_id in ("../../etc/passwd", "a" * 31, "A" * 32, "", "a" * 32 + "/"):
            self.assertIsNone(runs.get(run_id), run_id)


if __name__ == "__main__":
    unittest.main()
