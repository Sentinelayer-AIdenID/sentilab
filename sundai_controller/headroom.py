"""SLAB-039: Headroom runner — cheap search vs long SA to measure optimization headroom.

Run random, SA, UCB1 and signal_portfolio at 28 search + 4 reproduction evaluations over 8 seeds, plus a capped long SA,
and report cheap_median - best against 5x the mesh error.
"""
from __future__ import annotations

import argparse
import asyncio
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
from sundai_controller.experiment import LANE_IDS, OPERATORS, SIGNAL_CHOICES, _candidate, _shared_designs, _signal_portfolio

TAP_INITIAL_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))


def _parse_prereg(path: str | Path) -> dict:
    """Load and validate the preregistration file."""
    prereg_path = Path(path)
    if not prereg_path.is_file():
        raise FileNotFoundError(f"prereg file not found: {prereg_path}")
    with open(prereg_path, encoding="utf-8") as fh:
        prereg = json.load(fh)
    schema = prereg.get("schema")
    if schema not in ("slab-039-prereg-v1", "slab-039-prereg-v2"):
        raise ValueError(f"prereg must have schema slab-039-prereg-v1 or v2, got: {schema}")
    if prereg.get("fixture") != "ascend910":
        raise ValueError(f"unsupported fixture: {prereg.get('fixture')}")
    if prereg.get("rule", {}).get("k") != 5:
        raise ValueError("prereg k must be 5")
    return prereg


def _gate_pass(cheap_median: float, best: float, mesh_error: float, k: int = 5) -> tuple[bool, float]:
    """Apply the warden +1 condition 2: pass iff cheap_median - best >= k * mesh_error."""
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
    gap = cheap_median - best
    threshold = k * mesh_error
    return gap >= threshold, gap, mesh_error


