"""Canonical bytes and every hash and key the open-proposal contract binds (DESIGN rev 3 sections 3.4, 3.7, 3.9, 5.2, 7.4).

JSON is canonicalised with the repo's one RFC 8785 (JCS) implementation, sentilab_core.envelope.canonical: keys sorted
by UTF-16 code units, ECMAScript number text, no insignificant whitespace, UTF-8. Nonfinite numbers, unsafe integers and
lone surrogates fail closed. contracts/open-proposal-v1/canonical.mjs is the JavaScript twin; both run the same vectors.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from decimal import Decimal

from sentilab_core.envelope import RUN_ID, canonical

GEOMETRY_SCHEMA = "sentilab-open-geometry/1"
TRANSPORT_SCHEMA = "sentilab-open-transport-key/1"
TRANSPORT_PREFIX = "so1-"
TRANSPORT_HEX_CHARS = 48
SOURCE_PREFIX = "sentilab-open-source/1:"
SEALED_SCHEMA = "sentilab-open-sealed/1"
PROPOSAL_SCHEMA = "sentilab-open-proposal/1"
CHECK_REQUEST_SCHEMA = "sentilab-open-check-request/1"
TEAM_SCHEMA = "sentilab-open-team/1"
PUBLISH_SCHEMA = "sentilab-open-publish/1"
TEAM_KEY = "team"
PUBLISH_KEY_PREFIX = "publish:"
RUN_SCHEMA = "sentilab-open-run/1"
RUN_DIGEST_HEX_CHARS = 32
HEX64 = re.compile(r"[0-9a-f]{64}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value) -> str:
    """sha256 of the canonical bytes, as lowercase hex."""
    return sha256_hex(canonical(value))


def body_sha256(note: bytes) -> str:
    """The exact note bytes Senti returned (section 5.2): for a sealed note, the armoured ciphertext."""
    if not isinstance(note, (bytes, bytearray)):
        raise TypeError("the note is hashed as bytes")
    return sha256_hex(bytes(note))


def manifest_id(manifest) -> str:
    """sha256(JCS(manifest)) (section 4.1)."""
    return digest(manifest)


def geometry_object(item, manifest) -> dict:
    """The geometry_sha256 preimage (section 5.2): no actor, time, key, salt, terms or client."""
    return {"schema": GEOMETRY_SCHEMA, "problem": manifest["problem"],
            "fixture_config_sha256": manifest["fixture"]["config_sha256"],
            "units": item["units"], "anchor": item["anchor"],
            "dies": [{"die": d["die"], "x_um": d["x_um"], "y_um": d["y_um"], "rot_deg": d["rot_deg"]}
                     for d in item["dies"]]}


def geometry_sha256(item, manifest) -> str:
    return digest(geometry_object(item, manifest))


def content_sha256(item) -> str:
    """sha256(JCS(object)): proposal_sha256, request_sha256, the team hash or the publish hash. For a sealed object,
    the hash of the canonical salted plaintext: the retry identity, unchanged by re-encryption (section 3.7)."""
    return digest(item)


proposal_sha256 = content_sha256
request_sha256 = content_sha256


def source_ref(action_id: str) -> str:
    """sha256("sentilab-open-source/1:" + action_id) (section 7.4)."""
    return sha256_hex((SOURCE_PREFIX + action_id).encode("utf-8"))


def participant_ref(k_challenge: bytes, account_id: str) -> str:
    """HMAC-SHA256(k_challenge, account_id) (section 3.9): keyed per manifest family, so it does not link across
    challenges and nobody without the key can compute it from an account id."""
    if not isinstance(k_challenge, (bytes, bytearray)) or len(k_challenge) < 32:
        raise ValueError("k_challenge is at least 32 bytes")
    return hmac.new(bytes(k_challenge), account_id.encode("utf-8"), hashlib.sha256).hexdigest()


def actor_slot(actor_kind: str, actor_id: str | None) -> str:
    """The row's server-stamped actor (section 3.5): "agent:<agentId>" or "human". Never a label."""
    if actor_kind == "human" and actor_id is None:
        return "human"
    if actor_kind == "agent" and isinstance(actor_id, str) and actor_id:
        return "agent:" + actor_id
    raise ValueError("actor kind and actor id disagree")


def logical_key(item) -> str:
    """The logical key a transport key derives from (section 3.4): the proposal_key, the request_key, "team", or
    "publish:<proposal_sha256>" for a publish reply (rev 3 names no logical key for publish; CONTRACT.md)."""
    schema = item.get("schema")
    if schema == PROPOSAL_SCHEMA:
        return item["proposal_key"]
    if schema == CHECK_REQUEST_SCHEMA:
        return item["request_key"]
    if schema == TEAM_SCHEMA:
        return TEAM_KEY
    if schema == PUBLISH_SCHEMA:
        return PUBLISH_KEY_PREFIX + item["proposal_sha256"]
    raise ValueError("not a contract object")


