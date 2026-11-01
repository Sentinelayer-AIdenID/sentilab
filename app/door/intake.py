"""The submit body, read in the contract's stage order and mapped onto a contract proposal (no I/O).

1. transport   at most 4,096 bytes (the contract's plaintext cap), UTF-8: oversize, not_utf8
2. envelope    one JSON object, parsed by the contract's strict reader: too_deep, malformed_json, duplicate_key,
               nonfinite_number; then the door's envelope schema (additionalProperties false at every level):
               unknown_field, schema_invalid
3. token       the Worker verified the HMAC; this service re-checks purpose, case and expiry (403 token_scope or
               token_expired, the door token vocabulary of AGENT-DOOR section 1)
4. layout      the compact l= string (AGENT-DOOR section 3) or a JSON list of contract dies, mapped deterministically:
               dies[i] = {die: i, x_um: 500 x, y_um: 500 y, rot_deg: 90 r}. Whatever the mapping cannot read is
               schema_invalid at /layout; the dies then meet the contract's own dies schema
5. proposal    the manifest's units and anchor, geometry_sha256 per CONTRACT.md, a keyed salt and logical key
6. legality    validate_local with the pinned TapGeometry checker; only "legal" passes. Rotations come from the
               pinned catalogue: a CPU may take r 0 or 1 (0 or 90 degrees), a DRAM only r 0; anything else is
               refused by the contract (rotation_not_allowed, or schema_invalid for 180 and 270)

Submission violations carry only codes, schema-known paths and keywords, die indices and whole micrometres;
a request_key is kept only as a keyed digest. Arrival declarations are a separate opt-in public display record.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import unicodedata2 as declaration_unicode

from open_proposals.contract import canonical as hashes
from open_proposals.contract.codes import canonical_list, violation
from open_proposals.contract.schemas import REGISTRY, SCHEMAS, StrictValidator, pointer
from open_proposals.contract.validator import _json as strict_json
from open_proposals.contract.validator import validate_local
from sentilab_core.envelope import canonical

from .policy import CASE, CLASSES, OPERATORS, PURPOSE, PURPOSES, TOKEN_SKEW_S, TOKEN_TTL_S, principal_for

MAX_BODY_BYTES = 4096
MAX_COMPACT_CHARS = 128
COMPACT_ITEM = re.compile(r"(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.([0-9])\Z")
PROPOSAL_SCHEMA = "sentilab-open-proposal/1"
VISITOR_NOTICE = "sentilab-public-visitor/1"
VISITOR_DISCLOSURE = ("Your visit time, detector classification and selected purpose are public. If you opt in, "
                      "your declared name, reason and source category are also public. We keep a handle internally "
                      "to count purpose passes; that handle is not published. These declarations are not verified identity. "
                      "Referrer URLs and query strings are not collected automatically, and the raw purpose-pass "
                      "credential is not added as a generated feed field. All text you enter in name or reason "
                      "is public. Do not include private information.")
DISPLAY_TEXT = r"^[^\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]*$"
if declaration_unicode.unidata_version != "16.0.0":
    raise RuntimeError("declaration validation requires Unicode 16.0.0")
_REFUSED_DECLARATION_CATEGORIES = frozenset(("Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"))
_MAX_COMBINING_RUN = 8
# Match the Worker's nameKey rule; Python's \s includes extra C0/C1 characters.
_NAME_SPACE = re.compile(r"[\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")
_RESERVED_NAMES = frozenset(("human", "you", "senti", "participant", "unidentified participant",
                             "system", "owner", "admin", "moderator"))
COMMON = SCHEMAS["common"]["$id"]
SUBMIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["token_claims", "layout", "terms"],
    "properties": {
        "token_claims": {
            "type": "object",
            "additionalProperties": False,
            "required": ["purpose", "case", "nonce", "exp"],
            "properties": {
                "purpose": {"enum": list(PURPOSES)},
                "case": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"},
                "nonce": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
                "exp": {"type": "integer", "minimum": 1, "maximum": 9007199254740991},
            },
        },
        "layout": {"anyOf": [{"type": "string", "maxLength": MAX_COMPACT_CHARS},
                             {"type": "array", "maxItems": 32}]},
        "terms": {"$ref": COMMON + "#/$defs/terms_version"},
        "request_key": {"$ref": COMMON + "#/$defs/key"},
        "class": {"enum": list(CLASSES)},
        "operator": {"enum": list(OPERATORS)},
    },
}
ARRIVAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["class"],
    "properties": {
        "class": {"enum": list(CLASSES)},
        "operator": {"enum": list(OPERATORS)},
        "purpose": {"enum": list(PURPOSES)},
        "nonce": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
        "declaration": {
            "type": "object", "additionalProperties": False, "required": ["notice_version"],
            "properties": {
                "notice_version": {"const": VISITOR_NOTICE},
                "name": {"type": "string", "maxLength": 64, "pattern": DISPLAY_TEXT},
                "reason": {"type": "string", "maxLength": 160, "pattern": DISPLAY_TEXT},
                "source": {"enum": ["moltbook", "senti", "github", "direct", "other"]},
            },
        },
    },
}
_SUBMIT = StrictValidator(SUBMIT_SCHEMA, registry=REGISTRY)
_ARRIVAL = StrictValidator(ARRIVAL_SCHEMA, registry=REGISTRY)
_DIES = StrictValidator({"$ref": COMMON + "#/$defs/dies"}, registry=REGISTRY)


def schema_errors(validator, instance, prefix=()) -> list:
    """Every schema error as a contract violation (the mapping of schemas.schema_violations): paths are built only
    from schema-declared names and indices, never from submitted text."""
    found = []
    for error in validator.iter_errors(instance):
        path = list(prefix) + list(error.absolute_path)
        if error.validator == "additionalProperties":
            found.append(violation("unknown_field", path=pointer(path)))
        elif error.validator == "required":
            present = error.instance if isinstance(error.instance, dict) else {}
            found += [violation("schema_invalid", path=pointer(path + [name]), keyword="required")
                      for name in error.validator_value if name not in present]
        else:
            found.append(violation("schema_invalid", path=pointer(path), keyword=str(error.validator)))
    return canonical_list(found)


def read_object(raw: bytes, validator, size: int | None = None) -> tuple:
    """(object, violations): stages 1 and 2. Each stage stops at its first finding, as the contract's intake does.
    size is the body's declared length when it was not read in full."""
    size = len(raw) if size is None else size
    if size > MAX_BODY_BYTES or len(raw) > MAX_BODY_BYTES:
        return None, [violation("oversize", size_bytes=min(max(size, len(raw)), 1_000_000_000))]
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, [violation("not_utf8")]
    value, found = strict_json(text, fenced=False)
    if found:
        return None, canonical_list(found)
    found = schema_errors(validator, value)
    return (None, found) if found else (value, [])


