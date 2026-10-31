# SentiLab progress

**GB10 fixture preflight passed. Scientific results remain gated.**

This is a dated review draft: all 41 tickets and eight deliverables are covered through 07:50 UTC, with explicit later decisions and the completed GB10 artifact audit. It is not a live feed. None of the eight final deliverables is fully accepted.

| Status | What the evidence supports |
|---|---|
| **Done** | Aneta returned the second technical plan +1, bound to exact files and her stated incremental review scope. It does not approve results, deployment, spending, or future work by Aneta. |
| **Done** | Source-evidence, stored mesh-evidence and fixture dataset-export slices have scoped acceptance. Raw per-solve archives, independent reproduction and export cleanup still have work remaining. |
| **Measured** | One GB10 attempt completed 20 training steps, saved an adapter, reloaded it in a fresh container, evaluated 20 fixed entries, answered 40 localhost HTTP requests, and tore down. The independent artifact audit passed 112 checks. |
| **Measured** | Both evaluation paths returned exact JSON for 20/20 adapter entries versus 0/20 base entries. These entries repeat **six source cases already represented in training**, with label metadata supplied in the prompts. This demonstrates fixture plumbing, not scientific generalization. |
| **Measured** | Ascend headroom remains **INCONCLUSIVE**. The 24-layout mesh study is a fixed-sample numerical result, not a universal error bound. |
| **Open** | Scientific protocol and model admission, OpenResearch, full CLI/MCP capability coverage, current correctness repairs, verified public runtime and complete D00–D07 packaging remain open. |
| **Superseded** | Robotics reuse is outside current scope. The work is our own chiplet simulation and truthful thermal visualization; no MicroDuck/Pollen robot code, models, meshes or assets. |

Evidence: [GB10 audit](https://github.com/Sentinelayer-AIdenID/sentilab/blob/ff5c84233aa14363cbf08be820897a989a59aed0/docs/sentilab/evidence/SLAB-018/review/RESULT-REVIEW.md), [Aneta’s decision](SOURCE-CATALOG.md#source-aneta-56311), [41-ticket/eight-deliverable ledger](SOURCE-CATALOG.md#source-coverage-delta), [full dated progress and hashes](LEDGER.md).

Next priorities are to close the existing correctness queue; freeze the scientific metric, admission rule, family statistics and reproduction policy; complete model/provider admission and OpenResearch; assign full CLI/MCP conformance; and package verifiable runtime and final-deliverable evidence.

The GB10 attempt used **314.189539 charged seconds**. Including the conservative 180-second prior reservation, its total is **494.189539 seconds**, within the 60-minute cap. Warden’s new CI and experiment allocations are prospective allowances, not usage or execution acceptance. Exact historical CI consumption remains unknown, and no new micro150 execution is released.

**Cost:** no current total or invoice is verified. The last retained room estimate was **USD 255.79 at 07:31:44Z**. It is a historical estimate, not a current total.

Root owns this progress content and its evidence links. Forge has been asked to prepare the deck for **2026-11-01 18:00Z**; human presenter availability remains separate. This draft implements no public page, export interface, deployment or submission. The presentation/submission and GB10 CLI/MCP interfaces remain tracked follow-up work. Repository evidence links identify exact commits and may require access. Other sources are retained by opaque ID/hash with operator archive access required. No private source bodies are included.

The pinned PR28 evidence destination is commit `ff5c84233aa14363cbf08be820897a989a59aed0`. Linking it does not claim a current PR head, approval, CI result or public accessibility.
