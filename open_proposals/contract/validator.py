"""The reference validator: the intake's and the check's checks, in order, and the rules every record must meet.

No network and no solver. Stages (CONTRACT.md, "Validation"):

  0. chat       first non-blank bytes (after one optional BOM) are neither "{" nor "```": ignored, no receipt
  1. transport  unattributable and edited_before_ingest (intake only), oversize, not_utf8 (a BOM included)
  2. JSON       one object, bare or in one ```json fence: too_deep (pre-scan), malformed_json, duplicate_key,
                nonfinite_number
  2s. sealed    a sentilab-open-sealed/1 envelope: its schema, manifest and key version, the pinned age header;
                then the opener (the recorder's or the check's age identity) and stages 1-6 on the plaintext, which
                must carry a salt and name the envelope's manifest
  3. schema     unknown_field, schema_invalid; then salt_forbidden on a public proposal
  4. manifest   unknown_manifest, manifest_mismatch (incl. the declared lattice), wire_track_not_admitted,
                terms_mismatch, and (intake only) not_open_yet / manifest_closed
  5. geometry   exact integers: geometry_hash_mismatch, die_count, die_order, then per die rotation_not_allowed,
                out_of_frame, lattice
  6. layout     the OP-F7 seam: TapGeometry's margin, halo_overlap and min_spacing, run only when every die maps
                onto its catalogue entry; reported together with stage 5

Each stage reports everything it finds; the first stage with a violation ends the check (5 and 6 report together).
Without a layout checker a clean proposal is "contract_valid", never "legal"; without an opener a valid sealed
envelope is "sealed_unopened".
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable

from . import canonical as hashes
from .codes import canonical_list, fields_ok, violation
from .labels import LISTS, label_for, label_for_all
from .schemas import def_is_valid, schema_violations
from .states import (FAILURE_CODES, POLICY_CODES, REJECTION_CODES, REPRODUCTION_CODES, VERIFICATION_CODES,
                     created_at_ns)

MAX_NOTE_BYTES = 4096
MAX_DEPTH = 4
BOM = bytes((0xEF, 0xBB, 0xBF))
BLANK = b" \t\r\n"
FENCE = re.compile(r"```json[ \t]*\r?\n(.*)\r?\n```\Z", re.DOTALL)
LAYOUT_CODES = frozenset({"margin", "halo_overlap", "min_spacing"})
SEALED_SCHEMA = "sentilab-open-sealed/1"
AGE_HEADER = b"age-encryption.org/v1\n"
CAPABILITY = re.compile(r"opencap1-[0-9a-f]{64}")

LayoutChecker = Callable[[dict, dict], Iterable[dict]]
Opener = Callable[[bytes, dict], bytes]


class Unopenable(Exception):
    """Raised by an opener that cannot decrypt an age file. Any other exception is a fault and propagates."""


@dataclass(frozen=True)
class Reply:
    """What the intake read from Senti's row, all server-set: never anything from the note."""
    actor_user_id: str | None
    message_revision: int
    edited_at: str | None


@dataclass(frozen=True)
class Outcome:
    outcome: str        # ignored | rejected | refused | sealed_unopened | contract_valid | legal
    violations: tuple = ()
    proposal: dict | None = None
    proposal_sha256: str | None = None
    geometry_sha256: str | None = None
    sealed: bool = False
    ciphertext_ref: str | None = None

    def summary(self) -> dict:
        return {"outcome": self.outcome, "codes": list(self.violations), "proposal_sha256": self.proposal_sha256,
                "geometry_sha256": self.geometry_sha256, "sealed": self.sealed, "ciphertext_ref": self.ciphertext_ref}


def _outcome(outcome, found=(), proposal=None, proposal_sha=None, geometry_sha=None) -> Outcome:
    return Outcome(outcome, tuple(canonical_list(found)), proposal, proposal_sha, geometry_sha)


def is_chat(note: bytes) -> bool:
    start = 3 if note.startswith(BOM) else 0
    while start < len(note) and note[start] in BLANK:
        start += 1
    rest = note[start:]
    return not (rest.startswith(b"{") or rest.startswith(b"```"))


def _transport(note: bytes, reply: Reply | None) -> list:
    found = []
    if reply is not None:
        if not reply.actor_user_id:
            found.append(violation("unattributable"))
        if reply.message_revision != 1 or reply.edited_at is not None:
            found.append(violation("edited_before_ingest"))
    if len(note) > MAX_NOTE_BYTES:
        found.append(violation("oversize", size_bytes=len(note)))
    try:
        note.decode("utf-8", errors="strict")
        bad = note.startswith(BOM)
    except UnicodeDecodeError:
        bad = True
    if bad:
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


