# Heat path from junction to ambient: a resistance stack

> Representative reconstruction from public sources. This is not any manufacturer's design, and it is not silicon-validated. The resistances are one-dimensional hand estimates built from cited inputs. They are not simulation results, and nothing here is a temperature from the SentiLab repo (those are withdrawn). Fact ids such as `[pkg-051]` resolve to `evidence/<lane>/FACTS.jsonl`. "Derived" marks arithmetic on cited inputs.

## 0. Where the heat starts

- **Heat is generated in the thin front-end-of-line (FEOL) transistor layer** [thm-043].
- **In a flip-chip die that layer faces down**, toward the micro-bumps and interposer [pkg-055, pkg-026]. So the "junction" sits at the **bottom** of the compute die.
- **Top-side heat must cross the whole die thickness** (~710 µm of bulk silicon plus a ~10 µm BEOL in a planarized 2.5D package [thm-029, thm-032]) before it reaches TIM1.
- **Most of the heat goes up.** About 95% of a chip's heat leaves through the top of the package [thm-036]. The rest goes down through bumps, interposer, substrate and board: the secondary path [thm-012].
- **The industry splits junction-to-coolant resistance into these elements:** cold plate, TIM2, lid and TIM1, lateral heat crosstalk, and the die stack [thm-040].

## 1. Primary (top-side) path: lidded, liquid-cooled package

The reference die is an 814 mm² reticle-class compute die (NVIDIA GH100 area [prd-009]). The per-die resistance is R = R″/A, assuming one-dimensional flow over the die area.

| # | Layer (parts.json id) | Thickness | k (W/mK) | R″ (K·mm²/W) | R for 814 mm² (K/W) | Basis |
|---|---|---|---|---|---|---|
| 1 | Active layer + BEOL (`compute_die_active_layer`) | ~10 µm BEOL | n/a | not in series upward | — | Heat source location [thm-043]; the BEOL lies **below** the junction, on the secondary path |
| 2 | Bulk silicon (`compute_die_bulk_si`) | 710 µm [thm-029] | 150 at 27 °C → 112 at 100 °C (k = 150·(T/300)^-4/3, derived [thm-017]); 117.5-130 cited [thm-016, thm-019] | **4.7-6.3** derived; **5** measured in TSMC's benchmark [pkg-051] | 0.0058-0.0078 | k falls as the die heats; doped Si runs ~80% of pure [thm-018] |
| 3 | TIM1 (`tim1`) | 20-50 µm BLT [thm-021] | PCM 8.5 [thm-022]; indium 86 [thm-020]; "conventional high-performance" ~20 [thm-028] | **1.5-4** measured (fusion-bonded oxide 1.5, liquid metal 4) [pkg-051]; PCM 4 (0.04 °C·cm²/W) [thm-021] | 0.0018-0.0049 | TSMC's values come from integrated-cooler test structures, not production lids |
| 4 | Lid / IHS (`lid`) | not sourced (HotSpot default 1 mm) | Cu 389 [thm-013] | 2.6 per mm of Cu (1-D, derived) | ~0.003 per mm (1-D over the die area; real spreading lowers it) | Copper heat spreader on high-performance FCBGA [pkg-025]; TSMC "new TIM (lid package)" for CoWoS-S [pkg-012] |
| 5 | TIM2 (`tim2`) | 20-50 µm (PCM class) [thm-021] | 8.5 (PCM) [thm-022] | ~4 (PCM class) | smaller than TIM1 because it covers the larger lid area | Can dominate if its bondline is thick [thm-046]; large dies warp, which varies bondlines [thm-047] |
| 6 | Cold plate + coolant (`cold_plate`, `coolant`) | — | Cu plate [thm-042]; water or glycol [thm-044] | — | **~0.039** case-to-fluid at 1,000 W | Vendor test on an Intel thermal test vehicle with dielectric coolant [thm-039]: a magnitude, not an AI-package value |
| | **Sum (derived)** | | | | **≈ 0.050-0.056 K/W** | Package internal (2-5) ≈ 0.011-0.017; cooler ≈ 0.039 |

