# SentiLab ticket index — draft-0.5 / HOLD

41 draft tickets; no remote tickets or execution are released. A scoped +1 may cover named tickets together under an aggregate cap and expiry. These are proposed interfaces, not existing capabilities. Full machine-readable definitions: TICKETS.json. Model candidates: MODEL-ROUTING-PROPOSAL.md.

## SLAB-001: Reconcile council, peer authority, source packet and explicit +1 gates

Gate: G0. Proposed owner: Planning lead; authorized independent peer; owner/carther. Dependencies: none.

Complete source/council hydration, approval semantics, objections and revision-bound ticket release. Record #55936 participation authorization and #55938 no-approval review. Assign a nonauthor reviewer per seam; owner releases remain required. Canonical specs are hashed files, room posts pointers. A single gate-scoped release may name multiple tickets with one aggregate cap/expiry. Separate truthful deadline reporting from full D00-D07 completion.

CLI: sentilab plan export; sentilab approval inspect.

MCP: sentilab_plan_export; sentilab_approval_inspect.

Required acceptance evidence:

- Full source packet and council coverage/gaps
- Verified peer authorization; no inferred Aneta commitment
- Named +1 or explicit HOLD per revision; no remote tickets created before release
- Actual reviewer participation distinguished from human time/spend and exact-revision +1; no author approves own seam as independent reviewer.

## SLAB-002: Pin canonical Thermal Flight Lab source and reproduce existing claims

Gate: G1. Proposed owner: Scientific engineering owner. Dependencies: SLAB-001.

Inventory canonical checkout, snapshot and previous artifacts; retain verified code and contribution history. Reuse located sys_micro150.cfg8chiplet680W config; oracle is still Ascend910-wired. Treat reported55tests/manifest changes as peer reports until reproduced.

CLI: sentilab source inspect; sentilab regression run.

MCP: sentilab_source_inspect; sentilab_regression_run.

Required acceptance evidence:

- Canonical repo/ref and file manifest
- Fresh controller/numerical regression logs; nine-finalist claim checked if artifacts available
- Reported historical claims clearly separated from current evidence
- Current web frontend reused where appropriate; four/six-chiplet existing domains distinguished from missing requested eight-chiplet680W fixture

## SLAB-003: Verify box/model catalog and obtain missing Claude capability

Gate: G1. Proposed owner: Capability/catalog owner; carther supplies authorization. Dependencies: SLAB-001.

Inspect available model endpoints, quotas and tools; request exact Claude model/route from carther without exposing credentials. Gemini is absent from the reported catalog and needs its own authorized route or owner-approved change; do not silently substitute another model family. Calibrate roles on training families only.

CLI: sentilab model list; sentilab model probe.

MCP: sentilab_model_list; sentilab_model_probe.

Required acceptance evidence:

- Actual returned-model ID, allowed tools, quota and probe results per endpoint
- Claude request/response with exact model/version; no assumed local proprietary weights
- Role-to-capability assignment and approved usage ceilings
- Peer-reported catalog independently probed; cheapest qualifying model selected by per-role calibration; no secret requested in chat
- Separate Claude/Gemini entitlement status and owner decision deadlines; actual Qwen serving endpoint available to authorized boxes.

## SLAB-004: Complete GB10 key access and inventory compatible compute

Gate: G1. Proposed owner: GB10 platform owner. Dependencies: SLAB-001.

Verify passwordless access after the user's local authentication step; inventory ARM/GPU/driver/container/disk resources and distinguish rendering from training needs.

CLI: sentilab doctor --host gb10.

MCP: sentilab_doctor.

Required acceptance evidence:

- Successful authorized login and identity probe or exact blocker
- Hardware/OS/driver/container inventory with versions
- Separate approved training/rendering memory/runtime caps; no assumed H100 rendering compatibility

## SLAB-005: Freeze geometry, units, thermal objective and fixed wire budget

Gate: G1. Proposed owner: Scientific contract owner. Dependencies: SLAB-002.

Implement proposed task/geometry contract only after approval; center versus lower-left conversion, grid/gaps, scenario metric and initial-layout Manhattan cap. G1 decides new grid-peak primary/center diagnostics and explicitly pins version; no approved metric switch inferred. Full absolute candidates use fixed task/x0 constraints; deltas materialize exactparent.

CLI: sentilab contract validate; sentilab geometry check.

MCP: sentilab_contract_validate; sentilab_geometry_check.

Required acceptance evidence:

- Schema and valid/invalid geometry fixtures
- Coordinate/units/rotation/clearance tests and fixed-baseline wire budget proof
- Frozen objective, scenario manifest and zero-baseline/interconnect policy
- G1 chooses sequential threshold semantics with ordering limitation or deterministic batch/epoch selection using common schedule/frozen comparison reference; CAS alone not claimed best-candidate selector.

## SLAB-006: Version reference thermal evaluator and numerical uncertainty checks

Gate: G1. Proposed owner: Thermal/numerical owner. Dependencies: SLAB-002, SLAB-005.

Wrap the existing verified evaluator with pinned scenarios, correct temperature layer/statistic, raw artifacts and numerical convergence analysis. Parameterize actual micro150 config rather than recreating unknown powers. Preserve all-layer/chip-layer metric identity; proposed primary switch needs G1. C source enables an ARM preflight but proves no architecture compatibility.

CLI: sentilab evaluate; sentilab evaluator inspect.

