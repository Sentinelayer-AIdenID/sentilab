# CI allocation 56314

This controller enforces a **prospective** allocation: 100 reserved HotSpot launches
and 900 CPU seconds per workflow run, with at most 200 admitted runs before
2026-11-01 18:00:00 UTC. It never charges the experiment allowance. Historic use is
unknown; a visible Actions run count is neither a quota nor a measurement.

## Admission and rollout

The `pull_request`/main-push workflow (`ci.yml`) has **no write-token job**.
Its `allocation-proof` job runs fake tests first; `admission` then executes the
trusted base controller with `--read-only` and `contents: read`. It polls the
immutable Git slot receipt for up to 180 seconds, then uploads a local admission
artifact for `container`. Reading never creates, updates, deletes or refunds a
slot. Missing, unreadable, corrupt, expired, duplicate or mismatched admission
fails closed. The existing bounded owner rollout exception is described below.

`ci-allocation-admission.yml` separately handles `workflow_run: requested` for
`CI`. Only its `reserve` job has `contents: write`, with `actions: read` and
`pull-requests: read` for the metadata API (including private repositories). It checks
out `github.sha`, the **default-branch snapshot** for that event, with credentials
persistence disabled. It installs no PR dependencies, downloads no PR artifacts
and executes no upstream code. Its sole input is GitHub-authenticated run/PR/commit
metadata. The Git database API's commit creation and atomic create-if-absent slot
refs still supply durable reservation; the PR token cannot write them.

The writer validates repository, exact workflow path, event, run ID and first
attempt; re-reads the upstream run to refuse changed or already terminal requests;
and accepts only default-branch pushes or a single open PR targeting that branch.
For a PR it resolves the current merge commit through the API and checks its two
parents against the current base and the upstream run's head. For a push,
head/build are the pushed SHA. The reader requires exact equality with its own
repository/run/attempt/job/matrix/head/build identity. If a queued PR's merge ref
has moved, the slot may be charged but the old run cannot execute against that
mismatched receipt. Missing/ambiguous PR metadata (including fork events without
PR association), a pending merge SHA, API denial and source drift all refuse;
none falls back to a guessed SHA or a run-count estimate.

This uses the durable ref as the cross-workflow receipt, not a potentially lost
or expired Actions artifact as the quota. The writer also uploads
`allocation-owner-admission-RUN-ATTEMPT` for review; the PR-side copy remains
`allocation-admission-RUN-ATTEMPT`. The existing separate completed-event terminal
workflow needs only read permissions and retains runner-loss/full-charge handling,
combined CPU/launch violations and their known higher charges.

**Trade-off:** admission can reserve before fake proof finishes, and delayed
writers or source drift can waste a slot without workload. Reservations are never
refunded, including when the writer loses its response. A bounded reader wait
costs an extra job/latency and can fail under runner congestion. Counting prior
settlement artifacts instead would lack atomic reservation across overlapping
runs and would undercount pending, lost, deleted or expired artifacts. Keep the
immutable slot ruleset and owner history debit as the durable authority.