How to read it:

- **At kW scale the cooler is the largest single term,** roughly 70-78% of the 1-D total (derived).
- **Die silicon plus TIM1 is the next block,** about 15-25% (derived). That is the part the package designer controls, and it is where **hot spots** form, because R″ is area-specific: a 1 mm² region at 5× the average power density sees 5× the local rise through layers 2-3.
- Liquid cooling at the 1 kW rack scale is now standard (GB200 NVL72 is liquid-cooled [prd-017]). MI325X is rated at 1,000 W and H100 SXM5 at 700 W [prd-023, prd-012].

### Lidless variant

- Remove the lid and TIM2. The cold plate presses on the bare dies through a single TIM ("TIM1.5").
- A stiffener ring keeps the package flat [pkg-039, pkg-040, pkg-024].
- An exposed die has **one** interface instead of two [thm-041].
- 1-D sum ≈ 0.006-0.008 + 0.002-0.005 + ~0.039 ≈ **0.047-0.052 K/W** (derived).
- The trade-off is flatness. Lidless packages suffer increasing flatness problems as they grow, and every die has to sit at the same height (planarized) [pkg-040, thm-032].

## 2. Secondary (bottom-side) path

| Layer | Thickness | k (W/mK) | R″ (K·mm²/W, derived) | Basis |
|---|---|---|---|---|
| BEOL under the junction | ~10 µm | low-k dielectric, not sourced | — | [thm-029] |
| Micro-bumps + underfill | ~35 µm | 14-95 effective (parallel estimate, derived); underfill 0.6 [thm-023] | 0.4-2.5 | bump geometry [hbm-033, pkg-021] |
| Silicon interposer | 100 µm | 117-150 | 0.67-0.85 | [pkg-021, thm-016, thm-017] |
| C4 bumps + underfill | 60-100 µm | ~14 effective (derived) | 4-7 | [pkg-028, thm-025, thm-023] |
| Substrate core + build-up | core 400-1,600 µm + 2×(9-10) layers | dielectric 0.8 (core), 0.35 (prepreg) [thm-015, thm-014] | 500-2,000 through the core dielectric alone; Cu vias and planes lower this (not quantified here) | [pkg-032, pkg-031] |
| BGA + board | 0.3-0.6 mm stand-off [pkg-049, pkg-050] | SAC305 58 [thm-025] | — | A published FEM model lumps the PCB side as **20 K/W** [thm-035] |

The bottom path is roughly two orders of magnitude more resistive than the top path, which fits the ~5% share [thm-036]. It matters for:

- **power** (the same path carries the 1,000 A core rail [pkg-043]);
- **HBM**: its base die sits directly on the interposer.

It hardly matters for compute-die cooling. **Our model disables this path entirely**: the substrate bottom is adiabatic (`sundai_tap/util/hotspot.config:48`; see `our_model_mapping.md`).

## 3. HBM path and logic-HBM coupling

**Vertical, inside the stack**

- Heat from the **base die** (PHY, TSV landing, logic) and from each DRAM die has to climb through every bond layer above it. Each bond layer is micro-bumps plus MR-MUF or TC-NCF gap fill.
- Each interface is ≈ **3.8 K·mm²/W** [thm-031].
- A 12-high stack therefore has ≈ 12 × 3.8 + 501 µm Si / 130 ≈ **49 K·mm²/W**, about **9× the 720 µm logic die** at ≈ 5.5 (derived from [thm-030, thm-031]).
- Over an 11 × 11 mm footprint [hbm-018] that is ≈ **0.4 K/W per stack** (derived): every watt in the base die raises the base-die junction by ~0.4 K over the stack top. This is a per-watt figure, not a temperature prediction.
- In a published FEM model the **base (controller) die is the hottest layer** of the stack [thm-034].
- Vendors fight this resistance with:
  - **thermal dummy bumps** [hbm-024];
  - **larger bumps where heat must escape** [hbm-016];
  - higher-k gap fill. SK hynix argues MR-MUF fits more thermal bumps and conductive filler than TC-NCF [hbm-028, hbm-031] and claims a 10% improvement generation over generation [hbm-012]. Samsung counters with a 7 µm TC-NCF gap [hbm-015].
