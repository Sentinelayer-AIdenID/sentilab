"""Bounded reference controller. Models propose; local code and an injected oracle decide.

Local signing identities are a demonstration, NOT an AIdenID service integration.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import numbers
import re
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Awaitable, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def normalized_source_sha256(source: bytes) -> str:
    """Hash source independent of the platform's newline convention."""
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    normalized = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def redact(value):
    """Defense in depth. Callers must pass hashes, never credentials or raw prompts."""
    if isinstance(value, dict):
        return {k: (redact(v) if (k in {"input_tokens", "output_tokens"} and
                                  (v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= 0))) else
                    "[REDACTED]" if re.search(r"password|secret|token|authorization|api.?key|raw.?prompt", k, re.I)
                    else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"(?i)bearer\s+\S+|\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    return value


class FlightRecord:
    def __init__(self, key=None):
        self.key = key or Ed25519PrivateKey.generate()
        self.public_key = public_hex(self.key)
        self.events = []
        self.closed = False

    def append(self, event: str, **payload):
        if self.closed:
            raise RuntimeError("flight record is closed")
        body = {"sequence": len(self.events), "previous_hash": self.events[-1]["hash"] if self.events else "0" * 64,
                "timestamp": time.time(), "event": event, "payload": redact(payload)}
        h = digest(body)
        entry = {**body, "hash": h, "signature": base64.b64encode(self.key.sign(bytes.fromhex(h))).decode()}
        self.events.append(entry)
        return h

    def close(self):
        if self.closed:
            return self.events[-1]["hash"]
        if not self.events:
            raise RuntimeError("cannot close an empty flight record")
        final_hash = self.events[-1]["hash"]
        entry_hash = self.append("run_closed", event_count=len(self.events) + 1, final_hash=final_hash)
        self.closed = True
        return entry_hash

    @staticmethod
    def verify(events, pinned_public_key: str) -> bool:
        try:
            if not isinstance(events, list) or len(events) < 2 or not isinstance(events[-1], dict):
                return False
            if events[-1].get("event") != "run_closed":
                return False
            pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pinned_public_key))
            prev = "0" * 64
            entry_keys = {"sequence", "previous_hash", "timestamp", "event", "payload", "hash", "signature"}
            for sequence, entry in enumerate(events):
                if not isinstance(entry, dict) or set(entry) != entry_keys:
                    return False
                body = {k: entry[k] for k in ("sequence", "previous_hash", "timestamp", "event", "payload")}
                if (not isinstance(body["sequence"], int) or isinstance(body["sequence"], bool) or
                        body["sequence"] != sequence or body["previous_hash"] != prev or
                        not isinstance(body["timestamp"], (int, float)) or isinstance(body["timestamp"], bool) or
                        not math.isfinite(body["timestamp"]) or not isinstance(body["event"], str) or
                        not body["event"] or not isinstance(body["payload"], dict) or
                        not isinstance(entry["hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["hash"]) or
                        digest(body) != entry["hash"]):
                    return False
                pk.verify(base64.b64decode(entry["signature"], validate=True), bytes.fromhex(entry["hash"]))
                prev = entry["hash"]
            closing = events[-1]
            event_count = closing["payload"].get("event_count")
            if (not isinstance(event_count, int) or isinstance(event_count, bool) or event_count != len(events) or
                    closing["payload"].get("final_hash") != closing["previous_hash"]):
                return False
            return True
        except (KeyError, ValueError, TypeError, OverflowError, InvalidSignature):
            return False


@dataclass(frozen=True)
class Chiplet:
    id: str
    width_mm: float
    height_mm: float


class DesignValidationError(ValueError):
    """A design proposal has malformed coordinates or a catalog mismatch."""


def _finite_coordinate(value, operation):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise DesignValidationError(f"{operation} coordinates must be real numbers")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise DesignValidationError(f"{operation} coordinates must be finite real numbers") from exc
    if not math.isfinite(normalized):
        raise DesignValidationError(f"{operation} coordinates must be finite real numbers")
    return normalized


@dataclass(frozen=True)
class Design:
    width_mm: float
    height_mm: float
    gap_mm: float
    chiplets: tuple[Chiplet, ...]
    # Lower-left coordinates in the same order as the fixed chiplet catalog.
    positions: tuple[tuple[float, float], ...]

    @property
    def hash(self):
        def normalize_numbers(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                normalized = float(value)
                return 0.0 if normalized == 0.0 else normalized
            if isinstance(value, (list, tuple)):
                return [normalize_numbers(item) for item in value]
            if isinstance(value, dict):
                return {key: normalize_numbers(item) for key, item in value.items()}
            return value
        return digest(normalize_numbers(asdict(self)))

    def check(self):
        if len(self.positions) != len(self.chiplets) or len({c.id for c in self.chiplets}) != len(self.chiplets):
            raise ValueError("invalid catalog")
        if not all(math.isfinite(v) and v > 0 for v in (self.width_mm, self.height_mm)) or not math.isfinite(self.gap_mm) or self.gap_mm < 0:
            raise ValueError("invalid substrate")
        for c, (x, y) in zip(self.chiplets, self.positions):
            if not all(math.isfinite(v) for v in (x, y, c.width_mm, c.height_mm)) or min(c.width_mm, c.height_mm) <= 0:
                raise ValueError("nonfinite or invalid dimensions")
            if x < 0 or y < 0 or x + c.width_mm > self.width_mm or y + c.height_mm > self.height_mm:
                raise ValueError("outside substrate")
        for i, (a, (ax, ay)) in enumerate(zip(self.chiplets, self.positions)):
            for b, (bx, by) in list(zip(self.chiplets, self.positions))[i + 1:]:
                g = self.gap_mm
                if not (ax + a.width_mm + g <= bx or bx + b.width_mm + g <= ax or
                        ay + a.height_mm + g <= by or by + b.height_mm + g <= ay):
                    raise ValueError("overlap or clearance violation")

    def apply(self, operation: str, args: dict):
        positions = list(self.positions)
        indexes = {c.id: i for i, c in enumerate(self.chiplets)}
        if operation == "move" and set(args) == {"chiplet", "x_mm", "y_mm"}:
            positions[indexes[args["chiplet"]]] = (
                _finite_coordinate(args["x_mm"], "move"),
                _finite_coordinate(args["y_mm"], "move"),
            )
        elif operation == "swap" and set(args) == {"a", "b"} and args["a"] != args["b"]:
            a, b = indexes[args["a"]], indexes[args["b"]]
            positions[a], positions[b] = positions[b], positions[a]
        elif operation == "place" and set(args) == {"positions"}:
            supplied = args["positions"]

            def coordinate_pair(pair):
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise DesignValidationError("place coordinates must be two-element lists or tuples")
                return tuple(_finite_coordinate(value, "place") for value in pair)

            if isinstance(supplied, dict):
                if set(supplied) != set(indexes):
                    raise DesignValidationError("place must specify every chiplet exactly once")
                positions = [coordinate_pair(supplied[c.id]) for c in self.chiplets]
            elif isinstance(supplied, (list, tuple)) and len(supplied) == len(self.chiplets):
                positions = [coordinate_pair(pair) for pair in supplied]
            else:
                raise DesignValidationError("place must specify one coordinate pair per chiplet")
        else:
            raise ValueError("operation or argument set not allowlisted")
        candidate = Design(self.width_mm, self.height_mm, self.gap_mm, self.chiplets, tuple(positions))
        candidate.check()
        return candidate


@dataclass(frozen=True)
class ThermalResult:
    candidate_hash: str
    maximum_temperature_c: float
    solver_version: str
    converged: bool = True
    seed: int | None = None
    cost_microdollars: int = 0
    evidence_kind: str = "synthetic-reference-oracle"
    problem_hash: str = ""


@dataclass(frozen=True)
class Proposal:
    payload: dict
    signature: str

    @classmethod
    def sign(cls, key: Ed25519PrivateKey, **payload):
        # Serialization detaches external mutable references and disallows NaN.
        clean = json.loads(canonical(payload))
        return cls(clean, base64.b64encode(key.sign(canonical(clean))).decode())


@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str
    receipt_hash: str
    temperature_c: float | None = None


class Controller:
    def __init__(self, initial: Design, oracle: Callable[[Design], Awaitable[ThermalResult]], *,
                 run_id="sundai-reference", max_oracle_calls=20, max_cost_microdollars=100000,
                 evaluation_ceiling_microdollars=None, max_concurrency=2, max_attempts=3,
                 minimum_improvement_c=0.05, lane_ids=("default",), clock=time.time,
                 pre_admission_check=None):
        initial.check()
        lane_ids = tuple(lane_ids)
        if (not isinstance(evaluation_ceiling_microdollars, int) or
                isinstance(evaluation_ceiling_microdollars, bool) or evaluation_ceiling_microdollars <= 0):
            raise ValueError("evaluation ceiling must be a positive integer number of microdollars")
        if (max_concurrency < 1 or max_attempts < 1 or max_oracle_calls < 1 or
                min(max_cost_microdollars, evaluation_ceiling_microdollars) < 0 or
                not math.isfinite(minimum_improvement_c) or minimum_improvement_c < 0 or
                not lane_ids or len(set(lane_ids)) != len(lane_ids) or
                not all(isinstance(lane_id, str) and lane_id.strip() for lane_id in lane_ids)):
            raise ValueError("invalid budget")
        self.design, self.oracle, self.run_id, self.clock = initial, oracle, run_id, clock
        self.lane_ids = lane_ids
        self.minimum_improvement_c = float(minimum_improvement_c)
        self.revision, self.epoch, self.stopped = 0, 0, False
        self.best_temperature = None
        self.agents = {}
        self.task_grants = {}
        self.lane_agents = {}
        # TAP exposes this synchronous, side-effect-free geometry check. Keep it
        # before expensive-oracle admission, while leaving generic oracles optional.
        self.pre_admission_check = (pre_admission_check if pre_admission_check is not None
                                    else getattr(oracle, "centers_for", None))
        self.seen, self.attempts = set(), {}
        self.host_minted_tasks = set()
        self.verified_designs, self.verified_temperatures = {}, {}
        self.lane_best = {}
        self.log = FlightRecord()
        self.max_calls, self.max_cost = max_oracle_calls, max_cost_microdollars
        self.ceiling = evaluation_ceiling_microdollars
        self.calls, self.spent, self.reserved = 0, 0, 0
        self.actual_oracle_calls = 0
        self.oracle_contract = None
        self.max_attempts = max_attempts
        self.slots, self.lock = asyncio.Semaphore(max_concurrency), asyncio.Lock()

    def register(self, agent_id, key: Ed25519PrivateKey, allowed_tasks=()):
        if agent_id in self.agents:
            raise ValueError("identity already registered")
        self.agents[agent_id] = key.public_key()
        self.task_grants[agent_id] = set(allowed_tasks)
        self.log.append("identity_registered", agent_id=agent_id, public_key=public_hex(key),
                        allowed_tasks=sorted(self.task_grants[agent_id]), scope="local reference identity; no external identity claim")

    def bind_lane(self, lane_id, agent_id):
        """Bind a lane to one registered signing identity for the life of this run."""
        if lane_id not in self.lane_best and lane_id not in self.lane_ids:
            raise ValueError("unknown lane")
        if agent_id not in self.agents:
            raise ValueError("unregistered identity")
        if lane_id in self.lane_agents or agent_id in self.lane_agents.values():
            raise ValueError("lane identity already bound")
        self.lane_agents[lane_id] = agent_id
        self.log.append("lane_identity_bound", lane_id=lane_id, agent_id=agent_id,
                        public_key=self.agents[agent_id].public_bytes(
                            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex())

    def mint_task(self, agent_id):
        """Mint a single-step task grant at the host boundary."""
        if agent_id not in self.task_grants:
            raise ValueError("unregistered identity")
        task_id = str(uuid.uuid4())
        self.task_grants[agent_id].add(task_id)
        self.host_minted_tasks.add(task_id)
        self.log.append("task_granted", agent_id=agent_id, task_id=task_id, host_minted=True)
        return task_id

    async def initialize(self, shared_initial_designs=()):
        if self.best_temperature is not None:
            raise RuntimeError("already initialized")

        designs = [self.design, *shared_initial_designs]
        unique_designs = {}
        for sample_design in designs:
            if not isinstance(sample_design, Design):
                raise ValueError("shared initial samples must be designs")
            sample_design.check()
            if sample_design.hash in unique_designs:
                raise ValueError("shared initial samples must have unique designs")
            unique_designs[sample_design.hash] = sample_design

        samples = {}
        sample_contract = None
        for design_hash, sample_design in unique_designs.items():
            sample_result = await self.oracle(sample_design)
            self.validate_result(sample_result, sample_design)
            contract = (sample_result.solver_version, sample_result.problem_hash, sample_result.evidence_kind)
            if sample_contract is None:
                sample_contract = contract
            elif contract != sample_contract:
                raise ValueError("shared initial samples changed the oracle contract")
            samples[design_hash] = (sample_design, sample_result)
        self.oracle_contract = sample_contract
        for design_hash, (sample_design, sample_result) in samples.items():
            self.verified_designs[design_hash] = sample_design
            self.verified_temperatures[design_hash] = sample_result.maximum_temperature_c
        best_design, best_result = min(samples.values(), key=lambda item: item[1].maximum_temperature_c)
        self.design = best_design
        self.best_temperature = best_result.maximum_temperature_c
        self.lane_best = {lane_id: (self.design, self.best_temperature) for lane_id in self.lane_ids}
        sample_evidence = [{"design_hash": design.hash, "thermal": asdict(sample_result)}
                           for design, sample_result in samples.values()]
        self.log.append("baseline", design_hash=self.design.hash, thermal=asdict(best_result),
                        shared_initial_samples=sample_evidence, proposal_budget=False,
                        initialization_source="controller_oracle",
                        shared_initial_design_count=len(samples) - 1,
                        minimum_improvement_c=self.minimum_improvement_c,
                        problem_contract_hash=self.problem_contract_hash)
        return best_result

    @property
    def problem_contract_hash(self):
        if self.oracle_contract is None:
            return ""
        return digest({"oracle": self.oracle_contract, "minimum_improvement_c": self.minimum_improvement_c})

    @staticmethod
    def validate_result(result, candidate):
        if not isinstance(result, ThermalResult):
            raise ValueError("oracle returned an invalid result type")
        if result.candidate_hash != candidate.hash:
            raise ValueError("oracle result is for another candidate")
        if not result.converged or not math.isfinite(result.maximum_temperature_c) or not result.solver_version:
            raise ValueError("invalid or unconverged oracle result")
        if (not isinstance(result.cost_microdollars, int) or
                isinstance(result.cost_microdollars, bool) or result.cost_microdollars < 0):
            raise ValueError("invalid cost")

    def proposal(self, agent_id, key, task_id, operation, args, *, model_id="replay-fixture", ttl=60,
                 proposal_id=None, prompt_hash=None, tool_hash=None, lane_id="default", parent_hash=None):
        if parent_hash is None:
            parent_hash = self.lane_best.get(lane_id, (self.design, self.best_temperature))[0].hash
        return Proposal.sign(key, proposal_id=proposal_id or str(uuid.uuid4()), agent_id=agent_id,
                             run_id=self.run_id, task_id=task_id, base_revision=self.revision,
                             parent_hash=parent_hash, lane_id=lane_id,
                             problem_contract_hash=self.problem_contract_hash,
                             epoch=self.epoch, expires_at=self.clock() + ttl,
                             operation=operation, args=args, model_id=model_id,
                             prompt_hash=prompt_hash or digest("replay fixture; no model call"),
                             tool_hash=tool_hash or digest("controller.move-or-swap.v1"))

    def outcome(self, status, reason, payload, **extra):
        receipt = self.log.append("proposal_" + status, proposal_id=payload.get("proposal_id"),
                                  agent_id=payload.get("agent_id"), task_id=payload.get("task_id"),
                                  reason=reason, **extra)
        return Outcome(status, reason, receipt, extra.get("temperature_c"))

    async def stop(self, reason="owner STOP"):
        async with self.lock:
            self.stopped = True
            self.epoch += 1
            self.log.append("stopped", epoch=self.epoch, reason=reason)

    async def submit(self, proposal: Proposal):
        try:
            p = json.loads(canonical(proposal.payload))
        except (ValueError, TypeError):
            return self.outcome("rejected", "malformed proposal", {})
        if not isinstance(p, dict):
            return self.outcome("rejected", "malformed proposal", {})
        async with self.lock:
            try:
                self.agents[p["agent_id"]].verify(base64.b64decode(proposal.signature, validate=True), canonical(p))
            except (KeyError, InvalidSignature, ValueError, TypeError):
                return self.outcome("rejected", "unregistered identity or invalid signature", p)
            required = {"proposal_id", "agent_id", "run_id", "task_id", "base_revision", "parent_hash", "lane_id",
                        "problem_contract_hash", "epoch", "expires_at", "operation", "args", "model_id",
                        "prompt_hash", "tool_hash"}
            if set(p) != required or not all(isinstance(p[k], str) and p[k] for k in
                    ("proposal_id", "agent_id", "run_id", "task_id", "parent_hash", "lane_id",
                     "problem_contract_hash", "model_id", "prompt_hash", "tool_hash")):
                return self.outcome("rejected", "invalid proposal contract", p)
            if (not isinstance(p["base_revision"], int) or isinstance(p["base_revision"], bool) or
                    p["base_revision"] < 0):
                return self.outcome("rejected", "invalid proposal contract", p)
            proposal_key = (p["agent_id"], p["proposal_id"])
            if proposal_key in self.seen:
                return self.outcome("rejected", "replayed proposal", p)
            self.seen.add(proposal_key)
            if p["task_id"] not in self.task_grants[p["agent_id"]]:
                return self.outcome("rejected", "task outside agent grant", p)
            reason = self.freshness(p)
            if reason:
                return self.outcome("rejected", reason, p)
            if self.best_temperature is None:
                return self.outcome("rejected", "baseline missing", p)
            attempt_key = (p["agent_id"], p["task_id"])
            if p["task_id"] in self.host_minted_tasks and self.attempts.get(attempt_key, 0):
                return self.outcome("rejected", "host task already consumed", p)
            if self.attempts.get(attempt_key, 0) >= self.max_attempts:
                return self.outcome("rejected", "attempt limit", p)
            self.attempts[attempt_key] = self.attempts.get(attempt_key, 0) + 1
            try:
                parent = self.verified_designs[p["parent_hash"]]
                candidate = parent.apply(p["operation"], p["args"])
            except DesignValidationError as exc:
                return self.outcome("rejected", str(exc), p)
            except (ValueError, KeyError, TypeError, OverflowError):
                return self.outcome("rejected", "invalid geometry or operation", p)
            if self.pre_admission_check is not None:
                try:
                    self.pre_admission_check(candidate)
                except ValueError as exc:
                    return self.outcome("rejected", str(exc), p, oracle_called=False)
                except Exception as exc:
                    return self.outcome("rejected", f"pre-admission legality check failed ({type(exc).__name__})",
                                        p, oracle_called=False)
            reservation = self.ceiling
            if self.calls >= self.max_calls or self.spent + self.reserved + reservation > self.max_cost:
                return self.outcome("rejected", "budget exhausted", p)
            self.calls += 1
            self.reserved += reservation
            self.log.append("proposal_admitted", **p, candidate_hash=candidate.hash,
                            attempt=self.attempts[attempt_key], evaluation_admission=self.calls,
                            reserved_cost_microdollars=reservation)

        started = time.perf_counter()
        reservation_held = True
        charged = False
        oracle_started = False
        result = None
        try:
            async with self.slots:
                # STOP/staleness also checked after waiting for an evaluator slot.
                async with self.lock:
                    reason = self.freshness(p)
                    if reason:
                        self.reserved -= reservation
                        reservation_held = False
                        return self.outcome("rejected", reason, p, oracle_called=False)
                    self.actual_oracle_calls += 1
                    oracle_started = True
                result = await self.oracle(candidate)
                self.validate_result(result, candidate)
                if (result.solver_version, result.problem_hash, result.evidence_kind) != self.oracle_contract:
                    raise ValueError("oracle contract changed; baseline is not comparable")

            async with self.lock:
                self.reserved -= reservation
                reservation_held = False
                self.spent += result.cost_microdollars
                charged = True
                self.log.append("oracle_result", proposal_id=p["proposal_id"], agent_id=p["agent_id"],
                                candidate_hash=candidate.hash,
                                thermal=asdict(result), duration_ms=(time.perf_counter() - started) * 1000)
                if result.cost_microdollars > self.ceiling:
                    self.stopped = True
                    self.epoch += 1
                    return self.outcome("rejected", "provider exceeded declared cost ceiling; stopped", p)
                if self.spent > self.max_cost:
                    self.stopped = True
                    self.epoch += 1
                    return self.outcome("rejected", "run cost budget exceeded; stopped", p)
                reason = self.freshness(p)
                if reason:
                    return self.outcome("rejected", reason, p)
                self.verified_designs[candidate.hash] = candidate
                self.verified_temperatures[candidate.hash] = result.maximum_temperature_c
                lane_best = self.lane_best[p["lane_id"]]
                lane_best_design, lane_best_temperature = lane_best
                improvement_c = lane_best_temperature - result.maximum_temperature_c
                if (improvement_c < self.minimum_improvement_c or
                        (self.minimum_improvement_c == 0 and improvement_c <= 0)):
                    return self.outcome("rejected", "no verified improvement", p,
                                        temperature_c=result.maximum_temperature_c,
                                        lane_best_hash=lane_best_design.hash,
                                        minimum_improvement_c=self.minimum_improvement_c)
                self.lane_best[p["lane_id"]] = (candidate, result.maximum_temperature_c)
                if result.maximum_temperature_c < self.best_temperature:
                    self.design = candidate
                    self.best_temperature = result.maximum_temperature_c
                self.revision += 1
                return self.outcome("committed", "verified improvement on lane best", p,
                                    temperature_c=result.maximum_temperature_c, revision=self.revision,
                                    candidate_hash=candidate.hash, lane_id=p["lane_id"])
        except asyncio.CancelledError:
            async def record_cancellation():
                nonlocal reservation_held
                async with self.lock:
                    charged_cost = 0
                    uncertain_cost = False
                    if reservation_held:
                        self.reserved -= reservation
                        if oracle_started:
                            if (isinstance(result, ThermalResult) and
                                    isinstance(result.cost_microdollars, int) and
                                    not isinstance(result.cost_microdollars, bool) and result.cost_microdollars >= 0):
                                charged_cost = result.cost_microdollars
                            else:
                                charged_cost = reservation
                                uncertain_cost = True
                            self.spent += charged_cost
                            if self.spent > self.max_cost or charged_cost > self.ceiling:
                                self.stopped = True
                                self.epoch += 1
                        reservation_held = False
                    self.log.append("proposal_cancelled", proposal_id=p["proposal_id"],
                                    agent_id=p["agent_id"], task_id=p["task_id"],
                                    candidate_hash=candidate.hash, oracle_started=oracle_started,
                                    charged_cost_microdollars=charged_cost, uncertain_cost=uncertain_cost,
                                    final=True)
            cleanup = asyncio.create_task(record_cancellation())
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
            raise
        except Exception as exc:
            async with self.lock:
                if reservation_held:
                    self.reserved -= reservation
                    if not charged:
                        if oracle_started:
                            if (isinstance(result, ThermalResult) and
                                    isinstance(result.cost_microdollars, int) and
                                    not isinstance(result.cost_microdollars, bool) and result.cost_microdollars >= 0):
                                charged_cost = result.cost_microdollars
                            else:
                                charged_cost = reservation  # conservative charge on uncertain failure
                            self.spent += charged_cost
                            if self.spent > self.max_cost or charged_cost > self.ceiling:
                                self.stopped = True
                                self.epoch += 1
                    reservation_held = False
                return self.outcome("failed", "oracle failed; incumbent preserved", p,
                                    error_type=type(exc).__name__, candidate_hash=candidate.hash,
                                    duration_ms=(time.perf_counter() - started) * 1000)

    def freshness(self, p):
        if self.stopped or p.get("epoch") != self.epoch:
            return "stopped or invalidated epoch"
        if p.get("run_id") != self.run_id:
            return "wrong run"
        if not isinstance(p.get("expires_at"), (float, int)) or not math.isfinite(p["expires_at"]) or p["expires_at"] <= self.clock():
            return "expired proposal"
        if p.get("problem_contract_hash") != self.problem_contract_hash:
            return "wrong problem contract"
        if p.get("lane_id") not in self.lane_best:
            return "unknown lane"
        bound_agent = self.lane_agents.get(p.get("lane_id"))
        if bound_agent is not None and bound_agent != p.get("agent_id"):
            return "agent not bound to lane"
        if p.get("parent_hash") not in self.verified_designs:
            return "stale parent"
        return None


async def choose_advisory_operation(providers, request, *, timeout_s=2):
    """Ordered fallback only. Returned advice has NO acceptance authority."""
    failures = []
    for provider_id, provider in providers:
        try:
            operation = await asyncio.wait_for(provider(request), timeout_s)
            if not isinstance(operation, dict) or set(operation) != {"operation", "args"}:
                raise ValueError("invalid advisory schema")
            if operation["operation"] not in {"move", "swap", "place"} or not isinstance(operation["args"], dict):
                raise ValueError("invalid advisory operation")
            return {"provider_id": provider_id, **operation, "prior_failures": failures}
        except Exception as exc:
            failures.append({"provider_id": provider_id, "error_type": type(exc).__name__})
    raise RuntimeError("all advisory providers failed; no action")


class DisabledJevAdapter:
    """No endpoint/schema invented and no provider calls made by this reference."""
    async def __call__(self, request):
        raise RuntimeError("Jev disabled: wire a verified API adapter and explicit budgets before enabling")


class JevRoutingAdapter:
    """Official System One schema; OFF by default. This class never grades physics.

    Set JEV_ENABLE_REQUESTS=1 and JEV_API_KEY explicitly to permit provider calls.
    Configure a provider-side spending limit: request count is not a dollar cap.
    One logical call gets at most one retry for HTTP 429/529. Credentials and raw
    provider output are never returned to callers; only hashes and validated advice are.
    """
    routes = {"local_move", "swap", "global_resample", "stop"}
    model_id = "jev-1.13.0"
    max_request_bytes = 50_000
    max_response_bytes = 262_144
    max_timeout_s = 60.0
    retry_delay_s = 0.1

    def __init__(self, max_calls=4, timeout_s=2):
        if not isinstance(max_calls, int) or isinstance(max_calls, bool) or max_calls < 0:
            raise ValueError("max_calls must be a nonnegative integer")
        if (not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or
                not math.isfinite(timeout_s) or timeout_s <= 0 or timeout_s > self.max_timeout_s):
            raise ValueError("timeout_s must be positive and no greater than 60 seconds")
        self.max_calls, self.timeout_s, self.calls = max_calls, float(timeout_s), 0

    def __call__(self, state):
        return self.route(state)

    @staticmethod
    def _fallback(reason, *, input_hash=None, output_hash=None, provider_called=False,
                  duration_ms=0.0, retry_count=0, error_type=None,
                  input_tokens=None, output_tokens=None):
        result = {"route": None, "reason": reason, "provider_called": provider_called,
                  "input_hash": input_hash, "probabilities": None, "confidence": None,
                  "duration_ms": duration_ms, "retry_count": retry_count,
                  "error_type": error_type, "input_tokens": input_tokens,
                  "output_tokens": output_tokens}
        result["output_hash"] = output_hash or digest({"fallback": reason, "input_hash": input_hash})
        return result

    async def route(self, state):
        import os
        import time as time_module
        import urllib.error
        import urllib.request

        if not isinstance(state, dict):
            return self._fallback("invalid routing state")
        request_value = {"model": self.model_id, "state": state, "questions": {"route": {
            "type": "choice",
            "instructions": "Choose the operator for the next single evaluation from verified history and the remaining budget. Stop means stop requesting signal-layer advice; the host may continue its equal-budget run using its deterministic policy. This is advisory only and never validates physics or authorizes a commit.",
            "criteria": {
                "local_move": "Try a small legal local coordinate change to the selected chiplet.",
                "swap": "Exchange two chiplets if a different arrangement is useful.",
                "global_resample": "Explore a substantially different legal full layout.",
                "stop": "Stop further signal-layer calls when advice is unlikely to help."}}}}
        try:
            body = canonical(request_value)
            input_hash = hashlib.sha256(body).hexdigest()
        except (TypeError, ValueError, OverflowError):
            return self._fallback("invalid routing state")
        if len(body) > self.max_request_bytes:
            return self._fallback("bounded state exceeded", input_hash=input_hash)
        if os.environ.get("JEV_ENABLE_REQUESTS") != "1":
            return self._fallback("Jev disabled; deterministic fallback", input_hash=input_hash)
        if self.calls >= self.max_calls:
            return self._fallback("call budget exhausted; deterministic fallback", input_hash=input_hash)
        key = os.environ.get("JEV_API_KEY")
        if not key:
            return self._fallback("missing credential; deterministic fallback", input_hash=input_hash)
        self.calls += 1
        started = time_module.perf_counter()
        attempts = [0]
        output_hash = [None]
        usage_counts = [None, None]

        def request():
            for attempt in range(2):
                attempts[0] += 1
                req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", body,
                                             {"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                        raw = response.read(self.max_response_bytes + 1)
                    output_hash[0] = hashlib.sha256(raw).hexdigest()
                    if len(raw) > self.max_response_bytes:
                        raise ValueError("response too large")
                    payload = json.loads(raw)
                    if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
                        usage = payload["usage"]
                        values = (usage.get("input_tokens"), usage.get("output_tokens"))
                        if all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
                               for value in values):
                            usage_counts[:] = values
                    return payload
                except urllib.error.HTTPError as exc:
                    if attempt == 0 and exc.code in (429, 529):
                        time_module.sleep(self.retry_delay_s)
                        continue
                    raise
            raise RuntimeError("bounded retry exhausted")

        try:
            result = await asyncio.to_thread(request)
            if not isinstance(result, dict) or result.get("model") != self.model_id:
                raise ValueError("unexpected model or choice")
            answers = result.get("answers")
            if not isinstance(answers, dict):
                raise ValueError("unexpected model or choice")
            answer = answers.get("route")
            if (not isinstance(answer, dict) or answer.get("type") != "choice" or
                    answer.get("choice") not in self.routes):
                raise ValueError("unexpected model or choice")
            probabilities = answer.get("probabilities")
            if not isinstance(probabilities, dict):
                raise ValueError("invalid probabilities")
            values = list(probabilities.values())
            if (set(probabilities) != self.routes or
                    not all(isinstance(v, (int, float)) and not isinstance(v, bool) and
                            math.isfinite(v) and 0 <= v <= 1 for v in values) or
                    abs(sum(values) - 1) > 0.01):
                raise ValueError("invalid probabilities")
            confidence = answer.get("confidence")
            if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or
                    not math.isfinite(confidence) or not 0 <= confidence <= 1):
                raise ValueError("invalid confidence")
            return {"route": answer["choice"], "reason": "validated TypeSafe CHOICE advice",
                    "provider_called": True, "model_validated": True,
                    "probabilities": {name: float(probabilities[name]) for name in sorted(self.routes)},
                    "confidence": float(confidence), "input_hash": input_hash,
                    "output_hash": output_hash[0],
                    "duration_ms": (time_module.perf_counter() - started) * 1000,
                    "retry_count": attempts[0] - 1, "error_type": None,
                    "input_tokens": usage_counts[0], "output_tokens": usage_counts[1]}
        except Exception as exc:
            return self._fallback("provider failure; deterministic fallback", input_hash=input_hash,
                                  output_hash=output_hash[0], provider_called=True,
                                  duration_ms=(time_module.perf_counter() - started) * 1000,
                                  retry_count=max(0, attempts[0] - 1), error_type=type(exc).__name__,
                                  input_tokens=usage_counts[0], output_tokens=usage_counts[1])


def thermal_plate_adapter(grid_size=40):
    """Adapter to the sibling synthetic FVM demo. It is NOT chip sign-off."""
    import sys
    from pathlib import Path
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sundai_thermal"))
    from simulation import Plate, legal, POWERS
    if not isinstance(grid_size, int) or isinstance(grid_size, bool) or grid_size < 2:
        raise ValueError("plate grid size must be an integer >= 2")
    plate = Plate(grid_size)
    source_bytes = (Path(__file__).resolve().parent.parent / "sundai_thermal" / "simulation.py").read_bytes()
    problem_hash = digest({"source_file_sha256": normalized_source_sha256(source_bytes),
                           "grid": grid_size, "powers": np.asarray(POWERS).tolist(), "coordinate_units": "mm"})

    async def evaluate(candidate):
        candidate.check()
        if [(c.width_mm, c.height_mm) for c in candidate.chiplets] != [(6, 6), (6, 6), (5, 5), (5, 5)] or (candidate.width_mm, candidate.height_mm, candidate.gap_mm) != (25, 25, 0.5):
            raise ValueError("plate adapter catalog mismatch")
        centers = np.array([[x + c.width_mm / 2, y + c.height_mm / 2]
                            for c, (x, y) in zip(candidate.chiplets, candidate.positions)])
        if not legal(centers):
            raise ValueError("plate solver geometry rejected")
        peaks = await asyncio.to_thread(plate.evaluate, centers)
        return ThermalResult(candidate.hash, float(max(peaks)), f"synthetic-fvm-plate-v1-grid{grid_size}",
                             evidence_kind="synthetic steady-state plate; not silicon junction signoff", problem_hash=problem_hash)
    return evaluate
