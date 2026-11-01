#!/usr/bin/env python3
"""Fixed, text-only collaboration study runner (protocol v2)."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import queue
import re
import socket
import ssl
import sys
import threading
import time
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
        # requests' timeout limits socket inactivity, not total elapsed time.
        # A daemon owns the transport only: a late result cannot mutate receipts.
        result = queue.Queue(maxsize=1)

        def call():
            try:
                result.put((self._complete(messages, max_tokens=max_tokens, timeout=timeout), None))
            except BaseException as error:
                result.put((None, error))

        threading.Thread(target=call, daemon=True).start()
        try:
            reply, error = result.get(timeout=timeout)
        except queue.Empty:
            raise CallFailure("deadline_unknown") from None
        if error is not None:
            raise error
        return reply

    def _complete(self, messages: list[dict], *, max_tokens: int, timeout: float) -> Reply:
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

    def settle(self, attempt: dict, *, usage=None, failure: CallFailure | None = None,
               request_id=None, agent_cap: int | None = None, tokens_before: int = 0) -> None:
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
            overspend = max(0, tokens_before + charged - agent_cap) if agent_cap is not None else 0
            attempt.update({"end_utc": utc_now(), "state": "failed" if failure else "response",
                            "usage": usage, "unknown_usage": unknown, "charged_tokens": charged,
                            "charged_usd": decimal_text(amount), "request_id": request_id or (failure.request_id if failure else None),
                            "failure": failure.kind if failure else None,
                            "http_status": failure.status if failure else None,
                            "overspend_tokens": overspend,
                            "overspend_limit_exceeded": overspend > attempt["max_tokens"],
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
                      "unknown_usage": any(row.get("unknown_usage", False) for row in self._attempts),
                      "stop_reason": self.stop_reason, "scopes": scopes, "attempts": self._attempts}
            return json.loads(canonical(result))


@dataclass
class AgentState:
    number: int
    cap: int
    prompt_bound: int
    charged_tokens: int = 0
    successful_responses: int = 0
    retried: bool = False
    unknown_usage_attempts: int = 0
    stop_reason: str | None = None

    def __post_init__(self):
        if type(self.cap) is not int or self.cap <= 0 or type(self.prompt_bound) is not int or self.prompt_bound < 0:
            raise InputError("agent cap and initial prompt bound must be explicit nonnegative integers")


class RequestEngine:
    """One request lifecycle, shared by all arms; never guesses a prompt count.

    The caller must supply the initial prompt bound. Its protocol source is
    deliberately not defaulted here; subsequent bounds come from provider usage.
    """

    def __init__(self, model, ledger: Ledger, *, max_tokens_per_reply: int,
                 clock=time.monotonic, sleep=time.sleep):
        if type(max_tokens_per_reply) is not int or max_tokens_per_reply <= 0:
            raise InputError("max_tokens_per_reply must be a positive integer")
        self.model = model
        self.ledger = ledger
        self.reply_limit = max_tokens_per_reply
        self.clock = clock
        self.sleep = sleep

    def request(self, job_id: str, agent: AgentState, messages: list[dict], *,
                deadline: float, scope: str, record) -> Reply | None:
        retry = False
        message_hash = sha256(canonical(messages))
        while not agent.stop_reason:
            remaining_time = deadline - self.clock()
            if remaining_time <= 0:
                agent.stop_reason = "wall_time"
                return None
            remaining_tokens = agent.cap - agent.charged_tokens
            max_tokens = min(self.reply_limit, remaining_tokens)
            if max_tokens <= 0 or agent.prompt_bound + max_tokens > remaining_tokens:
                agent.stop_reason = "token_cap"
                return None
            attempt = self.ledger.reserve(job_id, agent.number, "retry" if retry else scope,
                                          prompt_bound=agent.prompt_bound, max_tokens=max_tokens)
            if attempt is None:
                agent.stop_reason = "dollar_cap"
                return None
            record({**attempt, "event": "request", "messages_sha256": message_hash})
            reply, failure = None, None
            try:
                reply = self.model.complete(messages, max_tokens=max_tokens, timeout=remaining_time)
                usage_counts(reply.usage)
            except CallFailure as error:
                failure = error
            usage = reply.usage if reply is not None else failure.usage
            request_id = reply.request_id if reply is not None else failure.request_id
            self.ledger.settle(attempt, usage=usage, failure=failure, request_id=request_id,
                               agent_cap=agent.cap, tokens_before=agent.charged_tokens)
            agent.charged_tokens += attempt["charged_tokens"]
            agent.unknown_usage_attempts += int(attempt["unknown_usage"])
            try:
                agent.prompt_bound = usage_counts(usage)[0]
            except CallFailure:
                pass
            record({**attempt, "event": "failure" if failure else "response",
                    "reply": reply.content if reply is not None else None,
                    "response_id": reply.response_id if reply is not None else None})
            if failure:
                if failure.safe_to_retry and not agent.retried and agent.successful_responses == 0:
                    if self.clock() + 10 >= deadline:
                        agent.stop_reason = "wall_time"
                        return None
                    agent.retried = True
                    self.sleep(10)
                    retry = True
                    continue
                agent.stop_reason = failure.kind
                return None
            agent.successful_responses += 1
            if self.clock() >= deadline:
                agent.stop_reason = "wall_time"
                return None
            if agent.charged_tokens >= agent.cap:
                agent.stop_reason = "token_cap"
            return reply
        return None


def write_json_exclusive(path: Path, value) -> None:
    data = canonical(value) + b"\n"
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class JobOutputs:
    """Append attempt receipts immediately; publish a job's result only once."""

    _creation_lock = threading.Lock()

    def __init__(self, output: Path, job: dict, *, clock=time.monotonic):
        job_id = job.get("job_id")
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", job_id):
            raise InputError("job_id must be a nonempty safe directory name")
        if job.get("arm") not in {"A", "B", "C"} or not isinstance(job.get("packet"), str) or type(job.get("repeat")) is not int:
            raise InputError("invalid job metadata")
        self.job = {name: job[name] for name in ("job_id", "arm", "packet", "repeat")}
        self.clock = clock
        self.start_utc = utc_now()
        self.start_time = clock()
        self.directory = output / job_id
        with self._creation_lock:
            if output.is_symlink() or not (output / ".running").is_file():
                raise InputError("output directory must be claimed first")
            if any(path.name.casefold() == job_id.casefold() for path in output.iterdir()):
                raise InputError("duplicate job directory")
            self.directory.mkdir()
        self._stream = (self.directory / "transcript.jsonl").open("x", encoding="utf-8")
        self._record_lock = threading.Lock()
        self.closed = False

    def record(self, value: dict) -> None:
        if self.closed:
            raise InputError("job output is already closed")
        with self._record_lock:
            self._stream.write(canonical(value).decode("utf-8") + "\n")
            self._stream.flush()

    def abort(self) -> None:
        """Close a partial transcript without pretending the job completed."""
        self._stream.close()
        self.closed = True

    def finish(self, agents: list[AgentState], findings, ledger: Ledger) -> None:
        if self.closed:
            raise InputError("job output is already closed")
        accounting = ledger.report()
        attempts = [row for row in accounting["attempts"] if row["job_id"] == self.job["job_id"]]
        if any(row["state"] == "pending" for row in attempts):
            raise InputError("cannot finish job with unfinished requests")
        per_agent = {}
        for agent in agents:
            rows = [row for row in attempts if row["agent"] == agent.number]
            per_agent[str(agent.number)] = {
                "cap": agent.cap, "charged_tokens": agent.charged_tokens,
                "unknown_usage_attempts": agent.unknown_usage_attempts,
                "overspend_tokens": max(0, agent.charged_tokens - agent.cap),
                "stop_reason": agent.stop_reason,
                "usage": [row["usage"] for row in rows],
            }
        job = {**self.job, "start_utc": self.start_utc, "end_utc": utc_now(),
               "wall_seconds": max(0, self.clock() - self.start_time), "agents": per_agent,
               "provider_request_ids": [row["request_id"] for row in attempts if row["request_id"] is not None],
               "failures": [row for row in attempts if row["state"] == "failed"],
               "unknown_usage": any(row["unknown_usage"] for row in attempts),
               "charged_usd": decimal_text(sum((Decimal(row["charged_usd"]) for row in attempts), Decimal(0))),
               "run_overshoot_usd_at_end": accounting["overshoot_usd"],
               "run_stop_reason": accounting["stop_reason"],
               "overspend_tokens": sum(agent["overspend_tokens"] for agent in per_agent.values()),
               "overspend_limit_exceeded": any(row["overspend_limit_exceeded"] for row in attempts)}
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self.abort()
        write_json_exclusive(self.directory / "findings.json", findings)
        write_json_exclusive(self.directory / "job.json", job)


