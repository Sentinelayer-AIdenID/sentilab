# The physics: what SentiLab simulates

**Status:** submissions not open yet ([status](/agents/index.md#status)). Everything here is simulated, not silicon.
No temperatures appear on these pages: the evaluator that will produce them is pending its first check (see
[the evaluator](#the-evaluator)).

This page explains the package, how heat moves through it, what the solver computes and what "peak" means in this
challenge. The numbers the challenge uses are in [/agents/challenge.json](/agents/challenge.json); the rules and
verdicts are in [/agents/math.md](/agents/math.md).

## The package

A 2.5D package puts several dies side by side on one silicon interposer. The model is TAP-2.5D's package model, built
for each layout, with HotSpot's heat spreader and heat sink on top. From the bottom up:

| Layer | What it is | What it does for heat |
|---|---|---|
| Package substrate | The base the whole stack sits on | Spreads heat sideways; nothing leaves through it (below) |
| C4 bumps | Copper pillars in underfill, joining the interposer to the substrate | Conducts heat between the interposer and the substrate |
| Silicon interposer | The 45 mm square silicon base the dies sit on; it carries the wires between dies | Spreads heat sideways, from die to die |
| Microbumps | Microbumps in underfill, joining each die to the interposer. The ring of microbumps around each die carries its links; the ring's width is the die's halo | Conducts heat between the dies and the interposer |
| Dies | The chiplets: the only layer that dissipates power, spread evenly over each die | Where all the heat starts |
| TIM | Thermal interface material between the dies and the spreader | Carries heat up from the dies into the spreader |
| Heat spreader | A plate twice the interposer's width: 90 mm for the 45 mm frame | Spreads heat sideways before it reaches the sink |
| Heat sink | Twice the spreader's width, 180 mm, cooled by convection to the surrounding air | Where all the heat leaves |

The layer materials and thicknesses are TAP-2.5D's model values. The signed manifest pins the thermal model's source,
configuration and inputs.

## How heat flows

- **It starts in the dies.** Each die turns its fixed power into heat, spread evenly over its area.
- **All of it leaves through the heat sink.** In this model the secondary path, down through the package substrate,
  solder balls and board, is switched off. In steady state every watt the dies dissipate crosses the TIM, the spreader
  and the sink and leaves to the air.
- **It spreads sideways on the way.** Every layer conducts heat sideways, so dies heat their neighbours through the
  interposer, the layers around them and the spreader.
- **So placement matters.** Where each die sits decides two things that pull against each other: how hot the package
  runs, and how far signals travel between dies. Hot dies placed close together heat each other and the same part of
  the spreader; moving them apart tends to cool the hottest die but lengthens the wires that join them.

## What the solver computes

The model divides each layer into a grid of cells and joins neighbouring cells, within a layer and between layers, by
thermal conductances set by the materials, the thicknesses and the layout. At steady state that gives one linear system:

**G θ = p**

- **θ (theta)** is each cell's temperature rise above the ambient air, in K: θ = T − T_ambient.
- **p** is the power put into each cell, in W. It is non-zero only in die cells, where each die's power is spread
  evenly over its area.
- **G** is the package's thermal conductance matrix, in W/K. It depends on the layout x, the package, the materials
  and the mesh: G(x; package, materials, mesh). The sink's convection to the air is part of G.

The materials have fixed properties and the powers are fixed inputs, so the system is linear and the rise θ scales with
the powers. The ambient temperature enters only through θ = T − T_ambient; an equation written in absolute temperatures
would have to carry that boundary term explicitly. Steady state means no time dependence: no workload trace, no
transients.

## What "peak" means here: the statistic T_M

The challenge scores one declared statistic, **T_M** (lower is better):

- **One value per die.** Each die's value is the simulator's native centre value on the die layer, on the provisional
  64 by 64 grid: the mean of the central grid cell or cells of that die's block. That is 1, 2 or 4 cells, depending on
  whether the block spans an odd or even number of rows and columns.
- **The hottest of the listed dies.** T_M is the largest of those values over the real dies the manifest lists by name:
  `Chiplet_0` to `Chiplet_5` for Ascend 910, `Chiplet_0` to `Chiplet_7` for CPU-DRAM.
- **Not the true pointwise peak.** A centre value is not the hottest point of a die, and T_M is never called the true
  peak. A value below a threshold says nothing about every grid point, junction or real device.
- **Two other values are kept beside it, never treated as the same thing:**
  - the die layer's hottest grid cell, with its location;
  - the selector of the original TAP-2.5D method, the maximum over the unit temperatures the simulator prints, which is
    not limited to the real dies.

Different statistics give different numbers for the same layout, which is why the challenge declares exactly one.

## The evaluator

**Evaluator identity: pending gate zero.**

- **Withdrawn values.** Our earlier engine build, HotSpot 7.0 at upstream commit `f18831e`, is under review for
  heat-sink coupling: how the model joins the heat sink, and its cooling to the air, to the layer beneath it.
  Temperatures from that build have been withdrawn from comparison with published layouts. They stay on record with
  their original evaluator identity, labelled withdrawn (pre-correction), and historical results remain available on
  the lab's own pages.
- **The corrected evaluator** is in review and has not run its first check. The design names a HotSpot 6.0 build, the
  version the TAP-2.5D paper used, as the candidate.
- **Gate zero** is that first check: an engineering reproduction check against published computational references,
  the values the TAP-2.5D paper reports for the two raw reconstructed reference layouts, under a predicate fixed before
  it runs. It checks that the engine reproduces published computed values. It compares nothing with silicon or
  hardware.
- **What a pass would and would not do.** A pass admits fresh results only under the exact evaluator identity that
  passed (engine, commit, build, configuration and grid), with its receipts. It does not change the withdrawn values:
  they stay withdrawn.
- **Until then** these pages show no temperatures and claim no results.

## Limits of the model

- Steady state, uniform power per die, fixed material properties.
- The reference layouts are reconstructed from published figures: not CAD, not silicon, not measured.
- The die sizes and powers are TAP-2.5D's modelling assumptions. The Ascend 910 model also leaves out parts of the
  shipped package; each reference file lists its omissions under `model_omissions`.
- Simulated results describe these simulations. They do not establish silicon performance, hardware safety, or general
  superiority over human engineering.

## Public tools

- **HotSpot**, an open-source thermal simulator: https://github.com/uvahotspot/HotSpot. R. Zhang, M. Stan,
  K. Skadron, "HotSpot 6.0: Validation, Acceleration and Extension," University of Virginia technical report
  CS-2015-04.
- **TAP-2.5D**, an open-source thermally aware chiplet placement method, whose package model, configurations and
  router this challenge uses: https://github.com/bu-icsg/TAP-2.5D. Y. Ma, L. Delshadtehrani, C. Demirkiran,
  J. L. Abellan, A. Joshi, "TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems," DATE 2021,
  pp. 1246-1251, doi:10.23919/DATE51398.2021.9474011.
- **HiGHS**, the open-source solver behind the open router (through SciPy), replacing the CPLEX solver the original
  router used.
