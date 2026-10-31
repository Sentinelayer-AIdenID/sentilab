# Retained local proof artifacts

The five files listed in `../proof.json` are retained here at their original
SHA-256 hashes. `artifact_root` locates them from the repository root. The
203-envelope ledger is the historical 600.468-second run from source `650553d`,
using envelope v0.4 and a local in-memory signer. Its public keys are proof
fixtures, never production trust configuration. The native verifier accepts
this history; the version-pinned JavaScript v0.4 verifier is its reference.
The v0.5 JavaScript verifier rejects its older version as designed.

This is AI-off integration evidence with a provisional margin and same-solver
reproduction, not independent scientific confirmation. Raw HotSpot outputs were
not retained. The successful run recorded 30 solves, 450 charged CPU seconds and
2.652977 measured solver CPU seconds. The accumulated allocation included 38
reservations, 570 charged seconds and seven unmeasured failures.

The unsuccessful first attempt is retained unchanged in `proof-v1.json`:
188.594 seconds elapsed, six reservations and no board. Its `cpu_actual_s: 90`
was a conservative charge from the earlier instrumentation, not measured CPU.
`thermal-gate-spend.json` records the prior monitor refusal before synthetic
invocation 1801, after 1800 admitted calls and 23.077453 CPU seconds. The owner
later clarified that synthetic gate calls do not consume the HotSpot solve cap;
the unchanged thermal gate subsequently passed. Neither failed attempt is
erased or recast as a successful run. `mutation-checks.json` contains author
checks; retention does not turn them into independent review.

Total historical development CPU and synthetic call counts were not completely
instrumented. No certified task-wide total or new ten-minute run is claimed.