async def _run_cheap_lane(initial, oracle, lane_id: str, seed: int, evaluations: int,
                          shared_designs: list, run_id: str) -> dict:
    """Run a single cheap lane (random, SA, or UCB1) and return its result."""
    lane_started_at = time.perf_counter()
    rng = random.Random(seed)
    agent_id = f"{run_id}:{lane_id}"
    key = Ed25519PrivateKey.generate()
    controller = Controller(
        initial, oracle, run_id=f"{run_id}:{lane_id}",
        max_oracle_calls=evaluations,
        max_cost_microdollars=evaluations * 1,
        evaluation_ceiling_microdollars=1,
        max_attempts=1, lane_ids=(lane_id,), minimum_improvement_c=0.05,
    )
    controller.register(agent_id, key)
    controller.bind_lane(lane_id, agent_id)
    await controller.initialize(shared_initial_designs=shared_designs[1:])

    current_design = controller.design
    current_temperature = controller.best_temperature
    counts = {operator: 0 for operator in OPERATORS}
    rewards = {operator: 0.0 for operator in OPERATORS}
    stagnation = 0
    improved_last = False
    noop_evaluations = 0
    proposal_attempts = 0
    max_proposal_attempts = evaluations * 128

    while controller.actual_oracle_calls < evaluations:
        proposal_attempts += 1
        if proposal_attempts > max_proposal_attempts:
            raise RuntimeError(f"{lane_id} could not fill its equal evaluation budget")
        state = {
            "lane_id": lane_id,
            "seed": seed,
            "evaluations_completed": controller.actual_oracle_calls,
            "evaluations_remaining": evaluations - controller.actual_oracle_calls,
            "best_temperature_c": controller.lane_best[lane_id][1],
            "current_temperature_c": current_temperature,
            "stagnation": stagnation,
            "improved_last": improved_last,
        }
        if lane_id == "simulated_annealing":
            progress = (1.0 if evaluations == 1 else
                        controller.calls / (evaluations - 1))
            state["temperature_scale_c"] = 0.5 * (0.05 / 0.5) ** progress
        if lane_id == "random":
            operator, selection_reason = rng.choice(OPERATORS), "uniform operator selection"
            parent = controller.lane_best[lane_id][0]
        elif lane_id == "simulated_annealing":
            operator = rng.choices(("local_move", "swap", "global_resample"), (7, 2, 1))[0]
            selection_reason = "seeded simulated-annealing proposal"
            parent = current_design
        elif lane_id == "ucb1":
            operator, selection_reason = _choose_ucb1(counts, rewards, rng), "UCB1 operator selection"
            parent = controller.lane_best[lane_id][0]
        elif lane_id == "signal_portfolio":
            det_operator, det_reason = _signal_portfolio(state)
            if det_operator == "stop":
                operator, selection_reason = rng.choice(OPERATORS), "signal stoppage fallback"
            else:
                operator, selection_reason = det_operator, det_reason
            parent = controller.lane_best[lane_id][0]
        else:
            raise ValueError(f"unsupported cheap lane: {lane_id}")

        candidate, operation, args = _candidate(parent, operator, rng, oracle)
        is_noop = candidate.hash == parent.hash
        noop_evaluations += int(is_noop)
        before_best = controller.lane_best[lane_id][1]
        controller.log.append("lane_decision", lane_id=lane_id, agent_id=agent_id,
                              policy=lane_id, operator=operator, reason=selection_reason,
                              state=state, parent_hash=parent.hash, candidate_hash=candidate.hash,
                              noop=is_noop)
        task_id = controller.mint_task(agent_id)
        proposal = controller.proposal(agent_id, key, task_id, operation, args,
                                      model_id=f"slab039-{lane_id}", lane_id=lane_id,
                                      parent_hash=parent.hash,
                                      tool_hash=controller.problem_contract_hash)
        outcome = await controller.submit(proposal)
        candidate_temperature = outcome.temperature_c
        improved_last = (candidate_temperature is not None and candidate_temperature < before_best)
        if improved_last:
            stagnation = 0
        elif candidate_temperature is not None:
            stagnation += 1
        if lane_id == "ucb1":
            counts[operator] += 1
            rewards[operator] += float(outcome.status == "committed")
        if lane_id == "simulated_annealing" and candidate_temperature is not None:
            delta = candidate_temperature - current_temperature
            temperature_scale = state["temperature_scale_c"]
            if delta <= 0 or rng.random() < math.exp(-delta / temperature_scale):
                current_design, current_temperature = candidate, candidate_temperature
        controller.log.append("lane_step_result", lane_id=lane_id, agent_id=agent_id,
                              task_id=task_id, proposal_id=proposal.payload["proposal_id"],
                              status=outcome.status, reason=outcome.reason,
                              oracle_calls=controller.actual_oracle_calls,
                              evaluation_admissions=controller.calls,
                              spent_microdollars=controller.spent, noop=is_noop)
        if outcome.status == "failed":
            raise RuntimeError(f"{lane_id} oracle evaluation failed: {outcome.reason}")
        if controller.stopped:
            raise RuntimeError(f"{lane_id} controller stopped: {outcome.reason}")
        if outcome.reason == "budget exhausted":
            raise RuntimeError(f"{lane_id} exhausted cost budget before its evaluation budget")

    if controller.calls != evaluations:
        raise RuntimeError(f"{lane_id} evaluation admissions differ from its target")
    if controller.reserved:
        raise RuntimeError(f"{lane_id} left an evaluation reservation open")
    controller.log.close()
    wall_time = time.perf_counter() - lane_started_at
    return {
        "lane_id": lane_id,
        "seed": seed,
        "best_temperature_c": controller.best_temperature,
        "best_design_hash": controller.design.hash,
        "evaluation_count": controller.actual_oracle_calls,
        "evaluation_admissions": controller.calls,
        "wall_time_s": wall_time,
        "noop_evaluations": noop_evaluations,
    }


def _choose_ucb1(counts: dict[str, int], rewards: dict[str, float], rng: random.Random) -> str:
    """UCB1 operator selection (duplicated from experiment.py to keep headroom self-contained)."""
    untried = [op for op in OPERATORS if counts[op] == 0]
    if untried:
        return untried[0]
    total = sum(counts.values())
    scores = {op: rewards[op] / counts[op] +
              math.sqrt(2 * math.log(total) / counts[op]) for op in OPERATORS}
    best_score = max(scores.values())
    return rng.choice([op for op, score in scores.items() if score == best_score])


