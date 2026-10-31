# Model routing proposal — G1 HOLD

2026-10-31, America/New_York. Candidates for all 41 tickets in the current draft-0.5 `TICKETS.json`. This supplemental map changes no ticket scope, dependencies or approval. No model launch, calibration, availability verification or replacement authority is implied.

Source: Warden's 03:30Z catalog in `remote-actions-readback-metadata.json`, reply to #55918, action `9e9a688f-eca9-4a75-9691-710a31bbe0a8`. Availability/endpoints remain unverified.

## Exact catalog identifiers

| Key | Warden-reported model ID |
|---|---|
| A | gpt-6-astra |
| S | gpt-5-6-sol |
| P | deepseek-v4-pro |
| F | deepseek-v4-1-flash |
| K | kimi-k2-7-code |
| G | grok-4-7 |
| C | cohere-command-a |
| L | llama-4-maverick |

Exact spelling preserved. Reported reasoning: A low/medium/high/xhigh; S none through xhigh. Accepted settings still need probing.

## Required runtime roles

- Astra lead: A; Grok lead: G; Kimi lead: K. Preserve their independent lab contexts.
- Claude lead: **missing**. Warden proposes `claude-opus-5-5` (lead candidate) and `claude-sonnet-5-5` (bounded-worker candidate). Both need key configuration, rates, calibration and Carter's release; neither is verified available.
- DeepSeek critic: P; F is a candidate for bounded mechanical review if it passes. Gemini is missing; C/L can be additional independent critics, not an automatic replacement for requested Gemini.
- Shared trainable worker: exact Qwen checkpoint/route remains pending GB10/NeMo recipe and serving proof. Listed ticket models write/review its code; they are not its trainable weights.
- Jev intent service: exact route pending verification. OpenResearch names its underlying model. Neither silently replaces a required lead family.

## Ticket candidates

First/check are build or analysis candidates, not execution authority or assignments of the runtime scientist roles. The checker cannot have authored that seam/revision. A different context or agent name alone does not establish model-family independence. AcceptanceGate and ResultCheck remain deterministic; LLM judges supply auditable reviews and labels, not scientific admission authority.

| Ticket | First | Check | Scope |
|---|---|---|---|
| SLAB-001 | A | P | Plan and adversarial reconciliation |
| SLAB-002 | S | P | Source and regression inventory |
| SLAB-003 | S | A | Catalog and missing-route integration |
| SLAB-004 | S | K | GB10 access and inventory |
| SLAB-005 | P | A | Geometry and objective contract |
| SLAB-006 | P | S | Thermal evaluator and uncertainty |
| SLAB-007 | S | P | Typed records and provenance |
| SLAB-008 | S | A | Deterministic AcceptanceGate |
| SLAB-009 | F | S | CLI/MCP transport bindings |
| SLAB-010 | S | P | ENGRAM and support invalidation |
| SLAB-011 | F | A | Typed Jev routing adapter |
| SLAB-012 | C | A | OpenResearch source audit |
| SLAB-013 | S | A | Four-lab orchestration |
| SLAB-014 | P | L | Judge protocol and calibration |
| SLAB-015 | S | P | Fresh reproduction service |
| SLAB-016 | F | P | Dataset schemas and eligibility |
| SLAB-017 | F | P | RLAIF export and label provenance |
| SLAB-018 | S | P | GB10 NeMo preflight integration |
| SLAB-019 | S | P | Approved training/selection plumbing |
| SLAB-020 | P | A | Benchmark design and runner |
| SLAB-021 | P | C | Family-level analysis and claims |
| SLAB-022 | S | P | Deterministic ResultCheck |
| SLAB-023 | F | S | Typed intake and pilot integration |
| SLAB-024 | K | A | Microduck source/fidelity review |
| SLAB-025 | K | S | Evidence and simulation interface |
| SLAB-026 | K | P | Approved Microduck workflow |
| SLAB-027 | S | P | Correction and replay fixtures |
| SLAB-028 | F | S | Complete D00–D07 handoff packaging and verification |
| SLAB-029 | C | A | Truthful progress submission and full-completion accounting |
| SLAB-030 | P | A | Optional surrogate evaluation |
| SLAB-031 | C | P | Optional domain/sponsor research |
| SLAB-032 | S | P | Frozen held-out run orchestration |
| SLAB-033 | S | A | Approved checkpoint serving |
| SLAB-034 | F | P | Coverage and transport conformance |
| SLAB-035 | C | A | License/terms source review |
| SLAB-036 | S | P | STOP, recovery and accounting |
| SLAB-037 | S | P | Deterministic conductor, AI-off live loop and later lab integration seam |
| SLAB-038 | S | K | Private box→GB10 serving path |
| SLAB-039 | P | A | Bounded headroom design/analysis |
| SLAB-040 | A | P | Independent trust root, certified record keys and forgery rejection |
| SLAB-041 | P | G | Early family splits, primary endpoints, budgets and preregistration |

SLAB-037's deterministic live loop can be built and checked without launching the four LLM labs; SLAB-013 consumes its integration seam later. SLAB-040's key checks establish integrity and authorized origin, not physical validation. SLAB-041 freezes the protocol and leakage controls before the corresponding approved experiments; the model selection process must respect those frozen splits.

## Cheapest passing policy

No cost ranking has been measured. With an approved G1 budget, probe identity, endpoints, modalities/tools, terms, rates, quotas and schemas. Calibrate role fixtures on **development families only**; measure correctness, invalid actions, abstention, latency, tokens/retries and cost. Choose the cheapest passing candidate; never tune on held-out families.

Hard failures include permission/approval bypass, invented evidence, source/metric mismatch, leakage or failed deterministic checks. Abstain on missing evidence or unsupported routes. A stronger model cannot waive those checks. Escalate unresolved reasoning/code failures to the proposed checker or A after the frozen attempt limit; never silently replace a required lead family. Independent peer +1 and owner release remain separate from model choice.

Calls/tokens, time, concurrency, retries, spend and escalation ceilings are **TBD: no execution until approved**. Record candidate changes at G1. Frozen benchmarks permit only their predefined failure policy or a new protocol, never opportunistic model changes.
