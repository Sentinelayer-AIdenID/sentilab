# Our thermal model vs the real package: layer mapping

This file maps the parts in `parts.json` to the layer stack that SentiLab's thermal oracle actually builds. It says what each model layer stands for, what the model simplifies or leaves out, and where in the code each value lives.

- **Repo:** `H:/sentilab`, read at `origin/main` = `46791be360555d0e24b4ad5f906abafb71f07118`, using `git show` and `git grep` only (nothing checked out or modified). Line numbers refer to that commit. Numbered copies of every file cited here are in `evidence/repo/`.
- **No temperatures.** This file quotes no temperature from the repo. Our vendored HotSpot v7.0 detailed-3D build has the convection-split error, and every kelvin value from it is withdrawn (`web/public/temperature-label.mjs:21-23` lists `HotSpot-7:f18831e…` as WITHDRAWN; `:28` shows the ACCEPTED list is empty). The numbers below are model inputs (thicknesses, conductivities, sizes) and resistances derived from them. None of them is a result.
- **Real-world values** cite fact ids in `evidence/<lane>/FACTS.jsonl` (for example `[pkg-021]`). "Derived" means arithmetic on cited inputs; the inputs are given each time.

## 1. Which code builds the model

| Step | What happens | Where |
|---|---|---|
| Fixture | Picks a die set: `ascend910` (default, 50 mm interposer), `micro150`, plus 45 mm variants of both | `sundai_hotspot/tap_oracle.py:25-33` |
| Generator | The worker calls TAP-2.5D's `PassiveInterposer.gen_flp()` / `gen_ptrace()` | `sundai_hotspot/tap_oracle_worker.py:176-203` |
| Layer file | TAP writes `samplelayers.lcf` with 6 layers (L0-L5) | `sundai_tap/passive_interposer.py:135-149` |
| Package | TAP copies `util/hotspot.config`, then rescales spreader, sink and convection | `sundai_tap/passive_interposer.py:151-165`, `sundai_tap/util/hotspot.config` |
| Solver | HotSpot (vendored v7.0, upstream `f18831e`) runs in grid mode with `-detailed_3D on -grid_layer_file … -grid_map_mode max` | `sundai_hotspot/tap_oracle_worker.py:356-369`; `sundai_hotspot/UPSTREAM_COMMIT:1` |
| Appended layers | HotSpot appends a **spreader** and a **sink** above the LCF layers. Secondary-path layers (PCB, solder, substrate) are only added when `model_secondary` is set, and it is 0 here | `sundai_hotspot/temperature_grid.h:46-54`; `temperature_grid.c:523-559, 561-608`; `sundai_tap/util/hotspot.config:48` |
| TAP upstream | `bu-icsg/TAP-2.5D` at `3a3f4e5…`. TAP's paper used HotSpot 6.0 [thm-002, thm-001] | `sundai_tap/UPSTREAM_COMMIT:1`; `sundai_tap/README.md:6` |

PR #56 (SLAB-049: the HotSpot 6.0 evaluator and "gate zero") is **not** on `origin/main` at this commit. The vertical-coupling code below is still the v7.0 form.

## 2. The model stack, bottom to top, and what each layer stands for

The material strings are at `sundai_tap/passive_interposer.py:22-24`: underfill = (2.32e6 J/m³K, 0.625 m·K/W, so k = 1.6 W/mK); copper = (3.4944e6, 0.0025, so k = 400); silicon = (1.75e6, 0.01, so k = 100). The bump and TSV layers use an area-weighted parallel mix (`:37-45`), k_eff = (k_Cu + A·k_fill)/(1 + A), where A = (cell edge / bump diameter)² − 1. That formula treats each bump as a **square** of side = diameter. A round bump has π/4 of that area, so the copper fraction is overstated by 4/π ≈ 1.27× (derived).

