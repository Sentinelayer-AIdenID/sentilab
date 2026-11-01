"""Root's review of PR #81 at d2481e09 (review sha256 e379782a): one test per finding, written to fail first.

P1-1  a returned evaluation and replay are bound to the admitted request before reproduction is reported
P1-2  restart recovery neither takes over another owner's attempt nor frees a slot while the remote attempt is open
P1-3  grant and token CPU are rechecked inside the claim transaction after settlement changes usage
P2-4  a malformed replay keeps its reported CPU as a lower bound and its usage stays unknown, never "measured"
C-1   a token authorizes one durable enqueue: dispatch is gated by the grant and manifest windows, not the token
"""
import http.server
import json
import sqlite3
import threading
import time
import unittest

from app.door import testkit as tk
from app.door.scorer import HttpScorer, ScorerError
from app.door.service import Door
from app.door.store import Store
from app.test_door_dispatch import moved
from app.test_door_feeds import TOKEN, evaluation, receipt

IMAGE = "sha256:" + "0" * 64
RUN = "open-00000000-" + "0" * 32
MANIFEST = "a" * 64
GEOMETRY = "b" * 64


def bound_receipt(cpu_s: float, **edits) -> dict:
    """A receipt as door-scorer's solve() builds it, for RUN's request."""
    value = {**receipt(cpu_s), "geometry_sha256": GEOMETRY, "reservation_id": "res-1", "manifest_id": MANIFEST,
             "input_sha256": {"sample.flp": "1" * 64}, "output_sha256": {"sample.grid.steady": "2" * 64},
             "output_map_sha256": "2" * 64, "worker_pid": 101, "engine_pid": 102, "workspace_id": "solve-aaaa",
             "cleanup_pids": [], "started_at": "2026-11-01T03:00:00Z", "ended_at": "2026-11-01T03:00:04Z"}
    value.update(edits)
    return value


