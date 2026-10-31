"""Equal-budget, signed strategy-lane experiments over a trusted simulator."""
from __future__ import annotations

import math
import random
import re
import time
from typing import Awaitable, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

if __package__:
    from .controller import Controller, Design, FlightRecord, ThermalResult, digest, public_hex
    from .trust import CERTIFICATE_LIFETIME_SECONDS, certify_lane
else:
    from controller import Controller, Design, FlightRecord, ThermalResult, digest, public_hex
    from trust import CERTIFICATE_LIFETIME_SECONDS, certify_lane


LANE_IDS = ("random", "simulated_annealing", "ucb1", "signal_portfolio")
# The frozen lanes keep their three operators. "rotate" (SLAB-048) is a further move that
# _candidate understands; a new protocol opts in by declaring it, which changes no frozen run.
OPERATORS = ("local_move", "swap", "global_resample")
ROTATE_OPERATOR = "rotate"
SIGNAL_CHOICES = (*OPERATORS, "stop")


def _candidate(parent: Design, operator: str, rng: random.Random, oracle):
    checker = getattr(oracle, "centers_for", None)
    tap_grid = callable(checker)
    step = 1.0 if tap_grid else 0.5

    def accept(operation, args):
        try:
            candidate = parent.apply(operation, args)
            if callable(checker):
                checker(candidate)
            return candidate, operation, args
        except (ValueError, TypeError, KeyError, OverflowError):
            return None

    ids = [chiplet.id for chiplet in parent.chiplets]
    if operator == "local_move":
        for _ in range(64):
            chiplet = rng.choice(parent.chiplets)
            x, y = parent.positions[ids.index(chiplet.id)]
            dx, dy = rng.choice((-2 * step, -step, step, 2 * step)), rng.choice((-2 * step, -step, step, 2 * step))
            found = accept("move", {"chiplet": chiplet.id, "x_mm": x + dx, "y_mm": y + dy})
            if found:
                return found
    elif operator == "swap" and len(ids) >= 2:
        for _ in range(32):
            a, b = rng.sample(ids, 2)
            found = accept("swap", {"a": a, "b": b})
            if found:
                return found
    elif operator == "global_resample":
        for _ in range(512):
            positions = {}
            for chiplet in parent.chiplets:
                min_x, max_x = chiplet.width_mm / 2 + 0.5, parent.width_mm - chiplet.width_mm / 2 - 0.5
                min_y, max_y = chiplet.height_mm / 2 + 0.5, parent.height_mm - chiplet.height_mm / 2 - 0.5
                xs = _grid_values(min_x, max_x, step)
                ys = _grid_values(min_y, max_y, step)
                positions[chiplet.id] = [rng.choice(xs) - chiplet.width_mm / 2,
                                         rng.choice(ys) - chiplet.height_mm / 2]
            found = accept("place", {"positions": positions})
            if found:
                return found
    elif operator == ROTATE_OPERATOR:
        # Turn one non-square die 90 degrees about its centre; try each such die once, in a seeded order.
        turnable = [chiplet.id for chiplet in parent.chiplets if chiplet.width_mm != chiplet.height_mm]
        for chiplet_id in rng.sample(turnable, len(turnable)):
            found = accept("rotate", {"chiplet": chiplet_id})
            if found:
                return found

    # A legal no-op is preferable to turning a finite search budget into an
    # unbounded geometry-rejection loop on a tightly packed benchmark.
    positions = {chiplet.id: list(parent.positions[index]) for index, chiplet in enumerate(parent.chiplets)}
    found = accept("place", {"positions": positions})
    if found:
        return found
    raise ValueError(f"could not construct a legal {operator} proposal")


def _grid_values(minimum: float, maximum: float, step: float) -> tuple[float, ...]:
    first = math.ceil((minimum - 1e-9) / step)
    last = math.floor((maximum + 1e-9) / step)
    return tuple(index * step for index in range(first, last + 1))


