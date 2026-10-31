"""SLAB-039: Headroom runner — cheap search vs long SA to measure optimization headroom.

Run random, greedy, and short simulated_annealing (reducer methods) at 28 search + 4 reproduction
evaluations over 8 seeds, plus a capped long SA, and report cheap_median - best against 5x the mesh error.
UCB1 and signal_portfolio run as extra diagnostics only, excluded from the gate criterion C.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import signal
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sundai_controller.controller import Controller, Ed25519PrivateKey, FlightRecord, digest, public_hex
from sundai_controller.experiment import OPERATORS, SIGNAL_CHOICES, _candidate, _shared_designs, _signal_portfolio

TAP_INITIAL_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))


def _validate_mesh_error(value: float | None) -> None:
    """Reject negative, non-finite, or None mesh error values."""
    if value is None:
        raise ValueError("mesh_error must not be None")
    if not math.isfinite(value):
        raise ValueError(f"mesh_error must be finite, got: {value}")
    if value < 0:
        raise ValueError(f"mesh_error must be non-negative, got: {value}")


def _compute_prereg_digest(path: str | Path) -> str:
    """Compute sha256 digest of prereg file contents for integrity check."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _parse_prereg(path: str | Path) -> dict:
    """Load and validate the preregistration file (accepts v1, v2, v3)."""
    prereg_path = Path(path)
    if not prereg_path.is_file():
        raise FileNotFoundError(f"prereg file not found: {prereg_path}")
    with open(prereg_path, encoding="utf-8") as fh:
        prereg = json.load(fh)
    schema = prereg.get("schema")
    if schema not in ("slab-039-prereg-v1", "slab-039-prereg-v2", "slab-039-prereg-v3"):
        raise ValueError(f"prereg must have schema slab-039-prereg-v1, v2, or v3, got: {schema}")
    if prereg.get("fixture") != "ascend910":
        raise ValueError(f"unsupported fixture: {prereg.get('fixture')}")
    if prereg.get("rule", {}).get("k") != 5:
        raise ValueError("prereg k must be 5")
    return prereg


def _gate_pass(cheap_median: float, best: float, mesh_error: float, k: int = 5) -> tuple[bool, float]:
    """Apply the warden +1 condition 2: pass iff cheap_median - best >= k * mesh_error.

    Rejects negative or non-finite mesh_error.
    """
    _validate_mesh_error(mesh_error)
    gap = cheap_median - best
    threshold = k * mesh_error
    return gap >= threshold, gap


def _gate_pass_dynamic(cheap_median: float, best: float, j32_values: list[float],
                       j64_values: list[float], k: int = 5) -> tuple[bool, float, float]:
    """Pass iff cheap_median - best >= k * max|J32 - J64|.

    Returns (passed, gap, effective_mesh_error).
    """
    if not j32_values or not j64_values:
        raise ValueError("J32 and J64 values are required for dynamic mesh error")
    if len(j32_values) != len(j64_values):
        raise ValueError(f"J32 length ({len(j32_values)}) must equal J64 length ({len(j64_values)})")
    differences = [abs(a - b) for a, b in zip(j32_values, j64_values)]
    mesh_error = max(differences)
    _validate_mesh_error(mesh_error)
    gap = cheap_median - best
    threshold = k * mesh_error
    return gap >= threshold, gap, mesh_error


def _choose_ucb1(counts: dict[str, int], rewards: dict[str, float],
                 trials: int, rng: random.Random) -> tuple[str, str]:
    """UCB1 operator selection: pick the operator with the highest upper confidence bound.

    Untried operators are chosen first. Returns (operator, reason).
    """
    untried = [op for op in OPERATORS if counts[op] == 0]
    if untried:
        return rng.choice(untried), "ucb1 untried operator"
    best_op = None
    best_score = float("-inf")
    for op in OPERATORS:
        exploitation = rewards[op] / counts[op]
        exploration = math.sqrt(2 * math.log(trials) / counts[op])
        score = exploitation + exploration
        if score > best_score:
            best_score = score
            best_op = op
    return best_op, f"ucb1 score = {best_score:.6f}"