MCP: sentilab_evaluate; sentilab_evaluator_inspect.

Required acceptance evidence:

- Power/energy/symmetry/zero-power and malformed-input checks
- Convergence/sensitivity evidence and approved acceptance margin/tolerance
- Complete per-scenario raw outputs with correct field/layer labels and no manufactured-device claim
- Existing TAP grid-peak versus new center metric and weighted-mean versus raw-sum wire proxy explicitly reconciled/versioned
- Persist exact generated simulator inputs and raw outputs before TemporaryDirectory cleanup; prove readback after cleanup and fail evidence completeness when files are missing or corrupt.
- Current converged=True indicates output validation only; demonstrate numerical convergence independently using the approved resolution/refinement checks.

## SLAB-007: Implement typed result contract, event recorder and artifact manifests

Gate: G1. Proposed owner: Evidence-contract owner. Dependencies: SLAB-009.

Version result/events with input/parent/model/runtime pins, raw artifact hashes, units, costs and correction lineage. Split lifecycle, validity and verification_tier; add metric_id/evaluator_version/coordinate_frame and immutable correction events. Generic evidence/receipt contracts do not import thermal code. Distinguish internal integrity, externally anchored service origin and scientific verification.

CLI: sentilab result inspect; sentilab event export; sentilab artifact verify.

MCP: sentilab_result_inspect; sentilab_event_export; sentilab_artifact_verify.

Required acceptance evidence:

- Canonical serialization/hash/schema tests
- Request/candidate/parent/status/scenario completeness checks
- Append-only events and actual signature/checkpoint verification procedure
- Named seam owner; retention or authorized tombstone policy; outbox/event/receipt distinctions
- Artifact manifest binds actual retained generated inputs, raw outputs and stdout/stderr; persistence completes and verifies before temporary-directory cleanup. Hashes, extracted fields or summaries alone do not satisfy D02.
- Golden fixtures express accepted-but-stale with preserved reproduction tier; live and replay use the same pure event projection and reject incompatible contexts.
- Authenticated event writer/admission; equal-position replay deterministic or rejected; withdrawn review covers cannot remain active.
- Verification tier cannot arise from empty/self evidence. Unsupported claims remain unverified; validated atomic evidence types are explicitly defined.

## SLAB-008: Enforce deterministic AcceptanceGate permissions, budgets and atomic admission

Gate: G2. Proposed owner: Execution governance owner. Dependencies: SLAB-005, SLAB-006, SLAB-007, SLAB-015.

Implement durable deterministic AcceptanceGate preserving current known-parent materialization and current-best comparison. Complete fixed-task candidate measurements survive board advancement; delta actions materialize their exact parent. Recheck current authority/STOP/context, atomically compare against current board, and retry only the comparison after CAS loss. Retain numeric evidence and lineage; no duplicate simulator charge. Reuse atomic run-JSON/recovery, replace process-local coordination/per-principal authorization gaps. No LLM in AcceptanceGate.

CLI: sentilab candidate submit; sentilab board inspect; sentilab approval apply; sentilab job cancel.

MCP: sentilab_candidate_submit; sentilab_board_inspect; sentilab_approval_apply; sentilab_job_cancel.

Required acceptance evidence:

- Exact-parent delta versus complete-candidate fixtures; old known parent not rejected merely for newer board
- Current-board CAS/retry with immutable numeric evidence, current grants/STOP and exactly-once job accounting
- G1-selected sequential or batch margin semantics tested; best eligible/reproduced candidate reported separately from robust accepted improvements
- Hard constraints, missing reproduction and stale scientific evidence still block admission; actual per-principal authorization
- Positive minimum margins can make sequential selection order-dependent; never promise current-board CAS chooses globally lowest completed result.

## SLAB-009: Provide shared CLI and MCP contract/transport foundation

Gate: G1. Proposed owner: Tooling/API owner. Dependencies: SLAB-001.

One domain implementation and versioned JSON contracts behind CLI and MCP, including auth, errors, status/cancel and idempotency.

CLI: sentilab capabilities; sentilab job status; sentilab job cancel.

MCP: sentilab_capabilities; sentilab_job_status; sentilab_job_cancel.

Required acceptance evidence:

- Capability registry with both transports
- Shared positive/negative contract fixtures and compatible JSON error codes
- No bypass through alternate transport and no credentials in outputs

## SLAB-010: Integrate council-compliant ENGRAM and evidence invalidation

Gate: G2. Proposed owner: Memory/evidence owner. Dependencies: SLAB-001, SLAB-007, SLAB-009.

Preserve deterministic L3/principal delta design, source refs/ACL epoch/coverage/raw expansion; add required scientific dependency semantics without assuming a new graph-selector/vector/Kafka architecture. Use arm/family/seed namespaces and isolated lab subnamespaces with reset runtime retrieval state but retained audit history. Sufficient supports are ownChecks AND OR-of-AND clauses, with compatible contexts and no cyclic self-proof.

CLI: sentilab memory recall; sentilab memory snapshot; sentilab evidence invalidate; sentilab evidence inspect.

MCP: sentilab_memory_recall; sentilab_memory_snapshot; sentilab_evidence_invalidate; sentilab_evidence_inspect.

Required acceptance evidence:

