# Prospective resource decision (pending)

No real HotSpot or micro150 evaluations were run for this change. The supplied
`SUPERVISOR-POLICY.json` is pending and refuses execution. A named operator must
approve its limits and explicitly accept the unbounded scheduler/cleanup risk
before any real run. This is a proposed best-effort resource policy, **not a hard
cumulative CPU cap** and not authorization to run. Exact-head scientific review
and the existing execution hold still apply independently.

The prior Ascend charge remains **1440.294565 CPU-s**. Micro150 can use at most
**2879.705435 CPU-s**, further reduced by existing micro150 charges, tighter fixture,
headroom or aggregate allocations. Non-headroom CPU remains charged at at least
720 CPU-s; unknown historical costs remain unknown. No ledger is reset.

## Supervisor and assumptions

The supported entry point is a fresh, single-threaded interpreter:

```
python -m sundai_controller.headroom_supervisor \
  --prereg docs/sentilab/evidence/SLAB-039/PREREG-v4.json \
  --budget docs/sentilab/evidence/SLAB-039/SPEND.json \
  --out /path/to/micro150-v4 \
  --policy /path/to/approved-resource-decision.json
```

One synchronous parent owns the ledger lock, forks a worker in its own process
group, polls independently of asyncio, and adopts/reaps orphaned descendants.
It covers worker imports, preregistration, setup, candidate generation between
calls, solver work, cleanup, RESULT/REPORT serialization and final persistence.
Workers create additional sessions, so the parent kills both the worker group
and individually identified descendants, repeating through adoption and reap.
No child or successful result escapes accounting on the normal completion path.
A metering/cleanup failure leaves the durable reservation unresolved.

Parent and worker inherit a CPU mask containing at most Q CPUs (Q = 1, 2 or 8).
This assumes the trusted code does not widen affinity or migrate outside the
supervised tree. It is not a sandbox against hostile code. `/proc` cumulative
CPU includes all threads and waited children; final `getrusage` after kernel
reap confirmation retains precise child charges. A conservative wall envelope
also limits admission independently of transient `/proc` undercounting.

Proposed parameters are sampling interval S = .01 wall-s, additional observation
delay D = .25, kill K = .25, reap R = .25, burst B = .02 CPU-s and terminal
settlement reserve T = .25 CPU-s. Reserve:

```
H = B + Q*(S + D + K + R) + T
```

H is 1.03 CPU-s at Q=1, 1.79 at Q=2, and 6.35 at Q=8. Before starting work, the
parent subtracts its already consumed lifetime CPU and H from the allowance.
The worker's maximum wall duration is `(allowance - parent CPU - H)/Q`, further
limited by the remaining solving wall allowance and 12:00Z deadline. The parent
also stops when observed cumulative CPU plus H reaches the allowance. Startup
after this sample is inside that same wall envelope. No worker starts if the
reserved duration is nonpositive. With only .1 CPU-s left, no generation or solve
is admitted; the supervisor's own refused-attempt overhead is still charged.

**Conditional guarantee:** if the rate/burst envelope and D/K/R/T bounds hold,
the stop reserve prevents exceeding the CPU allowance. For actual delays d/k/r
and terminal CPU t, the conditional worst-case excess is
`max(0, B + Q*(S+d+k+r) + t - H)`. The terminal work after the final sample is
reserved, not measured. It includes ledger/settlement serialization, fsync and
interpreter exit. No finite T is guaranteed here.

**Unconditional guarantee:** none. Ordinary Linux can deschedule this parent,
delay `/proc` or filesystem access, or delay kill/reap arbitrarily. Therefore the
unconditional worst-case CPU overshoot is **unbounded**, recorded as null with
`hard_cap=false`. A larger H, affinity or cpu.max alone does not fix this. Delayed
parent observations and cleanup that exceed the assumed bounds invalidate resource
acceptance. No numeric finite unconditional bound is claimed. Approval must
explicitly accept that risk, or the experiment must remain stopped until a host
with independently justified enforcement guarantees is supplied.

The solver retains its separate 45-second malfunction timeout and frozen p95
admission checks. The supervised production path does not start the former
per-call asyncio CPU watcher or per-call affinity/subreaper scope. Standalone
synthetic tests retain that cooperative helper to preserve its regression coverage;
it is not a supported enforcement route for real v4 evaluations. Direct real
`run_headroom` calls without the parent context refuse before oracle construction.

## Authoritative settlement

Before launch, SPEND contains an `outer_active` reservation for the entire
remaining allowance. A crash leaves it pending, so a second run cannot reset or
reuse the allowance. The inherited lock remains held by the parent through
terminal settlement. After every descendant is confirmed reaped, the parent
replaces partial worker CPU with the maximum of its prior recorded charge and
the original ledger charge plus whole-parent-lifetime CPU plus T. This includes
parent imports and supervision, worker setup/output and kill-to-reap CPU.

Each worker RESULT is explicitly provisional and carries the reservation ID.
Resource acceptance requires its matching durable `lifetime_settlements` entry
in SPEND (also exported as `SETTLEMENT-<id>.json`) with `result_accepted=true`.
That field concerns resource acceptance under the approved best-effort policy;
the worker's scientific verdict must independently satisfy the frozen criterion.
Consumers must not release from a provisional RESULT alone. Terminal receipts
bind the preregistration, supervisor source and operational policy hashes, measured
CPU, reserved tail, actual observation/kill-to-reap latency and overshoot. A stopped
or late run cannot obtain resource acceptance. An outstanding per-call reservation
on a killed worker remains unresolved for manual reconciliation.

## Numeric representation

The existing rule is now explicitly frozen as IEEE-754 binary64 arithmetic:
subtract the parsed binary64 C and best, then compare inclusively with binary64
`5 * 0.79`, without rounding or epsilon. Thus `100.1 - 96.15` is
`3.9499999999999886` and is below the threshold, whereas `3.95 - 0` equals the
threshold. This clarifies the existing semantics before any micro150 outcome;
it does not reinterpret the unchanged historical Ascend evidence.
