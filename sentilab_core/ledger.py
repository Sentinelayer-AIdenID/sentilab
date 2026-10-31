"""Fsynced per-run JSONL, one append transaction and authenticated replay prefix."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .envelope import MAX_BYTES, build, canonical, genesis, validate_run_id, verify


class BrokenLedger(ValueError):
    pass


@contextmanager
def lock(path, *, shared=False, blocking=True):
    with open(path, "a+b") as handle:
        flags = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        fcntl.flock(handle, flags | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_json(path, value):
    """Durable small metadata; never used to rewrite the event ledger."""
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def run_path(root, run_id):
    validate_run_id(run_id)
    root = Path(root).resolve()
    path = (root / f"{run_id}.jsonl").resolve()
    if path.parent != root:
        raise ValueError("run path escapes ledger root")
    return path


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_prefix(path, *, run_id, public_keys):
    """Return all bounded rows for display, but only the verified prefix for project().

    A malformed/oversize line has no reliable sequence; freeze in file order.
    Valid JSON envelopes order by seq, as required by v0.4, even if shuffled.
    """
    rows = []
    with open(path, "rb") as handle:
        while raw := handle.readline(MAX_BYTES + 2):
            if len(raw) > MAX_BYTES + 1 or not raw.endswith(b"\n"):
                while raw and not raw.endswith(b"\n"):
                    raw = handle.readline(MAX_BYTES + 2)
                rows.append({"error": "oversize or incomplete JSONL row"})
                continue
            try:
                value = json.loads(raw, object_pairs_hook=_object)
                if not isinstance(value, dict):
                    raise ValueError("envelope is not an object")
                rows.append({"envelope": value, "raw_digest": hashlib.sha256(raw).hexdigest()})
            except (ValueError, UnicodeError, RecursionError):
                rows.append({"error": "invalid JSONL row"})
    def seq(row):
        event = row.get("envelope", {}).get("event")
        return event.get("seq") if isinstance(event, dict) else None
    if all(type(seq(row)) is int for row in rows):
        rows.sort(key=lambda row: row["envelope"]["event"]["seq"])
    # Byte-identical retransmissions are no-ops. Conflicting groups freeze before
    # every member, independent of their delivery order (v0.5 corrective rule).
    unique, seen = [], set()
    for row in rows:
        raw_digest = row.get("raw_digest")
        if raw_digest is not None and raw_digest in seen:
            continue
        seen.add(raw_digest)
        unique.append(row)
    rows = unique
    by_seq, by_id = {}, {}
    for index, row in enumerate(rows):
        if type(seq(row)) is int:
            by_seq.setdefault(seq(row), []).append(index)
        event = row.get("envelope", {}).get("event")
        if isinstance(event, dict) and isinstance(event.get("event_id"), str):
            by_id.setdefault(event["event_id"], []).append(index)
    for indices in list(by_seq.values()) + list(by_id.values()):
        if len(indices) > 1:
            for index in indices:
                rows[index]["error"] = "conflicting or duplicate sequence/event id"
    prefix, previous, broken = [], genesis(run_id), None
    for row in rows:
        error = row.get("error")
        envelope = row.get("envelope")
        if error is None:
            try:
                verify(envelope, run_id=run_id, public_keys=public_keys)
                if envelope["event"]["seq"] != len(prefix) + 1:
                    raise ValueError("sequence gap or repeat")
                if envelope["prev_hash"] != previous:
                    raise ValueError("prev_hash mismatch")
            except ValueError as exc:
                error = str(exc)
        if broken is None and error is not None:
            broken = error
        row["projectable"] = broken is None
        if broken is None:
            prefix.append(envelope)
            previous = envelope["hash"]
        else:
            row["error"] = error or "after broken prefix"
    return {"prefix": prefix, "rows": rows, "last_seq": len(prefix),
            "error": broken, "head_hash": previous}


class Ledger:
    def __init__(self, root, run, *, public_keys, signer=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.run = run
        self.path = run_path(root, run["run_id"])
        self.lock_path = self.path.with_suffix(".lock")
        self.head_path = self.path.with_suffix(".head.json")
        self.public_keys, self.signer = public_keys, signer
        if self.path.exists():
            with lock(self.lock_path, shared=True):
                self._require_sound(self._read())

    def _read(self):
        if not self.path.exists():
            state = {"prefix": [], "rows": [], "last_seq": 0, "error": None,
                     "head_hash": genesis(self.run["run_id"])}
        else:
            state = read_prefix(self.path, run_id=self.run["run_id"], public_keys=self.public_keys)
        if self.head_path.exists():
            head = json.loads(self.head_path.read_text())
            seq = head["seq"]
            if seq > len(state["prefix"]) or (seq and state["prefix"][seq - 1]["hash"] != head["hash"]):
                state["error"] = state["error"] or "durable head missing or changed"
        return state

    @staticmethod
    def _require_sound(state):
        if state["error"]:
            raise BrokenLedger(state["error"])

    def read(self):
        with lock(self.lock_path, shared=True):
            return self._read()

    def append(self, event_type, body, *, event_id, values=None):
        """Service-internal append. No transport exposes roles or this method.

        A repeated event id returns the original envelope only for identical
        content. Roles are assigned by the service operation, not lab input.
        """
        if "actor_role" in body:
            raise ValueError("invalid caller role")
        if event_type == "lifecycle.transition" and body.get("to") in (
                "accepted", "non_improving_current", "within_margin"):
            raise ValueError("board outcome requires core gate")
        role = "lab" if event_type == "node.create" and body.get("kind") == "candidate" else "core"
        with lock(self.lock_path):
            state = self._read()
            self._require_sound(state)
            return self._append(state, event_type, body, event_id, role, values)

    def append_gate(self, gate, candidate_id, *, event_id):
        with lock(self.root / "admission.lock"):
            return self._gate(gate, candidate_id, event_id=event_id)

    def _gate(self, gate, candidate_id, *, event_id):
        from .projection import board
        with lock(self.lock_path):
            state = self._read()
            self._require_sound(state)
            # A replayed operation returns its recorded outcome; it cannot be
            # re-decided against the board it changed on its first execution.
            for old in state["prefix"]:
                if old["event"]["event_id"] == event_id:
                    if old["event"]["body"]["node"] != candidate_id:
                        raise ValueError("idempotency conflict")
                    return old
            bodies = [e["event"]["body"] for e in state["prefix"] if e["event"]["type"] == "node.create"]
            config = next(b["record"] for b in bodies if b["id"] == self.run["run_id"] + ":run")
            proposal = next(b["record"] for b in bodies if b["id"] == candidate_id)
            measurements = {b["record"]["phase"]: b["record"] for b in bodies
                            if b.get("kind") == "measurement" and b["record"]["candidate_node"] == candidate_id}
            if gate.margin != config["margin"] or gate.reproduction_tolerance != config["reproduction_tolerance"]:
                raise ValueError("gate configuration differs from frozen run")
            inputs = {"geometry_valid": proposal["geometry_valid"], "wire_cap_mm": config["wire_cap_mm"],
                      "binding": proposal["binding"], "evaluation": measurements.get("evaluate"),
                      "reproduction": measurements.get("reproduce"), "stopped": (self.root / "STOP").exists(),
                      "current": board(state["prefix"])}
            decision = gate.decide(**inputs)
            if decision["outcome"] not in ("accepted", "non_improving_current", "within_margin"):
                raise ValueError("candidate is not ready for a board outcome: " + decision["outcome"])
            body = {"node": candidate_id, "to": decision["outcome"], "ai_mode": "AI off",
                    "margin_label": "provisional margin", "record": {"inputs": inputs, "decision": decision}}
            return self._append(state, "lifecycle.transition", body, event_id, "acceptance_gate", None)

    def _append(self, state, event_type, body, event_id, role, values):
        if self.signer is None:
            raise ValueError("append requires the injected service signer")
        for old in state["prefix"]:
            if old["event"]["event_id"] == event_id:
                expected = {"event_id": event_id, "seq": old["event"]["seq"],
                            "type": event_type, "actor_role": role, "body": body}
                if canonical(old["event"]) != canonical(expected) or old.get("values") != values:
                    raise ValueError("idempotency conflict")
                return old
        event = {"event_id": event_id, "seq": state["last_seq"] + 1,
                 "type": event_type, "actor_role": role, "body": body}
        actor = {"agent_id": None, "life_id": None, "grant_id": None,
                 "lab": "gate" if role == "acceptance_gate" else "baseline-sa" if role == "lab" else "core"}
        envelope = build(event=event, run=self.run, actor=actor,
                         prev_hash=state["head_hash"], signer=self.signer, values=values)
        verify(envelope, run_id=self.run["run_id"], public_keys=self.public_keys)
        with open(self.path, "ab") as handle:
            handle.write(canonical(envelope) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        atomic_json(self.head_path, {"seq": event["seq"], "hash": envelope["hash"]})
        return envelope


def replay(root, run_id, *, public_keys):
    """Read-only replay stays usable when append has correctly been refused."""
    path = run_path(root, run_id)
    with lock(path.with_suffix(".lock"), shared=True):
        return read_prefix(path, run_id=run_id, public_keys=public_keys)
