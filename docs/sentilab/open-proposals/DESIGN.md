# Open proposals: design

Ticket `e76b348f`. Agents and people from other teams propose 2.5D chiplet layouts. SentiLab scores each one with the
same admitted engine, reference, metric and labels as its own entries, and shows it next to the SentiLab entry and the
human reference so the judges can assess it.

**Status: DRAFT for review.** This is a design only: no code, no deploys, no solves and no room posts. Every number
marked *proposed* is pending root review and is not frozen.

| Role | Owns |
|---|---|
| forge | The submission contract across CLI, MCP and REST; the free check; the skill; the judge pages; the challenge brief |
| warden | Capacity, per-participant budgets, admission, abuse operations and the load test |
| astra (root) | The claim rules (the math in section 4), evidence review and the readiness result |

**Pins.** Every `path:line` citation is at one of the commits below. Untagged paths are `[main]`.

| Tag | Source |
|---|---|
| `[main]` | sentilab `origin/main` `315bbff` |
| `[#57]` | sentilab PR #57 head `063f659` (SLAB-048: references, rotation, `TapGeometry`, router) |
| `[#56]` | sentilab PR #56 head `6413a3c` (SLAB-049: HotSpot 6.0 evaluator, gate zero) |
| `[cli]` | sentinelayer-cli 0.46.5; paths are relative to the npm package |
| `[api]` | sentinelayer-api `origin/main` `6f8058f5`. `R` = `src/services/session_relay_service.py`, `S` = `src/routes/sessions.py` |

Room messages are cited by number, such as room #56873; room ids are never cited.

## 0. Decisions at a glance

| # | Question | Decision |
|---|---|---|
| 1 | Transport and identity | **(a), room-native.** A proposal is a threaded reply in the challenge thread. Senti stamps each reply with the author's immutable account id, and an outbound-only intake worker reads it back. Four client transports write the same row: `sl session reply`, the `sl` MCP tool `session_reply`, the hosted MCP tool `sessions_reply`, and REST `POST …/actions`. No new inbound endpoint is needed. |
| 2 | "Anyone from anywhere" | Any person or agent, from anywhere, using a **free authenticated SentinelLayer account**. Anonymous submission is not offered. The free check, status and results need no account. |
| 3 | The math | One versioned **challenge manifest** per problem is the only source of numbers. The brief, the skill and the pages render from it. Verdict thresholds are *proposed*, and are frozen and published before any entrant is judged. |
| 4 | Proposal | `sentilab-open-proposal/1`: manifest id, a declared wire track, die centres in integer micrometres, rotation 0 or 90, a geometry hash and an idempotency key. It has no free-text fields. |
| 5 | Free check | A stateless `GET /api/open/v1/check`. It returns legality, proxy wire and routed wire, with no thermal solve and no account. It is rate limited and cached, and the checker code is published so heavy users can run it locally. |
| 6 | States | rejected, queued (held, evaluating), evaluated or failed, verified, withdrawn. Cancelled and expired entries are never charged. Receipts are signed ledger rows. |
| 7 | Evaluation | Only an admitted manifest is evaluated: a gate-zero PASS evaluator through `make_oracle`, merged references, a warden grant and astra's rules. Every evaluation is reserved before launch and settled on every exit. |
| 8 | Judge view | `/sentilab/open/`. Per problem, the human reference, the SentiLab entry and outside entries side by side, with our labels. |
| 9 | Skill | `SKILL.md`, `tools.json` and JSON Schemas at stable, versioned URLs, rendered from the manifest. Any agent framework can use them to check, submit, poll status and read results. |
| 10 | Capacity | Warden's commitments plus the cost and queue model in section 11. At capacity, entries queue or are refused with a reason and the next availability. |
| 11 | Readiness | A real outside account connects, checks, submits, polls status and reads its own result under the same identity. This runs after gate zero, the reference, source and grant checks, and warden's 50-agent load test. No invitation goes out before then. |

## 1. Scope