def _json(note: bytes):
    text = note.decode("utf-8").strip(" \t\r\n")
    if text.startswith("```"):
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


def _known(manifests, target_id: str, named_id: str):
    """The thread's manifest, or the violation that stops here."""
    if target_id not in manifests or named_id not in manifests:
        return None, [violation("unknown_manifest")]
    if named_id != target_id:
        return None, [violation("manifest_mismatch", path="/manifest_id")]
    return manifests[target_id], []


def _admission(manifest: dict, manifest_id: str, admission) -> list:
    if admission is None:
        return []
    state = admission.get(manifest_id, "not_open_yet")
    if state == "closed":
        return [violation("manifest_closed")]
    if state != "open" or manifest["status"] != "frozen":
        return [violation("not_open_yet")]                  # only a frozen manifest can ever be open
    return []


def _manifest(proposal: dict, manifest: dict) -> list:
    found = []
    if proposal["problem"] != manifest["problem"]:
        found.append(violation("manifest_mismatch", path="/problem"))
    if proposal["reference_id"] != manifest["reference"]["id"]:
        found.append(violation("manifest_mismatch", path="/reference_id"))
    if proposal["lattice_um"] != manifest["legality"]["lattice_um"]:
        found.append(violation("manifest_mismatch", path="/lattice_um"))
    if proposal["wire_track"] not in {track["id"] for track in manifest["wire_tracks"]}:
        found.append(violation("wire_track_not_admitted"))
    if proposal["terms"] != manifest["terms"]["id"]:
        found.append(violation("terms_mismatch"))
    return found


def _off_lattice(value: int, step: int) -> int:
    rest = value % step
    return min(rest, step - rest)


def _geometry(proposal: dict, manifest: dict):
    """Stage 5. Returns (server geometry hash, violations, whether every die maps onto its catalogue entry)."""
    server_hash = hashes.geometry_sha256(proposal, manifest)
    found = []
    if server_hash != proposal["geometry_sha256"]:
        found.append(violation("geometry_hash_mismatch"))
    dies, catalogue = proposal["dies"], manifest["dies"]
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


def _layout(proposal: dict, manifest: dict, checker: LayoutChecker) -> list:
    found = list(checker(proposal, manifest))
    for item in found:
        if not (fields_ok(item) and item["code"] in LAYOUT_CODES and def_is_valid("violation", item)):
            raise ValueError("the layout checker returned something outside the seam's contract")
    return found


def _proposal(value: dict, *, manifests, target_id, admission, layout_checker, sealed=False) -> Outcome:
    """Stages 3-6 on a parsed proposal. A sealed plaintext names the thread's manifest like any proposal; the
    envelope was already checked against the same thread, so the two always agree."""
    found = schema_violations("proposal", value)
    if found:
        return _outcome("rejected", found)
    if sealed and "salt" not in value:
        return _outcome("rejected", [violation("salt_required")])
    if not sealed and "salt" in value:
        return _outcome("rejected", [violation("salt_forbidden")])
    proposal_sha = hashes.proposal_sha256(value)
    manifest, found = _known(manifests, target_id, value["manifest_id"])
    if not found:
        found = _manifest(value, manifest) + _admission(manifest, target_id, admission)
    if found:
        return _outcome("rejected", found, value, proposal_sha)
    geometry_sha, found, mapped = _geometry(value, manifest)
    checked = mapped and layout_checker is not None
    if checked:
        found += _layout(value, manifest, layout_checker)
    if found:
        return _outcome("rejected", found, value, proposal_sha, geometry_sha)
    return _outcome("legal" if checked else "contract_valid", (), value, proposal_sha, geometry_sha)


def _decode_base64(text: str) -> bytes | None:
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None