- Source-pinned council adopt/change/defer ledger; completeness and recall claims measured
- Isolated namespace/cache/reviewer transcript tests; frozen snapshot restoration
- Direct/transitive stale propagation, alternative support preservation and checkpoint A/B recovery checks
- Maximum validated covered-through, separate delivered/scanned/processed cursors, missing-middle metadata and checkpoint C poison-label validation/quarantine
- Claim scientific validity separate from principal visibility; one entire current authorized support clause is required for audience use, never mixed partial clauses. Taint follows every actual trained_on input independently of alternate claim support.
- Cycle/self-loop-safe trained_on and recursive contains handling; every actual ineligible training input taints descendants regardless of alternate OR support.
- Cross-check context compatibility in each support clause and retain deterministic order without a test harness rewriting source sequence IDs.

## SLAB-011: Integrate Jev intent and calibrated capability routing

Gate: G2. Proposed owner: Intent/routing owner. Dependencies: SLAB-001, SLAB-003, SLAB-005, SLAB-009, SLAB-010.

Use Jev for versioned intent/routing with abstention and approved model/tool capabilities; preserve mandatory constraints and ACL. Reuse the existing jev-1.13.0/SystemOne seam after actual runtime capability, identity, access and schema proof. Jev compiles goal/contracts and routes intake only; labs choose hypotheses and trajectories, with decision originator recorded. Build tickets never prescribe the scientific search. Initial labs can use deterministic allowlisted routing before Jev integration; this does not remove the required Jev work.

CLI: sentilab intent compile; sentilab route evaluate.

MCP: sentilab_intent_compile; sentilab_route_evaluate.

Required acceptance evidence:

- Held-out routing precision/abstention results
- Mandatory-context stripping, unauthorized tools and inferred +1 negative tests
- Frozen route policy and source-backed explanation; OpenResearch role remains distinct
- Canonical Jev seam present is distinguished from a verified endpoint; actual model identity/access/contract/calibration evidence is required.

## SLAB-012: Run OpenResearch literature, prior-work and reproduction audit

Gate: G1. Proposed owner: Research owner. Dependencies: SLAB-001, SLAB-003.

Make OpenResearch a named-model research workspace; inspect ScienceClaw/Infinite and relevant thermal, experimental and reference-work methods. Verify supported OpenResearch telemetry controls and disable telemetry before any nonpublic inputs under configured approval. Cited notes carry no acceptance authority.

CLI: sentilab research request; sentilab research status; sentilab research export.

MCP: sentilab_research_request; sentilab_research_status; sentilab_research_export.

Required acceptance evidence:

- Actual workspace/run/export with underlying model identity
- Primary-source claim/evidence ledger, counterexamples and source limitations
- Artifact/reproduction integration recommendation and documented expert methods
- Document exact telemetry setting, effective configuration and nonpublic data flows; no unsupported assumption that one flag stops every external path.

## SLAB-013: Wire four scientists and bounded worker orchestration

Gate: G2. Proposed owner: Lab orchestration owner. Dependencies: SLAB-003, SLAB-005, SLAB-008, SLAB-010, SLAB-038, SLAB-039, SLAB-037.

Create four authorized lead roles with explicit specialties, two-worker concurrency limit, independent contexts and declared budgets. Deterministic routing supports first labs without waiting for Jev; scientific choices remain in labs.

CLI: sentilab lab start; sentilab lab status; sentilab candidate propose.

MCP: sentilab_lab_start; sentilab_lab_status; sentilab_candidate_propose.

Required acceptance evidence:

- Astra/Claude/Grok/Kimi exact model manifests and scientific role cards
- Four real proposal/critique/evaluation traces with separate identities
- Concurrency, identity, context and per-arm shared-budget enforcement
- Scientific decision-originator records; training-only model calibration; authenticated shared worker route from actual box.
- Required lab autonomy connects to the already running deterministic conductor; AI-off operation does not wait for lab/model availability.

## SLAB-014: Implement adversarial review protocol and calibrated LLM judges

Gate: G2. Proposed owner: Independent review owner. Dependencies: SLAB-003, SLAB-005, SLAB-007, SLAB-012.

Independent first reviews over identical packets, structured objections/resolution criteria, distinct judge/acceptor roles and consistent benchmark assistance.

CLI: sentilab review request; sentilab review reconcile.

MCP: sentilab_review_request; sentilab_review_reconcile.

Required acceptance evidence:

- Independent initial Gemini/DeepSeek and authorized peer review records
- Counterexample-to-executable-check closure and unresolved-objection ledger
- Model/settings/order-bias calibration; no failed constraint overridden by rhetoric
- Role manifest separates nonauthor code review from scientific model-family/provider independence; required Claude/Gemini families not silently substituted.

## SLAB-015: Build fresh-process reproduction service

Gate: G2. Proposed owner: Independent reproduction owner. Dependencies: SLAB-005, SLAB-006, SLAB-007.

Reproduce from delivered inputs and declared dependencies in a clean process/environment, labeling operational versus numerical independence. Optional approved cross-architecture reproduction may compile HotSpot C for ARM with independently pinned native dependencies; source availability alone is not compatibility or physical validation.

CLI: sentilab reproduce; sentilab reproduction inspect.

MCP: sentilab_reproduce; sentilab_reproduction_inspect.

Required acceptance evidence:

- Input/artifact hash binding and runnable reproduction command
- Separate identity/process/environment provenance
- Frozen tolerance comparison including missing dependencies, corrupt outputs and mismatch failures

