# SLAB-048 reference layouts

Ticket SLAB-048 REF-RECON (`c3dcb49a-430a-462e-a446-f532da204c46`).

Every layout here is an **approximate reconstruction from a published figure** and a **simulated reference, not silicon**.
- **Ascend 910 is a SHIPPED product.** The positions are read from a published figure, not CAD. The figure is TAP-2.5D's model of the package.
- **CPU-DRAM is a human-designed RESEARCH layout** (Kannan et al., MICRO 2015), not a shipped package.

Any claim made against these references carries the label in `claim_label`:
> Simulated with [evaluator and hash], steady state, uniform power per die. Reference reconstructed from a published figure. Not CAD, not silicon, not measured.

No thermal solve was run for this ticket. The envelope plan lists calls that wait for a warden grant ([ENVELOPE-PLAN.md](ENVELOPE-PLAN.md)).

## Files

| File | What it is |
|---|---|
| `decode_tap25d_figures.py` | Decoder: reads die outlines from the paper's vector figures. It needs PyMuPDF and the PDF; neither is in this repo |
| `tap25d-figure-decode.json` | Decoder output for Fig. 5 (a)-(d) and Fig. 6 (a)-(c), with the PDF's sha256 and the decoder's own sha256 |
| `ascend910-tap25d-fig6a.json` | MATCH reference: Ascend 910, Fig. 6(a). Raw, snapped, round trip and validation points |
| `micro150-tap25d-fig5a.json` | BEAT reference: CPU-DRAM, Fig. 5(a). Same contents |
| `envelope-plan.json`, `ENVELOPE-PLAN.md` | The SAMPLED +/-0.5 mm envelope call list and its sizing |

Rebuilding:
- `python -m sundai_hotspot.tap_references --check` rebuilds the reference and plan files from the committed decode and compares bytes. `--write` regenerates them.
- `sundai_hotspot/test_references.py` runs the same check.
- The build runs TAP's router (`sundai_hotspot/tap_router.py`, a MILP) but never a thermal solver.

## Source and decoding

- **Paper:** Y. Ma et al., "TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems", DATE 2021, http://people.bu.edu/joshi/files/Ma_TAP-2.5D-DATE2021.pdf.
  - PDF sha256 `b209f51aec188e2bcdbf6f4acc3723fb30fbc5c14cca7e70141d478edadec234`.
  - Fig. 5 and Fig. 6 are on page 6 (index 5).