def _sealed(envelope: dict, *, manifests, target_id, admission, opener, layout_checker) -> Outcome:
    found = schema_violations("sealed", envelope)
    if found:
        return _outcome("rejected", found)
    manifest, found = _known(manifests, target_id, envelope["manifest_id"])
    if found:
        return _outcome("rejected", found)
    sealing = manifest["sealing"]
    found = _admission(manifest, target_id, admission)
    if sealing is None or sealing["recipient"] is None or sealing["key_version"] != envelope["key_version"]:
        found.append(violation("sealed_key_version"))
    age_file = _decode_base64(envelope["ciphertext"])
    if age_file is None or not age_file.startswith(AGE_HEADER):
        found.append(violation("sealed_format"))
    if found:
        return _outcome("rejected", found)
    reference = hashes.ciphertext_ref(age_file)
    if opener is None:
        return Outcome("sealed_unopened", sealed=True, ciphertext_ref=reference)
    try:
        plaintext = opener(age_file, manifest)
    except Unopenable:
        return Outcome("rejected", (violation("sealed_undecryptable"),), sealed=True, ciphertext_ref=reference)
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("an opener returns the plaintext bytes")
    plaintext = bytes(plaintext)
    found = _transport(plaintext, None)
    value = None
    if not found:
        value, found = _json(plaintext) if not is_chat(plaintext) else (None, [violation("malformed_json")])
    if found:
        inner = _outcome("rejected", found)
    else:
        inner = _proposal(value, manifests=manifests, target_id=target_id, admission=None,
                          layout_checker=layout_checker, sealed=True)
    return Outcome(inner.outcome, inner.violations, inner.proposal, inner.proposal_sha256, inner.geometry_sha256,
                   sealed=True, ciphertext_ref=reference)


def _validate(note, *, manifests, target_id, reply, admission, layout_checker, opener, chat_is_malformed) -> Outcome:
    if not isinstance(note, (bytes, bytearray)):
        raise TypeError("the note is validated as bytes")
    note = bytes(note)
    if is_chat(note):
        return _outcome("rejected", [violation("malformed_json")]) if chat_is_malformed else Outcome("ignored")
    found = _transport(note, reply)
    if found:
        return _outcome("rejected", found)
    value, found = _json(note)
    if found:
        return _outcome("rejected", found)
    if value.get("schema") == SEALED_SCHEMA:
        return _sealed(value, manifests=manifests, target_id=target_id, admission=admission, opener=opener,
                       layout_checker=layout_checker)
    return _proposal(value, manifests=manifests, target_id=target_id, admission=admission,
                     layout_checker=layout_checker)


def validate_submission(note, *, reply: Reply, manifests, thread_manifest_id: str, admission,
                        layout_checker: LayoutChecker | None = None, opener: Opener | None = None) -> Outcome:
    """The intake: one reply to a challenge root. admission maps manifest id to open, not_open_yet or closed."""
    if not isinstance(reply, Reply) or admission is None:
        raise TypeError("the intake always checks attribution, revision and admission")
    return _validate(note, manifests=manifests, target_id=thread_manifest_id, reply=reply, admission=admission,
                     layout_checker=layout_checker, opener=opener, chat_is_malformed=False)


def validate_check_note(note, *, manifests, manifest_id: str, layout_checker: LayoutChecker | None = None,
                        opener: Opener | None = None) -> Outcome:
    """The check: the intake's checks without attribution, revision or admission. A chat-like note is malformed."""
    return _validate(note, manifests=manifests, target_id=manifest_id, reply=None, admission=None,
                     layout_checker=layout_checker, opener=opener, chat_is_malformed=True)


def decode_param(text: str) -> bytes | None:
    """Unpadded base64url, canonical only: re-encoding must give back the same text."""
    if len(text) % 4 == 1:
        return None
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    return raw if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") == text else None


def validate_check_request(request, *, manifests, layout_checker: LayoutChecker | None = None,
                           opener: Opener | None = None) -> Outcome:
    """GET /api/open/v1/check. A malformed request is "refused" (the error body); everything else is the check."""
    found = schema_violations("check-request", request)
    if found:
        return _outcome("refused", found)
    note = decode_param(request["p"])
    if note is None:
        return _outcome("refused", [violation("schema_invalid", path="/p", keyword="contentEncoding")])
    return validate_check_note(note, manifests=manifests, manifest_id=request["m"], layout_checker=layout_checker,
                               opener=opener)


# ── records: schema first; when the schema holds, the cross-field rules ──────────────────────────────────────────

RECORD_SCHEMAS = {"manifest": "manifest", "geometry": "geometry", "sealed": "sealed", "check_request": "check-request",
                  "check": "check", "receipt": "receipt", "restricted_receipt": "restricted-receipt",
                  "status": "status", "results": "results", "error": "error", "limits": "limits", "usage": "usage",
                  "cursor": "cursor", "current": "current", "private_request": "private-request",
                  "reason_codes": "reason-codes"}
