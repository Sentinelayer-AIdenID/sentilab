# SLAB-049 coupling allocation

Implementation status: allocation, exact numeric evaluation, the four final outcome wordings from Aneta #57732
(source `4d7804bb-1300-44af-93bc-1885cc0e311d`, accepted by root522), and the four-file replay policy are implemented. Signing and executing the experiment
remain pending independent review and Warden's new allocation; this implementation makes no experimental claim.

Ticket 01ac77ac adds the four calls from `coupling-call-list.json` as an explicitly selected allocation. The
call list stays at SHA-256 `db32a692b749e08324c295e56250f96a9548796aae232ca63f24d2ad4ab3e577`.
The default gate-zero manifest stays at `23a1a74b9d4fd56e5fa192982d74d9eaa90f6aeaf81d718247d566f12612053b`;
it still contains only its original twelve calls. Neither allocation inherits the other's grant or consumed calls.

`python -m sundai_hotspot.coupling_allocation` prints the coupling manifest's SHA-256. `--write PATH` saves its
exact bytes; `--check PATH` refuses bytes that differ from the tree's generator. The manifest incorporates the
immutable call list, the existing reference input pins, the operator public key, the coupling binary pin and the
implementation source hashes. Changing the implementation therefore requires a new coupling allocation hash.
Loading a manifest path alone never selects coupling: `--manifest coupling` is required explicitly.

The four rows retain the call-list order: Ascend primary/replay, then CPU-DRAM primary/replay. Each reserves
58.5 CPU-s (50 solver + 8.5 overhead), for a binding cap of 234 CPU-s, concurrency one, with no retries. The
existing signed ledger and create-only tag machinery handles admission, reservation, launch and settlement.
Ledger directories already include the manifest hash. Coupling uses `/srv/gate0/runs/coupling` for its output,
CPU carry and operator log; gate zero keeps `/srv/gate0/runs`. The coupling admission deadline is independently
fixed at **2026-11-02T06:00:00Z** (root512 and Aneta57718). Entry and signed-ledger admission accept the exact
deadline and refuse later times; the signed grant may close earlier. This changes no gate-zero window or grant.

The operator must provision the coupling directory under the host `/srv/gate0/runs` bind mount before use.
The coupling CLI refuses before dispatch if that directory is absent or aliased by a symlink, if mountinfo does
not show the exact writable `/srv/gate0/runs` mount with filesystem root `/srv/gate0/runs`, or if another mount
shadows any descendant. CPU carry, its temporary file, log and `report --out` must resolve inside coupling's
verified tree without symlink aliases. Only fresh per-call children are created, without recreating parents.

`cpu-used.json` must also be provisioned for coupling grant/run with a finite, nonnegative `used_cpu_s` number.
The operator initializes it to zero only for a genuinely unused allocation; otherwise the operator reconciles
retained accounting. Missing, null/unknown or invalid carry refuses; it never implicitly resets usage to zero.
Report readback can still inspect retained evidence when carry is absent. Consumed reservations remain consumed.

This mountinfo check is specific to the known host layout: its root field is filesystem-relative, not a universal
host-source pathname. Before release Warden must retain the actual wrapper and Docker mount metadata binding
host `/srv/gate0/runs` to container `/srv/gate0/runs`, plus a harmless marker and representative output, receipt,
carry and log hash readback from the host after the container exits. An existing directory or an offline mount
fixture does not establish that operational proof. Reports go directly in the coupling directory and cannot
overwrite its carry, temporary carry, log or per-call evidence. Do not work around a refusal by making an
ephemeral directory.
Report destinations must be fresh, including when an existing name belongs to a supervisor stdout/stderr
sidecar. Before each reservation, the operator rechecks storage and refuses any occupied call directory or
sidecar path; sidecar files are then created exclusively so an existing file or symlink cannot be overwritten.

## Binary identity and provenance

The only accepted binary is the operator image's `/app/sundai_hotspot/hotspot-material-only`, SHA-256
`6ea3b7813412c13d20c92adc6449fbc0bc87c46b521d4d5eaf80b8abc7900609`. The supervisor checks it before launching
validation. Validation checks its private content-addressed copy again, before admission or launch, using the
existing material-only identity markers (including the tag required by `MaterialOnlyCouplingOracle`). Build
provenance remains mandatory, and a CI-entry-guard build remains refused. Readback requires the signed receipt's
evaluator identity to match that same pin.

