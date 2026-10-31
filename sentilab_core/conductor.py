"""Finite, renewable AI-off runs. The signed ledger is the run/arm state."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import random
import time
import uuid

from sundai_controller.controller import Chiplet, Design
from sundai_controller.experiment import LANE_IDS, OPERATORS, _candidate, _choose_ucb1, _signal_portfolio

from .budget import Budget, BudgetHalt, Limits
from .envelope import validate_run_id
from .gate import AcceptanceGate
from .ledger import Ledger, atomic_json, lock
from .oracle import FreshProcessOracle
from .projection import board, project

LABELS = {"ai_mode": "AI off", "margin_label": "provisional margin",
          "scope": "diagnostic integration; no scientific acceptance"}
TERMINAL = {"accepted", "non_improving_current", "within_margin", "rejected_schema",
            "rejected_constraints", "failed_run", "reproduction_failed", "cancelled", "inconclusive"}


class StopSignal:
    def __init__(self, path, cancel_event):
        self.path, self.cancel_event = path, cancel_event

    def exists(self):
        return self.path.exists() or self.cancel_event is not None and self.cancel_event.is_set()


def design_record(design):
    return json.loads(json.dumps(asdict(design)))


def load_design(record):
    return Design(record["width_mm"], record["height_mm"], record["gap_mm"],
                  tuple(Chiplet(**c) for c in record["chiplets"]),
                  tuple(tuple(p) for p in record["positions"]))


class Conductor:
    def __init__(self, root, *, signer, public_keys, limits=Limits(), deadline=None,
                 fixture="ascend910", margin=0.32, grid=16, seed=11, oracle=None, cancel_event=None,
                 replay_labs=None, enable_replay_labs=False, isolated_labs=None):
        if type(enable_replay_labs) is not bool:
            raise ValueError("replay flag must be a boolean")
        if replay_labs is not None or enable_replay_labs:
            from .dispatch import Dispatcher
            from .labs import ReplayLab
            if not enable_replay_labs or type(replay_labs) is not Dispatcher:
                raise ValueError("replay labs require the explicit fixture flag and dispatcher")
            if any(type(r.lab) is not ReplayLab for r in replay_labs.registrations.values()):
                raise ValueError("only canned ReplayLab adapters are enabled")
            if oracle is None or isinstance(oracle, FreshProcessOracle):
                raise ValueError("replay labs require an injected CPU fixture oracle")
        if isolated_labs is not None:
            from .leads import IsolatedLabs
            if replay_labs is not None:
                raise ValueError("choose replay or isolated labs")
            if type(isolated_labs) is not IsolatedLabs or not isolated_labs.stand_in_only:
                raise ValueError("only deterministic isolated stand-ins are enabled")
            if oracle is None or isinstance(oracle, FreshProcessOracle):
                raise ValueError("isolated stand-ins require an injected CPU fixture oracle")
        self.isolated_labs = isolated_labs
        self.replay_labs = replay_labs
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if limits.evals_per_run < 2:
            raise ValueError("a run needs at least two solves for reproduction")
        if type(seed) is not int or not 0 <= seed <= 1000000:
            raise ValueError("seed must be an integer from 0 through 1000000")
        self.signer, self.public_keys = signer, public_keys
        self.budget = Budget(root, limits, deadline=deadline)
        self.cancel_event = cancel_event
        self.stop_signal = StopSignal(self.budget.stop_file, cancel_event)
        self.oracle = oracle if oracle is not None else FreshProcessOracle(fixture=fixture, grid=grid)
        self.gate = AcceptanceGate(margin=margin)
        self.config = {"fixture": fixture, "margin": margin, "grid": grid, "seed": seed,
                       "task_id": self.oracle.problem_hash, "wire_cap_mm": self.oracle.wire_cap_mm,
                       "solver_id": self.oracle.solver_version, "reproduction_tolerance": 0.001,
                       "initial": design_record(self.oracle.initial)}
        if replay_labs is not None:
            self.config["replay_labs"] = replay_labs.describe()
        if isolated_labs is not None:
            self.config["isolated_labs"] = isolated_labs.describe()
        self.ledger = None
        self.meta = None

    def check_stop(self):
        if getattr(self, "cancel_event", None) is not None and self.cancel_event.is_set():
            raise BudgetHalt("service shutdown")
        self.budget.check_stop()

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
        if self.replay_labs is not None or self.isolated_labs is not None:
            records = [e["event"]["body"].get("record", {}) for e in self.ledger.read()["prefix"]]
            if self.replay_labs is not None:
                self.replay_labs.restore(records)
            self._lab_record_index = sum(r.get("type", "").startswith("lab.") for r in records)
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

    def _lab_record(self, record):
        node = self.run_id + f":lab-record-{self._lab_record_index}"
        envelope = self.emit("node.create", {"id": node, "kind": "source", "record": record}, node)
        self._lab_record_index += 1
        return envelope

    def _isolated_records(self):
        records = []
        for envelope in self.ledger.read()["prefix"]:
            body = envelope["event"]["body"]
            if envelope["event"]["type"] != "node.create":
                continue
            record = dict(body.get("record", {}))
            if body.get("kind") in ("candidate", "measurement"):
                record["type"] = body["kind"]
            records.append(record)
        return records

    async def _isolated_propose(self, index):
        from .labs import materialize
        lab_ids = list(self.isolated_labs.labs)
        lab_id = lab_ids[(index - 1) % len(lab_ids)]
        result = await self.isolated_labs.propose(
            lab_id, self.meta["run"], self.config["initial"], self._isolated_records(),
            (index - 1) // len(lab_ids), sink=self._lab_record)
        self.check_stop()
        candidate, missing = self.oracle.initial, result.reason
        if result.message is not None:
            try:
                candidate = materialize(result.message, self.oracle.initial)
            except ValueError:
                missing = "catalog_mismatch"
        self._lab_record({"type": "lab.proposal", "message": result.message,
                          "provenance": result.provenance, "missing": missing})
        return candidate, lab_id, result.provenance, missing

    async def _isolated_advice(self, proposal, evidence):
        candidate_hash = next(e["hash"] for e in self.ledger.read()["prefix"]
                              if e["event"]["body"].get("id") == proposal["node"])
        lab_id = proposal["lane"]
        result = await self.isolated_labs.review(
            lab_id, self.meta["run"], proposal["design"], evidence, candidate_hash,
            (proposal["index"] - 1) // len(self.isolated_labs.labs),
            records=self._isolated_records(), sink=self._lab_record)
        self.check_stop()
        if result.reason != "already_attempted":
            self._lab_record({"type": "lab.review", "message": result.message,
                              "provenance": result.provenance, "missing": result.reason})

    async def _lab_propose(self, index):
        from .envelope import canonical
        from .labs import Request, materialize
        lab_ids = list(self.replay_labs.registrations)
        lab_id = lab_ids[(index - 1) % len(lab_ids)]
        request = Request(context=canonical({"initial": self.config["initial"]}), ordinal=(index - 1) // len(lab_ids))
        response = await self.replay_labs.call(lab_id, "propose", request, sink=self._lab_record)
        self.check_stop()
        if response is None:
            return None
        try:
            candidate = materialize(response, self.oracle.initial)
        except ValueError:
            self._lab_record({"type": "lab.refusal", "lab_id": lab_id, "reason": "catalog_mismatch"})
            return None
        self._lab_record({"type": "lab.proposal", "message": response})
        return candidate, lab_id, "replay", self.oracle.initial.hash

    async def _lab_advice(self, candidate_envelope, proposal):
        from .envelope import canonical
        from .labs import Request
        author = self.replay_labs.registrations[proposal["lane"]]
        reviewers = [r for r in self.replay_labs.registrations.values() if r.family != author.family]
        if not reviewers:
            self._lab_record({"type": "lab.refusal", "lab_id": author.lab_id, "reason": "no_independent_reviewer"})
            return
        # Rotating cross-family assignment; each of four labs gets one review per cycle.
        lab_ids = list(self.replay_labs.registrations)
        next_id = lab_ids[(lab_ids.index(author.lab_id) + 1) % len(lab_ids)]
        reviewer = next((r for r in reviewers if r.lab_id == next_id), reviewers[0])
        request = Request(context=canonical({"design": proposal["design"]}),
                          ordinal=(proposal["index"] - 1) // len(lab_ids),
                          target_hash=candidate_envelope["hash"], target_lab=author.lab_id)
        review = await self.replay_labs.call(reviewer.lab_id, "review", request, sink=self._lab_record)
        self.check_stop()
        if review is None:
            return
        envelope = self._lab_record({"type": "lab.review", "message": review})
        repair = await self.replay_labs.call(author.lab_id, "repair",
                                             replace(request, review_hash=envelope["hash"],
                                                     context=canonical({"review": review})),
                                             sink=self._lab_record)
        self.check_stop()
        if repair is not None:
            self._lab_record({"type": "lab.repair", "message": repair})

    async def _measurement(self, candidate, proposal, phase):
        operation = proposal["node"] + ":" + phase
        measurement_id = operation + ":measurement"
        for entry in self.ledger.read()["prefix"]:
            if entry["event"]["event_id"] == self.run_id + ":" + operation:
                return entry["event"]["body"]["record"]
        self.check_stop()
        try:
            with self.budget.reserve(self.run_id, operation) as reservation:
                self.emit("node.create", {"id": operation + ":reservation", "kind": "source",
                                          "record": {k: v for k, v in reservation.items() if k != "lease_fd"}},
                          operation + ":reservation")
                try:
                    result, usage = await self.oracle.measure(candidate, reservation, self.stop_signal)
                    self.budget.settle(operation, actual_cpu_s=usage["cpu_s"], success=True)
                except BaseException:
                    # The full reservation remains charged when there is no
                    # completed process-tree CPU measurement.
                    if self.budget._read()["reservations"][-1]["status"] == "reserved":
                        self.budget.settle(operation, actual_cpu_s=None, success=False)
                    raise
        except BudgetHalt as exc:
            if str(exc) != "operation already reserved":
                raise
            return {"success": False, "error": "interrupted reserved solve; no automatic retry"}
        except Exception as exc:
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise BudgetHalt("service shutdown") from exc
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
        values = {"J": {"value": record["j"], "unit": "C"},
                  "W": {"value": record["wire_mm"], "metric_id": "weighted-manhattan-mm"},
                  "scenario_id": "nominal", "artifact_hashes": list(record["input_hashes"].values())}
        self.emit("node.create", {"id": measurement_id, "kind": "measurement", "semantics": semantics,
                                  "record": record}, operation, values)
        return record

    async def tick(self):
        self.check_stop()
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
            lab_proposal = await self._lab_propose(index) if self.replay_labs is not None and index else None
            isolated = None
            if self.isolated_labs is not None and index:
                isolated = await self._isolated_propose(index)
                candidate, lane, provenance, missing = isolated
                operator, parent_hash = "stand-in-lead", self.oracle.initial.hash
            else:
                candidate, lane, operator, parent_hash = lab_proposal or self._propose(index, prefix)
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
            if isolated is not None:
                proposal["originator"] = provenance
                proposal["missing"] = missing
            geometry = [{"id": c.id, "xLL": xy[0], "yLL": xy[1], "w": c.width_mm,
                         "h": c.height_mm, "layer": 0} for c, xy in zip(candidate.chiplets, candidate.positions)]
            candidate_envelope = self.emit("node.create", {"id": node, "kind": "candidate", "record": proposal}, node,
                                           {"geometry": geometry, "units": "mm", "scenario_id": "nominal"})
            if lab_proposal is not None:
                await self._lab_advice(candidate_envelope, proposal)
        node = proposal["node"]
        if proposal.get("missing") is not None:
            self._transition(node, "cancelled", {"reason": proposal["missing"], "outcome": "inconclusive",
                             "missing_data_policy": self.isolated_labs.readiness.missing_data_policy})
            return self.snapshot()
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
        if self.isolated_labs is not None and proposal.get("originator") is not None:
            await self._isolated_advice(proposal, [evaluation, reproduction])
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
        self.check_stop()
        self.ledger.append_gate(self.gate, node, event_id=self.run_id + ":" + node + ":gate")
        return self.snapshot()

    def finish(self, reason):
        self.emit("node.create", {"id": self.run_id + ":halt", "kind": "source",
                                  "record": {"reason": reason, "spend": self.budget.snapshot(self.run_id)}}, "halt")
        self.meta["status"] = "stopped" if "STOP" in reason else "finished"
        self.meta["reason"] = reason
        atomic_json(self.root / f"{self.run_id}.meta.json", self.meta)

    async def run(self, *, run_id=None, duration=600, interval=15, renew=False, max_ticks=None):
        if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or
                isinstance(interval, bool) or not isinstance(interval, (int, float)) or
                not 0 < duration <= 86400 or not 0 <= interval <= 3600):
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
                        if reason == "service shutdown":
                            break
                        if reason == "run solve limit" and renew:
                            self.finish(reason)
                            self.open_run(uuid.uuid4().hex)
                            continue
                        if reason.startswith("hour ") and renew:
                            self.emit("node.create", {"id": self.run_id + ":wait-" + str(self.budget.snapshot()["solves"]),
                                                      "kind": "source", "record": {"reason": reason,
                                                                                   "spend": self.budget.snapshot(self.run_id)}},
                                      "wait-" + str(self.budget.snapshot()["solves"]))
                            await asyncio.sleep(min(1, max(0, deadline - time.monotonic())))
                            continue
                        self.finish(reason)
                        break
                    if max_ticks is not None and ticks >= max_ticks:
                        break
                    until = min(deadline, time.monotonic() + interval)
                    while time.monotonic() < until:
                        self.check_stop()
                        await asyncio.sleep(min(0.1, until - time.monotonic()))
                else:
                    self.finish("duration elapsed")
            except BudgetHalt as exc:
                if str(exc) != "service shutdown":
                    self.finish(str(exc))
            finally:
                # Keep ownership until cleanup finishes, even if EOF/cancel
                # arrives during normal cleanup or cancellation is repeated.
                cleanup = asyncio.create_task(self.oracle.aclose())
                cancelled = None
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError as exc:
                        cancelled = exc
                cleanup.result()  # observe failures, including self-cancellation
                if cancelled is not None:
                    raise cancelled
            return self.snapshot()


if __name__ == "__main__":
    from sentilab_cli.__main__ import main
    main(conductor=True)
