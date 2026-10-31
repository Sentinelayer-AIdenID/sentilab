"""The reference validator: the intake's checks in order (DESIGN rev 3 sections 5.3 and 5.4), the offline checker's,
and the cross-field rules every record must meet. No network, no solver, no clock.

  0. attempt    a note starting with "{", "```" or "sentilab-open-sealed/1" (its first bytes) is an attempt;
                anything else is chat: ignored, no receipt
  1. transport  unattributable and edited_before_ingest (the row); oversize (4,096 bytes plaintext, 8,192 sealed);
                not_utf8; a sealed note's header, key version and armour, then the opener: unsealable; a plaintext
                that declares "visibility": "private": private_requires_sealed
  2. envelope   one object, bare or in one ```json fence (a sealed plaintext: bare only): too_deep (pre-scan),
                malformed_json, duplicate_key, nonfinite_number; the "schema" value picks the object; then
                unknown_field and schema_invalid
  1b. key       the transport key recomputed from the row and the parsed content: transport_key_mismatch
  3. manifest   unknown_manifest, manifest_mismatch (the thread's manifest), not_open_yet / manifest_closed,
                terms_not_accepted
  4. hash       geometry_hash_mismatch
  5. catalogue  die_count, die_order, then per die rotation_not_allowed and out_of_frame
  6. lattice    exact integers
  7. layout     the OP-F7 seam (TapGeometry.layout_violations and keepouts): margin, halo_overlap, min_spacing,
                keepout; run only when every die maps onto its catalogue entry

Stages 1, 2 and 1b each stop the check when they find anything: nothing is read past a transport or envelope
failure. Stages 3 to 7 report every violation together, except that a manifest the thread does not name stops
there. Without a layout checker a clean layout is "contract_valid", never "legal"; without an opener a sealed note
whose header is valid is "sealed_unopened".
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable

from . import canonical as hashes
from .codes import canonical_list, fields_ok, violation
from .labels import LISTS, label_for
from .predicates import LABELS
from .schemas import POSTED, def_is_valid, schema_violations
from .states import FAILURE_CODES, POLICY_CODES, QUALIFIER_CODES, REJECTION_CODES, REPRODUCTION_CODES

MAX_PLAINTEXT_BYTES = 4096
MAX_SEALED_BYTES = 8192
MAX_DEPTH = 4
SEALED_PREFIX = b"sentilab-open-sealed/1"
SEALED_LINE = re.compile(rb"sentilab-open-sealed/1 ([0-9a-f]{64}) ([1-9][0-9]{0,5})\n")
ARMOR_BEGIN = b"-----BEGIN AGE ENCRYPTED FILE-----\n"
FENCE = re.compile(r"```json[ \t]*\r?\n(.*)\r?\n```\Z", re.DOTALL)
LAYOUT_CODES = frozenset({"margin", "halo_overlap", "min_spacing", "keepout"})
SEALABLE = frozenset({"proposal", "check-request"})
GEOMETRIC = frozenset({"proposal", "check-request"})
WITH_TERMS = frozenset({"proposal", "publish"})

LayoutChecker = Callable[[dict, dict], Iterable[dict]]
Opener = Callable[[bytes, dict, int], bytes]


class Unopenable(Exception):
    """Raised by an opener that cannot decrypt a note. Any other exception is a fault and propagates."""


@dataclass(frozen=True)
class Reply:
    """What the intake read from Senti's row: all server-set, never anything from the note."""
    room: str
    actor_user_id: str | None
    actor_kind: str | None          # "agent" or "human", as Senti stamped it
    actor_id: str | None            # the agent id on an agent row
    idempotency_key: str | None
    message_revision: int
    edited_at: str | None


@dataclass(frozen=True)
class Outcome:
    outcome: str        # ignored | rejected | sealed_unopened | contract_valid | legal
    violations: tuple = ()
    kind: str | None = None
    item: dict | None = None
    content_sha256: str | None = None
    geometry_sha256: str | None = None
    sealed: bool = False

    def summary(self) -> dict:
        return {"outcome": self.outcome, "codes": list(self.violations), "kind": self.kind,
                "content_sha256": self.content_sha256, "geometry_sha256": self.geometry_sha256,
                "sealed": self.sealed}


