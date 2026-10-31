"""SLAB-052 proposal harness. Host configuration is authority, never lab input.

No model transport or default solver is installed here. A host supplies the
SLAB-051 single-evaluation adapter after SLAB-048 readiness, admission and a
prospective grant. The budgeted oracle is the only lab-facing evaluation path.
"""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from .admission import Admission, NotAdmitted, public_name
from .envelope import canonical, check_caps, digest, validate_run_id
from .execution import _finish, admit
from .ledger import Ledger, LockBusy, lock

SCHEMA = "sentilab-proposal/1"
CLAIM = "descriptive computational simulation"
PROMPT = ("Propose ordered chiplet centers using only this public problem and your own feedback. "
          "Every submission, including an illegal layout, consumes one oracle slot. "
          "Results are simulated and descriptive; do not claim measured silicon performance.")


class _Stopped(Exception):
    pass


class _AdmissionRevoked(NotAdmitted):
    pass


def _positive(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("invalid positive bound")
    return value


@dataclass(frozen=True)
class PublicProblem:
    """Deliberate allowlist: no arbitrary prompt text, reference layout or answers."""
    oracle_id: str
    width_mm: float
    height_mm: float
    # Ordered (public catalog id, width_mm, height_mm, power_w).
    chiplets: tuple
    wire_cap_mm: float

    def __post_init__(self):
        if not isinstance(self.oracle_id, str) or not re.fullmatch(r"[0-9a-f]{64}", self.oracle_id):
            raise ValueError("oracle identity must bind the frozen constrained objective")
        for value in (self.width_mm, self.height_mm, self.wire_cap_mm):
            _positive(value)
        if type(self.chiplets) is not tuple or not 1 <= len(self.chiplets) <= 32:
            raise ValueError("invalid public catalog")
        names = []
        for chip in self.chiplets:
            if type(chip) is not tuple or len(chip) != 4:
                raise ValueError("invalid public chiplet")
            validate_run_id(chip[0])
            names.append(chip[0])
            for value in chip[1:]:
                _positive(value)
        if len(set(names)) != len(names):
            raise ValueError("duplicate public chiplet")

    def wire(self):
        return {**asdict(self), "chiplets": [list(chip) for chip in self.chiplets]}


@dataclass(frozen=True)
class ProposalGrant:
    """Operator-issued evidence references; this class does not mint approval."""
    run_id: str
    reference: str
    readiness_ref: str
    oracle_id: str
    expires_at: str
    solve_budget: int
    lab_ids: tuple

    def check(self, run_id, oracle_id, solve_budget, lab_ids):
        try:
            public_name(self.reference)
            public_name(self.readiness_ref)
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            if (self.run_id != run_id or self.oracle_id != oracle_id
                    or type(self.solve_budget) is not int or self.solve_budget != solve_budget
                    or type(self.lab_ids) is not tuple or self.lab_ids != tuple(lab_ids) or expires.tzinfo is None
                    or datetime.now(timezone.utc) >= expires):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise NotAdmitted("proposal grant missing, expired or wrong scope") from None


@dataclass(frozen=True)
class ProposalLab:
    lab_id: str
    model_id: str
    admission: Admission

    def check(self, run_id):
        validate_run_id(self.lab_id)
        public_name(self.model_id)
        if (type(self.admission) is not Admission or self.admission.run_id != run_id
                or self.admission.arm_id != self.lab_id):
            raise NotAdmitted("proposal admission scope mismatch")
        record = self.admission.check(self.model_id)
        if "lead" not in record.roles:
            raise NotAdmitted("proposal requires lead admission")
        return record


class ProposalHarness:
    """Operator orchestration for N isolated labs at one frozen slot budget.

    Each lab uses its own host-bound session/transport. Do not give proposer
    processes this object, the operator ledger, generic live/dataset/memory tools
    or host filesystem access. Model generation stays in the admitted host lane.
    """
    def __init__(self, *, root, run, signer, public_keys, problem, labs, solve_budget,
                 grant, oracle_factory, timeout=30):
        if type(problem) is not PublicProblem or type(grant) is not ProposalGrant:
            raise NotAdmitted("reviewed proposal configuration required")
        if type(solve_budget) is not int or not 1 <= solve_budget <= 10000:
            raise ValueError("invalid proposal budget")
        if not 0 < _positive(timeout) <= 300:
            raise ValueError("invalid proposal timeout")
        labs = tuple(labs)
        if (not 1 <= len(labs) <= 32 or any(type(lab) is not ProposalLab for lab in labs)
                or len({lab.lab_id for lab in labs}) != len(labs)
                or len(labs) * solve_budget > 10000):
            raise ValueError("one to 32 distinct labs and at most 10000 total slots required")
        if signer is None or public_keys.get(signer.key_id) != signer.public_key:
            raise NotAdmitted("pinned proposal signer required")
        self.run = deepcopy(run)
        self.problem, self.grant = problem, grant
        self.solve_budget, self.timeout = solve_budget, timeout
        self.labs = {lab.lab_id: lab for lab in labs}
        self.root = Path(root).resolve()
        self.stop_file = self.root / "STOP"
        grant.check(run["run_id"], problem.oracle_id, solve_budget, self.labs)
        for lab in labs:
            lab.check(run["run_id"])
        self.ledger = Ledger(self.root, run, signer=signer, public_keys=public_keys)
        manifest = {"schema": SCHEMA, "claim": CLAIM, "problem": problem.wire(),
                    "labs": [{"lab_id": lab.lab_id, "model_id": lab.model_id} for lab in labs],
                    "solve_budget": solve_budget, "timeout": timeout,
                    "grant": {**asdict(grant), "lab_ids": list(grant.lab_ids)}}
        check_caps(manifest)
        # A new host/restart cannot raise the budget or change the task/grant.
        with lock(self.root / (run["run_id"] + ".proposal-config.lock")):
            state = self._events()
            if state:
                if state[0]["event"]["type"] != "proposal.config" or state[0]["event"]["body"] != manifest:
                    raise ValueError("proposal run configuration changed")
            else:
                self.ledger.append("proposal.config", manifest, event_id="proposal-config")
        self.oracles = {lab.lab_id: BudgetedProposalOracle(self, lab, oracle_factory()) for lab in labs}
        if any(oracle.backend.oracle_id != problem.oracle_id for oracle in self.oracles.values()):
            raise NotAdmitted("constrained oracle identity mismatch")

    def _events(self):
        state = self.ledger.read()
        self.ledger._require_sound(state)
        return state["prefix"]

    def bind(self, lab_id):
        if lab_id not in self.labs:
            raise NotAdmitted("unknown proposal lab")
        return ProposalSession(self, lab_id)

    def _rows(self, lab_id):
        return [row for row in self._events() if row["event"]["body"].get("lab_id") == lab_id]

    def context(self, lab_id):
        self.grant.check(self.run["run_id"], self.problem.oracle_id, self.solve_budget, self.labs)
        self.labs[lab_id].check(self.run["run_id"])
        rows = self._rows(lab_id)
        used = sum(row["event"]["type"] == "proposal.reserved" for row in rows)
        return {"schema": SCHEMA, "status": "ready", "lab_id": lab_id, "prompt": PROMPT,
                "problem": self.problem.wire(), "budget": self.solve_budget, "used": used,
                # Bound the prompt. Other labs and all comparator answers are excluded.
                "feedback": [deepcopy(row["event"]["body"]["receipt"]) for row in rows
                             if row["event"]["type"] == "proposal.finished"][-16:]}

    def report(self, *, sa, human):
        """Operator-only table; comparator evidence is never stored in lab context.

        SA must use this same oracle and slot budget. An unfinished lab is shown
        as incomplete, never advertised as an equal-solves comparison.
        """
        for baseline, label in ((sa, "sa"), (human, "human")):
            fields = {"oracle_id", "J", "wire_mm", "evidence_ref"} | ({"solves"} if label == "sa" else set())
            if type(baseline) is not dict or set(baseline) != fields:
                raise ValueError("invalid comparator evidence")
            if baseline["oracle_id"] != self.problem.oracle_id:
                raise ValueError("comparator objective mismatch")
            public_name(baseline["evidence_ref"])
            _metrics(baseline)
        if type(sa["solves"]) is not int or sa["solves"] != self.solve_budget:
            raise ValueError("SA solve budget mismatch")
        rows = []
        for lab_id in self.labs:
            events = self._rows(lab_id)
            used = sum(row["event"]["type"] == "proposal.reserved" for row in events)
            receipts = [row["event"]["body"]["receipt"] for row in events
                        if row["event"]["type"] == "proposal.finished"]
            legal = [receipt for receipt in receipts if receipt["status"] == "evaluated"]
            best = min(legal, key=lambda row: (row["J"], row["wire_mm"], row["request_id"]), default=None)
            rows.append({"lab_id": lab_id, "solves": used, "budget": self.solve_budget,
                         "complete": used == self.solve_budget and len(receipts) == used,
                         "best_J": best["J"] if best else None,
                         "wire_at_best_J_mm": best["wire_mm"] if best else None,
                         "best_request_id": best["request_id"] if best else None,
                         "delta_wire_sa_mm": best["wire_mm"] - sa["wire_mm"] if best else None,
                         "delta_wire_human_mm": best["wire_mm"] - human["wire_mm"] if best else None,
                         "delta_J_sa": best["J"] - sa["J"] if best else None,
                         "delta_J_human": best["J"] - human["J"] if best else None})
        return {"schema": SCHEMA, "claim": CLAIM, "oracle_id": self.problem.oracle_id,
                "rows": rows, "sa": deepcopy(sa), "human": deepcopy(human)}


def _metrics(value):
    for field in ("J", "wire_mm"):
        number = value[field]
        if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
            raise ValueError("invalid oracle metrics")


class BudgetedProposalOracle:
    """Durable admission/counting at the oracle boundary, before legality.

    The backend contract is one evaluation per call, no internal retries/solves.
    Exceptions, illegality, cancellation and crash reservations are never refunded.
    """
    def __init__(self, harness, lab, backend):
        self.harness, self.lab, self.backend = harness, lab, backend

    async def submit(self, *, request_id, positions):
        from .capabilities import PROPOSAL_INPUTS
        arguments = {"request_id": request_id, "positions": positions}
        if not Draft202012Validator(PROPOSAL_INPUTS["submit"]).is_valid(arguments):
            raise ValueError("invalid proposal input")
        check_caps(arguments)
        validate_run_id(request_id)
        positions = deepcopy(positions)
        h, lab = self.harness, self.lab
        # Reject simultaneous calls rather than block the event loop on flock.
        try:
            with lock(h.root / (h.run["run_id"] + ".proposal-" + lab.lab_id + ".lock"), blocking=False):
                return await self._submit(request_id, positions)
        except LockBusy:
            return {"schema": SCHEMA, "status": "refused", "error": {"code": "lab_busy"}}

    async def _submit(self, request_id, positions):
        h, lab = self.harness, self.lab
        h.grant.check(h.run["run_id"], h.problem.oracle_id, h.solve_budget, h.labs)
        lab.check(h.run["run_id"])
        rows = h._rows(lab.lab_id)
        reservations = [row for row in rows if row["event"]["type"] == "proposal.reserved"]
        previous = next((row for row in reservations if row["event"]["body"]["request_id"] == request_id), None)
        if previous:
            if previous["event"]["body"]["positions"] != positions:
                raise ValueError("proposal idempotency conflict")
            finished = next((row for row in rows if row["event"]["type"] == "proposal.finished"
                             and row["event"]["body"]["request_id"] == request_id), None)
            return deepcopy(finished["event"]["body"]["receipt"]) if finished else {
                "schema": SCHEMA, "status": "interrupted", "request_id": request_id,
                "charged": True, "reservation_hash": previous["hash"]}
        if h.stop_file.exists():
            return {"schema": SCHEMA, "status": "refused", "error": {"code": "stopped"}}
        if len(reservations) >= h.solve_budget:
            return {"schema": SCHEMA, "status": "refused", "error": {"code": "solve_budget"}}
        event_id = digest({"lab_id": lab.lab_id, "request_id": request_id})
        try:
            reserved = h.ledger.append("proposal.reserved", {
                "lab_id": lab.lab_id, "request_id": request_id, "positions": positions,
                "slot": len(reservations) + 1, "budget": h.solve_budget,
                "grant_ref": h.grant.reference, "oracle_id": h.problem.oracle_id},
                event_id="reserve-" + event_id, guard=self._reserve)
        except _Stopped:
            return {"schema": SCHEMA, "status": "refused", "error": {"code": "stopped"}}
        receipt = {"schema": SCHEMA, "status": "oracle_error", "lab_id": lab.lab_id,
                   "request_id": request_id, "charged": True, "slot": len(reservations) + 1,
                   "budget": h.solve_budget, "reservation_hash": reserved["hash"]}
        try:
            async with asyncio.timeout(h.timeout):
                result = await self._evaluate(positions, reserved["event"]["body"]["admission_hash"])
            if not h.stop_file.exists():
                h.grant.check(h.run["run_id"], h.problem.oracle_id, h.solve_budget, h.labs)
            if h.stop_file.exists():
                receipt["status"] = "stopped"
            elif (type(result) is not dict or set(result) != {"legal", "J", "wire_mm"}
                    or type(result["legal"]) is not bool):
                raise ValueError("invalid oracle response")
            elif result["legal"]:
                _metrics(result)
                receipt.update(status="evaluated", J=result["J"], wire_mm=result["wire_mm"])
            else:
                receipt["status"] = "illegal"
        except asyncio.CancelledError:
            receipt["status"] = "cancelled"
            raise
        except _Stopped:
            receipt["status"] = "stopped"
        except _AdmissionRevoked:
            receipt["status"] = "admission_revoked"
        except NotAdmitted:
            receipt["status"] = "grant_expired"
        except TimeoutError:
            receipt["status"] = "timeout"
        except Exception:
            # Adapter diagnostics and rejected values cannot enter lab feedback.
            receipt["status"] = "oracle_error"
        finally:
            h.ledger.append("proposal.finished", {"lab_id": lab.lab_id, "request_id": request_id,
                            "receipt": receipt}, event_id="finish-" + event_id, guard=self._commit)
        return receipt

    @contextmanager
    def _reserve(self, body):
        h, lab = self.harness, self.lab
        # Ledger -> registry, never the reverse. Publication uses only registry.
        # Validate after BOTH waits; keep the policy stable through the append.
        with lock(lab.admission.registry_lock_path):
            h.grant.check(h.run["run_id"], h.problem.oracle_id, h.solve_budget, h.labs)
            admission = lab.check(h.run["run_id"])
            if h.stop_file.exists():
                raise _Stopped()
            body.update(model_id=admission.model_id, provider=admission.provider,
                        payer=admission.payer, admission_hash=admission.policy_sha256)
            yield

    @contextmanager
    def _commit(self, body):
        # This runs inside the final append lock, not before its potentially
        # blocking acquisition. Do not rewrite genuine errors or prior charges.
        receipt = body["receipt"]
        if receipt["status"] in {"evaluated", "illegal"} and self.harness.stop_file.exists():
            receipt["status"] = "stopped"
            receipt.pop("J", None)
            receipt.pop("wire_mm", None)
        yield

    async def _evaluate(self, positions, admission_hash):
        h = self.harness
        async def start():
            # Recheck when the task actually starts, after scheduling and lock
            # waits. A prior reservation remains charged if authority was lost.
            with lock(h.ledger.lock_path), lock(self.lab.admission.registry_lock_path):
                h.grant.check(h.run["run_id"], h.problem.oracle_id, h.solve_budget, h.labs)
                try:
                    current = self.lab.check(h.run["run_id"])
                    if current.policy_sha256 != admission_hash:
                        raise NotAdmitted("proposal admission changed after reservation")
                except NotAdmitted:
                    raise _AdmissionRevoked() from None
                if h.stop_file.exists():
                    raise _Stopped()
            if len(positions) != len(h.problem.chiplets):
                return {"legal": False, "J": None, "wire_mm": None}
            return await self.backend.evaluate(positions, stop_file=h.stop_file)
        # The adapter owns/reaps any child processes in its cancellation finally.
        task = asyncio.create_task(start())
        try:
            while not task.done():
                h.grant.check(h.run["run_id"], h.problem.oracle_id, h.solve_budget, h.labs)
                if h.stop_file.exists():
                    return None
                await asyncio.wait({task}, timeout=0.02)
            return task.result()
        finally:
            if not task.done():
                task.cancel()
            async def drain():
                await asyncio.gather(task, return_exceptions=True)
            _, cancelled = await _finish(asyncio.create_task(drain()))
            if cancelled:
                raise asyncio.CancelledError


@dataclass(frozen=True)
class ProposalSession:
    harness: ProposalHarness
    lab_id: str


async def execute(command, context, **arguments):
    admit("sentilab_proposal_" + command, arguments)
    session = getattr(context, "proposal_session", None)
    if type(session) is not ProposalSession:
        return {"schema": SCHEMA, "status": "blocked", "error": {"code": "not_configured"}}
    if command == "context":
        result = session.harness.context(session.lab_id)
    else:
        result = await session.harness.oracles[session.lab_id].submit(**arguments)
    # Fresh and replayed signed receipts must have identical transport bytes.
    return json.loads(canonical(result))
