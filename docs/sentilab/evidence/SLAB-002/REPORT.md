# SLAB-002 Evidence Report: Pin the Imported Source and Rerun Every Existing Claim

**Ticket:** 5ee83372 · **Date:** 2026-10-31 · **Agent:** ds-slab002-source (lifeId 6b23dc5cc8ed)

The toolchain, timings and claim tables below preserve the source-box **05:10Z**
observations. They do not measure the current script. The inherited **06:01Z**
observation remains separately labeled in `results.json`; its raw logs were not
retained. A fresh retained run is linked at the end of this report.

## Toolchain (05:10Z source-box observation)

| Component | Version |
|---|---|
| GCC | 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1) |
| Python | 3.12.3 |
| SuperLU | 6.0.1+dfsg1-1build1 (libsuperlu-dev) |
| BLAS | 3.12.0-3build1.1 (libblas-dev) |
| HotSpot binary sha256 | `e4358b46794ebc00f07102d13b3ca687507834a1784eba135d26d1d493d334b4` |
| hotfloorplan binary sha256 | `314b454c0e235809bf9295ee3202c65a100cca2e69ffe8045ad1eed037519653` |
| Host | Linux respawn-6b23dc5cc8ed 7.0.0-1017-azure x86_64, 16 cores, 62 GB RAM |

## PROVENANCE.json Verification

- Original 05:10Z result: **494/494 checkout-file SHA-256 checks**, 0 mismatches,
  0 missing. The ~0.5 s historical timing does not measure the later blob checker.
- The current script pins repository import commit
  `126507d4dbd8cf327aa158c4dd893c436f7cdf8f` and verifies each path → git blob → SHA-256.
  The retained fresh run below records that independent check and its import delta.
- Both original sources named in the unchanged `PROVENANCE.json` are
  `thermal-flight-lab@2199612` (`2199612932da142e0057e6162293940b4ea64bba`) and
  plan **PR #25@5e47b42a** (`5e47b42a1202cc4889ea74de8c57952e3f679210`).
- The prior report listed **52** post-import changes. That is a historical count;
  the fresh run's `import-delta/stdout.txt` is the current list.

### Files Changed Since Import (`git diff --name-only 0cd32a4 HEAD`)

```
.dockerignore
.github/workflows/ci.yml
.gitleaksignore
README.md
app/runs.py
contracts/HASHES.txt
... (52 files total — full list in regress script output)
```

---

## Reproduced in the 05:10Z Source-Box Observation

| # | Claim | Command | Exit | Count | Time (s) |
|---|-------|---------|------|-------|----------|
| 1 | 55 controller tests pass | `cd sundai_controller && python -m unittest -q test_controller.py test_experiment.py` | 0 | 55 (47+8) | ~0.4 |
| 2 | 1,000-case safety property (TFL-13) | `cd sundai_controller && python -m unittest -q test_safety_property.py` | 0 | 2 tests, 1000 cases | ~27.0 |
| 3 | TFL-08 multi-seed fingerprints | `cd sundai_controller && python -m unittest -q test_tfl08_leaderboard.py` | 0 | 8 | ~6.5 |
| 4 | HotSpot+SuperLU tap oracle tests | `cd sundai_hotspot && python -m unittest -q test_tap_oracle.py` | 0 | 14 | ~5.9 |
| 5 | 8 HotSpot+SuperLU Ascend910 probes | `cd sundai_hotspot && python run_tap_probe.py --report probe_results/report.json` (in scratch) | 0 | 8 | ~2.2 |
| 6 | TFL-14 probe peaks (single method) | `cd sundai_thermal && TFL_CANONICAL_CONTAINER=1 python -m unittest -q test_tfl14_regression.TFL14RegressionTests.test_eight_published_hotspot_probe_peaks` | 0 | 1 test | ~0.1 |
| 7 | Deterministic demo (baseline 93.3423169 C → final 92.3143491 C) | `cd sundai_controller && python demo.py` | 0 | 1 | ~1.6 |
| 8 | TFL-05 plate smoke test | `cd sundai_controller && python tfl05_smoke.py --benchmark plate` (in scratch) | 0 | 4 lanes, seed 11 | ~1.6 |
| 9 | TFL-05 ascend910 smoke test | `cd sundai_controller && python tfl05_smoke.py --benchmark ascend910` (in scratch) | 0 | 4 lanes, seed 11 | ~2.2 |
| 10 | TFL-09 run service tests | `python -m unittest -q app.test_runs` | 0 | 6 | ~2.3 |
| 11 | PROVENANCE.json sha256 integrity | Original checkout-file SHA-256 verification of all 494 entries | 0 | 494 files | ~0.5 |