def run_arm(job: dict, *, output: Path, engine: RequestEngine, system_prompt: str,
            packet_message: str, continue_prompt: str, initial_prompt_bounds: dict[int, int],
            c_turn_prompts: dict[int, str] | None = None, scope: str = "study",
            writer: JobOutputs | None = None) -> None:
    """Run fixed arm rules; the caller supplies sealed prompts and initial bounds.

    B agents run concurrently with independent histories and one arm deadline.
    C turn instructions must be supplied explicitly, never invented here.
    """
    arm = job.get("arm")
    if arm not in {"A", "B", "C"} or scope not in {"pilot", "study"}:
        raise InputError("invalid arm or accounting scope")
    numbers = [1] if arm == "A" else [1, 2, 3]
    if any(number not in initial_prompt_bounds for number in numbers):
        raise InputError("each agent needs an explicit initial prompt bound")
    if arm == "C" and (not isinstance(c_turn_prompts, dict) or
                       any(not isinstance(c_turn_prompts.get(n), str) for n in numbers)):
        raise InputError("C requires sealed turn prompts for all three agents")
    agents = [AgentState(n, 120000 if arm == "A" else 40000, initial_prompt_bounds[n]) for n in numbers]
    writer = writer or JobOutputs(output, job, clock=engine.clock)
    deadline = writer.start_time + 900
    base = [{"role": "system", "content": system_prompt}, {"role": "user", "content": packet_message}]

    def empty_set():
        return {"findings": [], "malformed": [], "discarded": 0}

    def isolated(agent):
        messages = [dict(message) for message in base]
        while not agent.stop_reason:
            reply = engine.request(job["job_id"], agent, messages, deadline=deadline,
                                   scope=scope, record=writer.record)
            if reply is None:
                break
            final = parse_final(reply.content)
            if final is not None:
                agent.stop_reason = "final"
                return final
            messages.extend([{"role": "assistant", "content": reply.content},
                             {"role": "user", "content": continue_prompt}])
        return empty_set()

    try:
        if arm == "A":
            findings = isolated(agents[0])
        elif arm == "B":
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(isolated, agents))
            findings = {str(agent.number): result for agent, result in zip(agents, results)}
        else:
            findings, transcript, finalized = empty_set(), [], False
            while not finalized and any(not agent.stop_reason for agent in agents):
                for agent in agents:
                    if agent.stop_reason:
                        continue
                    messages = base + transcript + [{"role": "user", "content": c_turn_prompts[agent.number]}]
                    reply = engine.request(job["job_id"], agent, messages, deadline=deadline,
                                           scope=scope, record=writer.record)
                    if reply is None:
                        continue
                    transcript.append({"role": "assistant", "content": f"Agent {agent.number}:\n{reply.content}"})
                    final = parse_final(reply.content)
                    if agent.number == 1 and final is not None:
                        findings, finalized = final, True
                        agent.stop_reason = "final"
                        for other in agents:
                            if not other.stop_reason:
                                other.stop_reason = "writer_final"
                        break
        writer.finish(agents, findings, engine.ledger)
    finally:
        if not writer.closed:
            writer.abort()