| # | Model layer (LCF) | Where | Thickness | k as coded (W/mK) | Lateral content | Real parts it stands for (parts.json ids) | Real-world reference values | Main simplifications |
|---|---|---|---|---|---|---|---|---|
| L0 | "substrate" | `passive_interposer.py:50-56, 144` | 200 µm | 0.30 (resistivity 3.33) | one block, same size as the interposer (45 or 50 mm) | `package_substrate` (core plus both build-ups), `bga_balls`, `system_board` (all lumped) | core 400-1,600 µm [pkg-032]; build-up 9-10 layers per side [pkg-031]; core k 0.8, prepreg 0.35, solder mask 0.24 [thm-015, thm-014, thm-013]; body 90-130 mm [pkg-033] | Far thinner than a real substrate, and it has the interposer's footprint rather than a 55-130 mm body. Its bottom face is **adiabatic**: no heat leaves through the BGA or PCB (`hotspot.config:48`). In reality about 5% leaves that way [thm-036]. |
| L1 | "Epoxy SiO2 underfill with C4 copper pillar" | `:31-32, 37, 40, 59-65, 145` | 70 µm | 70.8 effective (250 µm "Cu" bumps in a 600 µm cell = 17.4% Cu, rest underfill at k 1.6) | one block, interposer-sized | `c4_bumps` + `c4_underfill` | C4 pitch 130-210 µm [pkg-053, pkg-016, pkg-021, pkg-018]; bump 80-125 µm diameter, 60-100 µm tall, Cu pillar ~40 µm [pkg-028, pkg-029]; SAC305 k 58 [thm-025]; underfill k 0.6 [thm-023] | The bumps are treated as pure copper on a coarse 600 µm cell. A derived parallel estimate for real solder bumps is ~14 W/mK (100 µm bumps at 180 µm pitch). Because L0's bottom is adiabatic, this layer barely matters thermally. |
| L2 | "silicon interposer" | `:33-34, 38, 41, 68-74, 146` | 110 µm | 112 effective (10 µm Cu TSV on a 50 µm cell = 4% Cu in Si at k 100) | one block, 45 × 45 or 50 × 50 mm | `interposer_silicon`, `interposer_tsv` (homogenised) | thickness 100 µm [pkg-021, thm-029]; TSV >10 µm diameter at 210 µm pitch (Xilinx SSIT) [pkg-018]; size up to ~2,700 mm² CoWoS-S [pkg-001]; TAP paper 45 × 45 mm [thm-006] | No BEOL/RDL wiring layer (`interposer_beol_rdl`), no eDTC, no organic or bridge variants. Si k is held at 100 with no temperature dependence. |
| L3 | "Underfill with ubump" | `:35-36, 39, 42, 90-93, 105-108, 115, 147` | 10 µm | 124.6 effective (25 µm bump on a 45 µm cell = 30.9% Cu) under every die and its halo; 1.6 (underfill) in the gaps | Chiplet_i and its four halo strips use the bump mix; the interposer edge strips use the bump mix; whitespace is underfill (`util/fill_space.py:19, 164`) | `microbumps` + `microbump_underfill` | pitch 36-55 µm: 45 µm [pkg-021], 55 µm on HBM [hbm-023]; ~25 µm diameter [hbm-023, hbm-026]; ~35 µm tall [hbm-033]; HBM bond interfaces measure ~3.8 K·mm²/W each [thm-031] | The layer is nearly transparent: 10 µm / 124.6 = 0.08 K·mm²/W, against 3.8 K·mm²/W for a real HBM bond interface (not the same joint, but the closest cited value). The code assumes centre bump density equals edge density (`:114`, which says so). |
| L4 | "Chip layer" (the only powered layer) | `:94-97, 109-112, 116, 122, 148`; power `:182-195` | 150 µm | 100 (silicon) for dies and halos; 1.6 (underfill) in the gaps; 124.6 on the interposer edge strips | Chiplet_i silicon, halo strips as silicon, whitespace as underfill, edge strips as the bump mix | `compute_die`, `io_die`, `hbm_stack` (every die is a flat 150 µm silicon block), `mold_compound` (gaps) | Logic die 710 µm Si + 10 µm BEOL, planarized with 720 µm HBM [thm-029, thm-032, hbm-018]; HBM is 1 base + 8-12 DRAM dies with bond layers, ~9× more vertically resistive than a logic die (derived from [thm-031, thm-030]); mold k ~0.96 [thm-024] | One thin silicon layer stands in for both logic dies and HBM stacks. Power is uniform per die (no intra-die map, no PHY hot spots). The Ascend 910's two dummy dies are missing (`docs/sentilab/references/README.md:172-174`). The gaps get underfill (k 1.6), not mold (k ~1). The edge strips carry a copper-rich mix in the chip layer, a geometric artefact of TAP's edge units. |
| L5 | "TIM" | `:126-132, 149` | 20 µm | 4.0 | one block over the whole interposer, gaps included | `tim1` | TIM1 1.5-4 K·mm²/W measured (TSMC liquid-metal / oxide) [pkg-051]; PCM 0.04 °C·cm²/W = 4 K·mm²/W at 20-50 µm BLT [thm-021]; indium 86 W/mK [thm-020] | The model's 5 K·mm²/W (20 µm / 4) is in the measured TIM1 range. The TIM is continuous across the gaps, whereas a real TIM sits on die tops and mold. |
| +1 | HotSpot **spreader** | `hotspot.config:29-35`; resized at `passive_interposer.py:154, 160-161`; appended at `temperature_grid.c:529-541` | 1 mm | 400 | square, 2 × interposer edge (90 mm for 45 mm, 100 mm for 50 mm) [thm-002] | `lid` | Cu k 389 [thm-013]; lid thickness not sourced; real lids cover the die area, not 2× the interposer | Wider than any real lid. With no TIM2 below the sink, the lid-to-cooler interface is missing (HotSpot cannot model TIM2 [thm-009]). One study finds the spreader is the main logic-to-HBM coupling path [thm-026], so its size and k matter for placement studies. |
| +2 | HotSpot **sink** + lumped convection | `hotspot.config:15-25`; resized at `passive_interposer.py:155-156, 158-163`; convection added to the sink's rz at `temperature_grid.c:1055-1057` | 6.9 mm | 400 | square, 2 × spreader (180 mm / 200 mm) | `heat_sink` (air) or `cold_plate` + `coolant` | TAP: "a realistic air-forced heatsink", with convection scaled to keep h constant [thm-002, thm-003]; 1 kW-class parts are liquid cooled (GB200 NVL72 [prd-017]); case-to-fluid ~0.039 K/W at 1000 W in a vendor test [thm-039] | r_convec = 0.1·0.06²/s_sink² K/W gives 0.0111 K/W (45 mm) or 0.0090 K/W (50 mm). Either way that is a constant h_eff = 1/(0.1·0.06²) ≈ 2,778 W/m²K on the sink base (derived). The ambient boundary is an input of 318.15 K (`hotspot.config:78`; the paper's 45 °C convention [thm-002]). |
| — | not modelled | — | — | — | — | `bga_balls`, `system_board`, `vrm_*`, `board_bypass_caps`, `land_side_caps`, `die_side_caps`, `stiffener_ring`, `interposer_edtc`, `interposer_beol_rdl`, `rdl_interposer`, `lsi_bridge`, `hbm_base_die`, `hbm_bond_layer`, `hbm_dram_core_die`, `hbm_top_die`, `hbm_tsv`, `hbm_side_mold`, `dummy_die`, `tim2`, `hbm_phy`, `d2d_phy` | see `parts.json` | Show these in the 3D view as **anatomy only (not in the thermal model)**. |