ROUTER_TIMEOUT = frozenset({"router_timeout"})
LIFECYCLE_CODES = REJECTION_CODES | FAILURE_CODES | REPRODUCTION_CODES | VERIFICATION_CODES | ROUTER_TIMEOUT
DECIDED = frozenset({"passes_listed_cases", "fails_listed_cases"})


def _bad(code: str, path: str, rule: str) -> dict:
    return violation(code, path=path, rule=rule)


def _fields(items, path: str) -> list:
    return [_bad("record_inconsistent", f"{path}/{index}", "violation.fields")
            for index, item in enumerate(items) if not fields_ok(item)]


def state_codes_ok(state: str, codes) -> bool:
    names = [item["code"] for item in codes]
    if state == "rejected":
        return bool(names) and all(name in REJECTION_CODES for name in names)
    if state == "failed":
        return len(names) == 1 and names[0] in FAILURE_CODES
    if state == "not_reproduced":
        return len(names) == 1 and names[0] in REPRODUCTION_CODES
    if state == "not_verified":
        return len(names) == 1 and names[0] in VERIFICATION_CODES
    if state in ("cancelled", "expired"):
        return all(name in POLICY_CODES for name in names)
    if state == "withdrawn":
        return all(name in LIFECYCLE_CODES for name in names)
    if state in ("queued", "held", "evaluating"):
        return not names
    return all(name in ROUTER_TIMEOUT for name in names)


def _single(obj, path: str, lists) -> list:
    if obj is not None and obj["label"] != label_for(obj["evaluator"], lists):
        return [_bad("label_mismatch", path, "label.single")]
    return []


def _derived(obj, path: str, lists) -> list:
    if obj is not None and obj["label"] != label_for_all(obj["evaluators"], lists):
        return [_bad("label_mismatch", path, "label.derived")]
    return []


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _snap_suffix(grid_um: int) -> str:
    whole, rest = divmod(grid_um, 1000)
    return f"-snap{whole}" + (f"p{str(rest).rjust(3, '0').rstrip('0')}" if rest else "")


def _manifest_rules(record: dict, ctx: dict) -> list:
    lists, found = ctx["lists"], []
    dies = record["dies"]
    for index, die in enumerate(dies):
        if die["die"] != index:
            found.append(_bad("record_inconsistent", f"/dies/{index}", "manifest.die_index"))
        # TAP's catalogue: one orientation for a square die or under "catalog" rotation, both otherwise.
        fixed = die["w_um"] == die["h_um"] or record["legality"]["rotation"] == "catalog"
        if sorted(die["rot_deg"]) != ([0] if fixed else [0, 90]):
            found.append(_bad("record_inconsistent", f"/dies/{index}/rot_deg", "manifest.square_rotation"))
    netlist, count = record["netlist"], len(dies)
    square = len(netlist) == count and all(len(row) == count for row in netlist)
    if not square or any(netlist[index][index] != 0 for index in range(count)):
        found.append(_bad("record_inconsistent", "/netlist", "manifest.netlist"))
    track_ids = [track["id"] for track in record["wire_tracks"]]
    if len(set(track_ids)) != len(track_ids) or "strict" not in track_ids:
        found.append(_bad("record_inconsistent", "/wire_tracks", "manifest.tracks"))
    reference = record["reference"]
    found += _single(reference["t_ref"], "/reference/t_ref", lists)
    found += _single(reference["w_ref"], "/reference/w_ref", lists)
    found += _single(reference["paper"], "/reference/paper", lists)
    if record["example"] is not None:
        found += _single(record["example"]["temperature"], "/example/temperature", lists)
        found += _single(record["example"]["wire"], "/example/wire", lists)
    identity, router = record["temperature"]["evaluator"]["identity"], record["wire"]["evaluator"]
    if reference["t_ref"] is not None and identity is not None and reference["t_ref"]["evaluator"] != identity:
        found.append(_bad("record_inconsistent", "/reference/t_ref", "manifest.same_evaluator"))
    if reference["w_ref"] is not None and router is not None and reference["w_ref"]["evaluator"] != router:
        found.append(_bad("record_inconsistent", "/reference/w_ref", "manifest.same_evaluator"))
    variant = reference["engineering_variant"]
    if variant is not None and (variant["id"] != reference["id"] + _snap_suffix(variant["grid_um"])
                                or variant["grid_um"] % record["legality"]["lattice_um"]):
        found.append(_bad("record_inconsistent", "/reference/engineering_variant", "manifest.variant"))
    if record["status"] == "frozen":
        found += [_bad("record_inconsistent", path, "manifest.frozen_pins") for path in _missing_pins(record)]
    return found


