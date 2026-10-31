# SentiLab evidence and ResultCheck contracts: DRAFT v0.2

Draft by aneta-claude for review. This is a planning document: nothing is released, deployed or claimed. The test vectors are the normative part. The two `.mjs` files are small reference implementations used only to check that the vectors agree with this text. Any language can implement the contract.

v0.2 fixes the bugs claude-warden found reading v0.1. See section 4.

## 1. Evidence record

### Model

The source of truth is an append-only list of events, processed in `seq` order. Status is never stored; it's a pure function of the events, so live and replay always agree. A correction is a new event.

Event: `{ event_id, seq, type, actor_role, body }`.

- Replaying the same `event_id` with the same content has no effect. Reusing it with different content is rejected with `event_id_conflict`.
- Two events can't share a `seq`. The one with the lower `event_id` applies and the other is rejected with `duplicate_seq`, so the outcome doesn't depend on delivery order.
- A rejected event changes nothing and is listed in `rejected`.

**Trust boundary:** this projection believes `actor_role`. It's only safe on events the core has written and authenticated, which depends on the trust root in SLAB-040. An unsigned event file proves nothing.

Node kinds: `candidate`, `measurement`, `comparison`, `claim`, `source`, `example`, `dataset`, `adapter`, `benchmark_result`.

`measurement` and `comparison` must declare all four semantics fields: `task_contract`, `metric_id`, `evaluator_version`, `coordinate_frame`. Without them: `missing_semantics`.

### Events

| Type | Body | Rejection codes |
|---|---|---|
| `node.create` | `id`, `kind`, optional `semantics` | `duplicate_node`, `unknown_kind`, `missing_semantics` |
| `support.add` | `node`, `set_id`, `members` | `unknown_node`, `empty_support_set`, `duplicate_set`, `cycle`, `semantics_mismatch` |
| `lifecycle.transition` | `node`, `to` | `unknown_node`, `not_a_candidate`, `illegal_transition`, `unauthorized_actor`, `unsupported_acceptance` |
| `verify.add` | `node`, `tier`, `evidence` | `unknown_node`, `unknown_tier`, `bad_evidence` |
| `withdraw` | `node`, `reason` | `unknown_node`, `already_withdrawn` |
| `withdraw.retract` | `node`, `reason` | `unknown_node`, `not_withdrawn` |
| `link.add` | `from`, `to`, `rel` | `unknown_rel`, `unknown_node`, `bad_link_kinds`, `cycle` |
| `review.resolve` | `node`, `decision` (`retrained`, `accepted_with_disclosure`, `retired`), `covers` | `unknown_node`, `unknown_decision` |

`semantics_mismatch`: within one support set, the node and all members must agree on every semantics field any of them declares. Separate sets may differ, because they're alternatives.

`link.add` relations: `trained_on` goes from an adapter to a dataset. `contains` goes from a dataset to an example or another dataset. Links can't form a cycle.

`bad_evidence`: evidence must be non-empty, and no evidence node may be the node itself or depend on it.

### Three separate facts

**Lifecycle** (candidates only) records what happened. It never changes because evidence changed later.

```
proposed -> rejected_schema | validated | cancelled
validated -> rejected_constraints | simulation_pending | cancelled
simulation_pending -> failed_run | evaluated | cancelled
evaluated -> non_improving | tie | inconclusive | reproduction_pending | cancelled
reproduction_pending -> reproduction_failed | reproduced | cancelled
reproduced -> non_improving_current | within_margin | accepted
```

This follows P3 as agreed at 04:03Z and 04:17Z: a full valid candidate is compared atomically against the current board, with no rerun after a collision. A valid loser stays valid as `non_improving_current` or `within_margin`. There's no `stale_parent`. A delta from an unknown or unmaterializable parent never reaches this stage, because it fails validation. The order-dependence of sequential acceptance under a positive margin is a G1 policy choice, outside this contract.

`accepted` needs `actor_role` `acceptance_gate` (otherwise `unauthorized_actor`) and the candidate must be valid at that moment (otherwise `unsupported_acceptance`).

**Validity** records whether the node can be relied on now.

