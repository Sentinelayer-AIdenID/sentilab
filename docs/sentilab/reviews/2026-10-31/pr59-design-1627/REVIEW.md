# PR59 exact design review

**The room-native design is viable for separately admitted descriptive work, but this exact draft needs the concrete corrections below before it becomes the submission/claim contract.** Authoring schemas, recorded-response fixtures and a bounded checker can proceed in parallel. No full five-arm prerequisite, human approval loop, execution release, or intake/model/MILP launch is added by this review.

PR https://github.com/Sentinelayer-AIdenID/sentilab/pull/59 is attached. Exact head `28ecd6f2ecaf1226bf62358ea71bd2159d9bcaef`, base `315bbff4458dd6d033a74549b7f4b89765bf5835`, tree `768bc6e801fd51c01f346321ef2ecacbce3a9621`: three documentation files, all fully read and byte-bound. Room records 56895, 56897, 56899 and action `423b7251-cacc-4f76-9793-9339c83114f3` were read fully from their original durable files. The later contributor correction in 56899 and Forge's acceptance supersede Warden's earlier viewer wording. The accepted root math review and provisional contract were read and retained; their decisions are not reset here.

## 1. Separate transport retry identity from proposal identity

**P2, DESIGN.md:678–694, 927–930, 962–975; readiness step 5.** The design recommends sending `idempotencyKey = proposal_key`, while its own logical key is scoped to `(account, manifest, proposal_key)`. These have different server scopes.

Exact API `6f8058f5`, relay `12558–12572`, looks up the transport key within the **whole room**. `_message_action_replay` at `11669–11705` validates account/agent slot, action type and target, but **does not compare the note/body**. Consequently:

- Two accounts using the example key `example-1` can collide before intake, even though the design considers their keys distinct.
- Reusing one actor/key/target with a changed proposal body replays the original action; intake never sees the purported conflicting revision. Readiness step 5 cannot expect its own `idempotency_conflict` from that transport use.
- The rendered CLI example supplies neither `--idempotency-key` nor `--agent`; its defaults differ from the explicit MCP/REST examples.

Use one published transport-key derivation including room, authenticated account, actor slot, manifest, logical proposal key and canonical proposal hash, within the server's 180-character limit. Identical retries retain that transport key; changed content gets a different transport key but the **same logical proposal key**, allowing intake to record the intended conflict. Include actor slot because the same account's two agents have distinct server replay slots. Make CLI flags explicit. This requires no new CLI release: 0.46.5 already exposes both flags at `src/commands/session.js:4614–4628`.

## 2. Replies have an action cursor, not a submission sequence

**P2, DESIGN.md:147, 266, 682, 693, 1042, 1159, 1177.** The draft repeatedly resumes, orders or chooses winners using a reply's “server sequence.” The retained action row at API relay `10765–10789` has `id`, `createdAt`, and **target** sequence/cursor; it has no monotonically increasing submission sequence. All submissions under a challenge root share that target sequence. The actual action API reports `auditWindow.nextCursor` and order `created_at,id` at `12923–12929`.

Specify durable per-room action-page consumption with the returned cursor, overlap/dedupe by action id and revision, and explicit acknowledgement only after the journal is durable. For deterministic first-arrival and FIFO ordering, freeze an action ordering such as numeric timestamp then full action id, with room id as a cross-room tiebreak; do not confuse target sequence with arrival. The exact cross-room policy is a contract choice, not an existing server total order. Preserve revision-1-only semantics and retained rejection evidence; page outages must not advance the durable cursor.

## 3. Account attribution can converge; authorization paths are different

**DESIGN.md:114–128, 236–242, 246, 960–975.** The useful shared contract is a server-derived `actorUserId`. The claim that metadata source is the only transport difference is false.