def _rejected(found, *, kind=None, item=None, content=None, geometry=None, sealed=False) -> Outcome:
    return Outcome("rejected", tuple(canonical_list(found)), kind, item, content, geometry, sealed)


def is_attempt(note: bytes) -> bool:
    return note.startswith(b"{") or note.startswith(b"```") or note.startswith(SEALED_PREFIX)


def _row(reply: Reply) -> list:
    found = []
    slot_ok = (reply.actor_kind == "human" and reply.actor_id is None
               or reply.actor_kind == "agent" and isinstance(reply.actor_id, str) and reply.actor_id != "")
    if not reply.actor_user_id or not slot_ok:
        found.append(violation("unattributable"))
    if reply.message_revision != 1 or reply.edited_at is not None:
        found.append(violation("edited_before_ingest"))
    return found


def _size_and_text(note: bytes, cap: int) -> list:
    found = []
    if len(note) > cap:
        found.append(violation("oversize", size_bytes=len(note)))
    try:
        note.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        found.append(violation("not_utf8"))
    return found


def _too_deep(text: str) -> bool:
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            if depth > MAX_DEPTH:
                return True
        elif char in "}]":
            depth -= 1
    return False


def _json(text: str, *, fenced: bool):
    """(object, violations). A fence is allowed only around a plaintext note."""
    text = text.strip(" \t\r\n")
    if fenced and text.startswith("```"):
        match = FENCE.match(text)
        if not match:
            return None, [violation("malformed_json")]
        text = match.group(1).strip(" \t\r\n")
    if not text.startswith("{"):
        return None, [violation("malformed_json")]
    if _too_deep(text):
        return None, [violation("too_deep")]
    flags = set()

    def pairs(items):
        if len({key for key, _ in items}) != len(items):
            flags.add("duplicate_key")
        return dict(items)

    def constant(_name):
        flags.add("nonfinite_number")
        return 0

    def floating(literal):
        value = float(literal)
        if not math.isfinite(value):
            flags.add("nonfinite_number")
            return 0.0
        return value

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
    except (ValueError, RecursionError):
        return None, [violation("malformed_json")]
    if not isinstance(value, dict):
        return None, [violation("malformed_json")]
    if flags:
        return None, [violation(code) for code in flags]
    return value, []


def _unseal(note: bytes, *, manifests, target_id, opener):
    """(plaintext object, violations, opened). The header binds the note to the thread's manifest and its key
    version; the opener decrypts with that key version only. A note that fails to open is never re-read as
    plaintext."""
    match = SEALED_LINE.match(note)
    if not match:
        return None, [violation("unsealable")], False
    named, key_version = match.group(1).decode("ascii"), int(match.group(2))
    if named not in manifests:
        return None, [violation("unknown_manifest")], False
    if named != target_id:
        return None, [violation("manifest_mismatch", path="/manifest_id")], False
    sealing = manifests[named]["sealing"]
    armour = note[match.end():]
    if sealing["recipient"] is None or sealing["key_version"] != key_version or not armour.startswith(ARMOR_BEGIN):
        return None, [violation("unsealable")], False
    if opener is None:
        return None, [], False
    try:
        plaintext = opener(armour, manifests[named], key_version)
    except Unopenable:
        return None, [violation("unsealable")], False
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("an opener returns the plaintext bytes")
    plaintext = bytes(plaintext)
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        return None, [violation("oversize", size_bytes=len(plaintext))], True
    try:
        text = plaintext.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, [violation("unsealable")], True
    value, found = _json(text, fenced=False)
    if found and found[0]["code"] == "malformed_json":
        return None, [violation("unsealable")], True
    if found:
        return None, found, True
    if kind_of(value) not in SEALABLE:
        return None, [violation("unsealable")], True
    return value, [], True