### HotSpot Probe Values (all within expected ranges)

| Placement | Grid | Peak Chip Layer (°C) | Solver (s) |
|---|---|---|---|
| baseline_center | 16×16 | 118.36 | 0.037 |
| baseline_center | 32×32 | 118.89 | 0.472 |
| left_shift_2mm | 16×16 | 119.23 | 0.036 |
| left_shift_2mm | 32×32 | 119.36 | 0.460 |
| left_shift_4mm | 16×16 | 119.82 | 0.036 |
| left_shift_4mm | 32×32 | 119.78 | 0.460 |
| right_shift_2mm | 16×16 | 118.88 | 0.036 |
| right_shift_2mm | 32×32 | 118.84 | 0.467 |

**Assertion check (container_smoke.sh):** right_shift_2mm 32×32 peak 118.84 C — within [118.80, 118.90] ✓

---

## Reported But Not Reproducible From Repo Files

| # | Claim | Detail |
|---|-------|--------|
| 1 | TFL-14 README assertion (reproducible figures) | failed at 126507d4, import defect (the rewritten README dropped the asserted figures), fixed on main by 29b0c3b; passes on main |
| 2 | 114.82 / 105.28 C figures | These figures appear only in `docs/sentilab/draft-0.5/` plan documents and TFL-08 seed records, not as assertions in product code or tests. They represent prior reported results, not claims verifiable from the repo. |
| 3 | TFL-03 latency targets (< 0.1 s at 16×16, < 0.4 s at 32×32) | Per `scripts/container_smoke.sh` comments: these apply only to the deployed container, not a build agent. The SuperLU-in-use check (median < 2.0 s) passes: 16×16 median ~0.045 s, 32×32 median ~0.48 s. |

## Not Attempted

| # | Claim | Reason |
|---|-------|--------|
| 1 | `sys_micro150.cfg` (8 chiplets, 680 W) probe | Ticket states: "nothing uses it yet" — no test or probe references this config. |
| 2 | Full `scripts/container_smoke.sh` under Docker | not run in this box; CI ran the full container_smoke.sh green on main at 29b0c3b (Actions run 41171258578) |

---

## Notes

- **No product code was changed.** All findings are reported as-is.
- The historical source-box report recorded exit code 0 for these 11 measurements.
- The current script invokes the full TFL-14 module and propagates failure. That broader
  scope must not be attributed to the historical single-method ~0.1 s observation.
- The right_shift_2mm 32×32 probe peak (118.84 C) matches the container_smoke.sh assertion range exactly.
- The regress script (`scripts/sentilab_regress.sh`) runs all probe/demo/TFL-05 work in a scratch copy,
  captures and asserts demo.py output (93.3423169→92.3143491, receipt_chain_valid=true),
  and retains per-step stdout/stderr, artifacts, hashes, commands, exit codes and UTC
  timestamps in a new `runs/<UTC-timestamp>/` directory on success or failure.
  Only the newly created run directory is exempt from the clean checkout check.
  `run.json` records HEAD/tree/script hashes, Python/GCC/SuperLU/BLAS and the HotSpot hash.
- No product code or `PROVENANCE.json` was changed in these two evidence fixes.

See `results.json` for machine-readable details.

## Fresh retained run (2026-10-31)

The single authorized invocation of `bash scripts/sentilab_regress.sh` exited **0**:
**14 checks passed, 0 failed**, with 19 recorded steps including setup. This is a
new surrogate executor box under recorded model substitution; the earlier
source-box timings above are not attributed to this run.

