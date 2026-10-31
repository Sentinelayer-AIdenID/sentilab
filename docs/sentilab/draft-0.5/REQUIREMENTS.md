# SentiLab requirement traceability — DRAFT / HOLD

Version draft-0.5, revised 2026-10-31, America/New_York. No peer or owner +1 is recorded. This inventories requirements and planned acceptance evidence, not completed capabilities. No remote tickets were created by these files. [CANONICAL-SOURCE.md](CANONICAL-SOURCE.md) supplies the bounded source corrections integrated into this revision; draft-0.5 incorporates R1–R14, later P1–P11 and the independently checked canonical addendum without applying owner-only scope cuts.

## Source key and current boundaries

- **U**: current user request and exact visual reference in this chat.
- **A**: “reuse Thermal Flight Lab” attachment, C:/Users/carth/.codex/attachments/1d018318-21d5-4dec-9c10-5c524feb3ded/Pasted text.txt. Numbers refer to its sections.
- **B**: “third DGX Spark award” attachment, C:/Users/carth/.codex/attachments/51fbf85c-27bf-4c5d-b1ad-96cd671b51ae/Pasted text.txt. Numbers refer to its sections.
- **Council/science review**: [COUNCIL-REVIEW.md](COUNCIL-REVIEW.md), [SCIENCE-REVIEW.md](SCIENCE-REVIEW.md) and the pinned canonical-source review. Cached-council analysis is complete within the disclosed retrieval boundary, not proof of complete remote history/current deployment.
- **Warden reply**: action 9e9a688f-eca9-4a75-9691-710a31bbe0a8, target #55918, 03:29:33Z. Full note: .sentinelayer/sentilab-planning/gpt-astra-carter/remote-actions-readback-metadata.json. A peer proposal is not direct human authorization or exact-revision +1.
- **Technology sources**: primary NVIDIA Microduck article https://developer.nvidia.com/blog/using-ai-agents-to-teach-robots-like-microduck-to-walk-in-simulation/, official NeMo playbooks, scienceclawhack.ai/Luma and arXiv2603.14312v1, as documented by the technology reviewer. Exact video https://www.youtube.com/watch?v=ac6pspFbPsI still needs direct inspection.
- **Root verification**: canonical GitHub main2199612932da142e0057e6162293940b4ea64bba and matching thermal.aidenid.com/api/health build_sha. Current source contains frontend code, four/six-chiplet runtime domains and sys_micro150.cfg with eight chiplets/680 W; eight-chiplet oracle wiring and numerical evidence remain pending.

[TICKETS.json](TICKETS.json) gives proposed owners/model classes/dependencies/CLI+MCP deliverables/gates. Acceptance evidence below is required later, not declared present. Agent aneta-claude participation is authorized by #55936; no technical +1 was issued in #55938, and human Aneta time/ownership remain pending. Catalog entries are Warden-reported until independently probed; model choices require calibration.

## Coordination, approvals and execution governance

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| G01 | Join requested room 608657e4-5e60-4bb6-9353-9611b70c1c66 | U | SLAB-001 | Join receipt and verified room ID |
| G02 | Use identity gpt-astra-carter; distinguish local peer name from actual Senti identity aneta-claude | U; live peer reply | SLAB-001 | Identity receipt and peer authorization record |
| G03 | Read council 701639be-bd55-4634-8ca5-1eae3d5c0227 including actions and history coverage | U | SLAB-001, SLAB-010, SLAB-011 | Council source references, coverage/gaps and decision ledger |
| G04 | Adversarial reciprocal review; evidence/counterexample and resolution test per objection | U; A4 | SLAB-001, SLAB-014 | Independent review packets and resolved-objection ledger |
| G05 | Explicit +1 may release a named ticket set under one scope/cap/expiry; no assumed consent | U; P7 | SLAB-001 | Gate-scoped release record or HOLD; no redundant per-ticket prompt requirement |
| G06 | Ticketed implementation with dependencies and evidence | U | SLAB-001 | Approved ticket graph; current remote_ticket_id values null |
| G07 | Choose models from verified boxes by capability, budget and role | U; A4; B3 | SLAB-003, SLAB-011 | Live capability catalog and returned-model probes |
| G08 | Obtain missing Claude capability from carther; Warden proposes Opus/Sonnet catalog/rate entries but provider setup/release pending | U | SLAB-003 | Warden source reply, verified catalog/proxy/model/terms/quotas; secret configured outside chat |
| G09 | Human milestone ownership; human Aneta time/ownership pending; aneta-claude participation authorized, no +1 | U; A3; B11; live peer reply | SLAB-001, SLAB-029 | Named authorized owners and gate records |

## Project scope and reused foundation

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| P01 | Stage product SentiLab; thermal-aware chiplet placement is first experiment | A1; B1 | SLAB-001, SLAB-029 | Approved naming and scope |
| P02 | Reuse Thermal Flight Lab numerical/controller assets after reinspection | A2 | SLAB-002 | Inventory with retain/change decisions |
| P03 | Canonical repo/live build identified at 2199612932da142e0057e6162293940b4ea64bba; inspect source/tests/artifacts before reuse | A2; A9; root independent GitHub/health verification | SLAB-002 | Pinned canonical source/live build plus fresh code/artifact inspection |
| P04 | Distinguish existing work from event contribution | A9 | SLAB-002, SLAB-028, SLAB-029 | Contribution manifest |

