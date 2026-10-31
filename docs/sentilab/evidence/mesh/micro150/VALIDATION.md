# Micro150 mesh validation

The measured error is **e = 0.79 C**, with **e16 = 4.28 C**. At the predeclared
0.01 C reference-gap tolerance, all 276 layout pairs are eligible. Grid 32 has
one inversion and no coarse ties (275/276 agreement); grid 16 has nine inversions
and no coarse ties (267/276). The largest misordered J64 gaps are 0.24 C and
4.66 C, respectively. No reference pairs are excluded as ties at this tolerance.

The grid-32 inversion is spread-01 versus random-01: their J32 values are
170.23 and 170.31 C, while J64 is 170.89 and 170.65 C. Grid 32 therefore does
not preserve every observed rank. The empirical two-layout uncertainty margin
is greater than 2e = 1.58 C; 16 needs its own 2e16 = 8.56 C. These are bounds
derived from this fixed sample against grid 64, not continuum error guarantees
or measured gaps between benchmark methods. The 2e checks pass on 266/276 pairs
at grid 32 and 201/276 at grid 16; their same-sample mathematical guarantee is
explained in REPORT.md. Use 16 only with its measured screening uncertainty.

## Freeze and source provenance

Warden authorized this study after SLAB-002b merged, with published main
`c6d5b0caa0c33402eaa35012306a098701808f22`. The box contains snapshot base
`eb7729b6a004ab1cf44e51a354ed6bfcea7ffc5d`, labeled source `126507d4`, rather
than that original Git object. Applying `/workspace/main-c6d5b0c.patch` with
`git am --keep-cr` to the snapshot produced local integrated base
`f6ec4a0ed8a946a1a85cc4810697bc0b53778d2e`; these local commit IDs are not
published main IDs. The source patch SHA-256 is in VALIDATION.json.

The factory change and new layouts were committed **before any solve** at
`cd3df8d88d7ba8dda03bff376b6d10ae944a16e5`. Layout SHA-256:
`0a7819d5d062f358c53d27a3fdb294914208f37115cfafb733e13c79bd6ddd6b`.
Seed 1 selects 8 clustered, 8 spread and 8 random legal layouts from a
384-layout geometry-only pool. The 0.01 C tolerance was frozen in the same file.
The public PRNG seed is reproducibility metadata. No private signing seed is used.

`RESULT.execution_commit` records the requested evaluator source revision via
BUILD_SHA. The local mesh harness and freeze commit are recorded separately above
and in VALIDATION.json. Each result binds the actual binary, configuration and
generator hashes. All historical Ascend910 evidence files remain byte-identical
to the integrated base; no Ascend910 evidence was regenerated.

## Resource reservation and remainder

Warden's reservation is 250 solver executions and 8 CPU-minutes total, including
validation. No additional warm-up solves were performed for the study.

| Work | HotSpot executions | Measured CPU-minutes |
| --- | ---: | ---: |
| Micro150 study | 72 | 2.16324845 |
| Full local smoke script | 72 | 2.08449465 |
| New measured total | 144 | 4.24774310 |
| Historical mesh lower bound | at least 102 | unknown |
| Overall lower bound | at least 246 | at least 4.24774310 |

The **remaining solve allowance is at most 4**, and the **remaining CPU allowance
is at most 3.75225690 minutes**. Neither is certified available: earlier gate
counts and CPU were not fully recorded, and setup/preliminary non-solver checks
were not CPU-measured. Unknown usage is not zero. No further solves were run
after these gates. Additional reproduction needs reconciled accounting or a new
allowance from Warden.

Study CPU uses POSIX SELF + CHILDREN deltas after worker shutdown. Smoke CPU
uses the outer wrapper's CHILDREN delta after the traced smoke process exits,
including the tracer, tests, solver children and synthetic plate checks. The
small outer wrapper SELF cost is excluded and disclosed. Study wall time was
138.284318 s; smoke wall time was 133.840088 s. The processes partly overlapped,
so these are not deployed-host performance measurements.

