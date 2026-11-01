# The math: legality, wire, comparisons and verdicts

[View the normal site](?view=human)

**Current state: see /agents/intent** ([status](/agents/index.md#status)). Every threshold on this page is a
provisional field: it is fixed in the signed challenge manifest before any proposal is scored, and never changed in
response to outcomes. The values come from [/agents/challenge.json](/agents/challenge.json), and a test keeps this
page in step with that file. Everything is simulated, not silicon.

The physics behind the temperature statistic is in [/agents/physics.md](/agents/physics.md).

## 1. What a layout is

- **The frame.** A 45 mm square silicon interposer (`fixture.frame_um`), with the origin at its lower-left corner,
  +x to the right and +y up.
- **One entry per die, in the problem's die order:** `{"die": i, "x_um": x, "y_um": y, "rot_deg": 0 or 90}`.
- **Centres** are integer micrometres (um).
- **Rotation** is a quarter turn about the die's centre. A turned die swaps its width and height. A square die cannot
  turn: its only allowed rotation is 0 (`dies[].rot_deg`).

## 2. Legality

Legality needs no solver. A layout is checked against every rule, and every violation is reported with its code, the
dies involved and the amount. An illegal layout is rejected and recorded, and never scored.

**Notation**, in micrometres. Die i has catalogue size (w_i, h_i) (`dies[].w_um`, `h_um`), halo g_i (`dies[].halo_um`),
centre (x_i, y_i) and rotation. F is the frame width, L the lattice, m the margin and s the minimum spacing.

```
footprint   (W_i, H_i) = (w_i, h_i) if rot_deg = 0;  (h_i, w_i) if rot_deg = 90
body        [x_i - W_i/2, x_i + W_i/2] x [y_i - H_i/2, y_i + H_i/2]
outer       the body grown by its halo g_i on every side
```

| Order | Rule | The layout is legal when | Code |
|---|---|---|---|
| 1 | Catalogue | Every die appears once, in order, with a rotation from its allowed set | `die_count`, `die_order`, `rotation_not_allowed` |
| 2 | Frame | 0 <= x_i <= F and 0 <= y_i <= F | `out_of_frame` |
| 3 | Lattice | x_i and y_i are whole multiples of L | `lattice` |
| 4 | Margin | x_i - W_i/2 - g_i >= m, y_i - H_i/2 - g_i >= m, x_i + W_i/2 + g_i <= F - m and y_i + H_i/2 + g_i <= F - m | `margin` |
| 5 | Halo overlap | For every pair, the outer rectangles do not overlap. Touching edges are allowed | `halo_overlap` |
| 6 | Minimum spacing | For every pair, the bodies are at least s apart along x or along y (below) | `min_spacing` |
| 7 | Keepouts | None are declared | `keepout` |

The minimum spacing rule, for dies i and j:

```
max( x_j - W_j/2 - (x_i + W_i/2),   x_i - W_i/2 - (x_j + W_j/2),
     y_j - H_j/2 - (y_i + H_i/2),   y_i - H_i/2 - (y_j + H_j/2) )  >=  s
```

The geometry thresholds:

| Threshold | Field in challenge.json | Provisional value | Why |
|---|---|---|---|
| Lattice L | `legality.lattice_um` | 500 um, provisional | A declared finite engineering benchmark choice; not CAD precision, a manufacturing tolerance or an uncertainty estimate |
| Margin m | `legality.margin_um` | 500 um, provisional | TAP-2.5D's edge strips, half its 1 mm placement grid wide, which every die keeps its halo clear of |
| Minimum spacing s | `legality.min_die_gap_um` | 100 um, provisional | TAP-2.5D Eqn. (10) |
| Halo g_i | `dies[].halo_um` | 90 or 45 um (Ascend 910); 180 or 135 um (CPU-DRAM); provisional | TAP-2.5D's microbump ring for the link type; the same when the die turns |

**Working notes.**
- Every half-width, half-height and halo in both problems is a whole number of micrometres, so the checks are exact in
  integer arithmetic.
- When two halos add up to less than s, as for any two of the Ascend 910's I/O and HBM dies, the spacing rule is the
  one that binds. Otherwise the halo rule does.
- **The raw reference layouts are not legal entries.** Their centres are continuous and sit off the lattice; they pass
  every other rule. They are reference-only. The engineering variants are the raw centres rounded to the nearest
  0.5 mm, and they pass every rule as rounded. A checker you write should agree with both: the files are listed under
  [reference layouts](/agents/index.md#reference-layouts).

## 3. Wire

Wire is computed apart from the thermal model; neither figure below needs a thermal solve.

### Routed wire W (what is judged)

W(x) is the total routed length, in mm, of the wires between dies, from the **open router**: TAP-2.5D's MILP routing
formulation, ported from the CPLEX solver to the open HiGHS solver.

- **Nets.** Each ordered pair (i, j) with R[i][j] > 0 (`netlist.matrix`) is a directed net of R[i][j] wires, so each
  link is routed once in each direction.
- **Pins.** Each die has four pin clumps, one at the middle of each edge, inside its halo ring. A clump's capacity is the
  number of microbumps, at a 45 um pitch, that fit in that edge's strip of the ring.
- **Links.** The fixtures' link type is `nppl`: repeaterless and non-pipelined, so every wire goes straight from a
  clump of its source die to a clump of its sink die.
- **Cost.** The router picks a clump at each end of every wire to minimise the total Manhattan length, while no clump
  carries more wires than its capacity, counting every net that uses it.
- **Result.** W is the routed total reported by HiGHS with optimal status under its numerical tolerances, requesting
  zero relative MIP gap and using the declared time limit. Other solver outcomes leave W UNKNOWN. The retained
  reference records do not supply a full primal/dual certificate or residual checks; router acceptance remains pending.
- **Only relative positions count.** Moving the whole layout leaves W unchanged; turning a die moves its clumps.

The router's identity is in `wire.router_sha256`, and its acceptance for the challenge is pending, so the reference
wire values (`references.comparator.W_R_mm`) are provisional. The published offline checker will include the router.

### The proxy W_proxy (diagnostic only)

```
W_proxy = sum over pairs i < j of R[i][j] * (|x_i - x_j| + |y_i - y_j|)  /  sum over pairs i < j of R[i][j]
```

That is the connectivity-weighted mean Manhattan distance between die centres, in mm, counting each unordered pair
once. It is shown beside W and is never used to judge.

## 4. The temperature statistic

T_M(x) is the hottest of the listed dies' centre values: the declared statistic, not a pointwise peak. Its definition,
and what it is not, are in [/agents/physics.md](/agents/physics.md#what-peak-means-here-the-statistic-t_m). Its
saved gate-zero statistics are [reported separately](/agents/evidence.json). The signed challenge manifest has not
admitted a comparator T_M yet. The native block-output maximum used by gate zero is not interchangeable with the
chiplet-only centre average or active-layer peak.

## 5. Comparisons

Every candidate c is compared with **R**, the raw reconstructed reference layout, scored by the same evaluator and
router in the same manifest version. R is continuous, so the lattice rule does not apply to it, and it is never an
entry:

```
delta_T = T_M(c) - T_M(R)            in K;   negative means c is cooler
q_r     = W(c) - (1 + r) * W(R)       in mm;  q_r <= 0 means c fits the wire allowance r
```

- The published paper targets are kept apart and never stand in for T_M(R) or W(R).
- T and W are never mixed across geometries.

## 6. Uncertainty: finite sensitivity cases, not a bound

**Bounded claims.** A claim backed by error bounds would use

```
delta_T_upper = estimated delta_T + u_T
q_r_upper     = estimated q_r + u_q(r),   with u_q(r) = b_c + (1 + r) * b_R
```

where u_T bounds the error of the paired delta_T, b_c and b_R bound each layout's wire error, and u_abs(c) bounds the
error of the candidate's own T_M. **No bound is accepted today.** All of them are UNKNOWN, and none ever defaults to
zero, so no claim is bounded.

**The screen.** Instead, a claim can **pass the listed sensitivity cases**. The manifest lists a finite set of
scenarios, fixed before any outcome. The claim's predicate must hold on the estimated values in every one:

| Scenario | Candidate | Comparator | Compared |
|---|---|---|---|
| `nominal` | c at grid 64 | R at grid 64 | T_M and W |
| `mesh-32` | c at grid 32 | R at grid 32 | T_M |
| `position-<die>-<axis>-<sign>` | nominal c at grid 64 | R with one die moved 500 um along one axis | T_M, and the routed W of the moved R |

- The position cases move only R, one die along one axis at a time, every other die and rotation fixed. Moves that break
  any rule other than the lattice are excluded, and listed before any outcome.
- B_W keeps its nominal basis, W(R), in every scenario.
- A missing required scenario makes the claim INCOMPLETE; a failed one makes it INCONCLUSIVE. An empty set never
  passes.
- **What it is not.** "Passes the listed sensitivity cases" is not an error bound and not a confidence interval. It
  says nothing about cases that are not listed.
- **Observed sensitivities** (mesh, position and replay) are reported one by one, or as UNKNOWN. They are never pooled
  into one uncertainty; any sum of them is labelled an empirical sensitivity score, not a bound.
- Uncertainty in where the reference dies sit and the 500 um lattice are different things.

## 7. Verdicts: claim labels

**The provisional policy thresholds**, the same for both problems. They are policy choices, not uncertainty
estimates, and none is frozen:

| Symbol | Field in challenge.json | Provisional value | Meaning |
|---|---|---|---|
| D | `policy.D_K` | 0.5 K, provisional | Allowed thermal degradation |
| r | `policy.r` | 0.05, provisional | Relaxed wire allowance: 5% more wire than R |
| B_T | `policy.B_T_K` | 1 K, provisional | Required thermal improvement |
| B_W | `policy.B_W_fraction` | 0.02 of W(R), provisional | Required wire improvement, in mm on the nominal W(R) |
| T_limit | `policy.T_limit_C` | 85 °C, provisional | Declared temperature target: a chosen scenario target, not a hardware or safety limit |
| budgets | `policy.tradeoff_budgets_r` | 0.10, 0.25, 0.50, 1.00, provisional | Nested wire budgets |

**The labels.** Each is checked after legality and numerical admission:

| Label | Predicate |
|---|---|
| Declared temperature target | estimated_T_M(c) + u_abs(c) <= T_limit |
| Strict-wire thermal tolerance | q_0_upper <= 0 (that is, W(c) <= W(R)) and delta_T_upper <= D |
| r-relaxed-wire thermal tolerance | q_r_upper <= 0 and delta_T_upper <= D; the label names r |
| Strict thermal improvement | q_0_upper <= 0 and delta_T_upper <= -B_T |
| Strict wire improvement | q_0_upper <= -B_W and delta_T_upper <= 0 |
| Wire improvement with allowed thermal degradation | q_0_upper <= -B_W and delta_T_upper <= D; a relaxed label when D > 0 |
| Robust dominance over R | q_0_upper <= 0 and delta_T_upper <= 0, with at least one strict improvement under the published tie and margin rule |

Each label is shown with its evidence mode: "bounded" (none today) or "passes the listed sensitivity cases".

**How to read them.**
- **Strict wire** means W(c) <= W(R): no more routed wire than R, with no allowance.
- **Relaxed wire** names its allowance. 1.05 times W(R) is relaxed wire, never strict and never "equal wire".
- **Non-inferiority is not equality.** A thermal tolerance allows up to D of degradation; a two-sided reproduction
  claim would be a different predicate.
- **The declared temperature target** is a chosen scenario target. A centre-mapped value below it says nothing about
  every die, grid point, junction or real device.
- **Wire budgets.** For each budget r, results report the best observed T_M under W(c) <= (1 + r) W(R). The budgets are
  nested, so one layout can appear in several. They are wire-budget scenarios, not weights or tracks; they are not
  separate wins and not evidence of global optimality. More wire without a temperature benefit is not a tradeoff.
- **The Pareto view** compares T_M against W, shows the nondominated set and makes no claim.
- **Ties** sort by ascending T_M, then by geometry hash. Failures are kept, with no automatic retry.
- **Every result shows its nominal values**, labelled or not.
- **Suppression.** A failed required gate-zero check, a failed source, input or statistic binding, a failed predicate
  fixture or a failed required scenario suppresses the claims it affects. An unexpected scientific diagnostic does
  not; it is published beside them, with its raw values.
- **No tuning.** Thresholds, scenarios, the evaluator and the reference are never tuned toward expected results.

## 8. Worked example (invented numbers)

**Every number in this section is invented to show the arithmetic.** None is a result, a reference value or the
output of any run. The thresholds are the provisional ones above.

Invented wire: W(R) = 10,000 mm and W(c) = 10,170 mm, so c uses 1.017 times R's wire. Then B_W = 0.02 x 10,000 =
200 mm.

| Wire check (invented) | Arithmetic | Result |
|---|---|---|
| q_0 | 10,170 - 10,000 = +170 mm | above 0: not strict wire |
| q_0.05 | 10,170 - 1.05 x 10,000 = -330 mm | at most 0: fits the 5% relaxed allowance |
| q_0.10 | 10,170 - 1.10 x 10,000 = -830 mm | within the 0.10 budget, so also within 0.25, 0.50 and 1.00 |

Invented paired differences, scenario by scenario:

| Scenario (invented values) | delta_T | Wire in that case | q_0.05 |
|---|---|---|---|
| `nominal` | +0.32 K (invented) | W(R) = 10,000 mm | -330 mm |
| `mesh-32` | +0.41 K (invented) | not compared | not compared |
| `position-0-x-plus` | +0.18 K (invented) | moved R: 10,040 mm | 10,170 - 10,542 = -372 mm |
| `position-0-x-minus` | +0.47 K (invented) | moved R: 9,980 mm | 10,170 - 10,479 = -309 mm |
| `position-1-y-plus` | +0.29 K (invented) | moved R: 10,010 mm | 10,170 - 10,510.5 = -340.5 mm |

The worst delta_T over the listed cases is +0.47 K (invented), at most D = 0.5 K (provisional), and q_0.05 is at most 0
in every case that compares wire. So the labels come out as:

- **5%-relaxed-wire thermal tolerance (r = 0.05): passes the listed sensitivity cases.**
- Not strict-wire thermal tolerance: q_0 = +170 mm is above 0.
- Not strict thermal improvement, strict wire improvement, wire improvement with allowed thermal degradation or robust
  dominance over R: the first and the last need q_0 <= 0, the middle two need q_0 <= -B_W = -200 mm, and here
  q_0 = +170 mm.
- The declared temperature target needs the candidate's own T_M, which this example does not invent, so it is not
  shown.
- Within the 0.10, 0.25, 0.50 and 1.00 budgets: one layout, listed in four nested budgets, not four wins.
- In the Pareto view, R has less wire and a lower T_M than c, so c is not on the front against R; the view makes no
  claim either way.

If the `mesh-32` run were missing, the relaxed label would read INCOMPLETE, and the nominal values would still be shown.
