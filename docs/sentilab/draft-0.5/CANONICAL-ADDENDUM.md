# Canonical source and acceptance-rule addendum

Date: 2026-10-31, America/New_York. Reviewer: science-redteam for gpt-astra-carter. This adds new source findings to CANONICAL-SOURCE.md without rewriting the earlier bounded review. **Source inspection only: no build, test, simulation, peer `.mjs`, provider call or deployment was run.**

Source pin remains `Sentinelayer-AIdenID/thermal-flight-lab@2199612932da142e0057e6162293940b4ea64bba`. All repository findings below were read through GitHub at that exact SHA. The peer evidence was read in full from `draft04-remote-verification.json` (`decisionPosts` and `reviewerActions`), SHA-256 `76FAF8364FB79C0A051A7809EA068D40746D40DE6BA3DA51DD10A06C87F05CC8`.

Peer locators: Aneta P1–P11 **#55967**, event `9a2ad562-51d1-4a96-af68-dfbd4c79c92d`; Aneta contract/readback update **#55989**, event `437390af-b240-4a07-89c4-65ffd70dba99`; Warden code-review reply to **#55965**, action `ec5ec4c8-7b3a-465a-afa1-e3fcbdebf707`; Warden reply to **#55938**, action `db1d121f-037f-489e-b350-996f6e50c9bd`. These contain proposals and reported tests, not a scoped release from this reviewer.

## 1. Corrected fixture finding: micro150 exists

