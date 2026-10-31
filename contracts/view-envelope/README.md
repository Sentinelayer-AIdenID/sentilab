# View envelope vectors (for DRAFT v0.4)

Test vectors and a small reference implementation for `../view-envelope-0.4.md` (sha256 6a1eb642...). This is planning work, not a release.

## Files

- `view-envelope.mjs` is the reference implementation. It exports `genesis`, `hashEnvelope`, `signEnvelope`, `makeChain`, `verifyChain`, `checkCaps` and `mode`. It imports `canonical()` and `project()` from `../contract-0.2/` and does not copy them.
- `vectors-view.json` holds the vectors. Each chain has the core's input, the run the view requested, the page's pins and the keys it was served, the envelopes, a hand-written `expect` block, and the full `verifyChain()` result. There are also `mode`, `caps`, `hashing` and `canonical` cases.
- `run-view-vectors.mjs` regenerates every vector from the code and checks it against the file. It also re-derives the hash, chain, seq, signature and prefix rules separately, without using `view-envelope.mjs`.

## Run

```
node run-view-vectors.mjs           # check; exits non-zero on any failure
node run-view-vectors.mjs --write   # rewrite vectors-view.json from the code, then check
```

It was tested with Node 22.23 and has no dependencies. `../contract-0.2/run-vectors.mjs` must also still pass.

## Hash and sign rules

- `canonical()` is aneta's, from resultcheck.mjs. For these values it equals RFC 8785 (JCS). Absent fields are omitted, never `undefined` or `null`: both of those canonicalize to `null`, so neither hashes like an absent field.
- `hash` = sha256(canonical(envelope without `sig` and `hash`)), as lowercase hex. The verifier recomputes it from the content.
- `prev_hash` is the stored `hash` of the previous envelope by seq. For the first envelope it is sha256("sentilab-view-genesis:" + run_id), where run_id is the run the view requested.
- An envelope whose `run.run_id` is not the requested run is `run_mismatch`.
- `sig.value` is Ed25519 over the 64 hex characters of the recomputed hash as UTF-8. It is lowercase hex, 128 characters, and `sig.alg` is `"ed25519"`.
- `seq` must run 1, 2, 3 and so on. A seq equal to the previous one is `seq_repeat`; any other break is `seq_gap`. Only that envelope is flagged.
- `key_sha256` is sha256 of the raw 32-byte Ed25519 public key, which is the last 32 bytes of its SPKI DER, as lowercase hex.
- A key is used only if its `key_id` is in the page's pins and its `key_sha256` matches the pin. Otherwise the envelope is unverified (`key_not_pinned`, `key_unavailable` or `key_hash_mismatch`).

## Test keys

No key material is stored. The keys `core` and `forger` are derived at run time. The seed is sha256("sentilab-view-test-key:" + name), and the private key is PKCS8 DER `302e020100300506032b657004220420` followed by the seed. The vector file stores only the first 8 hex characters of each `key_sha256`, so other implementations can check how they derive it.

## verifyChain output

`verifyChain(envelopes, { runId, pins, keys })` returns `{ rows, chain_ok, prefix_end, frozen, label, projection, projection_error }`:

- `rows` has one entry per envelope in seq order: `{ seq, event_id, status, reasons, oversize, projected }`.
  - `status` is `verified` only when `reasons` is empty.
  - `oversize` lists cap codes; an empty list means the envelope is within the caps.
  - `projected` says whether the row is in the projectable prefix.
- `chain_ok` is true only if every row is verified. Oversize alone doesn't clear it.
- The projectable prefix is the longest run from seq 1 of rows that are verified and not oversize.
  - `prefix_end` is its last seq (0 if none), and `projection` is `project()` over exactly those events.
  - When any row follows the prefix, `frozen` is true and `label` is "chain broken after seq K; board frozen at seq K". Otherwise `frozen` is false and `label` is null.
- If `project()` throws, `projection` is null and `projection_error` is `project_threw`.

`mode(sourceKind, lastPollOkMs, lastVerifiedArrivalMs, nowMs)` uses client-clock times only. It returns:

- LIVE for `api` when a poll succeeded within 5 s and a verified envelope arrived within 60 s. Both limits are inclusive, and a time later than `nowMs` never counts.
- STALE for `api` otherwise.
- REPLAY for `file`.

## Caps

At most 64 KiB of canonical bytes for the whole envelope (`sig` and `hash` included), 64 entries in each capped `values` field, and 512 code points per string, with object keys counting as strings. Numbers must be finite, and nesting can go at most 8 levels deep, counting the envelope as level 1. Depth is checked first, without recursion, so a deeply nested envelope can't overflow the stack.

## The core's append checks

`makeChain` refuses what the core must refuse:

- a seq that isn't next;
- `undefined` anywhere, or `values` set to `undefined` or `null`;
- `values` on an event that can't carry them;
- an `actor_role` other than `lab`, `core` or `acceptance_gate`;
- `actor.lab` `gate` without the `acceptance_gate` role, or the reverse;
- a board outcome (`accepted`, `non_improving_current`, `within_margin`) not written by the gate;
- anything over a cap.

`append_checks: false` in a vector simulates a faulty writer.
