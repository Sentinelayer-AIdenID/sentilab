"""Forge view-envelope/0.4 hashing and strict, bounded JCS values.

The only signer input is an object exposing key_id, public_key and sign(bytes).
Key material is owned by the service; this module never loads or saves it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "view-envelope/0.4"
MAX_BYTES = 64 * 1024
MAX_ITEMS = 64
MAX_STRING = 512
MAX_DEPTH = 8
RUN_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def canonical(value) -> bytes:
    """RFC 8785 for JSON values; unsafe integers and lone surrogates fail closed.

    Python's shortest-round-trip float digits are formatted with ECMAScript's
    fixed/scientific thresholds. Keys sort by UTF-16 code units, not code points.
    Unlike JSON.stringify, nonfinite numbers are rejected before signing.
    """
    def encode(item):
        if item is None:
            return "null"
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, str):
            item.encode("utf-8", errors="strict")
            return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if isinstance(item, int):
            if abs(item) <= 9007199254740991:
                return str(item)
            if not math.isfinite(float(item)) or int(float(item)) != item:
                raise ValueError("integer is not exactly representable as a JSON number")
            item = float(item)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("nonfinite JSON number")
            if item == 0:
                return "0"
            sign = "-" if item < 0 else ""
            number = repr(abs(item)).lower()
            coefficient, _, exponent = number.partition("e")
            exponent = int(exponent or "0")
            left, _, right = coefficient.partition(".")
            digits = (left + right).lstrip("0").rstrip("0") or "0"
            # repr uses fixed notation for [1e-4, 1e16); its leading zero is
            # accounted for by the decimal exponent computed from the value.
            if left != "0":
                point = len(left) + exponent
            else:
                point = exponent - (len(right) - len(right.lstrip("0")))
            if 0 < point <= 21:
                body = (digits + "0" * (point - len(digits)) if point >= len(digits)
                        else digits[:point] + "." + digits[point:])
            elif -6 < point <= 0:
                body = "0." + "0" * (-point) + digits
            else:
                exp = point - 1
                body = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
                body += "e" + ("+" if exp >= 0 else "") + str(exp)
            return sign + body
        if isinstance(item, list):
            return "[" + ",".join(encode(v) for v in item) + "]"
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError("JSON object keys must be strings")
            keys = sorted(item, key=lambda key: key.encode("utf-16be", errors="strict"))
            return "{" + ",".join(encode(k) + ":" + encode(item[k]) for k in keys) + "}"
        raise ValueError("unsupported JSON value")

    return encode(value).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def genesis(run_id):
    validate_run_id(run_id)
    return hashlib.sha256(("sentilab-view-genesis:" + run_id).encode()).hexdigest()


def validate_run_id(run_id):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run_id")


def check_caps(value):
    # Match the contract: root container is level one; primitives do not
    # contribute a container level. Validate iteratively before canonical().
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, str):
            if len(item) > MAX_STRING:
                raise ValueError("oversize: string")
            item.encode("utf-8", errors="strict")
        elif isinstance(item, (dict, list)):
            if depth > MAX_DEPTH:
                raise ValueError("oversize: nesting")
            if isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise ValueError("JSON object keys must be strings")
                    if key in ("geometry", "center_temps", "artifact_hashes"):
                        if not isinstance(child, (dict, list)) or len(child) > MAX_ITEMS:
                            raise ValueError("oversize: " + key)
                    stack.extend(((key, depth + 1), (child, depth + 1)))
            else:
                stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("nonfinite JSON number")
        elif isinstance(item, int):
            if item.bit_length() > 1024:
                raise ValueError("JSON number out of range")
        elif item is not None:
            raise ValueError("unsupported JSON value")
    data = canonical(value)
    if len(data) > MAX_BYTES:
        raise ValueError("oversize: envelope")
    return data


def _validate_structure(envelope, run_id):
    required = {"v", "event", "run", "actor", "prev_hash", "hash", "sig", "ts"}
    if not isinstance(envelope, dict) or not required <= envelope.keys() or envelope.keys() - required - {"values"}:
        raise ValueError("invalid envelope fields")
    if envelope["v"] != VERSION:
        raise ValueError("invalid envelope version")
    if (not isinstance(envelope["run"], dict) or not isinstance(envelope["actor"], dict) or
            not isinstance(envelope["event"], dict)):
        raise ValueError("invalid envelope structure")
    run, actor, event = envelope["run"], envelope["actor"], envelope["event"]
    if set(run) != {"run_id", "arm", "family", "seed", "ticket_id"}:
        raise ValueError("invalid run fields")
    validate_run_id(run["run_id"])
    if run["run_id"] != run_id:
        raise ValueError("run_mismatch")
    if (any(not isinstance(run[key], str) for key in ("arm", "family", "ticket_id")) or
            type(run["seed"]) is not int):
        raise ValueError("invalid run structure")
    if set(actor) != {"agent_id", "life_id", "lab", "grant_id"} or not isinstance(actor["lab"], str):
        raise ValueError("invalid actor fields")
    if any(actor[key] is not None and not isinstance(actor[key], str)
           for key in ("agent_id", "life_id", "grant_id")):
        raise ValueError("invalid actor identity")
    if set(event) != {"event_id", "seq", "type", "actor_role", "body"}:
        raise ValueError("invalid event fields")
    if (not isinstance(event["body"], dict) or not isinstance(event["event_id"], str) or
            not event["event_id"] or not isinstance(event["type"], str)):
        raise ValueError("invalid event structure")
    if type(event["seq"]) is not int or event["seq"] < 1:
        raise ValueError("invalid sequence")
    if event["actor_role"] not in ("lab", "core", "acceptance_gate"):
        raise ValueError("invalid actor role")
    if (actor["lab"] == "gate") != (event["actor_role"] == "acceptance_gate"):
        raise ValueError("invalid gate actor")
    if (event["type"] == "lifecycle.transition" and
            event["body"].get("to") in ("accepted", "non_improving_current", "within_margin") and
            event["actor_role"] != "acceptance_gate"):
        raise ValueError("board outcome requires core gate")
    if "values" in envelope:
        if not isinstance(envelope["values"], dict) or not (event["type"] == "verify.add" or
                event["type"] == "node.create" and event["body"].get("kind") in ("candidate", "measurement")):
            raise ValueError("invalid values event")
    sig = envelope["sig"]
    if (not isinstance(sig, dict) or set(sig) != {"key_id", "alg", "value"} or
            sig["alg"] != "ed25519" or not isinstance(sig["key_id"], str) or not sig["key_id"]):
        raise ValueError("invalid signature fields")
    for value, length in ((sig["value"], 128), (envelope["hash"], 64), (envelope["prev_hash"], 64)):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, value):
            raise ValueError("invalid hash or signature encoding")
    if not isinstance(envelope["ts"], str):
        raise ValueError("invalid timestamp")


def build(*, event, run, actor, prev_hash, signer, values=None, ts=None):
    envelope = {"v": VERSION, "event": event, "run": run, "actor": actor,
                "prev_hash": prev_hash,
                "ts": ts or datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "hash": "0" * 64,
                "sig": {"key_id": signer.key_id, "alg": "ed25519", "value": "0" * 128}}
    if values is not None:
        envelope["values"] = values
    _validate_structure(envelope, run.get("run_id") if isinstance(run, dict) else None)
    # Fixed-width placeholders enforce the WHOLE envelope cap before signing.
    # Parsing the validated canonical bytes also detaches mutable caller inputs.
    envelope = json.loads(check_caps(envelope))
    envelope["hash"] = digest({k: v for k, v in envelope.items() if k not in ("hash", "sig")})
    envelope["sig"]["value"] = signer.sign(envelope["hash"].encode()).hex()
    _validate_structure(envelope, envelope["run"]["run_id"])
    return envelope


def verify(envelope, *, run_id, public_keys):
    """Verify one envelope against caller-pinned keys, never keys from the file."""
    try:
        _validate_structure(envelope, run_id)
        check_caps(envelope)
        sig = envelope["sig"]
        body = {k: v for k, v in envelope.items() if k not in ("hash", "sig")}
        computed = digest(body)
        if envelope["hash"] != computed:
            raise ValueError("hash_mismatch")
        Ed25519PublicKey.from_public_bytes(public_keys[sig["key_id"]]).verify(
            bytes.fromhex(sig["value"]), computed.encode())
    except (InvalidSignature, KeyError, TypeError, OverflowError, UnicodeError) as exc:
        raise ValueError("unverified envelope") from exc
    return envelope
