"""Run totals, sentilab-door-stats/1 (AGENT-DOOR Amendment 4 rev 2, section 4.4).

Counted from the events the feeds serve (GET /events), up to and including through_seq, in one read snapshot:

    passes              arrival events that carry a purpose (each purpose choice mints one pass)
    submissions         attempt events plus runs: every submission the intake recorded
    results.evaluated   runs with a run event in state evaluated
    results.reproduced  runs with a run event in state reproduced
    results.rejected    attempt events: submissions refused before any run
    results.failed      runs with a run event in state failed

Runs are told apart by run_id; short_id (four hex, display only) is never a key. Visitor counts are #89's (the counts
of GET /visitors) and are never repeated here under other names. An answer is reused for at most CACHE_S seconds.
"""
from __future__ import annotations

import threading

SCHEMA = "sentilab-door-stats/1"
CACHE_S = 5.0
REACHED = ("evaluated", "reproduced", "failed")


def totals(store) -> dict:
    with store.read() as db:
        through = db.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]
        passes = db.execute("SELECT COUNT(*) FROM events WHERE kind = 'arrival' AND seq <= ? "
                            "AND json_extract(body, '$.purpose') IS NOT NULL", (through,)).fetchone()[0]
        attempts = db.execute("SELECT COUNT(*) FROM events WHERE kind = 'attempt' AND seq <= ?",
                              (through,)).fetchone()[0]
        runs = db.execute("SELECT COUNT(DISTINCT run_id) FROM events WHERE kind = 'run' AND seq <= ?",
                          (through,)).fetchone()[0]
        reached = {row[0]: row[1] for row in db.execute(
            "SELECT json_extract(body, '$.state'), COUNT(DISTINCT run_id) FROM events WHERE kind = 'run' AND seq <= ? "
            "AND json_extract(body, '$.state') IN (?, ?, ?) GROUP BY 1", (through, *REACHED))}
    return {"schema": SCHEMA, "through_seq": through, "passes": passes, "submissions": attempts + runs,
            "results": {"evaluated": reached.get("evaluated", 0), "reproduced": reached.get("reproduced", 0),
                        "rejected": attempts, "failed": reached.get("failed", 0)}}


class Totals:
    """totals(store), reused for at most CACHE_S seconds of the given clock (recounted if the clock steps back)."""

    def __init__(self, cache_s: float = CACHE_S):
        self.cache_s = cache_s
        self._lock = threading.Lock()
        self._value, self._at = None, None

    def read(self, store, now: float) -> dict:
        with self._lock:
            if self._value is None or not 0 <= now - self._at < self.cache_s:
                self._value, self._at = totals(store), now
            return {**self._value, "results": dict(self._value["results"])}
