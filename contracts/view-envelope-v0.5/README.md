# View envelope vectors (for DRAFT v0.5)

Test vectors and a small reference implementation for `VIEW-ENVELOPE.md` in this folder (sha256 7a92d88a...). This is planning work, not a release. The v0.4 work stays in `../view-envelope/`.

## Files

- `view-envelope.mjs` is the reference implementation. It imports `canonical()` and `project()` from `../contract-0.2/` and does not copy them.
- `vectors-view.json` holds the vectors:
  - `chains`: V1 to V11 and V13 to V15.
  - `live`: V16 and V17.
  - `transport`: V18.
  - `input_checks`: V12.
  - Also `mode`, `hashing` and `canonical` cases.
- `run-view-vectors.mjs` regenerates every vector from the code and checks it against the file. It also re-derives the chain, duplicate, conflict and prefix rules separately, without using `view-envelope.mjs`.

## Run

```
node run-view-vectors.mjs           # check; exits non-zero on any failure
node run-view-vectors.mjs --write   # rewrite vectors-view.json from the code, then check
```

It was tested with Node 22.23 and has no dependencies. `../contract-0.2/run-vectors.mjs` must also still pass.

## Exports

- **Transport:** `parseApiResponse(text)` and `readReplayFile(text)` check the transport caps before anything is parsed. Each returns `{ ok: false, reason }` or `{ ok: true, lines }`.
- **View:** `verifyJsonl(textOrLines, { runId, pins, keys })` runs input-check steps 1 to 5 on each line. `verifyChain(envelopes, options)` does the same for envelopes that are already parsed, starting at step 3.
- **Core:** `makeChain(run, entries, values, key)` is the core's writer.
- **Single checks:** `checkLine(line)` runs steps 1 to 4 on one line, and `checkEnvelope(env)` runs steps 3 and 4 on one parsed envelope.
- **Mode:** `mode(sourceKind, lastPollOkMs, lastProgressMs, nowMs)`, `modeLabel(...)` with the same arguments, and `progressTracker()`.
- **Instrumentation:** `counters` and `resetCounters()` count calls to parse, `canonical()`, envelope hash, sign and verify.
- **Hashing:** `canonicalSize(value)`, `genesis(runId)`, `hashEnvelope(env)`, `signEnvelope(env, privateKey, keyId)` and `keySha256(publicKey)`.

## Input checks, in order

Both the core and the view run these before anything is hashed, signed or verified.

1. **Raw size.**
   - A line is at most 65,536 bytes. A longer line is never parsed.
   - An API response is at most 256 lines and 4,194,304 bytes. A larger one is a transport error, and the poll counts as failed.
   - A replay file is at most 64 MiB.
2. **Parse** the line as JSON.
3. **Structure,** checked with an explicit stack and no recursion:
   - Nesting is at most 8 levels deep, counting the envelope as level 1. Only objects and arrays count.
   - Strings and keys are well-formed UTF-16 with at most 512 code points.
   - Numbers are finite.
   - Each capped `values` field has at most 64 entries.
   - The schema holds.
4. **Canonical size** is at most 65,536 bytes. It is measured by `canonicalSize()`, which counts canonical bytes without calling `canonical()`.

A failure becomes one row with status `oversize` or `malformed` and the reason codes. The core holds objects, not lines. For step 1 it measures the line it will write, with placeholders of the final length for `hash` and `sig`. It has no step 2.

## Hash and sign rules

- `hash` = sha256(canonical(envelope without `sig` and `hash`)), as lowercase hex. The verifier recomputes it from the content.
- `prev_hash` is the stored `hash` of an envelope at the previous seq. For the first envelope it is sha256("sentilab-view-genesis:" + run_id), where run_id is the run the view requested.
- `sig.value` is Ed25519 over the 64 hex characters of the recomputed hash as UTF-8. It is lowercase hex, 128 characters.
- `key_sha256` is sha256 of the raw 32-byte public key, which is the last 32 bytes of its SPKI DER. A key is used only if its `key_id` is pinned and its hash matches the pin.

## Duplicates, conflicts and the prefix

- **Duplicates:** envelopes with identical canonical bytes, `sig` and `hash` included, count once. The copies make no row.
- **Conflicts:** different envelopes in the same run that share a seq get `seq_conflict`, and those that share an event_id get `event_id_conflict`. Every envelope involved is flagged.
- **The core's policy:** it refuses a conflict before signing and treats a byte-identical retransmission as a no-op.
- **Row order:** rows are in seq order. At one seq, rejected rows come first, then envelopes by stored hash, so delivery order never changes the result. Rejected rows whose seq can't be read come last.
- **The prefix:** the projectable prefix is the leading run of verified rows, and K is its last seq. The board is `project()` over exactly those events. When anything follows, the label is "chain broken after seq K; board frozen at seq K".

## Mode

`progressTracker()` is fed `{ nowMs, ok, K, received }` after every poll. A poll counts as good only if `ok` is true. Progress is recorded only when K rises above its highest value so far. `received` is ignored on purpose.

LIVE needs a good poll within 5 s and progress within 60 s. Both limits are inclusive, and only the client clock is used. The label reads "LIVE · progress N s ago" in whole seconds. Otherwise the mode is STALE for the API and REPLAY for a file.

## Test keys

No key material is stored. The keys `core` and `forger` are derived at run time. The seed is sha256("sentilab-view-test-key:" + name), and the private key is PKCS8 DER `302e020100300506032b657004220420` followed by the seed. `append_checks: false` in a vector simulates a faulty writer that signs anything; it is used only to build negative vectors.
