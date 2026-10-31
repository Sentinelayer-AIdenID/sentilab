"""Two real bounded HotSpot solves; the container gate builds the solver first."""
import tempfile
import unittest

from sentilab_core.budget import Budget, Limits
from sentilab_core.oracle import FreshProcessOracle


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