## Architecture, agents, routing and research

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| A01 | Four research labs propose, inspect and revise | A1; B3 | SLAB-013 | Four identity-isolated lab traces |
| A02 | Scientific executor validates and measures | A1; B3 | SLAB-005, SLAB-006, SLAB-008 | Typed executor outputs and denial fixtures |
| A03 | Independent reproduction queue/worker | A1; B3 | SLAB-015 | Fresh reproduction receipt and independence definition |
| A04 | Senti communication requires real authenticated intake consumers | A1; B9 | SLAB-008, SLAB-013, SLAB-023 | Request-consumption-receipt trace |
| A05 | ENGRAM findings, evidence and dependencies | A1; U | SLAB-010 | Source-backed recall and dependency records |
| A06 | AIdenID permission at actual execution boundary | A1; A3 | SLAB-008 | Allowed/denied bypass tests at executor boundary |
| A07 | Flight recorder preserves actions, hashes, outcomes and correction history | A1 | SLAB-007, SLAB-028, SLAB-036 | Verified event/manifest chain |
| A08 | Deterministic AcceptanceGate budgets, states and accepted-board commits | A1; B3 | SLAB-008 | Atomic state/usage tests |
| A09 | Lead identities Astra/OpenAI, Claude, Grok and Kimi | A4; B3 | SLAB-003, SLAB-013 | Verified catalog/model IDs and lead manifests |
| A10 | Initially at most two active workers per lab | B3 | SLAB-013, SLAB-036 | Concurrency-limit proof |
| A11 | Shared serving allowed with distinct worker identities/context/history | B3 | SLAB-013, SLAB-019, SLAB-033 | Isolation and serving records |
| A12 | Leads choose scientific trajectories; AcceptanceGate enforces bounds and Jev routes intake without prescribing research | B3; R8 | SLAB-008, SLAB-011, SLAB-013 | Policy and recorded scientific decision originators |
| A13 | Record actual model identity/settings/date/cost/role | A4; B5 | SLAB-003, SLAB-007, SLAB-020 | Invocation and accounting manifests |
| A14 | Four scientists adopt documented best-in-field methods and explicit specialties | U | SLAB-012, SLAB-013, SLAB-014 | Approved specialty/method cards with sources |
| A15 | Gemini independently reviews assumptions/spec/claims | A4 | SLAB-003, SLAB-014 | Independent initial review and model ID |
| A16 | DeepSeek independently reviews arithmetic/code/constraints/controls | A4 | SLAB-003, SLAB-014 | Counterexamples and numerical review |
| A17 | Parent/Claude mainly judges; no narrative override of deterministic checks | U; A1; B3 | SLAB-008, SLAB-014, SLAB-017 | Judge/acceptor authority separation |
| A18 | Bounded extra agents for interface and specialist tickets | U; B3 | SLAB-003, SLAB-013, SLAB-024, SLAB-025, SLAB-026 | Approved capacity/dependency plan |
| A19 | OpenResearch required research harness with source-backed outputs | U supersedes B10 optionality; A4 | SLAB-012 | Named underlying-model research run and export |
| A20 | Jev preferred intent and decision routing; reuse existing jev-1.13.0/SystemOne seam after runtime capability proof | U; B3; canonical source review | SLAB-011 | Actual identity/access/schema probe, versioned goal contract and calibrated routing results |
| A21 | ENGRAM combined memory and fast recall with freshness/provenance | U; A1 | SLAB-010 | Recall/latency/coverage measurements; no invented completeness claim |
| A22 | Reconcile existing council; preserve settled retrieval design | U; council review | SLAB-001, SLAB-010, SLAB-011 | Adopt/change/defer ledger tied to source references |

## Physics, geometry and numerical contract

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| S01 | Wire and validate existing eight-chiplet680W micro150 configuration as the initial task | B4; canonical addendum | SLAB-002, SLAB-005, SLAB-006 | Pinned sys_micro150.cfg, scenarios/oracle integration and verified initialization |
| S02 | Frozen power scenarios and power allocation | A7; B4 | SLAB-005, SLAB-006 | Scenario manifest with units |
| S03 | Fixed package, cooling, material and dimension assumptions | A7; B4 | SLAB-005, SLAB-006, SLAB-012 | Assumption/provenance manifest |
| S04 | Placement grid, boundary/spacing and nonoverlap rules | B4 | SLAB-005 | Executable legality fixtures |
| S05 | Explicit lower-left versus center conversion | A2 | SLAB-005 | Round-trip/unit/grid conversion tests |
| S06 | G1 chooses/version-controls proposed chip-layer grid-peak primary with center diagnostics versus attachment center objective | B4; canonical addendum; pending G1 decision | SLAB-005, SLAB-006 | Approved metric_id/evaluator_version and complete fields; historical center values not mixed |
| S07 | Weighted Manhattan center-distance proxy with fixed matrix | B4 | SLAB-005 | Proxy formula fixtures and c_ij pin |
| S08 | Wire allowance fixed to initial layout, not rolling parent; zero baseline policy | B4; expert review | SLAB-005 | No cumulative-budget drift test |
| S09 | In-bounds expanded footprints, correct gap convention and geometry rejection | A2; B4 | SLAB-005 | Boundary/nonoverlap/malformed fixtures |
| S10 | Metric units/layer/statistic explicit; proxy not routing/timing signoff | A2; B4 | SLAB-005, SLAB-006, SLAB-021, SLAB-025 | Labels and scope assertion tests |
| S11 | Power/energy/symmetry/zero-power/malformed-geometry checks | A2 | SLAB-002, SLAB-006 | Fresh numerical regression logs |
| S12 | Do not combine synthetic-plate, six-chiplet and eight-chiplet experiments | A2 | SLAB-002, SLAB-005, SLAB-021 | Experiment identity and incompatible-comparison refusals |
| S13 | Substrate field distinct from active-layer center/peak temperatures | A6; B4 | SLAB-006, SLAB-025 | Verified exporter labels and display fixtures |
| S14 | New exporter/objective requires new evaluator/protocol version | B4 | SLAB-005, SLAB-006, SLAB-020 | Version-change invalidation test |
| S15 | Annealing exploration may worsen; accepted best state remains separate | A2 | SLAB-008, SLAB-020 | Independent search/accepted-state regression |

