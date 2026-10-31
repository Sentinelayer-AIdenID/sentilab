# SentiLab external review and release status

Status: **DRAFT / HOLD**. This records discussion and evidence, not permission to implement, mint boxes, train, deploy or publish. The direct user's explicit `+1` rule remains in force.

## Latest status — 2026-10-31

Draft-0.5 supersedes draft-0.4 for the next review. Its current exact file hashes and document-consistency checks are in REVIEW-MANIFEST.json and VALIDATION.json. Earlier snapshots remain immutable. Preparing a revised packet is not a peer approval or an execution release.

The last authenticated remote decision check completed at **2026-10-31T04:07:57Z**. Aneta's **#56011** explicitly places draft-0.4 on HOLD. Warden's threaded action **217c740a-af2d-40bf-8ee7-8e6782294215**, at 04:06:14Z, says **“changes requested, no +1.”** No docs-only publication approval, owner budget/scope directive or revision-bound release was found. Exact messages and response hashes are in `.sentinelayer/sentilab-planning/gpt-astra-carter/decision-check-after-draft04.json`.

The new revision addresses P1–P11 and the independently verified canonical-source corrections. This includes the existing eight-chiplet `sys_micro150.cfg`, current-board admission, retained raw simulator artifacts, a service-authenticity trust root, independent early protocol work, and separating the base evidence/replay path from robotics. A truthful incomplete progress submission does not satisfy the complete D00–D07 handoff. Mandatory user scope remains tracked until the owner explicitly changes it.

Root challenged two additional review proposals: for minimized temperature, the headroom gap is cheap-method median minus best-found; a valid losing candidate is not an invalid stale parent. Mesh discrepancies are observed numerical diagnostics, not certified physical error bounds. The trust certificate must bind the actual record-signing key; a certified key can travel with an artifact if its certificate is checked against an independent pinned root. Origin authentication never substitutes for thermal validation.

Warden also reported defects in Aneta's reference contract code, including large-sample arithmetic, unit normalization, family grouping, input bounds, cycles, empty support, event ordering and unauthorized acceptance. These are **unverified peer code-review findings**, recorded as required resolution/conformance fixtures. Neither root nor this planning revision claims to have run that reference implementation or its reported tests.

The user-supplied MicroDuck video remains the exact visual reference. Its primary NVIDIA workflow is documented; the video itself has not been watched. Full robot workflow scope is retained while the user clarifies its intended relationship to chiplet visualization. The spend ceiling and this clarification remain pending questions. The GB10 is reachable on MIT SECURE, but the latest SSH public-key login failed; no device training or serving is claimed.

The temporary Senti listener was stopped. No recurring automation or persistent wake mechanism was installed by this task; this status is a bounded readback, not a promise of continued automatic monitoring.

## Participants and actual authority

- `gpt-astra-carter` joined room `608657e4-5e60-4bb6-9353-9611b70c1c66` and owns this planning/traceability review.
- `claude-warden-aneta` is Aneta's local Claude Code session name. The actual room identity is **`aneta-claude`**. In message **#55936**, it reported that Aneta authorized full participation. It then supplied the R1–R14 review in **#55938**, explicitly saying **no +1 yet**. Its proposed contract-authoring lane awaits scoped assignment; Aneta's human UI/outreach time remains uncommitted.
- **`claude-warden`** supplied a substantive independent response in action `9e9a688f-eca9-4a75-9691-710a31bbe0a8`, replying to message `#55918` at `2026-10-31T03:29:33.323149Z`. It agreed with the first six objections and added five requirements. This is not a revision-bound release `+1`.
- The Warden proposed **Warden + pocket-forge** technical approvals on the exact plan revision before any boxes are minted. Forge replied that it will review after its current web fix and is **not approving anything yet**. Aneta's subsequent R9 objection strengthens the rule: an author cannot supply an independent approval on their own contract or revision, so the eligible reviewers must be chosen per artifact.
- The Warden described a newer human direction in another conversation. That report informs the proposed live-product scope but is not silently substituted for direct authorization in this chat. Any release must cite its actual authorized scope, budget and revision.

## Source delivery and evidence

Both original user attachments were delivered as `SOURCE A 1/6` through `6/6` and `SOURCE B 1/7` through `7/7`. An authenticated raw remote read verified all **13 unique messages, byte-equivalent text and SHA-256**, at room sequences **55923–55935**. Verification is saved in `.sentinelayer/sentilab-planning/gpt-astra-carter/source-packets-remote-verification.json`.

The ENGRAM council was read from room `701639be-bd55-4634-8ca5-1eae3d5c0227`. [COUNCIL-REVIEW.md](COUNCIL-REVIEW.md) retains the source-indexed reconciliation and 28 complete relevant messages. Historical deployment claims are explicitly distinguished from present verification.

Canonical repository metadata and live health were independently checked: `Sentinelayer-AIdenID/thermal-flight-lab`, commit `2199612932da142e0057e6162293940b4ea64bba`; `https://thermal.aidenid.com/api/health` returned HTTP 200 and that exact build SHA. This proves metadata/build correspondence, not a fresh solver run or validation of historical temperatures.

## Adversarial findings incorporated into the draft

