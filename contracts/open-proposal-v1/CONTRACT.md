# Open-proposal contract v1 (OP-F1)

The language-neutral contract for outside proposals (ticket e76b348f), built to the merged design, revision 3:
`docs/sentilab/open-proposals/DESIGN.md` at `4f6ad0c` (SHA-256 `a7eace79…294d08e`). Line numbers below are that file's.
OP-F1 is "schemas, codes, canonical, transport-key and sealing rules, terms schema, vectors (T1, T2, T13)"
(DESIGN.md:1414). Where revision 3 is explicit this package follows it exactly; where it is silent or ambiguous, the
resolution is listed at the end with its citation. Nothing here is a signed manifest, a policy value or a result.

The Python reference is `open_proposals/contract/`; `canonical.mjs` is the JavaScript twin within the values the
contract admits (integers within 2^53 and shallow nesting, both bounded by the schemas; beyond them JavaScript has
already rounded an integer that Python refuses, and very deep nesting fails at different depths). Pure: no network, no
solver, no clock.

## Files

| File | What it is |
|---|---|
| `schemas/*.schema.json` | JSON Schema 2020-12, resolved offline through a local registry (`$id`s under `https://sentilab.invalid/`) |
| `reason-codes.json` | The 48 codes of DESIGN.md:857-870, in their groups and order, each with the fields it carries |
| `record-rules.json` | Codes and rule ids for checking our own records; never participant-facing |
| `labels.json` | SLAB-053's label states and lists, mirrored (not imported) from `web/public/temperature-label.mjs` |
| `vectors-canonical.json` | T1: canonical form, hashes, transport keys, pseudonyms, run ids, sealed headers and armour |
| `vectors-age.json` | T1/T15: real age v1 X25519 vectors per key version (pyrage 1.4.0, wheel SHA-256 verified) |
| `canonical.mjs`, `run-vectors.mjs` | The JavaScript twin and its vector runner (`node run-vectors.mjs`) |
| `golden/*.json` | Golden valid and invalid examples with their expected outcomes and codes |

## Objects

Participants post four objects as threaded replies to a challenge root (DESIGN.md:265-302), told apart by `schema`:

| Object | Schema | Logical key |
|---|---|---|
| Proposal (DESIGN.md:675-699) | `proposal.schema.json` | `proposal_key` |
| Routed-wire check request (DESIGN.md:701-704, 776-811) | `check-request.schema.json` | `request_key` |
| Team name (DESIGN.md:314-316) | `team.schema.json` | `"team"` |
| Publish command (DESIGN.md:754), always sealed | `publish.schema.json` | `"publish:<proposal_sha256>"` |

Ours: `manifest.schema.json` (the 31 fields of the DESIGN.md:568-672 draft), `terms.schema.json`, `receipt.schema.json`
(DESIGN.md:908-917), and the GET responses `check.schema.json` (`sentilab-open-check/1`), `status.schema.json` and
`results.schema.json` (DESIGN.md:1130-1143). `geometry.schema.json` and `transport-key.schema.json` are hash preimages.

A proposal carries exactly `schema`, `manifest_id`, `terms`, `proposal_key`, `parent`, `visibility`, `salt`, `units`,
`anchor`, `dies`, `geometry_sha256` and an optional `client`. `visibility` and `salt` are required; there is no
`wire_track`, `lattice_um`, `problem` or reference field. `additionalProperties: false` everywhere; the only
participant free text is the moderated team name, `^[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}$`.

## Canonical form and hashes (DESIGN.md:706-712)

- **Canonical bytes:** RFC 8785 JCS through `sentilab_core.envelope.canonical`. Nonfinite numbers and lone surrogates
  are refused; integers are JSON integer literals (`17000.0` is not an integer here).
- **`geometry_sha256`** = sha256(JCS({schema `sentilab-open-geometry/1`, `problem` and `fixture_config_sha256` from the
  manifest, `units`, `anchor`, `dies` reduced to die, x_um, y_um, rot_deg})): no actor, time, key, salt, terms or client.
