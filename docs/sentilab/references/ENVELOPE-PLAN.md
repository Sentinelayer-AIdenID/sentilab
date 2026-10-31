# SLAB-048 envelope plan: SAMPLED, not a bound

**Status: plan only.** No solve has been run for SLAB-048. Each call in `envelope-plan.json` waits for a named warden grant that lists these exact calls, a CPU cap, an expiry and the prior charges it keeps. SLAB-048 holds no prior solve charge.

A finite set of +/-0.5 mm probes is a **sampled sensitivity envelope**. It does not bound the reconstruction error. All of these layouts are simulated references, not silicon.

## Calls

- Each probe starts from the **legal snapped variant**, not the paper's layout, on the 45 mm fixtures at grid 64.
- The calls are the unperturbed variant, plus each die moved +0.5 and -0.5 mm in x, and separately in y.
- A move the fixture gate rejects is listed under `excluded` with its violations, and is not run.

| Reference | Fixture | Considered | Calls | Excluded |
|---|---|---:|---:|---|
| `ascend910-tap25d-fig6a` | `ascend910-45mm` | 25 | **24** | Nimbus x+0.5: halo crosses the 0.5 mm margin |
| `micro150-tap25d-fig5a` | `micro150-45mm` | 33 | **21** | All 8 CPU x moves, and the 4 DRAM moves toward their CPU: halo overlap or 0.1 mm spacing |
| **Total** | | 58 | **45** | 13 |

The JSON pins, for every call:
- the call id, die, axis and delta;
- the exact centres and rotation flags;
- the design hash;
- the fixture config sha256.

A runner must refuse any design whose hash is not listed.

## Raw-to-snapped deltas (what the envelope can and cannot cover)

- **Ascend 910.** The upper HBM pair sits 1.12 mm above its drawn position. Nimbus is 0.65 mm right of its drawn position. Everything else is within 0.4 mm. The +/-0.5 mm probes do not reach the raw positions of those dies.
- **CPU-DRAM.** Every die is within 0.55 mm of its drawn position. Snapping narrows the CPU-CPU gaps from 0.90 to 0.75 mm and the CPU-DRAM gaps from 0.85 to 0.50 mm, so no CPU can be probed in x. The rows' snap direction (17/27 rather than 18/28) is decided below the decode precision.
- **Wire.** The snapped variants are experiment layouts, not wire-faithful stand-ins for the paper's. Their routed wire is +10.5% (Ascend) and -4.3% (CPU-DRAM) against the paper; the raw layouts are -0.05% and +0.004%. The per-call `wire_proxy_mm` in the JSON is the oracle's centre-distance proxy.

## Sizing (a forecast, not a bound)

Measured inputs, all on the recorded Azure x86_64 host (16 CPUs):
- **Grid-64 solve wall, median:** Ascend 910 4.764 s, micro150 4.727 s (`docs/sentilab/evidence/micro150/TIMING.json`).
- **Mesh grid-64 evaluations, 24 each:** medians 4.74 and 4.86 s. The worst single call was **10.70 s** (`mesh/ascend910/RESULT.json`, `mesh/micro150/rows.jsonl`).
- **Fresh-worker lifecycle overhead:** 0.0497 CPU-s per call. That is 0.5435 CPU-s per call in SLAB-039 (worker reaped every call) minus the 0.494 s grid-32 median. SLAB-039 did not record its host, so treat it as indicative.

The 45 mm frame keeps the 64 x 64 grid, so the solve time is assumed unchanged. HotSpot is single-threaded, so CPU is close to wall at one CPU.

| Item | CPU-s |
|---|---:|
| Forecast: 45 x (median solve + measured overhead) | **215.9** (3.60 CPU-min) |
| Reserved: 45 x (median solve + startup 0.25 + reap 0.25 + archive 0.25) | 247.4 |
| Failed-attempt reserve: 5 calls (10%) at worst call + reserves | 57.2 |
| Stop headroom: one worst-case call | 11.4 |
| Settlement tail (SUPERVISOR-POLICY) | 0.25 |
| **Proposed cap** | **316.3** (5.27 CPU-min) |

Reap and tail are the values approved in `SLAB-039/SUPERVISOR-POLICY.json`. Startup and archive are this plan's own declared reserves, each about 5 times the measured overhead.

## Proposed execution rules

1. Run exactly the listed calls on the named fixtures at grid 64. Refuse an unlisted design hash or a changed config sha256.
2. Use one fresh worker per call, reaped after the call, serial at one CPU.
3. Before each call, stop if cumulative CPU plus one worst-case call would pass the granted cap.
4. Keep raw outputs and every incomplete or failed outcome. Never rerun a completed call.
5. Report J per call against the base call, as a sampled envelope.
