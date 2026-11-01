"""Carter (19:59Z): a proposal is attributed to the agent that declared. Every result record and every run record on
/events carries `visit_arrival`, the seq of the latest arrival of the SAME pass (the submission's token nonce, by its
keyed handle, exactly as a declaration's `arrival`) at or before the submission, or null; never a short-id match.
The results' own `arrival` keeps its meaning (the run's first record). No name or handle is published. Written to
fail first at main 2aab3e28.
"""
import json
import unittest

from app.door import intake
from app.door import testkit as tk
from app.test_door_dispatch import moved

COLLIDING = ("0000000000000049", "00000000000000bb")         # two passes that share the short id 0f62


class VisitTests(tk.DoorCase, unittest.TestCase):
    def arrive(self, nonce: str, klass: str = "declared_agent") -> int:
        status, body, _ = self.door.arrival(json.dumps({"class": klass, "purpose": "place-chiplets",
                                                        "nonce": nonce}).encode())
        self.assertEqual(204, status, body)
        return self.door.events(None, "200")[1]["events"][-1]["seq"]

    def run_for(self, nonce: str, layout: str) -> str:
        status, reply = self.submit(self.body(layout, nonce_value=nonce))
        self.assertEqual(202, status, reply)
        return reply["run_id"]

    def results(self) -> dict:
        return {item["id"]: item for item in self.door.results(None, "20")[1]["items"]}

    def run_events(self, run_id: str) -> list:
        return [event for event in self.door.events(None, "200")[1]["events"]
                if event["kind"] == "run" and event["run_id"] == run_id]

    def test_two_passes_with_colliding_short_ids_get_their_own_visit_arrival(self):
        first = self.arrive(COLLIDING[0])
        second = self.arrive(COLLIDING[1], "automation")
        later_first = self.arrive(COLLIDING[0])                        # the latest arrival of that pass counts
        run_second = self.run_for(COLLIDING[1], moved(0))
        run_first = self.run_for(COLLIDING[0], moved(1))
        self.drain()
        items = self.results()
        self.assertEqual(items[run_first]["short_id"], items[run_second]["short_id"], "the two passes share 0f62")
        self.assertEqual((later_first, second), (items[run_first]["visit_arrival"], items[run_second]["visit_arrival"]))
        self.assertNotEqual(first, later_first)
        for run_id, visit in ((run_first, later_first), (run_second, second)):
            events = self.run_events(run_id)
            self.assertGreaterEqual(len(events), 2, "queued and later states")
            self.assertEqual({visit}, {event["visit_arrival"] for event in events})
            # The results' own `arrival` keeps its meaning: the seq of the run's first record.
            self.assertEqual(events[0]["seq"], items[run_id]["arrival"])

    def test_a_reused_pass_gives_both_runs_the_same_visit_arrival(self):
        visit = self.arrive(COLLIDING[0])
        runs = [self.run_for(COLLIDING[0], moved(5)), self.run_for(COLLIDING[0], moved(6))]
        self.drain()
        items = self.results()
        self.assertEqual([visit, visit], [items[run_id]["visit_arrival"] for run_id in runs])
        self.assertEqual({visit}, {event["visit_arrival"] for run_id in runs for event in self.run_events(run_id)})

    def test_a_same_pass_arrival_stamped_after_the_submission_never_binds(self):
        """Root's P2 on 016afa23 (his retained probe): a concurrent same-pass arrival recorded after the submission's
        captured time (created 1793500002) must not bind to the run (created 1793500000). The pass's earlier arrival
        binds instead, or null when it has none."""
        def concurrent_arrival(nonce):
            self.clock.now = tk.NOW + 2                  # recorded while the submission at tk.NOW is in flight
            seq = self.arrive(nonce)
            self.clock.now = tk.NOW
            return seq

        late_only = concurrent_arrival(COLLIDING[1])
        lone = self.run_for(COLLIDING[1], moved(7))
        earlier = self.arrive(COLLIDING[0])
        late = concurrent_arrival(COLLIDING[0])
        bound = self.run_for(COLLIDING[0], moved(8))
        self.assertEqual((tk.NOW, tk.NOW), (self.store.run(lone)[0]["created_at"], self.store.run(bound)[0]["created_at"]))
        items = self.results()
        self.assertEqual((None, earlier), (items[lone]["visit_arrival"], items[bound]["visit_arrival"]))
        self.assertNotIn(items[bound]["visit_arrival"], (late, late_only))
        self.assertEqual({earlier}, {event["visit_arrival"] for event in self.run_events(bound)})

    def test_a_duplicate_submission_keeps_its_original_visit_arrival(self):
        first = self.arrive(COLLIDING[0])
        run_id = self.run_for(COLLIDING[0], moved(9))
        self.clock.advance(5)
        self.arrive(COLLIDING[0])
        status, reply = self.submit(self.body(moved(9), nonce_value=COLLIDING[0]))
        self.assertEqual((200, True, run_id), (status, reply["duplicate"], reply["run_id"]))
        self.assertEqual(first, self.results()[run_id]["visit_arrival"])

    def test_an_arrival_after_the_submission_is_not_its_visit(self):
        run_id = self.run_for(COLLIDING[0], moved(2))
        self.arrive(COLLIDING[0])
        self.assertIsNone(self.results()[run_id]["visit_arrival"])

    def test_a_run_with_no_arrival_gets_null(self):
        self.arrive(COLLIDING[1])                                     # another pass's arrival is not this run's
        run_id = self.run_for(COLLIDING[0], moved(3))
        self.drain()
        self.assertIsNone(self.results()[run_id]["visit_arrival"])
        self.assertEqual({None}, {event["visit_arrival"] for event in self.run_events(run_id)})
        self.assertIsNone(self.door.status(run_id, COLLIDING[0])[1]["visit_arrival"])

    def test_neither_handle_nor_a_name_appears_in_any_feed(self):
        self.arrive(COLLIDING[0])
        declaration = {"notice_version": intake.VISITOR_NOTICE, "name": "canary-declared-name"}
        status, body, _ = self.door.arrival(json.dumps({"class": "declared_agent", "nonce": COLLIDING[0],
                                                        "declaration": declaration}).encode())
        self.assertEqual(204, status, body)
        run_id = self.run_for(COLLIDING[0], moved(4))
        self.drain()
        with self.store.read() as db:
            stored = " ".join(row[0] for row in db.execute("SELECT body FROM events"))
        self.assertIn("pass_handle", stored)
        self.assertIn("visitor_handle", stored)
        runs = [self.door.results(None, "20")[1], self.door.board()[1], self.door.status(run_id, COLLIDING[0])[1]]
        run_events = [event for event in self.door.events(None, "200")[1]["events"] if event["kind"] != "arrival"]
        everything = runs + [self.door.events(None, "200")[1], self.door.visitors(None, "500")[1]]
        for name in ("pass_handle", "visitor_handle", COLLIDING[0]):
            self.assertNotIn(name, json.dumps(everything))
        # The declared name stays on the declaration's own record: no run record carries it.
        self.assertNotIn("canary-declared-name", json.dumps(runs + run_events))


if __name__ == "__main__":
    unittest.main()
