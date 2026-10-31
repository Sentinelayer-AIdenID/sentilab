# What a 2.5D AI accelerator package is made of

**Lane 1, anatomy content model for the SentiLab simulation room. Written 2026-10-31.**

> **Status:** representative reconstruction from public sources. This is **not** any manufacturer's CAD and **not** silicon-validated. Every number carries a fact id such as `[hbm-018]`. Each id resolves to a verbatim quote in `evidence/<lane>/FACTS.jsonl`; 176 of 176 quotes were machine-checked against the saved source text. "Derived" marks arithmetic on cited inputs, with the inputs shown. The report quotes no temperature from the SentiLab repo: the old HotSpot 7.0 detailed-3D kelvin values are withdrawn.
>
> Companion files: `parts.json` (machine-readable parts and interconnects), `thermal_path.md` (resistance stack and hot spots), `our_model_mapping.md` (how our HotSpot/TAP model maps to these parts), and `SOURCES.md`.

## 1. The whole thing in one paragraph

A modern AI accelerator puts one or two large **compute dies** and four to eight **HBM memory stacks** side by side on an **interposer**. The interposer is a thin slab of wiring: silicon, organic RDL, or local silicon bridges. Its job is to connect the dies with thousands of very short wires.

- The interposer sits on a large organic **package substrate**, which fans the connections out to **BGA balls** on the board.
- Above the dies, a **thermal interface material** couples them to a **lid** and then to a **cold plate** or heat sink. Lidless designs skip the lid and use a **stiffener ring** instead.
- **Heat** mostly goes up: about 95% of it [thm-036].
- **Power** comes up from voltage regulators on the board, at about 1,000 A and as little as 0.7 V [pkg-043, pkg-041].
- **Signals** run sideways through the interposer: HBM buses 1,024 to 2,048 bits wide [hbm-039, hbm-005], and die-to-die links of up to 10 TB/s [prd-015].

## 2. Exploded stack, top to bottom

Typical values only. See `parts.json` for ranges and sources.

```
 coolant (DI water / glycol)                                 [thm-044]
 COLD PLATE (Cu)  or  AIR HEAT SINK                          [thm-042, thm-039]
 TIM2  (grease / PCM, 20-50 um)          -- lidded only      [thm-021]
 LID / IHS (Cu)                          -- lidded only      [pkg-025, pkg-012]
   (lidless: STIFFENER RING on the substrate instead)        [pkg-039, pkg-024]
 TIM1  (PCM / indium / liquid metal, 20-50 um)               [thm-021, thm-020, pkg-051]
 TOP DIES, all ~720 um tall (planarized), mold in between    [thm-032, hbm-018, pkg-038]
   compute die(s)  |  HBM stacks  |  (I/O die, dummy dies)
     - flip-chip: active layer + BEOL at the BOTTOM          [thm-043, pkg-055]
 MICRO-BUMPS + UNDERFILL (~25 um bumps, 36-55 um pitch)      [hbm-023, pkg-021]
 INTERPOSER: wiring (BEOL/RDL) on top of ~100 um Si with TSVs and eDTC   [pkg-021, pkg-018, pkg-046]
 C4 BUMPS + UNDERFILL (130-210 um pitch)                     [pkg-053, pkg-021, pkg-018]
 PACKAGE SUBSTRATE: build-up / core (0.4-1.6 mm) / build-up  [pkg-032, pkg-031]
 BGA BALLS (0.8-1.0 mm pitch, ~0.5-0.6 mm balls)             [pkg-022, pkg-049, pkg-050]
 SYSTEM BOARD with VRMs and >= 3 mF bypass capacitors        [pkg-044, pkg-043]
```

## 3. Part by part, top down

Each part covers what it is, why it is there, materials and dimensions, thermal conductivity (k), and what it connects to.

### 3.1 Cold plate or heat sink, and coolant