def _missing_pins(record: dict) -> list:
    evaluator = record["temperature"]["evaluator"]
    pins = {"/reference/sha256": record["reference"]["sha256"],
            "/temperature/evaluator/binary_sha256": evaluator["binary_sha256"],
            "/temperature/evaluator/gate_zero_record_sha256": evaluator["gate_zero_record_sha256"],
            "/temperature/evaluator/identity": evaluator["identity"],
            "/wire/router_sha256": record["wire"]["router_sha256"],
            "/wire/time_limit_s": record["wire"]["time_limit_s"],
            "/wire/evaluator": record["wire"]["evaluator"],
            "/window/opens_at": record["window"]["opens_at"],
            "/window/closes_at": record["window"]["closes_at"],
            "/refs/grant": record["refs"]["grant"],
            "/refs/claim_rules": record["refs"]["claim_rules"],
            "/refs/checker_sha256": record["refs"]["checker_sha256"]}
    thresholds = record["thresholds"]
    for name in ("D_k", "B_T_k", "B_W", "scenario_target_c"):
        pins["/thresholds/" + name] = thresholds[name]
    if thresholds["B_W"] is not None:
        pins["/thresholds/B_W/of_reference_wire_mm"] = thresholds["B_W"]["of_reference_wire_mm"]
    variant = record["reference"]["engineering_variant"]
    if variant is not None:
        pins["/reference/engineering_variant/geometry_sha256"] = variant["geometry_sha256"]
        pins["/reference/engineering_variant/design_hash"] = variant["design_hash"]
    for index, control in enumerate(record["discrimination_control"]):
        pins[f"/discrimination_control/{index}/source_sha256"] = control["source_sha256"]
    if record["sealing"] is not None:
        pins["/sealing/recipient"] = record["sealing"]["recipient"]
        pins["/sealing/key_version"] = record["sealing"]["key_version"]
    missing = [path for path, value in pins.items() if value is None]
    if thresholds["status"] != "frozen":
        missing.append("/thresholds/status")
    if record["sensitivity"]["status"] != "frozen":
        missing.append("/sensitivity/status")
    return missing


def _fits_tracks(routed_mm, manifest: dict) -> list:
    reference = manifest["reference"]["w_ref"]
    if routed_mm is None or reference is None or reference["routed_mm"] is None:
        return []
    limit = Decimal(repr(reference["routed_mm"]))
    return [track["id"] for track in manifest["wire_tracks"]
            if Decimal(repr(routed_mm)) <= Decimal(repr(track["factor"])) * limit]


def _check_rules(record: dict, ctx: dict) -> list:
    found = _fields(record["violations"], "/violations")
    if record["legal"] != (not record["violations"]):
        found.append(_bad("record_inconsistent", "/legal", "check.legal"))
    status = record["wire"]["routed_status"]
    if (status == "skipped_illegal") == record["legal"] or (not record["legal"] and record["fits_tracks"]):
        found.append(_bad("record_inconsistent", "/wire/routed_status", "check.routed"))
    manifest = ctx["manifest"]
    if manifest is not None:
        if record["manifest_id"] != hashes.manifest_id(manifest):
            found.append(_bad("record_inconsistent", "/manifest_id", "record.manifest"))
        if record["fits_tracks"] != _fits_tracks(record["wire"]["routed_mm"], manifest):
            found.append(_bad("record_inconsistent", "/fits_tracks", "check.fits_tracks"))
    elif record["wire"]["routed_mm"] is None and record["fits_tracks"]:
        found.append(_bad("record_inconsistent", "/fits_tracks", "check.fits_tracks"))
    limits = ctx["limits"]
    if limits is not None and record["no_participant_charge"] != limits["check"]["no_participant_charge"]:
        found.append(_bad("record_inconsistent", "/no_participant_charge", "check.charge"))
    return found + _single(record["wire"], "/wire", ctx["lists"])


PROPOSAL_FIELDS = ("problem", "reference_id", "wire_track", "proposal_key", "terms")


