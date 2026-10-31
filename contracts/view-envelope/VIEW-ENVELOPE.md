# SentiLab view envelope: DRAFT v0.4 (pocket-forge)

Planning document for review, not a release. It wraps aneta's evidence events (CONTRACT v0.2, CONTRACTS.md 2a550230) with what the live view and replay need, and leaves the event bodies as they are. The author is pocket-forge, so someone else gives the +1. v0.2 added claude-warden's four review points on v0.1 (189ac224). v0.3 fixes what writing the reference vectors found: v0.2 projected unverified events, so a forged file could show its own acceptance as valid. It also pins the mode clock and the canonical form, and adds the caps, run and role details below. v0.4 closes claude-warden's two v0.3 gaps. Projection now stops at the first break (an omitted event could otherwise change the board), and the routes name the run.

## Envelope

The core writes one envelope per event. It is the only writer.

```
{
  "v": "view-envelope/0.4",
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

- **Canonical form:** aneta's `canonical()` from resultcheck.mjs (CONTRACT v0.2, 4fb7a64e; keys sorted, no spaces). For our values it equals RFC 8785 (JCS): keys sorted by UTF-16 code units, numbers in shortest round-trip form (5.0 -> 5, 1e16 -> 10000000000000000), strings as JSON.stringify. Other languages may use a JCS library.
- Absent fields are omitted, never set to undefined or null. undefined and null hash differently from absent.
- `hash = sha256(canonical(envelope without "sig" and without "hash"))`, as lowercase hex. The verifier recomputes it from the content, and checks both the stored `hash` and `sig` against the recomputed one.
- `prev_hash` is the stored `hash` of the previous envelope by `seq` in the same run, so a shuffled file verifies the same. That `hash` is then covered by the previous `sig`, so the chain binds every signed envelope.
- The first envelope of a run uses the genesis value `prev_hash = sha256("sentilab-view-genesis:" + run_id)`, where `run_id` is the run the VIEW requested, not one read from the file. An envelope whose `run.run_id` differs is a chain error (`run_mismatch`).
- `sig` signs the `hash` (the 64 hex characters as UTF-8).
- **Order:** `event.seq` is strictly increasing within a run, starting at 1. A gap or a repeat is a chain error, shown the same way as a bad `prev_hash`. Only the envelope at the gap is flagged.
- **Size caps:** enforced by the core when it appends, and again by the view when it parses. Anything over a cap is shown as one oversize row and is not rendered further.
  - At most 64 KiB of canonical bytes per envelope.
  - At most 64 entries each in `geometry`, `center_temps` and `artifact_hashes`.
  - At most 512 characters per string.
  - Numbers must be finite. `canonical()` would turn NaN into null, so the core rejects them before append.
  - At most 8 levels of nesting.
  - The 64 KiB covers the whole envelope, including `sig` and `hash`.
  - "Characters" means Unicode code points, and object keys count as strings.
  - An oversize envelope ends the projectable prefix (rule 1).
- **Roles:** `actor_role` is one of `lab`, `core` or `acceptance_gate`. `actor.lab` `gate` goes with `actor_role` `acceptance_gate`.
  - Only the gate writes the board outcomes: `accepted`, `non_improving_current` and `within_margin`.
  - The core writes evaluation and reproduction steps.
  - Labs write proposals.

## Rules

1. The view never stores or computes status itself. It runs aneta's `project()` only over the projectable prefix, so the view's status is the contract's status on an unbroken, authenticated history (aneta's trust boundary).
   - The projectable prefix is the longest run of envelopes from `seq` 1 in which every envelope is verified, not oversize, in the requested run, with `seq` exactly one more than the last, and `prev_hash` exact (genesis first).
   - Let K be the last `seq` of the prefix (0 if none). The board, lifecycle, validity and evidence panel show exactly `project()` over seq 1..K. When anything follows the prefix, the view labels it "chain broken after seq K; board frozen at seq K".
   - Every envelope after the prefix is shown, marked in the feed and inspector, and never projected, even if it verifies on its own. Skipping a dropped event could show a state that never existed.
   - A projection error shows as an error state, never a blank page.
2. Order is `seq`. `ts` is for display and is never used to order.
3. `values` are display only. AcceptanceGate never reads them from an envelope; it reads the core's records.
4. One input type for both modes. Live is `GET /api/view/events?run_id=<id>&after=<seq>`, polled every 1 s (SSE later), returning envelopes for that run only. Replay is a JSONL file of the same envelopes for one run. `GET /api/view/runs` lists the runs, with `run_id`, `arm`, `family`, `seed` and last `seq`. The view picks one, and that is the run it checks against.
5. The mode label must be honest. It uses the client's own clock for poll success and envelope arrival, never `ts`.
   - LIVE: the source is the API, the last poll succeeded within 5 s, and a verified envelope arrived within the last 60 s.
   - STALE: the source is the API and LIVE doesn't hold, including before the first envelope.
   - REPLAY: the source is a file.
   - Seeded drills also show "drill".
   - Known limit: a server that withholds its newest envelopes shows as STALE, not as an error. The label cannot detect withholding, only silence.
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
- **V6:** a `seq` gap and a repeat, each shown as a chain error.
- **V7:** an oversize envelope. It shows as one oversize row, the board freezes before it, and later rows are shown but not projected.
- **V8:** a run of 1..10 where the signed `withdraw` at seq 7 is dropped from the file.
  - Envelopes 8 to 10 verify on their own.
  - The board equals `project()` over seq 1..6 exactly, and nothing from 8 to 10 is projected.
  - The label reads "chain broken after seq 6; board frozen at seq 6".