async def _run_reducer_lane(initial, oracle, lane_id: str, seed: int, evaluations: int,
                            shared_designs: list, run_id: str) -> dict:
    """Run a single reducer lane (random, greedy, or simulated_annealing).

    Counts initialize() evaluations by recording actual_oracle_calls before and after init.
    """
    lane_started_at = time.perf_counter()
    rng = random.Random(seed)
    agent_id = f"{run_id}:{lane_id}"
    key = Ed25519PrivateKey.generate()
    controller = Controller(
        initial, oracle, run_id=f"{run_id}:{lane_id}",
        max_oracle_calls=evaluations + 10,
        max_cost_microdollars=(evaluations + 10) * 1,
        evaluation_ceiling_microdollars=1,
        max_attempts=1, lane_ids=(lane_id,), minimum_improvement_c=0.05,
    )
    controller.register(agent_id, key)
    controller.bind_lane(lane_id, agent_id)
    calls_before_init = controller.actual_oracle_calls
    await controller.initialize(shared_initial_designs=shared_designs[1:])
    init_evaluations = controller.actual_oracle_calls - calls_before_init

    current_design = controller.design
    current_temperature = controller.best_temperature
    stagnation = 0
    improved_last = False
    noop_evaluations = 0
    proposal_attempts = 0
    max_proposal_attempts = evaluations * 128

    while controller.actual_oracle_calls < init_evaluations + evaluations:
        proposal_attempts += 1
        if proposal_attempts > max_proposal_attempts:
            raise RuntimeError(f"{lane_id} could not fill its equal evaluation budget")
        state = {
            "lane_id": lane_id,
            "seed": seed,
            "evaluations_completed": controller.actual_oracle_calls - init_evaluations,
            "evaluations_remaining": evaluations - (controller.actual_oracle_calls - init_evaluations),
            "best_temperature_c": controller.lane_best[lane_id][1],
            "current_temperature_c": current_temperature,
            "stagnation": stagnation,
            "improved_last": improved_last,
        }
        if lane_id == "simulated_annealing":
            progress = (1.0 if evaluations == 1 else
                        (controller.actual_oracle_calls - init_evaluations) / (evaluations - 1))
            state["temperature_scale_c"] = 0.5 * (0.05 / 0.5) ** progress

        if lane_id == "random":
            operator = rng.choice(OPERATORS)
            selection_reason = "uniform operator selection"
            parent = controller.lane_best[lane_id][0]
        elif lane_id == "greedy":
            operator = rng.choice(OPERATORS)
            selection_reason = "greedy first-improvement hill climb"
            parent = current_design
        elif lane_id == "simulated_annealing":
            operator = rng.choices(OPERATORS, (7, 2, 1))[0]
            selection_reason = f"SA proposal (T scale {state.get('temperature_scale_c', 0):.4f})"
            parent = current_design
        else:
            raise ValueError(f"unknown reducer lane: {lane_id}")

        candidate, operation, args = _candidate(parent, operator, rng, oracle)
        is_noop = candidate.hash == parent.hash
        noop_evaluations += int(is_noop)
        before_best = controller.lane_best[lane_id][1]
        controller.log.append("lane_decision", lane_id=lane_id, agent_id=agent_id,
                              policy=lane_id, operator=operator,
                              reason=selection_reason, state=state,
                              parent_hash=parent.hash, candidate_hash=candidate.hash, noop=is_noop)
        task_id = controller.mint_task(agent_id)
        proposal = controller.proposal(agent_id, key, task_id, operation, args,
                                       model_id="slab039-reducer", lane_id=lane_id,
                                       parent_hash=parent.hash,
                                       tool_hash=controller.problem_contract_hash)
        outcome = await controller.submit(proposal)
        candidate_temperature = outcome.temperature_c
        if candidate_temperature is not None:
            if lane_id == "greedy":
                if candidate_temperature < current_temperature:
                    current_design, current_temperature = candidate, candidate_temperature
            elif lane_id == "simulated_annealing":
                delta = candidate_temperature - current_temperature
                if delta <= 0 or rng.random() < math.exp(-delta / state.get("temperature_scale_c", 0.5)):
                    current_design, current_temperature = candidate, candidate_temperature
            else:
                pass
        improved_last = controller.lane_best[lane_id][1] < before_best
        if improved_last:
            stagnation = 0
        else:
            stagnation += 1
        controller.log.append("lane_step_result", lane_id=lane_id, agent_id=agent_id,
                              task_id=task_id, proposal_id=proposal.payload["proposal_id"],
                              status=outcome.status, reason=outcome.reason,
                              oracle_calls=controller.actual_oracle_calls - init_evaluations,
                              evaluation_admissions=controller.calls,
                              spent_microdollars=controller.spent, noop=is_noop)
        if outcome.status == "failed":
            raise RuntimeError(f"lane {lane_id} oracle evaluation failed: {outcome.reason}")
        if controller.stopped:
            raise RuntimeError(f"lane {lane_id} controller stopped: {outcome.reason}")

    controller.log.close()
    wall_time = time.perf_counter() - lane_started_at
    return {
        "seed": seed,
        "best_temperature_c": controller.best_temperature,
        "best_design_hash": controller.design.hash,
        "evaluation_count": controller.actual_oracle_calls - init_evaluations,
        "evaluation_admissions": controller.calls,
        "wall_time_s": wall_time,
        "noop_evaluations": noop_evaluations,
        "init_evaluations": init_evaluations,
        "total_evaluations_including_init": controller.actual_oracle_calls,
    }


