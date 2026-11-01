// The one case the agent door serves, CPU-DRAM (TAP-2.5D Fig. 5a), and the values agents see about it. Every number
// here comes from a pinned record; web/test/door-case.test.mjs checks the dies, powers, connections and rules against
// sundai_tap/configs/sys_micro150_45mm.cfg and sundai_hotspot/tap_oracle.py, and the reference layout against
// web/public/agents/references/micro150-tap25d-fig5a-snap0p5.json.
//   - Dies, powers, connections, lattice, body gap, rotation: sundai_tap/configs/sys_micro150_45mm.cfg (sha256 de6e3edb…).
//   - Halos (microbump rings) 180 and 135 um: TAP-2.5D's own (the public reference case af66bcfc, cases.B.chiplets).
//   - Edge clearance 500 um including the halo: tap_oracle.py TAP_MARGIN_MM (TAP's g/2 edge strips, g = 1 mm).
//   - Rotations: CPU 0 or 90 degrees, DRAM 0 only (a square die has one footprint; AGENT-DOOR Amendment 1 item 4).
//   - Board metric and reference statistics: AGENT-DOOR Amendment 2 (root #57454).
//   - Published points: the TAP-2.5D paper (pdf sha256 b209f51a…), Sec. IV-B, p. 5: the original placement at 115.94 C
//     and 67,686 mm; the TAP-2.5D solution (c) at 94.89 C and 216,064 mm.
//   - Scorer: HotSpot 6.0, grid 64, block-centre map, binary 751b357f…, source merge 1575556d. Gate zero's status and
//     numbers are read from root's record, web/public/agents/evidence.json, never restated here.
// A module of its own because worker.js may export nothing but its default handler.

export const CASE_ID = "cpu-dram";
export const FRAME_UM = 45000;
export const LATTICE_UM = 500;
export const BODY_GAP_UM = 100;
export const EDGE_CLEARANCE_UM = 500;
export const LATTICE_STEPS = FRAME_UM / LATTICE_UM;   // 90: a centre index runs 0..90 inside the frame

const CPU = Object.freeze({ kind: "CPU", w: 8250, h: 9000, power_w: 150, halo: 180, rot_deg: Object.freeze([0, 90]) });
const DRAM = Object.freeze({ kind: "DRAM", w: 8750, h: 8750, power_w: 20, halo: 135, rot_deg: Object.freeze([0]) });

// Catalogue order: C0..C3 are Chiplet_0..3, D0..D3 are Chiplet_4..7. w is along x and h along y at 0 degrees.
export const DIES = Object.freeze(["C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3"].map((id, index) =>
  Object.freeze({ id, index, unit: `Chiplet_${index}`, ...(index < 4 ? CPU : DRAM) })));

// Wires between dies (the cfg's connections), symmetric, in catalogue order. The wire proxy counts each unordered
// pair once: 5,120 wires.
export const CONNECTIONS = Object.freeze([
  [0, 256, 0, 256, 1024, 0, 0, 0],
  [256, 0, 256, 0, 0, 1024, 0, 0],
  [0, 256, 0, 256, 0, 0, 1024, 0],
  [256, 0, 256, 0, 0, 0, 0, 1024],
  [1024, 0, 0, 0, 0, 0, 0, 0],
  [0, 1024, 0, 0, 0, 0, 0, 0],
  [0, 0, 1024, 0, 0, 0, 0, 0],
  [0, 0, 0, 1024, 0, 0, 0, 0],
].map((row) => Object.freeze(row)));

// The legal 0.5 mm snapped reference (engineering variant, rounded from the raw figure, no repair moves), as a compact
// layout: a starting point, not an improvement.
export const SNAPPED_REFERENCE = "36.35.0,54.35.0,54.55.0,36.55.0,17.35.0,73.35.0,73.55.0,17.55.0";

export const SCORER = Object.freeze({
  label: "simulated, not silicon",
  engine: "HotSpot 6.0",
  grid: 64,
  readout: "block-centre map",
  binary_sha256: "751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6",
  source_merge: "1575556d",
});

// The one board statistic (Amendment 2): score, replay, board and captions all use it.
export const BOARD_METRIC = Object.freeze({
  metric_id: "max_chiplet_centre_cell_mean_C",
  definition: "For each real chiplet (Chiplet_0..7), the mean of its 1, 2 or 4 central HotSpot 6.0 grid-64 cells; then the maximum over the chiplets.",
  unit: "C",
  precision_K: 0.01,
  rounding: "Display rounding is separate from comparisons.",
  reference_binding: Object.freeze({ layout: "raw", value_C: 115.935 }),
  snapped_reference_value_C: null,
});

// Other statistics of the raw reference layout under the same scorer: never the board metric.
export const REFERENCE_STATISTICS = Object.freeze({
  label: "Other statistics of the raw reference layout, same scorer. Never the board metric.",
  layout: "raw",
  native_all_block_max_C: 115.93,
  active_layer_peak_C: 119.07,
  active_guard: "strictly < 119.07",
});

export const WIRE_PROXY = Object.freeze({
  definition: "Weighted-mean Manhattan distance between die centres over the connection matrix, each unordered pair once (5,120 wires).",
  unit: "mm",
  references: Object.freeze([
    Object.freeze({ layout: "raw", label: "reference only, off the lattice", value_mm: 9.38487 }),
    Object.freeze({ layout: "snapped", label: "legal snapped reference", value_mm: 9.5 }),
  ]),
  rule: "Never pair the snapped geometry with the raw temperature.",
});

// The paper's own points (routed wire and the paper's temperature): a labelled reference block, not on the board's
// scales.
export const PUBLISHED = Object.freeze({
  label: "Published points from the paper: routed wire and the paper's temperature. Reference only; not on this board's metric or proxy scale.",
  source: "TAP-2.5D (Ma et al., DATE 2021), Sec. IV-B, CPU-DRAM",
  temperature_statistic: "the paper's selector: maximum over every HotSpot block",
  points: Object.freeze([
    Object.freeze({ name: "original", figure: "5(a)", published_temperature_C: 115.94, published_routed_wire_mm: 67686 }),
    Object.freeze({ name: "TAP-2.5D", figure: "5(c)", published_temperature_C: 94.89, published_routed_wire_mm: 216064 }),
  ]),
});

// SentiLab's purposes on the wall, in the shape of the gate's intent list (id, label). Of a purpose, only its id is
// ever recorded.
export const PURPOSES = Object.freeze([
  Object.freeze({ id: "place-chiplets", label: "place chiplets: propose a CPU-DRAM layout for the scorer" }),
  Object.freeze({ id: "review", label: "review the board and the results" }),
  Object.freeze({ id: "read", label: "read about the challenge" }),
]);
export const PURPOSE_IDS = Object.freeze(PURPOSES.map((purpose) => purpose.id));
