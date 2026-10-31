"""Local append-only memory, keyed by scope and supported by a signed ledger.

The host binds a tenant to its own ledger root and held-out policy. These are
trusted configuration, never caller-supplied authorization. No memory is science
acceptance; recall is a snapshot of the current authenticated ledger projection.
"""
import json
import os
from pathlib import Path

from .envelope import MAX_BYTES, MAX_REPLAY_BYTES, canonical, check_caps, digest, validate_run_id
from .ledger import BrokenLedger, _object, atomic_json, lock, replay
from .projection import project


SCOPE_FIELDS = ("tenant", "run", "arm", "family", "seed")


def _parse(raw):
    if len(raw) > MAX_BYTES + 1:
        raise ValueError("oversize memory JSON")
    try:
        value = json.loads(raw, object_pairs_hook=_object)
    except RecursionError as exc:
        raise ValueError("invalid memory JSON nesting") from exc
    check_caps(value)
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("expected a nonempty name of at most 128 characters")
    value.encode("utf-8")
    return value


def scope_key(scope):
    if not isinstance(scope, dict) or set(scope) != set(SCOPE_FIELDS):
        raise ValueError("scope requires exactly tenant, run, arm, family, seed")
    for field in SCOPE_FIELDS[:-1]:
        _name(scope[field])
    validate_run_id(scope["run"])
    if type(scope["seed"]) is not int or not 0 <= scope["seed"] <= 9007199254740991:
        raise ValueError("scope seed must be a nonnegative safe integer")
    return tuple(scope[field] for field in SCOPE_FIELDS)


def _item(item, evidence_refs):
    if not isinstance(item, dict) or "id" not in item:
        raise ValueError("memory item requires an id")
    _name(item["id"])
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise ValueError("evidence_refs must be a nonempty list")
    for ref in evidence_refs:
        _name(ref)
    if len(set(evidence_refs)) != len(evidence_refs):
        raise ValueError("duplicate evidence reference")
    check_caps({"item": item, "evidence_refs": evidence_refs})
    return json.loads(canonical(item)), sorted(evidence_refs)


