#!/usr/bin/env python3
"""Fixed, text-only collaboration study runner (protocol v2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import socket
import ssl
import threading
from urllib.parse import urlsplit

import requests
from pathlib import Path

PACKET_FILES = ("README.md", "config.json", "model.py", "results.json", "report.md")
FINDING_FIELDS = {"file", "location", "defect", "evidence"}


class InputError(ValueError):
    """Invalid study inputs; safe to report without file contents."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_packet(directory: Path) -> tuple[str, dict[str, str]]:
    if directory.is_symlink() or not directory.is_dir():
        raise InputError("packet must be a regular directory")
    if {path.name for path in directory.iterdir()} != set(PACKET_FILES):
        raise InputError("packet must contain exactly the five protocol files")
    sections, hashes = [], {}
    for name in PACKET_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise InputError("packet files must be regular files")
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise InputError("packet files must be UTF-8 text") from None
        hashes[name] = sha256(data)
        sections.append(f"### {name}\n{text}")
    return "\n\n".join(sections), hashes


def parse_final(text: str) -> dict | None:
    if not text.startswith("FINAL"):
        return None
    result = {"findings": [], "malformed": [], "discarded": 0}
    body = text[len("FINAL"):]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    for number, line in enumerate(body.splitlines(), start=1):
        try:
            finding = json.loads(line)
        except (ValueError, RecursionError):
            finding = None
        if not isinstance(finding, dict) or set(finding) != FINDING_FIELDS or not all(isinstance(v, str) for v in finding.values()):
            result["malformed"].append({"line": number, "text": line})
        elif len(result["findings"]) < 20:
            result["findings"].append(finding)
        else:
            result["discarded"] += 1
    return result


def claim_output(directory: Path) -> None:
    """Claim even an existing empty directory exclusively; never reuse a run."""
    if directory.is_symlink():
        raise InputError("output directory must be empty and not a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise InputError("output directory must start empty")
    try:
        with (directory / ".running").open("x", encoding="utf-8") as stream:
            stream.write("study-runner\n")
    except FileExistsError:
        raise InputError("output directory must start empty") from None


@dataclass(frozen=True)
class Inputs:
    protocol: dict
    prompts: dict[str, str]
    order: list[dict]
    packets: dict[str, str]
    packet_hashes: dict[str, dict[str, str]]
    freeze: dict


def read_json_bytes(data: bytes):
    try:
        return json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise InputError("invalid JSON input") from None


def snapshot_inputs(protocol_path: Path, prompt_paths: dict[str, Path], order_path: Path, packets_root: Path) -> Inputs:
    """Read input bytes once so every job uses the same review packet."""
    protocol_bytes = protocol_path.read_bytes()
    order_bytes = order_path.read_bytes()
    prompt_bytes = {name: path.read_bytes() for name, path in prompt_paths.items()}
    try:
        prompts = {name: data.decode("utf-8") for name, data in prompt_bytes.items()}
    except UnicodeError:
        raise InputError("prompts must be UTF-8 text") from None
    protocol, order = read_json_bytes(protocol_bytes), read_json_bytes(order_bytes)
    if not isinstance(protocol, dict) or not isinstance(order, list):
        raise InputError("protocol must be an object and order must be a list")
    if packets_root.is_symlink() or not packets_root.is_dir():
        raise InputError("packets root must be a regular directory")
    packets, packet_hashes, tree = {}, {}, {}
    for directory in sorted(packets_root.iterdir()):
        message, hashes = read_packet(directory)
        packets[directory.name], packet_hashes[directory.name] = message, hashes
        tree.update({f"{directory.name}/{name}": digest for name, digest in hashes.items()})
    freeze = {
        "schema": "collab-study-freeze-v2",
        "runner_sha256": sha256(Path(__file__).read_bytes()),
        "protocol": protocol,
        "protocol_sha256": sha256(protocol_bytes),
        "prompts": {name: {"file": path.name, "sha256": sha256(prompt_bytes[name])} for name, path in prompt_paths.items()},
        "order_sha256": sha256(order_bytes),
        "packet_files": dict(sorted(tree.items())),
        "packets_tree_sha256": sha256(canonical(tree)),
    }
    return Inputs(protocol, prompts, order, packets, packet_hashes, freeze)


def verify_freeze(path: Path, actual: dict) -> None:
    if read_json_bytes(path.read_bytes()) != actual:
        raise InputError("freeze does not match current runner and inputs")


def validate_pilot(path: Path, sealed_hashes: list[dict[str, str]]) -> tuple[str, dict[str, str]]:
    message, hashes = read_packet(path)
    digest = sha256(canonical(hashes))
    if any(sha256(canonical(sealed)) == digest for sealed in sealed_hashes):
        raise InputError("pilot must differ from every sealed packet")
    return message, hashes


class CallFailure(Exception):
    """Only bounded, credential-free categories cross the transport boundary."""

    def __init__(self, kind: str, *, safe_to_retry=False, status=None, request_id=None, usage=None):
        super().__init__(kind)
        self.kind = kind
        self.safe_to_retry = safe_to_retry
        self.status = status
        self.request_id = request_id
        self.usage = usage


@dataclass(frozen=True)
class Reply:
    content: str
    usage: dict | None
    request_id: str | None
    response_id: str | None


def usage_counts(usage: dict | None) -> tuple[int, int, int, int]:
    """Cached/reasoning details are subsets, not additional billed tokens."""
    try:
        prompt = usage["prompt_tokens"]
        output = usage["completion_tokens"]
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        values = (prompt, cached, output, reasoning)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError
        if cached > prompt or reasoning > output:
            raise ValueError
        if "total_tokens" in usage and usage["total_tokens"] != prompt + output:
            raise ValueError
        return values
    except (KeyError, TypeError, AttributeError, ValueError):
        raise CallFailure("invalid_usage", usage=usage) from None


def evidenced_presend(error: BaseException) -> bool:
    """Do not infer send state from a generic timeout/reset/SSL error."""
    pending, visited = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, (socket.gaierror, ConnectionRefusedError, ssl.SSLCertVerificationError)):
            return True
        for nested in [current.__cause__, getattr(current, "reason", None), *current.args]:
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def contains_credential(value, credential: str) -> bool:
    if isinstance(value, str):
        return credential in value
    if isinstance(value, dict):
        return any(contains_credential(k, credential) or contains_credential(v, credential) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_credential(item, credential) for item in value)
    return False