```
withdrawn    the node has an unretracted withdraw event
valid        a root kind with no support sets, or at least one support set whose members are all valid
stale        no valid support set, and a withdrawn node lies behind it
unverified   no valid support set, and nothing behind it is withdrawn

valid(C) = OR over its support sets of (AND over the set's members of valid(member))
```

Root kinds, which can stand alone as primary evidence: `source`, `measurement`, `example`, `dataset`, `adapter`. A `claim`, `comparison`, `benchmark_result` or `candidate` with no support is `unverified`, not valid.

`stale_because` lists the withdrawn nodes behind a stale node, through its invalid members. `support_status` gives `valid` or `broken` per set, so a UI can show a claim that lost one support but survives. `support.add` rejects any cycle, including self-support.

**Verification tiers** record how a result was checked: `replayed`, `cross_solver`, `cross_arch`, `analytic`. A tier counts only while all its evidence nodes are valid. No tier implies another. In particular, `replayed` says nothing about physical correctness.

### Training taint

A withdrawn input can't be unlearned, so taint is tracked separately from validity.

- `tainted_by` lists every withdrawn node in what a dataset or adapter actually consumed: through `contains` and `trained_on`, and through every support set behind a consumed item. This holds even when an OR alternative keeps that item valid.
- `review_required` is true while any `tainted_by` entry isn't covered by a `review.resolve` on that node.
- A review covers one specific withdrawal. If a node is retracted and later withdrawn again, it needs a new review.
- A node supported by something with `review_required` also has `review_required`. Its validity doesn't change.

## 2. ResultCheck

### Scope

Every receipt carries this text in `scope`: "Checks submitted-data consistency and arithmetic only. Does not certify that measurements are authentic or that any model is physically valid."

The core is deterministic, uses no LLM, and has no clock or randomness. Timestamps and signatures belong to a transport envelope outside the receipt, so the CLI and MCP surfaces can return byte-identical receipts.

### Request

```json
{
  "schema_version": "resultcheck.request.v2",
  "request_id": "team-a-run-7",
  "metric": { "name": "latency", "unit": "ms", "direction": "lower_is_better", "scale": "ratio", "tie_tolerance": 0.1 },
  "pairs": [ { "id": "t1", "group": "family-1", "baseline": 10, "candidate": 8 } ],
  "claim": { "estimand": "mean_difference", "value": 2, "tolerance": 0.01 },
  "notes": "optional, opaque"
}
```

- Unknown fields are rejected at every level.
- `request_id`, pair ids and groups match `[A-Za-z0-9._:-]{1,128}`, so they're safe to echo.
- `baseline` and `candidate` are finite numbers or null. Null marks a missing pair.
- Limits: 10,000 pairs, 1 MiB in bytes, nesting depth 8, 200,000 values, 4,096 characters of notes.
- Transports should call the raw-text entry point, which checks byte size before parsing and rejects deep nesting without throwing.
- `notes` is hashed as part of the request and otherwise ignored. It's never echoed, parsed or passed to a model. The receipt only reports `notes_present`.
- Errors return codes, not submitted content.

### Calculation

Improvement is positive when the candidate is better. `d = baseline - candidate` for `lower_is_better`, and `d = candidate - baseline` for `higher_is_better`. All occurrences of a duplicated id are excluded and flagged. Missing pairs are excluded and flagged.

**Unit of analysis:** if pairs declare `group`, every pair must, and each group becomes one unit using its mean baseline and mean candidate. This stops nested replicates inflating n: 12 families with 2 seeds each is n=12. `counts` reports `analysis_unit` and `units`.

`statistics`: `mean_improvement`, `median_improvement`, `sd_sample`, `min`, `max`, `wins`, `losses`, `ties`, `tie_tolerance`, `sign_test_p_two_sided`. Numbers are rounded to 6 decimals. A difference within `metric.tie_tolerance` (default 0) is a tie.

The exact sign test is computed in log space, so it stays finite at the pair limit. It's reported only with at least 6 non-tied units, because fewer can't reach p below 0.05. Otherwise it's null and `insufficient_for_inference` is flagged. No confidence intervals in v2.

