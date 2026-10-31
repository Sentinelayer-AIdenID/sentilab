# SLAB-043 round 7: pin the descendant before releasing the fixture

Source/base: `dbb2f55236fc82e2b19d8a6b91c115566b421460` (round 6).
Warden reports PR #43 at `5b9c2a81221bb1f8f937046ea659b4233c3673a3`
as tree-identical to that source. This round changes only the execution test
fixture and this evidence; production cleanup and main are unchanged.
The fixture fix is `f238262c915019e4d95fa4c2a0913379b39f7d17`.

The descendant publishes its own PID. Both it and the worker then wait for a
go file. The observer opens a pidfd, asserts that the pinned descendant is
alive, and releases the fixture. Only then can the closed-pipe descendant
close stdout and the worker exit. Pin failure still fails the test; ESRCH is
not accepted as success. The final liveness assertion uses the same pidfd,
avoiding another exists/read race with an orphan reaper removing `/proc`.

All six witnesses retain their cleanup assertions, including the prohibition
on numeric PID/PGID signals. The handshake has a three-second deadline and
the descendant retains its finite four-second lifetime after release. A marker
written before natural exit (including a handshake deadline expiry) makes that
path an explicit test failure, so a slow test cannot mistake natural exit for
cleanup.

## Reproduction and base proof

The unchanged round-6 fixture passed 20/20 local runs with the reaper below;
the CI scheduling race did not reproduce without intervention. In a disposable
worktree at `dbb2f55`, inserting `await asyncio.sleep(0.05)` immediately before
`child_fd = os.pidfd_open(child)` reproduced both reported closed-pipe errors:
`ProcessLookupError: [Errno 3] No such process` (2 tests, 2 errors, exit 1).
The final fixture under the identical delayed-observer experiment passes
both tests (exit 0). The artificial delay is not in the committed test.

The final test file was copied unchanged into a separate worktree at
`b227c34e08d72f0c80dc5d038c987df0669b765e`, the round-5 source Warden
reported carried tree-identically onto PR #43, subsequently identified as
`4ad3fe63`. The published `4ad3fe63` Git object is not present in this box;
this is executed proof against its reported source, not independent published
tree verification. From `/tmp/slab043-round7-before`, the exact command was:

```sh
OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/sentilab/.venv/bin/python /tmp/slab043-round7-reaper.py /workspace/sentilab/.venv/bin/python -m unittest -v sentilab_core.test_execution.WholeJobCleanupTests
```

Result: **7 tests, 7 failures, exit 1; no errors or skips**. All six requested
witnesses remain meaningful:

| Test suffix in `WholeJobCleanupTests` | Failure on round-5 source |
|---|---|
| `test_closed_pipe_success_removes_descendants` | Pinned descendant still alive |
| `test_closed_pipe_failure_removes_descendants` | Pinned descendant still alive |
| `test_inherited_pipe_timeout_removes_descendants` | Pinned descendant still alive |
| `test_inherited_pipe_cancellation_removes_descendants` | Pinned descendant still alive |
| `test_reap_before_callback_timeout_never_signals_recycled_group` | Forbidden `killpg` called once |
| `test_reap_before_callback_cancellation_never_signals_recycled_group` | Forbidden `killpg` called once |

The seventh, `test_pidfd_setup_failure_reaps_worker_before_dispatch`, also
still fails on base because its worker remains in `/proc`. No unrelated
process was signalled. These are existing tests, with stronger synchronization
and liveness assertions, rather than new test cases.

## Twenty repetitions and the container blocker

The requested exact image command was attempted from `/workspace/sentilab`:

```sh
docker build --build-arg BUILD_SHA=x -t thermal-api:ci .
```

It exits **127: `docker: command not found`**. The namespace prerequisite for
a local dedicated PID 1 was also attempted:

```sh
sudo -n unshare --pid --fork --mount-proc sh -c 'echo namespace-pid=$$'
```

It exits **1: `unshare failed: Operation not permitted`**. Consequently,
**the required image or `python:3.12` container/PID-1 repetition is blocked,
not passed**. Warden was informed; a container-capable runner is still needed.

As additional local evidence, Python **3.12.3** ran the exact smoke unittest
invocation under a dedicated Linux child-subreaper. This supervisor reaps
adopted orphan descendants, but it is not PID 1 or the `python:3.12` image.
The exact supervisor created at `/tmp/slab043-round7-reaper.py` was:

```python
import ctypes
import os
import sys

libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
    raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')
child = os.fork()
if child == 0:
    os.execvp(sys.argv[1], sys.argv[1:])
status = None
while True:
    try:
        pid, result = os.waitpid(-1, 0)
    except ChildProcessError:
        break
    if pid == child:
        status = os.waitstatus_to_exitcode(result)
sys.exit(status if status is not None and status >= 0 else 1)
```

The exact final loop, from `/workspace/sentilab`, was:

```sh
export OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
passes=0
for attempt in $(seq 1 20); do
  if .venv/bin/python /tmp/slab043-round7-reaper.py .venv/bin/python -m unittest -q sentilab_core.test_execution > "/tmp/slab043-round7-final-${attempt}.log" 2>&1; then
    passes=$((passes + 1))
  else
    tail -n 24 "/tmp/slab043-round7-final-${attempt}.log"
  fi
done
printf 'final fixture: %s/20 passed (8 tests per run)\n' "$passes"
test "$passes" -eq 20
```

Observed: **20/20 pass, 8 tests per run, 160 tests total; exit 0**.
These counts do not claim container execution. Logs are local scratch files;
the commands and outcomes here are the committed evidence.

## Other local validation

Python commands below used the same three OpenBLAS/OMP environment variables.
The additional lane/stdio/fixture run passed **153 tests, exit 0**, with:

```sh
.venv/bin/python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_memory_transports sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform sentilab_core.test_research sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs sentilab_core.test_build_info sentilab_core.memory_conformance sentilab_core.conformance.CanonicalConformance
```

| Command | Observed result |
|---|---|
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_gb10_backend sentilab_core.test_execution` | 59 pass with the initial handshake; final execution module, including the pidfd postcondition and deadline-exit guard, is covered by the 20-run loop above |
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
| `make -C sundai_hotspot -j4 SUPERLU=1` | Pass; solver not executed |
| `git diff --check` | Pass |

Zero solves, model calls, or device access. No npm/TypeScript manifest exists,
and no artificial gate configuration was added. Full container/thermal/solver
gates remain unrun; the wider ticket is not declared complete. Carry, image
proof, and independent review remain with the operator. This is a surrogate
executor's evidence under recorded model substitution, not review clearance.
