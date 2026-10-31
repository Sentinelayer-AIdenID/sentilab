# SLAB-043 round 6: worker ownership through whole-group cleanup

Source/base is round-5 `b227c34e08d72f0c80dc5d038c987df0669b765e`, on top of
main `70e19986dd3b33fa8265d39f662959405d9d3dca`. No rebase was requested.
Warden reports the prior carry as PR #43 at `4ad3fe63`; this box has not
published or independently verified a new PR head. The deny-all finding was
accepted; this change addresses the remaining cleanup finding from #56554.
It supersedes round 5's claim that checking cached `returncode` solved cleanup.

`execution.py` still creates a separate session/process group before exec, but
now owns the `Popen` leader's reap explicitly. Async pipe reads and pidfd exit
notifications do not call `waitpid`. Even after the worker exits, its unreaped
leader reserves the PID while cleanup discovers its group members in `/proc`.
Each member is tracked by `(pid, starttime)` and a pidfd; membership and identity
are checked again after opening the descriptor. Signals require a matching
identity and use the pidfd, never a numeric PID or PGID. This also closes the
check-to-signal reuse window.

Cleanup freezes the group to a fixed point before killing its members, waits
for their pidfds to report exit, and only then reaps the leader. A fork during
an earlier scan is captured by the next scan. Success, refusal, inherited-pipe
timeout, and cancellation all use that cleanup, including repeated cancellation.
Worker startup stays on the event-loop thread, preserving the original direct
child relationship. Failed pidfd initialization closes stdin before any request
is sent, closes stdout, and reaps the idle worker before propagating the error.

This implementation requires Linux `/proc` and pidfds. The box's cgroup v2
mount is read-only; no cgroup or device access was attempted. Containment follows
the worker's process group; the existing lane subprocesses retain that group.

## Regression evidence

The unchanged final test file was copied to the disposable worktree
`/tmp/slab043-round6-before` at the full base above. Running:

```sh
/workspace/sentilab/.venv/bin/python -m unittest -v sentilab_core.test_execution.WholeJobCleanupTests
```

exits **1**, with **7 tests and 7 failures**. Six reproduce the requested finite
witness classes; the seventh covers pidfd initialization failure. All eight
execution tests, including the pre-existing completed-worker check, pass with
the fix. Test descendants have a four-second finite lifetime and pidfd teardown.
`killpg` is intercepted; no unrelated process or actual recycled PGID is signalled.
The two reuse witnesses model the unsafe group signal by delaying CPython's
real post-waitpid callback and capturing its attempted numeric target.

| Added test in `sentilab_core/test_execution.py` | Failure at base |
|---|---|
| `test_reap_before_callback_timeout_never_signals_recycled_group` | Expected `killpg` not to have been called; called once |
| `test_reap_before_callback_cancellation_never_signals_recycled_group` | Expected `killpg` not to have been called; called once |
| `test_inherited_pipe_timeout_removes_descendants` | worker returned with a surviving descendant |
| `test_inherited_pipe_cancellation_removes_descendants` | worker returned with a surviving descendant |
| `test_closed_pipe_success_removes_descendants` | worker returned with a surviving descendant |
| `test_closed_pipe_failure_removes_descendants` | worker returned with a surviving descendant |
| `test_pidfd_setup_failure_reaps_worker_before_dispatch` | worker still present in `/proc` after the setup error |

B7 declaration for each of the seven named tests above:
`sentilab_core/test_execution.py` fails on
`b227c34e08d72f0c80dc5d038c987df0669b765e` and passes with fix
`219801cf5b3caf8d0d95a4e768d113300fcaa2ad`. These are executed local results,
not independent review declarations.

The cancellation cases also repeat cancellation during cleanup. Every finite
descendant case asserts no raw PID/group signals, a pidfd signal, and no live
survivor. Existing tests and assertions are retained unchanged.

## Validation

Python commands use the existing Python 3.12 virtual environment with
`OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`.
Every final validation command below exited 0.

| Command | Observed result |
|---|---|
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_gb10_backend sentilab_core.test_execution` | 59 pass, including both real cancellation surfaces |
| `.venv/bin/python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_memory_transports sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform sentilab_core.test_research` | 71 pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs sentilab_core.test_build_info sentilab_core.memory_conformance sentilab_core.conformance.CanonicalConformance` | 82 pass |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | 55 pass |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs scripts/deck-data.test.mjs` | 303 pass |
| `(cd contracts && sha256sum -c HASHES.txt)` | All match |
| `node run-vectors.mjs` in `contracts/contract-0.2` and `contract-0.3` | 74 / 83 checks pass |
| `node run-view-vectors.mjs` in `contracts/view-envelope` and `view-envelope-v0.5` | 113 / 193 checks pass |
| `node run-paging-vectors.mjs` in `contracts/view-envelope-v0.6` and `view-envelope-v0.6.1` | 174 / 222 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | 44 envelopes current |
| `.venv/bin/python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` | Pass |
| `.venv/bin/python -m compileall -q sentilab_core sentilab_cli sentilab_mcp scripts/record_build_info.py` | Pass |
| `.venv/bin/python -m pip check` | No broken requirements |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Build passes; solver binary not executed |
| `git diff --check` | Pass |

An initial integration attempt spawned on a background thread, causing the
existing direct-child cancellation fixture to miss workers (13 failures).
Spawning returned to the event-loop thread; the same unmodified cancellation
matrix then passed on both CLI and MCP. This failed attempt is not a green gate.

No solves, model calls, or device access were performed. Docker is unavailable;
the full image, thermal, and live solver gates remain unrun, not passed. This
repository has no npm manifest or TypeScript configuration, and no dummy gates
were added. The broader pending capabilities remain in COVERAGE.md; `gb10.serve`
stays pending until its owner implementation merges. Carry/export verification,
independent review, CI, and merge remain with the operator. This evidence is a
surrogate executor's report under recorded model substitution, not a clearance.
