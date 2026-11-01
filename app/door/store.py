"""Durable door state in one sqlite file: runs, CPU reservations, request counts, events and counters.

Every decision that reads and then writes runs inside one transaction holding the database's write lock (BEGIN
IMMEDIATE, behind one in-process lock), so concurrent requests, worker threads and any second process on the same
file see a single order. The rollback journal (not WAL) is used because the app's data directory may be a network
share.

- A run is bound once: UNIQUE(principal, manifest_id, proposal_key) -> (proposal_sha256, run_id). The same key with
  the same content returns that run; the same key with other content is refused (idempotency_conflict). A refused
  submission never owns a key.
- CPU is reserved when a run is queued (the grant's run envelope, held against both the token's and the grant's
  budget), activated at dispatch and settled when the attempt ends. Used CPU = held + active envelopes + settled
  charges, so queued work can never promise more CPU than the grant has.
- Activation rechecks the CPU in the same transaction (root's review, P1-3): a settlement may charge more than its
  envelope (an overrun, or a conservative charge), so before a held envelope becomes active the token's and the
  grant's used CPU must still be within their caps. When it is not, a stop is persisted (accounting_stops), the run
  stays queued with its charges untouched, and nothing more is activated for that token, or at all for the grant.
- One owner drives attempts (P1-2): the process holding an exclusive lock on <store>.owner. An attempt ends only on a
  definitive outcome. One whose outcome is unknown (the owner restarted mid-call, or the scorer's answer was
  ambiguous) stays `evaluating` with its envelope active, so its slot and CPU stay counted, until the scorer's
  idempotent retry of the same request resolves it or an operator settles it at no less than its envelope.
- Every state change goes through the contract's state machine (open_proposals.contract.states.transition) and writes
  one event; an event's seq is the feed cursor, and a run's version is the seq of its latest event.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from open_proposals.contract.codes import canonical_list, violation
from open_proposals.contract.states import Entry, transition

from .policy import utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  arrival INTEGER NOT NULL,
  manifest_id TEXT NOT NULL,
  principal TEXT NOT NULL,
  short_id TEXT NOT NULL,
  class TEXT NOT NULL,
  operator TEXT NOT NULL,
  case_id TEXT NOT NULL,
  proposal_key TEXT NOT NULL,
  proposal_sha256 TEXT NOT NULL,
  geometry_sha256 TEXT NOT NULL,
  proposal TEXT NOT NULL,
  wire_proxy_mm REAL NOT NULL,
  state TEXT NOT NULL,
  codes TEXT NOT NULL,
  reason TEXT,
  result TEXT,
  metric_c REAL,
  active_c REAL,
  binding_ok INTEGER,
  token_exp INTEGER,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  version INTEGER NOT NULL,
  UNIQUE (principal, manifest_id, proposal_key)
);
CREATE INDEX IF NOT EXISTS runs_by_state ON runs (state, arrival);
CREATE INDEX IF NOT EXISTS runs_by_version ON runs (version);
CREATE INDEX IF NOT EXISTS runs_by_principal ON runs (principal, created_at);
CREATE TABLE IF NOT EXISTS reservations (
  reservation_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE REFERENCES runs (run_id),
  principal TEXT NOT NULL,
  grant_id TEXT NOT NULL,
  amount_cpu_s REAL NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('held', 'active', 'settled', 'released')),
  charged_cpu_s REAL,
  usage TEXT,
  lower_bound_cpu_s REAL,
  owner TEXT,
  created_at REAL NOT NULL,
  settled_at REAL
);
CREATE TABLE IF NOT EXISTS accounting_stops (scope TEXT NOT NULL, key TEXT NOT NULL, short_id TEXT,
                                             reason TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY (scope, key));
CREATE INDEX IF NOT EXISTS reservations_by_principal ON reservations (grant_id, principal, state);
CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, principal TEXT);
CREATE INDEX IF NOT EXISTS requests_by_time ON requests (at);
CREATE INDEX IF NOT EXISTS requests_by_principal ON requests (principal, at);
CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL,
                                   run_id TEXT, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_by_kind ON events (kind, at);
CREATE INDEX IF NOT EXISTS events_by_kind_seq ON events (kind, seq);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""
VISITOR_TABLES = (
    "CREATE TABLE IF NOT EXISTS visitor_totals (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
    "recorded_arrivals INTEGER NOT NULL, unique_observed_handles INTEGER NOT NULL, "
    "arrivals_without_handle INTEGER NOT NULL, through_seq INTEGER NOT NULL)",
    # No type affinity: preserve json_extract's numeric/text grouping and DISTINCT semantics, including legacy rows.
    "CREATE TABLE IF NOT EXISTS visitor_classes (class, arrivals INTEGER NOT NULL)",
    "CREATE UNIQUE INDEX IF NOT EXISTS visitor_classes_key ON visitor_classes "
    "((class IS NULL), COALESCE(class, ''))",
    "CREATE TABLE IF NOT EXISTS visitor_handles (handle PRIMARY KEY)",
)
VISITOR_INSERT = """
CREATE TRIGGER IF NOT EXISTS visitor_arrival_insert AFTER INSERT ON events WHEN NEW.kind = 'arrival'
BEGIN
  INSERT INTO visitor_classes (class, arrivals) VALUES (json_extract(NEW.body, '$.class'), 1)
    ON CONFLICT DO UPDATE SET arrivals = arrivals + 1;
  UPDATE visitor_totals SET
    recorded_arrivals = recorded_arrivals + 1,
    unique_observed_handles = unique_observed_handles + CASE
      WHEN json_extract(NEW.body, '$.visitor_handle') IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM visitor_handles WHERE handle = json_extract(NEW.body, '$.visitor_handle'))
      THEN 1 ELSE 0 END,
    arrivals_without_handle = arrivals_without_handle + (json_extract(NEW.body, '$.visitor_handle') IS NULL),
    through_seq = MAX(through_seq, NEW.seq)
    WHERE singleton = 1;
  INSERT OR IGNORE INTO visitor_handles (handle)
    SELECT json_extract(NEW.body, '$.visitor_handle')
    WHERE json_extract(NEW.body, '$.visitor_handle') IS NOT NULL;
