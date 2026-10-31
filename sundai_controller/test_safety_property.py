"""TFL-13: structural safety property test.

The property: no code path commits a design unless the simulator returned a result bound to that exact candidate
hash under the unchanged problem contract. Advisory output (signal layer, LLM, surrogate) never has commit
authority, and nothing commits after an owner STOP.

The test drives the real Controller through randomly generated event orders:
- signed, forged, tampered, replayed, held (stale), expired, ungranted and wrong-run proposals;
- simulator calls released in random order with honest, wrong-candidate, changed-contract, unconverged,
  non-finite, bad-cost, over-cost and failing results;
- STOPs, cancellations and clock jumps while calls are in flight;
- proposals built from random advisory outputs: signal-layer routes from a mocked transport, LLM moves through
  choose_advisory_operation, and surrogate predictions that claim the problem contract.
- malformed LLM-generated full-layout coordinates that must be rejected before oracle admission or commit;
- initialization from a shared pool of starting designs, sometimes with one lying or failing answer, which the
  controller must refuse rather than start from.

The ground truth is a witness wrapped around the simulator, outside the controller. It records every result the
simulator really returned. The controller's incumbent and its flight record are checked against the witness,
never trusted. test_each_injected_bypass_is_caught mutates controller.py at the real call sites and requires the
property to catch every mutant, so a green run cannot mean "the check never fires".

    python -m unittest -q test_safety_property.py
    TFL13_CASES=20000 TFL13_SEED=7 python -m unittest -q test_safety_property.py    # soak / reproduce a seed

When the controller API changes (TFL-04 onward), update the ADAPTER section and the mutant anchors. Update witness keys only when controller semantics explicitly change (such as agent-scoped proposal ids); never lower the property checks or coverage floors. A moved anchor fails loudly ("anchor not found"), never silently.
"""
import asyncio
import json
import math
import os
import random
import sys
import types
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import controller as real_controller

CASES = int(os.environ.get("TFL13_CASES", "1000"))
BASE_SEED = int(os.environ.get("TFL13_SEED", "13013"))
MUTANT_CASES = int(os.environ.get("TFL13_MUTANT_CASES", "1000"))

SOLVER, PROBLEM, EVIDENCE = "NONPHYSICAL-witness-fixture-v1", "tfl13-problem-contract-v1", "nonphysical fixture"
CONTRACT = (SOLVER, PROBLEM, EVIDENCE)
WEIGHTS = ((1.3, 0.4), (0.7, 1.1), (0.9, 0.6))
TASKS = tuple(f"t{i}" for i in range(12))          # agents are granted t0-t9; t10 and t11 are never granted
ROUTES = ("local_move", "swap", "global_resample", "stop")
RESULTS = {"honest": 45, "wrong_candidate": 12, "changed_problem": 6, "changed_solver": 5, "changed_evidence": 5,
           "unconverged": 7, "nonfinite": 4, "bad_cost": 4, "over_cost": 4, "raise": 8}
VARIANTS = {"normal": 60, "forged": 6, "tampered": 6, "ghost": 4, "wrong_run": 5, "smuggled_field": 5,
            "collide_id": 4, "collide_other_agent": 4, "hold": 10}


def true_temp(design):
    """The simulator's answer: deterministic in the placement, and lower toward the origin so commits happen."""
    return 40.0 + sum((x + 0.5) * wx + (y + 0.25) * wy for (x, y), (wx, wy) in zip(design.positions, WEIGHTS))


def shared_designs(m, rng):
    """0-3 legal translations of the initial layout: the shared starting pool every lane would receive."""
    base = initial_design(m)
    shifts = rng.sample([(dx, dy) for dx in range(-9, 3) for dy in range(-7, 5) if (dx, dy) != (0, 0)],
                        rng.randint(0, 3))
    return [m.Design(base.width_mm, base.height_mm, base.gap_mm, base.chiplets,
                     tuple((x + dx, y + dy) for x, y in base.positions)) for dx, dy in shifts]


# ── ADAPTER: the only code that knows the controller's API. TFL-04 (lanes, any verified parent, host-minted task
# ids) updates these functions; the properties below stay as they are. ───────────────────────────────────────────
def initial_design(m):
    catalog = (m.Chiplet("a", 3, 3), m.Chiplet("b", 2, 4), m.Chiplet("c", 4, 2))
    return m.Design(30, 20, 1, catalog, ((10, 8), (18, 8), (24, 14)))


def make_controller(m, oracle, rng, clock):
    ceiling = rng.choice((10, 10, 50))
    return m.Controller(initial_design(m), oracle, run_id="tfl13", max_oracle_calls=rng.randint(3, 25),
                        max_cost_microdollars=rng.choice((ceiling * 5, 10 ** 6)),
                        evaluation_ceiling_microdollars=ceiling, max_concurrency=rng.randint(1, 3),
                        max_attempts=rng.randint(1, 3), minimum_improvement_c=rng.choice((0.0, 0.05, 0.5)),
                        lane_ids=rng.choice((("default",), ("random", "annealing", "ucb1", "signal"))), clock=clock)