## SLAB-016: Build raw experiment and eligible training JSONL datasets

Gate: G2. Proposed owner: Dataset/provenance owner. Dependencies: SLAB-005, SLAB-007, SLAB-035.

Retain all outcomes while constructing immutable eligible SFT/repair manifests with family splits, provenance and corrections. Eligibility can operate on immutable verifier receipts before ENGRAM integration; final memory/lineage integration remains required.

CLI: sentilab dataset export; sentilab dataset validate; sentilab dataset freeze.

MCP: sentilab_dataset_export; sentilab_dataset_validate; sentilab_dataset_freeze.

Required acceptance evidence:

- Raw success/failure/rejection/cancellation JSONL schema
- Family-level deduplication, leakage and license/eligibility checks
- Frozen train/validation/test manifests and no invalid-action-as-target contamination
- Minimum unique eligible example count/diversity and readiness threshold frozen before fitting; under-threshold pipeline has no learned-engineering claim.

## SLAB-017: Export RLAIF preference JSONL with verifier-grounded judgments

Gate: G2. Proposed owner: RLAIF/judge-data owner. Dependencies: SLAB-014, SLAB-016.

Persist blinded preference/tie/abstention records with judge identity, rubric and deterministic outcomes; actual preference optimization requires a separate +1.

CLI: sentilab judge compare; sentilab dataset export --kind rlaif.

MCP: sentilab_judge_compare; sentilab_dataset_export.

Required acceptance evidence:

- Versioned chosen/rejected/tie/abstention schema with source hashes
- Order-bias/self-preference/reward-hacking fixtures and disagreement retention
- Hard numerical constraints override preference; no hidden reasoning required
- label_source and verification_scope separate deterministic schema/geometry/wire/simulator evidence from LLM/mixed preferences; geometry-only verification is not a thermal-improvement claim.

## SLAB-018: Prove GB10 NeMo train-save-reload preflight

Gate: G1. Proposed owner: ML/GB10 owner. Dependencies: SLAB-004, SLAB-035.

Validate an exact approved GB10/NeMo/model recipe on permitted fixtures; do not combine general and Spark recipes or silently replace Qwen3-4B. Standalone tiny permitted-fixture NeMo smoke test does not require thermal code or MCP registry. Final wrapper parity remains required later.

CLI: sentilab train preflight; sentilab train status; sentilab checkpoint inspect.

MCP: sentilab_train_preflight; sentilab_train_status; sentilab_checkpoint_inspect.

Required acceptance evidence:

- Pinned model/tokenizer/container/source/driver recipe and license
- Approximately 20-step actual GB10 training, adapter save and fresh-process reload/inference
- Checkpoint identity proof and measured resource use; alternatives require scoped +1
- Spark-specific NeMo26.08/source pin/Qwen3-8B reference kept distinct from general26.10/Qwen3-4B; exact chosen recipe requires +1
- Measure inference latency/tokens-per-second, warmup/memory and planned device contention; no training/serving/rendering concurrency assumed.

## SLAB-019: Train candidate GB10 adapter and select using validation only

Gate: G3a. Proposed owner: ML/serving owner. Dependencies: SLAB-018, SLAB-016, SLAB-041.

Fit the candidate adapter on eligible training data and select using validation only; freeze selected artifact before any held-out exposure. Base weights remain unchanged. Held-out evaluation/promotion are separate tickets. Verifier-grounded SFT does not depend on RLAIF judges, preferences or an optimizer; those remain separate required work. Preregister data splits before fitting.

CLI: sentilab train start; sentilab train cancel; sentilab checkpoint select; sentilab checkpoint inspect.

MCP: sentilab_train_start; sentilab_train_cancel; sentilab_checkpoint_select; sentilab_checkpoint_inspect.

Required acceptance evidence:

- Actual GB10 train/validation logs, resource caps and immutable eligible dataset manifest
- Selected adapter/base/tokenizer/chat-template/module/rank/precision hashes and fresh reload proof
- No held-out data access or test-driven tuning; arbitrary incompatible adapter merges refused

## SLAB-020: Preregister benchmark protocol and implement five-arm runner

Gate: G3a. Proposed owner: Experimental design/runner owner. Dependencies: SLAB-005, SLAB-006, SLAB-010, SLAB-013, SLAB-014, SLAB-016, SLAB-039, SLAB-041.

Implement five-arm runner from early preregistration/splits. Keep32 inclusive with proposed28search+4reproduction in B0/B1 and7+1 each lab in B2/B3/B4; no transfer in primary contrast. Retain two seeds and all five arms. Freeze all initialization/cache/failure charges, randomized blocked order and G1-selected admission scheduling. Run held-out only after separate release.

CLI: sentilab benchmark validate; sentilab benchmark freeze; sentilab benchmark run; sentilab benchmark status.

MCP: sentilab_benchmark_validate; sentilab_benchmark_freeze; sentilab_benchmark_run; sentilab_benchmark_status.

Required acceptance evidence:

- Approved 3840-versus-1920 bundle interpretation with no per-lab multiplier
- Frozen split, seeds, prompts, model/runtime/memory configs and primary contrasts
- B0–B4 runner with failures/retries/reproductions counted and no data leakage
- Starting-layout initialization and shared samples outside existing proposal counters included in frozen aggregate accounting
- Fixed per-lab search/reproduction allocation removes evidence-sharing versus adaptive-budget confound; no owner-unapproved seed/model/adapter cuts.
- B0-B4 equal inclusive allocation table; reproduction is not silently moved outside32. Per-current-board margin order effects or deterministic epoch rule disclosed.

