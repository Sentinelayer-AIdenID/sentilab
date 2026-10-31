"""Service-authorized flight records; embedded keys alone establish only integrity.

Provision public roots in web/public/trust-pins.json through reviewed
configuration, never from an uploaded record. No production root was supplied
with this source: the empty registry deliberately authenticates nothing.
Rotation adds a key_id; removing it revokes all its certificates. Verification
uses current time (including for historical records), not an untrusted timestamp
from the file. Expired/revoked records can still pass the separate integrity check.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

if __package__:
    from .controller import FlightRecord, canonical, public_hex
else:
    from controller import FlightRecord, canonical, public_hex


_PIN_PATH = Path(__file__).resolve().parents[1] / "web/public/trust-pins.json"
PINNED_SERVICE_KEYS = MappingProxyType({entry["key_id"]: entry["public_key_hex"] for entry in
    (json.loads(_PIN_PATH.read_text()) if _PIN_PATH.is_file() else [])})
CERTIFICATE_VERSION = "sentilab.lane-certificate.v1"
CERTIFICATE_LIFETIME_SECONDS = 24 * 60 * 60
_CERTIFICATE_FIELDS = {"version", "key_id", "run_id", "lane_id", "lane_public_key", "expires_at", "signature"}


def load_service_key() -> Ed25519PrivateKey:
    """Read the service seed only from process memory; never fall back to a new root."""
    encoded = os.environ.get("FLIGHT_SIGNING_SEED_B64")
    message = "FLIGHT_SIGNING_SEED_B64 must be base64 encoding of a 32-byte Ed25519 seed"
    if not encoded:
        raise ValueError(message)
    try:
        seed = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError(message) from None
    if len(seed) != 32:
        raise ValueError(message)
    return Ed25519PrivateKey.from_private_bytes(seed)


def key_id_for(public_key_hex: str) -> str:
    return "sha256:" + hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()


def _valid_body(certificate) -> bool:
    return (isinstance(certificate, dict) and set(certificate) == _CERTIFICATE_FIELDS and
            certificate["version"] == CERTIFICATE_VERSION and
            all(isinstance(certificate[field], str) and certificate[field]
                for field in ("key_id", "run_id", "lane_id", "signature")) and
            isinstance(certificate["lane_public_key"], str) and
            re.fullmatch(r"[0-9a-f]{64}", certificate["lane_public_key"]) is not None and
            type(certificate["expires_at"]) is int and 0 < certificate["expires_at"] <= 2**53 - 1)


def certify_lane(service_key, run_id, lane_id, lane_public_hex, expires_at) -> dict:
    certificate = {"version": CERTIFICATE_VERSION, "key_id": key_id_for(public_hex(service_key)),
                   "run_id": run_id, "lane_id": lane_id, "lane_public_key": lane_public_hex,
                   "expires_at": expires_at, "signature": "pending"}
    if not _valid_body(certificate):
        raise ValueError("invalid lane certificate scope, public key or expiry")
    body = {key: value for key, value in certificate.items() if key != "signature"}
    certificate["signature"] = base64.b64encode(service_key.sign(canonical(body))).decode("ascii")
    return certificate


def verify_chain(record, certificate, pinned_service_public_hex=None, *, run_id=None, lane_id=None, now=None) -> bool:
    """Authenticate against caller-trusted roots (default: the reviewed pin registry).

    The optional root argument is trusted verifier configuration, never a field
    from the artifact. Expected run/lane labels, when supplied, must also match.
    FlightRecord.verify remains the explicitly weaker integrity-only primitive.
    """
    try:
        if not _valid_body(certificate):
            return False
        pins = PINNED_SERVICE_KEYS if pinned_service_public_hex is None else pinned_service_public_hex
        if isinstance(pins, str):
            pins = {key_id_for(pins): pins}
        root = pins.get(certificate["key_id"])
        if not isinstance(root, str) or not re.fullmatch(r"[0-9a-f]{64}", root):
            return False
        body = {key: value for key, value in certificate.items() if key != "signature"}
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(root)).verify(
            base64.b64decode(certificate["signature"], validate=True), canonical(body))
        current_time = time.time() if now is None else now
        if not 0 <= current_time < certificate["expires_at"]:
            return False
        if run_id is not None and certificate["run_id"] != run_id:
            return False
        if lane_id is not None and certificate["lane_id"] != lane_id:
            return False
        if not FlightRecord.verify(record, certificate["lane_public_key"]):
            return False
        bindings = [entry["payload"] for entry in record if entry["event"] == "lane_identity_bound"]
        if len(bindings) != 1:
            return False
        binding = bindings[0]
        return (binding.get("lane_id") == certificate["lane_id"] and
                binding.get("agent_id") == f'{certificate["run_id"]}:{certificate["lane_id"]}' and
                all(0 <= entry["timestamp"] < certificate["expires_at"] for entry in record))
    except (AttributeError, KeyError, ValueError, TypeError, OverflowError, InvalidSignature):
        return False


def inspect_record(record, public_key, certificate=None, pinned_service_public_hex=None, **scope) -> dict:
    """Keep integrity, authentic origin and scientific validity distinct."""
    integrity = FlightRecord.verify(record, public_key)
    authentic = (integrity and isinstance(certificate, dict) and
                 certificate.get("lane_public_key") == public_key and
                 verify_chain(record, certificate, pinned_service_public_hex, **scope))
    pins = PINNED_SERVICE_KEYS if pinned_service_public_hex is None else pinned_service_public_hex
    if isinstance(pins, str):
        pins = {key_id_for(pins): pins}
    unanchored = certificate is None or not pins or (isinstance(certificate, dict) and
                                                    certificate.get("key_id") not in pins)
    return {"integrity": integrity, "authentic": bool(authentic),
            "origin": "authentic" if authentic else "unanchored" if unanchored else "invalid",
            "scientific_validity": "not checked"}
