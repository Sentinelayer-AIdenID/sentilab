# Aneta 56739/56740: bounded informed source review

**Disposition: incorporate the source-grounded coupling lead and reference/claim safeguards; HOLD numerical calibration, evaluator replacement, new MATCH rules and evidence-status transitions pending their own reviewed protocol and authority. No execution +1 follows.** The original root freeze is unchanged. This review is informed by the earlier root/Warden/Forge reviews, and is not a blind replication.

## Packet identity and execution boundary

Both files match their claimed SHA256 exactly:

| Record | Extracted file | Bytes | SHA256 |
|---|---|---:|---|
| 56739 | `ANETA-REPORT.md` | 9,520 | `53565a80ae15a9a78b04c18816f4ed9e83fcb3f9599c107bc5d7569ad055c054` |
| 56740 | `thermal-network.mjs` | 11,130 | `2fedbad94e2644560fcb1555e62d7af87b1d0d9dc0d40b512f058aa82a6b1d39` |

The match removes exactly one marker-adjacent LF from each end of the marker interior. Raw collector records, decoded message UTF-8, marker interiors, and the explicit delimiter variants are retained in `EXTRACTION-MANIFEST.json`; no line-ending, Unicode, content or whitespace normalization was silently applied. Collector `sourceRecordSha256` and hashes of the stored JSON are separately identified, not conflated.

The model was **not executed or imported**. No thermal solve, numerical workload, test, build, model/provider call, GPU work, experiment, evidence withdrawal or external message occurred. One specifically named upstream C file was retrieved read-only to verify the cited equation; this was not a literature rerun. Numerical tables in Aneta's report remain author-reported outputs, not independently reproduced results in this review.

## 1. The coupling concern is real in the examined source; its temperature effect is still unverified here

Aneta report lines 20–25 accurately identify the key change. At upstream commit `a7a3286e368867c26381e0a23e36b3e273bdeda9`, the detailed-3D vertical macros use the lower layer's full `rz` (`HOTSPOT6-temperature_grid.c:2228–2230`); the direct-SuperLU matrix does likewise at `3391–3397`. Its sink `rz` includes convection at `829–834`.

The retained vendored C at PR55 `18f0dca` is byte-identical to the historical source reviewed earlier, SHA256 `1d50f58d…`. Its detailed-3D `find_res` uses adjacent half-sums (`temperature_grid.c:97–104`), sink `rz` contains the convection term (`1052–1057`), and the sink is grounded through full `rz` (`5439–5441`). This corroborates an ambient-boundary term entering an internal spreader–sink connection. The non-detailed branch uses the lower-layer full resistance (`116–121`).

This supports prioritizing CAL-COUPLING. It does **not** independently verify 54 K versus 1.3 K, a 2.57 rise ratio, or a universal temperature correction. Interface drop depends on local heat flux and lateral/peripheral paths. “Copper on copper” alone does not quantify that drop; the equation and boundary placement are the stronger evidence. Derive the intended node locations and material/boundary resistances first, then test a known-answer stack under a prospective grant. Neither old-version agreement nor deleting one term proves physical correctness.

The report's `v6` label means **Aneta's network with a v6-style vertical link**, not the HotSpot 6 executable. Actual v6 lateral links differ from the half-half links used in both model variants (`HOTSPOT6-temperature_grid.c:2220–2226,3392–3395`; model `73–83`). Pin an executable/build and full generated inputs before calling anything a HotSpot 6 or paper reproduction. A switch to the old binary is a proposed reproduction track, not an accepted production repair.

## 2. The model's centre metric does not implement native GRID_CENTER

Model `129–130` takes the single cell containing each die's geometric centre. Both examined HotSpot versions use the block's mapped coverage box, then average **one, two or four central cells**: v6 `1746–1759`; vendored v7 `1953–1966`. The coverage indices use tolerant floor/ceiling and a top-origin row transform (`v7:363–369`). Even a geometrically centred die can span an even number of cells, so these selectors are not generally equivalent.

