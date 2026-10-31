# PR #23 review #56222: contract-valid memory and Python runtime independence

Source: `/workspace/sentilab`, branch `slab010-review`. Main base:
`200cda7accc0f3c619273178bb4db0232c62f316`. The original memory change was
cherry-picked as `b6bc110794865460324ef03477f2a195138bc30b`; that is the pre-fix
baseline for these regressions. Implementation commits:

- `33a294cd00db82dde307ce24155fbf34f5172ac2`: Python contract projection and required Node parity placement.
- `822244ca6fdb8700468789e06766dfb56f6de8cc`: task presence validation in shared routing and CLI parsing.

## Findings addressed

The signed ledger authenticates bytes; it does not validate evidence semantics.
The shared Python projection now applies the pinned contract's semantic rejection
rules before mutating its graph. Missing measurement semantics never creates a
measurement. Empty or duplicate support additions never replace the original
set. Withdrawal therefore removes the existing dependent memory from recall,
refuses new writes against it, and retains the original audit entry. Other
contract rules cover semantics agreement, support/link cycles, lifecycle and
acceptance, verification evidence, training taint, and review withdrawal epochs.
Rejected acceptance events cannot replace a valid board entry.

The original before/after-withdrawal Node parity test is preserved in
`sentilab_core.memory_conformance`, imported by `sentilab_core.conformance`.
The existing Node-enabled live-conformance CI command discovers it. Docker's
`test_*.py` discovery exercises the pure Python tests, including the 29 reviewed
contract vectors. No availability-based skip, Node runtime call, workflow edit,
contract edit, or reduced assertion was introduced.

Shared routing distinguishes omitted task from explicit `null`. CLI calibration
omits task; argparse uses a suppressed default so explicit JSON `null` counts as
presence in the mutually exclusive group. Calibration with task presence fails
in both CLI and MCP; normal suggestions, abstention and calibration still agree.

## Failure-before evidence

Tests copied into the separate worktree `/workspace/sentilab-review-before` at
`b6bc110794865460324ef03477f2a195138bc30b`, executed with the main checkout's
Python 3.12 environment:

- `MemoryTests.test_signed_measurement_missing_semantics_cannot_enter_memory`:
  `AssertionError: ValueError not raised`.
- `MemoryTests.test_signed_empty_support_overwrite_cannot_revive_memory` and
  `test_signed_duplicate_support_overwrite_cannot_revive_memory`: recall returned
  the existing memory instead of `[]`. Three probes: **3 failures / 3 tests**.
  Each probe first verifies the signed chain has no authentication error.
- `MemoryTests.test_correction_projection_matches_reviewed_contract_without_solves`
  with `PATH=/nonexistent`: **1 error / 1 test**, `FileNotFoundError: 'node'`.
- `ProjectionContractTests.test_reviewed_evidence_vectors_and_delivery_order`
  plus `MemoryProjectionConformance`: **25 failures, 76 errors / 4 tests** across
  vector subtests on the inherited Python implementation.
- `ProjectionContractTests.test_board_ignores_rejected_acceptance_events`:
  **1 error / 1 test**, inherited projection throws on the rejected transition.
  During implementation, keeping the new projection but omitting the board
  rejection filter instead returned the rejected `j=1, seq=10` entry.
- `MemoryTransportTests.test_calibration_refuses_explicit_null_task_in_cli_and_mcp`:
  **1 failure / 1 test**, MCP returned a successful calibration instead of error.
  The first fixed transport run also exposed argparse's `None` default issue;
  that was corrected, not waived.

## Current local proof (all commands exit 0)

```sh
.venv/bin/python -m unittest -q sentilab_core.test_memory sentilab_core.test_projection_contract sentilab_core.test_memory_transports sentilab_core.test_routing sentilab_core.test_ledger sentilab_core.test_gate sentilab_core.test_budget sentilab_core.test_signing sentilab_core.test_environment sentilab_core.test_history sentilab_core.conformance.CanonicalConformance sentilab_core.conformance.HistoryConformance sentilab_core.conformance.MemoryProjectionConformance
PATH=/nonexistent /workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_memory sentilab_core.test_projection_contract sentilab_core.test_memory_transports sentilab_core.test_routing
(cd contracts && sha256sum -c HASHES.txt)
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q sentilab_core sentilab_cli sentilab_mcp
git diff --check
```

Results: **82 tests** in the first command; **34 tests with Node absent** in the
second; **16 reviewed contract hashes** unchanged; dependencies, compilation and
whitespace checks pass. Node parity includes **244 prefixes of 29 reviewed
vectors**, the three signed probes, and the original correction fixture.

Additional read-only checks authenticated the retained **203-envelope** v0.4
live proof and compared its complete Python projection with the pinned JavaScript
projection: equal. Running `reproduce()` from `reproduce.py` equals the committed
`RESULT.json` exactly. These checks replay evidence, with no solves or model calls.

No full CI, solver, browser suite, container build, container health/security
check or network dependency audit was rerun for this round. The repository has
no npm/TypeScript manifest; no substitute manifest was added. Local subset success
is not full CI or independent review approval. Operator carry and review remain.

## Delivery tracking against ticket 23a5285a

Authorized CLI/MCP **memory write and invalidate** delivery remains outstanding
against ticket `23a5285a` until the room assigns a split ticket. The split was
requested in the #56222 thread; no new ticket ID or tracker update is claimed.
The existing host methods and read/audit transports do not complete the human's
every-capability requirement.

That follow-up must expose explicit write/invalidate operations through both
transports, bind authorization and tenant/ledger policy from trusted host context,
retain held-out and exact-scope refusal, validate evidence before admission/recall,
preserve append-only audit, and prove matching success/refusal behavior through
real CLI/MCP calls. It requires explicit authorization checks, not caller-selected
identity or ledger paths. This review round adds neither endpoint.

The eight synthetic held-out routing examples still give candidate accuracy 6/8,
decision accuracy 5/8, selective accuracy 4/5, abstention 3/8. This is interface
proof, not production Jev/ENGRAM accuracy evidence.
