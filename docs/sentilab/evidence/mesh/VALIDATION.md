# Validation of SLAB-006a

Measured in the supplied source snapshot `126507d4dbd8cf327aa158c4dd893c436f7cdf8f`,
represented locally by snapshot commit `eb7729b`. The geometry-only sample and
SHA-256 were committed in `20e72d8` before any study simulation. The study took
152.289 s for 24 layouts x 3 grids. J32/J64 maximum discrepancy is 0.16 C; J16/J64
is 0.86 C. The JSON preserves raw values and timings, with execution and analysis
commits recorded separately. Summary analysis adds only the decimal roundoff
guard; the frozen 0.01 C tolerance and measured J values are unchanged.

## Commands and observed outcomes

All commands ran in the Python 3.12 virtual environment unless noted.

| Command | Observed outcome |
| --- | --- |
| `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt` | Exit 0 |
| `sudo apt-get install -y build-essential libsuperlu-dev libblas-dev` | Exit 0 |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Exit 0 |
| `(cd sundai_controller && python -m unittest -v test_controller.py test_experiment.py test_safety_property.py test_tfl08_leaderboard.py)` | 65 tests pass |
| `(cd sundai_hotspot && python -m unittest -q test_tap_oracle.py)` | 14 tests pass |
| `python -m unittest -q sundai_controller.test_mesh_study` | 9 tests pass, including four real layouts x two grids |
| `python -m compileall -q sundai_controller/mesh_study.py sundai_controller/test_mesh_study.py` | Exit 0 |
| `git diff --check` | Exit 0 |
| `python -m sundai_controller.mesh_study --fixture ascend910 --seed 1 --n 24` | Exit 0; 72 real evaluations |
| `python -m sundai_controller.mesh_study --check docs/sentilab/evidence/mesh/ascend910/RESULT.json` | Exit 0; internally consistent |
| Same checker on a copy with the coldest J64 layout's J32 raised above the hottest layout | Exit 1; summary mismatch and 23 published-bound inversion/tie violations |
| Three-layout CLI rerun from README at 32 and 64 | Exit 0; all six J values exactly match (max absolute difference 0 C) |
| `python -m unittest discover -s sundai_thermal -p 'test_*.py'` | **2 tests, 1 failure on the supplied baseline**: root README lacks three archived metric strings |

The thermal failure reproduces with the baseline README byte-for-byte unchanged.
A scratch checkout with just those truthful historical strings restored passes
both thermal tests. At 05:09 UTC, claude-warden reported this import defect fixed
on main `29b0c3b`, with green CI, and instructed carry onto that main without
editing README.md or .gitleaksignore. This branch follows that instruction; it
does **not** claim that the unchanged snapshot thermal gate passes. The operator
must verify the integrated gates on current main. This repository has no npm
manifest; the ticket's Python and HotSpot gates apply, not fabricated npm scripts.

## Tests can detect defects

Copying the new tests into a disposable checkout of local `base` fails at import:
`ImportError: cannot import name 'mesh_study' from 'sundai_controller'`.
The following targeted changes to the shipped module in a separate disposable
worktree each failed their corresponding test; the working checkout was never
stashed or reverted:

| Test | Defect caught |
| --- | --- |
| `test_mesh_error_uses_maximum_absolute_difference` | max replaced by min |
| `test_rank_catches_inversion_and_coarse_tie` | violation count forced to zero |
| `test_tolerance_boundary_and_no_eligible_pairs` | inclusive boundary made strict |
| `test_invalid_numeric_inputs_fail_closed` | numeric validation removed |
| `test_result_checker_detects_planted_inversion` | checker forced to report success |
| `test_seeded_legal_balanced_unique_layouts` | caller's seed ignored |
| `test_freeze_is_immutable_and_hash_checked` | SHA-256 check bypassed |
| `test_fixture_and_size_validation` | too-small sample allowed |
| `test_four_real_layouts_at_16_and_32` | real measured J replaced by zero |