- **What and why:** removes the heat. At the 1 kW class, rack systems use liquid cooling; GB200 NVL72 is liquid-cooled [prd-017].
- **Materials and size:**
  - Copper is the most used cold-plate material [thm-042].
  - DI water and water/glycol are the common coolants [thm-044].
  - One vendor test measured 0.039 K/W from case to fluid at 1,000 W [thm-039]. That was a dielectric coolant on an Intel test vehicle, so treat it as a magnitude only.
  - TAP-2.5D, and therefore our model, uses an air-forced heat sink instead [thm-002].
- **k:** Cu ≈ 389 W/mK [thm-013].
- **Connects to:** TIM2 (lidded) or TIM1/1.5 (lidless): thermal, mechanical.

### 3.2 TIM2

- **What and why:** a grease or phase-change pad between lid and cooler. It fills surface roughness.
- **Material and size:** PCM-class material, 8.5 W/mK, about 0.04 °C·cm²/W, with a bondline of roughly 20-50 µm [thm-022, thm-021]. A thick bondline can make TIM2 the dominant resistance [thm-046].
- **Note:** HotSpot (our solver) cannot model TIM2 directly [thm-009].
- **Connects to:** lid and cold plate (thermal).

### 3.3 Lid (integrated heat spreader), or a stiffener ring

**Lidded designs**

- The lid is a copper heat spreader bonded to the dies through a controlled TIM1 bondline. It is "the lowest possible thermal resistance" format for high-performance ASICs [pkg-025].
- TSMC's CoWoS-S roadmap added a "new TIM (lid package)" [pkg-012].
- k: Cu ≈ 389 W/mK [thm-013].
- **Lid thickness is not sourced in this pack.** The HotSpot default of 1 mm is a model value.
- The lid also spreads heat **sideways between dies**. One study finds most inter-chiplet heat transfer goes through the spreader rather than the interposer [thm-026], which matters for placement studies.

**Lidless designs**

- The heat sink touches the die directly, which gives better thermal performance [pkg-039].
- Large lidless packages get harder to keep flat, so a **stiffener ring** holds them flat [pkg-040, pkg-024].
- An exposed die has one TIM interface instead of two [thm-041].

**Connects to:** TIM1, TIM2, and the substrate (mechanical).

### 3.4 TIM1

- **What and why:** fills the gap between the die backsides and the lid (or cold plate).
- **Materials:**
  - polymer or PCM: 8.5 W/mK [thm-022];
  - indium solder: 86 W/mK [thm-020];
  - liquid metal;
  - "conventional high-performance" TIM: about 20 W/mK [thm-028];
  - a 2011 FPGA lid TIM1: 0.92 W/mK [thm-013].
- **Measured resistance:** 4 °C·mm²/W for liquid metal and 1.5 for fusion-bonded oxide in TSMC's benchmark [pkg-051]. PTM7950 gives 0.04 °C·cm²/W, which is the same 4 K·mm²/W [thm-021].
- **Bondline:** about 20-50 µm [thm-021].
- **Connects to:** every top die (compute, HBM, dummy) and the lid or cold plate.

### 3.5 Top dies

#### 3.5.1 Compute dies (logic chiplets)

- **What:** the tensor and vector engines, SRAM, network-on-chip, memory controllers and PHYs. This is the main heat source.
- **Orientation:** the dies are flip-chip. The active (FEOL) layer, where heat is generated, faces **down** toward the bumps [thm-043, pkg-055, pkg-026].
- **Size:**
  - NVIDIA GH100: 814 mm², TSMC 4N, 80 billion transistors [prd-009].
  - Blackwell: two reticle-limited dies, 208 billion transistors, joined by a 10 TB/s link [prd-014].
  - Huawei Ascend 910 "Vitruvian": 456 mm² [prd-003].
  - TAP-2.5D models that die as 31.4 × 14.5 mm at 256 W [thm-007].
  - One reticle is about 820-830 mm². TSMC gives 3.3× reticle ≈ 2,700 mm² [pkg-001]; Tom's Hardware gives "each roughly 830 square millimeters" [prd-018 source].
- **Thickness:** in a published 2.5D model the logic die is 710 µm of silicon plus a 10 µm BEOL. That makes it the same height as a 720 µm HBM stack, i.e. "planarized" [thm-029, thm-032]. Our model uses 150 µm.
- **Power:**
  - H100 SXM5: 700 W TDP [prd-012].
  - MI300X: 750 W; MI325X: 1,000 W [prd-022, prd-023].
  - Ascend 910: 350 W for the whole package [prd-005].
  - Average die flux on H100 is at most about 86 W/cm² (derived; TDP includes HBM).
