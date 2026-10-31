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
| Sharing, B2 versus B3 | Confirmatory primary | Within each family average the two paired seed differences, B2 final accepted-board J minus B3 final accepted-board J; positive favors sharing. If no candidate is accepted, retain the frozen initial reference. |
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
| Missing required paired family | Inconclusive; never remove a failed/unfavorable family to improve inference. |

Average the two seed outcomes within each family before testing. `sign_test`
computes a two-sided p from non-tied counts; `holm` applies both thresholds and
requires both endpoint names. These helpers do not establish favorable direction,
completeness, family independence or resource-release approval. The analysis runner
must enforce those prerequisites and record ties and missingness. Q04 headroom
checks remain training-only and require the pinned development protocol; no
held-out outcome may select a margin, family subset or tuning decision.

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

## Frozen-reference epoch and reproduction barrier

| Phase | Rule, common to all five arms |
|---|---|
| Before search | Pin one immutable initial reference, all scenarios, geometry/stack, grid/layer/metric/evaluator, wire baseline, margins, lab roster and runtime/memory/model settings. |
| All search | Exactly one epoch per run. All labs compare to the frozen reference. B3/B4 may share evaluated evidence, but the accepted board cannot advance and no reproduction begins during search. B2 stays isolated. |
| Nominate | Filter qualification first, including both uncertainties. Each lab then nominates its best eligible evaluated J. B0/B1 nominate their top four distinct eligible physical layouts. Use each lab's own evaluation; never a model's selection or lab arrival order. |
| All reproductions | Start only after every lab closes search. Reproduce eligible nominations with bound inputs, all constraints/scenarios and independent worker/process evidence. Do not substitute if reproduction fails. |
| Final gate | Wait until every slot is reproduced, failed after its allowed retry, or explicitly unused. Rank all qualifying reproductions once, against the frozen reference, then resolve every loser against the resulting board. |
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

An epoch is scoped to family × seed × arm. The sharing-round schedule/barriers
remain `pins.sharing_round_barriers = null` until fixed before execution. The
search/reproduction barrier is mandatory in every arm. Completed scientific
failure is an observed outcome and consumes its opportunity. Missing data or an
unobserved infrastructure result is inconclusive, not a tie, a model fallback or
a free replacement. Best observed board data may still be reported descriptively
when the paired family is incomplete; it cannot supply confirmatory success.

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

Attempt status is `success`, `failed`, `infrastructure_failure` or `missing`.
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
records failures/mismatches and marks missing outcomes incomplete; reports
physical attempts, charged/unused slots, per-lab/total charges and the best
evaluated unreproduced physical layout. A duplicate successfully reproduced
elsewhere in the same context is not reported as unreproduced. The supplied
`search_charges` are verified per-lab ledger totals including initialization,
refinements, caches and failed/uncertain starts, not just successful candidates.
The function checks the 7-search/1-reproduction lab caps (28/4 for B0/B1); it does
not independently reconstruct search-launch accounting or enforce live reservations. `rank_order_gate` alone expects
already validated successful reproductions. These pure functions do not spend
resources or mutate the source ledger. The caller records their outputs.

## Admission-review adoption and departures

Review input: `SLAB-041-ADMISSION-REVIEW-2026-10-31.md` from PR #31,
SHA-256 `a96ae18722698a2052d0f133933a195eb8a649d42b8afc68ecf319dfecf6d64f`.
This file is not copied here. Warden made the three counterexample fixes binding;
the remaining recommendations are authoring guidance, pending independent review.

| Review section | Adoption or explicit limit |
|---|---|
| 1: Total order | Adopt exact, unrounded finite J then physical-layout hash; no tolerance comparator. |
| 2: Qualification/decision metric | Adopt eligibility before nomination, inclusive positive uncertainty-adjusted margin, and reproduced-J ordering. Search/decision metric and refinement pins remain null; no refinement is executed. |
| 3: Physical identity/measurement | Adopt separate layout/proposal/slot IDs, immutable context and one authoritative measurement. The adapter must select the first complete eligible measurement in predetermined attempt order, never a minimum over repeats. The pure API rejects conflicting purported authoritative records. It also requires one authoritative decision measurement for duplicate layouts; independent raw reproduction records remain upstream evidence. Exact physical serialization remains a must-fill pin. |
| 4: Opportunities/cache | Adopt distinct eligible B0/B1 nominations, separate duplicate lab charges, cache opportunity charges and no cross-arm reuse. Actual CPU/model/scenario cost and signed-event adaptation remain runner responsibilities. |
| 5: Retry/reference | Adopt one retry only on durable pre-execution proof; uncertain/post-start consumes the slot with no replacement. Initial-reference and refinement allocation stays null until a preparation-vs-inclusive charging choice is approved. |
| 6: Failure/missingness | Adopt completed scientific failure versus missing/inconclusive distinction, no model fallback or smaller corpus denominator, two-seed family aggregation and endpoint-specific tie handling. The fixed-corpus analysis runner is outside this patch. |
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
    "incomplete_required_pair": "inconclusive; no post-outcome family removal",
    "sharing_ties": "absolute family difference <= frozen sharing_tolerance",
    "worker_ties": "exact equality of rational success rates",
    "ties": "exclude endpoint-specific ties from that endpoint denominator and report n",
    "test": "two-sided exact family sign test; favorable direction required",
    "multiplicity": "Holm across sharing and worker",
    "alpha": 0.05,
    "first_threshold": 0.025,
    "second_threshold": 0.05,
    "eight_non_tied_required_wins": 8,
    "six_non_tied_rule": "6/6 may pass second at .05 only after the other primary passes first at .025; a six-family design stays descriptive"
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
    "cross_architecture": "same reproduction slot only if frozen reproducer policy authorizes it; no free extra evidence"
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
    "missing": "completed scientific failure is observed; missing or unobserved infrastructure result makes confirmatory inference inconclusive, never a tie or free replacement"
  },
  "nomination": {
    "ranking": "exact finite evaluated J ascending, then canonical physical-layout hash ascending; no tolerance in comparator",
    "same_hash": "one authoritative measurement per physical-layout/context; retain separate proposal/lab/slot identities and charges",
    "eligibility": "filter valid candidates first: positive reference J minus evaluated J >= acceptance_margin + reference uncertainty + candidate uncertainty",
    "no_substitute": true
  },
  "gate": {
    "contract": "contract-0.2",
    "ranking": "exact finite reproduced J ascending, then canonical physical-layout hash; accept the first qualified reproduction",
    "accepted": "one winner with positive improvement reaching the frozen-reference margin plus both uncertainties; becomes the board",
    "non_improving_current": "board J minus candidate J <= 0",
    "within_margin": "0 < board J minus candidate J < acceptance_margin + board uncertainty + candidate uncertainty; exact boundary qualifies",
    "valid_losers": "retain valid evidence; never stale_parent",
    "reproduction": "fresh independent worker/process, identical bound inputs and frozen context; absolute J discrepancy <= reproduction_tolerance"
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
    "sharing_round_barriers": null
  }
}
```
