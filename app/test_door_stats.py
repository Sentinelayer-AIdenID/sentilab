"""Run totals, sentilab-door-stats/1 (AGENT-DOOR Amendment 4 rev 2, section 4.4).

The totals must equal an independent recount of the records the events feed serves, read page by page through the
feed itself, after a history with every kind of record: wall views, purpose passes (two of them sharing a short id),
opted-in declarations, refused and rejected submissions, a duplicate, an idempotency conflict, and runs that were
reproduced, not reproduced and failed. short_id is never a key; visitor counts stay in #89's counts."""
import json
import unittest

from app.door import intake
from app.door import testkit as tk
from app.door.stats import CACHE_S, SCHEMA
from app.test_door_dispatch import moved

# Two nonces whose passes share the short id 0f62 (the first 4 hex of sha256(nonce)): different visitors.
COLLIDING = ("0000000000000049", "00000000000000bb")
ILLEGAL = "36.35.0,36.35.0,54.55.0,36.55.0,17.35.0,73.35.0,73.55.0,17.55.0"


def recount(door) -> dict:
    """The totals, recounted from the events feed's own pages (200 per page), independently of the stats code."""
    events, after = [], 0
    while True:
        status, page, _ = door.events(str(after), "200")
        assert status == 200, page
        events += page["events"]
        if not page["has_more"]:
            break
        after = page["next_after"]
    attempts = [e for e in events if e["kind"] == "attempt"]
    runs = {e["run_id"] for e in events if e["kind"] == "run"}
    reached = lambda state: len({e["run_id"] for e in events if e["kind"] == "run" and e["state"] == state})
    return {"schema": "sentilab-door-stats/1", "through_seq": max((e["seq"] for e in events), default=0),
            "passes": sum(1 for e in events if e["kind"] == "arrival" and e["purpose"] is not None),
            "submissions": len(attempts) + len(runs),
            "results": {"evaluated": reached("evaluated"), "reproduced": reached("reproduced"),
                        "rejected": len(attempts), "failed": reached("failed")}}


