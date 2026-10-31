# Live paging vectors (for DRAFT v0.6)

Paging vectors and a pure reference reducer for `VIEW-ENVELOPE.md` in this folder (sha256 93386849...), rules 4 and 5. The envelope format and every verification rule are v0.5's. `paging.mjs` imports them from `../view-envelope-v0.5/view-envelope.mjs` and does not copy them. This is planning work, not a release.

## Files

- `paging.mjs` is the reducer and the reference server. It reads no clock, network, randomness or files, and it never mutates a state.
- `vectors-paging.json` holds the vectors:
  - bytes-to-rows cases;
  - cursor-hash cases;
  - C7 server conformance;
  - scenarios C1 to C6 and C8 to C11, each with its polls, what the server does at each poll, hand-written expectations and the full trace.
- `run-paging-vectors.mjs` regenerates every vector and checks it. It also checks invariants on every scenario and recomputes each hash separately. The V1 envelopes are read from `../view-envelope-v0.5/vectors-view.json`.

## Run

```
node run-paging-vectors.mjs           # check; exits non-zero on any failure
node run-paging-vectors.mjs --write   # rewrite vectors-paging.json from the code, then check
```

It was tested with Node 22.23 and has no dependencies.

## Exports

- **Client:** `initialState(runId, { limit })`, `request(state)` and `step(state, { status, headers, bodyBytes }, nowMs)`. `step` returns `{ state, outcome, newRows }`, where `outcome` is `ok`, `transport`, `paging_error`, `stream_replaced` or `paging_unsupported`.
- **Verification:** `verifyRows(state, { pins, keys })` returns `{ verification, K }`. `verifyBytes(rows, options)` verifies raw rows, and `verifyReplayBytes(fileBytes, options)` does the same for a replay file.
- **Label:** `liveLabel(state, tracker, nowMs, K)`, where `tracker` is the v0.5 `progressTracker()` and `K` is the current projectable prefix.
- **Server:** `servePage(logRows, { cursor, limit, cursor_hash })` returns `{ status, headers, bodyBytes }`.
- **Byte helpers:** `cursorHash(rows)`, `splitRows`, `joinRows` and `rowText`.

## Rules as implemented

- **Bytes to rows.**
  - Raw bytes are split on LF (0x0A) only, and a trailing LF doesn't start a row.
  - Each row is decoded on its own as strict UTF-8, keeping any BOM.
  - A row that isn't valid UTF-8 is a `malformed` row with reason `invalid_utf8`. If it is over 64 KiB, it is `oversize` instead, because raw size is checked first.
  - A row that starts with a BOM is `malformed` with reason `not_json`.
  - The same rule applies to replay files.
- **Cursor hash.** The cursor hash is SHA-256, lowercase hex, over the raw bytes of each row followed by one LF. Decoded text is never hashed.
- **A valid page** has status 200 and a body within 256 lines and 4 MiB. Its `x-next-cursor` is a plain decimal equal to the cursor plus the rows returned. Its `x-cursor-hash` equals the client's own hash of every row it would then hold.
- **Failed polls.** A failed poll keeps no rows and never moves the cursor.
  - `transport` covers no response, a status other than 200, 400, 404, 409 or 501, and a body over the caps.
  - `paging_error` covers a bad `x-next-cursor` or `x-cursor-hash`.
  - `stream_replaced` is a 409, and `paging_unsupported` is a 400, 404 or 501. Both stay until a manual reload, which means a new `initialState`.
- **Label.** It is decided in this order:
  1. A failed latest poll shows "STALE · transport", "STALE · paging error", "STALE · stream replaced" or "STALE · paging unsupported".
  2. Otherwise, if K is below the highest value it has reached, the label is "STALE · chain broken", at once.
  3. Otherwise the v0.5 tracker, fed only with valid pages, gives LIVE or STALE.
- **Server.**
  - A cursor or limit outside its range gets 400.
  - A cursor beyond the end gets 409, as does a cursor above 0 that comes without a `cursor_hash` or with one that doesn't match.
  - Otherwise the server returns up to `limit` rows within 4 MiB, with `x-next-cursor`, `x-has-more` and `x-cursor-hash`.