class MemoryStore:
    def __init__(self, root, *, ledger_root, public_keys, tenant, held_out_families):
        self.root = Path(root).resolve()
        self.ledger_root = Path(ledger_root).resolve()
        self.public_keys = dict(public_keys)
        self.tenant = _name(tenant)
        if not isinstance(held_out_families, (list, tuple, set, frozenset)):
            raise ValueError("held_out_families must be an explicit collection")
        self.held_out_families = frozenset(_name(family) for family in held_out_families)

    def _path(self, scope):
        key = scope_key(scope)
        if scope["tenant"] != self.tenant:
            raise ValueError("scope tenant differs from host tenant")
        # Hash the typed tuple, not concatenated names: separators, case and seed
        # types cannot alias. Persist the original scope and verify it on read.
        path = (self.root / (digest(list(key)) + ".jsonl")).resolve()
        if path.parent != self.root:
            raise ValueError("memory path escapes root")
        for suffix in (".lock", ".head.json"):
            if path.with_suffix(suffix).resolve().parent != self.root:
                raise ValueError("memory metadata path escapes root")
        return path

    def _records(self, path, scope):
        rows = []
        previous = digest(list(scope_key(scope)))
        if path.exists():
            with path.open("rb") as handle:
                if os.fstat(handle.fileno()).st_size > MAX_REPLAY_BYTES:
                    raise ValueError("oversize memory log")
                while raw := handle.readline(MAX_BYTES + 2):
                    if len(raw) > MAX_BYTES + 1 or not raw.endswith(b"\n"):
                        raise ValueError("invalid memory log row")
                    row = _parse(raw)
                    if not isinstance(row, dict) or set(row) != {
                            "v", "seq", "scope", "item", "evidence_refs", "ledger_head", "prev_hash", "hash"}:
                        raise ValueError("invalid memory record")
                    payload = {key: value for key, value in row.items() if key != "hash"}
                    if (row["v"] != "sentilab-memory/1" or row["scope"] != scope or
                            type(row["seq"]) is not int or row["seq"] != len(rows) + 1 or
                            row["prev_hash"] != previous or row["hash"] != digest(payload)):
                        raise ValueError("broken memory audit chain")
                    scope_key(row["scope"])
                    _item(row["item"], row["evidence_refs"])
                    anchor = row["ledger_head"]
                    if (not isinstance(anchor, dict) or set(anchor) != {"seq", "hash"} or
                            type(anchor["seq"]) is not int or anchor["seq"] < 1 or
                            not isinstance(anchor["hash"], str)):
                        raise ValueError("invalid memory ledger anchor")
                    if any(old["item"]["id"] == row["item"]["id"] for old in rows):
                        raise ValueError("duplicate memory id")
                    rows.append(row)
                    previous = row["hash"]
        head_path = path.with_suffix(".head.json")
        if head_path.exists():
            with head_path.open("rb") as handle:
                head = _parse(handle.read(MAX_BYTES + 2))
            if (not isinstance(head, dict) or type(head.get("seq")) is not int or
                    not 1 <= head["seq"] <= len(rows) or
                    rows[head["seq"] - 1]["hash"] != head.get("hash")):
                raise ValueError("durable memory head missing or changed")
        return rows

    def _projection(self, scope):
        state = replay(self.ledger_root, scope["run"], public_keys=self.public_keys)
        if state["error"]:
            raise BrokenLedger(state["error"])
        if not state["prefix"]:
            raise ValueError("memory needs nonempty ledger evidence")
        for envelope in state["prefix"]:
            run = envelope["run"]
            if any(run.get(key) != scope[field] for key, field in (
                    ("run_id", "run"), ("arm", "arm"), ("family", "family"), ("seed", "seed"))):
                raise ValueError("ledger differs from memory scope")
        try:
            projection = project(state["prefix"])
        except (KeyError, TypeError, RecursionError) as exc:
            raise ValueError("invalid ledger projection") from exc
        return state, projection["nodes"]

    @staticmethod
    def _invalid_refs(refs, nodes):
        return {ref: nodes.get(ref, {}).get("validity", "missing") for ref in refs
                if nodes.get(ref, {}).get("validity") != "valid"}

    def write(self, scope, item, evidence_refs):
        path = self._path(scope)
        if scope["family"] in self.held_out_families:
            raise ValueError("held-out family writes are refused")
        item, refs = _item(item, evidence_refs)
        self.root.mkdir(parents=True, exist_ok=True)
        with lock(path.with_suffix(".lock")):
            records = self._records(path, scope)
            state, nodes = self._projection(scope)
            for old in records:
                self._check_anchor(old, state)
            if self._invalid_refs(refs, nodes):
                raise ValueError("memory evidence must currently be valid")
            for old in records:
                if old["item"]["id"] == item["id"]:
                    if old["item"] == item and old["evidence_refs"] == refs:
                        self._check_anchor(old, state)
                        return old
                    raise ValueError("memory idempotency conflict")
            row = {"v": "sentilab-memory/1", "seq": len(records) + 1, "scope": dict(scope),
                   "item": item, "evidence_refs": refs,
                   "ledger_head": {"seq": state["last_seq"], "hash": state["head_hash"]},
                   "prev_hash": records[-1]["hash"] if records else digest(list(scope_key(scope)))}
            row["hash"] = digest(row)
            raw = check_caps(row)
            with path.open("ab") as handle:
                handle.write(raw + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            atomic_json(path.with_suffix(".head.json"), {"seq": row["seq"], "hash": row["hash"]})
            return row

    def audit(self, scope):
        """All immutable writes in exactly this scope, even with broken evidence."""
        path = self._path(scope)
        if not self.root.exists():
            return []
        with lock(path.with_suffix(".lock"), shared=True):
            return self._records(path, scope)

    @staticmethod
    def _check_anchor(record, state):
        anchor = record["ledger_head"]
        if (anchor["seq"] > len(state["prefix"]) or
                state["prefix"][anchor["seq"] - 1]["hash"] != anchor["hash"]):
            raise BrokenLedger("memory evidence history was replaced")

    def _current(self, scope):
        records = self.audit(scope)
        if not records:
            return []
        state, nodes = self._projection(scope)
        current = []
        for record in records:
            self._check_anchor(record, state)
            current.append((record, self._invalid_refs(record["evidence_refs"], nodes)))
        return current

    def recall(self, scope, query=""):
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        # No ranking model: stable append order and literal, case-insensitive
        # substring search over the canonical JSON item.
        return [record for record, invalid in self._current(scope) if not invalid and
                query.casefold() in canonical(record["item"]).decode().casefold()]

    def invalidate(self, scope):
        """Report ledger-driven invalidation; never overwrite historical writes."""
        return [{"id": record["item"]["id"], "invalid_evidence": invalid}
                for record, invalid in self._current(scope) if invalid]
