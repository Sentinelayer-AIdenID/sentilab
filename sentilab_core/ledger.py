"""Fsynced per-run JSONL, one append transaction and authenticated replay prefix."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from .envelope import MAX_BYTES, MAX_REPLAY_BYTES, build, canonical, check_envelope, genesis, validate_run_id, verify


class BrokenLedger(ValueError):
    pass


@contextmanager
def lock(path, *, shared=False, blocking=True):
    try:
        handle = open(path, "rb" if shared else "a+b")
    except FileNotFoundError:
        if not shared:
            raise
        # Imported read-only history may have no writer sidecar. A writer
        # creates its exclusive lock before creating or appending any ledger.
        yield
        return
    with handle:
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


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite JSON number")
    return value


def read_prefix(path, *, run_id, public_keys, version=None):
    """Verify original history versions, or require one explicit version profile.

    JSONL is UTF-8 without a leading BOM on any row. Decode strictly before
    parsing: json.loads(bytes) would silently accept BOMs and UTF-16/32.
    Raw transport evidence is preserved even when decoding/parsing fails.
    """
    rows = []
    incomplete_tail = False
    source_hash = hashlib.sha256()
    with open(path, "rb") as handle:
        if os.fstat(handle.fileno()).st_size > MAX_REPLAY_BYTES:
            raise ValueError("oversize: replay file")
        while raw := handle.readline(MAX_REPLAY_BYTES + 1):
            if handle.tell() > MAX_REPLAY_BYTES:
                raise ValueError("oversize: replay file")
            # An append in progress is not an immutable physical row yet.
            if not raw.endswith(b"\n"):
                incomplete_tail = True
                break
            source_hash.update(raw)
            line = raw[:-1]
            if len(line) > MAX_BYTES:
                rows.append({"error": "oversize JSONL row", "raw": raw,
                             "prefix_hash": source_hash.hexdigest()})
                continue
            row = {"raw": raw, "prefix_hash": source_hash.hexdigest()}
            try:
                value = json.loads(line.decode("utf-8", errors="strict"), object_pairs_hook=_object,
                                   parse_float=_finite_float, parse_constant=_finite_float)
                if not isinstance(value, dict):
                    raise ValueError("envelope is not an object")
                row["envelope"] = value
                data = check_envelope(value, run_id, version=version)
                row["canonical_digest"] = hashlib.sha256(data).hexdigest()
            except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
                row["error"] = str(exc) or "invalid JSONL row"
            rows.append(row)

    def seq(row):
        event = row.get("envelope", {}).get("event")
        value = event.get("seq") if isinstance(event, dict) else None
        return value if type(value) is int and value >= 1 else None

    # Keep physical append order for transport cursors, including retransmissions
    # and malformed evidence. Verification separately sorts and deduplicates.
    source_rows = rows.copy()
    # Canonical-identical retransmissions count once, even with different JSON
    # whitespace. Rejected input is never canonicalized for duplicate detection.
    unique, seen = [], set()
    for row in rows:
        fingerprint = row.pop("canonical_digest", None)
        if fingerprint is not None:
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
        unique.append(row)
    rows = sorted(unique, key=lambda row: (seq(row) if seq(row) is not None else float("inf"),
                                          0 if "error" in row else 1,
                                          str(row.get("envelope", {}).get("hash", ""))))
    by_seq, by_id = {}, {}
    for index, row in enumerate(rows):
        run = row.get("envelope", {}).get("run")
        run_name = run.get("run_id") if isinstance(run, dict) and isinstance(run.get("run_id"), str) else None
        if type(seq(row)) is int:
            by_seq.setdefault((run_name, seq(row)), []).append(index)
        event = row.get("envelope", {}).get("event")
        if isinstance(event, dict) and isinstance(event.get("event_id"), str):
            by_id.setdefault((run_name, event["event_id"]), []).append(index)
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
                verify(envelope, run_id=run_id, public_keys=public_keys, version=version)
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
    return {"prefix": prefix, "rows": rows, "source_rows": source_rows, "last_seq": len(prefix),
            "error": broken, "head_hash": previous, "incomplete_tail": incomplete_tail}


def _check_head(state, head_path):
    if head_path.exists():
        try:
            head = json.loads(head_path.read_text())
            seq = head["seq"]
            if (type(seq) is not int or seq < 1 or seq > len(state["prefix"]) or
                    state["prefix"][seq - 1]["hash"] != head["hash"]):
                state["error"] = state["error"] or "durable head missing or changed"
        except (ValueError, KeyError, TypeError):
            state["error"] = state["error"] or "invalid durable head"
    return state


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
        return _check_head(state, self.head_path)

    @staticmethod
    def _require_sound(state):
        if state["error"]:
            raise BrokenLedger(state["error"])
        if state.get("incomplete_tail"):
            raise BrokenLedger("incomplete JSONL tail")

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
                candidate = {**old, "event": expected}
                if values is None:
                    candidate.pop("values", None)
                else:
                    candidate["values"] = values
                if check_envelope(candidate, self.run["run_id"]) != canonical(old):
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
        return _check_head(read_prefix(path, run_id=run_id, public_keys=public_keys), path.with_suffix(".head.json"))