def finish_run(output: Path, ledger: Ledger) -> dict:
    """Hash all completed outputs. The manifest cannot include its own hash."""
    if output.is_symlink() or not (output / ".running").is_file() or (output / "RUN-MANIFEST.json").exists():
        raise InputError("run is not active or already sealed")
    accounting = ledger.report()
    if any(row["state"] == "pending" for row in accounting["attempts"]):
        raise InputError("cannot seal unfinished requests")
    for directory in output.iterdir():
        if directory.is_symlink():
            raise InputError("output must not contain symlinks")
        if directory.is_dir() and {path.name for path in directory.iterdir()} != {"job.json", "findings.json", "transcript.jsonl"}:
            raise InputError("cannot seal unfinished job")
    write_json_exclusive(output / "ACCOUNTING.json", accounting)
    hashes = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise InputError("output must not contain symlinks")
        if path.is_file() and path.name != ".running":
            hashes[path.relative_to(output).as_posix()] = sha256(path.read_bytes())
    manifest = {"schema": "collab-study-run-manifest-v2", "files": hashes}
    write_json_exclusive(output / "RUN-MANIFEST.json", manifest)
    (output / ".running").unlink()
    return manifest


FIXED_RULES = {
    "model": "deepseek-v4-pro", "caps": {"A": 120000, "B": 40000, "C": 40000},
    "wall_seconds": 900, "turn_order": [1, 2, 3], "writer": 1,
    "findings": {"fields": ["file", "location", "defect", "evidence"], "max_findings": 20, "marker": "FINAL"},
}


