# git -C H:/sentilab show origin/main:docs/sentilab/references/README.md | cat -n
# origin/main = 46791be360555d0e24b4ad5f906abafb71f07118
     1	# SLAB-048 reference layouts
     2	
     3	Ticket SLAB-048 REF-RECON (`c3dcb49a-430a-462e-a446-f532da204c46`).
     4	
     5	Every layout here is an **approximate reconstruction from a published figure** and a **simulated reference, not silicon**.
     6	- **Ascend 910 is a SHIPPED product.** The positions are read from a published figure, not CAD. The figure is TAP-2.5D's model of the package.
     7	- **CPU-DRAM is a human-designed RESEARCH layout** (Kannan et al., MICRO 2015), not a shipped package.
     8	
     9	Any claim made against these references carries the label in `claim_label`:
    10	> Simulated with [evaluator and hash], steady state, uniform power per die. Reference reconstructed from a published figure. Not CAD, not silicon, not measured.
    11	
    12	No thermal solve was run for this ticket. The envelope plan lists calls that wait for a warden grant ([ENVELOPE-PLAN.md](ENVELOPE-PLAN.md)).
    13	
    14	## Roles of the three layouts per reference
    15	
    16	These roles follow root's decision in ScienceClaw #56857 and #56858.
    17	
    18	| Layout | Where | Role |
    19	|---|---|---|
    20	| **Raw reconstruction** | `<reference>.json`, field `raw` | **Gate zero**: the paper-reconstruction comparison, with its exact continuous geometry and rotations. Frozen (below). |
    21	| **0.5 mm variant** (`snap0p5`) | `<reference>-snap0p5.json` | **Engineering** comparison and sensitivity baseline, separately admitted. Never a paper match, and not part of gate zero. The envelope probes it. |
    22	| **1 mm snapped variant** | `<reference>.json`, field `snapped` | The first legal experiment layout, kept unchanged. Not the paper's layout. Superseded as the baseline. |
    23	
    24	Gate zero, the accepted 8+4 allocation, uses the two raw 45 mm references only. Nothing in this folder appends calls to it or to any other job: the envelope is admitted as its own job.
    25	
    26	## Files
    27	
    28	| File | What it is |
    29	|---|---|
    30	| `decode_tap25d_figures.py` | Vector figure extraction from the PDF (sha256 `b209f51a...`), mapped to TAP's floorplan grid. It needs PyMuPDF and the PDF; neither is in this repo |
    31	| `tap25d-figure-decode.json` | Extraction output for Fig. 5 (a)-(d) and Fig. 6 (a)-(c), with the PDF's sha256 and the decoder's own sha256 |
    32	| `ascend910-tap25d-fig6a.json` | MATCH reference: Ascend 910, Fig. 6(a). Raw, 1 mm snapped, round trip, validation points |
    33	| `micro150-tap25d-fig5a.json` | BEAT reference: CPU-DRAM, Fig. 5(a). Same contents |
    34	| `ascend910-tap25d-fig6a-snap0p5.json`, `micro150-tap25d-fig5a-snap0p5.json` | The 0.5 mm engineering variants: manifests with rotations, units, config and source hashes, the rounding rule and displacements |
    35	| `envelope-plan.json`, `ENVELOPE-PLAN.md` | The SAMPLED ±0.5 mm envelope on the 0.5 mm variants, with its sizing |
    36	
    37	Rebuilding:
    38	- `python -m sundai_hotspot.tap_references --check` rebuilds every JSON above, except the extraction output, and compares bytes. `--write` regenerates them.
    39	- `sundai_hotspot/test_references.py` runs the same check.
    40	- The build runs the open router (a MILP on HiGHS, a real optimizer) but never a thermal solver.
    41	- Every route goes through one guarded boundary, `_routed_mm` in `sundai_hotspot/tap_references.py`. It checks SciPy against its pin (1.17.0, `requirements.txt`) before the optimizer runs, so a mismatched SciPy is refused with zero optimizer calls.
    42	- Only SciPy is pinned. The HiGHS version that SciPy reports (1.8.0) is recorded with the routed numbers; it is not pinned, and it does not admit any other binary or host.
    43	
    44	## Frozen sections and identities
    45	
    46	**The `raw` and `snapped` sections stay exactly as reviewed at `063f6593`.** SLAB-049 (PR #56) pins the sha256 of the canonical JSON of each `raw` section, and it refuses any change. So nothing added after that review goes inside them. It lives beside them, in `raw_annotations` and `snapped_annotations`: the content hash, the role, the continuous-rules result and the uncertainty statement. Each annotation block also records the section's own hash (`section_sha256`).
    47	
    48	| Reference | `raw` section sha256 (SLAB-049's pin) | `snapped` section sha256 |
    49	|---|---|---|
    50	| Ascend 910 | `15c77bbeecba13a7adece9a2603329d58f33a7b4301025826c1b3c1951547a3c` | `2ae6185ca8091bcad7cc6c3b2287c1874ab94cb4e9a539c4d0b483fd16600a10` |
    51	| CPU-DRAM | `6eba70b6307198fef85dbee0ec98055077b55e0fdae5bebb7ffe620556a457a7` | `9bf9cf5cbb12ed9e8702e280bb2eb5632dd5a8b079a22a417b27a729291ac31c` |
    52	
    53	Each layout also has a content hash, `identity.content_sha256` (in `raw_annotations`, `snapped_annotations`, and the 0.5 mm manifests). That is the sha256 of canonical JSON, built by `tap_references.layout_identity`, over:
    54	- the frame (45 mm);
    55	- the units: mm, die centres, origin at the interposer's lower-left corner, +x right, +y up;
    56	- the die order: the TAP config's;
    57	- the centres;
    58	- the rotations, where true means turned 90 degrees from the config's (width, height);
    59	- the footprints.
    60	
    61	| Layout | content_sha256 | design hash |
    62	|---|---|---|
    63	| Ascend raw | `0046e17b3e33feef14e570eb6a2026e17c3eea5c232160a052be62c2ae8e470e` | `b9bfcd23...` |
    64	| Ascend 0.5 mm | `e0c7ce9eb641ee6aea7d2015e5bc0fc5e3f38f1759c2c2252f14ad5104af022a` | `224f2ea0...` |
    65	| Ascend 1 mm | `45b0f7e05b82a5eedad1679d751f5684e98ef35c936db54aeea9b475ae397703` | `a2b5cac2...` |
    66	| CPU-DRAM raw | `6e541158ef9cec4e9e8eed469325490d7902e5175e7a41925bad72f900a5fce9` | `93ee854b...` |
    67	| CPU-DRAM 0.5 mm | `ecfca7f46fd422f6c35ee35cf7c9ffc97f2a0a627907a69f03891910bc248be9` | `0f806acb...` |
    68	| CPU-DRAM 1 mm | `9fee13e0b37d830e3ae1e749cb0bc0d84679de1a6dea03e41ad2e5d8aeea6bbb` | `c1d85d5d...` |
    69	
    70	The tests pin every hash in both tables (`sundai_hotspot/test_references.py`: `REVIEWED_SECTION_SHA256`, `LAYOUT_CONTENT_SHA256`, `PRIOR_DESIGN_HASHES`). The content hashes are recomputed from each layout's own centres, so moving any die fails them. Data mutations check both failures: a moved raw die, and an annotation written into the raw section.
    71	
    72	**Validating raw geometry.** Use `TapGeometry.continuous_centers_for` (`sundai_hotspot/tap_oracle.py:326`; the oracle delegate is at `:927`).
    73	- It applies every rule except the search lattice: frame, orientation catalog, margin with halo, halo non-overlap and the 0.1 mm minimum spacing.
    74	- Both raw layouts pass it. Only the 0.5 mm search lattice in `centers_for` (`:322`) refuses them.
    75	- A `HotSpotOracle` call still goes through `centers_for`. A gate-zero evaluation of raw geometry therefore needs its own path that validates with `continuous_centers_for`.
    76	
    77	## Source and extraction
    78	
    79	- **Paper:** Y. Ma et al., "TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems", DATE 2021, http://people.bu.edu/joshi/files/Ma_TAP-2.5D-DATE2021.pdf.
    80	  - PDF sha256 `b209f51aec188e2bcdbf6f4acc3723fb30fbc5c14cca7e70141d478edadec234`.
    81	  - Fig. 5 and Fig. 6 are on page 6 (index 5).
    82	- **Decoder:** sha256 `8bf98272d62c77119c334aec91d0021dc222c3b1ba56a6a1d4d620e1f3a69361`.
    83	  - Its docstring now states exactly what it does. Rerunning it changed only the recorded decoder hash in its output; every extracted value is identical.
    84	- **What it does.** It takes the stroked line segments of each figure and groups them into closed rectangles. It reads each panel's frame and scale from its four frame strips, and takes the die-sized rectangles in drawing order as TAP dies 0..n-1. Each outline is checked against that die's catalog size. Fig. 6 (b) and (c) are drawn rotated 90 degrees clockwise; the strips and line order show it, and they are rotated back.
    85	- **Assumption.** The drawing order and frame strips are those of TAP's `util/grid_thermal_map.pl` over its generated chip-layer floorplan. The checks are consistent with that but do not prove it.
    86	- **Die identity.** For CPU-DRAM the netlist cross-checks it: each DRAM sits beside the CPU it links to, and the CPU ring has no diagonal.
    87	- **Per-coordinate uncertainty** (`raw.center_uncertainty_mm`, 0.0007 to 0.0022 mm) is an **empirical estimate under stated assumptions** (`raw_annotations.uncertainty_statement`; the frozen `raw.uncertainty_rule` keeps its reviewed wording). The norm is per coordinate (L∞). It is the sum of:
    88	  - the extraction error measured on TAP's own panels, which must sit on its 1 mm grid; all 36 of their centres land within 0.0005 mm of it;
    89	  - the coordinate times the spread of the panel's three scale estimates;
    90	  - half the storage step.
    91	
    92	  It covers reading the figure only. It is **not a figure-to-silicon error bound**. Whether the figure matches the authors' simulated layout cannot be measured from the figure.
    93	
    94	## Round trip (room #56739, item (b)2)
    95	
    96	The criterion: our evaluator and router on the **raw** reference land within the paper's own numbers, with temperature within 1.0 K and routed wire within 2%.
    97	
    98	**Routed wire.** `sundai_hotspot/tap_router.py` ports TAP-2.5D's own MILP router (`routing.py`) from CPLEX to HiGHS. It carries an Apache-2.0 change notice, and it is listed in `THIRD_PARTY_NOTICES.md`.
    99	
   100	| Layout | Routed (open router), not paper | Paper | Difference |
   101	|---|---:|---:|---:|
   102	| Ascend 910 original, Fig. 6(a), raw | 16,417.5 mm | 16,426 mm | -0.05% |
   103	| CPU-DRAM original, Fig. 5(a), raw | 67,688.4 mm | 67,686 mm | +0.004% |
   104	
   105	How to read this:
   106	- **It is consistency evidence, not identification.** Routed wire depends only on differences between pin positions, so a common translation of the whole layout leaves it unchanged; the tests check this. Agreement checks the relative geometry, not the absolute coordinates.
   107	- **The routes launch no thermal solver.** They do run a real optimizer, under whatever per-job accounting applies.
   108	- **The router is not wired into the oracle or the search.** The oracle's `W` (`wirelength_mm`) and the `wire_proxy_mm` in these files remain a centre-distance proxy, and any claim using them must say "proxy".
   109	
   110	**Temperature: planned, not run.** The prerequisites are in `round_trip.temperature`:
   111	- a named warden grant;
   112	- the paper's statistic;
   113	- the paper's package physics (SLAB-049);
   114	- an evaluation path that validates raw centres with `continuous_centers_for`.
   115	
   116	**Three temperature statistics, kept separate and never substituted for one another:**
   117	1. TAP's selector: `run_hotspot()` takes `max(stdout.split()[3::2])` over the unit temperatures HotSpot prints, with `-grid_map_mode center`. It is not, by construction, limited to the chip layer. Reproducing it needs the literal selector or a reviewed emulation.
   118	2. The native temperatures of the real chiplet units (`Chiplet_i`).
   119	3. The active (chip) layer grid peak: our J, with `-grid_map_mode max`.
   120	
   121	**Validation points.** These are other published panels, routed as decoded. They are not tuning targets.
   122	
   123	| Layout | Paper J (unevaluated) | Routed (open router) | Paper | Difference |
   124	|---|---:|---:|---:|---:|
   125	| Ascend Compact-2.5D, Fig. 6(b) | 75.13 C | 23,805.5 mm | 23,794 mm | +0.05% |
   126	| Ascend TAP-2.5D, Fig. 6(c) | 75.47 C | 16,613.5 mm | 16,597 mm | +0.10% |
   127	| CPU-DRAM Compact-2.5D, Fig. 5(b) | 113.54 C | 100,832.1 mm | 100,864 mm | -0.03% |
   128	| CPU-DRAM TAP-2.5D non-pipelined, Fig. 5(c) | 94.89 C | 216,109.7 mm | 216,064 mm | +0.02% |
   129	| CPU-DRAM TAP-2.5D gas-station, Fig. 5(d) | 93.89 C | 139,036.1 mm | 138,956 mm | +0.06% |
   130	
   131	All seven totals are within 0.1% of the paper. **These five panels are reused:** they also feed the extraction-precision estimate above, so the two checks are not independent. Their temperatures are the paper's own values and stay unevaluated.
   132	
   133	## The 0.5 mm engineering variants
   134	
   135	**Rule:** each centre coordinate c becomes `0.5 * floor(c / 0.5 + 0.5)`, the nearest multiple of 0.5 mm. An **exact tie rounds up, toward +infinity**. Rotations are kept, and there are **no repair moves**: both variants pass the fixture's own gate as rounded.
   136	
   137	Per root's decision (ScienceClaw #56857, #56858), the choice follows legality and the smaller displacement, was made before any new thermal outcome, and was **not** chosen to fit the published routed wire.
   138	
   139	| Reference | 0.5 mm centres | Max displacement from raw: per coordinate (L∞) | Euclidean, per die | Routed (open router), not paper |
   140	|---|---|---:|---:|---:|
   141	| Ascend 910 | V (17, 22.5), N (38.5, 22.5), HBM (7.5, 11), (21.5, 11), (7.5, 34), (21.5, 34) | 0.1952 mm | 0.232117 mm | 16,672.1 mm (+1.50%) |
   142	| CPU-DRAM | CPU (18, 17.5), (27, 17.5), (27, 27.5), (18, 27.5); DRAM (8.5, 17.5), (36.5, 17.5), (36.5, 27.5), (8.5, 27.5) | 0.0751 mm | 0.090389 mm | 68,867.3 mm (+1.75%) |
   143	
   144	These maxima match root's independent figures (ScienceClaw #56857). The tests recompute and pin them.
   145	
   146	Both committed 1 mm variants put the raw layout **outside** a ±0.5 mm per-coordinate box:
   147	- Ascend by 1.1246 mm (Euclidean 1.173435 mm);
   148	- CPU-DRAM by 0.5496 mm (Euclidean 0.694694 mm). Its alternative 1 mm snaps, with rows at 18/28, reach 0.5503 mm. All 16 minimal 1 mm snaps lie between 0.5496 and 0.5503 mm.
   149	
   150	**Limits:**
   151	- The raw layout lies inside each 0.5 mm variant's ±0.5 mm per-coordinate box. That does not make it a sampled point of the envelope's one-axis stencil.
   152	- Finite sensitivity probes do not prove a uniform reconstruction bound.
   153	
   154	## The 1 mm snapped variants (kept unchanged)
   155	
   156	The rule (`snap_to_grid`) rounds to the nearest 1 mm node, then makes the fewest 1 mm moves that make the layout legal. Ties go to the layout closest to the raw centres, then the lexicographically smallest. Every adjustment is recorded with exactly what dropping it would break.
   157	- **Ascend:** Nimbus +1 x, and HBMs 4 and 5 +1 y. Plain rounding leaves a 0.05 mm compute-Nimbus gap and a 0.125 mm overlap.
   158	- **CPU-DRAM:** dies 0, 1, 4 and 5 move -1 y. The direction is a tie-break below the extraction precision.
   159	
   160	Routed wire is +10.5% and -4.3% against the paper, so these are not wire references.
   161	
   162	## What the paper reports, and what is not comparable
   163	
   164	Paper settings: 45 mm interposer, 1 mm placement grid, 64 x 64 thermal grid, 45 C ambient, HotSpot 6.0. Original layouts:
   165	- Ascend 910: 75.48 C, 16,426 mm routed.
   166	- CPU-DRAM: 115.94 C, 67,686 mm routed.
   167	
   168	Not comparable as they stand:
   169	- the temperature statistic (three statistics, above);
   170	- the simulator, HotSpot 6.0 vs our HotSpot 7.
   171	
   172	Model omissions:
   173	- The shipped Ascend 910 carries two unpowered silicon dummy dies (about 110 mm² each, Hot Chips 31: "added to ensure mechanical uniformity") beside Nimbus. TAP's model, its Fig. 6(a) and this reconstruction all omit them, so their lateral heat path is not modelled.
   174	- TAP's die sizes and its 256/14/4 x 20 W power split are modelling assumptions.
   175	
   176	## 45 mm fixtures
   177	
   178	`sundai_tap/configs/sys_ascend910_45mm.cfg` and `sys_micro150_45mm.cfg` sit next to the 50 mm files. Each carries a change notice. The dies, powers, netlist and TAP's 1 mm granularity are unchanged. What differs:
   179	- `intp_size = 45`. The worker builds the package from it, so the spreader is 90 mm and the sink 180 mm.
   180	- A `[sentilab]` section that only `sundai_hotspot/tap_oracle.py` reads:
   181	  - `center_lattice_mm = 0.5`;
   182	  - `min_die_gap_mm = 0.1`, TAP-2.5D Eqn. (10);
   183	  - `rotation = per_die_90`.
   184	
   185	The 50 mm fixtures are unchanged: same config bytes, same physics contract as the frozen mesh layouts, catalog orientation only, a 1 mm lattice and no extra spacing rule. Their problem hashes change as after any oracle edit; design hashes do not.
   186	
   187	## Rotation
   188	
   189	A turn is 90 degrees about the die centre: the die's footprint swaps width and height (`Design.apply("rotate", {"chiplet": id})`). Every consumer reads the turned die:
   190	- the oracle's legality and centres;
   191	- the worker request, where TAP's own `rotate()` runs before the floorplan is written;
   192	- the router;
   193	- the wire proxy;
   194	- the Lab/Package view rectangles (`sentilab_core.conductor.view_geometry`).
   195	
   196	Each fixture declares its orientation catalog. A square die has one orientation. The search operator `rotate` is opt-in, so the frozen lanes keep their three operators.
   197	
   198	## Open uncertainties
   199	
   200	- **Displacement norms.** Every displacement above names its norm. Per coordinate (L∞) and Euclidean differ.
   201	- **The 0.054 mm review figure.** It compared an earlier extraction (`page.rects`) with warden's then-rounded list, not with this decoder. This decoder selects four-line floorplan bodies instead, and its centres differ from that earlier extraction by up to 0.1016 mm (reconciliation in astra's review, PR #57 comment 6545653066). Its own self-check against TAP's grid is 0.0005 mm. These are different primitive selections and comparison targets, and **none of them is a figure-to-silicon error bound**.
   202	- **Figure fidelity.** The extraction assumes the figure was drawn from TAP's floorplan (the assumption under "Source and extraction"); the checks are consistent with that but do not prove it. Under that assumption, anything the authors changed between their simulation and the drawing cannot be seen. Fig. 6(b)/(c) being rotated for display shows the figures were edited after generation. The routed-wire agreement is consistent with unedited relative positions; it says nothing about absolute position.
