# SentiLab scientific and ML adversarial review

Review date: 2026-10-30, America/New_York. Reviewer: science-redteam for gpt-astra-carter. Scope: the two user attachments and current SentiLab request. No experiments or implementation were performed by this review.

Disposition: **HOLD for implementation and benchmark freeze pending the specified approvals and evidence.** The design is suitable for a versioned specification and approved preflights. All thresholds below must be frozen from the preflight and scientific requirements before comparative outcomes are inspected.

## P0: measurement and physics contract

### Historical claims are not current evidence

The attachments report 293 manifest matches, 16 controller tests, nine reproduced finalists, and authored-layout temperatures of 114.82°C and 105.28°C. These remain historical claims until the exact source, fixture, configuration and raw outputs are recovered and rerun. Their 9.54°C difference is a manually authored-layout preflight, not an agent optimization gain.

### Freeze the measured quantity

The proposed objective is:

\[
J(x)=\max_{s\in S}\max_{i\in\{1,\ldots,8\}}T^{\mathrm{center}}_{i,s}(x).
\]

This supports “maximum simulated chiplet-center temperature across the declared scenarios.” It does not establish die-peak/junction safety, physical accuracy, manufacturing readiness, or a continuous die-temperature heatmap. Exported layer, center mapping, interpolation, units and field dimensions belong in the evaluator version. The substrate field must not be relabeled as die temperature.

Freeze layer dimensions, conductivity, interface/contact resistance, ambient, cooling boundary conditions, per-chiplet power distribution, solver tolerances, and steady-state versus transient scope. A fixed-power steady-state model excludes workload dynamics and temperature-dependent leakage unless expressly modeled. Record scenario selection and package uncertainty; do not imply that a finite scenario maximum is worst-case over every physical workload.

### Executable verification gates

- Zero power produces ambient/reference equilibrium.
- Dimensions and units are consistent: W, W/m², W/m³, m, K/W and W/(m·K) are not interchangeable. Radiation, if used, requires absolute temperature.
- Integrated mapped power equals input power for each scenario.
- Generated power equals boundary heat flow within a frozen numerical tolerance at steady state.
- Symmetric geometry/material/power conditions produce symmetry; consistent relabeling preserves results.
- A fixed passive linear network obeys heating monotonicity when power increases.
- A simple slab/network case recovers `ΔT = P Rθ`.
- At least three spatial resolutions check convergence; promising candidates receive finer-grid verification.
- All inputs/outputs are finite; reject malformed dimensions, missing/duplicate chiplet IDs, invalid mappings, NaN and infinity.
- Published artifacts bind source revision, configuration, input and raw output hashes, platform and dependency versions, seed/settings and reproduction command.

**Hidden failure mode:** an optimizer can exploit rasterization, center sampling, interpolation or grid aliasing. Improvement must exceed a predeclared numerical uncertainty margin. A fresh process reproducing the same artifact does not detect a common model-form error.

Distinguish numerical verification from physical validation. Analytic cases, convergence and a separate implementation verify computation. Relevant independent measurements or a defensible reference dataset are needed to validate physical predictions. Expert endorsement alone cannot substitute for that evidence.

## P0: geometry and acceptance mathematics

Use one canonical coordinate system, preferably integer grid ticks plus explicit units. For lower-left coordinates `(l_i,b_i)` and orientation-adjusted dimensions `(w_i,h_i)`, centers are:

\[
c_i=(l_i+w_i/2,\ b_i+h_i/2).
\]

Freeze exact chiplet identities, dimensions, permitted orientation, power mapping, package origin/axes, placement grid, boundary clearance, keep-outs, and spacing metric. Rectangular guard bands, axis separation and Euclidean clearance are different constraints. Inflating both footprints by the full required spacing can accidentally double it.

For a declared center-distance interconnect proxy:

\[
W(x)=\sum_{i<j}c_{ij}(|c_{ix}-c_{jx}|+|c_{iy}-c_{jy}|).
\]

State the connection-weight units and whether endpoints are centers or electrical ports. Freeze `W_max`, or the permitted ratio against a nonzero baseline, before search. This is not routed interposer length, bandwidth, timing, signal/power integrity, congestion or mechanical reliability.