def validate_inputs(inputs: Inputs, prompt_paths: dict[str, Path], *, dry_run: bool, pilot: bool) -> None:
    protocol = inputs.protocol
    required = set(FIXED_RULES) | {"deployment", "max_tokens_per_reply", "max_usd", "prices_per_million",
                                   "prompt_files", "initial_prompt_tokens", "pilot_arms"}
    if set(protocol) != required or any(protocol[name] != value for name, value in FIXED_RULES.items()):
        raise InputError("protocol must declare the fixed study rules and all required fields")
    if not isinstance(protocol["deployment"], str) or not protocol["deployment"].strip():
        raise InputError("protocol deployment must be explicit")
    if type(protocol["max_tokens_per_reply"]) is not int or protocol["max_tokens_per_reply"] <= 0:
        raise InputError("max_tokens_per_reply must be a positive integer")
    prices = protocol["prices_per_million"]
    if not isinstance(prices, dict) or set(prices) != {"input", "cached_input", "output"}:
        raise InputError("sealed input, cached input and output prices are required")
    Ledger(protocol["max_usd"], prices)
    if set(prompt_paths) != {"system", "continue", "c1", "c2", "c3"} or protocol["prompt_files"] != {name: path.name for name, path in prompt_paths.items()}:
        raise InputError("all five prompt files must match the sealed protocol names")
    arms = protocol["pilot_arms"]
    if not isinstance(arms, list) or any(not isinstance(arm, str) or arm not in {"A", "B", "C"} for arm in arms) or len(set(arms)) != len(arms) or (pilot and not arms):
        raise InputError("pilot arms must be explicitly selected without duplicates")
    if not inputs.order:
        raise InputError("order must contain study jobs")
    seen, packet_set = set(), set()
    for job in inputs.order:
        if not isinstance(job, dict) or set(job) != {"job_id", "arm", "packet", "repeat"}:
            raise InputError("order jobs must contain job_id, arm, packet and repeat")
        job_id = job["job_id"]
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", job_id):
            raise InputError("order contains an unsafe job id")
        if job_id.casefold() in seen or job_id.casefold().startswith("pilot-"):
            raise InputError("order contains a duplicate or reserved job id")
        seen.add(job_id.casefold())
        if not isinstance(job["arm"], str) or job["arm"] not in {"A", "B", "C"} or not isinstance(job["packet"], str) or job["packet"] not in inputs.packets or type(job["repeat"]) is not int or job["repeat"] < 1:
            raise InputError("order contains an invalid arm, packet or repeat")
        packet_set.add(job["packet"])
    if packet_set != set(inputs.packets) or (not dry_run and len(packet_set) != 10):
        raise InputError("live study requires exactly ten packets; order must cover the packet directory")
    jobs = inputs.order + ([{"job_id": "pilot-" + arm, "arm": arm} for arm in arms] if pilot else [])
    bounds = protocol["initial_prompt_tokens"]
    if not isinstance(bounds, dict):
        raise InputError("initial prompt bounds must be supplied for each job and agent")
    for job in jobs:
        initial = bounds.get(job["job_id"])
        numbers = [1] if job["arm"] == "A" else [1, 2, 3]
        if not isinstance(initial, dict) or any(type(initial.get(str(n))) is not int or initial[str(n)] <= 0 for n in numbers):
            raise InputError("initial prompt bounds must be supplied for each job and agent")


class DryRunModel:
    """Deterministic offline provider; usage is synthetic and labelled in the freeze."""

    def complete(self, messages, *, max_tokens, timeout):
        history = [message for message in messages if message["role"] == "assistant"]
        shared = any(message["content"].startswith("Agent ") for message in history)
        if len(history) >= (3 if shared else 1):
            finding = {"file": "README.md", "location": "1", "defect": "synthetic dry-run finding",
                       "evidence": "Offline fixture; not a participant result."}
            content = "FINAL\n" + canonical(finding).decode("utf-8")
        else:
            content = "Synthetic review in progress."
        identity = sha256(canonical(messages))
        usage = {"prompt_tokens": 100, "completion_tokens": min(20, max_tokens),
                 "prompt_tokens_details": {"cached_tokens": 0},
                 "completion_tokens_details": {"reasoning_tokens": 0}}
        return Reply(content, usage, "dry-request-" + identity, "dry-response-" + identity)


