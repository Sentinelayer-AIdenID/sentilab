"""Synthetic ledger inputs only: no solver, model, or outcome artifacts."""
import copy
from dataclasses import replace
import itertools
import json
from pathlib import Path
import unittest

from sentilab_core.freeze import (Candidate, Attempt, Reference, nominate,
                                  eligible_for_reproduction, rank_order_gate,
                                  reproduction_slots, replay_epoch,
                                  validate_freeze, require_execution_ready,
                                  sign_test, holm)

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "docs/sentilab/freeze/slab041-freeze.json"
CONTEXT = "synthetic-family-seed-arm-epoch"


def candidate(name, j, lab="lab-a", arm="B3", valid=True, uncertainty=0):
    return Candidate(name, lab, arm, j, "eval-" + lab + "-" + name, valid,
                     uncertainty, CONTEXT, "measurement-" + name)


def attempt(name="a", j=8, lab="lab-a", number=0, status="success",
            execution="started", uncertainty=0):
    return Attempt(lab, 0, name, number, status, j, execution, uncertainty,
                   CONTEXT, "reproduction-" + name if status == "success" else None)


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.freeze = json.loads(FREEZE.read_text())
        # Explicit synthetic test values, never defaults or a benchmark release.
        self.freeze["parameters"].update(acceptance_margin=1, reproduction_tolerance=0.2,
                                         sharing_tolerance=0.1)
        self.reference = Reference(10, 0, CONTEXT)
        self.labs = ("lab-a", "lab-b", "lab-c", "lab-d")

    def nominate(self, rows, arm="B3", reference=None):
        return nominate(rows, arm, reference or self.reference, freeze=self.freeze)

    def gate(self, rows, reference=None):
        return rank_order_gate(rows, reference or self.reference, 1, freeze=self.freeze)

    def replay(self, rows, attempts, **kwargs):
        return replay_epoch(rows, attempts, "B3", self.reference, freeze=self.freeze,
                            labs=self.labs, search_complete=True,
                            search_charges=kwargs.pop("search_charges", dict.fromkeys(self.labs, 7)), **kwargs)

    def test_manifest_schema_and_document_agree(self):
        frozen = json.loads(FREEZE.read_text())
        validate_freeze(frozen)
        doc = FREEZE.with_name("SLAB-041-FREEZE.md").read_text()
        self.assertEqual(json.loads(doc.split("```json\n")[1].split("```", 1)[0]), frozen)
        self.assertIn("8 of 8", doc)
        self.assertIn("six-n endpoint", doc)
        for arm, row in frozen["arms"].items():
            self.assertEqual(row["labs"] * (row["search_per_lab"] + row["reproduction_per_lab"]), 32)
            self.assertIn(arm, doc)
        for change in (lambda f: f["arms"]["B2"].update(search_per_lab=8),
                       lambda f: f["families"].update(target=6),
                       lambda f: f["pins"].pop("scenario_manifest")):
            bad = copy.deepcopy(frozen)
            change(bad)
            with self.assertRaises(ValueError):
                validate_freeze(bad)

    def test_unknown_parameters_block_execution_and_nomination(self):
        frozen = json.loads(FREEZE.read_text())
        with self.assertRaisesRegex(ValueError, "must-fill-before-execution"):
            require_execution_ready(frozen)
        with self.assertRaises(ValueError):
            nominate([], "B3", self.reference, freeze=frozen)
        with self.assertRaises(ValueError):
            eligible_for_reproduction(candidate("a", 2), self.reference, None)
        frozen["status"] = "released"
        with self.assertRaises(ValueError):
            require_execution_ready(frozen)

    def test_exact_comparator_is_total_transitive_and_shuffle_invariant(self):
        # Warden #56377: a fuzzy comparator with tolerance 1 cycles on these.
        rows = [candidate("c", 100, arm="B0"), candidate("b", 100.75, arm="B0"),
                candidate("a", 101.5, arm="B0")]
        for shuffled in itertools.permutations(rows):
            result = self.nominate(shuffled, "B0", Reference(110, 0, CONTEXT))
            self.assertEqual(result, tuple(rows))
            for left, right in itertools.combinations(result, 2):
                self.assertLess(left.j, right.j)

    def test_only_exact_j_ties_use_physical_hash_not_lab_order(self):
        rows = [candidate("z", 8, arm="B0"), candidate("a", 8, arm="B0"),
                candidate("0", 8.01, arm="B0")]
        for shuffled in itertools.permutations(rows):
            self.assertEqual(self.nominate(shuffled, "B0"), (rows[1], rows[0], rows[2]))

    def test_eligibility_precedes_nomination_with_uncertainty(self):
        rows = [candidate("a", 97, uncertainty=3), candidate("b", 97.5, uncertainty=0.1)]
        self.assertEqual(self.nominate(rows, reference=Reference(100, 0, CONTEXT)), (rows[1],))
        self.assertFalse(eligible_for_reproduction(rows[1], Reference(100, 2, CONTEXT), 1))

    def test_each_lab_nominates_and_duplicate_layouts_keep_both_slots(self):
        rows = [candidate("same", 8), candidate("other", 8.5),
                candidate("same", 8, "lab-b"), candidate("last", 8.7, "lab-b")]
        self.assertEqual(self.nominate(rows), (rows[0], rows[2]))

    def test_one_authoritative_measurement_per_physical_layout_and_context(self):
        rows = [candidate("same", 8), candidate("same", 7, "lab-b")]
        with self.assertRaisesRegex(ValueError, "authoritative"):
            self.nominate(rows)
        rows[1] = replace(rows[1], j=8, measurement_id="different-authority")
        with self.assertRaises(ValueError):
            self.nominate(rows)
        with self.assertRaises(ValueError):
            self.nominate([replace(rows[0], context="another-arm-context")])

    def test_b0_b1_top_four_distinct_eligible_layouts(self):
        for arm in ("B0", "B1"):
            rows = [candidate(str(i), i, arm=arm) for i in range(6)]
            rows += [replace(rows[0], evaluation_id="another-proposal"),
                     candidate("ineligible", -10, arm=arm, uncertainty=100),
                     candidate("foreign", -10)]
            self.assertEqual([c.candidate_hash for c in self.nominate(rows, arm)], ["0", "1", "2", "3"])

    def test_invalid_candidates_and_nonfinite_values_fail_closed(self):
        self.assertEqual(self.nominate([candidate("bad", 0, valid=False)]), ())
        for value in (float("nan"), float("inf"), True, "1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.nominate([candidate("a", value)])
        with self.assertRaises(ValueError):
            self.nominate([], "unknown")
        with self.assertRaises(ValueError):
            self.nominate([candidate("a", 1, uncertainty=-1)])

    def test_exact_margin_is_inclusive_but_nonimproving_and_invalid_are_not_eligible(self):
        self.assertTrue(eligible_for_reproduction(candidate("a", 9), self.reference, 1))
        self.assertTrue(eligible_for_reproduction(candidate("a", 8.9), self.reference, 1))
        self.assertFalse(eligible_for_reproduction(candidate("a", 10), self.reference, 0))
        self.assertFalse(eligible_for_reproduction(candidate("a", 0, valid=False), self.reference, 1))
        self.assertTrue(eligible_for_reproduction(candidate("a", 8, uncertainty=1), self.reference, 1))

    def test_rank_uses_best_once_and_retains_valid_losers(self):
        rows = [candidate("a", 98), candidate("b", 97.5, "lab-b")]
        for shuffled in itertools.permutations(rows):
            result = self.gate(shuffled, Reference(100, 0, CONTEXT))
            self.assertEqual(result["board"], rows[1])
            self.assertEqual([r["outcome"] for r in result["decisions"]],
                             ["accepted", "non_improving_current"])

    def test_rank_margin_boundary_and_qualified_winner(self):
        result = self.gate([candidate("a", 9.1), candidate("b", 10)])
        self.assertEqual(result["board"], self.reference)
        self.assertEqual([r["outcome"] for r in result["decisions"]],
                         ["within_margin", "non_improving_current"])
        boundary = self.gate([candidate("a", 9)])
        self.assertEqual(boundary["decisions"][0]["outcome"], "accepted")
        rows = [candidate("a", 7, uncertainty=3), candidate("z", 8)]
        result = self.gate(rows)
        self.assertEqual(result["board"], rows[1])
        self.assertEqual(result["decisions"][1]["outcome"], "within_margin")

    def test_rank_cannot_override_or_bypass_frozen_margin(self):
        rows = [candidate("a", 9.5)]
        for margin in (0, 2):
            with self.subTest(margin=margin), self.assertRaisesRegex(ValueError, "frozen acceptance_margin"):
                rank_order_gate(rows, self.reference, margin, freeze=self.freeze)
        result = rank_order_gate(rows, self.reference, 1, freeze=self.freeze)
        self.assertEqual(result["board"], self.reference)
        self.assertEqual(result["decisions"][0]["outcome"], "within_margin")
        self.freeze["parameters"]["acceptance_margin"] = None
        with self.assertRaises(ValueError):
            rank_order_gate(rows, self.reference, 0, freeze=self.freeze)

    def test_reproduced_j_can_reverse_search_order(self):
        rows = [candidate("a", 8), candidate("b", 8.1, "lab-b")]
        result = self.replay(rows, [attempt("a", 8.2), attempt("b", 7.95, "lab-b")])
        self.assertEqual(result["gate"]["board"].candidate_hash, "b")
        self.assertEqual(result["gate"]["board"].j, 7.95)

    def test_slots_preserve_duplicates_and_unused_without_transfer(self):
        rows = [candidate("same", 8), candidate("same", 8, "lab-b")]
        slots = reproduction_slots(rows, "B3", self.reference, freeze=self.freeze,
                                   labs=tuple(reversed(self.labs)), search_complete=True)
        self.assertEqual([s["status"] for s in slots], ["nominated", "nominated", "unused", "unused"])
        self.assertEqual([s["candidate"].candidate_hash for s in slots[:2]], ["same", "same"])
        self.assertEqual(sum(s["reserved_bundles"] for s in slots), 4)

    def test_search_barrier_complete_roster_and_context_required(self):
        for kwargs in ({"search_complete": False, "labs": self.labs},
                       {"search_complete": True, "labs": self.labs[:3]}):
            with self.assertRaises(ValueError):
                reproduction_slots([], "B3", self.reference, freeze=self.freeze, **kwargs)
        with self.assertRaises(ValueError):
            self.replay([candidate("a", 8)], [replace(attempt(), context="wrong-context")])

    def test_duplicate_reproductions_both_spend_and_ledger_replays(self):
        rows = [candidate("same", 8), candidate("same", 8, "lab-b")]
        attempts = [attempt("same", 8), attempt("same", 8, "lab-b")]
        expected = self.replay(rows, attempts)
        self.assertEqual(expected["reproduction_bundles_spent"], 2)
        self.assertEqual(expected["unused_reproduction_bundles"], 2)
        self.assertEqual(len(expected["gate"]["decisions"]), 2)
        self.assertIsNone(expected["best_evaluated_unreproduced"])
        for cs in itertools.permutations(rows):
            for rs in itertools.permutations(attempts):
                self.assertEqual(self.replay(cs, rs), expected)
        with self.assertRaises(ValueError):
            self.replay(rows, [attempts[0], replace(attempts[1], j=8.1)])

    def test_proven_preexecution_failure_has_one_free_retry(self):
        first = attempt(j=None, status="infrastructure_failure", execution="not_started")
        retry = attempt(number=1)
        result = self.replay([candidate("a", 8)], [retry, first])
        self.assertEqual(result["physical_attempts"], 2)
        self.assertEqual(result["reproduction_bundles_spent"], 1)
        self.assertEqual(result["charged_by_lab"]["lab-a"], 8)
        with self.assertRaises(ValueError):
            self.replay([candidate("a", 8)], [first, retry, attempt(number=2)])
        with self.assertRaises(ValueError):
            self.replay([candidate("a", 8)], [first, replace(first, attempt=1), attempt(number=2)])
        with self.assertRaises(ValueError):
            self.replay([candidate("a", 8)], [first, attempt(number=0)])
        with self.assertRaises(ValueError):
            self.replay([candidate("a", 8)], [first, attempt("substitute", number=1)])

    def test_uncertain_or_started_launch_consumes_slot_no_retry(self):
        for execution in ("unknown", "started"):
            first = attempt(j=None, status="infrastructure_failure", execution=execution)
            result = self.replay([candidate("a", 8)], [first])
            self.assertEqual(result["charged_by_lab"]["lab-a"], 8)
            self.assertFalse(result["complete"])
            with self.assertRaises(ValueError):
                self.replay([candidate("a", 8)], [first, attempt(number=1)])

    def test_exhausted_preexecution_retry_is_inconclusive_and_keeps_reservation(self):
        first = attempt(j=None, status="infrastructure_failure", execution="not_started")
        retry = replace(first, attempt=1)
        result = self.replay([candidate("a", 8)], [retry, first])
        self.assertFalse(result["complete"])
        self.assertEqual(result["slots"][0]["status"], "inconclusive")
        self.assertEqual(result["slots"][0]["reserved_bundles"], 1)
        self.assertEqual(result["unused_reproduction_bundles"], 3)
        self.assertEqual(result["physical_attempts"], 2)
        self.assertEqual(result["reproduction_bundles_spent"], 0)
        self.assertEqual(result["charged_by_lab"]["lab-a"], 7)
        self.assertEqual(result["gate"]["board"], self.reference)
        self.assertEqual(result["best_evaluated_unreproduced"], candidate("a", 8))
        with self.assertRaises(ValueError):
            self.replay([candidate("a", 8)], [first, retry, attempt(number=2)])

    def test_no_lab_exceeds_eight_including_cache_and_retry(self):
        for bad in (8, -1, True, None):
            with self.assertRaises(ValueError):
                self.replay([candidate("a", 8)], [attempt()],
                            search_charges={**dict.fromkeys(self.labs, 7), "lab-a": bad})
        # A cache hit never claims a free pre-execution opportunity.
        result = self.replay([candidate("a", 8)], [attempt(execution="not_started")])
        self.assertEqual(result["charged_by_lab"]["lab-a"], 8)
        self.assertLessEqual(result["total_charged"], 32)

    def test_unrecorded_search_opportunity_and_missing_lab_charges_are_rejected(self):
        with self.assertRaises(ValueError):
            self.replay([candidate("a", 8)], [attempt()], search_charges=dict.fromkeys(self.labs, 0))
        with self.assertRaises(ValueError):
            self.replay([], [], search_charges={"lab-a": 7})
        # An unused reproduction never becomes an eighth search opportunity.
        with self.assertRaises(ValueError):
            self.replay([], [], search_charges=dict.fromkeys(self.labs, 8))

    def test_b0_four_slots_keep_failures_and_unused_without_substitutes(self):
        rows = [candidate("a", 8, arm="B0"), candidate("b", 8.5, arm="B0")]
        attempts = [attempt(), replace(attempt("b", j=None, status="failed"), slot=1)]
        result = replay_epoch(rows, attempts, "B0", self.reference, freeze=self.freeze,
                              labs=("lab-a",), search_complete=True, search_charges={"lab-a": 28})
        self.assertEqual(result["total_charged"], 30)
        self.assertEqual(result["unused_reproduction_bundles"], 2)
        self.assertEqual(result["gate"]["board"].candidate_hash, "a")
        self.assertEqual(result["best_evaluated_unreproduced"].candidate_hash, "b")

    def test_pending_reproduction_cannot_finalize_board(self):
        with self.assertRaisesRegex(ValueError, "barrier"):
            self.replay([candidate("a", 8)], [])
        with self.assertRaisesRegex(ValueError, "retry"):
            self.replay([candidate("a", 8)],
                        [attempt(j=None, status="infrastructure_failure", execution="not_started")])

    def test_terminal_failure_mismatch_and_unreproduced_report(self):
        for recorded in ([attempt(j=None, status="failed")], [attempt(j=7)],
                         [attempt(j=None, status="infrastructure_failure", execution="not_started"),
                          attempt(j=None, number=1, status="failed")]):
            result = self.replay([candidate("a", 8)], recorded)
            self.assertEqual(result["gate"]["board"], self.reference)
            self.assertEqual(result["best_evaluated_unreproduced"], candidate("a", 8))
            self.assertEqual(result["slots"][0]["status"], "reproduction_failed")
            self.assertTrue(result["complete"])

    def test_missing_data_is_inconclusive_not_failure_tie_or_substitute(self):
        result = self.replay([candidate("a", 8)],
                             [attempt(j=None, status="missing", execution="unknown")])
        self.assertFalse(result["complete"])
        self.assertEqual(result["slots"][0]["status"], "inconclusive")
        self.assertEqual(result["gate"]["board"], self.reference)
        self.assertEqual(result["charged_by_lab"]["lab-a"], 8)

    def test_no_retry_for_numerical_failure_success_or_unused_slot(self):
        for status, j in (("failed", None), ("success", 8)):
            with self.assertRaises(ValueError):
                self.replay([candidate("a", 8)], [attempt(j=j, status=status), attempt(number=1)])
        with self.assertRaises(ValueError):
            self.replay([], [attempt()])

    def test_pure_functions_do_not_mutate_inputs_and_tolerance_is_inclusive(self):
        rows, attempts = [candidate("a", 8)], [attempt(j=8.2)]
        before = copy.deepcopy((rows, attempts, self.freeze))
        result = self.replay(rows, attempts)
        self.assertEqual((rows, attempts, self.freeze), before)
        self.assertEqual(result["gate"]["board"].j, 8.2)

    def test_exact_sign_tests_and_holm_eight_of_eight(self):
        self.assertEqual(sign_test(8, 0), 0.0078125)
        self.assertEqual(sign_test(7, 1), 0.0703125)
        self.assertEqual(sign_test(6, 0), 0.03125)
        self.assertEqual(sign_test(0, 0), 1)
        self.assertEqual(holm({"sharing": sign_test(8, 0), "worker": sign_test(6, 0)}, freeze=self.freeze),
                         {"sharing": True, "worker": True})
        self.assertEqual(holm({"sharing": sign_test(6, 0), "worker": sign_test(6, 0)}, freeze=self.freeze),
                         {"sharing": False, "worker": False})
        with self.assertRaises(ValueError):
            holm({"sharing": 0.001}, freeze=self.freeze)


if __name__ == "__main__":
    unittest.main()