## Records, admission and correction

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| E01 | Request and candidate IDs | A3 | SLAB-007 | Schema/uniqueness fixtures |
| E02 | Retain exact lineage parent and separately record current comparison-board ID/version | A3; P3; canonical addendum | SLAB-007, SLAB-008 | Exact-parent delta materialization and current-board comparison records |
| E03 | Input/artifact hashes bind retained exact files, not only extracted fields or summaries | A3; canonical source review | SLAB-007, SLAB-028 | Exact-file persistence/readback and manifest hash verification after temporary cleanup |
| E04 | Evaluator version and source/runtime pin | A3 | SLAB-006, SLAB-007 | Reproducible run metadata |
| E05 | Metric name and units | A3 | SLAB-005, SLAB-007 | Unit/statistic consistency tests |
| E06 | Persist all generated simulator inputs and raw outputs before TemporaryDirectory cleanup | A3; B4; canonical source review | SLAB-006, SLAB-007 | Complete artifacts survive cleanup; missing/corrupt persistence fails D02 completeness |
| E07 | Constraint results | A3 | SLAB-005, SLAB-007 | Per-constraint evidence |
| E08 | Evidence dependencies plus separate lifecycle, validity and verification-tier fields | A3 | SLAB-007, SLAB-010 | Status/dependency schema |
| E09 | Schema and geometry must pass | B3 | SLAB-005, SLAB-008 | Fail-closed admission test |
| E10 | Required scenarios execute successfully | B3 | SLAB-006, SLAB-008 | Failure/incomplete-scenario refusal |
| E11 | Objective qualifies under frozen margin | B3; expert review | SLAB-006, SLAB-008 | Pinned threshold and uncertainty evidence |
| E12 | Independent reproduction required before accepted result | B3 | SLAB-008, SLAB-015 | Missing/failed-reproduction refusal |
| E13 | Atomically compare fixed-task complete candidates against current board; CAS retry reuses valid numerical evidence | B3; P3; canonical addendum | SLAB-008 | No stale-lineage invalidation or duplicate billing; current authority/STOP/context rechecked |
| E14 | Combined edits create a new candidate and full reevaluation | B3 | SLAB-008 | Merge-needs-evaluation regression |
| E15 | Stale/withdrawn evidence cannot silently remain valid | A6 | SLAB-008, SLAB-010 | Dependency-invalidated acceptance refusal |
| E16 | Clearly labeled seeded correction drill | A6 | SLAB-010, SLAB-027 | Replay with drill label and provenance |
| E17 | Direct and transitive stale propagation | A6 | SLAB-010, SLAB-027 | Diamond/cascade test and recorded drill |
| E18 | Independent support survives a withdrawal | A6 | SLAB-010, SLAB-027 | Alternative-support preservation test |
| E19 | Preserve original records or authorized tombstones/references under access and retention policy | A6 | SLAB-007, SLAB-010, SLAB-027 | History retention/revocation/deletion/restoration policy and replay proof |
| E20 | Actual signed evidence needs independently pinned service authority beyond embedded-key consistency | A6; canonical addendum | SLAB-007, SLAB-028, SLAB-036, SLAB-040 | Root/delegation validation, negative forgery tests and integrity/origin/science verdict separation |

## Benchmark arms, budgets and interpretation

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| B01 | Classical simulated annealing arm | A7; B5 | SLAB-020, SLAB-032 | Pinned B0 implementation and runs |
| B02 | One lead lab with base worker arm | A7; B5 | SLAB-020, SLAB-032 | Pinned B1 runs |
| B03 | Four isolated labs with base worker arm | A7; B5 | SLAB-010, SLAB-020, SLAB-032 | Pinned B2 isolation and runs |
| B04 | Four shared labs with base worker arm | A7; B5 | SLAB-020, SLAB-032 | Pinned B3 runs |
| B05 | Four shared labs with adapted worker arm | A7; B5 | SLAB-019, SLAB-020, SLAB-032 | Pinned B4 checkpoint and runs |
| B06 | Twelve held-out task families | A7; B5 | SLAB-016, SLAB-020 | Family grouping and split manifest |
| B07 | Two paired seeds | A7; B5 | SLAB-020 | Paired seed manifest |
| B08 | 32 inclusive aggregate bundles per run; proposed28search+4reproduction, fixed7+1 per lab in four-lab arms | A7; B5; freeze proposal pending approval | SLAB-020, SLAB-041 | Equal arm table, all charging rules and 3840 interpretation approved before execution |
| B09 | Each bundle includes required scenarios | A7; B5 | SLAB-006, SLAB-020 | Bundle/scenario accounting |
| B10 | Count failures and retries | A7; B5 | SLAB-008, SLAB-020, SLAB-036 | Failure/retry budget tests |
| B11 | Fixed proposal ceiling | B5 | SLAB-013, SLAB-020 | No free unlimited oracle/proposal access |
| B12 | Track aggregate model tokens, wall time and GPU time | A7; B5 | SLAB-007, SLAB-020, SLAB-036 | Usage ledger and per-arm accounting |
| B13 | Predeclare resource-driven reduction rule | B5 | SLAB-020 | Frozen reduction/stop rule before results |
| B14 | Same models/total budget for isolated versus shared contrast | B5 | SLAB-003, SLAB-020, SLAB-021 | B2/B3 balance table |
| B15 | Fixed held-out corpus is primary for worker learning; closed-loop B4 remains required secondary evidence | A7; B5; P6 | SLAB-019, SLAB-020, SLAB-021, SLAB-032 | Identical fixed-input decoder/runtime and matched closed-loop conditions; no silent dropped arm |
| B16 | Family grouping and train/validation/test separation | B5 | SLAB-016, SLAB-020 | Leakage and duplicate-family audit |
| B17 | Frontier leads remain frozen | A7; B5 | SLAB-003, SLAB-013, SLAB-019, SLAB-020 | Lead identity/prompt version freeze |
| B18 | Reviewers outside search or equal assistance/accounting | A4 | SLAB-014, SLAB-020 | Reviewer exposure/accounting manifest |
| B19 | First-attempt action validity | B5 | SLAB-019, SLAB-021, SLAB-032 | Per-run valid-action metric |
| B20 | Repairs needed | B5 | SLAB-019, SLAB-021, SLAB-032 | Repair distribution |
| B21 | Simulator-confirmed beneficial proposals | B5 | SLAB-006, SLAB-021, SLAB-032 | Verified beneficial proposal counts |
| B22 | Final thermal objective at fixed budget | B5 | SLAB-020, SLAB-021, SLAB-032 | Per-family final-J table |
| B23 | Time/cost per accepted improvement and contributor credit | B3; B5 | SLAB-007, SLAB-021 | Cost/time and separate proposer/reviewer/reproducer credit |
| B24 | Paired outcomes, ties/regressions; loss alone not improvement | B5 | SLAB-019, SLAB-021, SLAB-029, SLAB-032 | Full outcome table and supported claims |