def read_submit(raw: bytes, size: int | None = None) -> tuple:
    return read_object(raw, _SUBMIT, size)


def _declaration_text_allowed(text: str) -> bool:
    """Check original code points using the pinned Unicode 16 contract; never rewrite text."""
    combining_run = 0
    for char in text:
        category = declaration_unicode.category(char)
        if category in _REFUSED_DECLARATION_CATEGORIES:
            return False
        combining_run = combining_run + 1 if category in ("Mn", "Mc", "Me") else 0
        if combining_run > _MAX_COMBINING_RUN:
            return False
    return True


def read_arrival(raw: bytes, size: int | None = None) -> tuple:
    value, found = read_object(raw, _ARRIVAL, size)
    if found:
        return None, found
    declaration = value.get("declaration", {})
    found = [violation("schema_invalid", path="/declaration/" + field, keyword="pattern")
             for field in ("name", "reason") if not _declaration_text_allowed(declaration.get(field, ""))]
    if found:
        return None, canonical_list(found)
    name = declaration.get("name", "")
    # Compare a key only. Accepted declaration text remains exactly as submitted.
    key = declaration_unicode.normalize("NFKC", name)
    key = "".join(char for char in key if declaration_unicode.category(char) != "Cf")
    key = _NAME_SPACE.sub(" ", key).strip(" ").lower()
    if key in _RESERVED_NAMES:
        return None, [violation("schema_invalid", path="/declaration/name", keyword="not")]
    return value, []