def kind_of(value: dict):
    """The posted object's kind from its "schema" value; None for anything else, a non-string included."""
    schema = value.get("schema")
    return POSTED.get(schema) if isinstance(schema, str) else None


def _admission(manifest: dict, manifest_id: str, admission) -> list:
    if admission is None:
        return []
    state = admission.get(manifest_id, "not_open_yet")
    if state == "closed":
        return [violation("manifest_closed")]
    if state != "open" or manifest["status"] != "signed":
        return [violation("not_open_yet")]                  # only a signed manifest can ever be open
    return []


def _off_lattice(value: int, step: int) -> int:
    rest = value % step
    return min(rest, step - rest)


def _geometry(item: dict, manifest: dict):
    """Stages 4 to 6. Returns (server geometry hash, violations, whether every die maps onto its catalogue entry)."""
    server_hash = hashes.geometry_sha256(item, manifest)
    found = []
    if server_hash != item["geometry_sha256"]:
        found.append(violation("geometry_hash_mismatch"))
    dies, catalogue = item["dies"], manifest["dies"]
    if len(dies) != len(catalogue):
        found.append(violation("die_count", count=len(dies)))
    misplaced = [index for index, die in enumerate(dies) if die["die"] != index]
    if misplaced:
        found.append(violation("die_order", dies=misplaced))
    if len(dies) != len(catalogue) or misplaced:
        return server_hash, found, False
    frame, step = manifest["fixture"]["frame_um"], manifest["legality"]["lattice_um"]
    mapped = True
    for index, die in enumerate(dies):
        if die["rot_deg"] not in catalogue[index]["rot_deg"]:
            found.append(violation("rotation_not_allowed", dies=[index]))
            mapped = False
        outside = max(die["x_um"] - frame, die["y_um"] - frame, 0)
        if outside:
            found.append(violation("out_of_frame", dies=[index], amount_um=outside))
        off = max(_off_lattice(die["x_um"], step), _off_lattice(die["y_um"], step))
        if off:
            found.append(violation("lattice", dies=[index], amount_um=off))
    return server_hash, found, mapped


def _layout(item: dict, manifest: dict, checker: LayoutChecker) -> list:
    found = list(checker(item, manifest))
    for entry in found:
        if not (fields_ok(entry) and entry["code"] in LAYOUT_CODES and def_is_valid("violation", entry)):
            raise ValueError("the layout checker returned something outside the seam's contract")
    return found


def _object(value: dict, *, sealed, reply, manifests, target_id, admission, layout_checker) -> Outcome:
    """Stages 2 (schema), 1b and 3 to 7 on a parsed object."""
    kind = kind_of(value)
    if kind is None:
        return _rejected([violation("schema_invalid", path="/schema", keyword="enum")], sealed=sealed)
    found = schema_violations(kind, value)
    if found:
        return _rejected(found, kind=kind, sealed=sealed)
    content = hashes.content_sha256(value)
    if reply is not None and reply.idempotency_key != hashes.transport_key_for(
            value, room=reply.room, account=reply.actor_user_id, actor_kind=reply.actor_kind,
            actor_id=reply.actor_id):
        return _rejected([violation("transport_key_mismatch")], kind=kind, item=value, content=content, sealed=sealed)
    if value["manifest_id"] not in manifests:
        return _rejected([violation("unknown_manifest")], kind=kind, item=value, content=content, sealed=sealed)
    if value["manifest_id"] != target_id:
        return _rejected([violation("manifest_mismatch", path="/manifest_id")], kind=kind, item=value,
                         content=content, sealed=sealed)
    manifest = manifests[target_id]
    found = _admission(manifest, target_id, admission)
    if kind in WITH_TERMS and value["terms"] not in manifest["terms"]["accepted_versions"]:
        found.append(violation("terms_not_accepted"))
    geometry_sha, checked = None, False
    if kind in GEOMETRIC:
        geometry_sha, more, mapped = _geometry(value, manifest)
        found += more
        checked = mapped and layout_checker is not None
        if checked:
            found += _layout(value, manifest, layout_checker)
    if found:
        return _rejected(found, kind=kind, item=value, content=content, geometry=geometry_sha, sealed=sealed)
    outcome = "legal" if checked else "contract_valid"
    return Outcome(outcome, (), kind, value, content, geometry_sha, sealed)