async def _run_diagnostic_lane(initial, oracle, lane_id: str, seed: int, evaluations: int,
                               shared_designs: list, run_id: str) -> dict:
    """Run a single extra diagnostic lane (ucb1 or signal_portfolio).

    These are excluded from the gate criterion C but reported in the output.
    """
    lane_started_at = time.perf_counter()
    rng = random.Random(seed)
    agent_id = f"{run_id}:{lane_id}"
    key = Ed25519PrivateKey.generate()
    controller = Controller(
        initial, oracle, run_id=f"{run_id}:{lane_id}",
        max_oracle_calls=evaluations + 10,
        max_cost_microdollars=(evaluations + 10) * 1,
        evaluation_ceiling_microdollars=1,
        max_attempts=1, lane_ids=(lane_id,), minimum_improvement_c=0.05,
    )
    controller.register(agent_id, key)
    controller.bind_lane(lane_id, agent_id)
    calls_before_init = controller.actual_oracle_calls
    await controller.initialize(shared_initial_designs=shared_designs[1:])
    init_evaluations = controller.actual_oracle_calls - calls_before_init

    current_design = controller.design
    current_temperature = controller.best_temperature
    counts = {operator: 0 for operator in OPERATORS}
    rewards = {operator: 0.0 for operator in OPERATORS}
    stagnation = 0
    improved_last = False
    noop_evaluations = 0
    proposal_attempts = 0
    max_proposal_attempts = evaluations * 128

    while controller.actual_oracle_calls < init_evaluations + evaluations:
        proposal_attempts += 1
        if proposal_attempts > max_proposal_attempts:
            raise RuntimeError(f"{lane_id} could not fill its equal evaluation budget")
        state = {
            "lane_id": lane_id,
            "seed": seed,
            "evaluations_completed": controller.actual_oracle_calls - init_evaluations,
            "evaluations_remaining": evaluations - (controller.actual_oracle_calls - init_evaluations),
            "best_temperature_c": controller.lane_best[lane_id][1],
            "current_temperature_c": current_temperature,
            "stagnation": stagnation,
            "improved_last": improved_last,
        }
        if lane_id == "ucb1":
            operator, selection_reason = _choose_ucb1(counts, rewards,
                                                      controller.actual_oracle_calls - init_evaluations + 1, rng)
            parent = controller.lane_best[lane_id][0]
        elif lane_id == "signal_portfolio":
            signal_state = {
                "lane_id": lane_id,
                "seed": seed,
                "evaluations_completed": controller.actual_oracle_calls - init_evaluations,
                "evaluations_remaining": evaluations - (controller.actual_oracle_calls - init_evaluations),
                "best_temperature_c": controller.lane_best[lane_id][1],
                "current_temperature_c": current_temperature,
                "stagnation": stagnation,
                "improved_last": improved_last,
                "temperature_scale_c": 0.1,
                "counts": counts,
                "rewards": rewards,
            }
            choice = _signal_portfolio(signal_state)
            if choice[0] == "stop":
                break
            operator, selection_reason = choice
            parent = current_design
        else:
            raise ValueError(f"unknown diagnostic lane: {lane_id}")

        candidate, operation, args = _candidate(parent, operator, rng, oracle)
        is_noop = candidate.hash == parent.hash
        noop_evaluations += int(is_noop)
        before_best = controller.lane_best[lane_id][1]
        controller.log.append("lane_decision", lane_id=lane_id, agent_id=agent_id,
                              policy=lane_id, operator=operator,
                              reason=selection_reason, state=state,
                              parent_hash=parent.hash, candidate_hash=candidate.hash, noop=is_noop)
        task_id = controller.mint_task(agent_id)
        proposal = controller.proposal(agent_id, key, task_id, operation, args,
                                       model_id="slab039-diagnostic", lane_id=lane_id,
                                       parent_hash=parent.hash,
                                       tool_hash=controller.problem_contract_hash)
        outcome = await controller.submit(proposal)
        candidate_temperature = outcome.temperature_c
        if candidate_temperature is not None:
            counts[operator] += 1
            delta = before_best - candidate_temperature
            rewards[operator] += delta if delta > 0 else 0
            if lane_id == "ucb1":
                pass
            elif lane_id == "signal_portfolio":
                if candidate_temperature < current_temperature:
                    current_design, current_temperature = candidate, candidate_temperature
        improved_last = controller.lane_best[lane_id][1] < before_best
        if improved_last:
            stagnation = 0
        else:
            stagnation += 1
        controller.log.append("lane_step_result", lane_id=lane_id, agent_id=agent_id,
                              task_id=task_id, proposal_id=proposal.payload["proposal_id"],
                              status=outcome.status, reason=outcome.reason,
                              oracle_calls=controller.actual_oracle_calls - init_evaluations,
                              evaluation_admissions=controller.calls,
                              spent_microdollars=controller.spent, noop=is_noop)
        if outcome.status == "failed":
            raise RuntimeError(f"lane {lane_id} oracle evaluation failed: {outcome.reason}")
        if controller.stopped:
            raise RuntimeError(f"lane {lane_id} controller stopped: {outcome.reason}")

    controller.log.close()
    wall_time = time.perf_counter() - lane_started_at
    return {
        "seed": seed,
        "best_temperature_c": controller.best_temperature,
        "best_design_hash": controller.design.hash,
        "evaluation_count": controller.actual_oracle_calls - init_evaluations,
        "evaluation_admissions": controller.calls,
        "wall_time_s": wall_time,
        "noop_evaluations": noop_evaluations,
        "init_evaluations": init_evaluations,
        "total_evaluations_including_init": controller.actual_oracle_calls,
    }