def token_refusal(claims: dict, now: float):
    """None when the token's claims allow a placement now; otherwise the 403 body (AGENT-DOOR section 1)."""
    if claims["purpose"] != PURPOSE or claims["case"] != CASE:
        return {"error": "token_scope", "allowed": claims["purpose"]}
    if not now < claims["exp"]:
        return {"error": "token_expired"}
    if claims["exp"] > now + TOKEN_TTL_S + TOKEN_SKEW_S:
        return {"error": "token_invalid"}
    return None


def compact_dies(text: str) -> tuple:
    """The compact l= string as contract dies, or the violation that refuses it (AGENT-DOOR section 3)."""
    items = text.split(",")
    dies = []
    for index, item in enumerate(items):
        match = COMPACT_ITEM.match(item)
        if not match:
            return None, [violation("schema_invalid", path="/layout", keyword="pattern")]
        x, y, r = (int(part) for part in match.groups())
        dies.append({"die": index, "x_um": x * 500, "y_um": y * 500, "rot_deg": 90 * r})
    return dies, []


def compact_text(dies) -> str:
    """The inverse mapping, for dies on the 500 um lattice with rot_deg a multiple of 90."""
    return ",".join(f"{die['x_um'] // 500}.{die['y_um'] // 500}.{die['rot_deg'] // 90}" for die in dies)


def layout_dies(layout) -> tuple:
    """(dies, violations): stage 4. The dies then pass the contract's dies schema, paths under /dies."""
    if isinstance(layout, str):
        dies, found = compact_dies(layout)
        if found:
            return None, found
    else:
        dies = layout
    found = schema_errors(_DIES, dies, prefix=("dies",))
    return (None, found) if found else (dies, [])


@dataclass(frozen=True)
class Proposal:
    principal: str
    item: dict
    proposal_sha256: str
    geometry_sha256: str
    run_id: str


def build_proposal(policy, *, principal: str, terms: str, dies: list, request_key: str | None) -> Proposal:
    """Stage 5: the contract proposal the door posts on the principal's behalf. Public: the door runs an open board."""
    manifest = policy.manifest
    item = {"schema": PROPOSAL_SCHEMA, "manifest_id": policy.manifest_id, "terms": terms,
            "units": manifest["legality"]["units"], "anchor": manifest["legality"]["anchor"],
            "dies": [{"die": d["die"], "x_um": d["x_um"], "y_um": d["y_um"], "rot_deg": d["rot_deg"]} for d in dies]}
    geometry = hashes.geometry_sha256(item, manifest)
    if request_key is None:
        key = "gk-" + geometry[:40]
    else:
        key = "rk-" + policy.keyed("sentilab-door-request-key/1", principal, policy.manifest_id, request_key)[:40]
    item.update({"proposal_key": key, "parent": None, "visibility": "public",
                 "salt": policy.keyed("sentilab-door-salt/1", principal, policy.manifest_id, key)[:32],
                 "geometry_sha256": geometry})
    content = hashes.content_sha256(item)
    run_id = hashes.run_id(policy.manifest_id, policy.participant_ref(principal), content)
    return Proposal(principal, item, content, geometry, run_id)


def legality(policy, item: dict):
    """Stage 6: validate_local with the pinned checker. Returns (legal, violations)."""
    outcome = validate_local(canonical(item), manifests={policy.manifest_id: policy.manifest},
                             manifest_id=policy.manifest_id,
                             layout_checker=policy.checker)
    if outcome.outcome == "legal":
        return True, []
    if outcome.outcome == "rejected":
        return False, list(outcome.violations)
    raise RuntimeError("the legality gate did not reach a decision")       # contract_valid: the checker never ran


__all__ = ["MAX_BODY_BYTES", "Proposal", "build_proposal", "compact_dies", "compact_text", "layout_dies", "legality",
           "principal_for", "read_arrival", "read_submit", "token_refusal"]
