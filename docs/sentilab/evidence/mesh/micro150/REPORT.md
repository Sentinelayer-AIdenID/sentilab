# Mesh study: micro150

24 frozen layouts; 72 evaluations; 138.284 seconds. J is the chip-layer grid peak (Celsius).

Layouts SHA-256: `0a7819d5d062f358c53d27a3fdb294914208f37115cfafb733e13c79bd6ddd6b`.
Execution commit: `c6d5b0caa0c33402eaa35012306a098701808f22`.

Reference: 64x64. e = max |J32-J64| = 0.7899999999999636 C; e16 = max |J16-J64| = 4.28000000000003 C.

## Rank rule

32 passes if violations = 0 and at least one pair is eligible: for each pair with |J64(a)-J64(b)| > 2e, the signs of J32(a)-J32(b) and J64(a)-J64(b) must agree. 16 uses its own 2e16. Equality at the tolerance is excluded (1e-12 C roundoff guard); a coarse tie is a violation.

Because e is the maximum error on this same sample, the triangle inequality guarantees no inversions beyond 2e. This pass is an internal consistency check, not independent evidence that all ranks agree. Zero eligible pairs is inconclusive (null pass verdict). The predeclared fixed 0.01 C tolerance provides an additional ranking diagnostic.

| Grid | Max error C | 2e tolerance C | Eligible / total | Violations | Pass | Fixed 0.01 C eligible | Fixed inversions | Fixed coarse ties |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 16 | 4.280000 | 8.560000 | 201 / 276 | 0 | True | 276 | 9 | 0 |
| 32 | 0.790000 | 1.580000 | 266 / 276 | 0 | True | 276 | 1 | 0 |

## Observed ranking resolution

Grid 16: largest reference-grid gap reversed or left tied is 4.660000 C.
Grid 32: largest reference-grid gap reversed or left tied is 0.240000 C.

This statistic compares all unequal reference pairs (zero tie tolerance, with the same roundoff guard). It measures gaps on the reference grid, not coarse-grid differences, and is an observation on these layouts, not a guaranteed threshold for unseen layouts.


## Measured peaks (C)

| Layout | J16 | J32 | J64 |
| --- | ---: | ---: | ---: |
| clustered-01 | 204.59 | 205.75 | 205.79 |
| clustered-02 | 195.35 | 198.09 | 198.22 |
| clustered-03 | 230.16 | 231.48 | 231.27 |
| clustered-04 | 201.94 | 202.92 | 203.19 |
| clustered-05 | 181.59 | 182.71 | 182.75 |
| clustered-06 | 215.27 | 217.63 | 217.62 |
| clustered-07 | 193.25 | 193.55 | 193.91 |
| clustered-08 | 175.27 | 176.68 | 176.97 |
| spread-01 | 166.61 | 170.23 | 170.89 |
| spread-02 | 168.18 | 169.59 | 169.81 |
| spread-03 | 158.64 | 159.69 | 160.13 |
| spread-04 | 165.83 | 167.71 | 168.07 |
| spread-05 | 169.76 | 172.97 | 173.59 |
| spread-06 | 161.65 | 163.45 | 163.67 |
| spread-07 | 187.62 | 187.28 | 187.39 |
| spread-08 | 161.83 | 165.51 | 165.73 |
| random-01 | 169.70 | 170.31 | 170.65 |
| random-02 | 196.10 | 197.74 | 197.50 |
| random-03 | 170.55 | 168.47 | 168.93 |
| random-04 | 189.09 | 191.88 | 192.25 |
| random-05 | 195.49 | 196.10 | 196.08 |
| random-06 | 194.96 | 194.14 | 194.93 |
| random-07 | 189.26 | 190.42 | 190.52 |
| random-08 | 184.78 | 185.47 | 185.97 |

## Resource accounting

Solver executions in this run: 72. CPU-minutes (process plus reaped children): 2.163248.

Per-run accounting is not a shared-budget clearance. See VALIDATION.md in this evidence directory for the reservation, validation use and remaining allowance; historical accounting limitations are recorded in ../VALIDATION.md.


## Retained evidence

Raw HotSpot inputs and outputs are not retained; D02 is incomplete.
Full parsed receipts, input hashes, heatmaps and heatmap hashes are in rows.jsonl; RESULT.json binds the journal hash and per-row sequence numbers.


## Scope

e is an empirical discrepancy against 64 on this fixed layout set, not an error bound against the continuum or unseen layouts. Later R4/u_num and SLAB-039 margins can use e with that scope; a two-layout difference needs a margin greater than 2e. The fixed 0.01 C tolerance is a sensitivity diagnostic, not measured numerical uncertainty or a practical minimum effect. The 16-grid error and fixed-tolerance inversions show the limits of cheap screening. No benchmark method-gap or continuum-convergence claim is made here.

All J values, per-evaluation timings, design hashes, problem/config/source/binary hashes and all-layer peaks are in RESULT.json. Layout generation and reproduction instructions are in ../README.md. Each fixture has its own frozen sample and measured mesh error; do not transfer an error estimate between fixtures.
