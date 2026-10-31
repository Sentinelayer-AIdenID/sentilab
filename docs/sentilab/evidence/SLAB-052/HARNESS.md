# SLAB-052 proposal harness

This is harness source and synthetic test evidence, not a lab run report.
No model call, thermal solve, device operation or proposed performance result
was produced for this change. The claim scope is descriptive computational
simulation. The Ascend reconstruction is not Huawei CAD or measured silicon.
The five-arm confirmatory study and physical TTC validation remain separate.

## Surfaces and authority

The SLAB-043 registry owns these schemas and discovery names:

| CLI | MCP | Caller input |
| --- | --- | --- |
| `python -m sentilab_cli proposal context` | `sentilab_proposal_context` | none |
| `python -m sentilab_cli proposal submit --request-id candidate-1 --positions '[[2,2],[8,8]]'` | `sentilab_proposal_submit` | request ID and ordered centers in mm |

The example is syntax, not a solve instruction. Unconfigured hosts return
`status: blocked`, `error.code: not_configured`. No default oracle, model
transport, admission, grant or production factory is installed. In particular,
the existing unconstrained oracle is not silently substituted for SLAB-051.
The old pending `lab.propose` row still represents the advisory generation lane;
`proposal.submit` is a separate, budgeted evaluation capability.

The operator constructs `ProposalHarness` with a pinned in-memory service
signer, a dedicated run ledger, `PublicProblem`, N `ProposalLab` registrations,
one equal `solve_budget`, a `ProposalGrant` and an oracle factory. Bounds are
1–32 labs, at most 10,000 total slots, 1–32 chiplets and 0–300 seconds
(exclusive lower bound) per adapter call; the wire cap is 64 KiB. A grant binds
the run, frozen oracle identity, exact lab list, per-lab slot count, expiry,
operator grant reference and SLAB-048 readiness reference. These are trusted
host configuration, not evidence that this library can approve a run. The host
must obtain the real reviewed evidence before constructing them.

Each `ProposalLab` binds an existing `Admission` to the run and that lab's arm.
Submission rechecks current model/provider/payer admission and the `lead` role.
Reservation takes the ledger lock and then the registry publication lock, reads
current authority after both waits, and holds it through the signed append. The
adapter task rechecks authority and STOP at its protected start boundary. A policy
change after reservation returns `admission_revoked` without an adapter call and
retains the charged reservation. STOP is also checked inside the final append
lock: a new result becomes `stopped`, while prior charges and genuine failures
remain unchanged. See [ROUND-2.md](ROUND-2.md) for real-lock regression proof.
No model generation occurs here; any generating host must continue to use the
existing admitted, metered model transport. Proposal slots do not replace model
USD accounting or the solver's CPU/wall accounting.

Give each proposer a separate host-bound transport context:
`context.proposal_session = harness.bind(lab_id)`. Requests cannot select a lab,
root, oracle, budget, grant, comparator, policy or signer. Both transports refuse
non-proposal tools for a bound session; MCP discovery lists only its two tools.
The existing host capability-scope check remains in force. This boundary assumes
the proposer cannot execute arbitrary Python in the trusted host or read its
filesystem. Do not mount the operator ledger, comparator evidence or other labs'
files into proposer boxes. In-memory adapters are trusted host code, not plugins
loaded from proposer input.

## Constrained-oracle integration contract

SLAB-048 and SLAB-051 interfaces are absent from the supplied base `3e7c480`.
The remaining production integration is explicit: install the reviewed constrained
oracle adapter after those prerequisites, model admission and a prospective grant.
Its factory returns a fresh adapter for each lab with:

- `oracle_id`: the same 64-character digest as the frozen `PublicProblem`. It must
  identify the objective, catalog, units, constraints and solver configuration
  used for SA and the human comparison.
- `async evaluate(positions, *, stop_file)`: **one evaluation maximum**, no hidden
  retries, reproductions or extra solves; cancellation must stop and reap any
  owned worker before returning. Real CPU/wall grants remain the adapter's duty.
- Exactly `{"legal": bool, "J": number-or-null, "wire_mm": number-or-null}`.
  Legal results require finite nonnegative metrics. Illegal results expose no
  scores. Diagnostics, extra fields and backend exceptions never enter prompts.

The budgeted wrapper reserves and signs a slot **before** invoking that adapter
or rejecting a wrong chiplet count. Out-of-package/overlapping placements reach
the constrained adapter and still consume the slot. Wire/schema errors are
rejected before admission and consume no slot. A per-lab OS lock prevents two
hosts from spending the same slot concurrently; other labs can proceed.

`proposal.config`, `proposal.reserved` and `proposal.finished` use the existing
signed flight ledger. Reservations bind the full layout, lab, model/provider/
payer, admission-policy hash, oracle identity, slot and grant reference. Reopening
a run verifies the chain and rejects changed configuration, including increased
budgets. Matching request-ID retries return the original receipt; changed layouts
with the same ID are refused. A crash after reservation remains charged and returns
`interrupted`; it never silently re-evaluates. Illegal/error/timeout/cancelled/STOP
outcomes remain charged. Grant expiry during a call also cancels/drains the adapter
and retains the charge. STOP refuses new slots and cancels/drains active adapters;
a late STOP cannot publish a successful result. Signed receipts serialize identically
on fresh CLI and replayed MCP calls.

## Isolation and descriptive tables

`PublicProblem` deliberately has no arbitrary prompt text, answer layout, human/SA
score, held-out field or free-form context. It contains only frozen public package
dimensions, ordered chiplet IDs/dimensions/powers, wire cap and oracle identity.
Each lab receives that same public problem, its budget and at most its last 16
feedback receipts. Other labs' proposals and results are excluded.

`harness.report(sa=..., human=...)` is an operator-only Python method, never a
CLI/MCP tool. Comparator objects carry the same oracle identity, J, wire and an
evidence reference; SA additionally carries the exact matching solve count.
Mismatches are refused. The table includes each lab's best J, wire at that J,
request ID, charged slots, completeness and differences from SA and the human
reference. A partial run or a run with no legal result remains explicit. Comparator
evidence does not enter lab prompts. No table of actual performance is claimed.

## Verification scope

`test_proposals.py` uses synthetic admission records and in-memory signing keys.
Its adapter returns arithmetic fixture values; these are not thermal results.
Real CLI/MCP processes exercise successful submission/replay, context, safe errors,
scope denial, operator-tool isolation, STOP, SIGINT and MCP cancellation. The shared
SLAB-043 matrix also checks discovery, schemas, invalid input, host scopes and wire
bounds for the new rows. Recorded-worker cancellation tests retain their existing
operations; the signer-owning proposal adapter has its own transport cancellation
proof, and proposal context is a bounded synchronous read.

Full container smoke includes real HotSpot solves and is not run under this
assignment's no-solves instruction. The repository has no npm manifest or TS
project; fabricated npm/tsc gates are not added. See VALIDATION.md for exact commands,
counts and unrun gates. Root still reviews budget enforcement/isolation; operator
carry is not review clearance or merge.
