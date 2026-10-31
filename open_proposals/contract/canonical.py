"""Canonical bytes and every hash the open-proposal contract binds (CONTRACT.md, "Canonical form and hashes").

JSON is canonicalised with the repo's one RFC 8785 (JCS) implementation, sentilab_core.envelope.canonical: keys sorted
by UTF-16 code units, ECMAScript number text, no insignificant whitespace, UTF-8. Nonfinite numbers, unsafe integers and
lone surrogates fail closed. contracts/open-proposal-v1/canonical.mjs is the JavaScript twin; both run the same vectors.
"""
from __future__ import annotations

import hashlib
import hmac

from sentilab_core.envelope import RUN_ID, canonical

GEOMETRY_SCHEMA = "sentilab-open-geometry/1"
# DESIGN 7.4: source_ref = sha256("sentilab-open-source/1:" + action_id). Action ids are random UUIDs.
SOURCE_PREFIX = "sentilab-open-source/1:"
# The #59 review: the public pseudonym is keyed per challenge, so it can't be recomputed from a known account id.
PSEUDONYM_DOMAIN = "sentilab-open-pseudonym/1"
TRANSPORT_DOMAIN = "sentilab-open-transport/1"
TRANSPORT_PREFIX = "open-tk1-"
# The binding Idempotency-Key limit across the four transports: the hosted MCP's 128 (sentinelayer-api 6f8058f5
# src/routes/mcp.py:100); REST actions allow 180 visible characters (src/routes/sessions.py:1032).
TRANSPORT_MAX_LENGTH = 128
SENTILAB_PRINCIPAL = "sentilab"
# Sealed proposals (decision A10): the plaintext carries a salt, so its canonical hash (the retry identity) is
# unguessable; the salt also keys the per-request capability that addresses the private status, results and receipt.
SALT_DOMAIN = "sentilab-open-salt/1"
CAPABILITY_DOMAIN = "sentilab-open-capability/1"
CAPABILITY_PREFIX = "opencap1-"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value) -> str:
    """sha256 of the canonical bytes, as lowercase hex."""
    return sha256_hex(canonical(value))


def body_sha256(note: bytes) -> str:
    """The exact note bytes Senti returned (DESIGN 5.2)."""
    if not isinstance(note, (bytes, bytearray)):
        raise TypeError("the note is hashed as bytes")
    return sha256_hex(bytes(note))


def geometry_object(proposal, manifest) -> dict:
    """The geometry_sha256 preimage (DESIGN 5.2): layout in its task context, without actor, time, key or client."""
    return {"schema": GEOMETRY_SCHEMA, "problem": proposal["problem"],
            "fixture_config_sha256": manifest["fixture"]["config_sha256"],
            "units": proposal["units"], "anchor": proposal["anchor"], "lattice_um": proposal["lattice_um"],
            "dies": [{"die": d["die"], "x_um": d["x_um"], "y_um": d["y_um"], "rot_deg": d["rot_deg"]}
                     for d in proposal["dies"]]}


def geometry_sha256(proposal, manifest) -> str:
    return digest(geometry_object(proposal, manifest))


def proposal_sha256(proposal) -> str:
    """The candidate revision hash: the whole proposal, provenance kept. Clients compute it; it is the status key."""
    return digest(proposal)


def manifest_id(manifest) -> str:
    return digest(manifest)


def source_ref(action_id: str) -> str:
    return sha256_hex((SOURCE_PREFIX + action_id).encode("utf-8"))


def participant_ref(pseudonym_key: bytes, challenge: str, account_id: str) -> str:
    """HMAC-SHA256 under the challenge's secret key, over JCS([domain, challenge, account id])."""
    if not isinstance(pseudonym_key, (bytes, bytearray)) or len(pseudonym_key) < 32:
        raise ValueError("the pseudonym key is at least 32 bytes")
    message = canonical([PSEUDONYM_DOMAIN, challenge, account_id])
    return hmac.new(bytes(pseudonym_key), message, hashlib.sha256).hexdigest()