## SLAB-021: Analyze family-level results and enforce honest claims

Gate: G3b. Proposed owner: Statistics/claims owner. Dependencies: SLAB-032, SLAB-022.

Analyze paired family-level sharing/weight effects, resource balance, raw outcomes, uncertainty, ties and regressions. Sharing closed-loop B2/B3 and fixed-corpus worker learning have separately declared primary endpoints; closed-loop B4 remains required secondary evidence with multiplicity handling.

CLI: sentilab compare; sentilab claim check.

MCP: sentilab_compare; sentilab_claim_check.

Required acceptance evidence:

- Family-level paired results and appropriate small-sample uncertainty
- Validity/repair/useful-proposal/J/time/cost tables with complete failed runs
- Raw-Celsius-percent trap tests and claim ledger bounded by evidence
- Three action tiers under identical decoder: parse, geometry-plus-wire, simulator improvement. Primary contrasts have preregistered multiplicity/tie handling and family-level n=12; two seeds are nested.

## SLAB-022: Ship deterministic SentiResultCheck core with MCP and CLI

Gate: G2. Proposed owner: ResultCheck owner; Aneta lane only if authorized. Dependencies: SLAB-007, SLAB-009.

Validate paired measurements, units/direction and supported arithmetic/statistics, return versioned receipts with scope limits. Numeric core accepts only typed size-bounded fields. Quarantine optional outside free text; never auto-forward to privileged tools, labs, memory or training. Separately reviewed literature intake remains allowed. Numeric ResultCheck imports no thermal contract or scientific AcceptanceGate. Independent vectors must run without thermal code.

CLI: sentilab resultcheck.

MCP: sentilab_resultcheck.

Required acceptance evidence:

- Duplicate/missing-pair/zero-baseline/NaN/unit/insufficient-data fixtures
- Independent arithmetic outputs and unsupported-inference refusals
- Identical CLI/MCP receipt semantics; no certification of authenticity/physics
- Named seam owner; explicit per-pair versus aggregate percent estimand and raw-Celsius refusal
- Oversize/type/instruction-injection fixtures; free text never becomes commands or training automatically; evaluator signing key absent from lab boxes.
- Validate byte/depth limits before canonicalization; reject oversize/deep inputs safely. Unit normalization covers Celsius aliases; tolerance is metric-specific, not a unit-blind default.
- Stable binomial/sign-test at supported large n or explicit approved cap; preserve family/cluster grouping, tie tolerances and numerical error flags. Peer reference-code bug claims require independent verification.

## SLAB-023: Connect real ResultCheck intake and authorized external pilot

Gate: G2. Proposed owner: External-service owner; human outreach owner. Dependencies: SLAB-022, SLAB-009.

Connect request consumers and receipts; recruit/use a real partner only after outreach authorization. Partner intake has its own scoped authorization/limits; it does not mutate scientific accepted state or require thermal AcceptanceGate.

CLI: sentilab resultcheck submit; sentilab resultcheck status; sentilab resultcheck receipt.

MCP: sentilab_resultcheck_submit; sentilab_resultcheck_status; sentilab_resultcheck_receipt.

Required acceptance evidence:

- Real authorized request→execution→receipt trace
- Observed downstream use with honest partner attribution
- Timeout/cancel/tenant-separation and idempotency evidence

## SLAB-024: Inspect exact Microduck reference and freeze fidelity/feasibility scope

Gate: G1. Proposed owner: Visual simulation research owner. Dependencies: SLAB-001, SLAB-004, SLAB-012, SLAB-035.

Inspect exact YouTube reference and NVIDIA primary pipeline; identify assets, hardware, versions and costs. Exact requirement stays mandatory until any narrowing is approved.

CLI: sentilab reference inspect; sentilab simulation doctor.

MCP: sentilab_reference_inspect; sentilab_simulation_doctor.

Required acceptance evidence:

- Timestamped video/source pipeline inventory and reproducible references
- RTX Spark versus GB10 distinction, ARM/Dell rendering preflight and no H100 rendering assumption
- Code/STL license manifest and explicit fidelity +1

## SLAB-025: Build event-derived chiplet, lab, evidence and comparison interface

Gate: G2. Proposed owner: Evidence/product owner; Aneta conditional on authorization. Dependencies: SLAB-005, SLAB-007, SLAB-010.

Render exact geometry, active lab state, raw-measurement/reproduction drilldown, dependencies and comparison artifacts. Base fixtures/evidence view build without robotics feasibility or code; current default replay/finish-only source is not an incremental live conductor.

CLI: sentilab view data; sentilab view export.

MCP: sentilab_view_data; sentilab_view_export.

Required acceptance evidence:

- Coordinate/metric/layer fixture validation with clearly labeled recorded fixtures
- One real candidate→measurement→reproduction→acceptance sequence
- UI transitions bound to agent/artifact/timestamp; no fabricated heatmap/activity
- Common declared color scale and existing canonical web-source reuse decision; final benchmark data connected after SLAB-021

## SLAB-026: Implement approved exact Microduck simulation workflow

Gate: G2. Proposed owner: Robotics/simulation owner. Dependencies: SLAB-024, SLAB-003, SLAB-004, SLAB-009, SLAB-035.

