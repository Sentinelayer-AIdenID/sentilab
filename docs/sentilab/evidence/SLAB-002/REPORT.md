# SLAB-002 Evidence Report: Pin the Imported Source and Rerun Every Existing Claim

**Ticket:** 5ee83372 · **Date:** 2026-10-31 · **Agent:** ds-slab002-source (lifeId 6b23dc5cc8ed)

## Toolchain

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

- **494/494** files verified — 0 mismatches, 0 missing
- Source: `Sentinelayer-AIdenID/thermal-flight-lab@2199612932da142e0057e6162293940b4ea64bba`
- Every file is byte-identical to its source blob

---

## Reproduced Here

| # | Claim | Command | Exit | Count | Time (s) |
|---|-------|---------|------|-------|----------|
| 1 | 55 controller tests pass | `cd sundai_controller && python -m unittest -q test_controller.py test_experiment.py` | 0 | 55 (47+8) | ~0.4 |
| 2 | 1,000-case safety property (TFL-13) | `cd sundai_controller && python -m unittest -q test_safety_property.py` | 0 | 2 tests, 1000 cases | ~27.0 |
| 3 | TFL-08 multi-seed fingerprints | `cd sundai_controller && python -m unittest -q test_tfl08_leaderboard.py` | 0 | 8 | ~6.5 |
| 4 | HotSpot+SuperLU tap oracle tests | `cd sundai_hotspot && python -m unittest -q test_tap_oracle.py` | 0 | 14 | ~5.9 |
| 5 | 8 HotSpot+SuperLU Ascend910 probes | `cd sundai_hotspot && python run_tap_probe.py --report probe_results/report.json` | 0 | 8 | ~2.2 |
| 6 | TFL-14 probe peak regression (published values) | `TFL_CANONICAL_CONTAINER=1 ... python -m unittest test_tfl14_regression.TFL14RegressionTests.test_eight_published_hotspot_probe_peaks` | 0 | 1 (8 sub-checks) | ~0.1 |
| 7 | Deterministic demo (93.34 → 92.31 C) | `cd sundai_controller && python demo.py` | 0 | 1 | ~1.6 |
| 8 | TFL-05 plate smoke test | `cd sundai_controller && python tfl05_smoke.py --benchmark plate` | 0 | 4 lanes, seed 11 | ~1.6 |
| 9 | TFL-05 ascend910 smoke test | `cd sundai_controller && python tfl05_smoke.py --benchmark ascend910` | 0 | 4 lanes, seed 11 | ~2.2 |
| 10 | TFL-09 run service tests | `python -m unittest -q app.test_runs` | 0 | 6 | ~2.3 |
| 11 | PROVENANCE.json sha256 integrity | Scripted verification of all 494 entries | 0 | 494 files | ~0.5 |

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
| 1 | TFL-14 seeded random annealing artifacts in README.md | `test_tfl14_regression.TFL14RegressionTests.test_seeded_random_annealing_and_recorded_artifacts_are_reproducible` FAILS: it checks README.md for strings like `random 79.9564865°C`. The README.md was explicitly rewritten for SentiLab (PROVENANCE.json exclusions: "README.md: rewritten for SentiLab"), so those strings no longer exist. The simulation itself reproduces correctly. |
| 2 | 114.82 / 105.28 C figures | These figures appear only in `docs/sentilab/draft-0.5/` plan documents and TFL-08 seed records, not as assertions in product code or tests. They represent prior reported results, not claims verifiable from the repo. |
| 3 | TFL-03 latency targets (< 0.1 s at 16×16, < 0.4 s at 32×32) | Per `scripts/container_smoke.sh` comments: these apply only to the deployed container, not a build agent. The SuperLU-in-use check (median < 2.0 s) passes: 16×16 median ~0.045 s, 32×32 median ~0.48 s. |
| 4 | Full `scripts/container_smoke.sh` under Docker | Docker not available in this box. All individual components verified separately and pass. |

---

## Not Attempted

| # | Claim | Reason |
|---|-------|--------|
| 1 | `sys_micro150.cfg` (8 chiplets, 680 W) probe | Ticket states: "nothing uses it yet" — no test or probe references this config. |
| 2 | Full Docker build (`docker build .`) | Docker not available in this environment. Individual components all verified. |

---

## Notes

- **No product code was changed.** All findings are reported as-is.
- The `test_tfl14_regression` test failure is pre-existing: the README.md rewrite (documented in PROVENANCE.json) removed the strings the test checks for. This is a test/maintenance issue, not a regression.
- All 11 reproduced claims pass with exit code 0.
- The right_shift_2mm 32×32 probe peak (118.84 C) matches the container_smoke.sh assertion range exactly.

See `results.json` for machine-readable details.
