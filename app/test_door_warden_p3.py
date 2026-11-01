"""Warden's P3 follow-ups on PR #81 (warden's +1 at d1b09d12, issue comment 6553446129). The fixes are one line each,
and every test below was written to fail first at main b5cf6105:

P3-1  usage that was not fully measured settles at no less than the run's envelope (a malformed or mismatched replay
      reported 12 CPU-s against the 20 reserved for the run and settled at 12)
P3-3  the board's grant view counts this grant's reservations only (a second grant in the store was counted)
P3-6  the declared operator is accepted and never stored (runs.operator kept it although nothing returns it)
P3-2  two of the test gaps warden's mutants found, closed with tests (the code was already right): no part of a
      scorer receipt reaches a public result, and a malformed x-door-nonce on the board is a 400, never a 500
"""
import dataclasses
import json
import sqlite3
import unittest

from app.door import intake
from app.door import testkit as tk
from app.door.dispatch import outcome_for
from app.door.service import Door
from app.test_door_dispatch import moved


class WardenP3Tests(tk.DoorCase, unittest.TestCase):
    def policy_kwargs(self):
        return {"grant_value": tk.grant(run_reserve_cpu_s=20)}

    def reservation(self, run_id: str) -> tuple:
        with sqlite3.connect(self.store.path) as db:
            return db.execute("SELECT state, charged_cpu_s, usage FROM reservations WHERE run_id = ?",
                              (run_id,)).fetchone()

    def test_p3_1_unmeasured_usage_settles_at_no_less_than_the_envelope(self):
        """A malformed replay: 2 CPU-s measured for the score plus the 10 CPU-s replay reserve is 12, against the 20
        reserved for the run. The run is charged its whole envelope; measured usage is still charged as measured."""
        self.scorer.cpu_known, self.scorer.cpu_s = False, 12.0
        unknown = self.submit(self.body(moved(0)))[1]["run_id"]
        self.drain()
        self.assertEqual(("settled", 20.0, "unknown_charged_conservatively"), self.reservation(unknown))
        self.assertEqual(20.0, self.door.status(unknown, tk.NONCE)[1]["token"]["cpu_s_charged"])
        self.scorer.cpu_known = True
        measured = self.submit(self.body(moved(1), nonce_value=tk.OTHER_NONCE))[1]["run_id"]
        self.drain()
        self.assertEqual(("settled", 12.0, "measured"), self.reservation(measured))

    def test_p3_1_at_the_outcome(self):
        """The rule itself: unknown usage charges max(envelope, reported); a reported overrun is charged in full."""
        dies = intake.compact_dies(tk.SNAPPED)[0]
        score = self.scorer.score({"run_id": "open-00000000-" + "0" * 32, "token_ref": "0" * 64,
                                   "proposal": {"dies": dies, "geometry_sha256": "0" * 64}})
        for known, reported, charged in ((False, 12.0, 20.0), (False, 37.0, 37.0), (True, 12.0, 12.0),
                                         (True, 37.0, 37.0)):
            with self.subTest(known=known, reported=reported):
                value = dataclasses.replace(score, cpu_known=known, cpu_s=reported)
                outcome = outcome_for(value, {"proposal": {"dies": dies}, "envelope_cpu_s": 20.0},
                                      self.policy.checker)
                self.assertEqual(charged, outcome["charged_cpu_s"])
                self.assertEqual(reported, outcome["result"]["cpu_s"], "the reported CPU is kept as reported")

    def test_p3_3_the_board_counts_this_grants_reservations_only(self):
        """A run held under another grant in the same store is not this grant's: 0 reserved, the whole cap left."""
        other_grant = "slab-demo-other"
        other_policy = tk.policy(clock=self.clock, manifest=tk.door_manifest(**{"refs.grant": other_grant}),
                                 grant_value=tk.grant(grant=other_grant, run_reserve_cpu_s=25))
        other = Door(other_policy, self.store, tk.FakeScorer(other_policy.checker))
        status, reply, _ = other.submit(json.dumps(self.body(moved(2))).encode())
        self.assertEqual(202, status, reply)
        grant = self.door.board()[1]["grant"]
        self.assertEqual((0.0, 0.0, self.policy.grant.cpu_cap_s),
                         (grant["cpu_s_reserved"], grant["cpu_s_charged"], grant["cpu_s_remaining"]))
        mine = self.submit(self.body(moved(3), nonce_value=tk.OTHER_NONCE))[1]["run_id"]
        grant = self.door.board()[1]["grant"]
        self.assertEqual((20.0, self.policy.grant.cpu_cap_s - 20.0), (grant["cpu_s_reserved"], grant["cpu_s_remaining"]))
        self.assertEqual("queued", self.store.run(mine)[0]["state"])

    def test_p3_6_the_declared_operator_is_never_stored(self):
        run_id = self.submit(self.body(moved(4), operator="openai"))[1]["run_id"]
        with sqlite3.connect(self.store.path) as db:
            stored = db.execute("SELECT operator FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0]
        self.assertEqual("unknown", stored)
        with sqlite3.connect(self.store.path) as db:
            for table, in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
                for row in db.execute(f"SELECT * FROM {table}"):
                    self.assertNotIn("openai", json.dumps(row), table)

    def test_p3_2_no_part_of_a_receipt_reaches_a_public_result(self):
        run_id = self.submit(self.body(moved(5)))[1]["run_id"]
        self.drain()
        receipt = json.loads(self.store.run(run_id)[0]["result"])["receipt"]["score"]
        self.assertTrue(receipt, "the stored result keeps its receipt")
        bodies = [self.door.results(None, "20")[1], self.door.status(run_id, tk.NONCE)[1], self.door.board()[1]]
        for body in bodies:
            text = json.dumps(body)
            self.assertNotIn('"receipt"', text)
            self.assertNotIn('"fake"', text, "the fake scorer's receipt marker")
        self.assertNotIn("receipt", self.door.results(None, "20")[1]["items"][0]["result"])

    def test_p3_2_a_malformed_board_nonce_is_a_400(self):
        for nonce in ("", "zz", "0123456789ABCDEF", "0123456789abcdef0", 7):
            with self.subTest(repr(nonce)):
                status, body, _ = self.door.board(nonce)
                self.assertEqual((400, {"error": "token_required"}), (status, body))
        self.assertEqual(200, self.door.board(tk.NONCE)[0])


if __name__ == "__main__":
    unittest.main()