def _validate(note, *, reply, manifests, target_id, admission, layout_checker, opener, local) -> Outcome:
    if not isinstance(note, (bytes, bytearray)):
        raise TypeError("the note is validated as bytes")
    note = bytes(note)
    if not is_attempt(note):
        return _rejected([violation("malformed_json")]) if local else Outcome("ignored")
    found = _row(reply) if reply is not None else []
    sealed = note.startswith(SEALED_PREFIX)
    found += _size_and_text(note, MAX_SEALED_BYTES if sealed else MAX_PLAINTEXT_BYTES)
    if found:
        return _rejected(found, sealed=sealed)
    if sealed:
        value, found, opened = _unseal(note, manifests=manifests, target_id=target_id, opener=opener)
        if found:
            return _rejected(found, sealed=True)
        if not opened:
            return Outcome("sealed_unopened", sealed=True)
    else:
        value, found = _json(note.decode("utf-8"), fenced=True)
        if found:
            return _rejected(found)
        if not local and value.get("visibility") == "private":
            return _rejected([violation("private_requires_sealed")])
    return _object(value, sealed=sealed, reply=reply, manifests=manifests, target_id=target_id, admission=admission,
                   layout_checker=layout_checker)


def validate_reply(note, *, reply: Reply, manifests, thread_manifest_id: str, admission,
                   layout_checker: LayoutChecker | None = None, opener: Opener | None = None) -> Outcome:
    """The intake: one reply to a challenge root. admission maps manifest id to open, not_open_yet or closed."""
    if not isinstance(reply, Reply) or admission is None:
        raise TypeError("the intake always checks the row, the transport key and admission")
    return _validate(note, reply=reply, manifests=manifests, target_id=thread_manifest_id, admission=admission,
                     layout_checker=layout_checker, opener=opener, local=False)


def validate_local(note, *, manifests, manifest_id: str, layout_checker: LayoutChecker | None = None,
                   opener: Opener | None = None) -> Outcome:
    """The offline checker (section 6.1): the intake's content checks without the row, the transport key or
    admission, on the plaintext a participant is about to post or seal. Anything that is not an attempt is
    malformed here."""
    return _validate(note, reply=None, manifests=manifests, target_id=manifest_id, admission=None,
                     layout_checker=layout_checker, opener=opener, local=True)


# ── records: schema first; when the schema holds, the cross-field rules ──────────────────────────────────────────

RECORD_SCHEMAS = {"manifest": "manifest", "terms": "terms", "check": "check", "receipt": "receipt",
                  "status": "status", "results": "results", "geometry": "geometry", "transport_key": "transport-key",
                  "proposal": "proposal", "check_request": "check-request", "team": "team", "publish": "publish",
                  "reason_codes": "reason-codes"}
CHECK_CODES = REJECTION_CODES | {"check_unfinished"}
EVALUATED = frozenset({"evaluated", "replaying", "reproduced", "not_reproduced", "cross_checked"})
NO_DESIGN = frozenset({"rejected", "queued", "held", "cancelled", "expired"})


def _bad(code: str, path: str, rule: str) -> dict:
    return violation(code, path=path, rule=rule)


def _fields(items, path: str) -> list:
    return [_bad("record_inconsistent", f"{path}/{index}", "violation.fields")
            for index, item in enumerate(items) if not fields_ok(item)]


def state_codes_ok(state: str, codes) -> bool:
    names = [item["code"] for item in codes]
    rest = [name for name in names if name not in QUALIFIER_CODES]
    if state == "rejected":
        return bool(names) and all(name in REJECTION_CODES for name in names)
    if state == "failed":
        return len(rest) == 1 and rest[0] in FAILURE_CODES
    if state == "not_reproduced":
        return len(rest) == 1 and rest[0] in REPRODUCTION_CODES
    if state in EVALUATED:
        return not rest
    if state == "cancelled":
        return all(name in POLICY_CODES for name in names)
    return not names                                # queued, held, evaluating, expired


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _decimals_ok(value) -> bool:
    exact = Decimal(repr(value))
    return exact == exact.quantize(Decimal("0.01"))


