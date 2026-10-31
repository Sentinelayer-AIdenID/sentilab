# Proposed daytime deck integration — review required

This packet is local and additive. It changes no shared script, deck, PDF, repository branch or published page. Root accepts evidence/copy; Forge owns the implementation and render review. Keep the original packet and earlier deck/PDF immutable.

## Selection and schema

The proposed ID is `progress-2026-10-31-daytime-1505`. The inspected builder at commit `d63ccd768dbc8cd94816f8363285abed75cfd65c` accepts this through explicit `--packet`, but automatic discovery at `scripts/build-deck-data.mjs:276–279` accepts only `progress-YYYY-MM-DD`. Existing `deck-data.test.mjs:60–64` requires the generated packet to equal that auto-selected packet. Therefore explicit selection alone is insufficient. Add one reviewed selected-packet mechanism or consistent same-date discovery rule across generation, checks and CI. Do not invent a later calendar date to win sorting.

The original `progress.schema.json` is a frozen-snapshot contract: 41 tickets, eight incomplete deliverables, a fixed original GB10 attempt and `factsRefreshed:false`; top-level additions are disallowed. The root-level `progress.json` and schema in this proposal remain byte-identical to the original. `DAY-UPDATE.json` is a separately versioned typed overlay. It must not be ignored while a newer packet ID is shown. Validate both schemas and all source/manifest bindings, emit both input hashes, and fail explicitly on missing or unsupported day updates. The original object is a historical baseline, not today's fully refreshed record.

## Replace fragile inference with typed, scoped facts

The old builder reads only progress and page copy (`281–289`). It selects the first prose match for GB10, mesh, headroom and package view (`128,134,151,156`), ignores supersession, and drops milestone summaries/caveats from its lists (`191`). Appending newer prose cannot safely change those facts. Use stable attempt/claim IDs, typed metrics, explicit status and dependency dispositions from the sidecar. Unknown or superseded values must not fall back to an old numerical claim.

Separate observation time, review time and correction time. The old newest-evidence timestamp rule (`73`) can date an old value using a later correction. The sidecar's checkpoint, room cutoff, local addendum and original observation dates must retain their different meanings. Its filename is not evidence of freshness.

Do not parse grant caps or audit counts from PAGE-COPY, as the legacy builder does (`126,129`). Keep the three attempt records separate:

| Attempt | Supported purpose | Required limit |
|---|---|---|
| SLAB-018 attempt 1 | Original training/save/reload/serve fixture preflight; 112 checks; original 20-step/base comparison | Historical six-source-case overlap; preserve original reservations and charge |
| SLAB-047 | Startup failure before inference; 75 consistency checks | Mapping failure observed; old effective mount flags unknown; consumed attempt |
| SLAB-047b | Closed serving fixture; 323 checks; 20/20 responses | Six training-source cases and supplied labels beside every ratio; 148.9 whole-lifecycle wall seconds; no base comparison measured here |

The approximately 35-second first response is client-observed latency, not decoder throughput or time-to-first-token. Do not display 148.9 as GPU-s. Native preflight and failed-attempt charges remain separate. Unknown current total cost must remain null.

## Slide and speaker-note changes

1. **Problem / architecture:** distinguish designed behavior, fixture behavior and accepted runtime evidence. Existing unconditional signing/reproduction/verified-prefix statements in builder notes (`204–214,244–247`) and templates must not become claims of complete production acceptance through a newer date.
2. **Reviewed engineering:** show exact-source/merge/HTTP slices for PR51 and PR53, with scoped limits. PR54's later retained binding confirms merge `1bdf584b3446bc4b911e9f3a8b10b741ab867c47`, matching head/merge trees, 17 exact changed blobs and five successful CI jobs. Show the earlier pending observation only as superseded history. Keep operator production-browser observations separately attributed; no science/device grant follows from CI or merge.
3. **GB10 lifecycle:** show all three attempts, retained failure, timeout repair, 20/20-six-case caveat, startup and cleanup. Original train/reload and later serving are different attempts. Do not reuse the original 0/20 base score for 047b.
4. **Scientific correction:** preserve INCONCLUSIVE and the old evaluator's observations. Show the coupling/metric questions and correction history as reviewed hypotheses and source findings. No calibrated-temperature, silicon, optimality, completed MATCH/BEAT or universal-flatness claim. The old seeded-fault fixture is not the new real evaluator correction being completed.
5. **Open repair / evidence queue:** PR37 failed admission and operator-reported debit; PR55 four scoped closures with original unknown-method P2 and six container-CI cardinality subcases still open; PR56 all-layer parser repair; native6 gate-zero bindings, full learning/sharing study, real held-out worker evaluation and complete CLI/MCP obligations.
6. **Community / next:** research is first priority; Forge is the sole participant-listener/greeting owner while missing materials and UX continue in parallel. The announcement, reviewed five-file kit and operator-reported access promotion do not establish fresh-account/client/media acceptance or the full three-skill bundle. The Aneta/Nebius supplement is privately delivered; its compatibility assessment is not a tested transfer, hosted connection, cloud deployment or GB10 restart.
7. **Coverage / cost:** preserve 41/234/104+104/eight-incomplete as original scope, not implemented counts. Supplemental tracks remain separate. Keep current dollars and comprehensive CPU unknown and old deadlines/grants explicitly historical.