class HTTPModel:
    def __init__(self, endpoint: str, credential: str):
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise InputError("STUDY_ENDPOINT must be a complete HTTPS chat-completions URL")
        if not credential:
            raise InputError("STUDY_API_KEY must be set")
        self.endpoint = endpoint
        self._credential = credential

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("STUDY_ENDPOINT", ""), os.environ.get("STUDY_API_KEY", ""))

    def complete(self, messages: list[dict], *, max_tokens: int, timeout: float) -> Reply:
        payload = {"model": "deepseek-v4-pro", "messages": messages, "temperature": 0.3,
                   "top_p": 1, "max_tokens": max_tokens, "stream": False}
        if contains_credential(payload, self._credential):
            raise CallFailure("credential_in_input")
        try:
            with requests.Session() as session:
                response = session.post(self.endpoint, json=payload, headers={"Authorization": "Bearer " + self._credential},
                                        timeout=timeout, allow_redirects=False)
        except requests.RequestException as error:
            safe = evidenced_presend(error)
            raise CallFailure("presend_failure" if safe else "transport_unknown", safe_to_retry=safe) from None
        request_id = response.headers.get("x-request-id") or response.headers.get("apim-request-id")
        if contains_credential(request_id, self._credential):
            request_id = None
        try:
            body = response.json()
        except (ValueError, RecursionError):
            raise CallFailure("invalid_response", status=response.status_code, request_id=request_id) from None
        if contains_credential(body, self._credential):
            raise CallFailure("credential_in_response", status=response.status_code, request_id=request_id)
        usage = body.get("usage") if isinstance(body, dict) else None
        if not 200 <= response.status_code < 300:
            raise CallFailure("http_error", status=response.status_code, request_id=request_id, usage=usage)
        try:
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            response_id = body.get("id")
        except (KeyError, IndexError, TypeError, AttributeError):
            raise CallFailure("invalid_response", status=response.status_code, request_id=request_id, usage=usage) from None
        return Reply(content, usage, request_id, response_id)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def money(value) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError):
        raise InputError("prices and dollar cap must be finite nonnegative decimals") from None


def decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