def actor_slot(actor_kind: str, actor_agent_id: str | None) -> str:
    """Senti's server-stamped actor: the account's human slot, or one of its admitted agents. Never a label."""
    if actor_kind == "human" and actor_agent_id is None:
        return "human"
    if actor_kind == "agent" and isinstance(actor_agent_id, str) and actor_agent_id:
        return "agent:" + actor_agent_id
    raise ValueError("actor kind and agent id disagree")


def transport_id(*, room: str, account_id: str, actor_kind: str, actor_agent_id: str | None, manifest_id: str,
                 proposal_key: str, proposal_sha256: str) -> str:
    """The transport idempotency key: identical canonical content from the same room, account and actor slot gives
    the same key; any content change gives a new one under the same logical key (account, manifest, proposal_key)."""
    material = canonical([TRANSPORT_DOMAIN, room, account_id, actor_slot(actor_kind, actor_agent_id), manifest_id,
                          proposal_key, proposal_sha256])
    key = TRANSPORT_PREFIX + sha256_hex(material)
    if len(key) > TRANSPORT_MAX_LENGTH:
        raise ValueError("transport id exceeds the Idempotency-Key limit")
    return key


def derive_salt(client_secret: bytes, manifest_id: str, proposal_key: str) -> str:
    """The recommended salt: a retry recomputes it from the client's own secret, so nothing needs storing. Any 32
    bytes of fresh entropy, kept for retries, is equally valid; the server never sees the client secret."""
    if not isinstance(client_secret, (bytes, bytearray)) or len(client_secret) < 32:
        raise ValueError("the client secret is at least 32 bytes")
    return hmac.new(bytes(client_secret), canonical([SALT_DOMAIN, manifest_id, proposal_key]),
                    hashlib.sha256).hexdigest()


def capability(salt: str, manifest_id: str, proposal_sha256: str, epoch: int = 1) -> str:
    """The bearer capability for one sealed revision at one epoch, keyed by its salt: whoever holds it can read that
    revision's private status, results and receipt; it proves nothing about authorship. The client derives it, the
    server re-derives it after opening the envelope and keeps only its sha256. Rotation moves to the next epoch;
    the epoch is not secret, the salt is."""
    key = bytes.fromhex(salt)
    if len(key) != 32:
        raise ValueError("the salt is 32 bytes")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
        raise ValueError("the epoch is a positive integer")
    return CAPABILITY_PREFIX + hmac.new(key, canonical([CAPABILITY_DOMAIN, manifest_id, proposal_sha256, epoch]),
                                        hashlib.sha256).hexdigest()


def capability_sha256(value: str) -> str:
    return sha256_hex(value.encode("ascii"))


def ciphertext_ref(age_file: bytes) -> str:
    """The sealed note's reference: sha256 of the decoded age file bytes."""
    return sha256_hex(bytes(age_file))


def run_id(manifest_id: str, participant_ref: str) -> str:
    """One ledger run per (manifest, principal): open-<manifest 8 hex>-<participant_ref 16 hex> (DESIGN 7.4)."""
    principal = SENTILAB_PRINCIPAL if participant_ref == SENTILAB_PRINCIPAL else participant_ref[:16]
    value = "open-" + manifest_id[:8] + "-" + principal
    if not RUN_ID.fullmatch(value):
        raise ValueError("invalid run id")
    return value


def conductor_geometry(proposal, manifest) -> dict:
    """values for the receipt, as the conductor writes them: per die, lower-left corner and footprint in mm.

    Each coordinate is one exact integer ratio rounded once, (2 x centre - footprint) / 2000, so every language gets
    the same doubles. Float arithmetic in mm (centre - width / 2) does not, and is not the contract.
    """
    geometry = []
    for die in proposal["dies"]:
        spec = manifest["dies"][die["die"]]
        width, height = (spec["h_um"], spec["w_um"]) if die["rot_deg"] == 90 else (spec["w_um"], spec["h_um"])
        geometry.append({"id": f"tap-chiplet-{die['die']}",
                         "xLL": (2 * die["x_um"] - width) / 2000, "yLL": (2 * die["y_um"] - height) / 2000,
                         "w": width / 1000, "h": height / 1000, "layer": 0})
    return {"geometry": geometry, "units": "mm", "scenario_id": "nominal"}
