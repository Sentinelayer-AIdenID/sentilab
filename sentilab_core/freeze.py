"""Pure SLAB-041 decisions over validated ledger data; no I/O or solver imports.

The caller reads the versioned freeze JSON once and passes it explicitly. These
functions do not authenticate ledger events or replace contract validation.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
from math import comb, isfinite


@dataclass(frozen=True)
class Candidate:
    candidate_hash: str
    lab: str
    arm: str
    j: float
    evaluation_id: str
    valid: bool


@dataclass(frozen=True)
class Attempt:
    lab: str
    slot: int
    candidate_hash: str
    attempt: int
    status: str
    j: float | None


def _number(value, *, nonnegative=False):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("finite numeric value required")
    number = Fraction(str(value))
    if nonnegative and number < 0:
        raise ValueError("nonnegative numeric value required")
    return number


def _parameter(freeze, name):
    return _number(freeze["parameters"][name], nonnegative=True)


def validate_freeze(freeze):
    """Small schema/invariant check; incomplete preregistrations are valid files."""
    if freeze.get("version") != "slab041-freeze/1":
        raise ValueError("unknown freeze version")
    if set(freeze.get("arms", {})) != {"B0", "B1", "B2", "B3", "B4"}:
        raise ValueError("all five arms required")
    budget = freeze["budget"]
    for arm, row in freeze["arms"].items():
        expected = (1, 28, 4) if arm in ("B0", "B1") else (4, 7, 1)
        values = tuple(row[k] for k in ("labs", "search_per_lab", "reproduction_per_lab"))
        if any(type(v) is not int for v in values) or values != expected:
            raise ValueError("arm allowance differs from frozen 28+4 / 7+1")
        if row["labs"] * sum(values[1:]) != budget["total"]:
            raise ValueError("inclusive budget mismatch")
    families = freeze["families"]
    if (families["target"], families["fallback"], families["descriptive_only"],
            families["paired_seeds"]) != (12, 8, 6, 2):
        raise ValueError("family design differs from freeze")
    for design in ("target", "fallback", "descriptive"):
        n = families["descriptive_only" if design == "descriptive" else design]
        if budget[design + "_total"] != n * families["paired_seeds"] * len(freeze["arms"]) * budget["total"]:
            raise ValueError("aggregate budget mismatch")
    if (budget["search_total"], budget["reproduction_total"], budget["total"],
            budget["infrastructure_retry_limit"]) != (28, 4, 32, 1):
        raise ValueError("budget constants differ from freeze")
    if (families["alpha"], families["first_threshold"], families["second_threshold"],
            families["eight_non_tied_required_wins"]) != (0.05, 0.025, 0.05, 8):
        raise ValueError("statistical constants differ from freeze")
    if set(freeze["parameters"]) != {"nomination_tolerance", "acceptance_margin",
                                      "reproduction_tolerance", "sharing_tolerance"}:
        raise ValueError("required parameters missing or unknown")
    for value in freeze["parameters"].values():
        if value is not None:
            _number(value, nonnegative=True)
    tie = freeze["parameters"]["nomination_tolerance"]
    margin = freeze["parameters"]["acceptance_margin"]
    if tie is not None and margin is not None and _number(tie) > _number(margin):
        raise ValueError("nomination tolerance must not exceed acceptance margin")
    if freeze["epoch"]["count_per_run"] != 1 or freeze["nomination"]["no_substitute"] is not True:
        raise ValueError("epoch policy differs from freeze")


def require_execution_ready(freeze):
    """Fail closed on any null pin, unknown margin or missing release."""
    validate_freeze(freeze)

    def incomplete(value):
        if isinstance(value, dict):
            return not value or any(incomplete(v) for v in value.values())
        if isinstance(value, list):
            return not value or any(incomplete(v) for v in value)
        return value is None or value == ""

    if freeze.get("status") != "released" or incomplete(freeze):
        raise ValueError("must-fill-before-execution: freeze is not released and complete")


def _check_candidate(c):
    if not isinstance(c, Candidate) or any(not isinstance(v, str) or not v for v in
            (c.candidate_hash, c.lab, c.arm, c.evaluation_id)) or type(c.valid) is not bool:
        raise ValueError("candidate requires hash, lab, arm, evaluation_id and core validity")
    _number(c.j)


def _rank(candidates, tolerance):
    """Anchoring avoids nontransitive pairwise approximate comparisons."""
    remaining = sorted(candidates, key=lambda c: (_number(c.j), c.candidate_hash, c.evaluation_id, c.lab))
    result = []
    while remaining:
        anchor = _number(remaining[0].j)
        group = [c for c in remaining if _number(c.j) - anchor <= tolerance]
        remaining = remaining[len(group):]
        result.extend(sorted(group, key=lambda c: (c.candidate_hash, _number(c.j), c.evaluation_id, c.lab)))
    return tuple(result)


def nominate(candidates, arm, *, freeze):
    """Each lab's evaluated best, or B0/B1's top four distinct layouts."""
    validate_freeze(freeze)
    tolerance = _parameter(freeze, "nomination_tolerance")
    if arm not in freeze["arms"]:
        raise ValueError("unknown arm")
    by_lab = {}
    identities = {}
    for c in candidates:
        _check_candidate(c)
        if c.arm != arm:
            continue
        key = (c.lab, c.evaluation_id)
        if key in identities and identities[key] != c:
            raise ValueError("conflicting evaluation identity")
        identities[key] = c
        if c.valid:
            by_lab.setdefault(c.lab, []).append(c)
    policy = freeze["arms"][arm]
    if len(by_lab) > policy["labs"]:
        raise ValueError("too many labs for arm")
    nominated = []
    for rows in by_lab.values():
        distinct = {}
        for c in sorted(rows, key=lambda c: (_number(c.j), c.evaluation_id)):
            distinct.setdefault(c.candidate_hash, c)
        nominated.extend(_rank(distinct.values(), tolerance)[:policy["reproduction_per_lab"]])
    return _rank(nominated, tolerance)


def eligible_for_reproduction(c, reference, margin):
    _check_candidate(c)
    difference = _number(reference) - _number(c.j)
    return c.valid and difference > _number(margin, nonnegative=True)


def rank_order_gate(reproduced, reference, margin, *, freeze):
    """One batch winner; every loser resolves against that final board."""
    validate_freeze(freeze)
    tolerance = _parameter(freeze, "nomination_tolerance")
    _number(reference)
    if tolerance > _number(margin, nonnegative=True):
        raise ValueError("nomination tolerance must not exceed acceptance margin")
    rows = tuple(reproduced)
    for c in rows:
        _check_candidate(c)
        if not c.valid:
            raise ValueError("gate requires validated reproduced evidence")
    # Do not let a hash-first tie on the boundary hide a qualifying candidate.
    qualifying = [c for c in rows if eligible_for_reproduction(c, reference, margin)]
    winner = _rank(qualifying, tolerance)[0] if qualifying else None
    ordered = list(_rank(rows, tolerance))
    if winner is not None:
        ordered.remove(winner)
        ordered.insert(0, winner)
    board_j = winner.j if winner is not None else reference
    decisions = []
    for index, c in enumerate(ordered):
        improvement = _number(board_j) - _number(c.j)
        if index == 0 and winner is not None:
            outcome = "accepted"
        elif improvement <= 0:
            outcome = "non_improving_current"
        else:
            outcome = "within_margin"
        decisions.append({"candidate": c, "outcome": outcome})
    return {"board": winner if winner is not None else reference, "decisions": tuple(decisions)}


def reproduction_slots(candidates, arm, reference, *, freeze, labs, search_complete):
    """Produce all reserved slots, including unused slots, after the barrier."""
    nominations = nominate(candidates, arm, freeze=freeze)
    margin = freeze["parameters"]["acceptance_margin"]
    _number(margin, nonnegative=True)
    _number(reference)
    policy = freeze["arms"][arm]
    labs = tuple(labs)
    if (search_complete is not True or len(labs) != policy["labs"] or
            any(not isinstance(lab, str) or not lab for lab in labs) or len(set(labs)) != len(labs)):
        raise ValueError("search barrier requires the complete unique lab roster")
    if any(c.lab not in labs for c in nominations):
        raise ValueError("candidate lab is outside the frozen roster")
    result = []
    for lab in sorted(labs):
        selected = [c for c in nominations if c.lab == lab]
        for slot in range(policy["reproduction_per_lab"]):
            c = selected[slot] if slot < len(selected) else None
            eligible = c is not None and eligible_for_reproduction(c, reference, margin)
            result.append({"lab": lab, "slot": slot, "candidate": c,
                           "status": "nominated" if eligible else "unused",
                           "reserved_bundles": 1})
    return tuple(result)


def replay_epoch(candidates, attempts, arm, reference, *, freeze, labs, search_complete):
    """Replay a closed epoch's normalized ledger records without executing work.

    Attempt.success means the caller validated bindings, scenarios, geometry,
    wire limit and independent process evidence. This module also checks J
    repeatability. Counters distinguish logical slots from physical attempts;
    the unresolved retry-accounting pin blocks execution, never grants free work.
    """
    candidates = tuple(candidates)
    slots = reproduction_slots(candidates, arm, reference, freeze=freeze, labs=labs,
                               search_complete=search_complete)
    tolerance = _parameter(freeze, "reproduction_tolerance")
    grouped = {}
    for attempt in attempts:
        if (not isinstance(attempt, Attempt) or type(attempt.slot) is not int or attempt.slot < 0 or
                type(attempt.attempt) is not int or attempt.attempt < 0 or
                attempt.status not in {"success", "failed", "infrastructure_failure"}):
            raise ValueError("invalid reproduction attempt")
        if attempt.status == "success":
            _number(attempt.j)
        elif attempt.j is not None:
            raise ValueError("failed attempt must not carry a numerical result")
        grouped.setdefault((attempt.lab, attempt.slot), []).append(attempt)
    results, reproduced, spent, physical = [], [], 0, 0
    reproduced_hashes = set()
    for slot in slots:
        c = slot["candidate"]
        rows = sorted(grouped.pop((slot["lab"], slot["slot"]), []), key=lambda a: a.attempt)
        if slot["status"] == "unused":
            if rows:
                raise ValueError("unused slot cannot be spent or transferred")
            results.append({**slot, "attempts": ()})
            continue
        if not rows:
            raise ValueError("reproduction barrier: nominated slot still pending")
        if any(a.candidate_hash != c.candidate_hash for a in rows):
            raise ValueError("retry cannot substitute a different candidate")
        if ([a.attempt for a in rows] != list(range(len(rows))) or
                len(rows) > 1 + freeze["budget"]["infrastructure_retry_limit"]):
            raise ValueError("exactly one infrastructure retry permitted")
        if len(rows) > 1 and rows[0].status != "infrastructure_failure":
            raise ValueError("retry requires a declared infrastructure failure")
        if len(rows) == 1 and rows[0].status == "infrastructure_failure":
            raise ValueError("declared infrastructure retry is still pending")
        last = rows[-1]
        success = last.status == "success" and abs(_number(last.j) - _number(c.j)) <= tolerance
        if success:
            reproduced.append(replace(c, j=last.j))
            reproduced_hashes.add(c.candidate_hash)
        spent += 1
        physical += len(rows)
        results.append({**slot, "status": "reproduced" if success else "reproduction_failed", "attempts": tuple(rows)})
    if grouped:
        raise ValueError("attempt outside frozen lab/slot roster")
    remaining = [c for c in candidates if c.arm == arm and c.valid and
                 c.candidate_hash not in reproduced_hashes]
    best = _rank(remaining, _parameter(freeze, "nomination_tolerance"))
    return {"slots": tuple(results), "reproduction_bundles_spent": spent,
            "unused_reproduction_bundles": len(slots) - spent, "physical_attempts": physical,
            "best_evaluated_unreproduced": best[0] if best else None,
            "gate": rank_order_gate(reproduced, reference, freeze["parameters"]["acceptance_margin"], freeze=freeze)}


def sign_test(wins, losses):
    """Two-sided exact p; ties are removed separately for each endpoint."""
    if any(type(v) is not int or v < 0 for v in (wins, losses)):
        raise ValueError("nonnegative integer win/loss counts required")
    n = wins + losses
    return float(min(Fraction(1), Fraction(2 * sum(comb(n, k) for k in range(min(wins, losses) + 1)), 2 ** n)))


def holm(p_values, *, freeze):
    """Multiplicity only; caller also checks direction, completeness and design."""
    validate_freeze(freeze)
    if set(p_values) != {"sharing", "worker"}:
        raise ValueError("both primaries required; no endpoint may be dropped")
    for p in p_values.values():
        if not 0 <= _number(p) <= 1:
            raise ValueError("p value outside [0, 1]")
    result, passed = {}, True
    for index, (name, p) in enumerate(sorted(p_values.items(), key=lambda item: (item[1], item[0]))):
        threshold = freeze["families"]["first_threshold" if index == 0 else "second_threshold"]
        passed = passed and _number(p) <= _number(threshold)
        result[name] = passed
    return result
