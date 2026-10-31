# SentiLab owner authority — October 31, 2026

This additive record carries Carter's latest instructions into the new implementation repository. It supersedes the earlier requirement to obtain another human `+1` before each agreed project step. It does not replace independent technical review or scientific acceptance criteria. Historical draft-0.5 files remain unchanged.

## Direct owner decisions

| Source | Decision and effect |
| --- | --- |
| Carter's current Codex conversation, October 31 | “go full autonomous with your listeners and eveything. I want yall to work on this all night”. Continue project implementation, coordination, tests and reviewed delivery autonomously overnight. |
| Senti room `608657e4-5e60-4bb6-9353-9611b70c1c66`, human message #56037, `2026-10-31T04:52:34Z` | “Launch it!!!” reinforces the execution release. |
| Same room, human message #56038, `2026-10-31T04:54:31Z` | Create a **new repository** and selectively reuse Thermal Flight Lab source. Warden owns creation and operations. This is not an instruction to delete the old repository or service. |
| Earlier direct scope answer | “i think both 1 and 2”: retain **actual MicroDuck robotics simulation** and **NVIDIA's workflow applied to the chiplet interface**. Reference: <https://www.youtube.com/watch?v=ac6pspFbPsI>. Verify simulator, assets, compatibility and rights; visual resemblance alone does not satisfy the robotics requirement. |
| Earlier direct budget answer | “unlimited. I need this to win.” Record **no overall dollar ceiling**. Record real costs, payer, model, runtime and failure rates. Do not charge another person's credits without their permission. Per-job runtime/concurrency/retry limits remain necessary and are not a new overall financial ceiling. |

Earlier docs-only approval and HOLD text in [draft-0.5/OWNER-DECISIONS-2026-10-31.md](draft-0.5/OWNER-DECISIONS-2026-10-31.md), [PLAN.md](draft-0.5/PLAN.md) and ticket states describe their historical release. Read them alongside this later authority; do not rewrite their reviewed bytes or interpret this release as evidence that their work is complete.

## Repository and frozen review source

- Implementation: private <https://github.com/Sentinelayer-AIdenID/sentilab>, initial import `126507d4dbd8cf327aa158c4dd893c436f7cdf8f`.
- Imported runtime source: `Sentinelayer-AIdenID/thermal-flight-lab@2199612932da142e0057e6162293940b4ea64bba`. [PROVENANCE.json](../../PROVENANCE.json) records the 494 selectively imported files and exclusions. Its hashes describe the import; subsequent reviewed changes need their own commits and evidence.
- Frozen planning/source review archive: <https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/pull/25>, head `5e47b42a1202cc4889ea74de8c57952e3f679210`. Its 234 requirements, 41 draft tickets and original sources remain the traceability baseline. New remote ticket IDs and revisions must link back to that baseline; a draft ticket is not a launched or completed task.
- Frozen SHA-256: PLAN `e15174b8040d40b0675d8821586c2725ba84b79419393fe2a42e405218410f1a`; REQUIREMENTS `cef6ca1268486238be1a98c2fdf2634b2ff8cd7d1004d8b9f5bd61d0b30f658b`; TICKETS `e5acf2ec49c53407b3918c37c9ff0eeefe2bd53df3d189b7949add77513144d4`.

Warden's exact-head, nonauthor technical review of the archived plan is [recorded here](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/pull/25#issuecomment-6539217500). The second independent plan decision was still unverified when this authority record was prepared. Track it explicitly; an author, a readiness reaction, a contract-specific approval or owner autonomy is not that missing technical review. Infrastructure and the bounded defect-fix wave can proceed under the owner's later direction while plan review is reconciled. Dependent scientific gates still apply.

## Responsibilities and acceptance boundaries

| Owner | Current responsibility |
| --- | --- |
| `claude-warden` | New repository, ticket/box provisioning, secure model-route setup, operations, integration and merges with required checks. |
| `gpt-astra-carter` | Plan/requirement traceability, exact-source and independent technical/scientific reviews, coordination and overnight handoff. |
| `aneta-claude` | Evidence/ResultCheck contract seam, subject to nonauthor review. Participation does not authorize charging Aneta's account. |
| `pocket-forge` | View/replay contracts and interface implementation, including both required simulation experiences. |

Coordinate shared-file ownership and use isolated checkouts. Bind reviews to exact commits or artifact hashes. Preserve proposal, review, correction, acceptance, rejection and invalidation history. An LLM judge proposes or critiques; **AcceptanceGate** applies deterministic scientific and permission predicates. The operations agent `claude-warden` is not AcceptanceGate.

Headroom and mesh evidence precede paid LLM **experiment** spending. Authorized implementation-model work is a separate cost category. The first numerical preflight has a shared limit of **60 cumulative CPU minutes, 90 elapsed minutes and 10,000 actual solver/scenario executions**, stopping at the first limit; Warden allocates reservations and records the common release time. Count child CPU, warmups, retries, failures and restarts. A new box does not reset that allowance. Missing evidence yields an inconclusive result or a versioned follow-up, not an invented success.

Verify actual provider model IDs, endpoint behavior, entitlement, prices and payer. Catalog labels and surrogate-executor receipts do not prove an actual model served a request. Warden owns secure admission of the requested Claude route. Keep secrets out of rooms and repository artifacts. GB10 connectivity, successful training and serving require measured evidence; an SSH alias, configuration or launched listener is insufficient.

## Required project scope remains intact

The four scientific lead families remain Astra/OpenAI, Claude, Grok and Kimi, with independent Gemini/DeepSeek review where specified. Preserve the OpenResearch harness, Jev intent/decision routing, scoped ENGRAM memory, success/failure/repair datasets, RLAIF JSONL, and the GB10 train → save → fresh reload → evaluate → serve sequence. The two simulation experiences must use truthful physical models and verified source/asset rights. Every capability, including **SentiResultCheck**, must have both **CLI and MCP** interfaces and parity evidence.

All eight final deliverables remain required:

| ID | Required artifact |
| --- | --- |
| D00 | Proposed chiplet layout with exact coordinates and constraints. |
| D01 | Power scenarios and package assumptions. |
| D02 | Simulator inputs, versions and raw outputs. |
| D03 | Independent reproduction results. |
| D04 | Complete proposal → review → correction → acceptance history. |
| D05 | Comparison against conventional and agent baselines. |
| D06 | Trained worker checkpoint or adapter, with its evaluation. |
| D07 | Replayable visual demonstration. |

The full minimum evidence remains in [PLAN.md](draft-0.5/PLAN.md) and [REQUIREMENTS.md](draft-0.5/REQUIREMENTS.md). Neither this document nor a progress submission certifies all eight deliverables, physics validation, deployment readiness or a competition win.

## Overnight operation

The collector durably acquires room events, replies and edits; the Codex heartbeat supplies model wakeups. Check the exact owned process identity, successful event/action polls and unconsumed ledger, then acknowledge only processed records. Verify outgoing posts by readback. A live PID alone proves no delivery or completed work.

At or after **09:00 America/New_York on October 31, 2026 (13:00 UTC)**, provide a handoff of delivered artifacts, measured results, costs, blockers and next work, then pause this overnight automation. Preserve safely running approved jobs and unrelated listeners. Human-only credentials or access may remain blocking dependencies; continue independent work without repeated routine-step approval requests.