- **k (silicon):**
  - 117.5-130 W/mK quoted at room temperature [thm-016, thm-019].
  - The formula k ≈ 150·(T/300)^-4/3 gives about 119 at 85 °C and 112 at 100 °C (derived) [thm-017].
  - Doped silicon is about 80% of pure [thm-018].
- **Connects to:** micro-bumps (power, signal, thermal, mechanical), TIM1 (thermal), the mold and the neighbouring HBM (thermal coupling), and HBM and the partner die through its PHYs (signal).

#### 3.5.2 HBM stacks

**What it is**

- A molded "known-good stacked die": **one base (logic) die** under **4 to 16 thinned DRAM core dies**, joined by TSVs and micro-bumps, with side mold [hbm-047, hbm-003, hbm-007].

**Why it is there**

- Very wide, short memory buses next to the compute die.
- Bandwidth per stack:
  - HBM2: 256 GB/s [hbm-048].
  - HBM3: 819 GB/s at 6.4 Gb/s [hbm-001].
  - HBM3E: above 1.2 TB/s at more than 9.2 Gb/s, up to 1.28 TB/s [hbm-019, hbm-014].
  - HBM4: 2 TB/s at 8 Gb/s over 2,048 bits [hbm-005].
- Capacity is 24-36 GB per stack for HBM3E [hbm-010, hbm-014, hbm-019], and up to 64 GB on HBM3 and HBM4 [hbm-004, hbm-007].

**Dimensions**

| Item | Value | Source |
|---|---|---|
| Footprint, HBM2 (SK hynix) | 7.75 × 11.87 mm | [hbm-022] |
| Footprint, HBM3E (Micron) | 11 × 11 mm | [hbm-018] |
| Footprint, press figure for HBM3/3E/4 | about 10.5 × 12 mm | [hbm-037], low confidence |
| Footprint, Ascend 910 slide | 96 mm² | [prd-003] |
| Stack height, HBM2 through HBM3E | **720 µm** (12-high kept at 8-high height) | [hbm-018, hbm-035, hbm-017] |
| Stack height, HBM4 12/16-high | reported relaxed to 775 µm | [hbm-009], secondary |

**Layers, bottom to top** (thicknesses from a published FEM stack [thm-030, thm-029]; real products vary)

- **Base die: 50 µm.**
  - Holds the PHY, TSV landing and test logic.
  - Its 1,024 I/Os reach the host PHY through the interposer [hbm-025].
  - From HBM4, SK hynix moves the base die to TSMC's logic process [hbm-036].
  - In the model it is the hottest layer of the stack [thm-034].
- **Bond layers: about 7-15 µm.**
  - About 20 µm micro-bumps [hbm-046] plus gap fill.
  - Gap fill is either MR-MUF (liquid molded underfill [hbm-013]) or TC-NCF film, with a 7 µm gap at Samsung [hbm-015].
  - Thermal dummy bumps [hbm-024] and larger "heat" bumps [hbm-016] help heat escape.
  - Each interface is about **3.8 K·mm²/W** [thm-031].
- **DRAM core dies: 35 µm each** in the model. For 12-high stacks, SK hynix made each die 40% thinner [hbm-010].
- **Top DRAM die: 66 µm**, thicker than the others [thm-030].
- **TSVs:** more than 60,000 per 12-high stack [hbm-034]. HBM3E has twice the TSVs of HBM3 [hbm-021]. They cluster in a central TSV area of each die [hbm-024, hbm-033].
- **Bumps to the interposer:**
  - 25 µm diameter at 55 µm pitch in a face-centred-rectangular array [hbm-023].
  - An HBM2-era base die carries 3,990 micro-bumps: 1,728 I/O and 1,030 ground [hbm-032].
  - SK hynix's 2023 paper describes the same field as "96 µm staggered pitch" [hbm-026]. That is a different pitch definition, not reconciled by the sources.