def cost_ceiling(c):
    return c.ceiling


def register(c, agent_id, key):
    c.register(agent_id, key, allowed_tasks=TASKS[:10])


def attach_surrogate(c, surrogate):
    # The starter has no surrogate seam, so this attribute is inert there. A controller that ever lets a surrogate
    # answer in the simulator's seat is what the "surrogate" mutant models, and the witness check must catch it.
    c.surrogate = surrogate


def propose(c, agent_id, key, task, operation, args, ttl, lane_id, parent_hash):
    return c.proposal(agent_id, key, task, operation, args, ttl=ttl, lane_id=lane_id, parent_hash=parent_hash)


def lanes(c):
    return list(c.lane_best)


def lane_best(c, lane_id):
    return c.lane_best[lane_id][0]


def incumbents(c):
    """Every globally or lane-held design, with the temperature it claims for it."""
    held = {c.design.hash: (c.design, c.best_temperature)}
    for design, temperature in c.lane_best.values():
        held[design.hash] = (design, temperature)
    return list(held.values())


def verified(c):
    """Every design the controller labels verified (any of them may be a parent), with its recorded temperature."""
    return [(design, c.verified_temperatures[h]) for h, design in c.verified_designs.items()]


def contract_of(c):
    return c.oracle_contract


async def initialize(c, shared_designs):
    """Start from the baseline plus shared designs; the controller must evaluate every one through its oracle."""
    return await c.initialize(shared_initial_designs=tuple(shared_designs))


def initialized(c):
    return c.best_temperature is not None


def flight_record(c):
    if not c.log.closed:
        c.log.close()
    return c.log.events, c.log.public_key
# ── end ADAPTER ─────────────────────────────────────────────────────────────────────────────────────────────────


def pick(rng, weights):
    return rng.choices(list(weights), list(weights.values()))[0]


def is_real(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def malformed(operation, args):
    """Advice whose coordinates are not plain finite numbers: it must be rejected, never reinterpreted."""
    if not isinstance(args, dict):
        return False
    if operation == "move":
        return any(k in args and not is_real(args[k]) for k in ("x_mm", "y_mm"))
    if operation == "place" and "positions" in args:
        positions = args["positions"]
        pairs = positions.values() if isinstance(positions, dict) else positions
        if not isinstance(pairs, (list, tuple, type({}.values()))):
            return False
        return any(not (isinstance(pair, (list, tuple)) and len(pair) == 2 and all(is_real(v) for v in pair))
                   for pair in pairs)
    return False


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]