Consequently the claimed sub-0.4 K agreement and the reported centre-versus-grid differences do not establish equivalence to native `GRID_CENTER`. Their magnitude of error here is unknown without authorized evaluation; this is a source-level metric mismatch, not a newly measured temperature discrepancy. Reuse the same solved field to retain the native block IDs, central indices/weights, grid maximum/argmax and the exact historical TAP stdout selector separately. TAP selects positional stdout tokens (`passive_interposer.py:197–210`); the paper's metric should not be asserted from the word “centre” alone.

The model's stack values are all sampled at its chip-layer grid argmax (`132`), which is a sensible explicitly named diagnostic, but that argmax may move between variants. Preserve the coordinate, full fields and fluxes. A same-coordinate interface drop, each layer's independent maximum, and the difference between two variant maxima are different observables.

## 3. Useful sensitivity model, insufficient calibration evidence

The model openly simplifies lateral coupling, heterogeneous-cell mixing, microbump/edge geometry and reconstructed layouts (report `85–89`; model `5–6,24–46,143–168`). Its hand-built Ascend/CPU-DRAM layouts are not the paper's frozen geometries. Earlier vector reconstruction also shows orientation and coordinate issues; a scalar temperature or wire fit cannot uniquely recover many unknown coordinates.

Near-agreement on a weakly layout-sensitive example can support a common-mode package/cooling hypothesis, but is weak evidence for placement fidelity. The report's own corners mismatch and mesh sensitivity are material, not rounding noise. Held-out layouts are useful, provided they were not selected or adjusted after seeing their targets, share the exact metric/constraints, and are not mislabeled independent physical validation merely because multiple papers reuse the same solver lineage.

The retained paper distinguishes CPU-DRAM Fig. 5(c), 94.89 C / 216,064 mm, from Fig. 5(d), 93.89 C / 138,956 mm (paper text `583–589`). These are different cases, not evidence of a numerical contradiction. Name the exact figure/case in each comparison. Human-designed research layouts also involve human engineers; the important distinction is research reference versus shipped-product reference, not whether humans designed them.

The CG loop has a finite iteration cap but no failure status, explicit residual report, finite/positive denominator checks, or acceptance assertion (`model:112–136`). It can return a result after reaching the cap without satisfying its stop condition. Printed balance alone cannot certify convergence, correct topology or temperature error. This is a missing validation guard, **not a claim that the reported runs failed convergence**. Before a granted run, require terminal reason, residual/energy diagnostics, input/output identities and raw outputs.

TAP's inverse-area package scaling and stale-file guard are confirmed (`passive_interposer.py:151–164`). Reading and hashing the actual generated config can rule out an unscaled value without a solve. The report's one-run temperature table is a discriminating proposal conditional on matching inputs, not proof the hypotheses are exhaustive or mutually exclusive; both errors could coexist. Use paired fixed-input variants for causal attribution.

## 4. Tighten the proposed claim contract before adopting its constants

- **Reference provenance and common checker: agree; “if reference fails, checker is wrong”: reject** (report `52,56`). Failure may expose reconstruction/rotation/units, uncertainty, a different package domain, or an invalid proposed constraint. Preserve the failure and resolve it; do not relax the checker until a picture passes. Existing vector work already found overlap after naive snapping.
- **1 K, 2%, 85 C and relaxed r are prospective rules, not established guarantees** (`53,61–64`). Source and justify each domain-specific limit, and keep paper-reproduction tolerances separate from engineering feasibility. A single routed-wire scalar cannot “pin” coordinates. The half-millimetre/1,224-links estimate needs a declared endpoint displacement/router sensitivity model, not assumed identical changes to every link.
- **`U=max(mesh, perturbation, replay)` is not a justified combined bound** (`57`). Errors can coexist; a finite perturbation sample does not bound all admissible reconstructions. Separate numerical error, reconstruction uncertainty, replay variation and model discrepancy; assess the paired candidate-minus-reference quantity with its dependence/correlation. Predeclare an acceptable noninferiority margin separately from uncertainty. A robust rule can require an upper bound on the paired difference to be below that margin; allowing `T_candidate <= T_reference + U` otherwise becomes easier as uncertainty grows. No new universal bound is asserted here.
- **Write unambiguous MATCH/BEAT predicates** (`61–64`). Specify weak versus strict Pareto dominance, uncertainty on both axes, equality, missing data and feasibility. The present MATCH includes `T<=85 C` while saying feasibility is separate; choose explicit labels for matching a research reference versus passing a thermal ceiling. More wire for lower temperature is a trade-off, not dominance.
- **Discrimination controls are useful, but 100/5% is a design choice** (`58`). Freeze the legal-layout sampling distribution, rejection/projection rules, seed independence, primary metric and statistical treatment. A sample pass fraction is not a guaranteed population fraction. Controls, optimizers and finalists need declared opportunities, calls and compute; no 100-layout execution is authorized by this review.
- **ResultCheck versus deterministic MATCH: distinction supported** (`70`). Retained v0.3/Python source returns `insufficient_data` for fewer than two usable analysis units after declared grouping (`resultcheck.mjs:189–218`; `resultcheck.py:373–375`). Independence must come from experimental design; the code cannot infer it from unrelated IDs. Repeated runs of one unit do not create independent families. A separately defined deterministic predicate is reasonable but remains a new contract requiring prospective review, vectors and CLI/MCP parity. It does not replace the original family-level study freeze.

