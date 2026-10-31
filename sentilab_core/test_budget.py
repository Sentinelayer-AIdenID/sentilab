import tempfile
import unittest

from sentilab_core.budget import Budget, BudgetHalt, Limits


class BudgetTests(unittest.TestCase):
    def make(self, **kwargs):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Budget(directory.name, Limits(**kwargs), clock=lambda: 100)

    def spend(self, budget, run="r", operation="op"):
        with budget.reserve(run, operation):
            budget.settle(operation, actual_cpu_s=0.01, success=True)

    def test_each_solve_and_cpu_limit_is_enforced_before_work(self):
        for settings, second_run, expected in (
                ({"evals_per_hour": 1}, "other", "hour solve limit"),
                ({"evals_per_run": 1}, "r", "run solve limit"),
                ({"total_evals": 1}, "other", "total solve limit"),
                ({"cpu_seconds_per_hour": 15}, "other", "hour CPU limit"),
                ({"total_cpu_seconds": 15}, "other", "total CPU limit")):
            with self.subTest(settings=settings):
                budget = self.make(**settings)
                self.spend(budget)
                with self.assertRaisesRegex(BudgetHalt, expected), budget.reserve(second_run, "second"):
                    self.fail("budget admitted work")
                self.assertEqual(budget.snapshot()["solves"], 1)

    def test_stop_deadline_concurrency_and_rollback_clock(self):
        budget = self.make()
        with budget.reserve("r", "one"):
            with self.assertRaisesRegex(BudgetHalt, "concurrent solve"), budget.reserve("r", "two"):
                self.fail("second solve admitted")
        budget.stop_file.touch()
        with self.assertRaisesRegex(BudgetHalt, "STOP"), budget.reserve("r", "stop"):
            self.fail("STOP ignored")
        budget.stop_file.unlink()
        budget.deadline = 105
        with self.assertRaisesRegex(BudgetHalt, "deadline"), budget.reserve("r", "late"):
            self.fail("deadline ignored")
        budget.deadline = None
        budget.clock = lambda: 99
        with self.assertRaisesRegex(BudgetHalt, "clock"), budget.reserve("r", "backwards"):
            self.fail("clock rollback admitted")

    def test_failure_crash_and_restart_cannot_refund_or_repeat(self):
        budget = self.make(evals_per_run=2)
        with self.assertRaisesRegex(RuntimeError, "crash"), budget.reserve("r", "crashed"):
            raise RuntimeError("crash")
        again = Budget(budget.root, budget.limits, clock=lambda: 100)
        self.assertEqual(again.snapshot(), {"solves": 1, "cpu_charged_s": 15,
                                           "cpu_actual_s": 0, "cpu_unmeasured": 1, "unsettled": 1})
        with self.assertRaisesRegex(BudgetHalt, "already reserved"), again.reserve("r", "crashed"):
            self.fail("crashed solve repeated")
        with again.reserve("r", "failed"):
            again.settle("failed", actual_cpu_s=0.03, success=False)
        self.assertEqual(again.snapshot()["cpu_charged_s"], 30)
        with self.assertRaisesRegex(BudgetHalt, "run solve limit"), again.reserve("r", "third"):
            self.fail("failure refunded")

    def test_hour_window_and_new_run_keep_global_spend(self):
        budget = self.make(evals_per_hour=1, evals_per_run=1)
        self.spend(budget)
        budget.clock = lambda: 3700
        with self.assertRaisesRegex(BudgetHalt, "hour solve limit"), budget.reserve("new", "two"):
            self.fail("inflight portion aged out too early")
        budget.clock = lambda: 3716
        self.spend(budget, "new", "two")
        self.assertEqual(budget.snapshot()["solves"], 2)
        self.assertEqual(budget.snapshot("new")["solves"], 1)

    def test_limits_cannot_be_widened_and_policy_is_pinned(self):
        for field, value in (("evals_per_hour", 601), ("evals_per_run", 201), ("total_evals", 2001),
                             ("cpu_seconds_per_hour", 601), ("total_cpu_seconds", 1801),
                             ("total_evals", True), ("solve_cpu_seconds", float("nan"))):
            with self.subTest(field=field), self.assertRaises(ValueError):
                Limits(**{field: value})
        budget = self.make(evals_per_run=2)
        with self.assertRaisesRegex(ValueError, "immutable"):
            Budget(budget.root, Limits(), clock=lambda: 100)


if __name__ == "__main__":
    unittest.main()
