"""Isolated, pinned lead/judge infrastructure. Only local stand-ins can execute.

The SLAB-003 protocol is injected; StandInAdmission cannot admit a real model.
SLAB-039/041 records are placeholders until their authoritative producers merge.
No provider SDK, credential, network transport, or acceptance capability lives here.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import math
from typing import ClassVar, Protocol

from .envelope import canonical, check_caps, digest
from .labs import FAMILIES, MAX_MESSAGE_BYTES, Request, validate_message

LEAD_PROMPT = "SLAB-044/lead/1: Place the fixed catalog using only this lab's context. Return lab-proposal/1. Do not claim acceptance."
JUDGE_PROMPT = "SLAB-044/judge/1: Review only the supplied candidate and evidence. Return lab-review/1. Verdicts are advisory."
RUBRIC = "SLAB-044/rubric/1: Check geometry, evidence binding, convergence and reproduction. Missing evidence means abstain. A concern or no_concern never grants acceptance."


class NotAdmitted(Exception):
    pass


class OverCap(Exception):
    pass


class ProviderOutage(Exception):
    pass


@dataclass(frozen=True)
class AdmissionRecord:
    model_id: str
    version: str
    fixture_only: bool = True


class Admission(Protocol):
    def check(self, model_id: str) -> AdmissionRecord: ...
    def meter(self, model_id: str, usd: float) -> None: ...


class StandInAdmission:
    """Zero-dollar SLAB-003 stub. No model name can opt into paid execution."""
    def __init__(self):
        self.checks = []
        self.charges = []

    def check(self, model_id):
        self.checks.append(model_id)
        if model_id not in (DeterministicLead.model_id, DeterministicJudge.model_id):
            raise NotAdmitted("only the deterministic stand-in is admitted")
        return AdmissionRecord(model_id, "1")

    def meter(self, model_id, usd):
        if model_id not in (DeterministicLead.model_id, DeterministicJudge.model_id):
            raise NotAdmitted("unknown model")
        if type(usd) not in (int, float) or not math.isfinite(usd) or usd != 0:
            raise OverCap("stand-in spending cap is zero")
        self.charges.append((model_id, usd))


@dataclass(frozen=True)
class Readiness:
    headroom: str = "HOLD"
    frozen: bool = False
    freeze_id: str = "SLAB-041-pending"
    missing_data_policy: str = "record_missing_no_retry"

    def __post_init__(self):
        if self.headroom not in ("PASS", "HOLD", "FAIL", "INCONCLUSIVE") or type(self.frozen) is not bool:
            raise ValueError("invalid readiness")
        if not isinstance(self.freeze_id, str) or not self.freeze_id or len(self.freeze_id) > 128:
            raise ValueError("freeze reference required")
        if self.missing_data_policy != "record_missing_no_retry":
            raise ValueError("only the no-retry missing-data fixture policy is implemented")


@dataclass(frozen=True)
class LayoutContext:
    """Immutable serialized input; no shared cache, ledger, signer or oracle."""
    data: bytes


class LeadAdapter(Protocol):
    model_id: str
    version: str
    async def propose(self, context: LayoutContext) -> dict: ...


class JudgeAdapter(Protocol):
    model_id: str
    version: str
    async def review(self, candidate: bytes, evidence: bytes) -> dict: ...


@dataclass(frozen=True)
class DeterministicLead:
    model_id: ClassVar[str] = "stand-in/lead-v1"
    version: ClassVar[str] = "1"
    outage: bool = False

    async def propose(self, context):
        import json
        if self.outage:
            raise ProviderOutage("stand-in outage")
        data = json.loads(context.data)
        initial = data["initial"]
        # Reflection preserves containment and pairwise spacing; no thermal solve.
        reflect = int(digest(data)[0], 16) % 2 == 1
        geometry = [{"id": chip["id"],
                     "x_mm": initial["width_mm"] - chip["width_mm"] - xy[0] if reflect else xy[0],
                     "y_mm": xy[1]} for chip, xy in zip(initial["chiplets"], initial["positions"])]
        return {"v": "lab-proposal/1", "kind": "proposal", "lab_id": data["scope"]["lab_id"],
                "role": "scientist", "rationale": "Deterministic isolated layout fixture.", "geometry": geometry}


@dataclass(frozen=True)
class DeterministicJudge:
    model_id: ClassVar[str] = "stand-in/judge-v1"
    version: ClassVar[str] = "1"
    verdict: str | None = None
    outage: bool = False

    def __post_init__(self):
        if self.verdict not in (None, "concern", "no_concern", "abstain"):
            raise ValueError("invalid advisory verdict")

    async def review(self, candidate, evidence):
        import json
        if self.outage:
            raise ProviderOutage("stand-in outage")
        candidate, data = json.loads(candidate), json.loads(evidence)
        observations = data["evidence"]
        verdict = "abstain"
        if len(observations) == 2:
            matching = (observations[0].get("binding") == observations[1].get("binding")
                        and all(e.get("success") is True for e in observations)
                        and all(type(e.get("j")) in (int, float) for e in observations))
            verdict = "no_concern" if matching and abs(observations[0]["j"] - observations[1]["j"]) <= 0.001 else "concern"
        return {"v": "lab-review/1", "kind": "review", "lab_id": data["scope"]["lab_id"],
                "role": "adversarial_judge", "target_hash": data["target_hash"],
                "judge_role": "reproducibility_auditor", "verdict": self.verdict or verdict,
                "findings": ["Apply the deterministic geometry and evidence gate independently."],
                "rationale": "Fixture rubric only; no scientific acceptance authority."}


@dataclass(frozen=True)
class LabAdapters:
    lab_id: str
    family: str
    lead: LeadAdapter
    judge: JudgeAdapter

    def __post_init__(self):
        if self.lab_id not in FAMILIES or self.family != self.lab_id:
            raise ValueError("the four isolated labs require their declared family namespaces")


@dataclass(frozen=True)
class CallResult:
    message: dict | None
    provenance: dict
    context: dict
    reason: str | None = None


class IsolatedLabs:
    """Trusted context projector and call boundary, never passed to adapters.

    `records` must be the current run's verified ledger prefix, flattened by the
    conductor. Only own-lab candidates and their measurements enter lead memory.
    Judging uses a separate stateless adapter and never teaches another lead.
    """
    def __init__(self, labs, *, admission: Admission, readiness=Readiness(), call_limit=12, timeout=1.0):
        labs = tuple(labs)
        if not 1 <= len(labs) <= 4 or len({x.lab_id for x in labs}) != len(labs):
            raise ValueError("one to four distinct isolated labs required")
        if type(call_limit) is not int or not 1 <= call_limit <= 1000:
            raise ValueError("invalid call limit")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError("invalid call timeout")
        self.labs = {x.lab_id: x for x in labs}
        self.admission, self.readiness = admission, readiness
        self.call_limit, self.timeout = call_limit, timeout
        self._attempts = {}

    def describe(self):
        def pin(adapter):
            value = {"model_id": adapter.model_id, "version": adapter.version}
            if type(adapter) in (DeterministicLead, DeterministicJudge):
                value.update(asdict(adapter))
            return value
        return {"v": "isolated-labs/1", "labs": [
            {"lab_id": x.lab_id, "family": x.family, "lead": pin(x.lead), "judge": pin(x.judge)}
            for x in self.labs.values()], "readiness": asdict(self.readiness),
            "lead_prompt_hash": digest(LEAD_PROMPT), "judge_prompt_hash": digest(JUDGE_PROMPT),
            "rubric_hash": digest(RUBRIC), "memory_version": "own-candidates-and-measurements/1",
            "call_limit": self.call_limit, "timeout": self.timeout}

    @property
    def stand_in_only(self):
        return all(type(x.lead) is DeterministicLead and type(x.judge) is DeterministicJudge
                   for x in self.labs.values())

    @staticmethod
    def _scope(lab_id, run):
        return {**{k: run[k] for k in ("run_id", "arm", "family", "seed")}, "lab_id": lab_id}

    async def propose(self, lab_id, run, initial, records, ordinal, *, sink=None):
        own = [r for r in records if r.get("type") == "candidate" and r.get("lane") == lab_id][-4:]
        memory = [{"candidate": {k: v for k, v in r.items() if k != "type"},
                   "evidence": [e for e in records if e.get("type") == "measurement"
                                and e.get("candidate_node") == r["node"]]} for r in own]
        context = {"scope": self._scope(lab_id, run), "ordinal": ordinal, "initial": initial,
                   "memory": memory, "prompt": LEAD_PROMPT}
        return await self._call(lab_id, "propose", context, records, sink)

    async def review(self, lab_id, run, candidate, evidence, target_hash, ordinal, *, records=(), sink=None):
        context = {"scope": self._scope(lab_id, run), "ordinal": ordinal, "candidate": candidate,
                   "evidence": evidence, "target_hash": target_hash, "prompt": JUDGE_PROMPT, "rubric": RUBRIC}
        return await self._call(lab_id, "review", context, records, sink)

    async def _call(self, lab_id, operation, context, records, sink):
        import json
        lab = self.labs[lab_id]
        adapter = lab.lead if operation == "propose" else lab.judge
        scope = context["scope"]
        call_id = digest({"scope": scope, "operation": operation, "ordinal": context["ordinal"]})
        provenance = {"originator": lab_id, "family": lab.family, "role": operation,
                      "model_id": adapter.model_id, "model_version": adapter.version,
                      "prompt_hash": digest(context["prompt"]), "rubric_hash": digest(RUBRIC) if operation == "review" else None,
                      "seed": scope["seed"], "scope": scope, "call_id": call_id,
                      "configuration_hash": digest(self.describe()), "context_hash": digest(context)}
        # Detach even trusted mutable caller data before any await.
        encoded = canonical(context)
        context = json.loads(encoded)
        prior = {r["call_id"]: r for r in records if r.get("type") == "lab.adapter_call" and r.get("status") == "reserved"}
        prior.update(self._attempts)
        if call_id in prior:
            return CallResult(None, provenance, context, "already_attempted")
        charged = sum(r["scope"] == scope for r in prior.values())
        if charged >= self.call_limit:
            return CallResult(None, provenance, context, "call_budget")

        base = {"type": "lab.adapter_call", "call_id": call_id, "scope": scope,
                "operation": operation, "provenance": provenance, "usd": 0.0,
                "missing_data_policy": self.readiness.missing_data_policy}
        def emit(status, reason=None):
            record = {**base, "status": status, "reason": reason}
            if sink is not None:
                sink(record)
            return record
        self._attempts[call_id] = emit("reserved")
        try:
            admitted = self.admission.check(adapter.model_id)
            if admitted.model_id != adapter.model_id or admitted.version != adapter.version:
                raise ValueError("pin_mismatch")
            if type(adapter) not in (DeterministicLead, DeterministicJudge):
                if self.readiness.headroom != "PASS" or not self.readiness.frozen:
                    raise ValueError("readiness_hold")
                raise ValueError("real_calls_disabled")
            if admitted.fixture_only is not True:
                raise ValueError("pin_mismatch")
            check_caps(context)
            if len(encoded) > MAX_MESSAGE_BYTES:
                raise ValueError("context_limit")
            # Meter before invocation, retain charge on failure; never retry.
            self.admission.meter(adapter.model_id, 0.0)
            if operation == "propose":
                pending = adapter.propose(LayoutContext(encoded))
            else:
                pending = adapter.review(canonical(context["candidate"]), canonical(context))
            raw = await asyncio.wait_for(pending, self.timeout)
            request = Request(target_hash=context.get("target_hash"), judge_role="reproducibility_auditor")
            message = validate_message(raw, operation, lab_id, request)
        except asyncio.CancelledError:
            emit("missing", "cancelled")
            raise
        except (NotAdmitted, OverCap, ProviderOutage, TimeoutError) as exc:
            reason = next(reason for cls, reason in ((NotAdmitted, "not_admitted"), (OverCap, "over_cap"),
                          (ProviderOutage, "provider_outage"), (TimeoutError, "timeout")) if isinstance(exc, cls))
            emit("missing", reason)
            return CallResult(None, provenance, context, reason)
        except ValueError as exc:
            reason = str(exc) if str(exc) in ("pin_mismatch", "readiness_hold", "real_calls_disabled", "context_limit") else "invalid_response"
            emit("missing", reason)
            return CallResult(None, provenance, context, reason)
        except Exception:
            emit("missing", "provider_error")
            return CallResult(None, provenance, context, "provider_error")
        emit("completed")
        return CallResult(message, provenance, context)
