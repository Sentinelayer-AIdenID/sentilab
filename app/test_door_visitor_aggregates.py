"""Offline exact-count and bounded-work controls for the append-only visitor history."""
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from app.door.store import SCHEMA, Store


def original_counts(db):
    """The pre-repair query is an independent oracle, never part of the request path."""
    classes = {row[0]: row[1] for row in db.execute(
        "SELECT json_extract(body, '$.class'), COUNT(*) FROM events "
        "WHERE kind = 'arrival' GROUP BY json_extract(body, '$.class')")}
    handles, without, through = db.execute(
        "SELECT COUNT(DISTINCT json_extract(body, '$.visitor_handle')), "
        "COALESCE(SUM(json_extract(body, '$.visitor_handle') IS NULL), 0), COALESCE(MAX(seq), 0) "
        "FROM events WHERE kind = 'arrival'").fetchone()
    return {"recorded_arrivals": sum(classes.values()), "arrivals_by_class": classes,
            "unique_observed_handles": handles, "arrivals_without_handle": without, "through_seq": through}


class VisitorAggregateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "visitors.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def legacy(self):
        db = sqlite3.connect(self.path)
        db.executescript(SCHEMA)
        # Include SQLite's null/numeric/text cases rather than assuming every historical row has today's shape.
        classes = [None, "", 0, False, 1, 1.0, "1", "likely_human", "unknown"]
        handles = [None, "", 0, False, 1, 1.0, "1", "same", "same"]
        for i, (klass, handle) in enumerate(zip(classes, handles)):
            body = {"class": klass, "visitor_handle": handle, "legacy": "unchanged"}
            db.execute("INSERT INTO events (at, kind, body) VALUES (?, 'arrival', ?)", (i, json.dumps(body)))
            db.execute("INSERT INTO events (at, kind, body) VALUES (?, 'scorer', '{}')", (i,))
        db.execute("INSERT INTO events (at, kind, body) VALUES (20, 'arrival', '{}')")
        db.commit()
        expected = original_counts(db)
        before = db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        db.close()
        return expected, before

    def test_empty_totals_and_backfill_preserve_exact_legacy_semantics_and_bytes(self):
        empty = Store(self.path)
        self.assertEqual(empty.visitors(0, 1), ([], {
            "recorded_arrivals": 0, "arrivals_by_class": {}, "unique_observed_handles": 0,
            "arrivals_without_handle": 0, "through_seq": 0}))
        legacy_path = Path(self.tmp.name) / "legacy.sqlite3"
        self.path = legacy_path
        expected, before = self.legacy()
        for store in (Store(self.path), Store(self.path)):
            self.assertEqual(store.visitors(0, 1)[1], expected)
            with store.read() as db:
                self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM events ORDER BY seq")], before)

    def test_failed_initialization_rolls_back_and_can_retry(self):
        expected, before = self.legacy()
        with patch("app.door.store.VISITOR_INSERT", "invalid sql"), self.assertRaises(sqlite3.OperationalError):
            Store(self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT * FROM events ORDER BY seq").fetchall(), before)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name = 'visitor_totals'").fetchone())
        self.assertEqual(Store(self.path).visitors(0, 10)[1], expected)

    def test_inserts_use_identical_grouping_and_distinct_rules_after_backfill(self):
        self.legacy()
        store = Store(self.path)
        # Direct SQL represents a writer running the old code, which knows nothing about the new tables.
        with store.tx() as db:
            for klass in (None, "", 0, False, 1, 1.0, "1", "likely_human", "unknown"):
                for handle in (None, "", 0, False, 1, 1.0, "1", "same", "new"):
                    db.execute("INSERT INTO events (at, kind, body) VALUES (30, 'arrival', ?)",
                               (json.dumps({"class": klass, "visitor_handle": handle}),))
            expected = original_counts(db)
        self.assertEqual(store.visitors(0, 2)[1], expected)
        self.assertEqual(Store(self.path).visitors(0, 2)[1], expected)

    def test_refusal_rollback_and_nonarrival_events_do_not_inflate_counts(self):
        store = Store(self.path)
        self.assertTrue(store.note_arrival({"class": "unknown", "visitor_handle": "one"}, now=100, per_min=1))
        initial = store.visitors(0, 10)
        self.assertFalse(store.note_arrival({"class": "likely_human", "visitor_handle": "two"},
                                            now=101, per_min=1))
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with store.tx() as db:
                store._event(db, "arrival", {"class": "likely_human", "visitor_handle": "two"}, 200)
                raise RuntimeError("abort")
        store.scorer_event("up", 201)
        self.assertEqual(store.visitors(0, 10), initial)
        other = Store(self.path)
        self.assertTrue(other.note_arrival({"class": "unknown", "visitor_handle": "one"}, now=202, per_min=1))
        self.assertEqual(store.visitors(0, 10)[1], {
            "recorded_arrivals": 2, "arrivals_by_class": {"unknown": 2}, "unique_observed_handles": 1,
            "arrivals_without_handle": 0, "through_seq": 3})

    def test_page_and_counts_share_snapshot_during_another_stores_write(self):
        class PausingStore(Store):
            @contextmanager
            def read(inner):
                with super().read() as db:
                    class Query:
                        def execute(_self, sql, *args):
                            if "FROM visitor_totals" in sql:
                                start_writer.set()
                                self.assertTrue(staged.wait(5), "writer did not stage its arrival")
                            return db.execute(sql, *args)
                    yield Query()

        store = PausingStore(self.path)
        other = Store(self.path)
        store.note_arrival({"class": "unknown"}, now=1, per_min=100)
        start_writer, staged = threading.Event(), threading.Event()
        failures = []

        def write():
            try:
                if not start_writer.wait(5):
                    raise AssertionError("reader did not acquire its snapshot")
                with other.tx() as db:
                    other._event(db, "arrival", {"class": "likely_human", "visitor_handle": "new"}, 2)
                    staged.set()
            except BaseException as exc:
                failures.append(exc)
                staged.set()

        worker = threading.Thread(target=write)
        worker.start()
        try:
            rows, counts = store.visitors(0, 10)
        finally:
            worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(counts["recorded_arrivals"], 1)
        self.assertEqual(counts["through_seq"], rows[-1]["seq"])
        self.assertEqual(other.visitors(0, 10)[1]["recorded_arrivals"], 2)

    def test_indexed_page_and_totals_have_bounded_sql_work_as_history_grows(self):
        class WorkLimitedStore(Store):
            @contextmanager
            def read(inner):
                with super().read() as db:
                    ticks = []
                    statements = []
                    db.set_trace_callback(statements.append)
                    db.set_progress_handler(lambda: ticks.append(1) or len(ticks) > 20, 100)
                    try:
                        yield db
                    finally:
                        db.set_progress_handler(None, 0)
                        inner.last_ticks, inner.last_statements = len(ticks), statements

        store = WorkLimitedStore(self.path)
        expected_sequences = []
        for count in (32, 8192):
            with store.tx() as db:
                for i in range(count):
                    store._event(db, "scorer", {"state": "up"}, i)
                    expected_sequences.append(store._event(
                        db, "arrival", {"class": "unknown", "visitor_handle": str(i % 8)}, i))
            for after in (0, expected_sequences[-3]):
                rows, counts = store.visitors(after, 2)
                self.assertEqual([row["seq"] for row in rows], [n for n in expected_sequences if n > after][:2])
                self.assertEqual(counts["recorded_arrivals"], len(expected_sequences))
                self.assertEqual(counts["unique_observed_handles"], 8)
                self.assertLessEqual(store.last_ticks, 20, "request exceeded 2,000 SQLite VM instructions")
                self.assertFalse(any("json_extract" in sql.lower() for sql in store.last_statements))
            with sqlite3.connect(self.path) as db:
                plan = " ".join(str(row) for row in db.execute(
                    "EXPLAIN QUERY PLAN SELECT seq, at, body FROM events WHERE kind = 'arrival' AND seq > ? "
                    "ORDER BY seq LIMIT ?", (0, 2)))
                self.assertIn("events_by_kind_seq", plan)
                self.assertNotIn("TEMP B-TREE", plan)
                self.assertEqual(store.visitors(0, 2)[1], original_counts(db))


if __name__ == "__main__":
    unittest.main()