Acceptance requires all of: schema and immutable task match; geometry validity; all frozen constraints; successful required scenarios; qualifying objective beyond the margin; independent reproduction; current supporting evidence; and compare-and-swap against the exact parent board version. Combined changes form a new candidate and must be rechecked. Simulated annealing's exploratory state may worsen; the accepted best board is distinct.

An authorized peer `+1` is necessary where the user's protocol requires it, but is not sufficient to override a failed mathematical predicate. Bind approval to actor, scope, artifact version, timestamp and conditions. Silence, quoted approvals and generated recommendations are not authorization.

## P0: fair comparisons and data separation

The proposed five arms are classical simulated annealing; one lab/base worker; four isolated labs/base worker; four sharing labs/base worker; four sharing labs/adapted worker. The primary collaboration contrast is isolated versus sharing with the same lead models; the primary learning contrast changes the worker checkpoint while holding other conditions fixed.

If the evaluation unit is each family-seed, 12 families × 2 paired seeds × 5 arms × 32 bundles means **3,840 bundles**, multiplied by the number of scenarios for solver runs. Resolve this interpretation explicitly; reserve reproduction inside the allowance.

Freeze accounting for starting layouts, failed/invalid proposals, retries, timeouts, infrastructure errors, caching, logical versus physical evaluations and reproduction. Set aggregate model-token and proposal ceilings across the collective. Specify single-lab model selection, lab initialization, final design selection, stop rules and a resource-driven reduction rule before seeing outcomes.

Isolated labs need isolated run memories, contexts, accepted-state access and ENGRAM namespaces. A shared inference process must remain stateless across logical agents. Reviewers either operate before the benchmark or offer matched assistance with costs counted. A common initial knowledge corpus is permissible only if it contains no held-out experimental evidence.

Matched simulator budgets and matched aggregate model budgets among agent arms do not automatically mean identical total resources compared with simulated annealing. Report simulator calls, tokens, wall time, GPU time and cost separately. Record actual model identities/settings; interleave or balance run order if provider snapshots cannot be pinned.

Split by task **family**, including related power/layout variants. Prevent held-out leakage through ENGRAM, OpenResearch notes, prompts, critic messages, teacher output, checkpoint selection and debugging. Freeze worker and initial memory before evaluation. Retain test outcomes for a future version, not an online update during the scored comparison.

## P0: learning from successes and failures

“Learn from every experiment” means preserve every outcome with provenance. It does not mean train immediately on every answer.

Keep separate records for state/task/evaluator versions; proposed action; trusted executor result; constraint failure; verified repair; success/failure/tie/inconclusive/infrastructure-error/withdrawn status; concise rationale; judge identity and settings; source artifact IDs; dataset rights and eligibility; and split/snapshot identity.

For SFT, positive targets are verified actions or verified repairs. Failed actions are negative/context records, not silently successful demonstrations. For preference/RLAIF JSONL, compare actions under the same task and context, include evidence and score components, and preserve tie/inconclusive outcomes. Validity takes priority; do not force preference between numerically indistinguishable candidates.

LLM labels and deterministic verifier outcomes are distinct fields. Blind judges to author/arm where practical, randomize order, and test order swaps and self-preference. Treat evidence bodies as data, not instructions. An LLM majority cannot overrule a failed simulation or missing observation. Save concise evidence-based rationales and observable actions, not fabricated hidden reasoning.

Training data must be permitted for the intended use. Track sources, model/provider terms, dataset/model licenses, consent where required, and redaction of secrets or personal information. An API entitlement does not automatically grant rights to distill all outputs.

### Adapter identity and invalidation

Labs may contribute eligible examples to one shared worker. Arbitrary adapters from different bases/tokenizers/architectures/recipes cannot simply be exchanged or merged. Pin base and tokenizer revisions, chat template, target modules, rank, precision, training parameters and hashes. Evaluate any merge as a new artifact.

A withdrawn source invalidates dependent training eligibility and may quarantine datasets/checkpoints/adapters. Removing a memory row does not unlearn weights. Promotion requires a clean eligible snapshot and retraining or independently verified remediation. Retain full derivation lineage and prior artifact status.