The `e5923014...` hash in `ANALYSIS.md` is explicitly a build **without** `CI_ALLOCATION`, made on the author's
WSL host with GCC 15.2.0, glibc 2.43 and SuperLU 7.0.1. It is not the CI-guard hash. The operator image is a
different build environment; the Makefile also enables `-g`, which embeds the build path (see
`provenance.build_provenance`). These are build-specific hashes, not evidence of different coupling equations.
The ticket records unchanged C/Makefile inputs and identical `6ea3b781...` binaries across three operator image
builds. Those image rebuilds are operator evidence, not reproduced in this box.

## Statistic and readback

The statistic is the maximum native block-output temperature under centre mapping, including package nodes.
Chiplet block values, their centre mapping, the active-layer grid peak and argmax, and the same-index package
diagnostics are retained separately. A grid peak or chiplet-only maximum never replaces the frozen statistic.

| Reference | HS7 baseline C | HS6 baseline C | Variant threshold C |
|---|---:|---:|---:|
| Ascend 910 Fig. 6(a), Layout A | 123.42 | 75.48 | 82.671 |
| CPU-DRAM Fig. 5(a) | 232.67 | 115.93 | 133.441 |

Each successful call's signed receipt records `(T_hs7 - T_variant) / (T_hs7 - T_hs6)`, a decimal rendering and
the exact rational value, its maximizing node, and diagnostics. The comparison uses the exact rational value
against `17/20`, never a rounded temperature or fraction. The CPU-DRAM baseline is the frozen simulated gate
output **115.93**, not the paper target 115.94.

The coupling manifest freezes replay identity to `sample.steady`, `sample.grid.steady`, `stdout.txt` and
`stderr.txt`, compared byte for byte without normalization. Timestamped `receipt.json` is explicitly excluded.
Inspection of `hotspot.c`'s steady-state path found progress/summary text and the LCF warning with the frozen
relative input names (`samplelayers.lcf`, `sampleL4_ChipLayer.flp`), not wall-clock timestamps or per-run paths.
The SuperLU steady solve in `temperature_grid.c` initializes and frees statistics without printing them.
Thus both native streams are included. This is source inspection, not an additional thermal solve; any runtime
stream mismatch still makes no claim and authorizes no extra call. The signed receipts already bind all four
files. A replay whose primary is unavailable has no established replay identity. Gate zero retains its own
unchanged two-file replay policy.

`report` revalidates signed ledger entries, tags, receipts and raw output hashes through `gate_zero.verify_call`,
then recomputes the evaluation from the raw files. Stored evaluation fields are not trusted. A missing or unusable
call cannot produce PASS; a completed threshold miss or byte mismatch produces FAIL. No thermal solve is run by
the generator or report.

Alongside that mechanical verdict, each reference has its own outcome. Any missing or unusable call or any
replay mismatch takes precedence for the overall **DOESN'T COMPLETE** wording, even when another reference
misses the threshold. Otherwise both references meeting `17/20` selects **MEETS**, both missing selects
**MISSES**, and exactly one meeting selects **MIXED**. Each row names its reference and verdict before the
overall outcome. The mechanical PASS/FAIL/INCOMPLETE field is distinct from the scientific no-claim wording.
There are no retries or automatic extra calls.

The manifest freezes these wordings and the percentage mapping: in MEETS/MISSES, `[x]` is Ascend 910 and `[y]`
is CPU-DRAM. In MIXED, the first `[reference]` and `[x]` are the passing reference and its percentage; the second
`[reference]` and `[y]` are the missing reference and its percentage. This mapping reverses correctly when
CPU-DRAM passes and Ascend 910 misses.
Each signed evaluation retains `fraction_percent`, the mathematical floor of 100 times the exact rational,
without float conversion or clipping to 0–100%. The report repeats that rounding rule explicitly. Display
rounding does not affect the predicate: an exact 84.5% displays as 84% and misses `17/20`; exact 85% passes.

- **MEETS:** "With only that one link changed in 7.0, [x]% of the difference to 6.0 goes away on Ascend 910 and
  [y]% on CPU-DRAM, rounded down. Both meet the 85% we fixed. That localizes it to this term in this configured
  model. It doesn't tell us what the authors intended, or which version matches hardware."
- **MISSES:** "That one change accounts for [x]% of the difference on Ascend 910 and [y]% on CPU-DRAM, rounded
  down. Both are below the 85% we fixed. Something else also contributes."