The writer workflow and controller must be reviewed and installed on the default
branch before normal PR admission can work. A base with the older controller but
without `--read-only` support fails closed; it does not use bootstrap. Preserve
all required CI suites during this rollout. The bounded owner-authorized inline
bootstrap remains available only when the base has no controller at all. It
needs no write token and does not claim global-quota enforcement.
[GitHub's workflow_run documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
confirms that the workflow must exist on the default branch, uses that branch's
SHA, can receive a write token, and does not emit `requested` for reruns. Attempts
above one are refused by both admission paths. No `pull_request_target` execution
is introduced. End-to-end Actions scheduling and real cgroup proof remain rollout
checks; local fake API proof does not establish that they have occurred.

The PR introducing this controller cannot run a module absent from its trusted
base. For that rollout window only, admission inspects `git ls-tree` at the
verified base SHA. If and only if `scripts/ci_admit.py` is absent from that tree,
inline isolated Python (stdlib only) first validates an owner rollout authorization
and then emits a successful receipt with
`"mode": "bootstrap"`, `"reason": "controller absent at base <sha>"`, the base SHA,
full run identity, and the same 100-launch/900-CPU-second local limits. It does
**not** invent a durable slot or claim global admission was enforced. Errors in
Git inspection, an existing controller, the store, or owner configuration never
fall back to bootstrap; even a tracked controller missing from the checkout fails.
Once the controller is on the base branch, normal durable admission is mandatory.
The exception is tied to base contents, not a claim that only one workflow can
run during rollout. Owner accounting must include this rollout window when
choosing the historical debit; its run artifacts provide the measured evidence.

The repository owner supplies `CI_BOOTSTRAP_AUTHORIZATION` as a repository Actions
variable. Access to edit this variable must be restricted to the allocation owner.
It is configuration, never a secret. Missing configuration refuses bootstrap.
This closed example authorizes **zero** runs; no actual owner approval is invented
by the controller or this document:

```json
{
  "schema": "ci-hotspot-bootstrap-authorization-v1",
  "allocation_id": "56314",
  "authorization_id": "owner-assigned-rollout-reference",
  "approved_by": "owner approval reference",
  "repository": "OWNER/REPOSITORY",
  "workflow_path": ".github/workflows/ci.yml",
  "expires_at": 1793556000,
  "runs": []
}
```

GitHub Actions snapshots repository variables when a run is created; setting a
variable while an earlier job runs does not update that run's snapshot. A rerun
takes a fresh variable snapshot but keeps the original workflow source. Create a
**new run at the patched head**; do not rerun the older, unpatched bootstrap run.
Before checkout, the admission job writes canonical `context.json` (sorted keys,
compact separators, no newline) and its SHA-256 to `context.sha256`, prints the
digest, and uploads `allocation-context-<run>-<attempt>` with `always()`. This
records actual `GITHUB_SHA`, run ID, attempt, repository, workflow ref, container
job/matrix and PR head/base. Attempt `"1"` refuses without authorization. Retain
its context and attempt-specific admission artifacts, which record the identity,
base and a zero-workload debit. The owner then sets a **single-entry** authorization for that same run ID and attempt `"2"`,
pinning the independently downloaded raw context in `context_json` and its digest
in `context_sha256`, alongside `base_sha` and the complete `identity`
(repository, run_id, attempt, job
`"container"`, matrix `{}`, head_sha and build_sha = `GITHUB_SHA`). Keep the same
head, build and base; read the actual build SHA from attempt 1's context artifact
before authorizing attempt 2. Preserve and hash the raw prior context untouched.
Live context must match every field exactly except `GITHUB_RUN_ATTEMPT`: the
live attempt must equal the authorized decimal string and the pin must be its
immediate predecessor. Missing, noncanonical, conflicting or incorrectly hashed
context refuses admission and retains a full conservative debit. Re-running the
failed jobs admits attempt `"2"` only if every
field still matches; any drift requires a new authorization before execution.
Attempts must be decimal strings and match exactly; `"1"` and `"3"` cannot reuse
the attempt-2 authorization. The durable controller's rerun policy is unchanged.
Every listed identity reserves a separate 100 launches and 900 CPU seconds, including lost/failed runs;
IDs cannot repeat and the list is bounded to 200 entries. Source SHAs, repository,
workflow path, attempt, and expiry must match before the inline branch runs.
This is a bounded owner rollout allowance **outside** the durable 200-run counter,
not global-quota enforcement and not a one-workflow or one-run guarantee.
The owner must include every authorized rollout identity in the historical debit
before enabling normal admission; never refund it because an artifact was lost.
An approval added after execution is retrospective accounting, not proof of
prospective authorization. No actual rollout authorization has been installed by
the implementation box.

Admission records the authorization reference, approver reference, expiry,
allowlist size and SHA-256 of its canonical JSON, plus a `rollout_debit` bound to
the run/attempt and full reservation. The receipt also records `authorized_attempt`;
the container validator and meter precheck bind it to the receipt identity and
`GITHUB_RUN_ATTEMPT`. Archive authorization revisions and retain
the allowlist until all terminal witnesses have been produced. The trusted
default-branch `workflow_run` job receives the owner variable independently of
PR artifacts. It binds the event run, attempt, head, PR base and workflow path
to the owner entry. The downloaded admission and settlement must match the
authorized identity, including build SHA, job and matrix, before any measurement
is accepted. Attempt 1's refusal artifact remains a separate zero-workload record;
it cannot be matched to attempt 2. Missing or unverifiable terminal evidence still
gets a conservative full charge, not an inferred zero. It reconciles matching bootstrap identities before consulting the
durable slot store. A valid measured settlement remains measured; a lost or
malformed settlement remains unknown/full charge with the same rollout debit.
Absent/unverifiable authorization and no matching durable slot also stay
unknown/full charge: lack of a slot cannot prove that bootstrap work was zero.

`container` is a required check and has `needs: admission` plus `if: always()`.
It downloads admission data first; its first shell step validates it **before
checkout or workload execution**. An unsuccessful admission job or a missing,
refused, malformed, mismatched, or out-of-bounds receipt exits 1 with
`Container admission failed:`. A bootstrap receipt must match the trusted base
SHA and reason. Only a validated receipt reaches the same meter, launch gate,
required suites, and terminal recovery. Settlement JSON includes the admission
receipt, so bootstrap is visible even after interrupted recovery.
`scripts/tests/test_ci_workflow.py` executes these workflow shell blocks and checks
that every required job with dependencies uses `always()`; upstream failure must
produce a failed `container`, never a skipped required check.

The allocation owner must first create a commit whose entire message is JSON:

```json
{
  "allocation_id": "56314",
  "historical_runs_debit": 200,
  "historical_consumption": "unknown; owner-selected conservative debit"
}
```

The illustrated debit **closes** admission. The owner must choose a justified
conservative debit, not silently assume zero. Point
`refs/tags/ci-allocation-56314/bootstrap` at that commit. Its tree can be the reviewed
main tree. Configure a tag ruleset for `ci-allocation-56314/**` that forbids updates
and deletion, while allowing creation of new slot refs. Restrict administration of
that ruleset and bootstrap to the allocation owner. No controller path initializes,
updates, deletes or refunds a ref. Missing/unreadable/corrupt bootstrap or slots
refuse admission. Bootstrap lineage is bound into every slot commit.

Slots `slot-001` through `slot-200` are atomic create-if-absent refs pointing at a
commit with allocation id, slot, bootstrap SHA and full run identity. Concurrent
creators retry after conflict, re-reading the counter; a lost response retains its
reservation. Unreferenced commits created before a failed claim authorize nothing.
Each run reserves its entire 100/900 allowance. Attempt >1 and duplicate run ids
are refused, so a rerun cannot reset either per-run budget. Start a new workflow
run for a retry; it consumes a new global slot. The single supported workload is
job `container`, matrix `{}`. Adding jobs/matrix axes requires a shared accounting
design first; identity validation refuses unsupported shapes.

After the base-controller rollout, normal operation requires the owner bootstrap
ref and a successful controlled CI run. Missing owner configuration fails closed.
Rollback closes admission by exhausting the owner debit **before any slots exist**,
or disabling new workflow dispatches at the repository level; retain all existing
refs/artifacts. Do not revert to unmetered HotSpot execution. Workflow changes need
elevated review under SWE Excellence Framework sections F.2 and O.1.

## Launch boundary

CI builds HotSpot with `CI_ALLOCATION=1`. Its compiled `ci_entry.h` guard refuses
entry unless `sundai_hotspot/ci_gate.py` supplies a one-use inherited socket. This
check survives `cp` and renaming. Changing a filename or setting an environment
flag alone cannot authorize entry. Both the TAP worker and legacy TAP caller use
the wrapper. Example scripts that invoke the binary directly will fail in CI. A refused direct
entry also reports a violation to the broker, closing further admission and failing
the container job even if a caller ignores the nonzero exit.

The wrapper requests a slot from the host broker before spawning. The broker
locks and fsyncs the shared append-only JSONL journal before responding. It records
process start before the wrapper releases the C entry guard. Slots are never
refunded: failures, timeouts, signals, startup errors and retries consume them.
A failed transport/reservation starts no child. Workers in copied trees connect to
the same loopback broker; they never get a ledger file to reset. An external kill
that prevents the wrapper from settling leaves an outstanding reservation, which
the host finalizer settles as `interrupted`, without inventing an exit code.

This is an execution/accounting guard for reviewed CI source, **not a security
sandbox for malicious code with root access or code that rewrites the gate**.
The full journal distinguishes reservations, starts, exit codes and settlements;
`launches_reserved` is a conservative charge, not a claim that every reservation
entered the solver. Every record is bound to repository, run, attempt, job, matrix,
PR head SHA and the synthetic merge/build SHA in the journal's opening identity.

## CPU boundary

`scripts/ci_cpu_meter.py` creates a fresh cgroup-v2 subtree with
`cpu.max = 100000 100000` (100,000 microseconds of CPU quota per 100,000-microsecond
period). This permits bursts around period boundaries: it does not guarantee a
one-CPU bound over every rolling second and is not a cumulative CPU cap.
Its `host` leaf contains the job shell and a
**dedicated** Docker daemon. The daemon explicitly uses `cgroupfs` and the allocation
parent for all build and runtime containers. Docker's integrated BuildKit passes
this parent to its runc executor. The existing runner Docker socket is never used.
Dependencies, compilation, smoke tests, startup, health/origin-lock checks, daemon
work and exited descendants are included by the parent's cumulative `cpu.stat`.
Build cache is disabled, so a cached numerical suite cannot masquerade as a fresh
execution. Required smoke suites and their assertions are unchanged.

The out-of-group supervisor's `getrusage(SELF)` CPU delta from the initial cgroup
sample through the final sample is added, including broker threads. The isolated
Python entry helper initially starts outside the cgroup and blocks on its release
pipe. After attaching it, and before releasing any workload, the supervisor reads
the helper's cumulative user/system CPU counters from `/proc/PID/stat`. It adds
two clock ticks (one per truncated counter) to make a conservative startup debit.
This bounds the pre-attachment CPU; any helper CPU between attachment and that
sample is deliberately double charged. The debit participates in the pre-release
budget check, every in-flight observation, and the final accounted CPU total.
An unreadable counter prevents release. If cancellation, expiry or attach failure
prevents sampling, the helper is killed/reaped without release; the supervisor's
`getrusage(CHILDREN)` delta supplies its full CPU debit instead. Other children
reaped in that interval could only increase that conservative debit. An unreaped
helper makes the total unknown and charges at least the full reservation.

The artifact names this component `helper_startup_cpu_seconds` and records its
measurement method. `cpu_seconds` is the cgroup delta plus supervisor delta plus
this conservative startup debit, not a claim of exact disjoint measurement.
The boundary includes the helper's pre-attachment lifetime, but excludes the
supervisor's own interpreter/setup CPU before its baseline and serialization after
its final sample. It is not whole-lifetime accounting of the CI runner or meter.
This is deliberately broader than solver CPU. Process-tree CPU
from the mesh runner cannot account for a separately managed Docker daemon, so it
is not used as a fallback. Checkout, admission, artifact transfer and the unrelated
browser/contracts/secret-scan jobs are outside the container-job boundary.

The monitor samples every 50 ms and stops at 870 CPU seconds, reserving 30 for
in-flight work, observation lag (maximum 2 wall seconds), quota burst, supervisor
work and killing/draining descendants (maximum 5 wall seconds). No per-launch
estimate substitutes for the aggregate meter. Cancellation, expiry, missing or
regressing counters, excessive observation delay and unsupported cgroups cause
an immediate stop. Wall time diagnoses a late observation; it is never reported
as consumed CPU. `cgroup.kill` kills the entire subtree, including BuildKit and
startup processes. The final CPU read follows `cgroup.events: populated 0` and broker shutdown;
artifact serialization/transfer follows outside that boundary.

The stop reserve assumes a functioning Linux scheduler and kill mechanism within
those bounds. A stalled host or failure to drain is **inconclusive**, never a pass;
if an observed total exceeds 900 the result is explicitly `cpu_limit_violated`.
The settlement's `violations` array retains both `cpu_limit_violated` and
`launch_violation` when both occur; CPU takes primary state unless cleanup is
inconclusive. Terminal reconciliation preserves the known higher CPU total and
charge (including totals above 900) and validates that the violation list agrees
with the counters. It also accepts older combined records without a violation
list when their CPU and direct-entry counters support both facts.
This is not a kernel-provided cumulative CPU quota. The real CI proof must verify
these assumptions and the cgroup placement on the pinned runner image. On loss of
the supervisor or host, unknown CPU is charged at the full 900-second reservation.

## Artifacts and failure semantics

* `allocation-owner-admission-RUN-ATTEMPT`: trusted writer receipt or refusal.
* `allocation-admission-RUN-ATTEMPT`: read-only copy of the durable slot receipt,
  bounded owner bootstrap, or refusal.
* `allocation-settlement-RUN-ATTEMPT`: admission, `events.jsonl`, `settlement.json`.
* `allocation-terminal-RUN-ATTEMPT`: separate trusted `workflow_run` witness,
  including cancellation, timeout or runner loss when the original runner could
  not upload. It reads durable refs and treats downloaded JSON only as data.

Artifacts retain 90 days. A reviewer should archive them before that retention
expires. The terminal witness binds the workflow conclusion to the durable slot or
independent owner rollout authorization, and the original settlement. If evidence is missing, it reports null measurements and
full reserved charges, never an invented zero or an estimate presented as exact.
Loss of GitHub itself can also prevent a terminal witness; the durable full slot
reservation still cannot be reused. Exact physical consumption cannot be recovered
from a lost host. Existing historic consumption likewise remains unknown.

## Proof and limitations

### First measured run (operator-reported)

Warden reported PR #37 run `41189233388` at published head
`c5aa4180754c1ce7a4617b6806a9a33b7f0348bb`: admission succeeded and the required
container job ran, then failed with `state: launch_violation` in
`FreshOracleTests.test_real_fresh_process_reproduction_is_bound_and_metered`.
The reported settlement values were:

| Field | Reported value |
| --- | --- |
| Launches | 74 |
| Total CPU seconds | 237.53 |
| Cgroup CPU seconds | 232.17 |
| Supervisor CPU seconds | 5.37 |
| `cpu.max` | `100000 100000` |
| Final populated | `false` |

These reported counts are within the 100/900 caps, but the run **failed** the
launch guard. The component CPU figures are rounded and need not sum exactly to
the reported total. Raw artifact/log inspection and full identity bindings remain
pending; this is the first operator-reported measurement, not independent
compliance proof or a measurement of historic consumption. Bootstrap authorization
and its separate owner debit still require the provenance described above.

The launch inventory in `test_shipped_hotspot_call_sites_use_the_gate` covers all
Python process-spawn sites in `sundai_hotspot`, `sundai_controller`,
`sentilab_core`, and `app`, including tests, plus the legacy TAP interposer.
Only `ci_gate` starts the native solver. The TAP worker and interposer call that
gate; the warm oracle and `FreshProcessOracle` start Python workers, with the
latter forwarding the nonsecret `CI_ALLOCATION` selector through its environment
allowlist. Controller and app entry points use those oracles. The inventory also
records non-solver subprocesses (Git, JavaScript, CLI/MCP and test helpers), so new
raw spawn sites require review rather than silently gaining an exception.
The inventory separately lists eleven direct shell commands in vendored
`sundai_hotspot/examples/example{1..5}/run.sh` and `example2/newrun.sh`. CI does
not run these upstream examples; invoking them against a CI binary is refused by
the same compiled entry guard that rejects copied binaries.

Run the new proof without any thermal solver:

```sh
python3.12 -m unittest discover -s scripts/tests -p 'test_ci_*.py' -v
```

These tests execute the shipped policy, wrapper, HTTP broker, monitor, ref adapter
and terminal reconciler. A small non-thermal C program compiles the shipped entry
guard; it covers success, nonzero exit, SIGKILL, timeout, retry, copied-binary refusal
and refused admission. Concurrent reservations and injected clocks/counters test
quota and stop behavior. Existing container smoke suites stay enabled.

The implementation box has no Docker and a read-only cgroup mount. Fake proof,
non-numerical controller tests and compilation do not establish a real Docker CPU
boundary. Carter must review that boundary; warden must compare a real admitted
CI run's artifact with its logs, at the exact reviewed head. No new numerical
validation is authorized by this document.

BuildKit source used to check cgroup propagation:
https://github.com/moby/moby/blob/v27.5.1/cmd/dockerd/daemon.go
https://github.com/moby/moby/blob/v27.5.1/builder/builder-next/executor_linux.go
