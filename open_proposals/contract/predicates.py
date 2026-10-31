"""Claim labels (DESIGN.md 4.6-4.10, test T13): the seven label predicates with their evidence modes, claim
suppression and scientific diagnostics. Pure: no I/O.

In each required scenario: delta = T_c - T_R and q_r = W_c - (1 + r) W_R, with q_0 at r = 0. The mesh case (grid 32)
changes only the thermal grid, so it compares T_M and keeps the nominal wire. An R-only position case compares T_M and
routed W as given: the nominal c against the perturbed R. B_W_mm is an absolute threshold on its frozen nominal basis.

A label's mode, first match wins: UNKNOWN without numerical admission; INCONCLUSIVE if a required scenario failed;
INCOMPLETE if one is missing; UNKNOWN if a value or policy field the label reads is unknown (never zero); "bounded" if
every bound it reads is a number and the nominal upper values satisfy it; "passes the listed sensitivity cases" if the
estimated values satisfy it in every required scenario. Otherwise the label is unlabelled and omitted.

Arithmetic is exact: every number is taken as the decimal it prints as (its repr), so a value that equals a threshold
in decimal ties it, as the records' delta_T and q_r do. Binary floating point would move such ties.
"""
from __future__ import annotations

from decimal import Decimal

BOUNDED, PASSES = "bounded", "passes the listed sensitivity cases"
INCOMPLETE, INCONCLUSIVE, UNKNOWN = "INCOMPLETE", "INCONCLUSIVE", "UNKNOWN"
MODES = (BOUNDED, PASSES, INCOMPLETE, INCONCLUSIVE, UNKNOWN)
MESH_GRID = 32

# Label id, in display order: the scenario quantities it reads (t = T_c, d = delta, q0 = q_0, qr = q_r), the policy
# fields it reads, and its predicate (4.8). Robust dominance's tie and margin rule is unpublished: its margin is zero.
RULES = {
    "declared temperature target": (("t",), ("T_limit_C",), lambda x, p: x["t"] <= p["T_limit_C"]),
    "strict-wire thermal tolerance": (("q0", "d"), ("D_K",), lambda x, p: x["q0"] <= 0 and x["d"] <= p["D_K"]),
    "r-relaxed-wire thermal tolerance": (("qr", "d"), ("D_K", "r"), lambda x, p: x["qr"] <= 0 and x["d"] <= p["D_K"]),
    "strict thermal improvement": (("q0", "d"), ("B_T_K",), lambda x, p: x["q0"] <= 0 and x["d"] <= -p["B_T_K"]),
    "strict wire improvement": (("q0", "d"), ("B_W_mm",), lambda x, p: x["q0"] <= -p["B_W_mm"] and x["d"] <= 0),
    "wire improvement with allowed thermal degradation":
        (("q0", "d"), ("B_W_mm", "D_K"), lambda x, p: x["q0"] <= -p["B_W_mm"] and x["d"] <= p["D_K"]),
    "robust dominance over R":
        (("q0", "d"), (), lambda x, p: x["q0"] <= 0 and x["d"] <= 0 and (x["q0"] < 0 or x["d"] < 0)),
}
LABELS = tuple(RULES)
TARGET, RELAXED = LABELS[0], LABELS[2]
BOUND = {"t": "u_abs", "d": "u_T", "q0": "u_q", "qr": "u_q"}

# Each suppression reason, in the manifest's suppressed_by order, and whether it suppresses a given label (4.10).
# A failed predicate fixture that names no label vouches for none of them.
SUPPRESSES = {
    "failed gate zero": lambda failure, label: True,
    "failed binding": lambda failure, label: True,
    "failed predicate fixture": lambda failure, label: failure.get("label") in (None, label["id"]),
    "failed required scenario": lambda failure, label: label["mode"] == PASSES,
}


def number(x) -> bool:
    return isinstance(x, (int, float, Decimal)) and not isinstance(x, bool)


def exact(x) -> Decimal:
    """A JSON number as the decimal it prints as."""
    return Decimal(repr(x))