The `adpTWv2` source sets thermal weight to zero only when **both old and new temperatures are below 80 C** (`sim_annealing.py:86–91`). A reference near 75 C does not prove every candidate is below the threshold or that constrained thermal headroom is globally negligible. Keep the distinction between that code branch, the paper's 85 C discussion and a newly proposed feasibility rule.

## 5. Preserve historical evidence; change eligibility by dependency and claim

Report `76` overreaches if “withdraw every number” means erase raw data or declare all derived facts meaningless. Preserve immutable evaluator identity, inputs, raw outputs, timestamps, spend, incomplete witnesses, failures, coordinates and the proposal/review history. The old temperatures, gap and mesh differences remain observations of that specified evaluator; they cannot certify a corrected evaluator or silicon. Mark affected scientific claims ineligible, disputed or superseded through explicit dependency/reason records and link new evaluations under new identities.

Geometry/wire violations computed independently of temperature remain factual for those saved candidates, even when candidate selection depended on the suspect evaluator. Infrastructure results and paid charges also remain. Do not relabel historical INCONCLUSIVE as PASS, refund/restart closed work, silently rewrite the root freeze or perform an actual withdrawal cascade from this proposal. The correction drill should demonstrate append-only review and controlled invalidation, not retroactive deletion.

## 6. A faster reference is a new proposal, not a budget measurement

Report `77` compares its own reported wall time with a different implementation/hardware and does not measure the governed evaluator's CPU lifecycle. Its code is PCG, not a demonstrated reusable factorization. For `G(x)T=P(x)`, changing placement changes coverage, chip/microbump conductivity, resistances and thus `G` (`model:24–44,53–54,73–84`). Numeric factors can be reused when the operator is fixed, for example power-only right-hand sides, not automatically for arbitrary placements. Symbolic structure or a surrogate might be reusable, but needs explicit accuracy and cost tests.

Using a cheap model to search then evaluating only finalists can change opportunity counts, selection bias and equal-arm comparisons. Keep a separately preregistered diagnostic/reference track with final target-evaluator confirmation; retain every attempted proposal and its provenance. No millisecond-cost assumption or extra search authorization follows.

## Recommended bounded next decision

Carry these corrections into existing REF-RECON/CAL-COUPLING and claim-contract tickets: freeze geometry/rotation/uncertainty and generated config; specify the native observables and intended network equations; define a small known-answer and paired-variant plan with exact retained outputs; require explicit resource authorization before any solve. Treat Aneta's model as a transparent sensitivity proposal until its own measurement and convergence evidence exist. Keep physical validation, full agent-learning comparison, GB10 work and the original scientific freeze open rather than replacing them with the proposed smallest deck result.

`SOURCE-MANIFEST.json` binds the read sources and original report hash; `SEAL.json` binds this critique and preserved packet. No external routing was performed by this reviewer.