## Data, NVIDIA stack and deployment

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| M01 | Retain success/failure/correction/cancelled records | U; B5 | SLAB-007, SLAB-016 | Complete raw JSONL ledger |
| M02 | Structured state/action/tool feedback and verified correction | B5 | SLAB-016 | SFT/repair schema and validators |
| M03 | Task/evaluator versions in training records | B5 | SLAB-016 | Versioned manifests |
| M04 | Provenance and supporting raw artifact references | A7; B5 | SLAB-016, SLAB-035 | Source/license/lineage records |
| M05 | Training eligibility separate from retention; prevent evaluation leakage | A7; B5; U | SLAB-016, SLAB-020 | Eligibility and split checks |
| M06 | RLAIF-ready JSONL including judge disagreement/ties/abstention | U | SLAB-017 | Preference schema and blinded judge audit |
| M07 | Meaningful NVIDIA software use, not incidental GPU hosting | A7; B2 | SLAB-018, SLAB-019, SLAB-029 | Actual NVIDIA framework training evidence |
| M08 | NeMo AutoModel core; distinguish from Agent Toolkit | B2 | SLAB-018 | Verified product/version recipe |
| M09 | Pinned model/tokenizer/container/source/runtime versions | A7; B2 | SLAB-018, SLAB-019, SLAB-028 | Resolved hashes/digests |
| M10 | Tiny train/save/reload/fresh-inference preflight | A7; B2 | SLAB-018 | GB10 preflight logs and loaded-checkpoint proof |
| M11 | Freeze actual selected checkpoint before held-out matched evaluation; promotion is a later gate | A7; B5 | SLAB-019, SLAB-032, SLAB-033 | Train/validation selection → immutable hash freeze → untouched held-out results → promotion receipt |
| M12 | Qwen3-4B provisional; fallback before experiment freeze | A7; B2 | SLAB-003, SLAB-018, SLAB-020 | Approved worker choice and freeze |
| M13 | GB10 mandatory; user requests fine-tuning there | U supersedes attachment optional/inference-only scope | SLAB-004, SLAB-018, SLAB-019, SLAB-033 | GB10 actual training and serving records |
| M14 | Do not silently substitute H100-only training; reconcile placement | U; B2; B6 | SLAB-004, SLAB-018, SLAB-019, SLAB-033 | Scoped alternative approval if needed |
| M15 | C source permits ARM HotSpot build preflight; current x86 path retained until separately verified compatibility | B6; canonical addendum | SLAB-002, SLAB-004, SLAB-006, SLAB-015 | Recorded compiler/library/binary/architecture and prespecified tolerance; no assumed ARM success |
| M16 | GB10 portability distinct from same-hardware causal comparison | B6 | SLAB-021, SLAB-032, SLAB-033 | Hardware-labeled deployment and comparison evidence |
| M17 | H100/Nebius/Brev allocations/spend unconfirmed and capped | B7; B10 | SLAB-003, SLAB-004, SLAB-029 | Confirmed resources and explicit spending caps |

## Visual simulation, reference fidelity and replay

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| V01 | Exact chiplet geometry and translucent proposed moves | A6; B8 | SLAB-025 | Coordinate-bound visual fixture |
| V02 | Actual lab activity view | B8 | SLAB-025 | Event-derived agent-state trace |
| V03 | Evidence/dependency graph view | A6; B8 | SLAB-010, SLAB-025 | Inspectable provenance and dependencies |
| V04 | Experiment-comparison view | B8 | SLAB-021, SLAB-025 | Real matched-result fixtures |
| V05 | Show measured result, reproduction and accepted-board update | A6 | SLAB-025, SLAB-027 | Complete result replay |
| V06 | Every animation tied to agent/artifact/event timestamp | A6; B8 | SLAB-007, SLAB-025, SLAB-027 | No fabricated activity check |
| V07 | Inspect exact reference https://www.youtube.com/watch?v=ac6pspFbPsI | U; new reference | SLAB-024 | Timestamped reference inventory and primary sources |
| V08 | Identify exact Microduck simulator/tools/assets/workflow and licenses | U; NVIDIA primary article | SLAB-024, SLAB-026, SLAB-035 | Pinned pipeline/asset/license manifest |
| V09 | Interface and visual-simulation specialist agents/tickets | U | SLAB-003, SLAB-024, SLAB-025, SLAB-026 | Approved specialty assignments and dependencies |
| V10 | Exact pipeline mandatory; any narrowing needs +1 | U; primary reference | SLAB-001, SLAB-024, SLAB-026 | Explicit scope/fidelity acceptance; no silent generic substitute |
| V11 | Replays and time compression visibly labeled | A8; B8 | SLAB-027 | Replay labeling test |
| V12 | Replayable bundle and backup demonstration | A8; B11 | SLAB-027, SLAB-028, SLAB-029 | Offline replay rebuild and backup artifact |
| V13 | Correct field/layer display; no false continuous die heatmap | A6; B4 | SLAB-006, SLAB-025 | Exporter/display unit/layer assertion |

## ResultCheck, transports and external benefit

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| X01 | Actual intake worker; a Senti message alone is insufficient | B9 | SLAB-022, SLAB-023 | Executed intake-to-result trace |
| X02 | Paired baseline/candidate measurements | A6; B9 | SLAB-022 | Pairing fixtures |
| X03 | Task/trial IDs, metric/units and optimization direction | A6; B9 | SLAB-022 | Request schema |
| X04 | Recomputed supported arithmetic/statistics | A6; B9 | SLAB-022 | Independent arithmetic fixtures |
| X05 | Missing/duplicate pairs and discrepancy flags | A6; B9 | SLAB-022 | Malformed-data fixture suite |
| X06 | Insufficient-data outcome rather than invented confidence | A6 | SLAB-022 | Unsupported/insufficient-data refusal |
| X07 | Versioned request-linked receipt; submitted-data scope limits | A6; B9 | SLAB-022 | Hashed receipt and claim-scope text |
| X08 | SentiResultCheck both MCP and CLI | U | SLAB-009, SLAB-022, SLAB-034 | Equivalent positive/negative transport receipts |
| X09 | Every project capability has MCP and CLI access | U | SLAB-009, SLAB-034 | Complete capability matrix and parity report |
| X10 | Real external request, executed result and returned receipt | A6; B9 | SLAB-023 | Authorized real partner exchange |
| X11 | Observed downstream use, not just documentation/API presence | A6; B9 | SLAB-023, SLAB-029 | Partner-use evidence and honest adoption claim |

