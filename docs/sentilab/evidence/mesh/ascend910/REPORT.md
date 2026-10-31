# Mesh study: ascend910

24 frozen layouts; 72 evaluations; 152.289 seconds. J is the chip-layer grid peak (Celsius).

Layouts SHA-256: `8740e67a45c75d916927c008dd35cb360a8776d496a846175f387e9ea42bae14`.
Execution commit: `ba39fe4785ac0cd1bc5464c018188a6a83c82edf`.

Reference: 64x64. e = max |J32-J64| = 0.160000000000025 C; e16 = max |J16-J64| = 0.8600000000000136 C.

## Rank rule

32 passes if violations = 0 and at least one pair is eligible: for each pair with |J64(a)-J64(b)| > 2e, the signs of J32(a)-J32(b) and J64(a)-J64(b) must agree. 16 uses its own 2e16. Equality at the tolerance is excluded (1e-12 C roundoff guard); a coarse tie is a violation.

Because e is the maximum error on this same sample, the triangle inequality guarantees no inversions beyond 2e. This pass is an internal consistency check, not independent evidence that all ranks agree. Zero eligible pairs is inconclusive (null pass verdict). The predeclared fixed 0.01 C tolerance provides an additional ranking diagnostic.

| Grid | Max error C | 2e tolerance C | Eligible / total | Violations | Pass | Fixed 0.01 C eligible | Fixed inversions | Fixed coarse ties |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 16 | 0.860000 | 1.720000 | 55 / 276 | 0 | True | 273 | 15 | 1 |
| 32 | 0.160000 | 0.320000 | 220 / 276 | 0 | True | 273 | 3 | 2 |

## Observed ranking resolution

Grid 16: largest reference-grid gap reversed or left tied is 0.390000 C.
Grid 32: largest reference-grid gap reversed or left tied is 0.110000 C.

This statistic compares all unequal reference pairs (zero tie tolerance, with the same roundoff guard). It measures gaps on the reference grid, not coarse-grid differences, and is an observation on these layouts, not a guaranteed threshold for unseen layouts.


## Measured peaks (C)

| Layout | J16 | J32 | J64 |
| --- | ---: | ---: | ---: |
| clustered-01 | 117.40 | 118.10 | 118.15 |
| clustered-02 | 118.97 | 119.11 | 119.12 |
| clustered-03 | 119.88 | 120.08 | 120.07 |
| clustered-04 | 118.98 | 119.14 | 119.16 |
| clustered-05 | 120.47 | 120.59 | 120.65 |
| clustered-06 | 118.00 | 118.18 | 118.17 |
| clustered-07 | 118.91 | 118.96 | 118.98 |
| clustered-08 | 119.13 | 119.41 | 119.46 |
| spread-01 | 118.41 | 118.88 | 118.97 |
| spread-02 | 117.55 | 118.07 | 118.19 |
| spread-03 | 119.34 | 119.42 | 119.40 |
| spread-04 | 116.78 | 117.20 | 117.17 |
| spread-05 | 118.68 | 118.58 | 118.59 |
| spread-06 | 118.78 | 118.69 | 118.78 |
| spread-07 | 117.55 | 118.25 | 118.41 |
| spread-08 | 117.42 | 117.92 | 118.02 |
| random-01 | 119.91 | 120.06 | 120.03 |
| random-02 | 118.23 | 118.25 | 118.30 |
| random-03 | 120.03 | 120.41 | 120.48 |
| random-04 | 120.67 | 120.78 | 120.79 |
| random-05 | 118.80 | 118.88 | 118.91 |
| random-06 | 117.87 | 118.38 | 118.54 |
| random-07 | 119.20 | 119.16 | 119.27 |
| random-08 | 118.47 | 118.93 | 118.98 |

## Resource accounting

Solver executions in this run: 72. CPU-minutes (process plus reaped children): not measured; budget compliance is unverified.

The shared allowance is 150 solver executions and 6 CPU-minutes across both fixtures, including warm-up and validation. Per-run accounting is not a shared-budget clearance. See RESULT.json and VALIDATION.md for prior usage and unresolved accounting.


## Scope

e is an empirical discrepancy against 64 on this fixed layout set, not an error bound against the continuum or unseen layouts. Later R4/u_num and SLAB-039 margins can use e with that scope; a two-layout difference needs a margin greater than 2e. The fixed 0.01 C tolerance is a sensitivity diagnostic, not measured numerical uncertainty or a practical minimum effect. The 16-grid error and fixed-tolerance inversions show the limits of cheap screening. No benchmark method-gap or continuum-convergence claim is made here.

All J values, per-evaluation timings, design hashes, problem/config/source/binary hashes and all-layer peaks are in RESULT.json. Layout generation and reproduction instructions are in ../README.md. Ascend910 is interim evidence; required micro150 evidence is pending SLAB-002b wiring, so the combined study remains inconclusive.
