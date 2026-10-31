# Prospective micro150 v4 implementation and review handoff

Historical implementation receipt. The admission/overshoot policy below is superseded
by the prospective review corrections in `VALIDATION-v4-caps.md`; no v4 thermal run
was made under either revision at the time of that handoff.

This additive preregistration implements claude-warden's 2026-10-31 07:11Z
assignment. It is **not execution clearance**. No micro150 headroom solve, or
other real HotSpot solve, was run for this revision. The exact committed source
requires gpt-astra-carter review and explicit claude-warden release before use.

Local source/base is `6c27a913a7e397e45707ab590f0e482b79d3dcf9` (the previous
headroom carry). The operator reports that carry as PR #25 at `fa7ed8f`;
publication and independent review are operator-owned. This export contains only
the prospective v4 change after the local base. Prior micro150 wiring remains
in the separate earlier carry ending at `d93daad96282f19bc3307074f9b06ffbbe84aed4`.

## Rule and scope

`PREREG-v4.json` is a separate micro150-only preregistration. The existing
`PREREG.json`, `RESULT.json`, `REPORT.md`, and `VALIDATION.md` remain
byte-identical to the base. Ascend910 remains **INCONCLUSIVE under v3**.

The runner freezes each cheap search winner and its score before four fresh
reproductions. Every reproduction must match candidate, solver and problem
identity, converge, and agree within **absolute 1e-6 C, relative tolerance zero**.
Legal geometry (including the TAP catalog, grid and halos) is checked before each
admission. Exactly 24 lanes, 28 search calls per lane including initialization,
and all 96 agreeing reproductions establish C. `CHEAP_BASELINE.json` is persisted
before any reference call and its SHA256 is recorded in the final result.

Each long-SA restart reserves one fresh reproduction inside its 1,000-call cap:
999 search including initialization, then one verification of the frozen winner.
An interrupted restart without that verification supplies no eligible witness.
Previously verified cheap/reference winners remain eligible; adding witnesses
cannot increase their minimum score. This trades one search call per restart for
verification and does not verify every interim improvement.

PASS requires completed frozen C and a verified eligible witness with gap >= 3.95 C.
FAIL requires completed C and all four complete, verified reference restarts.
Otherwise the result is INCONCLUSIVE. Reproduction temperatures never replace
the frozen scores. The fixed e=0.79 C from PR #18 is a **24-layout sample
discrepancy**, not a universal error bound. This certifies only the preregistered
observed-headroom criterion; `paid_scientific_model_authorized` is always false.

## Admission and retained accounting

Before every oracle call, including initialization and witness reproduction:

- micro150: at most 4,768 calls and 48 CPU minutes;
- cumulative headroom: 9,700 calls and 72 CPU minutes;
- aggregate allocation: 10,000 calls and 84 CPU minutes;
- cumulative headroom solving wall: 90 minutes; deadline 2026-10-31 12:00Z.

CPU uses SELF+CHILDREN, with workers reaped after every call. Call reservations
are fsynced before execution. A call admitted strictly before all limits may
finish; actual CPU/wall/deadline overshoot is recorded and no later call is
admitted. The call counts themselves cannot overshoot. Raising the input-file
limits cannot raise the code's hard caps. Outstanding crash reservations still
fail closed pending reconciliation.

`SPEND.json` retains the actual 2,650 Ascend910 calls and
1,440.2945650000001 CPU seconds without rounding. The 0.294565-second v3 overshoot
reduces remaining headroom CPU, so the 72-minute total can bind before micro150
reaches its own 48-minute ceiling. Its retained solving interval is 1,525.852038
seconds, computed from the original result's start/finish timestamps. A reset or
rounded-down prior ledger is refused.

The full non-headroom allocation is conservatively reserved: 300 calls and
720 CPU seconds (mesh 8 minutes plus timing 4). Aggregate accounting adds the
larger of this reservation or the reconciled non-headroom charges. Retained
known charges include 60 prior timing calls and two development test calls from
`../micro150/SPEND.md`. Complete PR #18 mesh spend receipts are not in this
checkout. Unknown historical CPU and the unresolved CI allocation are explicitly
retained separately; their absence is not treated as measured zero. This is not
an all-time historical-compliance claim or a reconciliation of unknown spend.

## Checks actually run

- `.venv/bin/python -m unittest -q sundai_controller.test_headroom sundai_controller.test_headroom_v4`:
  **79 passed** (54 legacy plus 25 new). A subsequent exact-threshold boundary
  test passed separately: `... sundai_controller.test_headroom_v4.V4Tests.test_exact_3_95_threshold_passes_with_verified_witness`.
  **80 headroom tests total.** The two tightened aggregate/geometry tests were
  also rerun and passed after their assertion refinements. The full-schedule test
  was rerun with explicit fresh-call design-hash checks.