**k and thermal behaviour**

- The silicon is ordinary. The **bond layers dominate**.
- Effective vertical resistance is about 49 K·mm²/W, roughly 9× a 720 µm logic die (derived; see `thermal_path.md`).
- Temperature limits are lower than logic:
  - 85 / 95 °C (early), 95 / 105 °C (later), against 105 °C for logic [thm-038].
  - Micron HBM3E: 0 to +105 °C [hbm-020].
  - Refresh doubles above the trip points [thm-027].

**Connects to**

- micro-bumps (power, signal, thermal, mechanical);
- the host HBM PHY (signal);
- TIM1 (thermal);
- the compute die through the lid, interposer and mold (thermal coupling).

**Counts:**

| Product | Stacks | Source |
|---|---|---|
| Ascend 910 | 4 | [prd-001] |
| H100 SXM5 | 5 active of 6 sites | [prd-011, prd-010] |
| MI300X | 8 | [prd-019] |
| Blackwell (press) | 8 | [prd-018] |

#### 3.5.3 I/O dies, dummy dies and mold

**I/O die**

- Ascend 910's "Nimbus" die is 168 mm² and modelled at 14 W [prd-003, thm-007].
- MI300 does it in 3D instead: four 6 nm I/O dies, each with two compute dies (XCDs) stacked on top [prd-019, prd-020].

**Dummy dies**

- Ascend 910 adds **two 110 mm² dummy silicon dies "to ensure mechanical uniformity"** [prd-001, prd-003]. That gives 8 dies and 1,228 mm² of silicon in total [prd-002].
- Our model leaves them out.

**Mold compound**

- The dies on the interposer wafer are underfilled, then encapsulated in molding compound or molded underfill [pkg-038].
- The gap between logic and HBM is mold-filled [thm-032].
- Gaps on Ascend 910 are 0.72 mm from the compute die to the HBM row, and 2 mm between HBMs [prd-004].
- k ≈ 0.96 W/mK for a standard epoxy molding compound [thm-024]. That makes the mold a weak lateral heat path.

### 3.6 Micro-bumps, hybrid bonds and underfill

**Micro-bumps** connect every top die to the interposer. They are copper pillars with solder caps.

| Item | Value | Source |
|---|---|---|
| Pitch, Xilinx/TSMC interposer test vehicle | 45 µm | [pkg-021] |
| Pitch, Virtex-7 SSIT | 45 µm | [pkg-018] |
| Pitch, HBM | 55 µm | [hbm-023] |
| Pitch, UCIe "advanced package" range | 25-55 µm | [hbm-041] |
| Pitch, Intel EMIB | 55 µm, scaled to 45 µm | [pkg-035] |
| Diameter | about 25 µm | [hbm-023, hbm-026] |
| Reflowed height (HBM1) | about 35 µm | [hbm-033] |
| Practical lower limit for solder micro-bumps | about 20 µm pitch | [hbm-029] |

**Hybrid bonding** (direct Cu-to-Cu plus dielectric) replaces bumps for 3D stacking:

- TSMC SoIC: below 10 µm pitch [pkg-010], on a roadmap of 9 → 6 → 3 → 0.9 µm [pkg-011].
- Intel Foveros Direct: 9 µm [pkg-037].
- UCIe-3D: 10 µm or less [hbm-043].
- For HBM it removes the gap fill entirely [hbm-030].

**Underfill**

- Epoxy, about 0.6 W/mK [thm-023].
- Buffers the CTE mismatch and protects the joints [pkg-030, pkg-005].
- TAP-2.5D draws epoxy underfill between the C4s, the micro-bumps and the chiplets [thm-005].

**Effective k of a bump layer:** about 14-95 W/mK (derived parallel estimate). Our model uses 124.6 (see `our_model_mapping.md`).

### 3.7 Interposer: silicon, organic RDL, or bridges

**Why it exists**

- Silicon wiring is about 20× denser than organic wiring, which enables more than 10,000 die-to-die connections [pkg-020]. Virtex-7 SSIT used 10K-30K [pkg-018].
- The interposer also buffers stress between the dies and the organic substrate [pkg-015].

