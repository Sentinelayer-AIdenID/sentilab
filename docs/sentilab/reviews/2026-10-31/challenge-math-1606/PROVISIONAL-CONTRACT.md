Provisional challenge contract for review. This is neither the final challenge manifest nor an execution grant.

“Help us find chiplet layouts that reduce a declared simulated temperature statistic while preserving useful interconnects. Human and agent proposals will be compared reproducibly with named reconstructed research layouts under one published model and rule set. Results describe these simulations; they do not establish silicon performance, hardware safety, or general superiority over human engineering.”

Each version fixes dimensions, per-die power, netlist/direction/counting, 45 mm frame and coordinate origin, allowed rotations, edge margins, oriented halos/clearance, keepouts, submission lattice, material/package/cooling assumptions and ambient temperature. Every geometry has an immutable content hash. The raw paper reconstruction and each legal engineering variant have different reference IDs. Proposed geometry thresholds need explicit values and engineering or declared benchmark rationale; do not derive a physical design rule merely from a convenient reference spacing.

The version also fixes the temperature statistic M, thermal source/build/runtime/input identities, grid, router formulation/version/status acceptance and route-cost definition. Uniform-power steady state is an assumption. A centre-mapped block statistic must not be called the true pointwise peak. Routed wire and centre-distance proxy are separate metrics. Any net weights count their declared connections exactly once. Pending router/convergence/metric acceptance remains UNKNOWN.

Score the named comparator R and candidate c in that same version:

`delta_T = T_M(c) − T_M(R)`

`q_r = W(c) − (1+r) W(R)`

Store the published paper targets in separate fields. Do not substitute the published T for the same-model T_M(R), or combine T from one reference geometry with W from another, without a separately named paper-target diagnostic.

For a **bounded within-model result**, let `u_T` bound error in the paired delta_T, `u_q(r)` bound error in q_r, and `u_abs(c)` bound error in the candidate statistic itself. Their scope and derivation must be accepted; a sampled sensitivity sum is insufficient. Define:

`delta_T_upper = estimated_delta_T + u_T`

`q_r_upper = estimated_q_r + u_q(r)`

With individual wire error bounds b_c and b_R, `u_q(r)=b_c+(1+r)b_R` is a valid conservative choice for nonnegative r. Bounds here cover their stated computational/model-parameter scope, not unmeasured silicon discrepancy. No bound defaults to zero when it is unknown.

| Label | Conditional predicate, after legality and numerical admission |
|---|---|
| Declared temperature target | `estimated_T_M(c) + u_abs(c) ≤ T_limit` |
| Strict-wire thermal tolerance | `q_0_upper ≤ 0` and `delta_T_upper ≤ D` |
| r-relaxed-wire thermal tolerance | `q_r_upper ≤ 0` and `delta_T_upper ≤ D`; r must appear in the label |
| Strict thermal improvement | `q_0_upper ≤ 0` and `delta_T_upper ≤ −B_T` |
| Strict wire improvement | `q_0_upper ≤ −B_W` and `delta_T_upper ≤ 0` |
| Wire improvement with allowed thermal degradation | `q_0_upper ≤ −B_W` and `delta_T_upper ≤ D`; separate relaxed label if D>0 |
| Robust dominance over R | `q_0_upper ≤ 0` and `delta_T_upper ≤ 0`, with at least one strict improvement under the published tie/margin rule |

D, r, B_T, B_W and T_limit are policy parameters, not uncertainty estimates. The current proposed values are not frozen by this review. If B_W is “2% of reference wire,” name the fixed challenge-reference wire value used to define that threshold. A two-sided reproduction claim is a different predicate from one-sided non-inferiority; retain gate zero's own separately frozen target/metric/tolerance contract.

If valid bounds are unavailable, report nominal deltas and the separate observed mesh, position and replay sensitivities. A finite predeclared screen may require `max_s [estimated_T_M(c;s) − estimated_T_M(R;s)] ≤ D` across all its required scenarios, with the corresponding wire/temperature checks. Label it “passes the listed sensitivity cases,” not a rigorous bound or confidence claim. Specify which perturbations apply to c, R or both. Missing/failed required cases yield INCOMPLETE/INCONCLUSIVE. Do not select or remove scenarios after seeing outcomes.

For tradeoff budgets r∈{0.10,0.25,0.50,1.00}, report the best observed temperature under each corresponding wire constraint, with strict, relaxed and nondominated results separate. These nested budgets can contain the same candidate; they are not independent wins or evidence of global optimality. Give ties deterministic rules and retain every accepted/rejected/failed result.

Readiness uses this challenge's published version, existing gate-zero and exact operational admission, plus the already required outside-account submit/status/result demonstration. No full five-arm learning study is added as a prerequisite for a descriptive layout comparison. Sponsored legality/routing checks must state participant limits, sponsor funding, resource caps, queue behavior and observed latency. A thermal evaluation bundle must enumerate its calls and whole-lifecycle charges; it is not an unlimited no-cost service.
