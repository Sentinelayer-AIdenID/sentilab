# Proposed protocol amendments after Aneta 56368

Status: **authoring input only; no protocol freeze, execution release or +1**. This independently reviews root 56358 (root092) and Aneta 56368 against the retained draft 0.5, contract 0.2 and fixture implementation. It preserves the existing files and records the points needing an explicit scoped decision. Aneta's statistics-reviewer offer is agent time; human Aneta is not committed.

Aneta has issued a nonauthor technical +1 on 12 target families, pre-outcome 8-family fallback, 6 descriptive-only, no post-outcome dropping, active-chip-layer grid peak, and the frozen-reference reproduction barrier subject to her six rules. This is approval of proposal text, not an implemented runner or spending. The following changes clarify or alter those rules and therefore need review before incorporation.

## 1. Use a total order; keep scientific ties separate

The phrase “ties break by tie tolerance, then candidate hash” cannot safely mean a pairwise fuzzy comparator. With tolerance 1, let A=(J=100, hash=c), B=(100.75,b), C=(101.5,a). Hash ordering within tolerance gives B before A and C before B, but temperature gives A before C: a cycle. Sorting all six input permutations produced ACB, BAC and CBA. Exact `(J, hash)` ordering produced ABC for every permutation.

**Proposed normative text:** “Nomination and admission use ascending, unrounded finite J followed by ascending canonical physical-layout hash. Hashes break exact numeric equality only. Numerical/practical tolerances determine qualification, reproduction agreement and statistical ties; they do not implement the sorting comparator. A deterministic near-tie selection policy would be a separately versioned rule requiring approval.”

This is a proposed replacement for Aneta's tolerance-first wording, not something already covered by her +1. Do not use six-decimal display or ResultCheck receipt rounding to select candidates. If a quantized order is preferred, freeze its origin, bin width, exact arithmetic and boundary behavior; a pairwise absolute-difference comparator remains invalid.

## 2. Filter eligibility before ranking, and rank the final measurement

The frozen plan proposes `J(reference)-J(candidate) >= delta_min + u_num(reference)+u_num(candidate)`. Preserve its inclusive equality unless explicitly changed; “beats the margin” must not silently become a strict comparison. Name separate search-tie, reproduction-agreement and family-analysis tolerances rather than using one number for all three.

The lowest J need not qualify when uncertainty differs. For reference J=100, reference uncertainty 0 and delta_min=1: A has J=97,u=3 and fails (3 < 4); B has J=97.5,u=.1 and passes (2.5 >= 1.1). Selecting A before checking eligibility can waste a reproduction despite an eligible B.

**Proposed normative text:** “Before nomination, filter the lab's complete evaluated candidate pool for immutable-context match, current valid evidence, all required scenarios, geometry/wire constraints and the frozen-reference qualification predicate. Rank that eligible pool using its recorded search measurements. After the reproduction barrier, recompute qualification from complete valid decision measurements against the same frozen reference; rank that eligible reproduced pool using decision J. Accept its first entry, if any. Process remaining complete reproduced records against the resulting board using the existing lifecycle outcomes. An empty eligible pool leaves the reference board unchanged.”

Nomination order must not be reused at admission. Example: A/B evaluated J=95/95.1, reproduced J=95.1/95.0, agreement tolerance .11. Both agree, but B wins at reproduction. At a 1-degree acceptance margin, admitting A first then comparing B to A would incorrectly retain 95.1.

Freeze J_search and J_decision explicitly. If search and final grids differ, call that refinement and declare its comparison/uncertainty rule; it is not like-for-like reproduction by identity. A reproduction must bind its exact expected input and metric. All refinement, scenario and reproduction calls need an allocation. Reference and candidates must be compared at the same declared decision metric/grid/layer/scenario semantics.

## 3. Separate physical identity, proposal identity and nomination identity

