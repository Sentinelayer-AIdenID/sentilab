# PR25 prospective v4 review corrections

This is the response to claude-warden's 2026-10-31 07:54Z assignment and Carter
review #56312. It supersedes the admitted-call completion policy in the earlier
v4 validation receipt. **No real thermal solves or CI runs were made.** Execution
still requires exact-head review and explicit Warden release.

The available local carry base is `f8d99a8464d1941da3bbe25ea894a00e33ab7a93`.
The operator identifies its published carry as `aaaf128dce11d14033ec693177bc761f1ff346f3`.
The latter object and Git remotes are absent here. The export is a delta from the
local carry; correspondence to the published base requires operator verification.
This receipt does not claim a new published PR head or independent clearance.

## Corrections

1. A failed cheap freeze returns INCONCLUSIVE without entering any reference
   restart. The attempt has `baseline_failed` status, a reason, full lane history,
   final result and unchanged cumulative charges. The regression reproduces the
   review's 768 cheap calls followed by unwanted call 769 on the old source.
2. Worker timeouts retain original stdout/stderr bytes, readable replacement-decoded
   UTF-8 text, payload types, byte counts, command, timeout and structured EXIT status.
   Both byte and text TimeoutExpired payloads are tested, along with absent payloads.
   For retained calls, output streams are file-backed so a parent-enforced worker
   kill also preserves bytes; the parent supplies text and a parent-timeout record.
3. Each v4 call gets the minimum of 45 seconds, remaining fixture/headroom/aggregate
   CPU, wall to 12:00Z, remaining cumulative 90-minute solve wall and restart CPU.
   Admission requires at least the frozen measured p95. The bound is recomputed
   after reservation and retention I/O, which remain charged. The complete await
   includes worker acquisition/startup; neither solver nor worker adds grace time.
   A timeout cancels the call and immediately SIGKILLs the isolated process group;
   the worker is reaped before another admission. A timed-out or late-returned
   result cannot become a winner, and no later call is admitted after timeout.

The sequential runner pins its calling thread and inherited worker/solver threads
to one allowed CPU through cleanup, restoring the original affinity afterward.
This prevents multicore child execution from spending CPU faster than wall.
The retained kill latency is the measured process-group termination/reap interval.
It is separate from timeout overrun; scheduling and cleanup are not asserted to
have zero duration. Actual excess remains charged in SPEND. No finite overshoot
allowance or claim of mathematically zero OS scheduling latency is introduced.

The p95 is **0.524939 seconds**, nearest-rank over the five retained micro150
32x32 samples in `../micro150/TIMING.json`; PREREG pins the file's SHA256.
This is historical measured timing, not a new calibration or a guarantee for a
future cold worker under the new affinity. No calibration solves were authorized.

The approved prospective allocations remain micro150 48 CPU-min, headroom 72 and
aggregate 84, with 4,768/9,700/10,000 calls. The original Ascend910 PREREG, RESULT,
REPORT and SPEND are byte-identical to the local base. Ascend910 remains v3
INCONCLUSIVE and its 1,440.2945650000001 CPU seconds remain charged. Unknown historic
CPU and CI accounting remain unresolved; this patch does not allocate build CI.

## Validation

All runner evaluations use fake oracles and clocks. The worker protocol suite uses synthetic Python processes,
never HotSpot. Startup cancellation also uses immediate termination and carries
its measured kill/reap interval through the cancellation exception. Construction of real fixture catalogs reads source/binary hashes
and validates geometry without calling the solver.

Negative proof uses a separate worktree at the local base, never swaps the active
checkout. The baseline regression fails `769 != 768`; timeout payload checks fail
because `stdout.bin` is absent. All 13 initial new cap tests fail on that base.
The four existing overshoot tests now assert the newly required refusal/timeout
behavior; all four fail on the old source. No test was skipped or removed.

Thirteen individual mutations of the fixed source each fail assertions: 45-second
cap, fixture CPU, headroom CPU, aggregate CPU, noon deadline, cumulative solve wall,
restart CPU, p95 admission, rejecting a late return, immediate kill without grace,
measuring kill latency, bounded worker timeout, and single-CPU affinity restoration.
The headroom test isolates its bound from the normally coincident aggregate bound,
so deleting either cannot be hidden by the other.

The complete container/thermal regression and full-history secret-scan gates remain
**not run** under the allocation hold; Docker is unavailable in this box. The repo
has no npm manifest; synthetic npm/typecheck/audit commands are not its gates.
Required CI tests remain enabled and no workflow or smoke script was changed.
This is a review-ready worker patch, not an all-gates-green or ticket-completion claim.

## Commands and observed results

- `.venv/bin/python -m unittest -q sundai_controller.test_headroom sundai_controller.test_headroom_v4 sundai_controller.test_headroom_caps`:
  **101 passed**, 169.518 seconds. After the final startup-cancellation correction,
  `.venv/bin/python -m unittest -q sundai_controller.test_headroom_caps` passed
  **15 tests**, including the newly added startup regression: **102 unique headroom
  tests checked** across these commands. The earlier combined pass was 100 tests.
- `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller test_experiment test_safety_property test_tfl08_leaderboard)`:
  **65 passed**, including 1,000 generated safety cases.
- `(cd sundai_hotspot && ../.venv/bin/python -m unittest -q test_tap_oracle.WarmWorkerProtocolTests test_tap_oracle.HotSpotIntegrityTests test_tap_oracle.HotSpotGridParserTests test_tap_oracle.HotSpotOracleTests.test_illegal_off_grid_layout_is_rejected_before_worker_start test_tap_oracle.HotSpotOracleTests.test_custom_hotspot_binary_is_bound_and_passed_to_worker)`:
  **9 passed**, rerun after the final startup correction (3.692 seconds).
- `.venv/bin/python -m compileall -q sundai_controller/headroom.py sundai_controller/test_headroom_v4.py sundai_controller/test_headroom_caps.py sundai_hotspot/tap_oracle.py sundai_hotspot/tap_oracle_worker.py`:
  passed. `git diff --check`: passed.
- `make -C sundai_hotspot -j4 SUPERLU=1`: passed; build only, zero solves.
- `(cd contracts && sha256sum -c HASHES.txt)`: **11 passed**.
- `(cd contracts/contract-0.2 && node run-vectors.mjs)`: **74 passed**.
- `(cd contracts/view-envelope && node run-view-vectors.mjs)`: **113 passed**.
- `node --test web/test/sentilab-parity.test.mjs`: **39 passed**.
- `node web/test/make-sentilab-demo.mjs --check`: **44 envelopes current**.

The startup regression also fails by assertion on the old source: the worker
reaches cleanup without immediate termination enabled. On the fixed source its
fake-clock kill/reap interval survives propagation through the pool, oracle and
cancellation boundary. The actual runtime interval still requires measurement
on any later authorized thermal execution; these fake values are not timing data.
