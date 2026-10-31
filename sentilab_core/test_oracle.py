"""Real HotSpot reproduction plus synthetic process-group cleanup coverage."""
import asyncio
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core.budget import Budget, Limits
from sentilab_core.oracle import FreshProcessOracle


class FreshLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_lease_keeps_reservation_requirement_and_default(self):
        oracle = FreshProcessOracle(grid=16)
        for options in ({}, {"immediate_kill": False}, {"immediate_kill": True}):
            with self.subTest(options=options):
                with self.assertRaisesRegex(RuntimeError, "durable budget reservation"):
                    async with oracle.lease(**options):
                        self.fail("unreserved worker lease admitted")
                with tempfile.TemporaryDirectory() as root:
                    budget = Budget(root, Limits(evals_per_run=1))
                    with budget.reserve("lease-test", "lease") as reservation:
                        oracle.reservation = reservation
                        try:
                            async with oracle.lease(**options) as worker:
                                self.assertIs(worker, oracle)
                        finally:
                            oracle.reservation = None

    async def test_bounded_fresh_call_immediately_kills_worker_group(self):
        # Replace only the executable at the OS boundary: request construction,
        # lease, transport, cancellation and cleanup run through the real oracle.
        script = """
import os, signal, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = os.fork()
if child == 0:
    Path(sys.argv[1]).write_text(str(os.getpid()))
    while True:
        time.sleep(1)
os.waitpid(child, 0)
"""
        spawn = asyncio.create_subprocess_exec
        killpg = os.killpg
        processes = []
        with tempfile.TemporaryDirectory() as root:
            ready = Path(root) / "child.pid"
            budget = Budget(root, Limits(evals_per_run=1))
            oracle = FreshProcessOracle(grid=16)

            async def spawn_synthetic(*args, **kwargs):
                process = await spawn(sys.executable, "-c", script, str(ready), **kwargs)
                processes.append(process)
                return process

            with budget.reserve("lease-test", "bounded") as reservation:
                oracle.reservation = reservation
                with patch("sentilab_core.oracle.asyncio.create_subprocess_exec", side_effect=spawn_synthetic), \
                        patch("sentilab_core.oracle.os.killpg", wraps=killpg) as signals:
                    task = asyncio.create_task(oracle(oracle.initial, timeout_s=0.1))
                    try:
                        async with asyncio.timeout(5):
                            while not ready.exists():
                                if task.done():
                                    await task
                                await asyncio.sleep(0.01)
                        child_pid = int(ready.read_text())
                        with self.assertRaises(TimeoutError):
                            await asyncio.wait_for(task, 0.05)
                        self.assertEqual(len(processes), 1)
                        signals.assert_called_once_with(processes[0].pid, signal.SIGKILL)
                        self.assertEqual(processes[0].returncode, -signal.SIGKILL)
                        async with asyncio.timeout(5):
                            while True:
                                try:
                                    state = Path(f"/proc/{child_pid}/stat").read_text().split(")", 1)[1].split()[0]
                                except FileNotFoundError:
                                    break
                                if state == "Z":
                                    break
                                await asyncio.sleep(0.01)
                        self.assertIsNone(oracle.last_usage)
                    finally:
                        task.cancel()
                        for process in processes:
                            try:
                                killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            await process.wait()
                        await asyncio.gather(task, return_exceptions=True)
                        oracle.reservation = None


class FreshOracleTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_fresh_process_reproduction_is_bound_and_metered(self):
        with tempfile.TemporaryDirectory() as root:
            budget = Budget(root, Limits(evals_per_run=2))
            oracle = FreshProcessOracle(grid=16)
            results, usages = [], []
            for operation in ("evaluate", "reproduce"):
                with budget.reserve("oracle-test", operation) as reservation:
                    result, usage = await oracle.measure(oracle.initial, reservation, budget.stop_file)
                    budget.settle(operation, actual_cpu_s=usage["cpu_s"], success=True)
                    results.append(result)
                    usages.append(usage)
            self.assertEqual(results[0].candidate_hash, oracle.initial.hash)
            self.assertEqual(results[0].problem_hash, oracle.problem_hash)
            self.assertAlmostEqual(results[0].maximum_temperature_c, 118.36, places=2)
            self.assertEqual(results[0].maximum_temperature_c, results[1].maximum_temperature_c)
            self.assertNotEqual(usages[0]["process_id"].split(":")[0], usages[1]["process_id"].split(":")[0])
            self.assertTrue(all(0 < usage["cpu_s"] < 15 for usage in usages))
            self.assertEqual(budget.snapshot()["solves"], 2)


if __name__ == "__main__":
    unittest.main()
