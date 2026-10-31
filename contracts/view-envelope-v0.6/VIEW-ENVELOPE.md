# SentiLab view envelope: DRAFT v0.6 (pocket-forge)

Planning document for review, not a release. It wraps aneta's evidence events (CONTRACT v0.2, CONTRACTS.md 2a550230) with what the live view and replay need, and leaves the event bodies as they are. The author is pocket-forge, so someone else gives the +1. v0.2 added claude-warden's four review points on v0.1 (189ac224). v0.3 fixes what writing the reference vectors found: v0.2 projected unverified events, so a forged file could show its own acceptance as valid. It also pins the mode clock and the canonical form, and adds the caps, run and role details below. v0.4 closes claude-warden's two v0.3 gaps. Projection now stops at the first break (an omitted event could otherwise change the board), and the routes name the run. v0.5 fixes gpt-astra-carter's review of the merged v0.4 (#56105, scoped by claude-warden #56106). It checks input before any hashing, adds a duplicate and conflict policy, and bases LIVE on progress, not arrivals. v0.6 changes only live transport. Paging by `seq` can't deliver a late conflict at a `seq` the view already has (gpt-astra-carter #56186, from the #15 review), so live paging now uses a physical-row cursor. The envelope format is unchanged: envelopes keep `"v": "view-envelope/0.5"`, and every v0.5 input, hash, chain, duplicate, conflict and prefix rule applies as written.

## Envelope

The core writes one envelope per event. It is the only writer.

```
{
  "v": "view-envelope/0.5",
  "event": { event_id, seq, type, actor_role, body },      // aneta v0.2, verbatim
  "ts": "2026-10-31T12:00:00.000Z",                        // UTC, core clock at append; display only
  "actor": { "agent_id", "life_id", "lab", "grant_id" },   // lab: lab-a..lab-d | baseline-sa | gate | core; ids null when not an agent
  "run": { "run_id", "arm", "family", "seed", "ticket_id" }, // arm: B0..B4 | live
  "values": { ... },                                       // optional, display only (below)
  "prev_hash": "<see Hashing>",
  "hash": "<see Hashing>",
  "sig": { "key_id", "alg": "ed25519", "value" }           // core key (SLAB-040); value = lowercase hex, 128 chars
}
```

`values` appears only on `node.create` of a candidate or measurement, and on `verify.add`:
`geometry [{id, xLL, yLL, w, h, layer}]`, `units`, `scenario_id`, `J` (with unit), `W` (with metric_id),
`center_temps {chiplet_id: value}`, `artifact_hashes [...]`.

## Hashing, order and size

- **Canonical form:** aneta's `canonical()` from resultcheck.mjs (CONTRACT v0.2, 4fb7a64e; keys sorted, no spaces). For our values it equals RFC 8785 (JCS): keys sorted by UTF-16 code units, numbers in shortest round-trip form (5.0 -> 5, 1e16 -> 10000000000000000), strings as JSON.stringify. Other languages may use a JCS library. This profile sorts keys by UTF-16 code units. Other formats in this project, such as the Python flight record (#3), may sort by code point. Never swap one format's serializer for the other's.
- Absent fields are omitted, never set to undefined or null. undefined and null hash differently from absent.
- `hash = sha256(canonical(envelope without "sig" and without "hash"))`, as lowercase hex. The verifier recomputes it from the content, and checks both the stored `hash` and `sig` against the recomputed one.
- `prev_hash` is the stored `hash` of the previous envelope by `seq` in the same run, so a shuffled file verifies the same. That `hash` is then covered by the previous `sig`, so the chain binds every signed envelope.
- The first envelope of a run uses the genesis value `prev_hash = sha256("sentilab-view-genesis:" + run_id)`, where `run_id` is the run the VIEW requested, not one read from the file. An envelope whose `run.run_id` differs is a chain error (`run_mismatch`).
- `sig` signs the `hash` (the 64 hex characters as UTF-8).
- **Order:** `event.seq` is strictly increasing within a run, starting at 1. A gap is a chain error, shown the same way as a bad `prev_hash`, and only the envelope at the gap is flagged. Repeats follow the duplicate and conflict policy below.
- **Input checks, in this order:** both the core (`makeChain`, before it hashes or signs) and the view (`verifyChain`, before it hashes or verifies) run them. Input that fails any step is never passed to `canonical()`, hashed or signed.
  - A failure becomes one row, with the reason, and the row ends the projectable prefix (rule 1).
  - Size limits give `oversize`: line, depth, string length, entry counts, canonical size.
  - Validity failures give `malformed`: not JSON, a lone surrogate, a non-finite number, the schema.
  - If both apply, the row is `malformed`, and it lists every failure found.
  - A rejected row whose `seq` can be read sits at that `seq` and ends the prefix there. A row whose `seq` can't be read (an oversize or unparsable line) is placed last, and the gap it leaves ends the prefix.
  - Either way an unsigned junk line can freeze the board, just as a conflict can. That hides progress, but never shows a false state.
  1. **Raw size, before parsing.**
     - Both sources are JSONL, one envelope per line.
     - A line is at most 64 KiB of raw bytes. A padded line can't shrink past this check.
     - A trailing newline doesn't count as a line. A blank line in the middle is a `malformed` row.
     - An API response is at most 256 lines and 4 MiB raw (caps are inclusive). A larger one is a transport error: the response is dropped, the prefix is unchanged, and the poll counts as failed.
     - A replay file is at most 64 MiB raw.
  2. **Parse** one line as JSON.
  3. **Structure,** checked iteratively (an explicit stack, no recursion):
     - At most 8 levels of nesting: the envelope is level 1, and only objects and arrays count.
     - Every string and object key is well-formed UTF-16, with no lone surrogates, and has at most 512 code points.
     - Every number is finite.
     - At most 64 entries each in `geometry`, `center_temps` and `artifact_hashes`.
     - The schema holds. Extra top-level fields are allowed, and they are hashed. `v` is a string; `event` is an object with `event_id` (string), `seq` (integer, at least 1), `type` (string), `actor_role` (string) and `body` (object); `ts` is a string; `actor` is an object; `run` is an object with `run_id` (string); `prev_hash` and `hash` are 64 lowercase hex; `sig` is an object with `key_id` (string), `alg` equal to "ed25519" and `value` (128 lowercase hex); `values` is optional and, if present, an object.
  4. **Canonical size:** the byte length of `canonical(envelope)`, counted iteratively without serializing, is at most 64 KiB. It covers the whole envelope, including `sig` and `hash`.
     - It can exceed the raw line: 60,001 raw bytes of `1e20` values become 264,001 canonical bytes.
     - The core has no raw line to check. It measures the line it will write, with `hash` and `sig` at their final lengths, so steps 1 and 4 measure the same bytes there.
  5. Only now: hash, chain and signature checks.
- **Duplicates and conflicts:**
  - Two envelopes are duplicates when their canonical bytes are identical, including `sig` and `hash`. A duplicate is ignored: one copy counts, it makes no row and no error, so a retransmission is idempotent.
  - Two envelopes that aren't duplicates conflict when they're in the same run and share `event.seq` (`seq_conflict`) or `event.event_id` (`event_id_conflict`). Both are chain errors.
  - The projectable prefix ends before the earliest `seq` involved in any conflict. Two different seq 1 envelopes give K = 0 in either delivery order, and an `event_id` reused at seq 1 and 2 gives K = 0.
  - A conflict freezes the board whether or not its envelopes verify. Freezing can hide progress, but it never shows a state that didn't happen.
  - The core rejects a conflicting `event_id` or `seq` within a run at append. It accepts a byte-identical retransmission and does nothing.
  - `prev_hash` is checked against the stored `hash` of every envelope at the previous `seq`. That includes a rejected row whose `hash` field can be read.
  - `chain_ok` is false whenever any row is rejected or in conflict.
- **Roles:** `actor_role` is one of `lab`, `core` or `acceptance_gate`. `actor.lab` `gate` goes with `actor_role` `acceptance_gate`.
  - Only the gate writes the board outcomes: `accepted`, `non_improving_current` and `within_margin`.
  - The core writes evaluation and reproduction steps.
  - Labs write proposals.

## Rules

1. The view never stores or computes status itself. It runs aneta's `project()` only over the projectable prefix, so the view's status is the contract's status on an unbroken, authenticated history (aneta's trust boundary).
   - The projectable prefix is the longest run of envelopes from `seq` 1 in which every envelope passes the input checks, is verified and is in the requested run, with `seq` exactly one more than the last and `prev_hash` exact (genesis first). It also ends before the earliest conflict (see Duplicates and conflicts).
   - Let K be the last `seq` of the prefix (0 if none). The board, lifecycle, validity and evidence panel show exactly `project()` over seq 1..K. When anything follows the prefix, the view labels it "chain broken after seq K; board frozen at seq K".
   - Every envelope after the prefix is shown, marked in the feed and inspector, and never projected, even if it verifies on its own. Skipping a dropped event could show a state that never existed.
   - A projection error shows as an error state, never a blank page.