def _receipt_rules(record: dict, ctx: dict) -> list:
    found = _fields(record["codes"], "/codes")
    if not state_codes_ok(record["state"], record["codes"]):
        found.append(_bad("record_inconsistent", "/codes", "state.codes"))
    if record["proposal_sha256"] is None:
        derived = PROPOSAL_FIELDS + ("geometry_sha256", "design_hash", "parent", "values")
        bad = [name for name in derived if record[name] is not None]
    else:
        bad = [name for name in PROPOSAL_FIELDS if record[name] is None]
        if record["state"] not in ("rejected", "withdrawn"):
            bad += [name for name in ("geometry_sha256", "values") if record[name] is None]
    found += [_bad("record_inconsistent", "/" + name, "receipt.proposal_fields") for name in bad]
    if record["sealed"] != (record["ciphertext_ref"] is not None):
        found.append(_bad("record_inconsistent", "/ciphertext_ref", "receipt.sealed"))
    if ctx["audience"] == "public" and record["sealed"]:
        found.append(_bad("record_inconsistent", "/sealed", "privacy.sealed"))
    manifest = ctx["manifest"]
    if manifest is not None and record["manifest_id"] != hashes.manifest_id(manifest):
        found.append(_bad("record_inconsistent", "/manifest_id", "record.manifest"))
    return found


def _restricted_rules(record: dict, ctx: dict) -> list:
    found = []
    if record["source_ref"] != hashes.source_ref(record["action_id"]):
        found.append(_bad("ref_mismatch", "/source_ref", "ref.source"))
    manifest, key = ctx["manifest"], ctx["pseudonym_key"]
    if manifest is not None:
        if record["manifest_id"] != hashes.manifest_id(manifest):
            found.append(_bad("record_inconsistent", "/manifest_id", "record.manifest"))
        if key is not None and record["participant_ref"] != hashes.participant_ref(
                key, manifest["challenge"], record["actor_user_id"]):
            found.append(_bad("ref_mismatch", "/participant_ref", "ref.participant"))
    if record["proposal_sha256"] is None:
        if record["transport_id"] is not None or record["proposal_key"] is not None:
            found.append(_bad("ref_mismatch", "/transport_id", "ref.transport"))
    elif record["proposal_key"] is None or record["transport_id"] != hashes.transport_id(
            room=record["room"], account_id=record["actor_user_id"], actor_kind=record["actor_kind"],
            actor_agent_id=record["actor_agent_id"], manifest_id=record["manifest_id"],
            proposal_key=record["proposal_key"], proposal_sha256=record["proposal_sha256"]):
        found.append(_bad("ref_mismatch", "/transport_id", "ref.transport"))
    capability = (record["capability_sha256"], record["capability_epoch"], record["capability_revoked"])
    if (record["sealed"] and None in capability[:2]) or (not record["sealed"] and capability != (None, None, False)):
        found.append(_bad("record_inconsistent", "/capability_sha256", "receipt.sealed"))
    return found


def _status_rules(record: dict, ctx: dict) -> list:
    found = []
    manifest = ctx["manifest"]
    if manifest is not None and record["manifest_id"] != hashes.manifest_id(manifest):
        found.append(_bad("record_inconsistent", "/manifest_id", "record.manifest"))
    for index, receipt in enumerate(record["receipts"]):
        path = f"/receipts/{index}"
        found += _fields(receipt["codes"], path + "/codes")
        if not state_codes_ok(receipt["state"], receipt["codes"]):
            found.append(_bad("record_inconsistent", path + "/codes", "state.codes"))
        if receipt["run_id"] != hashes.run_id(record["manifest_id"], receipt["participant_ref"]):
            found.append(_bad("ref_mismatch", path + "/run_id", "ref.run_id"))
        if ctx["audience"] == "public" and receipt["sealed"]:
            found.append(_bad("record_inconsistent", path + "/sealed", "privacy.sealed"))
    return found


def _scored(row: dict) -> bool:
    return row["comparison"] is not None or bool(row["claims"]) or row["control"] is not None


def _results_rules(record: dict, ctx: dict) -> list:
    lists, manifest, found = ctx["lists"], ctx["manifest"], []
    for index, row in enumerate(record["rows"]):
        path = f"/rows/{index}"
        if ctx["audience"] == "public" and row["sealed"]:
            found.append(_bad("record_inconsistent", path + "/sealed", "privacy.sealed"))
        found += _single(row["temperature"], path + "/temperature", lists)
        found += _single(row["wire"], path + "/wire", lists)
        found += _single(row["paper"], path + "/paper", lists)
        for case_index, case in enumerate(row["sensitivity"]):
            found += _single(case, f"{path}/sensitivity/{case_index}", lists)
        for diagnostic_index, diagnostic in enumerate(row["diagnostics"]):
            found += _single(diagnostic, f"{path}/diagnostics/{diagnostic_index}", lists)
        found += _derived(row["comparison"], path + "/comparison", lists)
        for claim_index, claim in enumerate(row["claims"]):
            claim_path = f"{path}/claims/{claim_index}"
            found += _derived(claim, claim_path, lists)
            if claim["outcome"] in DECIDED and claim["label"] not in ("accepted", "illustrative"):
                found.append(_bad("label_mismatch", claim_path, "label.claim_outcome"))
        inputs = [row[name]["evaluator"] for name in ("temperature", "wire") if row[name] is not None]
        inputs += (row["comparison"] or {}).get("evaluators", [])
        inputs += [identity for claim in row["claims"] for identity in claim["evaluators"]]
        if _scored(row) and any(label_for(identity, lists) == "withdrawn" for identity in inputs):
            found.append(_bad("label_mismatch", path, "label.withdrawn_comparison"))
    if manifest is not None:
        found += _results_manifest_rules(record, manifest)
    return found