class Case:
    """One generated event order against one controller, plus the witness that knows what the simulator said."""

    def __init__(self, m, seed, stats):
        self.m, self.seed, self.rng, self.stats = m, seed, random.Random(seed), stats
        self.now = 1_000_000.0
        self.pending = []              # [future, candidate]: simulator calls the harness has not released yet
        self.bound = {}                # candidate hash -> temperature, from results bound to that exact candidate
        self.auto = True               # initialization calls are answered at once, honestly unless planned
        self.init_plan = {}            # design hash -> result kind for one initialization call
        self.asked_at_init = set()     # design hashes the simulator was asked about during initialization
        self.trace, self.violations, self.crashes = [], [], []
        self.tasks, self.held, self.sent = [], [], []
        self.stop_snapshot = None
        self.signal_body = b""

    # ── the simulator, seen from outside ──────────────────────────────────────────────────────────────────────
    async def oracle(self, candidate):
        if self.auto:
            self.asked_at_init.add(candidate.hash)
            result = self.result(self.init_plan.get(candidate.hash, "honest"), candidate)
        else:
            future = asyncio.get_running_loop().create_future()
            self.pending.append((future, candidate))
            result = self.result(await future, candidate)
        r = result
        if (r.candidate_hash == candidate.hash and (r.solver_version, r.problem_hash, r.evidence_kind) == CONTRACT
                and r.converged is True and isinstance(r.maximum_temperature_c, float)
                and math.isfinite(r.maximum_temperature_c) and isinstance(r.cost_microdollars, int)
                and not isinstance(r.cost_microdollars, bool) and r.cost_microdollars >= 0):
            self.bound.setdefault(candidate.hash, r.maximum_temperature_c)
        return result

    def result(self, kind, cand):
        m, rng, t = self.m, self.rng, true_temp(cand)
        lower = t - rng.choice((0.001, 0.5, 5.0, 60.0))     # every lie claims an improvement
        kw = dict(solver_version=SOLVER, problem_hash=PROBLEM, evidence_kind=EVIDENCE,
                  cost_microdollars=rng.randint(0, cost_ceiling(self.c)))
        if kind == "honest":
            return m.ThermalResult(cand.hash, t, **kw)
        if kind == "wrong_candidate":
            others = [c.hash for _, c in self.pending] + [d.hash for d, _ in incumbents(self.c)]
            other = rng.choice(others + [initial_design(m).hash, "%064x" % rng.getrandbits(256)])
            return m.ThermalResult(other if other != cand.hash else "0" * 64, lower, **kw)
        if kind == "unconverged":
            return m.ThermalResult(cand.hash, lower, converged=False, **kw)
        if kind == "nonfinite":
            return m.ThermalResult(cand.hash, rng.choice((-math.inf, math.nan)), **kw)
        if kind == "bad_cost":
            kw["cost_microdollars"] = rng.choice((-1, 0.5, "1"))
            return m.ThermalResult(cand.hash, t, **kw)
        if kind == "over_cost":
            kw["cost_microdollars"] = cost_ceiling(self.c) + rng.randint(1, 100)
            return m.ThermalResult(cand.hash, t, **kw)
        if kind == "raise":
            raise RuntimeError("simulator crashed")
        field = {"changed_problem": "problem_hash", "changed_solver": "solver_version",
                 "changed_evidence": "evidence_kind"}[kind]
        kw[field] = {"problem_hash": "changed-boundary-conditions", "solver_version": "surrogate-superposition-v0",
                     "evidence_kind": "surrogate prediction"}[field]
        return m.ThermalResult(cand.hash, lower, **kw)

    def release(self):
        future, cand = self.pending.pop(self.rng.randrange(len(self.pending)))
        if future.done():                                    # its submitter was cancelled
            return
        kind = pick(self.rng, RESULTS)
        self.stats["result_" + kind] += 1
        self.trace.append(f"release {kind} {cand.hash[:8]}")
        future.set_result(kind)

    # ── advisory sources: they may say anything, and none of it may matter to acceptance ──────────────────────
    def surrogate(self, cand):
        self.stats["surrogate_predictions"] += 1
        return self.m.ThermalResult(cand.hash, true_temp(cand) - 3.0, SOLVER, problem_hash=PROBLEM,
                                    evidence_kind=EVIDENCE)

    def fake_urlopen(self, request, timeout=None):
        if self.signal_body is None:
            raise TimeoutError("signal layer timeout")
        return FakeResponse(self.signal_body)

    def signal_response(self):
        rng = self.rng
        weights = [rng.random() + 1e-3 for _ in ROUTES]
        probabilities = {r: w / sum(weights) for r, w in zip(ROUTES, weights)}
        answer = {"type": "choice", "choice": rng.choice(ROUTES), "probabilities": probabilities,
                  "confidence": rng.random()}
        body = {"model": "jev-1.13.0", "answers": {"route": answer}}
        kind = self.signal_kind = rng.choice(("valid", "valid", "valid", "smuggled", "wrong_model", "bad_choice",
                                              "bad_probabilities", "bad_confidence", "oversize", "not_json", "timeout"))
        if kind == "smuggled":
            body.update(commit=True, temperature_c=-1e9, accept_candidate="%064x" % rng.getrandbits(256))
            answer["verdict"] = "commit now"
        elif kind == "wrong_model":
            body["model"] = "jev-9.9.9"
        elif kind == "bad_choice":
            answer["choice"] = rng.choice(("commit", "force_commit", "skip_simulator"))
        elif kind == "bad_probabilities":
            answer["probabilities"] = {**probabilities, ROUTES[0]: rng.choice((1.7, -0.2, math.nan))}
        elif kind == "bad_confidence":
            answer["confidence"] = rng.choice((1.5, -1, "high"))
        elif kind == "oversize":
            return b"{" + b" " * 300_000 + b"}"
        elif kind == "not_json":
            return b"not-json"
        elif kind == "timeout":
            return None
        return json.dumps(body).encode()

    async def route(self):
        self.signal_body = self.signal_response()
        out = await self.router.route({"remaining_budget": self.rng.randint(0, 20)})
        if out.get("provider_called"):
            self.stats["signal_" + self.signal_kind] += 1      # counted only when the adapter received it
        if out.get("route") is None:
            return "local_move"  # host-owned deterministic fallback
        if out.get("route") not in ROUTES:
            self.violation(f"signal layer returned a route outside the allowlist: {out.get('route')!r}")
            return "local_move"
        return out["route"]

    def llm_output(self, force_kind=None):
        rng = self.rng
        if force_kind is None:
            ids = ("a", "b", "c")
            move = {"operation": "move", "args": {"chiplet": rng.choice(ids), "x_mm": rng.uniform(0, 26),
                                                  "y_mm": rng.uniform(0, 16)}}
            kind = rng.choice(("move", "move", "swap", "claims", "claims", "smuggled_args", "smuggled_args", "bad_op", "odd_values",
                               "not_dict", "raise", "valid_place", "valid_place", "valid_place", "misparse_place",
                               "misparse_move"))
        else:
            kind, move = force_kind, None
        return kind, self.llm_payload(kind, move)

    def llm_payload(self, kind, move):
        rng, ids = self.rng, ("a", "b", "c")
        if kind == "move":
            return move
        if kind == "swap":
            return {"operation": "swap", "args": {"a": rng.choice(ids), "b": rng.choice(ids)}}
        if kind == "place":
            return {"operation": "place", "args": {"positions": {
                "a": "11", "b": ["1", "2"], "c": [True, 1.0]}}}
        if kind == "valid_place":                            # TFL-04's full-layout operation, from the parent
            if rng.random() < 0.7:                           # a translation keeps the layout legal and cooler
                dx, dy = rng.uniform(0, 3), rng.uniform(0, 3)
                pairs = [[round(x - dx, 3), round(y - dy, 3)] for x, y in self.base.positions]
            else:
                pairs = [[round(x - rng.uniform(-2, 4), 3), round(y - rng.uniform(-2, 4), 3)]
                         for x, y in self.base.positions]
            ids_ = [c.id for c in self.base.chiplets]
            positions = dict(zip(ids_, pairs)) if rng.random() < 0.5 else pairs
            return {"operation": "place", "args": {"positions": positions}}
        if kind == "misparse_place":                         # each would MISPARSE into a legal, cooler layout
            return {"operation": "place", "args": {"positions": rng.choice((
                {"a": "11", "b": "91", "c": "17"}, ["11", "91", "17"],
                {"a": ["1", "1"], "b": [9, 1], "c": [1, 7]}, {"a": [True, True], "b": [9, 1], "c": [1, 7]}))}}
        if kind == "misparse_move":
            return {"operation": "move", "args": {"chiplet": "a", **rng.choice((
                {"x_mm": "1", "y_mm": "1"}, {"x_mm": True, "y_mm": True}, {"x_mm": "1.5", "y_mm": 1}))}}
        if kind == "claims":
            return {**move, "temperature_c": -1e9, "commit": True, "verified": True}
        if kind == "smuggled_args":
            return {"operation": "move", "args": {**move["args"], "temperature_c": -1e9, "verified": True}}
        if kind == "bad_op":
            return {"operation": rng.choice(("commit", "place", "set_best", "resize")), "args": move["args"]}
        if kind == "odd_values":
            value = rng.choice(("12", "nan", None, [1], 1e308, -0.0, True, 10 ** 400, math.inf))
            return {"operation": "move", "args": {**move["args"], rng.choice(("x_mm", "y_mm")): value}}
        if kind == "not_dict":
            return rng.choice(("move a to 0,0", ["move", "a"], None, 42))
        return rng.choice((ValueError("model refused"), TimeoutError("model timeout")))   # the provider raises it

    async def llm_advice(self, force_kind=None):
        def provider(generated):
            kind, output = generated
            async def call(request):
                self.stats["llm_" + kind] += 1                 # counted only when the provider is consulted
                if isinstance(output, Exception):
                    raise output
                return output
            return call
        provider_count = 1 if force_kind is not None else self.rng.randint(1, 3)
        providers = [(f"llm{i}", provider(self.llm_output(force_kind if i == 0 else None)))
                     for i in range(provider_count)]
        try:
            return await self.m.choose_advisory_operation(providers, {"heatmap": "summary"}, timeout_s=0.5)
        except RuntimeError:
            self.stats["llm_all_failed"] += 1
            return None

    def pick_parent(self):
        """The lane and parent a proposer builds on: usually a verified design, sometimes one that is not."""
        rng, c = self.rng, self.c
        lane = rng.choice(lanes(c))
        kind = rng.choices(("lane_best", "any_verified", "unknown_lane", "unverified", "random"), (60, 25, 4, 7, 4))[0]
        self.stats["parent_" + kind] += 1
        base = lane_best(c, lane)
        if kind == "any_verified":
            base = rng.choice(verified(c))[0]
        elif kind == "unknown_lane":
            lane = "ghost-lane"
        elif kind == "unverified" and self.pending:
            base = rng.choice(self.pending)[1]                # still in the simulator: not verified (yet)
        elif kind in ("unverified", "random"):
            return lane, base, "%064x" % rng.getrandbits(256)
        return lane, base, base.hash

    def local_move(self, design):
        rng = self.rng
        if rng.random() < 0.15:                              # a full-layout place: the whole layout, translated
            dx, dy = rng.uniform(0, 3), rng.uniform(0, 3)
            return "place", {"positions": {c.id: [round(x - dx, 3), round(y - dy, 3)]
                                           for c, (x, y) in zip(design.chiplets, design.positions)}}
        if rng.random() < 0.2:
            a, b = rng.choice(design.chiplets).id, rng.choice(design.chiplets).id
            return "swap", {"a": a, "b": b}
        # Surrogate screening: an advisory ranking of three random moves, used only to pick what to propose.
        options = []
        for _ in range(3):
            i = rng.randrange(len(design.chiplets))
            x, y = design.positions[i]
            args = {"chiplet": design.chiplets[i].id, "x_mm": round(x - rng.uniform(-2, 4), 3),
                    "y_mm": round(y - rng.uniform(-2, 4), 3)}
            try:
                options.append((self.surrogate(design.apply("move", args)).maximum_temperature_c, args))
            except (ValueError, KeyError, TypeError):
                options.append((math.inf, args))
        return "move", min(options, key=lambda o: o[0])[1]

    # ── proposals ─────────────────────────────────────────────────────────────────────────────────────────────
    async def new_proposal(self):
        route = await self.route()
        if route == "stop":
            return None
        lane, base, parent_hash = self.pick_parent()
        self.base = base
        if route == "local_move":
            operation, args = self.local_move(base)
        else:
            advice = await self.llm_advice()
            if advice is None:
                return None
            operation, args = advice["operation"], advice["args"]
        rng = self.rng
        agent_id, key = rng.choice(self.agents)
        variant = pick(rng, VARIANTS)
        self.stats["proposal_" + variant] += 1
        try:
            p = propose(self.c, agent_id, key, rng.choice(TASKS), operation, args, rng.choice((60, 60, 60, 20, 5, -1)),
                        lane, parent_hash)
            if variant == "forged":
                p = self.m.Proposal.sign(self.rogue, **p.payload)
            elif variant == "tampered":
                p.payload["args"] = {"chiplet": "a", "x_mm": 0.0, "y_mm": 0.0}
            elif variant == "ghost":
                p = propose(self.c, "ghost", self.rogue, "t0", operation, args, 60, lane, parent_hash)
            elif variant == "wrong_run":
                p = self.m.Proposal.sign(key, **{**p.payload, "run_id": "another-run"})
            elif variant == "smuggled_field":
                p = self.m.Proposal.sign(key, **p.payload, temperature_c=-1e9, simulator_result="trusted")
            elif variant == "collide_id":
                prior = next((old for old in reversed(self.sent)
                              if old.payload["agent_id"] == p.payload["agent_id"]), None)
                if prior is not None:
                    p = self.m.Proposal.sign(key, **{**p.payload, "proposal_id": prior.payload["proposal_id"]})
            elif variant == "collide_other_agent":             # legal since ids are per agent; must not cross-wire
                prior = next((old for old in reversed(self.sent)
                              if old.payload["agent_id"] != p.payload["agent_id"]), None)
                if prior is not None:
                    p = self.m.Proposal.sign(key, **{**p.payload, "proposal_id": prior.payload["proposal_id"]})
        except (ValueError, TypeError, OverflowError):
            self.stats["proposal_unsignable"] += 1           # NaN/inf/unserializable advice cannot even be signed
            return None
        if variant == "hold":
            self.held.append(p)
            return None
        return p

    def submit(self, p, label):
        if malformed(p.payload.get("operation"), p.payload.get("args")):
            self.stats["submitted_malformed"] += 1
        self.sent.append(p)
        self.tasks.append(asyncio.ensure_future(self.c.submit(p)))
        self.trace.append(f"submit#{len(self.tasks) - 1} {label} {p.payload.get('operation')} "
                          f"{json.dumps(p.payload.get('args'), default=str)[:80]}")

    # ── the properties ────────────────────────────────────────────────────────────────────────────────────────
    def violation(self, text):
        self.violations.append(text)

    def check_state(self):
        for design, claimed in incumbents(self.c):
            h = design.hash
            if h not in self.bound:
                self.violation(f"incumbent {h[:12]} has no simulator result bound to it under the problem contract")
            elif claimed != self.bound[h]:
                self.violation(f"incumbent {h[:12]} claims {claimed!r} but the simulator said {self.bound[h]!r}")
        for design, claimed in verified(self.c):              # every possible parent is held to the same rule
            h = design.hash
            if h not in self.bound:
                self.violation(f"design {h[:12]} is labelled verified without a simulator result bound to it")
            elif claimed != self.bound[h]:
                self.violation(f"verified design {h[:12]} records {claimed!r}, the simulator said {self.bound[h]!r}")
        if contract_of(self.c) != CONTRACT:
            self.violation(f"problem contract changed to {contract_of(self.c)!r}")
        if self.stop_snapshot is not None and self.snapshot() != self.stop_snapshot:
            self.violation("an incumbent changed after the owner STOP returned")

    def snapshot(self):
        return [(d.hash, t) for d, t in incumbents(self.c)]

    def check_record(self):
        events, public_key = flight_record(self.c)
        if not self.m.FlightRecord.verify(events, public_key):
            self.violation("flight record does not verify")
        admitted, results, stopped_at = {}, {}, None
        for i, e in enumerate(events):
            p = e["payload"]
            if e["event"] == "stopped" or (e["event"] == "proposal_rejected"
                                           and str(p.get("reason", "")).endswith("stopped")):
                stopped_at = i if stopped_at is None else stopped_at
            elif e["event"] == "proposal_admitted":
                admitted.setdefault((p["agent_id"], p["proposal_id"]), (p["candidate_hash"], p["operation"], p["args"]))
                if malformed(p["operation"], p["args"]):         # legality comes before any simulator spend
                    self.violation(f"malformed advice admitted to the simulator: {p['operation']} "
                                   f"{json.dumps(p['args'])[:80]}")
            elif e["event"] == "oracle_result":
                results[(p["agent_id"], p["proposal_id"], p["candidate_hash"])] = p["thermal"]
            elif e["event"] == "proposal_committed":
                proposal_key = (p.get("agent_id"), p.get("proposal_id"))
                ch = p.get("candidate_hash")
                thermal = results.get((proposal_key[0], proposal_key[1], ch))
                if stopped_at is not None:
                    self.violation(f"commit at record event {i} after a STOP at event {stopped_at}")
                if ch not in self.bound:
                    self.violation(f"committed {str(ch)[:12]} without a simulator result bound to it")
                elif p.get("temperature_c") != self.bound[ch]:
                    self.violation(f"commit claims {p.get('temperature_c')!r}, simulator said {self.bound[ch]!r}")
                proposed = admitted.get(proposal_key)
                if not proposed or proposed[0] != ch:
                    self.violation(f"commit of {str(ch)[:12]} without a matching admission")
                elif malformed(proposed[1], proposed[2]):
                    self.violation(f"malformed advice committed: {proposed[1]} {json.dumps(proposed[2])[:80]}")
                elif proposed[1] == "place":
                    self.stats["commits_place"] += 1
                if not thermal or thermal.get("candidate_hash") != ch or (thermal.get("solver_version"),
                        thermal.get("problem_hash"), thermal.get("evidence_kind")) != CONTRACT \
                        or thermal.get("maximum_temperature_c") != self.bound.get(ch):
                    self.violation(f"commit of {str(ch)[:12]} not preceded by its bound oracle_result in the record")

    # ── the run ───────────────────────────────────────────────────────────────────────────────────────────────
    async def run(self):
        m, rng = self.m, self.rng
        self.c = make_controller(m, self.oracle, rng, lambda: self.now)
        self.agents = [(f"agent{i}", Ed25519PrivateKey.generate()) for i in range(rng.randint(1, 3))]
        self.rogue = Ed25519PrivateKey.generate()
        for agent_id, key in self.agents:
            register(self.c, agent_id, key)
        async def surrogate(candidate):
            return self.surrogate(candidate)
        attach_surrogate(self.c, surrogate)
        self.router = m.JevRoutingAdapter(max_calls=rng.randint(0, 12), timeout_s=1)
        shared = shared_designs(m, rng)
        self.stats["init_shared_designs"] += len(shared)
        pool = [initial_design(m)] + shared
        lie = None
        if rng.random() < 0.10:                              # one starting design gets a lying or failing answer
            target = rng.randrange(len(pool))
            lie = rng.choice(("wrong_candidate", "unconverged", "nonfinite", "bad_cost", "raise") +
                             (("changed_problem",) if target else ()))   # the first answer defines the contract
            self.init_plan[pool[target].hash] = lie
            self.trace.append(f"initialization: {lie} answer for starting design {target}")
        try:
            await initialize(self.c, shared)
        except (ValueError, RuntimeError, TypeError) as exc:
            if lie is None:
                self.violation(f"honest initialization failed: {exc!r}")
            else:
                self.stats["init_lie_refused"] += 1
                if not self.init_plan.keys() & self.asked_at_init:
                    self.violation("initialization refused before the planned bad answer reached the simulator")
            if initialized(self.c):
                self.violation("a refused initialization left the controller initialized")
            return
        if lie is not None:                                  # every planned answer is invalid: it must be refused
            self.violation(f"initialization accepted a planned {lie} answer")
        verified_now = {design.hash: claimed for design, claimed in verified(self.c)}
        for index, design in enumerate(pool):                # the whole pool reached the simulator and was kept
            if design.hash not in self.asked_at_init:
                self.violation(f"starting design {index} never reached the simulator")
            elif verified_now.get(design.hash) != self.bound.get(design.hash):
                self.violation(f"starting design {index} is not recorded with its simulator temperature")
        agent_id, key = self.agents[0]
        malformed_advice = await self.llm_advice(force_kind="place")
        if malformed_advice is None:
            self.violation("forced malformed LLM place output did not produce advisory data")
        else:
            malformed_task = self.c.mint_task(agent_id)
            lane = lanes(self.c)[0]
            malformed_place = propose(self.c, agent_id, key, malformed_task, malformed_advice["operation"],
                                      malformed_advice["args"], 60, lane, lane_best(self.c, lane).hash)
            incumbent_hash = self.c.design.hash
            revision, calls, actual_calls = self.c.revision, self.c.calls, self.c.actual_oracle_calls
            malformed_result = await self.c.submit(malformed_place)
            self.stats["malformed_place_cases"] += 1
            self.trace.append("malformed place coordinates from LLM advisory path")
            if (malformed_result.status != "rejected" or
                    malformed_result.reason != "place coordinates must be two-element lists or tuples"):
                self.violation(f"malformed place proposal was not rejected: {malformed_result.status}/{malformed_result.reason}")
            if (self.c.design.hash != incumbent_hash or self.c.revision != revision or self.c.calls != calls or
                    self.c.actual_oracle_calls != actual_calls or self.c.reserved != 0):
                self.violation("malformed place proposal reached oracle admission or changed the incumbent")
        self.auto = False
        self.check_state()
        for _ in range(rng.randint(5, 45)):
            event = rng.choices(("submit", "held", "replay", "release", "stop", "cancel", "clock", "yield"),
                                (34, 5, 3, 36, 3, 3, 6, 10))[0]
            if event == "submit":
                p = await self.new_proposal()
                if p is not None:
                    self.submit(p, "new")
            elif event == "held" and self.held:
                self.stats["submitted_held"] += 1
                self.submit(self.held.pop(rng.randrange(len(self.held))), "held")
            elif event == "replay" and self.sent:
                self.stats["submitted_replay"] += 1
                self.submit(rng.choice(self.sent), "replay")
            elif event == "release" and self.pending:
                self.release()
            elif event == "stop" and self.stop_snapshot is None:
                in_flight = bool(self.pending) or any(not t.done() for t in self.tasks)
                self.stats["stop_in_flight" if in_flight else "stop_idle"] += 1
                self.trace.append(f"STOP (in flight: {in_flight})")
                await self.c.stop()
                self.stop_snapshot = self.snapshot()
            elif event == "cancel":
                live = [t for t in self.tasks if not t.done()]
                if live:
                    self.stats["cancelled"] += 1
                    self.trace.append("cancel")
                    rng.choice(live).cancel()
            elif event == "clock":
                self.now += rng.choice((1, 10, 30, 61, 120))
            for _ in range(rng.randint(1, 6)):
                await asyncio.sleep(0)
            self.check_state()
        for _ in range(20000):                                 # drain: release everything still in flight
            if not self.pending and all(t.done() for t in self.tasks):
                break
            if self.pending:
                self.release()
            await asyncio.sleep(0)
        else:
            self.violation("harness could not drain the in-flight submissions")
        for t in self.tasks:
            if t.cancelled():
                continue
            if t.exception() is not None:
                self.crashes.append(repr(t.exception()))
            elif t.result().status == "committed":
                self.stats["commits"] += 1
        self.check_state()
        self.check_record()