**Silicon interposer (CoWoS-S class)**

- A passive silicon slab about **100 µm** thick [pkg-021, thm-029].
- **Cu TSVs** go through it. Virtex-7 SSIT used TSVs larger than 10 µm in diameter at 210 µm pitch [pkg-018].
- Its **BEOL wiring** sits on top:
  - 4 layers at 2 µm pitch on a 65 nm interposer [pkg-018, pkg-019];
  - thick copper "5Mi" on the 2021 CoWoS-S [pkg-014].
- Size up to 3.3× reticle, about 2,700 mm² [pkg-001]. The TAP-2.5D study used 45 × 45 mm [thm-006].
- It carries **embedded deep-trench capacitors** (eDTC / iCap) [pkg-002]: up to 340 nF/mm² in 40 × 40 µm cells (secondary report) [pkg-046].
- k ≈ 117-150 W/mK.

**Organic RDL interposer (CoWoS-R)**

- Polymer plus copper traces, 2/2 µm line/space at a 4 µm minimum pitch [pkg-003, pkg-004].

**Bridges (CoWoS-L LSI, Intel EMIB)**

- Small silicon bridges with sub-µm copper lines sit only under die edges [pkg-008, pkg-036].
- CoWoS-L reached 3.5× reticle in volume production in 2024 [pkg-007]. It can also embed stand-alone eDTCs under the SoC [pkg-009].

**Connects to:** micro-bumps above, C4 bumps below (power, signal, thermal, mechanical), and the eDTC (power).

### 3.8 C4 bumps and underfill

- **What and why:** the interposer's connection to the substrate. Every watt of power and every off-package signal passes through here.
- **Material:**
  - Cu C4 on CoWoS-S [pkg-013];
  - or a 40 µm copper pillar with a SnAg cap, or Pb-free 98.2Sn/1.8Ag bumps [pkg-029, pkg-054].
- **Geometry:**
  - Standard bumps are 60-100 µm high and 80-125 µm in diameter [pkg-028].
  - Pitch runs from 130 µm (InFO; flip-chip area-array minimum) [pkg-016, pkg-053] through 180 µm (Xilinx test vehicle) [pkg-021] to 210 µm (Virtex-7 SSIT) [pkg-018].
  - Substrate bump-pitch roadmaps reach 110 µm and then 90 µm [pkg-034].
- **k:** SAC305 is 58 W/mK [thm-025]; underfill about 0.6 W/mK [thm-023]. The layer averages about 14 W/mK (derived).

### 3.9 Package substrate and decoupling

**Structure**

- A glass-reinforced resin core sandwiched between ABF build-up layers of copper and dielectric [pkg-048].

**Dimensions**

| Item | Value | Source |
|---|---|---|
| Core thickness, conventional | 400-1,600 µm | [pkg-032] |
| Core thickness, thin | 150-250 µm | [pkg-032] |
| Build-up layers in volume | 9-10 per side | [pkg-031] |
| Build-up layers on roadmaps | 12-14 per side | [pkg-033, pkg-047] |
| Build-up, Virtex-7 SSIT (2011) | 4-2-4 | [pkg-018] |
| Line/space | 9/12 µm, heading to 6/6 µm | [pkg-031, pkg-034] |
| Body size | 90 × 90 mm (2026) to 130 × 130 mm (roadmap) | [pkg-033, pkg-047] |
| Body size, 2.5×-reticle InFO_oS in 2021 | 110 mm square | [pkg-017] |

**k (dielectrics):** core 0.8, prepreg 0.35, solder mask 0.24 W/mK [thm-015, thm-014, thm-013]. Copper planes raise the effective in-plane value; that is not quantified here.

**Decoupling**

- Interposer eDTC: see above.
- Board bypass capacitance of 3 mF or more under a 1,000 A processor [pkg-043].
- Substrate die-side and land-side capacitors are shown in `parts.json` as **unsourced placeholders**, low confidence.

### 3.10 BGA balls