def transport_key_object(*, room: str, account: str, actor_slot: str, manifest_id: str, logical_key: str,
                         content_sha256: str) -> dict:
    return {"schema": TRANSPORT_SCHEMA, "room": room, "account": account, "actor_slot": actor_slot,
            "manifest_id": manifest_id, "logical_key": logical_key, "content_sha256": content_sha256}


def transport_key(**fields) -> str:
    """"so1-" + hex(sha256(JCS(preimage)))[0:48]: 52 characters (section 3.4)."""
    return TRANSPORT_PREFIX + digest(transport_key_object(**fields))[:TRANSPORT_HEX_CHARS]


def transport_key_for(item, *, room: str, account: str, actor_kind: str, actor_id: str | None) -> str:
    """The key a client derives for one contract object, and the intake recomputes from the row."""
    return transport_key(room=room, account=account, actor_slot=actor_slot(actor_kind, actor_id),
                         manifest_id=item["manifest_id"], logical_key=logical_key(item),
                         content_sha256=content_sha256(item))


def run_id_object(manifest_id: str, participant_ref: str, proposal_sha256: str) -> dict:
    """The run id's preimage: the full manifest identity, the server-derived participant reference and the full
    proposal identity, domain-separated. Each must be 64 lower-case hex characters, in full."""
    for value in (manifest_id, participant_ref, proposal_sha256):
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise ValueError("a run id binds three full sha256 hex digests")
    return {"schema": RUN_SCHEMA, "manifest_id": manifest_id, "participant_ref": participant_ref,
            "proposal_sha256": proposal_sha256}


def run_id(manifest_id: str, participant_ref: str, proposal_sha256: str) -> str:
    """One signed run per account and proposal: open-<manifest_id 8 hex>-<32 hex of sha256(JCS(preimage))>.

    Root's review of DESIGN.md:898 (open-<manifest 8 hex>-<proposal_sha256 16 hex>): the same proposal bytes from two
    accounts must not share a run. The id is bound to the account through participant_ref, so a same-account retry
    (the same bytes, the same account) still lands on the same run; evaluation reuse across accounts is keyed by the
    geometry hash (evaluation_cache_key), never by the run id.
    """
    value = "open-" + manifest_id[:8] + "-" + digest(run_id_object(manifest_id, participant_ref, proposal_sha256))[
        :RUN_DIGEST_HEX_CHARS]
    if not RUN_ID.fullmatch(value):
        raise ValueError("invalid run id")
    return value


def evaluation_cache_key(manifest_id: str, geometry_sha256: str) -> tuple:
    """Section 5.5: the same geometry in the same manifest reuses the first complete evaluation, whoever posted it.
    The cache is keyed by geometry, apart from the account-bound run id and receipt."""
    for value in (manifest_id, geometry_sha256):
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise ValueError("an evaluation cache key binds two full sha256 hex digests")
    return (manifest_id, geometry_sha256)


def sealed_header(manifest_id: str, key_version: int) -> str:
    """A sealed note's first line (section 3.7): sentilab-open-sealed/1 <manifest_id> <key_version>."""
    if isinstance(key_version, bool) or not isinstance(key_version, int) or key_version < 1:
        raise ValueError("the key version is a positive integer")
    return f"{SEALED_SCHEMA} {manifest_id} {key_version}"


def r_key(r) -> str:
    """A q_r key: "0", or r with exactly two decimals ("0.10"). r must have at most two decimals."""
    exact = Decimal(repr(r))
    if exact != exact.quantize(Decimal("0.01")) or exact < 0:
        raise ValueError("r has at most two decimals")
    return "0" if exact == 0 else f"{exact:.2f}"


def q_r(w_c_mm, w_r_mm, key: str) -> float:
    """q_r = W(c) - (1 + r) W(R) (section 4.6), exact in decimal, then the nearest double. Every input carries at
    most a few decimals, so the double prints back as the exact decimal."""
    return float(Decimal(repr(w_c_mm)) - (1 + Decimal(key)) * Decimal(repr(w_r_mm)))


def conductor_geometry(item, manifest) -> dict:
    """values for the receipt, as the conductor writes them (sentilab_core/conductor.py:383-386): per die, the
    lower-left corner and footprint in mm.

    Each coordinate is one exact integer ratio rounded once, (2 x centre - footprint) / 2000, so every language gets
    the same doubles. Float arithmetic in mm (centre - width / 2) does not, and is not the contract.
    """
    geometry = []
    for die in item["dies"]:
        spec = manifest["dies"][die["die"]]
        width, height = (spec["h_um"], spec["w_um"]) if die["rot_deg"] == 90 else (spec["w_um"], spec["h_um"])
        geometry.append({"id": f"tap-chiplet-{die['die']}",
                         "xLL": (2 * die["x_um"] - width) / 2000, "yLL": (2 * die["y_um"] - height) / 2000,
                         "w": width / 1000, "h": height / 1000, "layer": 0})
    return {"geometry": geometry, "units": "mm", "scenario_id": "nominal"}