def run_case(m, seed, stats):
    case = Case(m, seed, stats)
    with patch("urllib.request.urlopen", case.fake_urlopen):
        asyncio.run(case.run())
    return case


def load_variant(name, replacements=()):
    """controller.py as a fresh module, with each (anchor, replacement) applied where the anchor occurs exactly once."""
    source = (Path(real_controller.__file__).resolve()).read_text(encoding="utf-8")
    for anchor, replacement in replacements:
        count = source.count(anchor)
        if count != 1:
            raise AssertionError(f"mutant {name!r}: anchor found {count} times, expected 1. The controller changed: "
                                 f"update this anchor to the equivalent line.\n{anchor}")
        source = source.replace(anchor, replacement)
    module = types.ModuleType(f"controller_{name.replace(' ', '_')}")
    module.__file__ = real_controller.__file__
    sys.modules[module.__name__] = module                      # dataclasses resolve annotations through it
    exec(compile(source, f"<controller.py: {name}>", "exec"), module.__dict__)
    return module


# Each mutant is a real bypass, written at the call site it would live at.
MUTANTS = {
    "place iterates string coordinates": [(
        "positions = [coordinate_pair(supplied[c.id]) for c in self.chiplets]",
        "positions = [tuple(float(v) for v in supplied[c.id]) for c in self.chiplets]")],
    "move coerces coordinates with float() again": [(
        'positions[indexes[args["chiplet"]]] = (\n'
        '                _finite_coordinate(args["x_mm"], "move"),\n'
        '                _finite_coordinate(args["y_mm"], "move"),\n'
        '            )',
        'positions[indexes[args["chiplet"]]] = (float(args["x_mm"]), float(args["y_mm"]))')],
    "candidate binding removed": [(
        "if result.candidate_hash != candidate.hash:",
        "if False:")],
    "convergence and finiteness check removed": [(
        "if not result.converged or not math.isfinite(result.maximum_temperature_c) or not result.solver_version:",
        "if False:")],
    "problem contract check removed": [(
        "if (result.solver_version, result.problem_hash, result.evidence_kind) != self.oracle_contract:",
        "if False:")],
    "surrogate answers in the simulator's seat": [(
        "result = await self.oracle(candidate)",
        "result = await (getattr(self, 'surrogate', None) or self.oracle)(candidate)")],
    "parent registry accepts a design before the simulator answers": [(
        "            self.calls += 1\n"
        "            self.reserved += reservation\n",
        "            self.calls += 1\n"
        "            self.reserved += reservation\n"
        "            self.verified_designs.setdefault(candidate.hash, candidate)\n"
        "            self.verified_temperatures.setdefault(candidate.hash, self.verified_temperatures[p['parent_hash']])\n")],
    "initialization ignores the shared designs": [(
        "designs = [self.design, *shared_initial_designs]",
        "designs = [self.design]")],
    "initialization skips result validation": [(
        "            self.validate_result(sample_result, sample_design)",
        "            pass")],
    "cost validation removed": [(
        "        if (not isinstance(result.cost_microdollars, int) or\n"
        "                isinstance(result.cost_microdollars, bool) or result.cost_microdollars < 0):",
        "        if False:")],
    "initialization trusts a surrogate answer": [(
        "sample_result = await self.oracle(sample_design)",
        "sample_result = await (getattr(self, 'surrogate', None) or self.oracle)(sample_design)")],
    "STOP and staleness recheck after the simulator removed": [(
        "                reason = self.freshness(p)\n"
        "                if reason:\n"
        "                    return self.outcome(\"rejected\", reason, p)\n"
        "                self.verified_designs[candidate.hash] = candidate",
        "                self.verified_designs[candidate.hash] = candidate")],
}