def _results_manifest_rules(record: dict, manifest: dict) -> list:
    found = []
    if record["manifest_id"] != hashes.manifest_id(manifest):
        found.append(_bad("record_inconsistent", "/manifest_id", "record.manifest"))
    if record["manifest_status"] != manifest["status"]:
        found.append(_bad("record_inconsistent", "/manifest_status", "record.manifest"))
    case_ids = [case["id"] for case in manifest["sensitivity"]["cases"]]
    controls = {control["id"]: control for control in manifest["discrimination_control"]}
    reference = manifest["reference"]
    for index, row in enumerate(record["rows"]):
        path = f"/rows/{index}"
        if not _scored(row):
            continue
        if manifest["status"] != "frozen":
            found.append(violation("manifest_not_frozen", path=path))
            continue
        if reference["t_ref"] is None or reference["w_ref"] is None:
            found.append(_bad("record_inconsistent", path, "results.scoring"))
        if (row["temperature"] is None or row["wire"] is None
                or row["temperature"]["evaluator"] != manifest["temperature"]["evaluator"]["identity"]
                or row["wire"]["evaluator"] != manifest["wire"]["evaluator"]):
            found.append(_bad("record_inconsistent", path, "results.same_evaluator"))
        found += _claim_cases(row, path, case_ids)
        if row["kind"] == "control":
            found += _control_result(row, path, controls)
    return found


def _claim_cases(row: dict, path: str, case_ids) -> list:
    """No case outside the predeclared list. A failed required case suppresses the claims (or leaves them unknown);
    a missing one leaves them incomplete, unknown or suppressed. Only a complete set of cases can decide a claim."""
    status = {case["case"]: case["status"] for case in row["sensitivity"]}
    if set(status) - set(case_ids):
        return [_bad("record_inconsistent", path + "/sensitivity", "claim.cases")]
    if any(status.get(case_id) == "failed" for case_id in case_ids):
        allowed = {"unknown", "suppressed"}
    elif any(status.get(case_id, "missing") == "missing" for case_id in case_ids):
        allowed = {"incomplete", "unknown", "suppressed"}
    else:
        return []
    return [_bad("record_inconsistent", f"{path}/claims/{index}", "claim.cases")
            for index, claim in enumerate(row["claims"]) if claim["outcome"] not in allowed]


def _control_result(row: dict, path: str, controls: dict) -> list:
    control = controls.get(row["control"]["id"])
    if control is None or control["id"] != row["id"]:
        return [_bad("record_inconsistent", path + "/control", "control.result")]
    observed = {(claim["type"], claim["r"]): claim["outcome"] for claim in row["claims"]}
    outcomes = [observed.get((expected["type"], expected["r"])) for expected in control["expected"]]
    if any(outcome not in DECIDED for outcome in outcomes):
        result = "incomplete"
    elif all(outcome == expected["outcome"] for outcome, expected in zip(outcomes, control["expected"])):
        result = "control_match"
    else:
        result = "control_mismatch"
    return [] if row["control"]["result"] == result else [
        _bad("record_inconsistent", path + "/control", "control.result")]


