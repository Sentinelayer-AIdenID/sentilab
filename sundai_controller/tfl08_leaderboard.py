"""TFL-08 equal-budget, multi-seed leaderboard and signed run bundle."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scipy.stats import wilcoxon
import numpy as np
import scipy
from threadpoolctl import threadpool_info

from sundai_controller.controller import Controller, Ed25519PrivateKey, FlightRecord, JevRoutingAdapter, ThermalResult, digest, public_hex, thermal_plate_adapter
from sundai_controller.experiment import LANE_IDS, OPERATORS, _candidate, _shared_designs, plate_initial_design, run_four_lanes
from sundai_controller.trust import CERTIFICATE_LIFETIME_SECONDS, certify_lane, load_service_key

DEFAULT_SEEDS = tuple(range(10))
JEV_INPUT_USD_PER_MILLION_TOKENS = 0.042
JEV_OUTPUT_USD_PER_MILLION_TOKENS = 0.0
JEV_PRICING_SOURCE = "https://typesafe.ai/"
TAP_INITIAL_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))
NONDETERMINISTIC_EVENT_FIELDS = frozenset({
    "signature", "hash", "previous_hash", "final_hash", "public_key", "record_public_key",
    "identity_public_key", "task_id", "proposal_id", "duration_ms", "latency_ms", "wall_time_s",
    "created_at", "timestamp", "expires_at", "evaluation_seconds", "solver_seconds",
    "input_generation_seconds",
})


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered or not 0 <= probability <= 1:
        raise ValueError("quantile requires values and a probability in [0, 1]")
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] + fraction * (ordered[high] - ordered[low])


def summarize(values, *, bootstrap_seed: int, resamples: int = 10000) -> dict:
    """Report median, inclusive IQR and a reproducible percentile CI for the median."""
    numbers = [float(value) for value in values]
    if not numbers or any(not math.isfinite(value) for value in numbers):
        raise ValueError("statistics require at least one finite observation")
    if not isinstance(resamples, int) or isinstance(resamples, bool) or resamples < 1000:
        raise ValueError("resamples must be an integer >= 1000")
    rng = random.Random(bootstrap_seed)
    boot = [statistics.median(rng.choices(numbers, k=len(numbers))) for _ in range(resamples)]
    median = statistics.median(numbers)
    q1, q3 = _quantile(numbers, 0.25), _quantile(numbers, 0.75)
    return {
        "n": len(numbers),
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "bootstrap_95_ci_median": [_quantile(boot, 0.025), _quantile(boot, 0.975)],
        "bootstrap_resamples": resamples,
    }


def _bootstrap_seed(benchmark: str, metric: str) -> int:
    return int.from_bytes(hashlib.sha256(f"tfl08:{benchmark}:{metric}".encode()).digest()[:8], "big")


def _runtime_metadata() -> dict:
    fields = ("user_api", "internal_api", "version", "threading_layer", "architecture", "num_threads")
    return {
        "python": platform.python_version(),
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "blas_pools": [{key: pool.get(key) for key in fields if pool.get(key) is not None}
                       for pool in threadpool_info()],
        "openblas_coretype_env": os.environ.get("OPENBLAS_CORETYPE"),
        "runner_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "controller_source_sha256": hashlib.sha256((Path(__file__).parent / "controller.py").read_bytes()).hexdigest(),
        "experiment_source_sha256": hashlib.sha256((Path(__file__).parent / "experiment.py").read_bytes()).hexdigest(),
    }


def _stable_event_value(value):
    if isinstance(value, dict):
        stable = {}
        for key, item in value.items():
            normalized_key = key.lower()
            if normalized_key in NONDETERMINISTIC_EVENT_FIELDS:
                continue
            if normalized_key == "input_sha256" and isinstance(item, (list, tuple)):
                # TAP's samplelayers.lcf embeds the per-call temporary directory
                # in its absolute floorplan paths. Its source floorplans are
                # hashed separately, so preserve those hashes and the LCF name
                # while removing only this invocation-specific digest.
                stable[key] = [
                    [entry[0], "<temporary-path-dependent>"]
                    if isinstance(entry, (list, tuple)) and len(entry) == 2
                    and entry[0] == "samplelayers.lcf"
                    else _stable_event_value(entry)
                    for entry in item
                ]
            else:
                stable[key] = _stable_event_value(item)
        return stable
    if isinstance(value, list):
        return [_stable_event_value(item) for item in value]
    return value


def _deterministic_record_projection(record: list[dict]) -> list[dict]:
    """Keep signed event content while excluding random keys, IDs, timestamps and runtime."""
    return [{"event": event.get("event"), "payload": _stable_event_value(event.get("payload", {}))}
            for event in record]


def _finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def curve_from_record(record: list[dict]) -> list[float]:
    """Read incumbent history from the signed baseline and committed outcomes."""
    baseline = next((event.get("payload", {}) for event in record if event.get("event") == "baseline"), None)
    if not isinstance(baseline, dict):
        raise ValueError("signed record has no baseline")
    samples = baseline.get("shared_initial_samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("signed baseline has no verified initial pool")
    temperatures = [sample.get("thermal", {}).get("maximum_temperature_c") for sample in samples]
    if any(not _finite_number(value) for value in temperatures):
        raise ValueError("signed baseline has an invalid temperature")
    best = min(temperatures)
    curve = [float(best)]
    for event in record:
        payload = event.get("payload", {})
        if event.get("event") == "proposal_committed":
            value = payload.get("temperature_c")
            if _finite_number(value):
                best = min(best, float(value))
        elif event.get("event") == "lane_step_result":
            curve.append(float(best))
    return curve


def _signal_metrics(record: list[dict], signal_mode: str) -> dict:
    decisions = [event.get("payload", {}) for event in record if event.get("event") == "signal_decision"]
    calls = sum(payload.get("provider_called") is True for payload in decisions)
    live_fallbacks = sum(bool(payload.get("fallback_reason")) for payload in decisions) if signal_mode == "live" else 0
    input_values = [payload.get("input_tokens") for payload in decisions if payload.get("provider_called") is True]
    output_values = [payload.get("output_tokens") for payload in decisions if payload.get("provider_called") is True]

    def total(values):
        if not values:
            return 0
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
            return None
        return sum(values)

    input_tokens, output_tokens = total(input_values), total(output_values)
    estimated_usd = None
    if input_tokens is not None and output_tokens is not None:
        estimated_usd = (input_tokens * JEV_INPUT_USD_PER_MILLION_TOKENS +
                         output_tokens * JEV_OUTPUT_USD_PER_MILLION_TOKENS) / 1_000_000
    return {
        "provider_decisions": len(decisions),
        "provider_calls": calls,
        "fallback_count": live_fallbacks,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "list_price_estimate_usd": estimated_usd,
        "invoice_cost_usd": None,
    }


async def _run_fixed_operator(initial, oracle, shared_designs, *, benchmark, seed, operator,
                              evaluations_per_lane, evaluation_ceiling_microdollars, service_key):
    lane_id = f"fixed_{operator}"
    lane_seed = seed + 104729 * (OPERATORS.index(operator) + 1)
    rng = random.Random(lane_seed)
    run_id = f"tfl08-{benchmark}-seed-{seed}-{lane_id}"
    agent_id = f"{run_id}:{lane_id}"
    key = Ed25519PrivateKey.generate()
    started = time.perf_counter()
    controller = Controller(
        initial, oracle, run_id=run_id,
        max_oracle_calls=evaluations_per_lane,
        max_cost_microdollars=evaluations_per_lane * evaluation_ceiling_microdollars,
        evaluation_ceiling_microdollars=evaluation_ceiling_microdollars,
        max_attempts=1, lane_ids=(lane_id,), minimum_improvement_c=0.05,
    )
    certificate = certify_lane(service_key, run_id, lane_id, controller.log.public_key,
                               int(time.time()) + CERTIFICATE_LIFETIME_SECONDS)
    controller.register(agent_id, key)
    controller.bind_lane(lane_id, agent_id)
    await controller.initialize(shared_initial_designs=shared_designs[1:])
    noops = 0
    for _ in range(evaluations_per_lane):
        parent = controller.lane_best[lane_id][0]
        candidate, operation, args = _candidate(parent, operator, rng, oracle)
        is_noop = candidate.hash == parent.hash
        noops += int(is_noop)
        controller.log.append("lane_decision", lane_id=lane_id, agent_id=agent_id,
                              policy="fixed_operator_reference", operator=operator,
                              reason="predeclared fixed-operator reference",
                              parent_hash=parent.hash, candidate_hash=candidate.hash, noop=is_noop)
        task_id = controller.mint_task(agent_id)
        proposal = controller.proposal(agent_id, key, task_id, operation, args,
                                       model_id=f"tfl08-fixed-{operator}", lane_id=lane_id,
                                       parent_hash=parent.hash, tool_hash=controller.problem_contract_hash)
        outcome = await controller.submit(proposal)
        controller.log.append("lane_step_result", lane_id=lane_id, agent_id=agent_id,
                              task_id=task_id, proposal_id=proposal.payload["proposal_id"],
                              status=outcome.status, reason=outcome.reason,
                              oracle_calls=controller.actual_oracle_calls,
                              evaluation_admissions=controller.calls,
                              spent_microdollars=controller.spent, noop=is_noop)
        if outcome.status == "failed" or controller.stopped or outcome.reason == "budget exhausted":
            raise RuntimeError(f"{lane_id} failed to complete its equal proposal budget: {outcome.reason}")
    if controller.calls != evaluations_per_lane or controller.reserved:
        raise RuntimeError(f"{lane_id} did not complete an equal, fully settled budget")
    controller.log.close()
    valid = FlightRecord.verify(controller.log.events, controller.log.public_key)
    if not valid:
        raise RuntimeError(f"{lane_id} signed record did not verify")
    return {
        "agent_id": agent_id,
        "run_id": run_id,
        "operator": operator,
        "shared_initial_sample_hashes": tuple(design.hash for design in shared_designs),
        "evaluation_count": controller.actual_oracle_calls,
        "evaluation_admissions": controller.calls,
        "spent_microdollars": controller.spent,
        "best_temperature_c": controller.best_temperature,
        "best_design_hash": controller.design.hash,
        "noop_evaluations": noops,
        "wall_time_s": time.perf_counter() - started,
        "record_public_key": controller.log.public_key,
        "record_certificate": certificate,
        "record_valid": valid,
        "record": controller.log.events,
    }


def _lane_artifact(lane_id, lane, *, signal_mode, record_path):
    record = lane["record"]
    curve = curve_from_record(record)
    if len(curve) != lane["evaluation_count"] + 1:
        raise ValueError(f"{lane_id} signed best-so-far curve has the wrong number of points")
    return {
        "lane_id": lane_id,
        "best_temperature_c": lane["best_temperature_c"],
        "best_design_hash": lane["best_design_hash"],
        "evaluation_count": lane["evaluation_count"],
        "evaluation_admissions": lane["evaluation_admissions"],
        "simulator_spend_microdollars": lane["spent_microdollars"],
        "wall_time_s": lane["wall_time_s"],
        "noop_evaluations": lane["noop_evaluations"],
        "best_so_far_c": curve,
        "signal": _signal_metrics(record, signal_mode) if lane_id == "signal_portfolio" else None,
        "record": {"path": record_path, "public_key": lane["record_public_key"],
                   "valid": lane["record_valid"], "event_count": len(record),
                   "tip_hash": record[-1]["hash"] if record else None},
    }


def _summary_rows(runs: list[dict], lane_ids: tuple[str, ...], benchmark: str) -> dict:
    rows = {}
    for lane_id in lane_ids:
        per_run = [run["lanes"][lane_id] for run in runs]
        temperatures = [row["best_temperature_c"] for row in per_run]
        seed = _bootstrap_seed(benchmark, lane_id)
        summary = summarize(temperatures, bootstrap_seed=seed)
        summary.update({
            "sample_variance_c2": statistics.variance(temperatures) if len(temperatures) > 1 else 0.0,
            "median_wall_time_s": statistics.median(row["wall_time_s"] for row in per_run),
            "total_simulator_spend_microdollars": sum(row["simulator_spend_microdollars"] for row in per_run),
            "total_noop_evaluations": sum(row["noop_evaluations"] for row in per_run),
            "best_so_far_curve": [
                {"evaluation": index,
                 "median_best_temperature_c": statistics.median(row["best_so_far_c"][index] for row in per_run),
                 "q1_c": _quantile([row["best_so_far_c"][index] for row in per_run], 0.25),
                 "q3_c": _quantile([row["best_so_far_c"][index] for row in per_run], 0.75)}
                for index in range(len(per_run[0]["best_so_far_c"]))
            ],
        })
        if lane_id == "signal_portfolio":
            signal_rows = [row["signal"] for row in per_run]
            token_fields = ("input_tokens", "output_tokens", "list_price_estimate_usd")
            summary["signal_layer"] = {
                "mode": per_run and runs[0]["signal_mode"],
                "total_provider_calls": sum(row["provider_calls"] for row in signal_rows),
                "total_fallbacks": sum(row["fallback_count"] for row in signal_rows),
                "total_input_tokens": None if any(row["input_tokens"] is None for row in signal_rows) else sum(row["input_tokens"] for row in signal_rows),
                "total_output_tokens": None if any(row["output_tokens"] is None for row in signal_rows) else sum(row["output_tokens"] for row in signal_rows),
                "estimated_list_price_usd": None if any(row["list_price_estimate_usd"] is None for row in signal_rows) else sum(row["list_price_estimate_usd"] for row in signal_rows),
                "invoice_cost_usd": None,
                "per_seed": [{field: row[field] for field in token_fields} | {
                    "provider_calls": row["provider_calls"], "fallback_count": row["fallback_count"]}
                    for row in signal_rows],
            }
        rows[lane_id] = summary

    for lane_id in lane_ids:
        if lane_id == "ucb1":
            continue
        left = [run["lanes"][lane_id]["best_temperature_c"] for run in runs]
        control = [run["lanes"]["ucb1"]["best_temperature_c"] for run in runs]
        test = wilcoxon(left, control, zero_method="zsplit", alternative="two-sided", method="auto")
        rows[lane_id]["paired_wilcoxon_vs_ucb1"] = {
            "statistic": float(test.statistic), "p_value": float(test.pvalue), "n": len(left),
            "zero_method": "zsplit",
            "paired_median_difference_c": statistics.median(a - b for a, b in zip(left, control)),
        }

    fixed = [run["hindsight_best_fixed_operator"] for run in runs]
    fixed_summary = summarize([row["best_temperature_c"] for row in fixed],
                              bootstrap_seed=_bootstrap_seed(benchmark, "hindsight_best_fixed_operator"))
    fixed_values = [row["best_temperature_c"] for row in fixed]
    fixed_summary["sample_variance_c2"] = statistics.variance(fixed_values) if len(fixed_values) > 1 else 0.0
    fixed_summary["selection_is_hindsight_upper_bound"] = True
    fixed_summary["selected_operator_counts"] = {
        operator: sum(row["operator"] == operator for row in fixed) for operator in OPERATORS
    }
    fixed_summary["total_noop_evaluations"] = sum(row["noop_evaluations"] for row in fixed)
    fixed_summary["median_wall_time_s"] = statistics.median(row["wall_time_s"] for row in fixed)
    fixed_summary["best_so_far_curve"] = [
        {"evaluation": index,
         "median_best_temperature_c": statistics.median(row["best_so_far_c"][index] for row in fixed),
         "q1_c": _quantile([row["best_so_far_c"][index] for row in fixed], 0.25),
         "q3_c": _quantile([row["best_so_far_c"][index] for row in fixed], 0.75)}
        for index in range(len(fixed[0]["best_so_far_c"]))
    ]
    rows["hindsight_best_fixed_operator"] = fixed_summary

    medians = {lane_id: rows[lane_id]["median"] for lane_id in LANE_IDS}
    best_median = min(medians.values())
    winners = [lane_id for lane_id, median in medians.items() if median == best_median]
    winner = winners[0] if len(winners) == 1 else "tie: " + ", ".join(winners)
    signal, ucb = medians["signal_portfolio"], medians["ucb1"]
    if signal < ucb:
        signal_statement = f"Signal portfolio median was {ucb - signal:.6f} C lower than UCB1."
    elif signal > ucb:
        signal_statement = f"Signal portfolio median was {signal - ucb:.6f} C higher (worse) than UCB1."
    else:
        signal_statement = "Signal portfolio and UCB1 had identical medians."
    signal_test = rows["signal_portfolio"]["paired_wilcoxon_vs_ucb1"]
    significance = (
        "not significant" if signal_test["p_value"] >= 0.05
        else "statistically significant at p<0.05"
    )
    signal_statement += (
        f" (paired Wilcoxon p={signal_test['p_value']:.2f}, n={signal_test['n']}; {significance})"
    )
    return {"lanes": rows, "winner_by_median": winner, "winners_by_median": winners,
            "signal_vs_ucb1_plain_result": signal_statement}


async def _oracle_for(benchmark: str, grid: int):
    if benchmark == "plate":
        return plate_initial_design(), thermal_plate_adapter(grid_size=40)
    if benchmark != "ascend910":
        raise ValueError(f"unsupported benchmark: {benchmark}")
    sys.path.insert(0, str(ROOT / "sundai_hotspot"))
    from tap_oracle import HotSpotOracle
    oracle = HotSpotOracle(grid, grid)
    return oracle.design_from_centers(TAP_INITIAL_CENTERS), oracle


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(data, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


async def run_benchmark(benchmark: str, *, service_key, seeds=DEFAULT_SEEDS, grid=16, evaluations_per_lane=8,
                        shared_sample_count=3, evaluation_ceiling_microdollars=1,
                        signal_mode="local", output_dir: Path | None = None) -> dict:
    seeds = tuple(seeds)
    if any(not isinstance(seed, int) or isinstance(seed, bool) or seed < 0 for seed in seeds):
        raise ValueError("TFL-08 seeds must be nonnegative integers")
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise ValueError("TFL-08 requires at least 10 distinct nonnegative integer seeds")
    if not isinstance(evaluations_per_lane, int) or isinstance(evaluations_per_lane, bool) or evaluations_per_lane < 1:
        raise ValueError("evaluations_per_lane must be a positive integer")
    if not isinstance(shared_sample_count, int) or isinstance(shared_sample_count, bool) or shared_sample_count < 0:
        raise ValueError("shared_sample_count must be a nonnegative integer")
    if (not isinstance(evaluation_ceiling_microdollars, int) or isinstance(evaluation_ceiling_microdollars, bool)
            or evaluation_ceiling_microdollars < 1):
        raise ValueError("evaluation_ceiling_microdollars must be a positive integer")
    if benchmark not in {"plate", "ascend910"}:
        raise ValueError(f"unsupported benchmark: {benchmark}")
    if signal_mode not in {"local", "live"}:
        raise ValueError("signal_mode must be local or live")
    benchmark_grid = 40 if benchmark == "plate" else grid
    initial, oracle = await _oracle_for(benchmark, benchmark_grid)
    output_dir = Path(output_dir) if output_dir is not None else None
    benchmark_runs = []
    try:
        for seed in seeds:
            run_id = f"tfl08-{benchmark}-seed-{seed}"
            # Each seed is an independent live trial. Do not let the adapter's
            # per-run provider-call cap consume every later seed's advice budget.
            signal_router = JevRoutingAdapter(max_calls=evaluations_per_lane, timeout_s=5) if signal_mode == "live" else None
            shared_designs = _shared_designs(initial, oracle, seed, shared_sample_count)
            experiment = await run_four_lanes(
                initial, oracle, service_key=service_key, run_id=run_id, seed=seed,
                evaluations_per_lane=evaluations_per_lane,
                evaluation_ceiling_microdollars=evaluation_ceiling_microdollars,
                shared_sample_count=shared_sample_count,
                signal_router=signal_router,
            )
            hashes = tuple(design.hash for design in shared_designs)
            if hashes != tuple(experiment["shared_initial_sample_hashes"]):
                raise RuntimeError("shared pool differs between benchmark lanes")
            if not experiment["evaluation_counts_equal"] or not experiment["flight_records_valid"]:
                raise RuntimeError("four-lane run did not meet equal-budget signed-record requirements")
            raw_lanes = dict(experiment["lane_results"])
            for operator in OPERATORS:
                fixed = await _run_fixed_operator(
                    initial, oracle, shared_designs, service_key=service_key, benchmark=benchmark, seed=seed,
                    operator=operator, evaluations_per_lane=evaluations_per_lane,
                    evaluation_ceiling_microdollars=evaluation_ceiling_microdollars,
                )
                raw_lanes[f"fixed_{operator}"] = fixed
            for lane in raw_lanes.values():
                if lane["evaluation_count"] != evaluations_per_lane or lane["evaluation_admissions"] != evaluations_per_lane:
                    raise RuntimeError("a leaderboard lane did not use the exact proposal budget")
                if tuple(lane["shared_initial_sample_hashes"]) != hashes:
                    raise RuntimeError("a leaderboard lane did not use the common initial pool")

            lane_artifacts = {}
            for lane_id, lane in raw_lanes.items():
                relative = Path("records") / benchmark / f"seed-{seed}" / f"{lane_id}.json"
                if output_dir is not None:
                    _write_json(output_dir / relative, {
                        "benchmark": benchmark, "grid": benchmark_grid, "seed": seed,
                        "lane_id": lane_id, "run_id": lane["record_certificate"]["run_id"],
                        "record_certificate": lane["record_certificate"],
                        "record_public_key": lane["record_public_key"], "events": lane["record"],
                    })
                lane_artifacts[lane_id] = _lane_artifact(
                    lane_id, lane, signal_mode=signal_mode, record_path=relative.as_posix())

            fixed_lane_id = min((f"fixed_{operator}" for operator in OPERATORS),
                                key=lambda lane_id: lane_artifacts[lane_id]["best_temperature_c"])
            fingerprint_lanes = [lane_id for lane_id in raw_lanes
                                 if lane_id != "signal_portfolio" or signal_mode == "local"]
            deterministic = {
                lane_id: _deterministic_record_projection(raw_lanes[lane_id]["record"])
                for lane_id in fingerprint_lanes
            }
            benchmark_runs.append({
                "benchmark": benchmark, "grid": benchmark_grid, "seed": seed,
                "evaluations_per_lane": evaluations_per_lane,
                "shared_initial_sample_hashes": list(hashes),
                "evaluation_counts_equal": True,
                "signal_mode": signal_mode,
                "deterministic_fingerprint_lanes": fingerprint_lanes,
                "lanes": lane_artifacts,
                "hindsight_best_fixed_operator": {
                    "operator": fixed_lane_id.removeprefix("fixed_"),
                    **{key: lane_artifacts[fixed_lane_id][key] for key in (
                        "best_temperature_c", "best_so_far_c", "wall_time_s",
                        "simulator_spend_microdollars", "noop_evaluations", "record")},
                },
                "deterministic_fingerprint": digest(deterministic),
            })
    finally:
        close = getattr(oracle, "aclose", None)
        if close is not None:
            await close()

    summary = _summary_rows(benchmark_runs, LANE_IDS, benchmark)
    return {
        "benchmark": benchmark,
        "grid": benchmark_grid,
        "seed_count": len(seeds),
        "seeds": list(seeds),
        "evaluations_per_lane": evaluations_per_lane,
        "shared_initial_sample_count": shared_sample_count + 1,
        "signal_mode": signal_mode,
        "statistics": summary,
        "runs": benchmark_runs,
        "signal_pricing": {
            "input_usd_per_million_tokens": JEV_INPUT_USD_PER_MILLION_TOKENS,
            "output_usd_per_million_tokens": JEV_OUTPUT_USD_PER_MILLION_TOKENS,
            "source": JEV_PRICING_SOURCE,
            "label": "estimated list price; invoice cost is unavailable from the System One response",
        },
        "runtime": _runtime_metadata(),
    }


async def run_leaderboard(benchmarks, *, service_key, seeds=DEFAULT_SEEDS, grid=16, evaluations_per_lane=8,
                          shared_sample_count=3, signal_mode="local", output_dir=None):
    seeds = tuple(seeds)
    benchmarks = tuple(benchmarks)
    if not benchmarks or len(set(benchmarks)) != len(benchmarks):
        raise ValueError("select one or more distinct benchmarks")
    output_dir = Path(output_dir) if output_dir is not None else None
    summaries = []
    for benchmark in benchmarks:
        summaries.append(await run_benchmark(
            benchmark, service_key=service_key, seeds=seeds, grid=grid, evaluations_per_lane=evaluations_per_lane,
            shared_sample_count=shared_sample_count, signal_mode=signal_mode,
            output_dir=output_dir,
        ))
    result = {
        "schema": "tfl08-leaderboard-v1",
        "runtime": _runtime_metadata(),
        "protocol": {
            "seed_count": len(seeds), "seeds": list(seeds),
            "evaluations_per_lane": evaluations_per_lane,
            "shared_initial_sample_count": shared_sample_count + 1,
            "lane_ids": list(LANE_IDS), "fixed_operator_references": list(OPERATORS),
            "signal_mode": signal_mode,
            "same_initial_pool_per_seed": True,
            "same_proposal_budget_per_lane": True,
            "deterministic_replay_fingerprint_excludes_runtime_and_random_signature_material": True,
            "signal_variance_note": "sample variance of per-seed best temperatures, reported in C^2",
            "hindsight_reference_note": "The fixed-operator upper bound selects the best of three separately signed fixed-operator runs per seed after observing their outcomes.",
            "simulator_cost_note": "Controller simulator spend is reported in its declared microdollar units; this is distinct from invoice cost.",
            "timing_note": "Observed lane wall time includes baseline initialization and shared-worker warm/cold effects in fixed lane order; it is report-only, not a controlled speed comparison.",
        },
        "benchmarks": {item["benchmark"]: item for item in summaries},
    }
    if output_dir is not None:
        _write_json(output_dir / "leaderboard.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", nargs="+", choices=("plate", "ascend910"), default=("plate", "ascend910"))
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--grid", type=int, default=16)
    parser.add_argument("--evaluations", type=int, default=8)
    parser.add_argument("--shared-samples", type=int, default=3)
    parser.add_argument("--signal", choices=("local", "live"), default="local")
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "tfl08")
    args = parser.parse_args()
    result = asyncio.run(run_leaderboard(
        args.benchmarks, service_key=load_service_key(), seeds=args.seeds, grid=args.grid,
        evaluations_per_lane=args.evaluations,
        shared_sample_count=args.shared_samples,
        signal_mode=args.signal, output_dir=args.out,
    ))
    print(json.dumps({"schema": result["schema"], "out": str(args.out),
                      "benchmarks": {name: {"winner": item["statistics"]["winner_by_median"],
                                             "signal_result": item["statistics"]["signal_vs_ucb1_plain_result"]}
                                     for name, item in result["benchmarks"].items()}},
                     sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