class SafetyPropertyTest(unittest.TestCase):
    maxDiff = None

    def report(self, case, title):
        return (f"{title}\nseed={case.seed} (reproduce: TFL13_CASES=1 TFL13_SEED={case.seed})\n"
                + "\n".join(f"  - {v}" for v in case.violations[:8] + case.crashes[:4])
                + "\nlast events:\n" + "\n".join("  " + t for t in case.trace[-30:]))

    def test_no_commit_without_bound_simulator_result(self):
        stats = Counter()
        with patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "fixture"}):
            for seed in range(BASE_SEED, BASE_SEED + CASES):
                case = run_case(real_controller, seed, stats)
                stats["cases"] += 1
                if case.violations or case.crashes:
                    self.fail(self.report(case, "SAFETY PROPERTY VIOLATED (or submit raised)"))
        # Coverage floors: the property is only meaningful if each hazard was actually generated, at volume.
        self.assertEqual(stats["cases"], CASES)
        # The forced probe runs in every case that initialized; a refused initialization ends its case first.
        self.assertEqual(stats["malformed_place_cases"], CASES - stats["init_lie_refused"])
        if CASES >= 1000:
            lies = sum(stats["result_" + k] for k in ("wrong_candidate", "changed_problem", "changed_solver",
                                                      "changed_evidence", "unconverged", "nonfinite"))
            # Floors sit at roughly half of what seed 13013 x 1000 generates, so a generator change that starves a
            # hazard fails here instead of quietly shrinking the evidence.
            floors = {"commits": 250, "lying results": (lies, 300), "stop_in_flight": 60, "cancelled": 50,
                      "proposal_forged": 200, "proposal_tampered": 200, "proposal_hold": 300, "submitted_held": 140,
                      "submitted_replay": 250, "signal_valid": 600, "signal_smuggled": 200, "llm_claims": 60,
                      "llm_smuggled_args": 55, "surrogate_predictions": 5000,
                      "proposal_collide_other_agent": 150, "parent_any_verified": 900, "parent_unverified": 250,
                      "parent_unknown_lane": 150, "commits_place": 40, "submitted_malformed": 90,
                      "init_shared_designs": 700, "init_lie_refused": 45}
            for name, floor in floors.items():
                got, need = floor if isinstance(floor, tuple) else (stats[name], floor)
                self.assertGreaterEqual(got, need, f"coverage floor {name}: {got} < {need}\n{dict(stats)}")
        print(f"\nTFL-13 property held over {stats['cases']} cases: {stats['commits']} commits, "
              f"{sum(v for k, v in stats.items() if k.startswith('result_') and k != 'result_honest')} non-honest "
              f"simulator results, {stats['stop_in_flight']} STOPs in flight, {stats['cancelled']} cancellations, "
              f"{stats['malformed_place_cases']} malformed place inputs rejected, "
              f"{stats['signal_smuggled'] + stats['llm_claims'] + stats['llm_smuggled_args']} advisory outputs "
              f"claiming commit authority")

    def test_each_injected_bypass_is_caught(self):
        with patch.dict(os.environ, {"JEV_ENABLE_REQUESTS": "1", "JEV_API_KEY": "fixture"}):
            control = load_variant("control")                 # same loading path, no mutation: must stay clean
            for seed in range(BASE_SEED, BASE_SEED + 200):
                case = run_case(control, seed, Counter())
                if case.violations or case.crashes:
                    self.fail(self.report(case, "the unmutated control module violated the property"))
            caught = {}
            for name, replacements in MUTANTS.items():
                module = load_variant(name, replacements)
                for n, seed in enumerate(range(BASE_SEED, BASE_SEED + MUTANT_CASES), 1):
                    if run_case(module, seed, Counter()).violations:  # crashes alone do not count as caught
                        caught[name] = n
                        break
                else:
                    self.fail(f"mutant {name!r} survived {MUTANT_CASES} cases: the property cannot see this bypass")
        print("\nTFL-13 bypasses caught (cases needed): " + "; ".join(f"{k}: {v}" for k, v in caught.items()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