## Ownership, scope, sponsors and presentation

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| O01 | Aneta proposed evidence/dependency/ResultCheck/demo owner conditional on authorization | A3; live peer reply | SLAB-001, SLAB-025, SLAB-029 | Authorization and accepted scope |
| O02 | Carter proposed scientific/orchestration/auth/evaluation/NVIDIA/partner owner | A3 | SLAB-001 | Confirmed human ownership |
| O03 | Freeze shared result schema before parallel implementation | A3; A9 | SLAB-005, SLAB-007 | Contract revision and interface fixtures |
| O04 | Interface may build against recorded explicitly labeled fixtures | A3 | SLAB-025 | Fixture lineage and labels |
| O05 | First vertical slice is real request→measurement→visible receipt | A9 | SLAB-008, SLAB-015, SLAB-025 | G2 complete-slice packet |
| O06 | General NVIDIA-platform prize target; verify actual rules | B1–2; B7 | SLAB-029 | Current sponsor requirements and submission checklist |
| O07 | Acknowledge/inspect ScienceClaw+Infinite prior work and integration | B10 | SLAB-012, SLAB-029 | Primary-paper and artifact-integration notes |
| O08 | Mentor review of thermal metric, artifacts and controlled comparison | B7; B10 | SLAB-012, SLAB-029 | Authorized request and actual feedback, if obtained |
| O09 | Resource URLs, compatible containers, confirmed GPUs/GB10 and submission rules | B7 | SLAB-003, SLAB-004, SLAB-018, SLAB-029 | Verified resources, version pins and eligibility |
| O10 | Sponsor-specific contribution/usage evidence | B10 | SLAB-007, SLAB-029 | Actual usage and sponsor packet |
| O11 | PRISMO verification/failure/rerun lessons and other named prior projects | A5 | SLAB-012, SLAB-029 | Primary-source claims ledger with uncertainty |
| O12 | Do not invent winning talks, rankings or causal award explanations | A5 | SLAB-012, SLAB-029 | Citation/claim audit |
| O13 | Five-slide 2:45 presentation plus 15-second margin | A8 | SLAB-029 | Editable deck and rehearsal timing |
| O14 | Conditional Aneta one-minute evidence/correction walkthrough | A8 | SLAB-025, SLAB-027, SLAB-029 | Authorized speaker plan and demonstrated sequence |
| O15 | Actual matched results and NVIDIA artifact on stage | A8; B12 | SLAB-019, SLAB-021, SLAB-029 | Claims bound to measured evidence |
| O16 | External benefit and final engineering artifact closing | A8; B12 | SLAB-023, SLAB-028, SLAB-029 | Real partner use and D00–D07 link |
| O17 | Null/regression wording and three rehearsals | A8–9 | SLAB-029 | Honest alternate script and timing logs |
| O18 | Deadline progress submission may state missing work; full D00–D07 completion remains separately required | A9; B11; P1 | SLAB-002, SLAB-028, SLAB-029 | Verified deadline/eligibility, honest progress/omission ledger and distinct full-completion status |
| O19 | PhysicsNeMo screening extension only after independent error/split validation | B8 | SLAB-030 | Separate extension approval and predictor validation |
| O20 | Nemotron fixed critic optional and mentor-supported | B2 | SLAB-031 | Explicit optional-role approval and model evidence |
| O21 | ALCHEMI/BioNeMo only with defensible domain bridge | A7; B2 | SLAB-031 | Scientific bridge and scope approval |
| O22 | Formlabs print/RTL-to-layout deferred; print does not validate thermal physics | B10–11 | SLAB-031 | Deferred-scope ledger and separate approvals |

## Eight final handoff deliverables

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| D00 | Exact chiplet layout and constraints | U; B1 | SLAB-005, SLAB-028 | D00 geometry manifest |
| D01 | Power scenarios and package assumptions | U; B1 | SLAB-005, SLAB-006, SLAB-028 | D01 frozen assumptions/scenarios |
| D02 | Simulator inputs, versions and raw outputs | U; B1 | SLAB-006, SLAB-007, SLAB-028 | D02 reproducible simulator bundle |
| D03 | Independent reproduction results | U; B1 | SLAB-015, SLAB-028 | D03 reproduction packet |
| D04 | Complete proposal→review→correction→acceptance history | U; B1 | SLAB-007, SLAB-010, SLAB-028 | D04 full event/dependency history |
| D05 | Conventional and agent baseline comparison | U; B1 | SLAB-020, SLAB-021, SLAB-028, SLAB-032 | D05 paired-results/analysis bundle |
| D06 | Trained worker checkpoint/adapter and evaluation | U; B1 | SLAB-018, SLAB-019, SLAB-028, SLAB-033, SLAB-032 | D06 model/data/provenance/evaluation bundle |
| D07 | Replayable visual demonstration | U; B1 | SLAB-026, SLAB-027, SLAB-028 | D07 replay package |