### Area-specific resistance of each model layer (inputs only; derived as t/k)

| Model layer | t | k | t/k (K·mm²/W) | Real-world comparison (K·mm²/W) |
|---|---|---|---|---|
| L0 substrate | 200 µm | 0.30 | 666 | (bottom adiabatic, so this does not sit in series with the top path) |
| L1 C4 | 70 µm | 70.8 | 0.99 | n/a |
| L2 interposer | 110 µm | 112 | 0.98 | 100 µm Si at 117-150 W/mK: 0.67-0.85 (derived) |
| L3 micro-bump | 10 µm | 124.6 | 0.08 | HBM bond interface 3.8 [thm-031] |
| L4 chip | 150 µm | 100 | 1.5 | bulk Si die: 5 measured [pkg-051]; 720 µm logic at 130 W/mK: 5.5 (derived); HBM stack ~49 (derived) |
| L5 TIM | 20 µm | 4 | 5.0 | TIM1 1.5-4 [pkg-051]; PCM 4 [thm-021] |
| spreader | 1 mm | 400 | 2.5 (1-D) | Cu lid of unknown thickness |
| sink base | 6.9 mm | 400 | 17.3 (1-D) | — |
| convection | — | — | 360 referred to the sink base; 22.5 referred to a 45 × 45 mm interposer area | cold plate ~0.039 K/W case-to-fluid [thm-039] |

Two consequences matter for SentiLab's chiplet-placement physics.

1. **The model's dies are vertically ~3.7× less resistive than real logic dies** (1.5 against 5.5 K·mm²/W), and its HBM stacks are ~30× less resistive than real stacks (1.5 against ~49). Lateral spreading inside a 150 µm die is also weaker than inside a 720 µm die. Real HBM stacks run hot because of their stacked bond layers and their proximity to the logic die. The model cannot show either effect, so it understates HBM sensitivity to placement.
2. **The model's lateral coupling paths differ from a real package.**
   - In the model, the gaps between dies are underfill at k 1.6, there is no mold above the dies, and the TIM is continuous.
   - Coupling through the spreader is present, and one study finds it is the dominant inter-chiplet path [thm-026]. Because the spreader is 2× the interposer, it spreads more than a real lid.
   - Interpret any placement-driven temperature gap with that in mind. This is a qualitative statement about model structure, not a number.

## 3. The fixtures against the real products

