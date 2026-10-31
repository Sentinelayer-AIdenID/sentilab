"""Synthetic ledger inputs only: no solver, model, or outcome artifacts."""
import copy
import itertools
import json
from pathlib import Path
import unittest

from sentilab_core.freeze import (Candidate, Attempt, nominate,
                                  eligible_for_reproduction, rank_order_gate,
                                  reproduction_slots, replay_epoch,
                                  validate_freeze, require_execution_ready,
                                  sign_test, holm)

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "docs/sentilab/freeze/slab041-freeze.json"


def candidate(name, j, lab="lab-a", arm="B3", valid=True):
    return Candidate(name, lab, arm, j, "eval-" + lab + "-" + name, valid)


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.freeze = json.loads(FREEZE.read_text())
        # Explicit synthetic test values, never defaults or a benchmark release.
        self.freeze["parameters"].update(nomination_tolerance=0.1,
                                         acceptance_margin=1,
                                         reproduction_tolerance=0.2)

    def test_manifest_schema_and_document_agree(self):
        frozen = json.loads(FREEZE.read_text())
        validate_freeze(frozen)
        doc = FREEZE.with_name("SLAB-041-FREEZE.md").read_text()
        self.assertEqual(json.loads(doc.split("```json\n")[1].split("```", 1)[0]), frozen)
        self.assertIn("8 of 8", doc)
        self.assertIn("six-n endpoint", doc)
        self.assertEqual(frozen["families"]["target"], 12)
        self.assertEqual(frozen["families"]["fallback"], 8)
        self.assertEqual(frozen["families"]["descriptive_only"], 6)
        for arm, row in frozen["arms"].items():
            self.assertEqual(row["labs"] * (row["search_per_lab"] + row["reproduction_per_lab"]), 32)
            self.assertIn(arm, doc)
        bad = copy.deepcopy(frozen)
        bad["arms"]["B2"]["search_per_lab"] = 8
        with self.assertRaises(ValueError):
            validate_freeze(bad)

    def test_unknown_parameters_block_execution_and_nomination(self):
        frozen = json.loads(FREEZE.read_text())
        with self.assertRaisesRegex(ValueError, "must-fill-before-execution"):
            require_execution_ready(frozen)
        with self.assertRaises(ValueError):
            nominate([], "B3", freeze=frozen)
        with self.assertRaises(ValueError):
            eligible_for_reproduction(candidate("a", 2), 5, None)

    def test_nominate_each_lab_by_own_j_and_preserve_duplicates(self):
        rows = [candidate("same", 8), candidate("other", 9),
                candidate("same", 7, "lab-b"), candidate("last", 10, "lab-b")]
        result = nominate(rows, "B3", freeze=self.freeze)
        self.assertEqual([(c.lab, c.candidate_hash) for c in result],
                         [("lab-b", "same"), ("lab-a", "same")])
        self.assertEqual(len(result), 2)

    def test_tolerance_chains_and_hash_ties_are_shuffle_invariant(self):
        rows = [candidate("z", 8), candidate("a", 8.1), candidate("0", 8.2)]
        for shuffled in itertools.permutations(rows):
            self.assertEqual(nominate(shuffled, "B3", freeze=self.freeze), (rows[1],))

    def test_b0_b1_top_four_distinct_and_other_arm_is_excluded(self):
        for arm in ("B0", "B1"):
            rows = [candidate(str(i), i, arm=arm) for i in range(6)]
            rows += [rows[0], candidate("foreign", -10)]
            self.assertEqual([c.candidate_hash for c in nominate(rows, arm, freeze=self.freeze)],
                             ["0", "1", "2", "3"])

    def test_invalid_candidates_and_nonfinite_values_fail_closed(self):
        self.assertEqual(nominate([candidate("bad", 0, valid=False)], "B3", freeze=self.freeze), ())
        for value in (float("nan"), float("inf"), True, "1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                nominate([candidate("a", value)], "B3", freeze=self.freeze)
        with self.assertRaises(ValueError):
            nominate([], "unknown", freeze=self.freeze)

    def test_exact_margin_and_nonimproving_are_not_eligible(self):
        self.assertFalse(eligible_for_reproduction(candidate("a", 9), 10, 1))
        self.assertTrue(eligible_for_reproduction(candidate("a", 8.9), 10, 1))
        self.assertFalse(eligible_for_reproduction(candidate("a", 10), 10, 0))
        self.assertFalse(eligible_for_reproduction(candidate("a", 0, valid=False), 10, 1))

    def test_rank_uses_best_once_and_retains_valid_losers(self):
        rows = [candidate("a", 98), candidate("b", 97.5, "lab-b")]
        for shuffled in itertools.permutations(rows):
            result = rank_order_gate(shuffled, 100, 1, freeze=self.freeze)
            self.assertEqual(result["board"], rows[1])
            self.assertEqual([r["outcome"] for r in result["decisions"]],
                             ["accepted", "non_improving_current"])

    def test_rank_margin_boundary_and_hash_tie_winner(self):
        result = rank_order_gate([candidate("a", 9), candidate("b", 10)], 10, 1, freeze=self.freeze)
        self.assertEqual(result["board"], 10)
        self.assertEqual([r["outcome"] for r in result["decisions"]],
                         ["within_margin", "non_improving_current"])
        result = rank_order_gate([candidate("z", 8), candidate("a", 8.1)], 10, 1, freeze=self.freeze)
        self.assertEqual(result["board"].candidate_hash, "a")
        self.assertEqual(result["decisions"][1]["outcome"], "within_margin")

    def test_ineligible_tie_cannot_hide_margin_clearing_candidate(self):
        rows = [candidate("a", 9), candidate("z", 8.95)]
        result = rank_order_gate(rows, 10, 1, freeze=self.freeze)
        self.assertEqual(result["board"], rows[1])

    def test_slots_preserve_duplicates_and_unused_without_transfer(self):
        rows = [candidate("same", 8), candidate("same", 8, "lab-b")]
        slots = reproduction_slots(rows, "B3", 10, freeze=self.freeze,
                                   labs=("lab-d", "lab-b", "lab-a", "lab-c"), search_complete=True)
        self.assertEqual(len(slots), 4)
        self.assertEqual([s["status"] for s in slots], ["nominated", "nominated", "unused", "unused"])
        self.assertEqual([s["candidate"].candidate_hash for s in slots[:2]], ["same", "same"])
        self.assertEqual(sum(s["reserved_bundles"] for s in slots), 4)

    def test_search_barrier_and_complete_lab_roster_are_required(self):
        for kwargs in ({"search_complete": False, "labs": ("a", "b", "c", "d")},
                       {"search_complete": True, "labs": ("a", "b", "c")}):
            with self.assertRaises(ValueError):
                reproduction_slots([], "B3", 10, freeze=self.freeze, **kwargs)

    def replay(self, candidates, attempts, **kwargs):
        return replay_epoch(candidates, attempts, "B3", 10, freeze=self.freeze,
                            labs=("lab-a", "lab-b", "lab-c", "lab-d"),
                            search_complete=True, **kwargs)

    def test_duplicate_reproductions_both_spend_and_ledger_replays(self):
        rows = [candidate("same", 8), candidate("same", 8, "lab-b")]
        attempts = [Attempt("lab-a", 0, "same", 0, "success", 8),
                    Attempt("lab-b", 0, "same", 0, "success", 8)]
        expected = self.replay(rows, attempts)
        self.assertEqual(expected["reproduction_bundles_spent"], 2)
        self.assertEqual(expected["unused_reproduction_bundles"], 2)
        self.assertEqual(len(expected["gate"]["decisions"]), 2)
        for cs in itertools.permutations(rows):
            for rs in itertools.permutations(attempts):
                self.assertEqual(self.replay(cs, rs), expected)

    def test_failed_reproduction_one_declared_retry_no_substitute(self):
        rows = [candidate("a", 8), candidate("b", 8.5)]
        first = Attempt("lab-a", 0, "a", 0, "infrastructure_failure", None)
        retry = Attempt("lab-a", 0, "a", 1, "success", 8)
        result = self.replay(rows, [retry, first])
        self.assertEqual(result["physical_attempts"], 2)
        self.assertEqual(result["reproduction_bundles_spent"], 1)
        self.assertEqual(result["gate"]["board"], rows[0])
        with self.assertRaises(ValueError):
            self.replay(rows, [first, Attempt("lab-a", 0, "b", 1, "success", 8.5)])
        with self.assertRaises(ValueError):
            self.replay(rows, [first, retry, Attempt("lab-a", 0, "a", 2, "success", 8)])

    def test_pending_reproduction_cannot_finalize_board(self):
        with self.assertRaisesRegex(ValueError, "barrier"):
            self.replay([candidate("a", 8)], [])
        with self.assertRaisesRegex(ValueError, "retry"):
            self.replay([candidate("a", 8)], [Attempt("lab-a", 0, "a", 0, "infrastructure_failure", None)])

    def test_terminal_failure_mismatch_and_unreproduced_report(self):
        rows = [candidate("a", 8), candidate("b", 8.5)]
        for attempts in ([Attempt("lab-a", 0, "a", 0, "failed", None)],
                         [Attempt("lab-a", 0, "a", 0, "success", 7)],
                         [Attempt("lab-a", 0, "a", 0, "infrastructure_failure", None),
                          Attempt("lab-a", 0, "a", 1, "failed", None)]):
            result = self.replay(rows, attempts)
            self.assertEqual(result["gate"]["board"], 10)
            self.assertEqual(result["best_evaluated_unreproduced"], rows[0])
            self.assertEqual(result["slots"][0]["status"], "reproduction_failed")

    def test_no_retry_for_numerical_failure_or_success_and_no_unused_spend(self):
        rows = [candidate("a", 8)]
        for status, j in (("failed", None), ("success", 8)):
            with self.assertRaises(ValueError):
                self.replay(rows, [Attempt("lab-a", 0, "a", 0, status, j),
                                   Attempt("lab-a", 0, "a", 1, "success", 8)])
        with self.assertRaises(ValueError):
            self.replay([], [Attempt("lab-a", 0, "a", 0, "success", 8)])

    def test_pure_functions_do_not_mutate_inputs(self):
        rows = [candidate("a", 8)]
        attempts = [Attempt("lab-a", 0, "a", 0, "success", 8.2)]
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


if __name__ == "__main__":
    unittest.main()