The seed mutation initially survived because a test compared seed metadata; the
assertion was corrected to compare actual layouts and then caught that defect.
An additional decimal-boundary regression failed before the roundoff guard with
`AssertionError: 3 != 2` eligible pairs for reference values 117.17, 117.18,
117.20 C at tolerance 0.01 C; the final five statistics tests and all nine mesh
tests pass. The guard is 1e-12 C, far below HotSpot's 0.01 C printed resolution.

The three-layout rerun above is self-verification, not claude-warden's independent
proof. Independent review and micro150 evaluation remain follow-up work. Revert
this ticket's commits to remove the harness/evidence; no runtime oracle, shared
fixture, dependency, workflow or production service code was changed.

## Budget instruction received after measurement

At 05:12 UTC, claude-warden specified a shared ceiling of 150 solver executions
and 6 CPU-minutes across both fixtures, including HotSpot child CPU and warm-up.
The original runner measured elapsed time only. RESULT.json records historical
CPU-seconds/minutes as null and shared-budget compliance as unverified. The
152.289 elapsed seconds are not a CPU estimate. At 05:15 UTC the reviewer
accepted explicit unknown historical CPU and requested accounting for future runs.

Retained results and validation logs establish a lower bound of 102 solver
executions: 72 study, 6 three-layout rerun, 16 from two successful full mesh
suites, and 8 from the real-run mutation. This excludes other oracle/gate
executions and is not a certified total. Another 72-run fixture would exceed
150 even using that lower bound. Further solver runs require reconciled
accounting or a revised remaining allowance; micro150 also awaits wiring.

Future successful runs record `run_accounting` with execution count and POSIX
process-plus-reaped-child CPU delta after worker shutdown. No warm-up runs
occur in the harness. Failed runs require external accounting; this does not
enforce a shared limit across independent processes.

The accounting regression launches a real child waiting for a CPU-consuming
grandchild, proving descendant CPU and seconds-to-minutes conversion without
HotSpot. Accounting, statistics and layout classes pass: 9 tests via
`python -m unittest -q sundai_controller.test_mesh_study.MeshAccountingTests
sundai_controller.test_mesh_study.MeshStatisticsTests
sundai_controller.test_mesh_study.MeshLayoutTests`. The new test fails on
`7c22f9d` with missing `cpu_usage`; removing child CPU from the implementation
also fails it. The real-run test was not repeated after accounting changed,
to conserve the unresolved allowance.

## Requested ranking resolution

Reanalysis of the unchanged measurements yields a largest reference-grid gap
reversed or left tied of 0.11 C for grid 32 and 0.39 C for grid 16. In the grid-32
case, spread-07 and random-02 both return 118.25 C at 32, but their J64 values
are 118.41 C and 118.30 C. This is a lost distinction of 0.11 C on the reference
grid, not a guarantee about differences measured at 32 or unseen layouts.

The new resolution test failed before the fix with a missing summary key;
removing coarse ties from the shipped rank function in a disposable checkout
fails it with `AssertionError: 2 != 4`. Final accounting/statistics/layout tests:
10 pass, no HotSpot runs. Resolution analysis has separate source-hash/base
provenance in RESULT.json; original execution and roundoff-analysis commits and
all measured temperatures remain unchanged.

Protocol correction #56072 is applied: zero eligible pairs now has a null pass
verdict (inconclusive), and strict inversions and coarse ties are reported
separately. At fixed 0.01 C, grid 32 has 3 inversions and 2 coarse ties; grid 16
has 15 inversions and 1 coarse tie. The strengthened tests failed before
these changes (`True is not None` and missing inversion-count key), then all
10 non-solver tests passed. All 24 frozen layouts are retained; no observed
subset is described as a preregistered independent check set. Ascend910 is
interim evidence and the combined fixture study remains inconclusive.