async def _run_long_sa(initial, oracle, seed: int, max_evaluations: int,
                       cpu_timeout_s: float, shared_designs: list, run_id: str) -> dict:
    """Run a long simulated annealing restart with strict CPU cap."""
    lane_started_at = time.perf_counter()
    rng = random.Random(seed)
    agent_id = f"{run_id}:long-sa"
    key = Ed25519PrivateKey.generate()
    controller = Controller(
        initial, oracle, run_id=f"{run_id}:long-sa",
        max_oracle_calls=max_evaluations,
        max_cost_microdollars=max_evaluations * 1,
        evaluation_ceiling_microdollars=1,
        max_attempts=1, lane_ids=("simulated_annealing",), minimum_improvement_c=0.05,
    )
    controller.register(agent_id, key)
    controller.bind_lane("simulated_annealing", agent_id)
    await controller.initialize(shared_initial_designs=shared_designs[1:])

    current_design = controller.design
    current_temperature = controller.best_temperature
    noop_evaluations = 0
    proposal_attempts = 0
    max_proposal_attempts = max_evaluations * 128

    while controller.actual_oracle_calls < max_evaluations:
        elapsed = time.perf_counter() - lane_started_at
        if elapsed > cpu_timeout_s:
            break
        proposal_attempts += 1
        if proposal_attempts > max_proposal_attempts:
            raise RuntimeError("long SA could not fill its evaluation budget")
        progress = (1.0 if max_evaluations == 1 else
                    controller.calls / (max_evaluations - 1))
        temperature_scale_c = 0.5 * (0.05 / 0.5) ** progress
        operator = rng.choices(("local_move", "swap", "global_resample"), (7, 2, 1))[0]

        state = {
            "lane_id": "simulated_annealing",
            "seed": seed,
            "evaluations_completed": controller.actual_oracle_calls,
            "evaluations_remaining": max_evaluations - controller.actual_oracle_calls,
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
                              oracle_calls=controller.actual_oracle_calls,
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
        "evaluation_count": controller.actual_oracle_calls,
        "evaluation_admissions": controller.calls,
        "wall_time_s": wall_time,
        "cpu_exhausted": cpu_exhausted,
        "cpu_timeout_s": cpu_timeout_s,
        "noop_evaluations": noop_evaluations,
    }