## Derived expert safeguards and current-source corrections

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| F01 | Numerical convergence/uncertainty margin distinct from physical validity | Expert review | SLAB-006, SLAB-008, SLAB-021 | Resolution/sensitivity report and frozen acceptance threshold |
| F02 | Family-level statistical unit and complete paired reporting | Expert review | SLAB-020, SLAB-021 | Preregistered analysis and family-level estimates |
| F03 | Raw Celsius percentages are origin-dependent; normalize only by declared meaningful denominator | Expert review | SLAB-021, SLAB-022 | Temperature-normalization refusal/validation tests |
| F04 | RLAIF hard checks outrank model preferences; order bias/self-preference/abstention audited | U; expert review | SLAB-014, SLAB-017 | Judge calibration and adversarial fixtures |
| F05 | Frozen dataset and memory; corrections mark affected checkpoints, not claimed unlearning | Expert review | SLAB-010, SLAB-016, SLAB-019, SLAB-033 | Eligibility propagation and checkpoint-review trail |
| F06 | MCP/CLI auth/errors/idempotency/cancellation parity | U; expert review | SLAB-009, SLAB-034, SLAB-036 | Transport conformance suite |
| F07 | Checkpoint A/B/C fixes, maximum validated coverage order, ACL epoch, gaps and raw expansion | Council review | SLAB-010, SLAB-036 | Council-conformance, model-label poison quarantine and recovery checks |
| F08 | Jev cannot strip mandatory constraints, bypass ACL, accept science or infer +1 | Council review | SLAB-008, SLAB-011 | Mandatory-context and authorization negative fixtures |
| F09 | Microduck primary pipeline includes Hermes/Nemotron, Astra, FreeCAD/Blender, CAD/USD, Isaac Sim/Omniverse/Newton, Isaac Lab and sim2real prep | NVIDIA primary article; research agent | SLAB-024, SLAB-026 | Pinned workflow comparison against exact video/reference |
| F10 | RTX Spark distinct from GB10/DGX Spark; H100/A100 not Isaac Sim rendering substitutes; Dell/ARM support requires preflight | NVIDIA primary sources; research agent | SLAB-004, SLAB-024, SLAB-026 | Compatible rendering/training hardware proof |
| F11 | Apache-2.0 code versus CC BY-NC-SA 4.0 STL assets; verify exact revisions/use rights | Primary repository findings; research agent | SLAB-024, SLAB-026, SLAB-035 | Code/asset/data license manifest and allowed-use decisions |
| F12 | Full source-to-ticket-to-evidence audit after every approved scope change | U | SLAB-001, SLAB-028, SLAB-034 | Coverage validation with no orphan requirements |
| F13 | GB10-specific NeMo26.08/Qwen3-8B playbook differs from general26.10/Qwen3-4B plan; no mixed recipe or silent substitution | Technology primary-source review | SLAB-018 | Exact model/hardware recipe or scoped +1 before freeze |
| F14 | Train/validation checkpoint selection precedes held-out freeze; test failure cannot authorize tuning on the same test | Science review | SLAB-019, SLAB-020, SLAB-032, SLAB-033 | Separated G3a/G3b/G4 manifests and no test-driven selection |
| F15 | Non-improving/tie/inconclusive outcomes are recorded science; validate geometry before simulation | Science review | SLAB-005, SLAB-008, SLAB-016 | Complete state taxonomy and failure/outcome fixtures |
| F16 | Same unchanged idempotent request creates no duplicate job; changed payload rejected; executed retries/failures count | Science review | SLAB-008, SLAB-020, SLAB-036 | Job identity and resource-accounting tests |
| F17 | At least three spatial resolutions; finer-grid and aliasing checks; current converged=True only means output validation | Science review; canonical source review | SLAB-006 | Separate numerical convergence/refinement evidence; no flag-based convergence claim |
| F18 | Passive heating monotonicity and ΔT=P·Rθ analytic checks; physical validation remains separate | Science review | SLAB-006, SLAB-015 | Independent analytic/numerical tests with explicit claim limits |
| F19 | Adapters must match base/tokenizer/chat template/modules/rank; any merge is a new evaluated artifact | Science review | SLAB-016, SLAB-019, SLAB-033 | Compatibility manifest and incompatible-merge refusal |
| F20 | Separate delivered/scanned/processed cursors; validated checkpoint coverage rather than insertion order | Council review | SLAB-010, SLAB-036 | Isolated cursor barrier, gap and atomic-projection tests |
| F21 | Credential×room quotas, typed source authority, live ACL/source-revision revocation across derived artifacts | Council review | SLAB-008, SLAB-010, SLAB-035, SLAB-036 | No quota widening, quoted +1/hash false positives or stale-ACL access |
| F22 | Differentiate lost wake from durable event loss; outbox/dedupe and poison-label quarantine | Council review | SLAB-007, SLAB-010, SLAB-036 | Commit/publish failure, visible poison path and downstream receipts |
| F23 | ResultCheck declares percent-change estimand; per-pair versus aggregate percent are not interchangeable | Science review | SLAB-022 | Aggregation/zero-denominator tests and explicit estimand |
| F24 | Temperature comparisons share a declared color scale; robotics physics never substitutes thermal evidence | Science review | SLAB-025, SLAB-026 | Visual scale and physics-source assertions |
| F25 | Artifact DAG/provenance/exchange/memory are prior ScienceClaw work, not claimed SentiLab novelty | Technology paper review | SLAB-012, SLAB-029 | Primary-paper attribution and measured differential-contribution claims |
| F26 | Current code contains web frontend; old snapshot missing frontend is not a current repo claim | Root independent GitHub verification | SLAB-002, SLAB-025 | Pinned current frontend inventory and reuse decision |
| F27 | Known cached-council analysis is complete; retrieval/current-deployment/external approval boundaries remain explicit | Science review | SLAB-001, SLAB-010 | Hashed council packet, localAppendComplete=false disclosure and deployment probes |
| F28 | Existing sys_micro150.cfg defines8chips/680W/50mm/matrix; oracle still hard-wired to six-chiplet Ascend910 | Canonical addendum | SLAB-002, SLAB-005, SLAB-006 | Existing config parameterized and pinned; original temperature claims not presumed reproduced |
| F29 | Current TAP uses chip-layer grid peak; proposed eight-chiplet primary change requires G1/version approval | Canonical addendum | SLAB-005, SLAB-006, SLAB-025 | Correct layer/statistic and approved primary/diagnostic labels |
| F30 | Current TAP wirelength_mm is weighted mean; proposed raw-sum proxy requires explicit version/units/threshold reconciliation | Pinned canonical source review | SLAB-005, SLAB-006 | Fixed-matrix relative equivalence and absolute-threshold conversion tests |
| F31 | Account existing initialization/shared samples; reuse atomic run-JSON/recovery while replacing process-local coordination and local-only auth | Pinned canonical source review | SLAB-008, SLAB-020, SLAB-036 | All evaluation work counted; durable coordination and actual per-principal AIdenID start-grant checks |

## External Warden proposals pending scoped approval

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| N01 | Peer-proposed hands-off live ticket→box→ResultCheck→approved merge→signed record→live interface within approved scope | Warden reply 03:29:33Z; PEER_PROPOSED | SLAB-001, SLAB-037 | Scoped +1 followed by authentic autonomous live trace |
| N02 | Peer-proposed AI-off deterministic baseline/evaluator/ResultCheck still populates live demo | Warden reply; PEER_PROPOSED | SLAB-020, SLAB-025, SLAB-037 | Model-disabled positive control; no fabricated model judgments |
| N03 | Choose cheapest role model that passes a measured calibration set | Warden reply; PEER_PROPOSED | SLAB-003, SLAB-013, SLAB-014 | Per-role calibration results and capability/price rationale |
| N04 | One named owner and contract per solver I/O, flight record and ResultCheck seam | Warden reply; PEER_PROPOSED | SLAB-001, SLAB-005, SLAB-007, SLAB-022 | Accepted seam owners and versioned contracts before parallel boxes |
| N05 | Two technical +1s proposed from claude-warden/pocket-forge on exact revision; none currently granted | Warden reply; PEER_PROPOSED | SLAB-001 | Actual authorized exact-revision approvals; owner release still required |
| N06 | Proposed Astra plan/parity, Forge architecture/visual and ops Warden release; agent Aneta participation authorized, human lane pending | Warden reply; PEER_PROPOSED | SLAB-001, SLAB-029 | Authorized role assignment; no inferred shipping permission |

## Actual external review R1–R14: draft-0.4 response