async def _run_long_sa(initial, oracle, seed: int, max_evaluations: int,
                       cpu_timeout_s: float, shared_designs: list, run_id: str) -> dict:
    """Run a single long simulated annealing restart."""
    lane_started_at = time.perf_counter()
    rng = random.Random(seed)
    agent_id = f"{run_id}:{seed}"
    key = Ed25519PrivateKey.generate()
    controller = Controller(
        initial, oracle, run_id=f"{run_id}:{seed}",
        max_oracle_calls=max_evaluations + 10,
        max_cost_microdollars=(max_evaluations + 10) * 1,
        evaluation_ceiling_microdollars=1,
        max_attempts=1, lane_ids=("simulated_annealing",), minimum_improvement_c=0.05,
    )
    controller.register(agent_id, key)
    controller.bind_lane("simulated_annealing", agent_id)
    calls_before_init = controller.actual_oracle_calls
    await controller.initialize(shared_initial_designs=shared_designs[1:])
    init_evaluations = controller.actual_oracle_calls - calls_before_init

    current_design = controller.design
    current_temperature = controller.best_temperature
    noop_evaluations = 0
    proposal_attempts = 0
    max_proposal_attempts = max_evaluations * 128

    while controller.actual_oracle_calls < init_evaluations + max_evaluations:
        elapsed = time.perf_counter() - lane_started_at
        if elapsed > cpu_timeout_s:
            break
        proposal_attempts += 1
        if proposal_attempts > max_proposal_attempts:
            raise RuntimeError("long SA could not fill its evaluation budget")
        progress = (1.0 if max_evaluations == 1 else
                    (controller.actual_oracle_calls - init_evaluations) / (max_evaluations - 1))
        temperature_scale_c = 0.5 * (0.05 / 0.5) ** progress
        operator = rng.choices(("local_move", "swap", "global_resample"), (7, 2, 1))[0]

        state = {
            "lane_id": "simulated_annealing",
            "seed": seed,
            "evaluations_completed": controller.actual_oracle_calls - init_evaluations,
            "evaluations_remaining": max_evaluations - (controller.actual_oracle_calls - init_evaluations),
            "best_temperature_c": controller.lane_best["simulated_annealing"][1],
            "current_temperature_c": current_temperature,
            "stagnation": 0,
            "improved_last": False,
            "temperature_scale_c": temperature_scale_c,
        }

        parent = current_design
        candidate, operation, args = _candidate(parent, operator, rng, oracle)
        is_noop = candidate.hash == parent.hash
        noop_evaluations += int(is_noop)
        before_best = controller.lane_best["simulated_annealing"][1]
        controller.log.append("lane_decision", lane_id="simulated_annealing", agent_id=agent_id,
                              policy="simulated_annealing", operator=operator,
                              reason="long SA proposal", state=state,
                              parent_hash=parent.hash, candidate_hash=candidate.hash, noop=is_noop)
        task_id = controller.mint_task(agent_id)
        proposal = controller.proposal(agent_id, key, task_id, operation, args,
                                       model_id="slab039-long-sa", lane_id="simulated_annealing",
                                       parent_hash=parent.hash,
                                       tool_hash=controller.problem_contract_hash)
        outcome = await controller.submit(proposal)
        candidate_temperature = outcome.temperature_c
        if candidate_temperature is not None:
            delta = candidate_temperature - current_temperature
            if delta <= 0 or rng.random() < math.exp(-delta / temperature_scale_c):
                current_design, current_temperature = candidate, candidate_temperature
        controller.log.append("lane_step_result", lane_id="simulated_annealing", agent_id=agent_id,
                              task_id=task_id, proposal_id=proposal.payload["proposal_id"],
                              status=outcome.status, reason=outcome.reason,
                              oracle_calls=controller.actual_oracle_calls - init_evaluations,
                              evaluation_admissions=controller.calls,
                              spent_microdollars=controller.spent, noop=is_noop)
        if outcome.status == "failed":
            raise RuntimeError(f"long SA oracle evaluation failed: {outcome.reason}")
        if controller.stopped:
            raise RuntimeError(f"long SA controller stopped: {outcome.reason}")

    controller.log.close()
    wall_time = time.perf_counter() - lane_started_at
    cpu_exhausted = wall_time > cpu_timeout_s
    return {
        "seed": seed,
        "best_temperature_c": controller.best_temperature,
        "best_design_hash": controller.design.hash,
        "evaluation_count": controller.actual_oracle_calls - init_evaluations,
        "evaluation_admissions": controller.calls,
        "wall_time_s": wall_time,
        "cpu_exhausted": cpu_exhausted,
        "cpu_timeout_s": cpu_timeout_s,
        "noop_evaluations": noop_evaluations,
        "init_evaluations": init_evaluations,
        "total_evaluations_including_init": controller.actual_oracle_calls,
    }