- **Decoder:** sha256 `c86c34d78f1399959317525ed56df22e0b376a1bed69b46c0be336099f06e825`. The same hash is inside the decode JSON and both reference files.
- **How the coordinates were obtained.** The figures were drawn by TAP's `util/grid_thermal_map.pl` from the generated chip-layer floorplan. That script draws each floorplan unit as four lines, in file order: `Edge_0..3`, then each die's halo strips and body (`Chiplet_i`), then whitespace. So:
  - the i-th die-sized rectangle in a panel is TAP die i;
  - a die's centre is the midpoint of its drawn outline;
  - the edge strips give the frame and the origin (the frame's lower-left corner);
  - the frame size comes out three ways (strip thickness with TAP's 1 mm granularity, strip length, and die outlines against the catalog), and all give 45 mm.

  Each reference lists, per die, the outline in PDF points and how it was mapped (`raw.how_obtained`).
- **Rotated panels.** Fig. 6 (b) and (c) are drawn rotated 90 degrees clockwise. Their line order and edge strips show it, and the decoder maps them back. Panel (a) of both figures is drawn unrotated.
- **Per-coordinate uncertainty** is given as `raw.center_uncertainty_mm`, 0.0007 to 0.0022 mm. It is the sum of three terms, rounded up:
  - the decode error measured on TAP's own panels: those must sit on its 1 mm grid, and all 36 of their centres decode to within 0.0005 mm of it;
  - the coordinate times the spread of the panel's three scale estimates;
  - half the 1e-4 mm storage step.

  This covers reading the figure only. Whether the figure matches the authors' simulated layout cannot be measured from the figure.
- **Die identity** follows the drawing order. For CPU-DRAM the netlist cross-checks it: each DRAM sits beside the CPU it links to, and the CPU ring has no diagonal.

## Round trip (room #56739, item (b)2)

The criterion: our evaluator and router on the **raw** reference reproduce the paper's own numbers, with temperature within 1.0 K and routed wire within 2%.

**Wire: done, no thermal solve needed.** `sundai_hotspot/tap_router.py` is TAP-2.5D's own MILP router (`routing.py`), ported from CPLEX to HiGHS. It carries the Apache-2.0 change notice. On the decoded layouts:

| Layout | Ours (routed mm) | Paper (mm) | Difference |
|---|---:|---:|---:|
| Ascend 910 original, Fig. 6(a), raw | 16,417.5 | 16,426 | -0.05% |
| CPU-DRAM original, Fig. 5(a), raw | 67,688.4 | 67,686 | +0.004% |

Half a millimetre of digitising error is about 3.7% of Ascend's routed wire, so this agreement is what pins the coordinates at the wire level.

**Temperature: planned, not run.** The prerequisites, all recorded in `round_trip.temperature`:
- a named warden grant;
- the paper's statistic: maximum of the chip-layer unit temperatures with `-grid_map_mode center` at 64 x 64. Our J, the grid peak with `max`, stays a diagnostic;
- the paper's package physics: HotSpot 6.0's vertical coupling, or a reviewed fix (SLAB-049 CAL-COUPLING);
- a fixture that accepts the raw centres. The 45 mm fixtures' 0.5 mm lattice refuses them.

**Validation points.** These are out-of-sample, not tuning targets. They are other published layouts, decoded the same way and never used to choose anything here.

| Layout | Paper J | Ours (routed mm) | Paper (mm) | Difference |
|---|---:|---:|---:|---:|
| Ascend Compact-2.5D, Fig. 6(b) | 75.13 C | 23,805.5 | 23,794 | +0.05% |
| Ascend TAP-2.5D, Fig. 6(c) | 75.47 C | 16,613.5 | 16,597 | +0.10% |
| CPU-DRAM Compact-2.5D, Fig. 5(b) | 113.54 C | 100,832.1 | 100,864 | -0.03% |
| CPU-DRAM TAP-2.5D non-pipelined, Fig. 5(c) | 94.89 C | 216,109.7 | 216,064 | +0.02% |
| CPU-DRAM TAP-2.5D gas-station, Fig. 5(d) | 93.89 C | 139,036.1 | 138,956 | +0.06% |

The temperatures are the paper's own values and have not been evaluated here.

**The wire numbers elsewhere are still a proxy.**
- The router is not wired into the oracle or the search. The `W` / `wirelength_mm` in oracle results and the `wire_proxy_mm` in these files remain the oracle's centre-distance proxy, and any claim using them must say "proxy".
- Wiring routed wire into the oracle's results and the STRICT wire track (SLAB-051) is a follow-up. One route takes 0.2 to 1.5 s on the measured hosts, with no solver grant needed.

## The references

**Raw reconstruction (approximate, from published figure)** is the decoded centres, kept exactly, at 1e-4 mm resolution. It is allowed to be illegal on our fixture, and it is: it is off the 0.5 mm centre lattice. Without the lattice it passes every other rule (margin, halos, 0.1 mm spacing).

**Legal snapped variant (adjusted)** is a separate experiment layout on the 1 mm grid. It is **not the paper's layout**. Never present it as such, and do not use it for wire comparisons against the paper:
- Ascend routed wire is 18,155.8 mm, +10.5% against the paper's figure.
- CPU-DRAM routed wire is 64,771.3 mm, -4.3%.

Snapping rule (`sundai_hotspot/tap_references.py: snap_to_grid`):
1. Round each raw centre to the nearest 1 mm node.
2. Make the fewest 1 mm moves that make the layout legal on the fixture. Legal means margin with halo, halo non-overlap, the 0.1 mm minimum body spacing and the centre lattice, as checked by `TapGeometry.centers_for`.
3. If several move sets of that size exist, keep the one closest to the raw centres (sum of squared distances), then the lexicographically smallest.
4. Every adjustment is recorded as die, dx, dy, and the reason is exactly what dropping it would break. The tests drop each one and require the layout to fail.

### Ascend 910, Fig. 6(a) (MATCH), fixture `ascend910-45mm`

| Die | Catalog (w x h) | Turned | Footprint | Raw centre | Snapped | Raw to snapped |
|---|---|---|---|---|---|---|
| 0 Vitruvian, 256 W | 14.5 x 31.4 | yes | 31.4 x 14.5 | (17.1501, 22.6003) | (17, 23) | (-0.1501, +0.3997) |
| 1 Nimbus, 14 W | 10.5 x 16 | no | 10.5 x 16 | (38.3497, 22.6003) | (39, 23) | (+0.6503, +0.3997) |
| 2 HBM, 20 W | 7.75 x 11.87 | yes | 11.87 x 7.75 | (7.3350, 11.1256) | (7, 11) | (-0.3350, -0.1256) |
| 3 HBM, 20 W | 7.75 x 11.87 | yes | 11.87 x 7.75 | (21.3048, 11.1256) | (21, 11) | (-0.3048, -0.1256) |
| 4 HBM, 20 W | 7.75 x 11.87 | yes | 11.87 x 7.75 | (7.3350, 33.8754) | (7, 35) | (-0.3350, +1.1246) |
| 5 HBM, 20 W | 7.75 x 11.87 | yes | 11.87 x 7.75 | (21.3048, 33.8754) | (21, 35) | (-0.3048, +1.1246) |

Plain rounding gives Nimbus 0.05 mm from Vitruvian, which breaks the halo clearance and the 0.1 mm spacing. It also gives a 0.125 mm overlap between Vitruvian and the upper HBMs. Three adjustments fix this: Nimbus +1 mm in x, and HBMs 4 and 5 +1 mm in y.

The largest raw-to-snapped shift is 1.12 mm, because the packed human layout cannot sit on a 1 mm grid. Its HBM-to-compute centre pitches are 11.47 and 11.28 mm. Clearance needs at least 11.26 mm, so the smallest legal pitch on the grid is 12 mm.

Wire proxy: raw **18.82 mm**, snapped 19.49 mm.

### CPU-DRAM, Fig. 5(a) (BEAT), fixture `micro150-45mm`

| Die | Catalog | Turned | Raw centre | Snapped | Raw to snapped |
|---|---|---|---|---|---|
| 0 CPU, 150 W | 8.25 x 9 | no | (17.9249, 17.5496) | (18, 17) | (+0.0751, -0.5496) |
| 1 CPU, 150 W | 8.25 x 9 | no | (27.0751, 17.5496) | (27, 17) | (-0.0751, -0.5496) |
| 2 CPU, 150 W | 8.25 x 9 | no | (27.0751, 27.4497) | (27, 27) | (-0.0751, -0.4497) |
| 3 CPU, 150 W | 8.25 x 9 | no | (17.9249, 27.4497) | (18, 27) | (+0.0751, -0.4497) |
| 4 DRAM, 20 W | 8.75 x 8.75 | no | (8.5751, 17.5496) | (9, 17) | (+0.4249, -0.5496) |
| 5 DRAM, 20 W | 8.75 x 8.75 | no | (36.4249, 17.5496) | (36, 17) | (-0.4249, -0.5496) |
| 6 DRAM, 20 W | 8.75 x 8.75 | no | (36.4249, 27.4497) | (36, 27) | (-0.4249, -0.4497) |
| 7 DRAM, 20 W | 8.75 x 8.75 | no | (8.5751, 27.4497) | (9, 27) | (+0.4249, -0.4497) |

Plain rounding puts both rows 9 mm apart, so each column's halos overlap. Four adjustments fix this: dies 0, 1, 4 and 5 each move -1 mm in y. Moving the upper row up instead costs 0.0014 mm² more per column. That is **below the decode precision** (bound 0.002 mm²), so the 17/27 row choice is a tie-break, not evidence. The 18/28 alternatives are listed in the file. Wire proxy: raw 9.38 mm, snapped 9.10 mm.

## What the paper reports, and what is not comparable

Paper settings: 45 mm interposer, 1 mm placement grid, 64 x 64 thermal grid, 45 C ambient, HotSpot 6.0. Original layouts:
- Ascend 910: 75.48 C, 16,426 mm routed.
- CPU-DRAM: 115.94 C, 67,686 mm routed.

Validation points are in the table above.

Not comparable with our thermal numbers as they stand:
- **Temperature statistic.** TAP's `run_hotspot()` takes the maximum over HotSpot's unit temperatures with `-grid_map_mode center`. Our J is the chip-layer grid peak with `-grid_map_mode max`.
- **Simulator.** HotSpot 6.0 vs our HotSpot 7.

Model omissions:
- The shipped Ascend 910 carries two unpowered silicon dummy dies (about 110 mm² each, Hot Chips 31: "added to ensure mechanical uniformity") beside Nimbus. TAP's model, its Fig. 6(a) and this reconstruction all omit them, so their lateral heat path is not modelled.
- TAP's die sizes and its 256/14/4 x 20 W power split are modelling assumptions.

## 45 mm fixtures

`sundai_tap/configs/sys_ascend910_45mm.cfg` and `sys_micro150_45mm.cfg` sit next to the 50 mm files. Each carries a change notice. The dies, powers, netlist and TAP's 1 mm granularity are unchanged. What differs:
- `intp_size = 45`. The worker builds the package from it, so the spreader is 90 mm and the sink 180 mm.
- A `[sentilab]` section that only `sundai_hotspot/tap_oracle.py` reads:
  - `center_lattice_mm = 0.5`, so the half-step envelope probes are legal;
  - `min_die_gap_mm = 0.1`, TAP-2.5D Eqn. (10);
  - `rotation = per_die_90`.

The 50 mm fixtures are unchanged: same config bytes, same physics contract as the frozen mesh layouts, catalog orientation only, a 1 mm lattice and no extra spacing rule. Their problem hashes do change, as after any oracle edit: the hash binds the oracle and worker sources, and it now also records the (unchanged) legality rules. Design hashes do not change.

## Rotation

A turn is 90 degrees about the die centre: the die's footprint swaps width and height (`Design.apply("rotate", {"chiplet": id})`). Because the footprint lives on the chiplet, every consumer reads the turned die:
- the oracle's legality and centres (`TapGeometry.centers_for`);
- the worker request (`rotated` flags), where TAP's own `rotate()` runs before the floorplan is written;
- the router;
- the wire proxy;
- the Lab/Package view rectangles (`sentilab_core.conductor.view_geometry`).

Each fixture declares its orientation catalog. A square die has one orientation, so turning it is refused rather than spending a solve on the same layout. The search operator `rotate` is available to `_candidate`. The frozen lanes keep their three operators, so no historical run changes; a new protocol opts in.

## Open uncertainties

- The micro150 snap direction is a tie below decode precision (above).
- The Ascend snapped variant moves the upper HBM pair 1.12 mm from the drawing. The +/-0.5 mm envelope does not reach the raw positions.
- On the fixtures' own 0.5 mm lattice, plain rounding is already legal for both references.
  - It needs no adjustment and keeps every die within 0.20 mm (Ascend) or 0.08 mm (CPU-DRAM) of the drawing.
  - Its routed wire is +1.5% and +1.75% against the paper, which is within the 2% round trip.
  - This PR keeps the 1 mm snap the review asked for. Switching is a one-argument change (`snap_to_grid(..., grid_mm=0.5)`).
- Review input (astra) reports that a separate vector extraction reproduces the Fig. 6(a) centres within 0.054 mm. This decoder's own check against TAP's grid is 0.0005 mm, and the routed-wire round trip agrees with the paper within 0.05%. The 0.054 mm difference is not explained here.
- The decode reads the figure, and the figure was drawn from TAP's floorplan. Anything the authors changed between their simulation and the drawing is invisible to us. Fig. 6(b)/(c) being rotated for display shows the figures were edited after generation. The routed-wire agreement on all seven panels suggests the positions were not.
