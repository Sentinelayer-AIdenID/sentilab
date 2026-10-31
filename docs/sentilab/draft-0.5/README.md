# SentiLab draft-0.5 review packet

**Documentation-only review. Project implementation remains on HOLD.** Carter approved publishing this private PR on October 31, 2026. The approved core is reproduced byte for byte; no application, infrastructure, model or runtime configuration is changed.

Read [the current owner decisions](OWNER-DECISIONS-2026-10-31.md) first. They resolve both pending questions: actual MicroDuck robotics simulation **and** NVIDIA's workflow applied to the chiplet interface are required; there is no overall dollar ceiling. The explicit execution `+1` gates still apply. These current decisions supersede the corresponding pending-choice language in the historical frozen files.

## Review order

1. [PLAN.md](PLAN.md): scientific task, system responsibilities, eight deliverables, experiment protocol and approval gates.
2. [REQUIREMENTS.md](REQUIREMENTS.md): 234 requirements with source, ticket and acceptance-evidence mappings.
3. [TICKET-INDEX.md](TICKET-INDEX.md) and [TICKETS.json](TICKETS.json): 41 draft tickets, dependencies, acceptance criteria, and MCP plus CLI surfaces.
4. [MODEL-ROUTING-PROPOSAL.md](MODEL-ROUTING-PROPOSAL.md): provisional model candidates; catalog, provider and execution access remain unverified.
5. [FORGE-REVIEW-RESPONSE.md](FORGE-REVIEW-RESPONSE.md): all F1–F12 follow-ups after the core freeze. These are proposed dispositions, not silently applied core changes or approvals.
6. [ANETA-REVIEW-RESPONSE.md](ANETA-REVIEW-RESPONSE.md), [CANONICAL-ADDENDUM.md](CANONICAL-ADDENDUM.md) and [technology-evidence.md](technology-evidence.md): scientific objections, current-source corrections and primary references. The canonical addendum supersedes earlier bounded-source uncertainty where noted.

All eight engineering deliverables remain mandatory for a full-completion claim: exact chiplet layout/constraints; power/package assumptions; versioned simulator inputs and raw outputs; independent reproduction; complete decision/correction history; baseline comparison; evaluated trained adapter/checkpoint; replayable visual demonstration. A truthful deadline progress report may disclose incomplete items without declaring the project complete.

## Integrity and source boundaries

The core is pinned to canonical repository commit `2199612932da142e0057e6162293940b4ea64bba` for source review. [REVIEW-MANIFEST.json](REVIEW-MANIFEST.json) binds the 13 frozen files. [VALIDATION.json](VALIDATION.json) records document consistency, not simulator or product tests. [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json) additionally covers this wrapper, owner decisions, later review context and source copies.

| Frozen core file | SHA-256 |
|---|---|
| PLAN.md | e15174b8040d40b0675d8821586c2725ba84b79419393fe2a42e405218410f1a |
| REQUIREMENTS.md | cef6ca1268486238be1a98c2fdf2634b2ff8cd7d1004d8b9f5bd61d0b30f658b |
| TICKETS.json | e5acf2ec49c53407b3918c37c9ff0eeefe2bd53df3d189b7949add77513144d4 |

The two original user proposals are included as [source A](sources/source-a.txt) and [source B](sources/source-b.txt), with exact original bytes and hashes in [source provenance](sources/PROVENANCE.md). Their numerical and deployment assertions remain historical claims unless separately verified by the review. Citation tokens from the original chat are preserved as source text, not presented as newly resolved citations.

Frozen files retain historical workstation paths and `.sentinelayer` cache references. Credentials, operational caches and raw full-room exports are not included. The review documents retain relevant event IDs, timestamps, quoted decisions and disclosed retrieval limits; this packet is not a complete export of every Senti action or a substitute for the missing experimental evidence. The original source files are mapped to portable copies in the provenance document.

## Approval boundary

The owner release covers this private docs-only PR. All 41 implementation tickets remain `DRAFT_HOLD`. Warden's contract-v0.2 approval is specific to that contract; agreement with numerical corrections or readiness reactions is not an approval of this PR head. Reviewers should identify the exact commit SHA, approved scope and any remaining objections. Authors cannot provide their own independent approval.

The publication commit uses `[skip ci]` because the existing PR workflow builds and executes the thermal application, while the present release is documentation-only. No workflow is modified. Verification here covers exact committed bytes, mappings, links and docs-only scope. Any later merge/execution release must address the applicable repository checks explicitly.