- Executed HEAD: `44736fb2c584849ffbf43b39ab06cb061cc26483`
- Executed git tree: `1f0cde65da5a64bff3a5994d80fbaba13a760dd1`
- Script SHA-256: `8ef8d368d9a955ea9ed36f0a6d92fb70dfd689430550b999295a75b0d45cacc6`
- [Retained run.json](runs/20261031T062919.996386168Z-ACp7UI/run.json) (SHA-256 `979ba004b3f01ac316112a76c01b89dce7cf1ec53dc3a1faba92c0c8509bf9bf`)
- Each step links exact argv/cwd, UTC start/end, wall time, exit code, stdout, stderr and artifact hashes. Probe, demo and smoke outputs remain available after scratch cleanup.
- Fresh toolchain: Python 3.12.3; GCC 13.3.0; SuperLU `6.0.1+dfsg1-1build1`; BLAS `3.12.0-3build1.1`. Exact command outputs are in `run.json`.
- HotSpot binary SHA-256: `e4358b46794ebc00f07102d13b3ca687507834a1784eba135d26d1d493d334b4`. This local build happens to match the historical hash; hashes may differ on other toolchains.

| Check | Exit | Count | Wall time (s) | Command and logs |
|---|---|---|---|---|
| Import path-to-blob-to-SHA-256 verification | 0 | 494 | 2.681 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/provenance/step.json) |
| HotSpot + SuperLU build | 0 | 2 | 5.438 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/hotspot-build/step.json) |
| Controller and experiment tests | 0 | 55 | 0.514 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/controller/step.json) |
| Safety property tests (1,000 generated cases) | 0 | 2 | 26.793 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/safety/step.json) |
| TFL-08 fingerprint tests | 0 | 8 | 8.317 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/fingerprints/step.json) |
| HotSpot tap oracle tests | 0 | 14 | 6.392 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/tap-oracle/step.json) |
| Ascend910 probe cases | 0 | 8 | 2.460 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/probe/step.json) |
| Full TFL-14 module (probe peaks and README artifacts) | 0 | 2 | 15.314 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/thermal/step.json) |
| Deterministic demo execution | 0 | 1 | 1.742 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/demo/step.json) |
| Demo baseline, final and receipt assertions | 0 | 3 | 0.020 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/demo-assertions/step.json) |
| TFL-05 plate smoke lanes | 0 | 4 | 1.787 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/smoke-plate/step.json) |
| TFL-05 Ascend910 smoke lanes | 0 | 4 | 1.778 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/smoke-ascend910/step.json) |
| TFL-09 run service tests | 0 | 6 | 2.354 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/service/step.json) |
| Checkout unchanged except this run directory | 0 | 1 | 0.009 | [step.json](runs/20261031T062919.996386168Z-ACp7UI/clean-checkout/step.json) |

The full TFL-14 module took **15.314 s** for two tests; the historical **~0.1 s** row covers only the single probe-peaks method. The fresh demo assertions passed, separately from the original demo observation.

Fresh [probe report](runs/20261031T062919.996386168Z-ACp7UI/probe/artifacts/probe_results/report.json) contains eight cases; right_shift_2mm at 32×32 is 118.84 °C. The TFL-08 eight-test suite passed. No Docker, micro150 probe, GPU, inference or deployment was attempted.

Validation: `bash -n scripts/sentilab_regress.sh`, `git diff --check`, and four recorder tests passed. The recorder tests use real subprocesses; the pre-fix revision fails all four, and separate artifact-loss, overwrite and false-success mutations are detected. These targeted tests use no thermal solves.

Retained targeted-test transcripts: [four passing tests](validation/recorder-pass.txt),
[pre-fix failures](validation/pre-fix-failure.txt),
[artifact-loss mutation](validation/artifact-loss-mutation.txt),
[overwrite mutation](validation/overwrite-mutation.txt), and
[false-success mutation](validation/false-success-mutation.txt).
All mutations were made in a disposable worktree; no extra regression or thermal
probe invocation was used. The historical-scope check also rejected the previous
TFL-14 row and accepted the corrected single-method row. All 82 summary/run hash
references were checked after writing the final report.