def q_r_keys(manifest: dict) -> set:
    """r = 0, the policy tolerance r and every tradeoff budget (section 6.2)."""
    policy = manifest["policy"]
    values = [0] + ([policy["r"]] if policy["r"] is not None else []) + list(policy["tradeoff_budgets_r"])
    return {hashes.r_key(value) for value in values}


def _q_r_rules(q_r: dict, w_c, manifest: dict, path: str, rule: str) -> list:
    if set(q_r) != q_r_keys(manifest):
        return [_bad("record_inconsistent", path, rule + "_keys")]
    w_r = manifest["references"]["comparator"]["W_R_mm"]
    for key, value in q_r.items():
        if value != ("UNKNOWN" if w_c == "UNKNOWN" else hashes.q_r(w_c, w_r, key)):
            return [_bad("record_inconsistent", path, rule + "_values")]
    return []


def _manifest_rules(record: dict, ctx: dict) -> list:
    found = []
    dies = record["dies"]
    for index, die in enumerate(dies):
        if die["die"] != index:
            found.append(_bad("record_inconsistent", f"/dies/{index}", "manifest.die_index"))
        if (sorted(die["rot_deg"]) != [0]) if die["w_um"] == die["h_um"] else (sorted(die["rot_deg"]) != [0, 90]):
            found.append(_bad("record_inconsistent", f"/dies/{index}/rot_deg", "manifest.square_rotation"))
    if record["statistic"]["real_chiplets"] != [die["unit"] for die in dies]:
        found.append(_bad("record_inconsistent", "/statistic/real_chiplets", "manifest.real_chiplets"))
    matrix, count = record["netlist"]["matrix"], len(dies)
    if len(matrix) != count or any(len(row) != count or row[index] != 0 for index, row in enumerate(matrix)):
        found.append(_bad("record_inconsistent", "/netlist/matrix", "manifest.netlist"))
    policy = record["policy"]
    budgets = policy["tradeoff_budgets_r"]
    if budgets != sorted(budgets) or not all(_decimals_ok(value) for value in budgets + [policy["r"] or 0]):
        found.append(_bad("record_inconsistent", "/policy/tradeoff_budgets_r", "manifest.r_values"))
    checks = record["checks"]
    if None not in (checks["solver_time_limit_s"], checks["check_wall_s"]) and not (
            checks["solver_time_limit_s"] < checks["check_wall_s"]):
        found.append(_bad("record_inconsistent", "/checks/solver_time_limit_s", "manifest.check_limits"))
    limits = record["limits"]
    if (limits["eval_per_account_day"] < limits["eval_per_account_hour"]
            or limits["eval_room_day"] < limits["eval_room_hour"]):
        found.append(_bad("record_inconsistent", "/limits", "manifest.quota_windows"))
    window = record["window"]
    if None not in window.values() and not window["opens_at"] < window["closes_at"]:
        found.append(_bad("record_inconsistent", "/window", "manifest.window"))
    ids = [scenario["id"] for scenario in record["screen"]["scenarios"]]
    if len(set(ids)) != len(ids) or "nominal" not in ids:
        found.append(_bad("record_inconsistent", "/screen/scenarios", "manifest.scenarios"))
    if record["status"] == "signed":
        found += [_bad("record_inconsistent", path, "manifest.signed_pins") for path in _missing_pins(record)]
    return found


