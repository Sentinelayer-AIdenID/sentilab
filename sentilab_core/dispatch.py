"""Bounded, round-robin advisory dispatch; budgets charge reservations, not claims.

Only cooperative async adapters belong here. The conductor currently accepts
exact ReplayLab instances only. Live/untrusted executable workers need process
isolation and approved headroom before an adapter can be wired into that hook.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field, replace
import math
import re

from .admission import NotAdmitted, OverCap
from .model_calls import AdmittedLab
from .envelope import check_caps
from .labs import FAMILIES, JUDGE_ROLES, KINDS, MAX_MESSAGE_BYTES, Lab, ReplayLab, Request, validate_message


@dataclass(frozen=True)
class LabBudget:
    calls: int = 12
    tokens: int = 262144
    wall_seconds: float = 30.0
    concurrency: int = 1
    call_timeout: float = 1.0
    output_bytes: int = MAX_MESSAGE_BYTES

    def __post_init__(self):
        for name, maximum in (("calls", 1000), ("tokens", 100000000),
                              ("concurrency", 2), ("output_bytes", MAX_MESSAGE_BYTES)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid lab budget: " + name)
        for name in ("wall_seconds", "call_timeout"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 3600:
                raise ValueError("invalid lab budget: " + name)


@dataclass(frozen=True)
class Registration:
    """Family and judge assignment come from trusted configuration, never output."""
    lab_id: str
    family: str
    lab: Lab
    budget: LabBudget = field(default_factory=LabBudget)
    judge_role: str = "constraint_auditor"

    def __post_init__(self):
        if not isinstance(self.lab_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", self.lab_id):
            raise ValueError("invalid lab id")
        if self.family not in FAMILIES or self.judge_role not in JUDGE_ROLES:
            raise ValueError("unknown lab family or judge role")
        if not isinstance(self.budget, LabBudget):
            raise ValueError("invalid lab budget")


class Dispatcher:
    def __init__(self, registrations, *, concurrency=4):
        registrations = tuple(registrations)
        if not 1 <= len(registrations) <= 4 or len({r.lab_id for r in registrations}) != len(registrations):
            raise ValueError("one to four distinct labs required")
        if type(concurrency) is not int or not 1 <= concurrency <= 4:
            raise ValueError("invalid dispatcher concurrency")
        self.registrations = {r.lab_id: r for r in registrations}
        self.concurrency = concurrency
        self._slots = asyncio.Semaphore(concurrency)
        self._round_lock = asyncio.Lock()
        self._round = 0
        self.events = []
        self.usage = {r.lab_id: {"calls": 0, "tokens": 0, "wall_seconds": 0.0} for r in registrations}
        self._active = dict.fromkeys(self.registrations, 0)

    def describe(self):
        return {"concurrency": self.concurrency, "labs": [
            {"lab_id": r.lab_id, "family": r.family, "judge_role": r.judge_role,
             "budget": asdict(r.budget), "fixture_hash": getattr(r.lab, "fixture_hash", None)}
            for r in self.registrations.values()]}

    def restore(self, records):
        """Replay only core-signed reservation records before attaching to a run."""
        if any(self._active.values()):
            raise ValueError("cannot restore active dispatcher")
        self.usage = {lab_id: {"calls": 0, "tokens": 0, "wall_seconds": 0.0}
                      for lab_id in self.registrations}
        self.events = []
        for record in records:
            if record.get("type") == "lab.dispatch" and record.get("status") == "reserved":
                self.usage[record["lab_id"]] = dict(record["usage"])

    def _event(self, lab_id, operation, status, reason, sink):
        record = {"type": "lab.dispatch", "lab_id": lab_id, "operation": operation,
                  "status": status, "reason": reason, "usage": dict(self.usage.get(lab_id, {}))}
        self.events.append(record)
        if sink is not None:
            sink(record)

    async def call(self, lab_id, operation, request: Request, *, sink=None):
        def refuse(reason):
            self._event(lab_id, operation, "refused", reason, sink)
            return None

        if lab_id not in self.registrations or operation not in KINDS:
            return refuse("unknown_assignment")
        registration = self.registrations[lab_id]
        if type(registration.lab) not in (ReplayLab, AdmittedLab):
            return refuse("model_not_admitted")
        if operation != "propose":
            target = self.registrations.get(request.target_lab)
            if target is None or not isinstance(request.target_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", request.target_hash):
                return refuse("unknown_target")
            if operation == "review":
                if target.family == registration.family:
                    return refuse("nonindependent_review")
                request = replace(request, judge_role=registration.judge_role)
            elif lab_id != request.target_lab or not isinstance(request.review_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", request.review_hash):
                return refuse("invalid_repair_target")
        try:
            encoded = check_caps(request.wire())
            if len(encoded) > MAX_MESSAGE_BYTES:
                return refuse("invalid_request")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return refuse("invalid_request")
        budget = registration.budget
        # Fixture accounting: one canonical UTF-8 byte is one conservative token
        # unit. Reserve input + maximum output, including on failure/cancellation.
        tokens = len(encoded) + budget.output_bytes
        if self._active[lab_id] >= budget.concurrency:
            return refuse("concurrency_budget")
        async with self._slots:
            usage = self.usage[lab_id]
            if self._active[lab_id] >= budget.concurrency:
                return refuse("concurrency_budget")
            for reason, exceeds in (("call_budget", usage["calls"] >= budget.calls),
                                    ("token_budget", usage["tokens"] + tokens > budget.tokens),
                                    ("wall_budget", usage["wall_seconds"] + budget.call_timeout > budget.wall_seconds)):
                if exceeds:
                    return refuse(reason)
            usage["calls"] += 1
            usage["tokens"] += tokens
            usage["wall_seconds"] += budget.call_timeout
            # This reservation is recorded before any adapter code executes.
            self._event(lab_id, operation, "reserved", "budget_reserved", sink)
            self._active[lab_id] += 1
            try:
                raw = await asyncio.wait_for(getattr(registration.lab, operation)(request), budget.call_timeout)
                result = validate_message(raw, operation, lab_id, request, max_bytes=budget.output_bytes)
            except asyncio.CancelledError:
                self._event(lab_id, operation, "refused", "cancelled", sink)
                raise
            except TimeoutError:
                return refuse("wall_timeout")
            except NotAdmitted:
                return refuse("model_not_admitted")
            except OverCap:
                return refuse("model_cost_cap")
            except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
                return refuse("invalid_response")
            except Exception:
                return refuse("lab_error")
            finally:
                self._active[lab_id] -= 1
            self._event(lab_id, operation, "completed", "advisory_only", sink)
            return result

    async def round(self, operation, requests, *, sink=None):
        """One opportunity per registered lab, rotated start; no automatic retries."""
        if set(requests) - self.registrations.keys():
            raise ValueError("unknown round participant")
        async with self._round_lock:
            order = list(self.registrations)
            offset = self._round % len(order)
            self._round += 1
            order = order[offset:] + order[:offset]
            selected = [lab_id for lab_id in order if lab_id in requests]
            results = await asyncio.gather(*(self.call(lab_id, operation, requests[lab_id], sink=sink)
                                             for lab_id in selected))
            return dict(zip(selected, results))
