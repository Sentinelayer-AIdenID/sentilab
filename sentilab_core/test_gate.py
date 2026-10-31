"""Drive the shipped pure admission rule with explicit recorded inputs."""
import copy
import unittest

from sentilab_core.gate import AcceptanceGate


class GateTests(unittest.TestCase):
    def setUp(self):
        self.gate = AcceptanceGate(margin=0.32, reproduction_tolerance=0.001)
        self.binding = dict(candidate_id="candidate", task_id="task", fixture_id="ascend910",
                            metric_id="peak-chip-c", scenario_id="nominal", solver_id="hotspot")
        self.evaluation = dict(binding=self.binding, j=70.0, wire_mm=20.0,
                               process_id="first", success=True)
        self.reproduction = {**self.evaluation, "process_id": "fresh"}
        self.inputs = dict(geometry_valid=True, wire_cap_mm=25.0, evaluation=self.evaluation,
                           reproduction=self.reproduction, current={"j": 71.0, "candidate_id": "old"},
                           binding=self.binding, stopped=False)

    def test_accept_nonimproving_tie_and_margin(self):
        for current, expected in ((71, "accepted"), (69, "non_improving_current"),
                                  (70, "non_improving_current"), (70.1, "within_margin"),
                                  (70.32, "within_margin")):
            with self.subTest(current=current):
                self.inputs["current"]["j"] = current
                outcome = self.gate.decide(**self.inputs)
                self.assertEqual(outcome["outcome"], expected)
                self.assertEqual(outcome["margin_label"], "provisional margin")
                self.assertEqual(outcome["reproduction_label"], "same-solver reproduction")
        self.inputs["current"] = None
        self.assertEqual(self.gate.decide(**self.inputs)["outcome"], "accepted")

    def test_geometry_cap_reproduction_binding_and_stop_fail_closed(self):
        cases = [("geometry_valid", False, "invalid_geometry"),
                 ("wire_cap_mm", 19, "wire_cap_exceeded"),
                 ("reproduction", None, "reproduction_failed"),
                 ("stopped", True, "stopped")]
        for field, value, reason in cases:
            with self.subTest(field=field):
                args = {**self.inputs, field: value}
                self.assertEqual(self.gate.decide(**args)["outcome"], reason)
        for field in self.binding:
            with self.subTest(binding=field):
                args = copy.deepcopy(self.inputs)
                args["reproduction"]["binding"] = {**self.binding, field: "wrong"}
                self.assertEqual(self.gate.decide(**args)["outcome"], "binding_mismatch")
        for patch, reason in (({"process_id": "first"}, "fresh_process_required"),
                              ({"j": 70.01}, "reproduction_mismatch"),
                              ({"success": False}, "reproduction_failed")):
            args = {**self.inputs, "reproduction": {**self.reproduction, **patch}}
            self.assertEqual(self.gate.decide(**args)["outcome"], reason)

    def test_nonfinite_bool_negative_and_impure_inputs(self):
        before = copy.deepcopy(self.inputs)
        self.assertEqual(self.gate.decide(**self.inputs), self.gate.decide(**self.inputs))
        self.assertEqual(before, self.inputs)
        for value in (float("nan"), float("inf"), True, "70"):
            for field in ("j", "wire_mm"):
                with self.subTest(value=value, field=field):
                    args = {**self.inputs, "evaluation": {**self.evaluation, field: value}}
                    self.assertEqual(self.gate.decide(**args)["outcome"], "evaluation_failed")
        for value in (-1, float("nan"), True):
            with self.assertRaises(ValueError):
                AcceptanceGate(margin=value)


if __name__ == "__main__":
    unittest.main()