Source: #55936 authorizes agent participation; #55938, event 692e6796-eb6e-420a-837d-aa53f2bd771f, explicitly says no +1 yet. Full text is in .sentinelayer/sentilab-planning/gpt-astra-carter/draft03-remote-verification.json. [ANETA-REVIEW-RESPONSE.md](ANETA-REVIEW-RESPONSE.md) records the scientific response. One-seed, adapter-removal and Isaac/Newton cuts remain owner-only proposals and are not applied.

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| R01 | Fixed8/lab in isolated/shared arms including reproduction; updated7search+1reproduction proposal | Actual external review R1; P5 reconciliation | SLAB-020, SLAB-032, SLAB-041 | 32 inclusive equal table; adaptive reallocation separate ablation |
| R02 | n=12 families with two paired seeds retained; preregister metric/test/ties/multiplicity/resource cuts and single-lead selection | Actual external review #55938; adopted controls pending +1 | SLAB-020, SLAB-021, SLAB-032 | Frozen family-level analysis and owner-approved reduction policy; no silent one-seed cut |
| R03 | Training-family headroom diagnostic before LLM experiment spend; long SA is CPU-capped proposed best-known reference | Actual external review #55938; adopted controls pending +1 | SLAB-039 | Random/heuristic/short-SA measurements, numerical margin and measured CPU cap; no optimum claim or held-out leakage |
| R04 | Inspect center mapping/interpolation; finer-grid recheck/tie margin and distinct replay/cross-check/analytic labels | Actual external review #55938; adopted controls pending +1 | SLAB-006, SLAB-015 | Mapping/refinement evidence and scoped verification-tier records |
| R05 | Same decoder; parse/geometry-wire/simulator-improvement tiers; label_source plus verification_scope; eligible-data readiness | Actual external review #55938; adopted controls pending +1 | SLAB-016, SLAB-017, SLAB-019, SLAB-021, SLAB-032 | Non-formatting worker metrics, mixed-label provenance and frozen minimum eligible data count/diversity |
| R06 | Arm/family/seed namespaces; lab isolation; training-only calibration; randomized family-blocked run order; failure/rerun rule | Actual external review #55938; adopted controls pending +1 | SLAB-010, SLAB-013, SLAB-020, SLAB-032 | Reset runtime memory with retained audit history and no cross-run leakage |
| R07 | Parameterize and validate located micro150 config/power/matrix before first eight-chiplet frozen contract | R7 corrected by canonical addendum | SLAB-002, SLAB-005, SLAB-006 | Existing config reused, missing oracle wiring fixed under approval; historical values separately verified |
| R08 | Jev only compiles goal/intake routes; labs originate scientific trajectories independently of build tickets | Actual external review #55938; adopted controls pending +1 | SLAB-011, SLAB-013 | Decision-originator logs and router authority-negative tests |
| R09 | AcceptanceGate deterministic service distinct from ops Warden; each seam requires authorized nonauthor review | Actual external review #55938; adopted controls pending +1 | SLAB-001, SLAB-007, SLAB-008 | Separate identities/authority and author-reviewer matrix; no self-issued independent +1 |
| R10 | Bounded live autonomy between named human releases; actual private box-to-GB10/Qwen path and labeled AI-off data | Actual external review #55938; adopted controls pending +1 | SLAB-001, SLAB-004, SLAB-025, SLAB-029, SLAB-037, SLAB-038 | Reachability/authentication receipts and owner dependencies; no blanket shipping approval |
| R11 | Reply/action gap coverage; ticket-scoped admission and TTL/renewal proof; UTC expiry tests; hashed canonical files | Actual external review #55938; adopted controls pending +1 | SLAB-001, SLAB-009, SLAB-036 | Actual review reply delivered, grant scope/expiry checks and DST-safe timers; no trust in rewritten room body |
| R12 | Typed size-bounded deterministic ResultCheck; quarantine outside text; separate reviewed literature intake; signing key/secret controls | Actual external review #55938; adopted controls pending +1 | SLAB-007, SLAB-016, SLAB-022, SLAB-035 | No automatic external instructions/training; numeric conformance and redacted publication artifacts |
| R13 | Claude and Gemini routes separately pending; no unapproved substitute; prove shared Qwen reachable from actual boxes | Actual external review #55938; adopted controls pending +1 | SLAB-003, SLAB-033, SLAB-038 | Authorized model/entitlement probes and private serving route; owner decides cuts |
| R14 | Orthogonal lifecycle/validity/verification; ownChecks AND OR-of-AND supports; compatible context; no cyclic self-proof; every trained_on input taints descendants | Actual external review #55938; adopted controls pending +1 | SLAB-007, SLAB-010, SLAB-016, SLAB-019, SLAB-027, SLAB-033 | Golden support/visibility fixtures and trained-input quarantine; immutable event projection |

## Later P1–P11 and canonical-source corrections: draft-0.5

Source: draft04-remote-verification.json decisionPosts #55967/#55989 and full reviewerActions; independently checked in [CANONICAL-ADDENDUM.md](CANONICAL-ADDENDUM.md). Q IDs map to Aneta P1–P11 because P01–P04 already identify original project requirements. These are planning corrections, not issued releases. [MODEL-ROUTING-PROPOSAL.md](MODEL-ROUTING-PROPOSAL.md) remains supplementary and uncalibrated.