The smoke trace counted 62 real binary executions in its scratch probe and 10
in the checkout (8 real mesh regression calls, 2 fixture integration calls).
Two fake solver script executions were excluded. VALIDATION.json retains each
real exec PID, path, successful execve outcome and termination, plus the source
trace/log hashes. A timeout test's real solver launch still consumes an execution.
Local diagnostic originals were `/tmp/micro150-gates/execve.log` and
`/tmp/micro150-gates/container-smoke.log`; the normalized execution records are
committed, not an independent attestation.

## Commands and outcomes

From the repository root, all commands below exited 0:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-service.txt
.venv/bin/python -m pip check
make -C sundai_hotspot -j4 SUPERLU=1
.venv/bin/python -m compileall -q sundai_controller/mesh_study.py sundai_controller/test_mesh_study.py
.venv/bin/python -m sundai_controller.mesh_study --fixture micro150 --seed 1 --n 24 --freeze-only
# Commit cd3df8d before the next command.
BUILD_SHA=c6d5b0caa0c33402eaa35012306a098701808f22 .venv/bin/python -m sundai_controller.mesh_study --fixture micro150 --seed 1 --n 24
.venv/bin/python -m sundai_controller.mesh_study --check docs/sentilab/evidence/mesh/micro150/RESULT.json
.venv/bin/python -m sundai_controller.mesh_study --check docs/sentilab/evidence/mesh/ascend910/RESULT.json
PATH=/workspace/sentilab/.venv/bin:$PATH OPENBLAS_CORETYPE=Haswell strace -f -e trace=execve -s 256 -o /tmp/micro150-gates/execve.log bash scripts/container_smoke.sh
PATH=/workspace/sentilab/.venv/bin:$PATH node --test web/test/*.test.mjs
(cd contracts && sha256sum -c HASHES.txt)
node contracts/contract-0.2/run-vectors.mjs
node contracts/view-envelope/run-view-vectors.mjs
node contracts/view-envelope-v0.5/run-view-vectors.mjs
node web/test/make-sentilab-demo.mjs --check
git diff --check
```

For local execution of the unmodified smoke script, `/app` was a symlink to
this checkout. Its demo output overwrote two tracked demonstration JSON files;
those generated changes were restored, and none is included in this patch.
The script creates its own in-memory/environment test signer; no signing
material was persisted. The trace command was launched with subprocess.run in
a dedicated Python process, with time.monotonic and resource.getrusage(CHILDREN)
sampled after completion; its exact measured values are in VALIDATION.json.

The smoke script passed **133 Python tests**: controller 47, property 2,
experiment 8, leaderboard 8, oracle 14, thermal 2, service 6, mesh 25, trust 12,
and micro150 9. It also passed the deterministic demo assertions, both four-lane
smokes and all 8 HotSpot probe assertions. Browser tests: **103/103**. Contracts:
**74**, **113**, and **193** checks; all **16** reviewed file hashes match.
The generated view demo matches all **44** envelopes.

The dedicated pure mesh command (Accounting, Statistics, Layout, Identity and
Receipt test classes) passed **24 tests** before evaluation. The four layout
tests passed separately. In a disposable worktree at integrated base f6ec4a0,
the added `test_micro150_freeze_uses_its_own_legal_seeded_catalog` fails with
`ValueError: micro150 requires SLAB-002b wiring`; it passes with the change.
It checks repeatability, changed-seed layouts, 8/8/8 coverage, legality,
eight-chiplet/680 W fixture identity and each requested grid without solving.
The obsolete negative test case for the now-supported fixture was replaced by
this positive coverage; invalid fixture/path and size checks remain.

A separate Decimal-based arithmetic check, without calling the harness's
statistics functions, reproduces e, e16, inversion/tie counts and largest gaps
from the retained J values at their 0.01 C output precision. Its computed
inversion pairs are in VALIDATION.json. This is a self-check, not independent
thermal reproduction. The shipped checker validates all 72 journal receipts.

Docker is unavailable locally. The smoke script ran directly, **not in a built
image**. Docker image build, HTTP health/origin-lock and full-history gitleaks
CI remain for the operator. No npm manifest/typecheck/lint/build/audit command
exists for this Python/HotSpot project; no artificial manifest was added.
Local passing checks are not an all-CI-green or merge claim.

Raw solver inputs/outputs still await the oracle archival seam. Parsed receipts,
input hashes and heatmaps are retained, but **D02 remains incomplete**.
