# SLAB-052 round 2: authority and STOP after real lock waits

Source base: `42a68ebca751719d41de499bc57219ae1bbc815b`.
Warden reports that source was carried byte-identically as PR #54 `5a26d1a9`.
The published object is absent in this box, so base regression execution below
uses the supplied source, not an independently verified published checkout.

The reservation guard runs inside the ledger append lock, after the soundness
read, then takes the registry publication lock. It rereads the complete current
admission and grant, checks STOP, and signs the current provider, payer and policy
hash while publication remains locked. The scheduled adapter task checks again
after its ledger/registry waits; revocation or a policy change cannot start the
adapter using a previously charged reservation. The charge remains in history.
The finish guard checks STOP after its append wait and removes successful metrics
from the new receipt. It does not rewrite signed history or genuine failures.

`sentilab_core/test_proposal_locks.py` uses separate open file descriptions and
actual `flock` contention. A failed nonblocking syscall observes contention,
then the blocking syscall is real. Tests publish reviewed fixture registries or
write STOP while the other holder owns the lock. No sleep establishes ordering.
All signing keys stay in memory; the adapter returns arithmetic fixture values.

Every test below fails on unchanged `42a68eb` (9 failures, no errors/skips) and
passes with the fix (9 passes):

| Test suffix (all start with `test_`) | Pre-fix failure |
| --- | --- |
| `revocation_during_rows_wait_refuses_without_charge` | `NotAdmitted not raised` |
| `revocation_during_reservation_wait_refuses_without_charge` | `NotAdmitted not raised` |
| `reservation_uses_current_provider_payer_and_policy_after_wait` | signed provider/payer/hash differ from current authority |
| `revocation_during_start_wait_keeps_prior_charge_without_call` | `evaluated != admission_revoked` |
| `changed_provider_payer_during_start_wait_keeps_original_reservation` | `evaluated != admission_revoked` |
| `stop_during_reservation_wait_refuses_without_charge` | returns a charged stopped receipt instead of refusing without charge |
| `stop_during_start_wait_keeps_prior_charge_without_call` | `evaluated != stopped` |
| `stop_during_finish_wait_signs_stopped_and_keeps_charge` | `evaluated != stopped` |
| `publication_waits_through_signed_reservation` | publication never contends on the registry lock |

The finish witness also preserves an earlier signed adapter failure and charge
byte-for-byte, verifies the chain, and replays that failure unchanged after STOP.
The start witnesses verify zero adapter calls and retention of the genuine
reservation. On the base, which lacks a start lock, they encounter the later
finish lock and expose the forbidden call/result.

Reproduction used a separate worktree, never a revert of the working checkout:

```sh
git worktree add --detach /tmp/slab052-r2-base 42a68eb
cp sentilab_core/test_proposal_locks.py /tmp/slab052-r2-base/sentilab_core/
(cd /tmp/slab052-r2-base && /workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_proposal_locks)
# exit 1: Ran 9 tests; FAILED (failures=9)
.venv/bin/python -m unittest -q sentilab_core.test_proposal_locks
# exit 0: Ran 9 tests; OK
```

Validation uses Python 3.12.3 and Node v22.23.3, the existing virtualenv, and
`OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`.
This is worker proof, not independent review. Original proposal/conformance tests
are unchanged. No labs, thermal solves, model calls or device access were run.
The real HotSpot reproduction test and container smoke remain unrun under the
explicit no-solves instruction. Docker is absent. Generic npm/TypeScript gates
are inapplicable: this repository has no npm manifest or TypeScript project.
Root's external 11 isolation/budget/restart controls were not supplied in this
box; their independent rerun and operator carry remain pending.

## Gate results

All commands below exited 0. The full CPU-only selection is the unchanged
selection documented in [VALIDATION.md](VALIDATION.md); the helper at
`/workspace/slab052-safe-gates.py` executes that selection and excludes exactly
the one named real HotSpot reproduction test.

| Command (repo root, virtualenv on PATH) | Result |
| --- | --- |
| `PYTHONPATH=. python /workspace/slab052-safe-gates.py` | 361 tests, pass (242.494 s); includes all 20 original proposal tests, all 19 shared conformance tests, and 9 new lock tests |
| `python -m unittest -q sentilab_core.test_proposal_locks` | 9 tests, pass; same 9 fail on supplied pre-fix source |
| `python -m unittest -q sentilab_core.conformance sentilab_core.memory_conformance` | 35 tests, pass |
| `python -m sentilab_core.test_resultcheck --parity` | 9 tests, pass |
| `node --test web/test/*.test.mjs scripts/deck-data.test.mjs` | 345 tests, pass; no skipped tests |
| `python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` | pass |
| `python -m compileall -q sentilab_core sentilab_cli sentilab_mcp` | pass |
| `pip check` | no broken requirements |
| `git diff --check` | pass |

An initial coverage-check invocation omitted its required path and exited 2;
the corrected command above passed. No production file changed during the final
core/contract/browser gate runs. Existing proposal and conformance tests, and the
admission implementation, remain byte-identical to the supplied base.