- `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller test_experiment test_safety_property test_tfl08_leaderboard)`:
  **65 passed**, including 1,000 generated safety cases.
- `.venv/bin/python -m compileall -q sundai_controller/headroom.py sundai_controller/test_headroom_v4.py`:
  passed. `git diff --check`: passed.
- `make -C sundai_hotspot -j4 SUPERLU=1`: passed; build only, no solve.
- `(cd contracts && sha256sum -c HASHES.txt)`: **11 files passed**.
- `(cd contracts/contract-0.2 && node run-vectors.mjs)`: **74 passed**.
- `(cd contracts/view-envelope && node run-view-vectors.mjs)`: **113 passed**.
- `node --test web/test/sentilab-parity.test.mjs`: **39 passed**.
- `node web/test/make-sentilab-demo.mjs --check`: passed, **44 envelopes current**.

All numerical runner checks use fake oracles and clocks. They retain real ledger
writes and pre-call readbacks; the v4 fake runs omit filesystem fsync barriers
for speed. Legacy budget regressions exercise the unpatched persistence path.
One test constructs the real micro150 catalog and validates the initial layout
and 680 W sum without invoking its evaluator.

Negative proof uses a separate disposable worktree at the base, never swaps the
active checkout. All 26 added v4 test methods fail on the base (unsupported v4 schema,
missing layout constant, wrong CPU limits and assertion mismatches). In addition,
14 isolated source mutations are detected by targeted fake-oracle tests:
unchecking reproduction tolerance; replacing frozen scores; allowing incomplete
cheap eligibility; accepting an unverified reference; allowing partial-reference
FAIL; weakening fixture CPU, headroom CPU, fixture calls, headroom calls,
aggregate calls, wall, deadline or aggregate CPU bounds; and changing >= to >
at the exact 3.95 C threshold. Each mutation failed by assertion. These checks
establish sensitivity to individual rules, beyond rejection of the old schema.

The first v4 test pass exposed a geometry-validation ordering issue; the initial
layout is now validated before shared-sample generation. No existing test was
deleted, skipped, renamed or weakened.

Full container smoke and historical thermal regression gates remain **not run**
under the existing allocation hold; Docker is absent in this box. No npm manifest
exists, so synthetic npm/typecheck/audit commands are not repository gates.
Worker proof is not independent review, export verification, merge, or execution
clearance. No paid scientific model release is claimed.

## Additional review #56223: common domain and retained attempts

Carter's review of the earlier Ascend910 source identified a domain mismatch:
the retained winners were not constrained to the initial wire proxy. This
revision makes the domain explicit prospectively; it does not refilter or
reinterpret the Ascend910 history. A wrapper checks the connectivity-weighted
Manhattan center-distance proxy against the initial micro150 value, with zero
tolerance, before shared sampling, proposals and every oracle admission.
The ceiling never follows a new winner. `DOMAIN.json` retains the initial design,
its hash, wire ceiling and complete fixture problem description.

Every v4 invocation creates a unique `attempt-<id>` child of the requested output
root. `SPEND.json` links cumulative attempts and preserves their starting/ending
call counts and status. Each attempt retains the exact preregistration and runner
bytes read at its start; result hashes use those bytes, not a later reread of the
live files. Signed controller events are appended durably during each lane,
including proposals and receipts, with their public verification identity. No
private signing identity is serialized. Complete per-call designs and returned
thermal records (or errors) are retained. Raw generated inputs, steady-state
output files, stdout/stderr and process exit records are retained under that
call's directory. A failed solver keeps its generated files and error output;
default oracle use retains its existing temporary-directory cleanup behavior.

Six added review regression tests fail on the preceding v4 implementation
`0a820aa`. They test the common wire domain, the fixed ceiling after a better
layout, mid-run preregistration mutation, two-invocation artifact preservation
and signature verification, directory survival on success/error, and the
oracle-to-worker retention route with a fake nonzero solver exit. All pass with
this change. The fake worker test calls no native solver.

The updated combined command passed **85 tests** (54 legacy plus 31 v4); the
subsequently added raw-failure routing test passed separately (**86 total**).
The tightened zero-wire-tolerance parser case and wire-domain test also passed
in a focused rerun. Nine selected existing worker/protocol/integrity/parser
checks passed from `sundai_hotspot`, using stubs/synthetic executables, plus the
two existing content-identity/cardinality tests passed from the repository root.
The first worker invocation from root hit legacy bare-import errors; the
correct directory invocation passed without changing those tests. Compileall
and whitespace checks pass for all four changed Python files. Other pure gates
above remain valid; no real HotSpot solves or container/thermal gate reruns were
made. Final export and exact-head review remain pending.
