# SLAB-048 envelope plan: SAMPLED, not a bound

**Status: plan only.** No solve has been run for SLAB-048. Each call in `envelope-plan.json` waits for a named warden grant that lists these exact calls, a CPU cap, an expiry and the prior charges it keeps. SLAB-048 holds no prior solve charge.

**Role: ENGINEERING comparison and sensitivity.**
- This is a separately admitted experiment, never a paper match.
- Gate zero, the accepted 8+4 allocation, uses the two original raw 45 mm references. These calls are **not part of it and must never be appended to any other job, the gate-zero job included**.

A finite set of ±0.5 mm probes is a **sampled sensitivity envelope**. It does not bound the reconstruction error. All of these layouts are simulated references, not silicon.

## Calls

- Each probe starts from the **0.5 mm engineering variant** (`snap0p5`) of each reference, on the 45 mm fixtures at grid 64. The variant is plain nearest-0.5 mm rounding of the raw layout, legal with no repair, as decided by astra in ScienceClaw #56857.
- The calls are the unperturbed variant, plus each die moved +0.5 and -0.5 mm in x, and separately in y.
- Every call id names its base, for example `ascend910-tap25d-fig6a-snap0p5/die2/x+0.5`, so no call can be mistaken for the raw layout.
- A move the fixture gate rejects is listed under `excluded`, with its violations, and is not run.

| Base | Considered | Calls | Excluded |
|---|---:|---:|---|
| `ascend910-tap25d-fig6a-snap0p5` | 25 | **17** | 8 moves toward a neighbour across a 0.375 or 0.55 mm gap: Vitruvian +x and ±y, Nimbus -x, the lower HBMs +y, the upper HBMs -y (halo overlap or body overlap) |
| `micro150-tap25d-fig5a-snap0p5` | 33 | **29** | 4 CPU x moves toward the neighbouring CPU (halo overlap) |
| **Total** | 58 | **46** | 12 |

The JSON pins, for every call:
- the call id, die, axis and delta;
- the exact centres and rotation flags;
- the design hash;
- the base's content hash;
- the fixture config sha256.

A runner must refuse any design whose hash is not listed.

## Limits (what the envelope can and cannot say)

- **Not a stencil point.** The raw layout lies inside each base's ±0.5 mm per-coordinate box: L∞ 0.1952 mm for Ascend and 0.0751 mm for CPU-DRAM. That does **not** make it a sampled point of this one-axis stencil.
- **Not a uniform bound.** Finite sensitivity probes do not prove a uniform reconstruction bound.
- **Wire is a proxy.** The per-call `wire_proxy_mm` is the oracle's centre-distance proxy. The bases' routed wire (open router, not paper) is +1.50% and +1.75% against the paper's.

## Sizing (forecasts, not measured guarantees)

Measured inputs, all on the recorded Azure x86_64 host (16 CPUs):
- **Grid-64 solve wall, median:** Ascend 910 4.764 s, micro150 4.727 s (`docs/sentilab/evidence/micro150/TIMING.json`).
- **Mesh grid-64 evaluations, 24 each:** medians 4.74 and 4.86 s. The worst single call was **10.70 s**.
- **Lifecycle overhead, a heuristic:** 0.049685 CPU-s per call.
  - It is SLAB-039's aggregate CPU mean (0.5435 CPU-s per grid-32 call, fresh worker reaped every call) minus a *different* workload's wall median (the 0.494 s grid-32 TIMING solve).
  - It cannot isolate lifecycle overhead, and SLAB-039 did not record its host.

The 45 mm frame keeps the 64 x 64 grid, so the solve time is assumed unchanged.

| Item | CPU-s |
|---|---:|
| Forecast: 46 x (median solve + heuristic overhead) | **220.4** (3.67 CPU-min) |
| Reserved: 46 x (median solve + startup 0.25 + reap 0.25 + archive 0.25) | 252.6 |
| Failed-attempt reserve: 5 calls (10%) at the worst call plus reserves | 57.2 |
| Stop headroom: one worst-case call | 11.4 |
| Settlement tail (SUPERVISOR-POLICY) | 0.25 |
| **Proposed cap** | **321.5** (5.36 CPU-min) |

Reap and tail are the values approved in `SLAB-039/SUPERVISOR-POLICY.json`. Startup and archive are this plan's own declared reserves.

**Superseded first plan, kept on record.** It probed the 1 mm snapped variants: 45 calls, a forecast of 215.851 CPU-s and a proposed cap of 316.308 CPU-s, with the same derivation. It was superseded before any grant and never ran. Those figures are forecasts too.

## Proposed execution rules

1. Run exactly the listed calls on the named fixtures at grid 64. Refuse an unlisted design hash or a changed config sha256.
2. Admit this as its own job. Never append these calls to any other job, the gate-zero job included.
3. Use one fresh worker per call, reaped after the call, serial at one CPU.
4. Before each call, stop if cumulative CPU plus one worst-case call would pass the granted cap.
5. Keep raw outputs and every incomplete or failed outcome. Never rerun a completed call.
6. Report J per call against the base call, as a sampled envelope.