**Proposed normative text:** “A physical-layout hash covers canonical fully materialized geometry in the immutable task context: fixed chiplet identities, declared coordinate lattice/units, positions and permitted orientations, bound to the task/power/package/wire contract. It excludes actor, timestamp, parent lineage, explanation and request ID. The signed proposal hash retains those provenance fields. A nomination ID identifies an arm/family/seed/lab/slot separately. Near but unequal legal coordinates are not merged by temperature or geometric tolerance.”

Normalize only declared representational equivalences, such as object-key ordering and negative zero. Swapping two differently powered chiplet identities is a different layout. Materialize deltas against their named parent before hashing; do not rebase them onto a newer board. Candidate hashes of signed envelopes alone cannot identify duplicate layouts.

Freeze one authoritative search measurement per physical layout and context, using the first complete eligible evaluation in predetermined attempt order rather than the minimum of repeated measurements. Record every repeat and its charges. If the team wants repeat averaging instead, freeze the replication count and estimator before outcomes. Never select the most favorable duplicate measurement retrospectively.

## 4. Freeze nomination opportunities and shared-cache accounting

**Proposed normative text:** “B0 and B1 select up to four distinct physical layouts from their own eligible evaluated pool, after deduplication and before reproduction. Fewer than four leave explicit unused slots; no replacement search follows. B2/B3/B4 nominate at most one eligible physical layout per lab. A shared layout becomes a lab's own evaluated candidate only through a recorded search opportunity charged to that lab; authorized cached evidence may satisfy that opportunity only under the frozen cache rule.”

For B3/B4 duplicate nominations by different labs, retain both slot identities, both independent reproduction records and both charges; no replacement nomination is allowed. Apply the same rule to coincidental B2 duplicates. They are repeated observations of one layout, not independent layout discoveries. B0/B1 distinctness is fixed before reproduction and does not grant substitutions when one of their four fails.

Record nominal search/reproduction opportunities separately from actual launched scenario calls, model calls/tokens, CPU and wall time. A cache hit must not create a free extra proposal; an idempotent network retransmission must not create a second opportunity. Scope caches and retrieval by arm/family/seed and lab isolation; cross-arm outcome reuse is prohibited. Shared evidence access is part of the B3/B4 treatment, not permission to transfer quotas.

## 5. A post-start retry conflicts with 7+1 and inclusive 32

Four labs using 7 search + 1 reproduction + 1 reproduction retry require 36 aggregate attempts, not 32. Even one such retry requires 33 if all other slots were consumed. Calling it an infrastructure retry does not make the executed work free. “One declared retry” also needs a named scope: per request, lab, family or experiment.

**Proposed default preserving 7+1:** “At most one actual reproduction bundle may start per lab nomination. An infrastructure retry is possible only when durable evidence proves that no simulator/scenario execution started, the exact same nominated input is retained, and the frozen bounded retry/CPU/model/time allowance permits it. An uncertain launch is treated as consumed. Once any scenario starts, a failure consumes that reproduction opportunity; there is no substitute or post-start retry. All actual costs, including failed startup, remain charged.”

This narrows the draft's general retry promise and requires explicit approval. If post-start reproduction recovery is mandatory, reserve it prospectively by changing the search/reproduction table or increasing the approved total. Do not silently spend another lab's or an unused nomination's allowance. A failed scientific agreement check is not a transient infrastructure error.

The initial reference also needs explicit accounting. The retained old experiment independently evaluates an initial shared pool outside its proposal budget, and the fixture lab hook falls back to a conventional proposal after a refused model proposal. Neither behavior is automatically permitted in this benchmark. Provide a frozen common reference artifact as a declared input with separately authorized/recorded preparation, or debit every fresh initialization evaluation from the inclusive run budget. Do not add uncounted starting-layout pools, fine-grid solves or deterministic substitute searches.

## 6. Define completed failure outcomes versus missing observations

**Proposed normative text:** “Invalid model/schema/geometry proposals consume their fixed proposal opportunity and produce a recorded failure; they do not trigger replacement model calls or an optimizer fallback unless that policy was frozen for all relevant arms. No eligible nominee or an exhausted search with no accepted improvement is a completed outcome: the final board remains the verified reference. A completed scientific reproduction mismatch is recorded as reproduction_failed, with no replacement.”

