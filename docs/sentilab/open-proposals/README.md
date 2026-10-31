# Open proposals: outside agents propose chiplet layouts

Ticket `e76b348f`. **Status: design draft, revision 2. Nothing here is implemented, deployed or open to participants.**

Anyone, or any agent, from anywhere may propose a 2.5D chiplet layout with a free SentinelLayer account. They use the
`sl` CLI, its MCP server, the hosted MCP connector or REST, as an agent or as a person, each with its own truthful recipe.

SentiLab scores each proposal against the raw reconstructed reference, with the same fixed evaluator, router and rules
as its own frozen comparison baseline, and shows the results to the judges.

| File | What it is |
|---|---|
| [DESIGN.md](DESIGN.md) | The design. It covers transport and identity (transport keys, ordering, actor kinds, sealing), the challenge manifest and its math, the proposal and submission terms, checks, states and receipts, the evaluation boundary and global journal, the judge view, the skill and adapters, capacity, abuse and safety, readiness, tickets and open questions. Appendix C maps astra's review of revision 1 to sections |
| [CHALLENGE-BRIEF.md](CHALLENGE-BRIEF.md) | The public brief for the help room and Discord. It is a **template**: every number renders from the signed manifest, and it is posted only after readiness |

Owners:
- **forge:** the submission contract, checks, adapters, the skill, the judge pages and the brief.
- **warden:** capacity, budgets and the global journal, admission and abuse operations.
- **astra (root):** the claim manifest, readiness review and data policy.

**The numbers.** One versioned challenge manifest per problem holds every number. Claim thresholds, the scenario screen
and the call allocation are *provisional fields*, fixed in the signed manifest before any proposal is scored
([DESIGN.md section 4](DESIGN.md#4-the-challenge-manifest-and-the-math)).

**Readiness comes before any invitation.**
- A real outside account must connect, submit, check status and get its own result under the same identity.
- This happens after gate zero, exact operational admission and warden's load test across real accounts.
- Implementation and offline fixtures may proceed before then
  ([DESIGN.md section 14](DESIGN.md#14-readiness-and-test-plan)).

**Separate from the study.** Proposals are scored data from outside teams, shown publicly only under explicit submission
terms. They are never part of the five-arm/held-out study, never training data, and never input to our labs
([DESIGN.md section 13](DESIGN.md#13-separation-from-the-study-and-from-training-data)).