**In scope:**
- The two published TAP-2.5D problems on the 45 mm fixtures:
  - Ascend 910: `ascend910-45mm`, MATCH reference `ascend910-tap25d-fig6a`;
  - CPU-DRAM: `micro150-45mm`, BEAT reference `micro150-tap25d-fig5a`.

  Sources: [#57] `docs/sentilab/references/README.md:16-22`; [#57] `sundai_hotspot/tap_oracle.py:25-32`.
- Submission from the clients participants already have, plus plain HTTPS for any agent framework.
- Read-only public status, results and judge pages.

**Not in scope:**
- A new `sl` release (option (c) stays optional; section 3.3).
- Any model or LLM in intake, checking or scoring.
- Any change to the five-arm study, its held-out corpus, the live loop's board or training data (section 13).
- Prizes, dates or completed-model claims, and any judge claim before the readiness run (section 14).

## 2. What exists today

| Piece | Where | Used here for |
|---|---|---|
| **Fixture geometry and legality, no solver.** `TapGeometry`: catalogue and frame checks, every violation with a rule code (`margin`, `lattice`, `halo_overlap`, `min_spacing`), the rotation catalogue and per-die rotation | [#57] `sundai_hotspot/tap_oracle.py:111-135, 255-275, 278-312, 320-398` | The pre-evaluation validator and the free check, unchanged |
| **45 mm fixture rules.** 0.5 mm centre lattice, 0.1 mm minimum die gap, `rotation = per_die_90` | [#57] `sundai_tap/configs/sys_ascend910_45mm.cfg:30-38`, `sys_micro150_45mm.cfg:32-40` | Manifest legality |
| **The engine boundary.** Legality runs before any worker. The worker request, including the binary path and hashes, is built by the server. Results are bound to candidate, problem and binary. The worker re-hashes the binary and sources, gets a fixed environment, and caps a request at 64 KiB | `sundai_hotspot/tap_oracle.py:779-808, 840-848`; `sundai_hotspot/tap_oracle_worker.py:100-106, 218-240, 347-348` | Proposals contribute centres and rotations only |
| **Corrected-evaluator selection.** `make_oracle(evaluator, purpose)` refuses any binary without a gate-zero PASS. `HotSpot6Oracle` has its own identity. Direct `HotSpotOracle` construction is not rerouted | [#56] `sundai_hotspot/evaluators.py:3-14, 41-72, 90-104`; [#56] `sundai_hotspot/gate_zero.py:247-280` | The only open evaluation path |
| **References.** The raw reconstruction (off-lattice) and the legal snapped variant, with labels and claim label | [#57] `docs/sentilab/references/README.md:5-10, 86-99`; `ascend910-tap25d-fig6a.json:2, 246, 368, 516-518, 631` | Reference rows, labels, `W_ref` |
| **Router.** TAP-2.5D's MILP router on HiGHS: geometry only, proven optimum | [#57] `sundai_hotspot/tap_router.py:1-12, 74-143` | Routed wire `W` |
| **Budgets.** A durable reservation before compute, charged at its full ceiling, with a rolling hour, a settle step, and STOP on overrun | `sentilab_core/budget.py:18-40, 80-150`; `sentilab_core/conductor.py:300-343` | Reserve and settle; extended with per-participant windows |
| **Proposal harness (SLAB-052).** Host configuration is the authority, never lab input. Signed `proposal.reserved` before evaluation and `proposal.finished` in a `finally`. Idempotency conflicts are refused. Diagnostics never reach the proposer. Replayed receipts are byte-identical | `sentilab_core/proposals.py:1-5, 262-325, 268-271, 319-321, 404-405` | The receipt pattern |
| **Evaluate, reproduce, verify.** A binding tuple; a fresh-process reproduction checked by `AcceptanceGate`; `verify.add` tier `replayed`, labelled "same-solver reproduction" | `sentilab_core/conductor.py:368-370, 402-424`; `sentilab_core/gate.py:35-38, 63-75`; `sentilab_core/projection.py:13` | The `verified` state |
| **Signed ledger.** Append-only fsynced JSONL, RFC 8785 canonical bytes, Ed25519 service signer, idempotent event ids, no roles from transports. Lab-role rows hardcode actor `baseline-sa` | `sentilab_core/ledger.py:330-411`, `401-402`; `sentilab_core/envelope.py:65-95, 233-268` | Receipts; needs an actor-label change |
| **Capability registry (SLAB-043).** CLI command, MCP tool, schemas, errors and scope per capability, with drift and real-process parity tests | `sentilab_core/capabilities.py:12-27, 282-296`; `sentilab_core/test_conformance.py:246, 304, 380, 466, 542, 552, 584, 595, 715` | Our operator read capabilities and the contract tests |
| **Read-only public edge.** The Worker refuses every non-GET under `/api/*`, only the Worker holds the origin token, and the view routes page by cursor | `web/src/worker.js:28-30, 51-56`; `app/main.py:20-25`; `sentilab_core/README.md:112-135` | No write route is added |
| **Separation rules.** Separate study tracks, separate manifests, quarantined outside text, rights blocked by default | `docs/sentilab/draft-0.5/CANONICAL-SOURCE.md:65`; `docs/sentilab/draft-0.5/PLAN.md:260, 306`; `docs/sentilab/draft-0.5/ANETA-REVIEW-RESPONSE.md:26`; `sentilab_core/dataset.py:71-76, 183` | Section 13 |

## 3. Transport and identity

### 3.1 What Senti and `sl` give us

**Identity.**
- **Ordinary messages expose no account id to readers.** The event row carries labels, payload, sequence and source, but no author id ([api] `R:5635-5649`).
- **Labels are not identities.**
  - Human labels are `human-<github login or account id>` ([api] `R:1778-1783`).
  - Agent names are unique only per account ([api] `alembic/versions/050_user_agent_grants.py:72-76`).
- **Threaded replies carry `actorUserId`.** They are rows in the message-actions channel, and each carries `actorUserId` ([api] `R:10776`).
  - The server sets it from the authenticated caller, never from the body ([api] `R:12574`, `R:12650-12654`). For an agent, it is the delegating person's account.
  - It is removed only for public, non-member readers ([api] `R:10283-10285`, `R:3185`).
- **Replies can be edited** ([api] `S:6082`). Every row reports `messageRevision` and `editedAt` ([api] `src/services/session_message_service.py:59-72`).

**Membership.**
- **Writing requires membership.** Removal deletes the membership row and emits no event ([api] `S:5704`, `R:5310-5316`; access check `R:3157-3181`).
- **Admitted agents lose authority** when their person is no longer a member ([api] `src/services/session_admission_service.py:4159-4171`).

**Reading and limits.**
- **Machine clients poll.** They read `GET …/events` ([api] `S:6396`) and `GET …/actions` ([api] `S:6569`), and machine credentials get no event stream ([api] `S:6164-6181`).
- **Rate limits.** Action reads are 120 per minute and action writes 120 per minute ([api] `S:231-232`, keyed per user and room at `S:7377-7384`). A reply note may be up to 64,000 characters ([api] `S:2828`; `src/services/message_limits.py:1`).

**Rejected room carriers.**
- **Tickets are not byte-exact.** Title and body are rewritten on read ([api] `R:11806-11807`) and normalised at create ([api] `R:12048-12049`).
- **Attachments return only the uploader's label** ([api] `R:14103`).

**Credentials.**
- **Accepted on `POST …/actions`:**
  - MCP tokens with `sessions:write`;
  - scoped agent tokens;
  - user JWTs and API tokens ([api] `S:595-628`, route at `S:7367-7376`).
- **No third-party audience.** No token can be minted for another service. MCP tokens always name the MCP resource ([api] `src/auth/mcp_tokens.py:137-151`). User JWTs are 7-day bearers whose `sub` is the account id ([api] `src/routes/auth.py:649-673`).
- **Agent passports** prove identity, not authorization ([api] `src/services/agent_passport.py:8-14`). They are issued when an agent claims an admission ([api] `src/services/session_admission_service.py:2691`).
- **No billing for replies.** Posting a reply is not a metered action ([api] `src/services/session_usage_quota_service.py:51-92, 186-188`).

**The `sl` CLI and its MCP server.**
- **Both submit through the same channel.**
  - CLI: `sl session reply <sessionId> <targetSequenceId> <message...>` ([cli] `src/commands/session.js:4614`).
  - MCP: `session_reply {sessionId, agentId, targetSequenceId, message, idempotencyKey}` ([cli] `src/mcp/session-stdio-server.js:1565-1585`).
  - Both `POST …/actions` ([cli] `src/session/sync.js:2994-3002`; `src/mcp/session-stdio-server.js:765-773`).
- **The 13 native MCP tools** are listed at [cli] `src/session/route-classes.js:25-37`.
- **No structured input.**
  - No command or tool accepts structured JSON, so the proposal travels as text.
  - MCP `send_message` allows no extra fields ([cli] `src/mcp/session-stdio-server.js:1493-1515`).
  - MCP text is capped at 16,000 characters ([cli] `src/mcp/session-stdio-server.js:42`).
- **No new commands without a release.**
  - The command set is fixed at build ([cli] `src/cli.js:7-138`).
  - Generated `sl.*` bridge tools are refused at runtime ([cli] `src/mcp/cli-command-tools.js:389, 623`; `src/mcp/session-stdio-server.js:1755-1759`).
- **The only mintable token** is a short-lived bearer for the hosted MCP resource ([cli] `src/commands/mcp.js:175-182`).
- **The hosted MCP** exposes `sessions_reply`, which requires an idempotency key and `sessions:write` ([api] `src/routes/mcp.py:2221-2242`), and `whoami` ([api] `src/routes/mcp.py:1890-1905`).

### 3.2 Recommendation: (a), threaded replies read by an outbound-only intake

**How submission works.**
- A participant replies, under the challenge thread's root message, with one JSON proposal.
- Whichever client they use, Senti writes one message-action row and stamps it with the author's account id from the authenticated caller.
- Our intake polls the thread. It binds each proposal to that account id, validates it, and records a signed receipt. It points to the receipt in the thread and on the read-only pages.

**Why (a):**
1. **Server-authenticated, immutable identity.** `actorUserId` is set by Senti from the caller. It is not a label and not a body field.
2. **Least new trust surface.**
   - No inbound write endpoint is added, and the public edge stays write-free (`web/src/worker.js:51-56`).
   - We never handle a participant's credential.
   - The only new secret is our intake's own room credential.
3. **One row for every client.** All four transports create the same action row, so the contract is the row (section 3.5).
4. **Moderation reuses membership.** A removed member cannot write.
5. **Two independent records.** Senti's transcript and our signed ledger can be cross-checked by an auditor.

**Costs and how they are handled:**
- **Polling latency:** the target is under 30 s at p95.
- **Senti outages:** intake pauses and resumes from the last server sequence.
- **Chat noise:** only replies to a challenge root count.
- **Edits:** handled by binding revision 1 (section 3.6).
- **Receipt posting is rate limited:** room pointers are best effort; the public status route is authoritative.

### 3.3 Alternatives

**(b) A thermal-api endpoint that verifies Senti credentials.**
- **What it gives:** synchronous receipts.
- **Why not:**
  - Senti cannot mint a token for our audience. We would have to accept either a participant's replayable 7-day account JWT, or an MCP-audience token never meant for us ([api] `src/auth/mcp_tokens.py:137-151`).
  - There is no introspection endpoint. Passports prove identity, not authorization, and we found no check that makes a presenter prove it holds the passport key.
  - We would still need our own Senti credential to check room membership.
  - It opens a write route at the edge, reversing `web/src/worker.js:51-56`, and creates a new public abuse surface keyed on IP.

  Rejected.

**(c) A new `sl` command and native MCP tool** (e.g. `sl lab submit/status`).
- **What it gives:** local validation, hashing and nicer output.
- **Why not now:**
  - It needs a sentinelayer-cli release, because commands are fixed at build and bridge tools are refused (section 3.1). Every team would have to upgrade mid-event.
  - It still needs (a) or (b) underneath.

  Deferred as optional ticket OP-F8. It must emit byte-identical replies and pass the same vectors, and it is not needed for readiness.

**Other room carriers.**
- Top-level messages: rejected, because readers get no account id ([api] `R:5635-5649`).
- Tickets: rejected, because they are not byte-exact and any contributor may edit an unleased ticket ([api] `R:12203-12205`).
- Attachments: rejected, because they return the uploader's label only and uploads need an owner or contributor ([api] `R:14103`, `R:14180-14184`).

### 3.4 "Anyone from anywhere": free authenticated accounts

**Recommendation.** Anyone, or any agent, from anywhere can take part with a **free SentinelLayer account**, signed in with GitHub or Google.

**Joining.**
- An account joins the help room. When warden opens it (section 11.1), an overflow room takes the overflow.
- A person's agents post under that person's account and do not take a place.

**What needs no account.** The free check, status, results and the judge pages.

**Billing.** No participant is billed:
- replies are not metered ([api] `src/services/session_usage_quota_service.py:51-92`);
- evaluations run on SentiLab's compute;
- no evaluation is ever charged to another participant's credits.

| | Free authenticated accounts (recommended) | Anonymous |
|---|---|---|
| Identity | Immutable account id from Senti | None. An IP or a self-made key; a Sybil costs nothing |
| Attributable receipt | Yes | No |
| Per-participant budget | Per account, or per team where warden maps one | Per IP only, which is weak |
| Removal | Remove the member; the account stays the key | Not possible |
| New surface | None; Senti already does sign-in | A public write endpoint, captcha and IP limits |
| Friction | A one-time sign-up by a person; after that, agents run unattended | None |

**The abuse trade-off.** One person can open several accounts. Several mitigations bound this:
- each account needs a GitHub or Google sign-in;
- budgets are per account, with team mapping where warden sets it;
- a global cap;
- warden's suspension;
- room seats are capped.

That is far easier to bound than anonymous submission, which cannot meet the contract's attributable-receipt rule.

### 3.5 One contract for every client

The contract lives once in `contracts/open-proposal-v1/`, pinned in `contracts/HASHES.txt` like the existing contracts. It contains:
- the JSON Schemas for the manifest, proposal, check, receipt, status and results;
- `reason-codes.json`;
- the canonicalization rules;
- test vectors.

Consumers:
- the intake (Python);
- the free check;
- the judge pages (JS);
- the skill;
- our own sentilab CLI/MCP read capabilities;
- any later `sl` thin client.

All of them run the same vectors.

| Operation | `sl` CLI | `sl` MCP (stdio) | Hosted MCP | Any framework (REST) | Contract artifact |
|---|---|---|---|---|---|
| Manifest | `curl …/manifest/<problem>/current.json` | fetch | fetch | `GET` | `manifest.schema.json` |
| Check (free) | `curl …/api/open/v1/check?…` | fetch | fetch | `GET` | `check.schema.json` |
| Submit | `sl session reply <room> <root-seq> "<json>"` | `session_reply {targetSequenceId, message, idempotencyKey}` | `sessions_reply {…, idempotencyKey}` | `POST /api/v1/sessions/<room>/actions` `{"actionType":"reply", …}` | `proposal.schema.json` |
| Status | `curl …/api/open/v1/status?…`; also the receipt pointer via `sl session read` | fetch; or `read_history` | fetch; or `sessions_actions_list` | `GET` | `status.schema.json`, `reason-codes.json` |
| Results | `curl …/api/open/v1/results?…` | fetch | fetch | `GET` | `results.schema.json` |

**Transports.**
- **Submission** always becomes the same Senti action row. The only difference between clients is `metadata.source` (`cli` or `mcp`, [cli] `src/mcp/session-stdio-server.js:770-773`), which the intake ignores.
- **Check, status and results** are the same public GETs for every client.
- **Room pointers** are a convenience. They are rate limited and never authoritative.
- **Errors.** The contract's codes are the reason codes in section 7.2. Senti's own transport errors (403, 413, 429) pass through unchanged.

### 3.6 Identity rules

1. **Principal.** The principal is the Senti account id from `actorUserId` on the reply row. Never a label, `agentId`, metadata or anything in the body.
2. **Recognised replies.** Only replies whose target is a challenge root posted by our intake count. Other replies are ignored, and so are our own rows.
3. **Missing id.** A reply without `actorUserId` is rejected with `unattributable`.
4. **Revision 1 only.** Intake accepts `messageRevision = 1` with `editedAt = null`. An edited reply is rejected with `edited_before_ingest`. Later edits never change what was ingested.
5. **Public form.** The public form of an account is
   `participant_ref = sha256("sentilab-open-participant/1:" + account_id)`.
   - Raw ids stay in the private intake journal.
   - A participant can recompute the ref from `whoami` ([api] `src/routes/mcp.py:1890-1905`), from `GET /auth/me` ([api] `src/routes/auth.py:3326`), or from the `actorUserId` on their own reply.
   - Team labels come from warden's registry, never from the room.
6. **Our own entries.** The SentiLab entry uses the reserved principal `sentilab`, which no account can produce.

### 3.7 Components and secrets

```
participant (person or agent)
  │ reply: sl CLI · sl MCP · hosted MCP · REST            ┌──── free check, status, results (GET, no account)
  ▼                                                       │
Senti help room / overflow room (action row, actorUserId) │
  │ GET …/actions, …/events (poll by server sequence)     │
  ▼                                                       │
intake (outbound only; room credential; no signer)        │
  │ exact bytes + Senti ids → private journal (hash-chained)
  ▼                                                       │
recorder + evaluator (thermal-api side; signer; make_oracle; budgets)
  │ signed rows → open ledger ──GET──► read-only Worker ──►┘ judge pages, skill, status
  ▼
intake reads receipts ──► one pointer reply in the thread
```

**Intake** (new):
- It holds only a Senti credential for a dedicated intake identity. That identity is a contributor in the challenge rooms only, with read and post scopes ([cli] `src/session/admission.js:46-52`).
- It is never the operator account our agents share.
- It writes the private journal and posts pointers. It has no signer and no solver.

**Recorder and evaluator** (the existing thermal-api side):
- It holds the existing service signer (`sentilab_core/README.md:77-91`).
- It re-parses and re-validates every journal row from the raw bytes, and never trusts the intake's verdict.
- It signs ledger rows and runs evaluations.
- It never talks to Senti and never sees a participant credential.

**Free check:**
- A stateless GET route.
- It uses the same validator and router code as the recorder, with its own CPU budget (section 6).

## 4. The challenge manifest and the math

Root's rule (room #56874): one versioned manifest per problem is the single source of the math. The brief, the skill and the
pages render from it and never restate numbers by hand. Constraints and acceptance thresholds are published **before**
any entrant is judged. This section defines every term. The draft brief (room #56873) proposed the verdicts. **Every
threshold here is proposed, pending root review.**

### 4.1 The manifest

**Identity and versioning.**
- **Schema:** `sentilab-open-manifest/1`.
- **Id:** `manifest_id = sha256(JCS(manifest))`, with JCS as in `sentilab_core/envelope.py:65-91`.
- **Published once, never edited.** A manifest is published at `/sentilab/open/manifest/<problem>/v<N>.json`, and a `current.json` pointer names the open version.

**What it binds:**
- the fixture: config bytes, frame, dies, powers, netlist and legality rules;
- the reference identity and the layout used for verdicts;
- the temperature statistic, evaluator identity and grid;
- the wire definitions (routed and proxy);
- the uncertainty recipe, the verdict thresholds and the discrimination control;
- the submission window, grant reference, claim-rules reference, submission threads, and the checker and router hashes.

**Freezing rules.**
- Any change makes a new version.
- An entry is judged only under the manifest it named.
- Thresholds never change after outcomes are known. Re-judging under a later version requires root approval and is labelled.

### 4.2 Problems and reference layouts

| | Ascend 910 (MATCH) | CPU-DRAM (BEAT) |
|---|---|---|
| Fixture | `ascend910-45mm`: 6 dies, 45 mm frame, links `nppl` ([#57] `sundai_tap/configs/sys_ascend910_45mm.cfg:11-28`) | `micro150-45mm`: 8 dies ([#57] `sys_micro150_45mm.cfg:11-30`) |
| Dies, powers, netlist | Config `[chiplets]` lines 17-28 | Config `[chiplets]` lines 17-30 |
| Ambient | 318.15 K, i.e. 45 °C (`sundai_tap/util/hotspot.config:78`) | Same |
| Raw reconstruction (approximate, from the published figure) | Decoded centres at 1e-4 mm. Off the 0.5 mm lattice, so not legal on the fixture ([#57] `ascend910-tap25d-fig6a.json:246`) | Same ([#57] `micro150-tap25d-fig5a.json`) |
| Engineering variant (adjusted, legal) | At PR #57's head: the 1 mm snapped variant, moving dies by up to 1.12 mm ([#57] `README.md:94-115`; `sundai_hotspot/tap_references.py:39`). A 0.5 mm plain rounding is also legal and stays within 0.20 mm ([#57] `README.md:174-177`) | 1 mm snap; the 0.5 mm rounding stays within 0.08 mm |
| Paper values (HotSpot 6.0, CPLEX) | 75.48 °C, 16,426 mm ([#57] `README.md:134-136`) | 115.94 °C, 67,686 mm |
| Our routed wire on the raw reconstruction | 16,417.5 mm, -0.05% ([#57] `README.md:57-60`) | 67,688.4 mm, +0.004% |

**Rules for using the references:**
- **Verdict reference.** `T_ref` and `W_ref` are **our** evaluator and **our** router on **one** reference layout identity in the same manifest. They are never the paper's numbers.
  - Our evaluator may differ from the paper by up to the gate-zero tolerance of 1.0 K ([#56] `sundai_hotspot/gate_zero.py:32-33`). That is larger than the proposed `D`.
- **Recommended identity: the raw reconstruction.** Its routed wire reproduces the paper's within 0.05%. The snapped variant's is +10.5% and -4.3% ([#57] `README.md:90-92`), which would make wire verdicts against it meaningless.
  - The raw reconstruction cannot be a candidate, because it is off-lattice. Its `T` therefore comes from the reference-validation path with frozen inputs, which PR #56 schedules as the next allocation ([#56] `gate_zero.py:41, 61-64`).
  - Until that run exists, no Match or Beat verdict is issued. The judge view shows "not yet evaluated in this manifest" (open question A4).
- **The engineering variant is shown separately**, labelled "legal snapped variant (adjusted), not the paper's layout" ([#57] `README.md:90`). Which variant the manifest names, 1 mm or 0.5 mm, is open question A5.

### 4.3 Legality

A layout gives each catalogue die `i` a centre `(x_i, y_i)` in integer micrometres, with the origin at the lower-left of the
frame, and a rotation `rot_i` of 0 or 90 degrees about its centre. Rotation swaps the footprint ([#57]
`sundai_hotspot/tap_oracle.py:296-312`). A layout is legal when all of the following hold:

1. **Catalogue.** Exactly one entry per catalogue die, in die order, with the catalogue footprint or its rotated footprint. A square die has one orientation ([#57] `tap_oracle.py:272-274, 327-332`).
2. **Frame.** The frame is the fixture's size ([#57] `tap_oracle.py:333-335`).
3. **Lattice.** Every centre is a multiple of the lattice: 0.5 mm, checked exactly on integers ([#57] `tap_oracle.py:367-373`; config `[sentilab]`).
4. **Margin.** The body plus its microbump halo keeps 0.5 mm from every frame edge ([#57] `tap_oracle.py:33-34, 355-365`).
5. **Halo clearance.** No two halo rectangles overlap ([#57] `tap_oracle.py:375-382`).
6. **Minimum spacing.** Die bodies are at least 0.1 mm apart along some axis, as in TAP-2.5D Eqn. (10) ([#57] `tap_oracle.py:384-397`).

The halo per die is computed by TAP from the link type ([#57] `tap_oracle.py:210-211`, via `compute_ubump_overhead`). The
manifest publishes it per die so clients can check locally: Ascend 0.09 mm for die 0 and 0.045 mm for dies 1-5;
CPU-DRAM 0.18 mm for CPUs and 0.135 mm for DRAMs (the reference files' `dies[].halo_mm`). The server's `TapGeometry`
is authoritative.

### 4.4 Temperature `T`

- **Statistic.** `T` is TAP-2.5D's own selector: the maximum over the block temperatures in HotSpot's steady file, which are the chip-layer floorplan's units, with `-grid_map_mode center`, minus 273.15 ([#56] `sundai_hotspot/gate_zero.py:36-37, 174-177`; [#57] `ascend910-tap25d-fig6a.json:126`).
  - Which peak: the hottest unit's block temperature, centre-mapped. The record keeps the unit that holds it.
  - Which layer: the chip layer. The worker passes `sampleL4_ChipLayer.flp` to HotSpot as `-f` (`sundai_hotspot/tap_oracle_worker.py:318`).
  - Which grid: 64 x 64 ([#56] `gate_zero.py:34`; `sundai_tap/util/hotspot.config:112-123`).
- **Evaluator.** The HotSpot 6.0 evaluator (`a7a3286e`) with a gate-zero PASS for the exact binary on the evaluating host ([#56] `gate_zero.py:115-121, 247-280`). Binary hashes are host-specific, so each host pins its own ([#56] `docs/sentilab/diagnostics/SLAB-049/ANALYSIS.md:304-305`).
- **Not the objective.** The chip-layer grid peak with `-grid_map_mode max` (our earlier `J`, `sundai_hotspot/tap_oracle.py:682`) is reported only as a labelled diagnostic, because it is not the same statistic ([#57] `ascend910-tap25d-fig6a.json:126`).
- **Withdrawn values.** Any value from the withdrawn HotSpot 7 identity is excluded from all math (section 9.3).

### 4.5 Wire `W`: routed and proxy

**Routed wire, `W`.** This is the judged wire.
- It is the optimal value of TAP-2.5D's MILP router, as `routed_wirelength(…).total_mm`, in mm: every directed net's wires, routed between pin clumps under the hop limit for the fixture's link type ([#57] `sundai_hotspot/tap_router.py:7, 28-36, 74-143`).
- HiGHS with `mip_rel_gap = 0` must prove the optimum. If it cannot within the manifest's time limit, `W` is unavailable and no wire verdict is given ([#57] `tap_router.py:138-142`).
- The router reproduces all seven routed wirelengths the paper publishes within 0.2% ([#57] `tap_router.py:10-11`; `README.md:57-78`).

**Proxy wire, `W_proxy`.** This is a diagnostic only.
- It is the connectivity-weighted mean Manhattan centre distance, in mm ([#57] `tap_oracle.py:400-408`).
- It is about 19 mm against about 16,400 mm routed, so it is never compared with routed wire, never used for a verdict, and always labelled "proxy" ([#57] `README.md:82-84`).

### 4.6 Uncertainty `U` (proposed)

"More uncertainty makes every verdict harder to reach, never easier" (room #56873). `U` is an allowance assembled from
measured terms. **It is not an error bound** (root, room #56874).

| Term | Definition | Source |
|---|---|---|
| `u_rerun(L)` | The absolute difference between the evaluation and its fresh-process reproduction for layout `L` | `sentilab_core/gate.py:72-75` |
| `u_grid(L)` | The absolute difference between `T` at grid 64 and grid 32 for `L`, one extra grid-32 call | The SLAB-049 call list uses grids 32 and 64 ([#56] PR description) |
| `u_ref` | The largest absolute `T` change over the reference's sampled +/-0.5 mm probes. This is a **sampled sensitivity**, run once under warden's grant. The probes start from the snapped variant and do not reach every raw position | [#57] `docs/sentilab/references/ENVELOPE-PLAN.md:5, 9, 29` |

**How the terms combine:**
- **For one layout:** `U_cand = u_rerun(cand) + u_grid(cand)`.
- **For a comparison with the reference:** `U = U_cand + u_rerun(ref) + u_grid(ref) + u_ref`.

  This follows the frozen-plan form `J(ref) - J(cand) >= delta_min + u_num(ref) + u_num(cand)`, inclusive (`docs/sentilab/SLAB-041-ADMISSION-REVIEW-2026-10-31.md:17`).
- **Pages show each term separately**, never pooled.

### 4.7 Verdicts (proposed, pending root review)

**Proposed values** (room #56873):
- `D` = 0.5 K
- `r` = 5%
- `B` = 1 K
- `B_W` = 2% of `W_ref`
- feasibility flag at 85 °C
- relaxed wire budgets at +10, +25, +50 and +100%

**Prerequisites.** A verdict needs `T` from the admitted evaluator and routed `W` for the same geometry and the same
manifest. Verdicts never mix manifests or engines.

**Declared wire track (proposed).**
- Each proposal declares one wire track before it is scored. The choices are `strict`, `relaxed+10`, `relaxed+25`, `relaxed+50` and `relaxed+100`, from the manifest's admitted list.
- The track is judged only on routed wire. The proxy is never a track.
- An entry is judged only in the track it declared, so a track cannot be chosen after the result is known.

| Track | Verdict | Requirement | Label |
|---|---|---|---|
| any | **Below 85 °C** (flag; the draft brief's "Feasible") | `T + U_cand <= 85 °C` | "simulated T below 85 °C". A flag, not a safety or feasibility claim |
| `strict` | **Match** | `(T - T_ref) + U <= D` and `W <= W_ref (1 + r)` | "Match: within D of the reference temperature, at most +r routed wire". **Never "equal wire"** |
| `strict` | **Beat (temperature)** | `W <= W_ref` and `(T_ref - T) - U >= B` | "Beat at no more wire" |
| `strict` | **Beat (wire)** | `(W_ref - W) >= B_W` and `(T - T_ref) + U <= D` | "Beat on wire at matched temperature" |
| `relaxed+b` | **Trade-off** | `W <= W_ref (1 + b)`, reported with `(T_ref - T) - U` | "relaxed wire budget +b%: a trade-off, not a Beat" |
| `relaxed+b` | **Over budget** | `W > W_ref (1 + b)` | "over its declared wire budget: no verdict" |
| all | **Pareto view** | The `(T, W)` frontier over all evaluated entries, across tracks | "Pareto comparison, no verdict" |

**Comparisons, ties and limits.**
- **Tie-break.** Equal `T` breaks by geometry hash, for ordering only (`docs/sentilab/SLAB-041-ADMISSION-REVIEW-2026-10-31.md:11`).
- **Inside the uncertainty.** A difference inside `U` is shown as "within uncertainty" and is never ordered.
- **No silicon claims.** Nothing in this table is a claim about silicon.
- **Not in the repo yet.** The 85 °C flag is the draft brief's proposal. TAP's DTM threshold at `sundai_tap/util/hotspot.config:10-11` (354.95 K) is unrelated and must not be used.
- **The router's round-trip tolerance is also 2%** (`sundai_hotspot/tap_references.py:43`). That limit applies to comparisons with the paper's values. Candidates and the reference share one router.

### 4.8 Labels for wire tracks and comparisons (root, room #56874)

**Wire labels.**
- Strict wire (`W <= W_ref`), Match's "+r" allowance, each relaxed-wire budget and the Pareto view each carry their own label, as in the table above.
- 1.05x wire is never called equal wire.
- Routed and proxy wire sit in separate columns.

**Uncertainty and source labels.**
- The sampled +/-0.5 mm probes are labelled "sampled sensitivity, not an error bound" ([#57] `ENVELOPE-PLAN.md:5`).
- Every temperature is labelled "simulated" with its evaluator identity.
- The paper's values are labelled "paper (HotSpot 6.0, CPLEX), not our evaluation".

### 4.9 The discrimination control (proposed)

**Why.** A verdict rule must be able to fail. The reviews already require showing that a task "discriminates methods
above numerical noise" (`docs/sentilab/draft-0.5/ANETA-REVIEW-RESPONSE.md:17`). They also record the earlier Ascend
task's weak discriminative power (`docs/sentilab/draft-0.5/CANONICAL-ADDENDUM.md:62`).

**The control.** Before any Match or Beat verdict is published for a problem, the frozen rule is applied to published
layouts with known relations, using **our** measured `T` and routed `W`. Every expected class must come out.

| Control layout | Expected class | Why |
|---|---|---|
| The reference itself, re-evaluated | Match; not Beat | Identity |
| Ascend TAP-2.5D, Fig. 6(c) | Match; not Beat | Paper: 75.47 vs 75.48 °C. Our routed wire is 16,613.5 mm against the raw reference's 16,417.5 mm, +1.2% ([#56] `gate_zero.py:65-66`; [#57] `README.md:59, 75`) |
| Ascend Compact-2.5D, Fig. 6(b) | No Match (wire); trade-off at +50% | Routed +45% ([#57] `README.md:74`) |
| CPU-DRAM TAP-2.5D, Fig. 5(c)/(d) | No Beat; outside the +100% budget | Routed +219% and +105% ([#57] `README.md:77-78`) |

**What happens if the control fails.** Beat verdicts are suspended for that problem, and the page says so.

**Cost.** The control's solves are listed in warden's grant. Some of these layouts are still pending: one is waiting on
SLAB-048 ([#56] `gate_zero.py:67-68`).

### 4.10 Draft manifest v0 (Ascend 910): proposed, pending root review

Values cite the sources above. Fields shown as `<…>` are filled at publication from pinned bytes.

```json
{
  "schema": "sentilab-open-manifest/1", "version": 0, "status": "draft: proposed, pending root review",
  "problem": "ascend910",
  "fixture": {"id": "ascend910-45mm", "config": "sundai_tap/configs/sys_ascend910_45mm.cfg",
              "config_sha256": "4a922560510ba0ab66d04030f137f80262891e7ac7afac3025a57f539e885a8c",
              "frame_um": 45000, "ambient_c": 45, "link_type": "nppl"},
  "dies": [
    {"die": 0, "name": "compute", "w_um": 14500, "h_um": 31400, "power_w": 256, "halo_um": 90, "rot_deg": [0, 90]},
    {"die": 1, "name": "io",      "w_um": 10500, "h_um": 16000, "power_w": 14,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 2, "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 3, "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 4, "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 5, "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]}],
  "netlist": [[0,200,256,256,256,256],[200,0,0,0,0,0],[256,0,0,0,0,0],[256,0,0,0,0,0],[256,0,0,0,0,0],[256,0,0,0,0,0]],
  "legality": {"units": "um", "anchor": "die-centre", "origin": "frame lower-left", "lattice_um": 500,
               "margin_um": 500, "min_die_gap_um": 100, "rotation": "per_die_90"},
  "reference": {"id": "ascend910-tap25d-fig6a", "sha256": "<file bytes>", "track": "MATCH",
                "verdict_layout": "raw", "engineering_variant": "<snapped-1mm | rounded-0.5mm>",
                "t_ref": "<our evaluator, raw, from its validation receipt>", "w_ref_mm": 16417.5,
                "paper": {"t_c": 75.48, "w_mm": 16426}},
  "temperature": {"statistic": "tap-block-centre-max", "grid": 64, "grid_map_mode": "center",
                  "evaluator": {"kind": "hotspot6", "upstream": "a7a3286e368867c26381e0a23e36b3e273bdeda9",
                                "binary_sha256": "<host binary>", "gate_zero_record_sha256": "<record>"},
                  "diagnostic": "chip-layer grid peak, grid_map_mode max"},
  "wire": {"judged": "routed", "router_sha256": "<tap_router.py bytes>", "time_limit_s": "<warden>",
           "proxy": "connectivity-weighted mean Manhattan centre distance, diagnostic only"},
  "uncertainty": {"terms": ["u_rerun", "u_grid", "u_ref_sampled"], "u_ref": "<from the envelope grant>"},
  "verdicts": {"status": "proposed, pending root review", "D_k": 0.5, "r": 0.05, "B_k": 1.0, "B_W": 0.02,
               "flag_c": 85, "relaxed_wire_budgets": [0.10, 0.25, 0.50, 1.00]},
  "wire_tracks": ["strict", "relaxed+10", "relaxed+25", "relaxed+50", "relaxed+100"],
  "discrimination_control": ["reference", "fig6c", "fig6b"],
  "example": {"label": "invented numbers", "T_c": "<chosen at freeze>", "W_mm": "<…>", "U_k": "<…>"},
  "window": {"opens_at": null, "closes_at": null},
  "refs": {"grant": "<warden grant>", "claim_rules": "<astra record>", "checker_sha256": "<…>"},
  "submission": {"threads": "<room and root sequence per room, rendered at publication>"}
}
```

The CPU-DRAM manifest has the same shape. Its values come from `sys_micro150_45mm.cfg:11-40` and
`micro150-tap25d-fig5a.json` ([#57]). Its `w_ref_mm` is 67,688.4 and its paper values are 115.94 °C and 67,686 mm.

## 5. The proposal

### 5.1 Object

```json
{"schema": "sentilab-open-proposal/1",
 "manifest_id": "<64 hex>", "problem": "ascend910", "reference_id": "ascend910-tap25d-fig6a", "wire_track": "strict",
 "proposal_key": "team-a-07", "parent": null, "units": "um", "anchor": "die-centre",
 "dies": [{"die": 0, "x_um": 17000, "y_um": 23000, "rot_deg": 90}, …],
 "geometry_sha256": "<64 hex>",
 "client": {"name": "my-agent", "version": "1.2.0"}}
```

| Field | Rule |
|---|---|
| `manifest_id` | An open manifest. It must match the root the reply targets |
| `problem`, `reference_id` | Must equal the manifest's values. They are redundant on purpose, so receipts are self-describing |
| `wire_track` | The declared track: one of the manifest's `wire_tracks` (section 4.7). It is part of the proposal hash, so it cannot change after submission |
| `proposal_key` | `^[a-z0-9][a-z0-9_-]{0,63}$`, the same pattern as `sentilab_core/capabilities.py:160`. Scoped to the principal and manifest |
| `parent` | `null`, or the `geometry_sha256` of the principal's own earlier entry in this manifest |
| `units`, `anchor` | The constants `"um"` and `"die-centre"` |
| `dies` | One per catalogue die, `die` equal to its index. `x_um` and `y_um` are integers in `[0, frame_um]`. `rot_deg` must be in the die's allowed set |
| `geometry_sha256` | Must equal the server's recomputation (section 5.2) |
| `client` | Optional. `name` and `version` match `^[A-Za-z0-9._-]{1,32}$`. Kept privately and never rendered |

**What the schema forbids.**
- Every object has `additionalProperties: false`.
- There are no note, explanation or prompt fields.
- A proposal cannot name a binary, host, grid, timeout, metric, budget or grant (section 8.2).

### 5.2 Canonical form and hashes

- **Canonical JSON.** RFC 8785 JCS, as in `sentilab_core/envelope.py:65-91`.
  - Cross-language vectors already exist (`sentilab_core/conformance.py:19-37`), as does a browser copy (`web/public/sentilab/canonical.mjs:1-10`).
  - Geometry is integers only, so every client's JSON encoder agrees once keys are sorted.
- **`geometry_sha256`** is the physical-layout hash:

  `sha256(JCS({"schema":"sentilab-open-geometry/1","problem","fixture_config_sha256","units","anchor","dies":[{die,x_um,y_um,rot_deg}…]}))`

  It is geometry in its task context, without actor, time, key or client (`docs/sentilab/SLAB-041-ADMISSION-REVIEW-2026-10-31.md:29-31`).
- **`proposal_sha256`** is `sha256(JCS(the whole proposal))`: the candidate revision hash, with provenance kept. Clients can compute it, so it doubles as the status key.
- **`design_hash`** is computed by the server. It is the oracle's `Design.hash` of the materialised design ([#57] `sundai_controller/controller.py:151-164`), the `candidate_hash` the worker is bound to (`sundai_hotspot/tap_oracle.py:782, 843`).
- **`body_sha256`** is the SHA-256 of the exact UTF-8 note bytes returned by Senti.

### 5.3 Limits

- **Note.** At most 4,096 bytes of UTF-8, far below Senti's 64,000 and MCP's 16,000-character caps.
  - The trimmed note must be one JSON object, or one ```` ```json ```` fenced block holding one.
  - A reply that starts with neither `{` nor ```` ``` ```` is chat and is ignored.
- **JSON.**
  - Strict UTF-8 with no BOM.
  - No duplicate keys, no NaN and no infinities.
  - Nesting at most 4 deep, at most 32 dies.
  - Integer geometry only.
- **Per principal.** Submission rates and queue caps are warden's (section 11).

### 5.4 Legality before any evaluation

Checks run in order, all without a solver or a reservation. All violations are reported, not just the first:
1. transport checks (thread, revision, size);
2. JSON and schema;
3. manifest checks;
4. the geometry hash;
5. catalogue and rotation;
6. lattice, checked exactly on integers;
7. `TapGeometry.layout_violations`, after materialising with `design_from_centers` ([#57] `tap_oracle.py:296-312, 320-398`).

**What a rejection reports.** Each violation becomes a reason code with die indices and amounts, never submitted text
(`LayoutViolation`, [#57] `tap_oracle.py:127-134`).

**Who checks.** The recorder re-runs every check from the raw bytes. The oracle's own pre-worker check still applies
(`sundai_hotspot/tap_oracle.py:779-780`). The free check runs the same code (section 6).

### 5.5 Duplicates and equivalent layouts

**Same geometry, same manifest.** The layout is not evaluated again and nothing is charged. The receipt points to the
first complete evaluation, which is the one authoritative measurement per layout and context
(`docs/sentilab/SLAB-041-ADMISSION-REVIEW-2026-10-31.md:33`).

**Equivalent layouts.** These are equal after one of the square frame's eight symmetries, combined with a permutation of
interchangeable dies (same footprint, power and netlist role). They are evaluated normally and labelled "equivalent to
`<entry>`", never merged (`SLAB-041-ADMISSION-REVIEW-2026-10-31.md:29-31`).

**Copies.** Copies of the SentiLab entry or a reference layout are labelled the same way.

## 6. The free check (no thermal solve)

The draft brief's best idea (room #56873): bots iterate on geometry for free, and spend thermal budget only on serious
candidates.

**Request.**
- `GET /api/open/v1/check?m=<manifest_id>&p=<base64url(proposal JSON)>`.
- No account and no state. It goes through the read-only Worker, which keeps its GET-only rule (`web/src/worker.js:51-56`).

**Response** (`check.schema.json`):
- **Fields:** `geometry_sha256`, `proposal_sha256`, `legal`, `violations`, `wire.proxy_mm`, `wire.routed_mm`, `wire.routed_status` (`optimal`, `timeout` or `skipped_illegal`), `fits_tracks`, and the manifest id. `fits_tracks` lists the tracks whose wire limit the layout meets: `strict` when `W <= W_ref (1 + r)`, the Match allowance; `relaxed+b` when `W <= W_ref (1 + b)`.
- **Labels:** "geometry only, no thermal solve, not a score".

**Same code everywhere.** The check uses the same validator and router as the recorder. Contract vectors prove that the
check and the intake agree on every case.

**Cost** (old-engine host measurements; the router does not depend on the thermal engine):
- Legality and proxy wire take about a millisecond.
- A routed wire takes 0.2 to 1.5 s of CPU on the measured hosts ([#57] `README.md:84`).

**Limits** (the numbers are warden's):
1. **Cache.** Results are cached by `(manifest_id, geometry_sha256)`. A repeat costs nothing.
2. **Routing only for legal layouts.** Illegal layouts are never routed.
3. **Router time limit.** The manifest's limit is far below the router's 60 s default ([#57] `tap_router.py:74-75`). A timeout returns `routed_status: "timeout"` and no wire.
4. **Per-IP rate limit at the edge.** This uses the same mechanism as the Worker's existing limiter binding (`web/src/worker.js:39-46`).
5. **Global router concurrency cap at the API.** Over the cap, the response is 429 with `Retry-After`.
6. **The checker is published** (validator and router, pinned by `checker_sha256` in the manifest), so heavy users can run it locally at no cost to anyone. The router is TAP-2.5D's Apache-2.0 code, with its change notice ([#57] `tap_router.py:3-8`). Publishing it is open question A9.

## 7. States, idempotency and receipts

### 7.1 States

```
reply ─► rejected                                   (terminal; reason codes; nothing charged)
      └► queued ─► evaluating ─► evaluated ─► verifying ─► verified
           │ ▲          │            │             └──────► not_reproduced
           ▼ │          ▼            ▼
          held        failed       failed           (charged; no automatic retry)
           │
           └► cancelled · expired                    (before any reservation; never charged)
withdrawn: from any state, by moderation (signed; restorable)
```

| State | Meaning | Charged | Ledger lifecycle |
|---|---|---|---|
| rejected | Failed the transport, schema, manifest, hash or legality checks, or a policy check | No CPU (counts toward the submission rate) | `rejected_schema` or `rejected_constraints` (existing: `web/public/sentilab/lab-model.mjs:218-225`; `sentilab_core/dataset.py:22`) |
| queued | Valid, recorded, waiting for budget or its turn | No | New: `queued` |
| held | Moderation hold | No | New: `held` |
| evaluating | Reservation recorded; worker running | Yes | `simulation_pending` (existing) |
| evaluated | One admitted evaluation completed and settled | Yes | `evaluated` (existing) |
| failed | The attempt ended without a result: `timeout`, `oracle_error`, `stopped`, `grant_expired` or `interrupted` | Yes | `failed_run` (existing) |
| verifying | Reproduction reserved or running | Yes | `reproduction_pending` (existing) |
| verified | The fresh-process reproduction agreed (section 8.5) | Yes | `reproduced` plus `verify.add` (existing) |
| not_reproduced | The reproduction disagreed or failed. The evaluated result stays visible and flagged | Yes | `reproduction_failed` (existing) |
| cancelled / expired | Removed before any reservation (participant removed, STOP, operator), or the window closed before start | No | `cancelled` (existing); new: `expired` |
| withdrawn | Moderation | — | `withdraw` and `withdraw.retract` (existing: `web/public/sentilab/evidence-projection.mjs:134-140`) |

**Mapping to the contract's four states.**

| Contract state | States here |
|---|---|
| rejected | rejected |
| queued | queued, held, evaluating |
| evaluated | evaluated or failed |
| independently verified | verified |

**No board.** The open ledger never writes a board outcome, and the ledger already refuses one outside the gate
(`sentilab_core/ledger.py:340-342`).

### 7.2 Reason codes

A fixed vocabulary. Receipts carry codes, die indices and amounts only, never submitted text. This follows
`sentilab_core/transport.py:8-11` and `sentilab_core/research.py:26-27`.

| Group | Codes |
|---|---|
| Transport | `oversize`, `not_utf8`, `edited_before_ingest`, `unattributable` |
| Envelope | `malformed_json`, `duplicate_key`, `nonfinite_number`, `too_deep`, `unknown_field`, `schema_invalid` (with the failing schema path, never the value) |
| Manifest | `unknown_manifest`, `manifest_mismatch`, `manifest_closed`, `not_open_yet`, `wire_track_not_admitted` |
| Geometry | `die_count`, `die_order`, `out_of_frame`, `rotation_not_allowed`, `lattice`, `margin`, `halo_overlap`, `min_spacing`, `geometry_hash_mismatch` |
| Revision | `idempotency_conflict`, `unknown_parent` |
| Policy | `participant_suspended`, `participant_removed`, `rate_limited`, `queue_full`, `capacity_full`, `budget_exhausted` |
| Evaluation | `timeout`, `stopped`, `oracle_error`, `grant_expired`, `interrupted`, `binding_mismatch`, `router_timeout` |
| Verification | `reproduction_mismatch`, `fresh_process_required`, `reproduction_failed` |

### 7.3 Idempotency and immutable revisions

**What counts as a submission.**
- One Senti reply row at revision 1 is one submission.
- The key is `(principal, manifest_id, proposal_key)`, and the lowest server sequence wins.

**Duplicates and conflicts.**
- **Same key, same `proposal_sha256`:** no new record. The same receipt is returned, and the pointer is re-posted at most once.
- **Same key, different content:** rejected with `idempotency_conflict`, the pattern of `sentilab_core/proposals.py:268-271`.

**Immutability.**
- A revision never changes. Later edits of the reply ([api] `S:6082`) are ignored, and pages show the ingested bytes.
- History is the principal's revisions in server-sequence order. `parent` adds an explicit lineage edge.

**Retries.**
- Clients should send `idempotencyKey = proposal_key`, so Senti also dedupes transport retries ([api] `S:2830`). `sl` already requires a key on every mutation ([cli] `src/auth/http.js:470-474`).
- Ledger event ids derive from `(manifest, principal, proposal_key, phase)`, so a restart cannot append twice (`sentilab_core/ledger.py:387-398`).

### 7.4 What is hashed and signed, and by whom

**Senti.** Senti signs nothing for us. Its guarantee is the authenticated `actorUserId` on its own row.

**Intake journal** (private, hash-chained, unsigned). One line per ingested reply:
- journal sequence, previous hash and read time;
- Senti action id, server sequence and target sequence;
- `actorUserId`, the label (private) and `messageRevision`;
- the note bytes and `body_sha256`.

**Recorder** (holds the service signer). It appends Ed25519-signed envelopes to the open ledger (`sentilab_core/envelope.py:233-247`), verifiable against the existing pins (`web/public/trust-pins.json`; `sentilab_core/README.md:86-91`).

**Ledger partitions.** One run per `(manifest, principal)`, so each run stays small. Run id: `open-<manifest 8 hex>-<participant_ref 16 hex>`, which matches `sentilab_core/envelope.py:26`.

**The receipt** is the signed candidate row and its transitions. Its record holds:
- `participant_ref`, and `source_ref = sha256("sentilab-open-source/1:" + action_id)`;
- `body_sha256`, `proposal_sha256`, `geometry_sha256` and `design_hash`;
- `manifest_id`, `problem`, `reference_id` and `wire_track`;
- `proposal_key`, `revision_index` and `parent`;
- the state and reason codes;
- `values.geometry`, as the conductor writes it (`sentilab_core/conductor.py:383-386`).

**Measurement rows** carry:
- the binding, `T`, `W`, process id, CPU charged and measured, and input hashes (`sentilab_core/conductor.py:331-342`);
- SLAB-049's per-solve fields ([#56] PR description).

**The receipt hash** is the envelope hash (`sentilab_core/envelope.py:244`).

**Who can verify what:**
- **Anyone** can verify signatures and the chain against the pins.
- **A participant** can recompute `participant_ref` and `source_ref` from their own account id and action id.
- **Astra and warden** can open the commitments from the journal and re-read the Senti row to confirm author and bytes.
- **No public row** carries an account id, label, message id or room id.

### 7.5 What the intake posts in the room

**Roots.** One root per open manifest, per room:
- fixed text, the manifest id and links;
- posted only after readiness, apart from the readiness root (section 14).

**Pointers.** At most two per submission: one at intake (queued or rejected) and one at the end (verified,
not_reproduced, failed, cancelled or expired).
- Each is built only from signed fields: `state=<…> codes=<…> receipt=<hash> status=<url>`.
- A pointer is a reply to the submission. Replies can target replies ([api] `alembic/versions/057_session_message_action_targets.py:1-8`).
- Under load, pointers degrade in this order:
  1. queued pointers are dropped;
  2. terminal pointers are batched per root.

  This keeps us under the per-room action write limit ([api] `S:232`). Status stays available at the public route.

## 8. The evaluation boundary

### 8.1 Admitted manifests only

A manifest is admitted, in a host-side registry (host configuration is the authority: `sentilab_core/proposals.py:1-5`),
only when all five of these hold:
1. **Gate zero.** `require_gate_zero` passes for the exact binary on the evaluating host. `make_oracle(evaluator, "open")` then returns ([#56] `evaluators.py:90-104`; add `"open"` to `PURPOSES` at line 28).
2. **References.** PR #57 is merged, and the reference bytes are pinned in the manifest.
3. **Source.** The deployed build and binary hashes equal the reviewed ones. The problem hash binds the generator and binary hashes (`sundai_hotspot/tap_oracle.py:663-684`), and the worker re-hashes them (`sundai_hotspot/tap_oracle_worker.py:218-240`).
4. **Grant.** Warden's grant is recorded: budgets, window, hosts and STOP.
5. **Claim rules.** Astra's rules for the manifest are recorded.

Otherwise intake answers `manifest_closed` or `not_open_yet`. This matches root's direction that the HotSpot 6.0 loop
runs behind its own exact job admission after gate zero (room #56874).

### 8.2 What a submission can and cannot influence

**Can influence:**
- which open manifest, by id only;
- die centres and rotations, after legality;
- its own key and parent.

**Cannot influence:**
- the shell, argv, binary path, host, grid, timeout, solver flags, environment or retained-output path;
- the budget, grant, signer, metric, wire definition, scenario, comparator, reference geometry or verification.

**Why.** All of these come from the manifest registry and the oracle:
- the worker request is built server-side (`sundai_hotspot/tap_oracle.py:781-808`);
- the native solver runs a fixed argv with a fixed environment (`sundai_hotspot/tap_oracle_worker.py:347-348`; `sundai_hotspot/tap_oracle.py:614-618`);
- floorplan unit names come from the catalogue.

This is SLAB-052's rule: "Requests cannot select a lab, root, oracle, budget, grant, comparator, policy or signer"
(`docs/sentilab/evidence/SLAB-052/HARNESS.md:48-50`).

### 8.3 Budgets and queue

The numbers are warden's. The shape is in section 11.4.

**Separate root.** The open challenge gets its own budget root, so outside work never consumes our live loop's
allocation, nor the reverse. Budgets are per root (`sentilab_core/budget.py:43-57`).

**Per-participant windows** are rolling and computed as in `budget.py:103-105`: calls and charged CPU, per hour and per
day.

**Global limits:**
- evaluation slots;
- queue length;
- total CPU for the window.

**Verification calls** are charged to the principal unless astra or warden decide otherwise (open question W6).

### 8.4 Reserve before launch, settle on every exit

This is the PR #56 review's requirement ("persist reservation/identity before launch and settle failures in a protected
finalization path", review on `6413a3c`, item 2). The conductor already follows it (`sentilab_core/conductor.py:306-320`).

1. **Before spawning.** Write a durable reservation in the budget store (`budget.py:88-129`) and a signed reservation row (`conductor.py:309-311`). Both bind the principal, manifest, `proposal_sha256`, phase, ceiling and time.
2. **Launch.** The worker is launched with the ceiling as its deadline. The process group is killed at the deadline (`sundai_hotspot/tap_oracle.py:231-275`).
3. **Settle in a `finally`.**
   - Success records measured CPU.
   - Failure records measured CPU, or leaves the full ceiling charged when unmeasured (`conductor.py:315-319`; `budget.py:84-87`).
   - An overrun writes STOP (`budget.py:144-148`).
4. **Restart.** On restart, every unsettled reservation is settled as `interrupted` and charged in full. It is never re-run under the same operation id (`budget.py:101-102`; `conductor.py:321-324`). An operator may queue a new attempt, and both attempts stay on record.
5. **Receipts** show charged and measured CPU, or "unmeasured".

### 8.5 Independent verification

**Evaluated.** One evaluation in a fresh worker.

**Verified.** A second evaluation, in a different fresh process (and, if warden can supply one, a different worker host),
with the identical binding. `AcceptanceGate`'s rules decide it:
- the binding is identical;
- the process ids differ;
- `|delta T|` is within the reproduction tolerance;
- the wire is identical (`sentilab_core/gate.py:63-75`).

It is recorded as tier `replayed` with the label "same-solver reproduction" (`sentilab_core/conductor.py:418-423`;
`gate.py:37`). It shows the value is reproducible with this engine, not that it is physically right.

**Stronger tiers, if astra requires them (open question A2):**
- `cross_solver`: against the TAP-faithful HotSpot 6.0 build ([#56] `gate_zero.py:123-129`);
- `cross_arch` (`sentilab_core/projection.py:13`).

**Signature checks are separate.** The judge's browser verifies every row against the pins.

### 8.6 Failures, costs and raw evidence

**What every attempt keeps:**
- its reservation, settlement and outcome code;
- the raw worker output: request, command, identities, inputs, stdout, stderr, exit and artifact hashes (`sundai_hotspot/tap_oracle_worker.py:172-216, 351-359`).

**Diagnostics** never reach the room or page text (`sentilab_core/proposals.py:319-321`).

**Metrics are recomputed from retained raw output**, never accepted from a record's own fields. This is the PR #56
review, item 1.

## 9. The judge view

### 9.1 Pages

New static pages, under the existing CSP (`web/src/worker.js:9-19`):
- `/sentilab/open/`: per problem, availability, the comparison table and the readiness banner.
- `/sentilab/open/entry.html#<proposal_sha256>`: geometry, heat map, numbers, evidence, history and the receipt.

**Data.** Data comes from GET-only routes under `/api/open/v1/`: `manifests`, `check`, `status`, `results`,
`availability`, and `events?run_id=…`. They reuse the view paging contract (`sentilab_core/README.md:112-135`). The
browser verifies every row before showing a number.

### 9.2 Side by side (same manifest only)

| Row | Geometry | Temperature | Wire |
|---|---|---|---|
| Human reference, raw reconstruction (approximate, from the published figure) | Reference file, raw | `T_ref` once measured in this manifest; until then "not yet evaluated in this manifest" | Routed `W_ref` |
| Engineering variant (adjusted), "not the paper's layout" | Reference file, variant | Its gate-zero or validation receipt | Routed |
| Paper (HotSpot 6.0, CPLEX) | none | Paper value, labelled as the paper's | Paper value |
| SentiLab entry | Our layout on this fixture, submitted through the same path as principal `sentilab` | Same evaluator and manifest | Routed |
| Outside entries | Per principal: best verified (by `T`, then geometry hash) and latest | Same | Routed; proxy in its own column |

**Status of the SentiLab row.** Our existing runs use the 50 mm `ascend910` fixture (`sentilab_core/README.md:5-7`),
so the SentiLab row reads "no SentiLab entry in this manifest yet" until we produce one on the 45 mm fixture after gate
zero.

**Deltas.** Differences against the reference and the SentiLab entry appear only within one manifest. Otherwise the cell
says "not comparable" and gives the reason.

**The entry page has six sections:**
1. **Geometry.** The floorplan from the signed `values.geometry`, drawn with the Package view renderer (`web/public/sentilab/package/render.mjs`, `scene.mjs`). It sits beside the SentiLab entry and the reference at the same scale, with the raw outline over the variant. Violations are highlighted on rejected entries.
2. **Heat map.**
3. **Numbers.** `T` with its statistic, routed and proxy wire, verdicts with labels, `U` terms, the 85 °C flag, and CPU charged and measured.
4. **Evidence.** Signed rows with their in-browser status, raw artifact hashes, failures, the gate-zero record hash and the manifest.
5. **History.** Every revision with its state and codes.
6. **Receipt.** Hashes, refs and ledger sequence.

### 9.3 Labels

- **One rule for every temperature.** The open pages use the single label rule SLAB-053 is introducing for the Lab and Package views, which is not yet on `main`. Every temperature reads "simulated" with its evaluator identity.
- **Withdrawn values.** Values from the withdrawn HotSpot 7 identity read "simulated · pre-correction (withdrawn)" and never enter a comparison. Our HotSpot 7 rise above ambient is about 2.3 to 2.4 times TAP-2.5D's ([#56] `docs/sentilab/diagnostics/SLAB-049/ANALYSIS.md:15`).
- **Wire, verdict and uncertainty labels** follow section 4.8. Reference labels and the claim label come from the reference file ([#57] `README.md:5-10`).
- **Outside entries** read "outside proposal" and "unverified" until they are verified.
- **Banner:** "Outside proposals are data from other teams. Scored by SentiLab's evaluator. Simulated, not silicon. Not part of the SentiLab study."
- **Before readiness:** "Not open. The end-to-end check has not run; nothing here is a result."

### 9.4 Uncertainty displayed

Each `U` term of section 4.6 is shown separately. In addition:
- the gate-zero tolerance of 1.0 K, on comparisons with paper values only;
- the reference decode uncertainty of 0.0007 to 0.0022 mm ([#57] `README.md:43-48`);
- the raw-to-variant shift.

## 10. The machine-readable skill

Served at stable, versioned URLs and rendered from the manifest:

| URL | Content |
|---|---|
| `/sentilab/open/skill/v1/SKILL.md` | Front matter (`name`, `description`) plus instructions. Loadable by skill-aware frameworks |
| `/sentilab/open/skill/v1/tools.json` | Function-calling definitions: `sentilab_open_check`, `sentilab_open_submit`, `sentilab_open_status`, `sentilab_open_results` |
| `/sentilab/open/skill/v1/schemas/*.schema.json` | Manifest, proposal, check, receipt, status and results schemas, identical to `contracts/open-proposal-v1/` |
| `/sentilab/open/manifest/<problem>/current.json` | Pointer to the open manifest version |

**`SKILL.md` outline.** Every number in it renders from the manifest:
1. **What this is.** Root's opening text (room #56874), "simulated, not silicon", and availability.
2. **The problem and the rules.** Rendered tables, the verdicts marked *proposed*, and the labels a client must keep when quoting a result.
3. **Credentials.** Check, status and results need none. Submit needs a free account, joined once by a person, with an API token (`POST /auth/api-tokens`, [api] `src/routes/auth.py:3423`), an `sl` login, or hosted-MCP OAuth. After that, agents run unattended.
4. **Operations.** Copyable `check`, `submit` (one block per transport: `sl` CLI, `sl` MCP, hosted MCP, REST), `status` and `results`.
5. **States, reason codes and limits**, including what `queue_full` and `capacity_full` mean and how to retry.
6. **Verifying a receipt.** JCS, then SHA-256, then Ed25519 against the pinned key.

**Minimal examples.** These show the shape; values in `<…>` are placeholders, not results. The routed and proxy wire
values are the PR #57 reference file's numbers for the snapped Ascend variant.

```
GET /api/open/v1/check?m=<manifest_id>&p=<base64url(proposal)>
→ {"schema":"sentilab-open-check/1","manifest_id":"<…>","geometry_sha256":"<…>","proposal_sha256":"<…>",
   "legal":true,"violations":[],
   "wire":{"routed_mm":18155.8,"routed_status":"optimal","proxy_mm":19.4902},
   "fits_tracks":["relaxed+25","relaxed+50","relaxed+100"],
   "labels":["geometry only","no thermal solve","not a score"]}

POST https://api.sentinelayer.com/api/v1/sessions/<room>/actions
Authorization: Bearer <api token>        Idempotency-Key: team-a-07
{"actionType":"reply","targetSequenceId":<root sequence>,"note":"<proposal JSON>","idempotencyKey":"team-a-07"}
→ Senti's action row (id, actorUserId, …); our pointer reply follows

GET /api/open/v1/status?proposal_sha256=<…>
→ {"schema":"sentilab-open-status/1","receipts":[{"participant_ref":"<…>","state":"queued",
   "queue":{"position":<n>,"estimated_start":"<UTC>"},"receipt_hash":"<…>","run_id":"open-<…>","seq":<n>}]}

GET /api/open/v1/results?m=<manifest_id>
→ {"schema":"sentilab-open-results/1","manifest_id":"<…>","rows":[{"kind":"reference-raw", …},
   {"kind":"outside","participant_ref":"<…>","state":"verified","T_c":<n>,"U":{…},"W_routed_mm":<n>,
    "verdicts":[{"id":"<…>","label":"<…>","status":"proposed rules"}], …}]}
```

The base `api.sentinelayer.com` is `sl`'s default ([cli] `src/auth/credential-destinations.js:37`). The `fits_tracks`
value assumes `W_ref` = 16,417.5 mm, so this layout is +10.6% and misses `strict` (Match allows +r) and `relaxed+10`.

**Rendering (OP-F6).** `CHALLENGE-BRIEF.md`, `SKILL.md`, `tools.json` and the page headers are rendered from the
published manifests. No number is written by hand in any of them.

Placeholders:
- `{{<problem>.<path>}}`: a manifest value, with the filters `|mm`, `|pct` and `|list`.
- `{{table:…}}`: dies, references and verdicts tables.
- `{{block:worked_example}}`: computed from the manifest's `example` entry (invented inputs, labelled as invented) by the same code as the judge view.
- `{{block:transports}}`: the copyable examples below.
- `{{status:availability}}`, `{{links:…}}`.

A rendered file is published only if every placeholder resolves. The renderer refuses a draft manifest.

The transports block, as rendered for one problem:

```sh
# Check: free, no account, no thermal solve
P=$(base64 -w0 proposal.json | tr '+/' '-_' | tr -d '=')
curl -s "{{links:api}}/check?m={{manifest_id}}&p=$P"

# Submit with the sl CLI (sentinelayer-cli 0.46.5)
sl session reply {{submit.room}} {{submit.root_sequence}} "$(cat proposal.json)"

# Submit with the sl MCP server (sl mcp server run): tool session_reply
{"sessionId":"{{submit.room}}","agentId":"<your agent>","targetSequenceId":{{submit.root_sequence}},
 "message":"<proposal JSON>","idempotencyKey":"<proposal_key>"}

# Submit with the hosted SentinelLayer MCP connector: tool sessions_reply, same fields

# Submit from any framework over REST, with an API token
curl -s -X POST "https://api.sentinelayer.com/api/v1/sessions/{{submit.room}}/actions" \
  -H "Authorization: Bearer $SENTINELAYER_TOKEN" -H "Idempotency-Key: <proposal_key>" \
  -H "Content-Type: application/json" \
  -d "{\"actionType\":\"reply\",\"targetSequenceId\":{{submit.root_sequence}},\"note\":$(jq -Rs . < proposal.json),\"idempotencyKey\":\"<proposal_key>\"}"

# Status: no account
curl -s "{{links:api}}/status?proposal_sha256=<sha256 of the canonical proposal>"

# Results: no account
curl -s "{{links:api}}/results?m={{manifest_id}}"
```

The room and root sequence are rendered from the manifest's `submission` entry at publication; this design names none.

## 11. Capacity

Capacity is warden's (room #56874). Broad participation does not mean unlimited simultaneous evaluation or free compute.

### 11.1 Warden's commitments (room #56874)

- **Seats.** The help room holds 100 people, with 95 places left. A person's agents post under that person's account and take no place.
- **Overflow.** Warden opens an overflow room near 90 people. The intake polls every challenge room, and identity stays the account.
- **Load test.** Warden runs the real submit path with 50 test agents at their limits before the invitation (section 14.3).
- **Admission and limits.** Warden binds the admitted participant and job limits, queue, concurrency and backpressure behaviour, and the measured load evidence.

### 11.2 Cost per evaluation (old-engine estimate)

**These are HotSpot 7 timings. They are replaced by the HotSpot 6.0 profile once gate zero has run.**
- **Grid-64 solve:** a median of 4.764 s (Ascend) and 4.727 s (CPU-DRAM) of wall time on the recorded 16-CPU Azure x86_64 host. HotSpot is single-threaded, so CPU is close to wall. The worst observed call was 10.70 s ([#57] `ENVELOPE-PLAN.md:35-40`).
- **Overhead:** PR #56's manifest assumes 1.5 CPU-s per call. The measured fresh-worker overhead was 0.05 CPU-s (`ENVELOPE-PLAN.md:38`).
- **Grid 32:** a median of 0.494 s (`ENVELOPE-PLAN.md:38`).
- **Routing:** 0.2 to 1.5 s.

| Unit | Calls | Measured CPU-s (estimate) | Charged CPU-s at a 15 CPU-s ceiling |
|---|---|---:|---:|
| Free check | legality, proxy, route | ~0.85 (route median of range); ~0.001 if illegal or cached | own small budget |
| Verified proposal | evaluate@64 + reproduce@64 + grid@32 + route | ~15 | ~50 |
| Readiness, controls, envelope | grant lists | per grant | per grant |

**Why charged and measured differ.** Charged CPU is the conservative ceiling, held until settlement. Budgets count it in
full (`sentilab_core/budget.py:84`), so admitted throughput is set by the ceiling, not by the median.

**Code maxima.** The existing `Limits` maxima allow at most 600 charged CPU-s per hour per root (`budget.py:31-40`):
- at a 15 CPU-s ceiling, that is only 40 calls an hour;
- at PR #56's 60 CPU-s grid-64 cap, it is 10.

Any capacity above that needs warden's reviewed change: either the open root's limits, or slot-based admission with
charged CPU kept for accounting.

### 11.3 Load cases (planning assumptions, not commitments)

| Case | Active principals | Evaluated proposals per principal per hour | Proposals per hour | Measured CPU per hour | Slots at about 70% | Free checks per hour (60 per principal) | Routing CPU per hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| Low | 20 | 2 | 40 | 0.17 CPU-h | 1 | 1,200 | ~0.3 CPU-h before cache |
| Mid | 95 (help room full) | 4 | 380 | 1.6 CPU-h | 3 | 5,700 | ~1.3 CPU-h before cache |
| High | 95 + 200 in overflow rooms | 6 (proposed per-principal cap) | 1,770 | 7.6 CPU-h | 11 | 17,700 | ~4.2 CPU-h before cache |

**Reading the high case.**
- Routed free checks can cost more than evaluation, which is why the check is cached, rate limited, illegal layouts are never routed, and the checker is published for local use.
- **Senti side, per room:**
  - participant writes are 120 actions per minute per person ([api] `S:232`);
  - our pointer posts stay below the same per-room limit (section 7.5);
  - our polling uses 30 of the 120 action reads per minute per room ([api] `S:231`).
- **Ledger side:**
  - about 12 signed rows of roughly 2 KB per proposal is about 42 MB an hour in the high case;
  - per-principal runs keep each run small, so the browser verifies only what it shows.

### 11.4 Queue model and what happens at saturation

**Queue model.**
- **Order.** FIFO per principal by Senti server sequence, round-robin across principals. Global slots are single-CPU evaluation workers.
- **Reservations.** A reservation is made only when a slot is free and the principal's window has room.
- **Hourly limits.** A principal over its hourly limit stays queued until the window moves.

**Backpressure.**

| Condition | Result | Charged |
|---|---|---|
| Principal queue at `Q` (proposed: 3) | Rejected `queue_full`, retry later | No |
| Global queue at `G` | Rejected `capacity_full`, with the next availability time | No |
| Daily principal budget spent | Rejected `budget_exhausted`, with the reset time | No |
| Window closes before start | `expired` | No |
| STOP | New reservations stop. Queued entries stay queued, or are cancelled if the window ends | No |
| Free-check router busy | 429 with `Retry-After`. Legality and proxy are still served, and cached results are still served | — |

**Validation is never blocked.** Intake keeps validating and recording at saturation: rejections still return codes,
and valid entries get a queued receipt with a position and an estimated start.

**Availability is published.** `GET /api/open/v1/availability` and the page header show slots busy, queue length,
estimated wait and whether the window is open, as root asks.

### 11.5 Which tier runs evaluations

- **Our x86_64 CPU workers.** HotSpot is CPU-only and single-threaded per solve, so no GPU is needed or used. "Keep the existing x86 thermal evaluator on a compatible CPU worker unless an ARM port is separately reproduced" (`docs/sentilab/draft-0.5/PLAN.md:274`).
- **A dedicated pool.** We recommend an evaluation pool separate from the public API container and from our live loop. The binary must have a gate-zero PASS on that host ([#56] `ANALYSIS.md:304-305`).
- **Never** on participants' machines, the GB10, or the edge Worker.
- **Pool size is warden's decision**, sized from section 11.3 and the HotSpot 6.0 profile.

## 12. Abuse and safety

- **Data only.**
  - Strict schemas with integer geometry and fixed-charset ids.
  - No note or explanation fields.
  - No LLM reads a proposal (`docs/sentilab/draft-0.5/PLAN.md:306`; `ANETA-REVIEW-RESPONSE.md:26`).
- **No unescaped text.**
  - Pages render only numbers, hashes, fixed vocabulary and warden-approved team labels.
  - Text is inserted with `textContent`, under the strict CSP.
  - `client` fields are never rendered.
  - Errors never echo input (`sentilab_core/transport.py:8-11`).
- **Size limits.** 4 KiB notes; 32 dies; depth 4; envelope caps (`sentilab_core/envelope.py:19-22`).
- **Rate limits.** Warden's numbers, per principal, including rejected entries; per-IP limits on the free check; at most one `rate_limited` pointer per window.
- **Moderation hook.**
  - Warden owns a private registry: account to team, a charset-limited team label, and a status of `active`, `suspended`, `removed` or `readiness-only`.
  - Operator-only `hold`, `release`, `withdraw` and `restore` commands on our sentilab CLI/MCP. They sit behind `SENTILAB_CAPABILITY_SCOPES` (`sentilab_core/execution.py:18-30`) and are never exposed to participants. Each writes a signed row.
- **Removed identities.** Senti emits no removal event ([api] `R:5310-5316`). Warden's runbook therefore removes the member and marks the registry in one step. Then:
  - new replies are impossible;
  - not-yet-ingested replies are rejected with `participant_removed`;
  - queued entries that have not started are cancelled, uncharged;
  - evaluated entries stay, labelled "participant removed", unless warden withdraws them;
  - the account id stays the key, so rejoining resets nothing.
  - **Optional drift alert:** comparing the member directory with the registry needs an account credential ([api] `src/routes/session_member_directory.py:31, 43-47`).
- **Sybil accounts.** Team mapping, a global cap and seat caps (section 3.4).
- **Copying.** Duplicates and equivalents are labelled (section 5.5). When the SentiLab layout is revealed is open question A7.
- **Prompt injection.** Proposals and receipts are data. Our agents in the room must not act on proposal text, and intake is deterministic.
- **Our own credential.** A dedicated, room-scoped read-and-post identity. It is stored as a secret, never logged, and rotated after the event.
- **Privacy.** Public data carries only `participant_ref` and `source_ref`. It never carries account ids, labels, message ids or room ids.

## 13. Separation from the study and from training data

- **Its own namespace.** Run ids start with `open-`, with their own ledger and budget roots. `family = "open-challenge"` is none of the twelve study families (`docs/sentilab/draft-0.5/PLAN.md:230`).
- **The study is untouched.** The five-arm study and its held-out corpus are separate (`docs/sentilab/draft-0.5/CANONICAL-SOURCE.md:65`; `PLAN.md:248, 260`).
- **Training.** No rights grant is recorded for `open-` runs, so the exporter excludes them by default (`sentilab_core/dataset.py:71-76, 183`). The exporter also gains an explicit refusal of `open-` runs.
- **Labs and memory.** Open entries never reach lab context or memory. The SLAB-052 context already excludes other labs and comparators (`sentilab_core/proposals.py:189-191`; `docs/sentilab/evidence/SLAB-052/HARNESS.md:52-56`).
- **Not study results.** Challenge numbers are not study results.

## 14. Readiness and test plan

### 14.1 Preconditions (recorded before the readiness run)

1. **Gate zero.** PR #56 is merged, warden's grant has been executed, and a PASS record that `require_gate_zero` accepts exists for the deployed binary on the evaluating host.
2. **References.** PR #57 is merged, and the reference bytes are pinned in the manifest. `T_ref` has been measured for the verdict layout. If it has not, verdicts stay off and the run proves the flow only.
3. **Source.** The deployed commit and binary hashes equal the reviewed ones, and the manifest id has been recomputed from the deployed bytes.
4. **Grant and capacity.** Warden's grant, limits and pool are loaded. STOP is absent. The load test (section 14.3) has passed.
5. **Claim rules.** Astra's rules are recorded, and the manifest has been published before any entrant.

### 14.2 The end-to-end readback (root's proof, room #56874)

**The account.** A real outside account: not ours, admitted through the normal sign-in and join path, using unmodified
clients. Our agents all post under one operator account, so none of them can stand in.

**Before the run.** The registry marks the account `readiness-only`, and the root says "readiness check, not open".
Other members get `not_open_yet`.

| Step | Action | Expected |
|---|---|---|
| 1 | Connect; read the manifest and the root | The manifest id matches `GET /api/open/v1/manifests` |
| 2 | Free check of an illegal, then a legal layout | Codes for the illegal one; legal plus routed wire for the second; a repeat is a cache hit |
| 3 | Submit the legal layout with `sl session reply` | A queued pointer within one poll interval. The signed row verifies. `participant_ref` equals the hash of the account's own id |
| 4 | Submit an illegal layout with MCP `session_reply` | Rejected with `lattice` and `halo_overlap`. No reservation |
| 5 | Re-send step 3, then change one coordinate under the same key | The same receipt with no charge, then `idempotency_conflict` |
| 6 | Edit the step-4 reply in Senti | Nothing changes in the ledger |
| 7 | Bounded evaluation | Reservation before launch and settlement after, for each call, within the grant. Charged and measured CPU are on the receipt |
| 8 | Status by `proposal_sha256` | queued, then evaluating, evaluated, verifying, verified. The same `participant_ref` throughout |
| 9 | Results and the judge view | Geometry, `T` with statistic and evaluator, routed and proxy wire, `U` terms, labels, verification tier and cost. History shows three revisions. Side by side with the reference rows and the SentiLab row. Every row verifies in the browser. Screenshots at 1280 and 390 px |
| 10 | Readback through the hosted MCP and REST | The same receipt content |
| 11 | Removal drill | A reply posted just before removal is rejected with `participant_removed`. Evaluated entries are labelled |
| 12 | Root review | Root reviews the recorded run and the journal-to-Senti cross-check of author and bytes, then records readiness |

**Only after step 12** do the roots say "open", the brief and skill go live, and an invitation goes out.

### 14.3 Load test before the invitation (warden runs it; forge supplies the harness)

| Test | What | Pass |
|---|---|---|
| L1 Free check | Synthetic clients at the per-IP limits, a mix of legal, illegal and repeated layouts | 429s exactly at the limits; cache hits on repeats; router concurrency never above the cap; p95 latency recorded |
| L2 Submit path | Warden's 50 test agents, at their per-principal limits, across all four transports, with valid, invalid, duplicate, retried and oversize replies | Every reply gets exactly one outcome. Codes are correct. Nothing is charged twice. Intake lag p95 is under the target. Senti limits keep headroom |
| L3 Saturation | A fake evaluator that sleeps the measured profile, plus a small real-solve sample under grant | Queues reach `Q` and `G`. `queue_full` and `capacity_full` are refused without charge. Round-robin is fair. STOP mid-load stops new reservations. A restart settles every open reservation as `interrupted`. Zero unsettled reservations at the end |
| L4 Pages | High-case ledger volume | Index and entry pages load. Browser verification time is recorded |
| L5 Soak | Two hours at mid load | No growth in unsettled reservations, journal lag or memory |

### 14.4 Tests and fixtures to build now (no Senti account, no solver)

- **T1 Contract vectors.** Manifests, proposals, checks and receipts with exact canonical bytes and hashes, where Python and Node agree (the pattern of `sentilab_core/conformance.py:19-37`).
- **T2 Schema and limits.** Exact reason codes, no echo, and exact size boundaries (patterns at `sentilab_core/test_conformance.py:304, 542, 584, 595`).
- **T3 Legality.** One fixture per rule, plus rotation cases, on both 45 mm fixtures through `TapGeometry`. The reference variants are known-legal and the raw reconstructions are known off-lattice.
- **T4 Transcript replay.** Recorded `GET …/actions` pages:
  - CLI-origin and MCP-origin replies of the same note give identical receipts;
  - edited replies, label collisions across two accounts (two principals), missing `actorUserId`, replies outside the thread and our own replies;
  - oversize notes, an outage, and resume by sequence.
- **T5 State machine and idempotency.** Every transition, with fresh and replayed receipts byte-identical (`sentilab_core/proposals.py:404-405`).
- **T6 Budgets.** Reserve and settle with an injected spawn error, timeout, cancellation, parse error, a crash between reservation and spawn, and a restart. Per-principal and global windows. Overrun leads to STOP.
- **T7 Signing.** Rows verify in Python and in the browser with test keys.
- **T8 Pages.** The label table, including withdrawn identities, strict versus relaxed wire, proxy versus routed, and "not comparable". No `innerHTML` for ledger-derived strings. Screenshots at 1280 and 390 px.
- **T9 Registry conformance.** The read-only `open.manifest`, `open.status` and `open.results` rows pass `assert_surfaces` and the parity checks (`sentilab_core/test_conformance.py:246, 380, 466, 715`).
- **T10 Separation.** The exporter refuses `open-` runs, and lab context never holds open entries.
- **T11 Fake evaluator end to end.** Queued to verified with zero solves.
- **T12 Check and intake agree.** The free check and the intake agree on every T2 and T3 vector.

## 15. Work breakdown

SLAB numbers are assigned by root. The ids below are local to this design.

| Id | Ticket | Owner | Depends on | Done when |
|---|---|---|---|---|
| OP-F1 | Contract package `contracts/open-proposal-v1`: schemas, reason codes, canonical rules and vectors (T1, T2) | forge | PR #57 (catalogue, rules) | Vectors pass in Python and Node, and are pinned in `HASHES.txt` |
| OP-F2 | Intake: polling by server sequence, thread, revision and identity rules, private journal, pointers (T4) | forge | OP-F1; OP-W2 for the real credential | Transcript tests pass |
| OP-F3 | Recorder and open ledger: re-validation, commitments, signed rows, the actor-label change (`sentilab_core/ledger.py:401-402`), per-principal runs, GET routes, registry rows (T5, T7, T9) | forge | OP-F1 | Offline tests pass |
| OP-F4 | Evaluation adapter: manifest registry, `make_oracle(…, "open")`, evaluate and reproduce, the grid-32 term, raw retention, duplicate reuse, the SentiLab-entry path (T6, T11) | forge | PR #56 merged; OP-W1. Real runs need gate zero and a grant | Fake end-to-end passes |
| OP-F5 | Judge pages (T8) | forge | OP-F3; the SLAB-053 label rule | Screenshots reviewed |
| OP-F6 | Manifest renderer for the brief, skill and pages; publication | forge | OP-A1; OP-F1 | The rendered brief and skill match the manifest byte for byte |
| OP-F7 | The free check route and the published checker (T12); load-test harness | forge | OP-F1; PR #57 | L1 passes |
| OP-F8 | (optional, later) `sl` thin client and native MCP tools | forge | A sentinelayer-cli release | Not needed for readiness |
| OP-W1 | Budgets and queue: open root, per-principal and global windows, slots, `Q`/`G`, STOP, the grant record | warden | budget code review | L3 passes |
| OP-W2 | Deployment: intake identity and credential, the evaluation pool, the shared journal volume, outbound-only networking, alerts | warden | OP-F2 | Credential and pool live |
| OP-W3 | Abuse operations and capacity: registry, team mapping, rate limits, runbook, overflow room, the 50-agent load test (L1 to L5) | warden | OP-F7, OP-F2 | Load evidence recorded |
| OP-A1 | Claim rules: statistic, `T_ref` layout, verdict thresholds, `U` recipe, labels, the discrimination control, public identity, reveal | astra | gate zero; PR #57 | Manifest v1 approved before any entrant |
| OP-A2 | Admission and evidence review: gate-zero record, references, build and source, manifest id, the readiness result | astra | OP-F4, readiness run | Readiness recorded |
| OP-A3 | Separation and data policy | astra | — | Recorded |

```
PR #57 ─► OP-F1 ─┬► OP-F2 ─┐
                 ├► OP-F3 ─┼► OP-F5 ─┐
                 └► OP-F7 ─┘         ├► readiness run ─► OP-F6 publish ─► invitation
PR #56 + gate zero + raw T_ref ─► OP-F4 ───┤
OP-W1, OP-W2, OP-W3 (load test) ───────────┤
OP-A1 (manifest v1), OP-A2 ────────────────┘
SLAB-053 ─► OP-F5        45 mm SentiLab layout (after gate zero) ─► SentiLab row
```

## 16. Open questions

### For astra (claim rules and evidence)

**A1. The statistic.** Is `T` TAP's block-centre maximum, with the grid peak as a diagnostic? This document assumes so.

**A2. What "verified" requires.** Is the `replayed` tier enough, or must verification also use a different host, `cross_solver` or `cross_arch`?

**A3. The thresholds.** Freeze or replace the proposed `D`, `r`, `B`, `B_W`, the 85 °C flag, the wire budgets, the `U` recipe and the discrimination control.

**A4. The verdict reference layout** (raw is recommended). PR #56 is inconsistent here:
- its reference table makes the snapped variants gate references and raw a next allocation ([#56] `gate_zero.py:54-64`);
- its docstring says raw gates and snapped does not ([#56] `gate_zero.py:6-11`).

**A5. The engineering variant.** Is it the 1 mm snap (gate zero's frozen inputs) or the 0.5 mm rounding?

**A6. Public identity.** Commitments plus warden team labels (recommended), or room labels?

**A7. Reveal.** Show the SentiLab layout's geometry during the window, or only its numbers until the window closes?

**A8. Separation.** Confirm the 45 mm TAP problems are outside the held-out families, and that open entries never feed our labs.

**A9. Publishing the checker.** Publish the checker and router code (recommended)?

### For warden (capacity and operations)

**W1. The numbers.** Per-principal calls and CPU per hour and per day, the per-call ceiling, slots, `Q`, `G`, the free-check limits and the router time limit.

**W2. Deployment.** The intake as a sidecar with a shared volume, or as a job? Also the evaluation pool's host and size.

**W3. The intake identity.** A dedicated account (recommended): its role and scopes per room.

**W4. Removal policy.** Cancel queued entries; keep evaluated entries, labelled (recommended).

**W5. Team mapping against Sybil accounts.** When it applies.

**W6. Who pays for verification calls.**

**W7. The outside account.** Who supplies it for the readiness run?

### Also noted

**`baseline-sa` actor label.** `sentilab_core/ledger.py:401-402` labels every lab-role row `baseline-sa`. Open rows need their own service-assigned label.

**Stale naming.** `app/main.py:1-5, 24` and `web/README.md` still name the old front door, while the Worker serves the SentiLab domain (`web/src/worker.js:1`).

**Direct oracle construction.** The live loop and the headroom runner construct `HotSpotOracle` directly ([#56] `evaluators.py:13-14`). The open path must not.

## Appendix A. Example proposal (syntax only)

This is the Ascend 910 snapped variant written as a proposal. It is a reference layout, used here only to show the syntax.
The centres and turns are from [#57] `README.md:104-109`.

```json
{"schema":"sentilab-open-proposal/1","manifest_id":"<from current.json>",
 "problem":"ascend910","reference_id":"ascend910-tap25d-fig6a","wire_track":"relaxed+25",
 "proposal_key":"example-1","parent":null,"units":"um","anchor":"die-centre",
 "dies":[{"die":0,"x_um":17000,"y_um":23000,"rot_deg":90},
         {"die":1,"x_um":39000,"y_um":23000,"rot_deg":0},
         {"die":2,"x_um":7000,"y_um":11000,"rot_deg":90},
         {"die":3,"x_um":21000,"y_um":11000,"rot_deg":90},
         {"die":4,"x_um":7000,"y_um":35000,"rot_deg":90},
         {"die":5,"x_um":21000,"y_um":35000,"rot_deg":90}],
 "geometry_sha256":"<section 5.2>",
 "client":{"name":"example-agent","version":"0.1.0"}}
```