After explicit fidelity/resources approval, implement the reference workflow across intent, CAD/materials, USD, physics/rendering, RL and local validation as scoped. Any omission is an explicit approved change.

CLI: sentilab simulation build; sentilab simulation train; sentilab simulation replay; sentilab simulation export.

MCP: sentilab_simulation_build; sentilab_simulation_train; sentilab_simulation_replay; sentilab_simulation_export.

Required acceptance evidence:

- Pinned Hermes/Nemotron/Astra/FreeCAD/Blender/CAD/USD/Isaac/Omniverse/Newton/Isaac Lab/BAM/domain-randomization scope matrix
- Actual compatible hardware runs and asset-rights proof; no cosmetic substitute claim
- Clear distinction between robot physics and thermal evaluator; authentic replayable artifacts

## SLAB-027: Build correction drill and reproducible visual replay

Gate: G2. Proposed owner: Demo/replay owner. Dependencies: SLAB-010, SLAB-025.

Replay actual result histories and a labeled seeded evidence withdrawal, preserve unaffected support, create rebuildable backup demonstration.

CLI: sentilab replay render; sentilab replay export; sentilab correction drill.

MCP: sentilab_replay_render; sentilab_replay_export; sentilab_correction_drill.

Required acceptance evidence:

- Deterministic replay from event/artifact bundle with source pins
- Direct/transitive stale propagation and preserved alternative support visible
- Replay/time-compression/drill labels and backup export
- Thermal correction drill and base evidence replay run with no robotics code installed; mandatory robotics lane remains independently required.

## SLAB-028: Package and independently rebuild D00–D07 engineering handoff

Gate: G5. Proposed owner: Release/reproducibility owner. Dependencies: SLAB-007, SLAB-015, SLAB-019, SLAB-021, SLAB-027, SLAB-033, SLAB-034, SLAB-026, SLAB-040.

Build all eight deliverables with manifest, versions, evidence limits and reproducible commands; rebuild from only delivered contents in a fresh location. This is full project completion only: every required D00-D07 and full capability claim needs evidence. A partial deadline packet never marks this ticket complete.

CLI: sentilab package build; sentilab package verify; sentilab package export.

MCP: sentilab_package_build; sentilab_package_verify; sentilab_package_export.

Required acceptance evidence:

- D00–D07 completeness and content-hash manifest
- Fresh-location reconstruction independent of developer checkout
- Full history/contribution/provenance and limitations inspectable through both transports

## SLAB-029: Prepare truthful deadline progress submission and separately report full-completion status

Gate: G5. Proposed owner: Human presentation/submission owner; Aneta role conditional. Dependencies: SLAB-001.

At the approved deadline, collect available verified evidence, source references, failures and explicit D00-D07 omissions into a truthful deck/progress packet. This path must not depend on finishing robotics, adapter, partner or other implementation tickets. Publish only under G5 approval; no partial package is represented as full project completion, successful partnership, service authenticity or unmeasured benefit.

CLI: sentilab presentation export; sentilab submission validate.

MCP: sentilab_presentation_export; sentilab_submission_validate.

Required acceptance evidence:

- Removing any non-core implementation ticket leaves a path to truthful deadline reporting
- Evidence/claim/omission ledger labels every missing mandatory artifact incomplete and distinguishes source reports from executed results
- Approved deadline/team/sponsor details, honest deck/rehearsal records where available, and G5 release for publication
- A full-completion claim requires SLAB-028; unanchored signatures not advertised as trusted service provenance

## SLAB-030: Evaluate optional PhysicsNeMo screening extension

Gate: G5. Proposed owner: Scientific ML extension owner. Dependencies: SLAB-006, SLAB-016, SLAB-020, SLAB-028.

Deferred extension: predict chiplet-center temperatures with separate split/error controls and reference-simulator admission retained.

CLI: sentilab surrogate train; sentilab surrogate evaluate.

MCP: sentilab_surrogate_train; sentilab_surrogate_evaluate.

Required acceptance evidence:

- Separate approved scope/resource budget
- Held-out error and screening-benefit evaluation
- Every accepted candidate still verified by reference simulator

## SLAB-031: Track optional sponsor/domain/physical-design extensions

Gate: G5. Proposed owner: Extension planning owner. Dependencies: SLAB-028, SLAB-029.

Keep Nemotron critic, ALCHEMI/BioNeMo domain bridge, Formlabs geometry print and RTL-to-layout as explicit deferred tickets/subscopes, not unacknowledged omissions.

CLI: sentilab extension plan export.

MCP: sentilab_extension_plan_export.

Required acceptance evidence:

- Separate owner, budget and +1 per extension
- Defensible scientific task and primary-source/asset rights
- No printed-material thermal-validation claim or core-scope distraction

## SLAB-032: Freeze selected checkpoint and run untouched held-out comparisons

Gate: G3b. Proposed owner: Independent benchmark execution owner. Dependencies: SLAB-019, SLAB-020.

After G3a fitting/validation selection, freeze all model/memory/runtime/prompt/tool settings and execute fixed held-out action corpus plus closed-loop five-arm benchmark. Never tune or select on these results. Fixed held-out action corpus is primary for learning and generated/held by isolated deterministic infrastructure before release. Closed-loop B4 remains required secondary, not silently cut.

CLI: sentilab benchmark freeze; sentilab benchmark run; sentilab checkpoint evaluate.

