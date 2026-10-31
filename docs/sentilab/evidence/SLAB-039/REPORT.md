# SLAB-039 Headroom Report: ascend910

**Verdict: INCONCLUSIVE**

Run: 2026-10-31T06:29:43.495793+00:00 to 2026-10-31T06:55:09.347831+00:00.
Preregistration SHA256: `211bd3c181305ead1bc924ffc11dc5fb042cd7a6e05ce5ca15a8ca89c500db8e`.

Mesh error: 0.160000 C; k = 5; threshold = 0.800000 C.
Gap = cheap median 117.685000 minus best 116.090000 = 1.595000 C.
Reducer spread across seeds: 1.660000 C.

## Reducer methods

| Method | Median best C | Min C | Max C |
|---|---:|---:|---:|
| random | 118.145000 | 117.230000 | 118.890000 |
| greedy | 117.685000 | 117.270000 | 118.450000 |
| simulated_annealing | 118.190000 | 117.480000 | 118.820000 |

The gate uses the lowest reducer median. Each seed receives 28 search calls, including initialize() and any shared designs, then 4 fresh evaluations of the frozen search winner. Greedy starts at the fixture initial layout and accepts only strict improvements.

## Long SA

| Seed | Calls | Best C | CPU seconds | Stop reason |
|---|---:|---:|---:|---|
| 100 | 1000 | 116.260000 | 544.846 | completed |
| 101 | 882 | 116.090000 | 474.916 | fixture_cpu_cap |
| 102 | 0 | unavailable | 0.001 | fixture_cpu_cap |
| 103 | 0 | unavailable | 0.001 | fixture_cpu_cap |

## Spend

Actual oracle calls this run: 2650; CPU: 1440.295 seconds (24.005 minutes).
Accounting: getrusage SELF+CHILDREN; workers reaped after every call; includes startup.
The durable ledger reserves and fsyncs before every call, including initialization and reproduction. Caps are 4,768 calls / 24 CPU minutes per fixture and 9,700 calls / 48 CPU minutes across fixtures. An in-flight evaluation may cross the CPU limit; the next call is refused. A crash with an outstanding reservation fails closed pending reconciliation.

Extra diagnostics: 0 runs; skip reason: declared_runs_incomplete. Diagnostics run only after all declared runs and cannot change the reducer median.

At least one declared run did not complete. This result cannot establish protocol PASS or FAIL.

micro150 was not run; its own mesh error is still required.