def _missing_pins(record: dict) -> list:
    """Every value a signed manifest must have fixed (sections 4.1, 4.11): nothing left null or provisional."""
    statistic, policy, checks = record["statistic"], record["policy"], record["checks"]
    pins = {"/fixture/package/hotspot_config_sha256": record["fixture"]["package"]["hotspot_config_sha256"],
            "/references/file_sha256": record["references"]["file_sha256"],
            "/wire/router_sha256": record["wire"]["router_sha256"],
            "/evaluation_bundle/ceilings_cpu_s": record["evaluation_bundle"]["ceilings_cpu_s"],
            "/terms/retention": record["terms"]["retention"],
            "/sealing/recipient": record["sealing"]["recipient"],
            "/sealing/key_version": record["sealing"]["key_version"]}
    for name in ("binary_sha256", "gate_zero_record_sha256", "build", "runtime"):
        pins["/statistic/evaluator/" + name] = statistic["evaluator"][name]
    for name in ("D_K", "r", "B_T_K", "B_W_mm", "T_limit_C"):
        pins["/policy/" + name] = policy[name]
    for name in ("solver_time_limit_s", "check_wall_s", "cleanup_headroom_s", "cpu_reserve_s"):
        pins["/checks/" + name] = checks[name]
    for name in ("opens_at", "closes_at"):
        pins["/window/" + name] = record["window"][name]
    for name in ("grant", "claim_rules", "checker_sha256"):
        pins["/refs/" + name] = record["refs"][name]
    missing = [path for path, value in pins.items() if value is None]
    if not record["terms"]["accepted_versions"]:
        missing.append("/terms/accepted_versions")
    if not policy["status"].startswith("frozen"):
        missing.append("/policy/status")
    if record["evaluation_bundle"]["status"] != "frozen":
        missing.append("/evaluation_bundle/status")
    if not record["limits"]["status"].startswith("frozen"):
        missing.append("/limits/status")
    if statistic["numerical_admission"] != "admitted":
        missing.append("/statistic/numerical_admission")
    if any(scenario["id"] == "position-<die>-<axis>-<sign>" for scenario in record["screen"]["scenarios"]):
        missing.append("/screen/scenarios")
    return missing


def _terms_rules(record: dict, ctx: dict) -> list:
    if not record["version"].endswith("@" + record["text_sha256"]):
        return [_bad("record_inconsistent", "/version", "terms.version_hash")]
    return []


def check_codes_ok(status: str, codes) -> bool:
    """A routed check has no codes. The solver limit gives time_limit with one check_unfinished naming it; the wall
    or the CPU reserve gives not_routed with one check_unfinished naming that limit; a rejection is not_routed with
    its rejection codes (a quota refusal is rate_limited)."""
    names = [item["code"] for item in codes]
    if any(name not in CHECK_CODES for name in names):
        return False
    unfinished = [item.get("limit") for item in codes if item["code"] == "check_unfinished"]
    if status == "optimal":
        return not names
    if status == "time_limit":
        return len(names) == 1 and unfinished == ["solver_time_limit_s"]
    if unfinished:
        return len(names) == 1 and unfinished[0] in ("check_wall_s", "cpu_reserve_s")
    return bool(names)


def _check_rules(record: dict, ctx: dict) -> list:
    found = _fields(record["codes"], "/codes")
    if not check_codes_ok(record["router_status"], record["codes"]):
        found.append(_bad("record_inconsistent", "/codes", "check.codes"))
    if ctx["manifest"] is not None:
        found += _q_r_rules(record["q_r_nominal"], record["W_c_mm"], ctx["manifest"], "/q_r_nominal", "check.q_r")
    elif any(value != "UNKNOWN" for value in record["q_r_nominal"].values()) and record["W_c_mm"] == "UNKNOWN":
        found.append(_bad("record_inconsistent", "/q_r_nominal", "check.q_r_values"))
    return found


