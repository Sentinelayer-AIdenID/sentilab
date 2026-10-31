"""Routed inter-chiplet wirelength: TAP-2.5D's MILP router on an open solver. Geometry only, no thermal solve.

Derived from TAP-2.5D (https://github.com/bu-icsg/TAP-2.5D, commit 3a3f4e5), sundai_tap/routing.py,
Copyright the TAP-2.5D authors, Apache License 2.0 (sundai_tap/LICENSE).

Change notice (Apache-2.0 section 4(b)): ported for SLAB-048 from routing.py (get_input and
solve_Cplex). The pin-clump geometry and capacities, the integer flow variables, the constraints
(Eq. 12-15 and 18) and the objective are TAP's. What changed:
- the solver: scipy.optimize.milp (HiGHS) replaces IBM CPLEX;
- the solver settings: TAP ran CPLEX with threads=1, a 500 s time limit and CPLEX's default MIP gap.
  This runs HiGHS with mip_rel_gap=0 (a proven optimum) and a 60 s time limit by default. scipy
  exposes no thread setting, so HiGHS uses its own default;
- the result: the total routed wirelength in mm. TAP prints that and returns the per-wire mean;
- failure: any solve that is not a proven optimum (time limit, infeasible, other) raises, where TAP
  returned a placeholder 100. Malformed inputs are refused before the model is built;
- the interposer type: _tap_system always sets TAP's interposer type to "passive", and _pin_clumps
  takes the hop limit from the link type alone (2 for ppl, else 1). routing.py's get_input applies
  the ppl hop limit of 2 only under its intp_type == 'passive' guard; this port drops that guard, so
  it models passive interposers only.

Published-number check (sundai_hotspot/test_tap_router.py): on the decoded TAP-2.5D figures its
totals are within 0.1% of all seven routed wirelengths the paper reports.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numbers
from pathlib import Path
import sys

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

TAP_ROOT = Path(__file__).resolve().parent.parent / "sundai_tap"
if str(TAP_ROOT) not in sys.path:
    sys.path.insert(0, str(TAP_ROOT))
from passive_interposer import PassiveInterposer  # noqa: E402

UBUMP_PITCH_MM = 0.045  # routing.py: "ubump_pitch = 0.045 # 45um in unit of mm"
CLUMPS = 4              # one pin clump per die edge


LINK_TYPES = ("nppl", "ppl")


@dataclass(frozen=True)
class RoutedWire:
    total_mm: float
    wires: int  # TAP's wire_count: every directed net's wires (each link is routed both ways)
    link_type: str


def solver_versions() -> dict:
    """The solver stack behind a routed number: scipy and the HiGHS build it bundles."""
    versions = {"scipy": scipy.__version__, "highs": "unavailable"}
    try:  # scipy has no public HiGHS version API; this private module is read, never relied on
        from scipy.optimize._highspy import _core
        versions["highs"] = f"{_core.HIGHS_VERSION_MAJOR}.{_core.HIGHS_VERSION_MINOR}.{_core.HIGHS_VERSION_PATCH}"
    except (ImportError, AttributeError):
        pass
    return versions


def _validated(problem, centers, rotated, link_type):
    count = len(problem.widths_mm)
    if link_type not in LINK_TYPES:
        raise ValueError(f"link type must be one of {LINK_TYPES}")
    if not isinstance(centers, (list, tuple)) or len(centers) != count:
        raise ValueError(f"routing needs exactly one centre per die ({count})")
    points = []
    for center in centers:
        if (not isinstance(center, (list, tuple)) or len(center) != 2 or
                any(isinstance(v, bool) or not isinstance(v, numbers.Real) or not math.isfinite(v) for v in center)):
            raise ValueError("each centre must be a pair of finite numbers (mm)")
        points.append((float(center[0]), float(center[1])))
    if (not isinstance(rotated, (list, tuple)) or len(rotated) != count or
            any(not isinstance(flag, bool) for flag in rotated)):
        raise ValueError(f"routing needs exactly one boolean rotation flag per die ({count})")
    return points, tuple(rotated)


def _tap_system(problem, centers, rotated, link_type):
    system = PassiveInterposer()
    system.set_chiplet_count(len(problem.widths_mm))
    system.initialize()
    system.set_interposer_type("passive")
    system.set_interposer_size(problem.interposer_size_mm)
    system.set_chiplet_size(list(problem.widths_mm), list(problem.heights_mm))
    system.set_connection_matrix([[int(v) for v in row] for row in problem.connections])
    system.set_granularity(problem.granularity_mm)
    system.set_link_type(link_type)
    system.compute_ubump_overhead()  # the halo follows the link type, as in TAP
    for index, turned in enumerate(rotated):
        if turned:
            system.rotate(index)
    system.x = [float(c[0]) for c in centers]
    system.y = [float(c[1]) for c in centers]
    return system


def _pin_clumps(system):
    """routing.get_input: clump h of die i sits mid-edge in its halo ring; capacity is its bump count."""
    hop_max = 2 if system.link_type == "ppl" else 1
    xl, yl, xc, yc, pmax = [], [], [], [], []
    for i in range(system.chiplet_count):
        w, h, b = system.width[i], system.height[i], system.hubump[i]
        xl.append(system.x[i] - w / 2 - b)
        yl.append(system.y[i] - h / 2 - b)
        side = int(b / UBUMP_PITCH_MM) * int((h + b) / UBUMP_PITCH_MM)
        top = int(b / UBUMP_PITCH_MM) * int((w + b) / UBUMP_PITCH_MM)
        xc.append((b / 2, w / 2 + b, w + b * 1.5, w / 2 + b))
        yc.append((h / 2 + b, b * 1.5 + h, h / 2 + b, b / 2))
        pmax.append((side, top, side, top))
    return xl, yl, xc, yc, pmax, hop_max


def routed_wirelength(problem, centers, rotated, *, link_type: str | None = None,
                      time_limit_s: float = 60.0) -> RoutedWire:
    link_type = problem.link_type if link_type is None else link_type
    centers, rotated = _validated(problem, centers, rotated, link_type)
    system = _tap_system(problem, centers, rotated, link_type)
    xl, yl, xc, yc, pmax, hop_max = _pin_clumps(system)
    R = system.connection_matrix
    C, K = system.chiplet_count, CLUMPS
    nets = [(i, j) for i in range(C) for j in range(C) if i != j and R[i][j] > 0]
    N = len(nets)

    def var(i, h, j, k, n):
        return (((i * K + h) * C + j) * K + k) * N + n

    size = C * K * C * K * N
    cost, upper = np.zeros(size), np.zeros(size)
    for i in range(C):
        for h in range(K):
            for j in range(C):
                for k in range(K):
                    d = abs(xl[i] + xc[i][h] - xl[j] - xc[j][k]) + abs(yl[i] + yc[i][h] - yl[j] - yc[j][k])
                    for n in range(N):
                        cost[var(i, h, j, k, n)] = d
                        upper[var(i, h, j, k, n)] = 0.0 if (i == j and h == k) else pmax[i][h]
    rows, cols, values, lower_rhs, upper_rhs = [], [], [], [], []

    def constrain(entries, low, high):
        row = len(lower_rhs)
        for column, value in entries:
            rows.append(row)
            cols.append(column)
            values.append(value)
        lower_rhs.append(low)
        upper_rhs.append(high)

    def net_flow(node, n):  # Eq. 12: outflow minus inflow at a die, over other dies only
        return [entry for h in range(K) for j in range(C) if j != node for k in range(K)
                for entry in ((var(node, h, j, k, n), 1), (var(j, k, node, h, n), -1))]

    for n, (s, t) in enumerate(nets):
        constrain(net_flow(s, n), R[s][t], R[s][t])
        constrain(net_flow(t, n), -R[s][t], -R[s][t])
        for i in range(C):
            if i not in (s, t):
                constrain(net_flow(i, n), 0, 0)
    for n, (s, t) in enumerate(nets):  # Eq. 13 and 14: nothing enters the source or leaves the sink
        constrain([(var(j, k, s, h, n), 1) for h in range(K) for j in range(C) for k in range(K)], 0, 0)
        constrain([(var(t, h, j, k, n), 1) for h in range(K) for j in range(C) for k in range(K)], 0, 0)
    for i in range(C):  # Eq. 15: a clump carries at most its bump count
        for h in range(K):
            constrain([entry for j in range(C) if j != i for k in range(K) for n in range(N)
                       for entry in ((var(i, h, j, k, n), 1), (var(j, k, i, h, n), 1))], -np.inf, pmax[i][h])
    for n, (s, t) in enumerate(nets):  # Eq. 18: hop limit (1 repeaterless, 2 gas-station)
        if hop_max == 1:
            constrain([(var(i, h, j, k, n), 1) for i in range(C) for h in range(K) for j in range(C)
                       for k in range(K)], -np.inf, R[s][t])
        else:
            entries = []
            for h in range(K):
                for k in range(K):
                    entries.append((var(s, h, t, k, n), 2))
                    entries.extend((var(i, h, j, k, n), 1) for i in range(C) for j in range(C) if i != s or j != t)
            constrain(entries, -np.inf, 2 * R[s][t])

    matrix = coo_matrix((values, (rows, cols)), shape=(len(lower_rhs), size)).tocsr()
    result = milp(cost, constraints=LinearConstraint(matrix, lower_rhs, upper_rhs), integrality=np.ones(size),
                  bounds=Bounds(np.zeros(size), upper),
                  options={"time_limit": time_limit_s, "mip_rel_gap": 0.0})
    if result.status != 0 or result.fun is None:
        raise RuntimeError(f"TAP router found no proven optimum: {result.message}")
    return RoutedWire(float(result.fun), int(sum(R[s][t] for s, t in nets)), link_type)