class StatsTests(tk.DoorCase, unittest.TestCase):
    http = True

    def arrive(self, **body):
        status, reply, _ = self.door.arrival(json.dumps(body).encode())
        self.assertEqual(status, 204, reply)

    def history(self):
        """Every kind of record the feeds serve, through the door's own code paths."""
        self.arrive(**{"class": "automation"})                                          # a wall view: no pass
        self.arrive(**{"class": "declared_agent", "purpose": "place-chiplets", "nonce": COLLIDING[0],
                       "declaration": {"notice_version": intake.VISITOR_NOTICE, "name": "<b>x</b>", "source": "moltbook"}})
        self.arrive(**{"class": "likely_human", "purpose": "read", "nonce": COLLIDING[1]})
        self.arrive(**{"class": "unknown", "purpose": "review", "nonce": tk.nonce(900)})
        accepted = []
        for nonce in COLLIDING:                 # two strangers whose runs share the short id 0f62
            status, reply = self.submit(self.body(moved(5), nonce_value=nonce))
            self.assertEqual(status, 202, reply)
            self.assertEqual(reply["short_id"], "0f62")
            accepted.append(reply["run_id"])
        for index in range(5):
            status, reply = self.submit(self.body(moved(index), nonce_value=tk.nonce(10 + index)))
            self.assertEqual(status, 202, reply)
            accepted.append(reply["run_id"])
        self.assertEqual(self.submit(self.body(moved(0), nonce_value=tk.nonce(10)))[0], 200)          # duplicate
        self.assertEqual(self.submit(self.body(moved(1), nonce_value=tk.nonce(10), request_key="k-1"))[0], 202)
        self.assertEqual(self.submit(self.body(moved(2), nonce_value=tk.nonce(10), request_key="k-1"))[0], 409)
        self.assertEqual(self.submit(self.body(ILLEGAL, nonce_value=tk.nonce(30)))[0], 422)            # rejected
        for mode in ("ok", "ok", "mismatch", "error"):
            self.scorer.mode = mode
            self.assertEqual(self.drain(1), 1)
        self.scorer.mode = "ok"
        return accepted

    def test_the_totals_equal_a_recount_of_the_events_feed(self):
        self.history()
        status, stats, headers = self.request("GET", "/api/open/v1/door/stats")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("cache-control"), "no-store")
        self.assertEqual(stats, recount(self.door))
        # The history above, by hand: 3 passes (two sharing a short id); 8 runs plus 2 refusals (the conflict and the
        # illegal layout); of the 4 runs drained, 3 were evaluated (2 reproduced: the two strangers sharing 0f62; 1 not
        # reproduced) and 1 failed.
        self.assertEqual(stats["passes"], 3)
        self.assertEqual(stats["submissions"], 10)
        self.assertEqual(stats["results"], {"evaluated": 3, "reproduced": 2, "rejected": 2, "failed": 1})
        reproduced = [item for item in self.door.results(None, "20")[1]["items"] if item["status"] == "reproduced"]
        self.assertEqual([item["short_id"] for item in reproduced], ["0f62", "0f62"])
        self.assertEqual(len({item["id"] for item in reproduced}), 2)
        self.assertEqual(stats["through_seq"], self.store.last_seq())

    def test_submissions_agree_with_the_boards_own_counter(self):
        self.history()
        counts = self.door.board()[1]["counts"]
        stats = self.door.stats()[1]
        self.assertEqual(stats["submissions"], counts["attempts"])
        self.assertEqual(stats["results"]["rejected"], counts["rejected"] + counts["refused"])

    def test_a_short_id_collision_is_two_passes(self):
        for nonce in COLLIDING:
            self.arrive(**{"class": "declared_agent", "purpose": "place-chiplets", "nonce": nonce})
        shorts = [e["short_id"] for e in self.door.events(None, None)[1]["events"]]
        self.assertEqual(shorts, ["0f62", "0f62"])
        self.assertEqual(self.door.stats()[1]["passes"], 2)

    def test_only_these_fields_and_no_visitor_counts(self):
        self.history()
        stats = self.door.stats()[1]
        self.assertEqual(set(stats), {"schema", "through_seq", "passes", "submissions", "results"})
        self.assertEqual(set(stats["results"]), {"evaluated", "reproduced", "rejected", "failed"})
        self.assertEqual(stats["schema"], SCHEMA)
        for value in (stats["through_seq"], stats["passes"], stats["submissions"], *stats["results"].values()):
            self.assertIs(type(value), int)
        text = json.dumps(stats)
        for absent in ("arrivals", "handle", "visitor", "declaration", "short_id", "<b>x</b>", "moltbook", "operator"):
            self.assertNotIn(absent, text)

    def test_an_empty_door_counts_nothing(self):
        self.assertEqual(self.door.stats()[1], {"schema": SCHEMA, "through_seq": 0, "passes": 0, "submissions": 0,
                                                "results": {"evaluated": 0, "reproduced": 0, "rejected": 0,
                                                            "failed": 0}})

    def test_an_answer_is_reused_for_at_most_five_seconds(self):
        first = self.door.stats()[1]
        self.arrive(**{"class": "automation", "purpose": "read", "nonce": tk.nonce(1)})
        self.clock.advance(CACHE_S - 0.5)
        self.assertEqual(self.door.stats()[1], first)
        self.clock.advance(0.5)
        self.assertEqual(self.door.stats()[1]["passes"], 1)
        self.assertEqual(self.door.stats()[1], recount(self.door))
        self.assertEqual(CACHE_S, 5)

    def test_a_caller_cannot_change_the_cached_answer(self):
        first = self.door.stats()[1]
        first["passes"] = 999
        first["results"]["failed"] = 999
        again = self.door.stats()[1]
        self.assertEqual((again["passes"], again["results"]["failed"]), (0, 0))

    def test_a_clock_step_back_never_serves_a_stale_answer(self):
        self.door.stats()
        self.arrive(**{"class": "automation", "purpose": "read", "nonce": tk.nonce(2)})
        self.clock.advance(-1)
        self.assertEqual(self.door.stats()[1]["passes"], 1)


if __name__ == "__main__":
    unittest.main()