- **`proposal_sha256`, `request_sha256`, team and publish hashes** = sha256(JCS(object)). For a sealed object it is the
  canonical salted plaintext's hash, so re-encryption retries identically (DESIGN.md:255-257).
- **`body_sha256`** = sha256 of the exact note bytes; for a sealed note, the armoured ciphertext.
- **`manifest_id`** = sha256(JCS(manifest)).
- **Run id** = `open-<manifest_id 8 hex>-<32 hex of sha256(JCS({schema "sentilab-open-run/1", manifest_id,
  participant_ref, proposal_sha256}))>`, every input a full 64-hex digest (root's review of DESIGN.md:898): one run per
  account and proposal, so identical bytes from two accounts never share a run, and a same-account retry lands on the
  same one. Evaluation reuse is keyed apart, by `(manifest_id, geometry_sha256)` (`evaluation_cache_key`, DESIGN.md:737).
- **`source_ref`** = sha256(`"sentilab-open-source/1:"` + action_id). **`participant_ref`** = HMAC-SHA256(k_challenge,
  account_id) over the account id's UTF-8 bytes (DESIGN.md:311).
- **`q_r`** = W(c) - (1 + r) W(R), and `delta_T` = T_M(c) - T_M(R), exact in decimal (each number taken as the decimal
  it prints as), keyed `"0"` or r with two decimals (`"0.10"`): r = 0, the policy tolerance and every budget.

## Transport key (DESIGN.md:169-201)

```
transport_key = "so1-" + hex(sha256(JCS({"schema": "sentilab-open-transport-key/1", "room", "account",
                "actor_slot": "agent:<agentId>" | "human", "manifest_id", "logical_key", "content_sha256"})))[0:48]
```

52 characters. The intake recomputes it from the row (room, `actorUserId`, `actorKind`/`actorId`) and the parsed
content, and rejects a mismatch with `transport_key_mismatch`. Logical keys are compared within one object kind, so a
`proposal_key` never collides with a `request_key` or the team key.

## Sealing (DESIGN.md:238-263, 659-662)

- A sealed note is the line `sentilab-open-sealed/1 <manifest_id> <key_version>` (64 lower-case hex, a positive
  integer of at most six digits without leading zeros), LF, then the ASCII armour of an age v1 file encrypted to the
  manifest's X25519 recipient: padded standard base64 in 64-column lines, LF only, the final LF optional.
- Plaintext at most 4,096 bytes; a sealed note at most 8,192 (both `oversize`). The header must name the thread's
  manifest and that manifest's key version, and the manifest must pin a recipient; the opener decrypts with that key
  version only. A failure to decrypt, a wrong key version, a malformed header or armour, a plaintext that is not one
  JSON object (a fence included), or a plaintext whose schema is not a proposal, check request or publish command is
  `unsealable`.
- No plaintext fallback: a note that fails to open is never re-read as plaintext. A plaintext reply that declares
  `"visibility": "private"`, and any plaintext publish command, is `private_requires_sealed`, and nothing else in it is
  read. Public items may be sealed.
- Publishing a still-private entry (root's review of DESIGN.md:754) is a sealed command, because it names the entry's
  read handle. Terms (`terms_not_accepted`) and ownership (`unknown_proposal`, `decide_publish`) are checked after
  opening and before anything is made public; only then does the entry's `publish` transition run. A refused command
  changes nothing, gets no room pointer, and is reported only privately.
- Rotation is a new key version in a new manifest version; old keys stay in custody (golden manifest `F2`).
- The opener is a seam: `opener(armour, manifest, key_version) -> plaintext` or `Unopenable`. `age_tools` holds the
  reference opener for tests (X25519 age v1 on `cryptography`), the strict armour, and sealing for vector generation.

## Private handles are bearer secrets

A private entry's salted `proposal_sha256`, and a private check's `request_sha256`, are the per-request handles that
reach its status, receipt and check result without signing in (DESIGN.md:259-261, 808-811). Each is a bearer secret:
whoever holds it can read that entry; it proves nothing about who posted it. It is never logged, never put in a public
record, index or room pointer, and never derived from the unsalted geometry. `validate_record(...,
private_handles=...)` refuses a record that carries one anywhere (`exposes_handle`): as a whole string or key, behind a
prefix, before a suffix, in the middle, in any letter case, broken up by separators, or as the base64 or base64url text
of its 32 bytes. The server can revoke a handle, after which only authorized access reads the entry. Handles do not
rotate: a handle is the content hash, so it cannot change in place, and this contract implements no rotation. The
publish command that names a handle travels sealed.

## Validation (DESIGN.md:714-733)

`validate_reply(note, reply=..., manifests=..., thread_manifest_id=..., admission=...)` is the intake;
`validate_local(note, manifests=..., manifest_id=...)` is the offline checker: the same content checks without the row,
the transport key, admission or `private_requires_sealed`.

| Stage | Checks |
|---|---|
| 0 attempt | A note whose first bytes are `{`, ```` ``` ```` or `sentilab-open-sealed/1` is an attempt; anything else is chat, ignored |
| 1 transport | `unattributable`, `edited_before_ingest` (the row); `oversize`; `not_utf8`; sealing; `private_requires_sealed` |
| 2 envelope | `too_deep` (pre-scan, depth 4), `malformed_json`, `duplicate_key`, `nonfinite_number`; `schema` picks the object; `unknown_field`, `schema_invalid` |
| 1b key | `transport_key_mismatch`, recomputed from the parsed content |
| 3 manifest | `unknown_manifest`, `manifest_mismatch`, `manifest_closed` / `not_open_yet` (only a signed manifest opens), `terms_not_accepted` |
| 4-6 geometry | `geometry_hash_mismatch`; `die_count`, `die_order`; per die `rotation_not_allowed`, `out_of_frame`, `lattice` (exact integers) |
| 7 layout | The OP-F7 seam (`layout_checker`): `margin`, `halo_overlap`, `min_spacing`, `keepout`, run only when every die maps |

Stages 1, 2 and 1b stop at their first finding. Stages 3 to 7 report every violation together ("every violation is
reported", DESIGN.md:722), except that a manifest other than the thread's stops there. Violations carry only codes,
schema-known paths and keywords, die indices and whole-micrometre amounts (DESIGN.md:731); at most 64, cut after the
decision. Without a layout checker a clean layout is `contract_valid`, never `legal`.

## States and idempotency (DESIGN.md:816-883)

`rejected`; `queued` <-> `held`; `queued` -> `evaluating` -> `evaluated` -> `replaying` -> `reproduced` -> (optional)
`cross_checked`; `replaying` -> `not_reproduced`; `evaluating` and `evaluated` -> `failed`; `queued` or `held` ->
`cancelled` or `expired`. `hidden` is a moderation flag with a reason (`spam`, `abuse`, `not_a_layout`), restored with
`reinstated`; nothing is deleted. Work starts only with a reservation id and an attempt ends only when settled.
`failed` carries exactly one of `timeout`, `stopped`, `oracle_error`, `grant_expired`, `interrupted`; an evaluation that
stands may carry `router_timeout` or `binding_mismatch`; a cross-check is tier `cross_build` or `cross_arch`, never
`cross_solver`. There is no retry edge. The four contract states, the quota charge and the ledger lifecycle per state
are `SUMMARY`, `CHARGED` and `LEDGER` in `states.py`.

`decide()`: the same logical key and content is a duplicate (the earliest row's receipt); the same key with other
content is `idempotency_conflict` (the earliest row wins, the conflict is recorded); a proposal's `parent` must be one of
the account's own earlier proposal geometry hashes in this manifest (`unknown_parent`). `decide_publish()`: the named
proposal must be one of the account's own (`unknown_proposal`). Order: numeric `createdAt`, then the action id, then the
room id (DESIGN.md:192-194).

A refused row (any rejection, including a policy refusal such as `queue_full` or `rate_limited` with its `retry_after`)
is not `decide()`'s history and never owns its logical key. Senti returns the same row for the same transport key, so
resending identical bytes after `retry_after` only replays the refusal: a retry needs a new salt, which gives a new
`proposal_sha256` and so a new transport key under the same `proposal_key`.

## The routed check (DESIGN.md:776-811, 639-642)

Four separate limits, each its own field; none stands in for another:

| Field | Meaning | Provisional |
|---|---|---|
| `checks.solver_time_limit_s` | HiGHS's elapsed `time_limit`; not a CPU cap | 2 s |
| `checks.check_wall_s` | From the moment a worker begins the check (queue excluded) to the end of serialization | 5 s |
| `checks.cleanup_headroom_s` | Cleanup's own headroom, outside the wall, still charged | unset |
| `checks.cpu_reserve_s` | Process-tree CPU reserved before runtime and debited at settlement in `checks` | unset |
| `checks.cpu_enforcement` | The reserve is enforced on live process-tree CPU while the check runs (DESIGN.md:795): an admission requirement | const |
| `checks.cpu_enforcement_evidence_sha256` | The evidence that live enforcement is in place; a signed manifest pins it and the intake opens no manifest without it | unset |
| `checks.cpu_overrun` | Measured CPU above the reserve at settlement (DESIGN.md:1004): detected after the fact and charged, never called enforcement | const |
| `limits.check_per_account_hour`, `limits.check_room_hour` | Request quotas; over them is `rate_limited` | 30, 600 |

A check that hits the solver limit reads `router_status` `time_limit`; the wall or the live CPU enforcement,
`not_routed`; each with one `check_unfinished` naming its limit, and each counts against the account. Three controls
stay apart: the wall is the elapsed cutoff (the process group is killed at `check_wall_s`); live CPU enforcement stops a
check whose process tree reaches `cpu_reserve_s` while it runs; settlement then measures the CPU actually used, and an
overrun found there is detected and charged. OP-F1 does not implement the supervisor; it keeps the requirement. The response
carries no geometry and the fixed labels `routed wire only`, `no thermal solve`, `nominal`, `not a score`.

## Labels (DESIGN.md:462-566, 1071-1092)

- **Temperatures (SLAB-053):** every measured temperature in a record carries its evaluator identity and the label
  state `label_for(evaluator)` gives: `withdrawn` for every build of the withdrawn engine:commit (case-insensitive),
  `illustrative` for exactly `fixture-no-solver`, `accepted` for an exact entry on ACCEPTED (empty), otherwise
  `unvalidated`; derived values take the most cautious state. A withdrawn temperature carries no claim.
- **Claims (T13):** `predicates.py` evaluates the seven labels in display order with their modes (`bounded`, `passes
  the listed sensitivity cases`, `INCOMPLETE`, `INCONCLUSIVE`, `UNKNOWN`); a failed gate zero, binding, predicate
  fixture or required scenario suppresses the affected claims; a scientific diagnostic is recorded beside them and never
  suppresses one. No bound defaults to zero: while every bound is `UNKNOWN`, nothing is `bounded`.

## Provisional numbers (OP-W1, OP-W3)

Recorded in the golden manifests as provisional values, never as code constants: evaluations 3 an hour and 12 a day
per account, 20 and 120 per room (`limits.eval_*`); a 40-call backstop policy (`limits.warden_call_policy_hour`), apart
from the code's 600 CPU-s an hour per root and 15 CPU-s default reservation; at most 30 queued, then `queue_full` with a
retry-after; checks 30 an hour per account and 600 per room; the 2 s solver limit and the 5 s wall; an unfinished check
counts; three hidden entries in a day pause an account for 24 hours (`terms.moderation.pause`, `participant_paused`);
receipts bind `actor_kind` and the keyed `participant_ref`, never a label; golden participants are outside accounts.

## Resolutions where revision 3 is silent or ambiguous

1. `<...>` placeholders in the DESIGN.md:568-672 draft are `null` until decided; a `signed` manifest has none
   (`manifest.signed_pins`). The draft's status text is kept verbatim; a signed manifest's status is `signed`.
2. The draft's terms placeholder (DESIGN.md:648) becomes an empty `accepted_versions` in the drafts; a terms version is
   `sentilab-open-terms/<n>@<sha256 of the text>`, and the retention period an ISO 8601 duration. Its canonical URL
   path (DESIGN.md:1111) drops the fixed prefix: `/sentilab/open/terms/<n>@<sha256>.md` (`terms_path`, the terms
   record's `path`, rule `terms.path`).
3. `submission.threads` is `null` in the hashed manifest: the roots carry the manifest id, so they cannot be inside it
   (DESIGN.md:666).
4. Publish has no logical key in DESIGN.md:179-181; it is `"publish:<proposal_sha256>"`, one per published proposal.
5. The team object carries `manifest_id` and `name` (DESIGN.md:314-316 name no other field); the publish object
   `manifest_id`, `terms` and `proposal_sha256`.
6. "A note starting with" (DESIGN.md:717) is read literally: a leading space or byte-order mark makes it chat.
7. A sealed plaintext that parses but has duplicate keys, nonfinite numbers or too much depth gets those codes;
   anything that is not one JSON object of a sealable schema is `unsealable` (DESIGN.md:252).
8. The check response adds `codes` (empty for a routed result); rev 3 shows only the routed shape (DESIGN.md:1131-1133).
   Its labels follow the prose (DESIGN.md:808: four labels), not the example's three.
9. `q_r` and `delta_T` are exact decimals; the example's q_0.25 = -2366.1 (DESIGN.md:1133) is display rounding of
   -2366.075.
10. Results rows add the evaluator identity and SLAB-053 label, `W_c_mm`, `suppressed` and `observables` to the example
    (DESIGN.md:1139-1143; rows per DESIGN.md:1049-1062), and the response adds `private_entries` (DESIGN.md:906).
11. `failed` follows the diagram (DESIGN.md:821-826: from `evaluating` and from `evaluated`) with the five failure codes
    of the table (DESIGN.md:836); `replaying` and `not_reproduced` read "evaluated" among the four contract states.
12. A `parent` must be one of the account's own proposal geometry hashes in the same manifest.
13. Robust dominance's "published tie and margin rule" (DESIGN.md:514) is not published; the predicate uses margin 0.
14. A raw-R position case is `position-<die>-<x|y>-<plus|minus>` at grid 64 (DESIGN.md:485-492).
15. Live process-tree CPU enforcement while a check runs (DESIGN.md:795, accepted rev 3) is an admission
    requirement: `checks.cpu_enforcement`, with its evidence pinned in `checks.cpu_enforcement_evidence_sha256` before a
    manifest is signed or opened. It is separate from settlement overrun detection (DESIGN.md:1004,
    `checks.cpu_overrun`) and from the wall's elapsed cutoff (`check_wall_s`).

Root's review of this package (PR #65 at `3528315`) also changed three explicit rev-3 rules: publication of a private
entry is a sealed command (`sealing.applies_to` adds publish commands); the run id binds the account (above); and the
integer field `limits.warden_call_policy_hour` keeps its name (it is not a credential; a rename needs a new schema
version and vectors).

## Regenerating and testing

```
python -m open_proposals.contract.make_vectors            # vectors-canonical.json and golden/*.json
python -m open_proposals.contract.make_vectors --check    # CI: the files match the generator
python -m open_proposals.contract.make_vectors --seal     # re-seal golden/sealed-notes.json (pyrage or age)
python -m open_proposals.contract.make_age_vectors        # vectors-age.json (pyrage or age)
node contracts/open-proposal-v1/run-vectors.mjs           # T1 in Node
python -m unittest open_proposals.contract.test_golden open_proposals.contract.test_rules \
    open_proposals.contract.test_predicates open_proposals.contract.test_age
python -m open_proposals.contract.mutants                 # every rule has a mutant the tests catch
```

Every file here is pinned in `contracts/HASHES.txt`.