class Scripted(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self._send(*self.server.health)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", "0")))
        self._send(*self.server.answers[self.path.rsplit("/", 1)[1]])

    def _send(self, status, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ReplyBindingTests(unittest.TestCase):
    """P1-1, P2-4 and health: HttpScorer against scripted door-scorer replies."""

    def setUp(self):
        from app.door import intake

        self.dies = intake.compact_dies(tk.SNAPPED)[0]
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Scripted)
        self.score = {**evaluation(self.dies), "run_id": RUN, "receipt": bound_receipt(2.0)}
        self.replay_receipt = bound_receipt(2.5, reservation_id="res-2", worker_pid=201, engine_pid=202,
                                            workspace_id="solve-bbbb")
        self.server.answers = {"score": (200, self.score), "replay": (200, self.good_replay())}
        self.server.health = (200, {"ok": True, "binary_sha256": tk.EVALUATOR_BINARY_SHA256,
                                    "grant_id": "slab-demo-20261101", "image_digest": IMAGE})
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def good_replay(self, **edits) -> dict:
        answer = {**self.score, "state": "reproduced", "receipt": self.replay_receipt,
                  "receipts": [self.score["receipt"], self.replay_receipt], "codes": []}
        answer.update(edits)
        return answer

    def scorer(self, **pins):
        return HttpScorer(self.url, TOKEN, **{"grant_id": "slab-demo-20261101", "image_digest": IMAGE, **pins})

    def request(self):
        return {"run_id": RUN, "token_ref": "2" * 64,
                "proposal": {"schema": "sentilab-open-proposal/1", "manifest_id": MANIFEST,
                             "geometry_sha256": GEOMETRY, "dies": self.dies}}

    def test_a_bound_score_and_distinct_replay_reproduce(self):
        score = self.scorer().score(self.request())
        self.assertEqual((score.replay_fresh_process, score.replay_match, score.replay_code), (True, True, None))
        self.assertEqual((score.cpu_s, score.cpu_known), (4.5, True))

    def test_a_score_for_another_request_is_refused(self):
        for edit in ({"run_id": "open-11111111-" + "1" * 32}, {"receipt": bound_receipt(2.0, manifest_id="c" * 64)},
                     {"receipt": bound_receipt(2.0, geometry_sha256="c" * 64)},
                     {"receipt": bound_receipt(2.0, grant_id="another-grant")},
                     {"receipt": bound_receipt(2.0, image_digest="sha256:" + "9" * 64)},
                     {"receipt": {k: v for k, v in bound_receipt(2.0).items() if k != "reservation_id"}}):
            self.server.answers["score"] = (200, {**self.score, **edit})
            with self.assertRaises(ScorerError, msg=str(list(edit))) as caught:
                self.scorer().score(self.request())
            self.assertEqual((caught.exception.reason, caught.exception.began), ("scorer_error", True))
            self.assertEqual(caught.exception.cpu_s, 2.0, "the reported CPU stays a lower bound")
        self.server.answers["score"] = (200, {k: v for k, v in self.score.items() if k != "wire_proxy_mm"})
        with self.assertRaises(ScorerError):
            self.scorer().score(self.request())

    def test_roots_control_foreign_ids_and_one_execution_never_reproduce(self):
        """Root's control: score and replay for foreign run ids and bindings, one receipt, one worker, one engine and
        one workspace for both phases."""
        foreign = bound_receipt(2.0, manifest_id="c" * 64, geometry_sha256="d" * 64, grant_id="g", image_digest="x")
        self.server.answers["score"] = (200, {**self.score, "run_id": "open-22222222-" + "2" * 32,
                                              "receipt": foreign})
        self.server.answers["replay"] = (200, {**self.score, "run_id": "open-33333333-" + "3" * 32,
                                               "state": "reproduced", "receipt": foreign,
                                               "receipts": [foreign, foreign], "codes": []})
        with self.assertRaises(ScorerError):
            self.scorer().score(self.request())

    def test_a_replay_must_be_a_distinct_execution_of_the_accepted_score(self):
        same = dict(self.score["receipt"])
        cases = (({"receipts": [self.score["receipt"], same], "receipt": same}, "fresh_process_required"),
                 ({"receipts": [bound_receipt(2.0, reservation_id="res-0"), self.replay_receipt]},
                  "reproduction_failed"),
                 ({"run_id": "open-44444444-" + "4" * 32}, "reproduction_failed"),
                 ({"receipts": [self.score["receipt"], {**self.replay_receipt, "geometry_sha256": "e" * 64}]},
                  "reproduction_failed"),
                 ({"receipts": [self.score["receipt"], {**self.replay_receipt,
                                                        "output_sha256": {"sample.grid.steady": "3" * 64}}]},
                  "reproduction_mismatch"),
                 ({"max_chiplet_centre_mean_c": self.score["max_chiplet_centre_mean_c"] + 0.01,
                   "peak_c": self.score["peak_c"] + 0.01}, "reproduction_mismatch"))
        for edit, code in cases:
            self.server.answers["replay"] = (200, self.good_replay(**edit))
            score = self.scorer().score(self.request())
            self.assertFalse(score.replay_fresh_process and score.replay_match, code)
            self.assertEqual(score.replay_code, code, str(list(edit)))

    def test_a_malformed_replay_keeps_its_reported_cpu_as_a_lower_bound(self):
        self.server.answers["replay"] = (200, self.good_replay(
            state="not_reproduced", codes=[{"code": "bogus"}], receipt=bound_receipt(35.0, reservation_id="res-2"),
            receipts=[self.score["receipt"], bound_receipt(35.0, reservation_id="res-2")]))
        score = self.scorer().score(self.request())
        self.assertEqual((score.replay_match, score.replay_code), (False, "reproduction_failed"))
        self.assertEqual((score.cpu_s, score.cpu_known), (37.0, False), "2 measured + 35 reported, never 12")
        self.assertIsNotNone(score.receipt["replay_reply"], "the raw failed reply is kept")
        # A 5xx replay leaves the outcome unknown: the attempt stays open, carrying the same lower bound.
        self.server.answers["replay"] = (500, {"error": "oracle_error", "receipt": {"cpu_s": 35.0}})
        with self.assertRaises(ScorerError) as caught:
            self.scorer().score(self.request())
        self.assertEqual((caught.exception.definitive, caught.exception.cpu_s), (False, 37.0))

    def test_health_pins_the_image_too(self):
        self.assertTrue(self.scorer().health())
        self.assertFalse(self.scorer(image_digest="sha256:" + "9" * 64).health())
        with self.assertRaises(ValueError):
            HttpScorer(self.url, TOKEN, grant_id="slab-demo-20261101")      # an image pin is required


class AccountingCase(tk.DoorCase, unittest.TestCase):
    def reservations(self):
        with sqlite3.connect(self.store.path) as db:
            return {row[0]: row[1:] for row in db.execute(
                "SELECT run_id, state, charged_cpu_s, usage FROM reservations")}


class ClaimAccountingTests(AccountingCase):
    """P1-3: an overrun settled after intake must stop activation within the same claim transaction."""

    def test_a_token_overrun_stops_its_remaining_queued_runs(self):
        self.policy.grant = tk.policy(grant_value=tk.grant(token_cpu_s=20)).grant
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        second = self.submit(self.body(moved(1)))[1]["run_id"]
        other = self.submit(self.body(moved(2), nonce_value=tk.OTHER_NONCE))[1]["run_id"]
        self.scorer.cpu_s = 35.0
        self.assertTrue(self.door.dispatcher.run_once())
        self.assertEqual(self.store.run(first)[0]["state"], "reproduced")
        self.scorer.cpu_s = 2.0
        self.drain()
        self.assertEqual(self.store.run(second)[0]["state"], "queued", "45 CPU-s promised against a 20 CPU-s cap")
        self.assertEqual(self.store.run(other)[0]["state"], "reproduced", "another token is unaffected")
        self.assertEqual(self.reservations()[first][1], 35.0, "the overrun stays charged")
        stops = self.door.board()[1]["accounting_stops"]
        self.assertIn({"scope": "token", "short_id": self.store.run(first)[0]["short_id"], "reason": "over_cap"},
                      [{key: stop[key] for key in ("scope", "short_id", "reason")} for stop in stops])

    def test_a_grant_overrun_stops_every_activation(self):
        self.policy.grant = tk.policy(grant_value=tk.grant(cpu_cap_s=20, token_cpu_s=20)).grant
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        other = self.submit(self.body(moved(1), nonce_value=tk.OTHER_NONCE))[1]["run_id"]
        self.scorer.cpu_s = 35.0
        self.assertTrue(self.door.dispatcher.run_once())
        self.drain()
        self.assertEqual(self.store.run(first)[0]["state"], "reproduced")
        self.assertEqual(self.store.run(other)[0]["state"], "queued")
        self.assertIn("grant", [stop["scope"] for stop in self.door.board()[1]["accounting_stops"]])


class RecoveryTests(AccountingCase):
    """P1-2: one owner drives attempts; a restart reconciles with the scorer instead of declaring an end."""

    def policy_kwargs(self):
        return {"grant_value": tk.grant(parallel=1)}

    def second_door(self, scorer=None):
        door = Door(self.policy, Store(self.store.path), scorer or tk.FakeScorer(self.policy.checker))
        self.addCleanup(door.stop)
        return door

    def test_a_second_startup_cannot_take_over_or_free_an_owned_attempt(self):
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        second = self.submit(self.body(moved(1), nonce_value=tk.OTHER_NONCE))[1]["run_id"]
        self.scorer.release = threading.Event()
        self.door.start()
        deadline = time.monotonic() + 10
        while self.store.run(first)[0]["state"] != "evaluating" and time.monotonic() < deadline:
            time.sleep(0.02)
        intruder = self.second_door()
        intruder.start()
        self.assertFalse(intruder.dispatcher.run_once(), "a second process never claims or recovers")
        self.assertEqual(self.store.run(first)[0]["state"], "evaluating")
        self.assertEqual(self.reservations()[first][0], "active")
        self.assertEqual(self.store.run(second)[0]["state"], "queued", "the parallel=1 slot is still taken")
        self.scorer.cpu_s = 35.0
        self.scorer.release.set()
        deadline = time.monotonic() + 10
        while self.store.run(first)[0]["state"] == "evaluating" and time.monotonic() < deadline:
            time.sleep(0.02)
        self.door.stop()
        self.assertEqual(self.store.run(first)[0]["state"], "reproduced")
        self.assertEqual(self.reservations()[first][1:], (35.0, "measured_overrun"),
                         "the original attempt's larger measured charge is kept")

    def test_restart_reconciles_through_the_scorer_and_holds_the_slot_until_then(self):
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        second = self.submit(self.body(moved(1), nonce_value=tk.OTHER_NONCE))[1]["run_id"]
        claimed = self.store.claim(check=self.door.launch_check, parallel=1, now=self.clock(),
                                   grant=self.policy.grant)
        self.assertEqual(claimed["run_id"], first)
        self.door.stop()            # the owning process dies here without settling; a new one starts on the file
        scorer = tk.FakeScorer(self.policy.checker, healthy=False, cpu_s=35.0)
        restarted = self.second_door(scorer)
        restarted.start(workers=False)
        self.assertEqual(self.store.run(first)[0]["state"], "evaluating", "unresolved: not declared interrupted")
        self.assertEqual(self.reservations()[first][0], "active")
        self.assertFalse(restarted.dispatcher.run_once(), "the scorer is down: nothing resolves, nothing frees")
        self.assertEqual(self.store.run(second)[0]["state"], "queued")
        scorer.healthy, scorer.mode = True, "refused"
        self.clock.advance(6)
        self.assertFalse(restarted.dispatcher.run_once(), "a refusal says nothing about how the original call ended")
        self.assertEqual(self.store.run(first)[0]["state"], "evaluating")
        self.assertEqual(self.store.run(second)[0]["state"], "queued")
        scorer.mode = "ok"
        self.clock.advance(11)
        self.assertTrue(restarted.dispatcher.run_once(), "the scorer's idempotent retry resolves the attempt")
        self.assertEqual(self.store.run(first)[0]["state"], "reproduced")
        self.assertEqual(self.reservations()[first][1], 35.0)
        self.assertEqual([call["run_id"] for call in scorer.calls], [first, first],
                         "the same request each time, so door-scorer answers from its ledger")
        self.assertTrue(restarted.dispatcher.run_once())
        self.assertEqual(self.store.run(second)[0]["state"], "reproduced")

    def test_an_operator_resolves_an_attempt_only_with_at_least_its_envelope(self):
        first = self.submit(self.body(moved(0)))[1]["run_id"]
        self.store.claim(check=self.door.launch_check, parallel=1, now=self.clock(), grant=self.policy.grant)
        with self.assertRaises(ValueError):
            self.store.resolve_interrupted(first, charged_cpu_s=5.0, now=self.clock())
        self.assertTrue(self.store.resolve_interrupted(first, charged_cpu_s=12.0, now=self.clock()))
        row, _ = self.store.run(first)
        self.assertEqual((row["state"], row["reason"]), ("failed", "interrupted"))
        self.assertEqual(self.reservations()[first][1:], (12.0, "operator_resolved"))


class UnknownUsageTests(AccountingCase):
    """P2-4 at the store: CPU that was not fully measured is never recorded as measured."""

    def test_unmeasured_cpu_is_labelled_so(self):
        self.scorer.cpu_known, self.scorer.cpu_s = False, 37.0
        run_id = self.submit(self.body())[1]["run_id"]
        self.drain()
        self.assertEqual(self.reservations()[run_id][1:], (37.0, "unknown_charged_conservatively"))
        self.assertEqual(self.door.status(run_id, tk.NONCE)[1]["result"]["verification"]["cpu"],
                         "unknown_charged_conservatively")


class TokenLifetimeTests(AccountingCase):
    """C-1: the token authorizes one durable enqueue; the grant and manifest windows gate dispatch."""

    def test_a_queued_run_dispatches_after_its_token_expires(self):
        run_id = self.submit(self.body(exp=int(self.clock()) + 60))[1]["run_id"]
        self.assertEqual(self.store.run(run_id)[0]["token_exp"], int(self.clock()) + 60)
        self.clock.advance(120)
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.store.run(run_id)[0]["state"], "reproduced")


class VerificationBlockTests(AccountingCase):
    """The 3D lane's boundary: an explicit verification state on every result."""

    def test_every_result_says_what_was_verified_and_what_was_not(self):
        run_id = self.submit(self.body())[1]["run_id"]
        self.drain()
        result = self.door.status(run_id, tk.NONCE)[1]["result"]
        self.assertEqual(result["verification"], {
            "replay": "reproduced", "replay_code": None, "distinct_execution": True, "receipts_bound": True,
            "binding_ok": True, "binding_basis": ["per_die", "wire"], "active_guard_ok": True,
            "cpu": "measured", "candidate": True,
            "not_claimed": ["beat", "margin", "routed wire", "source acceptance"]})


if __name__ == "__main__":
    unittest.main()