MCP: sentilab_benchmark_freeze; sentilab_benchmark_run; sentilab_checkpoint_evaluate.

Required acceptance evidence:

- Selected artifact hashes, memory snapshot and complete G3b freeze receipt
- Identical fixed-corpus inputs/settings for base and adapter; matched closed-loop starting state/budgets
- Complete per-family/seed/arm raw outcomes, failures/costs and isolation proof; failed test can reject promotion only
- Same decoder for base/adapter; fixed8-per-lab allocation, arm/family/seed namespaces and randomized blocked order; provider failure/rerun and two-contrast multiplicity policies preregistered.

## SLAB-033: Approve and serve verified worker checkpoint on GB10

Gate: G4. Proposed owner: Warden/GB10 serving owner under explicit owner release. Dependencies: SLAB-019, SLAB-021, SLAB-032.

Promote the exact evaluated artifact on GB10 after explicit release; verify actual serving identity and maintain rollback/quarantine lineage.

CLI: sentilab checkpoint promote; sentilab checkpoint serve; sentilab checkpoint rollback.

MCP: sentilab_checkpoint_promote; sentilab_checkpoint_serve; sentilab_checkpoint_rollback.

Required acceptance evidence:

- Exact adapter/base/tokenizer/config hashes and serving identity match
- G4 scoped approval with held-out regressions and resource limits
- Rollback/invalidated-dataset checkpoint quarantine; no claim that deleting memory unlearns weights
- Measured worker call counts/latency and approved overnight availability/resource slots fit the actual benchmark/demo window; no unmeasured contention assumption.

## SLAB-034: Audit complete MCP/CLI parity and requirement coverage

Gate: G5. Proposed owner: Independent conformance owner. Dependencies: SLAB-009, SLAB-008, SLAB-010, SLAB-011, SLAB-012, SLAB-017, SLAB-019, SLAB-020, SLAB-022, SLAB-026, SLAB-027, SLAB-032, SLAB-033, SLAB-037, SLAB-038, SLAB-039, SLAB-040, SLAB-041.

Validate both transports for every advertised capability, including errors, authorization, output schema, jobs/cancel and immutable artifacts.

CLI: sentilab conformance run; sentilab coverage validate.

MCP: sentilab_conformance_run; sentilab_coverage_validate.

Required acceptance evidence:

- No missing capability row; identical meaningful positive/negative outcomes
- No alternate-transport permission/idempotency/cancel bypass
- Every requirement and D00–D07 maps to implemented ticket and evidence or explicit approved limitation
- Identical deterministic payloads and authorization/errors across transports; byte-identical receipt on same idempotent request only. Independent runs retain legitimate different provenance.

## SLAB-035: Review code/model/data/asset licenses and permitted-use provenance

Gate: G1. Proposed owner: Provenance/licensing owner; human legal review when needed. Dependencies: SLAB-001.

Check exact revisions and permitted use of model/dataset outputs, source code, robot assets and redistributable artifacts; clarify additional legal scope if requested.

CLI: sentilab provenance inspect; sentilab license manifest.

MCP: sentilab_provenance_inspect; sentilab_license_manifest.

Required acceptance evidence:

- License/terms manifest with sources and unresolved restrictions
- Apache-2.0 code versus CC BY-NC-SA STL separation and approved use
- Training/distribution eligibility decisions; no invented legal clearance
- Evaluator signing key stays outside lab boxes; public flight records undergo secret scan/redaction; untrusted literature uses reviewed source intake rather than a blanket ban.

## SLAB-036: Verify bounded operations, STOP, recovery and accounting

Gate: G2. Proposed owner: Runtime/reliability owner. Dependencies: SLAB-007, SLAB-008, SLAB-010.

Exercise crashes, duplicate delivery, cancellations, quota exhaustion, source withdrawal and checkpoint recovery without broadening execution permissions. Cover listen/thread-reply gap with bounded action reconciliation; verify ticket-scoped admission, actual grant renewal/replacement support and TTL. Canonical contracts use hashes/readback because room filters can rewrite text.

CLI: sentilab runtime status; sentilab runtime stop; sentilab runtime recover.

MCP: sentilab_runtime_status; sentilab_runtime_stop; sentilab_runtime_recover.

Required acceptance evidence:

- Bounded concurrency/token/time/GPU budget and stop behavior
- Replay/restart/checkpoint A/B integrity with validated coverage order
- Failure/cancel/late-completion/idempotency accounting and observability
- Actual reply wakes waiting worker; UTC grant expiry and monotonic timeout accounting across repeated DST hour; expired/missing-scope grants fail closed. No production dependency on reviewer's laptop.

## SLAB-037: Build deterministic conductor, AI-off live loop and lab integration seam

Gate: G2. Proposed owner: Proposed Forge live-design owner and Warden boxops owner; each seam named before release. Dependencies: SLAB-008, SLAB-022, SLAB-025, SLAB-036.

Build durable run/arm state, scheduler, restart recovery and incremental delivery using SSE or safe cursor polling. The deterministic AI-off live loop works without LLM labs, labels its data and respects scope/budget/STOP. Expose the integration seam consumed by SLAB-013 for later required lab autonomy; no model completion is fabricated.

CLI: sentilab live run; sentilab live status; sentilab live stop; sentilab live verify --ai-off.

MCP: sentilab_live_run; sentilab_live_status; sentilab_live_stop; sentilab_live_verify.

