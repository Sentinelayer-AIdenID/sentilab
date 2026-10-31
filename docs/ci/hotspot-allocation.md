# CI allocation 56314

This controller enforces a **prospective** allocation: 100 reserved HotSpot launches
and 900 CPU seconds per workflow run, with at most 200 admitted runs before
2026-11-01 18:00:00 UTC. It never charges the experiment allowance. Historic use is
unknown; a visible Actions run count is neither a quota nor a measurement.

## Admission and rollout

The `allocation-proof` job runs fake tests first. `admission` then executes only
trusted base-branch code, with a job-scoped `contents: write` permission. It reserves
one immutable Git ref before the unprivileged container job may run its workload
(except for the base-controller rollout path below).
PR code never runs in the admission job; checkout does not persist credentials.
Normal durable admission for fork PRs without a writable token fails closed. The
inline rollout branch needs no write API; its separate owner authorization below
applies regardless of token write access. No `pull_request_target` execution of PR
code is introduced.

`contents: write` is necessary for the Git database API's commit creation and
atomic create-if-absent slot refs; `contents: read` cannot reserve a durable slot.
Only admission receives this permission. Its sole checkout is the PR **base SHA**
(the pushed SHA on `main`), checked against `HEAD` before execution. The module is
loaded only from that tree; no PR checkout, PR artifact, dependency install, or
PR-head script runs with the write token. Head/merge SHAs enter the receipt only
as data, through environment variables. The container job has read permissions.

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

Before an authorized queued run reaches admission, the owner adds an entry with
`base_sha` and the complete `identity` (repository, run_id, attempt `"1"`, job
`"container"`, matrix `{}`, head_sha and build_sha). Use owner queue/approval
controls to hold a run while assigning its known run ID. Every listed identity
reserves a separate 100 launches and 900 CPU seconds, including lost/failed runs;
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
the run/attempt and full reservation. Archive authorization revisions and retain
the allowlist until all terminal witnesses have been produced. The trusted
default-branch `workflow_run` job receives the owner variable independently of
PR artifacts. It reconciles matching bootstrap identities before consulting the
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
`cpu.max = 100000 100000` (one CPU). Its `host` leaf contains the job shell and a
**dedicated** Docker daemon. The daemon explicitly uses `cgroupfs` and the allocation
parent for all build and runtime containers. Docker's integrated BuildKit passes
this parent to its runc executor. The existing runner Docker socket is never used.
Dependencies, compilation, smoke tests, startup, health/origin-lock checks, daemon
work and exited descendants are included by the parent's cumulative `cpu.stat`.
Build cache is disabled, so a cached numerical suite cannot masquerade as a fresh
execution. Required smoke suites and their assertions are unchanged.

The out-of-group supervisor's measured `getrusage(SELF)` CPU is added, including
broker threads. This is deliberately broader than solver CPU. Process-tree CPU
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
This is not a kernel-provided cumulative CPU quota. The real CI proof must verify
these assumptions and the cgroup placement on the pinned runner image. On loss of
the supervisor or host, unknown CPU is charged at the full 900-second reservation.

## Artifacts and failure semantics

* `allocation-admission-RUN-ATTEMPT`: durable slot receipt or refusal.
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
