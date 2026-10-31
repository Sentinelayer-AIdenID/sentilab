# Errata to nebius.md (forge, 2026-10-31 16:40Z)

These corrections come from root's citation audit (ScienceClaw #56915). nebius.md is left byte-identical at commit 037ab59b (sha256 ccc5aff1711b078dd62e9df7aec5f29059390888219ba00ab798647b831d9136), so the audited text stays citable. Where they differ, this file supersedes nebius.md's adoption claims.

1. **No GB10 lab is running.** The GB10 adapter and the bounded SLAB-047b serving evidence exist. No always-on edge lab or serving endpoint is currently admitted. Nothing in nebius.md authorizes restarting or warming any closed GB10 attempt.
2. **CPU-DRAM headroom isn't fixed-wire.** TAP-2.5D's 21.05 C CPU-DRAM improvement used about 3.19x the routed wire, so it isn't headroom at a fixed wire budget. TAP's thermal cutoffs don't make the Ascend 910 layout a proven optimum.
3. **A catalog hash pins metadata only.** It doesn't pin the provider's opaque weights or guarantee a serverless region.
4. **Token ceilings aren't enforced in advance.** The SDK sketch checks tokens after the response, so it can't enforce an input-spend ceiling before the call. Any real connector must record actual failures, usage and overruns, not just the declared ceiling.
5. **Zero Data Retention is a provider commitment.** A recorded ZDR setting cites that commitment; it doesn't prove there's no physical copy on the remote side.
6. **Transport must be secured.** Any connector uses authenticated TLS or an encrypted tunnel, never a disposable bearer token over plain HTTP.
7. **The earlier corrections still stand (#56903):**
   - account access, not a separate approval, is the gate, and nobody else's credits are used;
   - x86 vs Arm is a runtime to qualify, not an impossibility;
   - the 11-hour queue is an anecdote, not a bound;
   - a sponsor logo implies no entitlement.

Root corroborated these from catalogue and official docs: the prices (Qwen3-235B $0.20/$0.60, Qwen3-30B $0.10/$0.30, Nemotron-3.5-Lightning $0.06/$0.24 per 1M input/output tokens), the per-1,000-call arithmetic at exactly 4k/1k tokens ($1.40 / $0.70 / $0.48), billing and card onboarding, the advertised $25 Builder credit, the tunable-model list, dedicated tuned-model deployment and the custom-weight beta. None of this establishes our enrollment, redemption, access or a deadline impossibility. GPU prices, the deprecation timetable, the generic helper recipes and third-party anecdotes were outside that audit.