[sys_micro150.cfg](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_tap/configs/sys_micro150.cfg#L14) explicitly contains:

- Line 14: `chiplet_count = 8`.
- Lines 15–16: four 8.25×9 mm footprints and four 8.75×8.75 mm footprints.
- Line 17: four 150 W plus four 20 W chiplets, totaling **680 W**.
- Line 10: 50 mm interposer; line 3: placement granularity 1.
- Lines 19–26: the complete 8×8 connection matrix.

This corrects the earlier bounded-review statement that the requested configuration had not been located in the inspected paths. It does not establish the attachment's authored placements or 114.82/105.28°C values. The configuration is source material to reuse, not a reproduced experiment.

[tap_oracle.py:24](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_hotspot/tap_oracle.py#L24) still fixes `TAP_CONFIG` to `sys_ascend910.cfg`. The API's supported benchmark names and initial centers likewise remain plate/Ascend910. Plan **parameterization and pinning of an existing micro150 configuration**, not fabrication of dimensions/powers from two temperature values. Validate microbump halos, grid, scenarios, model assumptions and exact initial placements under the new contract.

## 2. Signature finding: self-consistency is not authenticated service origin

The missing trust anchor is verified from these paths:

- [experiment.py:252](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_controller/experiment.py#L252) generates a new proposal/lane identity key for each lane.
- [controller.py:60](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_controller/controller.py#L60) separately generates a record-signing key when none is passed; constructor line 282 calls `FlightRecord()` without a supplied key.
- [verify-core.js:238](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/web/public/verify-core.js#L238) calls `verifyRecord(lane.record, lane.record_public_key)`, taking the verification key from the same untrusted document.
- [verify.html:56](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/web/public/verify.html#L56) already states that the page does not prove who holds that key, and identifies identity anchoring as future work.

Consequently, a wholly fabricated but internally consistent artifact with a newly generated key can satisfy this key-relative verification. This is **not a break of Ed25519** and does not establish that an attacker can alter a record while retaining a separately pinned original key. The missing property is trusted provenance/authorized service origin.

DEPLOY.md documents `FLIGHT_SIGNING_SEED_B64`, but the inspected active run→controller→record call path does not consume it. No secret value was read. Do not represent documentation of a secret as proof that runtime signing is anchored to it.

Proposed trust-root seam, requiring approval before implementation/public provenance claims:

1. Configure a trusted service/root public key independently of the artifact being verified; keep signing authority off lab boxes.
2. Either sign executor receipts directly or certify ephemeral lane/record keys with run, tenant, role, task-contract scope, key ID, validity and algorithm/version binding.
3. Require an authorized certificate chain to that pinned root in both CLI and browser/MCP verification; reject unknown roots, substituted keys, wrong scope/run and invalid signatures.
4. Fail closed if required signing material is missing. Define rotation, revocation, historical verification and retained final checkpoints.
5. Separate displayed verdicts: internal integrity, authenticated origin, and scientific verification. A valid signature cannot certify thermal truth.

No forged-record script or peer executable was run here. The source call graph supports the trust-boundary conclusion; adversarial conformance tests are future approved work.

## 3. Grid peak, source architecture and frontend behavior

**Grid meaning.** [tap_oracle_worker.py:67](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_hotspot/tap_oracle_worker.py#L67) requires all eight layers, line 75 selects layer 4, and lines 248–250 return the Celsius chip-layer field maximum and the separate all-layer maximum. Thus the current code does not read a substrate-only grid. Eight layers are not eight chiplets.

Using this **discrete chip-layer grid peak** as the new primary metric is a defensible proposal and avoids a center-only sampling blind spot. It still changes the attachment's center-temperature contract: assign a new metric/evaluator version and obtain the required +1. It is not the continuous physical die peak. Retain mesh sensitivity and label any center diagnostics separately.

**ARM feasibility.** The [Dockerfile](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/Dockerfile) installs build tools/SuperLU/BLAS and compiles HotSpot C with `make ... SUPERLU=1`; it does not merely ship an irreducibly x86 binary. An ARM build attempt is therefore reasonable under an approved preflight. Python/native dependencies, make settings, ARM image availability and the explicit `OPENBLAS_CORETYPE=Haswell` environment require review. No ARM build was attempted or proved.

A separately built ARM binary will have a different hash. Record each architecture/compiler/library/binary and compare within a prespecified tolerance using the same model, inputs and metric. This is cross-architecture computational reproduction, not an independently implemented physical model or silicon validation. Do not assign it free budget or allow GB10 contention to invalidate the paired comparison.

**Frontend.** [app.js:8](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/web/public/app.js#L8) specifies a replay JSON. Line 421 opens that replay unless a run is linked. `startLive` sends POST `/api/runs`; line 369 loads result data only when the run is `done`. The loop updates running status while polling, but it does not display per-evaluation scientific progress as it occurs. A truly hands-off, event-updating demo needs durable orchestration and an incremental result-delivery contract. SSE is one option, not a correctness requirement; safe cursor polling may satisfy measured latency with less new transport work.

## 4. Archived baseline data: headroom must be measured, not assumed

The pinned `web/public/tfl08/leaderboard.json` reports these Ascend910 online-lane medians (n=10): random **117.835°C**, local signal portfolio **117.835°C**, simulated annealing **118.080°C**, UCB1 **118.095°C**. It explicitly names random and signal portfolio as tied winners. These are values read from archived data, not independently rerun results.

That supports a concern about the existing short Ascend910 task's discriminative power. It does not prove micro150 is hard enough, that random is optimal, or that no stronger search can improve it. The reported 0.260°C difference of medians must not be substituted for the median of paired differences. Keep each statistic's definition.

For micro150, compare bounded search methods on development families; estimate objective/mesh error; retain actual cost; freeze the best-found reference and headroom criterion before held-out results. A clustered-versus-spread gap alone proves layout sensitivity, not optimization headroom. 32/64 grid rank agreement on selected layouts is useful but is neither complete convergence proof nor a free mandatory workload. Long SA is subject to measured runtime and an approved ceiling. Say **empirical gap to best found**, not unqualified regret or optimality.

## 5. P3: preserve valid numeric evidence while committing against current state

Aneta's correction is sound **when candidates are complete layouts, evaluation is a pure function of that layout under a fixed task contract, and constraints refer to the fixed task/x0 rather than the evolving parent.** Changing the board does not change a previously evaluated candidate's temperature.

The current reference already partially embodies this principle:

- [controller.py:448](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_controller/controller.py#L448) retrieves the named verified parent and materializes `parent.apply(operation,args)` before evaluation.
- [controller.py:513](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_controller/controller.py#L513) compares the returned candidate to the **current lane best** under its lock.
- [controller.py:597](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/blob/2199612932da142e0057e6162293940b4ea64bba/sundai_controller/controller.py#L597) rejects a parent absent from `verified_designs`; it does not reject a known parent merely because another design is newer.
- Other freshness checks still enforce run, STOP/epoch, expiry, contract and lane identity. This source review does not prove the complete controller race invariants; no tests ran.

The draft's strict parent-board CAS rule should therefore be corrected for the future durable global AcceptanceGate rather than incorrectly described as an existing-code stale-parent bug.

### Proposed rule

1. Materialize an immutable complete candidate x and its hash. For delta operations, use the **exact referenced parent snapshot**; retain that parent for lineage and credit. Never replay an old delta on a new board while reusing the old measurement.
2. Validate fixed task/metric/evaluator/scenario/configuration IDs, geometry and `W(x) <= W_max(x0)`. Bind trusted evaluation and reproduction receipts to x. Preserve the numeric result whether or not it becomes the winner.
3. At admission, recheck current authority, STOP epoch, allowed lifetime, scientific evidence validity and approval scope. An old valid measurement is not permission to ignore a later stop/revocation.
4. Read current board b at version v with matching verified metric/evaluator/scenarios. Apply the frozen criterion, for example:

   `J(b) - J(x) >= delta_min + u_num(b) + u_num(x)`.

   The uncertainty terms remain the declared estimates/envelopes, not invented confidence bounds.
5. Atomically commit accepted-board update **conditional on v**, along with its acceptance event and exact comparison references. If another commit wins, reread current b and re-evaluate the comparison; do not rerun the simulator solely because CAS lost. Bound control retries and preserve pending evidence.
6. If x no longer improves the current board, record `evaluated/reproduced` with an admission outcome such as `not_selected_current_best` or `within_margin`, not invalid physics. Every actual evaluation still consumes its declared budget; a CAS retry does not create another simulator charge.

Record both `lineage_parent_id/version` and `comparison_board_id/version`. Numeric validity, lifecycle, admission outcome and present evidence validity remain separate fields.

For two reproduced improvements from the same parent, the stronger candidate can replace the weaker only if it also passes the declared margin against the now-current board. With a positive per-update margin, selection can therefore depend on completion order: from 100°C with a 1°C margin and zero illustrative numerical uncertainty, 98°C followed by 97.5°C stops at 98°C, whereas 97.5°C arriving first stops at 97.5°C. Do not claim this sequential rule necessarily selects the best evaluated candidate.

The approved contract must choose between sequential threshold semantics with recorded ordering, or a deterministic batch/epoch selection rule with a frozen comparison reference, total-order ranking/tie rule and explicit margin treatment. An order-independent best-selection claim requires the latter or another separately reviewed rule; CAS alone does not supply it. In either case, retain every valid result, never discard it merely for coming from an older known parent, and never retroactively refund genuine compute.

This reuse rule does **not** apply blindly to stateful simulations, changed power/package/task contracts, moving x0 constraints, parent-relative constraints, materialization on a different parent, or withdrawn evidence. Those require a new candidate/context or explicit reevaluation.

## 6. Aneta P1–P11: integration disposition

| Item | Planning response |
|---|---|
| P1/P2 | Decouple artifact/slide preparation and the thermal correction drill from unrelated implementation dependencies where technically valid. Missing mandatory deliverables remain incomplete; publishing a narrowed package or dropping exact Microduck requires owner +1. A dependency fix is not silent scope deletion. |
| P3 | Adopt the full-candidate/current-board rule above after contract review; keep exact-parent delta materialization and STOP/authority checks. |
| P4 | Add bounded, development-only optimization headroom evidence, distinct from authored-layout sensitivity; preserve best-found and numerical uncertainty qualifiers. |
| P5 | Fixed equal search allocation and equal reproduction policy are essential. Moving reproduction outside the original 32-bundle total changes the attachment budget; propose it to the owner, do not silently enlarge the allowance. Count actual total compute in all arms, including B0 and cross-architecture work. |
| P6 | Fixed-corpus learning evaluation is a strong primary candidate. Closed-loop B4 may be secondary statistically, but remains a requested deliverable unless the owner approves dropping it. Generating held-out corpus fixtures must not expose them to training/calibration. |
| P7 | A gate approval can name an explicit ticket set and shared cap, avoiding 39 redundant approvals; its scope/limits must be concrete. No blank cap or elapsed deadline creates consent. Use monotonic durations and UTC instants. |
| P8 | Remove unjustified import/dependency coupling: ResultCheck core need not import thermal physics; SFT need not depend on RLAIF optimization; a fixture UI need not await robotics. Shared authorization, size limits, source rights and final MCP/CLI parity still apply. |
| P9 | Confirm overnight ownership/network access and measure GB10 serving/training contention. Bound the schedule from measured workload, not model-name assumptions; separate training, evaluation and rendering reservations. |
| P10 | Maintain one role/model manifest. Independence has levels: non-author review, separate context, different model/family/provider, different implementation. Do not call an OpenAI reviewer independent-model evidence against an OpenAI lead without qualification. Claude participation similarly limits Aneta's model-family independence. No unapproved fourth-lab substitution. |
| P11 | OpenResearch telemetry defaults are peer-reported here, not independently inspected. Before private inputs, verify supported telemetry controls and data flows in the approved configuration and record evidence; do not assume a flag disables every external data path. |

The five-arm/two-seed/32-including-reproduction requirements and Microduck/GB10/adapter scope cannot be changed by peer proposal alone. Update the requirement ledger when the owner decides. Aneta has accepted a noncircular capped CPU preflight-review path in #55989, but that message is not itself a specific approved run.

## 7. Claims not independently reproduced by this addendum

- Warden's reported 55 tests plus the 1,000-case property run.
- The manifest's reported eight changed entries, or any fresh hash audit of all packaged files.
- A live Jev production run and its latency/call count.
- NeMo playbook versions, OpenResearch telemetry defaults, or actual model-route availability.
- Aneta's reported contract-vector/mutation-test results. Her `.mjs` files were not executed.
- Absence of the exact 114.82/105.28°C numbers from every repository file. Their source packet and numerical reproduction remain missing evidence.

**Review verdict:** incorporate the verified micro150, trust-root, frontend and current-parent distinctions into the next plan revision. Publish the corrected acceptance contract for peer review. Source-only planning is complete for this bounded request; implementation and scientific execution remain HOLD pending scoped approval.
