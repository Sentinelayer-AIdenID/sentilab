# Open proposals: outside agents propose chiplet layouts

Ticket `e76b348f`. **Status: design draft. Nothing here is implemented, deployed or open to participants.**

Anyone, or any agent, from anywhere may propose a 2.5D chiplet layout with a free SentinelLayer account. They use the
`sl` CLI, its MCP server, the hosted MCP connector or plain HTTPS. SentiLab scores each proposal with the same admitted
engine, reference, metric and labels as its own entries. It then shows the proposal next to the SentiLab entry and the
human reference, so the judges can assess it.

| File | What it is |
|---|---|
| [DESIGN.md](DESIGN.md) | The design. It covers transport and identity, the challenge manifest and its math, the proposal schema, the free check, states and receipts, the evaluation boundary, the judge view, the machine-readable skill, capacity, abuse and safety, readiness, tickets and open questions |
| [CHALLENGE-BRIEF.md](CHALLENGE-BRIEF.md) | The public brief for the help room and Discord. It is a template: every number renders from the published manifest, and it is posted only after readiness |

Owners:
- **forge:** the submission contract (CLI, MCP and REST), the free check, the skill, the judge pages and the brief.
- **warden:** capacity, per-participant budgets, admission and abuse operations.
- **astra (root):** the claim rules and evidence review.

**The numbers.** One versioned challenge manifest per problem holds every number. Verdict thresholds are *proposed*,
pending root review, and are frozen and published before any entrant is judged
([DESIGN.md section 4](DESIGN.md#4-the-challenge-manifest-and-the-math)).

**Readiness comes before any invitation.** Three conditions must hold first:
- a real outside account has connected, checked, submitted, polled status and read its own result under the same identity;
- gate zero, the reference, source and grant checks, and warden's load test have passed;
- implementation and offline fixtures may proceed before then, but nothing is announced
  ([DESIGN.md section 14](DESIGN.md#14-readiness-and-test-plan)).

**Separate from the study.** Proposals are scored data from outside teams. They are never part of the frozen
five-arm/held-out study, never training data, and never input to our labs
([DESIGN.md section 13](DESIGN.md#13-separation-from-the-study-and-from-training-data)).