| Fixture | Where | Dies in the model | Real product (fact ids) | Differences |
|---|---|---|---|---|
| `ascend910` (50 mm) / `ascend910-45mm` | `sundai_tap/configs/sys_ascend910.cfg:10, 14-17`; `sys_ascend910_45mm.cfg:14, 18-21, 30-38` | 6 dies: compute 14.5 × 31.4 mm at 256 W; I/O 10.5 × 16 mm at 14 W; 4 × HBM 7.75 × 11.87 mm at 20 W (total 350 W) | Huawei Ascend 910 (Hot Chips 31): 8 dies, 456 + 168 + 4 × 96 + 2 × 110 = 1,228 mm²; 350 W; gaps 0.72 mm (compute to HBM row) and 2 mm (between HBMs) [prd-001…005]. TAP Table II sizes and powers [thm-007] | No dummy dies. HBM area is 92 mm² against Huawei's 96 mm² (TAP's 7.75 × 11.87 is the HBM2 KGSD outline [hbm-022]). The power split is TAP's modelling assumption (`references/README.md:174`). Interposer 45 mm comes from the TAP paper [thm-006]; the real interposer size is not in this pack. |
| `micro150` / `micro150-45mm` | `sys_micro150.cfg:10, 14-17`; `sys_micro150_45mm.cfg:14, 18-21` | 8 dies: 4 × 8.25 × 9 mm at 150 W and 4 × 8.75 × 8.75 mm at 20 W (680 W) | TAP's "CPU-DRAM" case study, sourced to an academic design (Kannan et al., MICRO 2015, TAP ref. [14]) | A conceptual system, not a shipping product. Its DRAM is not HBM-sized. |
| `multigpu` (not registered in the oracle) | `sys_multigpu.cfg:10, 14-17` | CPU 12 × 12 mm at 105 W; 2 × GPU 18.2 × 18.2 mm at 295 W; 3 × HBM 7.75 × 11.87 mm at 20 W | TAP's conceptual multi-GPU case | Conceptual. |

## 4. Simplifications, ranked by likely effect on placement conclusions

This ranking is the lane's judgement. It has not been measured.

1. **HBM as a 150 µm, 20 W silicon block.** The real stack is base die + DRAM + bond layers, ~720 µm tall and ~49 K·mm²/W vertically (derived); the base die is the hottest layer [thm-034]; real limits are 85-105 °C against 105 °C for logic [thm-038, hbm-020]. *To add:* a multi-layer HBM in the LCF (L4 split into base / bond / DRAM sub-layers), or at minimum an effective vertical k of ~15 W/mK over 720 µm for HBM footprints (derived).
2. **Die thickness 150 µm instead of a planarized ~720 µm** [thm-029, thm-032]. *To add:* a 720 µm chip layer, which also changes how the interposer and mold couple laterally.
3. **Spreader 2× the interposer and no TIM2.** HotSpot cannot model TIM2 [thm-009]; real lids are die-area-sized; liquid cold plates replace air sinks at 1 kW [prd-017, thm-039]. *To add:* a lid-sized spreader and a TIM2-equivalent layer (an extra LCF layer above L5).
4. **Uniform power per die.** There is no power map (`passive_interposer.py:182-195`). Hot spots inside the compute die and at the HBM PHY edges are invisible, and HotSpot is known to under-spread laterally [thm-010].
5. **Micro-bump layer nearly transparent** (0.08 against ~3.8 K·mm²/W) and the square-bump area overestimate (×1.27).
6. **No secondary path** (`model_secondary 0`, `hotspot.config:48`). The real share is ~5% [thm-036]; enabling it would need the HotSpot 6.0-compatible secondary-path option [thm-012].
7. **Gap material** is underfill k 1.6 rather than mold ~0.96 [thm-024]; dummy dies are omitted; the edge-strip artefact remains.
8. **Constant k** (Si 100 W/mK) with no temperature dependence and leakage feedback off (`hotspot.config:95`). At 85-100 °C the formula gives 112-119 W/mK for pure Si, and doped Si runs ~80% of that [thm-017, thm-018], so k = 100 is a reasonable single value.
9. **Evaluator:** the v7.0 detailed-3D vertical coupling at `temperature_grid.c:104` plus the convection in the sink's rz at `:1055-1057` put half of the convection resistance between spreader and sink. This is the known withdrawn-numbers issue; see SLAB-049 and PR #56 for the HotSpot 6.0 path.

## 5. What the 3D view should mark

- **Shown and simulated:** interposer outline (L2), dies and gaps (L4), TIM (L5), spreader (as "lid"), sink.
- **Shown, simulated in simplified form:** C4 layer (L1), micro-bump layer (L3), substrate (L0, thin and adiabatic).
- **Shown for anatomy only (not in the thermal model):** everything in the "not modelled" row above, especially the HBM internal stack, dummy dies, mold between dies, stiffener, TIM2, BGA, board and VRMs.
- **Never label a model temperature as measured.** Today every evaluator identity is either WITHDRAWN or unvalidated (`web/public/temperature-label.mjs:21-28`).