Required acceptance evidence:

- Actual live end-to-end trace and explicit permissions for any merge/deployment
- AI-off mode keeps deterministic placements/evaluator/ResultCheck/live evidence working without fabricated model decisions
- Budget/STOP/cancellation/unapproved-scope tests; replay remains required audit/backup rather than sole demo if adopted

## SLAB-038: Verify private box-to-GB10 network and shared Qwen serving path

Gate: G1. Proposed owner: Operations/GB10 owner under scoped human release. Dependencies: SLAB-003, SLAB-004, SLAB-009.

Prove actual authorized boxes can reach the on-site GB10/shared base-worker endpoint over an approved private authenticated path. Laptop SSH is not this proof. Any tunnel/relay/network change needs its own approved scope; no implicit public exposure.

CLI: sentilab route doctor --source box --target gb10; sentilab worker probe.

MCP: sentilab_route_doctor; sentilab_worker_probe.

Required acceptance evidence:

- Source box, destination, authentication and endpoint identity recorded
- Real structured Qwen request/response from box with bounded timeout and no credential disclosure
- Network/privacy/TTL/firewall failure tests and explicit owner resource/route approval
- Named overnight device custodian/access window, actual cloud-to-venue route, throughput/latency and bounded training/serving/rendering contention schedule.

## SLAB-039: Measure training-family optimization headroom before LLM experiments

Gate: G1. Proposed owner: Scientific evaluation owner. Dependencies: SLAB-002.

After source inventory and an explicit scoped preflight release, approve and pin the minimal fixture, objective/evaluator, search allowance, mesh set, development cases and CPU/elapsed/execution cap. Run the CPU-only headroom diagnostic using the source or a bounded preflight harness permitted by that release; no final production contract SLAB-005, product evaluator SLAB-006 or MCP implementation is a prerequisite. Compare random/heuristic/short-SA methods and a capped empirical reference. No paid inference, held-out access or unapproved 10000-evaluation run is implied.

CLI: sentilab headroom run; sentilab headroom report.

MCP: sentilab_headroom_run; sentilab_headroom_report.

Required acceptance evidence:

- Pinned training-only cases, equal short-budget/reproduction convention and raw solver artifacts
- Measured seconds per bundle, approved CPU cap and staged stop rule before any long run
- Gap-to-best-known and numerical noise reported without optimum claim; low headroom triggers approved task revision before held-out exposure
- Predeclared median short-budget-random best minus empirical best-found reference threshold k times measured mesh error; k/repetitions/CPU cap fixed before diagnostics. Not merely clustered-versus-spread sensitivity.
- Proposed gap is cheap-method median MINUS best found >=5 times max|J32-J64|; observed discrepancy not certified error. Fixed layouts use tolerance-aware rank/tie checks.
- Preflight release binds the pinned minimal fixture/objective/search/mesh/cap before any CPU diagnostic; source harness scope is explicit and does not require final product implementation.

## SLAB-040: Anchor service authenticity to an independent trust root

Gate: G1. Proposed owner: Trust-root/evidence security owner with nonauthor reviewer. Dependencies: SLAB-001.

Configure issuer/service public trust root outside submitted artifacts; issue scoped delegated signer certificates or direct trusted receipts. Required signing secret absent fails closed. Existing embedded-key consistency remains a separately labeled weak verdict; signing keys stay off lab boxes. Minimal signing/delegation contract can be prepared without the complete evidence/MCP implementation. Certify the actual record_public_key or explicitly bind separate lane identity/record keys. File-carried certified keys are accepted only under external pinned-root validation; CLI/MCP/browser share policy. This blocks stronger authenticity claims, not honest incomplete reporting.

CLI: sentilab trust inspect; sentilab receipt verify.

MCP: sentilab_trust_inspect; sentilab_receipt_verify.

Required acceptance evidence:

- Negative forged/re-signed artifact, replacement root, unknown issuer, wrong task/run/tenant scope and altered payload tests
- Expiry/revocation/rotation/historical-verification policy and both CLI/MCP/browser trust validation
- Separate internal integrity/authenticated origin/scientific verification outcomes; source-only trust-boundary finding not misrepresented as broken Ed25519
- Real record-signing key bound to scoped issuer; untrusted replacement embedded key fails, externally certified embedded key can pass; missing required signer configuration fails closed.

## SLAB-041: Preregister task-family splits, endpoints, budgets and gate scope before runner

Gate: G1. Proposed owner: Experimental protocol owner and independent statistics reviewer. Dependencies: SLAB-001, SLAB-005.

Prepare early immutable family/split manifests, training/validation selection plan, fixed-corpus and sharing primary endpoints, secondary B4, admission-order semantics, inclusive32 proposal and failure/resource-cut rules. This does not require the complete runner, live labs or headroom results to draft; experiment freeze later requires scoped evidence.

CLI: sentilab protocol validate; sentilab split inspect; sentilab protocol freeze.

MCP: sentilab_protocol_validate; sentilab_split_inspect; sentilab_protocol_freeze.

Required acceptance evidence:

- No held-out exposure to training/calibration; two seeds/five arms retained absent owner change
- 28+4/7+1 proposed table, actual charging, diagnostics k/repetitions/CPU cap and multiplicity/tie rules approved before corresponding runs
- Gate release names ticket sets/cap/expiry/humans; no blanket null-cap execution or required preflight-results approval deadlock