def quantities(temps: dict, wires: dict, r) -> dict:
    """t, d, q0 and qr in one scenario, exactly: None wherever an input is not a number."""
    t_c, t_r, w_c, w_r = temps.get("T_c"), temps.get("T_R"), wires.get("W_c"), wires.get("W_R")
    wire = number(w_c) and number(w_r)
    return {"t": exact(t_c) if number(t_c) else None,
            "d": exact(t_c) - exact(t_r) if number(t_c) and number(t_r) else None,
            "q0": exact(w_c) - exact(w_r) if wire else None,
            "qr": exact(w_c) - (1 + exact(r)) * exact(w_r) if wire and number(r) else None}


def evaluate_labels(*, policy: dict, bounds: dict, admission: bool, screen: list, values: dict) -> list:
    """The shown labels in display order, each {"id", "r", "mode"}; "r" is the policy r on the r-relaxed label only."""
    runs = {s["id"]: values.get(s["id"], {}) for s in screen}
    if "nominal" not in runs:  # so the screen is never empty: no pass on an empty set (4.7)
        raise ValueError("the screen must list the nominal scenario")
    statuses = {run.get("status", "missing") for run in runs.values()}
    # The same for every label: no admission, then a failed case, then a missing one.
    common = (UNKNOWN if not admission else INCONCLUSIVE if "failed" in statuses
              else INCOMPLETE if statuses != {"observed"} else None)
    r = policy.get("r")
    policy = {key: exact(value) if number(value) else value for key, value in policy.items()}
    cases = [(s, quantities(runs[s["id"]], runs["nominal" if s.get("grid") == MESH_GRID else s["id"]], r))
             for s in screen]
    nominal = quantities(runs["nominal"], runs["nominal"], r)
    shown = []
    for label in LABELS:
        mode = common or label_mode(label, policy, bounds, cases, nominal)
        if mode:
            shown.append({"id": label, "r": r if label == RELAXED else None, "mode": mode})
    return shown


def label_mode(label: str, policy: dict, bounds: dict, cases: list, nominal: dict):
    """UNKNOWN, bounded, the screen, or None (unlabelled), once every required scenario is observed."""
    reads, fields, holds = RULES[label]
    # R-only cases reuse the nominal c, so the target reads only the cases that evaluate c.
    scope = [x for s, x in cases if label != TARGET or s["applies_to"] != "R"]
    if not all(number(policy.get(f)) for f in fields) or any(x[k] is None for x in scope for k in reads):
        return UNKNOWN
    known = all(number(bounds.get(BOUND[k])) for k in reads)
    if known and holds({k: nominal[k] + exact(bounds[BOUND[k]]) for k in reads}, policy):
        return BOUNDED
    return PASSES if all(holds(x, policy) for x in scope) else None


def apply_suppression(labels: list, failures: list) -> tuple:
    """(shown, suppressed): a suppressed label is {"id", "r", "by"}, by its first reason in SUPPRESSES order."""
    unknown = {failure["by"] for failure in failures} - set(SUPPRESSES)
    if unknown:
        raise ValueError(f"unknown suppression reasons: {sorted(unknown)}")
    shown, suppressed = [], []
    for label in labels:
        by = next((reason for reason, hits in SUPPRESSES.items()
                   if any(failure["by"] == reason and hits(failure, label) for failure in failures)), None)
        if by:
            suppressed.append({"id": label["id"], "r": label["r"], "by": by})
        else:
            shown.append(label)
    return shown, suppressed


def record_diagnostic(labels: list, hypothesis: dict, observed: dict) -> tuple:
    """(labels, record): the labels unchanged beside the diagnostic, which never hides a valid claim (A13).

    hypothesis and observed map label ids to whether the predicate holds. matched compares the hypothesised predicates
    only; an empty hypothesis matches nothing.
    """
    matched = bool(hypothesis) and all(observed.get(label) == holds for label, holds in hypothesis.items())
    return labels, {"hypothesis": hypothesis, "observed": observed, "matched": matched}