- **Pitch:** 0.8-1.0 mm [pkg-022, pkg-018].
- **Ball diameter:** about 0.5-0.6 mm nominal [pkg-049, pkg-050].
- **Stand-off:** 0.31-0.6 mm [pkg-049, pkg-050].
- **Count:** a 55 mm body at 1.0 mm pitch holds 3,136 balls in a full array [pkg-027]. Larger AI substrates scale by area.
- **k:** SAC305 is 58 W/mK [thm-025].

### 3.11 Board and power delivery (VRM to die)

**The chain**

1. VRM
2. board copper planes
3. BGA
4. substrate planes and vias
5. C4
6. interposer TSVs
7. interposer wiring (with eDTC)
8. micro-bumps
9. die

This is the same path that HotSpot calls the "secondary" heat path [thm-012], and the same path Amkor describes from the active side of the die through the substrate [pkg-026].

**Numbers (VR-vendor article, medium confidence)**

- Core VDD as low as 0.7 V, ±5% [pkg-041].
- dI/dt of 2,000 A/µs or more [pkg-041].
- About 1,000 A continuous [pkg-043].
- HBM VDD 1.1-1.2 V [pkg-042]. HBM4 uses VDDQ 0.7-0.9 V and VDDC 1.0-1.05 V [hbm-008].
- 30 or more lateral VR phases, losing at least 50 W in board planes [pkg-044].
- Placing a VR **under** the package cut PDN impedance from 60 to 11 µΩ [pkg-045].

## 4. The links

### HBM PHY to HBM

- A PHY strip on the compute-die edge faces each stack.
- The bus runs across the interposer to the base-die PHY [hbm-025]. Cadence's PHY is "designed for optimized interposer routing" [hbm-040].
- **HBM3/3E:** 16 channels × 64 bits = 1,024 bits [hbm-002, hbm-039].
  - Up to 9.6 Gb/s per pin [hbm-011, hbm-038].
  - Samsung quotes 1,280 GB/s per stack [hbm-014].
- **HBM4:** 32 channels and 2,048 bits at 8 Gb/s, giving 2 TB/s [hbm-005, hbm-006].
- **Energy:** about 4.3 pJ/bit for HBM2E; about 20% lower for HBM3E; about 60% lower expected for HBM4 [hbm-027].

### Die to die

| Link | Figures | Source |
|---|---|---|
| NVIDIA NV-HBI (Blackwell) | 10 TB/s | [prd-015] |
| AMD MI300X XCD↔IOD | 2.1 TB/s | [prd-025] |
| AMD Infinity Fabric AP | 4.8 TB/s and 6 TB/s bisection | [prd-025] |
| UCIe-A (2.5D) | x64 lanes, 4-32 GT/s, ≤2 mm reach, 25-55 µm bumps, 165-1,317 GB/s per mm of shoreline, 0.25 pJ/b | [hbm-041…044] |
| UCIe-S (2D) | x16 lanes, 100-130 µm bumps, ≤25 mm reach, 0.5 pJ/b | [hbm-041…044] |

## 5. Heat, power and signal flows (summary)

| Flow | Path | Key numbers |
|---|---|---|
| Heat, primary (~95%) [thm-036] | active layer → bulk Si (710 µm) → TIM1 → lid → TIM2 → cold plate → coolant | Si about 5 K·mm²/W [pkg-051]; TIM1 1.5-4 K·mm²/W [pkg-051, thm-021]; cooler about 0.04 K/W at 1 kW [thm-039] |
| Heat, secondary (~5%) | active layer → BEOL → micro-bumps → interposer → C4 → substrate → BGA → board | dominated by the organic substrate (k 0.35-0.8 [thm-014, thm-015]); one model lumps the PCB side as 20 K/W [thm-035] |
| Heat, HBM | base die → 8-16 bond layers → top die → TIM1 | about 3.8 K·mm²/W per bond [thm-031]; about 9× a logic die overall (derived) |
| Heat, coupling | logic → lid/spreader → HBM (dominant in one study [thm-026]); logic → interposer → HBM (Si couples more than glass [thm-048]); logic → mold → HBM (weak, k ≈ 1 [thm-024]) | gap 0.72-2 mm [prd-004] |
| Power | VRM → board → BGA → substrate → C4 → TSV → interposer wiring (eDTC) → micro-bumps → die | ≥0.7 V, ~1,000 A, ≥3 mF [pkg-041, pkg-043]; eDTC 340 nF/mm² [pkg-046] |
| Signal, memory | HBM PHY → micro-bumps → interposer → micro-bumps → base die → TSVs → DRAM | 1,024 / 2,048 bits; 0.8-2 TB/s per stack [hbm-001, hbm-005] |
| Signal, die-to-die | D2D PHY → micro-bumps → interposer wiring or bridge → micro-bumps → D2D PHY | up to 10 TB/s [prd-015] |
| Signal, off-package | die → micro-bumps → interposer wiring → TSV → C4 → substrate → BGA → board | — |

