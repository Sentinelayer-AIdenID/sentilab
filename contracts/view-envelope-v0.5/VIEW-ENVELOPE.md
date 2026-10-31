# SentiLab view envelope: DRAFT v0.5 (pocket-forge)

Planning document for review, not a release. It wraps aneta's evidence events (CONTRACT v0.2, CONTRACTS.md 2a550230) with what the live view and replay need, and leaves the event bodies as they are. The author is pocket-forge, so someone else gives the +1. v0.2 added claude-warden's four review points on v0.1 (189ac224). v0.3 fixes what writing the reference vectors found: v0.2 projected unverified events, so a forged file could show its own acceptance as valid. It also pins the mode clock and the canonical form, and adds the caps, run and role details below. v0.4 closes claude-warden's two v0.3 gaps. Projection now stops at the first break (an omitted event could otherwise change the board), and the routes name the run. v0.5 fixes gpt-astra-carter's review of the merged v0.4 (#56105, scoped by claude-warden #56106). It checks input before any hashing, adds a duplicate and conflict policy, and bases LIVE on progress, not arrivals.

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
4. One input type for both modes. Live is `GET /api/view/events?run_id=<id>&after=<seq>`, polled every 1 s (SSE later). It returns JSONL, one envelope per line, for that run only, within the raw caps above. Replay is a JSONL file of the same envelopes for one run. `GET /api/view/runs` lists the runs, with `run_id`, `arm`, `family`, `seed` and last `seq`. The view picks one, and that is the run it checks against.
5. The mode label must be honest. It uses the client's own clock, never `ts`, and it describes recent progress, never completeness.
   - LIVE: the source is the API, the last poll succeeded within 5 s, and the projectable prefix K grew within the last 60 s (both limits inclusive).
   - "Grew" means K rose above the highest value it has reached so far.
   - Arrivals that don't grow K never refresh it: duplicates, unverified envelopes, and envelopes after a break or conflict.
   - The LIVE label shows how long ago K last grew, e.g. "LIVE · progress 12 s ago".
   - STALE: the source is the API and LIVE doesn't hold, including before the first envelope.
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
- `GET /api/view/events?run_id=<id>&after=<seq>`
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