def run_jobs(inputs: Inputs, *, output: Path, engine: RequestEngine, parallel: int,
             pilot_message: str | None = None) -> None:
    """Start jobs in sealed order, with at most six arm workers in flight."""
    if type(parallel) is not int or not 1 <= parallel <= 6:
        raise InputError("parallel must be between one and six")
    prompts = inputs.prompts

    def arguments(job, packet_message, scope):
        return {"output": output, "engine": engine, "system_prompt": prompts["system"],
                "packet_message": packet_message, "continue_prompt": prompts["continue"],
                "initial_prompt_bounds": {n: inputs.protocol["initial_prompt_tokens"][job["job_id"]][str(n)]
                                          for n in ([1] if job["arm"] == "A" else [1, 2, 3])},
                "c_turn_prompts": {n: prompts[f"c{n}"] for n in (1, 2, 3)}, "scope": scope}

    if pilot_message is not None:
        for arm in inputs.protocol["pilot_arms"]:
            job = {"job_id": "pilot-" + arm, "arm": arm, "packet": "pilot", "repeat": 1}
            run_arm(job, **arguments(job, pilot_message, "pilot"))
    active = set()
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for job in inputs.order:
            if len(active) == parallel:
                completed, active = wait(active, return_when=FIRST_COMPLETED)
                for future in completed:
                    future.result()
            # The coordinator creates the receipt synchronously, so the recorded
            # job starts follow order.json even when worker scheduling differs.
            writer = JobOutputs(output, job, clock=engine.clock)
            active.add(pool.submit(run_arm, job, writer=writer,
                                   **arguments(job, inputs.packets[job["packet"]], "study")))
        for future in active:
            future.result()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--prompt", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pilot-packet", type=Path)
    parser.add_argument("--parallel", type=int, default=6)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--print-freeze", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.parallel <= 6:
            raise InputError("parallel must be between one and six")
        prompts = {}
        for argument in args.prompt:
            name, separator, path = argument.partition("=")
            if not separator or not path or name in prompts:
                raise InputError("prompts must be distinct NAME=PATH arguments")
            prompts[name] = Path(path)
        inputs = snapshot_inputs(args.protocol, prompts, args.order, args.packets)
        validate_inputs(inputs, prompts, dry_run=args.dry_run, pilot=args.pilot_packet is not None)
        pilot_message, pilot_freeze = None, None
        if args.pilot_packet is not None:
            sealed = [inputs.packet_hashes[job["packet"]] for job in inputs.order]
            pilot_message, hashes = validate_pilot(args.pilot_packet, sealed)
            pilot_freeze = {"packet_sha256": sha256(canonical(hashes)), "files": hashes,
                            "arms": inputs.protocol["pilot_arms"]}
        endpoint = os.environ.get("STUDY_ENDPOINT", "")
        if not args.dry_run and not endpoint:
            raise InputError("STUDY_ENDPOINT must be set for a live freeze")
        descriptor = {**inputs.freeze,
                      "request_settings": {"model": "deepseek-v4-pro", "deployment": inputs.protocol["deployment"],
                                           "temperature": 0.3, "top_p": 1, "max_tokens_per_reply": inputs.protocol["max_tokens_per_reply"],
                                           "stream": False, "allow_redirects": False, "timeout": "remaining arm wall time"},
                      "endpoint_sha256": None if args.dry_run else sha256(endpoint.encode("utf-8")),
                      "caps": {"tokens_per_agent": inputs.protocol["caps"], "wall_seconds": 900,
                               "max_usd": inputs.protocol["max_usd"], "parallel_arms": args.parallel},
                      "turn_rule": {"order": [1, 2, 3], "writer": 1, "skip_stopped_agents": True},
                      "retry_rule": {"limit": 1, "delay_seconds": 10, "before_first_success_only": True,
                                     "evidenced_presend_only": True},
                      "dry_run": args.dry_run, "pilot": pilot_freeze}
        credential = os.environ.get("STUDY_API_KEY", "")
        if credential and contains_credential([descriptor, inputs.prompts, inputs.packets, pilot_message], credential):
            raise InputError("credential found in study inputs")
        if args.freeze:
            verify_freeze(args.freeze, descriptor)
        if args.print_freeze:
            print(canonical(descriptor).decode("utf-8"))
            return 0
        if args.freeze is None:
            raise InputError("a matching --freeze file is required to run")
        if args.output is None:
            raise InputError("--output is required to run")
        model = DryRunModel() if args.dry_run else HTTPModel.from_env()
        claim_output(args.output)
        write_json_exclusive(args.output / "FREEZE.json", descriptor)
        ledger = Ledger(inputs.protocol["max_usd"], inputs.protocol["prices_per_million"])
        engine = RequestEngine(model, ledger, max_tokens_per_reply=inputs.protocol["max_tokens_per_reply"])
        run_jobs(inputs, output=args.output, engine=engine, parallel=args.parallel, pilot_message=pilot_message)
        finish_run(args.output, ledger)
        return 0
    except InputError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        print("study input or output could not be accessed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