## 6. Real products used as anchors

| Product | Compute silicon | HBM | Power | Packaging facts in this pack |
|---|---|---|---|---|
| Huawei Ascend 910 (Hot Chips 31) | Vitruvian 456 mm², 7+ nm EUV; Nimbus I/O 168 mm² [prd-003, prd-007] | 4 stacks (96 mm² each) [prd-003] | 350 W [prd-005] | 8 dies including 2 dummy; 1,228 mm² of silicon; 0.72 / 2 mm gaps [prd-001, prd-002, prd-004]. The product image looks lidded (marketing render, low confidence). |
| NVIDIA H100 SXM5 | GH100, 814 mm², 4N, 80 B transistors [prd-009] | 5 of 6 sites, 80 GB, 3.35 TB/s [prd-011, prd-013] | 700 W [prd-012] | Packaging type not stated in the sources captured |
| NVIDIA Blackwell / Blackwell Ultra | 2 reticle-limited dies, 208 B transistors, 4NP, NV-HBI 10 TB/s [prd-014, prd-015] | 8 stacks (press) [prd-018]; Blackwell Ultra 288 GB, 8 TB/s [prd-016] | — | GB200 NVL72 liquid-cooled [prd-017] |
| AMD MI300X / MI325X | 8 XCDs on 4 IODs (6 nm), 153 B transistors [prd-019, prd-020, prd-024] | 8 × 24 GB HBM3 at 5.2 Gb/s, 5.3 TB/s; MI325X 256 GB HBM3E, 6.0 TB/s [prd-021, prd-023] | 750 W / 1,000 W [prd-022, prd-023] | Hybrid-bond pitch not captured |

## 7. Biggest uncertainties and conflicts

1. **HBM geometry differs by generation and vendor.**
   - Footprints: 7.75 × 11.87 (HBM2) [hbm-022], 11 × 11 (Micron HBM3E) [hbm-018], about 10.5 × 12 (press) [hbm-037].
   - HBM4 height: 775 µm (reported JEDEC) [hbm-009] against about 950 µm for 16-high in the press [hbm-037].
   - Micro-bump "pitch": 55 µm FCR [hbm-023] against 96 µm "staggered" [hbm-026].
   - Per-die thickness has only a model value (35 µm) plus a relative claim (40% thinner) [thm-030, hbm-010].
   - HBM TSV diameter is not captured from a primary source.
2. **Thicknesses we could not source:** lid, substrate build-up layers, total substrate stack, stiffener, cold plate. `parts.json` marks every display value for these as `render_hint` with its basis.
3. **Interface and cooler resistances come from test structures** (TSMC micro-cooler TIMs [pkg-051], an Intel test vehicle with dielectric coolant [thm-039]), not from AI products. They are magnitudes only.
4. **Coupling physics is contested.** One study puts most logic→HBM coupling in the lid/spreader [thm-026]; another highlights the interposer [thm-048]. Both are single studies.
5. **Product packaging details** are largely unpublished by vendors: for example, whether a given product is lidded, and its interposer size. This pack makes no such claim beyond what is cited.
6. **Secondary sources** are marked medium confidence and fill specific gaps: TrendForce, Tom's Hardware, ServeTheHome, IEEE Spectrum, the Vertiv and Vicor articles, the Krayden page, and a blog report of the TSMC iCap paper.
7. **Excluded material:** no MicroDuck or Pollen material is used.
