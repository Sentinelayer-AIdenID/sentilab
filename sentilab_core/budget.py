"""Durable reservation before compute, including failures and interrupted jobs."""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import json
import math
import os
from pathlib import Path
import time

from .ledger import atomic_json, lock


class BudgetHalt(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    development: bool = True
    evals_per_hour: int = 600
    cpu_seconds_per_hour: float = 600
    evals_per_run: int = 200
    total_evals: int = 2000
    total_cpu_seconds: float = 1800
    solve_cpu_seconds: float = 15

    def __post_init__(self):
        if type(self.development) is not bool:
            raise ValueError("development must be boolean")
        for name, maximum in (("evals_per_hour", 600), ("evals_per_run", 200), ("total_evals", 2000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be an integer from 1 through {maximum}")
        for name, maximum in (("cpu_seconds_per_hour", 600), ("total_cpu_seconds", 1800),
                              ("solve_cpu_seconds", 60)):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(value) or not 0 < value <= maximum):
                raise ValueError(f"invalid {name}")


class Budget:
    def __init__(self, root, limits=Limits(), *, clock=time.time, deadline=None):
        self.root, self.limits, self.clock = Path(root), limits, clock
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "budget.json"
        self.stop_file = self.root / "STOP"
        self.deadline = deadline
        with lock(self.root / "budget.lock"):
            if self.path.exists():
                state = self._read()
                if state["limits"] != asdict(limits) or state["deadline"] != deadline:
                    raise ValueError("budget policy is immutable for this service allocation")
            else:
                atomic_json(self.path, {"limits": asdict(limits), "deadline": deadline,
                                        "last_clock": clock(), "reservations": []})

    def _read(self):
        state = json.loads(self.path.read_text())
        state["limits"].setdefault("development", True)
        return state

    def check_stop(self):
        if self.stop_file.exists():
            raise BudgetHalt("STOP file")
        if self.deadline is not None and self.clock() >= self.deadline:
            raise BudgetHalt("elapsed deadline")

    def snapshot(self, run_id=None):
        with lock(self.root / "budget.lock", shared=True):
            records = self._read()["reservations"]
        if run_id is not None:
            records = [r for r in records if r["run_id"] == run_id]
        return {"solves": len(records), "cpu_charged_s": sum(r["ceiling_s"] for r in records),
                "cpu_actual_s": sum(r.get("actual_cpu_s") or 0 for r in records),
                "cpu_unmeasured": sum(r.get("actual_cpu_s") is None for r in records),
                "unsettled": sum(r["status"] == "reserved" for r in records)}

    @contextmanager
    def reserve(self, run_id, operation_id):
        """Lease stays open in the worker too, so an orphan blocks a second solve.

        CPU ceilings are charged in full, even when actual CPU is lower. A
        reservation without a result survives a crash and can never be executed
        again under the same operation id.
        """
        with open(self.root / "solve.lock", "a+b") as lease:
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BudgetHalt("concurrent solve") from exc
            try:
                with lock(self.root / "budget.lock"):
                    self.check_stop()
                    state = self._read()
                    now = self.clock()
                    if now < state["last_clock"]:
                        raise BudgetHalt("clock moved backwards")
                    records = state["reservations"]
                    if any(r["operation_id"] == operation_id for r in records):
                        raise BudgetHalt("operation already reserved")
                    # A reservation counts until an hour after its latest possible
                    # completion, not merely an hour after it started.
                    recent = [r for r in records if r["at"] + r["ceiling_s"] > now - 3600]
                    run = [r for r in records if r["run_id"] == run_id]
                    solve_limits = [(recent, self.limits.evals_per_hour, "hour solve limit"),
                                    (run, self.limits.evals_per_run, "run solve limit")]
                    if self.limits.development:
                        solve_limits.append((records, self.limits.total_evals, "total solve limit"))
                    for group, maximum, reason in solve_limits:
                        if len(group) >= maximum:
                            raise BudgetHalt(reason)
                    ceiling = self.limits.solve_cpu_seconds
                    cpu_limits = [(recent, self.limits.cpu_seconds_per_hour, "hour CPU limit")]
                    if self.limits.development:
                        cpu_limits.append((records, self.limits.total_cpu_seconds, "total CPU limit"))
                    for group, maximum, reason in cpu_limits:
                        if sum(r["ceiling_s"] for r in group) + ceiling > maximum:
                            raise BudgetHalt(reason)
                    if self.deadline is not None and now + ceiling > self.deadline:
                        raise BudgetHalt("elapsed deadline")
                    record = {"run_id": run_id, "operation_id": operation_id, "at": now,
                              "ceiling_s": ceiling, "status": "reserved"}
                    records.append(record)
                    state["last_clock"] = now
                    atomic_json(self.path, state)
                os.set_inheritable(lease.fileno(), True)
                yield {**record, "lease_fd": lease.fileno()}
            finally:
                # close rather than LOCK_UN: inherited worker descriptors must
                # keep the lease if a caller is interrupted.
                pass

    def settle(self, operation_id, *, actual_cpu_s, success):
        if actual_cpu_s is not None and (isinstance(actual_cpu_s, bool) or not isinstance(actual_cpu_s, (int, float)) or
                not math.isfinite(actual_cpu_s) or actual_cpu_s < 0):
            raise ValueError("invalid CPU measurement")
        with lock(self.root / "budget.lock"):
            state = self._read()
            record = next(r for r in state["reservations"] if r["operation_id"] == operation_id)
            if record["status"] != "reserved":
                raise ValueError("operation already settled")
            if actual_cpu_s is not None and actual_cpu_s > record["ceiling_s"]:
                record.update(actual_cpu_s=actual_cpu_s, status="overrun")
                atomic_json(self.path, state)
                self.stop_file.touch()
                raise BudgetHalt("CPU ceiling exceeded")
            record.update(actual_cpu_s=actual_cpu_s, status="success" if success else "failed")
            atomic_json(self.path, state)

    def amend_deadline(self, deadline, *, reason):
        """Service-owner operation; not exposed to labs, CLI requests or MCP tools.

        Resource limits and every prior reservation survive a clock amendment.
        """
        if not isinstance(deadline, (int, float)) or not math.isfinite(deadline) or not reason:
            raise ValueError("invalid clock amendment")
        with lock(self.root / "budget.lock"):
            state = self._read()
            state.setdefault("clock_amendments", []).append(
                {"from": state["deadline"], "to": deadline, "reason": reason, "at": self.clock()})
            state["deadline"] = deadline
            atomic_json(self.path, state)
            self.deadline = deadline