class Ledger:
    """Reserve concurrent calls atomically; retain actual and unknown charges."""

    def __init__(self, max_usd, prices: dict):
        self.max_usd = money(max_usd)
        self.prices = {name: money(prices[name]) for name in ("input", "cached_input", "output")}
        self._lock = threading.Lock()
        self._spent = Decimal(0)
        self._reserved = Decimal(0)
        self._attempts = []
        self.stop_reason = None

    def cost(self, prompt: int, cached: int, output: int) -> Decimal:
        return ((prompt - cached) * self.prices["input"] + cached * self.prices["cached_input"] + output * self.prices["output"]) / 1_000_000

    def reserve(self, job_id: str, agent: int, scope: str, *, prompt_bound: int, max_tokens: int) -> dict | None:
        if scope not in {"pilot", "study", "retry"}:
            raise InputError("invalid accounting scope")
        if type(prompt_bound) is not int or prompt_bound < 0 or type(max_tokens) is not int or max_tokens <= 0:
            raise InputError("invalid reservation token bounds")
        bound = (prompt_bound * max(self.prices["input"], self.prices["cached_input"]) + max_tokens * self.prices["output"]) / 1_000_000
        with self._lock:
            if self.stop_reason or self._spent + self._reserved + bound > self.max_usd:
                self.stop_reason = "dollar_cap"
                return None
            attempt = {"job_id": job_id, "agent": agent, "scope": scope, "attempt": len(self._attempts) + 1,
                       "start_utc": utc_now(), "prompt_bound": prompt_bound, "max_tokens": max_tokens,
                       "reserved_usd": decimal_text(bound), "state": "pending"}
            self._reserved += bound
            self._attempts.append(attempt)
            return attempt

    def settle(self, attempt: dict, *, usage=None, failure: CallFailure | None = None, request_id=None) -> None:
        unknown = False
        if failure and failure.safe_to_retry and usage is None:
            charged, amount = 0, Decimal(0)
        else:
            try:
                prompt, cached, output, _ = usage_counts(usage)
                charged, amount = prompt + output, self.cost(prompt, cached, output)
            except CallFailure:
                unknown = True
                charged = attempt["prompt_bound"] + attempt["max_tokens"]
                amount = Decimal(attempt["reserved_usd"])
        # An ambiguous failed request can include partial usage. Keep it as
        # evidence, but never let it reduce the conservative reservation.
        if failure and not failure.safe_to_retry:
            unknown = True
            charged = max(charged, attempt["prompt_bound"] + attempt["max_tokens"])
            amount = max(amount, Decimal(attempt["reserved_usd"]))
        with self._lock:
            if attempt["state"] != "pending":
                raise RuntimeError("attempt already settled")
            self._reserved -= Decimal(attempt["reserved_usd"])
            self._spent += amount
            attempt.update({"end_utc": utc_now(), "state": "failed" if failure else "response",
                            "usage": usage, "unknown_usage": unknown, "charged_tokens": charged,
                            "charged_usd": decimal_text(amount), "request_id": request_id or (failure.request_id if failure else None),
                            "failure": failure.kind if failure else None,
                            "http_status": failure.status if failure else None,
                            "over_reserved_tokens": max(0, charged - attempt["prompt_bound"] - attempt["max_tokens"])})
            if self._spent > self.max_usd:
                self.stop_reason = "dollar_cap"

    def report(self) -> dict:
        with self._lock:
            scopes = {}
            for scope in ("pilot", "study", "retry"):
                attempts = [item for item in self._attempts if item["scope"] == scope and item["state"] != "pending"]
                scopes[scope] = {"usd": decimal_text(sum((Decimal(item["charged_usd"]) for item in attempts), Decimal(0))),
                                 "charged_tokens": sum(item["charged_tokens"] for item in attempts),
                                 "attempts": len(attempts), "unknown_usage_attempts": sum(item["unknown_usage"] for item in attempts)}
            result = {"max_usd": decimal_text(self.max_usd), "grand_total_usd": decimal_text(self._spent),
                      "reserved_usd": decimal_text(self._reserved), "overshoot_usd": decimal_text(max(Decimal(0), self._spent - self.max_usd)),
                      "stop_reason": self.stop_reason, "scopes": scopes, "attempts": self._attempts}
            return json.loads(canonical(result))