- Hybrid bonding removes the gap fill altogether, and is the route to 16-high and beyond [hbm-030, hbm-029].

**Lateral, from logic into HBM.** HBM sits very close to the compute die: 0.72 mm on Ascend 910, with 2 mm between HBMs [prd-004]. Heat crosses three paths:

1. **the lid or heat spreader above** (Cu, mm-thick, k ≈ 389). One study finds this is where **most inter-chiplet heat transfer** happens, rather than the interposer. That limits what thermal floorplanning alone can achieve [thm-026]. This bears directly on SentiLab's placement premise.
2. **the silicon interposer below** (100 µm, k ≈ 120). Silicon couples more than glass [thm-048].
3. **the mold between dies** (k ≈ 1 [thm-024]): weak.

**Why HBM often sets the limit.**

- Logic typically runs to a junction of **105 °C**.
- Early HBM had **85 °C (single refresh) / 95 °C (double refresh)** limits, raised to 95 / 105 °C in later generations [thm-038].
- Micron specifies HBM3E operation from **0 to +105 °C** (T_OPER) [hbm-020].
- Above the trip points, refresh rate doubles, up to 4× nominal [thm-027], costing bandwidth and energy.

## 4. Where hot spots come from

1. **Power-density map inside the compute die.**
   - Average fluxes are moderate: H100 ≤ **86 W/cm²** (700 W TDP over 814 mm², an upper bound because the TDP includes HBM; derived from [prd-012, prd-009]). TAP's Ascend 910 compute die is **56 W/cm²** (256 W over 14.5 × 31.4 mm, derived from [thm-007]). A published 1.5 kW scenario assumes **225 W/cm²** [thm-033].
   - Power is not uniform. It concentrates in compute arrays (tensor and matrix units), less so in SRAM. The HBM and die-to-die PHY strips sit on the die edges facing their partners [hbm-025, prd-015].
   - **No public power map is captured in this pack, so peak-to-average ratios are not quantified here.**
   - HotSpot itself under-estimates lateral spreading: it over-predicts high-power areas and under-predicts quiet ones against IBM POWER7+ data [thm-010].
2. **Layout.** Packing high-power chiplets tightly to save wire is thermally inefficient. That is the premise of TAP-2.5D and of SentiLab [thm-045]. Spacing helps mostly through the interposer and mold paths. If the spreader dominates coupling [thm-026], the gain is smaller than a 2-D intuition suggests.
3. **Vertical stack-ups with high R″.** The HBM stack (≈ 9× logic, derived) and any 3D-stacked compute (e.g. MI300's XCDs on IODs [prd-019, prd-020]) trap heat in their lower dies.
4. **Interface quality.** TIM bondline and voids [thm-046, thm-047], and lid or cold-plate flatness on large packages [pkg-040].

## 5. The same path in our model (structure only)

Our model's stack, from `our_model_mapping.md`:

| Step | Layer | R″ (K·mm²/W) |
|---|---|---|
| 1 | chip, 150 µm | 1.5 |
| 2 | TIM, 20 µm | 5.0 |
| 3 | spreader, 1 mm Cu, 2 × interposer edge | 2.5 (1-D) |
| 4 | sink, 6.9 mm Cu | 17.3 (1-D) |
| 5 | lumped convection, h ≈ 2,778 W/m²K on the sink base (derived) | 360 at sink area |

- The bottom is adiabatic.
- HBM is a 150 µm silicon block. The model therefore has **no ~9× HBM vertical penalty, a ~3.7× lighter die, no TIM2, and a spreader larger than any real lid**.
- These are model-structure facts. They say nothing about the size of any temperature effect.
