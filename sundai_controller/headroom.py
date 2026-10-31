"""SLAB-039: Headroom runner — cheap search vs long SA to measure optimization headroom.

Run random, greedy, and short simulated_annealing (reducer methods) at 28 search + 4 reproduction
evaluations over 8 seeds, plus a capped long SA, and report cheap_median - best against 5x the mesh error.
UCB1 and signal_portfolio run as extra diagnostics only, excluded from the gate criterion C.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import fcntl
import resource
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sundai_controller.controller import Controller, Ed25519PrivateKey
from sundai_controller.experiment import OPERATORS, _candidate, _shared_designs, _signal_portfolio

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


class BudgetExhausted(RuntimeError):
    """No further oracle calls may be admitted under this allocation."""


def _cpu_seconds():
    usages = (resource.getrusage(resource.RUSAGE_SELF),
              resource.getrusage(resource.RUSAGE_CHILDREN))
    return sum(usage.ru_utime + usage.ru_stime for usage in usages)


class SolveBudget:
    """One durable allocation shared by fixtures and all evaluation phases.

    Hold the lock for the run. Reserve and fsync before starting each oracle call;
    a crash with an outstanding reservation requires reconciliation, never a reset.
    """
    def __init__(self, path, fixture, prereg):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix('.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise
        self.fixture = fixture
        allocation = prereg.get('allocation', {})
        per_fixture = allocation.get('per_fixture', {})
        self.solve_limit = min(9700, allocation.get('headroom_solve_limit', 9700))
        self.fixture_limit = min(4768, per_fixture.get('total_solves', 4768))
        self.cpu_limit = min(48 * 60, allocation.get('headroom_cpu_minutes', 48) * 60)
        self.fixture_cpu_limit = min(24 * 60, per_fixture.get('cpu_minutes', 24) * 60)
        self.clock = prereg.get('clock', {})
        self.last_cpu = _cpu_seconds()
        self.state = (json.loads(self.path.read_text()) if self.path.exists() else
                      {'total_calls': 0, 'cpu_seconds': 0.0, 'fixtures': {}, 'active': None})
        if self.state['active'] is not None:
            self.lock.close()
            raise RuntimeError('unreconciled oracle reservation in spend ledger')
        self.entry = self.state['fixtures'].setdefault(fixture, {'calls': 0, 'cpu_seconds': 0.0})
        self.reason = None

    def checkpoint(self):
        now = _cpu_seconds()
        elapsed = max(0.0, now - self.last_cpu)
        self.last_cpu = now
        self.state['cpu_seconds'] += elapsed
        self.entry['cpu_seconds'] += elapsed
        _write_json(self.path, self.state)

    def check(self):
        self.checkpoint()
        now = datetime.now(timezone.utc)
        reason = self.reason
        if self.clock.get('released') and now < datetime.fromisoformat(self.clock['released']):
            reason = 'before_release'
        elif self.clock.get('deadline') and now >= datetime.fromisoformat(self.clock['deadline']):
            reason = 'deadline'
        elif self.state['cpu_seconds'] >= self.cpu_limit:
            reason = 'total_cpu_cap'
        elif self.entry['cpu_seconds'] >= self.fixture_cpu_limit:
            reason = 'fixture_cpu_cap'
        elif self.state['total_calls'] >= self.solve_limit:
            reason = 'total_solve_cap'
        elif self.entry['calls'] >= self.fixture_limit:
            reason = 'fixture_solve_cap'
        if reason:
            self.reason = reason
            raise BudgetExhausted(reason)

    def reserve(self, design, lane):
        self.check()
        self.state['total_calls'] += 1
        self.entry['calls'] += 1
        self.state['active'] = {'fixture': self.fixture, 'lane': lane, 'design_hash': design.hash}
        self.checkpoint()

    def finish(self):
        self.state['active'] = None
        self.checkpoint()

    def close(self):
        try:
            self.checkpoint()
        finally:
            self.lock.close()


class _LaneOracle:
    def __init__(self, oracle, budget, lane, limit, cpu_timeout_s=None):
        self.oracle, self.budget, self.lane = oracle, budget, lane
        self.limit, self.calls, self.best_design, self.best_result = limit, 0, None, None
        self.stop_reason = None
        self.started_cpu = _cpu_seconds()
        self.cpu_timeout_s = cpu_timeout_s

    def __getattr__(self, name):
        return getattr(self.oracle, name)

    async def __call__(self, design):
        if self.calls >= self.limit:
            self.stop_reason = 'lane_solve_cap'
        elif (self.cpu_timeout_s is not None and
              _cpu_seconds() - self.started_cpu >= self.cpu_timeout_s):
            self.stop_reason = 'restart_cpu_cap'
        if self.stop_reason:
            raise BudgetExhausted(self.stop_reason)
        try:
            self.budget.reserve(design, self.lane)
        except BudgetExhausted as exc:
            self.stop_reason = str(exc)
            raise
        self.calls += 1
        try:
            result = await self.oracle(design)
            Controller.validate_result(result, design)
            if self.best_result is None or result.maximum_temperature_c < self.best_result.maximum_temperature_c:
                self.best_design, self.best_result = design, result
            return result
        finally:
            # Warm workers retain descendant CPU until reaped. Closing after each
            # call makes SELF+CHILDREN include solver AND worker startup CPU before
            # the next admission. No hidden warm-up or uncounted retry is allowed.
            close = getattr(self.oracle, 'aclose', None)
            if close is not None:
                await close()
            self.budget.finish()


async def _run_lane(initial, oracle, lane_id, seed, evaluations, shared_designs,
                    run_id, *, budget, reproduction_evaluations=0, cpu_timeout_s=None):
    started = time.perf_counter()
    rng = random.Random(seed)
    counted = _LaneOracle(oracle, budget, run_id, evaluations + reproduction_evaluations, cpu_timeout_s)
    agent_id = f'{run_id}:{seed}'
    signing_identity = Ed25519PrivateKey.generate()
    controller = Controller(initial, counted, run_id=agent_id,
                            max_oracle_calls=max(1, evaluations),
                            max_cost_microdollars=max(1, evaluations),
                            evaluation_ceiling_microdollars=1, max_attempts=1,
                            lane_ids=(lane_id,), minimum_improvement_c=0)
    controller.register(agent_id, signing_identity)
    controller.bind_lane(lane_id, agent_id)
    init_evaluations = search_count = noop_evaluations = 0
    reproductions = []
    counts = {op: 0 for op in OPERATORS}
    rewards = {op: 0.0 for op in OPERATORS}
    stagnation = 0
    improved_last = False
    current_design = initial
    try:
        # Greedy starts at the fixture layout. Other lanes share up to four
        # initial designs; ALL of these calls are inside the 28-search budget.
        shared = [] if lane_id == 'greedy' else shared_designs[1:evaluations]
        await controller.initialize(shared_initial_designs=shared)
        init_evaluations = counted.calls
        current_design, current_temperature = controller.design, controller.best_temperature
        attempts = 0
        while counted.calls < evaluations:
            attempts += 1
            if attempts > evaluations * 128:
                raise RuntimeError(f'{lane_id} could not fill its search budget')
            before_calls = counted.calls
            before_best = counted.best_result.maximum_temperature_c
            progress = counted.calls / max(1, evaluations - 1)
            scale = 0.5 * (0.05 / 0.5) ** progress
            state = dict(lane_id=lane_id, seed=seed, evaluations_completed=counted.calls,
                         evaluations_remaining=evaluations-counted.calls,
                         best_temperature_c=before_best, current_temperature_c=current_temperature,
                         stagnation=stagnation, improved_last=improved_last,
                         temperature_scale_c=scale, counts=counts, rewards=rewards)
            if lane_id == 'simulated_annealing':
                operator = rng.choices(OPERATORS, (7, 2, 1))[0]
            elif lane_id == 'ucb1':
                operator, _ = _choose_ucb1(counts, rewards, counted.calls + 1, rng)
            elif lane_id == 'signal_portfolio':
                operator, _ = _signal_portfolio(state)
                if operator == 'stop':
                    break
            elif lane_id in ('random', 'greedy'):
                operator = rng.choice(OPERATORS)
            else:
                raise ValueError(f'unknown lane: {lane_id}')
            parent = controller.design if lane_id in ('random', 'ucb1') else current_design
            candidate, operation, args = _candidate(parent, operator, rng, oracle)
            noop_evaluations += int(candidate.hash == parent.hash)
            proposal = controller.proposal(agent_id, signing_identity, controller.mint_task(agent_id),
                                           operation, args, lane_id=lane_id, parent_hash=parent.hash,
                                           model_id='slab039', tool_hash=controller.problem_contract_hash)
            outcome = await controller.submit(proposal)
            if counted.stop_reason:
                raise BudgetExhausted(counted.stop_reason)
            if outcome.status == 'failed' or controller.stopped:
                raise RuntimeError(f'{lane_id} oracle/controller failure: {outcome.reason}')
            temperature = outcome.temperature_c
            if temperature is not None:
                counts[operator] += counted.calls - before_calls
                rewards[operator] += max(0, before_best - temperature)
                delta = temperature - current_temperature
                if delta < 0 or (lane_id == 'simulated_annealing' and
                                 (delta == 0 or rng.random() < math.exp(-delta / scale))):
                    current_design, current_temperature = candidate, temperature
            improved_last = counted.best_result.maximum_temperature_c < before_best
            stagnation = 0 if improved_last else stagnation + 1
        search_count = counted.calls
        # Four fresh oracle calls of the frozen search winner, not cache reads
        # and not more proposals. The same allocation admits each call.
        winner = counted.best_design
        for _ in range(reproduction_evaluations):
            reproduced = await counted(winner)
            reproductions.append({'design_hash': winner.hash,
                                  'temperature_c': reproduced.maximum_temperature_c})
    except BudgetExhausted:
        if not init_evaluations:
            init_evaluations = counted.calls
        if not search_count:
            search_count = min(counted.calls, evaluations)
    finally:
        controller.log.close()
    best = counted.best_result
    return dict(seed=seed, best_temperature_c=None if best is None else best.maximum_temperature_c,
                best_design_hash=None if best is None else counted.best_design.hash,
                best_design=None if best is None else asdict(counted.best_design),
                current_design_hash=current_design.hash,
                evaluation_count=counted.calls, evaluation_admissions=controller.calls,
                search_evaluation_count=search_count, reproduction_evaluation_count=len(reproductions),
                reproductions=reproductions, init_evaluations=init_evaluations,
                total_evaluations_including_init=counted.calls, noop_evaluations=noop_evaluations,
                wall_time_s=time.perf_counter()-started, cpu_seconds=_cpu_seconds()-counted.started_cpu,
                cpu_exhausted='cpu' in (counted.stop_reason or ''), stop_reason=counted.stop_reason,
                complete=counted.calls == evaluations + reproduction_evaluations,
                solver_version=None if best is None else best.solver_version,
                problem_hash=None if best is None else best.problem_hash)


async def _run_reducer_lane(initial, oracle, lane_id, seed, evaluations, shared_designs, run_id,
                            *, budget, reproduction_evaluations=0):
    return await _run_lane(initial, oracle, lane_id, seed, evaluations, shared_designs, run_id,
                           budget=budget, reproduction_evaluations=reproduction_evaluations)


async def _run_diagnostic_lane(initial, oracle, lane_id, seed, evaluations, shared_designs, run_id,
                               *, budget):
    return await _run_lane(initial, oracle, lane_id, seed, evaluations, shared_designs, run_id, budget=budget)


async def _run_long_sa(initial, oracle, seed, max_evaluations, cpu_timeout_s, shared_designs, run_id,
                       *, budget):
    return await _run_lane(initial, oracle, 'simulated_annealing', seed, max_evaluations,
                           shared_designs, run_id, budget=budget, cpu_timeout_s=cpu_timeout_s)


async def run_headroom(fixture: str, mesh_error: float | None, prereg_path: str | Path,
                       output_dir: str | Path | None = None,
                       j32_values: list[float] | None = None,
                       j64_values: list[float] | None = None,
                       budget_path: str | Path | None = None) -> dict:
    """Run reducers, long SA, then optional diagnostics under one durable budget."""
    prereg = _parse_prereg(prereg_path)
    if fixture != prereg['fixture']:
        raise ValueError('fixture differs from preregistration')
    if j32_values is not None or j64_values is not None:
        _, _, mesh_error = _gate_pass_dynamic(0, 0, j32_values, j64_values)
    _validate_mesh_error(mesh_error)
    declared_mesh = prereg.get('mesh_error', {}).get(fixture)
    if declared_mesh is not None and declared_mesh.get('e_c') != mesh_error:
        raise ValueError('mesh error is pending or differs from fixture preregistration')
    cheap_cfg = prereg.get('reducer_methods', prereg.get('cheap_methods', {}))
    reducer_methods = tuple(cheap_cfg['methods'])
    diag_methods = tuple(prereg.get('extra_diagnostics', {}).get('methods', []))
    seeds = tuple(cheap_cfg['seeds'])
    evaluations = cheap_cfg.get('search_evaluations_per_method', cheap_cfg.get('evaluations_per_method'))
    reproduction_evals = cheap_cfg.get('reproduction_evaluations_per_method', 0)
    long_cfg = prereg['long_sa']
    long_seeds = tuple(long_cfg['seeds'])
    max_evals = long_cfg['max_evaluations_per_restart']
    if (not seeds or not long_seeds or not reducer_methods or evaluations < 1 or
            max_evals < 1 or reproduction_evals < 0):
        raise ValueError('empty or invalid declared evaluation schedule')
    output_dir = Path(output_dir) if output_dir is not None else Path(prereg_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    budget = SolveBudget(budget_path or Path(prereg_path).parent / 'SPEND.json', fixture, prereg)
    started_at = datetime.now(timezone.utc).isoformat()
    starting_calls = budget.state['total_calls']
    starting_cpu = budget.state['cpu_seconds']
    from sundai_hotspot.tap_oracle import HotSpotOracle

    oracle = None
    all_reducer_results, all_diag_results, long_sa_results = [], [], []
    diagnostic_skip_reason = None
    try:
        grid = prereg['grid']
        oracle = HotSpotOracle(grid, grid, fixture=fixture)
        initial = oracle.design_from_centers(TAP_INITIAL_CENTERS)
        def shared_initials(seed, count):
            try:
                budget.check()
            except BudgetExhausted:
                return [initial]
            return _shared_designs(initial, oracle, seed, min(3, count - 1))

        for method in reducer_methods:
            for seed in seeds:
                lane_seed = seed + 7919 * (list(reducer_methods).index(method) + 1)
                shared_designs = shared_initials(seed, evaluations)
                result = await _run_reducer_lane(
                    initial, oracle, method, lane_seed, evaluations, shared_designs,
                    f'slab039-{fixture}-{method}-{seed}', budget=budget,
                    reproduction_evaluations=reproduction_evals)
                result.update(method=method, category='reducer', prereg_seed=seed)
                all_reducer_results.append(result)

        # All four declared reference restarts take precedence over diagnostics.
        for seed in long_seeds:
            shared_designs = shared_initials(seed, max_evals)
            result = await _run_long_sa(initial, oracle, seed, max_evals,
                                        long_cfg['max_cpu_minutes'] * 60, shared_designs,
                                        f'slab039-{fixture}-long-sa-{seed}', budget=budget)
            long_sa_results.append(result)

        declared_complete = all(r['complete'] for r in all_reducer_results + long_sa_results)
        if declared_complete:
            for method in diag_methods:
                for seed in seeds:
                    try:
                        budget.check()
                    except BudgetExhausted as exc:
                        diagnostic_skip_reason = str(exc)
                        break
                    lane_seed = seed + 7919 * (len(reducer_methods) + list(diag_methods).index(method) + 1)
                    shared_designs = shared_initials(seed, evaluations)
                    result = await _run_diagnostic_lane(
                        initial, oracle, method, lane_seed, evaluations, shared_designs,
                        f'slab039-{fixture}-{method}-{seed}', budget=budget)
                    result.update(method=method, category='extra_diagnostic', prereg_seed=seed)
                    all_diag_results.append(result)
        else:
            diagnostic_skip_reason = 'declared_runs_incomplete'
    finally:
        try:
            if oracle is not None:
                close = getattr(oracle, 'aclose', None)
                if close is not None:
                    await close()
        finally:
            budget.close()

    reducer_medians, all_method_all_bests = {}, {}
    for method in reducer_methods:
        bests = [r['best_temperature_c'] for r in all_reducer_results
                 if r['method'] == method and r['best_temperature_c'] is not None]
        all_method_all_bests[method] = bests
        reducer_medians[method] = statistics.median(bests) if bests else None
    finite_medians = [v for v in reducer_medians.values() if v is not None]
    cheap_median = min(finite_medians) if finite_medians else None
    all_results = all_reducer_results + long_sa_results + all_diag_results
    all_bests = [r['best_temperature_c'] for r in all_results if r['best_temperature_c'] is not None]
    best = min(all_bests) if all_bests else None
    all_method_medians = dict(reducer_medians)
    for method in diag_methods:
        bests = [r['best_temperature_c'] for r in all_diag_results
                 if r['method'] == method and r['best_temperature_c'] is not None]
        if bests:
            all_method_all_bests[method] = bests
            all_method_medians[method] = statistics.median(bests)
    numeric_pass = False
    gap = None
    if cheap_median is not None and best is not None:
        numeric_pass, gap = _gate_pass(cheap_median, best, mesh_error, prereg['rule']['k'])
    long_sa_exhausted = any(r['stop_reason'] is not None for r in long_sa_results)
    long_sa_partial = any(not r['complete'] for r in long_sa_results)
    verdict = ('INCONCLUSIVE' if not declared_complete else 'PASS' if numeric_pass else 'FAIL')
    reducer_bests = [r['best_temperature_c'] for r in all_reducer_results if r['best_temperature_c'] is not None]
    result = {
        'schema': 'slab-039-result-v3', 'prereg_schema': prereg['schema'],
        'prereg_digest_sha256': _compute_prereg_digest(prereg_path),
        'runner_sha256': _compute_prereg_digest(__file__),
        'fixture': fixture, 'grid': grid, 'mesh_error_c': mesh_error,
        'mesh_error_source': 'provided' if j32_values is None else 'dynamic from J32/J64',
        'started_at': started_at, 'finished_at': datetime.now(timezone.utc).isoformat(),
        'k': prereg['rule']['k'], 'verdict': verdict, 'passed': verdict == 'PASS',
        'numeric_threshold_met': numeric_pass, 'gap_c': gap,
        'threshold_c': prereg['rule']['k'] * mesh_error,
        'cheap_median_c': cheap_median, 'best_c': best,
        'spread_across_seeds_c': max(reducer_bests)-min(reducer_bests) if reducer_bests else None,
        'reducer_methods': list(reducer_methods), 'extra_diagnostics': list(diag_methods),
        'cheap_method_medians_c': all_method_medians, 'cheap_method_all_bests_c': all_method_all_bests,
        'reducer_results': all_reducer_results, 'extra_diagnostic_results': all_diag_results,
        'diagnostic_skip_reason': diagnostic_skip_reason, 'long_sa_results': long_sa_results,
        'long_sa_exhausted': long_sa_exhausted, 'long_sa_partial': long_sa_partial,
        'aggregate_evaluations': budget.state['total_calls'] - starting_calls,
        'cpu_seconds': budget.state['cpu_seconds'] - starting_cpu,
        'allocation_spend': budget.state,
        'cpu_accounting': 'getrusage SELF+CHILDREN; workers reaped after every call; includes startup',
        'search_evaluations': evaluations, 'reproduction_evaluations': reproduction_evals,
    }
    _write_json(output_dir / 'RESULT.json', result)
    _write_report(output_dir / 'REPORT.md', result, prereg, cheap_cfg)
    return result


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)



def _write_report(path: Path, result: dict, prereg: dict, cheap_cfg: dict) -> None:
    def number(value):
        return 'unavailable' if value is None else f'{value:.6f}'

    lines = [f"# SLAB-039 Headroom Report: {result['fixture']}", '',
             f"**Verdict: {result['verdict']}**", '',
             f"Run: {result['started_at']} to {result['finished_at']}.",
             f"Preregistration SHA256: `{result['prereg_digest_sha256']}`.", '',
             f"Mesh error: {number(result['mesh_error_c'])} C; k = {result['k']}; "
             f"threshold = {number(result['threshold_c'])} C.",
             f"Gap = cheap median {number(result['cheap_median_c'])} minus best "
             f"{number(result['best_c'])} = {number(result['gap_c'])} C.",
             f"Reducer spread across seeds: {number(result['spread_across_seeds_c'])} C.", '',
             '## Reducer methods', '',
             '| Method | Median best C | Min C | Max C |', '|---|---:|---:|---:|']
    for method in result['reducer_methods']:
        bests = result['cheap_method_all_bests_c'][method]
        lines.append(f"| {method} | {number(result['cheap_method_medians_c'][method])} | "
                     f"{number(min(bests) if bests else None)} | {number(max(bests) if bests else None)} |")
    lines += ['', 'The gate uses the lowest reducer median. Each seed receives '
              f"{result['search_evaluations']} search calls, including initialize() and any shared designs, "
              f"then {result['reproduction_evaluations']} fresh evaluations of the frozen search winner. "
              'Greedy starts at the fixture initial layout and accepts only strict improvements.', '',
              '## Long SA', '', '| Seed | Calls | Best C | CPU seconds | Stop reason |',
              '|---|---:|---:|---:|---|']
    for sa in result['long_sa_results']:
        lines.append(f"| {sa['seed']} | {sa['evaluation_count']} | {number(sa['best_temperature_c'])} | "
                     f"{sa['cpu_seconds']:.3f} | {sa['stop_reason'] or 'completed'} |")
    lines += ['', '## Spend', '',
              f"Actual oracle calls this run: {result['aggregate_evaluations']}; "
              f"CPU: {result['cpu_seconds']:.3f} seconds ({result['cpu_seconds']/60:.3f} minutes).",
              f"Accounting: {result['cpu_accounting']}.",
              'The durable ledger reserves and fsyncs before every call, including initialization and reproduction. '
              'Caps are 4,768 calls / 24 CPU minutes per fixture and 9,700 calls / 48 CPU minutes across fixtures. '
              'An in-flight evaluation may cross the CPU limit; the next call is refused. '
              'A crash with an outstanding reservation fails closed pending reconciliation.', '',
              f"Extra diagnostics: {len(result['extra_diagnostic_results'])} runs; "
              f"skip reason: {result['diagnostic_skip_reason'] or 'none'}. "
              'Diagnostics run only after all declared runs and cannot change the reducer median.', '']
    if result['verdict'] == 'INCONCLUSIVE':
        lines.append('At least one declared run did not complete. This result cannot establish protocol PASS or FAIL.')
    elif result['verdict'] == 'FAIL':
        lines.append('The declared search did not establish headroom at this mesh error; no LLM lane is authorized by this result.')
    else:
        lines.append('The declared search established the preregistered headroom threshold.')
    lines += ['', 'micro150 was not run; its own mesh error is still required.', '']
    path.write_text('\n'.join(lines), encoding='utf-8', newline='\n')


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
    parser.add_argument('--budget', type=Path, default=None,
                        help='shared durable allocation ledger (default: beside prereg)')
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
        budget_path=args.budget,
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