- **MIXED:** "On [reference], that one change accounts for [x]% of the difference, rounded down, meeting the 85%
  we fixed. On [reference], it accounts for [y]%, rounded down, below the 85% we fixed, so something else also
  contributes there. It doesn't meet the bar on both references. It doesn't tell us what the authors intended,
  or which version matches hardware."
- **DOESN'T COMPLETE:** "The run didn't complete, so we make no claim from it."

## Operator review and execution

Warden first reruns the suites and the manifest generator in `sentilab-gate0:5cedde1`, mutates the binary pin and
predicate to show the tests fail, and obtains the independent science/contract review. Only then does Warden sign
a new grant and run these four calls. No grant was signed and no coupling experiment was executed by the implementer.

Review tests can import the new checkout mounted at `/src`; the operator resolves its imports from that checkout
instead of the old image's `/app`. Execution still requires the merged operator code deployed at `/app`, as the
existing supervisor specifies. Recheck the material-only binary hash in that runtime before signing.

The Dockerfile writes material-only provenance alongside default HS7 provenance. Before the grant, verify that
the deployed image retains it and that it binds the pinned binary; this source change has not built an image.
The existing provenance writer reads the binary and loader metadata and runs no thermal solve.

```sh
python -m sundai_hotspot.provenance material_only
python -m sundai_hotspot.coupling_allocation --check-binary /app/sundai_hotspot/hotspot-material-only
python -m sundai_hotspot.gate0_operator grant --manifest coupling --grant-id <new-grant-id>
python -m sundai_hotspot.gate0_operator run --manifest coupling --grant-id <new-grant-id>
python -m sundai_hotspot.gate0_operator report --manifest coupling --out /srv/gate0/runs/coupling/report.json
```

The operator supplies the usual external key, ledger-root and anchor environment. The original gate-zero
`record` command remains specific to HS6 certification; coupling adds a diagnostic report, not a gate-zero PASS.

## Prior implementation proof at 95cb2709

The surrogate executor used Python 3.12.3, GCC 13.3.0, glibc 2.39 and SuperLU 6.0.1. Test temporary files were
placed on executable tmpfs (`TMPDIR=/dev/slab049-test-tmp`) so throwaway signing fixtures never reached disk.
These commands exited zero:

- `.venv/bin/python -m unittest discover -s sundai_hotspot -p 'test_*.py'`: 235 tests, no skips, including 21
  coupling tests.
- `(cd sundai_controller && ../.venv/bin/python -m unittest -v test_controller.py test_experiment.py)`: 55 tests.
- `.venv/bin/python -m unittest discover -s sundai_thermal -p 'test_*.py'`: 2 tests.
- `make -j4 SUPERLU=1 -C sundai_hotspot` and `make SUPERLU=1 -C sundai_hotspot hotspot-material-only`.
- `PATH="$PWD/.venv/bin:$PATH" bash scripts/build_hotspot6.sh`.
- `git diff --check`.

The initial regression failed on the unmodified code with `load_manifest() got an unexpected keyword argument
'selection'`. The added test module also fails in a disposable worktree at snapshot base
`022d5753b96fc2b598ac8a1d8468d3f83dcf156d`, which has no coupling allocation module. Ten deliberate mutations
were each caught by a named regression: changed binary pin, skipped pin check, skipped identity tag, weakened
threshold, rounding before comparison, skipped replay bytes, trusted stored evaluation, skipped receipt pin,
ignored manifest selection, and shared CPU files. A separate import-shadow regression failed before replacing
the hardcoded `/app` import root and passes with the checkout-derived import root.

For the outcome/replay follow-up, all seven new tests and the extended exact-threshold test fail against
pre-fix `b54569fe3d98592de8392bb832cf14550b6a2ff5` in a disposable worktree: the 21-test coupling file reports
two failures and eleven errors (including rounding subcases). Both authentic stream-mismatch regressions
fail with `AssertionError: True is not false`. With the fix, all 21 pass. They cover verbatim outcomes, missing
or unusable calls, mixed results, exact rounding on both sides of a half-percent, and independent stdout/stderr
mismatches, using the real validation/report paths and fake engines. No thermal solve is added.

That prior tree generated coupling manifest SHA-256
`e2de4a6ab7a10602f7236bc8747ae65c5b66597fc7b65cd4c6de943fb5341f9f`.
The locally built material-only binary is `bb47ba9c0f72170d2bf5460515f1fb8a1e0ced09d9d451ec721bb655405e27a2`;
its material-only identity was checked, and `--check-binary` correctly refused it against the operator-image pin.
Docker is unavailable in this box, so the pinned-image suites/build check remain Warden's independent proof.