def _receipt_rules(record: dict, ctx: dict) -> list:
    found = _fields(record["codes"], "/codes")
    state = record["state"]
    if not state_codes_ok(state, record["codes"]):
        found.append(_bad("record_inconsistent", "/codes", "state.codes"))
    read = ("terms", "visibility", "proposal_key", "revision_index")
    derived = ("geometry_sha256", "design_hash", "parent", "values")
    if record["proposal_sha256"] is None:
        bad = [name for name in read + derived if record[name] is not None]
        if state != "rejected":
            bad.append("proposal_sha256")
    else:
        bad = [name for name in read if record[name] is None]
        if state != "rejected":
            bad += [name for name in ("geometry_sha256", "values") if record[name] is None]
    found += [_bad("record_inconsistent", "/" + name, "receipt.proposal_fields") for name in bad]
    if (state in NO_DESIGN and record["design_hash"] is not None
            or state in EVALUATED and record["design_hash"] is None):
        found.append(_bad("record_inconsistent", "/design_hash", "receipt.design_hash"))
    manifest, item = ctx["manifest"], ctx["item"]
    if manifest is not None and record["manifest_id"] != hashes.manifest_id(manifest):
        found.append(_bad("record_inconsistent", "/manifest_id", "record.manifest"))
    if item is not None and manifest is not None and record["proposal_sha256"] is not None:
        if (record["proposal_sha256"] != hashes.proposal_sha256(item)
                or record["proposal_key"] != item["proposal_key"] or record["terms"] != item["terms"]
                or record["visibility"] != item["visibility"] or record["parent"] != item["parent"]):
            found.append(_bad("ref_mismatch", "/proposal_sha256", "ref.proposal"))
        if record["geometry_sha256"] not in (None, hashes.geometry_sha256(item, manifest)):
            found.append(_bad("ref_mismatch", "/geometry_sha256", "ref.geometry"))
        if record["values"] not in (None, hashes.conductor_geometry(item, manifest)):
            found.append(_bad("ref_mismatch", "/values", "ref.values"))
    if ctx["action_id"] is not None and record["source_ref"] != hashes.source_ref(ctx["action_id"]):
        found.append(_bad("ref_mismatch", "/source_ref", "ref.source"))
    if ctx["k_challenge"] is not None and ctx["account_id"] is not None and record["participant_ref"] != (
            hashes.participant_ref(ctx["k_challenge"], ctx["account_id"])):
        found.append(_bad("ref_mismatch", "/participant_ref", "ref.participant"))
    return found


def _status_rules(record: dict, ctx: dict) -> list:
    found = []
    wanted = None
    if ctx["manifest"] is not None and ctx["proposal_sha256"] is not None:
        wanted = hashes.run_id(hashes.manifest_id(ctx["manifest"]), ctx["proposal_sha256"])
    for index, receipt in enumerate(record["receipts"]):
        path = f"/receipts/{index}"
        if (receipt["queue"] is not None) != (receipt["state"] == "queued"):
            found.append(_bad("record_inconsistent", path + "/queue", "status.queue"))
        if wanted is not None and receipt["run_id"] != wanted:
            found.append(_bad("ref_mismatch", path + "/run_id", "ref.run_id"))
    return found


CLAIMED = frozenset({"bounded", "passes the listed sensitivity cases"})


def _exact_difference(a, b):
    """a - b exactly in decimal, then the nearest double; UNKNOWN if either is."""
    return "UNKNOWN" if "UNKNOWN" in (a, b) else float(Decimal(repr(a)) - Decimal(repr(b)))


