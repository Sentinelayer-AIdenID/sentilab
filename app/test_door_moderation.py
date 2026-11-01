"""Local operator hiding preserves raw evidence while both public projections redact it."""
import contextlib
import io
import json
import math
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from app.door.service import Door
from app.door.store import Store


class DeclarationHideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "door.sqlite3"
        self.store = Store(self.path)
        self.door = Door.__new__(Door)
        self.door.store = self.store
        self.door.scorer_state = SimpleNamespace(snapshot=lambda: {"state": "not_started"})
        self.secret = "private-declaration-canary"
        self.body = {"class": "likely_human", "purpose": "review", "short_id": "abcd",
                     "label": "likely_human · abcd", "visitor_handle": "internal-handle-canary",
                     "declaration": {"notice_version": "sentilab-public-visitor/1", "name": self.secret,
                                     "reason": self.secret + "-reason", "source": "moltbook"}}
        with self.store.tx() as db:
            self.passive = self.store._event(db, "arrival", {"class": "unknown"}, 1)
            self.seq = self.store._event(db, "arrival", self.body, 2)
            self.sibling = self.store._event(db, "arrival", self.body, 3)
            self.nonarrival = self.store._event(db, "scorer", {"state": "up"}, 4)

    def tearDown(self):
        self.tmp.cleanup()

    def raw_state(self):
        with self.store.read() as db:
            return {name: [tuple(row) for row in db.execute("SELECT * FROM " + name)]
                    for name in ("events", "counters", "visitor_totals", "visitor_classes", "visitor_handles",
                                 "visitor_event_totals", "runs", "reservations")}

    def public_rows(self):
        return (self.door.events(None, "200")[1]["events"], self.door.visitors(None, "500")[1]["items"])

    def test_hide_preserves_raw_history_counts_and_visible_sibling(self):
        before = self.raw_state()
        counts = self.door.visitors(None, None)[1]["counts"]
        receipt = self.store.hide_declaration(self.seq, "privacy", now=1000.25)
        self.assertEqual(receipt, {"status": "hidden", "seq": self.seq, "reason": "privacy", "at": 1000.25})
        self.assertEqual(self.raw_state(), before)
        self.assertEqual(self.door.visitors(None, None)[1]["counts"], counts)
        for rows in self.public_rows():
            hidden = next(row for row in rows if row["seq"] == self.seq)
            visible = next(row for row in rows if row["seq"] == self.sibling)
            self.assertIsNone(hidden["declaration"])
            self.assertEqual(hidden["hidden"], "privacy")
            self.assertEqual(hidden["event_kind"], "declaration")
            self.assertEqual(hidden["label"], "likely_human · abcd")
            self.assertNotIn(self.secret, json.dumps(hidden))
            self.assertNotIn("moltbook", json.dumps(hidden))
            self.assertNotIn("internal-handle-canary", json.dumps(rows))
            self.assertEqual(visible["declaration"], self.body["declaration"])

    def test_nested_and_derived_legacy_text_cannot_escape_a_hidden_projection(self):
        poisoned = {key: {"nested": self.secret} for key in ("class", "purpose", "short_id", "label", "extra")}
        poisoned.update(declaration={"name": self.secret, "nested": {"reason": self.secret}},
                        hidden=self.secret, event_kind=self.secret, seq=self.secret, at=self.secret,
                        latest_name=self.secret, latest_purpose=self.secret)
        with self.store.tx() as db:
            seq = self.store._event(db, "arrival", poisoned, 8)
        self.store.hide_declaration(seq, "abuse", now=10)
        for rows in self.public_rows():
            row = next(row for row in rows if row["seq"] == seq)
            self.assertNotIn(self.secret, json.dumps(row))
            self.assertEqual(row["class"], "unknown")
            self.assertEqual(row["label"], "unknown")
            self.assertIsNone(row["purpose"])
            self.assertIsNone(row["short_id"])
            self.assertEqual(row["hidden"], "abuse")

    def test_unique_hidden_text_is_absent_from_complete_public_responses(self):
        canary = "unique-hidden-name-purpose-and-nested-canary"
        body = {"class": "likely_human", "purpose": canary, "short_id": "0123", "label": canary,
                "visitor_handle": canary, "declaration": {"name": canary, "reason": canary,
                                                            "extra": {"nested": canary}},
                "latest_name": canary, "latest_purpose": canary, "extra": {"nested": canary}}
        with self.store.tx() as db:
            seq = self.store._event(db, "arrival", body, 9)
        before = self.raw_state()
        counts = self.door.visitors(None, None)[1]["counts"]
        self.store.hide_declaration(seq, "privacy", now=10)
        for response in (self.door.events(None, "200"), self.door.visitors(None, "500")):
            self.assertEqual(response[0], 200)
            self.assertNotIn(canary, json.dumps(response))
        self.assertEqual(self.raw_state(), before)
        self.assertEqual(self.door.visitors(None, None)[1]["counts"], counts)

    def test_restart_and_repeated_hide_keep_the_first_audit_record(self):
        self.store.hide_declaration(self.seq, "privacy", now=11.5)
        store = Store(self.path)
        self.assertEqual(store.hide_declaration(self.seq, "spam", now=12),
                         {"status": "already_hidden", "seq": self.seq, "reason": "privacy", "at": 11.5})
        self.door.store = store
        self.assertTrue(all(next(row for row in rows if row["seq"] == self.seq)["hidden"] == "privacy"
                            for rows in self.public_rows()))

    def test_concurrent_operators_insert_one_hide_without_changing_history(self):
        before = self.raw_state()
        stores = [Store(self.path) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda store: store.hide_declaration(self.seq, "spam", now=15), stores))
        self.assertEqual(sum(row["status"] == "hidden" for row in replies), 1)
        self.assertEqual(sum(row["status"] == "already_hidden" for row in replies), 7)
        self.assertEqual(self.raw_state(), before)

    def test_invalid_targets_reasons_times_and_sequence_types_never_mutate(self):
        with self.store.tx() as db:
            malformed = [self.store._event(db, "arrival", {"declaration": value}, 5)
                         for value in (None, [], "bad", 0, False)]
        before = self.raw_state()
        for seq in (self.passive, self.nonarrival, 9999, *malformed):
            with self.subTest(seq=seq), self.assertRaisesRegex(ValueError, "not_declaration"):
                self.store.hide_declaration(seq, "privacy", now=20)
        for seq in (True, False, 0, -1, 1.5, "2", 2 ** 63):
            with self.subTest(seq=seq), self.assertRaisesRegex(ValueError, "invalid_seq"):
                self.store.hide_declaration(seq, "privacy", now=20)
        for reason in ("", "privacy\n", self.secret, None, {}, "'); DELETE FROM events;--"):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "invalid_reason"):
                self.store.hide_declaration(self.seq, reason, now=20)
        for now in (True, math.nan, math.inf, -1, "20", 253402300800):
            with self.subTest(now=now), self.assertRaisesRegex(ValueError, "invalid_time"):
                self.store.hide_declaration(self.seq, "privacy", now=now)
        self.assertEqual(self.raw_state(), before)
        with self.store.read() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM hidden_declarations").fetchone()[0], 0)

    def test_empty_legacy_object_is_a_declaration_and_paging_stays_stable(self):
        with self.store.tx() as db:
            seq = self.store._event(db, "arrival", {"class": "unknown", "declaration": {}}, 8)
        self.store.hide_declaration(seq, "other", now=20)
        first = self.door.visitors(None, "1")[1]
        second = self.door.visitors(str(first["next_after"]), "500")[1]
        self.assertEqual([row["seq"] for row in first["items"] + second["items"]],
                         [self.passive, self.seq, self.sibling, seq])
        self.assertEqual(second["items"][-1]["event_kind"], "declaration")
        self.assertEqual(first["counts"], second["counts"])

    def test_database_constraints_refuse_invalid_reason_and_nondeclaration_target(self):
        for seq, reason in ((self.seq, "free-form"), (self.passive, "privacy"), (self.nonarrival, "privacy")):
            with self.subTest(seq=seq, reason=reason), self.assertRaises(sqlite3.IntegrityError):
                with self.store.tx() as db:
                    db.execute("INSERT INTO hidden_declarations VALUES (?, ?, ?)", (seq, reason, 1))

    def test_upgrade_and_old_writer_preserve_rows_and_aggregate_triggers(self):
        with self.store.tx() as db:
            db.execute("DROP TABLE hidden_declarations")
        before = self.raw_state()
        Store(self.path)
        self.assertEqual(self.raw_state(), before)
        self.store.hide_declaration(self.seq, "privacy", now=20)
        # An older writer only appends to events; the new side table never changes its aggregate triggers.
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO events (at, kind, body) VALUES (?, ?, ?)", (30, "arrival", json.dumps(self.body)))
        counts = self.door.visitors(None, None)[1]["counts"]
        self.assertEqual((counts["recorded_arrivals"], counts["declaration_events"]), (4, 3))

    def test_operator_command_is_local_safe_and_requires_an_existing_store(self):
        from app.door.moderation import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["hide", "--store", str(self.path), "--seq", str(self.seq), "--reason", "privacy"])
        self.assertEqual(code, 0)
        reply = json.loads(out.getvalue())
        self.assertEqual(set(reply), {"status", "seq", "reason", "at"})
        self.assertNotIn(self.secret, out.getvalue())
        missing = Path(self.tmp.name) / "typo.sqlite3"
        empty = Path(self.tmp.name) / "other.sqlite3"
        empty.touch()
        for path in (missing, empty):
            before = empty.read_bytes()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["hide", "--store", str(path), "--seq", "2", "--reason", "privacy"]), 1)
            self.assertEqual(json.loads(out.getvalue()), {"status": "refused", "error": "store_unavailable"})
            self.assertFalse(missing.exists())
            self.assertEqual(empty.read_bytes(), before)

    def test_hide_has_no_http_write_route_and_hidden_http_responses_are_no_store(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.door.routes import configure, router
        self.store.hide_declaration(self.seq, "privacy", now=20)
        app = FastAPI()
        app.include_router(router)
        previous = configure(self.door)
        try:
            client = TestClient(app)
            for endpoint in ("events", "visitors"):
                reply = client.get("/api/open/v1/door/" + endpoint)
                self.assertEqual(reply.headers["cache-control"], "no-store")
                rows = reply.json().get("events", reply.json().get("items"))
                self.assertNotIn(self.secret, json.dumps(next(row for row in rows if row["seq"] == self.seq)))
            self.assertEqual(client.post("/api/open/v1/door/hide", json={"seq": self.seq}).status_code, 404)
            self.assertEqual(client.post("/api/open/v1/door/visitors", json={"seq": self.seq}).status_code, 405)
        finally:
            configure(previous)

    def test_operator_argument_errors_do_not_echo_private_arguments(self):
        from app.door.moderation import main
        normal = ["hide", "--store", str(self.path), "--seq", str(self.seq), "--reason", "privacy"]
        for args in (normal + ["--" + self.secret], ["hide", "--seq", self.secret],
                     normal[:-1] + [self.secret], [self.secret]):
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(args=args), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as stopped:
                    main(args)
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(err.getvalue(), "Invalid arguments; use --help.\n")


if __name__ == "__main__":
    unittest.main()