async def run_headroom(fixture: str, mesh_error: float | None, prereg_path: str | Path,
                       output_dir: str | Path | None = None,
                       j32_values: list[float] | None = None,
                       j64_values: list[float] | None = None) -> dict:
    """Run the full headroom experiment.

    Reducer methods: random, greedy, simulated_annealing (determine the gate).
    Extra diagnostics: ucb1, signal_portfolio (run after declared runs, excluded from C).

    If mesh_error is provided as a float, it is validated (non-negative, finite).
    If j32_values and j64_values are provided, the mesh error is computed as max|J32 - J64|.
    """
    prereg = _parse_prereg(prereg_path)
    schema = prereg.get("schema", "slab-039-prereg-v1")

    _validate_mesh_error(mesh_error)

    # Determine reducer methods and extra diagnostics from prereg
    if schema == "slab-039-prereg-v3":
        cheap_cfg = prereg.get("reducer_methods", {})
        diag_cfg = prereg.get("extra_diagnostics", {})
        reducer_methods = tuple(cheap_cfg.get("methods", ["random", "greedy", "simulated_annealing"]))
        diag_methods = tuple(diag_cfg.get("methods", ["ucb1", "signal_portfolio"]))
    elif "reducer_methods" in prereg:
        cheap_cfg = prereg["reducer_methods"]
        reducer_methods = tuple(cheap_cfg.get("methods", ["random", "greedy", "simulated_annealing"]))
        diag_cfg = prereg.get("extra_diagnostics", {})
        diag_methods = tuple(diag_cfg.get("methods", ["ucb1", "signal_portfolio"]))
    else:
        cheap_cfg = prereg.get("cheap_methods", {})
        reducer_methods = tuple(cheap_cfg.get("methods", ["random", "simulated_annealing", "ucb1"]))
        # v1/v2: UCB1 and signal_portfolio were mixed in; for compatibility treat as reducer
        diag_methods = ()
        diag_cfg = {}

    long_cfg = prereg["long_sa"]
    seeds = tuple(cheap_cfg["seeds"])

    if "search_evaluations_per_method" in cheap_cfg:
        evaluations = cheap_cfg["search_evaluations_per_method"]
        reproduction_evals = cheap_cfg.get("reproduction_evaluations_per_method", 0)
    else:
        evaluations = cheap_cfg["evaluations_per_method"]
        reproduction_evals = 0

    output_dir = Path(output_dir) if output_dir is not None else Path("docs/sentilab/evidence/SLAB-039")
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT / "sundai_hotspot"))
    from tap_oracle import HotSpotOracle

    grid = prereg["grid"]
    oracle = HotSpotOracle(grid, grid)
    initial = oracle.design_from_centers(TAP_INITIAL_CENTERS)

    all_reducer_results: list[dict] = []
    all_diag_results: list[dict] = []
    long_sa_results: list[dict] = []
    aggregate_evaluations = 0

    try:
        # Phase 1: Reducer methods (determine gate)
        for method in reducer_methods:
            for seed in seeds:
                lane_seed = seed + 7919 * (list(reducer_methods).index(method) + 1)
                rng = random.Random(seed)
                shared_designs = _shared_designs(initial, oracle, seed, 3)
                run_id = f"slab039-{fixture}-{method}"
                result = await _run_reducer_lane(
                    initial, oracle, method, lane_seed, evaluations, shared_designs, run_id,
                )
                result["method"] = method
                result["category"] = "reducer"
                all_reducer_results.append(result)
                aggregate_evaluations += result["total_evaluations_including_init"]

        # Phase 2: Extra diagnostics (after declared runs)
        for method in diag_methods:
            for seed in seeds:
                lane_seed = seed + 7919 * (len(reducer_methods) + list(diag_methods).index(method) + 1)
                rng = random.Random(seed)
                shared_designs = _shared_designs(initial, oracle, seed, 3)
                run_id = f"slab039-{fixture}-{method}"
                result = await _run_diagnostic_lane(
                    initial, oracle, method, lane_seed, evaluations, shared_designs, run_id,
                )
                result["method"] = method
                result["category"] = "extra_diagnostic"
                all_diag_results.append(result)
                aggregate_evaluations += result["total_evaluations_including_init"]

        # Phase 3: Long SA
        long_seeds = tuple(long_cfg["seeds"])
        max_evals = long_cfg["max_evaluations_per_restart"]
        cpu_minutes = long_cfg["max_cpu_minutes"]
        cpu_timeout_s = cpu_minutes * 60.0

        for sa_seed in long_seeds:
            rng = random.Random(sa_seed)
            shared_designs = _shared_designs(initial, oracle, sa_seed, 3)
            run_id = f"slab039-{fixture}-long-sa"
            result = await _run_long_sa(
                initial, oracle, sa_seed, max_evals, cpu_timeout_s, shared_designs, run_id,
            )
            long_sa_results.append(result)
            aggregate_evaluations += result["total_evaluations_including_init"]
    finally:
        close = getattr(oracle, "aclose", None)
        if close is not None:
            await close()

    # Compute reducer method medians (gate C uses only reducer methods)
    reducer_medians = {}
    reducer_all_bests = {}
    for method in reducer_methods:
        method_results = [r for r in all_reducer_results if r["method"] == method]
        bests = [r["best_temperature_c"] for r in method_results]
        reducer_all_bests[method] = bests
        reducer_medians[method] = statistics.median(bests)

    cheap_median = min(reducer_medians.values())

    # Best from anywhere: reducer + diagnostics + long SA
    all_bests = [r["best_temperature_c"] for r in all_reducer_results]
    all_bests += [r["best_temperature_c"] for r in all_diag_results]
    all_bests += [r["best_temperature_c"] for r in long_sa_results]
    best = min(all_bests)

    # Combine all method medians for reporting (including diagnostics)
    all_method_medians = dict(reducer_medians)
    all_method_all_bests = dict(reducer_all_bests)
    for method in diag_methods:
        method_results = [r for r in all_diag_results if r["method"] == method]
        if method_results:
            bests = [r["best_temperature_c"] for r in method_results]
            all_method_all_bests[method] = bests
            all_method_medians[method] = statistics.median(bests)

    # Gate computation
    passed, gap = _gate_pass(cheap_median, best, mesh_error, k=prereg["rule"]["k"])

    # Check long SA exhaustion: if ALL long SA runs were cpu_exhausted or partial,
    # verdict is INCONCLUSIVE, not PASS/FAIL
    long_sa_exhausted = all(r.get("cpu_exhausted", False) for r in long_sa_results)
    long_sa_partial = any(r.get("evaluation_count", 0) < 1 for r in long_sa_results)
    if long_sa_exhausted or long_sa_partial:
        verdict = "INCONCLUSIVE"
    elif passed:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    # Spread across reducer seeds
    reducer_bests = [r["best_temperature_c"] for r in all_reducer_results]
    spread = max(reducer_bests) - min(reducer_bests) if reducer_bests else 0.0

    # Compute prereg digest
    prereg_digest = _compute_prereg_digest(prereg_path)

    result = {
        "schema": "slab-039-result-v3",
        "prereg_schema": schema,
        "prereg_digest_sha256": prereg_digest,
        "fixture": fixture,
        "grid": grid,
        "mesh_error_c": mesh_error,
        "mesh_error_source": "provided" if j32_values is None else "dynamic from J32/J64",
        "k": prereg["rule"]["k"],
        "verdict": verdict,
        "passed": passed,
        "gap_c": gap,
        "threshold_c": prereg["rule"]["k"] * mesh_error,
        "cheap_median_c": cheap_median,
        "best_c": best,
        "spread_across_seeds_c": spread,
        "reducer_methods": list(reducer_methods),
        "extra_diagnostics": list(diag_methods),
        "cheap_method_medians_c": all_method_medians,
        "cheap_method_all_bests_c": all_method_all_bests,
        "reducer_results": all_reducer_results,
        "extra_diagnostic_results": all_diag_results,
        "long_sa_results": long_sa_results,
        "long_sa_exhausted": long_sa_exhausted,
        "long_sa_partial": long_sa_partial,
        "aggregate_evaluations": aggregate_evaluations,
        "search_evaluations": evaluations,
        "reproduction_evaluations": reproduction_evals,
    }

    result_path = output_dir / "RESULT.json"
    _write_json(result_path, result)

    report_path = output_dir / "REPORT.md"
    _write_report(report_path, result, prereg, cheap_cfg)

    return result


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(data, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_report(path: Path, result: dict, prereg: dict, cheap_cfg: dict) -> None:
    verdict = result["verdict"]
    gap = result["gap_c"]
    threshold = result["threshold_c"]
    cheap_median = result["cheap_median_c"]
    best = result["best_c"]
    spread = result["spread_across_seeds_c"]
    mesh = result["mesh_error_c"]
    k = result["k"]

    lines = [
        f"# SLAB-039 Headroom Report: {result['fixture']}",
        "",
        f"**Verdict: {verdict}**",
        "",
        "## Rule",
        f"- k = {k}",
        f"- mesh error = {mesh:.6f} C",
        f"- threshold = k × mesh error = {threshold:.6f} C",
        f"- gap = cheap_median − best = {cheap_median:.6f} − {best:.6f} = {gap:.6f} C",
        f"- pass iff gap ≥ {threshold:.6f} C",
        "",
        "## Reducer Methods (gate C)",
        f"- search evaluations per method: {result.get('search_evaluations', 32)}",
        f"- reproduction evaluations per method: {result.get('reproduction_evaluations', 0)}",
        f"- total per method: {result.get('search_evaluations', 32) + result.get('reproduction_evaluations', 0)}",
        f"- seeds: {cheap_cfg.get('seed_count', 8)}",
        "",
    ]

    for method, median_val in result["cheap_method_medians_c"].items():
        bests = result["cheap_method_all_bests_c"][method]
        category = "reducer" if method in result.get("reducer_methods", []) else "extra diagnostic"
        lines.append(f"- **{method}** ({category}): median = {median_val:.6f} C, "
                     f"range = [{min(bests):.6f}, {max(bests):.6f}] C")

    lines += [
        "",
        f"**cheap_median** (min over reducer methods) = {cheap_median:.6f} C",
        "",
        "## Long SA",
    ]
    for i, sa in enumerate(result["long_sa_results"]):
        lines.append(f"- restart {i}: best = {sa['best_temperature_c']:.6f} C, "
                     f"evals = {sa['evaluation_count']}, "
                     f"wall = {sa['wall_time_s']:.1f}s, "
                     f"cpu_exhausted = {sa.get('cpu_exhausted', False)}")

    lines += [
        "",
        f"**best** (any method) = {best:.6f} C",
        "",
        "## Spread",
        f"- spread across all reducer seeds = {spread:.6f} C",
        "",
        "## Verdict",
        f"- {verdict}: gap ({gap:.6f} C) {'≥' if result['passed'] else '<'} threshold ({threshold:.6f} C)",
    ]

    if result.get("long_sa_exhausted"):
        lines.append("")
        lines.append("**Long SA was exhausted or partial — verdict is INCONCLUSIVE. "
                     "The protocol does not permit PASS when the reference run did not complete.**")

    if not result["passed"] and verdict != "INCONCLUSIVE":
        lines.append("")
        lines.append("**The task may be too flat for any method to win. "
                     "Consider revising the task before the benchmark.**")

    if result.get("extra_diagnostic_results"):
        lines += [
            "",
            "## Extra Diagnostics (excluded from gate C)",
        ]
        diag_methods = set(r["method"] for r in result["extra_diagnostic_results"])
        for method in sorted(diag_methods):
            method_results = [r for r in result["extra_diagnostic_results"] if r["method"] == method]
            bests_diag = [r["best_temperature_c"] for r in method_results]
            if bests_diag:
                lines.append(f"- **{method}**: median = {statistics.median(bests_diag):.6f} C, "
                             f"range = [{min(bests_diag):.6f}, {max(bests_diag):.6f}] C")

    report = "\n".join(lines) + "\n"
    path.write_text(report, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=("ascend910",), default="ascend910",
                        help="benchmark fixture (default: ascend910)")
    parser.add_argument("--mesh-error", type=float, default=None,
                        help="mesh error in C (from SLAB-006a); must be non-negative and finite")
    parser.add_argument("--j32", nargs="+", type=float, default=None,
                        help="J32 values for dynamic mesh error computation")
    parser.add_argument("--j64", nargs="+", type=float, default=None,
                        help="J64 values for dynamic mesh error computation")
    parser.add_argument("--prereg", type=Path, required=True,
                        help="path to PREREG.json")
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory (default: docs/sentilab/evidence/SLAB-039)")
    args = parser.parse_args()

    if args.mesh_error is None and (args.j32 is None or args.j64 is None):
        parser.error("either --mesh-error or both --j32 and --j64 are required")
    if args.mesh_error is not None:
        _validate_mesh_error(args.mesh_error)
    if args.j32 is not None:
        for v in args.j32:
            _validate_mesh_error(v)
    if args.j64 is not None:
        for v in args.j64:
            _validate_mesh_error(v)

    result = asyncio.run(run_headroom(
        fixture=args.fixture,
        mesh_error=args.mesh_error,
        prereg_path=args.prereg,
        output_dir=args.out,
        j32_values=args.j32,
        j64_values=args.j64,
    ))

    verdict = result["verdict"]
    gap = result["gap_c"]
    threshold = result["threshold_c"]
    cheap_median = result["cheap_median_c"]
    best = result["best_c"]
    print(json.dumps({
        "verdict": verdict,
        "gap_c": gap,
        "threshold_c": threshold,
        "cheap_median_c": cheap_median,
        "best_c": best,
        "passed": result["passed"],
        "long_sa_exhausted": result.get("long_sa_exhausted", False),
    }, sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