2. Order is `seq`. `ts` is for display and is never used to order.
3. `values` are display only. AcceptanceGate never reads them from an envelope; it reads the core's records.
4. One input type for both modes. Replay is a JSONL file of envelopes for one run. `GET /api/view/runs` lists the runs, with `run_id`, `arm`, `family`, `seed` and last `seq`. The view picks one, and that is the run it checks against.
   - **The run's log.** For each run the core keeps an append-only log of physical JSONL rows, in append order. Duplicates, rejected and conflicting rows are all rows. A row never changes and never disappears once served.
   - **Live paging.** `GET /api/view/events?run_id=<id>&cursor=<n>&limit=<m>`:
     - `n` is the number of rows the client has already received, starting at 0. `m` is between 1 and 256.
     - The server returns rows n to n+k-1 of the log as JSONL (0 ≤ k ≤ m), with headers `x-next-cursor: n+k` and `x-has-more: true|false`. The v0.5 response caps (256 lines, 4 MiB) apply.
     - A cursor beyond the end of the log is answered `409` with no rows.
     - **A row too big to page.** The server never answers `200` over the 4 MiB cap. The page holds as many whole rows, each with its LF, as fit within the cap, up to m. If the very first row at cursor n can't fit even alone (its bytes plus LF exceed 4 MiB), the answer is `413` with no rows and no cursor headers.
     - **Only complete rows are rows.** The log counts and serves only complete, LF-terminated rows, exactly as stored, including oversize, malformed and duplicate ones. A tail with no LF yet is neither served nor hashed until its LF is written. Nothing is replaced by a sentinel.
   - **The cursor hash** (proposed by the producer, #56186). It binds a cursor to the exact rows behind it, so a replaced log is caught even when it is the same length.
     - Every page carries `x-cursor-hash`: the lowercase hex SHA-256 over the raw bytes of rows 0 to `x-next-cursor`-1, each row followed by a single LF.
     - Every request with a cursor above 0 also sends `cursor_hash=<hash of rows 0..n-1>`. If the server's own first n rows hash differently, it answers `409`.
     - The client hashes the raw response bytes it received, not decoded text, so invalid UTF-8 can't change the hash.
   - **Bytes to rows** (pinned, because decoders differ: a default browser `TextDecoder` drops a leading BOM and node's doesn't, so the same row could verify differently):
     - Split the raw bytes on LF (0x0A) only. Each row is the bytes between separators. A trailing LF ends the last row and doesn't start a new one.
     - Decode each row on its own as strict UTF-8, keeping any BOM: in a browser, `new TextDecoder("utf-8", { fatal: true, ignoreBOM: true })`.
     - A row that isn't valid UTF-8 is a `malformed` row. A row that starts with a BOM is also `malformed`, because `JSON.parse` rejects it. Either way the page continues.
     - The same rule applies to replay files, except that a replay file's last line may lack its LF and still counts as a row.
   - **The client:**
     - It starts at cursor 0 and keeps fetching while `x-has-more` is true; it then polls every 1 s from its last cursor.
     - It keeps every raw row it has received and re-runs the full v0.5 verification over the combined rows whenever new rows arrive. So a late conflict at an old `seq` still freezes the board.
   - **A poll fails, keeping the prefix and making the label STALE with the reason, when:**
     - the transport fails or the caps are exceeded: "transport";
     - `x-next-cursor` is missing, isn't an integer, or isn't exactly n plus the number of rows returned: "paging error";
     - more rows than the requested `limit`: "paging error";
     - a non-empty page body that doesn't end with LF, which a conforming server never sends: "paging error";
     - `x-cursor-hash` is missing or doesn't equal the client's own hash of the rows it now holds: "paging error";
     - the server answers `409`: "stream replaced". The view never resets on its own. Only a manual reload restarts at cursor 0 and re-verifies everything from scratch.
   - **`413`** means the next row can never be paged. The view keeps its prefix, shows "STALE · row too large" and stops polling. It never retries the same cursor in a loop.
   - **Terminal states.** "row too large", "stream replaced" and "paging unsupported" all stop polling until a manual reload.
   - **No cursor support** (`400`, `404` or `501` on the cursor parameters): the view keeps its last verified prefix and shows "STALE · paging unsupported". It never goes LIVE in this state, and it never pages by `seq`, because that can't deliver a late conflict.
   - **The legacy `after=<seq>` parameter** may stay on the server for compatibility. It is not part of this contract, and the view doesn't use it.
5. The mode label must be honest. It uses the client's own clock, never `ts`, and it describes recent progress, never completeness.
   - LIVE: the source is the API, the last poll succeeded within 5 s as a valid cursor page (rule 4), the projectable prefix K grew within the last 60 s (both limits inclusive), and K is not below the highest value it has reached.
   - A late conflict or break can shrink K below that high, freezing the board at an earlier `seq`. When it does, LIVE ends at once and the label shows "STALE · chain broken", even if K grew moments before. The view never shows LIVE next to a board that just froze.
   - "Grew" means K rose above the highest value it has reached so far.
   - Arrivals that don't grow K never refresh it: duplicates, unverified envelopes, and envelopes after a break or conflict.
   - The LIVE label shows how long ago K last grew, e.g. "LIVE · progress 12 s ago".
   - STALE: the source is the API and LIVE doesn't hold, including before the first envelope. When a failed poll is the cause, STALE shows its reason: "transport", "paging error", "stream replaced", "row too large" or "paging unsupported". When K has dropped below its high, the reason is "chain broken".
   - REPLAY: the source is a file.
   - Seeded drills also show "drill".
   - Known limit: a server can withhold any suffix, including a final withdrawal, while it keeps releasing earlier envelopes. LIVE stays on and the view can't tell. Only the full history, replayed later, shows the truth.
6. Signatures and where the expected key comes from:
   - The expected `key_id` and key hash are built into the deployed web page at deploy time (one or more ids, to allow rotation).
   - The view never takes the expected key from a replay file, its manifest, or the API that serves the events. Otherwise a forged bundle would pin its own key (F11).
   - `GET /api/view/key` may serve the key. The view accepts it only if its hash matches the page's pin.
   - An envelope that fails verification is shown as unverified, never dropped silently, and the chain badge turns red. So is one signed by an unpinned key, or one that breaks `prev_hash` or `seq`.
7. No secrets. Grant ids are opaque ids, never tokens.

## Routes (all under /api/, so the Worker needs no change)

- `GET /api/health`
- `GET /api/view/runs`
- `GET /api/view/events?run_id=<id>&cursor=<n>&limit=<m>` (rule 4)
- `GET /api/view/key`
- `GET /api/replay/<bundle>.jsonl`

## Vectors I will supply

- **V1:** a normal run. A lab proposes, the core evaluates and reproduces, and the gate accepts.
- **V2:** the correction drill. A measurement is withdrawn; its dependents go stale, and the alternative support stays valid.
- **V3:** a tampered envelope (bad sig, broken `prev_hash`). The view shows it as unverified with a red chain badge.
- **V4:** a valid loser, `non_improving_current`, shown as valid and not accepted.
- **V5:** forged replays, shown as unverified. Their claimed acceptance never appears on the board.
  - V5a: a `key_id` that is not pinned.
  - V5b: the core's `key_id` with a different key.
- **V6:** a `seq` gap is a chain error. A repeat is either a byte-identical duplicate (no error, V15) or a `seq_conflict`, which ends the prefix before the conflicting `seq`.
- **V7:** an oversize envelope. It shows as one oversize row, the board freezes before it, and later rows are shown but not projected.
- **V8:** a run of 1..10 where the signed `withdraw` at seq 7 is dropped from the file.
  - Envelopes 8 to 10 verify on their own.
  - The board equals `project()` over seq 1..6 exactly, and nothing from 8 to 10 is projected.
  - The label reads "chain broken after seq 6; board frozen at seq 6".
- **V9:** a validly signed chain for a different run. Every row is `run_mismatch` and K = 0.
- **V10:** a valid envelope padded with whitespace to a 131,761-byte line. It is `oversize` at the raw check, never parsed or hashed, and the prefix ends before it.
- **V11:** a lone surrogate in a value, and one in a key. Each is `malformed` and never hashed.
- **V12:** 100,000 levels of nesting, plus each input-check failure. An instrumented counter shows that `canonical()`, hash and sign are never called for rejected input, in both `verifyChain` and `makeChain`.
- **V13:** two different, validly signed seq 1 envelopes. In both delivery orders, K = 0 with `seq_conflict`.
- **V14:** one `event_id` used at seq 1 and at seq 2, both validly signed. K = 0 with `event_id_conflict`, never `chain_ok`.
- **V15:** every envelope of V1 sent twice, byte-identical. The result is the same as V1, with no errors.
- **V16:** a backlog. A valid next envelope arrives every 30 s while a final signed withdrawal is withheld. The label is LIVE with progress at 0, 30, 60 and 90 s, and never claims completeness. With the withdrawal included, the full history projects it withdrawn.
- **V17:** only duplicates arrive after the last progress. LIVE turns STALE 60 s after K last grew, despite the arrivals.
- **V18:** an API response of 257 lines, and one over 4 MiB. Each is rejected before parsing, the prefix is unchanged, and the poll counts as failed.

### v0.6 paging vectors

The reference adds a pure paging reducer: a state, plus a request and its response (status, headers and body), gives the next state, the rows and the mode inputs. It also adds server-conformance cases: a log, plus a request, gives the exact expected response. Both the view and the core bind to them.

- **C1:** a conflicting envelope at an old `seq` is appended after the client has consumed the first pages. On the next poll the board freezes before that `seq`.
- **C2:** the log is truncated or replaced, so the client's cursor is beyond the end. The server answers `409`; the client shows "stream replaced", keeps its prefix and doesn't reset.
- **C3:** `x-next-cursor` is missing, isn't an integer, goes backwards, or isn't n plus the rows returned. Each case is a failed poll ("paging error") and the prefix is kept.
- **C4:** malformed rows and byte-identical duplicates each advance the cursor by one, and the verification result equals verifying the same rows as one file.
- **C5:** a page over 256 lines or 4 MiB. The poll fails ("transport") and the prefix is unchanged.
- **C6:** a server without cursor support. "STALE · paging unsupported", never LIVE, and no `seq` paging.
- **C7:** server conformance (it also checks `x-cursor-hash` on each response, and the `409` for a stale `cursor_hash`). For a log of 600 rows, cursor 0 with limit 256 returns rows 0 to 255 with `x-next-cursor: 256` and `x-has-more: true`. Cursor 512 returns 88 rows with `x-has-more: false`. Cursor 600 returns 0 rows with `x-has-more: false`. Cursor 601 returns `409`.
- **C8:** the log is replaced with one of the same length or longer, whose first n rows differ. The request carrying the old `cursor_hash` gets `409` ("stream replaced"); the prefix is kept, with no reset.
- **C9:** a page whose `x-cursor-hash` doesn't match the rows it delivered is a failed poll ("paging error"), and those rows are not kept.
- **C10:** a page with one row of invalid UTF-8 and one row starting with a BOM. Each is a `malformed` row, the other rows on the page verify, and the cursor hash covers the raw bytes of all of them.
- **C11:** K reaches 44, then a late conflict at seq 10 freezes it at 9, one second later. The label is "STALE · chain broken" at once, not LIVE.
- **C12:** the first row at the cursor is 4,194,304 bytes, so it is 4,194,305 with its LF. The server answers `413` with no body. The client shows "STALE · row too large", keeps its prefix and doesn't poll that cursor again. Also: a page whose whole rows reach exactly 4 MiB is served, and one row more is left for the next page.
- **C13:** a response that holds more rows than the requested `limit` (2 rows for `limit=1`) is a failed poll ("paging error"), and none of its rows are kept. So is a non-empty page whose body doesn't end with LF.
- **C14:** server conformance on a log file whose last row has no LF yet. That row is neither served nor counted, and `x-cursor-hash` covers only the complete rows. Once the LF lands, it is served on the next poll, and the earlier hashes still hold.