| Path at the cited source | Identity/admission behavior |
|---|---|
| CLI 0.46.5 | Resolves an authoring agent; `runMessageActionCommand` enters `withAgentAdmission` when applicable (`session.js:4309–4317`). Posts `metadata.agentId`; explicit missing identity can refuse. |
| Native stdio MCP | Requires `sessionId`, `agentId`, target and message; admission routing can require a valid stored admission (`session-stdio-server.js:927–950,1565–1585`). |
| Hosted MCP | `sessions_reply` requires agentId and idempotencyKey, authorizes the agent, and explicitly writes `actor_kind="agent"` (`mcp.py:2221–2242,4595–4678`). |
| Draft's bare REST account-token example | With no agent claim, `_resolve_session_actor` returns a **human** actor derived from account context (`sessions.py:875–951`). A scoped agent credential remains an agent; an account credential with a validated `metadata.agentId` follows the granted-agent branch. |

Publish separate tested human REST and agent REST recipes. Do not instruct an agent to omit identity or use `cli-user` to appear human. Bind quotas to `actorUserId`, preserve actorKind/actorId for provenance, and keep admission/role differences visible in the integration tests. Signing in and joining alone does not prove every agent path has its required grant/admission.

Likewise, publishing `tools.json` describes tool schemas; it does not register handlers in an arbitrary MCP client. The proposed native capability checks at `DESIGN.md:1166` cover manifest/status/results but omit the computed check. Freeze which actual CLI/MCP adapters provide check/submit/status/results; a table cell saying “fetch” is not a demonstrated native tool. This is an implementation deliverable, not evidence that those clients already work.

## 4. Apply the accepted math corrections consistently

**DESIGN.md:355–459, CHALLENGE-BRIEF.md:84–136.** Several acknowledged open questions are still expressed as facts in the brief or executable-looking table:

- `strict` Match and free-check `fits_tracks.strict` permit `W <= 1.05 W_ref`, while the brief defines strict as reference wire. Rename the 5% category explicitly; retain genuine strict wire at `W <= W_ref`. Wire Beat with `delta_T <= D` permits thermal degradation and needs that label.
- A sum of sampled differences remains an empirical sensitivity score. Saying “not an error bound” does not make “within uncertainty,” guaranteed temperature-target checks, or nonordering by that sum rigorous. Adopt the accepted finite-scenario or explicitly nominal contract. The sampled snapped-reference envelope cannot be silently treated as an uncertainty bound around the raw comparator. Missing cases/terms stay unknown.
- The cited `tap_selector_c` at PR56 `6413a3c`, `gate_zero.py:174–177`, takes the maximum of **all parsed steady-file names**, without a real-chiplet/layer filter. Passing a chip-layer floorplan as `-f` does not itself prove that the resulting maximum is restricted to real dies. Choose and pin the exact inclusion list and native centre mapping; retain the historical TAP positional selector and active-layer grid peak separately. Remove “same version and method as the published reference” until correspondence is demonstrated.
- The proposed 85 C threshold is a declared model scenario, not hardware feasibility. The proposed D/r/B/B_W are policy parameters, not significance or uncertainty estimates. Root still chooses them.
- The discrimination table's “reference itself must Match” is not an algebraic identity under its own additive U penalty: it can fail whenever U exceeds D. Other published classifications are predictions under a reconstructed model, not facts that may be forced by tuning. Separate fixed positive/negative predicate fixtures from scientific diagnostic controls and predeclare what a mismatch means.
- Remove the brief's general “AI agents … as well as human engineers” framing and “the contest … mostly about wire.” Report comparison with the named reconstructed research layouts. The draft's own “meaningless” description of a snapped comparator is also too strong: it is a different experiment, useful with its own identity, not a paper-faithful replacement.
- `DESIGN.md:881–883` retains the provisional 2.3–2.4 multiplier and treats all identities as simply simulated. Use the accepted shared evaluator-status rule and qualitative withdrawn-build wording; no unreviewed magnitude should enter the rendered brief/pages.

The accepted `challenge-math-review-1606/PROVISIONAL-CONTRACT.md` already supplies conditional strict/relaxed predicates, proper paired bounds if independently justified, and a finite-scenario alternative. Reuse it rather than reopening its underlying critique. Gate-zero role inconsistency at the cited PR56 head is already acknowledged as A4; bind the eventual corrected record/reference set instead of treating that old head as final admission.

## 5. Reconcile Warden's provisional operational choices without turning them into capacity promises

**DESIGN.md:593–620, 780–829, 997–1059; Warden 56897/56899.** Three specific points need a recorded choice:

1. **Anonymous checker versus account quota.** The document's no-account GET checker can enforce IP/global limits; it cannot implement Warden's 30 checks/account/hour from unauthenticated requests. Choose authenticated sponsored routing, or a distinct anonymous IP-limited tier plus authenticated account limits. Keep local legality/proxy checking available. A submitted account id is not authentication.
2. **Calls versus proposals and whole-job costs.** Existing budget code permits 600 charged CPU-seconds/root/hour; “40 per hour” is derived for 15-second **calls**, not verified proposals. The proposed evaluate64/reproduce64/grid32 bundle already has three thermal calls plus routing/overhead. Warden's provisional 20 room evaluations/hour is an upper request quota, not proved executable throughput under that ceiling. Specify bundle charges and nested/global grants; do not describe rejected parsing/routing or cache hits as literally zero CPU. Keep participant billing zero separate from sponsor resource consumption. The old grid64 wall timings and inferred cross-run overhead are forecasts for native6, not native6 lifecycle CPU evidence.
3. **Accounting and admission.** Section 8.3 says a separate allocation never consumes the live-loop budget; Warden says the same ledger as SLAB-052. This can be reconciled as separate admitted suballocations under one accounting journal/global ceiling, but must be explicit and must retain existing charges. The 2-second MILP limit must name whether it covers only HiGHS or full build/start/cleanup, and CPU/memory/concurrency settlement must be recorded. An internal solver limit is not automatically a whole-lifecycle wall/CPU cap.

Warden's contributor correction is accepted; do not reopen viewer role or request human permission. His 30 waiting, 3/12 account thermal, 20/120 room thermal, 30/600 checker limits and three-strike pause remain **provisional**, not current deployed service behavior. Record account-versus-agent composition of the load test: 50 agents under one account cannot establish fairness across 50 quota principals. Two real accounts plus appropriately scoped synthetic isolation cases can test the distinction without pretending every test identity is an outside participant.

## 6. Freeze disclosure and data-use scope, not a claim of held-out independence

**DESIGN.md:250–255, 711–728, 854–877, 1099–1105, A6–A8.** Public candidate rows contain geometry. Therefore A7's “hide our geometry until close” cannot be achieved by hiding the picture while those same signed rows remain public. Choose public geometry from first acceptance, or a separate private/commit-only phase with a frozen reveal rule and later evidence release.

`sha256(fixed-prefix + account_id)` is deterministic pseudonymization, not anonymity or a hiding commitment: room members who know account ids can compute the public mapping. It satisfies “do not print the raw UUID” but no stronger privacy claim. A per-challenge secret-key pseudonym is an alternative if unlinkability is wanted; root decides.

The no-training/no-lab-context policy is appropriate. An `open-` namespace does not establish that Ascend/CPU-DRAM reference families are disjoint from a future held-out study. Record this as a descriptive public track and flag/exclude its exposed family/source instances when constructing a confirmatory split. Do not certify held-out independence merely because the frame changed from 50 to 45 mm. This imposes no five-arm gate on the descriptive challenge.

Add the narrow participant terms actually needed for this design: authorization to evaluate, retain evidence and display submitted geometry/results, version of those terms, moderation visibility semantics and retention. Do not turn that into training rights. The draft currently promises public display/immutable retention without defining that scope. Existing right-to-publish checker dependencies and notices must remain pinned when the checker package is published.

## Bounded review result

No code, solver, optimizer, model, intake, room mutation or test suite was executed. Work was local source capture, reading and hashing. All three changed docs, four requested authenticated records, twelve support-source bindings and five transport-source bindings are retained. Snapshot CI at capture had four successful jobs and one container job in progress (`41219397685`); no new run was requested, and this is not a final green/merge decision. Monetary cost and full machine CPU were not measured.

`ROOT-DECISION-OPTIONS.md` gives concise proposed answers for root to select or amend. Forge may continue contract/fixture authorship with these corrections; root retains metric, scenario, threshold, disclosure and data-policy decisions. Warden retains exact operational grants and release. No invitation or evaluated-result readiness is claimed by this documentation review.