def _choose_ucb1(counts: dict[str, int], rewards: dict[str, float], rng: random.Random) -> str:
    untried = [operator for operator in OPERATORS if counts[operator] == 0]
    if untried:
        return untried[0]
    total = sum(counts.values())
    scores = {operator: rewards[operator] / counts[operator] +
              math.sqrt(2 * math.log(total) / counts[operator]) for operator in OPERATORS}
    best = max(scores.values())
    return rng.choice([operator for operator, score in scores.items() if score == best])


def _signal_portfolio(state: dict) -> tuple[str, str]:
    """Deterministic local signal policy; TFL-06 may inject the live router."""
    stagnation = state.get("stagnation_count", state.get("stagnation", 0))
    if stagnation >= 2 and state["evaluations_remaining"] > 1:
        return "global_resample", "stagnation-triggered exploration"
    if state["improved_last"]:
        return "local_move", "continue a productive local search"
    if state["evaluations_remaining"] <= 2:
        return "swap", "use the bounded end-of-budget operator"
    return "local_move", "deterministic local-search fallback"


def _verified_signal_history(controller: Controller, limit=12) -> list[dict]:
    """Return a bounded history built only from controller-verified oracle receipts."""
    history = []

    def add(design_hash, thermal):
        if (not isinstance(design_hash, str) or design_hash not in controller.verified_temperatures or
                not isinstance(thermal, dict)):
            return
        temperature = thermal.get("maximum_temperature_c")
        if temperature != controller.verified_temperatures[design_hash]:
            return
        wirelength = thermal.get("wirelength_mm")
        wire_metric = thermal.get("wire_metric")
        if (not isinstance(wirelength, (int, float)) or isinstance(wirelength, bool) or
                not math.isfinite(wirelength)):
            wirelength, wire_metric = None, None
        elif not isinstance(wire_metric, str):
            wire_metric = None
        history.append({"design_hash": design_hash, "tmax_c": float(temperature),
                        "wirelength_mm": None if wirelength is None else float(wirelength),
                        "wire_metric": wire_metric})

    for event in controller.log.events:
        payload = event.get("payload", {})
        if event.get("event") == "baseline":
            for sample in payload.get("shared_initial_samples", []):
                add(sample.get("design_hash"), sample.get("thermal"))
        elif event.get("event") == "oracle_result":
            add(payload.get("candidate_hash"), payload.get("thermal"))
    unique = []
    seen = set()
    for item in history:
        if item["design_hash"] not in seen:
            unique.append(item)
            seen.add(item["design_hash"])
    return unique if limit is None else unique[-limit:]