def _limits_rules(record: dict, ctx: dict) -> list:
    found, check = [], record["check"]
    if check["no_participant_charge"] and not (check["sponsored"] and check["solver_elapsed_limit_s"] is not None
                                               and check["wall_deadline_s"] is not None):
        found.append(_bad("record_inconsistent", "/check/no_participant_charge", "limits.charge"))
    if (check["solver_elapsed_limit_s"] is not None and check["wall_deadline_s"] is not None
            and check["solver_elapsed_limit_s"] > check["wall_deadline_s"]):
        found.append(_bad("record_inconsistent", "/check/solver_elapsed_limit_s", "limits.windows"))
    evaluations = record["evaluations"]
    for scope in ("account", "room"):
        hour, day = evaluations[f"per_{scope}_per_hour"], evaluations[f"per_{scope}_per_day"]
        if hour is not None and day is not None and day < hour:
            found.append(_bad("record_inconsistent", f"/evaluations/per_{scope}_per_day", "limits.windows"))
    for name in ("evaluation_call", "check"):
        budget = record["cpu"][name]
        values = (budget["reservation_s"], budget["enforcement_s"], budget["cleanup_headroom_s"])
        if None not in values and Decimal(repr(values[0])) != Decimal(repr(values[1])) + Decimal(repr(values[2])):
            found.append(_bad("record_inconsistent", f"/cpu/{name}", "limits.cpu"))
    return found


def _usage_rules(record: dict, ctx: dict) -> list:
    found = _fields(record["codes"], "/codes")
    unmeasured = record["measured_cpu_s"] is None
    reserved = Decimal(repr(record["reserved_cpu_s"]))
    if (reserved != Decimal(repr(record["enforced_cpu_s"])) + Decimal(repr(record["cleanup_headroom_cpu_s"]))
            or unmeasured and record["debited_cpu_s"] != record["reserved_cpu_s"]
            or record["outcome"] == "interrupted" and not unmeasured):
        found.append(_bad("record_inconsistent", "/debited_cpu_s", "usage.charge"))
    if record["enforcement"] == "stopped_in_flight" and (record["outcome"] != "failed" or [
            item["code"] for item in record["codes"]] != ["timeout"]):
        found.append(_bad("record_inconsistent", "/enforcement", "usage.enforcement"))
    measured = record["measured_cpu_s"]
    overrun = "unmeasured" if unmeasured else (
        "detected" if Decimal(repr(measured)) > reserved else "none")
    if record["overrun"] != overrun:
        found.append(_bad("record_inconsistent", "/overrun", "usage.overrun"))
    if record["run_id"] is not None:
        principal = record["participant_ref"]
        expected = "sentilab" if principal == "sentilab" else (principal or "")[:16]
        if record["run_id"].rsplit("-", 1)[-1] != expected:
            found.append(_bad("ref_mismatch", "/run_id", "ref.run_id"))
    return found


def _cursor_rules(record: dict, ctx: dict) -> list:
    if record["after"] is None:
        return []
    try:
        created_at_ns(record["after"]["created_at"])
    except ValueError:
        return [_bad("record_inconsistent", "/after/created_at", "cursor.created_at")]
    return []


def _current_rules(record: dict, ctx: dict) -> list:
    manifest = ctx["manifest"]
    if manifest is None:
        return []
    if (record["manifest_id"] != hashes.manifest_id(manifest) or record["problem"] != manifest["problem"]
            or record["version"] != manifest["version"]):
        return [_bad("record_inconsistent", "/manifest_id", "record.manifest")]
    return []


def _error_rules(record: dict, ctx: dict) -> list:
    return _fields(record["codes"], "/codes")


RULES = {"manifest": _manifest_rules, "check": _check_rules, "receipt": _receipt_rules,
         "restricted_receipt": _restricted_rules, "status": _status_rules, "results": _results_rules,
         "limits": _limits_rules, "usage": _usage_rules, "cursor": _cursor_rules, "current": _current_rules,
         "error": _error_rules}


def validate_record(kind: str, record, *, manifest=None, limits=None, pseudonym_key=None, lists=LISTS,
                    audience: str = "public") -> list:
    """Every violation of one record, in canonical order. The schema comes first; rules run only on a valid shape.

    manifest, limits and pseudonym_key enable the rules that need them; without them those rules are skipped.
    audience "public" (the default) refuses sealed entries; "private" is for capability-addressed responses. No
    record of any kind may carry a capability: only a private request does.
    """
    if kind not in RECORD_SCHEMAS or audience not in ("public", "private"):
        raise ValueError("unknown record kind or audience")
    found = schema_violations(RECORD_SCHEMAS[kind], record)
    if found:
        return canonical_list(found)
    ctx = {"manifest": manifest, "limits": limits, "pseudonym_key": pseudonym_key, "lists": lists,
           "audience": audience}
    found = RULES.get(kind, lambda _record, _ctx: [])(record, ctx)
    if kind != "private_request" and any(CAPABILITY.search(text) for text in _strings(record)):
        found.append(_bad("record_inconsistent", "", "privacy.capability"))
    return canonical_list(found)
