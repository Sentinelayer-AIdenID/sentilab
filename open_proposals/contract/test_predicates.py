"""Test T13, predicates and screen (DESIGN.md 4.6-4.10): every hand-written predicate fixture through evaluation,
suppression and diagnostics; no claim from missing values; no "bounded" mode without the bounds a label reads.

    python -m unittest -q open_proposals.contract.test_predicates
"""
from __future__ import annotations

import unittest

from . import predicate_fixtures as fx
from .predicates import BOUNDED, LABELS, MODES, PASSES, apply_suppression, evaluate_labels, record_diagnostic

INPUTS = ("policy", "bounds", "admission", "screen", "values")
# The labels that read each bound: u_abs bounds T_M(c); u_T and u_q bound delta and q.
READERS = {"u_abs": {fx.TARGET}, "u_T": set(fx.LABELS) - {fx.TARGET}, "u_q": set(fx.LABELS) - {fx.TARGET}}


def evaluate(case: dict, **override) -> list:
    return evaluate_labels(**{key: override.get(key, case[key]) for key in INPUTS})


class Predicates(unittest.TestCase):
    def test_vocabulary(self):
        self.assertEqual(LABELS, fx.LABELS)
        self.assertEqual(MODES, ("bounded", "passes the listed sensitivity cases", "INCOMPLETE", "INCONCLUSIVE",
                                 "UNKNOWN"))

    def test_fixtures_hold_each_label_both_ways(self):
        names = [case["name"] for case in fx.cases()]
        self.assertEqual(len(names), len(set(names)))
        claimed, omitted = set(), set()
        for case in fx.cases():
            claimed |= {label["id"] for label in case["expect"] if label["mode"] in (BOUNDED, PASSES)}
            omitted |= set(fx.LABELS) - {label["id"] for label in case["expect"]}
        self.assertEqual((claimed, omitted), (set(fx.LABELS), set(fx.LABELS)))

    def test_fixtures(self):
        for case in fx.cases():
            with self.subTest(case["name"]):
                labels = evaluate(case)
                self.assertEqual(labels, case["expect"])
                suppressed = case.get("expect_suppressed", [])
                gone = {item["id"] for item in suppressed}
                self.assertEqual(apply_suppression(labels, case.get("failures", [])),
                                 ([label for label in case["expect"] if label["id"] not in gone], suppressed))
                diagnostic = case.get("diagnostic", fx.UNEXPECTED)
                self.assertEqual(record_diagnostic(labels, diagnostic["hypothesis"], diagnostic["observed"]),
                                 (case["expect"], diagnostic))

    def test_no_label_is_claimed_when_every_value_is_missing(self):
        """Missing is never zero: with nothing measured each label is INCOMPLETE or UNKNOWN, never a claim."""
        ids = [scenario["id"] for scenario in fx.SCREEN]
        blank = {"status": "observed", "T_c": "UNKNOWN", "T_R": "UNKNOWN", "W_c": "UNKNOWN", "W_R": "UNKNOWN"}
        for values, mode in (({}, "INCOMPLETE"), (dict.fromkeys(ids, {"status": "missing"}), "INCOMPLETE"),
                             (dict.fromkeys(ids, {"status": "observed"}), "UNKNOWN"),
                             (dict.fromkeys(ids, blank), "UNKNOWN")):
            with self.subTest(values=values):
                labels = evaluate_labels(policy=fx.POLICY, bounds=fx.BOUNDS, admission=True, screen=fx.SCREEN,
                                         values=values)
                self.assertEqual([(label["id"], label["mode"]) for label in labels],
                                 [(label, mode) for label in fx.LABELS])

    def test_no_bounded_mode_while_a_bound_it_reads_is_unknown(self):
        cases = fx.cases()
        bounded = {label["id"] for case in cases for label in evaluate(case, bounds=fx.BOUNDS)
                   if label["mode"] == BOUNDED}
        self.assertEqual(bounded, set(fx.LABELS))  # the control: with every bound known, each label can be bounded
        for case in cases:
            for bound, readers in READERS.items():
                with self.subTest(case["name"], unknown=bound):
                    labels = evaluate(case, bounds=fx.BOUNDS | {bound: "UNKNOWN"})
                    self.assertEqual([label["id"] for label in labels
                                      if label["id"] in readers and label["mode"] == BOUNDED], [])

    def test_malformed_inputs_are_refused(self):
        with self.assertRaises(ValueError):  # no nominal scenario, so never a pass on an empty screen
            evaluate_labels(policy=fx.POLICY, bounds=fx.NO_BOUNDS, admission=True, screen=[], values={})
        with self.assertRaises(ValueError):
            apply_suppression(fx.shown(fx.TARGET), [{"by": "failed gate-zero", "label": None}])

    def test_an_empty_hypothesis_matches_nothing(self):
        self.assertEqual(record_diagnostic([], {}, {}), ([], {"hypothesis": {}, "observed": {}, "matched": False}))


if __name__ == "__main__":
    unittest.main()
