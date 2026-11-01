"""Root's review of PR #81 at 796fec43: an open attempt's retained lower bound must count wherever CPU is counted.

An attempt kept open (mark_recovering) holds its envelope and the largest CPU any answer reported. Intake, the claim,
the board's remaining grant CPU and a token's remaining CPU must all count max(envelope, lower bound) for it, and its
slot stays held until it resolves. Written to fail first at 796fec43.
"""
import unittest

from app.door import testkit as tk
from app.test_door_dispatch import moved
from app.test_door_root_r1 import AccountingCase


class LowerBoundAccountingTests(AccountingCase):
    def policy_kwargs(self):
        return {"grant_value": tk.grant(cpu_cap_s=40, token_cpu_s=40, run_reserve_cpu_s=20, parallel=2)}

    def open_with_lower_bound(self, run_id: str, lower: float) -> None:
        claimed = self.store.claim(check=self.door.launch_check, parallel=2, now=self.clock(),
                                   grant=self.policy.grant)
        self.assertEqual(claimed["run_id"], run_id)
        self.store.mark_recovering(run_id=run_id, reservation_id=claimed["reservation_id"], lower_bound_cpu_s=lower,
                                   now=self.clock())

    def test_the_claim_counts_an_open_attempts_reported_cpu(self):
        """Root's control: an active 20 CPU-s envelope reporting 35, plus another queued 20, under a 40 cap."""
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        second = self.submit(self.body(moved(1)))[1]["run_id"]
        self.open_with_lower_bound(first, 35.0)
        claimed = self.store.claim(check=self.door.launch_check, parallel=2, now=self.clock(),
                                   grant=self.policy.grant)
        self.assertIsNone(claimed, "35 + 20 = 55 would be promised against a 40 CPU-s cap")
        self.assertEqual(self.store.run(second)[0]["state"], "queued")
        self.assertEqual(self.store.run(first)[0]["state"], "evaluating", "the open attempt keeps its slot")
        self.assertIn("grant", [stop["scope"] for stop in self.store.stops()])

    def test_intake_counts_it_too(self):
        self.policy.grant = tk.policy(grant_value=tk.grant(cpu_cap_s=60, token_cpu_s=60, run_reserve_cpu_s=20,
                                                           parallel=2)).grant
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        self.open_with_lower_bound(first, 35.0)
        self.assertEqual(self.submit(self.body(moved(1)))[0], 202, "35 + 20 = 55 fits under 60")
        status, reply = self.submit(self.body(moved(2)))
        self.assertEqual(status, 429, "55 + 20 = 75 does not")
        self.assertEqual(reply["limits"], ["grant_cpu", "token_cpu"])

    def test_both_remaining_views_count_it(self):
        """Under a 60 CPU-s cap, 35 reported and 20 queued leave at most 5, not 20."""
        self.policy.grant = tk.policy(grant_value=tk.grant(cpu_cap_s=60, token_cpu_s=60, run_reserve_cpu_s=20,
                                                           parallel=2)).grant
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        self.submit(self.body(moved(1)))
        self.open_with_lower_bound(first, 35.0)
        grant = self.door.board()[1]["grant"]
        self.assertEqual((grant["cpu_s_reserved"], grant["cpu_s_remaining"]), (55.0, 5.0))
        token = self.door.board(tk.NONCE)[1]["token"]
        self.assertEqual((token["cpu_s_reserved"], token["cpu_s_remaining"]), (55.0, 5.0))
        self.assertEqual(self.door.status(first, tk.NONCE)[1]["token"]["cpu_s_remaining"], 5.0)


if __name__ == "__main__":
    unittest.main()