Keep product-facing wording free of private paths, device/account IDs, invitation credentials and implementation-only controls. Preserve the existing public-render rules; internal source IDs and precise reviewer attribution remain in evidence appendices. No invitation links or secret source bodies are included in the portable proposal.

## Required checks after root accepts content and Forge adapts it

- Baseline byte/hash preservation, all original IDs, 234 requirements, 104 CLI and 104 MCP declarations, zero completion inflation, source references and new manifest integrity.
- Consistent same-date packet selection across generation/check/CI; sidecar/schema/hash binding; failure for absent/unsupported sidecars.
- Reordered and superseded-first milestones, missing facts, null replacements, old-observation/new-review timestamps, and no legacy regex fallback.
- Separate GB10 attempts, units, charges, denominators, labels, base-comparison scope and audit counts; no promotion to generalization or production acceptance.
- PR54 merged/current and pending/historical states retain separate times. PR55 HOLD is now the original unknown-method finding plus red container CI; preserve the four scoped closures and five-finding historical review. PR56 parser P2, consumed PR37 bootstrap and expired scientific grants remain explicit. Saved-field parent analysis covers eight grids; independent reparse covers two representative cases only.
- Deterministic JSON/JS parity, updated template and speaker notes, public-render rules, artifact/fixture links and visible dates.
- Render every deck/PDF page and inspect text, layout, caveats and clipping at the required viewport/export sizes. Preserve the original export: the current PDF naming uses only the date, so add an explicit daytime/version suffix before export.

The local packet validates both JSON Schemas, evidence references, fixed scope counts, source hashes and package integrity; see VALIDATION.json and the external local completion receipt for exact results. No shared renderer, visual export or CI check was run during this preparation. The renderer-specific checks above remain Forge's later work. There is no scientific or execution grant in this proposed packet.

## Frozen 15:05 contract

Consume sidecar version sentilab-progress-day-update/2 and its schema. The prior 1435 packet and manifest remain unchanged outside this proposal. Keep the accepted 14:49 observations dated. The factual cutoff is 15:05:00 UTC; later 15:08:55 verification establishes pre-cutoff PR55 delivery and sealed bytes only. Do not treat verification or packaging time as factual freshness.

Render PR55 at efe12c6 with four original scoped closures, one remaining unknown-method P2, and the existing container failure: six WorkerCardinality subcases need otherwise valid owned workspaces, with separate unavailable-workspace controls. Keep 67 passes and three missing-binary errors out of 70 selected tests distinct from seven protocol passes. Do not show 70/70 or erase the old five findings. PR56 at 997269e has one all-layer parser P2, 20 passes, eight skips, two retained-file controls and five existing green CI jobs, with no native execution.

Native6 gate zero has design allocation accepted by Forge #56794 at 15:02:23.364 UTC: 8 primary calls plus 4 fresh-process grid-64 replays. Exact executable source/input/host/window/grant binding is still pending. The 12-run/1,800-CPU-second envelope is prospective; additional published verification at 75.47/94.89 C is DEFERRED to a later allocation, with no extra calls in the current 12 and no unseen statistical holdout claim, and the old HotSpot 7 material-only 32-call plan is NOT_REQUESTED. Preserve computational reference tolerance versus physical fidelity. Report PR37's conservative 100/900 booking as operator-reported. Zero applies only to reported metered container use, never runner CPU or money. No second grant exists.

Ordinary help-room participation and ticket work require no new human approval interruption. Warden reports room-scoped auto-admission; source and decisions remain for internal verification. Agents retain actual identities: never substitute a human cli-user workaround. Forge remains the sole listener; do not introduce a duplicate approver.

Focused later renderer checks must reject stale five-open PR55 presentation, closure inflation, 70/70 claims, grant inference from the native6 envelope, whole-run zero-cost inference, human identity substitution and redating pre-cutoff facts from later verification. Local focused schema/hash checks do not replace Forge's rendering and visual checks.

Publication-copy schema delta: nativeGateZero adds typed design acceptance and the 8+4 allocation, while exactCallAllocationAccepted remains false for the pending executable binding. The field outOfSampleChecksC is replaced by additionalPublishedVerificationC, paired with DEFERRED, inclusion=false and unseenStatisticalHoldoutClaim=false. Consume the supplied exact sidecar/schema together; the legacy progress/schema and shared renderer are unchanged. The new forge56794 source reference is included; earlier 70 references retain their bindings. ROOT-CONTENT-ACCEPTANCE.json records root acceptance of prior facts separately from final delta, renderer and publication approval.