| Issue | Review outcome | Required evidence before execution/claim |
|---|---|---|
| Historical counts and temperatures | Warden agrees they require current evidence | Recover inputs/artifacts and rerun; never claim an authored layout difference as agent gain |
| Center temperature versus peak | Must use explicit layer/statistic/version | Current six-chiplet TAP peak and requested eight-chiplet centers stay separate |
| Learning from failures | Retain every outcome; train only eligible records | Family split, rights/provenance, verified repairs, negative/tie/inconclusive labels |
| Reproduction versus validation | Warden adds analytic or different-solver checks | Same-solver repeatability plus separately scoped numerical/physical-validity evidence |
| Benchmark allowance | Still unresolved | Define whether 32 bundles applies per family/seed/arm; 3,840 is one interpretation, not an approved budget |
| GB10 training | User requirement preserved; bounded preflight proposed | Key access, exact compatible recipe, data/context/memory proof, explicit release for larger training |
| Live product | Warden proposes autonomous live loop and AI-off path | Real intake/queue/executor/receipt/UI flow, intervention accounting; replay remains required audit/backup artifact |
| Model choice | Warden proposes calibration | Preserve four required lead families; cheapest suitable specialists must pass measured role fixtures |
| Contract ownership | One named owner per seam proposed | Solver I/O, evidence/flight record, ResultCheck and transport parity contracts signed off before implementation |
| Existing source reuse | Frontend exists at canonical HEAD | Extend current live/replay frontend; do not assume recovered-snapshot omissions still apply |
| Existing fixtures/proxy | Current four/six-chiplet tasks differ from new task | Eight-chiplet fixture recovery; current normalized wire proxy cannot inherit raw-sum thresholds silently |
| Existing execution controls | Local signing/origin access is insufficient | Durable accepted state and actual principal-scoped AIdenID authorization at executor boundary |
| ENGRAM | Reuse deterministic L3/principal slice first | Coverage/gaps/raw expansion, live ACL, correction lineage, no invented recall SLA or automatic unlearning |
| Microduck | Primary workflow identified; exact local fidelity unproved | Asset rights; Isaac/Omniverse/Newton/Lab pin and GB10 check; thermal and robot evidence kept distinct |

Root sent the reconciliation as reply action `ade063f9-486a-452f-9850-490cdc872741`, and source-specific corrections as `01f144c1-e906-4dae-b6da-6329ed87c811`, both under `#55918`. Those are review contributions, not approvals.

## Claude model route dependency

The Warden reports that the box inference proxy supports Anthropic, but no Anthropic key is configured on its host and no Claude model is presently listed. It proposes catalog/rate entries for `claude-opus-5-5` and `claude-sonnet-5-5`, subject to actual provider/model verification. The Warden owns that change. Carter must provision credentials through the approved private configuration path and release the paid route; no password or API key should be posted to the room or this document. No model route was installed by this review.

## Release conditions still open

1. External reviewers must inspect the exact completed draft and provide their named, scoped `+1` or objections; no silence or general agreement substitutes for a release.
2. Confirm the authorized approvers and resource ceilings for each gate. An approved plan does not authorize unbounded compute or a new public domain.
3. Finish GB10 key access and the approved preflight; no successful login or training is claimed.
4. Resolve the benchmark accounting unit, exact fixture parameters, model identities, visual fidelity/rights and actual team/sponsor resource status before the dependent runs.

The draft implementation tickets are local planning records only. No remote ticket creation, paid box launch, experiment, training, code merge, deployment or submission was performed by `gpt-astra-carter` for this request.

## Second external review and draft revision

Aneta's complete R1–R14 review challenged budget reallocation, family-level inference, headroom, grid artifacts, formatting-only learning, memory leakage, missing eight-chiplet source, central planning, Warden role ambiguity, human dependencies, Senti transport/admission gaps, untrusted inputs, missing model routes, and evidence support semantics. [ANETA-REVIEW-RESPONSE.md](ANETA-REVIEW-RESPONSE.md) records each disposition and the counterarguments.

Root replied under #55938 with both scientific and architecture responses. Accepted changes include fixed per-lab budgets for the primary sharing comparison, separate parse/geometry/numerical-benefit metrics, blocked run ordering, deterministic **AcceptanceGate** naming, non-author review, separate lifecycle/validity/verification tier, OR-of-AND evidence support clauses, and distinct training-data taint. The 10,000-evaluation diagnostic, seed reduction, adapter removal, and Isaac/Newton cuts are not automatically adopted. CPU diagnostics need bounded approval; best-found performance is not a proven optimum. The user's required scope remains intact until explicit approval changes it.

The exact original-source reconstruction concern was resolved: preserve all source characters and original CRLF, strip only the transport marker's single separating LF, and concatenate with the empty string. Both files match their original byte lengths and hashes. This supports careful source transfer, not an assumption that all room messages are immune to transformation.

Draft-0.3 was transmitted and remotely verified in **26 exact, unique packets** (13 plan, nine requirements, four ticket-index). Its directed request is #55965. Draft-0.4 incorporates the newly received review and supersedes it for future approval; no approval for either revision has been received. The user has also been asked whether the MicroDuck requirement means actual robots alongside chiplets, NVIDIA's workflow applied to chiplets, or visual style only. Full robotics scope is preserved while that clarification is pending.
