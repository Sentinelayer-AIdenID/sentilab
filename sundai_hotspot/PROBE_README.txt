Sund ai chiplet research probe, 2026-10-18

What was actually run
---------------------
Compiled unmodified UVA HotSpot source at commit
f18831e48cef5d62580585cca0d7fab6c71bc3cc using make -j4, GCC, no SuperLU.
Used unmodified TAP-2.5D thermal/floorplan generation at commit
3a3f4e5a4d019b2d9cda1f72d8d1755238845dbb and its public
configs/sys_ascend910.cfg geometry, chiplet power and connectivity.

The original TAP license remains in ../sundai_tap/LICENSE. The original
HotSpot license remains here in LICENSE. Retain those notices with source.

The eight completed experiments use four HAND-AUTHORED legal placements,
each at 16x16 and 32x32 thermal grid resolution, with unchanged 350 W total
chiplet power and the source material/cooling setup at 45 C ambient.
These are not AI-generated designs, not evidence of Jev efficacy, not a
trained thermal surrogate, and not commercial-chip manufacturing signoff.

Reproduce
---------
Keep sundai_hotspot and sundai_tap as sibling directories. In sundai_hotspot,
build HotSpot with SuperLU and run the oracle contract tests and all probes:
  make -j4 SUPERLU=1
  python -m unittest -q test_tap_oracle.py
  python run_tap_probe.py --report probe_results/report.json

You can run a subset by naming cases, and set a different solver timeout or
report destination:
  python run_tap_probe.py baseline_center right_shift_2mm --solver-timeout 45
  python run_tap_probe.py --report probe_results/my-run.json

Each Design is checked for the published chiplet catalog, TAP-generated
microbump halos, the 0.5 mm interposer margin, halo overlap, and the 1 mm
placement grid before a worker starts. Each worker has a fresh temporary
directory, starts with the TAP tree as its working directory, and runs one
bounded HotSpot process. No process calls os.chdir. The driver returns the
chip-layer heatmap, peak, candidate and problem hashes, generated-input hashes,
and a connectivity-weighted Manhattan center-distance proxy. This is not CPLEX
routed wirelength and does not claim real routing feasibility. Reports use a
unique timestamped filename by default; pass --report to choose a destination.

Evidence
--------
probe_results/combined_report.json contains the eight original completed
runs, exact solver commands, input hashes and runtime measurements.
probe_results/published_data_probe.png plots actual computed thermal maps.
Each case directory contains generated thermal inputs and raw solver output.
The source-based simulations ran in around 2.3-2.5 seconds at 16x16 and
10.4-23.3 seconds at 32x32 in this shared runtime. Those are individual
observations, not a performance distribution or apples-to-apples latency
claim against Jev.

An initial 64x64 baseline run exceeded a 45-second timeout. It did not
complete, and it is not included among the eight completed results.

Key finding
-----------
Moving the hot chiplet from x=21 to x=25 mm reduced the 32x32 computed
peak from 119.78 C to 118.89 C while increasing the wire proxy by 3.82%.
At 32x32, x=27 appears 0.04 C cooler still; at 16x16, x=25 wins instead.
This is a direct demonstration of unresolved mesh sensitivity. Do not
claim the 0.04 C margin is a reliable physical improvement. A stronger
study needs mesh convergence, calibrated package parameters, representative
workloads, and independent solver or physical validation.

Primary sources and constraints are in research_notes.json.
