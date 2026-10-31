"""Finite, renewable AI-off runs. The signed ledger is the run/arm state."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import math
from pathlib import Path
import random
import time
import uuid

from sundai_controller.controller import Chiplet, Design
from sundai_controller.experiment import LANE_IDS, OPERATORS, _candidate, _choose_ucb1, _signal_portfolio

from .budget import Budget, BudgetHalt, Limits
from .envelope import digest, validate_run_id
from .gate import AcceptanceGate
from .ledger import Ledger, atomic_json, lock
from .oracle import FreshProcessOracle
from .projection import board, project

LABELS = {"ai_mode": "AI off", "margin_label": "provisional margin",
          "scope": "diagnostic integration; no scientific acceptance"}
TERMINAL = {"accepted", "non_improving_current", "within_margin", "rejected_schema",
            "rejected_constraints", "failed_run", "reproduction_failed", "cancelled", "inconclusive"}


def design_record(design):
    return json.loads(json.dumps(asdict(design)))


def load_design(record):
    return Design(record["width_mm"], record["height_mm"], record["gap_mm"],
                  tuple(Chiplet(**c) for c in record["chiplets"]),
                  tuple(tuple(p) for p in record["positions"]))


class Conductor:
    def __init__(self, root, *, signer, public_keys, limits=Limits(), deadline=None,
                 fixture="ascend910", margin=0.32, grid=16, seed=11, oracle=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.signer, self.public_keys = signer, public_keys
        self.budget = Budget(root, limits, deadline=deadline)
        self.oracle = oracle if oracle is not None else FreshProcessOracle(fixture=fixture, grid=grid)
        self.gate = AcceptanceGate(margin=margin)
        self.config = {"fixture": fixture, "margin": margin, "grid": grid, "seed": seed,
                       "task_id": self.oracle.problem_hash, "wire_cap_mm": self.oracle.wire_cap_mm,
                       "solver_id": self.oracle.solver_version, "reproduction_tolerance": 0.001,
                       "initial": design_record(self.oracle.initial)}
        self.ledger = None
        self.meta = None

    def open_run(self, run_id=None):
        if run_id is None:
            for path in sorted(self.root.glob("*.meta.json"), reverse=True):
                meta = json.loads(path.read_text())
                if meta["status"] == "running":
                    run_id = meta["run"]["run_id"]
                    break
        run_id = run_id or uuid.uuid4().hex
        validate_run_id(run_id)
        path = self.root / f"{run_id}.meta.json"
        run = {"run_id": run_id, "arm": "live", "family": self.config["fixture"],
               "seed": self.config["seed"], "ticket_id": "d72c9769"}
        if path.exists():
            meta = json.loads(path.read_text())
            if meta["config"] != self.config:
                raise ValueError("run fixture, margin, task and solver are immutable")
            self.meta = meta
        else:
            self.meta = {"run": run, "config": self.config, "status": "running", **LABELS}
            atomic_json(path, self.meta)
        self.ledger = Ledger(self.root, run, signer=self.signer, public_keys=self.public_keys)
        self.emit("node.create", {"id": run_id + ":run", "kind": "source",
                                  "record": self.config}, "run")
        return run_id

    @property
    def run_id(self):
        return self.meta["run"]["run_id"]

    def emit(self, event_type, body, operation, values=None):
        return self.ledger.append(event_type, {**body, **LABELS},
                                  event_id=self.run_id + ":" + operation, values=values)

    def snapshot(self):
        state = self.ledger.read()
        projection = project(state["prefix"])
        if projection["rejected"]:
            raise ValueError("contract projection rejected core events")
        return {"run_id": self.run_id, "status": self.meta["status"], "seq": state["last_seq"],
                "head_hash": state["head_hash"], "projection": projection,
                "board": board(state["prefix"], projection), "spend": self.budget.snapshot(self.run_id),
                "error": state["error"], **LABELS}

    def _propose(self, index, prefix):
        """The existing lane operators, deterministic under recorded run/index.

        Arms learn from all valid measurements, including board losers. The SA
        walk remains separate from robust board admission.
        """
        initial = self.oracle.initial
        if index == 0:
            return initial, "baseline", "initial", initial.hash
        lane = LANE_IDS[(index - 1) % len(LANE_IDS)]
        rng = random.Random(self.config["seed"] + 7919 * index)
        candidates = {e["event"]["body"]["id"]: e["event"]["body"]["record"] for e in prefix
                      if e["event"]["type"] == "node.create" and e["event"]["body"].get("kind") == "candidate"}
        observations = []
        for e in prefix:
            body = e["event"]["body"]
            record = body.get("record", {})
            if body.get("kind") == "measurement" and record.get("phase") == "evaluate":
                proposal = candidates[record["candidate_node"]]
                if proposal["lane"] in ("baseline", lane):
                    observations.append((proposal, record))
        parent, best_j, current_j = initial, None, None
        best_design, counts, rewards = initial, dict.fromkeys(OPERATORS, 0), dict.fromkeys(OPERATORS, 0.0)
        stagnation, improved = 0, False
        for proposal, measured in observations:
            candidate, j = load_design(proposal["design"]), measured["j"]
            improvement = 0 if best_j is None else max(0, best_j - j)
            improved = best_j is None or j < best_j
            if proposal["operator"] in counts:
                counts[proposal["operator"]] += 1
                rewards[proposal["operator"]] += improvement
            if improved:
                best_design, best_j, stagnation = candidate, j, 0
            else:
                stagnation += 1
            walk_rng = random.Random(self.config["seed"] + 104729 * proposal["index"])
            if current_j is None or j < current_j or walk_rng.random() < math.exp(min(0, (current_j - j) / 0.5)):
                parent, current_j = candidate, j
        if lane == "random":
            operator, parent = rng.choice(OPERATORS), best_design
        elif lane == "simulated_annealing":
            operator = rng.choices(OPERATORS, (7, 2, 1))[0]
        elif lane == "ucb1":
            operator, parent = _choose_ucb1(counts, rewards, rng), best_design
        else:
            operator, _ = _signal_portfolio({"stagnation": stagnation, "improved_last": improved,
                                             "evaluations_remaining": self.budget.limits.evals_per_run - index * 2})
            parent = best_design
        candidate, _, _ = _candidate(parent, operator, rng, self.oracle)
        return candidate, lane, operator, parent.hash

    def _transition(self, node, to, record=None):
        body = {"node": node, "to": to}
        if record is not None:
            body["record"] = record
        return self.emit("lifecycle.transition", body, node + ":" + to)

    async def _measurement(self, candidate, proposal, phase):
        operation = proposal["node"] + ":" + phase
        measurement_id = operation + ":measurement"
        for entry in self.ledger.read()["prefix"]:
            if entry["event"]["event_id"] == self.run_id + ":" + operation:
                return entry["event"]["body"]["record"]
        self.budget.check_stop()
        try:
            with self.budget.reserve(self.run_id, operation) as reservation:
                self.emit("node.create", {"id": operation + ":reservation", "kind": "source",
                                          "record": {k: v for k, v in reservation.items() if k != "lease_fd"}},
                          operation + ":reservation")
                try:
                    result, usage = await self.oracle.measure(candidate, reservation, self.budget.stop_file)
                    self.budget.settle(operation, actual_cpu_s=usage["cpu_s"], success=True)
                except BaseException:
                    # The full reservation remains charged when there is no
                    # completed process-tree CPU measurement.
                    self.budget.settle(operation, actual_cpu_s=reservation["ceiling_s"], success=False)
                    raise
        except BudgetHalt as exc:
            if str(exc) != "operation already reserved":
                raise
            return {"success": False, "error": "interrupted reserved solve; no automatic retry"}
        except Exception as exc:
            return {"success": False, "error": type(exc).__name__}
        if result.candidate_hash != candidate.hash or result.problem_hash != self.config["task_id"]:
            return {"success": False, "error": "result binding mismatch"}
        record = {"binding": proposal["binding"], "j": result.maximum_temperature_c,
                  "wire_mm": result.wirelength_mm, "process_id": usage["process_id"],
                  "success": result.converged is True, "phase": phase, "candidate_node": proposal["node"],
                  "cpu_s": usage["cpu_s"], "measurement_id": measurement_id,
                  "input_hashes": dict(result.input_sha256)}
        semantics = {"task_contract": self.config["task_id"], "metric_id": "peak-chip-c",
                     "evaluator_version": self.config["solver_id"], "coordinate_frame": "lower-left-mm"}
        values = {"J": {"value": record["j"], "unit": "°C"},
                  "W": {"value": record["wire_mm"], "metric_id": "weighted-manhattan-mm"},
                  "scenario_id": "nominal", "artifact_hashes": list(record["input_hashes"].values())}
        self.emit("node.create", {"id": measurement_id, "kind": "measurement", "semantics": semantics,
                                  "record": record}, operation, values)
        return record

    async def tick(self):
        self.budget.check_stop()
        prefix = self.ledger.read()["prefix"]
        projection = project(prefix)
        candidates = [e["event"]["body"] for e in prefix if e["event"]["type"] == "node.create"
                      and e["event"]["body"].get("kind") == "candidate"]
        pending = next((c for c in candidates if projection["nodes"][c["id"]]["lifecycle"] not in TERMINAL), None)
        if pending:
            proposal = pending["record"]
            candidate = load_design(proposal["design"])
        else:
            if self.budget.snapshot(self.run_id)["solves"] + 2 > self.budget.limits.evals_per_run:
                raise BudgetHalt("run solve limit")
            index = len(candidates)
            candidate, lane, operator, parent_hash = self._propose(index, prefix)
            node = self.run_id + f":candidate-{index}"
            binding = {"candidate_id": candidate.hash, "task_id": self.config["task_id"],
                       "fixture_id": self.config["fixture"], "metric_id": "peak-chip-c",
                       "scenario_id": "nominal", "solver_id": self.config["solver_id"]}
            try:
                centers = self.oracle.centers_for(candidate)
                wire = self.oracle._wirelength_mm(centers)
                geometry_valid = True
            except ValueError:
                geometry_valid, wire = False, None
            proposal = {"node": node, "index": index, "lane": lane, "operator": operator,
                        "parent_hash": parent_hash, "design": design_record(candidate), "binding": binding,
                        "geometry_valid": geometry_valid, "wire_mm": wire}
            geometry = [{"id": c.id, "xLL": xy[0], "yLL": xy[1], "w": c.width_mm,
                         "h": c.height_mm, "layer": 0} for c, xy in zip(candidate.chiplets, candidate.positions)]
            self.emit("node.create", {"id": node, "kind": "candidate", "record": proposal}, node,
                      {"geometry": geometry, "units": "mm", "scenario_id": "nominal"})
        node = proposal["node"]
        if not proposal["geometry_valid"]:
            self._transition(node, "rejected_schema", {"outcome": "invalid_geometry"})
            return self.snapshot()
        self._transition(node, "validated")
        if proposal["wire_mm"] > self.config["wire_cap_mm"]:
            self._transition(node, "rejected_constraints", {"outcome": "wire_cap_exceeded"})
            return self.snapshot()
        self._transition(node, "simulation_pending")
        evaluation = await self._measurement(candidate, proposal, "evaluate")
        if not evaluation["success"]:
            self._transition(node, "failed_run", evaluation)
            return self.snapshot()
        self._transition(node, "evaluated")
        self._transition(node, "reproduction_pending")
        reproduction = await self._measurement(candidate, proposal, "reproduce")
        inputs = {"geometry_valid": proposal["geometry_valid"], "wire_cap_mm": self.config["wire_cap_mm"],
                  "binding": proposal["binding"], "evaluation": evaluation,
                  "reproduction": reproduction, "stopped": False}
        decision = self.gate.decide(**inputs, current=None)
        if decision["outcome"] != "accepted":
            self._transition(node, "reproduction_failed", {"outcome": decision["outcome"]})
            return self.snapshot()
        self.emit("support.add", {"node": node, "set_id": "evaluation-and-reproduction",
                                  "members": [evaluation["measurement_id"], reproduction["measurement_id"]]},
                  node + ":support")
        self.emit("verify.add", {"node": evaluation["measurement_id"], "tier": "replayed",
                                 "evidence": [reproduction["measurement_id"]],
                                 "record": {"label": "same-solver reproduction"}}, node + ":verified")
        self._transition(node, "reproduced")
        self.budget.check_stop()
        self.ledger.append_gate(self.gate, node, event_id=self.run_id + ":" + node + ":gate",
                                stopped=self.budget.stop_file.exists())
        return self.snapshot()

    def finish(self, reason):
        self.emit("node.create", {"id": self.run_id + ":halt", "kind": "source",
                                  "record": {"reason": reason, "spend": self.budget.snapshot(self.run_id)}}, "halt")
        self.meta["status"] = "stopped" if "STOP" in reason else "finished"
        self.meta["reason"] = reason
        atomic_json(self.root / f"{self.run_id}.meta.json", self.meta)

    async def run(self, *, run_id=None, duration=600, interval=15, renew=False, max_ticks=None):
        if not 0 < duration <= 86400 or not 0 <= interval <= 3600:
            raise ValueError("invalid duration or interval")
        deadline = time.monotonic() + duration
        ticks = 0
        with lock(self.root / "owner.lock", blocking=False):
            self.open_run(run_id)
            if self.meta["status"] != "running":
                return self.snapshot()
            try:
                while time.monotonic() < deadline:
                    try:
                        await self.tick()
                        ticks += 1
                    except BudgetHalt as exc:
                        reason = str(exc)
                        if reason == "run solve limit" and renew:
                            self.finish(reason)
                            self.open_run(uuid.uuid4().hex)
                            continue
                        if reason.startswith("hour ") and renew:
                            await asyncio.sleep(min(1, max(0, deadline - time.monotonic())))
                            continue
                        self.finish(reason)
                        break
                    if max_ticks is not None and ticks >= max_ticks:
                        break
                    until = min(deadline, time.monotonic() + interval)
                    while time.monotonic() < until:
                        self.budget.check_stop()
                        await asyncio.sleep(min(0.1, until - time.monotonic()))
                else:
                    self.finish("duration elapsed")
            except BudgetHalt as exc:
                self.finish(str(exc))
            finally:
                await self.oracle.aclose()
            return self.snapshot()


if __name__ == "__main__":
    from sentilab_cli.__main__ import main
    main(conductor=True)