| ID | Requirement | Source | Draft tickets | Required acceptance evidence |
|---|---|---|---|---|
| Q01 | P1: truthful deadline progress submission independent of missing optional/required implementation, without claiming full completion | Actual later review/canonical addendum; approval pending | SLAB-001, SLAB-028, SLAB-029 | Remove any non-core ticket and deadline reporting still has a path; D00–D07 omissions stay incomplete |
| Q02 | P2: base UI/correction drill independent of robotics code; mandatory robotics delivery remains tracked | Actual later review/canonical addendum; approval pending | SLAB-025, SLAB-026, SLAB-027 | Correction fixture runs with no robotics code; no owner-unapproved scope cut |
| Q03 | P3: preserve complete candidate evidence under immutable task; exact-parent delta materialization and current-board atomic comparison | Actual later review/canonical addendum; approval pending | SLAB-005, SLAB-007, SLAB-008 | Concurrent known-parent candidates retained, authority rechecked, CAS comparison retry not simulator rerun |
| Q04 | P4: empirical short-search gap to best found exceeds frozen k×mesh error; diagnostic CPU/runtime cap | Actual later review/canonical addendum; approval pending | SLAB-039, SLAB-041 | Training-only staged diagnostic, explicit cost/repetitions/k and no optimum assertion |
| Q05 | P5: keep32 inclusive of reproduction; equal28+4 aggregate /7+1 per lab is a freeze proposal | Actual later review/canonical addendum; approval pending | SLAB-020, SLAB-032, SLAB-041 | Arm allocation/initialization/cache/failure/cross-architecture charging table approved |
| Q06 | P6: one primary endpoint per question; fixed corpus learning primary and closed-loop B4 required secondary | Actual later review/canonical addendum; approval pending | SLAB-021, SLAB-032, SLAB-041 | Frozen hypothesis/multiplicity table; deterministic hidden corpus with no training exposure |
| Q07 | P7: gate-scoped +1 covers named ticket set under aggregate cap; actual owner spend/cut approval pending | Actual later review/canonical addendum; approval pending | SLAB-001, SLAB-036, SLAB-041 | One release starts its named scope; missing caps/expiry fail closed; no repetitive prompts |
| Q08 | P8: remove incidental thermal/MCP/Jev/robotics/preference-judge prerequisites while preserving final integrations | Actual later review/canonical addendum; approval pending | SLAB-012, SLAB-013, SLAB-016, SLAB-018, SLAB-019, SLAB-020, SLAB-022, SLAB-023, SLAB-025, SLAB-027, SLAB-041 | Independent ResultCheck vectors, standalone smoke/SFT, deterministic routes and fixture UI paths |
| Q09 | P9: measure GB10 latency/throughput/overnight access/private path and device contention schedule | Actual later review/canonical addendum; approval pending | SLAB-004, SLAB-018, SLAB-033, SLAB-038 | Required call count×measured latency fits approved window; mutually bounded training/serving/rendering slots |
| Q10 | P10: scientific family/provider independence is distinct from nonauthor implementation review | Actual later review/canonical addendum; approval pending | SLAB-003, SLAB-014 | Single role manifest with qualification of shared-family reviewers; no silent lead substitutes |
| Q11 | P11: verify/disable OpenResearch telemetry before nonpublic data and document effective setting/data flows | Actual later review/canonical addendum; approval pending | SLAB-012, SLAB-035 | Exact supported setting and effective-config evidence; no assumed all-egress disabling |
| C01 | Service authenticity needs independently pinned trust root and scoped delegation, beyond valid signatures under embedded keys | Actual later review/canonical addendum; approval pending | SLAB-007, SLAB-028, SLAB-034, SLAB-040 | Forged/re-signed/unknown-root/wrong-scope/expired/revoked negative fixtures and fail-closed signing |
| C02 | Micro150 config exists, but oracle wiring and original temperatures are not verified by its existence | Actual later review/canonical addendum; approval pending | SLAB-002, SLAB-005, SLAB-006 | Pinned source plus new task/evaluator integration and independent numerical evidence |
| C03 | Grid-peak primary with center diagnostics is a proposed G1 change, not approved metric or continuous physical die peak | Actual later review/canonical addendum; approval pending | SLAB-005, SLAB-006, SLAB-021, SLAB-025 | New approved metric/evaluator and mapping/convergence checks |
| C04 | Current POST/replay/finish-only UI lacks autonomous durable conductor and incremental event delivery | Actual later review/canonical addendum; approval pending | SLAB-025, SLAB-036, SLAB-037 | Durable scheduler/run recovery/event feed with measured SSE or safe-polling contract |
| C05 | HotSpot C/SuperLU build permits ARM attempt but Haswell/native dependencies/architecture remain unproved | Actual later review/canonical addendum; approval pending | SLAB-004, SLAB-006, SLAB-015, SLAB-038 | Approved ARM preflight with independent binary pin and matched-model tolerance |
| C06 | Peer-reported tests/manifest changes/contract-vector counts remain attributed unless independently reproduced | Actual later review/canonical addendum; approval pending | SLAB-002, SLAB-007, SLAB-022, SLAB-029 | Source/verification ledger separates code inspection, peer reports and actual execution |
| C07 | Positive per-current-board margin is order-dependent; G1 chooses sequential semantics or deterministic batch/epoch ranking | Actual later review/canonical addendum; approval pending | SLAB-005, SLAB-008, SLAB-020, SLAB-041 | Recorded comparison reference/order/tie/margin; no claim CAS guarantees globally best completed candidate |

## Superseding requirements and unresolved release decisions

- Reported 293 hash matches, 16 tests, nine finalist reproductions, 680 W and 114.82°C/105.28°C authored layouts remain historical claims until reproduced. Their 9.54°C difference is not an agent gain. Source/live build identity does not establish current numerical validity.
- Latest GB10 evidence: reachable 10.29.169.231, key login Permission denied. No training/serving is inferred. Local cached-council analysis is complete; current deployment, external reconciliation and +1 remain pending.
- U supersedes optional OpenResearch and H100-only/GB10-inference-only scope. GB10 training, OpenResearch, exact Microduck approach and MCP plus CLI for every capability remain requirements.
- G3a fits/selects using train/validation only. G3b freezes selected artifact/memory/settings before untouched held-out fixed-corpus and closed-loop evaluation. G4 promotes separately. Failed test results cannot justify tuning on that same test. Preserve all outcomes without training on all of them.
- RLAIF JSONL is required; an additional preference optimizer needs scoped approval. Any compatible adapter merge is a new evaluated artifact.
- Jev proposes routing; OpenResearch hosts research. Preserve the council-adopted L3/principal-delta draft without claiming owner approval, deployed completeness or 95% recall.
- The current freeze proposal retains two seeds and 32 bundles per family/seed/arm (3,840 total), inclusive of proposed 28 search + 4 reproduction. Final charging and caps require approval; no owner-unapproved one-seed cut or outside-budget reproduction. Null caps mean blocked, not unlimited.
- Do not replace exact Microduck with a generic robot UI without +1. RTX Spark, DGX Spark and Dell GB10 are distinct; H100/A100 are not Isaac Sim rendering substitutes. Asset rights and exact platform/model recipe need proof.
- Warden's two technical +1s, live-loop/AI-off and ownership are tracked proposals, not blanket shipping authorization. No actual +1 exists for this draft.
- Official Sunday Nov 1 13:00 America/New_York deadline, team size and rubric were source-verified; actual team registration and sponsor prize split/forms remain unconfirmed. Do not invent Friday 22:00 registration or eligibility.
- Clarify any additional jurisdiction-specific legal scope. Geometric legality, scientific validity and license/terms provenance are covered without legal-certification claims.

## Coverage invariant

Tracked requirements: **234**. Draft tickets: **41**. All original audit IDs and D00–D07 remain mapped. Every requirement has tickets and planned evidence; dependencies, JSON, both transports and HOLD status must be validated. Reaudit after each approved scope change. Current verdict: **DRAFT / HOLD**.