def _signal_choice_result(response, state):
    """Normalize untrusted router output into an allowlisted advisory record."""
    fallback = {"route": None, "reason": "router unavailable; deterministic fallback",
                "provider_called": False, "input_hash": digest(state),
                "output_hash": None, "probabilities": None, "confidence": None,
                "duration_ms": 0.0, "retry_count": 0,
                "input_tokens": None, "output_tokens": None}
    if isinstance(response, tuple) and len(response) == 2:
        route, reason = response
        if route not in OPERATORS:
            return fallback
        return {**fallback, "route": route,
                "reason": str(reason)[:160] if isinstance(reason, str) else "advisory operator"}
    if not isinstance(response, dict):
        return fallback

    route = response.get("route")
    provider_called = response.get("provider_called") is True
    probabilities = response.get("probabilities")
    confidence = response.get("confidence")
    invalid_advice = route is not None and route not in SIGNAL_CHOICES
    if route is not None and route not in SIGNAL_CHOICES:
        route = None
    if probabilities is not None:
        if (not isinstance(probabilities, dict) or set(probabilities) != set(SIGNAL_CHOICES) or
                not all(isinstance(value, (int, float)) and not isinstance(value, bool) and
                        math.isfinite(value) and 0 <= value <= 1 for value in probabilities.values()) or
                abs(sum(probabilities.values()) - 1.0) > 0.01):
            route, probabilities, confidence = None, None, None
            invalid_advice = True
    if confidence is not None and (not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or
                                   not math.isfinite(confidence) or not 0 <= confidence <= 1):
        route, probabilities, confidence = None, None, None
        invalid_advice = True
    if provider_called and route is not None and probabilities is None:
        route, confidence = None, None
        invalid_advice = True

    input_hash = response.get("input_hash")
    if not isinstance(input_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", input_hash):
        input_hash = fallback["input_hash"]
    output_hash = response.get("output_hash")
    if not isinstance(output_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", output_hash):
        response_reason = response.get("reason")
        output_hash = digest({"route": route, "probabilities": probabilities,
                              "confidence": confidence,
                              "reason": response_reason[:160] if isinstance(response_reason, str) else None})
    duration_ms = response.get("duration_ms", 0.0)
    if (not isinstance(duration_ms, (int, float)) or isinstance(duration_ms, bool) or
            not math.isfinite(duration_ms) or duration_ms < 0):
        duration_ms = 0.0
    retry_count = response.get("retry_count", 0)
    if not isinstance(retry_count, int) or isinstance(retry_count, bool) or retry_count not in (0, 1):
        retry_count = 0
    reason = response.get("reason")
    if invalid_advice:
        reason = "invalid advisory response; deterministic fallback"
    usage = {}
    for field in ("input_tokens", "output_tokens"):
        value = response.get(field)
        usage[field] = value if (isinstance(value, int) and not isinstance(value, bool) and value >= 0) else None
    return {"route": route, "reason": reason[:160] if isinstance(reason, str) else fallback["reason"],
            "provider_called": provider_called, "input_hash": input_hash, "output_hash": output_hash,
            "probabilities": probabilities, "confidence": confidence,
            "duration_ms": float(duration_ms), "retry_count": retry_count, **usage}


def plate_initial_design() -> Design:
    """The four-chiplet synthetic plate layout used by the controller demo."""
    if __package__:
        from .controller import Chiplet
    else:
        from controller import Chiplet

    return Design(25, 25, 0.5,
                  tuple(Chiplet(name, size, size) for name, size in
                        (("compute-a", 6), ("compute-b", 6), ("memory-a", 5), ("memory-b", 5))),
                  ((2, 2), (9, 2), (2, 10), (9, 10)))


async def run_four_lanes(initial: Design, oracle: Callable[[Design], Awaitable[ThermalResult]], *,
                         service_key: Ed25519PrivateKey, run_id="tfl05", seed=1, evaluations_per_lane=4,
                         evaluation_ceiling_microdollars=1, shared_sample_count=3,
                         signal_router=None) -> dict:
    """Run four independently signed lanes against one initial design pool.

    One shared design pool is generated for all lanes. Each lane's controller
    independently evaluates that pool through its own oracle before proposals;
    initialization does not consume the proposal budget. Each lane has its own
    identity, task grants, evaluation ceiling, and verifiable flight record.
    """
    if (not isinstance(evaluations_per_lane, int) or isinstance(evaluations_per_lane, bool) or
            evaluations_per_lane < 1):
        raise ValueError("evaluations_per_lane must be a positive integer")
    if (not isinstance(shared_sample_count, int) or isinstance(shared_sample_count, bool) or
            shared_sample_count < 0):
        raise ValueError("shared_sample_count must be a nonnegative integer")
    if (not isinstance(evaluation_ceiling_microdollars, int) or
            isinstance(evaluation_ceiling_microdollars, bool) or evaluation_ceiling_microdollars <= 0):
        raise ValueError("evaluation ceiling must be a positive integer")

    # The entry point supplies signing authority explicitly; the library never reads env.
    if not isinstance(service_key, Ed25519PrivateKey):
        raise ValueError("an Ed25519 service_key is required")
    certificate_expiry = int(time.time()) + CERTIFICATE_LIFETIME_SECONDS

    shared_designs = _shared_designs(initial, oracle, seed, shared_sample_count)
    sample_hashes = tuple(design.hash for design in shared_designs)

    lane_results = {}
    for lane_index, lane_id in enumerate(LANE_IDS):
        lane_started_at = time.perf_counter()
        lane_seed = seed + 7919 * (lane_index + 1)
        rng = random.Random(lane_seed)
        agent_id = f"{run_id}:{lane_id}"
        key = Ed25519PrivateKey.generate()
        controller = Controller(
            initial, oracle, run_id=f"{run_id}:{lane_id}",
            max_oracle_calls=evaluations_per_lane,
            max_cost_microdollars=evaluations_per_lane * evaluation_ceiling_microdollars,
            evaluation_ceiling_microdollars=evaluation_ceiling_microdollars,
            max_attempts=1, lane_ids=(lane_id,), minimum_improvement_c=0.05,
        )
        certificate = certify_lane(service_key, run_id, lane_id, controller.log.public_key, certificate_expiry)
        controller.register(agent_id, key)
        controller.bind_lane(lane_id, agent_id)
        await controller.initialize(shared_initial_designs=shared_designs[1:])

        current_design = controller.design
        current_temperature = controller.best_temperature
        counts = {operator: 0 for operator in OPERATORS}
        rewards = {operator: 0.0 for operator in OPERATORS}
        stagnation = 0
        improved_last = False
        signal_advice_active = True
        noop_evaluations = 0
        proposal_attempts = 0
        max_proposal_attempts = evaluations_per_lane * 128

        while controller.actual_oracle_calls < evaluations_per_lane:
            proposal_attempts += 1
            if proposal_attempts > max_proposal_attempts:
                raise RuntimeError(f"{lane_id} could not fill its equal evaluation budget")
            state = {
                "lane_id": lane_id,
                "seed": seed,
                "evaluations_completed": controller.actual_oracle_calls,
                "evaluations_remaining": evaluations_per_lane - controller.actual_oracle_calls,
                "best_temperature_c": controller.lane_best[lane_id][1],
                "current_temperature_c": current_temperature,
                "stagnation": stagnation,
                "improved_last": improved_last,
            }
            if lane_id == "signal_portfolio":
                verified_history = _verified_signal_history(controller, limit=None)
                current_sample = next((sample for sample in reversed(verified_history)
                                       if sample["design_hash"] == current_design.hash), None)
                state = {
                    "lane_id": lane_id,
                    "verified_history": verified_history[-12:],
                    "evaluations_completed": controller.actual_oracle_calls,
                    "evaluations_remaining": evaluations_per_lane - controller.actual_oracle_calls,
                    "stagnation_count": stagnation,
                    "stagnation": stagnation,
                    "current_tmax_c": current_temperature,
                    "current_wirelength_mm": current_sample["wirelength_mm"] if current_sample else None,
                    "current_wire_metric": current_sample["wire_metric"] if current_sample else None,
                    "horizon_evaluations": 1,
                    "improved_last": improved_last,
                }
            if lane_id == "simulated_annealing":
                # Geometric cooling from 0.5 C to 0.05 C over the lane budget.
                # Initialization calls are outside the proposal budget; the
                # annealing schedule must span proposal evaluations only.
                progress = (1.0 if evaluations_per_lane == 1 else
                            controller.calls / (evaluations_per_lane - 1))
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
            else:
                deterministic_operator, deterministic_reason = _signal_portfolio(state)
                response = None
                if signal_router is not None and signal_advice_active:
                    try:
                        response = signal_router(state)
                        response = await response if hasattr(response, "__await__") else response
                    except Exception as exc:
                        response = {"route": None, "reason": "router failure; deterministic fallback",
                                    "provider_called": False, "error_type": type(exc).__name__}
                elif not signal_advice_active:
                    response = {"route": None, "reason": "signal-layer advice stopped for this lane",
                                "provider_called": False}

                decision = _signal_choice_result(response, state)
                requested_choice = decision["route"]
                stop_requested = requested_choice == "stop"
                if requested_choice in OPERATORS:
                    operator = requested_choice
                    selection_reason = "signal-layer CHOICE advised " + operator
                else:
                    operator, selection_reason = deterministic_operator, deterministic_reason
                if stop_requested:
                    # Stop is advisory for this lane's provider calls, not an early
                    # exit from the TFL-05 equal-evaluation protocol.
                    signal_advice_active = False
                    selection_reason = "signal layer requested stop; deterministic equal-budget continuation"
                if decision["output_hash"] is None:
                    decision["output_hash"] = digest({
                        "requested_choice": requested_choice,
                        "applied_operator": operator,
                        "probabilities": decision["probabilities"],
                        "confidence": decision["confidence"],
                        "reason": decision["reason"],
                    })
                controller.log.append(
                    "signal_decision", lane_id=lane_id,
                    evaluations_completed=state["evaluations_completed"],
                    horizon_evaluations=1, input_hash=decision["input_hash"],
                    output_hash=decision["output_hash"], requested_choice=requested_choice,
                    applied_operator=operator, stop_requested=stop_requested,
                    provider_called=decision["provider_called"],
                    probabilities=decision["probabilities"], confidence=decision["confidence"],
                    latency_ms=decision["duration_ms"], retry_count=decision["retry_count"],
                    input_tokens=decision["input_tokens"], output_tokens=decision["output_tokens"],
                    fallback_reason=(decision["reason"] if requested_choice is None else None),
                    state=state)
                parent = controller.lane_best[lane_id][0]

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
                                           model_id=f"tfl05-{lane_id}", lane_id=lane_id,
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
                # Binary reward keeps standard UCB1's [0, 1] assumption and
                # makes each arm's score independent of temperature units.
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

        if controller.calls != evaluations_per_lane:
            raise RuntimeError(f"{lane_id} evaluation admissions differ from its target")
        if controller.reserved:
            raise RuntimeError(f"{lane_id} left an evaluation reservation open")
        controller.log.close()
        valid_record = FlightRecord.verify(controller.log.events, controller.log.public_key)
        if not valid_record:
            raise RuntimeError(f"{lane_id} flight record did not verify")
        lane_results[lane_id] = {
            "agent_id": agent_id,
            "identity_public_key": public_hex(key),
            "run_id": controller.run_id,
            "shared_initial_sample_hashes": sample_hashes,
            "evaluation_count": controller.actual_oracle_calls,
            "evaluation_admissions": controller.calls,
            "spent_microdollars": controller.spent,
            "best_temperature_c": controller.best_temperature,
            "best_design_hash": controller.design.hash,
            "noop_evaluations": noop_evaluations,
            "wall_time_s": time.perf_counter() - lane_started_at,
            "record_public_key": controller.log.public_key,
            "record_certificate": certificate,
            "record_valid": valid_record,
            "record": controller.log.events,
        }

    counts = {result["evaluation_count"] for result in lane_results.values()}
    if counts != {evaluations_per_lane}:
        raise RuntimeError("lanes did not complete identical evaluation counts")
    return {
        "run_id": run_id,
        "seed": seed,
        "lane_ids": LANE_IDS,
        "shared_initial_sample_hashes": sample_hashes,
        "shared_initial_sample_count": len(shared_designs),
        "evaluations_per_lane": evaluations_per_lane,
        "evaluation_ceiling_microdollars": evaluation_ceiling_microdollars,
        "lane_results": lane_results,
        "evaluation_counts_equal": True,
        "flight_records_valid": all(result["record_valid"] for result in lane_results.values()),
    }


def _shared_designs(initial: Design, oracle, seed: int, count: int) -> list[Design]:
    rng = random.Random(seed)
    designs = [initial]
    seen = {initial.hash}
    source = initial
    operators = ("local_move", "swap", "global_resample")
    for sample_index in range(count):
        accepted = None
        for attempt in range(256):
            operator = operators[(sample_index + attempt) % len(operators)]
            try:
                candidate, _, _ = _candidate(source, operator, rng, oracle)
            except ValueError:
                continue
            if candidate.hash not in seen:
                accepted = candidate
                break
        if accepted is None:
            raise RuntimeError(f"could not construct shared initial sample {sample_index + 1}")
        seen.add(accepted.hash)
        designs.append(accepted)
        source = accepted
    return designs
