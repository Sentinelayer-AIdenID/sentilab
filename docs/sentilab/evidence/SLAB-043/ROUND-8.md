# SLAB-043 round 8: verify fixture identity before teardown

Source: `/workspace/sentilab`, branch `agent/slab043-current-main`.
Carry base: `4d24d348c0116b19746e3fc521c47bce6f108bdf`.
Fix commit: `5d98c39a4ff13121bc68fb3625dd3e33bc355f9d`.
No rebase onto the newer main. The intervening `6830b6f` commit records
round-seven evidence only. Warden reported published PR #43 at `ed2b3ec6`
with green CI; that is not a claim about this round's unpublished head.

## Fix

Option **1a**, entirely in `sentilab_core/test_execution.py`: the child writes
its PID/starttime identity before publishing its ready marker. After opening
the candidate pidfd, the observer compares `/proc/<pid>/stat` with that recorded
identity and checks the pidfd is still live **after** the procfs read. A pidfd
that became readable cannot become live again, so an exit/reuse during the
read also fails verification. Only then is `child_verified` set and the go
file released. Teardown signals only verified descriptors; rejected candidates
are closed without a signal. The timeout is unchanged. Finished timeout tasks
are collected even when the observer rejects the candidate.

Production `execution.py` is byte-identical to the carry base, verified both
with `git diff --exit-code` and a byte comparison against `git show`.
SHA-256: `fb04c97de470db3ca3d5258995682cb31bc14f97e7b6d65aa16b196ea3d8695e`.
No other production file changed.

## Counterexamples and retained checks

Six new `FixtureIdentityTests` exercise the actual `WholeJobCleanupTests.exercise`
harness with a mocked worker, procfs, pidfd and signals. They start no processes
and send no real signals. The delayed-observer case waits until a mock worker
has consumed the **actual timeout argument (0.35 seconds)** and raised timeout,
then models a live replacement with the same PID and a different starttime.
It asserts timeout precedes pinning, verification fails, go is never released,
the descriptor closes once, and no signal is attempted. This is a bounded
model of the schedule, not a claim of inducing real kernel PID reuse.

The new class was copied into a disposable worktree at the carry base, with
its JSON import. The original `exercise()` was confirmed byte-identical to
`git show 4d24d348:sentilab_core/test_execution.py` using `ast.get_source_segment`.
The same command was run in that worktree and on the fix:

```sh
/workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_execution.FixtureIdentityTests
```

| New test | Carry base | Fixed harness |
|---|---|---|
| `test_delayed_observer_rejects_reused_pid_without_signalling` | FAIL | PASS |
| `test_exited_pidfd_is_rejected_without_signalling` | FAIL | PASS |
| `test_exit_during_identity_read_is_rejected_without_signalling` | FAIL | PASS |
| `test_missing_identity_is_rejected_without_signalling` | FAIL | PASS |
| `test_pin_esrch_is_a_failure` | PASS | PASS |
| `test_natural_exit_is_a_failure_with_owned_teardown` | PASS | PASS |

Base: **6 tests, 4 failures, no errors/skips, exit 1**. Every failing
counterexample reports `Expected 'pidfd_send_signal' to not have been called`
and the mocked call `call(900001, <Signals.SIGKILL: 9>)`. Fixed: **6 pass,
exit 0**. The last two tests preserve existing rejection behavior; they are
not claimed as new failures on the base.

All six original whole-job cleanup witnesses remain. The final test module
was copied to a separate worktree at
`b227c34e08d72f0c80dc5d038c987df0669b765e` (Warden-reported source of
published `4ad3fe63`, whose object is absent locally), then run there:

```sh
/workspace/sentilab/.venv/bin/python -m unittest -q \
  sentilab_core.test_execution.WholeJobCleanupTests.test_reap_before_callback_timeout_never_signals_recycled_group \
  sentilab_core.test_execution.WholeJobCleanupTests.test_reap_before_callback_cancellation_never_signals_recycled_group \
  sentilab_core.test_execution.WholeJobCleanupTests.test_inherited_pipe_timeout_removes_descendants \
  sentilab_core.test_execution.WholeJobCleanupTests.test_inherited_pipe_cancellation_removes_descendants \
  sentilab_core.test_execution.WholeJobCleanupTests.test_closed_pipe_success_removes_descendants \
  sentilab_core.test_execution.WholeJobCleanupTests.test_closed_pipe_failure_removes_descendants
```

Observed: **6 failures, no errors/skips, exit 1**. These are the original
surviving-descendant/forbidden-broadcast assertions, not failed setup.

## Local gates

Python **3.12.3** in the existing dependency-installed `.venv`. Python test
commands used `OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`.
Warden's round-seven instruction permits direct Python repetitions; these
are **not** container builds or dedicated-PID-1 runs.

```sh
export OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
. .venv/bin/activate
passes=0
for attempt in $(seq 1 20); do
  if python3 -m unittest -q sentilab_core.test_execution > "/tmp/slab043-round8-repeat-${attempt}.log" 2>&1; then
    passes=$((passes + 1))
  else
    tail -n 24 "/tmp/slab043-round8-repeat-${attempt}.log"
  fi
done
printf '%s/20 passes (14 tests per run)\n' "$passes"
test "$passes" -eq 20
```

Observed: **20/20 pass, 14 tests per run, 280 total, exit 0**.

| Command | Observed result |
|---|---|
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_gb10_backend sentilab_core.test_execution` | 65 pass |
| Lane/transport command below | 153 pass |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | 55 pass |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs scripts/deck-data.test.mjs` | 303 pass |
| `(cd contracts && sha256sum -c HASHES.txt)` | All match |
| `node run-vectors.mjs` in `contracts/contract-0.2` and `contract-0.3` | 74 / 83 checks pass |
| `node run-view-vectors.mjs` in `contracts/view-envelope` and `view-envelope-v0.5` | 113 / 193 checks pass |
| `node run-paging-vectors.mjs` in `contracts/view-envelope-v0.6` and `view-envelope-v0.6.1` | 174 / 222 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | 44 envelopes current |
| `.venv/bin/python -m compileall -q sentilab_core sentilab_cli sentilab_mcp scripts/record_build_info.py` | Pass |
| `.venv/bin/python -m pip check` | No broken requirements |
| `.venv/bin/python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` | Pass |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Pass; solver not executed |
| `git diff --check` | Pass |

All rows above exited 0. Exact lane/transport command:

```sh
.venv/bin/python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_memory_transports sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform sentilab_core.test_research sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs sentilab_core.test_build_info sentilab_core.memory_conformance sentilab_core.conformance.CanonicalConformance
```

`docker build --build-arg BUILD_SHA=x -t thermal-api:ci .` exited **127**:
`docker: command not found`. New container/thermal/solver/secret-scan gates
remain unrun locally; CI after carry is still required. No npm/TypeScript
manifest exists, and no artificial configuration was added. CPU only; no
solves, model calls or device access. The broader ticket is not marked done.

Handoff: `git bundle create /workspace/slab043-v8.bundle 4d24d348..HEAD`.
Operator export verification, CI and assigned review remain outstanding.
This records a surrogate executor's evidence under recorded model substitution;
READY is not publication, clearance or merge.
