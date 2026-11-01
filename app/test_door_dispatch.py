"""Agent door queue and workers (AGENT-DOOR.md section 4, Amendment 1 items 2 and 3, hostile checks 2, 6 and 8):
the contract's state transitions with a fake scorer, CPU reserved per token and per grant atomically before dispatch
and settled after, failures charged, the bounded persisted queue revalidated at launch, scorer down, and the floods."""
import json
import sqlite3
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from app.door import testkit as tk
from open_proposals.contract import canonical as hashes
from app.door.dispatch import failure_for
from app.door.scorer import ScorerError
from app.door.store import Store


def moved(index: int) -> str:
    """One of 22 distinct legal layouts: C0 at x 17.5 or 18.0 mm and y 13.0 to 18.0 mm, the room the snapped layout
    leaves it between D0, C1 and C3 (moved(3) is the snapped layout itself)."""
    items = tk.SNAPPED.split(",")
    items[0] = f"{35 + index % 2}.{36 - index // 2 % 11}.0"
    return ",".join(items)


class StateTests(tk.DoorCase, unittest.TestCase):
    def submit_one(self, layout=tk.SNAPPED, **edits) -> str:
        status, reply = self.submit(self.body(layout, **edits))
        self.assertEqual(status, 202, reply)
        return reply["run_id"]

    def states(self, run_id) -> list:
        events = json.loads(json.dumps(self.door.events(None, "200")[1]))["events"]
        return [event["state"] for event in events if event["kind"] == "run" and event["run_id"] == run_id]

    def reservation(self, run_id) -> dict:
        with sqlite3.connect(self.store.path) as db:
            db.row_factory = sqlite3.Row
            return dict(db.execute("SELECT * FROM reservations WHERE run_id = ?", (run_id,)).fetchone())

    def test_a_scored_run_walks_the_contract_states_and_is_charged_its_measured_cpu(self):
        run_id = self.submit_one()
        self.assertEqual(self.reservation(run_id)["state"], "held")
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.states(run_id), ["queued", "evaluating", "evaluated", "replaying", "reproduced"])
        held = self.reservation(run_id)
        self.assertEqual((held["state"], held["charged_cpu_s"], held["usage"]), ("settled", 2.5, "measured"))
        request = self.scorer.calls[0]
        row, _ = self.store.run(run_id)
        self.assertEqual(set(request), {"run_id", "token_ref", "proposal"}, "door-scorer's exact request shape")
        self.assertEqual(request["run_id"], run_id)
        self.assertEqual(request["proposal"], json.loads(row["proposal"]))
        self.assertEqual(request["token_ref"], self.policy.participant_ref(row["principal"]))
        self.assertEqual(hashes.run_id(self.policy.manifest_id, request["token_ref"],
                                       hashes.proposal_sha256(request["proposal"])), run_id,
                         "the scorer's run-id check (run_id(manifest, token_ref, proposal_sha256)) gives the door's")

    def test_replay_failures_end_not_reproduced_with_their_code(self):
        for mode, code in (("mismatch", "reproduction_mismatch"), ("not_fresh", "fresh_process_required")):
            self.scorer.mode = mode
            run_id = self.submit_one(moved({"mismatch": 1, "not_fresh": 2}[mode]))
            self.drain()
            row, _ = self.store.run(run_id)
            self.assertEqual((row["state"], [c["code"] for c in json.loads(row["codes"])]), ("not_reproduced", [code]))
            self.assertEqual(self.states(run_id)[-2:], ["replaying", "not_reproduced"])

    def test_scorer_failures_end_failed_with_an_explicit_reason_and_their_charge(self):
        cases = (("down", "scorer_down", "oracle_error", 0.0, "never_began"),
                 ("timeout", "scorer_timeout", "timeout", 10.0, "unknown_charged_envelope"),
                 ("error", "scorer_error", "oracle_error", 40.0, "unknown_charged_envelope"),
                 ("cutoff", "scorer_cutoff", "stopped", 10.0, "unknown_charged_envelope"),
                 ("grant_expired", "grant_expired", "grant_expired", 10.0, "unknown_charged_envelope"))
        for index, (mode, reason, code, charged, usage) in enumerate(cases):
            self.scorer.mode, self.scorer.healthy = mode, True
            self.door.scorer_state.state = "up"
            run_id = self.submit_one(moved(index), nonce_value=tk.nonce(100 + index))
            self.assertEqual(self.drain(1), 1, mode)
            row, _ = self.store.run(run_id)
            self.assertEqual((row["state"], row["reason"]), ("failed", reason), mode)
            self.assertEqual([c["code"] for c in json.loads(row["codes"])], [code], mode)
            held = self.reservation(run_id)
            self.assertEqual((held["charged_cpu_s"], held["usage"]), (charged, usage), mode)
            status, item, _ = self.door.status(run_id, tk.nonce(100 + index))
            self.assertEqual((item["status"], item["reason"]), ("failed", reason))

    def test_while_the_scorer_is_down_queued_work_waits_and_the_feed_says_so(self):
        self.scorer.healthy = False
        run_id = self.submit_one()
        self.assertEqual(self.drain(), 0)
        self.assertEqual(self.scorer.calls, [])
        self.assertEqual(self.store.run(run_id)[0]["state"], "queued")
        board = self.door.board()[1]
        self.assertEqual(board["scorer"]["state"], "down")
        events = self.door.events(None, None)[1]["events"]
        self.assertIn({"kind": "scorer", "state": "down"}, [{k: e[k] for k in ("kind", "state") if k in e}
                                                            for e in events if e["kind"] == "scorer"])
        self.scorer.healthy = True
        self.clock.advance(6)
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.store.run(run_id)[0]["state"], "reproduced")
        self.assertEqual(self.door.board()[1]["scorer"]["state"], "up")

    def test_a_score_whose_numbers_disagree_with_its_parts_keeps_the_evaluation_but_no_verdict(self):
        """The metric must be the maximum of the per-die values, each per-die value its grid mean when a grid comes
        back, and the scorer's wire proxy the door's."""
        for index, (mode, with_grid, failed) in enumerate((("bad_binding", False, "per_die_ok"),
                                                            ("bad_wire", False, "wire_ok"),
                                                            ("bad_die", True, "grid_ok"))):
            self.scorer.mode, self.scorer.with_grid = mode, with_grid
            run_id = self.submit_one(moved(index), nonce_value=tk.nonce(800 + index))
            self.drain()
            row, _ = self.store.run(run_id)
            self.assertEqual((row["state"], [c["code"] for c in json.loads(row["codes"])]),
                             ("reproduced", ["binding_mismatch"]), mode)
            item = self.door.status(run_id, tk.nonce(800 + index))[1]
            self.assertFalse(item["result"]["binding_ok"], mode)
            self.assertFalse(json.loads(row["result"])["binding"][failed], mode)
            self.assertIsNone(item["verdict"], mode)

    def test_a_bound_score_with_a_grid_passes_every_check(self):
        self.scorer.with_grid = True
        run_id = self.submit_one()
        self.drain()
        bound = json.loads(self.store.run(run_id)[0]["result"])["binding"]
        self.assertEqual({name: bound[name] for name in ("per_die_ok", "grid_ok", "wire_ok", "ok")},
                         {"per_die_ok": True, "grid_ok": True, "wire_ok": True, "ok": True})

    def test_a_replay_that_cannot_complete_is_not_reproduced_and_a_refusal_costs_nothing(self):
        self.scorer.mode = "replay_failed"
        run_id = self.submit_one()
        self.drain()
        row, _ = self.store.run(run_id)
        self.assertEqual((row["state"], [c["code"] for c in json.loads(row["codes"])]),
                         ("not_reproduced", ["reproduction_failed"]))
        self.scorer.mode = "refused"
        run_id = self.submit_one(moved(1))
        self.drain()
        row, _ = self.store.run(run_id)
        self.assertEqual((row["state"], row["reason"]), ("failed", "scorer_refused"))
        held = self.reservation(run_id)
        self.assertEqual((held["charged_cpu_s"], held["usage"]), (0.0, "never_began"))

    def test_an_unknown_outcome_keeps_the_attempt_open_with_its_lower_bound(self):
        """A timeout after sending, or an adapter fault: the remote attempt may still run. Nothing is settled, the slot
        and envelope stay counted, and a later definitive answer settles it at no less than the reported CPU."""
        for index, mode in enumerate(("ambiguous", "raise")):
            self.scorer.mode = mode
            run_id = self.submit_one(moved(index), nonce_value=tk.nonce(900 + index))
            self.assertEqual(self.drain(1), 0, mode)
            row, _ = self.store.run(run_id)
            self.assertEqual((row["state"], row["reason"]), ("evaluating", "unresolved"), mode)
            held = self.reservation(run_id)
            self.assertEqual((held["state"], held["usage"]), ("active", "recovering"), mode)
        self.assertEqual(self.reservation(self.store.recovering()[0]["run_id"])["lower_bound_cpu_s"], 13.0)
        self.scorer.mode = "ok"
        self.clock.advance(11)
        self.assertEqual(self.drain(), 2, "the same request again resolves both")
        first = self.store.recovering()
        self.assertEqual(first, [])
        charges = sorted(row["charged_cpu_s"] for row in map(self.reservation, [
            call["run_id"] for call in self.scorer.calls[-2:]]))
        self.assertEqual(charges, [2.5, 13.0], "a reported lower bound outlives a smaller later measurement")

    def test_restart_recovery_never_declares_an_end(self):
        run_id = self.submit_one()
        claimed = self.store.claim(check=self.door.launch_check, parallel=4, now=self.clock(),
                                   grant=self.policy.grant)
        self.assertEqual(claimed["run_id"], run_id)
        again = Store(self.store.path)
        self.assertEqual(again.recover(self.clock()), 1)
        row, _ = again.run(run_id)
        self.assertEqual((row["state"], row["reason"]), ("evaluating", "unresolved"))
        held = self.reservation(run_id)
        self.assertEqual((held["state"], held["charged_cpu_s"], held["usage"]), ("active", None, "recovering"))
        self.assertTrue(self.store.settle(run_id=run_id, reservation_id=claimed["reservation_id"],
                                          outcome={"kind": "failed", "code": "oracle_error", "reason": "scorer_error",
                                                   "charged_cpu_s": 35.0, "usage": "unknown_charged_envelope"},
                                          now=self.clock()), "the original's late settlement still counts")
        self.assertEqual(self.reservation(run_id)["charged_cpu_s"], 35.0)

    def test_at_most_parallel_attempts_run_at_once_across_workers(self):
        self.scorer.release = threading.Event()
        for index in range(6):
            self.submit_one(moved(index % 8), nonce_value=tk.nonce(200 + index))
        self.door.start()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                states = self.door.board()[1]["counts"]
                if states["evaluating"] == 4:
                    break
                time.sleep(0.02)
            time.sleep(0.2)
            counts = self.door.board()[1]["counts"]
            self.assertEqual((counts["evaluating"], counts["queued"]), (4, 2))
            self.scorer.release.set()
            deadline = time.monotonic() + 15
            while self.door.board()[1]["counts"]["reproduced"] < 6 and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(self.door.board()[1]["counts"]["reproduced"], 6)
        finally:
            self.scorer.release.set()
            self.door.stop()

    def test_a_claim_respects_the_parallel_limit_whoever_asks(self):
        for index in range(3):
            self.submit_one(moved(index), nonce_value=tk.nonce(700 + index))
        claims = [self.store.claim(check=self.door.launch_check, parallel=2, now=self.clock(),
                                   grant=self.policy.grant) for _ in range(3)]
        self.assertEqual([claim is not None for claim in claims], [True, True, False])
        self.assertEqual(self.door.board()[1]['counts']['evaluating'], 2)

    def test_a_window_that_ends_expires_queued_work_and_releases_its_cpu(self):
        run_id = self.submit_one()
        self.clock.now = self.policy.grant.not_after
        self.assertEqual(self.drain(), 0)
        row, _ = self.store.run(run_id)
        self.assertEqual((row["state"], row["reason"]), ("expired", "window_closed"))
        held = self.reservation(run_id)
        self.assertEqual((held["state"], held["charged_cpu_s"]), ("released", 0))
        self.assertEqual(self.scorer.calls, [])

    def test_launch_revalidates_the_stored_proposal(self):
        run_id = self.submit_one()
        with sqlite3.connect(self.store.path) as db:
            proposal = json.loads(db.execute("SELECT proposal FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0])
            proposal["dies"][1]["x_um"] = proposal["dies"][0]["x_um"]
            db.execute("UPDATE runs SET proposal = ? WHERE run_id = ?", (json.dumps(proposal), run_id))
        self.assertEqual(self.drain(), 0)
        row, _ = self.store.run(run_id)
        self.assertEqual((row["state"], row["reason"]), ("cancelled", "revalidation_failed"))
        self.assertEqual(self.scorer.calls, [])

    def test_an_unreadable_stored_run_is_cancelled_and_the_queue_moves_on(self):
        broken = self.submit_one()
        good = self.submit_one(moved(1))
        with sqlite3.connect(self.store.path) as db:
            db.execute("UPDATE runs SET proposal = '{not json' WHERE run_id = ?", (broken,))
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.store.run(broken)[0]["state"], "cancelled")
        self.assertEqual(self.store.run(good)[0]["state"], "reproduced")

    def test_get_routes_never_start_a_solve(self):
        run_id = self.submit_one()
        for _ in range(3):
            self.door.board(), self.door.results(None, None), self.door.events(None, None)
            self.door.status(run_id, tk.NONCE)
        self.assertEqual(self.scorer.calls, [])
        self.assertEqual(self.store.run(run_id)[0]["state"], "queued")


class QuotaTests(tk.DoorCase, unittest.TestCase):
    """Amendment 1 item 2: 30 CPU-seconds per token, held before dispatch; attempt counts kept apart."""

    def policy_kwargs(self):
        return {"eval_per_account_hour": 100, "eval_per_account_day": 100, "eval_room_hour": 1000,
                "eval_room_day": 1000}

    def test_cpu_per_token_is_reserved_at_enqueue_and_counts_held_envelopes(self):
        statuses = [self.submit(self.body(moved(index)))[0] for index in range(3)]
        self.assertEqual(statuses, [202, 202, 202])
        status, reply = self.submit(self.body(moved(3)))
        self.assertEqual(status, 429)
        self.assertEqual(reply["limits"], ["token_cpu"])
        self.assertEqual(reply["codes"], [{"code": "budget_exhausted",
                                           "retry_after": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(
                                               int(self.clock()) + 600))}])
        self.drain()
        usage = self.door.status(self.store.changed_runs(0, 1)[0]["run_id"], tk.NONCE)[1]["token"]
        self.assertEqual(usage["cpu_s_charged"], 7.5)
        self.assertEqual(usage["cpu_s_remaining"], 22.5)
        self.assertEqual(usage["evaluations_last_hour"], 3)
        status, reply = self.submit(self.body(moved(3)))
        self.assertEqual(status, 202, "settled at the measured 2.5 CPU-s each, the token has room again")

    def test_failures_are_charged_and_an_overrun_is_charged_in_full(self):
        self.scorer.mode = "timeout"
        self.submit(self.body(moved(0)))
        self.drain()
        self.scorer.mode, self.scorer.cpu_s = "ok", 25.0
        self.submit(self.body(moved(1)))
        self.drain()
        usage = self.door.status(self.store.changed_runs(0, 1)[0]["run_id"], tk.NONCE)[1]["token"]
        self.assertEqual(usage["cpu_s_charged"], 35.0)
        self.assertEqual(usage["cpu_s_remaining"], 0.0)
        status, reply = self.submit(self.body(moved(2)))
        self.assertEqual((status, reply["limits"]), (429, ["token_cpu"]))
        with sqlite3.connect(self.store.path) as db:
            self.assertIn(("measured_overrun",), db.execute("SELECT usage FROM reservations").fetchall())

    def test_the_grant_cap_holds_across_token_churn(self):
        self.policy.grant = tk.policy(grant_value=tk.grant(cpu_cap_s=45)).grant
        accepted = [self.submit(self.body(moved(index), nonce_value=tk.nonce(300 + index)))[0]
                    for index in range(8)]
        self.assertEqual(accepted.count(202), 4)
        refused = self.submit(self.body(moved(5), nonce_value=tk.nonce(999)))[1]
        self.assertEqual(refused["limits"], ["grant_cpu"])
        self.drain()
        self.assertEqual(self.submit(self.body(moved(6), nonce_value=tk.nonce(998)))[0], 202)

    def test_concurrent_admissions_never_promise_more_cpu_than_the_grant(self):
        """The decision and the write share one transaction under the write lock: with the window between them
        held open, concurrent requests still see one order and the cap holds exactly."""
        self.policy.grant = tk.policy(grant_value=tk.grant(cpu_cap_s=50)).grant
        self.store.pause_hook = lambda: time.sleep(0.05)

        def one(index):
            try:
                return self.submit(self.body(moved(index), nonce_value=tk.nonce(400 + index)))[0]
            except Exception as error:  # noqa: BLE001 - an error is a failure of atomicity, counted not raised
                return type(error).__name__

        with ThreadPoolExecutor(max_workers=12) as pool:
            statuses = list(pool.map(one, range(12)))
        self.assertEqual(sorted(map(str, statuses)), ['202'] * 5 + ['429'] * 7, statuses)
        with sqlite3.connect(self.store.path) as db:
            held = db.execute("SELECT SUM(amount_cpu_s) FROM reservations WHERE state = 'held'").fetchone()[0]
        self.assertEqual(held, 50.0)