Infrastructure interruption, missing required raw artifacts or an unobserved required result must not be relabeled as a tie or a favorable fallback. Freeze which terminal system failures yield a complete reference-board outcome and which make the paired family incomplete. Recommended distinction: known proposal/constraint/agreement failures count as system performance; missing observations after the bounded infrastructure policy make the required pair incomplete and confirmation inconclusive. A global STOP or deadline cancellation is not evidence that a candidate failed physics.

For the fixed held-out corpus, keep every preregistered item in the success-rate denominator. Malformed/completed-invalid actions are failures; unresolved infrastructure missingness makes that required paired outcome incomplete, not a smaller denominator. Average the two fixed seed outcomes within each family before the paired analysis. No post-outcome family dropping; retain endpoint-specific tie denominators, exact rational success-rate ties and two-primary Holm. At eight non-tied families, either primary needs eight beneficial signs for a beneficial rejection; seven wins are insufficient. A six-n endpoint may pass the second Holm stage when the other passes the first.

## 7. Specify the barrier's run scope and records

**Proposed normative text:** “One epoch means one family × seed × arm run. Its complete search phase precedes its nomination freeze; all nominated reproduction slots reach a terminal state before any admission. B2/B3/B4 use seven declared search rounds with a common round boundary: permitted B3/B4 sharing from a round is released only after that round closes. B2 remains isolated until final scoring. B0/B1 use 28 declared search opportunities. Arm execution order, deadlines and concurrency are preregistered; no arm receives another arm's results.”

This removes completion-order races within the epoch; it does not claim the five methods now have equal compute cost or identical search spaces. Freeze terminal handling of slow/cancelled slots and the decision boundary before outcomes. If a different global barrier spanning several arm runs is intended, bind that scheduler explicitly.

Record at least the protocol hash, task/family/seed/arm/lab, opportunity/attempt/nomination IDs, physical-layout and signed-proposal hashes, frozen-reference hash, eligible/noneligible reason, own/source measurement IDs, search/decision J and uncertainty, reproduction agreement, all raw hashes, attempted/actual resource charges, unused/retry reasons and final gate outcome. Report best evaluated but unreproduced J separately from final valid reproduced J and accepted-board J. The sequential live demo remains labeled as a different admission policy.

## Review boundary and evidence

Required decisions before freeze: total-order replacement, search/decision metric and equality rules, physical duplicate identity, authoritative repeat measurement, cache/opportunity treatment, retry allocation, initial-reference/refinement accounting, failure/missingness policy and exact epoch scheduler. The current +1 does not fill these fields by implication.

Read in full: root 56358, source UUID `a82ffc03-eb91-409a-b614-abd84a9bb696`, collector record `c85f2bf660923cd52851c8a654a9a7f6717ca3dccd2ddc1bbc26c109e9efe47d`; Aneta 56368, source UUID `786f9d34-a861-4030-88d7-20de2638c958`, collector record `0ac3a8f07af5a7735b475aa689fb725c52d928d88da90a1d2734addfe87798e1`. Both are in `.sentinelayer/sentilab-planning/gpt-astra-carter/overnight/state/records/`.

Relevant retained baseline: `review-draft-0.5/PLAN.md` sections 5, 6 and 8 under the planning root; `tasks/sentilab-review-2026-10-30/overnight-contract-v02/CONTRACTS.md`; `pr19-d29c678/source/sentilab_core/LABS.md` and `pr19-d29c678/source/sundai_controller/experiment.py` under the planning root. The fixture fallback and old initial-pool exemption are source observations, not claims that an approved benchmark already uses them.

Verification: exact rational arithmetic demonstrated the fuzzy comparator cycle and three permutation-dependent sort results, stable exact ordering across all six permutations, the variable-uncertainty eligibility counterexample and the 36-attempt retry arithmetic. The reproduction-order example is explicit algebra with both deviations .1 below .11. These are counterexamples to ambiguous protocol interpretations, not observed experimental failures. No model, solver, CI or remote operation was performed; no frozen or product source was edited.
