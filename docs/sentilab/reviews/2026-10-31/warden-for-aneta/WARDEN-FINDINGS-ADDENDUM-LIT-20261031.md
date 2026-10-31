# Warden findings: literature addendum (2026-10-31, after the freeze; adds facts and changes no frozen claim)
Tags: [V] read at source; [D] my own arithmetic or digitisation, not stated in the source.

## A. A third calibration suspect for SLAB-049: the METRIC
- [V] TAP-2.5D's reported "peak" is the maximum over block-centre temperatures: HotSpot `grid_map_mode center` (TAP repo configs and code).
- [V] Our oracle's J is the maximum over every cell of the chip-layer grid (tap_oracle_worker.py:91-93). A grid maximum is always ≥ a centre maximum.
- [V] TAP also used HotSpot 6.0 with Meng's 3D extension, grid 64, spreader 2× interposer, sink 2× spreader, `r_convec` scaled as 0.1·0.06²/s_sink² (about 0.011 K/W at 45 mm), ambient 45 °C and no secondary path.
- So CAL-COUPLING should report BOTH metrics (grid max and block-centre max) for the old and new coupling, at grid 64 and 45 mm, before attributing the 2.3× gap.

## B. Independent coordinates for the Ascend 910 original (cross-check for SLAB-048)
- [D] Extracted from TAP Fig. 6(a)'s vector rectangles (PDF p.6). 45 mm frame, origin bottom-left, centres to about ±0.2 mm. Recovered die sizes match Table II within 0.1 mm.
  - Compute die: centre (17.1, 22.6), 31.4 wide × 14.5 high.
  - Nimbus: centre (38.3, 22.5), 10.5 wide × 16 high.
  - HBM (11.87 wide × 7.75 high): (7.3, 33.9), (21.3, 33.9), (7.3, 11.2), (21.3, 11.2).
  - HBM–HBM gap 2.1 mm; other gaps 0.2–0.3 mm; NO dummy dies.
  - Widths and heights are swapped relative to our config for the compute die and the HBMs, so rotation is required.
- [V] Paper results: original 75.48 °C / 16,426 mm routed wire; TAP 75.47 / 16,597; compact 75.13 / 23,794.
  - CPU-DRAM original 115.94 / 67,686 → TAP 94.89 / 216,064 (93.89 / 138,956 with the alternate link type).

## C. The real package (Huawei Hot Chips 31, slides 33/37/38)
- [V] 8 dies: Vitruvian 456 mm², Nimbus 168 mm², 4 HBM2 at 96 mm², 2 dummy dies at 110 mm²; total 1228 mm².
- [V] HBMs sit about 2 mm apart above and below the left of the compute die. Nimbus is at the right end with a dummy above and below. The compute die is 31.25 × 14.6 mm.
- [V] Spec 350 W. The launch release says it shipped at 310 W maximum. TAP omits the dummies. Neither the interposer size nor per-die power is public.

## D. Search effort and accuracy caveats
- [V] Paper annealing decay 0.95 (about 4,500 steps, best of 5) vs the repo default 0.8 (about 1,050 steps). Use the paper's for any "TAP baseline" claim.
- [V] HotSpot vs FEM in 2.5D: mean absolute error 1.01–7.39 °C (MFIT, arXiv 2410.09188). HotSpot 6.0 was validated only on a monolithic chip and "underestimates lateral heat transfer". So compare DIFFERENCES within one frozen setup.
- [V] STAMP-2.5D: applying an intra-die power map to the compute die raised the peak only 0.18–1.45 °C, and the ranking didn't change.

Sources: TAP-2.5D https://people.bu.edu/joshi/files/Ma_TAP-2.5D-DATE2021.pdf ; repo https://github.com/bu-icsg/TAP-2.5D ; Hot Chips 31 https://www.old.hotchips.org/hc31/HC31_1.11_Huawei.Davinci.HengLiao_v4.0.pdf ; RLPlanner https://arxiv.org/abs/2312.16895 ; TACPAs https://arxiv.org/abs/2504.03808 ; STAMP-2.5D https://arxiv.org/abs/2504.21140 ; HotSpot 6.0 TR https://www.cs.virginia.edu/~skadron/Papers/HotSpot60_TR.pdf ; MFIT https://arxiv.org/abs/2410.09188