class LimitTests(tk.DoorCase, unittest.TestCase):
    """The manifest's evaluation quotas (per token, per room) and queue cap, and the HTTP flood limits."""

    def test_per_token_evaluations_follow_the_manifest_and_say_when_to_retry(self):
        self.policy.grant = tk.policy(grant_value=tk.grant(token_cpu_s=100, run_reserve_cpu_s=1)).grant
        statuses = [self.submit(self.body(moved(index)))[0] for index in range(3)]
        self.assertEqual(statuses, [202] * 3)
        status, reply = self.submit(self.body(moved(3)))
        self.assertEqual((status, reply["limits"]), (429, ["token_hour"]))
        self.assertEqual(reply["codes"][0]["code"], "rate_limited")
        self.clock.advance(3601)
        self.assertEqual(self.submit(self.body(moved(3)))[0], 202)

    def test_the_queue_is_bounded_and_says_queue_full(self):
        self.policy.manifest["limits"].update({"queue_max": 2, "eval_room_hour": 100, "eval_room_day": 100})
        statuses = [self.submit(self.body(moved(index), nonce_value=tk.nonce(500 + index)))[0] for index in range(3)]
        self.assertEqual(statuses, [202, 202, 429])
        status, reply = self.submit(self.body(moved(4), nonce_value=tk.nonce(600)))
        self.assertEqual((reply["codes"][0]["code"], reply["limits"]), ("queue_full", ["queue"]))

    def test_flood_from_one_token_holds_its_quota_and_the_view_stays_up(self):
        """Hostile check 6a: 50 quick submissions from one token."""
        self.policy.flood = type(self.policy.flood)(nonce_per_min=6, total_per_min=240)
        with ThreadPoolExecutor(max_workers=10) as pool:
            replies = list(pool.map(lambda index: self.submit(self.body(moved(index % 8))), range(50)))
        statuses = [status for status, _ in replies]
        self.assertTrue(set(statuses) <= {202, 200, 429}, statuses)
        self.assertLessEqual(statuses.count(202), 3)
        self.assertGreaterEqual(statuses.count(429), 44)
        for status, reply in replies:
            if status == 429:
                self.assertEqual(reply["state"], "rejected")
                self.assertTrue(all(item["code"] in ("rate_limited", "budget_exhausted") for item in reply["codes"]))
        self.assertEqual(self.door.board()[0], 200)
        self.drain()
        with sqlite3.connect(self.store.path) as db:
            charged = db.execute("SELECT SUM(COALESCE(charged_cpu_s, amount_cpu_s)) FROM reservations").fetchone()[0]
        self.assertLessEqual(charged, 30.0)

    def test_flood_from_many_tokens_holds_the_room_and_queue_and_the_grant(self):
        """Hostile check 6b: 200 submissions from many tokens."""
        self.policy.flood = type(self.policy.flood)(nonce_per_min=6, total_per_min=240)
        with ThreadPoolExecutor(max_workers=16) as pool:
            replies = list(pool.map(lambda index: self.submit(self.body(moved(index % 8),
                                                                        nonce_value=tk.nonce(1000 + index))),
                                    range(200)))
        statuses = [status for status, _ in replies]
        self.assertEqual(statuses.count(202), 20, "the manifest's room quota: 20 evaluations an hour")
        self.assertEqual(statuses.count(429), 180)
        limits = {scope for status, reply in replies if status == 429 for scope in reply["limits"]}
        self.assertIn("room_hour", limits)
        board = self.door.board()[1]
        self.assertLessEqual(board["queue"]["length"], 30)
        self.assertLessEqual(board["grant"]["cpu_s_reserved"] + board["grant"]["cpu_s_charged"], 3600)
        self.assertEqual(board["counts"]["attempts"], 200)

    def test_the_request_rate_limits_per_nonce_and_in_total(self):
        self.policy.flood = type(self.policy.flood)(nonce_per_min=2, total_per_min=3)
        statuses = [self.submit(self.body(moved(index)))[0] for index in range(3)]
        self.assertEqual(statuses[:2], [202, 202])
        status, reply = self.submit(self.body(moved(2)))
        self.assertEqual((status, reply["limits"], reply["codes"][0]["code"]), (429, ["request_rate"], "rate_limited"))
        self.assertEqual(self.submit(self.body(moved(3), nonce_value=tk.OTHER_NONCE))[0], 202)
        status, reply = self.submit(self.body(moved(4), nonce_value=tk.nonce(77)))
        self.assertEqual((status, reply["codes"][0]["code"]), (429, "rate_limited"), "the total is spent")
        self.clock.advance(61)
        self.assertNotEqual(self.submit(self.body(moved(4), nonce_value=tk.nonce(77)))[0], 429)


class FailureChargeTests(unittest.TestCase):
    def test_charging_rules(self):
        self.assertEqual(failure_for(ScorerError("scorer_down", began=False), 10)["charged_cpu_s"], 0.0)
        self.assertEqual(failure_for(ScorerError("scorer_timeout", began=True), 10)["charged_cpu_s"], 10)
        self.assertEqual(failure_for(ScorerError("scorer_error", began=True, cpu_s=12.5), 10)["charged_cpu_s"], 12.5)
        self.assertEqual(failure_for(ScorerError("scorer_error", began=True, cpu_s=float("nan")), 10)
                         ["charged_cpu_s"], 10)


if __name__ == "__main__":
    unittest.main()
