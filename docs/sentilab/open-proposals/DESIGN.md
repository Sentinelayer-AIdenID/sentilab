# Open proposals: design

Ticket `e76b348f`. Agents and people from other teams propose 2.5D chiplet layouts. SentiLab scores each one with the
same admitted engine, comparator, statistic and labels as its own frozen baseline, and shows the results to the judges.

**Status: DRAFT for review, revision 3.** This is a design only: no code, no deploys, no solves and no room posts. It
applies five inputs:
- root's decisions on revision 1's open questions (room #56902);
- root's challenge-math review and provisional contract (`[review]` below);
- astra's review of revision 1 at `28ecd6f` (room #56918), checked in revision 3 against the exact review files (`[#59-review]`): six corrections and the gaps revision 2 missed, mapped in Appendix C;
- astra's review of revision 2 at `6e6e110` (room #56957): groups 1, 2, 3 and 6 and the core of group 4 closed; the accounting correction and decisions A10 to A13, mapped in Appendix C. The review file (SHA-256 `cf575bfa…1a1c`) was not in any ref I could fetch, so it is applied from the room text;
- warden's provisional operations decisions (room #56897, corrected by #56899; the 5 s whole-check wall in #56952, accepted in room #56957).

Policy thresholds and the call allocation are **provisional manifest fields**, not constants. They are fixed in the
signed manifest before any candidate is scored. Nothing here releases an intake, solver, cloud model or load execution.

| Role | Owns |
|---|---|
| forge | The submission contract across CLI, MCP and REST; checks; adapters; the skill; the judge pages; the brief |
| warden | Capacity, budgets and the global journal, admission, abuse operations, the load test |
| astra (root) | The claim manifest (the math in section 4), readiness review, data policy |

**Pins.** Every `path:line` citation is at one of the commits below. Untagged paths are `[main]`.

| Tag | Source |
|---|---|
| `[main]` | sentilab `origin/main` `568dd39` (SLAB-053 part 1, PR #58). Every `[main]` citation outside `web/public/temperature-label.mjs` is unchanged from `315bbff` |
| `[#57]` | sentilab PR #57 at `063f659` (SLAB-048). The PR has since merged `main` at `6dd4dd0`: cited `tap_oracle.py` lines shift by 1 to 2 with identical code, and the other cited files are unchanged |
| `[#56]` | sentilab PR #56 head `6413a3c` (SLAB-049: HotSpot 6.0, gate zero, per-solve record) |
| `[review]` | sentilab `2f69727`, `docs/sentilab/reviews/2026-10-31/challenge-math-1606/`. `REVIEW.md` SHA-256 `0d427674…f48b`; `PROVISIONAL-CONTRACT.md` SHA-256 `480c2e37…0032`. Both verified |
| `[#57b]` | sentilab PR #57 at `7de7d01`: the 0.5 mm `snap0p5` engineering variants, frozen layout identities, the 46-call envelope and the hardened router. The raw and 1 mm layouts are byte-identical to `063f659` (`README.md:62`) |
| `[#59-review]` | sentilab `b7bd8bd`, `docs/sentilab/reviews/2026-10-31/pr59-design-1627/`: astra's review of revision 1. `REVIEW.md` SHA-256 `4b2dd6f8…22d9`; `ROOT-DECISION-OPTIONS.md` SHA-256 `d960dc99…f6c2`. Both verified and read in full |
| `[cli]` | sentinelayer-cli 0.46.5; paths are relative to the npm package |
| `[api]` | sentinelayer-api `origin/main` `6f8058f5`. `R` = `src/services/session_relay_service.py`, `S` = `src/routes/sessions.py` |

Room messages are cited by number; room ids are never cited.

## 0. Decisions at a glance

| # | Question | Decision |
|---|---|---|
| 1 | Transport and identity | **(a), room-native.** A proposal is a threaded reply in the challenge thread, stamped by Senti with the author's account id (`actorUserId`). An outbound-only intake reads replies in `created_at,id` order and persists its cursor only after durable processing. Every client derives a **bounded transport idempotency key** from room, account, actor slot, manifest, logical key and content hash. No new inbound endpoint. |
| 2 | Actor kinds | Agents post through the `sl` CLI (`--agent`), the `sl` MCP, the hosted MCP or REST with an agent claim. People post through REST without one. Each has a truthful recipe, and quotas bind to the account. |
| 3 | Confidentiality | Private submissions **and** private routed checks are sealed with `age` to the intake's recipient, bound to the signed manifest (A10, adopted). There is no plaintext fallback. Private status is reachable only through an unguessable per-request handle. |
| 4 | Identity in public | Per-challenge keyed pseudonyms plus voluntary, moderated team names. Account ids stay in the restricted ledger. Public display requires explicit, versioned submission terms. |
| 5 | The math | One versioned manifest per problem, aligned with root's contract. The raw comparator `R` is measured by the same fixed evaluator; published targets are separate. `T_M` = the maximum native centre-map value over **explicitly enumerated** real chiplets. Claims are strict, relaxed and Pareto predicates. With no accepted bounds, a claim can only "pass the listed sensitivity cases". |
| 6 | Checks | An offline local checker for anyone. An **authenticated, sponsored remote routed-wire check** for the account-limited tier, which runs through the room. There are no anonymous remote checks. |
| 7 | States | rejected; queued (held, evaluating); evaluated or failed; "reproduced under that evaluator"; optionally a separately qualified cross-check. Moderation hides from public views and never deletes. |
| 8 | Evaluation | Only an admitted manifest, through `make_oracle`. Every native call, route and lifecycle step is reserved before launch and settled on every exit, under distinct suballocations of **one retained global journal**. |
| 9 | Judge view | Public pages show the frozen SentiLab baseline and reference geometry from opening, the published targets kept separately, and entries with public consent. A restricted judge view shows everything. |
| 10 | Skill and adapters | `SKILL.md`, `tools.json` and JSON Schemas, rendered from the manifest, plus reference adapters. `tools.json` alone registers nothing. |
| 11 | Capacity | Warden's provisional quotas. Throughput is proven only by measurement and a load test across real quota principals. |
| 12 | Readiness | Root's proof: a real outside account connects, submits, checks status and gets its own result under the same identity, after gate zero, admission and the load test. There is no five-arm prerequisite. |

## 1. Scope

**In scope:**
- The two published TAP-2.5D problems on the 45 mm fixtures: Ascend 910 (`ascend910-45mm`, reference `ascend910-tap25d-fig6a`) and CPU-DRAM (`micro150-45mm`, `micro150-tap25d-fig5a`) ([#57] `docs/sentilab/references/README.md:16-22`; `sundai_hotspot/tap_oracle.py:25-32`).
- Submission through the clients participants already have.
- Public pages, a restricted judge view, status and results.
- A **descriptive** comparison with named reconstructed research layouts. It does not establish that agents are as good as human engineers ([review] `REVIEW.md:15`).

**Not in scope:**
- A new `sl` release (OP-F8 is optional).
- Any LLM in intake, checking or scoring.
- Any change to the five-arm study, held-out data, the live loop or training data (section 13).
- Prizes, dates, completed-model claims, and judge claims before readiness (section 14).

## 2. What exists today

| Piece | Where | Used here for |
|---|---|---|
| **Root's math review and provisional contract.** `(T_R, W_R)`, `delta_T`, `q_r`, bounded and screened predicates, budgets, readiness | [review] `REVIEW.md:1-21`; `PROVISIONAL-CONTRACT.md:1-41` | Section 4 |
| **Fixture legality, no solver** (`TapGeometry`) | [#57] `sundai_hotspot/tap_oracle.py:111-135, 255-275, 278-312, 320-398` | Legality checks |
| **45 mm fixture rules** | [#57] `sundai_tap/configs/sys_ascend910_45mm.cfg:30-38`, `sys_micro150_45mm.cfg:32-40` | Manifest legality |
| **Per-solve record.** `chiplet_centre_mapping.max_C` (GRID_CENTER: the mean of 1, 2 or 4 cells), `active_layer_grid_peak` with argmax, `historical_tap_stdout_selector` | [#56] `sundai_hotspot/slab049.py:242-251, 1001-1004, 1025, 1045-1049, 1077-1080` | `T_M` and its separate observables |
| **Engine boundary.** Legality before any worker; server-built request; binding; worker re-hashing; fixed environment; 64 KiB request cap | `sundai_hotspot/tap_oracle.py:779-808, 840-848`; `sundai_hotspot/tap_oracle_worker.py:100-106, 218-240, 347-348` | Proposals contribute centres and rotations only |
| **Evaluator selection.** `make_oracle` with gate zero | [#56] `sundai_hotspot/evaluators.py:3-14, 41-72, 90-104`; `sundai_hotspot/gate_zero.py:247-280` | The only open evaluation path |
| **References and published values** | [#57] `docs/sentilab/references/README.md:5-10, 86-99, 132-136`; `ascend910-tap25d-fig6a.json:2, 246, 368, 516-518` | `R`, engineering variants, published targets |
| **Router.** MILP on HiGHS; the model is built in Python, then `time_limit` applies | [#57] `sundai_hotspot/tap_router.py:1-12, 35, 74-143` | Routed wire `W` |
| **Budgets and reservation** | `sentilab_core/budget.py:18-40, 80-150`; `sentilab_core/conductor.py:300-343` | The global journal |
| **Proposal harness (SLAB-052)** | `sentilab_core/proposals.py:1-5, 262-325, 268-271, 319-321, 404-405` | The receipt pattern; warden's "same ledger as SLAB-052" |
| **Evaluate, replay, verify** | `sentilab_core/conductor.py:368-370, 402-424`; `sentilab_core/gate.py:35-38, 63-75`; `sentilab_core/projection.py:13` | "Reproduced under that evaluator" |
| **Signed ledger.** Lab-role rows hardcode `baseline-sa` | `sentilab_core/ledger.py:330-411, 401-402`; `sentilab_core/envelope.py:65-95, 233-268` | Receipts |
| **Label rule (merged).** `ACCEPTED` is empty | `web/public/temperature-label.mjs:12-19, 23-28, 38-53, 60-85` | Temperatures on the open pages |
| **Capability registry (SLAB-043)** | `sentilab_core/capabilities.py:12-27, 282-296`; `sentilab_core/test_conformance.py:246, 304, 380, 466, 542, 552, 584, 595, 715` | Operator capabilities, contract tests |
| **Read-only public edge** | `web/src/worker.js:28-30, 51-56`; `app/main.py:20-25`; `sentilab_core/README.md:112-135` | No inbound write route |
| **Separation rules** | `docs/sentilab/draft-0.5/CANONICAL-SOURCE.md:65`; `PLAN.md:260, 306`; `ANETA-REVIEW-RESPONSE.md:26`; `sentilab_core/dataset.py:71-76, 183` | Section 13 |

## 3. Transport and identity

### 3.1 What Senti and `sl` give us

**Identity.**
- **Ordinary messages expose no account id** ([api] `R:5635-5649`).
- **Labels are not identities** ([api] `R:1778-1783`; `alembic/versions/050_user_agent_grants.py:72-76`).
- **A reply row carries:**
  - `id`, `actionType`, `actorKind`, `actorId`, `actorUserId`, `idempotencyKey` and `createdAt`;
  - the target sequence;
  - `messageRevision` and `editedAt` ([api] `R:10768-10787`; `src/services/session_message_service.py:59-72`).
- **`actorUserId` comes from the authenticated caller** ([api] `R:12574`, `R:12650-12654`). It is removed only for public readers ([api] `R:10283-10285`, `R:3185`).

**Actor kind.** It is decided by `_resolve_session_actor` ([api] `S:878-951`), in this order:
1. a scoped agent token acts as itself;
2. a claimed `agentId` must be a grant (for message actions the claim is read from `metadata`, `S:891`, `S:954-971`);
3. otherwise the action is stamped as the human (`S:896-897`).

**Replays.** The idempotency lookup is scoped to the **room**, not the account ([api] `R:12558-12573`). A replay compares
the actor slot, action type and targets, **but not the note** ([api] `R:11669-11691`). A same-key retry with a changed
note returns the original row, and another account's same key is refused.

**Reading.**
- `GET …/actions` returns `auditWindow {nextCursor, hasMore, order: "created_at,id"}` ([api] `R:12926-12930`; route `S:6569`). Machine clients poll ([api] `S:6164-6181`).
- Limits: 120 action reads and 120 writes per minute per user per room ([api] `S:231-232`, `S:7377-7384`). A note may be up to 64,000 characters ([api] `S:2828`), and a key up to 180 ([api] `S:1032`).

**Membership.**
- Writing requires membership. Removal emits no event ([api] `S:5704`, `R:5310-5316`, `R:3157-3181`).
- Admitted agents lose authority with their person ([api] `src/services/session_admission_service.py:4159-4171`).
- **Every member reads every reply.**

**Rejected carriers.** Tickets ([api] `R:11806-11807`, `R:12048-12049`) and attachments ([api] `R:14103`).

**Credentials.**
- `POST …/actions` accepts MCP tokens with `sessions:write`, scoped agent tokens, user JWTs and API tokens ([api] `S:595-628`).
- No third-party audience ([api] `src/auth/mcp_tokens.py:137-151`).
- Passports prove identity, not authorization ([api] `src/services/agent_passport.py:8-14`).
- Replies are not metered ([api] `src/services/session_usage_quota_service.py:51-92, 186-188`).

**`sl` clients.**
- `sl session reply <sessionId> <targetSequenceId> <message...>` with `--agent <id>` and `--idempotency-key <key>` ([cli] `src/commands/session.js:4614-4617`).
- MCP `session_reply` ([cli] `src/mcp/session-stdio-server.js:1565-1585`).
- Both `POST …/actions` ([cli] `src/session/sync.js:2994-3002`; `src/mcp/session-stdio-server.js:765-773`).
- The 13 native tools are at [cli] `src/session/route-classes.js:25-37`.
- There is no structured input (`:1493-1515`), and MCP text is capped at 16,000 characters (`:42`).
- Commands are fixed at build ([cli] `src/cli.js:7-138`; bridge refused: `src/mcp/cli-command-tools.js:389, 623`).
- The hosted MCP has `sessions_reply` and `whoami` ([api] `src/routes/mcp.py:2221-2242, 1890-1905`).

### 3.2 Recommendation: (a), threaded replies read by an outbound-only intake

**How it works.**
- A participant replies under a challenge root.
- Senti writes one action row stamped with the caller's account id.
- The intake reads the room's action window, binds each submission to that id, validates it, and records a signed receipt.

**Why (a):**
1. **Server-authenticated identity.**
2. **No inbound write endpoint.** The edge stays GET-only (`web/src/worker.js:51-56`), and we never handle participant credentials.
3. **The same row from every client.**
4. **Moderation reuses membership.**
5. **Two independent records.**

**Costs:**
- polling latency (target under 30 s at p95);
- outages (resume from the last durably processed cursor; section 3.4);
- chat noise (only replies to a challenge root count);
- edits (revision 1 only);
- room pointers are best effort.

### 3.3 Alternatives

**(b) An endpoint verifying Senti credentials.** It would need replayable account JWTs or MCP-audience tokens ([api]
`src/auth/mcp_tokens.py:137-151`). There is no introspection, no passport proof of possession, and it needs a write
route at the edge. Rejected.

**(c) A new `sl` command.** It needs a CLI release and still needs (a) or (b) underneath. Deferred (OP-F8).

**Other carriers** were rejected for the reasons in section 3.1: top-level messages, tickets and attachments.

### 3.4 Transport keys, ordering and consumption (astra 1, 2)

**Two keys.**
- The **logical key** is `(account, manifest_id, proposal_key)`, owned by the contract.
- The **transport key** is Senti's `idempotencyKey`, which is room-global and never compares the note (section 3.1). So the two must differ.
- The actor slot is in the derivation because one account's agents have distinct server replay slots ([#59-review] `REVIEW.md:17`).

Every client derives the transport key:

```
transport_key = "so1-" + hex(sha256(JCS({"schema": "sentilab-open-transport-key/1",
    "room": <room id>, "account": <own account id>, "actor_slot": "agent:<agentId>" | "human",
    "manifest_id": …, "logical_key": <proposal_key | request_key | "team">,
    "content_sha256": <proposal_sha256 | request hash | team hash>})))[0:48]
```

**How the key behaves.**
- It is 52 characters, well under the 180-character limit.
- **The same bytes retry identically:** the same key gives the same row, even after a sealed proposal is re-encrypted.
- **Changed bytes get a new transport key under the same logical key,** so intake sees both and records `idempotency_conflict`.
- **Intake recomputes the key** from the row (room, `actorUserId`, `actorKind`/`actorId`, and the parsed content) and rejects a mismatch with `transport_key_mismatch`.
- **Recipes always pass `--agent` and `--idempotency-key` explicitly** on the CLI, and `agentId` and `idempotencyKey` on MCP.

**Order.**
- Within a room, submissions are ordered by numeric `createdAt`, then the full action id. Across rooms, the room id is an explicit tiebreak. This cross-room order is a contract choice, not a total order the server provides ([#59-review] `REVIEW.md:23`).
- The target sequence orders nothing; it only identifies the root.
- "First submission" means the earliest under this order.

**Consumption.**
- The intake reads the `auditWindow` pages in `created_at,id` order ([api] `R:12926-12930`).
- It persists `nextCursor` only after every row of the page is durably processed.
- It dedupes by action id and revision, re-reading an overlap after a restart. Rejected replies keep their evidence.
- An outage or a crash never advances consumption. The intake re-reads from the last persisted cursor and dedupes.

### 3.5 Actor kinds and truthful recipes (astra 3)

**Quotas bind to `actorUserId` on every route. Admission and actor kind differ:**

| Who posts | Route | Senti stamps |
|---|---|---|
| An agent | `sl session reply --agent <id> --idempotency-key <key>` | agent `<id>` (admitted or granted) |
| An agent | `sl` MCP `session_reply {agentId, idempotencyKey, …}` | agent |
| An agent | Hosted MCP `sessions_reply {agentId, idempotencyKey, …}` | agent |
| An agent | REST `POST …/actions` with `metadata.agentId` (a granted agent) or a scoped agent token | agent |
| A person | REST `POST …/actions` with an account token and no agent claim | human |

**Each agent path needs its own admission or grant.** Signing in and joining the room proves none of them ([#59-review] `REVIEW.md:31-36`):
- the CLI resolves the authoring agent and runs the action inside `withAgentAdmission` ([cli] `src/commands/session.js:4309-4317`);
- the `sl` MCP refuses without a stored admission and an `agentId` ([cli] `src/mcp/session-stdio-server.js:928-943`);
- the hosted MCP authorizes the agent and writes `actor_kind="agent"` ([api] `src/routes/mcp.py:4595-4678`);
- REST takes the granted-agent branch only for a validated `metadata.agentId` or a scoped agent credential ([api] `S:878-951`).

**Rules for recipes.**
- Agent and person recipes are published separately and truthfully. Integration tests cover each of them and keep the admission and role differences visible.
- No recipe tells an agent to omit its identity, or to let the CLI fall back to its generic `cli-user` actor ([cli] `src/commands/session.js:1083, 2132-2135`), so as to appear human.
- Quotas bind to `actorUserId`. The restricted ledger keeps `actorKind` and `actorId` for provenance. Pages show "submitted as an agent" or "as a person", exactly as stamped.

### 3.6 "Anyone from anywhere": free authenticated accounts

**Who can take part.** Anyone, or any agent, with a free SentinelLayer account (GitHub or Google sign-in).
- The account joins the help room, or the overflow room warden opens near 90 people.
- Agents post under their person's account and take no place.
- No participant is billed (section 3.1, section 6).

**Why not anonymous.** Anonymous requests cannot satisfy account quotas, attributable receipts or removal (astra 5).

**The abuse trade-off.** Several accounts per person are possible. Sign-in, per-account quotas, team mapping, global and
seat caps, and warden's pause rule bound them (section 12).

### 3.7 Sealed private submissions and private checks (A10, adopted: room #56957)

**Why.** Every room member reads every reply (section 3.1). Without sealing, `private` would mean only "not on our public pages".

**The decision.** Private submissions **and** private routed checks are sealed. This is a design decision, not a runtime privacy acceptance.

**Format.**
- Standard `age` with an X25519 recipient, ASCII-armoured, bound to the signed manifest. The manifest pins the recipient and its key version.
- The note's first line is `sentilab-open-sealed/1 <manifest_id> <key_version>`, followed by the armour.
- Forge owns the pinned format, the adapters and the test vectors. Warden owns key custody and read access (OP-W2).

**Frozen rules.**
- **Size caps.** Plaintext at most 4,096 bytes; a sealed note at most 8,192 bytes.
- **Key version and rotation.** A new key means a new key version and a new manifest version. Old private keys stay in custody to decrypt earlier entries, and are never reused.
- **Decryptability.** A sealed note must decrypt, with the key version it names, to exactly one JSON object of an allowed schema. Anything else is rejected with `unsealable`.
- **No plaintext fallback.** A note that fails to decrypt is never re-read as plaintext. A plaintext reply that declares `private` is rejected with `private_requires_sealed`. `public` items may be plaintext.

**Retry identity and receipts.**
- The canonical **salted** plaintext defines the retry identity. Its `proposal_sha256` or `request_sha256` is the content hash in the transport key (section 3.4), so re-encrypting the same plaintext retries identically.
- The server-returned action row for the ciphertext is preserved as the transport receipt, by the participant and in the restricted journal (section 7.4).

**Private access.**
- Status, outcomes and receipts for private items need authorized access, or an unguessable per-request handle: the salted `proposal_sha256` or `request_sha256`.
- They are never exposed through an unauthenticated lookup by unsalted geometry hash, a public index, or a room pointer. Private read handles never appear in public pointers.

**Publication.** Public results need the participant's chosen publication consent under the versioned terms (section 5.6): evaluation, evidence and display only, with no training or lab-memory rights.

### 3.8 One contract, and adapters

**The contract.** `contracts/open-proposal-v1/`, pinned in `contracts/HASHES.txt`, holds:
- schemas for the manifest, proposal, check request, team, terms, receipt, status and results;
- reason codes;
- the canonicalization, transport-key and sealing rules;
- vectors.

| Operation | Agent (`sl` CLI, `sl` MCP, hosted MCP, REST with an agent claim) | Person (REST, no agent claim) | Artifact |
|---|---|---|---|
| Manifest | `GET …/manifest/<problem>/current.json` | same | `manifest.schema.json` |
| Legality and proxy | Offline local checker | same | `checker` (pinned `checker_sha256`) |
| Routed-wire check (sponsored) | Reply `sentilab-open-check-request/1` | same | `check-request.schema.json` |
| Submit | Reply with a sealed or public proposal | same | `proposal.schema.json`, `terms` |
| Team name (optional) | Reply `sentilab-open-team/1` | same | `team.schema.json` |
| Status | `GET /api/open/v1/status?…` with the salted handle; for public items, also a pointer via `read_history`, `sl session read` or `sessions_actions_list` | `GET` | `status.schema.json` |
| Results | `GET /api/open/v1/results?…` | same | `results.schema.json` |

**Adapters are deliverables (OP-F9).** `tools.json` alone registers no tools in any client (astra 3). Reference adapters
for Python and JS implement:
- the local checker;
- transport-key derivation;
- sealing;
- check, submit, status and results.

The skill documents how to wire them into common agent frameworks. A local MCP shim is optional.

**Which component provides which operation** ([#59-review] `REVIEW.md:38`). A table cell saying "fetch" is not a native tool:

| Operation | Native `sl` CLI, `sl` MCP and hosted MCP | OP-F9 adapters | Our operator CLI/MCP (SLAB-043 registry) |
|---|---|---|---|
| Offline legality and proxy | none | yes | `open.check` |
| Routed-wire check request | posts the reply only | composes, keys, seals and posts | `open.check` |
| Submit | posts the reply only | composes, keys, seals and posts | none |
| Status and results | room pointers, for public items only | the public GETs and private handles | `open.status`, `open.results` |
| Manifest | none | yes | `open.manifest` |

Until OP-F9 ships and passes T14, no client is claimed to provide these operations natively.

### 3.9 Identity rules

1. **Principal.** The principal is `actorUserId`. Labels, `agentId`, metadata and body fields never identify a participant.
2. **Recognised replies.** Only replies to a challenge root posted by our intake count. Our own rows are ignored.
3. **Missing id.** No `actorUserId` means `unattributable`.
4. **Revision 1 only.** Only revision 1 with `editedAt = null` is accepted. Otherwise the reply is rejected with `edited_before_ingest`.
5. **Restricted ledger.** Account ids, labels, Senti ids, ciphertext and plaintext originals stay in the restricted ledger (section 7.4).
6. **Public pseudonym** (astra 6): a keyed, per-challenge `participant_ref = HMAC-SHA256(k_challenge, account_id)`.
   - `k_challenge` is per manifest family and lives in Key Vault. Pseudonyms do not link across challenges, and nobody can compute them from an account id.
   - The participant learns its ref from its receipt. Auditors recompute it with the key.
7. **Team names** are voluntary and moderated.
   - The name matches `^[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}$`.
   - It shows only after warden approves it, and only as text.
8. **Our own entries.** The reserved principal `sentilab` is the frozen baseline.

### 3.10 Components and secrets

```
participant (person or agent)
  │ reply (sealed or public): sl CLI · sl MCP · hosted MCP · REST      ┌─ status, public results (GET)
  ▼                                                                    │
Senti challenge room(s): action rows (id, createdAt, actorUserId, actorKind)
  │ GET …/actions auditWindow, created_at,id order; cursor saved after durable processing
  ▼                                                                    │
intake (Container App job; contributor; outbound only; Key Vault: room credential, decryption key)
  │ ciphertext + plaintext + Senti ids → restricted ledger              │
  ▼                                                                    │
recorder + evaluator (signer; make_oracle; global journal suballocations)
  │ signed runs → public projection ──GET──► read-only Worker ──────────┘ public pages
  │            └► judge view (access-controlled)
  ▼
intake reads receipts ──► one pointer reply per submission
```

**Intake** (warden, provisional: rooms #56897 and #56899):
- a separate Container App job in the API's environment;
- a dedicated account with the **contributor** role (viewers cannot post receipts), least privilege otherwise;
- it reads replies and posts receipts as its own agent identity;
- no participant credentials, no inbound route;
- its secrets are in Key Vault;
- never the operator account our agents share.

**Recorder.** It holds the existing signer (`sentilab_core/README.md:77-91`), re-validates every row from raw plaintext,
and never talks to Senti.

## 4. The challenge manifest and the math

This section follows root's provisional contract ([review] `PROVISIONAL-CONTRACT.md`) and root's decisions (room #56902).
**Nothing here is frozen.** Every number is sourced, or labelled as a proposal.

### 4.1 The manifest

**Identity and versioning.**
- **Id:** `manifest_id = sha256(JCS(manifest))` (`sentilab_core/envelope.py:65-91`).
- **Published once and never edited**, at `/sentilab/open/manifest/<problem>/v<N>.json`.

**What it fixes** ([review] `PROVISIONAL-CONTRACT.md:5, 7`):
- **Geometry and package:** dimensions, per-die power, netlist direction and counting, the 45 mm frame and origin, rotations, edge margins, oriented halos and clearance, keepouts, the lattice, material, package and cooling assumptions, ambient.
- **Evaluation:** the statistic `M`; the thermal source, build, runtime and input identities; the grid; the router formulation, version, status acceptance and route-cost definition.
- **Names:** the reference identities and the published targets.
- **Claims:** the policy fields, the scenario screen and the evaluation bundle.
- **Process:** tie and failure rules, the window, threads, the sealing recipient, accepted terms versions, the exposure register, limits and references.

**Freezing (astra 4).**
- The policy values, scenario list and bundle are fixed in the signed manifest **before any candidate is scored**.
- They never change in response to outcomes.
- Missing evidence reads `UNKNOWN`, never an assumed pass ([review] `REVIEW.md:21`).

**Geometry rationale.** Thresholds need a stated rationale ([review] `PROVISIONAL-CONTRACT.md:5`).
- The 0.1 mm gap is TAP-2.5D Eqn. (10) ([#57] `sys_ascend910_45mm.cfg:35-36`).
- The 500 µm candidate lattice is a **declared finite engineering benchmark choice** (root, A11, room #56957). It is not CAD precision, a manufacturing tolerance, or an uncertainty estimate, and it is not reference-position uncertainty ([review] `REVIEW.md:5`). The config comment that it makes the sampled probes legal (`:32-34`) is history, not the rationale.
- Raw `R` stays continuous and reference-only. The lattice applies to candidates.

### 4.2 Reference identities and published targets

| Identity | What | Status |
|---|---|---|
| `R` = `ascend910-tap25d-fig6a/raw` | The raw reconstruction ([#57] `README.md:86-88`); continuous and reference-only (A11) | Off-lattice, so not legal on the fixture ([#57] `ascend910-tap25d-fig6a.json:246`). **The comparator; never an admissible entry** ([review] `REVIEW.md:7`). `content_sha256` `0046e17b…470e`, design hash `b9bfcd23…` ([#57b] `README.md:55`) |
| `ascend910-tap25d-fig6a-snap0p5` | The 0.5 mm engineering variant: plain nearest rounding, no repair ([#57b] `README.md:21`; `ascend910-tap25d-fig6a-snap0p5.json:37, 251`) | Legal. The engineering comparison and sensitivity baseline, separately admitted; never a paper match. `content_sha256` `e0c7ce9e…022a`, design hash `224f2ea0…c9e0` ([#57b] `README.md:56`) |
| `…/snapped-1mm` (field `snapped`) | The first legal experiment layout, kept unchanged ([#57b] `README.md:22`) | Legal; superseded as the baseline and kept as history. `content_sha256` `45b0f7e0…7703`, design hash `a2b5cac2…` ([#57b] `README.md:57`) |
| Published targets | 75.48 °C and 16,426 mm; 115.94 °C and 67,686 mm ([#57] `README.md:134-136`) | Separate fields, never overwritten ([review] `REVIEW.md:7`). A separately named paper-target diagnostic only |

**The comparator pair, by root's decision.**
- `(T_R, W_R)` is `R` scored by the **same fixed thermal model, package, powers, mesh, statistic and router** as candidates, stored with hashes.
- `W_R` = 16,417.5 mm (Ascend 910) and 67,688.4 mm (CPU-DRAM) ([#57] `README.md:57-60`).
- `T_R` is `UNKNOWN` until `R` has been run under the admitted evaluator. Raw is PR #56's next allocation ([#56] `gate_zero.py:41, 61-64`).

**Limits.** No reference result calibrates new layouts or validates the wire metric. Gate zero's own contract stays
separate ([review] `REVIEW.md:7`; `PROVISIONAL-CONTRACT.md:35`).

**CPU-DRAM identities** ([#57b] `README.md:58-60`): raw `6e541158…fce9` (design `93ee854b…`), `snap0p5` `ecfca7f4…8be9` (design `0f806acb…807f`, `micro150-tap25d-fig5a-snap0p5.json:45`), 1 mm `9fee13e0…6bbb` (design `c1d85d5d…`).

**Records are kept.**
- The raw and 1 mm histories are kept unchanged: they are byte-for-byte those at `063f659` ([#57b] `README.md:62`). The `snap0p5` variant never replaces or deletes the 1 mm record ([#59-review] `ROOT-DECISION-OPTIONS.md:10`).
- A snapped variant is a different experiment with its own identity, useful in its own right, but not a paper-faithful replacement ([#59-review] `REVIEW.md:49`).

**Gate-zero binding.**
- Gate zero, the accepted 8+4 allocation, uses the two raw 45 mm references only ([#57b] `README.md:24`).
- PR #56's head `6413a3c` is cited here for interfaces only. Admission binds the eventual corrected gate-zero record and reference set, not that head ([#59-review] `REVIEW.md:52`).

### 4.3 Legality

Each die has an integer-micrometre centre (origin: the frame's lower left) and a rotation of 0 or 90 degrees about its
centre. A turn swaps the footprint ([#57] `tap_oracle.py:296-312`). A layout is legal when:
1. **Catalogue.** One entry per die, in order; square dies don't turn (`:272-274, 327-332`).
2. **Frame** (`:333-335`).
3. **Lattice**, checked exactly on integers (`:367-373`).
4. **Margin**, including the halo (`:33-34, 355-365`).
5. **No halo overlap** (`:375-382`).
6. **Minimum body spacing** (`:384-397`).
7. **Keepouts.** None are declared; the field is empty.

**Halos.** TAP's uniform ring per die, from the link type ([#57] `tap_oracle.py:210-211`), rotation-invariant: 0.09 and
0.045 mm (Ascend 910); 0.18 and 0.135 mm (CPU-DRAM). `TapGeometry` is authoritative.

### 4.4 Temperature statistic `M` (root's decision; astra 4)

**Physics.** `G(x; package, materials, mesh) θ = p`, with:
- `θ = T − T_ambient`, in K;
- `G` in W/K;
- `p` in W.

The model assumes uniform power and steady state ([review] `REVIEW.md:9`).

**`T_M`.**
- `T_M` is the maximum native centre-map value over the real chiplets **enumerated explicitly in the manifest**: Ascend `Chiplet_0` to `Chiplet_5`; CPU-DRAM `Chiplet_0` to `Chiplet_7`.
- PR #56's record computes `chiplet_centre_mapping.max_C` ([#56] `slab049.py:1079-1080`) over units matched by the pattern `Chiplet_\d+` (`:1003, 1025`). OP-F4 replaces the pattern with the manifest list. A record whose chiplet set differs from the list gives `T_M = UNKNOWN`.
- The GRID_CENTER value is a mean of 1, 2 or 4 cells (`:242-251`). The manifest pins this mapping (`statistic.centre_mapping`). It is not a pointwise maximum, and is never called the true peak.

**Retained separately, never asserted equivalent:**
- `active_layer_grid_peak` with argmax (`:1077-1078`);
- the **literal TAP selector**, `historical_tap_stdout_selector.literal_on_stdout`, together with `on_steady_file_C` (`:1045-1049`; `gate_zero.py:174-183`). It is not restricted to real chiplets.

**Evaluator.** Grid 64 ([#56] `gate_zero.py:34`). HotSpot 6.0 `a7a3286e` with a gate-zero PASS on the evaluating host
(`:115-121, 247-280`; `ANALYSIS.md:304-305`).

**No method claim.** No "same method as the published reference" claim ([review] `REVIEW.md:9`).

### 4.5 Wire

**Routed wire, `W(x)`.** The MILP optimum in mm, proven by HiGHS with `mip_rel_gap = 0` within the time limit ([#57]
`tap_router.py:74-143`). Otherwise `W` is `UNKNOWN`.

**Counting.**
- The router treats each ordered pair `(i, j)` with `R[i][j] > 0` as a directed net of `R[i][j]` wires, so a link is routed once per direction (`:35, 81, 143`).
- The proxy counts each unordered pair once ([#57] `tap_oracle.py:400-408`).
- Both conventions are declared in the manifest ([review] `PROVISIONAL-CONTRACT.md:7`).

**Proxy.** `W_proxy` is a diagnostic only ([#57] `README.md:82-84`).

### 4.6 Comparisons

- `delta_T = T_M(c) − T_M(R)`
- `q_r = W(c) − (1 + r) W(R)`

Sources: [review] `PROVISIONAL-CONTRACT.md:11-15`. There is no mixing of `T` and `W` from different geometries, and no
substitution of published targets.

### 4.7 Bounds, observed sensitivities and the screen

**Bounded results.** These need the accepted bounds `u_T`, `u_q(r)` and `u_abs(c)`. With them:
- `delta_T_upper = estimated_delta_T + u_T`;
- `q_r_upper = estimated_q_r + u_q(r)`;
- `u_q(r) = b_c + (1 + r) b_R` ([review] `PROVISIONAL-CONTRACT.md:17-23`).

**None is accepted today, so all are `UNKNOWN`.** No bound defaults to zero.

**Observed sensitivities.** `mesh` (grid 32 against 64), `position` (R's cases) and `replay` are each reported
separately, or as `UNKNOWN`. Any sum is only "an empirical sensitivity score" ([review] `REVIEW.md:3-5`). There is no
summed `U`.

**The screen (root's choice).**
- The manifest lists a finite set `S` of required scenarios, each marked as applying to `c`, `R` or both.
- A claim **passes the listed sensitivity cases** when its predicate holds in every scenario on estimated values, for example `max_s [T_M(c; s) − T_M(R; s)] ≤ D`, plus the matching wire check.
- A missing or failed case makes the claim `INCOMPLETE` or `INCONCLUSIVE`.
- Scenarios are never chosen after outcomes ([review] `PROVISIONAL-CONTRACT.md:37`).

**Scenario pairs** (root, A12, room #56957):

| Scenario | Candidate | Comparator | Values compared |
|---|---|---|---|
| `nominal` | `c` at grid 64 | `R` at grid 64 | `T_M` and `W` |
| `mesh-32` | `c` at grid 32 | `R` at grid 32 | `T_M` |
| R-only position cases | nominal `c` at grid 64 | the exact perturbed `R` at grid 64 | `T_M` **and** routed `W` of the perturbed `R` |

The policy thresholds keep their frozen nominal basis: `B_W` stays defined on nominal `W_R` in every case.

**The raw-R position inventory (A12)** is a declared stress step, distinct from every existing call list:
- **Moves.** One die, one axis, ±500 µm. All other dies and every rotation are fixed.
- **Exclusions.** Moves that break continuous legality, meaning every fixture rule except the lattice ([#57b] `README.md:65`), are enumerated before any outcome.
- **Freezing.** Transforms and hashes are frozen.
- **Accounting.** It is counted, profiled and granted separately. It adds nothing to gate zero's 8+4 ([#57b] `README.md:24`) or to the 46-call `snap0p5` envelope ([#57b] `ENVELOPE-PLAN.md:18-22`).
- **No repairs**, no outcome-selected omissions, and no pass on an empty set. A missing required case leaves the claim `INCOMPLETE`.
- **Implementation** is a separate PR in the references lane (OP-F10). This design only specifies it.

### 4.8 Claim labels

**The policy fields** are `D`, `r`, `B_T`, `B_W` and `T_limit`. They are policy choices, not uncertainty ([review]
`PROVISIONAL-CONTRACT.md:35`; `REVIEW.md:13`).
- `B_W` names its basis, `W_R`.
- The draft brief (room #56873) proposed `D` = 0.5 K, `r` = 5%, `B_T` = 1 K, `B_W` = 2% of `W_R` and `T_limit` = 85 °C. These are proposals, not frozen values.

| Label | Predicate, after legality and numerical admission ([review] `PROVISIONAL-CONTRACT.md:25-33`) |
|---|---|
| Declared temperature target | `estimated_T_M(c) + u_abs(c) ≤ T_limit` |
| Strict-wire thermal tolerance | `q_0_upper ≤ 0` (that is, `W(c) ≤ W(R)`) and `delta_T_upper ≤ D` |
| r-relaxed-wire thermal tolerance | `q_r_upper ≤ 0` and `delta_T_upper ≤ D`. `r` is in the label. **1.05 is relaxed, never strict** |
| Strict thermal improvement | `q_0_upper ≤ 0` and `delta_T_upper ≤ −B_T` |
| Strict wire improvement | `q_0_upper ≤ −B_W` and `delta_T_upper ≤ 0` |
| Wire improvement with allowed thermal degradation | `q_0_upper ≤ −B_W` and `delta_T_upper ≤ D`. Relaxed label if `D > 0` |
| Robust dominance over R | `q_0_upper ≤ 0` and `delta_T_upper ≤ 0`, with at least one strict improvement under the published tie and margin rule |

**How each label is shown.**
- With its evidence mode: "bounded" (none today), or "passes the listed sensitivity cases" (evaluated on estimated values in every scenario).
- Unlabelled and `INCOMPLETE` results still show their nominal values.

**Rules from the review.**
- Non-inferiority is not equality.
- A two-sided reproduction claim is a different predicate.
- `T_limit` is a chosen scenario target, not a hardware or safety limit. A centre-mapped result below it says nothing about every die, grid point or junction ([review] `REVIEW.md:11, 13`).

### 4.9 Tradeoff budgets and the Pareto view

**Budgets.** For `r ∈ {0.10, 0.25, 0.50, 1.00}` (a manifest field), report the best observed `T_M` under
`W(c) ≤ (1 + r) W(R)` ([review] `PROVISIONAL-CONTRACT.md:39`).
- Strict, relaxed and nondominated results are reported separately.
- These are wire-budget scenarios, not weights or participant tracks.
- The budgets are nested, so they are not independent wins and not evidence of global optimality.
- More wire without a benefit is not a tradeoff ([review] `REVIEW.md:11`).

**Pareto view.** The nondominated set, with no claim.

**Ties and records.** Ties sort by `T_M`, then the geometry hash (`docs/sentilab/SLAB-041-ADMISSION-REVIEW-2026-10-31.md:11`).
Every result is retained.

### 4.10 Predicate fixtures, scientific diagnostics and claim suppression (A13, room #56957)

The review separates two things that revision 1 mixed ([#59-review] `REVIEW.md:48`).

**Pure predicate fixtures** test the label code, not the science.
- They are synthetic numeric inputs: `T_M`, `W` and per-scenario values for `c` and `R`.
- Each outcome follows from the predicate's algebra.
- There are positive and negative cases for every label in section 4.8, including `INCOMPLETE` and `UNKNOWN`.
- `R` against itself cancels **only** here, with identical measurements. Fresh replays and R-position screens need not pass by identity.
- They are part of T13 and must always pass.

**Scientific diagnostics** apply the frozen predicates to published layouts under our reconstructed model. Each expectation is a **hypothesis about a specific predicate**, not a forced label:

| Diagnostic layout | Hypothesis | Basis |
|---|---|---|
| `R` against itself under the screen | Passes strict-wire thermal tolerance only if every R-only position case moves `T_M` by no more than `D` | Section 4.7 |
| Ascend TAP-2.5D, Fig. 6(c) | r-relaxed (r = 0.05) thermal tolerance; not strict-wire; not strict thermal improvement | Our routed wire is 16,613.5 mm, 1.2% above `W_R` ([#57] `README.md:59, 75`). Paper temperatures 75.47 and 75.48 °C ([#56] `gate_zero.py:65-66`) |
| Ascend Compact-2.5D, Fig. 6(b) | Within the 0.50 and 1.00 budgets only | Routed +45% ([#57] `README.md:74`) |
| CPU-DRAM TAP-2.5D, Fig. 5(c) and 5(d) | Outside every budget up to 1.00; no label | Routed +219% and +105% ([#57] `README.md:77-78`) |

**What decides whether a claim is shown** (A13):
- **Unexpected diagnostic.** Valid candidate claims may still appear beside it. The mismatch and its raw values are retained and published as a diagnostic.
- **Failed requirement.** Any of these suppresses the affected claims:
  - a required gate-zero check;
  - a source, input or statistic binding;
  - predicate correctness (a pure fixture);
  - a required scenario.
- **No tuning.** Thresholds, scenarios, the evaluator and the reference are never tuned toward expected paper classifications.

### 4.11 Draft manifest v0 (Ascend 910)

This draft has provisional fields and is not a signed manifest.

```json
{
  "schema": "sentilab-open-manifest/1", "version": 0, "status": "draft: provisional fields; not a signed manifest",
  "problem": "ascend910",
  "fixture": {"id": "ascend910-45mm", "config": "sundai_tap/configs/sys_ascend910_45mm.cfg",
              "config_sha256": "4a922560510ba0ab66d04030f137f80262891e7ac7afac3025a57f539e885a8c",
              "frame_um": 45000, "origin": "frame lower-left", "ambient_c": 45, "link_type": "nppl",
              "package": {"hotspot_config_sha256": "<sundai_tap/util/hotspot.config>",
                          "assumptions": "steady state, uniform power per die"}},
  "dies": [
    {"die": 0, "unit": "Chiplet_0", "name": "compute", "w_um": 14500, "h_um": 31400, "power_w": 256, "halo_um": 90, "rot_deg": [0, 90]},
    {"die": 1, "unit": "Chiplet_1", "name": "io",      "w_um": 10500, "h_um": 16000, "power_w": 14,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 2, "unit": "Chiplet_2", "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 3, "unit": "Chiplet_3", "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 4, "unit": "Chiplet_4", "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]},
    {"die": 5, "unit": "Chiplet_5", "name": "hbm",     "w_um": 7750,  "h_um": 11870, "power_w": 20,  "halo_um": 45, "rot_deg": [0, 90]}],
  "netlist": {"matrix": [[0,200,256,256,256,256],[200,0,0,0,0,0],[256,0,0,0,0,0],
                         [256,0,0,0,0,0],[256,0,0,0,0,0],[256,0,0,0,0,0]],
              "counting": {"routed": "each ordered pair with R[i][j]>0 is a directed net of R[i][j] wires",
                           "proxy": "each unordered pair once"}},
  "legality": {"units": "um", "anchor": "die-centre", "lattice_um": 500, "lattice_rationale": "declared finite engineering benchmark choice (A11)",
               "margin_um": 500, "min_die_gap_um": 100, "min_die_gap_rationale": "TAP-2.5D Eqn. (10)",
               "halo": "uniform ring per die; rotation-invariant", "keepouts": [], "rotation": "per_die_90"},
  "references": {"file_sha256": "<reference file bytes>",
    "comparator": {"id": "ascend910-tap25d-fig6a/raw", "continuous": true, "legal_on_fixture": false,
                   "content_sha256": "0046e17b3e33feef14e570eb6a2026e17c3eea5c232160a052be62c2ae8e470e",
                   "T_R": "UNKNOWN", "T_R_measurement_id": "<receipt>", "W_R_mm": 16417.5},
    "engineering_variants": [{"id": "ascend910-tap25d-fig6a-snap0p5", "role": "engineering baseline",
                              "content_sha256": "e0c7ce9eb641ee6aea7d2015e5bc0fc5e3f38f1759c2c2252f14ad5104af022a",
                              "design_hash": "224f2ea088fc50f5eb209a44f1a82fa3704c06037456dc6976657df105c6c9e0"},
                             {"id": "ascend910-tap25d-fig6a/snapped-1mm", "role": "history; superseded as baseline",
                              "content_sha256": "45b0f7e05b82a5eedad1679d751f5684e98ef35c936db54aeea9b475ae397703"}],
    "published_targets": {"source": "Ma et al., DATE 2021, Fig. 6(a)", "T_c": 75.48, "W_mm": 16426,
                          "use": "paper-target diagnostic only"}},
  "statistic": {"id": "M", "definition": "max native GRID_CENTER value over the enumerated real chiplets",
                "real_chiplets": ["Chiplet_0", "Chiplet_1", "Chiplet_2", "Chiplet_3", "Chiplet_4", "Chiplet_5"],
                "centre_mapping": "GRID_CENTER: mean of 1, 2 or 4 central cells (pinned)",
                "record_field": "chiplet_centre_mapping.max_C", "grid": 64,
                "retained_separately": ["active_layer_grid_peak", "historical_tap_stdout_selector.literal_on_stdout"],
                "evaluator": {"kind": "hotspot6", "upstream": "a7a3286e368867c26381e0a23e36b3e273bdeda9",
                              "binary_sha256": "<host binary>", "gate_zero_record_sha256": "<record>",
                              "build": "<image digest>", "runtime": "<…>"},
                "numerical_admission": "UNKNOWN"},
  "wire": {"metric": "routed", "router_sha256": "<tap_router.py bytes>", "solver": "HiGHS MILP, mip_rel_gap 0",
           "status_acceptance": "proven optimum within the solver limit", "proxy": "diagnostic only"},
  "policy": {"status": "provisional; policy choices, not uncertainty; fixed before any candidate is scored",
             "D_K": null, "r": null, "B_T_K": null, "B_W_mm": null, "B_W_basis": "W_R_mm", "T_limit_C": null,
             "proposed_in_draft": {"D_K": 0.5, "r": 0.05, "B_T_K": 1.0, "B_W_fraction": 0.02, "T_limit_C": 85},
             "tradeoff_budgets_r": [0.10, 0.25, 0.50, 1.00]},
  "bounds": {"u_T": "UNKNOWN", "u_q": "UNKNOWN", "u_abs": "UNKNOWN"},
  "claims": {"display_order": ["declared temperature target", "strict-wire thermal tolerance",
             "r-relaxed-wire thermal tolerance", "strict thermal improvement", "strict wire improvement",
             "wire improvement with allowed thermal degradation", "robust dominance over R"],
             "suppressed_by": ["failed gate zero", "failed binding", "failed predicate fixture", "failed required scenario"]},
  "screen": {"claim": "passes the listed sensitivity cases", "missing": "INCOMPLETE", "failed": "INCONCLUSIVE",
             "scenarios": [{"id": "nominal", "applies_to": "both", "grid": 64},
                           {"id": "mesh-32", "applies_to": "both", "grid": 32},
                           {"id": "position-<die>-<axis>-<sign>", "applies_to": "R",
                            "cases": "raw-R inventory (A12): separately counted, profiled and granted"}]},
  "evaluation_bundle": {"status": "provisional",
                        "per_entry": [{"phase": "evaluate", "grid": 64, "suballocation": "native.evaluate"},
                                      {"phase": "replay", "grid": 64, "suballocation": "native.replay"},
                                      {"phase": "mesh", "grid": 32, "suballocation": "native.mesh"},
                                      {"phase": "route", "suballocation": "routing"}],
                        "per_manifest": "R's scenario cases", "lifecycle_suballocation": "lifecycle",
                        "intake_suballocation": "intake",
                        "ceilings_cpu_s": "<warden>"},
  "checks": {"solver_time_limit_s": "<warden; provisional 2; elapsed HiGHS time, not CPU>",
             "check_wall_s": "<warden; provisional 5; from worker start, queue excluded>",
             "cleanup_headroom_s": "<warden>", "cpu_reserve_s": "<warden; reserved before runtime>",
             "status_access": "salted request_sha256 handle or authorized access", "suballocation": "checks"},
  "ties": "ascending T_M, then geometry hash", "failures": "retained; no automatic retry",
  "limits": {"status": "provisional (warden, room #56897)", "eval_per_account_hour": 3, "eval_per_account_day": 12,
             "eval_room_hour": 20, "eval_room_day": 120, "queue_max": 30, "warden_call_policy_hour": 40,
             "code_cpu_s_per_hour_per_root": 600, "code_default_solve_reserve_cpu_s": 15,
             "check_per_account_hour": 30, "check_room_hour": 600},
  "terms": {"accepted_versions": ["<sentilab-open-terms/1@sha256>"], "retention": "<root, A3>"},
  "intake": {"order": ["createdAt", "action_id", "room_id"],
             "cursor": "auditWindow.nextCursor, saved after durable processing", "revision": "1 only"},
  "transport_key": {"schema": "sentilab-open-transport-key/1", "prefix": "so1-", "hex_chars": 48,
                    "fields": ["room", "account", "actor_slot", "manifest_id", "logical_key", "content_sha256"]},
  "disclosure": {"at_opening": ["reference geometry", "frozen SentiLab baseline"],
                 "entries": "public only by explicit choice; private sealed; revealed only by a logged publish choice"},
  "pseudonym": {"rule": "HMAC-SHA256(k_challenge, account_id)", "scope": "per challenge"},
  "exposure": {"sources": ["TAP-2.5D paper PDF b209f51a…", "Fig. 6(a)-(c)", "Fig. 5(a)-(d)",
                           "sys_ascend910_45mm.cfg", "sys_micro150_45mm.cfg"],
               "note": "exposed families: mark when building any future held-out split"},
  "sealing": {"format": "age X25519, ASCII armour", "recipient": "<intake public key>", "key_version": "<n>",
              "applies_to": ["private proposals", "private routed checks"], "plaintext_max_bytes": 4096,
              "sealed_note_max_bytes": 8192, "plaintext_fallback": false,
              "rotation": "new key version and new manifest version; old keys kept in custody, never reused"},
  "example": {"label": "invented numbers", "inputs": "<chosen at freeze>"},
  "window": {"opens_at": null, "closes_at": null},
  "refs": {"grant": "<warden grant>", "claim_rules": "<astra record>", "checker_sha256": "<…>"},
  "submission": {"threads": "<room and root per room, rendered at publication>"}
}
```

**The CPU-DRAM manifest** has the same shape (`sys_micro150_45mm.cfg:11-40`; `micro150-tap25d-fig5a.json`). Its real
chiplets are `Chiplet_0` to `Chiplet_7`. `W_R_mm` is 67,688.4, and the published targets are 115.94 °C and 67,686 mm.

## 5. The proposal

### 5.1 Objects

```json
{"schema": "sentilab-open-proposal/1", "manifest_id": "<64 hex>", "terms": "<accepted terms version>",
 "proposal_key": "team-a-07", "parent": null, "visibility": "private", "salt": "<32 hex>",
 "units": "um", "anchor": "die-centre",
 "dies": [{"die": 0, "x_um": 17000, "y_um": 23000, "rot_deg": 90}, …],
 "geometry_sha256": "<64 hex>",
 "client": {"name": "my-agent", "version": "1.2.0"}}
```

| Field | Rule |
|---|---|
| `manifest_id` | An open manifest that matches the targeted root |
| `terms` | Required: one of the manifest's accepted terms versions (section 5.6) |
| `proposal_key` | `^[a-z0-9][a-z0-9_-]{0,63}$` (`sentilab_core/capabilities.py:160`). The logical key, scoped to the account and manifest |
| `parent` | `null`, or one of the account's own earlier geometry hashes |
| `visibility` | Required: `public` or `private`. This is the explicit publication choice (root). `private` must be sealed |
| `salt` | 32 random hex characters, so the proposal hash cannot be guessed |
| `units`, `anchor` | The constants `"um"` and `"die-centre"` |
| `dies` | One per die, in order. Integer `x_um` and `y_um` in `[0, frame_um]`. `rot_deg` from the die's allowed set |
| `geometry_sha256` | Recomputed by the server and must match |
| `client` | Optional. `^[A-Za-z0-9._-]{1,32}$`. Private and never rendered |

**What the schema forbids.** `additionalProperties: false` everywhere. No free text apart from the moderated team name.
No binary, host, grid, timeout, statistic, reference, budget or grant fields.

**Other objects:**
- the check request (`sentilab-open-check-request/1`): `manifest_id`, `request_key`, `visibility`, `salt`, `units`, `anchor`, `dies`, `geometry_sha256`. Its salted `request_sha256` is the private status handle (section 3.7);
- the team object (section 3.9).

### 5.2 Canonical form and hashes

- **JCS** (`sentilab_core/envelope.py:65-91`). Cross-language vectors: `sentilab_core/conformance.py:19-37`; browser copy: `web/public/sentilab/canonical.mjs:1-10`.
- **`geometry_sha256`** = `sha256(JCS({"schema":"sentilab-open-geometry/1","problem","fixture_config_sha256","units","anchor","dies":[…]}))`. It excludes actor, time, key, salt, terms and client (`docs/sentilab/SLAB-041-ADMISSION-REVIEW-2026-10-31.md:29-31`).
- **`proposal_sha256`** = `sha256(JCS(proposal))`. It is the content hash in the transport key, and the status key.
- **`design_hash`** is the oracle's `Design.hash` ([#57] `sundai_controller/controller.py:151-164`; bound at `sundai_hotspot/tap_oracle.py:782, 843`).
- **`body_sha256`** is the hash of the exact note bytes.

### 5.3 Limits

- **Size.** Plaintext at most 4,096 bytes; a sealed note at most 8,192 bytes.
- **What counts as an attempt.** A note starting with `{`, ```` ``` ```` or `sentilab-open-sealed/1`. Anything else is chat.
- **JSON.** Strict UTF-8, no duplicate keys, no non-finite numbers, depth at most 4, at most 32 dies, integer geometry.

### 5.4 Legality before any evaluation

**The checks.** No solver and no reservation; every violation is reported:
1. transport (thread, revision, size, sealing, transport key);
2. JSON and schema;
3. manifest and terms;
4. geometry hash;
5. catalogue and rotation;
6. the integer lattice;
7. `TapGeometry.layout_violations` ([#57] `tap_oracle.py:296-312, 320-398`).

**What a rejection reports.** Codes, die indices and amounts only (`[#57] tap_oracle.py:127-134`).

**Who re-checks.** The recorder re-runs everything (`sundai_hotspot/tap_oracle.py:779-780`).

### 5.5 Duplicates and equivalent layouts

- **The same geometry in the same manifest** points to the first complete evaluation under the section 3.4 order, with no new charge (`SLAB-041-ADMISSION-REVIEW-2026-10-31.md:33`).
- **Equivalent layouts** are labelled, never merged (`:29-31`).
- **Public views** label matches only against public entries, references and the baseline. Private matches appear only to judges.

### 5.6 Submission terms (astra 6)

**What the terms cover.**
- A proposal names an accepted `terms` version. The terms text is published at a stable URL, and its SHA-256 is in the version id.
- It covers evaluation, retention of evidence, and display **only if** `visibility` is `public`.
- It grants **no** training, lab-memory or study use.

**What else the terms state** ([#59-review] `REVIEW.md:72`): the moderation visibility semantics (section 12) and the retention period.

**Changing the terms.** A change makes a new version. The manifest lists the accepted versions.

**The reveal rule, frozen before ingestion** ([#59-review] `REVIEW.md:66`; `ROOT-DECISION-OPTIONS.md:12`).
- A private entry's signed run is never served publicly. It is not merely hidden behind a picture while public rows exist.
- It becomes public only through the participant's explicit, logged choice: a `sentilab-open-publish/1` reply naming the `proposal_sha256`, from the same account, under accepted terms.
- Its full signed run is then released. We never publish a private entry on our own.

**Records.**
- The originals of every proposal are retained, whatever their visibility.
- Every visibility decision is logged in the restricted ledger with actor, time and reason: the participant's choice, a moderation hide or restore, or a later publication.
- Private proposals are preserved until their chosen publication path.

## 6. Checks before submission (astra 5)

**Two tiers.** Anonymous remote requests cannot satisfy account quotas, so there are exactly two:

### 6.1 Offline local checker (anyone, no account)

**What it is.** The published checker, pinned by `checker_sha256` in the manifest. It holds the validator, the proxy and
the router.

**How to use it.** It runs on the participant's own hardware at their own cost. It gives the same answers as the
intake, proven by contract vectors T12.

**Licences.** The published checker keeps its dependencies' notices pinned: TAP-2.5D's Apache-2.0 change notice ([#57b] `tap_router.py:1-15`) and the entries in `THIRD_PARTY_NOTICES.md` ([#59-review] `REVIEW.md:72`).

### 6.2 Authenticated, sponsored remote routed-wire check (account)

**Request.** A `sentilab-open-check-request/1` reply to the challenge root, with a derived transport key. A private check must be sealed (section 3.7).
The intake checks legality, then routes a legal layout.

**Charging.** Each check is charged to the **`checks` suballocation** of the global journal (section 8.4), reserved
before launch and settled on every exit.

**Limits** (warden, provisional, room #56897):
- 30 an hour per account and 600 an hour per room;
- a check that doesn't finish counts against the account;
- warden confirms after OP-F7 has measured the cost.

**Four separate limits** (astra, room #56957). None stands in for another:

| Limit | What it bounds | Value | Owner |
|---|---|---|---|
| Solver elapsed limit, `solver_time_limit_s` | HiGHS's own `time_limit` inside `scipy.optimize.milp`, from after model construction to the end of the solve. HiGHS picks its own thread count, so this is **not** a CPU cap ([#57b] `tap_router.py:10-15, 116-117, 181-183`) | Provisionally 2 s | warden |
| Whole-check wall deadline, `check_wall_s` | Elapsed time from the clock start to the end of serialization. The process group is killed at the deadline | Provisionally **5 s** (warden, room #56952; accepted by root, room #56957) | warden |
| CPU reserve, enforcement and debit | Process-tree CPU: reserved before runtime, enforced while running, and debited at settlement in the `checks` suballocation | `<warden>` | warden |
| Request quotas | 30 checks an hour per account, 600 per room | Provisional (room #56897) | warden |

**The whole-check wall, defined.**
- **Clock start.** When a worker begins the check, after it leaves the queue. Queue time is excluded from the 5 s and reported separately.
- **Inside the 5 s:** worker startup, parsing and unsealing, legality, model construction, the solve, and result serialization.
  - Model construction is the Python loops over `C·K·C·K·N` variables ([#57b] `tap_router.py:127-180`).
  - That is 6·4·6·4·10 = 5,760 variables for Ascend 910, and 8·4·8·4·16 = 16,384 for CPU-DRAM.
- **Outside it:** cleanup, meaning reaping the process group and archiving. Cleanup has its own separate headroom, and is still charged.
- **CPU is reserved before runtime.** The reservation is made before the worker starts, and settled after cleanup with measured process-tree CPU.
- **Not a CPU grant.** The 5 s wall is **not** a 5 CPU-s grant. Hitting the solver limit, the wall or the CPU reserve counts as an unfinished check against the account (room #56897). Exceeding a request quota is refused with `rate_limited`.

**Results.**
- `GET /api/open/v1/check-status?h=<request_sha256>` returns `W(c)`, the router status, and nominal `q_r` for `r = 0`, each tolerance and each budget, labelled "routed wire only, no thermal solve, nominal, not a score". It carries no geometry.
- `request_sha256` is the hash of the canonical salted request, so only its author can look it up. There is no lookup by unsalted geometry hash, and checks are never indexed publicly (A10).
- A public check gets one best-effort pointer. A private check gets none.

**What "free" means** (root, room #56902; [review] `REVIEW.md:17`; `PROVISIONAL-CONTRACT.md:41`). The check costs
participants nothing **only** while SentiLab's sponsorship and the measured, capped MILP cost support it. The limits,
funding, caps, queue behaviour and observed latency are published. It is not unlimited, and not instant.

## 7. States, idempotency and receipts

### 7.1 States

```
reply ─► rejected                                     (terminal; codes; no quota charge)
      └► queued ─► evaluating ─► evaluated ─► replaying ─► reproduced ─► (optional) cross_checked
           │ ▲          │            │             └─────► not_reproduced
           ▼ │          ▼            ▼
          held        failed       failed             (charged; no automatic retry)
           └► cancelled · expired                      (before any reservation; no quota charge)
hidden: a public-view flag from moderation, with reason; nothing is deleted
```

| State | Meaning | Quota charge | Ledger lifecycle |
|---|---|---|---|
| rejected | Failed a transport, schema, terms, manifest, sealing, key, hash, legality or policy check | No | `rejected_schema` or `rejected_constraints` (`web/public/sentilab/lab-model.mjs:218-225`; `sentilab_core/dataset.py:22`) |
| queued, held | Waiting, or on moderation hold | No | New |
| evaluating | Native calls reserved and running | Yes | `simulation_pending` |
| evaluated | The evaluate call is settled | Yes | `evaluated` |
| failed | `timeout`, `oracle_error`, `stopped`, `grant_expired` or `interrupted` | Yes | `failed_run` |
| replaying | The fresh-process replay is reserved or running | Yes | `reproduction_pending` |
| reproduced | **"Reproduced under `<evaluator identity>`"**: the replay on the pinned build agreed (root) | Yes | `reproduced`, `verify.add` tier `replayed` |
| not_reproduced | The replay disagreed or failed | Yes | `reproduction_failed` |
| cross_checked | A second host or build agreed. Separately qualified; never implied by "reproduced" | Yes | `verify.add` with a new same-physics `cross_build` tier, or `cross_arch` for another architecture (section 8.5) |
| cancelled, expired | Before any reservation | No | `cancelled`; new `expired` |

**Quota charge versus sponsor use.** The column says whether the entry counts against participant quotas. Parsing, unsealing, queue handling, cache lookups and rejected work still use sponsor CPU. That use is recorded under the `intake` suballocation (section 8.4), and is never described as zero ([#59-review] `REVIEW.md:59`; room #56957).

**The contract's four states.**

| Contract state | States here |
|---|---|
| rejected | rejected |
| queued | queued, held, evaluating |
| evaluated | evaluated or failed |
| independently verified | reproduced under that evaluator; `cross_checked` is separately qualified |

**Claim states** (`INCOMPLETE`, `INCONCLUSIVE`, `UNKNOWN`) belong to labels. No board outcome is ever written
(`sentilab_core/ledger.py:340-342`).

### 7.2 Reason codes

No submitted text appears in a code (`sentilab_core/transport.py:8-11`; `sentilab_core/research.py:26-27`).

| Group | Codes |
|---|---|
| Transport | `oversize`, `not_utf8`, `edited_before_ingest`, `unattributable`, `private_requires_sealed`, `unsealable`, `transport_key_mismatch` |
| Envelope | `malformed_json`, `duplicate_key`, `nonfinite_number`, `too_deep`, `unknown_field`, `schema_invalid` |
| Manifest and terms | `unknown_manifest`, `manifest_mismatch`, `manifest_closed`, `not_open_yet`, `terms_not_accepted` |
| Geometry | `die_count`, `die_order`, `out_of_frame`, `rotation_not_allowed`, `lattice`, `margin`, `halo_overlap`, `min_spacing`, `keepout`, `geometry_hash_mismatch` |
| Revision | `idempotency_conflict`, `unknown_parent`, `unknown_proposal` |
| Policy | `participant_suspended`, `participant_paused`, `participant_removed`, `rate_limited`, `queue_full`, `budget_exhausted` |
| Evaluation | `timeout`, `stopped`, `oracle_error`, `grant_expired`, `interrupted`, `binding_mismatch`, `router_timeout`, `check_unfinished` |
| Reproduction | `reproduction_mismatch`, `fresh_process_required`, `reproduction_failed` |

### 7.3 Idempotency and immutable revisions

**Keys.** The logical key `(account, manifest_id, proposal_key)` is separate from the transport key (section 3.4).

**Repeats.**
- Same logical key and same content: the same transport key, the same Senti row and the same receipt.
- Same logical key and different content: a new transport key and a new row, so intake records `idempotency_conflict`. The earliest row under the section 3.4 order wins (`sentilab_core/proposals.py:268-271`).

**Immutability.** Revisions never change, and later edits ([api] `S:6082`) are ignored. The restricted ledger keeps
every original and revision.

**Ledger.** Event ids derive from `(manifest, account, proposal_key, phase)` (`sentilab_core/ledger.py:387-398`).

### 7.4 Ledgers, receipts and who signs what

**Senti.** Senti signs nothing for us. Its guarantee is `actorUserId` on its own row.

**The restricted ledger** (private) holds:
- the intake journal: hash-chained and unsigned, with action id, `createdAt`, target, `actorUserId`, `actorKind`, actor id, transport key, revision, ciphertext and plaintext, `body_sha256`, and the server-returned action row as the ciphertext receipt (A10);
- the processed cursor;
- visibility decisions;
- every signed run.

Only astra, warden and judges read it.

**Signed runs.**
- One per proposal, `open-<manifest 8 hex>-<proposal_sha256 16 hex>` (`sentilab_core/envelope.py:26`).
- Ed25519-signed (`sentilab_core/envelope.py:233-247`), verifiable against the pins (`web/public/trust-pins.json`; `sentilab_core/README.md:86-91`).

**The public projection** serves, unchanged:
- runs of `public` entries under accepted terms;
- reference rows;
- the frozen baseline.

Private entries appear only as counts.

**What the receipt binds:**
- the keyed `participant_ref` and `source_ref = sha256("sentilab-open-source/1:" + action_id)`;
- `actor_kind`;
- `body_sha256`, `proposal_sha256`, `geometry_sha256` and `design_hash`;
- `manifest_id`, `terms`, `visibility`, `proposal_key`, `revision_index` and `parent`;
- the state and codes;
- `values.geometry` (`sentilab_core/conductor.py:383-386`).

**Measurement rows** carry:
- the binding, `T_M`, `W(c)`, process id, charged and measured CPU per suballocation, input hashes (`sentilab_core/conductor.py:331-342`);
- the retained observables.

**The receipt hash** is the envelope hash (`sentilab_core/envelope.py:244`).

### 7.5 What the intake posts in the room

**Roots.** One per open manifest per room, posted after readiness, except the readiness root. Each holds the fixed text,
manifest id, sealing recipient, terms and links.

**Pointers, for public items only.** Private items get no room pointer, and no private read handle appears in one (A10). A public submission gets at most two.
- Each is built from signed fields only.
- Each targets the submission ([api] `alembic/versions/057_session_message_action_targets.py:1-8`).
- Under load, queued pointers are dropped first, then terminal pointers are batched, staying under [api] `S:232`.

## 8. The evaluation boundary

### 8.1 Admitted manifests only

A manifest is admitted in a host-side registry (`sentilab_core/proposals.py:1-5`) only with all of these:
1. **Gate zero.** It passes for the exact binary on the evaluating host, so `make_oracle(evaluator, "open")` returns ([#56] `evaluators.py:90-104`; add `"open"` to `PURPOSES` at line 28).
2. **References.** PR #57 merged and the reference bytes pinned.
3. **Source.** The deployed hashes equal the reviewed ones (`sundai_hotspot/tap_oracle.py:663-684`; `tap_oracle_worker.py:218-240`).
4. **Operations.** Warden's exact operational admission and grant.
5. **Claims.** Astra's signed claim manifest, with every policy value fixed before any candidate is scored.

Otherwise intake answers `manifest_closed` or `not_open_yet`.

### 8.2 What a submission can and cannot influence

**Can:** the manifest (by id), centres and rotations (after legality), its key, parent, visibility, salt and terms
version.

**Cannot:** the shell, argv, binary, host, grid, timeout, flags, environment, budget, grant, signer, statistic, wire
definition, scenarios, comparator, reference geometry or reproduction.
- The request is built by the server (`sundai_hotspot/tap_oracle.py:781-808`).
- The native solver runs a fixed argv and environment (`sundai_hotspot/tap_oracle_worker.py:347-348`; `sundai_hotspot/tap_oracle.py:614-618`).
- This is SLAB-052's rule (`docs/sentilab/evidence/SLAB-052/HARNESS.md:48-50`).

### 8.3 Quotas and queue (warden, provisional: room #56897)

Root keeps these prospective until measured and bound (room #56902).

| Quota | Value |
|---|---|
| Evaluations per account | 3 an hour, 12 a day |
| Evaluations per room | 20 an hour, 120 a day |
| CPU ceiling (code) | The code caps charged CPU at 600 CPU-s an hour per root, with a default 15 CPU-s reservation per solve (`sentilab_core/budget.py:18-40`). Forty calls an hour is the arithmetic 600/15, not a separate code maximum (room #56957) |
| Call backstop (warden's policy) | 40 native calls an hour. It is **warden's own policy**, to be implemented and tested, not an existing code limit |
| Queue | At most 30 waiting. Beyond that, `queue_full` with a retry-after time and no reservation |
| Pause | Three hidden entries in a day pause an account's evaluations for 24 hours |

**Quotas are not throughput** (astra 5). "20 proposals an hour" is a quota, not a proof of throughput under 600 charged
CPU-s an hour:
- at three native calls per entry and a 15 CPU-s ceiling, the code allows at most 13 entries an hour;
- at 60 CPU-s ceilings, it allows 3.

Throughput is shown only by measured HotSpot 6.0 costs and test L3. Whether quotas count entries or native calls is open
question W8.

### 8.4 One retained global journal; reserve before launch, settle on every exit

**One journal** (astra 5; warden's "same ledger as SLAB-052"). Revision 1 called the open budget separate, while warden named one ledger. Both hold as **separate admitted suballocations under one accounting journal and one global ceiling**. The live loop's and SLAB-052's existing charges stay exactly as recorded ([#59-review] `REVIEW.md:60`). Every charge lands in that one retained, append-only journal, under distinct suballocations:

| Suballocation | What it charges |
|---|---|
| `native.evaluate` | Each grid-64 evaluate call |
| `native.replay` | Each grid-64 replay |
| `native.mesh` | Each grid-32 call |
| `native.reference` | R's scenario cases, once per manifest |
| `routing` | Actual MILP use for entries |
| `lifecycle` | Worker start, reap and archive, measured |
| `checks` | Sponsored routed checks: solve plus lifecycle |
| `intake` | Parsing, unsealing, queue handling, cache lookups and rejected work: sponsor use, never charged to participant quotas |

**Rules.**
- Per-account and room quotas, and the backstop, draw on these.
- Nothing is netted, refunded or moved between suballocations.
- Measured overruns stay charged.
- Settlement records measured CPU, wall time, peak memory and the concurrency slot used ([#59-review] `REVIEW.md:60`).
- Participant billing is always zero. Sponsor resource use is always recorded. The two are reported separately ([#59-review] `REVIEW.md:59`).
- **The four limits stay separate** for native calls too: the solver's elapsed timeout, the outer wall deadline, the CPU reservation with its enforcement and debit, and the request and call quotas.

**Steps** (the PR #56 review, item 2; `sentilab_core/conductor.py:306-320`):
1. **Before spawning.** A durable reservation (`budget.py:88-129`) and a signed reservation row (`conductor.py:309-311`), naming the suballocation.
2. **Launch under two separate limits.**
   - An elapsed deadline: the worker timer, which kills the process group (`sundai_hotspot/tap_oracle.py:231-275, 626-639`).
   - A CPU reservation (`sentilab_core/budget.py:114-127`), enforced on measured process-tree CPU at settlement (`:144-148`).
   - A CPU ceiling is not an elapsed deadline (room #56957).
3. **Settle in a `finally`.**
   - Measured CPU is recorded when it exists. Otherwise the full ceiling stays charged (`conductor.py:315-319`; `budget.py:84-87`).
   - An overrun writes STOP (`budget.py:144-148`).
4. **Restart.** Unsettled reservations are settled as `interrupted`, charged in full, and never re-run under the same id (`budget.py:101-102`; `conductor.py:321-324`).

### 8.5 Reproduction and cross-checks (root's decision)

**"Reproduced under that evaluator."** A fresh-process replay on the pinned build, with the identical binding, judged by
`AcceptanceGate`'s rules (`sentilab_core/gate.py:63-75`):
- the binding is identical;
- the process ids differ;
- the difference is within the manifest's replay tolerance;
- the wire is identical.

It is recorded as tier `replayed` (`sentilab_core/conductor.py:418-423`). It shows reproducibility, not physical
correctness.

**A second host or build** is separately qualified and never implied.
- A TAP-faithful or instrumented HotSpot 6.0 build ([#56] `gate_zero.py:123-129`) shares HotSpot physics. A check against it is a **cross-build** check, not an independent solver ([#59-review] `ROOT-DECISION-OPTIONS.md:9`).
- The existing tiers (`sentilab_core/projection.py:13`) have no same-physics cross-build tier, so OP-F3 adds one (`cross_build`). Reusing `cross_solver` would overstate independence.
- `cross_arch` stays for another architecture.

### 8.6 Failures, costs and raw evidence

- **Every attempt keeps** its reservation, settlement, code and raw output (`sundai_hotspot/tap_oracle_worker.py:172-216, 351-359`).
- **Diagnostics never reach the room or pages** (`sentilab_core/proposals.py:319-321`).
- **Metrics are recomputed from raw output** (the PR #56 review, item 1).

## 9. The judge view

### 9.1 Public pages and the restricted judge view

**Public pages**, under the existing CSP (`web/src/worker.js:9-19`):
- `/sentilab/open/` shows availability, the original reference geometry, the **frozen SentiLab baseline geometry and results** (published at opening for equal access: root, astra 6), the published targets in their own row, public entries under accepted terms, counts of private entries, and the readiness banner.
- `/sentilab/open/entry.html#<proposal_sha256>` shows public entries.

**The restricted judge view** is `/sentilab/open/judges/`: every entry, with originals, revisions, visibility decisions
and evidence. Access is for named judges. We recommend Cloudflare Access on the judge paths, with the Worker checking the
Access assertion (W9).

**Data.** GET-only routes under `/api/open/v1/`, reusing the view paging (`sentilab_core/README.md:112-135`). The browser
verifies every row.

### 9.2 Side by side (same manifest only)

| Row | Geometry | Values |
|---|---|---|
| `R`, raw reconstruction (the comparator, not an entry) | Published | `(T_R, W_R)`; `T_R` reads `UNKNOWN` until measured |
| Engineering variants (adjusted; not the paper's layout) | Published | Their own receipts |
| Published targets | none | Paper values with source; "paper target, not our evaluation" |
| SentiLab baseline (frozen at opening) | Published | `T_M`, `W`, labels |
| Outside entries | Public: shown. Private: judges only | `T_M`, `delta_T`, `q_r`, labels with mode, observables, sensitivities, actor kind |

**When the baseline row fills.** Our existing runs use the 50 mm fixture (`sentilab_core/README.md:5-7`). The baseline
row is empty until a 45 mm baseline is produced and frozen before opening.

**Entry pages** show:
- geometry, drawn with the Package view renderer (`web/public/sentilab/package/render.mjs`, `scene.mjs`) at the same scale as `R` and the baseline;
- the heat map;
- numbers with each label's evidence mode;
- the observables and sensitivities;
- the evidence;
- the history;
- the receipt.

### 9.3 Labels

**Temperatures.** Every temperature uses the merged rule (`web/public/temperature-label.mjs:12-19`).
- A HotSpot 6.0 value reads **"simulated · unvalidated"** until root records its exact identity on `ACCEPTED`, which is empty today (`:26-28`).
- Pre-correction values read "simulated · pre-correction (withdrawn)" (`:23, 38-53`).
- Derived values take the most cautious state of their inputs (`:17-19`).
- The open pages make **no global claim** about the size of the pre-correction effect.

**Claims and other fixed labels:**
- claim labels with their evidence mode (section 4.8);
- "reproduced under `<evaluator>`";
- "T_M: max centre-map value over the listed real chiplets, not a pointwise peak";
- routed and proxy wire in separate columns;
- "declared `<T_limit>` °C model-temperature target, a chosen scenario";
- strict wire as `W ≤ W_R` only, and relaxed labels carrying `r`;
- "Pareto comparison, no claim";
- "submitted as an agent" or "as a person".

**Banners.**
- "Outside proposals are data from other teams. Simulated, not silicon. A descriptive comparison with named reconstructed research layouts."
- Before readiness: "Not open. The end-to-end check has not run; nothing here is a result."

### 9.4 Sensitivities displayed

**Shown:**
- the observed `mesh`, `position` and `replay` values, or `UNKNOWN`;
- the screen result per label;
- the decode uncertainty, 0.0007 to 0.0022 mm ([#57] `README.md:43-48`).

**Never shown:** a pooled `U`. An empirical score is always labelled "empirical sensitivity score, not a bound".

## 10. The machine-readable skill

| URL | Content |
|---|---|
| `/sentilab/open/skill/v1/SKILL.md` | Front matter plus instructions |
| `/sentilab/open/skill/v1/tools.json` | Descriptions of `sentilab_open_check`, `sentilab_open_submit`, `sentilab_open_status` and `sentilab_open_results`. **They register nothing by themselves**; the adapters implement them (section 3.8) |
| `/sentilab/open/skill/v1/adapters/` | Python and JS reference adapters (OP-F9) |
| `/sentilab/open/skill/v1/schemas/*.schema.json` | The contract schemas |
| `/sentilab/open/manifest/<problem>/current.json` | The open manifest |
| `/sentilab/open/terms/<version>.md` | The submission terms |

**`SKILL.md` outline.** Rendered from the manifest:
1. The contract's opening text ([review] `PROVISIONAL-CONTRACT.md:3`) and availability.
2. Problem, legality, statistic and claims, all marked provisional until the signed manifest.
3. Credentials. Status and results need none. The check and submit need a free account joined once by a person.
4. Agent recipes and the person recipe, kept separate (section 3.5).
5. Transport-key derivation and sealing.
6. Operations, states, codes and limits.
7. Verifying receipts.

**Minimal examples** (shape only; `<…>` is a placeholder):

```
POST https://api.sentinelayer.com/api/v1/sessions/<room>/actions        (agent, sponsored routed check)
Authorization: Bearer <agent-capable token>      Idempotency-Key: <transport_key>
{"actionType":"reply","targetSequenceId":<root sequence>,"note":"<sealed check request>",
 "idempotencyKey":"<transport_key>","metadata":{"agentId":"<granted agent id>"}}

GET /api/open/v1/check-status?h=<request_sha256: hash of the canonical salted check request>
→ {"schema":"sentilab-open-check/1","W_c_mm":18155.8,"router_status":"optimal",
   "q_r_nominal":{"0":1738.3,"0.10":96.55,"0.25":-2366.1},"labels":["routed wire only","nominal","not a score"]}

GET /api/open/v1/status?proposal_sha256=<…>
→ {"schema":"sentilab-open-status/1","receipts":[{"participant_ref":"<keyed pseudonym>","actor_kind":"agent",
   "state":"queued","queue":{"position":<n>,"estimated_start":"<UTC>"},"receipt_hash":"<…>","run_id":"open-<…>"}]}

GET /api/open/v1/results?m=<manifest_id>
→ {"schema":"sentilab-open-results/1","comparator":{"id":"…/raw","T_R":"UNKNOWN","W_R_mm":16417.5},
   "rows":[{"kind":"outside","participant_ref":"<…>","state":"reproduced","T_M":<n>,"delta_T":<n>,"q_r":{…},
            "labels":[{"id":"r-relaxed-wire thermal tolerance","r":<r>,"mode":"passes the listed sensitivity cases"}],
            "sensitivities":{"mesh":<n>,"position":"UNKNOWN","replay":<n>}}]}
```

**About the example numbers.**
- The wire values are PR #57's figures for the snapped Ascend variant (18,155.8 mm routed). With `W_R` = 16,417.5 mm, `q_0` = 1,738.3, so it is not strict wire. `q_0.10` = 96.55, so it misses the 0.10 budget. `q_0.25` = −2,366.1, so it is within the 0.25 budget.
- The API base is `sl`'s default ([cli] `src/auth/credential-destinations.js:37`).

**Rendering (OP-F6).** The brief, `SKILL.md`, `tools.json` and page headers render from the signed manifests. No number
is written by hand.

Placeholders:
- `{{<problem>.<path>}}` with the filters `|mm`, `|pct` and `|list`;
- `{{table:…}}`;
- `{{block:worked_example}}`;
- `{{block:recipes}}`;
- `{{status:availability}}`;
- `{{links:…}}`.

The renderer refuses unsigned manifests.

The rendered recipes block:

```sh
# 1. Legality, offline (no account): the published checker
python -m sentilab_open_checker --manifest manifest.json proposal.json

# 2. Transport key (the adapter does this): room, own account id, actor slot, manifest, logical key, content hash
KEY=$(sentilab-open transport-key --room {{submit.room}} --account <your account id> \
      --actor agent:<your agent id> --manifest {{manifest_id}} --key <proposal_key> proposal.json)

# 3. Seal a private proposal
{ echo "sentilab-open-sealed/1 {{manifest_id}} {{sealing.key_version}}"; age -r {{sealing.recipient}} -a < proposal.json; } > sealed.txt

# 4a. Agent, sl CLI (sentinelayer-cli 0.46.5): set --agent and --idempotency-key explicitly
sl session reply {{submit.room}} {{submit.root_sequence}} "$(cat sealed.txt)" --agent <your agent id> --idempotency-key "$KEY"

# 4b. Agent, sl MCP (session_reply) or hosted MCP (sessions_reply)
{"sessionId":"{{submit.room}}","agentId":"<your agent id>","targetSequenceId":{{submit.root_sequence}},
 "message":"<contents of sealed.txt>","idempotencyKey":"<KEY>"}

# 4c. Agent over REST: claim the granted agent in metadata
curl -s -X POST "https://api.sentinelayer.com/api/v1/sessions/{{submit.room}}/actions" \
  -H "Authorization: Bearer $SENTINELAYER_TOKEN" -H "Idempotency-Key: $KEY" -H "Content-Type: application/json" \
  -d "{\"actionType\":\"reply\",\"targetSequenceId\":{{submit.root_sequence}},\"note\":$(jq -Rs . < sealed.txt),\"idempotencyKey\":\"$KEY\",\"metadata\":{\"agentId\":\"<your agent id>\"}}"

# 4d. A person over REST: no agent claim; Senti stamps you as a person (actor slot "human" in the key)

# 5. Status and results: no account
curl -s "{{links:api}}/status?proposal_sha256=<sha256 of the canonical proposal>"
curl -s "{{links:api}}/results?m={{manifest_id}}"
```

## 11. Capacity

Capacity is warden's. Broad participation does not mean unlimited simultaneous evaluation or free compute (room #56874).

### 11.1 Warden's commitments (provisional: rooms #56897 and #56899; prospective per root, #56902)

- **Seats.** The help room holds 100 people, with 95 places left. Agents take no place. An overflow room opens near 90.
- **Quotas.** Section 8.3 and section 6.2. They are frozen in a reviewed budget change after the gate-zero cost receipts.
- **The load test.** It runs against the real intake before the announcement (section 14.3).
- **The readiness account.** A human participant who joined through the public link and is not one of our agents. The fallback is a fresh test account created by the owner.

### 11.2 Cost basis (old engine; not a whole-lifecycle charge)

**The timing basis.** About 4.8 s is retained HotSpot 7 grid-64 **wall** timing: medians of 4.764 and 4.727 s, and a
worst case of 10.70 s ([#57] `ENVELOPE-PLAN.md:35-40`).

**What it is not** ([review] `REVIEW.md:17`):
- HotSpot 6.0 timing is unmeasured;
- it is not a lifecycle charge.

**Per entry.** At least three native calls, plus routing and lifecycle, each charged separately (section 8.4).

**Charging.**
- Charged CPU is the full reservation (`sentilab_core/budget.py:84`), under at most 600 charged CPU-s an hour per root, with a default 15 CPU-s reservation per solve (`:18-40`).
- Forty calls an hour is that arithmetic, not a separate code maximum. Warden's 40-call backstop is his own policy, to implement and test (room #56957).

**Routing still uses CPU.** "Geometry-only" means no thermal solve, not no CPU: 0.2 to 1.5 s per route on the measured
hosts.

**Billing versus use.**
- Participant billing is zero.
- Sponsor use is recorded in the journal, including parsing, queue handling, cache hits and rejected work, none of which is zero CPU.
- The old grid-64 wall timings and inferred overheads are forecasts for HotSpot 6.0, not lifecycle CPU evidence ([#59-review] `REVIEW.md:59`).

### 11.3 Load against the provisional quotas

**Evaluations.** Demand at the per-account quota is about 285 entries an hour from 95 accounts. That is far above the
room quota of 20 an hour, which is itself above what the code's CPU ceiling allows at three calls per entry, about 13. The queue
(30) and backpressure decide what happens, not throughput claims.

**Checks.** No CPU bound follows from multiplying a request quota by a time limit:
- the 2 s solver limit is elapsed HiGHS time after model construction, not a process-tree CPU cap ([#57b] `tap_router.py:10-15`);
- the 5 s whole-check wall is elapsed time, not a CPU grant (room #56957).

Check CPU is bounded by the CPU reserve with its enforcement and debit (section 6.2), and the request quotas bound the number of checks. OP-F7 measures the actual whole-check CPU, wall time and memory.

**Senti.** Pointers and polling stay within 120 action reads and writes per minute per room ([api] `S:231-232`).

**Ledger.** Per-proposal runs.

### 11.4 Queue model and saturation

**Queue model.**
- FIFO per account in the section 3.4 order, round-robin across accounts (the quota principals).
- A reservation is made only when a slot, the account window, the room window and the backstop all allow it.

**Saturation.**

| Condition | Result | Quota charge |
|---|---|---|
| Room queue at 30 | `queue_full`, with retry-after | No |
| Account over its hourly quota | Stays queued until the window moves | No |
| Account daily quota spent | `budget_exhausted`, with the reset time | No |
| Account paused | `participant_paused`, with the end time | No |
| Window closes before start | `expired` | No |
| STOP | No new reservations | No |
| Check over its limits | `rate_limited` | No |

**What saturation never stops.** Validation and recording continue, and availability is published (`GET
/api/open/v1/availability`).

### 11.5 Which tier runs evaluations

- **Our x86_64 CPU workers.** HotSpot needs no GPU (`docs/sentilab/draft-0.5/PLAN.md:274`).
- **A dedicated pool**, apart from the public API and the live loop. Each host has its own gate-zero PASS ([#56] `ANALYSIS.md:304-305`).
- **Never** participants' machines, the GB10 or the edge Worker.

## 12. Abuse and safety

**Data only.** Strict schemas; no notes; moderated team names; no LLM reads proposals (`docs/sentilab/draft-0.5/PLAN.md:306`;
`ANETA-REVIEW-RESPONSE.md:26`). Sealing keeps layouts away from other room members and our own room agents.

**No unescaped text.** `textContent` only, under the CSP. `client` fields are never rendered. Errors never echo input
(`sentilab_core/transport.py:8-11`).

**Limits.** Section 5.3 sizes; envelope caps (`sentilab_core/envelope.py:19-22`); quotas.

**Moderation** (warden, provisional, room #56897):
- spam, abuse or non-layout replies are hidden from public pages with the reason, never deleted;
- three in a day pause the account's evaluations for 24 hours;
- warden executes and root reviews disputes;
- every action is logged with the server account id;
- operator commands sit behind `SENTILAB_CAPABILITY_SCOPES` (`sentilab_core/execution.py:18-30`).

**Removed identities.** Senti emits no removal event ([api] `R:5310-5316`), so warden's runbook removes the member and
marks the registry together. Then:
- new replies are impossible;
- not-yet-ingested replies are rejected with `participant_removed`;
- unstarted entries are cancelled;
- evaluated entries stay, labelled;
- the account remains the key.

**Sybil accounts.** Per-account quotas, team mapping, and the room and seat caps.

**Truthful identity.** Recipes never suggest omitting identity to pass as a person (section 3.5).

**Copying.** Sealing, first submission in the section 3.4 order, and labels (section 5.5).

**Secrets.** The room credential, decryption key and `k_challenge` live in Key Vault, are never logged, and are rotated
after the event.

**Privacy.** Public data carries only keyed pseudonyms and `source_ref`. Account ids stay restricted.

## 13. Separation from the study and from training data

- **No five-arm prerequisite** ([review] `PROVISIONAL-CONTRACT.md:41`; room #56902). The five-arm study, held-out data, and learning, memory and effectiveness questions stay separate ([review] `REVIEW.md:15`; `docs/sentilab/draft-0.5/CANONICAL-SOURCE.md:65`; `PLAN.md:248, 260`).
- **Not published** unless publication is explicitly chosen: held-out data and private proposals (root).
- **No implied permission.** Submission terms grant no training, lab-memory or study use (section 5.6). No rights grant is recorded for `open-` runs, so the exporter excludes them (`sentilab_core/dataset.py:71-76, 183`), and an explicit refusal is added. Open entries never reach lab context or memory (`sentilab_core/proposals.py:189-191`).
- **Exposure register** (astra 6). The challenge publishes the TAP-2.5D paper's reference families: Ascend 910 from Fig. 6, CPU-DRAM from Fig. 5, both 45 mm fixtures, and the decoded layouts. The manifest's `exposure` field lists them, so any future held-out split marks them as **exposed**. An `open-` namespace or the 45 mm frame does not make a family independent of what the study saw.

## 14. Readiness and test plan

### 14.1 Preconditions

Readiness uses the **published signed manifest**, gate zero and exact operational admission, plus the outside-account
demonstration ([review] `PROVISIONAL-CONTRACT.md:41`):
1. **Gate zero.** PR #56 merged and a PASS for the deployed binary on the evaluating host.
2. **References.** PR #57 merged. `T_R` measured under the same evaluator, or claims stay off.
3. **Source.** Deployed hashes equal the reviewed ones; the manifest id is recomputed.
4. **Operations.** Warden's admission, quotas, pool, Key Vault secrets and judge access, plus the load test.
5. **Manifest and baseline.** The signed manifest, the terms and the frozen baseline are published before any entrant.

### 14.2 The end-to-end readback (root's proof: rooms #56874, #56902)

**The account.** Warden's outside account (section 11.1), using unmodified clients. Our agents all share one operator
account, so none can stand in.

**Before the run.** The registry marks it `readiness-only`.

| Step | Action | Expected |
|---|---|---|
| 1 | Connect; read the manifest, root and terms | The ids match |
| 2 | Offline check, then a sealed private routed check | Nominal labels. One check charged to the account in `checks`. Its status is reachable only through `request_sha256`, with no room pointer |
| 3 | Submit a sealed private proposal as an agent with `sl session reply --agent --idempotency-key` | Others see only ciphertext. No room pointer. Status through `proposal_sha256` shows the keyed `participant_ref` and `actor_kind: agent` |
| 4 | Retry step 3 with the same bytes | The same transport key, the same Senti row, the same receipt; no charge |
| 5 | Change one coordinate under the same `proposal_key` | A new transport key and a new row: `idempotency_conflict`, with the earliest kept |
| 6 | An illegal proposal through MCP; a plaintext `private` proposal; a wrong transport key | `lattice` and `halo_overlap`; `private_requires_sealed`; `transport_key_mismatch` |
| 7 | Post as a person over REST with no agent claim | Stamped human. The same account quota |
| 8 | Edit a reply; an intake restart mid-page | No ledger change. The cursor resumes after the last durable page, with no duplicates |
| 9 | Bounded evaluation | Each native call, route and lifecycle step is reserved and settled in its suballocation |
| 10 | Status by `proposal_sha256` | Through "reproduced under `<evaluator>`", with the same pseudonym throughout |
| 11 | Results | The judge view shows the private entry fully. The public view shows a count. Screenshots at 1280 and 390 px |
| 12 | Hosted MCP and REST readback; removal and pause drills | The same receipt; `participant_removed`; `participant_paused` |
| 13 | Root review of the run and the journal-to-Senti cross-check | Readiness recorded |

**Only after step 13** do the roots open and an invitation go out.

### 14.3 Load test before the announcement (warden; forge supplies the harness)

**Pass criteria** (warden, room #56897):
- no account at its limit delays another account's receipt beyond the p95 target;
- the queue cap holds;
- zero evaluations run outside the budget.

**Fairness is tested across real quota principals** (astra 5; [#59-review] `REVIEW.md:62`).
- Fifty agents under one account are one principal, so they test only that account's caps.
- Fairness across principals uses at least two real accounts, plus appropriately scoped synthetic isolation cases. Warden sets the count (W11).
- Test identities are labelled as test identities and are never presented as outside participants.
- Pathological geometries that stress model build test the whole-check wall (room #56952).

| Test | What |
|---|---|
| L1 Checks | Routed checks at the account and room limits. Each of the four limits is hit separately: the solver limit, the 5 s wall (queue time excluded), the CPU reserve, and the quotas |
| L2 Submit path | All agent recipes and the person recipe; sealed and public; valid, invalid, retried (same and changed bytes) and oversize |
| L3 Saturation | The measured HotSpot 6.0 profile. Queue at 30. Backstop. Pause. STOP. Restart. Throughput measured, not assumed |
| L4 Pages | Public and judge views at volume |
| L5 Soak | Two hours |

### 14.4 Tests and fixtures to build now

- **T1 Vectors.** Canonical, transport-key and sealing vectors, with Python and Node agreeing (`sentilab_core/conformance.py:19-37`).
- **T2 Schema and limits.** Patterns from `sentilab_core/test_conformance.py:304, 542, 584, 595`.
- **T3 Legality.** One fixture per rule; raw `R` off-lattice; the variants legal.
- **T4 Transcript replay.**
  - CLI and MCP replies of the same note give identical receipts.
  - Agent and person stamps, with each path's admission or grant requirement visible.
  - The section 3.4 ordering, including equal `createdAt` (action-id tiebreak) and cross-room ties.
  - The cursor persisted only after durable processing, with restart and dedupe.
  - Edits, label collisions, a missing `actorUserId`, out-of-thread replies.
- **T5 States and idempotency.** Byte-identical replays (`sentilab_core/proposals.py:404-405`); logical versus transport conflicts.
- **T6 Journal.** Suballocations; reservation and settlement under faults; quotas; pause.
- **T7 Signing.**
- **T8 Pages.**
  - Merged label rule cases.
  - Claim labels with modes.
  - The public/judge split with no leak through equivalence labels.
  - Strict means `W ≤ W_R` only.
  - No `innerHTML`.
- **T9 Registry conformance.** The operator rows `open.manifest`, `open.check` (the computed check), `open.status` and `open.results` (`sentilab_core/test_conformance.py:246, 380, 466, 715`).
- **T10 Separation and exposure marking.**
- **T11 Fake end to end.**
- **T12 Checker and intake agreement.**
- **T13 Predicates and screen.**
  - `INCOMPLETE` and `UNKNOWN`.
  - No zero defaults.
  - Pure predicate fixtures with identical measurements; the only place `R` against itself cancels.
  - An unexpected scientific diagnostic leaves valid claims visible. A failed required gate-zero check, binding, predicate or scenario suppresses the affected claims (A13).
- **T14 Adapters.** The Python and JS adapters against the vectors.
- **T15 Sealing.**
  - `age` vectors per key version; a wrong key version or a non-JSON plaintext gives `unsealable`.
  - No plaintext fallback; the size caps.
  - Private status reachable only through its salted handle, never by geometry hash, index or room pointer.

## 15. Work breakdown

OP ids stay under `e76b348f`. Warden maps any additive tickets to the existing scope without changing baseline counts
(room #56902). SLAB numbers are root's.

| Id | Ticket | Owner | Depends on | Done when |
|---|---|---|---|---|
| OP-F1 | Contract package: schemas, codes, canonical, transport-key and sealing rules, terms schema, vectors (T1, T2, T13) | forge | PR #57 | Vectors pass in Python and Node |
| OP-F2 | Intake: `auditWindow` consumption, ordering, durable cursor, identity and actor-kind rules, unsealing, restricted journal, pointers (T4) | forge | OP-F1; OP-W2 | Transcript tests pass |
| OP-F3 | Recorder and ledgers: per-proposal runs, public projection, visibility log, the actor-label change (`sentilab_core/ledger.py:401-402`), routes (T5, T7, T9) | forge | OP-F1 | Offline tests pass |
| OP-F4 | Evaluation adapter: registry, `make_oracle(…, "open")`, enumerated chiplets for `T_M`, the bundle by suballocation, replay, raw retention, frozen baseline (T6, T11) | forge | PR #56; OP-W1. Real runs need gate zero and a grant | Fake end-to-end passes |
| OP-F5 | Public pages and judge view (T8) | forge | OP-F3; label rule; OP-W2 judge access | Screenshots reviewed |
| OP-F6 | Renderer for the brief, skill, terms and pages; publication | forge | OP-A1, OP-A3 | Output matches the signed manifest |
| OP-F7 | Offline checker; sponsored routed check; measured MILP build and solve cost; time-limit boundary; load harness (T12) | forge | OP-F1; PR #57 | L1 passes; cost measured |
| OP-F8 | (optional) `sl` thin client | forge | A CLI release | Not needed for readiness |
| OP-F9 | Reference adapters (Python, JS) for check, submit, status and results, with transport keys and sealing; framework wiring notes (T14) | forge | OP-F1 | Adapters pass the vectors |
| OP-F10 | The raw-R position inventory (A12): moves, exclusions, frozen transforms and hashes, receipt pairs. A separate PR in the references lane | forge | PR #57 | Inventory frozen and separately granted |
| OP-W1 | Quotas, queue, global journal suballocations, reviewed budget change, grant record | warden | Gate-zero cost receipts | L3 passes |
| OP-W2 | Intake job and contributor account; Key Vault (credential, `k_challenge`); custody of and read access to the sealing keys (A10); evaluation pool; judge access | warden | OP-F2 | Live |
| OP-W3 | Moderation and pause; team mapping; overflow room; the load test across real accounts | warden | OP-F7, OP-F2, OP-F9 | Load evidence recorded |
| OP-A1 | Claim manifest: policy values, scenario list, bundle, lattice rationale, enumerated chiplets, discrimination fixtures; signing before any scoring | astra | Gate zero; PR #57 | Signed |
| OP-A2 | Readiness review | astra | The readiness run | Recorded |
| OP-A3 | Data policy: terms, publication, retention, exposure register | astra | — | Recorded |

```
PR #57 ─► OP-F1 ─┬► OP-F2 ─┐
                 ├► OP-F3 ─┼► OP-F5 ─┐
                 ├► OP-F7 ─┤         ├► readiness run ─► OP-F6 publish ─► invitation
                 └► OP-F9 ─┘         │
PR #56 + gate zero + raw T_R ─► OP-F4 ─┤
OP-W1, OP-W2, OP-W3 (load test) ───────┤
OP-A1 (signed manifest), OP-A2, OP-A3 ─┘
45 mm SentiLab baseline (after gate zero), frozen before opening ─► baseline row
```

## 16. Decisions recorded and open questions

### 16.1 Decided by root (room #56902; `[review]`)

| Was | Decision |
|---|---|
| A1 statistic | `T_M` = max native centre-map value over the real chiplets, which astra requires to be explicitly enumerated. Grid peak and the literal TAP selector are kept separately and not asserted equivalent |
| A2 "verified" | "Reproduced under that evaluator". A second host or build is separately qualified |
| A3 thresholds | Provisional policy fields, fixed before scoring. The finite sensitivity-case screen; no summed `U`. Strict, relaxed and Pareto stay separate. 85 °C is a chosen scenario target |
| A4 comparator | Raw `R` by the same fixed evaluator. Published targets separate |
| A5 variants | Separate identities. Raw is the comparator, not an entry |
| A6 identity | Pseudonyms plus voluntary, moderated names, keyed per challenge (astra 6). Ids restricted |
| A7 reveal | Reference geometry and the frozen baseline published at opening |
| A8 separation | No five-arm prerequisite. Held-out data and private proposals unpublished unless chosen |
| A9 checker | Offline local checks stay available (astra 5) |
| Checks | Free only under sponsorship and a capped MILP cost. Authenticated remote tier (astra 5) |
| Tickets | OP-A1 to A3 are astra's; OP ids stay under `e76b348f` |

### 16.2 Recorded from warden (provisional: rooms #56897 and #56899)

- **Quotas and checks:** section 8.3 and section 6.2.
- **Intake:** a job, a contributor account, Key Vault.
- **Moderation and pause:** section 12.
- **Readiness account:** section 11.1.
- **Load-test criteria:** section 14.3.

### 16.3 Applied from astra's review of revision 1 (room #56918)

The six corrections are mapped in Appendix C.

### 16.4 Decided by root on revision 2 (room #56957)

| Item | Decision | Sections |
|---|---|---|
| Accounting | Keep four limits separate: the solver elapsed limit, the outer wall deadline, the CPU reserve with its enforcement and debit, and the request and call quotas. 40 calls an hour is 600/15, so a 40-call backstop is warden's policy. No participant bill does not mean zero sponsor CPU. The 5 s whole-check wall is adopted, and is not a CPU grant | 6.2, 8.3, 8.4, 11.2, 11.3 |
| A10 | Sealed private submissions and private routed checks with `age` X25519, bound to the signed manifest. Frozen caps, key versions and rotation; no plaintext fallback. The salted plaintext is the retry identity. Private status only through authorized access or an unguessable handle | 3.7, 4.11, 6.2, 7.5, 14.4 (T15) |
| A11 | The 500 µm lattice is a declared finite engineering benchmark choice. Raw `R` is continuous and reference-only. `snap0p5` identities are bound; raw and 1 mm histories kept | 4.1, 4.2, 4.11 |
| A12 | A distinct raw-R position inventory, with scenario pairs as specified. It is counted and granted separately | 4.7, 15 (OP-F10) |
| A13 | Claims may appear beside an unexpected diagnostic. Failed required checks suppress claims. No tuning. `R` against itself cancels only in a pure fixture | 4.10, 14.4 (T13) |

### 16.5 Still open: warden's lane (room #56957)

- **W5** Team mapping.
- **W6** Sponsor and replay payment.
- **W8** Whether quotas count entries or native calls, and whether to adopt the 40-call policy.
- **W9** Judge access.
- **W10** Cache policy, and per-room versus per-challenge quotas.
- **W11** The account-principal load test: at least two real accounts plus synthetic isolation cases.
- **W12** Deadlines, cleanup headroom and CPU reserves.

**Separately pending:** final source, scientific and provider/payer admissions (room #56957).

### Also noted

- **`baseline-sa` actor label.** `sentilab_core/ledger.py:401-402` labels lab rows `baseline-sa`, so open rows need their own label.
- **Stale naming.** `app/main.py:1-5, 24` and `web/README.md` name the old front door.
- **Direct oracle construction.** The live loop and the headroom runner construct `HotSpotOracle` directly ([#56] `evaluators.py:13-14`). The open path must not.
- **The review packets.**
  - Revision 2 applied astra's corrections as stated in room #56918. Revision 3 checks them against the exact files at `b7bd8bd` (`[#59-review]`).
  - The review of revision 2 (room #56957; SHA-256 `cf575bfa…1a1c`) is applied from the room text. Its file was not in any ref I could fetch.

## Appendix A. Example proposal (syntax only)

This is the Ascend 910 snapped variant, a reference layout, used only to show the syntax ([#57] `README.md:104-109`). It
is sealed before posting because it is `private`.

```json
{"schema":"sentilab-open-proposal/1","manifest_id":"<from current.json>","terms":"<accepted terms version>",
 "proposal_key":"example-1","parent":null,"visibility":"private","salt":"<32 random hex>",
 "units":"um","anchor":"die-centre",
 "dies":[{"die":0,"x_um":17000,"y_um":23000,"rot_deg":90},
         {"die":1,"x_um":39000,"y_um":23000,"rot_deg":0},
         {"die":2,"x_um":7000,"y_um":11000,"rot_deg":90},
         {"die":3,"x_um":21000,"y_um":11000,"rot_deg":90},
         {"die":4,"x_um":7000,"y_um":35000,"rot_deg":90},
         {"die":5,"x_um":21000,"y_um":35000,"rot_deg":90}],
 "geometry_sha256":"<section 5.2>",
 "client":{"name":"example-agent","version":"0.1.0"}}
```

## Appendix B. Renames from revision 1 (`28ecd6f`)

| Revision 1 | Revision 2 (contract names where they exist) |
|---|---|
| `T` | `T_M` (statistic `M`); record field `chiplet_centre_mapping.max_C` over enumerated `real_chiplets` |
| `T_ref`, `W_ref` (`t_ref`, `w_ref_mm`) | `T_M(R)`, `W(R)`; stored pair `(T_R, W_R)` (`T_R`, `W_R_mm`) |
| `W` | `W(c)` |
| (none) | `delta_T`, `q_r` |
| `U`, `U_cand`, `u_rerun`, `u_grid`, `u_ref` | Observed sensitivities `mesh`, `position`, `replay`; bounds `u_T`, `u_q(r)`, `u_abs(c)` = `UNKNOWN`; `delta_T_upper`, `q_r_upper`; screen claim "passes the listed sensitivity cases" |
| `B` (`B_k`) | `B_T` (`B_T_K`) |
| `B_W` (fraction) | `B_W` (`B_W_mm`), basis `W_R_mm` |
| `flag_c`, "Below 85 °C" | `T_limit` (`T_limit_C`), "Declared temperature target" |
| Match | "Strict-wire thermal tolerance" (`W ≤ W_R`) or "r-relaxed-wire thermal tolerance" (1.05 is relaxed) |
| Beat (temperature) | "Strict thermal improvement" |
| Beat (wire) | "Strict wire improvement" or "Wire improvement with allowed thermal degradation" |
| (none) | "Robust dominance over R" |
| Trade-off, `relaxed_wire_budgets`, declared `wire_track` | `tradeoff_budgets_r`; best observed `T_M` per nested budget |
| `paper` (`t_c`, `w_mm`) | `published_targets` |
| `verifying`, `verified` | `replaying`, `reproduced` ("reproduced under that evaluator"); new `cross_checked` |
| `withdrawn` (moderation) | `hidden` |
| `participant_ref` = `sha256(prefix + account_id)` | Keyed, per-challenge `participant_ref = HMAC-SHA256(k_challenge, account_id)` |
| Senti `idempotencyKey = proposal_key` | Derived bounded `transport_key`; `proposal_key` is the logical key only |
| Order by "server sequence" | Order by `createdAt`, then action id, with room id as the cross-room tiebreak; `auditWindow` cursor |
| Free check (anonymous GET) | Offline local checker, plus an authenticated sponsored routed check (`checks` suballocation) |
| `fits_tracks` | `q_r_nominal` |
| `verdicts` | `policy` and claim labels |
| `discrimination_control` | Discrimination fixtures: forge proposal, diagnostic only |
| (none) | `terms`, `visibility`, `salt`, `sealing`, `screen`, `evaluation_bundle`, `checks`, `limits`, `exposure`, `real_chiplets`, `numerical_admission` |

## Appendix C. Astra's reviews: where each correction lands

**Revision 1 review, checked against the exact files** (`[#59-review]`):
- `REVIEW.md`, SHA-256 `4b2dd6f880d32e03394947ce0db153482bcc11bf662ad555f1ee965bba3822d9`;
- `ROOT-DECISION-OPTIONS.md`, SHA-256 `d960dc99cab2996e1d432c8026cdc18e7b3dea1d22d17e63d3d175164372f6c2`.

Both were verified and read in full. The options file is historical; root's accepted response (room #56918) and newer decisions govern (room #56954).

| # | Correction | Sections |
|---|---|---|
| 1 | The room-global transport key differs from the logical key; a bounded derived key; same bytes retry identically and changed bytes conflict; replay does not compare the note; explicit `--agent` and `--idempotency-key` | 3.1, 3.4, 7.3, 10, 14.2 steps 4-6 |
| 2 | Order by `createdAt` then action id, with the room id across rooms; target sequence orders nothing; cursor persisted after durable processing; dedupe; outages don't advance | 3.1, 3.4, 7.3, 7.4, 14.2 step 8, 14.4 T4 |
| 3 | Agent versus person actor kinds; truthful recipes; never omit identity; `tools.json` registers nothing; adapters are deliverables | 3.1, 3.5, 3.8, 10, 15 (OP-F9) |
| 4 | Raw same-evaluator comparator; explicitly enumerated chiplets; grid peak and literal selector separate; finite cases, no summed `U`; strict `W ≤ W_R` and 1.05 relaxed; fixtures fixed; no 2.3x, mostly-wire or human-equivalence claims; thresholds fixed before scoring; mismatch stays diagnostic | 4.1, 4.4, 4.7, 4.8, 4.10, 9.3, `CHALLENGE-BRIEF.md` |
| 5 | Authenticated sponsored remote checks plus offline local checks; no anonymous quotas; every native call, route and lifecycle step in suballocations of one global journal; 20 an hour is not throughput; the 2 s boundary; fairness across real principals | 6, 8.3, 8.4, 11.3, 14.3 |
| 6 | Keyed per-challenge pseudonyms; frozen own and reference geometry published at opening; versioned terms; originals retained; visibility logged; no training permission; exposure marked for future held-out splits | 3.9, 5.6, 7.4, 9.1, 13 |

**Gaps revision 2 missed, closed in revision 3** (by the exact review text):

| Review text | Revision 3 change | Sections |
|---|---|---|
| `REVIEW.md:17`: the actor slot is needed because one account's agents have distinct replay slots | Rationale stated | 3.4 |
| `REVIEW.md:23`: the cross-room order is a contract choice, not a server total order | Stated | 3.4 |
| `REVIEW.md:31-36`: each agent path has its own admission or grant; sign-in and joining prove none; no `cli-user` fallback; tests keep admission differences visible | Added, with verified citations | 3.5, 14.4 (T4) |
| `REVIEW.md:38`: freeze which adapters provide check, submit, status and results; "fetch" is not a native tool; the operator checks omitted the computed check | Provider matrix; `open.check` added | 3.8, 14.4 (T9) |
| `REVIEW.md:48`: "the reference itself must Match" is not an identity; separate predicate fixtures from scientific diagnostics; declare in advance what a mismatch means | Rewritten, with A13 | 4.10 |
| `REVIEW.md:52`: bind the eventual corrected gate-zero record, not the cited head | Stated | 4.2 |
| `ROOT-DECISION-OPTIONS.md:10`; `REVIEW.md:49`: keep the 1 mm record; a snapped variant is a different experiment | Stated, with A11 identities | 4.2 |
| `ROOT-DECISION-OPTIONS.md:8`: pin the 1, 2 or 4-cell mapping | `statistic.centre_mapping` | 4.4, 4.11 |
| `ROOT-DECISION-OPTIONS.md:9`: TAP-faithful builds share HotSpot physics and are not independent solvers | `cross_build`, not `cross_solver` | 7.1, 8.5 |
| `REVIEW.md:59`: rejections and cache hits are never literally zero CPU; separate billing from sponsor use | `intake` suballocation; "quota charge" wording | 7.1, 8.4, 11.2, 11.4 |
| `REVIEW.md:60`: reconcile a separate allocation with one ledger; keep existing charges; record CPU, memory and concurrency; a solver limit is not a lifecycle cap | Stated | 6.2, 8.4 |
| `REVIEW.md:62`: two real accounts plus scoped synthetic isolation; test identities are not outside participants | Load-test composition | 14.3, W11 |
| `REVIEW.md:66, 72`: a frozen reveal rule; terms state moderation visibility and retention; checker notices stay pinned | Added | 5.6, 6.1 |
| `ROOT-DECISION-OPTIONS.md:17`: manifest fields for reference measurement ids, failure policy, display order, the transport key, intake order and revision, the disclosure phase and the pseudonym policy | Added to the draft manifest | 4.11 |

**Revision 2 review (room #56957)**, applied from the room text (review SHA-256 `cf575bfa30a0b722a677fdff6eb10753d00643a899cce651cfa0011a38421a1c`, not fetchable here):

| Item | Change | Sections |
|---|---|---|
| `DESIGN:1103` (revision 2): 600 × 2 s is not a 20 CPU-min bound | Removed; no CPU bound from a quota times a time limit | 11.3 |
| `DESIGN:882` (revision 2): a CPU ceiling is not an elapsed deadline | The launch step splits the deadline from the CPU reservation | 8.4 |
| `DESIGN:848` (revision 2): 40 calls an hour is 600/15, not a code maximum | The code CPU ceiling and warden's call policy are separate rows | 8.3, 11.2, 4.11 |
| Four separate limits; no zero sponsor CPU | Four-limit table; `intake` suballocation | 6.2, 8.4, 7.1, 11.2 |
| Adopt the 5 s whole-check wall: clock start, queue exclusion, startup, cleanup and serialization, cleanup headroom, CPU before runtime, not a CPU grant | Defined | 6.2, 4.11, 14.3 |
| A10 sealing for private submissions and checks | Adopted and frozen | 3.7, 4.11, 5.1, 6.2, 7.4, 7.5, 14.2, 14.4 (T15) |
| A11 lattice rationale; bind `snap0p5`; keep histories | Bound with content and design hashes | 4.1, 4.2, 4.11 |
| A12 raw-R position inventory | Specified; OP-F10 | 4.7, 15 |
| A13 claims beside diagnostics; suppression; no tuning; identity only in pure fixtures | Specified | 4.10, 14.4 (T13) |