def _measured_rules(row: dict, path: str, t_r, ctx: dict) -> list:
    manifest, found = ctx["manifest"], []
    if not label_ok(row["T_M"], row["evaluator"], row["temperature_label"], ctx["lists"]):
        found.append(_bad("label_mismatch", path + "/temperature_label", "label.temperature"))
    if row["delta_T"] != _exact_difference(row["T_M"], t_r):
        found.append(_bad("record_inconsistent", path + "/delta_T", "results.delta_t"))
    ids = [label["id"] for label in row["labels"]]
    positions = [LABELS.index(name) for name in ids]
    if positions != sorted(set(positions)) or set(ids) & {item["id"] for item in row["suppressed"]}:
        found.append(_bad("record_inconsistent", path + "/labels", "results.label_set"))
    policy_r = manifest["policy"]["r"] if manifest is not None else None
    for item in row["labels"] + row["suppressed"]:
        relaxed = item["id"] == "r-relaxed-wire thermal tolerance"
        if relaxed != (item["r"] is not None) or relaxed and manifest is not None and item["r"] != policy_r:
            found.append(_bad("record_inconsistent", path + "/labels", "results.label_r"))
            break
    claimed = [label for label in row["labels"] if label["mode"] in CLAIMED]
    for label in claimed:
        needs = [row["T_M"]] if label["id"] == LABELS[0] else [row["delta_T"], row["W_c_mm"]]
        if "UNKNOWN" in needs:
            found.append(_bad("record_inconsistent", path + "/labels", "results.unknown_claim"))
            break
    if manifest is not None and any(label["mode"] == "bounded" for label in row["labels"]) and "UNKNOWN" in (
            manifest["bounds"].values()):
        found.append(_bad("record_inconsistent", path + "/labels", "results.bounded"))
    if claimed and row["temperature_label"] == "withdrawn":
        found.append(_bad("label_mismatch", path + "/labels", "label.withdrawn_claim"))
    if manifest is not None:
        found += _q_r_rules(row["q_r"], row["W_c_mm"], manifest, path + "/q_r", "results.q_r")
    return found


def _results_rules(record: dict, ctx: dict) -> list:
    manifest, comparator, found = ctx["manifest"], record["comparator"], []
    if not label_ok(comparator["T_R"], comparator["evaluator"], comparator["temperature_label"], ctx["lists"]):
        found.append(_bad("label_mismatch", "/comparator/temperature_label", "label.temperature"))
    if manifest is not None:
        pinned = manifest["references"]["comparator"]
        if (comparator["id"], comparator["T_R"], comparator["W_R_mm"]) != (pinned["id"], pinned["T_R"],
                                                                              pinned["W_R_mm"]):
            found.append(_bad("record_inconsistent", "/comparator", "results.comparator"))
    for index, row in enumerate(record["rows"]):
        path = f"/rows/{index}"
        if row["kind"] == "published_target":
            continue
        found += _measured_rules(row, path, comparator["T_R"], ctx)
        if row["kind"] == "outside" and row["state"] not in EVALUATED and (row["T_M"] != "UNKNOWN" or row["labels"]):
            found.append(_bad("record_inconsistent", path + "/state", "results.state"))
    return found


RULES = {"manifest": _manifest_rules, "terms": _terms_rules, "check": _check_rules, "receipt": _receipt_rules,
         "status": _status_rules, "results": _results_rules}


def validate_record(kind: str, record, *, manifest=None, item=None, action_id=None, k_challenge=None,
                    account_id=None, proposal_sha256=None, private_handles=(), lists=LISTS) -> list:
    """Every violation of one record, in canonical order. The schema comes first; rules run only on a valid shape.

    The keyword arguments enable the rules that need them (the manifest, the parsed proposal, the restricted row's
    action and account ids with k_challenge, the status query); without them those rules are skipped.
    private_handles are salted proposal_sha256 and request_sha256 values of private items: bearer secrets that no
    record may carry, checked on every record kind.
    """
    if kind not in RECORD_SCHEMAS:
        raise ValueError("unknown record kind")
    found = schema_violations(RECORD_SCHEMAS[kind], record)
    if found:
        return canonical_list(found)
    ctx = {"manifest": manifest, "item": item, "action_id": action_id, "k_challenge": k_challenge,
           "account_id": account_id, "proposal_sha256": proposal_sha256, "lists": lists}
    found = RULES.get(kind, lambda _record, _ctx: [])(record, ctx)
    handles = set(private_handles)
    if handles and any(text in handles for text in _strings(record)):
        found.append(_bad("record_inconsistent", "", "privacy.handle"))
    return canonical_list(found)


def label_ok(value, evaluator, label, lists=LISTS) -> bool:
    """A measured temperature carries its evaluator identity and the SLAB-053 label state that identity gets."""
    return value == "UNKNOWN" and label is None or value != "UNKNOWN" and label == label_for(evaluator, lists)
