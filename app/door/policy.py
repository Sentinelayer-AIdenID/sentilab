"""What the door serves and on what terms (AGENT-DOOR.md section 4, Amendments 1 and 2).

The door opens only when every one of these holds, checked before enqueue and again before dispatch:
- the manifest passes the contract's record rules, is `signed`, and its pins match the pinned legality adapter;
- the operator-signed binding verifies with the pinned operator key and names this exact manifest id;
- admission is open: the operator switch DOOR_ADMISSION is "open", the contract's admission rule passes (a signed
  manifest with live CPU enforcement evidence), and now lies inside both the manifest window and the grant window;
- the grant names the manifest's grant ref and carries the scorer's whole-container enforcement evidence.

A signed manifest whose admission is closed refuses at both points. Nothing here defaults the door open: a missing or
malformed input closes it, and the reason is a fixed phrase, never input.

The principal is a scoped purpose token, never an account or a person: anon-token/1:<sha256(nonce)>. Its
participant_ref is the contract's HMAC rule keyed by DOOR_K_CHALLENGE, so it does not link across challenges.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from open_proposals.contract import canonical as hashes
from open_proposals.contract.codes import violation
from open_proposals.contract.validator import _admission as contract_admission
from open_proposals.contract.validator import validate_record

PURPOSE = "place-chiplets"
PURPOSES = ("place-chiplets", "review", "read")
CASE = "cpu-dram"
PROBLEM_FOR_CASE = {"cpu-dram": "micro150"}
PRINCIPAL_PREFIX = "anon-token/1:"
PRINCIPAL = re.compile(r"anon-token/1:[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{16}\Z")
# The edge classifier's enums (AIdenID 09b2ff46 packages/aidenid-classifier/src/types.ts), plus "ours" for our own
# labelled background agents. The classifier's free-text label is never accepted.
CLASSES = ("verified_agent", "signed_agent", "declared_agent", "crawler_claimed", "automation", "likely_human",
           "unknown", "ours")
OPERATORS = ("openai", "google", "meta", "anthropic", "perplexity", "microsoft", "apple", "amazon", "bytedance",
             "commoncrawl", "deepseek", "unknown")
# warden's operator key is the one pinned for SLAB-049, read from that record (never a second copy here).
OPERATOR_PIN = Path(__file__).resolve().parents[2] / "docs/sentilab/diagnostics/SLAB-049/CALL-LIST-v4.json"
BINDING_SCHEMA = "sentilab-door-binding/1"
TOKEN_TTL_S = 3600          # the purpose token's lifetime (AGENT-DOOR section 1)
TOKEN_SKEW_S = 120          # clock skew allowed between the Worker and this service
COMPACT_STEP_UM = 500       # the compact l= format counts 500 um lattice steps (AGENT-DOOR section 3)
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
GRANT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_TAG = re.compile(r"[a-z0-9][a-z0-9._/-]{0,127}:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


def parse_utc(text) -> float:
    if not isinstance(text, str) or not UTC.match(text):
        raise ValueError("not a UTC time")
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def utc(ts: float) -> str:
    """Whole seconds, rounded up, so a retry_after is never earlier than the moment it names."""
    return datetime.fromtimestamp(math.ceil(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def principal_for(nonce: str) -> str:
    if not isinstance(nonce, str) or not NONCE.match(nonce):
        raise ValueError("a nonce is 16 lower-case hex characters")
    return PRINCIPAL_PREFIX + hashlib.sha256(nonce.encode("ascii")).hexdigest()


def short_id(principal: str) -> str:
    """The first 4 hex characters of sha256(nonce): the only token-derived text a public view shows."""
    return principal[len(PRINCIPAL_PREFIX):][:4]


def _number(value, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("not a finite number")
    if not low < value <= high:
        raise ValueError("out of range")
    return float(value)


@dataclass(frozen=True)
class Grant:
    """The runtime grant binding (warden): the CPU the door may spend, per token and in total, and when, and the
    scorer image whose answers count (every receipt and every health answer must name it). scorer_image_tag is
    optional: the operator's name for that image digest. A result's evaluator identity needs it to name the
    reproduction-tested build (evaluator.py); without it every result reads unvalidated."""
    grant: str
    cpu_cap_s: float
    token_cpu_s: float
    parallel: int
    run_reserve_cpu_s: float
    not_before: float
    not_after: float
    enforcement_evidence_sha256: str
    scorer_image_digest: str
    scorer_image_tag: str | None = None

    FIELDS = ("grant", "cpu_cap_s", "token_cpu_s", "parallel", "run_reserve_cpu_s", "not_before", "not_after",
              "enforcement_evidence_sha256", "scorer_image_digest")
    OPTIONAL = ("scorer_image_tag",)

    @classmethod
    def parse(cls, value) -> "Grant":
        if not isinstance(value, dict) or not set(cls.FIELDS) <= set(value) <= set(cls.FIELDS + cls.OPTIONAL):
            raise ValueError("the grant binding has exactly its fields")
        if not isinstance(value["grant"], str) or not GRANT_ID.match(value["grant"]):
            raise ValueError("grant id")
        cap = _number(value["cpu_cap_s"], 0, 1_000_000)
        token = _number(value["token_cpu_s"], 0, cap)
        reserve = _number(value["run_reserve_cpu_s"], 0, token)
        parallel = value["parallel"]
        if isinstance(parallel, bool) or not isinstance(parallel, int) or not 1 <= parallel <= 8:
            raise ValueError("parallel")
        not_before, not_after = parse_utc(value["not_before"]), parse_utc(value["not_after"])
        if not not_before < not_after:
            raise ValueError("grant window")
        evidence = value["enforcement_evidence_sha256"]
        if not isinstance(evidence, str) or not HEX64.match(evidence):
            raise ValueError("enforcement evidence")
        image = value["scorer_image_digest"]
        if not isinstance(image, str) or not IMAGE.match(image):
            raise ValueError("scorer image")
        tag = value.get("scorer_image_tag")
        if "scorer_image_tag" in value and (not isinstance(tag, str) or not IMAGE_TAG.match(tag)):
            raise ValueError("scorer image tag")
        return cls(value["grant"], cap, token, parallel, reserve, not_before, not_after, evidence, image, tag)


@dataclass(frozen=True)
class FloodLimits:
    """The HTTP layer's own request limits (not the manifest's evaluation quotas)."""
    nonce_per_min: int = 6
    total_per_min: int = 240
    arrivals_per_min: int = 600
    queue_retry_s: int = 30


def pinned_operator_key(path: Path = OPERATOR_PIN) -> str:
    """The operator public key SLAB-049 pins (the key that signs gate zero's grant and receipts), or ValueError."""
    try:
        operator = json.loads(path.read_bytes())["operator"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("no pinned operator key") from None
    key = operator.get("public_key_ed25519") if isinstance(operator, dict) else None
    if operator.get("status") != "pinned" or not isinstance(key, str) or not HEX64.match(key):
        raise ValueError("no pinned operator key")
    return key


def verify_binding(signed, public_key_hex: str) -> dict:
    """The operator-signed binding's body, or ValueError. Ed25519 over the gate-zero canonical bytes
    (sundai_hotspot.gate0_anchor.sign/verify), so warden signs it with the tooling and key he already holds."""
    from sundai_hotspot import gate0_anchor

    try:
        body = gate0_anchor.verify(public_key_hex, signed)
    except gate0_anchor.AuthenticationError as exc:
        raise ValueError("binding signature") from exc
    if set(body) != {"schema", "manifest_id", "grant"} or body["schema"] != BINDING_SCHEMA:
        raise ValueError("binding shape")
    if not isinstance(body["manifest_id"], str) or not HEX64.match(body["manifest_id"]):
        raise ValueError("binding manifest id")
    return body


class Policy:
    """Built once from fixed inputs; every check reads the clock it is given."""

    def __init__(self, *, manifest, binding, admission_switch: str, k_challenge: bytes,
                 flood: FloodLimits = FloodLimits(), operator_public_key: str | None = None,
                 clock=time.time, checker_factory=None):
        self.clock = clock
        self.flood = flood
        self.admission_switch = admission_switch
        self.problems: list[str] = []
        self.manifest = manifest if isinstance(manifest, dict) else None
        self.manifest_id = None
        self.grant: Grant | None = None
        self.checker = None
        self.k_challenge = k_challenge if isinstance(k_challenge, (bytes, bytearray)) else b""
        if len(self.k_challenge) < 32:
            self.problems.append("k_challenge missing or shorter than 32 bytes")
        if self.manifest is None:
            self.problems.append("no manifest")
            return
        if validate_record("manifest", self.manifest):
            self.problems.append("manifest fails the contract's record rules")
            self.manifest = None
            return
        self.manifest_id = hashes.manifest_id(self.manifest)
        if self.manifest["problem"] != PROBLEM_FOR_CASE[CASE]:
            self.problems.append("manifest problem is not the door's case")
        if self.manifest["legality"]["lattice_um"] != COMPACT_STEP_UM:
            self.problems.append("manifest lattice is not the compact format's step")
        if self.manifest["legality"]["units"] != "um" or self.manifest["legality"]["anchor"] != "die-centre":
            self.problems.append("manifest units or anchor")
        try:
            body = verify_binding(binding, operator_public_key or pinned_operator_key())
            if body["manifest_id"] != self.manifest_id:
                raise ValueError("binding names another manifest")
            self.grant = Grant.parse(body["grant"])
            if self.grant.grant != self.manifest["refs"]["grant"]:
                raise ValueError("grant is not the manifest's grant")
        except ValueError:
            self.problems.append("signed binding missing, unverified or not for this manifest")
            self.grant = None
        try:
            if checker_factory is None:
                from app.door.legality import PinnedTapChecker as checker_factory
            self.checker = checker_factory(self.manifest)
        except ValueError:
            self.problems.append("manifest does not match the pinned legality adapter")

    @classmethod
    def from_env(cls, env=None, *, clock=time.time) -> "Policy":
        env = os.environ if env is None else env

        def load(name):
            path = env.get(name, "")
            if not path:
                return None
            try:
                return json.loads(Path(path).read_bytes())
            except (OSError, ValueError):
                return None

        key_hex = env.get("DOOR_K_CHALLENGE", "")
        try:
            key = bytes.fromhex(key_hex)
        except ValueError:
            key = b""

        def count(name, default):
            try:
                value = int(env.get(name, default))
            except ValueError:
                return default
            return value if 1 <= value <= 100_000 else default

        flood = FloodLimits(nonce_per_min=count("DOOR_RATE_NONCE_PER_MIN", 6),
                            total_per_min=count("DOOR_RATE_TOTAL_PER_MIN", 240),
                            arrivals_per_min=count("DOOR_RATE_ARRIVALS_PER_MIN", 600),
                            queue_retry_s=count("DOOR_QUEUE_RETRY_S", 30))
        policy = cls(manifest=load("DOOR_MANIFEST_PATH"), binding=load("DOOR_BINDING_PATH"),
                     admission_switch=env.get("DOOR_ADMISSION", ""), k_challenge=key, flood=flood, clock=clock)
        if not env.get("ORIGIN_SHARED_TOKEN"):
            policy.problems.append("origin token not configured: the door is reachable only through the Worker")
        return policy

    @property
    def usable(self) -> bool:
        return not self.problems and self.manifest is not None and self.grant is not None

    def admission(self, now: float) -> tuple[list, bool]:
        """(violations, final). No violations means open. final means it can never reopen for this manifest and
        grant (a window has ended), so queued work expires; otherwise queued work waits."""
        if not self.usable:
            return [violation("not_open_yet")], False
        switch = self.admission_switch if self.admission_switch in ("open", "closed") else "not_open_yet"
        found = contract_admission(self.manifest, self.manifest_id, {self.manifest_id: switch})
        if found:
            return found, False
        try:
            opens = max(parse_utc(self.manifest["window"]["opens_at"]), self.grant.not_before)
            closes = min(parse_utc(self.manifest["window"]["closes_at"]), self.grant.not_after)
        except ValueError:
            return [violation("not_open_yet")], False
        if now >= closes:
            return [violation("manifest_closed")], True
        if now < opens:
            return [violation("not_open_yet")], False
        return [], False

    def participant_ref(self, principal: str) -> str:
        return hashes.participant_ref(bytes(self.k_challenge), principal)

    def keyed(self, label: str, *parts: str) -> str:
        """HMAC-SHA256 under the door's secret over a domain label and NUL-separated parts, as hex."""
        message = "\x00".join((label,) + parts).encode("utf-8")
        return hmac.new(bytes(self.k_challenge), message, hashlib.sha256).hexdigest()
