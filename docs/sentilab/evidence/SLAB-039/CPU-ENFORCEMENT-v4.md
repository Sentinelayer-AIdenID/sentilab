# Prospective v4 CPU enforcement (room #56358)

Execution remains held for review of the exact published head. This amendment
runs no micro150/HotSpot solve and does not relabel Ascend910 v3.

The fixture ceiling is **2879.705435 CPU-s**, exactly 72 minutes minus the retained
Ascend910 charge of 1440.294565 CPU-s. The existing fixture, headroom, aggregate,
restart, call-count, noon-deadline and cumulative-wall limits still apply.

The declared rate Q is 1 CPU-s/wall-s by default (supported rates: 1, 2, 8).
Every existing runner thread is confined to the same affinity mask of at most Q CPUs; worker
processes and newly created threads inherit it. Fewer available CPUs keep the
Q-derived wall bound conservative. A dedicated runner with no
pre-existing children is required. Unsupported confinement fails closed.

H is 1 CPU-s. Sampling is every 0.01 wall-s, at most 0.08 CPU-s at Q=8 before
sampling/scheduling overhead; the rest of H reserves startup and shutdown work.
Each CPU-derived wall bound is `(remaining CPU - H) / Q`. The admitted bound is
the minimum of these, 45 seconds, time to noon, and remaining cumulative solve
wall. The retained p95 (0.524939 s) is only an admission floor, never a cap.
The live meter cancels when measured CPU plus H reaches the allowance. Any
actual excess remains charged; the tests require it never exceed allowance + H.
An excess is not a renewed allowance or permission to keep solving.

Linux `/proc/<pid>/stat` counts process threads and already-waited child CPU.
Parent-first traversal reads every thread's children list. Parent identity is
checked to avoid claiming a reused PID. A Linux subreaper adopts orphaned
children; cleanup kills survivors and waits for them. An empty `/proc` scan must
also receive kernel confirmation that no children remain. CPU is sampled through
confirmed reap, including work after cancellation/kill. The final charge cannot
be dropped by a temporary process-scan dip. Historical v1-v3 keeps its original
`getrusage` accounting; its source regression tests remain enabled.

`SPEND.runs.jsonl` is an append-only per-call ledger linked from `SPEND.json`.
It records metered CPU, admitted allowance, Q/H, stop CPU, CPU after stop (when
stopped by the outer guard), and reaping confirmation. Reservation stays active
on an uncompleted cleanup or interrupted write, requiring reconciliation before
another invocation. Per-attempt full evaluation artifacts remain in place, and
the attempt snapshots/hash-binds the enforcement module alongside the runner.
No result enters the winner set before cleanup. Late, cancelled, partial, or
over-budget output is not accepted. Complete frozen C remains a prerequisite
for every reference call.

## Validation

No new scientific result is reported. Unit tests use fake oracles/clocks; the
process tests use tiny Python/hashlib thread loops and a short forked child.

- Focused CPU/process suite: 29 passed, including Q=1/2/8, a child forking a
  grandchild, CPU after a stop signal, cancellation, failed metering, all runner
  thread masks, PID reuse, and final kernel reap confirmation.
- Seven new cap regression methods fail on pre-change source
  `b2975e5fc6e7b401fb4014bae9e92095b5e03a42` in a disposable worktree.
- Eight isolated enforcement mutations fail assertions: omit live children,
  omit reaped CPU, omit subreaper, confine only the main thread, ignore Q, skip
  reaping, omit kernel confirmation, or claim a reused unrelated PID.
- Controller tests: 57 passed, including the 1,000-case safety property.
- Synthetic worker/protocol/parser tests: 7 passed.
- Contract hashes: 11 matched; contract vectors: 74 passed; view checks: 113
  passed; browser parity: 39 passed; demo fixture: 44 envelopes current.
- `make -C sundai_hotspot -j4 SUPERLU=1`, Python compilation and
  `git diff --check` passed. Building the C binary did not run it.

Full combined headroom validation is recorded in the carry manifest after the
final test run. Repository README/CI commands define the gates (Python/C and
plain JavaScript; no npm manifest was added). Docker/thermal smoke and CI remain
held, not passed, under the existing execution/allocation restriction. The
original Ascend910 PREREG/RESULT/REPORT/SPEND files remain unchanged.