END
"""
VISITOR_EVENT_TABLE = """
CREATE TABLE IF NOT EXISTS visitor_event_totals (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  passive_arrival_events INTEGER NOT NULL,
  declaration_events INTEGER NOT NULL,
  unclassified_arrival_events INTEGER NOT NULL
)
"""
VISITOR_EVENT_INSERT = """
CREATE TRIGGER IF NOT EXISTS visitor_event_kind_insert AFTER INSERT ON events WHEN NEW.kind = 'arrival'
BEGIN
  UPDATE visitor_event_totals SET
    passive_arrival_events = passive_arrival_events +
      (COALESCE(json_type(NEW.body, '$.declaration'), 'null') = 'null'),
    declaration_events = declaration_events +
      (COALESCE(json_type(NEW.body, '$.declaration'), 'null') = 'object'),
    unclassified_arrival_events = unclassified_arrival_events +
      (COALESCE(json_type(NEW.body, '$.declaration'), 'null') NOT IN ('null', 'object'))
    WHERE singleton = 1;
END
"""
LIVE = "state NOT IN ('cancelled', 'expired')"
# A held or active attempt counts at its envelope, or at the CPU an answer reported for it when that is larger.
PROMISED = "MAX(amount_cpu_s, COALESCE(lower_bound_cpu_s, 0))"
QUEUED = ("queued", "held")
EPSILON = 1e-9


def _json(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def label(klass: str, short: str) -> str:
    return f"{klass} · {short}"


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.pause_hook = None       # tests only: called inside admit's transaction, between decision and write
        self.owner_id = None
        self._owner_handle = None
        db = self._connect()
        try:
            db.executescript(SCHEMA)
            self._initialize_visitors(db)
        finally:
            db.close()

    @staticmethod
    def _initialize_visitors(db) -> None:
        """Backfill append-only history once, atomically with installing its insert trigger.

        A trigger also covers older Store processes still writing this file during an upgrade. The summary row is
        the initialization marker: no caller can see partially backfilled counts or rerun the backfill on restart.
        Historical events are never rewritten. Normal reads touch only a bounded page and the materialized counts.
        """
        db.execute("BEGIN IMMEDIATE")
        try:
            for statement in VISITOR_TABLES:
                db.execute(statement)
            if db.execute("SELECT 1 FROM visitor_totals WHERE singleton = 1").fetchone() is None:
                db.execute("INSERT INTO visitor_classes (class, arrivals) "
                           "SELECT json_extract(body, '$.class'), COUNT(*) FROM events "
                           "WHERE kind = 'arrival' GROUP BY json_extract(body, '$.class')")
                db.execute("INSERT INTO visitor_handles (handle) "
                           "SELECT DISTINCT json_extract(body, '$.visitor_handle') FROM events "
                           "WHERE kind = 'arrival' AND json_extract(body, '$.visitor_handle') IS NOT NULL")
                db.execute("INSERT INTO visitor_totals SELECT 1, COUNT(*), "
                           "(SELECT COUNT(*) FROM visitor_handles), "
                           "COALESCE(SUM(json_extract(body, '$.visitor_handle') IS NULL), 0), "
                           "COALESCE(MAX(seq), 0) FROM events WHERE kind = 'arrival'")
            db.execute(VISITOR_INSERT)
            # Separate additive table: older Store initializers keep their original totals-table arity.
            # Its own marker and trigger cover upgrades, restarts and inserts from those older writers.
            db.execute(VISITOR_EVENT_TABLE)
            if db.execute("SELECT 1 FROM visitor_event_totals WHERE singleton = 1").fetchone() is None:
                db.execute("INSERT INTO visitor_event_totals SELECT 1, "
                           "COALESCE(SUM(COALESCE(json_type(body, '$.declaration'), 'null') = 'null'), 0), "
                           "COALESCE(SUM(COALESCE(json_type(body, '$.declaration'), 'null') = 'object'), 0), "
                           "COALESCE(SUM(COALESCE(json_type(body, '$.declaration'), 'null') "
                           "NOT IN ('null', 'object')), 0) FROM events WHERE kind = 'arrival'")
            db.execute(VISITOR_EVENT_INSERT)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    def acquire_owner(self) -> bool:
        """The exclusive right to drive attempts and recover them: a non-blocking lock on <store>.owner, held until
        release_owner or the process ends. Another Store on the same file, in this process or another, cannot take
        it."""
        import fcntl

        if self._owner_handle is not None:
            return True
        handle = open(self.path + ".owner", "a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._owner_handle, self.owner_id = handle, f"{os.getpid()}-{uuid.uuid4().hex[:12]}"
        return True

    def release_owner(self) -> None:
        import fcntl

        if self._owner_handle is not None:
            fcntl.flock(self._owner_handle.fileno(), fcntl.LOCK_UN)
            self._owner_handle.close()
            self._owner_handle, self.owner_id = None, None

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def tx(self):
        """One write transaction under the database's write lock."""
        with self._lock:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                try:
                    yield db
                except BaseException:
                    db.execute("ROLLBACK")
                    raise
                db.execute("COMMIT")
            finally:
                db.close()

    @contextmanager
    def read(self):
        db = self._connect()
        try:
            db.execute("BEGIN")
            yield db
            db.execute("COMMIT")
        finally:
            db.close()

    # ── shared helpers ──────────────────────────────────────────────────────────────────────────────────────────

    def _event(self, db, kind: str, body: dict, now: float, run_id: str | None = None) -> int:
        return db.execute("INSERT INTO events (at, kind, run_id, body) VALUES (?, ?, ?, ?)",
                          (now, kind, run_id, _json(body))).lastrowid

    def _bump(self, db, **deltas) -> None:
        for name, delta in deltas.items():
            db.execute("INSERT INTO counters (name, value) VALUES (?, ?) "
                       "ON CONFLICT (name) DO UPDATE SET value = value + excluded.value", (name, delta))

    def _cpu_used(self, db, grant_id: str, principal: str | None = None) -> float:
        """What the grant (or one token) has promised or spent: each held or active attempt at the larger of its
        envelope and any CPU an answer reported for it (an open attempt's lower bound), plus settled charges. Intake,
        the claim and both remaining-CPU views count it this one way."""
        sql = (f"SELECT COALESCE(SUM(CASE WHEN state IN ('held', 'active') THEN {PROMISED} "
               "WHEN state = 'settled' THEN charged_cpu_s ELSE 0 END), 0) FROM reservations WHERE grant_id = ?")
        args = [grant_id]
        if principal is not None:
            sql += " AND principal = ?"
            args.append(principal)
        return float(db.execute(sql, args).fetchone()[0])

    def _position(self, db, arrival: int) -> int:
        return db.execute("SELECT COUNT(*) FROM runs WHERE state IN ('queued', 'held') AND arrival <= ?",
                          (arrival,)).fetchone()[0]

    def _run_event(self, db, run, state: str, now: float, **extra) -> int:
        body = {"run_id": run["run_id"], "label": label(run["class"], run["short_id"]), "short_id": run["short_id"],
                "class": run["class"], "state": state, **extra}
        return self._event(db, "run", body, now, run["run_id"])

    # ── intake ──────────────────────────────────────────────────────────────────────────────────────────────────

    def note_request(self, *, principal: str, now: float, flood) -> list:
        """The HTTP layer's flood limits, per nonce and in total, over the last minute. A refused request is not
        counted, so one flooding token cannot use up everyone else's share."""
        with self.tx() as db:
            db.execute("DELETE FROM requests WHERE at < ?", (now - 120,))
            found = []
            mine = db.execute("SELECT COUNT(*), MIN(at) FROM requests WHERE principal = ? AND at > ?",
                              (principal, now - 60)).fetchone()
            if mine[0] >= flood.nonce_per_min:
                found.append(violation("rate_limited", retry_after=utc(mine[1] + 60)))
            total = db.execute("SELECT COUNT(*), MIN(at) FROM requests WHERE at > ?", (now - 60,)).fetchone()
            if total[0] >= flood.total_per_min:
                found.append(violation("rate_limited", retry_after=utc(total[1] + 60)))
            if not found:
                db.execute("INSERT INTO requests (at, principal) VALUES (?, ?)", (now, principal))
            return canonical_list(found)

    def note_rejected(self, *, principal: str, short: str, klass: str, codes: list, now: float) -> None:
        """A refused submission: counted and shown as codes only, never stored as a run."""
        with self.tx() as db:
            self._bump(db, attempts=1, rejected=1)
            self._event(db, "attempt", {"label": label(klass, short), "short_id": short, "class": klass,
                                        "outcome": "rejected", "codes": [item["code"] for item in codes]}, now)

    def _quota(self, db, *, policy, principal: str, token_exp: float, now: float) -> list:
        """(scope, violation) for every quota the new run would break. Evaluations per token and per room come from
        the manifest; the queue cap from the manifest; CPU from the signed grant binding."""
        limits, grant, manifest_id = policy.manifest["limits"], policy.grant, policy.manifest_id
        found = []
        windows = (("token_hour", principal, limits["eval_per_account_hour"], 3600),
                   ("token_day", principal, limits["eval_per_account_day"], 86400),
                   ("room_hour", None, limits["eval_room_hour"], 3600),
                   ("room_day", None, limits["eval_room_day"], 86400))
        for scope, who, cap, window in windows:
            sql = f"SELECT COUNT(*), MIN(created_at) FROM runs WHERE manifest_id = ? AND created_at > ? AND {LIVE}"
            args = [manifest_id, now - window]
            if who is not None:
                sql += " AND principal = ?"
                args.append(who)
            count, oldest = db.execute(sql, args).fetchone()
            if count >= cap:
                found.append((scope, violation("rate_limited", retry_after=utc((oldest or now) + window))))
        queued = db.execute("SELECT COUNT(*) FROM runs WHERE manifest_id = ? AND state IN ('queued', 'held')",
                            (manifest_id,)).fetchone()[0]
        if queued >= limits["queue_max"]:
            found.append(("queue", violation("queue_full", retry_after=utc(now + policy.flood.queue_retry_s))))
        envelope = grant.run_reserve_cpu_s
        if self._cpu_used(db, grant.grant, principal) + envelope > grant.token_cpu_s + EPSILON:
            found.append(("token_cpu", violation("budget_exhausted", retry_after=utc(token_exp))))
        if self._cpu_used(db, grant.grant) + envelope > grant.cpu_cap_s + EPSILON:
            found.append(("grant_cpu", violation("budget_exhausted", retry_after=utc(grant.not_after))))
        return found

    def admit(self, *, policy, proposal, klass: str, operator: str, wire_proxy_mm: float, token_exp: float,
              now: float) -> dict:
        """One atomic decision: duplicate, conflict, a policy refusal, or queued with its CPU envelope held."""
        manifest_id, grant, item = policy.manifest_id, policy.grant, proposal.item
        short = proposal.principal[-64:][:4]
        with self.tx() as db:
            bound = db.execute("SELECT run_id, proposal_sha256 FROM runs WHERE principal = ? AND manifest_id = ? "
                               "AND proposal_key = ?", (proposal.principal, manifest_id,
                                                        item["proposal_key"])).fetchone()
            if bound is not None:
                if bound["proposal_sha256"] == proposal.proposal_sha256:
                    self._bump(db, duplicates=1)
                    return {"decision": "duplicate", "run_id": bound["run_id"]}
                codes = [violation("idempotency_conflict")]
                self._bump(db, attempts=1, rejected=1)
                self._event(db, "attempt", {"label": label(klass, short), "short_id": short, "class": klass,
                                            "outcome": "rejected", "codes": ["idempotency_conflict"]}, now)
                return {"decision": "rejected", "codes": codes}
            found = self._quota(db, policy=policy, principal=proposal.principal, token_exp=token_exp, now=now)
            if self.pause_hook is not None:
                self.pause_hook()
            if found:
                codes = canonical_list([entry for _scope, entry in found])
                self._bump(db, attempts=1, legal=1, refused=1)
                self._event(db, "attempt", {"label": label(klass, short), "short_id": short, "class": klass,
                                            "outcome": "refused", "codes": [entry["code"] for entry in codes]}, now)
                return {"decision": "refused", "codes": codes, "limits": sorted({scope for scope, _ in found})}
            transition(Entry(), "accept")
            run = {"run_id": proposal.run_id, "class": klass, "short_id": short, "operator": operator}
            seq = self._run_event(db, run, "queued", now)
            db.execute(
                "INSERT INTO runs (run_id, arrival, manifest_id, principal, short_id, class, operator, case_id, "
                "proposal_key, proposal_sha256, geometry_sha256, proposal, wire_proxy_mm, state, codes, token_exp, "
                "created_at, updated_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', '[]', ?, ?, ?, ?)",
                (proposal.run_id, seq, manifest_id, proposal.principal, short, klass, operator, "cpu-dram",
                 item["proposal_key"], proposal.proposal_sha256, proposal.geometry_sha256, _json(item),
                 wire_proxy_mm, int(token_exp), now, now, seq))
            db.execute("INSERT INTO reservations (reservation_id, run_id, principal, grant_id, amount_cpu_s, state, "
                       "created_at) VALUES (?, ?, ?, ?, ?, 'held', ?)",
                       (str(uuid.uuid4()), proposal.run_id, proposal.principal, grant.grant,
                        grant.run_reserve_cpu_s, now))
            self._bump(db, attempts=1, legal=1, accepted=1)
            return {"decision": "queued", "run_id": proposal.run_id, "position": self._position(db, seq)}

    # ── dispatch ────────────────────────────────────────────────────────────────────────────────────────────────

    def _end_queued(self, db, run, verdict: tuple, now: float) -> None:
        """A queued run that will not be dispatched: expired (no codes) or cancelled (policy codes). Its held
        envelope is released; nothing was charged."""
        event, reason = verdict[0], verdict[1]
        codes = list(verdict[2]) if len(verdict) > 2 else []
        entry = transition(Entry("queued"), event, {"codes": [item["code"] for item in codes]})
        db.execute("UPDATE reservations SET state = 'released', charged_cpu_s = 0, usage = 'never_dispatched', "
                   "settled_at = ? WHERE run_id = ? AND state = 'held'", (now, run["run_id"]))
        seq = self._run_event(db, run, entry.state, now, reason=reason)
        db.execute("UPDATE runs SET state = ?, codes = ?, reason = ?, updated_at = ?, version = ? WHERE run_id = ?",
                   (entry.state, _json(codes), reason, now, seq, run["run_id"]))

    def _stop(self, db, scope: str, key: str, short: str | None, reason: str, now: float) -> None:
        db.execute("INSERT OR IGNORE INTO accounting_stops (scope, key, short_id, reason, at) VALUES (?, ?, ?, ?, ?)",
                   (scope, key, short, reason, now))

    def _over_cap(self, db, grant, principal: str, short: str, now: float):
        """None when both the grant's and the token's used CPU (held and active envelopes plus settled charges) are
        within their caps and no stop stands; otherwise "grant" or "token", with the stop persisted."""
        stopped = {row[0] for row in db.execute(
            "SELECT scope FROM accounting_stops WHERE (scope = 'grant' AND key = ?) OR (scope = 'token' AND key = ?)",
            (grant.grant, principal))}
        if "grant" in stopped or self._cpu_used(db, grant.grant) > grant.cpu_cap_s + EPSILON:
            self._stop(db, "grant", grant.grant, None, "over_cap", now)
            return "grant"
        if "token" in stopped or self._cpu_used(db, grant.grant, principal) > grant.token_cpu_s + EPSILON:
            self._stop(db, "token", principal, short, "over_cap", now)
            return "token"
        return None

    def claim(self, *, check, parallel: int, now: float, grant, owner: str | None = None):
        """Start the oldest queued run that may start, if fewer than `parallel` envelopes are active (across every
        worker and process). check(run) returns None to start it, "wait" to leave it queued, or a verdict that ends
        it. Within the same transaction the token's and the grant's CPU are rechecked: a token over its cap is skipped
        (its runs stay queued), a grant over its cap stops every activation."""
        with self.tx() as db:
            active = db.execute("SELECT COUNT(*) FROM reservations WHERE state = 'active'").fetchone()[0]
            if active >= parallel:
                return None
            for run in db.execute("SELECT * FROM runs WHERE state = 'queued' ORDER BY arrival LIMIT 256").fetchall():
                verdict = check(run)
                if verdict == "wait":
                    return None
                if verdict is not None:
                    self._end_queued(db, run, verdict, now)
                    continue
                over = self._over_cap(db, grant, run["principal"], run["short_id"], now)
                if over == "grant":
                    return None
                if over == "token":
                    continue
                held = db.execute("SELECT * FROM reservations WHERE run_id = ? AND state = 'held'",
                                  (run["run_id"],)).fetchone()
                if held is None:
                    raise RuntimeError("a queued run has no held reservation")
                transition(Entry("queued"), "start", {"reservation_id": held["reservation_id"]})
                db.execute("UPDATE reservations SET state = 'active', owner = ? WHERE reservation_id = ? "
                           "AND state = 'held'", (owner, held["reservation_id"]))
                seq = self._run_event(db, run, "evaluating", now)
                db.execute("UPDATE runs SET state = 'evaluating', updated_at = ?, version = ? WHERE run_id = ?",
                           (now, seq, run["run_id"]))
                return self._claimed(run, held)
            return None

    @staticmethod
    def _claimed(run, held) -> dict:
        return {"run_id": run["run_id"], "principal": run["principal"], "reservation_id": held["reservation_id"],
                "envelope_cpu_s": held["amount_cpu_s"], "proposal": json.loads(run["proposal"]),
                "geometry_sha256": run["geometry_sha256"], "manifest_id": run["manifest_id"]}

    def recovering(self) -> list:
        """The open attempts whose outcome is unknown, oldest first, as claim() returns them."""
        with self.read() as db:
            rows = db.execute("SELECT runs.*, reservations.reservation_id AS held_id, reservations.amount_cpu_s "
                              "FROM runs JOIN reservations ON reservations.run_id = runs.run_id "
                              "WHERE runs.state = 'evaluating' AND reservations.state = 'active' "
                              "AND reservations.usage = 'recovering' ORDER BY runs.arrival").fetchall()
        return [self._claimed(row, {"reservation_id": row["held_id"], "amount_cpu_s": row["amount_cpu_s"]})
                for row in rows]

    def mark_recovering(self, *, run_id: str, reservation_id: str, lower_bound_cpu_s, now: float) -> None:
        """An attempt whose outcome is unknown: it stays evaluating and active (slot and envelope still counted) and
        keeps the largest CPU any answer reported as a lower bound for its settlement."""
        with self.tx() as db:
            held = db.execute("SELECT * FROM reservations WHERE reservation_id = ? AND run_id = ? AND state = 'active'",
                              (reservation_id, run_id)).fetchone()
            if held is None:
                return
            lower = max(held["lower_bound_cpu_s"] or 0.0, lower_bound_cpu_s or 0.0)
            db.execute("UPDATE reservations SET usage = 'recovering', lower_bound_cpu_s = ? WHERE reservation_id = ?",
                       (lower or None, reservation_id))
            if held["usage"] != "recovering":
                run = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                seq = self._run_event(db, run, "evaluating", now, reason="unresolved")
                db.execute("UPDATE runs SET reason = 'unresolved', updated_at = ?, version = ? WHERE run_id = ?",
                           (now, seq, run_id))

    def end_all_queued(self, verdict: tuple, now: float) -> int:
        with self.tx() as db:
            runs = db.execute("SELECT * FROM runs WHERE state = 'queued' ORDER BY arrival").fetchall()
            for run in runs:
                self._end_queued(db, run, verdict, now)
            return len(runs)

    def settle(self, *, run_id: str, reservation_id: str, outcome: dict, now: float) -> bool:
        """End one attempt: settle its envelope, then record the contract transitions. outcome is
        {"kind": "failed", "code", "reason", "charged_cpu_s", "usage"} or
        {"kind": "scored", "charged_cpu_s", "usage", "qualifiers", "reproduced", "replay_code", "result", "metric_c"}.
        Returns False when the attempt was already settled (for instance by recovery after a restart)."""
        with self.tx() as db:
            held = db.execute("SELECT * FROM reservations WHERE reservation_id = ? AND run_id = ?",
                              (reservation_id, run_id)).fetchone()
            run = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if held is None or held["state"] != "active" or run is None or run["state"] != "evaluating":
                return False
            charged, usage = outcome["charged_cpu_s"], outcome["usage"]
            if held["lower_bound_cpu_s"] is not None and held["lower_bound_cpu_s"] > charged:
                charged, usage = held["lower_bound_cpu_s"], "reported_lower_bound"
            db.execute("UPDATE reservations SET state = 'settled', charged_cpu_s = ?, usage = ?, settled_at = ? "
                       "WHERE reservation_id = ? AND state = 'active'", (charged, usage, now, reservation_id))
            entry = Entry("evaluating")
            if outcome["kind"] == "failed":
                entry = transition(entry, "fail", {"codes": [outcome["code"]], "settled": True})
                codes = [violation(outcome["code"])]
                seq = self._run_event(db, run, entry.state, now, reason=outcome["reason"],
                                      codes=[outcome["code"]])
                db.execute("UPDATE runs SET state = ?, codes = ?, reason = ?, updated_at = ?, version = ? "
                           "WHERE run_id = ?", (entry.state, _json(codes), outcome["reason"], now, seq, run_id))
                return True
            qualifiers = list(outcome["qualifiers"])
            entry = transition(entry, "complete", {"codes": qualifiers, "settled": True})
            self._run_event(db, run, entry.state, now)
            entry = transition(entry, "replay", {"reservation_id": reservation_id})
            self._run_event(db, run, entry.state, now)
            if outcome["reproduced"]:
                entry = transition(entry, "reproduced", {"settled": True, "fresh_process": True})
                final = qualifiers
            else:
                entry = transition(entry, "not_reproduced", {"codes": [outcome["replay_code"]], "settled": True})
                final = qualifiers + [outcome["replay_code"]]
            codes = canonical_list([violation(code) for code in final])
            seq = self._run_event(db, run, entry.state, now, codes=[item["code"] for item in codes])
            result = outcome["result"]
            db.execute("UPDATE runs SET state = ?, codes = ?, reason = NULL, result = ?, metric_c = ?, active_c = ?, "
                       "binding_ok = ?, updated_at = ?, version = ? WHERE run_id = ?",
                       (entry.state, _json(codes), _json(result), outcome["metric_c"], result["active_layer_peak_C"],
                        int(result["binding"]["ok"]), now, seq, run_id))
            return True

    def recover(self, now: float) -> int:
        """At startup, by the owner only: an attempt the previous owner left open has an unknown outcome (its remote
        solve may still run, or may have finished with a charge the door has not seen). It is not declared ended: it
        stays evaluating and active, marked recovering, until the scorer's idempotent retry resolves it."""
        with self.tx() as db:
            rows = db.execute("SELECT reservations.reservation_id, reservations.usage, runs.* FROM runs "
                              "JOIN reservations ON reservations.run_id = runs.run_id "
                              "WHERE runs.state = 'evaluating' AND reservations.state = 'active'").fetchall()
            for row in rows:
                db.execute("UPDATE reservations SET usage = 'recovering' WHERE reservation_id = ?",
                           (row["reservation_id"],))
                if row["usage"] != "recovering":
                    seq = self._run_event(db, row, "evaluating", now, reason="unresolved")
                    db.execute("UPDATE runs SET reason = 'unresolved', updated_at = ?, version = ? WHERE run_id = ?",
                               (now, seq, row["run_id"]))
            return len(rows)

    def resolve_interrupted(self, run_id: str, *, charged_cpu_s: float, now: float) -> bool:
        """An operator's settlement of an open attempt, once the remote attempt is known to have ended: failed with
        interrupted, charged no less than its envelope or any reported lower bound."""
        with self.tx() as db:
            held = db.execute("SELECT * FROM reservations WHERE run_id = ? AND state = 'active'",
                              (run_id,)).fetchone()
            run = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if held is None or run is None or run["state"] != "evaluating":
                return False
            if charged_cpu_s < max(held["amount_cpu_s"], held["lower_bound_cpu_s"] or 0.0):
                raise ValueError("an operator settles an open attempt at no less than its envelope")
            db.execute("UPDATE reservations SET state = 'settled', charged_cpu_s = ?, usage = 'operator_resolved', "
                       "settled_at = ? WHERE reservation_id = ?", (charged_cpu_s, now, held["reservation_id"]))
            entry = transition(Entry("evaluating"), "fail", {"codes": ["interrupted"], "settled": True})
            seq = self._run_event(db, run, entry.state, now, reason="interrupted", codes=["interrupted"])
            db.execute("UPDATE runs SET state = ?, codes = ?, reason = 'interrupted', updated_at = ?, version = ? "
                       "WHERE run_id = ?", (entry.state, _json([violation("interrupted")]), now, seq, run_id))
            return True

    def stops(self) -> list:
        with self.read() as db:
            return [{"scope": row["scope"], "short_id": row["short_id"],
                     "grant": row["key"] if row["scope"] == "grant" else None, "reason": row["reason"],
                     "at": row["at"]} for row in db.execute("SELECT * FROM accounting_stops ORDER BY at")]

    def scorer_event(self, state: str, now: float) -> None:
        with self.tx() as db:
            self._event(db, "scorer", {"state": state}, now)

    def note_arrival(self, body: dict, *, now: float, per_min: int) -> bool:
        with self.tx() as db:
            recent = db.execute("SELECT COUNT(*) FROM events WHERE kind = 'arrival' AND at > ?",
                                (now - 60,)).fetchone()[0]
            if recent >= per_min:
                return False
            self._event(db, "arrival", body, now)
            return True

    # ── reads ───────────────────────────────────────────────────────────────────────────────────────────────────

    def run(self, run_id: str):
        with self.read() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                return None, None
            position = self._position(db, row["arrival"]) if row["state"] in QUEUED else None
            return dict(row), position

    def token_usage(self, *, principal: str, grant, manifest_id: str, now: float) -> dict:
        with self.read() as db:
            used = self._cpu_used(db, grant.grant, principal)
            row = db.execute(f"SELECT COALESCE(SUM(CASE WHEN state IN ('held', 'active') THEN {PROMISED} ELSE 0 "
                             "END), 0), COALESCE(SUM(CASE WHEN state = 'settled' THEN charged_cpu_s ELSE 0 END), 0) "
                             "FROM reservations WHERE grant_id = ? AND principal = ?",
                             (grant.grant, principal)).fetchone()
            hour = db.execute(f"SELECT COUNT(*) FROM runs WHERE principal = ? AND manifest_id = ? AND created_at > ? "
                              f"AND {LIVE}", (principal, manifest_id, now - 3600)).fetchone()[0]
            day = db.execute(f"SELECT COUNT(*) FROM runs WHERE principal = ? AND manifest_id = ? AND created_at > ? "
                             f"AND {LIVE}", (principal, manifest_id, now - 86400)).fetchone()[0]
        return {"cpu_s_budget": grant.token_cpu_s, "cpu_s_reserved": round(row[0], 6),
                "cpu_s_charged": round(row[1], 6), "cpu_s_remaining": round(max(0.0, grant.token_cpu_s - used), 6),
                "evaluations_last_hour": hour, "evaluations_last_day": day}

    def runs_by_id(self, run_ids) -> list:
        marks = ", ".join("?" for _ in run_ids)
        with self.read() as db:
            return [dict(row) for row in db.execute(f"SELECT * FROM runs WHERE run_id IN ({marks})", list(run_ids))]

    def changed_runs(self, after: int, limit: int) -> list:
        with self.read() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM runs WHERE version > ? ORDER BY version LIMIT ?", (after, limit)).fetchall()]

    def events(self, after: int, limit: int) -> list:
        with self.read() as db:
            return [dict(row) for row in db.execute(
                "SELECT seq, at, kind, run_id, body FROM events WHERE seq > ? ORDER BY seq LIMIT ?",
                (after, limit)).fetchall()]

    def visitors(self, after: int, limit: int) -> tuple:
        """An indexed arrival page and exact materialized counts from the same read snapshot."""
        with self.read() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT seq, at, body FROM events WHERE kind = 'arrival' AND seq > ? "
                "ORDER BY seq LIMIT ?", (after, limit)).fetchall()]
            classes = {row[0]: row[1] for row in db.execute(
                "SELECT class, arrivals FROM visitor_classes")}
            counts = dict(db.execute("SELECT recorded_arrivals, unique_observed_handles, arrivals_without_handle, "
                                     "through_seq FROM visitor_totals WHERE singleton = 1").fetchone())
            event_counts = dict(db.execute("SELECT passive_arrival_events, declaration_events, "
                                           "unclassified_arrival_events FROM visitor_event_totals "
                                           "WHERE singleton = 1").fetchone())
            return rows, {**counts, **event_counts, "arrivals_by_class": classes}

    def last_seq(self) -> int:
        with self.read() as db:
            return db.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]

    def board_rows(self, grant_id=None) -> tuple:
        """Scored runs without their grids (the ranking and the front need only these columns), the counters, the
        run states and this grant's reservations by state (another grant's are not this one's: warden's P3-3)."""
        with self.read() as db:
            scored = [dict(row) for row in db.execute(
                "SELECT run_id, state, metric_c, active_c, binding_ok, wire_proxy_mm, geometry_sha256 FROM runs "
                "WHERE state IN ('reproduced', 'not_reproduced') AND metric_c IS NOT NULL")]
            counters = {row["name"]: row["value"] for row in db.execute("SELECT name, value FROM counters")}
            states = {row[0]: row[1] for row in db.execute("SELECT state, COUNT(*) FROM runs GROUP BY state")}
            grant_rows = {row[0]: row[1] for row in db.execute(
                f"SELECT state, COALESCE(SUM(CASE WHEN state = 'settled' THEN charged_cpu_s ELSE {PROMISED} END), 0) "
                "FROM reservations WHERE grant_id = ? GROUP BY state", (grant_id,))}
        return scored, counters, states, grant_rows