async def run_headroom(fixture: str, mesh_error: float | None, prereg_path: str | Path,
                       output_dir: str | Path | None = None,
                       j32_values: list[float] | None = None,
                       j64_values: list[float] | None = None) -> dict:
    """Run the full headroom experiment.

    If mesh_error is provided as a float, it is used directly.
    If j32_values and j64_values are provided, the mesh error is computed as max|J32 - J64|.
    """
    prereg = _parse_prereg(prereg_path)
    cheap_cfg = prereg["cheap_methods"]
    long_cfg = prereg["long_sa"]

    seeds = tuple(cheap_cfg["seeds"])
    # v2 schema: 28 search + 4 reproduction; v1: 32 flat
    if "search_evaluations_per_method" in cheap_cfg:
        evaluations = cheap_cfg["search_evaluations_per_method"]
        reproduction_evals = cheap_cfg.get("reproduction_evaluations_per_method", 0)
    else:
        evaluations = cheap_cfg["evaluations_per_method"]
        reproduction_evals = 0
    methods = tuple(cheap_cfg["methods"])

    if mesh_error is None:
        if j32_values is None or j64_values is None:
            raise ValueError("mesh_error or j32/j64 values required")
        if len(j32_values) != len(j64_values):
            raise ValueError(f"J32 length ({len(j32_values)}) must equal J64 length ({len(j64_values)})")
        differences = [abs(a - b) for a, b in zip(j32_values, j64_values)]
        mesh_error = max(differences)

    output_dir = Path(output_dir) if output_dir is not None else Path("docs/sentilab/evidence/SLAB-039")
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT / "sundai_hotspot"))
    from tap_oracle import HotSpotOracle

    grid = prereg["grid"]
    oracle = HotSpotOracle(grid, grid)
    initial = oracle.design_from_centers(TAP_INITIAL_CENTERS)

    all_cheap_results: list[dict] = []
    long_sa_results: list[dict] = []

    try:
        for method in methods:
            for seed in seeds:
                lane_seed = seed + 7919 * (list(methods).index(method) + 1)
                rng = random.Random(seed)
                shared_designs = _shared_designs(initial, oracle, seed, 3)
                run_id = f"slab039-{fixture}-{method}"
                result = await _run_cheap_lane(
                    initial, oracle, method, lane_seed, evaluations, shared_designs, run_id,
                )
                result["method"] = method
                all_cheap_results.append(result)

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
    finally:
        close = getattr(oracle, "aclose", None)
        if close is not None:
            await close()

    method_medians = {}
    method_all_bests = {}
    for method in methods:
        method_results = [r for r in all_cheap_results if r["method"] == method]
        bests = [r["best_temperature_c"] for r in method_results]
        method_all_bests[method] = bests
        method_medians[method] = statistics.median(bests)

    cheap_median = min(method_medians.values())
    all_bests = [r["best_temperature_c"] for r in all_cheap_results]
    all_bests += [r["best_temperature_c"] for r in long_sa_results]
    best = min(all_bests)

    passed, gap = _gate_pass(cheap_median, best, mesh_error, k=prereg["rule"]["k"])

    cheap_bests = [r["best_temperature_c"] for r in all_cheap_results]
    spread = max(cheap_bests) - min(cheap_bests)

    result = {
        "schema": "slab-039-result-v2" if prereg.get("schema") == "slab-039-prereg-v2" else "slab-039-result-v1",
        "prereg_schema": prereg.get("schema"),
        "fixture": fixture,
        "grid": grid,
        "mesh_error_c": mesh_error,
        "mesh_error_source": "provided" if j32_values is None else "dynamic max|J32-J64|",
        "k": prereg["rule"]["k"],
        "threshold_c": prereg["rule"]["k"] * mesh_error,
        "cheap_median_c": cheap_median,
        "best_c": best,
        "gap_c": gap,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "cheap_method_medians_c": method_medians,
        "cheap_method_all_bests_c": method_all_bests,
        "long_sa_bests_c": [r["best_temperature_c"] for r in long_sa_results],
        "spread_across_seeds_c": spread,
        "cheap_results": all_cheap_results,
        "long_sa_results": long_sa_results,
        "prereg_sha256": digest({"path": str(prereg_path)}),
        "search_evaluations": evaluations,
        "reproduction_evaluations": reproduction_evals,
    }

    result_path = output_dir / "RESULT.json"
    _write_json(result_path, result)

    report_path = output_dir / "REPORT.md"
    _write_report(report_path, result, prereg)

    return result


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(data, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_report(path: Path, result: dict, prereg: dict) -> None:
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
        "## Cheap Methods",
        f"- search evaluations per method: {result.get('search_evaluations', 32)}",
        f"- reproduction evaluations per method: {result.get('reproduction_evaluations', 0)}",
        f"- total per method: {result.get('search_evaluations', 32) + result.get('reproduction_evaluations', 0)}",
        f"- seeds: {cheap_cfg.get('seed_count', 8)}",
        "",
    ]

    for method, median_val in result["cheap_method_medians_c"].items():
        bests = result["cheap_method_all_bests_c"][method]
        lines.append(f"- **{method}**: median = {median_val:.6f} C, "
                     f"range = [{min(bests):.6f}, {max(bests):.6f}] C")

    lines += [
        "",
        f"**cheap_median** (min over methods) = {cheap_median:.6f} C",
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
        f"- spread across all cheap seeds = {spread:.6f} C",
        "",
        "## Verdict",
        f"- {verdict}: gap ({gap:.6f} C) {'≥' if result['passed'] else '<'} threshold ({threshold:.6f} C)",
    ]

    if not result["passed"]:
        lines.append("")
        lines.append("**The task may be too flat for any method to win. "
                     "Consider revising the task before the benchmark.**")

    report = "\n".join(lines) + "\n"
    path.write_text(report, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=("ascend910",), default="ascend910",
                        help="benchmark fixture (default: ascend910)")
    parser.add_argument("--mesh-error", type=float, default=None,
                        help="mesh error in C (from SLAB-006a); if omitted, --j32/--j64 required")
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
    }, sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
