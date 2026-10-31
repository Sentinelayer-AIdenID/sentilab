# SLAB-041 benchmark freeze

Version: **slab041-freeze/1**. Ticket: **c07d2f4e**. Status:
**must-fill-before-execution**. This is a preregistration and executable decision
policy, not a benchmark result or authorization to run experiments. No outcome
files, solves, model calls or GPUs are used by this implementation or its tests.

[slab041-freeze.json](slab041-freeze.json) is the single configuration source for
these functions and the future benchmark runner. Its exact UTF-8 file bytes are
hashed with SHA-256; record that hash in the run header and PR. Any filled pin or
policy change requires a new reviewed hash before any outcome. The JSON appendix
below is checked for exact equality by the test suite. Unknown values are explicit
nulls, never zero, permissive defaults or estimated scientific constants.

This ticket supersedes the open benchmark proposals in draft-0.5 PLAN §§5.2, 5.3,
8 and REQUIREMENTS, and disposition rows B08, R01, Q04, Q05, Q06. It preserves the
contract-0.2 lifecycle. Warden’s binding amendment delivered 2026-10-31
(overriding #56377 counterexamples) supersedes tolerance ordering, nomination
before qualification, and ambiguous retry charging. It does not change the
sequential diagnostic conductor.

## Endpoints and claim classes

| Question or measurement | Role | Definition and direction |
|---|---|---|
| Sharing, B2 versus B3 | Confirmatory primary | Within each family average the two paired seed differences, B2 final accepted-board J minus B3 final accepted-board J; positive favors sharing. With complete required evidence and no accepted candidate, the gate retains the frozen initial reference. Missing-data fallback and final-evidence rules must be filled before execution. |
| Worker learning, base versus adapter | Confirmatory primary | Fixed hidden action/repair corpus geometry-plus-wire success rate, adapter minus base, using identical inputs, decoder, runtime and memory; positive favors adapter. Use exact rational rates. |
| Thermal objective J | Versioned primary thermal statistic | Maximum over all frozen scenarios and all grid cells on the active chip layer, lower is better. Pin metric_id, evaluator version, grid and layer. A sampled grid peak is not a certified continuous physical junction peak. |
| Chiplet centers; parsing | Diagnostic | Never replace the primary grid peak or geometry-plus-wire endpoint. |
| Closed-loop B3 versus B4; simulator-confirmed fixed-corpus utility | Required secondary | Report even if null, unfavorable or unavailable; no promotion to primary after outcomes. |
| Best evaluated but unreproduced candidate | Descriptive | Report separately from reproduced/accepted evidence; it cannot become the board. |

## Families and multiplicity

| Design or rule | Frozen interpretation |
|---|---|
| Target | 12 independent held-out families; related layout/power variants remain in one family. Two seeds are nested replicates, never independent families. |
| Fallback | 8 families only under a resource rule approved before any outcome, selected from a frozen stratified order. |
| Six-family design | 6 is descriptive only, even if an unadjusted p value is small. |
| Two primary hypotheses | Two-sided exact family-level sign tests; Holm family-wise alpha .05. Favorable direction is additionally required for a benefit claim. No primary is dropped after outcomes. |
| Endpoint ties | Sharing: absolute family difference at or below the frozen sharing tolerance. Worker: exactly equal rational success rates. Exclude ties separately for each endpoint and report its effective n. |
| Eight non-tied families | **8 of 8** favorable families are necessary, with or without Holm: two-sided p(8/8) = .0078125; p(7/8) = .0703125. |
| Endpoint reduced to n=6 by ties | A **six-n endpoint** can pass second at .05 only if the other primary passes first at .025: p(6/6) = .03125. This does not turn a six-family design into a confirmatory design. |
| Missing required paired family | Apply the frozen loss/final-evidence policy and, only for a preregistered named treatment's beneficial-direction primary claim, adverse-sign imputation. Never remove a family or seed or treat missingness as a measured tie. |

Average the two seed outcomes within each family before testing. `sign_test`
computes a two-sided p from non-tied counts; `holm` applies both thresholds and
requires both endpoint names. These helpers do not establish favorable direction,
completeness, family independence or resource-release approval. The analysis runner
must enforce those prerequisites and record ties and missingness. Q04 headroom
checks remain training-only and require the pinned development protocol; no
held-out outcome may select a margin, family subset or tuning decision.

Missing-family adverse signs are permitted only for the named treatment's
beneficial-direction primary claim specified before outcomes in
`pins.missing_family_primary_claims`; this pin is currently null. Retain every
frozen family and both seed positions. Never average over just the available seed
or fabricate the missing seed's temperature. Only measured endpoint-specific ties
reduce that endpoint's n. Apply the two-sided exact sign tests and two-primary
Holm to the preregistered family signs, and require favorable direction for a
benefit claim. Report **measured wins/losses/ties separately from imputed adverse
signs**, including missing-family and missing-seed evidence. Imputed losses cannot
support a harm claim, a secondary claim, or invented temperatures. The missing
reference/scorer/seed and global-STOP rules below determine applicability; this
is not blanket permission to impute any absent observation.

For 11 favorable signs of 12, the two-sided exact p is **0.00634765625**.
The room's quoted 2.1452%/68.1118% no-loss probabilities assume iid homogeneous
failures; they are not measured reliability.

## Arms and charging

The unit is an all-scenario bundle per **family × seed × arm**.

| Arm | Search system | Labs | Search per lab | Reproduction per lab | Aggregate |
|---|---|---:|---:|---:|---:|
| B0 | Conventional simulated annealing | 1 | 28 | 4 | 32 |
| B1 | One lab, base worker | 1 | 28 | 4 | 32 |
| B2 | Isolated labs, base worker | 4 | 7 | 1 | 32 |
| B3 | Shared-evidence labs, base worker | 4 | 7 | 1 | 32 |
| B4 | Shared-evidence labs, adapted worker | 4 | 7 | 1 | 32 |

Every arm has 28 search + 4 reproduction slots. Across five arms and two seeds,
target/fallback/descriptive allocations are respectively 3840/2560/1920 bundles.
Equal simulator allowance does not imply equal model or total compute cost.

| Event | Charging and audit rule |
|---|---|
| Initial reference and refinement evaluations | Their exact allocation is `pins.reference_and_refinement_charges = null`, must-fill before execution. They cannot create free search or bypass the inclusive 32. Pin x0 before search. |
| Cached request or shared initial sample | Each requesting lab spends its opportunity, using one authoritative measurement per physical layout/context; record actual compute and cache provenance separately. No cross-arm reuse. Sharing cannot manufacture additional search allowance. |
| Invalid or failed search | Spends its search slot; no free substitute. |
| Same layout nominated by two labs | Both spend their own reproduction slot and both remain recorded; no cross-lab deduplication. |
| Unused reproduction | Record the slot as unused with its nominee if ineligible; never transfer to search, another lab, arm, seed or family. |
| Reproduction failure | No replacement nominee. Only a declared transient infrastructure failure with proof that the solve never started permits one retry of the same candidate/context/slot. Numerical mismatch or ordinary failure permits no retry. Record both attempts and all actual costs. |
| Retry charging | Only a proven pre-execution failure is free. Unknown or post-start execution consumes the slot and permits no second charged attempt. A cache hit still consumes its opportunity. Each four-lab arm stays at most 8 per lab and 32 total, including retries. |
| Cross-architecture reproduction | Requires a frozen reproducer policy; no free additional scientific evidence. |
| Consumed opportunity lost or cancelled with no result | Keep the charge and original reason. No replacement slot, even when an otherwise valid final board survives under the frozen final-evidence policy. |

Held-out fixed-corpus no-result retries require pre-outcome attempt and seed
schedules, idempotency/ordering, symmetric limits across compared treatments, and
all charges. These are explicit null pins below. Select the first complete
measurement-valid evaluation in frozen attempt order before testing success or
benefit. Never retry a measured scientific failure to find a favorable result.
Fixed inputs alone do not eliminate retry selection bias. This corpus policy
does not enlarge chiplet's 32 opportunities or relax its existing rule that only
proven pre-execution infrastructure failure permits a free retry.

## Frozen-reference epoch and reproduction barrier

| Phase | Rule, common to all five arms |
|---|---|
| Before search | Pin one immutable initial reference, all scenarios, geometry/stack, grid/layer/metric/evaluator, wire baseline, margins, lab roster and runtime/memory/model settings. |
| All search | Exactly one epoch per run. All labs compare to the frozen reference. B3/B4 may share evaluated evidence, but the accepted board cannot advance and no reproduction begins during search. B2 stays isolated. |
| Nominate | First select the complete measurement-valid evaluation in frozen attempt order for each layout/context, before testing any nomination margin. Then filter qualification, including both uncertainties, and rank eligible candidates. B0/B1 take their top four distinct eligible layouts; other arms take the best per lab. Never select by model choice or lab arrival order. |
| All reproductions | Start only after every lab closes search. Reproduce eligible nominations with bound inputs, all constraints/scenarios and independent worker/process evidence. Do not substitute if reproduction fails. |
| Final gate | Wait until every slot is terminal (reproduced, measured failure, cancelled/no-result, exhausted infrastructure retry, or explicitly unused). Rank qualifying reproductions once against the frozen reference, then resolve losers against the resulting board. Apply the frozen final-evidence/loss policy separately before using a board for inference. |
| Live demo | The existing sequential live-loop board remains demonstration evidence only. It is not this benchmark schedule. |

Order candidates by **exact finite J, then canonical physical-layout hash**.
Tolerances govern qualification and endpoint statistics, never ordering. The
amendment counterexample A=(100,c), B=(100.75,b), C=(101.5,a), with tolerance 1,
cycles under a pairwise fuzzy comparator; the frozen order is A, B, C for every
input permutation. Only exact equal J uses the hash tie-break. Physical layout
identity excludes proposal signatures and lab/slot identity; freeze its canonical
geometry serialization before execution. Each physical layout/context has one
authoritative measurement. Conflicting duplicate measurements are rejected,
never silently selected by best value or input arrival order. Each duplicate lab
still consumes and records its own opportunity, even when served cached evidence.

Select the **first complete measurement-valid evaluation in frozen attempt
order before testing the nomination margin**, never the first favorable or
qualifying result. Measurement-valid means complete, core-validated evidence for
all frozen constraints/scenarios; it does not mean an improving objective. If the
selected measurement fails the margin, do not advance to a later repeat. For
example, with reference 10 and margin 1, an earlier valid J=9.5 excludes a later
J=8 from becoming that layout's authoritative nomination measurement. The exact
attempt order remains `pins.evaluation_attempt_order = null` until approved.

Before normalizing duplicate measurements, the adapter must preserve every
slot's **original independent reproduction and agreement evidence**, identities,
attempt provenance and charge. It checks agreement on each original search and
reproduction pair; selecting a common decision measurement cannot turn a failed
slot into a successful one. B2 isolation also holds before normalization: no
cross-lab evidence is exposed during its search. One authoritative measurement
is a decision convention, never a waiver of independent evidence or slot charges.

Qualification requires a core-validated complete candidate and
`reference_J - candidate_J >= acceptance_margin + reference_uncertainty + candidate_uncertainty`.
The improvement must also be strictly positive. **Exactly at the total margin
qualifies**, preserving PLAN §5.3; a zero improvement is never accepted. Qualification precedes nomination:
at reference 100 and margin 1, A=(J 97, uncertainty 3) is ineligible while
B=(97.5, .1) is eligible when reference uncertainty is zero. The gate ranks by
**reproduced J**, which can reverse search order within the reproduction tolerance.
The first qualifying reproduction alone becomes `accepted`. Against that board,
a zero/negative improvement is `non_improving_current`; a positive improvement
strictly below the total uncertainty/practical margin is `within_margin`. Losers retain
valid evidence, never `stale_parent`. Successful reproduction requires absolute
evaluated-versus-reproduced J difference at most `reproduction_tolerance`.
`rank_order_gate` requires a non-null frozen `acceptance_margin` and rejects a
caller margin that differs from it; a helper call cannot override the freeze.

An epoch is scoped to family × seed × arm. The sharing-round schedule/barriers
remain `pins.sharing_round_barriers = null` until fixed before execution. The
search/reproduction barrier is mandatory in every arm. Completed scientific
failure is an observed outcome and consumes its opportunity. Cancelled/no-result
and unobserved infrastructure outcomes remain missing observations, distinct from
measured scientific failures or ties. A consumed loss never earns a replacement,
but need not erase an otherwise valid final board. Two proven pre-execution
failures exhaust the declared retry without a scientific observation: the slot
remains reserved and inconclusive, both attempts are recorded, neither consumes a
solve, and no third attempt or replacement is allowed. Slot-level `inconclusive`
does not itself decide final-board validity or confirmatory inference.

The following policies are **must-fill nulls before any outcome**. No fallback or
loss limit is silently supplied by the pure helper's returned board:

| Pin | Required decision |
|---|---|
| `board_fallback` | When a measured reference or other board may serve as fallback after loss. |
| `required_final_evidence` | Evidence needed for a valid final board and each paired primary endpoint. |
| `loss_counting_and_limits` | Counting unit, counted loss classes, allowed limits and symmetric handling. |
| `missing_reference_policy` | Handling when the required reference is unavailable. |
| `missing_scorer_policy` | Handling when required scoring evidence is unavailable. |
| `missing_seed_policy` | Treatment of a missing paired seed without removing it or inventing a value. |
| `global_stop_policy` | Treatment of global STOP, including scope and analysis applicability. |
| `missing_family_primary_claims` | Named treatments, beneficial-direction primary claims and mapping of missing required evidence to adverse family signs. |
| `held_out_attempt_schedule`, `held_out_seed_schedule` | Predeclared corpus attempts and seeds. |
| `held_out_idempotency_and_ordering` | Retry identity, transport deduplication and deterministic attempt ordering. |
| `held_out_symmetric_retry_limits`, `held_out_retry_charges` | Equal retry limits and complete per-attempt charging. |

## Replay interface and scope

`sentilab_core.freeze` uses only immutable candidate/attempt records and a passed
configuration; it has no clock, randomness, I/O, solver, model or implicit config
load. A runner reads the JSON once, verifies its recorded hash and calls
`require_execution_ready` before any work. The draft fails that guard. The caller
must validate every filled pin, authorized release, family selection, charging
policy and actual resource cap; the guard alone is not an authorization verifier.

The normalized ledger schema is:

- `Reference(j, uncertainty, context)`.
- `Candidate(candidate_hash, lab, arm, j, evaluation_id, valid, uncertainty, context, measurement_id)`.
- `Attempt(lab, slot, candidate_hash, attempt, status, j, execution, uncertainty, context, measurement_id)`.

Slots and attempts are zero-based. Candidate hash is the physical-layout identity;
evaluation_id is the lab opportunity/proposal identity; measurement_id identifies
the authoritative measurement. The same hash in the same context must use the
same measurement ID, J and uncertainty. Reproduction authority is separate from
evaluation authority. Context binds the family/seed/arm/epoch and immutable task,
metric, evaluator and scenarios. A cross-context record is rejected.

Attempt status is `success`, `failed`, `infrastructure_failure`, `missing`,
`cancelled` or `no_result`. Cancelled/no-result reasons remain in original attempts;
their slot status is `inconclusive`, never `reproduction_failed`.
Execution evidence is `not_started`, `started` or `unknown`. Only success carries
finite J and measurement_id; a known cache hit can succeed without a new start,
but still spends an opportunity. `failed` means completed scientific failure.
`valid`, execution proof and success must come from core contract validation,
including geometry, wire, all scenarios, matching hashes/context and fresh
independent worker/process evidence, never a lab assertion. Verify signatures and
deduplicate transport retransmissions first using the ledger reader.

The current ledger stores the arm in its run header and measurements/proposals in
event bodies; an adapter must join those records into this schema. This ticket
provides the pure replay API, not a new live runner or signed-event adapter:

```python
from dataclasses import asdict
import json
from sentilab_core.freeze import Candidate, Attempt, Reference, replay_epoch

# Caller supplies a verified closed epoch and its pinned config; no simulation.
result = replay_epoch(
    [Candidate(**row) for row in epoch["candidates"]],
    [Attempt(**row) for row in epoch["attempts"]],
    epoch["arm"], Reference(**epoch["reference"]), freeze=config,
    labs=epoch["labs"], search_complete=epoch["search_complete"],
    search_charges=epoch["search_charges"],
)
print(json.dumps(result, default=asdict, sort_keys=True))
```

`reproduction_slots` records all reserved slots. `replay_epoch` rejects pending
slots, retries without pre-execution proof, third attempts, substitutions and transfers;
records failures/mismatches and marks missing slot observations incomplete; reports
physical attempts, charged/unused slots, per-lab/total charges and the best
evaluated unreproduced physical layout. A duplicate successfully reproduced
elsewhere in the same context is not reported as unreproduced. The supplied
`search_charges` are verified per-lab ledger totals including initialization,
refinements, caches and failed/uncertain starts, not just successful candidates.
The function checks the 7-search/1-reproduction lab caps (28/4 for B0/B1); it does
not independently reconstruct search-launch accounting or enforce live reservations. `rank_order_gate` alone expects
already validated successful reproductions. `complete` describes slot observation
coverage, not final-board validity or claim approval; a surviving board still
requires the frozen final-evidence and loss checks. The raw-attempt adapter and
family/corpus analysis runner enforce the selection and imputation policies above;
this module does not implement those runners. These pure functions do not spend
resources or mutate the source ledger. No helper or null-valued config is execution
approval. The caller records their outputs.

## Admission-review adoption and departures

Review input: `SLAB-041-ADMISSION-REVIEW-2026-10-31.md` from PR #31,
SHA-256 `a96ae18722698a2052d0f133933a195eb8a649d42b8afc68ecf319dfecf6d64f`.
This file is not copied here. Warden made the three counterexample fixes binding.
The table retains all seven dispositions and incorporates Warden's later
qualified policy instructions from the PR #33 review (#56413, restated #56451).
Undecided execution details remain null and require pre-outcome review.

| Review section | Adoption or explicit limit |
|---|---|
| 1: Total order | Adopt exact, unrounded finite J then physical-layout hash; no tolerance comparator. |
| 2: Qualification/decision metric | Adopt eligibility before nomination, inclusive positive uncertainty-adjusted margin, and reproduced-J ordering. Search/decision metric and refinement pins remain null; no refinement is executed. |
| 3: Physical identity/measurement | Adopt separate layout/proposal/slot IDs, immutable context and one authoritative measurement. As qualified by the later review, the adapter selects the first complete measurement-valid evaluation in frozen attempt order BEFORE the margin test, never the first favorable/qualifying result. Preserve each slot's original independent reproduction and agreement evidence, B2 isolation and charge before normalization. The pure API rejects conflicting authorities. Exact physical serialization and attempt order remain must-fill pins. |
| 4: Opportunities/cache | Adopt distinct eligible B0/B1 nominations, separate duplicate lab charges, cache opportunity charges and no cross-arm reuse. Actual CPU/model/scenario cost and signed-event adaptation remain runner responsibilities. |
| 5: Retry/reference | Adopt one retry only on durable pre-execution proof; uncertain/post-start consumes the slot with no replacement. Initial-reference and refinement allocation stays null until a preparation-vs-inclusive charging choice is approved. |
| 6: Failure/missingness | Preserve measured failure versus cancelled/no-result, fixed corpus denominator, both seeds and measured endpoint ties. The later qualified policy supersedes blanket missing-means-inconclusive: consumed losses get no replacements but may leave a valid board; adverse signs apply only to a named beneficial-direction primary claim, reported separately from measured results. Final-evidence/loss/STOP and held-out retry details remain null pins. Analysis runners remain outside this patch. |
| 7: Epoch/scheduler | Adopt family × seed × arm scope and both search/reproduction barriers. Seven synchronous sharing rounds are guidance, not a binding release: the exact round schedule remains null and blocks execution. Replay consumes certified search closure and per-lab ledger charge totals; no live scheduler is added. |

## Machine-readable appendix

Every numeric policy constant and all unknown execution pins are in this JSON.
The document and external JSON must change together. Unknown wire metric (sum
versus mean), weights, alpha, x0 and zero-baseline absolute cap must be filled;
the baseline is x0, never a moving accepted parent. Margin derivation must name
practical and measured numerical uncertainty; no observed outcome can set it.

```json
{
  "version": "slab041-freeze/1",
  "status": "must-fill-before-execution",
  "source_rows": [
    "B08",
    "R01",
    "Q04",
    "Q05",
    "Q06"
  ],
  "endpoints": {
    "sharing": "primary: paired family mean of B2 final J minus B3 final J",
    "worker": "primary: paired family fixed-corpus geometry-plus-wire success rate, adapter minus base",
    "thermal_objective": "versioned active-chip-layer grid peak; maximum over all frozen scenarios; lower is better",
    "centers": "diagnostic only",
    "parsing": "diagnostic only",
    "b4_closed_loop": "required secondary: B3 versus B4",
    "simulator_confirmed_corpus_utility": "required secondary",
    "best_evaluated_unreproduced": "descriptive only; never accepted evidence"
  },
  "families": {
    "target": 12,
    "fallback": 8,
    "fallback_approval": "before any outcome, from frozen stratified order",
    "descriptive_only": 6,
    "paired_seeds": 2,
    "seed_aggregation": "arithmetic mean within family before testing",
    "primary_dropping": "forbidden after outcomes",
    "incomplete_required_pair": "apply the frozen final-evidence/loss policy; never drop a family or seed, average over only observed seeds, or treat missingness as a measured tie",
    "sharing_ties": "absolute family difference <= frozen sharing_tolerance",
    "worker_ties": "exact equality of rational success rates",
    "ties": "exclude endpoint-specific ties from that endpoint denominator and report n",
    "test": "two-sided exact family sign test; favorable direction required",
    "multiplicity": "Holm across sharing and worker",
    "alpha": 0.05,
    "first_threshold": 0.025,
    "second_threshold": 0.05,
    "eight_non_tied_required_wins": 8,
    "six_non_tied_rule": "6/6 may pass second at .05 only after the other primary passes first at .025; a six-family design stays descriptive",
    "missing_family_adverse_sign": {
      "scope": "only a pre-named treatment beneficial-direction primary claim under pins.missing_family_primary_claims; not a harm claim or a secondary endpoint",
      "retention": "retain all frozen families and both seed positions; endpoint-specific measured ties alone reduce n; never remove unfavorable or missing families",
      "analysis": "apply adverse family signs for missing required evidence only as preregistered; two-sided exact sign tests and two-primary Holm, with favorable direction also required",
      "report": "report measured wins, losses and ties separately from imputed adverse signs and missing seed/family evidence",
      "prohibitions": "never invent temperatures, fabricate seed means, convert missingness to a measured failure, or infer harm from imputed losses"
    },
    "eleven_of_twelve_two_sided_p": 0.00634765625,
    "no_loss_probability_caveat": "quoted 2.1452% and 68.1118% assume iid homogeneous failures; not measured reliability"
  },
  "arms": {
    "B0": {
      "system": "conventional simulated annealing",
      "labs": 1,
      "search_per_lab": 28,
      "reproduction_per_lab": 4,
      "nomination": "top distinct"
    },
    "B1": {
      "system": "one lab with base worker",
      "labs": 1,
      "search_per_lab": 28,
      "reproduction_per_lab": 4,
      "nomination": "top distinct"
    },
    "B2": {
      "system": "four isolated labs with base worker",
      "labs": 4,
      "search_per_lab": 7,
      "reproduction_per_lab": 1,
      "nomination": "best per lab"
    },
    "B3": {
      "system": "four shared-evidence labs with base worker",
      "labs": 4,
      "search_per_lab": 7,
      "reproduction_per_lab": 1,
      "nomination": "best per lab"
    },
    "B4": {
      "system": "four shared-evidence labs with adapted worker",
      "labs": 4,
      "search_per_lab": 7,
      "reproduction_per_lab": 1,
      "nomination": "best per lab"
    }
  },
  "budget": {
    "unit": "all-scenario bundle per family x seed x arm",
    "search_total": 28,
    "reproduction_total": 4,
    "total": 32,
    "target_total": 3840,
    "fallback_total": 2560,
    "descriptive_total": 1920,
    "transfer": "forbidden between labs, phases, arms, seeds or families",
    "initialization": "initial reference and refinement charges must be pinned before execution; no free search opportunity",
    "cache_and_shared_sample": "every requesting lab spends its opportunity using the authoritative measurement; no cross-arm reuse",
    "invalid_or_failed_search": "spends search slot; no free substitute",
    "duplicate_nomination": "each lab spends and records its own reproduction slot",
    "unused_reproduction": "record unused; never transfer",
    "infrastructure_retry_limit": 1,
    "retry": "exactly one declared transient infrastructure retry only after proven pre-execution failure; same candidate/context/slot; record all attempts and costs; no substitute",
    "retry_accounting": "free only on proof solve never started; uncertain or post-start launch consumes slot; at most one pre-execution retry, never another charged attempt in same slot",
    "cross_architecture": "same reproduction slot only if frozen reproducer policy authorizes it; no free extra evidence",
    "lost_opportunity": "a consumed search or reproduction loss remains charged and never earns a replacement; preserve reason and execution evidence even if an otherwise valid final board survives",
    "held_out_no_result_retries": {
      "scope": "fixed held-out corpus evaluation; not additional chiplet search/reproduction opportunities",
      "prerequisites": "freeze attempt schedule, seed schedule, idempotency and ordering, symmetric retry limits and every charge before outcomes",
      "selection": "first complete measurement-valid evaluation in frozen attempt order before any success, nomination margin or favorable-direction test; never retry measured scientific failure for a better result",
      "accounting": "retain every attempt and charge including no-result attempts; fixed inputs alone do not remove selection bias; chiplet remains at 32 with its existing pre-execution-only retry rule"
    }
  },
  "epoch": {
    "count_per_run": 1,
    "reference": "immutable initial reference, shared by all labs for the entire search",
    "schedule": [
      "all search",
      "deterministic nomination",
      "all reproductions",
      "rank-order gate"
    ],
    "barrier": "every lab search closed before any reproduction in each of B0 through B4; all slots terminal before final gate",
    "sharing": "B3 and B4 may share evaluated evidence during search; no reproduction or accepted-board updates during search",
    "demo": "sequential live-loop board is demonstration only, never benchmark evidence",
    "scope": "family x seed x arm; immutable context binds evaluator, metric, scenarios and physical-layout canonicalization",
    "missing": "cancelled/no-result and unobserved infrastructure losses remain distinct from measured scientific failures; no free replacement; a consumed loss need not invalidate an otherwise valid final board; apply frozen final-evidence/loss and claim-specific missing-family policies",
    "final_board_policy": "freeze board fallback, required final evidence, loss counting/limits, and treatment of missing reference, scorer, seed and global STOP before outcomes; unresolved pins block execution"
  },
  "nomination": {
    "ranking": "exact finite evaluated J ascending, then canonical physical-layout hash ascending; no tolerance in comparator",
    "same_hash": "one authoritative measurement per physical-layout/context; retain separate proposal/lab/slot identities and charges",
    "eligibility": "filter valid candidates first: positive reference J minus evaluated J >= acceptance_margin + reference uncertainty + candidate uncertainty",
    "no_substitute": true,
    "measurement_selection": "select first complete measurement-valid evaluation in frozen attempt order BEFORE testing nomination margin; never first favorable or qualifying result; a margin failure cannot advance to a later repeat",
    "normalization_evidence": "preserve each slot original independent reproduction and per-slot agreement evidence, B2 isolation, attempt provenance and charge BEFORE duplicate normalization; one authoritative measurement never replaces a slot evidence obligation"
  },
  "gate": {
    "contract": "contract-0.2",
    "ranking": "exact finite reproduced J ascending, then canonical physical-layout hash; accept the first qualified reproduction",
    "accepted": "one winner with positive improvement reaching the frozen-reference margin plus both uncertainties; becomes the board",
    "non_improving_current": "board J minus candidate J <= 0",
    "within_margin": "0 < board J minus candidate J < acceptance_margin + board uncertainty + candidate uncertainty; exact boundary qualifies",
    "valid_losers": "retain valid evidence; never stale_parent",
    "reproduction": "fresh independent worker/process, identical bound inputs and frozen context; absolute J discrepancy <= reproduction_tolerance",
    "margin_binding": "rank_order_gate rejects null acceptance_margin or a caller margin unequal to the frozen value"
  },
  "parameters": {
    "acceptance_margin": null,
    "reproduction_tolerance": null,
    "sharing_tolerance": null
  },
  "pins": {
    "metric_id": null,
    "evaluator_version": null,
    "scenario_manifest": null,
    "active_layer": null,
    "grid": null,
    "geometry_and_stack": null,
    "wire_metric_and_units": null,
    "wire_connection_matrix": null,
    "wire_x0": null,
    "wire_alpha": null,
    "wire_zero_baseline_absolute_cap": null,
    "margin_derivation_and_numerical_uncertainty": null,
    "family_manifest_and_stratified_order": null,
    "paired_seed_values_and_run_order": null,
    "hidden_corpus_and_split": null,
    "models_prompts_tools_and_memory": null,
    "lab_rosters": null,
    "reproducer_policy": null,
    "runtime_token_proposal_and_retry_cost_caps": null,
    "training_only_headroom_protocol": null,
    "pre_outcome_release": null,
    "physical_layout_canonicalization": null,
    "reference_and_refinement_charges": null,
    "sharing_round_barriers": null,
    "evaluation_attempt_order": null,
    "board_fallback": null,
    "required_final_evidence": null,
    "loss_counting_and_limits": null,
    "missing_reference_policy": null,
    "missing_scorer_policy": null,
    "missing_seed_policy": null,
    "global_stop_policy": null,
    "missing_family_primary_claims": null,
    "held_out_attempt_schedule": null,
    "held_out_seed_schedule": null,
    "held_out_idempotency_and_ordering": null,
    "held_out_symmetric_retry_limits": null,
    "held_out_retry_charges": null
  }
}
```