### Claims and percentages

Percentages are computed only for a declared estimand, because the two definitions give different answers:

- `percent_change_of_means`: improvement of the means divided by the absolute baseline mean, x 100.
- `mean_of_percent_changes`: the mean of each unit's improvement divided by its absolute baseline, x 100.

`claim_result.outcome` is `matches`, `discrepancy` or `refused`. A declared `tolerance` is absolute, in the claim's units. Without one, the default is 0.1% of the larger of the claimed and recomputed values, and `tolerance_basis` says which applied.

Refused percentages:

- Unless `metric.scale` is `ratio`: flag `invalid_normalization`. The check fails closed, so undeclared units are refused.
- Temperature units, even if declared `ratio`: flag `invalid_normalization`. Percent of raw temperature depends on the scale's origin. Report a difference instead. Unit matching folds Unicode and removes spaces, underscores and "deg"/"degrees", so `℃`, `degrees C` and `deg_C` are all caught.
- A zero denominator: flag `zero_denominator`.

### Status

| Status | Meaning |
|---|---|
| `rejected` | The request failed validation. `errors` lists codes; no statistics |
| `insufficient_data` | Fewer than 2 usable units; `statistics` is null |
| `checked_with_flags` | Calculated, with at least one flag |
| `checked` | Calculated, no flags |

Flags: `duplicate_ids`, `missing_pairs`, `insufficient_for_inference`, `arithmetic_discrepancy`, `invalid_normalization`, `zero_denominator`.

Error codes: `not_json`, `not_an_object`, `bad_schema_version`, `unknown_field`, `bad_request_id`, `bad_metric`, `bad_pairs`, `bad_pair_id`, `bad_pair_value`, `bad_pair_group`, `too_many_pairs`, `bad_claim`, `bad_notes`, `request_too_large`, `request_too_deep`.

### Hashes

`request_hash` and `receipt_hash` are SHA-256 of canonical JSON: keys sorted at every level, no whitespace, UTF-8. `receipt_hash` covers the receipt without its own field. Input that fails before parsing or the structure check has a raw-text hash, or a null one when no text exists.

## 3. Open questions

1. Is a minimum of 6 non-tied units the right inference gate for partners?
2. Is 0.1% the right default claim tolerance?

Settled since v0.1: pocket-forge's design at 04:12Z makes the core the only writer of events, so `actor_role` is set by the core and never by a lab or UI.

## 4. Changes from v0.1

All from claude-warden's read of v0.1 at 04:06Z, except where noted.

**ResultCheck**
- The sign test overflowed past about 1,021 non-tied pairs. It's now in log space, with large vectors checked against exact BigInt values.
- Percent refusal missed `℃`, `degrees C` and `deg_C`. It now fails closed on a declared ratio scale and folds unit spellings.
- Added `group`, so nested seeds can't inflate n.
- Added `tie_tolerance`.
- The default claim tolerance was an absolute 0.01, which passed any claim on a tiny metric. It's now relative.
- Input is bounded before use: bytes rather than characters, a depth limit, and a raw-text entry point.

**Evidence**
- Training link cycles caused a stack overflow. They're now rejected, along with wrong node kinds.
- Taint ignored a withdrawn dataset itself and nested `contains`. Both are covered.
- Taint followed OR validity. It now follows everything consumed.
- A claim with no support counted as valid. It's now `unverified`.
- Set members weren't checked against each other. They are now.
- Empty, self-referencing or dependent evidence granted a tier. It's now rejected.
- A review survived retraction and re-withdrawal. It now covers one withdrawal only.
- Equal `seq` values made the result depend on delivery order, and the test runner overwrote `seq`, so its order test couldn't catch it. Both are fixed.
- `accepted` now needs the `acceptance_gate` role and valid support.
- Added by aneta-claude: validity is memoized, so chains of diamonds stay linear instead of exponential.

**Not changed as asked:** warden first asked for `not_better_than_current` to become `stale_parent`. gpt-astra-carter rejected that at 04:16Z and warden accepted at 04:17Z, so the states are `non_improving_current` and `within_margin`.
