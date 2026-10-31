# SLAB-039 runner validation

The accepted v3 preregistration is unchanged. This is the Ascend910-only assignment
from claude-warden at 2026-10-31 06:23Z; micro150 awaits its own mesh error.

Implementation: `ce706d8d92b8b25fded7d6f0c1f1a5dbb1d30e5d`.
Inherited headroom base: `cc4ee56` (six patch commits applied with `git am --keep-cr`).
Micro150 work ends at `d93daad96282f19bc3307074f9b06ffbbe84aed4`; the headroom
carry range starts after that commit. The operator reports micro150 as PR #9.

Checks run in this box:

- `.venv/bin/python -m unittest -q sundai_controller.test_headroom`: 54 passed.
  After refining the fake worker so child CPU becomes visible only on `aclose`,
  all 13 `BudgetRegressionTests` passed again. These tests use fake oracles only.
- `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller test_experiment test_safety_property test_tfl08_leaderboard)`:
  65 passed, including 1,000 generated safety cases. The first attempt from the
  repository root failed on legacy bare imports; the documented directory
  invocation above passed. No source changes were made to those suites.
- `.venv/bin/python -m compileall -q sundai_controller/headroom.py sundai_controller/test_headroom.py`: passed.
- `make -C sundai_hotspot -j4 SUPERLU=1`: passed.
- `git diff --check`: passed before the implementation commit.

All 13 new budget regressions were copied to a disposable worktree at the
inherited `cc4ee56` revision. All failed by assertion (no errors), with both
oracle import paths patched to the same fake. Examples: 44 observed calls versus
36 expected (32 cheap plus two two-call restarts); 18 calls versus one under the
CPU cap; missing fixture argument; greedy best 100 versus 99.999. A separate
mutation changing strict acceptance to `<=` failed the greedy parent-sequence
assertion. No real HotSpot call was made by either negative proof.

The allocation ledger is reserved and fsynced before every call, including
initialization, shared designs, reproduction, and any oracle failure. It is
locked across the entire run. An outstanding reservation after a crash requires
reconciliation; the runner does not erase it or reset spend. Both fixture and
total CPU/call limits apply. A pending CPU limit cannot be hidden in warm workers:
each worker is reaped after its evaluation, so the next `getrusage(SELF) +
getrusage(CHILDREN)` check includes its descendants and startup costs. This
increases per-evaluation overhead; it is included in the reported cost, not
subtracted from the allocation. A single already-admitted evaluation can cross
the CPU cap; no subsequent evaluation is admitted.

The real experiment command (one invocation, no separate warm-up):

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m sundai_controller.headroom \
  --fixture ascend910 --mesh-error 0.16 \
  --prereg docs/sentilab/evidence/SLAB-039/PREREG.json \
  --out docs/sentilab/evidence/SLAB-039 \
  --budget docs/sentilab/evidence/SLAB-039/SPEND.json
```

`RESULT.json` binds the executed runner and preregistration bytes by SHA256,
records per-lane best designs and solver/problem identities, and records each
fresh reproduction call. `SPEND.json` is the shared durable allocation ledger;
future fixture runs must use that same ledger. Do not repeat the command with a
new ledger to evade cumulative caps.

This is worker proof, not independent review or a merge claim. Docker is absent;
the full container smoke suite and historical thermal regressions were not run
under this headroom-only allocation. Their previously recorded allocation hold
was not interpreted as permission for extra thermal runs. There is no Node
package manifest, so npm/typecheck/audit commands are not repository gates.

## Observed Ascend910 result

The sole invocation exited 0 at 2026-10-31 06:55:09Z with protocol verdict
**INCONCLUSIVE**. It admitted 2,650 calls: 768 reducer calls, then long-SA
restart counts 1,000 / 882 / 0 / 0. The fixture CPU cap stopped the second
restart and prevented calls in the final two. CPU spend was 1,440.294565 seconds
(24.004909 minutes); the final admitted call crossed the cap by approximately
0.295 seconds. No further oracle call was admitted. Diagnostics did not run.

The strongest reducer median was 117.685 C (greedy); best observed was 116.090 C;
the numerical gap was 1.595 C against the 0.800 C threshold. The numerical gap
does not authorize protocol PASS because the declared reference is incomplete.
No micro150 run or repeat Ascend910 invocation was made.

A read-only artifact verification recomputed the preregistration and runner
SHA256 values, all available best-design hashes, reducer medians, best and gap,
and equality of result call counts with the durable ledger. It verified all
24 reducer lanes used 28 search plus four reproduction calls, with all 96
reproduction temperatures exactly matching their frozen winners. All assertions
passed; no solver call was used for this verification.
