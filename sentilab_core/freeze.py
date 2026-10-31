"""Pure SLAB-041 policy over validated, normalized ledger records.

No clock, randomness, I/O, solver or model. The caller supplies the pinned JSON
and verifies ledger signatures, physical hashes, measurement authority and run
boundaries before calling. Policy validation is not an authentication boundary.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
from math import comb, isfinite


@dataclass(frozen=True)
class Reference:
    j: float
    uncertainty: float
    context: str


@dataclass(frozen=True)
class Candidate:
    candidate_hash: str  # Canonical physical layout, not a signed proposal hash.
    lab: str
    arm: str
    j: float
    evaluation_id: str  # Lab opportunity/proposal identity, distinct from layout.
    valid: bool
    uncertainty: float
    context: str  # Pinned family/seed/arm/epoch and evaluator/scenario context.
    measurement_id: str  # One authoritative evaluated measurement per layout/context.


@dataclass(frozen=True)
class Attempt:
    lab: str
    slot: int
    candidate_hash: str
    attempt: int
    status: str
    j: float | None
    execution: str  # Core evidence: not_started, started, or unknown.
    uncertainty: float
    context: str
    measurement_id: str | None


def _number(value, *, nonnegative=False):
    if type(value) not in (int, float):
        raise ValueError("finite numeric value required")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("finite numeric value required")
    number = Fraction(str(value))
    if nonnegative and number < 0:
        raise ValueError("nonnegative numeric value required")
    return number


def _text(value):
    return isinstance(value, str) and bool(value)


def _parameter(freeze, name):
    return _number(freeze["parameters"][name], nonnegative=True)


def validate_freeze(freeze):
    """Small schema/invariant check; null scientific pins are valid draft data."""
    sections = {"version", "status", "source_rows", "endpoints", "families", "arms",
                "budget", "epoch", "nomination", "gate", "parameters", "pins"}
    if not isinstance(freeze, dict) or set(freeze) != sections:
        raise ValueError("missing or unknown freeze section")
    if freeze["version"] != "slab041-freeze/1":
        raise ValueError("unknown freeze version")
    pin_names = {
        "metric_id", "evaluator_version", "scenario_manifest", "active_layer", "grid",
        "geometry_and_stack", "wire_metric_and_units", "wire_connection_matrix", "wire_x0",
        "wire_alpha", "wire_zero_baseline_absolute_cap", "margin_derivation_and_numerical_uncertainty",
        "family_manifest_and_stratified_order", "paired_seed_values_and_run_order", "hidden_corpus_and_split",
        "models_prompts_tools_and_memory", "lab_rosters", "reproducer_policy",
        "runtime_token_proposal_and_retry_cost_caps", "training_only_headroom_protocol",
        "pre_outcome_release", "physical_layout_canonicalization", "reference_and_refinement_charges",
        "sharing_round_barriers"}
    if set(freeze["pins"]) != pin_names:
        raise ValueError("missing or unknown execution pin")
    if set(freeze["arms"]) != {"B0", "B1", "B2", "B3", "B4"}:
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
    if set(freeze["parameters"]) != {"acceptance_margin", "reproduction_tolerance", "sharing_tolerance"}:
        raise ValueError("required parameters missing or unknown")
    for value in freeze["parameters"].values():
        if value is not None:
            _number(value, nonnegative=True)
    if freeze["epoch"]["count_per_run"] != 1 or freeze["nomination"]["no_substitute"] is not True:
        raise ValueError("epoch policy differs from freeze")


def require_execution_ready(freeze):
    """Reject unresolved pins; caller must still verify the release and pin values."""
    validate_freeze(freeze)

    def incomplete(value):
        if isinstance(value, dict):
            return not value or any(incomplete(v) for v in value.values())
        if isinstance(value, list):
            return not value or any(incomplete(v) for v in value)
        return value is None or value == ""

    if freeze["status"] != "released" or incomplete(freeze):
        raise ValueError("must-fill-before-execution: freeze is not released and complete")


def _check_reference(reference):
    if not isinstance(reference, Reference) or not _text(reference.context):
        raise ValueError("reference requires a pinned context and measured uncertainty")
    _number(reference.j)
    _number(reference.uncertainty, nonnegative=True)


def _check_candidate(c):
    if not isinstance(c, Candidate) or any(not _text(v) for v in
            (c.candidate_hash, c.lab, c.arm, c.evaluation_id, c.context, c.measurement_id)) or type(c.valid) is not bool:
        raise ValueError("candidate requires physical hash, identities, context and core validity")
    _number(c.j)
    _number(c.uncertainty, nonnegative=True)


def _authoritative(candidates):
    seen = {}
    for c in candidates:
        key = (c.context, c.candidate_hash)
        measurement = (c.measurement_id, _number(c.j), _number(c.uncertainty))
        if key in seen and seen[key] != measurement:
            raise ValueError("conflicting authoritative measurement for physical layout/context")
        seen[key] = measurement


def _rank(candidates):
    # Exact numeric ordering is total and transitive. Metadata orders only
    # identical physical layouts with the same authoritative objective.
    return tuple(sorted(candidates, key=lambda c: (_number(c.j), c.candidate_hash, c.lab, c.evaluation_id)))


def eligible_for_reproduction(c, reference, margin):
    _check_candidate(c)
    _check_reference(reference)
    if c.context != reference.context:
        raise ValueError("candidate/reference context mismatch; cross-arm reuse forbidden")
    threshold = _number(margin, nonnegative=True) + _number(reference.uncertainty) + _number(c.uncertainty)
    improvement = _number(reference.j) - _number(c.j)
    return c.valid and improvement > 0 and improvement >= threshold


def nominate(candidates, arm, reference, *, freeze):
    """Filter qualification first, then nominate by exact evaluated J and hash."""
    validate_freeze(freeze)
    _parameter(freeze, "acceptance_margin")
    _check_reference(reference)
    if arm not in freeze["arms"]:
        raise ValueError("unknown arm")
    rows, identities = [], {}
    for c in candidates:
        _check_candidate(c)
        if c.arm != arm:
            continue
        if c.context != reference.context:
            raise ValueError("candidate/reference context mismatch")
        key = (c.lab, c.evaluation_id)
        if key in identities and identities[key] != c:
            raise ValueError("conflicting evaluation identity")
        identities[key] = c
        rows.append(c)
    _authoritative(rows)
    policy = freeze["arms"][arm]
    if len({c.lab for c in rows}) > policy["labs"]:
        raise ValueError("too many labs for arm")
    by_lab = {}
    for c in _rank(rows):
        if eligible_for_reproduction(c, reference, freeze["parameters"]["acceptance_margin"]):
            by_lab.setdefault(c.lab, {}).setdefault(c.candidate_hash, c)
    return _rank(c for distinct in by_lab.values() for c in
                 tuple(distinct.values())[:policy["reproduction_per_lab"]])


def rank_order_gate(reproduced, reference, margin, *, freeze):
    """One batch winner; caller margin must equal the non-null frozen margin."""
    validate_freeze(freeze)
    _check_reference(reference)
    if _number(margin, nonnegative=True) != _parameter(freeze, "acceptance_margin"):
        raise ValueError("margin must equal frozen acceptance_margin")
    rows = tuple(reproduced)
    for c in rows:
        _check_candidate(c)
        if not c.valid:
            raise ValueError("gate requires validated reproduced evidence")
        if c.context != reference.context:
            raise ValueError("reproduced/reference context mismatch")
    if len({c.arm for c in rows}) > 1:
        raise ValueError("cannot rank multiple arms together")
    _authoritative(rows)
    ordered = list(_rank(rows))
    winner = next((c for c in ordered if eligible_for_reproduction(c, reference, margin)), None)
    board = winner if winner is not None else reference
    if winner is not None:
        ordered.remove(winner)
        ordered.insert(0, winner)
    decisions = []
    for index, c in enumerate(ordered):
        improvement = _number(board.j) - _number(c.j)
        if index == 0 and winner is not None:
            outcome = "accepted"
        elif improvement <= 0:
            outcome = "non_improving_current"
        else:
            outcome = "within_margin"
        decisions.append({"candidate": c, "outcome": outcome})
    return {"board": board, "decisions": tuple(decisions)}


def reproduction_slots(candidates, arm, reference, *, freeze, labs, search_complete):
    """Produce all reserved slots after every lab has closed search."""
    candidates = tuple(candidates)
    nominations = nominate(candidates, arm, reference, freeze=freeze)
    policy = freeze["arms"][arm]
    labs = tuple(labs)
    if (search_complete is not True or len(labs) != policy["labs"] or
            any(not _text(lab) for lab in labs) or len(set(labs)) != len(labs)):
        raise ValueError("search barrier requires the complete unique lab roster")
    if any(c.lab not in labs for c in candidates if c.arm == arm):
        raise ValueError("candidate lab outside frozen roster")
    result = []
    for lab in sorted(labs):
        selected = [c for c in nominations if c.lab == lab]
        for slot in range(policy["reproduction_per_lab"]):
            c = selected[slot] if slot < len(selected) else None
            result.append({"lab": lab, "slot": slot, "candidate": c,
                           "status": "nominated" if c is not None else "unused", "reserved_bundles": 1})
    return tuple(result)


def _settle(rows, c, retry_limit):
    if not rows:
        raise ValueError("reproduction barrier: nominated slot still pending")
    if any(a.candidate_hash != c.candidate_hash or a.context != c.context for a in rows):
        raise ValueError("attempt substituted candidate or context")
    if [a.attempt for a in rows] != list(range(len(rows))) or len(rows) > 1 + retry_limit:
        raise ValueError("exactly one pre-execution infrastructure retry permitted")
    free = lambda a: a.status == "infrastructure_failure" and a.execution == "not_started"
    if len(rows) > 1 and not free(rows[0]):
        raise ValueError("retry requires proof that the first solve never started")
    if len(rows) == 1 and free(rows[0]):
        raise ValueError("declared pre-execution retry is still pending")
    return sum(not free(a) for a in rows)


def replay_epoch(candidates, attempts, arm, reference, *, freeze, labs, search_complete, search_charges):
    """Replay a closed epoch; counts are opportunities, including cached evidence.

    search_charges is the verified ledger's per-lab aggregate, including initial
    reference, refinements, failed/uncertain launches and cache opportunities.
    It must not be a count of only successful candidate rows. Runtime enforces
    these reservations before launch; this function checks the recorded totals.
    """
    candidates, labs = tuple(candidates), tuple(labs)
    slots = reproduction_slots(candidates, arm, reference, freeze=freeze, labs=labs, search_complete=search_complete)
    policy = freeze["arms"][arm]
    if set(search_charges) != set(labs) or any(type(n) is not int or not 0 <= n <= policy["search_per_lab"]
                                              for n in search_charges.values()):
        raise ValueError("search charges exceed allowance or omit a lab")
    for lab in labs:
        opportunities = {c.evaluation_id for c in candidates if c.arm == arm and c.lab == lab}
        if len(opportunities) > search_charges[lab]:
            raise ValueError("candidate opportunities exceed recorded search charges")
    tolerance = _parameter(freeze, "reproduction_tolerance")
    grouped = {}
    for a in attempts:
        if (not isinstance(a, Attempt) or not _text(a.lab) or not _text(a.candidate_hash) or
                not _text(a.context) or type(a.slot) is not int or a.slot < 0 or
                type(a.attempt) is not int or a.attempt < 0 or
                a.execution not in {"not_started", "started", "unknown"} or
                a.status not in {"success", "failed", "infrastructure_failure", "missing"}):
            raise ValueError("invalid reproduction attempt")
        _number(a.uncertainty, nonnegative=True)
        if a.status == "success":
            _number(a.j)
            if not _text(a.measurement_id) or a.execution == "unknown":
                raise ValueError("successful measurement requires known execution and authority")
        elif a.j is not None or a.measurement_id is not None:
            raise ValueError("failed/missing attempt cannot carry a numerical measurement")
        if a.status == "failed" and a.execution != "started":
            raise ValueError("completed scientific failure requires a started execution")
        grouped.setdefault((a.lab, a.slot), []).append(a)
    results, reproduced, spent, physical, complete = [], [], 0, 0, True
    charged = dict(search_charges)
    for slot in slots:
        c = slot["candidate"]
        rows = sorted(grouped.pop((slot["lab"], slot["slot"]), []), key=lambda a: a.attempt)
        if c is None:
            if rows:
                raise ValueError("unused slot cannot be spent or transferred")
            results.append({**slot, "attempts": ()})
            continue
        charge = _settle(rows, c, freeze["budget"]["infrastructure_retry_limit"])
        last = rows[-1]
        success = last.status == "success" and abs(_number(last.j) - _number(c.j)) <= tolerance
        if success:
            reproduced.append(replace(c, j=last.j, uncertainty=last.uncertainty, measurement_id=last.measurement_id))
        missing = last.status in {"missing", "infrastructure_failure"}
        complete = complete and not missing
        status = "reproduced" if success else "inconclusive" if missing else "reproduction_failed"
        charged[slot["lab"]] += charge
        spent += charge
        physical += len(rows)
        results.append({**slot, "status": status, "attempts": tuple(rows), "charged_bundles": charge})
    if grouped:
        raise ValueError("attempt outside frozen lab/slot roster")
    if (any(n > policy["search_per_lab"] + policy["reproduction_per_lab"] for n in charged.values()) or
            sum(charged.values()) > freeze["budget"]["total"]):
        raise ValueError("inclusive arm/lab budget exceeded")
    hashes = {c.candidate_hash for c in reproduced}
    best = _rank(c for c in candidates if c.arm == arm and c.valid and c.candidate_hash not in hashes)
    return {"slots": tuple(results), "reproduction_bundles_spent": spent,
            "unused_reproduction_bundles": sum(s["status"] == "unused" for s in slots),
            "physical_attempts": physical, "charged_by_lab": charged, "total_charged": sum(charged.values()),
            "complete": complete, "best_evaluated_unreproduced": best[0] if best else None,
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