The current request prioritizes GB10 for the worker and fine-tuning. Exact NVIDIA NeMo/ARM/GPU/container/model compatibility needs an approved train→save→reload→serve preflight. Historical H100 plans are not permission to silently move the requested GB10 work elsewhere. A fallback requires the agreed `+1` and a documented scope change.

## P1: statistical evidence and independence

Two seeds do not convert 12 related families into 24 independent scientific samples. Analyze paired family-level effects with seed variation separately; report ties, regressions, failure rates, effect sizes and uncertainty. Do not promise statistical significance or broad generalization from this small fixture domain.

Use both a fixed held-out action/repair corpus and a closed-loop comparison. In the fixed corpus, prompts, memory, tools, runtime, precision and decoding are identical. In the closed loop, starting conditions and budgets match while trajectories naturally diverge. Measure first-action validity, repair count, simulator-confirmed benefit, final objective, latency and cost. Training loss and successful loading are pipeline evidence, not engineering improvement.

| Check | What it establishes |
|---|---|
| Fresh process, same solver, immutable inputs, no output cache | Repeatability |
| Different worker/operator/environment | Operational reproduction |
| Independent numerical implementation | Cross-method verification |
| Relevant independent measurements | Physical validation |

The reproducer must execute from recorded inputs, not approve a prefilled expected output. Two interfaces backed by the same model are not independent model reviewers. A common solver bug survives separate processes and agent identities.

## P1: Senti ResultCheck arithmetic

Promise arithmetic and submitted-data consistency only. Require unique paired sample IDs, comparable units, metric direction, exact aggregation and the intended claim. For lower-is-better:

\[
d_j=b_j-c_j,\qquad \bar d=\frac{1}{n}\sum_jd_j.
\]

Flag duplicates, missing pairs, changed populations, unit mismatch, zero percentage denominators and nonfinite values. Mean per-sample percent change and percent change in aggregate means are different estimands; do not substitute one silently. Small/dependent samples may support descriptive arithmetic only.

**Celsius trap:** percent reduction in raw °C depends on the temperature origin. Report Δ°C/ΔK, or explicitly normalize thermal rise above ambient. Do not advertise “X% cooler” from raw Celsius values.

Signed receipts attest to the computation on submitted data, not the authenticity or physical validity of those measurements. CLI and MCP must call the same versioned implementation and return equivalent receipts and structured errors. Capture actual external-team request, executed check, receipt and observed downstream use before claiming collaboration benefit.

## P1: scientist roles, routing and visual fidelity

Use the methods of excellent practitioners, without claiming to instantiate a famous scientist or treating a persona as expertise. Competency tracks should cover thermal/package uncertainty, constrained optimization, statistical/ML evaluation, and reproduction/provenance. Leads must pass fixtures for dimensional reasoning, invalid geometry, impossible claims, uncertainty and tool use. Keep provider identity separate from assigned discipline.

Jev may propose intent/routing choices with calibrated abstention. Deterministic policy still checks permission, frozen constraints, budget and explicit approval. OpenResearch is a research harness with an identified underlying agent/model. Neither a route prediction nor a narrative summary proves completion.

The exact NVIDIA Microduck reference, assets/license, simulator version and hardware support must be identified before promising exact simulation parity. A robotics renderer does not validate thermal physics. Render actual geometry, correctly identified temperature data, common color scales and explicit replay/time-compression labels. Test GB10's actual ARM/software/graphics compatibility; do not assume a generic GPU container works.

## Required approval gates

1. **Specification:** coordinate/metric/scenario definitions, rights and authority model, exact benchmark unit, complete requirements traceability.
2. **Evaluator:** canonical source/artifacts recovered; numerical sanity/convergence checks; stated scope and limitations accepted.
3. **Learning preflight:** permitted fixture→train→save→reload→identity proof→same-runtime inference on the approved hardware path.
4. **Experiment freeze:** family splits, initial memories, model snapshots, budgets, analysis/failure policy and approval hashes locked.
5. **Release:** reproduction, honest comparisons, CLI/MCP parity, correction/withdrawal handling, real partner exchange and replay verification.

Approval records require named approver, exact version/scope, conditions and time. Material changes require renewed approval. No implementation or deployment was authorized by this review itself.
